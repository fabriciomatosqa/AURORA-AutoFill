"""Janela de cores completa, no tema Aurora, sem seletor nativo inconsistente."""
from __future__ import annotations

from .themes import set_ui_style, ui_color

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDialog, QDialogButtonBox


COLOR_DIALOG_STYLE = """
QColorDialog#auroraColorDialog {
    background-color: #0c1d31;
    color: #eaf7ff;
    border: 1px solid #4c9baf;
}
QColorDialog#auroraColorDialog QLabel {
    color: #d4eafb;
    background: transparent;
    border: none;
    font-size: 12px;
}
QColorDialog#auroraColorDialog QLineEdit,
QColorDialog#auroraColorDialog QSpinBox {
    min-height: 22px;
    color: #f2fcff;
    background: #17354b;
    border: 1px solid #3b657c;
    border-radius: 6px;
    padding: 3px 5px;
    selection-background-color: #2e817c;
}
QColorDialog#auroraColorDialog QLineEdit:focus,
QColorDialog#auroraColorDialog QSpinBox:focus {
    border-color: #79ead8;
}
QColorDialog#auroraColorDialog QPushButton {
    background: #1b3a51;
    border: 1px solid #41677a;
    border-radius: 7px;
    color: #ecf8ff;
    min-height: 25px;
    padding: 5px 12px;
}
QColorDialog#auroraColorDialog QPushButton:hover {
    background: #245568;
    border-color: #79ead8;
}
QColorDialog#auroraColorDialog QPushButton#auroraApplyColor {
    background: #55d6c0;
    border-color: #55d6c0;
    color: #09283b;
    font-weight: 750;
}
QColorDialog#auroraColorDialog QPushButton#auroraApplyColor:hover {
    background: #99f4e2;
}
"""


class AuroraColorDialog(QColorDialog):
    """Mantém espectro, HSV/RGB, código hexadecimal, paletas e customizadas."""

    def __init__(self, initial: QColor, parent=None, title: str = "Cor do texto"):
        super().__init__(initial, parent)
        self.setObjectName("auroraColorDialog")
        self.setWindowTitle(f"AURORA AutoFill · {title}")
        self.setOption(QColorDialog.DontUseNativeDialog, True)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        set_ui_style(self, COLOR_DIALOG_STYLE)
        self.setMinimumWidth(520)
        for button_box in self.findChildren(QDialogButtonBox):
            apply = button_box.button(QDialogButtonBox.Ok)
            cancel = button_box.button(QDialogButtonBox.Cancel)
            if apply:
                apply.setText("Aplicar cor")
                apply.setObjectName("auroraApplyColor")
            if cancel:
                cancel.setText("Cancelar")

    @classmethod
    def get_color(cls, initial: QColor, parent=None, title: str = "Cor do texto") -> QColor:
        dialog = cls(initial, parent, title)
        return dialog.selectedColor() if dialog.exec() == QDialog.Accepted else QColor()
