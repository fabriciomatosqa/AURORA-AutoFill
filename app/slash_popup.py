"""Non-activating slash-command panel, styled with AURORA's navy/teal palette.

The focused external editor keeps the keyboard. Global navigation is handled
by the Windows hook only when the popup acknowledges an exact typed prefix.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame,
                               QLabel, QListWidget, QListWidgetItem, QVBoxLayout)

from .themes import current_theme
from .windows_context import _GUIInfo, _api


def suggestion_anchor() -> QPoint:
    """Prefer a native caret position; fall back to the current pointer."""
    fallback = QCursor.pos() + QPoint(12, 20)
    if sys.platform != "win32":
        return fallback
    try:
        import ctypes
        from ctypes import wintypes
        info = _GUIInfo(cbSize=ctypes.sizeof(_GUIInfo))
        api = _api()
        if not api.GetGUIThreadInfo(0, ctypes.byref(info)) or not info.caret:
            return fallback
        point = wintypes.POINT(info.rect.left, info.rect.bottom)
        api.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        if not api.ClientToScreen(info.caret, ctypes.byref(point)):
            return fallback
        return QPoint(point.x + 2, point.y + 7)
    except (OSError, AttributeError, TypeError, ValueError):
        return fallback


class SlashCommandPopup(QFrame):
    """Six visible rows with scrollable results; selection never steals focus."""

    MAX_VISIBLE = 6

    def __init__(self):
        flags = Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags)
        self.setObjectName("auroraSlashPopup")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedWidth(410)
        self._prefix = ""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(5)
        self.heading = QLabel("✦  AURORA  ·  COMANDOS")
        self.heading.setObjectName("slashHeading")
        layout.addWidget(self.heading)

        self.results = QListWidget()
        self.results.setObjectName("slashResults")
        self.results.setAccessibleName("Comandos sugeridos pelo AURORA")
        self.results.setFocusPolicy(Qt.NoFocus)
        self.results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setSpacing(3)
        layout.addWidget(self.results)

        self.hint = QLabel("↑ ↓  navegar     Tab / Enter  inserir     Esc  fechar")
        self.hint.setObjectName("slashHint")
        layout.addWidget(self.hint)
        self._apply_theme()

    def _apply_theme(self):
        if current_theme() == "light":
            bg, fg, muted, stroke, hover, selected = (
                "#f4fbfd", "#142c41", "#537486", "#7eb4be", "#d5eef0", "#b7e7e2")
        else:
            bg, fg, muted, stroke, hover, selected = (
                "#10273b", "#f1fbff", "#9fbbcc", "#39828b", "#1c445a", "#246c74")
        self.setStyleSheet(f"""
            QFrame#auroraSlashPopup {{
                background: {bg}; color: {fg}; border: 1px solid {stroke};
                border-radius: 12px;
            }}
            QLabel#slashHeading {{
                color: {fg}; font-weight: 760; font-size: 11px;
                padding: 4px 7px 6px 7px; border: 0px;
            }}
            QLabel#slashHint {{
                color: {muted}; font-size: 11px; padding: 6px 5px 2px 5px;
                border: 0px;
            }}
            QListWidget#slashResults {{
                color: {fg}; background: transparent; border: none;
                outline: none; font-size: 12px;
            }}
            QListWidget#slashResults::item {{
                padding: 7px 9px; border: none; border-radius: 7px;
            }}
            QListWidget#slashResults::item:hover {{
                background: {hover};
            }}
            QListWidget#slashResults::item:selected {{
                background: {selected}; color: {fg}; font-weight: 650;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {stroke}; border-radius: 3px; min-height: 24px;
            }}
        """)

    def present(self, prefix: str, matches: list[tuple[str, str]],
                anchor: QPoint | None = None):
        if not prefix or not matches:
            self.dismiss()
            return
        self._apply_theme()
        selected = self.current_shortcut() if prefix == self._prefix else None
        self._prefix = prefix
        self.results.clear()
        for shortcut, title in matches:
            label = f"{shortcut}    ·    {title}"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, shortcut)
            item.setToolTip(title)
            item.setSizeHint(QSize(370, 36))
            self.results.addItem(item)
        rows = min(len(matches), self.MAX_VISIBLE)
        self.results.setFixedHeight(rows * 39 + 3)
        self.results.setCurrentRow(
            next((i for i, pair in enumerate(matches) if pair[0] == selected), 0))
        self.adjustSize()

        position = anchor or suggestion_anchor()
        screen = QApplication.screenAt(position) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            x = max(area.left(), min(position.x(), area.right() - self.width() + 1))
            y = position.y()
            if y + self.height() > area.bottom():
                y = max(area.top(), position.y() - self.height() - 26)
            position = QPoint(x, y)
        self.move(position)
        self.show()

    def current_shortcut(self) -> str | None:
        item = self.results.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def navigate(self, delta: int):
        if not self.results.count():
            return
        current = self.results.currentRow()
        self.results.setCurrentRow((current + delta) % self.results.count())

    def dismiss(self):
        self._prefix = ""
        self.results.clear()
        self.hide()
