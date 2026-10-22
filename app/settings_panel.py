"""Aurora-themed settings page. Signals keep all storage and update actions in ui.py."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QVBoxLayout, QWidget)
from .version import IS_PRERELEASE
from .icons import apply_icon


class SettingsPage(QWidget):
    sound_toggled = Signal(bool)
    volume_changed = Signal(int)
    startup_toggled = Signal(bool)
    start_minimized_toggled = Signal(bool)
    updates_toggled = Signal(bool)
    prereleases_toggled = Signal(bool)
    play_requested = Signal()
    backup_requested = Signal()
    restore_requested = Signal()
    open_backups_requested = Signal()
    check_requested = Signal()
    close_requested = Signal()

    def __init__(self, prefs: dict, *, startup_supported: bool, startup_enabled: bool,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        # A custom QWidget and a scroll viewport do not automatically paint the
        # parent's stylesheet. Explicit surfaces keep the Windows dark palette
        # from showing through as an unrelated black rectangle.
        self.setAttribute(Qt.WA_StyledBackground, True)
        check_icon = (Path(__file__).resolve().parents[1] / "assets" / "checkmark.svg").as_posix()
        self.setStyleSheet("""
            QWidget#settingsPage, QWidget#settingsContent, QWidget#settingsViewport {
                background: #091426; color: #eaf4ff;
            }
            QCheckBox { color: #eaf4ff; spacing: 10px; font-size: 13px; }
            QCheckBox:disabled { color: #7995ab; }
            QCheckBox::indicator {
                width: 16px; height: 16px; border: 1px solid #58788f;
                border-radius: 4px; background: #132d43;
            }
            QCheckBox::indicator:hover { border-color: #72e6d5; }
            QCheckBox::indicator:checked {
                background: #63dfc9; border-color: #63dfc9; image: url("CHECK_ICON");
            }
            QCheckBox::indicator:disabled { background: #1a3042; border-color: #3b5365; }
            QSlider::groove:horizontal { background: #264459; height: 6px; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #479f9e; border-radius: 3px; }
            QSlider::handle:horizontal {
                background: #72e6d5; width: 17px; margin: -6px 0; border-radius: 8px;
            }
            QSlider::handle:horizontal:hover { background: #a0f5e5; }
            QSlider::handle:horizontal:disabled { background: #4b687b; }
            QSlider::sub-page:horizontal:disabled { background: #304d60; }
            QScrollArea#settingsScroll { border: none; background: #091426; }
        """.replace("CHECK_ICON", check_icon))
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroller = QScrollArea()
        scroller.setObjectName("settingsScroll")
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.viewport().setObjectName("settingsViewport")
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("settingsContent")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(14, 14, 18, 12)
        layout.setSpacing(14)
        scroller.setWidget(body)
        root.addWidget(scroller)
        head = QHBoxLayout()
        heading = QLabel("Configurações")
        heading.setObjectName("heading")
        head.addWidget(heading)
        head.addStretch()
        back = apply_icon(QPushButton("Voltar"), "back")
        back.clicked.connect(self.close_requested.emit)
        head.addWidget(back)
        layout.addLayout(head)
        self._label(layout, "ÁUDIO")
        self.sound = QCheckBox("Reproduzir som ao salvar e acionar comandos")
        self.sound.setChecked(prefs["sound_enabled"])
        self.sound.toggled.connect(self.sound_toggled.emit)
        layout.addWidget(self.sound)
        sound_hint = QLabel(
            "O som indica que a colagem foi acionada; alguns navegadores "
            "não permitem confirmar se o conteúdo foi aceito.")
        sound_hint.setObjectName("hint")
        sound_hint.setWordWrap(True)
        layout.addWidget(sound_hint)
        volume_row = QHBoxLayout()
        volume_row.addWidget(QLabel("Volume"))
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(prefs["sound_volume"])
        self.volume.valueChanged.connect(self.volume_changed.emit)
        volume_row.addWidget(self.volume, 1)
        self.volume_label = QLabel(str(self.volume.value()) + "%")
        self.volume_label.setMinimumWidth(44)
        self.volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.volume.valueChanged.connect(lambda n: self.volume_label.setText(str(n) + "%"))
        volume_row.addWidget(self.volume_label)
        layout.addLayout(volume_row)
        self.sound.toggled.connect(self.volume.setEnabled)
        self.volume.setEnabled(self.sound.isChecked())
        self.sample_button = apply_icon(QPushButton("Ouvir gota de confirmação"), "volume")
        self.sample_button.setToolTip("Ouvir o som com o volume escolhido")
        self.sample_button.setEnabled(self.sound.isChecked())
        self.sound.toggled.connect(self.sample_button.setEnabled)
        self.sound.toggled.connect(self.volume_label.setEnabled)
        self.volume_label.setEnabled(self.sound.isChecked())
        self.sample_button.clicked.connect(self.play_requested.emit)
        layout.addWidget(self.sample_button)
        self._divider(layout)
        self._label(layout, "INICIALIZAÇÃO")
        startup_row = QHBoxLayout()
        self.startup = QCheckBox("Iniciar com o Windows")
        self.startup.setEnabled(startup_supported)
        self.startup.setChecked(startup_enabled)
        self.startup.setToolTip("Disponível no AURORA instalado no Windows")
        startup_row.addWidget(self.startup)
        self.start_minimized = QCheckBox("Iniciar minimizado")
        self.start_minimized.setToolTip(
            "Ao iniciar com o Windows, permanece na bandeja do sistema, sem abrir a janela.")
        self.start_minimized.setChecked(prefs.get("start_minimized", False))
        self.start_minimized.setEnabled(startup_supported and startup_enabled)
        self.startup.toggled.connect(
            lambda enabled: self.start_minimized.setEnabled(startup_supported and enabled))
        self.startup.toggled.connect(self.startup_toggled.emit)
        self.start_minimized.toggled.connect(self.start_minimized_toggled.emit)
        startup_row.addSpacing(25)
        startup_row.addWidget(self.start_minimized)
        startup_row.addStretch(1)
        layout.addLayout(startup_row)
        if not startup_supported:
            hint = QLabel("A inicialização automática exige o aplicativo instalado no Windows.")
            hint.setObjectName("hint")
            layout.addWidget(hint)
        self._divider(layout)
        self._label(layout, "SEGURANÇA DOS DADOS")
        hint = QLabel("O backup inclui todas as pastas, comandos, formatação e ordem.\n"
                      "Um backup adicional será criado antes de instalar atualizações.")
        hint.setWordWrap(True)
        hint.setObjectName("hint")
        layout.addWidget(hint)
        backup_buttons = QHBoxLayout()
        for label, signal, glyph in (("Criar backup completo", self.backup_requested, "backup"),
                                     ("Restaurar backup", self.restore_requested, "restore"),
                                     ("Abrir backups", self.open_backups_requested, "folder")):
            button = apply_icon(QPushButton(label), glyph)
            button.clicked.connect(signal.emit)
            backup_buttons.addWidget(button)
        layout.addLayout(backup_buttons)
        self._divider(layout)
        self._label(layout, "ATUALIZAÇÕES")
        self.updates = QCheckBox("Avisar quando houver uma nova versão")
        self.updates.setChecked(prefs["check_updates"])
        self.updates.toggled.connect(self.updates_toggled.emit)
        layout.addWidget(self.updates)
        self.prereleases = QCheckBox("Receber versões de teste")
        self.prereleases.setChecked(prefs.get("include_prereleases", IS_PRERELEASE))
        self.prereleases.toggled.connect(self.prereleases_toggled.emit)
        layout.addWidget(self.prereleases)
        updates_text = QLabel("Busca ao iniciar e a cada 6 horas de funcionamento do computador.\n"
                              "Aviso próximo ao relógio com Sim/Não; após Não, novo aviso em 3 horas. "
                              "Instalação somente após confirmação.")
        updates_text.setWordWrap(True)
        updates_text.setObjectName("hint")
        layout.addWidget(updates_text)
        self.check_button = apply_icon(QPushButton("Verificar atualizações agora"), "update")
        self.check_button.clicked.connect(self.check_requested.emit)
        layout.addWidget(self.check_button)
        saved_hint = QLabel("As preferências são salvas automaticamente neste computador.")
        saved_hint.setObjectName("hint")
        saved_hint.setWordWrap(True)
        layout.addWidget(saved_hint)
        layout.addStretch(1)

    def _label(self, layout, value):
        title = QLabel(value)
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

    def _divider(self, layout):
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("border: none; background-color: #24445f;")
        layout.addWidget(line)
