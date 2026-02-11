# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A pure Python parser for BTRFS filesystems that reads disk images and extracts file/directory metadata. No external dependencies required beyond Python 3.6+ standard library.

## Commands

```bash
# Auto-detect BTRFS partitions (recommended for multi-partition images)
python btrfs_parser.py image.img -a               # Auto-detect and prompt if multiple found
python btrfs_parser.py image.img -a -v            # Verbose output during detection

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

# Statistics generation
# Note: Statistics are automatically generated for every parse
python btrfs_parser.py image.img                      # Creates image_stats.json (in image directory)
python btrfs_parser.py image.img -o json -f out.json  # Creates out_stats.json (in same dir as out.json)

# Debug script for analyzing BTRFS structures
python debug.py image.img [partition_offset]
```

## Architecture

The parser follows BTRFS's layered architecture:

```
btrfs_parser.py     # CLI entry point, orchestrates the parsing pipeline
    │
    ├── partition_detect.py  # Auto-detect BTRFS partitions (MBR/GPT support)
    │   └── detect_btrfs_partitions()  # Scans for BTRFS signature in partitions
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
    ├── output.py        # Formatters (JSON, CSV, console, tree)
    │
    └── statistics.py    # Statistics calculation and aggregation
```

### Partition Detection

The parser can automatically detect BTRFS partitions in disk images using the `-a` flag:

1. **Partition Table Reading** (`partition_detect.py`):
   - Reads MBR (Master Boot Record) partition tables at offset 0x0
   - Reads GPT (GUID Partition Table) headers at LBA 1 (offset 512)
   - Parses partition entries to extract start offset and size

2. **BTRFS Signature Detection**:
   - Checks each partition for BTRFS magic bytes `_BHRfS_M` at offset 0x10000
   - Extracts BTRFS label from superblock if present
   - Returns list of detected BTRFS partitions

3. **User Selection**:
   - If single partition found: used automatically
   - If multiple partitions found: prompts user to select
   - If no partitions found: reports error

### Parsing Pipeline

1. **Superblock** (`superblock.py`): Read from partition_offset + 0x10000, validate magic `_BHRfS_M`
2. **Chunk Map** (`chunk.py`): Parse `sys_chunk_array` from superblock, then read full chunk tree
3. **Root Tree**: Traverse to find ROOT_ITEM entries for subvolumes
4. **Filesystem Trees**: Parse INODE_ITEM, INODE_REF, DIR_ITEM from each subvolume tree
5. **Path Building**: Walk parent chain to construct full paths
6. **Statistics Generation** (`statistics.py`): Automatically calculates and exports statistics
   - Saved as `<output_file>_stats.json` (if `-f` specified) or `<image>_stats.json` (if output to stdout)
   - Categories: by file extension, by BTRFS type, by ownership (uid/gid)
   - Metrics: file count and total size in bytes

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
