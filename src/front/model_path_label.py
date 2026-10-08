"""Elided model-path label with clipboard actions."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QContextMenuEvent, QFontMetrics, QResizeEvent
from PyQt6.QtWidgets import QApplication, QLabel, QMenu


_ELISION_MARKER = "<...>"


class ModelPathLabel(QLabel):
    """Single-line model path display with exact-value clipboard actions."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._full_path = ""
        self.setWordWrap(False)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    @property
    def full_path(self) -> str:
        return self._full_path

    def set_path(self, path: str) -> None:
        self._full_path = str(path)
        self.setToolTip(self._full_path)
        self._refresh_text()

    def copy_file_path(self) -> str:
        self._copy(self._full_path)
        return self._full_path

    def copy_folder_path(self) -> str:
        folder = str(Path(self._full_path).parent)
        self._copy(folder)
        return folder

    def context_menu_event(self, ev: QContextMenuEvent | None) -> None:
        if ev is None:
            return
        menu = QMenu(self)
        copy_file = menu.addAction("Copy file path")
        copy_folder = menu.addAction("Copy folder path")
        chosen = menu.exec(ev.globalPos())
        if chosen is copy_file:
            self.copy_file_path()
        elif chosen is copy_folder:
            self.copy_folder_path()
        ev.accept()

    contextMenuEvent = context_menu_event

    def resize_event(self, a0: QResizeEvent | None) -> None:
        super().resizeEvent(a0)
        self._refresh_text()

    resizeEvent = resize_event

    def _refresh_text(self) -> None:
        width = self.contentsRect().width()
        if width <= 0:
            self.setText(self._full_path)
            return
        self.setText(self._elided_path(self._full_path, QFontMetrics(self.font()), width))

    @staticmethod
    def _elided_path(path: str, metrics: QFontMetrics, width: int) -> str:
        if metrics.horizontalAdvance(path) <= width:
            return path
        marker_width = metrics.horizontalAdvance(_ELISION_MARKER)
        if width <= marker_width:
            return metrics.elidedText(_ELISION_MARKER, Qt.TextElideMode.ElideRight, width)

        separator = max(path.rfind("/"), path.rfind("\\"))
        suffix_start = separator if separator >= 0 else max(0, len(path) - 1)
        prefix_floor = 0
        if len(path) >= 3 and path[1] == ":" and path[2] in "/\\":
            prefix_floor = 3
        elif path.startswith(("/", "\\")):
            prefix_floor = 1

        for kept_suffix in range(len(path) - suffix_start, 0, -1):
            suffix = path[-kept_suffix:]
            prefix_limit = len(path) - kept_suffix
            low = min(prefix_floor, prefix_limit)
            high = prefix_limit
            best_prefix = -1
            while low <= high:
                prefix_size = (low + high) // 2
                candidate = path[:prefix_size] + _ELISION_MARKER + suffix
                if metrics.horizontalAdvance(candidate) <= width:
                    best_prefix = prefix_size
                    low = prefix_size + 1
                else:
                    high = prefix_size - 1
            if best_prefix >= 0:
                return path[:best_prefix] + _ELISION_MARKER + suffix

        return metrics.elidedText(_ELISION_MARKER, Qt.TextElideMode.ElideRight, width)

    @staticmethod
    def _copy(value: str) -> None:
        application = QApplication.instance()
        if isinstance(application, QApplication):
            clipboard = application.clipboard()
            if clipboard is not None:
                clipboard.setText(value)
