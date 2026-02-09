"""
BTRFS Chunk Parser - Logical to physical address mapping.
"""
import struct
from typing import Dict, Optional, BinaryIO
from structures import BtrfsKey, BtrfsChunk, BtrfsHeader, BtrfsItem, BTRFS_ITEM_SIZE
from constants import HEADER_SIZE, BTRFS_TYPE


class ChunkMap:
    """Maps logical addresses to physical addresses."""

    def __init__(self):
        # Dict of {logical_start: (length, physical_offset)}
        self.chunks: Dict[int, tuple] = {}
        # Partition offset for multi-partition images
        self.partition_offset: int = 0

    def add_chunk(self, logical_start: int, length: int, physical_offset: int):
        """Add a chunk mapping."""
        self.chunks[logical_start] = (length, physical_offset)

    def logical_to_physical(self, logical_addr: int) -> Optional[int]:
        """
        Convert logical address to physical address.

        Returns absolute offset in the image file (includes partition offset).
        """
        for chunk_start, (length, physical_offset) in self.chunks.items():
            if chunk_start <= logical_addr < chunk_start + length:
                offset_in_chunk = logical_addr - chunk_start
                # Add partition offset for absolute file position
                return self.partition_offset + physical_offset + offset_in_chunk
        return None

    def __len__(self):
        return len(self.chunks)

    def __repr__(self):
        return f"ChunkMap({len(self.chunks)} chunks, partition_offset=0x{self.partition_offset:x})"


def parse_sys_chunk_array(sys_chunk_array: bytes, size: int) -> ChunkMap:
    """
    Parse the sys_chunk_array from superblock.

    Format: repeated (KEY, CHUNK_ITEM) pairs
    KEY format: objectid(8) + type(1) + offset(8) = 17 bytes
    The key.offset is the logical address of the chunk.
    """
    chunk_map = ChunkMap()
    pos = 0

    while pos < size:
        # Read key (17 bytes)
        if pos + 17 > size:
            break

        key = BtrfsKey.unpack(sys_chunk_array, pos)
        pos += 17

        # key.offset is the logical start address
        logical_start = key.offset

        # Read chunk item (need at least fixed header)
        if pos + 48 > size:
            break

        chunk = BtrfsChunk.unpack(sys_chunk_array, pos)

        # For single device, use first stripe's physical offset
        if chunk.stripes:
            physical_offset = chunk.stripes[0][1]  # (devid, offset, uuid)
            chunk_map.add_chunk(logical_start, chunk.length, physical_offset)

        pos += chunk.total_size

    return chunk_map


def read_chunk_tree(f: BinaryIO, chunk_tree_addr: int, chunk_map: ChunkMap,
                    nodesize: int) -> ChunkMap:
    """
    Read the full chunk tree to get all chunk mappings.

    This is needed because sys_chunk_array only contains system chunks,
    but we need metadata and data chunks too.
    """
    visited = set()

    def traverse_chunk_tree(logical_addr: int):
        if logical_addr in visited:
            return
        visited.add(logical_addr)

        physical = chunk_map.logical_to_physical(logical_addr)
        if physical is None:
            return

        f.seek(physical)
        block = f.read(nodesize)

        if len(block) < HEADER_SIZE:
            return

        header = BtrfsHeader.unpack(block)

        if header.level == 0:
            # Leaf node - parse CHUNK_ITEMs
            item_pos = HEADER_SIZE
            for i in range(header.nritems):
                if item_pos + BTRFS_ITEM_SIZE > len(block):
                    break

                item = BtrfsItem.unpack(block, item_pos)

                if item.key.type == BTRFS_TYPE.CHUNK_ITEM:
                    # item.key.offset is the logical address
                    logical_start = item.key.offset

                    data_start = HEADER_SIZE + item.offset
                    if data_start + 48 <= len(block):
                        try:
                            chunk = BtrfsChunk.unpack(block, data_start)
                            if chunk.stripes:
                                physical_offset = chunk.stripes[0][1]
                                chunk_map.add_chunk(logical_start, chunk.length, physical_offset)
                        except Exception:
                            pass

                item_pos += BTRFS_ITEM_SIZE
        else:
            # Internal node - traverse children
            from structures import BtrfsKeyPtr, BTRFS_KEY_PTR_SIZE
            ptr_pos = HEADER_SIZE
            for i in range(header.nritems):
                if ptr_pos + BTRFS_KEY_PTR_SIZE > len(block):
                    break
                ptr = BtrfsKeyPtr.unpack(block, ptr_pos)
                traverse_chunk_tree(ptr.blockptr)
                ptr_pos += BTRFS_KEY_PTR_SIZE

    traverse_chunk_tree(chunk_tree_addr)
    return chunk_map
