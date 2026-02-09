"""
BTRFS B-tree Traversal - Read and traverse tree blocks.
"""
from typing import List, Tuple, Optional, BinaryIO
from structures import (BtrfsHeader, BtrfsItem, BtrfsKeyPtr,
                        BTRFS_ITEM_SIZE, BTRFS_KEY_PTR_SIZE)
from constants import HEADER_SIZE
from chunk import ChunkMap


def read_tree_block(f: BinaryIO, logical_addr: int,
                    chunk_map: ChunkMap, nodesize: int) -> bytes:
    """Read a tree block given its logical address."""
    physical = chunk_map.logical_to_physical(logical_addr)
    if physical is None:
        raise ValueError(f"Cannot map logical address 0x{logical_addr:x}")

    f.seek(physical)
    return f.read(nodesize)


def parse_leaf_items(block: bytes) -> List[Tuple[BtrfsItem, bytes]]:
    """
    Parse all items from a leaf node.
    Returns list of (item_descriptor, item_data) tuples.

    Layout:
    [header 101 bytes][item0][item1]...[itemN]...[dataN]...[data1][data0]
    Items grow forward, data grows backward from end of block.
    """
    header = BtrfsHeader.unpack(block)

    if header.level != 0:
        raise ValueError(f"Not a leaf node: level={header.level}")

    items = []
    item_pos = HEADER_SIZE  # 101 bytes

    for i in range(header.nritems):
        item = BtrfsItem.unpack(block, item_pos)

        # item.offset is relative to start of block data area
        # Data area starts after header at offset HEADER_SIZE
        data_start = HEADER_SIZE + item.offset
        data = block[data_start:data_start + item.size]

        items.append((item, data))
        item_pos += BTRFS_ITEM_SIZE  # 25 bytes

    return items


def parse_internal_node(block: bytes) -> List[BtrfsKeyPtr]:
    """Parse key pointers from an internal node."""
    header = BtrfsHeader.unpack(block)

    if header.level == 0:
        raise ValueError("Not an internal node: level=0")

    ptrs = []
    ptr_pos = HEADER_SIZE  # 101 bytes

    for i in range(header.nritems):
        ptr = BtrfsKeyPtr.unpack(block, ptr_pos)
        ptrs.append(ptr)
        ptr_pos += BTRFS_KEY_PTR_SIZE  # 33 bytes

    return ptrs


def search_tree(f: BinaryIO, root_addr: int, chunk_map: ChunkMap,
                nodesize: int, target_objectid: int,
                target_type: Optional[int] = None) -> List[Tuple[BtrfsItem, bytes]]:
    """
    Search tree for items matching objectid (and optionally type).
    Returns all matching (item, data) tuples.
    """
    results = []
    visited = set()  # Prevent infinite loops

    def traverse(addr: int):
        if addr in visited:
            return
        visited.add(addr)

        try:
            block = read_tree_block(f, addr, chunk_map, nodesize)
        except ValueError:
            return  # Skip unmappable addresses

        header = BtrfsHeader.unpack(block)

        if header.level == 0:
            # Leaf node - check items
            try:
                for item, data in parse_leaf_items(block):
                    if item.key.objectid == target_objectid:
                        if target_type is None or item.key.type == target_type:
                            results.append((item, data))
            except Exception:
                pass  # Skip malformed leaves
        else:
            # Internal node - traverse children
            try:
                ptrs = parse_internal_node(block)
                for ptr in ptrs:
                    traverse(ptr.blockptr)
            except Exception:
                pass  # Skip malformed nodes

    traverse(root_addr)
    return results


def traverse_tree_all(f: BinaryIO, root_addr: int, chunk_map: ChunkMap,
                      nodesize: int) -> List[Tuple[BtrfsItem, bytes]]:
    """Traverse entire tree and return all items."""
    results = []
    visited = set()  # Prevent infinite loops

    def traverse(addr: int):
        if addr in visited:
            return
        visited.add(addr)

        try:
            block = read_tree_block(f, addr, chunk_map, nodesize)
        except ValueError:
            return  # Skip unmappable addresses

        header = BtrfsHeader.unpack(block)

        if header.level == 0:
            # Leaf node
            try:
                results.extend(parse_leaf_items(block))
            except Exception:
                pass  # Skip malformed leaves
        else:
            # Internal node
            try:
                for ptr in parse_internal_node(block):
                    traverse(ptr.blockptr)
            except Exception:
                pass  # Skip malformed nodes

    traverse(root_addr)
    return results
