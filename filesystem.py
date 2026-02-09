"""
BTRFS Filesystem Parser - Extract files and directories from filesystem tree.
"""
import struct
import stat
from typing import Dict, List, Optional, BinaryIO
from dataclasses import dataclass, field

from structures import BtrfsInodeItem, BtrfsDirItem, BtrfsSuperblock
from constants import BTRFS_TYPE, BTRFS_OBJECTID, parse_mode
from chunk import ChunkMap
from btree import traverse_tree_all


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


@dataclass
class FileSystem:
    """Holds parsed filesystem state."""
    inodes: Dict[int, BtrfsInodeItem] = field(default_factory=dict)
    names: Dict[int, str] = field(default_factory=dict)           # inode -> name
    parents: Dict[int, int] = field(default_factory=dict)         # inode -> parent_inode
    children: Dict[int, List[int]] = field(default_factory=dict)  # inode -> [child_inodes]
    dir_entries: Dict[int, List[BtrfsDirItem]] = field(default_factory=dict)


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


def extract_files(fs: FileSystem) -> List[FileEntry]:
    """Convert parsed filesystem to list of FileEntry objects."""
    entries = []

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
                parent_inode=fs.parents.get(unique_inode)
            )
            entries.append(entry)
        except Exception:
            # Skip entries that fail to convert
            continue

    # Sort by path
    entries.sort(key=lambda e: e.path)
    return entries
