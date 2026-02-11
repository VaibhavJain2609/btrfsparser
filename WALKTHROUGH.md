# BTRFS Parser - Complete Code Walkthrough

A detailed explanation of every aspect of the codebase, from CLI invocation to final output.

---

## Table of Contents

- [Phase 0: CLI Entry Point](#phase-0-cli-entry-point)
- [Phase 1: Partition Detection](#phase-1-partition-detection)
- [Phase 2: Superblock](#phase-2-superblock)
- [Phase 3: Chunk Map — Address Translation](#phase-3-chunk-map--address-translation)
- [Phase 4: B-tree Traversal Engine](#phase-4-b-tree-traversal-engine)
- [Phase 5: Filesystem Parsing](#phase-5-filesystem-parsing)
- [Phase 6: Path Building & File Extraction](#phase-6-path-building--file-extraction)
- [Phase 7: Statistics](#phase-7-statistics)
- [Phase 8: Output](#phase-8-output)
- [Data Structures Summary](#data-structures-summary)
- [Constants](#constants)
- [Timestamps Explained](#timestamps-explained)
- [End-to-End Flow Summary](#end-to-end-flow-summary)

---

## Phase 0: CLI Entry Point

**File:** `btrfs_parser.py`

When you run:

```bash
python btrfs_parser.py image.img -a -o json -f out.json
```

Execution starts at `btrfs_parser.py:295-296`:

```python
if __name__ == '__main__':
    sys.exit(main())
```

### Argument Parsing (lines 59-98)

`main()` creates an `argparse.ArgumentParser` with these arguments:

| Flag | Purpose | Default |
|------|---------|---------|
| `image` | Path to the disk image file | Required |
| `-a` | Auto-detect BTRFS partitions | `False` |
| `-p` | Manual partition byte offset | `4198400s` (sector notation) |
| `-o` | Output format: `console`, `json`, `csv`, `tree` | `console` |
| `-f` | Output file path | stdout |
| `--info-only` | Only print superblock, don't parse files | `False` |
| `-v` | Verbose logging to stderr | `False` |

### Offset Parsing (`parse_offset`, lines 26-35)

If you use `-p` instead of `-a`, the offset string is parsed by `parse_offset()`:

- `"4198400s"` — ends with `s`, so it's a sector count: `4198400 * 512 = 2,149,580,800 bytes`
- `"0x80280000"` — starts with `0x`, parsed as hex: `2,149,580,800`
- `"2149580800"` — plain decimal

This tells the parser where the BTRFS partition begins inside the disk image.

### Statistics Filename Derivation (`derive_stats_filename`, lines 38-55)

Generates the statistics output filename from a given file path:

- `/path/to/image.img` becomes `/path/to/image_stats.json`
- `output.json` becomes `output_stats.json`
- `/path/to/output.json` becomes `/path/to/output_stats.json`

Uses `pathlib.Path` to split the stem and parent directory, then appends `_stats.json`.

---

## Phase 1: Partition Detection

**File:** `partition_detect.py`

If `-a` is used, the parser auto-detects partitions instead of using a manual offset.

### `detect_btrfs_partitions()` (line 193)

This function tries MBR first, then GPT.

### MBR Reading (`read_mbr`, line 34)

1. Seeks to byte 0 of the image and reads 512 bytes (the Master Boot Record).
2. Checks for the MBR signature `0x55AA` at offset `0x1FE` (byte 510).
3. Parses 4 partition entries starting at offset `0x1BE` (byte 446). Each entry is 16 bytes:
   - Byte `0x04`: partition type code (e.g., `0x83` = Linux)
   - Bytes `0x08-0x0B`: LBA start sector (little-endian 32-bit)
   - Bytes `0x0C-0x0F`: number of sectors (little-endian 32-bit)
4. Skips entries where type is 0 or sector count is 0 (empty slots).
5. Returns a list of `(index, start_sector, num_sectors)` tuples.

### GPT Reading (`read_gpt`, line 83)

1. Seeks to byte 512 (LBA 1) and reads the GPT header.
2. Checks for the signature `"EFI PART"` at the start.
3. From the header, extracts:
   - `partition_entry_lba` (offset `0x48`): which LBA holds the partition entry array
   - `num_entries` (offset `0x50`): number of partition entries (up to 128)
   - `entry_size` (offset `0x54`): size per entry (typically 128 bytes)
4. Seeks to `partition_entry_lba * 512` and reads all entries.
5. For each entry:
   - Checks if `type_guid` is all zeros (empty slot, skip).
   - Reads `start_lba` (offset `0x20`) and `end_lba` (offset `0x28`).
   - Decodes the partition name at offset `0x38` (72 bytes, UTF-16LE).
   - Calculates size as `end_lba - start_lba + 1`.

### BTRFS Signature Check (`check_btrfs_signature`, line 161)

For each detected partition, the code:

1. Seeks to `partition_offset + 0x10000 + 0x40` (superblock magic location).
2. Reads 8 bytes and compares to `_BHRfS_M`.
3. If it matches, reads the BTRFS label from offset `0x12B` within the superblock.

### User Interaction (btrfs_parser.py lines 104-157)

If multiple BTRFS partitions are found:

- Displays all partitions with their index, type, offset, size, and label.
- Prompts the user to select a partition number.
- Asks for confirmation before proceeding with parsing.

---

## Phase 2: Superblock

**Files:** `superblock.py`, `structures.py`, `constants.py`

### `read_superblock()` (`superblock.py:8`)

1. Calculates `absolute_offset = partition_offset + 0x10000` (the superblock is always 64 KiB into the partition).
2. Opens the image, seeks to that offset, reads 4096 bytes.
3. Calls `BtrfsSuperblock.unpack(data)` to parse the raw bytes.
4. Validates the magic bytes are `_BHRfS_M`.

### `BtrfsSuperblock.unpack()` (`structures.py:307`)

This parses the 4096-byte superblock using `struct.unpack_from` with little-endian format (`<`). The key fields and their byte offsets (defined in `constants.py` class `SB_OFFSET`):

| Offset | Field | Size | Purpose |
|--------|-------|------|---------|
| `0x00` | `csum` | 32B | Checksum of the superblock |
| `0x20` | `fsid` | 16B | Filesystem UUID |
| `0x30` | `bytenr` | 8B | Physical address of this superblock |
| `0x40` | `magic` | 8B | Must be `_BHRfS_M` |
| `0x48` | `generation` | 8B | Transaction generation counter |
| `0x50` | `root` | 8B | **Logical address of the root tree** |
| `0x58` | `chunk_root` | 8B | **Logical address of the chunk tree** |
| `0x70` | `total_bytes` | 8B | Total filesystem size |
| `0x78` | `bytes_used` | 8B | Bytes used |
| `0x90` | `sectorsize` | 4B | Sector size (usually 4096) |
| `0x94` | `nodesize` | 4B | B-tree node size (usually 16384) |
| `0xA0` | `sys_chunk_array_size` | 4B | How many bytes of `sys_chunk_array` are used |
| `0xC4` | `csum_type` | 2B | Checksum algorithm (0 = CRC32C) |
| `0xC6` | `root_level` | 1B | Tree depth of root tree |
| `0xC7` | `chunk_root_level` | 1B | Tree depth of chunk tree |
| `0x12B` | `label` | 256B | Filesystem label (null-terminated UTF-8) |
| `0x32B` | `sys_chunk_array` | 2048B | **Bootstrap chunk mappings** |

The two most critical fields are `root` (where to find the root tree) and `chunk_root` (where to find the chunk tree). Both are **logical addresses** — they cannot be used directly to seek in the image file. You need the chunk map to translate them.

### `print_superblock_info()` (`superblock.py:33`)

Displays human-readable superblock information: label, UUID, generation, sizes, tree addresses, device count, and checksum type.

### `format_uuid()` (`superblock.py:49`)

Converts raw UUID bytes to standard hyphenated format: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.

---

## Phase 3: Chunk Map — Address Translation

**File:** `chunk.py`

### Why Chunks Exist

BTRFS uses a **virtual address space**. Every pointer in the B-trees is a "logical address." To actually read data from the disk, you need to translate logical to physical. The chunk map is this translation table.

### The Bootstrap Problem

The chunk tree itself is at a logical address (`sb.chunk_root`). To read it, you need the chunk map. But the chunk map comes from the chunk tree. Chicken-and-egg.

BTRFS solves this with `sys_chunk_array` — a small bootstrap chunk map embedded directly in the superblock. It contains just enough mappings (the "system" chunks) to locate and read the full chunk tree.

### `ChunkMap` class (line 10)

```python
class ChunkMap:
    chunks: Dict[int, tuple]     # {logical_start: (length, physical_offset)}
    partition_offset: int         # Added to all physical addresses
```

- `add_chunk(logical_start, length, physical_offset)`: Adds a mapping entry.
- `logical_to_physical(logical_addr)`: Iterates all chunks. For each, checks if `chunk_start <= logical_addr < chunk_start + length`. If so, calculates `partition_offset + physical_offset + (logical_addr - chunk_start)`.
- `__len__()`: Returns the number of chunks in the map.

### Step 2a: `parse_sys_chunk_array()` (line 43)

Parses the `sys_chunk_array` (2048 bytes max) from the superblock. The format is repeated `(BtrfsKey, BtrfsChunk)` pairs:

1. Read a `BtrfsKey` (17 bytes): `objectid(8) + type(1) + offset(8)`. The `key.offset` is the **logical start address** of the chunk.
2. Read a `BtrfsChunk` (48 bytes fixed + 32 bytes per stripe):
   - `length` (8B): chunk size in bytes
   - `num_stripes` (2B): how many physical copies
   - Each stripe has: `devid(8) + offset(8) + dev_uuid(16)` = 32 bytes
3. For a single-device filesystem, `stripes[0][1]` is the physical offset.
4. Adds to chunk map: `logical_start -> (length, physical_offset)`.

After this, `chunk_map.partition_offset` is set to the partition offset so all physical translations include it.

### Step 2b: `read_chunk_tree()` (line 81)

Now that we have the bootstrap chunk map, we can read the full chunk tree to get **all** chunk mappings (metadata and data chunks, not just system chunks).

This is a recursive B-tree traversal starting at `sb.chunk_root`:

1. Translate `logical_addr` to physical using the current chunk map.
2. Seek and read `nodesize` bytes (one full tree block).
3. Parse the `BtrfsHeader` (101 bytes) at the start.
4. If `header.level == 0` (leaf node):
   - Parse each `BtrfsItem` (25 bytes each).
   - For items with `key.type == CHUNK_ITEM` (228): parse the `BtrfsChunk` data and add to chunk map.
5. If `header.level > 0` (internal node):
   - Parse `BtrfsKeyPtr` entries (33 bytes each): `key(17) + blockptr(8) + generation(8)`.
   - Recursively traverse each `ptr.blockptr`.
6. A `visited` set prevents re-reading the same block.

After this, the chunk map is complete.

---

## Phase 4: B-tree Traversal Engine

**File:** `btree.py`

This module provides the generic tree traversal used by all subsequent phases.

### Tree Block Layout

Every tree block (node) in BTRFS starts with a 101-byte `BtrfsHeader`:

| Offset | Field | Size | Purpose |
|--------|-------|------|---------|
| `0x00` | `csum` | 32B | Checksum of this block |
| `0x20` | `fsid` | 16B | Filesystem UUID |
| `0x30` | `bytenr` | 8B | Logical address of this block |
| `0x38` | `flags` | 8B | Block flags |
| `0x40` | `chunk_tree_uuid` | 16B | UUID |
| `0x50` | `generation` | 8B | Transaction generation |
| `0x58` | `owner` | 8B | Which tree owns this block |
| `0x60` | `nritems` | 4B | Number of items in this node |
| `0x64` | `level` | 1B | 0 = leaf, >0 = internal |

### Leaf Nodes (`parse_leaf_items`, line 22)

Layout: `[header 101B][item0 25B][item1 25B]...[itemN]...[dataN]...[data1][data0]`

Items grow **forward** from byte 101. Data grows **backward** from the end of the block. Each `BtrfsItem` (25 bytes) is:

- `BtrfsKey` (17B): `objectid(8) + type(1) + offset(8)` — identifies the item
- `offset` (4B): byte offset of this item's data, relative to position 101 (header end)
- `size` (4B): byte size of the data

So to read item data: `data_start = 101 + item.offset`, then read `item.size` bytes.

### Internal Nodes (`parse_internal_node`, line 53)

Layout: `[header 101B][keyptr0 33B][keyptr1 33B]...`

Each `BtrfsKeyPtr` (33 bytes) is:

- `BtrfsKey` (17B): the smallest key in the child subtree
- `blockptr` (8B): logical address of the child block
- `generation` (8B): generation of the child

### `read_tree_block()` (line 11)

Translates a logical address to physical via `chunk_map`, seeks, and reads `nodesize` bytes.

### `traverse_tree_all()` (line 115)

Generic full-tree traversal. Recursively visits every node, collecting all `(BtrfsItem, data)` pairs from all leaf nodes. Uses a `visited` set to prevent infinite loops.

### `search_tree()` (line 71)

Same as `traverse_tree_all` but filters results: only returns items matching a specific `objectid` and optionally a `type`.

---

## Phase 5: Filesystem Parsing

**File:** `filesystem.py`

### Step 3: `find_all_subvolumes()` (line 169)

Traverses the **root tree** (at `sb.root`) to discover all subvolumes:

1. Collects all `ROOT_ITEM` entries (type 132). For each, reads the `bytenr` at offset 176 within the item data — this is the **root of that subvolume's filesystem tree**.
2. Collects all `ROOT_REF` entries (type 156). These contain the subvolume name: `dirid(8) + sequence(8) + name_len(2) + name(variable)`.
3. Builds a list of `(objectid, name, bytenr)`. Object IDs >= 256 are user subvolumes. Object ID 5 is the default filesystem tree (`FS_TREE`).

### Step 4: `parse_all_subvolumes()` (line 215)

For each subvolume, calls `parse_filesystem()` to parse its tree, then merges results into a combined `FileSystem` object.

To prevent inode collisions across subvolumes (each subvolume has its own inode 256 for root), it creates **unique inodes**: `unique_inode = (subvolume_id << 48) | original_inode`. This packs the subvolume ID into the upper 16 bits.

### `parse_filesystem()` (line 270)

This is the core parsing function. It traverses the entire filesystem tree and processes each item by type:

#### `INODE_ITEM` (type 1) — `BtrfsInodeItem` at 160 bytes

| Offset | Field | Size | Meaning |
|--------|-------|------|---------|
| 0 | `generation` | 8B | Creation transaction |
| 8 | `transid` | 8B | Last modification transaction |
| 16 | `size` | 8B | File size in bytes |
| 24 | `nbytes` | 8B | Allocated disk bytes |
| 32 | `block_group` | 8B | Block group hint |
| 40 | `nlink` | 4B | Hard link count |
| 44 | `uid` | 4B | User ID |
| 48 | `gid` | 4B | Group ID |
| 52 | `mode` | 4B | Permission bits (like Unix `stat.st_mode`) |
| 56 | `rdev` | 8B | Device number for device files |
| 64 | `flags` | 8B | Inode flags (NODATASUM, COMPRESS, etc.) |
| 72 | `sequence` | 8B | Sequence number |
| 80 | reserved | 32B | (unused) |
| 112 | `atime` | 12B | Access time: `sec(8) + nsec(4)` |
| 124 | `ctime` | 12B | Change time |
| 136 | `mtime` | 12B | Modification time |
| 148 | `otime` | 12B | Creation time |

Stored in `fs.inodes[objectid]`.

#### `INODE_REF` (type 12) — Links an inode to its parent

- Format: `index(8) + name_len(2) + name(variable)`
- `key.objectid` = this inode, `key.offset` = parent inode
- Stored in `fs.names[objectid]` and `fs.parents[objectid]`
- Also populates `fs.children[parent]`

#### `DIR_ITEM` (type 84) — Directory entry (30 bytes fixed + name)

- `location` (17B): `BtrfsKey` pointing to the child inode
- `transid` (8B)
- `data_len` (2B): xattr data length (0 for normal dir entries)
- `name_len` (2B)
- `type` (1B): file type enum (1=file, 2=dir, 7=symlink, etc.)
- `name` (variable)
- Stored in `fs.dir_entries[objectid]`

#### `XATTR_ITEM` (type 24) — Extended attributes (reuses `BtrfsDirItem` structure)

- The name is the xattr key (e.g., `security.selinux`)
- The data follows the name
- Stored in `fs.xattrs[objectid]`

#### `EXTENT_DATA` (type 108) — File extent mapping (`BtrfsFileExtentItem`)

- Fixed header (21 bytes): `generation(8) + ram_bytes(8) + compression(1) + encryption(1) + other(2) + type(1)`
- If `type == 0` (inline): file data is embedded right after the 21-byte header. Small files.
- If `type == 1` (regular) or `type == 2` (prealloc): 32 more bytes follow: `disk_bytenr(8) + disk_num_bytes(8) + offset(8) + num_bytes(8)`
  - `disk_bytenr`: logical address on disk where the data lives (0 = hole/sparse)
  - `disk_num_bytes`: size on disk (may differ from file size if compressed)
  - `offset`: offset within the uncompressed extent
  - `num_bytes`: how many bytes this extent covers in the file
- `key.offset` = file offset (where this extent's data appears in the file)
- Stored in `fs.extents[objectid]` as tuples: `(file_offset, disk_bytenr, disk_num_bytes, compression, extent_type, inline_data)`

### `FileSystem` dataclass (line 72)

Holds all parsed state:

```python
inodes:      Dict[int, BtrfsInodeItem]     # inode -> metadata
names:       Dict[int, str]                 # inode -> filename
parents:     Dict[int, int]                 # inode -> parent inode
children:    Dict[int, List[int]]           # inode -> child inodes
dir_entries: Dict[int, List[BtrfsDirItem]]  # inode -> directory entries
xattrs:      Dict[int, List[tuple]]         # inode -> [(name, value)]
extents:     Dict[int, List[tuple]]         # inode -> extent info tuples
checksums:   Dict[int, int]                 # logical_offset -> count
```

### Step 4b: `parse_checksum_tree()` (line 130)

1. Finds the checksum tree root by searching the root tree for `ROOT_ITEM` with `objectid == 7` (CSUM_TREE).
2. Traverses the checksum tree. Each item has:
   - `key.type == EXTENT_CSUM` (128)
   - `key.offset` = logical byte offset of the data being checksummed
   - `data` = array of 4-byte CRC32C checksums, one per sector (4096 bytes)
3. Stores `{logical_offset: num_checksums}`.

---

## Phase 6: Path Building & File Extraction

**File:** `filesystem.py`

### `build_path()` (line 353)

Constructs the full path for an inode by walking up the parent chain:

1. Start at the target inode.
2. Look up `fs.names[current]` for the filename.
3. Look up `fs.parents[current]` for the parent inode.
4. Repeat until you hit the root (name starts with `/`) or run out of parents.
5. Reverse the collected parts and join with `/`.
6. Detects cycles with a `seen` set and caps depth at 100.

### `extract_files()` (line 686)

Converts the `FileSystem` into a list of `FileEntry` objects:

1. **Resolve usernames/groups**: Calls `resolve_names_from_filesystem()` which:
   - Searches the parsed filesystem for files at `/etc/passwd` and `/etc/group`
   - Reads their data from disk using `read_file_data()`
   - Parses the colon-delimited format to build `uid -> username` and `gid -> groupname` maps

2. **For each inode** in `fs.inodes`:
   - Extracts the original inode number: `unique_inode & 0xFFFFFFFFFFFF` (lower 48 bits)
   - Extracts subvolume ID: `unique_inode >> 48` (upper 16 bits)
   - Calls `build_path()` for the full path
   - Calls `get_file_type()` to classify by mode bits (uses Python's `stat` module)
   - Calls `parse_mode()` to produce the `drwxr-xr-x` string
   - Calls `parse_inode_flags()` to decode flag bits into strings like `"NODATASUM,COMPRESS"`
   - Counts xattrs, extents, and checksums
   - Calculates physical offset of first extent via `chunk_map.logical_to_physical()`
   - **For regular files**: reads the file data from disk and computes MD5 and SHA256 hashes

### `read_file_data()` (line 416)

Reassembles a file's contents from its extents:

1. Sorts extents by `file_offset`.
2. For each extent:
   - **Inline** (`type == 0`): data is embedded in the extent item. Decompresses if needed.
   - **Hole** (`disk_bytenr == 0`): fills with zeros.
   - **Compressed** (`compression != 0`): calls `decompress_data()` which supports zlib (built-in), LZO (optional), and zstd (optional).
   - **Regular**: translates `disk_bytenr` logical to physical, seeks, reads `disk_num_bytes` bytes.
3. Concatenates all extent data into the final file bytes.

### `decompress_data()` (line 491)

Handles decompression based on the compression type:

| Value | Algorithm | Support |
|-------|-----------|---------|
| 0 | None | Built-in |
| 1 | zlib | Built-in (Python stdlib) |
| 2 | LZO | Optional (`python-lzo` package) |
| 3 | zstd | Optional (`zstandard` package) |

### `calculate_hashes()` (line 535)

Computes MD5 and SHA256 hex digests of file data using Python's `hashlib`.

### `resolve_names_from_filesystem()` (line 623)

Searches the parsed filesystem for `/etc/passwd` and `/etc/group` (also checks `/root/etc/passwd` and `/root/etc/group` for alternative layouts):

- `parse_passwd_data()` (line 551): Parses `username:password:uid:gid:gecos:home:shell` format, returns `{uid: username}`.
- `parse_group_data()` (line 587): Parses `groupname:password:gid:members` format, returns `{gid: groupname}`.

### `FileEntry` dataclass (line 31)

The final output record for each file/directory:

```python
inode: int                    # Original inode number
name: str                    # Filename
path: str                    # Full path
size: int                    # File size in bytes
type: str                    # 'file', 'directory', 'symlink', etc.
mode: int                    # Raw permission bits
mode_str: str                # 'drwxr-xr-x'
uid: int                     # User ID
gid: int                     # Group ID
nlink: int                   # Hard link count
atime: str                   # Access time (ISO format)
mtime: str                   # Modification time (ISO format)
ctime: str                   # Change time (ISO format)
otime: str                   # Creation time (ISO format)
parent_inode: Optional[int]  # Parent inode number
uid_name: Optional[str]      # Resolved username
gid_name: Optional[str]      # Resolved group name
generation: Optional[int]    # Transaction ID when created
transid: Optional[int]       # Last modification transaction
flags: Optional[int]         # Raw flag bits
flags_str: Optional[str]     # Decoded: "NODATASUM,COMPRESS"
subvolume_id: Optional[int]  # Subvolume/snapshot ID
xattr_count: int             # Number of extended attributes
extent_count: int            # Number of extents
disk_bytes: int              # Total bytes on disk (compressed)
physical_offset: Optional[int]  # Raw disk offset (first extent)
checksum_count: int          # Number of checksums covering file
md5: Optional[str]           # MD5 hash of file contents
sha256: Optional[str]        # SHA256 hash of file contents
```

---

## Phase 7: Statistics

**File:** `statistics.py`

### `calculate_statistics()` (line 38)

A single pass over all `FileEntry` objects, aggregating into three categories:

- **`by_extension`**: Groups by file extension (`.txt`, `.py`, `(directory)`, `(no extension)`). Counts files and sums sizes.
- **`by_type`**: Groups by BTRFS type string (`file`, `directory`, `symlink`).
- **`by_ownership`**: Groups by UID, with nested GID breakdown. Includes resolved usernames/groupnames.

Also computes a summary: total files, total directories, total symlinks, total size, unique extensions, unique owners.

### `get_file_extension()` (line 12)

Extracts normalized file extension:

- Directories return `(directory)`
- Files without extensions return `(no extension)`
- Otherwise returns lowercase extension with dot (e.g., `.txt`)

### `write_statistics_json()` (line 113)

Writes the stats dict to a JSON file. Errors are non-fatal — prints a warning to stderr and continues.

---

## Phase 8: Output

**File:** `output.py`

### `to_json()` (line 13)

Converts each `FileEntry` to a dict via `dataclasses.asdict()`, then `json.dumps` with indent 2.

### `to_csv()` (line 18)

Uses `csv.DictWriter` with a fixed set of 27 columns. Writes a header row followed by one row per entry.

Columns: `path`, `name`, `type`, `size`, `mode_str`, `uid`, `uid_name`, `gid`, `gid_name`, `nlink`, `atime`, `mtime`, `ctime`, `otime`, `inode`, `subvolume_id`, `generation`, `transid`, `flags`, `flags_str`, `extent_count`, `disk_bytes`, `physical_offset`, `xattr_count`, `checksum_count`, `md5`, `sha256`.

### `to_console()` (line 68)

Formats a table with columns: Mode, Owner (uid + username), Group (gid + groupname), Size, Modified, Path. Directories show `<DIR>` instead of size.

### `to_tree()` (line 101)

Builds a nested dict from paths, then recursively renders it with box-drawing connectors, like the Unix `tree` command.

---

## Data Structures Summary

**File:** `structures.py`

| Structure | Size | Purpose |
|-----------|------|---------|
| `BtrfsKey` | 17B | Universal item identifier: `objectid + type + offset` |
| `BtrfsHeader` | 101B | At start of every tree block |
| `BtrfsItem` | 25B | Item descriptor in leaf nodes (key + data pointer) |
| `BtrfsKeyPtr` | 33B | Child pointer in internal nodes |
| `BtrfsInodeItem` | 160B | File/directory metadata (size, mode, timestamps) |
| `BtrfsDirItem` | 30B+ | Directory entry (name, target inode, type) |
| `BtrfsChunk` | 48B+ | Logical-to-physical address mapping |
| `BtrfsFileExtentItem` | 21-53B | Where file data lives on disk |
| `BtrfsTimespec` | 12B | Timestamp: `seconds(8) + nanoseconds(4)` |
| `BtrfsSuperblock` | 4096B | Top-level filesystem metadata |

All use `struct.unpack_from('<...', data, pos)` — little-endian byte order, which is what BTRFS uses on disk.

---

## Constants

**File:** `constants.py`

### `BTRFS_TYPE` — Item Type Codes

| Code | Name | Purpose |
|------|------|---------|
| 1 | `INODE_ITEM` | File/directory metadata |
| 12 | `INODE_REF` | Inode name and parent link |
| 13 | `INODE_EXTREF` | Extended inode reference |
| 24 | `XATTR_ITEM` | Extended attributes |
| 84 | `DIR_ITEM` | Directory entry |
| 96 | `DIR_INDEX` | Directory index entry |
| 108 | `EXTENT_DATA` | File extent mapping |
| 128 | `EXTENT_CSUM` | Data checksums |
| 132 | `ROOT_ITEM` | Tree root definition |
| 156 | `ROOT_REF` | Subvolume reference |
| 228 | `CHUNK_ITEM` | Chunk mapping |

### `BTRFS_OBJECTID` — Well-Known Object IDs

| ID | Name | Purpose |
|----|------|---------|
| 1 | `ROOT_TREE` | Root of all trees |
| 2 | `EXTENT_TREE` | Extent allocation tracking |
| 3 | `CHUNK_TREE` | Logical-to-physical mapping |
| 4 | `DEV_TREE` | Device information |
| 5 | `FS_TREE` | Default filesystem tree |
| 6 | `ROOT_TREE_DIR` | Root directory of root tree |
| 7 | `CSUM_TREE` | Data checksums |
| 256 | `FIRST_FREE` | First user-allocatable object ID |

### `BTRFS_FT` — Directory Entry File Types

| Code | Name |
|------|------|
| 0 | unknown |
| 1 | regular file |
| 2 | directory |
| 3 | character device |
| 4 | block device |
| 5 | FIFO |
| 6 | socket |
| 7 | symlink |
| 8 | xattr |

### `BTRFS_INODE_FLAGS` — Inode Flag Bitmasks

| Bit | Name | Meaning |
|-----|------|---------|
| 0 | `NODATASUM` | Don't checksum data |
| 1 | `NODATACOW` | Don't copy-on-write data |
| 2 | `READONLY` | Readonly inode |
| 3 | `NOCOMPRESS` | Don't compress |
| 4 | `PREALLOC` | Preallocated extent |
| 5 | `SYNC` | Synchronous updates |
| 6 | `IMMUTABLE` | Immutable file |
| 7 | `APPEND` | Append only |
| 8 | `NODUMP` | Don't dump |
| 9 | `NOATIME` | Don't update access time |
| 10 | `DIRSYNC` | Directory sync |
| 11 | `COMPRESS` | Compress this file |

### Helper Functions

- `parse_mode(mode: int) -> str`: Converts integer mode to `drwxr-xr-x` string using Python's `stat` module bitmasks.
- `parse_inode_flags(flags: int) -> str`: Converts flag integer to comma-separated string like `"NODATASUM,COMPRESS"`.

---

## Timestamps Explained

The four timestamps come from `BtrfsInodeItem` (`structures.py:122-140`):

| Field | Name | Meaning |
|-------|------|---------|
| `atime` | **Access time** | Last time the file's contents were read (e.g., `cat file.txt`, opening a file) |
| `mtime` | **Modification time** | Last time the file's **data** was changed (e.g., writing to the file) |
| `ctime` | **Change time** | Last time the file's **metadata** was changed (e.g., permissions, ownership, renaming, or data changes — any inode update) |
| `otime` | **Creation time** (birth time) | When the inode was originally created. This is BTRFS-specific — most older Linux filesystems (ext3, etc.) don't track this. |

### Key Distinctions

- **mtime vs ctime**: Running `chmod 644 file.txt` updates `ctime` but not `mtime` (metadata changed, data didn't). Writing to the file updates both.
- **atime**: Updated on reads. Many systems mount with `noatime` or `relatime` to reduce disk writes, so this may be stale.
- **otime**: Never changes after creation. Useful for forensics — tells you when a file first appeared on the filesystem.

### Storage Format

Each is stored on disk as a `BtrfsTimespec` — 12 bytes: `seconds(8) + nanoseconds(4)` since Unix epoch (January 1, 1970). The `to_iso()` method at `structures.py:57` converts them to ISO 8601 strings like `2024-03-15T14:30:22`.

---

## End-to-End Flow Summary

```
CLI args
  |
  +- (-a) --> partition_detect.py --> MBR/GPT scan --> BTRFS signature check
  |                                                          |
  +- (-p) --> parse_offset() --------------------------------+
                                                             |
                                                     partition_offset
                                                             |
                                                   +------------------+
                                                   |  read_superblock |
                                                   | (offset+0x10000) |
                                                   +--------+---------+
                                                            |
                                             BtrfsSuperblock (root, chunk_root,
                                                             sys_chunk_array)
                                                            |
                                              +-------------+-------------+
                                              | parse_sys_chunk_array()   |
                                              | (bootstrap chunk map)     |
                                              +-------------+-------------+
                                                            |
                                              +-------------+-------------+
                                              | read_chunk_tree()         |
                                              | (complete chunk map)      |
                                              +-------------+-------------+
                                                            |
                                                       ChunkMap
                                                  (logical -> physical)
                                                            |
                                              +-------------+-------------+
                                              | find_all_subvolumes()     |
                                              | (traverse root tree)      |
                                              +-------------+-------------+
                                                            |
                                              +-------------+-------------+
                                              | parse_all_subvolumes()    |
                                              | (traverse each FS tree)   |
                                              +-------------+-------------+
                                                            |
                                                   FileSystem object
                                         (inodes, names, parents, extents, xattrs)
                                                            |
                                              +-------------+-------------+
                                              | parse_checksum_tree()     |
                                              +-------------+-------------+
                                                            |
                                              +-------------+-------------+
                                              | extract_files()           |
                                              | (build paths, read data,  |
                                              |  compute hashes,          |
                                              |  resolve uid/gid names)   |
                                              +-------------+-------------+
                                                            |
                                                   List[FileEntry]
                                                            |
                                         +------------------+----------------+
                                         |                  |                |
                                  calculate_statistics  to_json/csv/    write output
                                         |              console/tree
                                  write_stats.json
```
