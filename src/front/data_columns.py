"""Canonical Data-table column definitions.

One ordered source of truth for column labels, default (canonical) widths, and
which columns are locked.  ``window_layout`` builds the table from it,
``integration_controller._column_definitions`` seeds Settings from it, and the
Settings widget resolves missing or invalid widths back to it.  Columns that are
not ``hideable`` are always visible; columns that are not ``reorderable`` stay
pinned at the front.
"""

from __future__ import annotations

from front.settings_data_support import ColumnDefinition

DATA_COLUMNS: tuple[ColumnDefinition, ...] = (
    ColumnDefinition("selection", "", True, 32, 32, hideable=False, reorderable=False),
    ColumnDefinition("column_1", "File", True, 530),
    ColumnDefinition("column_2", "Format", True, 100),
    ColumnDefinition("column_3", "File Size", True, 80),
    ColumnDefinition("column_4", "Architecture", True, 100),
    ColumnDefinition("column_5", "Model Type", True, 90),
    ColumnDefinition("column_6", "Adapter", True, 70),
    ColumnDefinition("column_7", "Quantization", True, 100),
    ColumnDefinition("column_8", "Precision", True, 355),
    ColumnDefinition("column_9", "UNet Precision", True, 305),
    ColumnDefinition("column_10", "VAE Precision", True, 280),
    ColumnDefinition("column_11", "Text Encoder Precision", True, 280),
    ColumnDefinition("column_12", "Transformer Precision", True, 280),
    ColumnDefinition("column_13", "Parameters", True, 95),
    ColumnDefinition("column_14", "Tensors", True, 65),
    ColumnDefinition("column_15", "LoRA Rank", True, 100),
    ColumnDefinition("column_16", "MoE", True, 60),
    ColumnDefinition("column_17", "Experts", True, 65),
    ColumnDefinition("column_18", "Exp Act", True, 65),
    ColumnDefinition("column_19", "Software", True, 115),
    ColumnDefinition("column_20", "Images", True, 100),
    ColumnDefinition("column_21", "Resolution", True, 100),
    ColumnDefinition("column_22", "Epochs", True, 70),
    ColumnDefinition("column_23", "Steps", True, 70),
)

DATA_COLUMN_LABELS: tuple[str, ...] = tuple(column.label for column in DATA_COLUMNS)

DEFAULT_COLUMN_WIDTHS: dict[str, int] = {column.key: column.width for column in DATA_COLUMNS}

LOCKED_COLUMN_KEYS: frozenset[str] = frozenset(
    column.key for column in DATA_COLUMNS if not column.hideable or not column.reorderable
)


def column_key(index: int) -> str:
    """Stable key for a logical Data-table column index."""
    return "selection" if index == 0 else f"column_{index}"


def default_column_width(key: str, fallback: int = 100) -> int:
    """Canonical width for a column key, falling back for unknown keys."""
    return DEFAULT_COLUMN_WIDTHS.get(key, fallback)


__all__ = [
    "DATA_COLUMNS",
    "DATA_COLUMN_LABELS",
    "DEFAULT_COLUMN_WIDTHS",
    "LOCKED_COLUMN_KEYS",
    "column_key",
    "default_column_width",
]