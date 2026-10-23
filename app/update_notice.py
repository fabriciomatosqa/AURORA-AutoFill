"""Aviso de atualização próximo à bandeja do Windows, com botões de decisão.

QSystemTrayIcon.showMessage não oferece botões próprios em todas as versões
do Windows. Uma janela Tool pequena permite Sim/Não sem abrir a interface
principal ou bloquear outros programas.
"""
from __future__ import annotations

from .themes import set_ui_style, ui_color

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)


class UpdateNotice(QWidget):
    accepted = Signal()
    declined = Signal()

    def __init__(self):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setObjectName("auroraUpdateNotice")
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedWidth(366)

        outside = QVBoxLayout(self)
        outside.setContentsMargins(3, 3, 3, 3)
        panel = QFrame()
        panel.setObjectName("updatePanel")
        set_ui_style(panel, """
            QFrame#updatePanel {
                background: #0d2238;
                border: 1px solid #4c9baf;
                border-radius: 14px;
            }
            QLabel { color: #eff8ff; background: transparent; border: none; }
            QLabel#updateHeading { font-size: 16px; font-weight: 760; color: #7cebd9; }
            QLabel#updateDetail { font-size: 12px; color: #d4e9f7; }
            QPushButton {
                border-radius: 8px; padding: 10px 20px;
                font-weight: 700; font-size: 13px;
                border: 1px solid #3d7084;
                color: #eefaff; background: #1c3b52;
            }
            QPushButton:hover { border-color: #7cebd9; background: #28536a; }
            QPushButton#updateAccept {
                background: #65e2ca; color: #092437; border: 1px solid #65e2ca;
            }
            QPushButton#updateAccept:hover { background: #a2f6e8; }
        """)
        content = QVBoxLayout(panel)
        content.setContentsMargins(18, 16, 18, 16)
        content.setSpacing(9)

        title = QLabel("AURORA AutoFill — Atualização")
        title.setObjectName("updateHeading")
        content.addWidget(title)
        self.versions = QLabel()
        self.versions.setObjectName("updateDetail")
        self.versions.setWordWrap(True)
        content.addWidget(self.versions)
        self.description = QLabel("Deseja atualizar agora?")
        self.description.setWordWrap(True)
        self.description.setObjectName("updateDetail")
        content.addWidget(self.description)
        note = QLabel("Não: perguntar novamente após 3 horas de uso do computador.")
        note.setWordWrap(True)
        note.setObjectName("updateDetail")
        content.addWidget(note)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.no_button = QPushButton("Não")
        self.no_button.clicked.connect(self._decline)
        buttons.addWidget(self.no_button)
        self.yes_button = QPushButton("Sim")
        self.yes_button.setObjectName("updateAccept")
        self.yes_button.clicked.connect(self._accept)
        buttons.addWidget(self.yes_button)
        content.addLayout(buttons)
        outside.addWidget(panel)

    def display(self, version: str, installed: str, *, page_only: bool = False) -> None:
        self.versions.setText(f"Nova versão: v{version}\nInstalada: v{installed}")
        if page_only:
            self.description.setText(
                "Deseja abrir a página oficial para atualizar neste formato de instalação?")
        else:
            self.description.setText(
                "Deseja baixar e instalar a nova versão automaticamente?")
        self.adjustSize()
        self._position_near_tray()
        self.show()
        self.raise_()

    def _position_near_tray(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        self.move(available.right() - self.width() - 14,
                  available.bottom() - self.sizeHint().height() - 14)

    def _accept(self) -> None:
        self.hide()
        self.accepted.emit()

    def _decline(self) -> None:
        self.hide()
        self.declined.emit()
