"""Model-cache directory selection history and precedence resolution.

The application has two cache locations:

* the cache root (``app_paths.cache_dir``), resolved from ``SMI_CACHE_DIR``
  or the default location, holding the primary inspection cache plus
  ancillary caches (sidecars, raw dumps, directory scans); and
* the model cache (``app_paths.model_cache_dir``), resolved from
  ``SMI_MODEL_CACHE_DIR`` or falling back to the cache root, holding only the
  primary inspection-cache index/entries/data.

``--cachedir`` relocates the cache root transiently for one run; ``--cache``
relocates only the model cache and records the selection in a settings history
array so the most recently used directory becomes the next-launch default.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

HISTORY_KEY = "cache_dir_history"
MAX_HISTORY = 10


def _norm(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))


def read_cache_dir_history(store: Any) -> list[str]:
    """Return the persisted selection history in most-recent-first order."""
    raw = store.value(HISTORY_KEY, [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw if isinstance(item, str) and str(item).strip()]


def existing_cache_dir_history(store: Any) -> list[str]:
    """Prior history directories that still exist, deduplicated, order preserved."""
    seen: set[str] = set()
    result: list[str] = []
    for raw in read_cache_dir_history(store):
        key = _norm(raw)
        if key in seen:
            continue
        seen.add(key)
        try:
            if Path(raw).is_dir():
                result.append(raw)
        except OSError:
            continue
    return result


def last_used_cache_dir(store: Any) -> str | None:
    """The most recently used history directory that still exists, if any."""
    history = existing_cache_dir_history(store)
    return history[0] if history else None


def record_cache_dir(store: Any, path: str | Path) -> None:
    """Prepend ``path`` to the selection history, dedupe, cap, and persist."""
    value = str(path)
    history = [value] + [
        item for item in read_cache_dir_history(store) if _norm(item) != _norm(value)
    ]
    store.setValue(HISTORY_KEY, history[:MAX_HISTORY])


def redirect_model_cache(store: Any, path: str | Path) -> None:
    """Point the live model cache at ``path`` and record it in history.

    Only the model cache location changes (``SMI_MODEL_CACHE_DIR``): no
    existing cache files are moved or deleted, and settings/themes/assets and
    the ancillary caches (sidecars, raw dumps, directory scans) stay put.
    """
    os.environ["SMI_MODEL_CACHE_DIR"] = str(path)
    record_cache_dir(store, path)


def apply_cache_location(
    cache: str | Path | None,
    cachedir: str | Path | None,
    store: Any,
) -> None:
    """Resolve the effective cache directories with deterministic precedence.

    Precedence (highest first):

    1. explicit ``--cache`` (sets ``SMI_MODEL_CACHE_DIR``; also recorded)
    2. explicit ``--cachedir`` (sets ``SMI_CACHE_DIR``; transient)
    3. a pre-existing ``SMI_CACHE_DIR`` environment value
    4. persisted most-recently-used existing history directory
       (sets ``SMI_MODEL_CACHE_DIR``)
    5. the default ``app_data_dir()/cache`` (left to ``app_paths.cache_dir``)
    """
    if cache is not None:
        redirect_model_cache(store, cache)
        return
    if cachedir is not None:
        os.environ["SMI_CACHE_DIR"] = str(cachedir)
        return
    if os.environ.get("SMI_CACHE_DIR"):
        return
    selected = last_used_cache_dir(store)
    if selected:
        os.environ["SMI_MODEL_CACHE_DIR"] = selected


__all__ = [
    "HISTORY_KEY",
    "MAX_HISTORY",
    "apply_cache_location",
    "existing_cache_dir_history",
    "last_used_cache_dir",
    "read_cache_dir_history",
    "record_cache_dir",
    "redirect_model_cache",
]
