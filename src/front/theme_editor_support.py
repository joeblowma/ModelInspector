"""Small presentation helpers shared by the live theme editor controls."""

from __future__ import annotations

from PyQt6.QtGui import QColor

from back.theme_loader import Theme


REQUIRED_COLOR_ORDER = (
    "background",
    "surface",
    "surface_alt",
    "text",
    "muted",
    "accent",
    "accent_text",
    "border",
    "success",
    "warning",
    "error",
    "highlight",
    "highlight_selected",
    "stat_label",
    "accent_adapter",
    "accent_moe",
    "accent_component",
    "accent_display",
    "tab_inactive_hover",
)

COLOR_LABELS = {
    "background": "Window Background",
    "surface": "Primary Surface",
    "surface_alt": "Alternate Surface",
    "text": "Main Text",
    "muted": "Status Text",
    "accent": "Accent (Buttons, Badges, Inactive Tabs, Headers)",
    "accent_text": "Text on Accent Controls",
    "border": "Borders",
    "success": "Success Status",
    "warning": "Warning Status",
    "error": "Error Status",
    "highlight": "Highlight Text",
    "highlight_selected": "Selected Highlight Text",
    "stat_label": "Statistic Label Text",
    "accent_adapter": "Adapter Accent",
    "accent_moe": "MoE Accent",
    "accent_component": "Component Accent",
    "accent_display": "Display Accent",
    "tab_inactive_hover": "Inactive Tab Hover Background",
}


def color_label(key: str) -> str:
    """Return a reader-friendly label while retaining a useful unknown fallback."""
    return COLOR_LABELS.get(key, key.replace("_", " ").title())


def qcolor_from_hex(value: str, full_color_re) -> QColor | None:
    """Convert a validated hex color to ``QColor`` without accepting partial input."""
    value = value.strip()
    if full_color_re.fullmatch(value) is None:
        return None
    red, green, blue = (int(value[index:index + 2], 16) for index in (1, 3, 5))
    alpha = int(value[7:9], 16) if len(value) == 9 else 255
    return QColor(red, green, blue, alpha)


def update_color_button(button, key: str, value: str, full_color_re) -> None:
    """Apply the swatch value and accessible tooltip when it is fully valid."""
    color = qcolor_from_hex(value, full_color_re)
    if button is None or color is None:
        return
    normalized = value.strip().upper()
    button.setProperty("colorValue", normalized)
    button.setStyleSheet(
        f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
    )
    button.setToolTip(f"Choose {color_label(key)} color with QColorDialog (current {normalized}).")


def new_theme_from_default(theme_id: str, default_theme: Theme) -> Theme:
    """Return the named writable copy of the resource-backed default palette."""
    number = theme_id.removeprefix("new_theme_")
    return Theme(
        theme_id,
        f"New Theme {number}",
        dict(default_theme.colors),
        "A writable copy of the bundled default theme.",
        "user",
        dict(default_theme.variables),
    )
