"""Ribbon controls with predictable icon geometry on Windows and Linux."""
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from .icons import apply_icon, icon
from .themes import ui_color


class RibbonToolButton(QToolButton):
    """Keep the artwork centered; the menu arrow has its own hit area."""
    def __init__(self, parent=None, *, menu=False, launcher=False):
        super().__init__(parent)
        self._split_menu = menu
        self._launcher = launcher
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover)
        if menu:
            self.setProperty('paragraphMenu', True)
            self.setPopupMode(QToolButton.MenuButtonPopup)

    def icon_rect(self):
        size = self.iconSize().boundedTo(self.size()-QSize(8,6))
        return QRect((self.width()-size.width())//2, (self.height()-size.height())//2,
                     size.width(), size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(.4)
        active = self.isChecked() or self.isDown()
        hover = self.underMouse()
        background = '#2c6870' if active else '#28546a' if hover else '#19364b'
        border = '#79ead8' if active or hover else '#365a71'
        if not self._launcher or hover or active:
            painter.setPen(QPen(ui_color(border),1))
            painter.setBrush(ui_color(background))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),4,4)
        if self._split_menu:
            x = self.width()-13.5
            painter.setPen(QPen(ui_color('#365a71'),1))
            painter.drawLine(QPointF(x,2),QPointF(x,self.height()-2))
            painter.setPen(QPen(ui_color('#81e9d9'),1.4,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            x, y = self.width()-7, self.height()/2
            painter.drawLine(QPointF(x-2,y-1),QPointF(x,y+1))
            painter.drawLine(QPointF(x,y+1),QPointF(x+2,y-1))
        if not self.icon().isNull():
            artwork = icon(self._aurora_icon[0],'#f1fffd') if active and hasattr(self,'_aurora_icon') else self.icon()
            artwork.paint(painter,self.icon_rect())
        elif self.text():
            painter.setFont(self.font())
            painter.setPen(QColor('#ffffff') if active else ui_color('#effaff'))
            painter.drawText(self.rect(),Qt.AlignCenter,self.text())
        painter.end()


class TableSplitButton(RibbonToolButton):
    """Dois menus reais: corpo abre dimensões, seta abre galeria de estilos.

    O popup da área principal permanece InstantPopup nativo, sem disparar
    showMenu() no sinal clicked (que causava travamento/reentrância).
    """

    ARROW_WIDTH = 14

    def __init__(self, parent=None):
        super().__init__(parent, menu=True)
        self.setPopupMode(QToolButton.InstantPopup)
        self.styles_menu = None
        self.setFocusPolicy(Qt.StrongFocus)

    def icon_rect(self):
        # Centraliza a arte na área principal, não sobre a divisória da seta.
        size = self.iconSize().boundedTo(
            QSize(self.width() - self.ARROW_WIDTH - 8, self.height() - 6))
        return QRect(
            (self.width() - self.ARROW_WIDTH - size.width()) // 2,
            (self.height() - size.height()) // 2, size.width(), size.height())

    def is_styles_arrow(self, x):
        return x >= self.width() - self.ARROW_WIDTH

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton and self.styles_menu is not None
                and self.is_styles_arrow(event.position().x())):
            # popup() não cria o loop de eventos aninhado de exec().
            self.styles_menu.popup(self.mapToGlobal(
                QPoint(self.width() - self.ARROW_WIDTH, self.height())))
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if (self.styles_menu is not None
                and event.key() == Qt.Key_Down
                and event.modifiers() & Qt.AltModifier):
            self.styles_menu.popup(self.mapToGlobal(
                QPoint(self.width() - self.ARROW_WIDTH, self.height())))
            event.accept()
            return
        super().keyPressEvent(event)


class RibbonFooter(QWidget):
    def __init__(self, title, callback, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        layout.addSpacing(22)
        self.label = QLabel(title)
        self.label.setObjectName('ribbonGroupTitle')
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label,1)
        self.launcher = RibbonToolButton(launcher=True)
        self.launcher.setObjectName('ribbonLauncher')
        self.launcher.setFixedSize(22,20)
        apply_icon(self.launcher,'paragraph-settings',label='Abrir opções de '+title.lower())
        self.launcher.setToolTip('Abrir opções de '+title.lower())
        self.launcher.clicked.connect(callback)
        layout.addWidget(self.launcher)
