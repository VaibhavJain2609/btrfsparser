# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A pure Python parser for BTRFS filesystems that reads disk images and extracts file/directory metadata. No external dependencies required beyond Python 3.6+ standard library.

## Commands

```bash
# Parse BTRFS image (console output)
python btrfs_parser.py image.img

# Parse with partition offset (for images containing partition tables)
python btrfs_parser.py image.img -p 4198400s      # sector notation
python btrfs_parser.py image.img -p 0x80280000    # hex offset
python btrfs_parser.py image.img -p 2149580800   # byte offset

# Output formats
python btrfs_parser.py image.img -o json          # JSON to stdout
python btrfs_parser.py image.img -o csv -f out.csv
python btrfs_parser.py image.img -o tree          # tree view

# Show superblock info only
python btrfs_parser.py image.img --info-only

# Debug script for analyzing BTRFS structures
python debug.py image.img [partition_offset]
```

## Architecture

The parser follows BTRFS's layered architecture:

```
btrfs_parser.py   # CLI entry point, orchestrates the parsing pipeline
    │
    ├── superblock.py    # Reads superblock at offset 0x10000
    │
    ├── chunk.py         # Logical-to-physical address translation
    │   └── ChunkMap     # Maps logical addresses to physical disk offsets
    │
    ├── btree.py         # B-tree traversal (internal nodes + leaf parsing)
    │
    ├── filesystem.py    # Extracts inodes, directory entries, builds paths
    │   └── FileSystem   # Holds parsed state (inodes, names, parents)
    │
    ├── structures.py    # Dataclasses for all BTRFS on-disk structures
    │
    ├── constants.py     # Magic numbers, type enums, field offsets
    │
    └── output.py        # Formatters (JSON, CSV, console, tree)
```

### Parsing Pipeline

1. **Superblock** (`superblock.py`): Read from partition_offset + 0x10000, validate magic `_BHRfS_M`
2. **Chunk Map** (`chunk.py`): Parse `sys_chunk_array` from superblock, then read full chunk tree
3. **Root Tree**: Traverse to find ROOT_ITEM entries for subvolumes
4. **Filesystem Trees**: Parse INODE_ITEM, INODE_REF, DIR_ITEM from each subvolume tree
5. **Path Building**: Walk parent chain to construct full paths

### Key Data Structures

- **BtrfsKey**: 17 bytes (objectid + type + offset) - identifies every item
- **ChunkMap**: Translates logical addresses to physical, accounts for partition offset
- **FileSystem**: Accumulates parsed inodes and directory relationships
- **FileEntry**: Final output record with path, timestamps, permissions

### Address Translation

BTRFS uses logical addresses internally. The `ChunkMap` class handles:
- Logical-to-physical mapping via chunk items
- Partition offset adjustment for multi-partition images

### Subvolume Handling

The parser discovers all subvolumes via ROOT_REF items in the root tree and creates unique inode IDs by combining subvolume ID (upper 16 bits) with original inode number (lower 48 bits).
