"""
BTRFS Output Formatters - JSON, CSV, and console output.
"""
import json
import csv
from typing import List
from io import StringIO
from dataclasses import asdict

from filesystem import FileEntry


def to_json(entries: List[FileEntry], indent: int = 2) -> str:
    """Convert file entries to JSON string."""
    return json.dumps([asdict(e) for e in entries], indent=indent)


def to_csv(entries: List[FileEntry]) -> str:
    """Convert file entries to CSV string."""
    output = StringIO()
    fieldnames = ['path', 'name', 'type', 'size', 'mode_str',
                  'uid', 'gid', 'nlink',
                  'atime', 'mtime', 'ctime', 'otime',
                  'inode', 'subvolume_id',
                  'generation', 'transid', 'flags', 'flags_str',
                  'extent_count', 'disk_bytes', 'physical_offset',
                  'xattr_count', 'checksum_count',
                  'md5', 'sha256']

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for entry in entries:
        row = {
            'path': entry.path,
            'name': entry.name,
            'type': entry.type,
            'size': entry.size,
            'mode_str': entry.mode_str,
            'uid': entry.uid,
            'gid': entry.gid,
            'nlink': entry.nlink,
            'atime': entry.atime,
            'mtime': entry.mtime,
            'ctime': entry.ctime,
            'otime': entry.otime,
            'inode': entry.inode,
            'subvolume_id': entry.subvolume_id,
            'generation': entry.generation,
            'transid': entry.transid,
            'flags': entry.flags,
            'flags_str': entry.flags_str,
            'extent_count': entry.extent_count,
            'disk_bytes': entry.disk_bytes,
            'physical_offset': entry.physical_offset,
            'xattr_count': entry.xattr_count,
            'checksum_count': entry.checksum_count,
            'md5': entry.md5,
            'sha256': entry.sha256,
        }
        writer.writerow(row)

    return output.getvalue()


def to_console(entries: List[FileEntry]) -> str:
    """Format file entries for console display."""
    lines = []
    lines.append(f"{'Mode':<12} {'UID':>5} {'GID':>5} {'Size':>12} {'Modified':<20} Path")
    lines.append('-' * 80)

    for entry in entries:
        mtime_short = entry.mtime[:19] if entry.mtime else ''
        if entry.type == 'directory':
            size_str = '<DIR>'
        else:
            size_str = f"{entry.size:,}"

        lines.append(
            f"{entry.mode_str:<12} {entry.uid:>5} {entry.gid:>5} "
            f"{size_str:>12} {mtime_short:<20} {entry.path}"
        )

    return '\n'.join(lines)


def to_tree(entries: List[FileEntry]) -> str:
    """Format file entries as a tree structure."""
    # Build tree structure
    tree = {}
    for entry in entries:
        parts = entry.path.strip('/').split('/')
        current = tree
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        if parts:
            current[parts[-1]] = entry

    lines = []

    def print_tree(node, prefix='', is_last=True):
        if isinstance(node, FileEntry):
            return

        items = list(node.items())
        for i, (name, value) in enumerate(items):
            is_last_item = (i == len(items) - 1)
            connector = '└── ' if is_last_item else '├── '

            if isinstance(value, FileEntry):
                type_indicator = 'd' if value.type == 'directory' else '-'
                lines.append(f"{prefix}{connector}[{type_indicator}] {name}")
            else:
                lines.append(f"{prefix}{connector}[d] {name}/")
                new_prefix = prefix + ('    ' if is_last_item else '│   ')
                print_tree(value, new_prefix, is_last_item)

    lines.append('/')
    print_tree(tree)
    return '\n'.join(lines)
