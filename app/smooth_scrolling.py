"""Smooth mouse-wheel scrolling across the AURORA desktop interface.

A single application-level event filter handles wheel events for Qt scroll
areas, rich-text editors, lists, previews and auxiliary dialogs. Standard
mouse wheels are animated; precision touchpad pixel deltas stay native.

This never changes cursor selection, keyboard commands or scrollbar dragging.
"""
from __future__ import annotations

from PySide6.QtCore import (QAbstractAnimation, QEasingCurve, QEvent, QObject,
                            QPropertyAnimation, Qt)
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QAbstractItemView, QAbstractScrollArea,
                               QAbstractSlider, QApplication, QComboBox,
                               QScrollBar, QWidget)


class SmoothWheelScroller(QObject):
    """Short, accumulated ease-out transitions for traditional wheel steps."""

    PIXELS_PER_LINE = 27
    DURATION_MS = 170

    def __init__(self, parent=None):
        super().__init__(parent)
        self._animations: dict[QScrollBar, QPropertyAnimation] = {}
        self._targets: dict[QScrollBar, int] = {}

    def _stop_animation(self, bar: QScrollBar) -> None:
        animation = self._animations.get(bar)
        if animation is not None:
            animation.stop()
        self._targets.pop(bar, None)

    def _ensure_animation(self, bar: QScrollBar) -> QPropertyAnimation:
        animation = self._animations.get(bar)
        if animation is None:
            animation = QPropertyAnimation(bar, b"value", bar)
            animation.setDuration(self.DURATION_MS)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            self._animations[bar] = animation
            # A manually dragged thumb must obey the mouse immediately.
            bar.sliderPressed.connect(lambda b=bar: self._stop_animation(b))
            bar.destroyed.connect(lambda _=None, b=bar: self._remove_animation(b))
        return animation

    def _remove_animation(self, bar: QScrollBar) -> None:
        self._animations.pop(bar, None)
        self._targets.pop(bar, None)

    @staticmethod
    def _scroll_ancestors(receiver: QWidget):
        """Nearest scroll area first, permitting an outer page at inner limits."""
        widget = receiver
        while widget is not None:
            if isinstance(widget, QAbstractScrollArea):
                yield widget
            widget = widget.parentWidget()

    def _animate(self, bar: QScrollBar, delta: int) -> bool:
        minimum, maximum = bar.minimum(), bar.maximum()
        if maximum <= minimum:
            return False
        current = bar.value()
        animation = self._ensure_animation(bar)
        if animation.state() == QAbstractAnimation.Running:
            origin = self._targets.get(bar, current)
        else:
            origin = current
        target = max(minimum, min(maximum, origin - delta))
        if target == current and animation.state() != QAbstractAnimation.Running:
            return False
        if target == origin:
            # While an animation is still reaching the endpoint, swallow
            # repeated ticks so the inner area doesn't jump or prematurely
            # forward them to its enclosing scroll area.
            return animation.state() == QAbstractAnimation.Running
        self._targets[bar] = target
        animation.stop()
        animation.setStartValue(current)
        animation.setEndValue(target)
        animation.start()
        return True

    def eventFilter(self, receiver, event):
        if event.type() != QEvent.Wheel or not isinstance(event, QWheelEvent):
            return False
        if not isinstance(receiver, QWidget):
            return False

        # Native precision touchpads already supply pixel-by-pixel movement,
        # so adding a second animation would make their gestures feel sluggish.
        if not event.pixelDelta().isNull():
            return False
        # Preserve Ctrl+wheel zoom in QTextEdit and other native modifiers.
        if event.modifiers() != Qt.NoModifier:
            return False
        # Let the Qt scrollbar track/thumb keep its ordinary direct behavior.
        if isinstance(receiver, (QAbstractSlider, QComboBox)):
            return False
        angle = event.angleDelta()
        if angle.isNull():
            return False
        # Prefer vertical scrolling, horizontal only for horizontal wheels.
        vertical = angle.y() != 0
        degrees = angle.y() if vertical else angle.x()
        app = QApplication.instance()
        lines = max(1, min(5, app.wheelScrollLines() if app else 3))
        pixels = round(degrees * self.PIXELS_PER_LINE * lines / 120)
        if pixels == 0:
            return False

        for area in self._scroll_ancestors(receiver):
            # QListWidget/QTreeView default to per-item jumps. Pixel mode is
            # necessary even when the viewport is smaller than one row.
            if isinstance(area, QAbstractItemView):
                if vertical and area.verticalScrollMode() != QAbstractItemView.ScrollPerPixel:
                    area.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
                elif not vertical and area.horizontalScrollMode() != QAbstractItemView.ScrollPerPixel:
                    area.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            bar = (area.verticalScrollBar() if vertical
                   else area.horizontalScrollBar())
            if self._animate(bar, pixels):
                event.accept()
                return True
        return False


def install_smooth_scrolling(app: QApplication) -> SmoothWheelScroller:
    """Install once; covers existing and future dialogs/popups in this process."""
    controller = getattr(app, "_aurora_smooth_scrolling", None)
    if controller is None:
        controller = SmoothWheelScroller(app)
        app.installEventFilter(controller)
        app._aurora_smooth_scrolling = controller
    return controller
