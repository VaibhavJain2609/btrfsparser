#!/usr/bin/env python3
"""
Debug script to analyze BTRFS structures.
"""
import sys
import struct

from superblock import read_superblock, print_superblock_info
from chunk import parse_sys_chunk_array
from btree import traverse_tree_all, read_tree_block
from structures import BtrfsHeader
from constants import BTRFS_TYPE, BTRFS_OBJECTID


def parse_offset(value: str) -> int:
    """Parse offset value."""
    value = value.strip().lower()
    if value.endswith('s'):
        return int(value[:-1]) * 512
    elif value.startswith('0x'):
        return int(value, 16)
    else:
        return int(value)


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug.py <image> [partition_offset]")
        print("Example: python debug.py image.img 4198400s")
        sys.exit(1)

    image_path = sys.argv[1]
    partition_offset = parse_offset(sys.argv[2]) if len(sys.argv) > 2 else 0

    print(f"Image: {image_path}")
    print(f"Partition offset: {partition_offset} (0x{partition_offset:x})")
    print()

    # Read superblock
    print("=" * 60)
    print("SUPERBLOCK")
    print("=" * 60)
    sb = read_superblock(image_path, partition_offset)
    print_superblock_info(sb)
    print()

    # Parse chunk map
    print("=" * 60)
    print("CHUNK MAP (from sys_chunk_array)")
    print("=" * 60)
    chunk_map = parse_sys_chunk_array(sb.sys_chunk_array, sb.sys_chunk_array_size)
    chunk_map.partition_offset = partition_offset

    print(f"Found {len(chunk_map)} chunks:")
    for logical_start, (length, physical) in sorted(chunk_map.chunks.items()):
        print(f"  Logical 0x{logical_start:x} -> Physical 0x{physical:x} (len: {length})")
    print()

    # Try to read root tree
    print("=" * 60)
    print("ROOT TREE ANALYSIS")
    print("=" * 60)
    print(f"Root tree logical addr: 0x{sb.root:x}")
    print(f"Root tree level: {sb.root_level}")

    physical = chunk_map.logical_to_physical(sb.root)
    if physical is None:
        print(f"ERROR: Cannot map root tree address 0x{sb.root:x} to physical!")
        print()
        print("This means the root tree is outside the sys_chunk_array mappings.")
        print("We need to parse the full chunk tree first.")
        print()

        # Try reading chunk tree
        print("=" * 60)
        print("CHUNK TREE ANALYSIS")
        print("=" * 60)
        print(f"Chunk tree logical addr: 0x{sb.chunk_root:x}")
        print(f"Chunk tree level: {sb.chunk_root_level}")

        chunk_physical = chunk_map.logical_to_physical(sb.chunk_root)
        if chunk_physical:
            print(f"Chunk tree physical addr: 0x{chunk_physical:x}")
        else:
            print("ERROR: Cannot map chunk tree address either!")
        return

    print(f"Root tree physical addr: 0x{physical:x}")
    print()

    # Read and parse root tree
    with open(image_path, 'rb') as f:
        print("Traversing root tree...")
        try:
            items = traverse_tree_all(f, sb.root, chunk_map, sb.nodesize)
            print(f"Found {len(items)} items in root tree")
            print()

            # Group by type
            type_counts = {}
            for item, data in items:
                t = item.key.type
                type_counts[t] = type_counts.get(t, 0) + 1

            print("Item types found:")
            for t, count in sorted(type_counts.items()):
                type_name = {
                    1: "INODE_ITEM",
                    12: "INODE_REF",
                    84: "DIR_ITEM",
                    96: "DIR_INDEX",
                    132: "ROOT_ITEM",
                    144: "ROOT_BACKREF",
                    156: "ROOT_REF",
                    228: "CHUNK_ITEM",
                }.get(t, f"TYPE_{t}")
                print(f"  {type_name} ({t}): {count}")
            print()

            # Look for ROOT_ITEMs
            print("ROOT_ITEMs found:")
            for item, data in items:
                if item.key.type == BTRFS_TYPE.ROOT_ITEM:
                    objid = item.key.objectid
                    objname = {
                        1: "ROOT_TREE",
                        2: "EXTENT_TREE",
                        3: "CHUNK_TREE",
                        4: "DEV_TREE",
                        5: "FS_TREE",
                        6: "ROOT_TREE_DIR",
                        7: "CSUM_TREE",
                        8: "QUOTA_TREE",
                        9: "UUID_TREE",
                        10: "FREE_SPACE_TREE",
                    }.get(objid, f"TREE_{objid}")

                    # Try to extract bytenr
                    if len(data) >= 184:
                        bytenr = struct.unpack_from('<Q', data, 176)[0]
                        print(f"  {objname} (objectid={objid}): bytenr=0x{bytenr:x}, data_len={len(data)}")
                    else:
                        print(f"  {objname} (objectid={objid}): data_len={len(data)} (too short!)")

            # Check specifically for FS_TREE
            print()
            print("Looking for FS_TREE (objectid=5, type=132)...")
            found = False
            for item, data in items:
                if item.key.objectid == BTRFS_OBJECTID.FS_TREE and item.key.type == BTRFS_TYPE.ROOT_ITEM:
                    found = True
                    print(f"  FOUND! key=({item.key.objectid}, {item.key.type}, {item.key.offset})")
                    print(f"  Data length: {len(data)}")
                    if len(data) >= 184:
                        bytenr = struct.unpack_from('<Q', data, 176)[0]
                        print(f"  FS tree root bytenr: 0x{bytenr:x}")

            if not found:
                print("  NOT FOUND!")
                print()
                print("Possible reasons:")
                print("  1. This might be a subvolume-based filesystem")
                print("  2. The default subvolume might have a different ID")
                print("  3. The filesystem structure is different")
                print()
                print("All objectids with ROOT_ITEM:")
                for item, data in items:
                    if item.key.type == BTRFS_TYPE.ROOT_ITEM:
                        print(f"    objectid={item.key.objectid}")

        except Exception as e:
            print(f"Error traversing root tree: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()
