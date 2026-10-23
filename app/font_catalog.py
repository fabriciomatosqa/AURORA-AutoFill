"""Lista pesquisável de fontes realmente instaladas.

Em certas distribuições PySide6 no Windows a enumeração do Qt fica vazia
ou mostra só a fonte padrão; o registro do Windows também contém as fontes
instaladas pelo sistema e pelo usuário.
"""
from __future__ import annotations

import sys

from .themes import ui_color

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontDatabase, QPainter, QPen
from PySide6.QtWidgets import QApplication, QComboBox, QCompleter


def _windows_installed_families() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        import winreg
    except ImportError:
        return []
    names: set[str] = set()
    path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(hive, path) as registry:
                index = 0
                while True:
                    try:
                        description, _filename, _type = winreg.EnumValue(registry, index)
                        index += 1
                    except OSError:
                        break
                    # Os nomes de registro têm sufixos descritivos, não
                    # pertencentes à família exibida (ex.: ' (TrueType)').
                    family = str(description).strip()
                    for suffix in (" (TrueType)", " (OpenType)", " (All res)"):
                        if family.casefold().endswith(suffix.casefold()):
                            family = family[:-len(suffix)].strip()
                    if family:
                        names.add(family)
        except OSError:
            continue
    return sorted(names, key=str.casefold)


def installed_font_families() -> list[str]:
    try:
        qt_families = QFontDatabase.families()
    except (RuntimeError, TypeError):
        qt_families = []
    qt_families = [str(name).strip() for name in qt_families if str(name).strip()]
    installed = {*qt_families, *_windows_installed_families()}
    if not installed:
        app = QApplication.instance()
        if app is not None:
            installed.add(app.font().family())
    return sorted((name for name in installed if name), key=str.casefold)


class AuroraFontCombo(QComboBox):
    """Combo editável com lista real de famílias, busca e seta sempre visível."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fontFamily")
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(16)
        self.reload_families()

    def reload_families(self):
        old = self.currentText()
        families = installed_font_families()
        self.blockSignals(True)
        self.clear()
        self.addItems(families)
        if old:
            self.setEditText(old)
        elif self.count():
            self.setCurrentIndex(0)
        self.blockSignals(False)
        completer = QCompleter(families, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)
        self.lineEdit().setPlaceholderText("Pesquisar fonte…")

    def paintEvent(self, event):
        super().paintEvent(event)
        # O CSS global ocultava a seta nativa em algumas versões Windows/Qt.
        # A seta é desenhada pelo próprio Aurora, independente do estilo host.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(ui_color("#81e9d9"), 1.7))
        x = self.width() - 15
        y = self.height() // 2
        painter.drawLine(x - 5, y - 2, x, y + 3)
        painter.drawLine(x, y + 3, x + 5, y - 2)
        painter.end()
