"""
BTRFS Filesystem Parser - Extract files and directories from filesystem tree.
"""
import struct
import stat
import hashlib
import zlib
from typing import Dict, List, Optional, BinaryIO
from dataclasses import dataclass, field

from structures import BtrfsInodeItem, BtrfsDirItem, BtrfsSuperblock, BtrfsFileExtentItem
from constants import BTRFS_TYPE, BTRFS_OBJECTID, parse_mode, parse_inode_flags
from chunk import ChunkMap
from btree import traverse_tree_all

# Try to import compression modules (optional dependencies)
try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False

try:
    import lzo
    HAS_LZO = True
except ImportError:
    HAS_LZO = False


@dataclass
class FileEntry:
    """Represents a file or directory extracted from BTRFS."""
    inode: int
    name: str
    path: str
    size: int
    type: str             # 'file', 'directory', 'symlink', etc.
    mode: int
    mode_str: str         # 'drwxr-xr-x'
    uid: int
    gid: int
    nlink: int
    atime: str            # ISO format
    mtime: str
    ctime: str
    otime: str            # creation time
    parent_inode: Optional[int] = None
    uid_name: Optional[str] = None  # Resolved username from /etc/passwd
    gid_name: Optional[str] = None  # Resolved group name from /etc/group
    # Phase 1: Already parsed data
    generation: Optional[int] = None          # Transaction ID when created
    transid: Optional[int] = None             # Last modification transaction
    flags: Optional[int] = None               # Raw flag bits
    flags_str: Optional[str] = None           # Decoded: "NODATASUM,COMPRESS"
    # Phase 5: Subvolume
    subvolume_id: Optional[int] = None        # Subvolume/snapshot ID
    # Phase 2: XATTRs
    xattr_count: int = 0                      # Number of extended attributes
    # Phase 3: Extents
    extent_count: int = 0                     # Number of extents
    disk_bytes: int = 0                       # Total bytes on disk (compressed)
    # Phase 6: Physical offset
    physical_offset: Optional[int] = None     # Raw disk offset (first extent)
    # Phase 4: Checksums
    checksum_count: int = 0                   # Number of checksums covering file
    # Cryptographic hashes
    md5: Optional[str] = None                 # MD5 hash of file contents
    sha256: Optional[str] = None              # SHA256 hash of file contents
    # Internal: unique inode for extent lookup during extraction
    unique_inode: Optional[int] = None


@dataclass
class FileSystem:
    """Holds parsed filesystem state."""
    inodes: Dict[int, BtrfsInodeItem] = field(default_factory=dict)
    names: Dict[int, str] = field(default_factory=dict)           # inode -> name
    parents: Dict[int, int] = field(default_factory=dict)         # inode -> parent_inode
    children: Dict[int, List[int]] = field(default_factory=dict)  # inode -> [child_inodes]
    dir_entries: Dict[int, List[BtrfsDirItem]] = field(default_factory=dict)
    xattrs: Dict[int, List[tuple]] = field(default_factory=dict)  # inode -> [(name, value)]
    extents: Dict[int, List[tuple]] = field(default_factory=dict) # inode -> [(file_offset, disk_bytenr, disk_bytes, compression)]
    checksums: Dict[int, int] = field(default_factory=dict)       # logical_offset -> checksum_count
    xattrs: Dict[int, List[tuple]] = field(default_factory=dict)  # inode -> [(name, value)]
    extents: Dict[int, List[tuple]] = field(default_factory=dict) # inode -> [(file_offset, disk_bytenr, disk_bytes, compression)]
    checksums: Dict[int, int] = field(default_factory=dict)       # logical_offset -> checksum_count


def find_fs_tree_root(f: BinaryIO, sb: BtrfsSuperblock,
                       chunk_map: ChunkMap) -> int:
    """
    Find the filesystem tree root from root tree.
    Search for ROOT_ITEM with objectid=FS_TREE_OBJECTID (5).
    """
    # Get all items from root tree
    items = traverse_tree_all(f, sb.root, chunk_map, sb.nodesize)

    for item, data in items:
        if (item.key.objectid == BTRFS_OBJECTID.FS_TREE and
            item.key.type == BTRFS_TYPE.ROOT_ITEM):
            # ROOT_ITEM contains bytenr at offset 176 (after embedded inode_item)
            # btrfs_root_item: inode(160) + generation(8) + root_dirid(8) + bytenr(8)
            if len(data) >= 184:
                bytenr = struct.unpack_from('<Q', data, 176)[0]
                return bytenr

    raise ValueError("Filesystem tree root not found")


def find_csum_tree_root(f: BinaryIO, sb: BtrfsSuperblock,
                        chunk_map: ChunkMap) -> Optional[int]:
    """
    Find the checksum tree root from root tree.
    Search for ROOT_ITEM with objectid=CSUM_TREE (7).
    Returns None if checksum tree doesn't exist.
    """
    try:
        items = traverse_tree_all(f, sb.root, chunk_map, sb.nodesize)

        for item, data in items:
            if (item.key.objectid == BTRFS_OBJECTID.CSUM_TREE and
                item.key.type == BTRFS_TYPE.ROOT_ITEM):
                if len(data) >= 184:
                    bytenr = struct.unpack_from('<Q', data, 176)[0]
                    return bytenr
    except Exception:
        pass

    return None


def parse_checksum_tree(f: BinaryIO, sb: BtrfsSuperblock,
                        chunk_map: ChunkMap) -> Dict[int, int]:
    """
    Parse checksum tree and return map of logical_offset -> checksum_count.

    Checksum tree items:
    - key.objectid = BTRFS_OBJECTID.EXTENT_CSUM (-10)
    - key.type = BTRFS_TYPE.EXTENT_CSUM (128)
    - key.offset = logical byte offset
    - data = array of 4-byte CRC32C checksums

    Returns: Dict mapping logical offset ranges to checksum counts
    """
    csum_root = find_csum_tree_root(f, sb, chunk_map)
    if not csum_root:
        return {}

    checksums = {}
    blocksize = sb.sectorsize  # Typically 4096 bytes per checksum

    try:
        items = traverse_tree_all(f, csum_root, chunk_map, sb.nodesize)

        for item, data in items:
            if item.key.type == BTRFS_TYPE.EXTENT_CSUM:
                # key.offset = starting logical byte offset
                logical_start = item.key.offset
                # Each checksum is 4 bytes (CRC32C), covers one block
                num_checksums = len(data) // 4
                # Store: logical_start -> num_checksums
                checksums[logical_start] = num_checksums

    except Exception:
        # If checksum tree parsing fails, return empty dict
        pass

    return checksums


def find_all_subvolumes(f: BinaryIO, sb: BtrfsSuperblock,
                        chunk_map: ChunkMap) -> List[tuple]:
    """
    Find all subvolumes/snapshots in the filesystem.

    Returns list of (objectid, name, bytenr) tuples.
    Subvolumes have objectid >= 256 and have ROOT_ITEM entries.
    """
    items = traverse_tree_all(f, sb.root, chunk_map, sb.nodesize)

    subvolumes = []
    root_items = {}  # objectid -> bytenr
    root_names = {}  # objectid -> name

    for item, data in items:
        if item.key.type == BTRFS_TYPE.ROOT_ITEM:
            objectid = item.key.objectid
            if len(data) >= 184:
                bytenr = struct.unpack_from('<Q', data, 176)[0]
                root_items[objectid] = bytenr

        elif item.key.type == BTRFS_TYPE.ROOT_REF:
            # ROOT_REF: parent_objectid -> child info
            # key.objectid = parent tree id
            # key.offset = child tree id
            # data: dirid(8) + sequence(8) + name_len(2) + name
            child_id = item.key.offset
            if len(data) >= 18:
                name_len = struct.unpack_from('<H', data, 16)[0]
                if len(data) >= 18 + name_len:
                    name = data[18:18+name_len].decode('utf-8', errors='replace')
                    root_names[child_id] = name

    # Build subvolume list
    for objectid, bytenr in root_items.items():
        if objectid >= BTRFS_OBJECTID.FIRST_FREE:  # >= 256, user subvolumes
            name = root_names.get(objectid, f"subvol_{objectid}")
            subvolumes.append((objectid, name, bytenr))

    # Also include FS_TREE (5) if it exists
    if BTRFS_OBJECTID.FS_TREE in root_items:
        subvolumes.insert(0, (BTRFS_OBJECTID.FS_TREE, "(default)", root_items[BTRFS_OBJECTID.FS_TREE]))

    return subvolumes


def parse_all_subvolumes(f: BinaryIO, sb: BtrfsSuperblock,
                         chunk_map: ChunkMap) -> FileSystem:
    """
    Parse all subvolumes and combine into a single filesystem view.
    """
    subvolumes = find_all_subvolumes(f, sb, chunk_map)

    combined_fs = FileSystem()

    for objectid, subvol_name, bytenr in subvolumes:
        try:
            # Parse this subvolume's tree
            fs = parse_filesystem(f, bytenr, chunk_map, sb.nodesize)

            # Merge into combined filesystem with subvolume prefix
            for inode, inode_item in fs.inodes.items():
                # Create unique inode by combining subvolume id and original inode
                unique_inode = (objectid << 48) | inode
                combined_fs.inodes[unique_inode] = inode_item

                # Update name with subvolume context
                orig_name = fs.names.get(inode, '')
                if orig_name:
                    combined_fs.names[unique_inode] = orig_name

                # Update parent reference
                if inode in fs.parents:
                    parent = fs.parents[inode]
                    unique_parent = (objectid << 48) | parent
                    combined_fs.parents[unique_inode] = unique_parent

                # Update extents with unique_inode key
                if inode in fs.extents:
                    combined_fs.extents[unique_inode] = fs.extents[inode]

                # Update xattrs with unique_inode key
                if inode in fs.xattrs:
                    combined_fs.xattrs[unique_inode] = fs.xattrs[inode]

            # Store subvolume root info
            # The root inode (256) of each subvolume
            root_inode = (objectid << 48) | 256
            if root_inode in combined_fs.inodes:
                if objectid == BTRFS_OBJECTID.FS_TREE:
                    combined_fs.names[root_inode] = "/"
                else:
                    combined_fs.names[root_inode] = f"/{subvol_name}"

        except Exception:
            # Skip subvolumes that fail to parse
            continue

    return combined_fs


def parse_filesystem(f: BinaryIO, fs_tree_root: int,
                     chunk_map: ChunkMap, nodesize: int) -> FileSystem:
    """Parse all inodes and directory entries from filesystem tree."""
    fs = FileSystem()

    items = traverse_tree_all(f, fs_tree_root, chunk_map, nodesize)

    for item, data in items:
        objectid = item.key.objectid
        item_type = item.key.type

        try:
            if item_type == BTRFS_TYPE.INODE_ITEM:
                # Parse inode metadata
                if len(data) >= 160:
                    inode_item = BtrfsInodeItem.unpack(data)
                    fs.inodes[objectid] = inode_item

            elif item_type == BTRFS_TYPE.INODE_REF:
                # Parse inode reference (name + parent)
                # Format: index(8) + name_len(2) + name(variable)
                if len(data) >= 10:
                    name_len = struct.unpack_from('<H', data, 8)[0]
                    if len(data) >= 10 + name_len:
                        name = data[10:10+name_len].decode('utf-8', errors='replace')
                        fs.names[objectid] = name
                        fs.parents[objectid] = item.key.offset  # parent inode

                        # Track children
                        parent = item.key.offset
                        if parent not in fs.children:
                            fs.children[parent] = []
                        fs.children[parent].append(objectid)

            elif item_type == BTRFS_TYPE.DIR_ITEM:
                # Parse directory entry
                if len(data) >= 30:
                    dir_item = BtrfsDirItem.unpack(data)
                    if objectid not in fs.dir_entries:
                        fs.dir_entries[objectid] = []
                    fs.dir_entries[objectid].append(dir_item)

            elif item_type == BTRFS_TYPE.XATTR_ITEM:
                # Parse extended attribute (reuses DIR_ITEM structure)
                if len(data) >= 30:
                    xattr = BtrfsDirItem.unpack(data)
                    if objectid not in fs.xattrs:
                        fs.xattrs[objectid] = []
                    # Store xattr name and data (if data_len > 0, data follows name)
                    xattr_data = data[30+xattr.name_len:30+xattr.name_len+xattr.data_len] if xattr.data_len > 0 else b''
                    fs.xattrs[objectid].append((xattr.name, xattr_data))

            elif item_type == BTRFS_TYPE.EXTENT_DATA:
                # Parse file extent data
                if len(data) >= 21:
                    extent = BtrfsFileExtentItem.unpack(data)
                    if objectid not in fs.extents:
                        fs.extents[objectid] = []

                    # For inline extents (type=0), extract the inline data
                    inline_data = None
                    if extent.type == 0 and len(data) > 21:
                        # Inline data starts after fixed header (21 bytes)
                        inline_data = data[21:]

                    # key.offset = file offset
                    # Store: (file_offset, disk_bytenr, disk_num_bytes, compression, extent_type, inline_data)
                    fs.extents[objectid].append((
                        item.key.offset,
                        extent.disk_bytenr,
                        extent.disk_num_bytes,
                        extent.compression,
                        extent.type,
                        inline_data
                    ))

        except Exception:
            # Skip malformed items
            continue

    return fs


def build_path(fs: FileSystem, inode: int, max_depth: int = 100) -> str:
    """Build full path for an inode by walking up parent chain."""
    parts = []
    current = inode
    depth = 0
    seen = set()

    while current in fs.names and depth < max_depth:
        if current in seen:
            break  # Prevent infinite loop
        seen.add(current)

        name = fs.names[current]
        # Don't add the subvolume root name if it starts with /
        if name.startswith('/'):
            parts.append(name)
            break
        parts.append(name)

        if current in fs.parents:
            parent = fs.parents[current]
            if parent == current:
                break
            current = parent
        else:
            break
        depth += 1

    parts.reverse()

    # Build the path
    if parts and parts[0].startswith('/'):
        # Subvolume root
        root = parts[0]
        rest = '/'.join(parts[1:]) if len(parts) > 1 else ''
        if root == '/':
            return '/' + rest if rest else '/'
        else:
            return root + '/' + rest if rest else root
    else:
        return '/' + '/'.join(parts) if parts else '/'


def get_file_type(mode: int) -> str:
    """Determine file type from mode."""
    if stat.S_ISDIR(mode):
        return 'directory'
    elif stat.S_ISREG(mode):
        return 'file'
    elif stat.S_ISLNK(mode):
        return 'symlink'
    elif stat.S_ISCHR(mode):
        return 'chrdev'
    elif stat.S_ISBLK(mode):
        return 'blkdev'
    elif stat.S_ISFIFO(mode):
        return 'fifo'
    elif stat.S_ISSOCK(mode):
        return 'socket'
    else:
        return 'unknown'


def read_file_data(f: BinaryIO, extents: List[tuple], chunk_map: ChunkMap,
                   max_size: int = 0) -> bytes:
    """
    Read file data by following extent mappings.

    Args:
        f: Open file handle to disk image
        extents: List of (file_offset, disk_bytenr, disk_num_bytes, compression, extent_type, inline_data)
        chunk_map: ChunkMap for logical->physical translation
        max_size: Maximum bytes to read (0 = read all)

    Returns:
        File data as bytes
    """
    if not extents:
        return b''

    # Sort extents by file offset
    sorted_extents = sorted(extents, key=lambda e: e[0])

    file_data = bytearray()

    for extent_info in sorted_extents:
        # Unpack extent (handle both old and new formats)
        if len(extent_info) == 6:
            file_offset, disk_bytenr, disk_num_bytes, compression, extent_type, inline_data = extent_info
        else:
            # Old format compatibility
            file_offset, disk_bytenr, disk_num_bytes, compression = extent_info
            extent_type = 1  # Assume regular extent
            inline_data = None

        # Handle inline extents (type=0)
        if extent_type == 0 and inline_data:
            # Inline data is embedded in the extent item
            # Decompress if needed
            decompressed = decompress_data(inline_data, compression)
            if decompressed:
                file_data.extend(decompressed)
            continue

        # Skip holes (sparse regions) for regular extents
        if disk_bytenr == 0:
            # Fill with zeros for hole
            file_data.extend(b'\x00' * disk_num_bytes)
            continue

        # Skip compressed extents (would need decompression)
        if compression != 0:
            continue

        # Translate logical to physical address
        physical_offset = chunk_map.logical_to_physical(disk_bytenr)
        if not physical_offset:
            continue

        # Read extent data
        try:
            f.seek(physical_offset)
            extent_data = f.read(disk_num_bytes)
            file_data.extend(extent_data)
        except Exception:
            continue

        # Stop if we've read enough
        if max_size > 0 and len(file_data) >= max_size:
            break

    # Truncate to max_size if specified
    if max_size > 0 and len(file_data) > max_size:
        file_data = file_data[:max_size]

    return bytes(file_data)


def decompress_data(data: bytes, compression: int) -> Optional[bytes]:
    """
    Decompress BTRFS compressed data.

    Args:
        data: Compressed data bytes
        compression: Compression type (0=none, 1=zlib, 2=lzo, 3=zstd)

    Returns:
        Decompressed data bytes, or None if decompression failed or not supported
    """
    if compression == 0:
        # No compression
        return data

    elif compression == 1:
        # ZLIB compression
        try:
            return zlib.decompress(data)
        except Exception:
            return None

    elif compression == 2:
        # LZO compression
        if not HAS_LZO:
            return None
        try:
            return lzo.decompress(data)
        except Exception:
            return None

    elif compression == 3:
        # ZSTD compression
        if not HAS_ZSTD:
            return None
        try:
            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(data)
        except Exception:
            return None

    return None


def calculate_hashes(data: bytes) -> tuple:
    """
    Calculate MD5 and SHA256 hashes for data.

    Returns:
        (md5_hex, sha256_hex)
    """
    if not data:
        return (None, None)

    md5_hash = hashlib.md5(data).hexdigest()
    sha256_hash = hashlib.sha256(data).hexdigest()

    return (md5_hash, sha256_hash)


def parse_passwd_data(data: bytes) -> Dict[int, str]:
    """
    Parse /etc/passwd format and return uid->username mapping.

    Format: username:password:uid:gid:gecos:home:shell
    Example: root:x:0:0:root:/root:/bin/bash

    Args:
        data: Contents of /etc/passwd file

    Returns:
        Dictionary mapping uid (int) -> username (str)
    """
    uid_map = {}

    try:
        text = data.decode('utf-8', errors='ignore')
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(':')
            if len(parts) >= 3:
                username = parts[0]
                try:
                    uid = int(parts[2])
                    uid_map[uid] = username
                except (ValueError, IndexError):
                    continue
    except Exception:
        pass

    return uid_map


def parse_group_data(data: bytes) -> Dict[int, str]:
    """
    Parse /etc/group format and return gid->groupname mapping.

    Format: groupname:password:gid:members
    Example: root:x:0:

    Args:
        data: Contents of /etc/group file

    Returns:
        Dictionary mapping gid (int) -> groupname (str)
    """
    gid_map = {}

    try:
        text = data.decode('utf-8', errors='ignore')
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = line.split(':')
            if len(parts) >= 3:
                groupname = parts[0]
                try:
                    gid = int(parts[2])
                    gid_map[gid] = groupname
                except (ValueError, IndexError):
                    continue
    except Exception:
        pass

    return gid_map


def resolve_names_from_filesystem(fs: FileSystem, chunk_map: Optional[ChunkMap],
                                   disk_file: Optional[BinaryIO]) -> tuple:
    """
    Extract and parse /etc/passwd and /etc/group from the filesystem.

    Searches multiple possible locations:
    - /etc/passwd and /etc/group (standard Linux)
    - /root/etc/passwd and /root/etc/group (alternative/embedded systems)

    Args:
        fs: Parsed FileSystem object
        chunk_map: ChunkMap for logical->physical translation
        disk_file: Open file handle to disk image

    Returns:
        Tuple of (uid_map, gid_map) where each is a dict mapping id->name
    """
    uid_map = {}
    gid_map = {}

    if not chunk_map or not disk_file:
        return (uid_map, gid_map)

    # Possible paths to search for passwd and group files
    passwd_paths = ['/etc/passwd', '/root/etc/passwd']
    group_paths = ['/etc/group', '/root/etc/group']

    # Find passwd and group file inodes
    passwd_inode = None
    group_inode = None

    for unique_inode, name in fs.names.items():
        path = build_path(fs, unique_inode)

        # Check all possible passwd locations
        if path in passwd_paths and passwd_inode is None:
            passwd_inode = unique_inode

        # Check all possible group locations
        if path in group_paths and group_inode is None:
            group_inode = unique_inode

    # Parse /etc/passwd (or /root/etc/passwd)
    if passwd_inode and passwd_inode in fs.extents:
        try:
            passwd_data = read_file_data(disk_file, fs.extents[passwd_inode],
                                        chunk_map, max_size=0)
            uid_map = parse_passwd_data(passwd_data)
        except Exception:
            pass

    # Parse /etc/group (or /root/etc/group)
    if group_inode and group_inode in fs.extents:
        try:
            group_data = read_file_data(disk_file, fs.extents[group_inode],
                                       chunk_map, max_size=0)
            gid_map = parse_group_data(group_data)
        except Exception:
            pass

    return (uid_map, gid_map)


def extract_files(fs: FileSystem, chunk_map: Optional[ChunkMap] = None,
                  disk_file: Optional[BinaryIO] = None) -> List[FileEntry]:
    """Convert parsed filesystem to list of FileEntry objects."""
    entries = []

    # Resolve user and group names from /etc/passwd and /etc/group
    uid_map, gid_map = resolve_names_from_filesystem(fs, chunk_map, disk_file)

    # Helper function to count checksums for a file's extents
    def count_checksums(unique_inode: int) -> int:
        """Count how many checksums cover this file's extents."""
        if unique_inode not in fs.extents or not fs.checksums:
            return 0

        total_checksums = 0
        for extent_info in fs.extents[unique_inode]:
            # Unpack extent (handle both old and new formats)
            if len(extent_info) == 6:
                file_offset, disk_bytenr, disk_bytes, compression, extent_type, inline_data = extent_info
            else:
                file_offset, disk_bytenr, disk_bytes, compression = extent_info

            if disk_bytenr == 0:  # Skip holes/sparse/inline extents
                continue

            # Find checksums that overlap with this extent
            # Checksums are indexed by logical offset (disk_bytenr)
            for csum_start, csum_count in fs.checksums.items():
                csum_end = csum_start + (csum_count * 4096)  # Assume 4K per checksum
                extent_end = disk_bytenr + disk_bytes

                # Check if ranges overlap
                if disk_bytenr < csum_end and extent_end > csum_start:
                    # Calculate overlap
                    overlap_start = max(disk_bytenr, csum_start)
                    overlap_end = min(extent_end, csum_end)
                    overlap_bytes = overlap_end - overlap_start
                    if overlap_bytes > 0:
                        # Count checksums in overlap (one per 4K block)
                        total_checksums += (overlap_bytes + 4095) // 4096

        return total_checksums

    for unique_inode, inode_item in fs.inodes.items():
        # Extract original inode (lower 48 bits) and subvolume id (upper 16 bits)
        original_inode = unique_inode & 0xFFFFFFFFFFFF
        subvol_id = unique_inode >> 48

        name = fs.names.get(unique_inode, '(unknown)')
        path = build_path(fs, unique_inode)
        mode = inode_item.mode
        file_type = get_file_type(mode)

        # Skip entries with placeholder names at root
        if name == '(unknown)' and path == '/':
            continue

        try:
            entry = FileEntry(
                inode=original_inode,
                name=name,
                path=path,
                size=inode_item.size,
                type=file_type,
                mode=mode,
                mode_str=parse_mode(mode),
                uid=inode_item.uid,
                gid=inode_item.gid,
                nlink=inode_item.nlink,
                atime=inode_item.atime.to_iso(),
                mtime=inode_item.mtime.to_iso(),
                ctime=inode_item.ctime.to_iso(),
                otime=inode_item.otime.to_iso(),
                parent_inode=fs.parents.get(unique_inode),
                uid_name=uid_map.get(inode_item.uid),
                gid_name=gid_map.get(inode_item.gid),
                # Phase 1: Already parsed data
                generation=inode_item.generation,
                transid=inode_item.transid,
                flags=inode_item.flags,
                flags_str=parse_inode_flags(inode_item.flags),
                # Phase 5: Subvolume ID
                subvolume_id=subvol_id,
                # Phase 2: Extended attributes count
                xattr_count=len(fs.xattrs.get(unique_inode, [])),
                # Phase 3: Extent data summary
                extent_count=len(fs.extents.get(unique_inode, [])),
                disk_bytes=sum(e[2] for e in fs.extents.get(unique_inode, [])),
                # Phase 6: Physical offset (first extent)
                physical_offset=None,
                # Phase 4: Checksum count
                checksum_count=count_checksums(unique_inode)
            )

            # Store unique_inode for extraction lookup
            entry.unique_inode = unique_inode

            # Calculate physical offset if we have extents and chunk_map
            if chunk_map and unique_inode in fs.extents and fs.extents[unique_inode]:
                first_extent = fs.extents[unique_inode][0]
                logical_addr = first_extent[1]  # disk_bytenr
                if logical_addr > 0:  # Skip holes/sparse extents
                    physical_offset = chunk_map.logical_to_physical(logical_addr)
                    if physical_offset:
                        entry.physical_offset = physical_offset

            # Calculate MD5/SHA256 hashes for regular files
            if (file_type == 'file' and disk_file and chunk_map and
                unique_inode in fs.extents and inode_item.size > 0):
                try:
                    # Read file data (limit to actual file size)
                    file_data = read_file_data(disk_file, fs.extents[unique_inode],
                                              chunk_map, inode_item.size)
                    # Calculate hashes
                    md5_hash, sha256_hash = calculate_hashes(file_data)
                    entry.md5 = md5_hash
                    entry.sha256 = sha256_hash
                except Exception:
                    # Skip files that fail to read
                    pass

            entries.append(entry)
        except Exception:
            # Skip entries that fail to convert
            continue

    # Sort by path
    entries.sort(key=lambda e: e.path)
    return entries
