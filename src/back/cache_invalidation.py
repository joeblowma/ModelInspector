"""Small cache-artifact removals shared by targeted invalidation."""

import json
import os
from collections.abc import Callable
from pathlib import Path

from app_paths import cache_dir


def invalidate_raw_dump(
    filepath: str, version: int, path_match_values: Callable[[str], set[str]]
) -> bool:
    """Remove a raw dump for a model, even when no inspection cache exists."""
    path = cache_dir() / "raw_dumps.json"
    try:
        index = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        entries = index.get("entries") if index.get("version") == version else []
        if not isinstance(entries, list):
            entries = []
        wanted = path_match_values(filepath)
        kept = [
            entry
            for entry in entries
            if not isinstance(entry, dict)
            or not wanted
            & {
                str(entry.get("filepath") or "").lower(),
                str(entry.get("resolved_filepath") or "").lower(),
            }
        ]
        if len(kept) == len(entries):
            return False
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps({"version": version, "entries": kept}, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        return True
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
