"""Vector icons with explicit colors on every platform and display scale."""
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_NAMES = ('settings', 'home', 'save', 'trash', 'plus', 'minus', 'export', 'import', 'undo', 'folder', 'play', 'pause', 'volume', 'update', 'backup', 'restore', 'back', 'check', 'close', 'bolt', 'bold', 'italic', 'underline', 'image',)
ROOT = Path(__file__).resolve().parents[1] / 'assets/icons'


class VectorIconEngine(QIconEngine):
    def __init__(self, data):
        super().__init__()
        self.data = data

    def clone(self):
        return VectorIconEngine(self.data)

    def paint(self, painter, rect, mode, state):
        painter.save()
        if mode == QIcon.Disabled:
            painter.setOpacity(0.4)
        QSvgRenderer(QByteArray(self.data)).render(painter, QRectF(rect))
        painter.restore()

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        self.paint(painter, pixmap.rect(), mode, state)
        painter.end()
        return pixmap


@lru_cache(maxsize=96)
def icon(name, color='#d7f5ff'):
    if name not in ICON_NAMES:
        raise ValueError('Unknown icon: ' + name)
    data = (ROOT / (name + '.svg')).read_bytes().replace(b'#d7f5ff', color.encode('ascii'))
    return QIcon(VectorIconEngine(data))


def apply_icon(widget, name, *, color='#d7f5ff', label=None):
    widget.setIcon(icon(name, color))
    if hasattr(widget, 'setIconSize'):
        widget.setIconSize(QSize(18, 18))
    if label:
        widget.setAccessibleName(label)
    return widget
