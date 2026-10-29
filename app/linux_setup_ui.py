"""Assistente Linux Wayland com consentimento explícito e terminal visível.

Não modifica permissões silenciosamente no instalador. O administrador
precisa autorizar no terminal com sudo e reiniciar a sessão.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QVBoxLayout,
)
from .wayland_input import is_wayland_session, diagnose_wayland

COMMANDS = """sudo usermod -aG input "$USER"
printf '%s\\n' 'KERNEL=="uinput", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/70-aurora-uinput.rules
sudo modprobe uinput
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc
echo "Configuração solicitada. Encerre a sessão e entre novamente para ativar o grupo input."
"""


def terminal_command():
    """Somente executáveis conhecidos, sem usar shell=True."""
    for executable, arguments in (
        ("gnome-terminal", ["--", "bash", "-lc"]),
        ("x-terminal-emulator", ["-e", "bash", "-lc"]),
        ("konsole", ["-e", "bash", "-lc"]),
    ):
        target = shutil.which(executable)
        if target:
            return [target, *arguments, COMMANDS + "\nexec bash"]
    return None


class LinuxSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AURORA — Atalhos no Linux Wayland")
        self.setMinimumWidth(540)
        self.setStyleSheet("""
            QDialog { background: #0d2036; color: #edfbff; }
            QLabel, QCheckBox { color: #edfbff; }
            QPushButton { background: #21445c; color: #efffff;
                border: 1px solid #5da9b2; border-radius: 7px; padding: 8px; }
        """)
        root = QVBoxLayout(self)
        root.setSpacing(12)
        status = QLabel(
            "Sessão: Wayland" if is_wayland_session() else
            "Sessão atual: fora do Wayland"
        )
        status.setStyleSheet("font-weight:bold;")
        root.addWidget(status)
        message = diagnose_wayland() if is_wayland_session() else (
            "Essa configuração só é necessária no GNOME Wayland.")
        details = QLabel(message)
        details.setWordWrap(True)
        root.addWidget(details)
        privacy = QLabel(
            "IMPORTANTE: a autorização ao grupo input concede à sua conta "
            "acesso a eventos do teclado e outros dispositivos, inclusive em "
            "outros aplicativos. É uma permissão poderosa e só deve ser "
            "utilizada em computadores pessoais confiáveis. "
            "A ativação pede senha do administrador; o AURORA nunca a recebe.")
        privacy.setWordWrap(True)
        root.addWidget(privacy)
        self.consent = QCheckBox(
            "Entendo que esta permissão permite leitura global do teclado.")
        root.addWidget(self.consent)
        row = QHBoxLayout()
        self.activate = QPushButton("Configurar com autorização")
        self.activate.setEnabled(False)
        self.consent.toggled.connect(self.activate.setEnabled)
        self.activate.clicked.connect(self._start)
        row.addWidget(self.activate)
        copy = QPushButton("Copiar comandos")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(COMMANDS))
        row.addWidget(copy)
        close = QPushButton("Fechar")
        close.clicked.connect(self.close)
        row.addWidget(close)
        root.addLayout(row)
        footer = QLabel(
            "A configuração precisa ser solicitada uma única vez. "
            "Encerre a sessão e entre novamente antes de testar os atalhos. "
            "Para revogar o acesso, veja docs/linux-wayland.md no GitHub.")
        footer.setWordWrap(True)
        root.addWidget(footer)

    def _start(self):
        if not self.consent.isChecked():
            return
        args = terminal_command()
        if not args:
            QApplication.clipboard().setText(COMMANDS)
            QMessageBox.information(
                self, "Terminal não encontrado",
                "Não foi possível localizar um terminal compatível. "
                "Os comandos foram copiados para você colar em um terminal.")
            return
        try:
            subprocess.Popen(args, close_fds=True)
            QMessageBox.information(
                self, "Autorização no Terminal",
                "O terminal foi aberto para você conferir a operação e "
                "autorizar com sua senha de administrador. "
                "Após concluir, saia da sessão e entre novamente.")
        except OSError as error:
            QApplication.clipboard().setText(COMMANDS)
            QMessageBox.warning(
                self, "Erro ao abrir Terminal",
                f"{error}. Os comandos foram copiados para colagem manual.")
