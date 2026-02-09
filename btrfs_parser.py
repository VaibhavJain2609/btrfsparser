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
"""

import argparse
import sys

from superblock import read_superblock, print_superblock_info
from chunk import parse_sys_chunk_array, read_chunk_tree, ChunkMap
<<<<<<< HEAD
from filesystem import find_fs_tree_root, parse_filesystem, extract_files, find_all_subvolumes, parse_all_subvolumes, parse_checksum_tree
from output import to_json, to_csv, to_console, to_tree
from statistics import calculate_statistics, write_statistics_json
=======
from filesystem import find_fs_tree_root, parse_filesystem, extract_files, find_all_subvolumes, parse_all_subvolumes
from output import to_json, to_csv, to_console, to_tree
>>>>>>> f40cb6e (initial commit)


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


<<<<<<< HEAD
def derive_stats_filename(image_path: str) -> str:
    """Generate statistics filename from image path.

    Example:
        /path/to/image.img -> /path/to/image_stats.json
        disk.raw -> disk_stats.json
    """
    from pathlib import Path
    p = Path(image_path)
    stats_filename = f"{p.stem}_stats.json"
    return str(p.parent / stats_filename)


=======
>>>>>>> f40cb6e (initial commit)
def main():
    parser = argparse.ArgumentParser(
        description='Parse BTRFS filesystem from image file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  %(prog)s image.img                         # Console output (partition at start)
  %(prog)s image.img -p 4198400s             # Partition at sector 4198400
  %(prog)s image.img -p 0x80280000           # Partition at hex offset
  %(prog)s image.img -p 2149580800           # Partition at byte offset
  %(prog)s image.img -o json                 # JSON to stdout
  %(prog)s image.img -o csv -f out.csv       # CSV to file
  %(prog)s image.img --info-only             # Just show superblock info
  %(prog)s image.img -o tree                 # Tree view

Offset formats:
  4198400s    - Sector number (multiplied by 512)
  0x80280000  - Hexadecimal byte offset
  2149580800  - Decimal byte offset
'''
    )

    parser.add_argument('image', help='Path to BTRFS image file (.img)')
    parser.add_argument('-p', '--partition-offset',
<<<<<<< HEAD
                        type=str, default='4198400s',
=======
                        type=str, default='0',
>>>>>>> f40cb6e (initial commit)
                        help='Partition start offset (sectors with "s" suffix, hex with "0x", or bytes)')
    parser.add_argument('-o', '--output',
                        choices=['console', 'json', 'csv', 'tree'],
                        default='console',
                        help='Output format (default: console)')
    parser.add_argument('-f', '--file',
                        help='Output file path (default: stdout)')
    parser.add_argument('--info-only', action='store_true',
                        help='Only show superblock info, do not parse files')
<<<<<<< HEAD
    parser.add_argument('--stats', action='store_true',
                        help='Generate statistics JSON file (<image>_stats.json)')
=======
>>>>>>> f40cb6e (initial commit)
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Verbose output')

    args = parser.parse_args()

    try:
        # Parse partition offset
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

<<<<<<< HEAD
            # Step 4b: Parse checksum tree
            if args.verbose:
                print("Parsing checksum tree...", file=sys.stderr)

            fs.checksums = parse_checksum_tree(f, sb, chunk_map)

            if args.verbose:
                print(f"  Found {len(fs.checksums)} checksum ranges", file=sys.stderr)

        # Step 5: Extract file entries
        with open(args.image, 'rb') as f:
            entries = extract_files(fs, chunk_map, f)
=======
        # Step 5: Extract file entries
        entries = extract_files(fs)
>>>>>>> f40cb6e (initial commit)

        if args.verbose:
            print(f"  Extracted {len(entries)} entries", file=sys.stderr)
            print(file=sys.stderr)

<<<<<<< HEAD
        # Step 5.5: Generate statistics if requested
        if args.stats:
            if args.verbose:
                print("Calculating statistics...", file=sys.stderr)

            stats = calculate_statistics(entries)
            stats_path = derive_stats_filename(args.image)
            write_statistics_json(stats, stats_path)

            if args.verbose:
                print(f"Statistics written to {stats_path}", file=sys.stderr)
                print(file=sys.stderr)

=======
>>>>>>> f40cb6e (initial commit)
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
