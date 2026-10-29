"""Janela de cores completa, no tema Aurora, sem seletor nativo inconsistente."""
from __future__ import annotations

from .themes import set_ui_style, ui_color

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractButton, QColorDialog, QDialog,
                               QDialogButtonBox, QLabel)


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
QColorDialog#auroraColorDialog QPushButton#auroraResetColor {
    background: #24445a;
    border-color: #6c9cae;
    color: #eaf7ff;
}
QColorDialog#auroraColorDialog QPushButton#auroraResetColor:hover {
    border-color: #79ead8;
    background: #2e6070;
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
        # RGB/HSV labels need more room when written in Portuguese.
        self.setMinimumWidth(630)
        self.reset_requested = False
        self.reset_button = None
        self._localize_qt_controls()
        for button_box in self.findChildren(QDialogButtonBox):
            apply = button_box.button(QDialogButtonBox.Ok)
            cancel = button_box.button(QDialogButtonBox.Cancel)
            if apply:
                apply.setText("Aplicar cor")
                apply.setObjectName("auroraApplyColor")
            if cancel:
                cancel.setText("Cancelar")
            self.reset_button = button_box.addButton(
                "Remover realce" if "realce" in title.casefold()
                else "Cor automática",
                QDialogButtonBox.ResetRole,
            )
            self.reset_button.setObjectName("auroraResetColor")
            self.reset_button.setToolTip(
                "Remove somente o realce da seleção, mantendo outros estilos."
                if "realce" in title.casefold() else
                "Remove somente a cor fixa do texto e restaura a cor automática."
            )
            self.reset_button.clicked.connect(self._reset_to_automatic)

    def _localize_qt_controls(self):
        """Translate Qt's built-in color picker (which may lack pt_BR .qm)."""
        terms = {
            "basic colors": "Cores básicas",
            "custom colors": "Cores personalizadas",
            "pick screen color": "Capturar cor da tela",
            "add to custom colors": "Adicionar às cores personalizadas",
            "hue": "Matiz",
            "sat": "Saturação",
            "val": "Brilho",
            "red": "Vermelho",
            "green": "Verde",
            "blue": "Azul",
            "html": "Hexadecimal",
            "name": "Nome",
            "alpha": "Transparência",
        }
        for child in [*self.findChildren(QLabel),
                      *self.findChildren(QAbstractButton)]:
            original = child.text()
            normalized = original.replace("&", "").strip()
            key = normalized.rstrip(":").strip().casefold()
            replacement = terms.get(key)
            if replacement:
                child.setText(replacement + (":" if normalized.endswith(":") else ""))

    def _reset_to_automatic(self):
        self.reset_requested = True
        self.accept()

    @classmethod
    def get_choice(cls, initial: QColor, parent=None,
                   title: str = "Cor do texto") -> tuple[bool, QColor]:
        """Returns (accepted, color); invalid accepted color means automatic."""
        dialog = cls(initial, parent, title)
        if dialog.exec() != QDialog.Accepted:
            return False, QColor()
        return True, QColor() if dialog.reset_requested else dialog.selectedColor()

    @classmethod
    def get_color(cls, initial: QColor, parent=None, title: str = "Cor do texto") -> QColor:
        """Legacy API: returns invalid color on cancel or automatic reset."""
        accepted, color = cls.get_choice(initial, parent, title)
        return color if accepted else QColor()
