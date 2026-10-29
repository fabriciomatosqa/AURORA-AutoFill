"""Componentes visuais reutilizáveis do cabeçalho, menus e lista AURORA.

Extraídos da janela principal sem mudar seu comportamento ou propriedades.
"""
from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QSize, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QLinearGradient,
    QPen, QPixmap, QPalette,
)
from PySide6.QtWidgets import QWidget, QLabel, QMenu, QComboBox, QToolButton, QListWidget
from .themes import set_ui_style, ui_color


class AuroraBanner(QWidget):
    """Desenha o panorama no topo sem deformar sua proporção original.

    Usa a região central do cenário para destacar aurora, picos e reflexos.
    O recorte se adapta ao tamanho da janela mantendo pixels proporcionais.
    """

    def __init__(self, picture: Path, parent=None):
        super().__init__(parent)
        self._night = QPixmap(str(picture))
        self._day = QPixmap(str(picture.with_name("aurora_banner_day.png")))
        self._image = self._night
        self._theme = "dark"
        self.setObjectName("topbar")

    def set_theme(self, theme):
        self._theme = theme
        self._image = self._day if theme == "light" else self._night
        self.update()

    def panorama_width(self):
        # Limit magnification on ultrawide displays; reflect the panorama at its
        # edge to preserve the landscape framing at the fixed header height.
        return min(self.width(), 1320)

    @staticmethod
    def source_crop(source_width: int, source_height: int, view_width: int, view_height: int):
        if not source_width or not source_height or not view_width or not view_height:
            return QRectF()
        src_ratio = source_width / source_height
        dst_ratio = view_width / view_height
        if src_ratio < dst_ratio:
            # Para cobrir uma janela longa, recorta o centro vertical da arte.
            crop_height = source_width / dst_ratio
            y = max(0, min(source_height - crop_height, source_height * 0.56 - crop_height * .5))
            return QRectF(0, y, source_width, crop_height)
        crop_width = source_height * dst_ratio
        return QRectF((source_width - crop_width) / 2, 0, crop_width, source_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if not self._image.isNull():
            width = self.panorama_width()
            rect = self.source_crop(self._image.width(), self._image.height(), width, self.height())
            painter.drawPixmap(QRectF(0, 0, width, self.height()), self._image, rect)
            # Reflect only the rightmost scenery, at the same scale as the
            # main panorama. Alternating strips meet without visible seams.
            edge = QRectF(rect.right() - rect.width() * .38, rect.y(), rect.width() * .38, rect.height())
            strip_width = width * .38
            offset = float(width)
            mirrored = True
            while offset < self.width():
                painter.save()
                painter.translate(offset + (strip_width if mirrored else 0), 0)
                if mirrored:
                    painter.scale(-1, 1)
                painter.drawPixmap(QRectF(0, 0, strip_width, self.height()), self._image, edge)
                painter.restore()
                offset += strip_width
                mirrored = not mirrored
        else:
            painter.fillRect(self.rect(), QColor("#06152b"))
        painter.end()


class AuroraWordmark(QWidget):
    """Assinatura tipográfica geométrica, com letras vetoriais, sem PNG borrado.

    Bahnschrift é uma família moderna presente no Windows 10/11; há fontes
    alternativas para Linux, mantendo os efeitos vetoriais da marca.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(470, 60)
        self.setMaximumHeight(60)
        self.setAttribute(Qt.WA_TranslucentBackground)

    def paintEvent(self, event):
        super().paintEvent(event)
        from PySide6.QtGui import QFontDatabase
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        # A borda pertence às letras; o panorama continua sem filtros.
        painter.translate(2, 0)
        outline = QPen(QColor("#071b31"), 3.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        installed = set(QFontDatabase.families())
        family = next((name for name in (
            "Bahnschrift", "Bahnschrift SemiCondensed", "Segoe UI Variable Display",
            "Montserrat", "DejaVu Sans") if name in installed), "Sans Serif")

        base = QFont(family)
        base.setPixelSize(35)
        base.setWeight(QFont.Bold)
        base.setLetterSpacing(QFont.AbsoluteSpacing, 4.1)
        base.setKerning(True)
        baseline = 40
        brand = QPainterPath()
        brand.addText(0, baseline, base, "AURORA")
        painter.strokePath(brand, outline)
        white = QLinearGradient(0, 5, 0, 43)
        white.setColorAt(0, QColor("#ffffff"))
        white.setColorAt(1, QColor("#d7e8ff"))
        painter.fillPath(brand, white)

        spacing = QFontMetricsF(base).horizontalAdvance("AURORA") + 18
        accent = QFont(family)
        accent.setPixelSize(31)
        accent.setWeight(QFont.DemiBold)
        accent.setLetterSpacing(QFont.AbsoluteSpacing, 1.35)
        accent_path = QPainterPath()
        accent_path.addText(spacing, baseline, accent, "AutoFill")
        color = QLinearGradient(spacing, 0, spacing + 155, 0)
        color.setColorAt(0, QColor("#8bfbeb"))
        color.setColorAt(.55, QColor("#55e0e0"))
        color.setColorAt(1, QColor("#99acff"))
        painter.strokePath(accent_path, outline)
        painter.fillPath(accent_path, color)

        # Traço de marca, inspirado na linha de luz da aurora.
        bar = QLinearGradient(0, 0, 410, 0)
        bar.setColorAt(0, QColor("#39cfcb"))
        bar.setColorAt(.50, QColor("#80edd4"))
        bar.setColorAt(1, QColor(102, 160, 255, 0))
        painter.fillRect(QRectF(1, 49, min(self.width() - 8, 398), 2), bar)
        painter.end()


class AuroraBannerCaption(QLabel):
    """Legenda com contorno nas letras, sem fundo sobre a paisagem."""

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setContentsMargins(2, 2, 3, 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        metrics = QFontMetricsF(self.font())
        bounds = QRectF(self.contentsRect())
        baseline = bounds.center().y() + (metrics.ascent() - metrics.descent()) / 2
        path = QPainterPath()
        path.addText(bounds.left(), baseline, self.font(), self.text())
        painter.strokePath(path, QPen(QColor("#071b31"), 2.4,
                                     Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.fillPath(path, self.palette().color(QPalette.WindowText))
        painter.end()


class AuroraMenu(QMenu):
    """Rounded popup with an explicitly transparent window outside its corners."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        set_ui_style(self, """
            QMenu { background: #112f41; color: #ebfaff; border: 1px solid #2f8590;
                border-radius: 10px; padding: 6px; font-size: 13px; }
            QMenu::item { background: transparent; color: #e5f7ff;
                padding: 10px 16px; margin: 2px 3px; border-radius: 7px; }
            QMenu::item:selected { background: #287281; color: white; }
            QMenu::item:checked { color: #7df0d9; }
            QMenu::separator { background: #355168; height: 1px; margin: 4px 8px; }
        """)


class AuroraFolderCombo(QComboBox):
    """Exibe as pastas usando menu Qt próprio, evitando bordas nativas acinzentadas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._folder_menu = None

    def showPopup(self):
        menu = AuroraMenu(self)
        menu.setObjectName("folderSelectionMenu")
        menu.setMinimumWidth(max(self.width(), 210))
        set_ui_style(menu, menu._aurora_dark_style + "QMenu::indicator { width: 0px; height: 0px; }")
        for i in range(self.count()):
            action = menu.addAction(self.itemText(i))
            action.setCheckable(True)
            action.setChecked(i == self.currentIndex())
            action.triggered.connect(lambda checked=False, index=i: self.setCurrentIndex(index))
        menu.aboutToHide.connect(menu.deleteLater)
        self._folder_menu = menu
        pos = self.mapToGlobal(QPoint(0, self.height() + 3))
        screen = self.screen()
        if screen is not None:
            available = screen.availableGeometry()
            menu_height = menu.sizeHint().height()
            if pos.y() + menu_height > available.bottom():
                pos.setY(max(available.top(), self.mapToGlobal(QPoint(0, 0)).y() - menu_height - 3))
        menu.popup(pos)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(ui_color("#8ef7de"), 2.0, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x = self.width() - 16
        y = self.height() // 2 - 1
        painter.drawLine(x - 5, y - 2, x, y + 3)
        painter.drawLine(x, y + 3, x + 5, y - 2)
        painter.end()


class AuroraMenuButton(QToolButton):
    """Menu trigger with the same rounded surface and arrow lane as folders."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tokenPicker")
        self.setMinimumHeight(40)
        set_ui_style(self, "QToolButton#tokenPicker { font-weight: 400; }")
        self.setPopupMode(QToolButton.InstantPopup)

    def sizeHint(self):
        size = super().sizeHint()
        width = self.fontMetrics().horizontalAdvance(self.text()) + 76
        return size.expandedTo(QSize(width, 40))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        bounds = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = QPainterPath()
        path.addRoundedRect(bounds, 10, 10)
        active = self.underMouse() or self.isDown() or bool(self.menu() and self.menu().isVisible())
        painter.fillPath(path, ui_color("#184156" if active else "#143345"))
        painter.save()
        painter.setClipPath(path)
        arrow_left = self.width() - 29
        painter.fillRect(QRectF(arrow_left, 0, 29, self.height()), ui_color("#1b495c"))
        painter.setPen(ui_color("#28586d"))
        painter.drawLine(arrow_left, 0, arrow_left, self.height())
        painter.restore()
        border = "#67e7d5" if self.hasFocus() else "#59dfcf" if active else "#2f7077"
        painter.setPen(QPen(ui_color(border), 1))
        painter.drawPath(path)
        center_y = self.height() // 2
        self.icon().paint(painter, QRect(12, center_y - 9, 18, 18))
        text_rect = QRect(36, 0, max(0, arrow_left - 44), self.height())
        painter.setPen(ui_color("#f0feff" if self.isEnabled() else "#7995ab"))
        painter.setFont(self.font())
        label = self.fontMetrics().elidedText(self.text(), Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)
        painter.setPen(QPen(ui_color("#8ef7de"), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x = self.width() - 15
        painter.drawLine(x - 5, center_y - 3, x, center_y + 2)
        painter.drawLine(x, center_y + 2, x + 5, center_y - 3)
        painter.end()


class ReorderableSnippetList(QListWidget):
    """Permite arrastar e soltar comandos e avisa quando a ordem foi alterada."""
    reordered = Signal()

    def dropEvent(self, event):
        if event.source() is not self:
            event.ignore()
            return
        super().dropEvent(event)
        if event.isAccepted():
            self.reordered.emit()


