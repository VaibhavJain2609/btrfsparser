"""
BTRFS Partition Detection - Automatically detect BTRFS partitions in disk images.

Supports both MBR (Master Boot Record) and GPT (GUID Partition Table) partition schemes.
"""
import struct
from typing import List, Tuple, Optional
from dataclasses import dataclass
from constants import BTRFS_MAGIC, SUPERBLOCK_OFFSET


@dataclass
class Partition:
    """Detected partition information."""
    index: int
    offset: int
    size: int
    type_name: str
    label: Optional[str] = None

    def __str__(self) -> str:
        size_gib = self.size / (1024**3)
        parts = [
            f"Partition {self.index}",
            f"Type: {self.type_name}",
            f"Offset: 0x{self.offset:x} ({self.offset} bytes)",
            f"Size: {size_gib:.2f} GiB"
        ]
        if self.label:
            parts.insert(1, f"Label: {self.label}")
        return " | ".join(parts)


def read_mbr(image_path: str) -> List[Tuple[int, int, int]]:
    """
    Read MBR partition table and return list of (partition_index, start_sector, size_sectors).

    MBR format:
    - Located at offset 0x0
    - Partition entries start at offset 0x1BE (446)
    - Each entry is 16 bytes
    - 4 partition entries maximum
    - Signature 0x55AA at offset 0x1FE

    Partition entry format (16 bytes):
    - Offset 0x00: Boot indicator (0x80 = bootable)
    - Offset 0x01-0x03: CHS start address
    - Offset 0x04: Partition type
    - Offset 0x05-0x07: CHS end address
    - Offset 0x08: LBA start (4 bytes, little endian)
    - Offset 0x0C: Number of sectors (4 bytes, little endian)
    """
    partitions = []

    with open(image_path, 'rb') as f:
        # Read MBR
        f.seek(0)
        mbr = f.read(512)

        # Check MBR signature
        if len(mbr) < 512 or mbr[0x1FE:0x200] != b'\x55\xAA':
            return partitions

        # Parse 4 partition entries
        for i in range(4):
            offset = 0x1BE + (i * 16)
            entry = mbr[offset:offset + 16]

            # Extract fields
            partition_type = entry[0x04]
            lba_start = struct.unpack('<I', entry[0x08:0x0C])[0]
            num_sectors = struct.unpack('<I', entry[0x0C:0x10])[0]

            # Skip empty partitions
            if partition_type == 0 or num_sectors == 0:
                continue

            partitions.append((i + 1, lba_start, num_sectors))

    return partitions


def read_gpt(image_path: str) -> List[Tuple[int, int, int, str]]:
    """
    Read GPT partition table and return list of (partition_index, start_lba, size_lba, name).

    GPT format:
    - Located at LBA 1 (sector 1, offset 512)
    - Header is 92 bytes minimum
    - Signature: "EFI PART"
    - Partition entries start at LBA specified in header
    - Each entry is typically 128 bytes
    - Up to 128 partition entries by default

    GPT Header (at LBA 1):
    - Offset 0x00: Signature "EFI PART" (8 bytes)
    - Offset 0x08: Revision (4 bytes)
    - Offset 0x0C: Header size (4 bytes)
    - Offset 0x20: Current LBA (8 bytes)
    - Offset 0x28: Backup LBA (8 bytes)
    - Offset 0x30: First usable LBA (8 bytes)
    - Offset 0x38: Last usable LBA (8 bytes)
    - Offset 0x48: Partition entry LBA (8 bytes)
    - Offset 0x50: Number of partition entries (4 bytes)
    - Offset 0x54: Size of partition entry (4 bytes)

    Partition Entry (typically 128 bytes):
    - Offset 0x00: Partition type GUID (16 bytes)
    - Offset 0x10: Unique partition GUID (16 bytes)
    - Offset 0x20: Starting LBA (8 bytes)
    - Offset 0x28: Ending LBA (8 bytes)
    - Offset 0x30: Attributes (8 bytes)
    - Offset 0x38: Partition name (72 bytes, UTF-16LE)
    """
    partitions = []

    with open(image_path, 'rb') as f:
        # Read GPT header at LBA 1
        f.seek(512)
        header = f.read(512)

        # Check GPT signature
        if len(header) < 92 or header[0:8] != b'EFI PART':
            return partitions

        # Parse GPT header
        partition_entry_lba = struct.unpack('<Q', header[0x48:0x50])[0]
        num_entries = struct.unpack('<I', header[0x50:0x54])[0]
        entry_size = struct.unpack('<I', header[0x54:0x58])[0]

        # Read partition entries
        f.seek(partition_entry_lba * 512)
        entries_data = f.read(num_entries * entry_size)

        for i in range(num_entries):
            offset = i * entry_size
            entry = entries_data[offset:offset + entry_size]

            # Check if partition is empty (all zeros in type GUID)
            type_guid = entry[0:16]
            if type_guid == b'\x00' * 16:
                continue

            # Parse partition entry
            start_lba = struct.unpack('<Q', entry[0x20:0x28])[0]
            end_lba = struct.unpack('<Q', entry[0x28:0x30])[0]

            # Parse partition name (UTF-16LE, null-terminated)
            name_bytes = entry[0x38:0x38 + 72]
            try:
                name = name_bytes.decode('utf-16-le').rstrip('\x00')
            except:
                name = ''

            size_lba = end_lba - start_lba + 1
            partitions.append((i + 1, start_lba, size_lba, name))

    return partitions


def check_btrfs_signature(image_path: str, partition_offset: int) -> Tuple[bool, Optional[str]]:
    """
    Check if a partition contains BTRFS filesystem by reading the superblock signature.

    Returns:
        (is_btrfs, label) - tuple of boolean and optional label string
    """
    try:
        with open(image_path, 'rb') as f:
            # Seek to superblock location within partition
            f.seek(partition_offset + SUPERBLOCK_OFFSET)

            # Read magic number location (offset 0x40 within superblock)
            f.seek(partition_offset + SUPERBLOCK_OFFSET + 0x40)
            magic = f.read(8)

            if magic != BTRFS_MAGIC:
                return False, None

            # Read label (offset 0x12B within superblock, 256 bytes)
            f.seek(partition_offset + SUPERBLOCK_OFFSET + 0x12B)
            label_bytes = f.read(256)

            # Parse label (null-terminated string)
            label = label_bytes.split(b'\x00', 1)[0].decode('utf-8', errors='ignore')

            return True, label if label else None

    except Exception:
        return False, None


def detect_btrfs_partitions(image_path: str) -> List[Partition]:
    """
    Detect all BTRFS partitions in a disk image.

    Supports both MBR and GPT partition schemes.

    Returns:
        List of Partition objects with BTRFS filesystems
    """
    btrfs_partitions = []

    # Try MBR first
    mbr_partitions = read_mbr(image_path)

    if mbr_partitions:
        for index, start_sector, num_sectors in mbr_partitions:
            offset = start_sector * 512
            size = num_sectors * 512

            is_btrfs, label = check_btrfs_signature(image_path, offset)

            if is_btrfs:
                partition = Partition(
                    index=index,
                    offset=offset,
                    size=size,
                    type_name='MBR',
                    label=label
                )
                btrfs_partitions.append(partition)

        if btrfs_partitions:
            return btrfs_partitions

    # Try GPT
    gpt_partitions = read_gpt(image_path)

    if gpt_partitions:
        for index, start_lba, size_lba, name in gpt_partitions:
            offset = start_lba * 512
            size = size_lba * 512

            is_btrfs, label = check_btrfs_signature(image_path, offset)

            if is_btrfs:
                partition = Partition(
                    index=index,
                    offset=offset,
                    size=size,
                    type_name='GPT',
                    label=label or name
                )
                btrfs_partitions.append(partition)

    return btrfs_partitions


def format_partition_list(partitions: List[Partition]) -> str:
    """Format list of partitions for display."""
    lines = []
    for p in partitions:
        lines.append(f"  [{p.index}] {p}")
    return '\n'.join(lines)
