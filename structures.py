"""
BTRFS Data Structures - Dataclass definitions for parsing binary data.
"""
import struct
from dataclasses import dataclass
from datetime import datetime
from typing import List

# Structure size constants
BTRFS_KEY_SIZE = 17           # objectid(8) + type(1) + offset(8)
BTRFS_ITEM_SIZE = 25          # key(17) + offset(4) + size(4)
BTRFS_KEY_PTR_SIZE = 33       # key(17) + blockptr(8) + generation(8)
BTRFS_INODE_ITEM_SIZE = 160
BTRFS_TIMESPEC_SIZE = 12      # sec(8) + nsec(4)
BTRFS_DIR_ITEM_FIXED_SIZE = 30
BTRFS_CHUNK_ITEM_FIXED_SIZE = 48
BTRFS_STRIPE_SIZE = 32        # devid(8) + offset(8) + dev_uuid(16)
BTRFS_DEV_ITEM_SIZE = 98


@dataclass
class BtrfsKey:
    """17 bytes: objectid(8) + type(1) + offset(8)"""
    objectid: int
    type: int
    offset: int

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsKey':
        objectid = struct.unpack_from('<Q', data, pos)[0]
        type_ = struct.unpack_from('<B', data, pos + 8)[0]
        offset = struct.unpack_from('<Q', data, pos + 9)[0]
        return cls(objectid, type_, offset)

    def __repr__(self):
        return f"Key({self.objectid}, {self.type}, {self.offset})"


@dataclass
class BtrfsTimespec:
    """12 bytes: sec(8) + nsec(4)"""
    sec: int
    nsec: int

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsTimespec':
        sec = struct.unpack_from('<Q', data, pos)[0]
        nsec = struct.unpack_from('<I', data, pos + 8)[0]
        return cls(sec, nsec)

    def to_datetime(self) -> datetime:
        try:
            return datetime.fromtimestamp(self.sec + self.nsec / 1e9)
        except (OSError, OverflowError, ValueError):
            return datetime(1970, 1, 1)

    def to_iso(self) -> str:
        return self.to_datetime().isoformat()


@dataclass
class BtrfsHeader:
    """101 bytes - at start of every tree block."""
    csum: bytes           # 32 bytes
    fsid: bytes           # 16 bytes
    bytenr: int           # 8 bytes - logical address
    flags: int            # 8 bytes
    chunk_tree_uuid: bytes  # 16 bytes
    generation: int       # 8 bytes
    owner: int            # 8 bytes - tree objectid
    nritems: int          # 4 bytes
    level: int            # 1 byte (0=leaf)

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsHeader':
        return cls(
            csum=data[pos:pos+32],
            fsid=data[pos+32:pos+48],
            bytenr=struct.unpack_from('<Q', data, pos+48)[0],
            flags=struct.unpack_from('<Q', data, pos+56)[0],
            chunk_tree_uuid=data[pos+64:pos+80],
            generation=struct.unpack_from('<Q', data, pos+80)[0],
            owner=struct.unpack_from('<Q', data, pos+88)[0],
            nritems=struct.unpack_from('<I', data, pos+96)[0],
            level=struct.unpack_from('<B', data, pos+100)[0],
        )


@dataclass
class BtrfsItem:
    """25 bytes - item descriptor in leaf node."""
    key: BtrfsKey         # 17 bytes
    offset: int           # 4 bytes - offset to data in leaf
    size: int             # 4 bytes - size of data

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsItem':
        return cls(
            key=BtrfsKey.unpack(data, pos),
            offset=struct.unpack_from('<I', data, pos+17)[0],
            size=struct.unpack_from('<I', data, pos+21)[0],
        )


@dataclass
class BtrfsKeyPtr:
    """33 bytes - key pointer in internal node."""
    key: BtrfsKey         # 17 bytes
    blockptr: int         # 8 bytes - logical address
    generation: int       # 8 bytes

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsKeyPtr':
        return cls(
            key=BtrfsKey.unpack(data, pos),
            blockptr=struct.unpack_from('<Q', data, pos+17)[0],
            generation=struct.unpack_from('<Q', data, pos+25)[0],
        )


@dataclass
class BtrfsInodeItem:
    """160 bytes - file/directory metadata."""
    generation: int       # 8
    transid: int          # 8
    size: int             # 8 - file size in bytes
    nbytes: int           # 8 - allocated bytes
    block_group: int      # 8
    nlink: int            # 4 - hard link count
    uid: int              # 4
    gid: int              # 4
    mode: int             # 4 - permissions
    rdev: int             # 8
    flags: int            # 8
    sequence: int         # 8
    # reserved: 32 bytes (4 x 8)
    atime: BtrfsTimespec  # 12 - access time
    ctime: BtrfsTimespec  # 12 - change time
    mtime: BtrfsTimespec  # 12 - modification time
    otime: BtrfsTimespec  # 12 - creation time

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsInodeItem':
        return cls(
            generation=struct.unpack_from('<Q', data, pos)[0],
            transid=struct.unpack_from('<Q', data, pos+8)[0],
            size=struct.unpack_from('<Q', data, pos+16)[0],
            nbytes=struct.unpack_from('<Q', data, pos+24)[0],
            block_group=struct.unpack_from('<Q', data, pos+32)[0],
            nlink=struct.unpack_from('<I', data, pos+40)[0],
            uid=struct.unpack_from('<I', data, pos+44)[0],
            gid=struct.unpack_from('<I', data, pos+48)[0],
            mode=struct.unpack_from('<I', data, pos+52)[0],
            rdev=struct.unpack_from('<Q', data, pos+56)[0],
            flags=struct.unpack_from('<Q', data, pos+64)[0],
            sequence=struct.unpack_from('<Q', data, pos+72)[0],
            # skip reserved[4] at pos+80 (32 bytes)
            atime=BtrfsTimespec.unpack(data, pos+112),
            ctime=BtrfsTimespec.unpack(data, pos+124),
            mtime=BtrfsTimespec.unpack(data, pos+136),
            otime=BtrfsTimespec.unpack(data, pos+148),
        )


@dataclass
<<<<<<< HEAD
class BtrfsFileExtentItem:
    """Variable length - file extent mapping to disk."""
    generation: int       # 8 bytes
    ram_bytes: int        # 8 bytes - uncompressed size
    compression: int      # 1 byte - 0=none, 1=zlib, 2=lzo, 3=zstd
    encryption: int       # 1 byte
    other: int           # 2 bytes (reserved)
    type: int            # 1 byte - 0=inline, 1=regular, 2=prealloc
    # For type=1 (regular extent):
    disk_bytenr: int     # 8 bytes - logical disk address (0 if hole/sparse)
    disk_num_bytes: int  # 8 bytes - size on disk (compressed)
    offset: int          # 8 bytes - offset into uncompressed extent
    num_bytes: int       # 8 bytes - number of bytes in this extent

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsFileExtentItem':
        if len(data) < pos + 21:
            raise ValueError("Data too short for BtrfsFileExtentItem")

        generation = struct.unpack_from('<Q', data, pos)[0]
        ram_bytes = struct.unpack_from('<Q', data, pos+8)[0]
        compression = struct.unpack_from('<B', data, pos+16)[0]
        encryption = struct.unpack_from('<B', data, pos+17)[0]
        other = struct.unpack_from('<H', data, pos+18)[0]
        type_ = struct.unpack_from('<B', data, pos+20)[0]

        # For inline extents (type=0), data is embedded and there's no disk_bytenr
        # For regular/prealloc extents (type=1,2), parse disk location
        if type_ in (1, 2) and len(data) >= pos + 53:
            disk_bytenr = struct.unpack_from('<Q', data, pos+21)[0]
            disk_num_bytes = struct.unpack_from('<Q', data, pos+29)[0]
            offset = struct.unpack_from('<Q', data, pos+37)[0]
            num_bytes = struct.unpack_from('<Q', data, pos+45)[0]
        else:
            # Inline extent or insufficient data
            disk_bytenr = 0
            disk_num_bytes = 0
            offset = 0
            num_bytes = ram_bytes

        return cls(generation, ram_bytes, compression, encryption, other, type_,
                   disk_bytenr, disk_num_bytes, offset, num_bytes)


@dataclass
=======
>>>>>>> f40cb6e (initial commit)
class BtrfsDirItem:
    """Variable length - directory entry."""
    location: BtrfsKey    # 17 bytes - key of target inode
    transid: int          # 8 bytes
    data_len: int         # 2 bytes - xattr data length
    name_len: int         # 2 bytes
    type: int             # 1 byte - file type (BTRFS_FT_*)
    name: str             # variable

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsDirItem':
        location = BtrfsKey.unpack(data, pos)
        transid = struct.unpack_from('<Q', data, pos+17)[0]
        data_len = struct.unpack_from('<H', data, pos+25)[0]
        name_len = struct.unpack_from('<H', data, pos+27)[0]
        type_ = struct.unpack_from('<B', data, pos+29)[0]
        name = data[pos+30:pos+30+name_len].decode('utf-8', errors='replace')
        return cls(location, transid, data_len, name_len, type_, name)

    @property
    def total_size(self) -> int:
        return 30 + self.name_len + self.data_len


@dataclass
class BtrfsChunk:
    """Variable length - chunk mapping."""
    length: int           # 8 - chunk size
    owner: int            # 8 - root objectid
    stripe_len: int       # 8
    type: int             # 8 - block group flags
    io_align: int         # 4
    io_width: int         # 4
    sector_size: int      # 4
    num_stripes: int      # 2
    sub_stripes: int      # 2
    stripes: List[tuple]  # [(devid, offset, dev_uuid), ...]

    @classmethod
    def unpack(cls, data: bytes, pos: int = 0) -> 'BtrfsChunk':
        length = struct.unpack_from('<Q', data, pos)[0]
        owner = struct.unpack_from('<Q', data, pos+8)[0]
        stripe_len = struct.unpack_from('<Q', data, pos+16)[0]
        type_ = struct.unpack_from('<Q', data, pos+24)[0]
        io_align = struct.unpack_from('<I', data, pos+32)[0]
        io_width = struct.unpack_from('<I', data, pos+36)[0]
        sector_size = struct.unpack_from('<I', data, pos+40)[0]
        num_stripes = struct.unpack_from('<H', data, pos+44)[0]
        sub_stripes = struct.unpack_from('<H', data, pos+46)[0]

        stripes = []
        stripe_pos = pos + 48
        for _ in range(num_stripes):
            devid = struct.unpack_from('<Q', data, stripe_pos)[0]
            offset = struct.unpack_from('<Q', data, stripe_pos+8)[0]
            dev_uuid = data[stripe_pos+16:stripe_pos+32]
            stripes.append((devid, offset, dev_uuid))
            stripe_pos += 32

        return cls(length, owner, stripe_len, type_, io_align,
                   io_width, sector_size, num_stripes, sub_stripes, stripes)

    @property
    def total_size(self) -> int:
        return 48 + (32 * self.num_stripes)


@dataclass
class BtrfsSuperblock:
    """4096 bytes - filesystem superblock."""
    csum: bytes
    fsid: bytes
    bytenr: int
    flags: int
    magic: bytes
    generation: int
    root: int             # logical addr of root tree
    chunk_root: int       # logical addr of chunk tree
    log_root: int
    total_bytes: int
    bytes_used: int
    root_dir_objectid: int
    num_devices: int
    sectorsize: int
    nodesize: int
    stripesize: int
    sys_chunk_array_size: int
    chunk_root_generation: int
    csum_type: int
    root_level: int
    chunk_root_level: int
    log_root_level: int
    label: str
    sys_chunk_array: bytes

    @classmethod
    def unpack(cls, data: bytes) -> 'BtrfsSuperblock':
        label_raw = data[0x12B:0x12B+256]
        label = label_raw.split(b'\x00')[0].decode('utf-8', errors='replace')

        return cls(
            csum=data[0x00:0x20],
            fsid=data[0x20:0x30],
            bytenr=struct.unpack_from('<Q', data, 0x30)[0],
            flags=struct.unpack_from('<Q', data, 0x38)[0],
            magic=data[0x40:0x48],
            generation=struct.unpack_from('<Q', data, 0x48)[0],
            root=struct.unpack_from('<Q', data, 0x50)[0],
            chunk_root=struct.unpack_from('<Q', data, 0x58)[0],
            log_root=struct.unpack_from('<Q', data, 0x60)[0],
            total_bytes=struct.unpack_from('<Q', data, 0x70)[0],
            bytes_used=struct.unpack_from('<Q', data, 0x78)[0],
            root_dir_objectid=struct.unpack_from('<Q', data, 0x80)[0],
            num_devices=struct.unpack_from('<Q', data, 0x88)[0],
            sectorsize=struct.unpack_from('<I', data, 0x90)[0],
            nodesize=struct.unpack_from('<I', data, 0x94)[0],
            stripesize=struct.unpack_from('<I', data, 0x9C)[0],
            sys_chunk_array_size=struct.unpack_from('<I', data, 0xA0)[0],
            chunk_root_generation=struct.unpack_from('<Q', data, 0xA4)[0],
            csum_type=struct.unpack_from('<H', data, 0xC4)[0],
            root_level=struct.unpack_from('<B', data, 0xC6)[0],
            chunk_root_level=struct.unpack_from('<B', data, 0xC7)[0],
            log_root_level=struct.unpack_from('<B', data, 0xC8)[0],
            label=label,
            sys_chunk_array=data[0x32B:0x32B+2048],
        )

    def validate(self) -> bool:
        return self.magic == b'_BHRfS_M'
