"""
BTRFS Statistics Module - Calculate and export file statistics.
"""
from collections import defaultdict
from typing import List, Dict, Any
import json
import os
import sys
from filesystem import FileEntry


def get_file_extension(entry: FileEntry) -> str:
    """Extract normalized file extension from FileEntry.

    Args:
        entry: FileEntry object to extract extension from

    Returns:
        - Lowercase extension including dot (e.g., '.txt', '.py')
        - '(directory)' for directories
        - '(no extension)' for files without extensions
    """
    if entry.type == 'directory':
        return '(directory)'

    if not entry.name:
        return '(no extension)'

    # Use os.path.splitext for reliable extension extraction
    _, ext = os.path.splitext(entry.name)

    if ext:
        return ext.lower()
    else:
        return '(no extension)'


def calculate_statistics(entries: List[FileEntry]) -> Dict[str, Any]:
    """Calculate file statistics by extension, type, and ownership.

    Args:
        entries: List of FileEntry objects to analyze

    Returns:
        Dictionary containing:
        - summary: Overall statistics
        - by_extension: Statistics grouped by file extension
        - by_type: Statistics grouped by BTRFS type
        - by_ownership: Statistics grouped by uid, with nested gid breakdown
    """
    # Initialize structures with defaultdict for cleaner code
    by_extension = defaultdict(lambda: {"count": 0, "total_size_bytes": 0})
    by_type = defaultdict(lambda: {"count": 0, "total_size_bytes": 0})
    by_uid = defaultdict(lambda: {
        "uid": None,
        "count": 0,
        "total_size_bytes": 0,
        "by_gid": defaultdict(lambda: {"gid": None, "count": 0, "total_size_bytes": 0})
    })

    # Single pass aggregation - O(n) complexity
    for entry in entries:
        ext = get_file_extension(entry)
        size = entry.size

        # By extension
        by_extension[ext]["count"] += 1
        by_extension[ext]["total_size_bytes"] += size

        # By type
        by_type[entry.type]["count"] += 1
        by_type[entry.type]["total_size_bytes"] += size

        # By ownership (uid -> gid hierarchy)
        uid_key = f"uid_{entry.uid}"
        by_uid[uid_key]["uid"] = entry.uid
        by_uid[uid_key]["count"] += 1
        by_uid[uid_key]["total_size_bytes"] += size

        gid_key = f"gid_{entry.gid}"
        by_uid[uid_key]["by_gid"][gid_key]["gid"] = entry.gid
        by_uid[uid_key]["by_gid"][gid_key]["count"] += 1
        by_uid[uid_key]["by_gid"][gid_key]["total_size_bytes"] += size

    # Calculate summary metrics
    summary = {
        "total_files": sum(1 for e in entries if e.type != 'directory'),
        "total_size_bytes": sum(e.size for e in entries),
        "total_directories": sum(1 for e in entries if e.type == 'directory'),
        "total_symlinks": sum(1 for e in entries if e.type == 'symlink'),
        "unique_extensions": len(by_extension),
        "unique_owners": len(by_uid)
    }

    # Convert defaultdicts to regular dicts for JSON serialization
    return {
        "summary": summary,
        "by_extension": dict(by_extension),
        "by_type": dict(by_type),
        "by_ownership": {
            k: {
                **v,
                "by_gid": dict(v["by_gid"])
            }
            for k, v in by_uid.items()
        }
    }


def write_statistics_json(stats: dict, output_path: str) -> None:
    """Write statistics to JSON file with error handling.

    Args:
        stats: Dictionary containing calculated statistics
        output_path: Path where JSON file should be written

    Note:
        Errors are non-fatal - prints warning and continues
    """
    try:
        with open(output_path, 'w') as f:
            json.dump(stats, f, indent=2)
    except IOError as e:
        # Non-fatal error - print warning but continue
        print(f"Warning: Could not write statistics to {output_path}: {e}",
              file=sys.stderr)
