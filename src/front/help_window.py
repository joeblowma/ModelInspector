"""Scrollable help window for frozen builds that have no console output."""

from PyQt6.QtWidgets import QDialog, QPlainTextEdit, QVBoxLayout


def show_help_window(text: str) -> None:
    """Show read-only help text in a resizable dialog, blocking until closed."""
    dialog = QDialog()
    dialog.setWindowTitle("Model Inspector Help")
    dialog.resize(760, 560)
    layout = QVBoxLayout(dialog)
    viewer = QPlainTextEdit()
    viewer.setReadOnly(True)
    viewer.setPlainText(text)
    layout.addWidget(viewer)
    dialog.exec()
