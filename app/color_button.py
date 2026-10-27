"""Botões de cor compactos com indicador visual sincronizado ao último tom escolhido."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QPushButton


class AuroraColorButton(QPushButton):
    """Desenha ícone, seta e amostra inferior com a cor efetivamente aplicada."""

    def __init__(self, glyph: str, initial_color: QColor | str, parent=None):
        super().__init__(parent)
        self._glyph = glyph
        self._marker_color = QColor(initial_color)
        if not self._marker_color.isValid():
            self._marker_color = QColor("#ffffff")
        self.setObjectName("fontTool")
        self.setFixedSize(37, 26)
        self.setText("")
        self.setCursor(Qt.PointingHandCursor)

    def marker_color(self) -> QColor:
        return QColor(self._marker_color)

    def set_marker_color(self, color: QColor | str) -> None:
        chosen = QColor(color)
        if not chosen.isValid():
            return
        self._marker_color = chosen
        self.update()

    def marker_rect(self) -> QRect:
        # A amostra fica exatamente sob o glifo, nunca sob a seta.
        return QRect(6, self.height() - 7, max(20, self.width() - 17), 3)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        foreground = self.palette().buttonText().color()
        painter.setPen(foreground)
        font = QFont(self.font())
        font.setPointSize(11)
        font.setBold(self._glyph == "A")
        painter.setFont(font)
        painter.drawText(QRect(3, 1, self.width() - 12, self.height() - 8),
                         Qt.AlignHCenter | Qt.AlignVCenter, self._glyph)

        marker = self.marker_rect()
        # A borda fina mantém a amostra visível até com tons muito escuros.
        painter.fillRect(marker.adjusted(-1, -1, 1, 1), QColor("#89adba"))
        painter.fillRect(marker, self._marker_color)
        painter.setPen(QPen(foreground, 1.2))
        x = self.width() - 7
        y = self.height() // 2
        painter.drawLine(QPoint(x - 3, y - 1), QPoint(x, y + 2))
        painter.drawLine(QPoint(x, y + 2), QPoint(x + 3, y - 1))
        painter.end()
