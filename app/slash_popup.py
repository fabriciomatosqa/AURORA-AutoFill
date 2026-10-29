"""Non-activating slash-command panel in AURORA's navy/teal palette.

Rounded corners belong to an inner card on a translucent top-level window.
The popup stays outside the caret's entire text line and does not take focus.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFrame,
                               QLabel, QListWidget, QListWidgetItem, QVBoxLayout)

from .themes import current_theme
from .windows_context import _GUIInfo, _api


POPUP_GAP = 11
FRAME_MARGIN = 3
ASSETS = Path(__file__).resolve().parent.parent / "assets" / "icons"


def suggestion_anchor() -> QRect:
    """Caret's *line* in screen coordinates, not just an ambiguous point.

    Most Win32 text controls publish rcCaret via GetGUIThreadInfo. Browsers
    that do not publish one fall back to the mouse, padded to a line height.
    Neither path reads the text in the target application.
    """
    cursor = QCursor.pos()
    fallback = QRect(cursor.x(), cursor.y() - 12, 1, 27)
    if sys.platform != "win32":
        return fallback
    try:
        import ctypes
        from ctypes import wintypes
        info = _GUIInfo(cbSize=ctypes.sizeof(_GUIInfo))
        api = _api()
        if not api.GetGUIThreadInfo(0, ctypes.byref(info)) or not info.caret:
            return fallback
        first = wintypes.POINT(info.rect.left, info.rect.top)
        last = wintypes.POINT(info.rect.right, info.rect.bottom)
        api.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        if not (api.ClientToScreen(info.caret, ctypes.byref(first))
                and api.ClientToScreen(info.caret, ctypes.byref(last))):
            return fallback
        height = last.y - first.y
        if not 8 <= height <= 120:
            # An empty/invalid rcCaret must not place the popup on the text.
            return fallback
        if abs(first.x) > 100000 or abs(first.y) > 100000:
            return fallback
        return QRect(first.x, first.y, max(1, last.x-first.x), height)
    except (OSError, AttributeError, TypeError, ValueError):
        return fallback


def placement_for_caret(caret: QRect, screen: QRect, size: QSize,
                        gap: int = POPUP_GAP) -> tuple[QPoint, str, int]:
    """Screen-clamped position, side, and room without overlapping the line.

    Below has priority if the panel fits; otherwise prefer above if it fits.
    When neither fits, choose the roomier side so the list can shrink.
    """
    below_y = caret.bottom() + 1 + gap
    above_bottom = caret.top() - gap - 1
    room_below = max(0, screen.bottom() - below_y + 1)
    room_above = max(0, above_bottom - screen.top() + 1)
    if size.height() <= room_below:
        side, room = "below", room_below
    elif size.height() <= room_above:
        side, room = "above", room_above
    elif room_below >= room_above:
        side, room = "below", room_below
    else:
        side, room = "above", room_above
    x = max(screen.left(), min(caret.left(), screen.right() - size.width() + 1))
    y = below_y if side == "below" else above_bottom - size.height() + 1
    return QPoint(x, y), side, room


class SlashCommandPopup(QFrame):
    """Scrollable, non-activating command picker with genuinely rounded corners."""

    MAX_VISIBLE = 6
    ROW_HEIGHT = 39

    def __init__(self):
        flags = Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus
        super().__init__(None, flags)
        self.setObjectName("auroraSlashPopup")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedWidth(410)
        self._prefix = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(FRAME_MARGIN, FRAME_MARGIN,
                                 FRAME_MARGIN, FRAME_MARGIN)
        outer.setSpacing(0)
        self.card = QFrame(self)
        self.card.setObjectName("slashCard")
        self.card.setAutoFillBackground(False)
        outer.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(5)
        self.heading = QLabel("✦  AURORA  ·  COMANDOS")
        self.heading.setObjectName("slashHeading")
        layout.addWidget(self.heading)

        self.results = QListWidget(self.card)
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
        light = current_theme() == "light"
        if light:
            bg, fg, muted, stroke, hover, selected, track, thumb, arrow = (
                "#f4fbfd", "#142c41", "#537486", "#7eb4be", "#d5eef0",
                "#b7e7e2", "#e5f1f5", "#65b9bd", "#d9ecef")
        else:
            bg, fg, muted, stroke, hover, selected, track, thumb, arrow = (
                "#10273b", "#f1fbff", "#9fbbcc", "#39828b", "#1c445a",
                "#246c74", "#16364b", "#54a5a9", "#20495c")

        up = (ASSETS / ("scroll-up-light.svg" if light else "scroll-up-dark.svg")).as_posix()
        down = (ASSETS / ("scroll-down-light.svg" if light else "scroll-down-dark.svg")).as_posix()
        self.setStyleSheet(f"""
            QFrame#auroraSlashPopup {{
                background: transparent; border: none;
            }}
            QFrame#slashCard {{
                background-color: {bg}; color: {fg};
                border: 1px solid {stroke}; border-radius: 12px;
            }}
            QLabel#slashHeading {{
                color: {fg}; font-weight: 760; font-size: 11px;
                padding: 4px 7px 6px 7px; border: none; background: transparent;
            }}
            QLabel#slashHint {{
                color: {muted}; font-size: 11px; padding: 6px 5px 2px 5px;
                border: none; background: transparent;
            }}
            QListWidget#slashResults {{
                color: {fg}; background: transparent;
                border: none; outline: none; font-size: 12px;
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
            QListWidget#slashResults QScrollBar:vertical {{
                background: {track}; border: none; border-radius: 7px;
                width: 14px; margin: 0;
            }}
            QListWidget#slashResults QScrollBar::handle:vertical {{
                background: {thumb}; margin: 2px 3px;
                border-radius: 4px; min-height: 25px;
            }}
            QListWidget#slashResults QScrollBar::handle:vertical:hover {{
                background: {stroke};
            }}
            QListWidget#slashResults QScrollBar::sub-line:vertical,
            QListWidget#slashResults QScrollBar::add-line:vertical {{
                background: {arrow}; border: none; border-radius: 6px;
                height: 19px; subcontrol-origin: margin;
            }}
            QListWidget#slashResults QScrollBar::sub-line:vertical {{
                subcontrol-position: top;
            }}
            QListWidget#slashResults QScrollBar::add-line:vertical {{
                subcontrol-position: bottom;
            }}
            QListWidget#slashResults QScrollBar::up-arrow:vertical {{
                image: url("{up}"); width: 11px; height: 8px;
            }}
            QListWidget#slashResults QScrollBar::down-arrow:vertical {{
                image: url("{down}"); width: 11px; height: 8px;
            }}
            QListWidget#slashResults QScrollBar::add-page:vertical,
            QListWidget#slashResults QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

    def _resize_for_rows(self, rows: int):
        self.results.setFixedHeight(rows * self.ROW_HEIGHT + 3)
        self.adjustSize()
        self.resize(self.width(), self.sizeHint().height())

    def present(self, prefix: str, matches: list[tuple[str, str]],
                anchor: QPoint | QRect | None = None):
        if not prefix or not matches:
            self.dismiss()
            return
        self._apply_theme()
        selected = self.current_shortcut() if prefix == self._prefix else None
        self._prefix = prefix
        self.results.clear()
        for shortcut, title in matches:
            item = QListWidgetItem(f"{shortcut}    ·    {title}")
            item.setData(Qt.UserRole, shortcut)
            item.setToolTip(title)
            item.setSizeHint(QSize(370, 36))
            self.results.addItem(item)
        self.results.setCurrentRow(
            next((i for i, pair in enumerate(matches) if pair[0] == selected), 0))

        caret = anchor if isinstance(anchor, QRect) else (
            QRect(anchor.x(), anchor.y() - 12, 1, 27)
            if isinstance(anchor, QPoint) else suggestion_anchor())
        screen = QApplication.screenAt(caret.center()) or QApplication.primaryScreen()
        self._resize_for_rows(min(len(matches), self.MAX_VISIBLE))
        if screen is not None:
            area = screen.availableGeometry()
            for rows in range(min(len(matches), self.MAX_VISIBLE), 0, -1):
                self._resize_for_rows(rows)
                _position, _side, space = placement_for_caret(
                    caret, area, self.size())
                if self.height() <= space:
                    break
            point, side, _space = placement_for_caret(caret, area, self.size())
            # No screen is tall enough for a full card? Respect the caret
            # boundary instead of pushing the popup across the typed line.
            if side == "above":
                point.setY(max(area.top(), point.y()))
            self.move(point)
        else:
            self.move(caret.left(), caret.bottom() + POPUP_GAP + 1)
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
