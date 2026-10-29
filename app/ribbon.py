"""Ribbon controls with predictable icon geometry on Windows and Linux."""
from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QWidget

from .icons import apply_icon, icon
from .themes import current_theme, ui_color


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
            self.setPopupMode(QToolButton.DelayedPopup)

    def mousePressEvent(self, event):
        # Native MenuButtonPopup reserves an invisible arrow at the far edge.
        # Use the arrow we actually paint in the centered split control.
        arrow = self.visual_rect()
        if (self._split_menu and self.menu() is not None and
                event.button() == Qt.LeftButton and
                arrow.right()-12 <= event.position().x() < self.width()):
            event.accept()
            self.showMenu()
            return
        super().mousePressEvent(event)

    def visual_rect(self):
        """Center the visible square inside a wider grid column."""
        arrow = 13 if self._split_menu else 0
        width = max(0, min(self.width()-2, self.height()+1+arrow))
        return QRect((self.width()-width)//2, 0, width, self.height())

    def icon_rect(self):
        visible = self.visual_rect()
        square_width = max(0, visible.width()-(13 if self._split_menu else 0))
        size = self.iconSize().boundedTo(
            QSize(max(0, square_width-6), max(0, visible.height()-6)))
        return QRect(visible.left()+(square_width-size.width())//2,
                     visible.top()+(visible.height()-size.height())//2,
                     size.width(), size.height())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        if not self.isEnabled():
            painter.setOpacity(.4)
        active = self.isChecked() or self.isDown()
        hover = self.underMouse()
        light = current_theme() == 'light'
        background = ('#d8f1ef' if active else '#eaf4fa' if hover else '#f5f9fc') if light else (
            '#2c6870' if active else '#28546a' if hover else '#19364b')
        border = ('#228b8b' if active or hover else '#b5cbd9') if light else (
            '#79ead8' if active or hover else '#365a71')
        visible = self.visual_rect()
        if not self._launcher or hover or active:
            painter.setPen(QPen(ui_color(border), 1))
            painter.setBrush(ui_color(background))
            painter.drawRoundedRect(QRectF(visible).adjusted(.5,.5,-.5,-.5),5,5)
        if self._split_menu:
            divider = visible.right()-12
            painter.setPen(QPen(ui_color('#aac6d7' if light else '#365a71'),1))
            painter.drawLine(QPointF(divider,3),QPointF(divider,self.height()-3))
            painter.setPen(QPen(ui_color('#176571' if light else '#81e9d9'),
                                1.5,Qt.SolidLine,Qt.RoundCap,Qt.RoundJoin))
            x,y = visible.right()-6,visible.center().y()
            painter.drawLine(QPointF(x-2,y-1),QPointF(x,y+1))
            painter.drawLine(QPointF(x,y+1),QPointF(x+2,y-1))
        if not self.icon().isNull():
            artwork = (icon(self._aurora_icon[0],'#f1fffd')
                       if active and hasattr(self,'_aurora_icon') and not light
                       else self.icon())
            artwork.paint(painter,self.icon_rect())
        elif self.text():
            painter.setFont(self.font())
            painter.setPen(QColor('#16324f' if light else '#ffffff' if active else '#effaff'))
            content = QRect(visible)
            if self._split_menu:
                content.setWidth(max(0,content.width()-13))
            painter.drawText(content,Qt.AlignCenter,self.text())
        painter.end()


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
        self.launcher.setToolTip('Abrir opções completas de '+title.lower())
        self.launcher.clicked.connect(callback)
        layout.addWidget(self.launcher)
