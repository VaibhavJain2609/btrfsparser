"""
BTRFS Constants - Magic numbers, offsets, and type enums.
"""
import stat

# Superblock location constants
SUPERBLOCK_OFFSET = 0x10000        # 65536 bytes (64 KiB) relative to partition start
SUPERBLOCK_MIRROR_1 = 0x4000000    # 64 MiB
SUPERBLOCK_MIRROR_2 = 0x4000000000 # 256 GiB
SUPERBLOCK_SIZE = 4096

# Magic and size constants
BTRFS_MAGIC = b'_BHRfS_M'
BTRFS_CSUM_SIZE = 32
BTRFS_FSID_SIZE = 16
BTRFS_UUID_SIZE = 16
BTRFS_LABEL_SIZE = 256
BTRFS_SYSTEM_CHUNK_ARRAY_SIZE = 2048
BTRFS_NUM_BACKUP_ROOTS = 4


class SB_OFFSET:
    """Superblock field offsets (exact byte positions)."""
    CSUM = 0x00              # 32 bytes - checksum
    FSID = 0x20              # 16 bytes - filesystem UUID
    BYTENR = 0x30            # 8 bytes - physical address of this block
    FLAGS = 0x38             # 8 bytes
    MAGIC = 0x40             # 8 bytes - must be "_BHRfS_M"
    GENERATION = 0x48        # 8 bytes
    ROOT = 0x50              # 8 bytes - logical addr of root tree
    CHUNK_ROOT = 0x58        # 8 bytes - logical addr of chunk tree
    LOG_ROOT = 0x60          # 8 bytes
    LOG_ROOT_TRANSID = 0x68  # 8 bytes (unused/deprecated)
    TOTAL_BYTES = 0x70       # 8 bytes
    BYTES_USED = 0x78        # 8 bytes
    ROOT_DIR_OBJECTID = 0x80 # 8 bytes (typically 6)
    NUM_DEVICES = 0x88       # 8 bytes
    SECTORSIZE = 0x90        # 4 bytes
    NODESIZE = 0x94          # 4 bytes
    LEAFSIZE = 0x98          # 4 bytes (unused, == nodesize)
    STRIPESIZE = 0x9C        # 4 bytes
    SYS_CHUNK_ARRAY_SIZE = 0xA0  # 4 bytes
    CHUNK_ROOT_GENERATION = 0xA4 # 8 bytes
    COMPAT_FLAGS = 0xAC      # 8 bytes
    COMPAT_RO_FLAGS = 0xB4   # 8 bytes
    INCOMPAT_FLAGS = 0xBC    # 8 bytes
    CSUM_TYPE = 0xC4         # 2 bytes (0 = CRC32C)
    ROOT_LEVEL = 0xC6        # 1 byte
    CHUNK_ROOT_LEVEL = 0xC7  # 1 byte
    LOG_ROOT_LEVEL = 0xC8    # 1 byte
    DEV_ITEM = 0xC9          # 98 bytes
    LABEL = 0x12B            # 256 bytes
    CACHE_GENERATION = 0x22B # 8 bytes
    UUID_TREE_GENERATION = 0x233  # 8 bytes
    METADATA_UUID = 0x23B    # 16 bytes
    SYS_CHUNK_ARRAY = 0x32B  # 2048 bytes
    SUPER_ROOTS = 0xB2B      # 672 bytes (4 x 168 bytes)


class HEADER_OFFSET:
    """Tree block header offsets (101 bytes total)."""
    CSUM = 0x00              # 32 bytes
    FSID = 0x20              # 16 bytes
    BYTENR = 0x30            # 8 bytes - logical address of this block
    FLAGS = 0x38             # 8 bytes
    CHUNK_TREE_UUID = 0x40   # 16 bytes
    GENERATION = 0x50        # 8 bytes
    OWNER = 0x58             # 8 bytes - tree objectid
    NRITEMS = 0x60           # 4 bytes - number of items
    LEVEL = 0x64             # 1 byte - 0=leaf, >0=internal node


HEADER_SIZE = 101


class BTRFS_TYPE:
    """Item types (key.type values)."""
    INODE_ITEM = 1
    INODE_REF = 12
    INODE_EXTREF = 13
    XATTR_ITEM = 24
    ORPHAN_ITEM = 48
    DIR_LOG_ITEM = 60
    DIR_LOG_INDEX = 72
    DIR_ITEM = 84
    DIR_INDEX = 96
    EXTENT_DATA = 108
    EXTENT_CSUM = 128
    ROOT_ITEM = 132
    ROOT_BACKREF = 144
    ROOT_REF = 156
    EXTENT_ITEM = 168
    METADATA_ITEM = 169
    TREE_BLOCK_REF = 176
    EXTENT_DATA_REF = 178
    SHARED_BLOCK_REF = 182
    SHARED_DATA_REF = 184
    BLOCK_GROUP_ITEM = 192
    FREE_SPACE_INFO = 198
    FREE_SPACE_EXTENT = 199
    FREE_SPACE_BITMAP = 200
    DEV_EXTENT = 204
    DEV_ITEM = 216
    CHUNK_ITEM = 228
    QGROUP_STATUS = 240
    QGROUP_INFO = 242
    QGROUP_LIMIT = 244
    QGROUP_RELATION = 246


class BTRFS_OBJECTID:
    """Tree object IDs."""
    ROOT_TREE = 1
    EXTENT_TREE = 2
    CHUNK_TREE = 3
    DEV_TREE = 4
    FS_TREE = 5
    ROOT_TREE_DIR = 6
    CSUM_TREE = 7
    QUOTA_TREE = 8
    UUID_TREE = 9
    FREE_SPACE_TREE = 10
    FIRST_FREE = 256        # First free objectid for files/dirs
    LAST_FREE = 0xFFFFFFFFFFFFFF00
    FIRST_CHUNK_TREE = 256


class BTRFS_FT:
    """Directory entry types."""
    UNKNOWN = 0
    REG_FILE = 1
    DIR = 2
    CHRDEV = 3
    BLKDEV = 4
    FIFO = 5
    SOCK = 6
    SYMLINK = 7
    XATTR = 8


FT_NAMES = {
    0: 'unknown',
    1: 'file',
    2: 'directory',
    3: 'chrdev',
    4: 'blkdev',
    5: 'fifo',
    6: 'socket',
    7: 'symlink',
    8: 'xattr'
}


<<<<<<< HEAD
<<<<<<< HEAD
=======
>>>>>>> 286cf09 (feat: added hashing)
class BTRFS_INODE_FLAGS:
    """Inode flags (from inode_item.flags field)."""
    NODATASUM = 1 << 0      # Don't checksum
    NODATACOW = 1 << 1      # Don't COW data
    READONLY = 1 << 2       # Readonly inode
    NOCOMPRESS = 1 << 3     # Don't compress
    PREALLOC = 1 << 4       # Preallocated extent
    SYNC = 1 << 5           # Sync updates
    IMMUTABLE = 1 << 6      # Immutable file
    APPEND = 1 << 7         # Append only
    NODUMP = 1 << 8         # Don't dump
    NOATIME = 1 << 9        # Don't update atime
    DIRSYNC = 1 << 10       # Directory sync
    COMPRESS = 1 << 11      # Compress this file


def parse_inode_flags(flags: int) -> str:
    """Convert inode flags to comma-separated string."""
    if flags == 0:
        return ''

    result = []
    if flags & BTRFS_INODE_FLAGS.NODATASUM:
        result.append('NODATASUM')
    if flags & BTRFS_INODE_FLAGS.NODATACOW:
        result.append('NODATACOW')
    if flags & BTRFS_INODE_FLAGS.READONLY:
        result.append('READONLY')
    if flags & BTRFS_INODE_FLAGS.NOCOMPRESS:
        result.append('NOCOMPRESS')
    if flags & BTRFS_INODE_FLAGS.PREALLOC:
        result.append('PREALLOC')
    if flags & BTRFS_INODE_FLAGS.SYNC:
        result.append('SYNC')
    if flags & BTRFS_INODE_FLAGS.IMMUTABLE:
        result.append('IMMUTABLE')
    if flags & BTRFS_INODE_FLAGS.APPEND:
        result.append('APPEND')
    if flags & BTRFS_INODE_FLAGS.NODUMP:
        result.append('NODUMP')
    if flags & BTRFS_INODE_FLAGS.NOATIME:
        result.append('NOATIME')
    if flags & BTRFS_INODE_FLAGS.DIRSYNC:
        result.append('DIRSYNC')
    if flags & BTRFS_INODE_FLAGS.COMPRESS:
        result.append('COMPRESS')

    return ','.join(result)


<<<<<<< HEAD
=======
>>>>>>> f40cb6e (initial commit)
=======
>>>>>>> 286cf09 (feat: added hashing)
def parse_mode(mode: int) -> str:
    """Convert mode integer to string like 'drwxr-xr-x'."""
    file_type = {
        stat.S_IFREG: '-',
        stat.S_IFDIR: 'd',
        stat.S_IFLNK: 'l',
        stat.S_IFBLK: 'b',
        stat.S_IFCHR: 'c',
        stat.S_IFIFO: 'p',
        stat.S_IFSOCK: 's'
    }.get(stat.S_IFMT(mode), '?')

    perms = ''
    for who in [(stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
                (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
                (stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH)]:
        perms += 'r' if mode & who[0] else '-'
        perms += 'w' if mode & who[1] else '-'
        perms += 'x' if mode & who[2] else '-'
    return file_type + perms
