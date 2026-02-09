"""
BTRFS Superblock Parser - Read and validate superblock from image file.
"""
from constants import SUPERBLOCK_OFFSET, SUPERBLOCK_SIZE, BTRFS_MAGIC
from structures import BtrfsSuperblock


def read_superblock(image_path: str, partition_offset: int = 0) -> BtrfsSuperblock:
    """
    Read and parse superblock from image file.

    Args:
        image_path: Path to image file
        partition_offset: Byte offset where the BTRFS partition starts (default: 0)
    """
    absolute_offset = partition_offset + SUPERBLOCK_OFFSET

    with open(image_path, 'rb') as f:
        f.seek(absolute_offset)
        data = f.read(SUPERBLOCK_SIZE)

    if len(data) != SUPERBLOCK_SIZE:
        raise ValueError(f"Failed to read superblock: got {len(data)} bytes, expected {SUPERBLOCK_SIZE}")

    sb = BtrfsSuperblock.unpack(data)

    if not sb.validate():
        raise ValueError(f"Invalid BTRFS magic: {sb.magic!r}, expected {BTRFS_MAGIC!r}")

    return sb


def print_superblock_info(sb: BtrfsSuperblock):
    """Display superblock information."""
    print("=== BTRFS Superblock ===")
    print(f"Label:           {sb.label or '(none)'}")
    print(f"UUID:            {format_uuid(sb.fsid)}")
    print(f"Generation:      {sb.generation}")
    print(f"Total bytes:     {sb.total_bytes:,} ({sb.total_bytes / 1024**3:.2f} GiB)")
    print(f"Bytes used:      {sb.bytes_used:,} ({sb.bytes_used / 1024**3:.2f} GiB)")
    print(f"Node size:       {sb.nodesize}")
    print(f"Sector size:     {sb.sectorsize}")
    print(f"Root tree addr:  0x{sb.root:x}")
    print(f"Chunk tree addr: 0x{sb.chunk_root:x}")
    print(f"Devices:         {sb.num_devices}")
    print(f"Checksum type:   {sb.csum_type} ({'CRC32C' if sb.csum_type == 0 else 'Unknown'})")


def format_uuid(uuid_bytes: bytes) -> str:
    """Format UUID bytes as standard UUID string."""
    hex_str = uuid_bytes.hex()
    return f"{hex_str[0:8]}-{hex_str[8:12]}-{hex_str[12:16]}-{hex_str[16:20]}-{hex_str[20:32]}"
