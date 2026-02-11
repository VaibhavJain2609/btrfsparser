#!/usr/bin/env python3
"""
BTRFS Filesystem Parser
Parses BTRFS filesystem from image file and extracts file information.

Usage:
  python btrfs_parser.py image.img                    # Console output
  python btrfs_parser.py image.img -o json            # JSON to stdout
  python btrfs_parser.py image.img -o csv -f out.csv  # CSV to file
  python btrfs_parser.py image.img --info-only        # Just show superblock info
  python btrfs_parser.py image.img -p 4198400         # Partition at sector 4198400
  python btrfs_parser.py image.img -a                 # Auto-detect BTRFS partitions
  python btrfs_parser.py image.img --recent 10        # 10 most recently accessed files
  python btrfs_parser.py image.img --extract          # Interactive file extraction
"""

import argparse
import os
import sys

from superblock import read_superblock, print_superblock_info
from chunk import parse_sys_chunk_array, read_chunk_tree, ChunkMap
from filesystem import find_fs_tree_root, parse_filesystem, extract_files, find_all_subvolumes, parse_all_subvolumes, parse_checksum_tree, read_file_data, FileSystem
from output import to_json, to_csv, to_console, to_tree
from statistics import calculate_statistics, write_statistics_json
from partition_detect import detect_btrfs_partitions, format_partition_list


def parse_offset(value: str) -> int:
    """Parse offset value - supports decimal, hex (0x), or sector notation (s)."""
    value = value.strip().lower()
    if value.endswith('s'):
        # Sector notation (512 bytes per sector)
        return int(value[:-1]) * 512
    elif value.startswith('0x'):
        return int(value, 16)
    else:
        return int(value)


def derive_stats_filename(file_path: str) -> str:
    """Generate statistics filename from a given file path.

    Args:
        file_path: Path to image or output file

    Returns:
        Path to statistics file in same directory

    Examples:
        /path/to/image.img -> /path/to/image_stats.json
        output.json -> output_stats.json
        /path/to/output.json -> /path/to/output_stats.json
    """
    from pathlib import Path
    p = Path(file_path)
    stats_filename = f"{p.stem}_stats.json"
    return str(p.parent / stats_filename)


def interactive_extract(image_path, entries, fs, chunk_map):
    """Interactive file extraction loop.

    Allows user to search for files, select them, and extract to a destination.
    """
    # Build lookup from entries (files only)
    file_entries = [e for e in entries if e.type == 'file']

    if not file_entries:
        print("No files available for extraction.", file=sys.stderr)
        return

    print("\n=== File Extraction Mode (type 'exit' to quit) ===\n")

    while True:
        try:
            search = input("Search for file: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting extraction mode.")
            break

        if search.lower() == 'exit':
            print("Exiting extraction mode.")
            break

        if not search:
            continue

        # Case-insensitive substring match on path
        matches = [e for e in file_entries if search.lower() in e.path.lower()]

        if not matches:
            print(f"No files matching '{search}'.")
            continue

        # Display numbered results
        print(f"\nFound {len(matches)} file(s):")
        for i, entry in enumerate(matches, 1):
            size_str = _format_size(entry.size)
            print(f"  {i}. {entry.path} ({size_str})")

        # Get user selection
        try:
            selection = input("\nSelect file number(s) (comma-separated, or 'back'): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting extraction mode.")
            break

        if selection.lower() in ('back', ''):
            continue

        # Parse selected indices
        selected = []
        for part in selection.split(','):
            part = part.strip()
            try:
                idx = int(part)
                if 1 <= idx <= len(matches):
                    selected.append(matches[idx - 1])
                else:
                    print(f"  Skipping invalid selection: {idx}")
            except ValueError:
                print(f"  Skipping invalid input: {part}")

        if not selected:
            continue

        # Get destination directory
        try:
            dest = input("Destination directory: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting extraction mode.")
            break

        if not dest:
            dest = '.'

        # Create destination if it doesn't exist
        os.makedirs(dest, exist_ok=True)

        # Extract selected files
        with open(image_path, 'rb') as f:
            for entry in selected:
                if entry.unique_inode is None or entry.unique_inode not in fs.extents:
                    print(f"  [SKIP] {entry.name} - no extent data available")
                    continue

                try:
                    extents = fs.extents[entry.unique_inode]
                    data = read_file_data(f, extents, chunk_map, entry.size)
                    out_path = os.path.join(dest, entry.name)

                    # Avoid overwriting: append number if file exists
                    if os.path.exists(out_path):
                        base, ext = os.path.splitext(entry.name)
                        counter = 1
                        while os.path.exists(out_path):
                            out_path = os.path.join(dest, f"{base}_{counter}{ext}")
                            counter += 1

                    with open(out_path, 'wb') as out_f:
                        out_f.write(data)
                    print(f"  [OK] {entry.path} -> {out_path} ({_format_size(len(data))})")
                except Exception as e:
                    print(f"  [ERROR] {entry.name}: {e}")

        print()  # Blank line before next search


def _format_size(size):
    """Format byte size to human-readable string."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.1f} GB"


def main():
    parser = argparse.ArgumentParser(
        description='Parse BTRFS filesystem from image file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s image.img                         # Console output (partition at start)
  %(prog)s image.img -a                      # Auto-detect BTRFS partitions
  %(prog)s image.img -p 4198400s             # Partition at sector 4198400
  %(prog)s image.img -p 0x80280000           # Partition at hex offset
  %(prog)s image.img -p 2149580800           # Partition at byte offset
  %(prog)s image.img -o json                 # JSON to stdout
  %(prog)s image.img -o csv -f out.csv       # CSV to file
  %(prog)s image.img --info-only             # Just show superblock info
  %(prog)s image.img -o tree                 # Tree view
  %(prog)s image.img --recent 10              # 10 most recently accessed files
  %(prog)s image.img --recent 5 -o json       # Recent files as JSON
  %(prog)s image.img --extract                # Interactive file extraction
  %(prog)s image.img --recent 10 --extract    # Recent files + extraction

Offset formats:
  4198400s    - Sector number (multiplied by 512)
  0x80280000  - Hexadecimal byte offset
  2149580800  - Decimal byte offset
'''
    )

    parser.add_argument('image', help='Path to BTRFS image file (.img)')
    parser.add_argument('-a', '--auto-detect', action='store_true',
                        help='Automatically detect BTRFS partitions (prompts if multiple found)')
    parser.add_argument('-p', '--partition-offset',
                        type=str, default='4198400s',
                        help='Partition start offset (sectors with "s" suffix, hex with "0x", or bytes)')
    parser.add_argument('-o', '--output',
                        choices=['console', 'json', 'csv', 'tree'],
                        default='console',
                        help='Output format (default: console)')
    parser.add_argument('-f', '--file',
                        help='Output file path (default: stdout)')
    parser.add_argument('--info-only', action='store_true',
                        help='Only show superblock info, do not parse files')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')
    parser.add_argument('-r', '--recent', type=int, metavar='N',
                        help='Show N most recently accessed files (sorted by atime)')
    parser.add_argument('-e', '--extract', action='store_true',
                        help='Interactive file extraction mode')

    args = parser.parse_args()

    try:
        # Handle automatic partition detection
        partition_offset = None

        if args.auto_detect:
            if args.verbose:
                print(f"Scanning {args.image} for BTRFS partitions...", file=sys.stderr)

            partitions = detect_btrfs_partitions(args.image)

            if not partitions:
                print("Error: No BTRFS partitions detected in image", file=sys.stderr)
                return 1

            if len(partitions) == 1:
                # Single partition found, show it to user
                print(f"Found 1 BTRFS partition:", file=sys.stderr)
                print(f"  {partitions[0]}", file=sys.stderr)
                print(file=sys.stderr)
                partition_offset = partitions[0].offset
            else:
                # Multiple partitions found, prompt user
                print("Detected multiple BTRFS partitions:", file=sys.stderr)
                print(format_partition_list(partitions), file=sys.stderr)
                print(file=sys.stderr)

                while True:
                    try:
                        choice = input("Select partition number to parse: ").strip()
                        selected_index = int(choice)

                        # Find partition with matching index
                        selected = None
                        for p in partitions:
                            if p.index == selected_index:
                                selected = p
                                break

                        if selected:
                            partition_offset = selected.offset
                            print(f"Selected: {selected}", file=sys.stderr)
                            print(file=sys.stderr)
                            break
                        else:
                            print(f"Invalid selection. Please choose from: {[p.index for p in partitions]}", file=sys.stderr)
                    except (ValueError, EOFError, KeyboardInterrupt):
                        print("\nError: Invalid input or interrupted", file=sys.stderr)
                        return 1

            # Ask for confirmation before parsing
            try:
                confirm = input("Proceed with parsing? [Y/n]: ").strip().lower()
                if confirm and confirm not in ['y', 'yes']:
                    print("Parsing cancelled.", file=sys.stderr)
                    return 0
            except (EOFError, KeyboardInterrupt):
                print("\nParsing cancelled.", file=sys.stderr)
                return 0
        else:
            # Use manual partition offset
            partition_offset = parse_offset(args.partition_offset)

        if args.verbose:
            if partition_offset > 0:
                print(f"Partition offset: {partition_offset} bytes (0x{partition_offset:x})", file=sys.stderr)

        # Step 1: Read superblock
        if args.verbose:
            print(f"Reading superblock from {args.image}...", file=sys.stderr)

        sb = read_superblock(args.image, partition_offset)

        if args.info_only:
            print_superblock_info(sb)
            return 0

        if args.verbose:
            print_superblock_info(sb)
            print(file=sys.stderr)

        # Step 2: Build chunk map from sys_chunk_array
        if args.verbose:
            print("Parsing initial chunk map from sys_chunk_array...", file=sys.stderr)

        chunk_map = parse_sys_chunk_array(
            sb.sys_chunk_array,
            sb.sys_chunk_array_size
        )
        # Set partition offset for physical address translation
        chunk_map.partition_offset = partition_offset

        if args.verbose:
            print(f"  Found {len(chunk_map)} initial chunks", file=sys.stderr)

        # Step 2b: Read full chunk tree to get all chunk mappings
        if args.verbose:
            print("Reading full chunk tree...", file=sys.stderr)

        with open(args.image, 'rb') as f:
            chunk_map = read_chunk_tree(f, sb.chunk_root, chunk_map, sb.nodesize)

        if args.verbose:
            print(f"  Total chunks after reading chunk tree: {len(chunk_map)}", file=sys.stderr)

        # Step 3: Find all subvolumes
        if args.verbose:
            print("Finding subvolumes...", file=sys.stderr)

        with open(args.image, 'rb') as f:
            subvolumes = find_all_subvolumes(f, sb, chunk_map)

            if args.verbose:
                print(f"  Found {len(subvolumes)} subvolumes:", file=sys.stderr)
                for objid, name, bytenr in subvolumes:
                    print(f"    - {name} (id={objid}, root=0x{bytenr:x})", file=sys.stderr)

            # Step 4: Parse all subvolumes
            if args.verbose:
                print("Parsing all subvolumes...", file=sys.stderr)

            fs = parse_all_subvolumes(f, sb, chunk_map)

            if args.verbose:
                print(f"  Found {len(fs.inodes)} total inodes", file=sys.stderr)

            # Step 4b: Parse checksum tree
            if args.verbose:
                print("Parsing checksum tree...", file=sys.stderr)

            fs.checksums = parse_checksum_tree(f, sb, chunk_map)

            if args.verbose:
                print(f"  Found {len(fs.checksums)} checksum ranges", file=sys.stderr)

        # Step 5: Extract file entries
        with open(args.image, 'rb') as f:
            entries = extract_files(fs, chunk_map, f)

        if args.verbose:
            print(f"  Extracted {len(entries)} entries", file=sys.stderr)
            print(file=sys.stderr)

        # Apply --recent filter: show N most recently accessed files
        if args.recent:
            # Filter to files only (exclude directories, symlinks, etc.)
            file_entries = [e for e in entries if e.type == 'file']
            # Sort by atime descending (most recent first)
            file_entries.sort(key=lambda e: e.atime, reverse=True)
            # Take top N
            entries = file_entries[:args.recent]
            if args.verbose:
                print(f"  Showing {len(entries)} most recently accessed files", file=sys.stderr)

        # Step 5.5: Generate statistics automatically
        if args.verbose:
            print("Calculating statistics...", file=sys.stderr)

        stats = calculate_statistics(entries)

        # Save statistics in same directory as output file if specified, otherwise same as image
        if args.file:
            stats_path = derive_stats_filename(args.file)
        else:
            stats_path = derive_stats_filename(args.image)

        write_statistics_json(stats, stats_path)

        if args.verbose:
            print(f"Statistics written to {stats_path}", file=sys.stderr)
            print(file=sys.stderr)

        # Step 6: Generate output
        if args.output == 'json':
            output = to_json(entries)
        elif args.output == 'csv':
            output = to_csv(entries)
        elif args.output == 'tree':
            output = to_tree(entries)
        else:
            output = to_console(entries)

        # Write output
        if args.file:
            with open(args.file, 'w') as f:
                f.write(output)
            if args.verbose:
                print(f"Output written to {args.file}", file=sys.stderr)
        else:
            print(output)

        # Interactive file extraction mode
        if args.extract:
            interactive_extract(args.image, entries, fs, chunk_map)

        return 0

    except FileNotFoundError:
        print(f"Error: File not found: {args.image}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
