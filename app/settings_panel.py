"""Responsive, compact settings dashboard with self-contained AURORA cards.

The panels only reorganize controls. All signals, preference keys, accessible
names and save/update operations keep their established behavior in ui.py.
"""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSlider, QVBoxLayout, QWidget,
)

from .icons import apply_icon
from .themes import set_ui_style
from .version import IS_PRERELEASE


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    sound_toggled = Signal(bool)
    volume_changed = Signal(int)
    startup_toggled = Signal(bool)
    start_minimized_toggled = Signal(bool)
    updates_toggled = Signal(bool)
    prereleases_toggled = Signal(bool)
    suggestions_toggled = Signal(bool)
    global_search_requested = Signal()
    statistics_requested = Signal()
    linux_setup_requested = Signal()
    play_requested = Signal()
    backup_requested = Signal()
    restore_requested = Signal()
    open_backups_requested = Signal()
    check_requested = Signal()
    close_requested = Signal()

    # Two useful columns when room permits; one comfortable reading column
    # on smaller windows. Based on the *available viewport*, not screen DPI.
    TWO_COLUMN_MIN_WIDTH = 820

    def __init__(self, prefs: dict, *, startup_supported: bool, startup_enabled: bool,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        check_icon = (Path(__file__).resolve().parents[1] / "assets" / "checkmark.svg").as_posix()
        set_ui_style(self, r"""
            QWidget#settingsPage, QWidget#settingsContent,
            QWidget#settingsViewport, QWidget#settingsDashboard,
            QWidget#settingsLeftColumn, QWidget#settingsRightColumn {
                background: #091426; color: #eaf4ff;
            }
            QScrollArea#settingsScroll {
                border: none; background: #091426;
            }
            QFrame#settingsCard {
                background: #102338; border: 1px solid #24445f;
                border-radius: 12px;
            }
            QFrame#settingsAccent {
                background: #63dfc9; border: none; border-radius: 2px;
            }
            QLabel#settingsCardTitle {
                color: #eaf4ff; font-size: 16px; font-weight: 700;
                background: transparent;
            }
            QLabel#settingsPageTitle {
                color: #eaf4ff; font-size: 22px; font-weight: 750;
                background: transparent;
            }
            QLabel#settingsIntro, QLabel#settingsHint,
            QLabel#settingsCardIntro {
                color: #b8cde0; font-size: 12px; background: transparent;
            }
            QLabel#settingsFieldLabel {
                color: #eaf4ff; font-size: 13px; font-weight: 600;
                background: transparent;
            }
            QFrame#settingsToolTile {
                background: #143345; border: 1px solid #28546a;
                border-radius: 9px;
            }
            QLabel#settingsToolName {
                font-size: 13px; font-weight: 650; color: #eaf4ff;
                background: transparent;
            }
            QCheckBox {
                color: #eaf4ff; spacing: 9px; font-size: 13px;
                background: transparent;
            }
            QCheckBox:disabled { color: #7995ab; }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 1px solid #58788f; border-radius: 4px;
                background: #132d43;
            }
            QCheckBox::indicator:hover { border-color: #72e6d5; }
            QCheckBox::indicator:checked {
                background: #63dfc9; border-color: #63dfc9;
                image: url("CHECK_ICON");
            }
            QCheckBox::indicator:disabled {
                background: #1a3042; border-color: #3b5365;
            }
            QComboBox#themePicker {
                min-height: 30px; padding: 3px 10px;
                border: 1px solid #416777; border-radius: 7px;
                background: #19364b; color: #eaf4ff;
            }
            QSlider::groove:horizontal {
                background: #264459; height: 6px; border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #479f9e; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #72e6d5; width: 17px;
                margin: -6px 0; border-radius: 8px;
            }
            QSlider::handle:horizontal:hover { background: #a0f5e5; }
            QSlider::handle:horizontal:disabled { background: #4b687b; }
            QSlider::sub-page:horizontal:disabled { background: #304d60; }
            QPushButton#settingsAction {
                min-height: 31px; padding: 3px 12px;
                border-radius: 7px; border: 1px solid #416777;
                background: #19364b; color: #eaf4ff;
            }
            QPushButton#settingsAction:hover {
                background: #28546a; border-color: #72e6d5;
            }
            QPushButton#settingsAction:pressed { background: #24445f; }
            QPushButton#settingsAction:disabled { color: #7995ab; }
            QPushButton#settingsBack {
                min-height: 32px; padding: 4px 14px;
                border-radius: 7px; border: 1px solid #416777;
                background: #19364b; color: #eaf4ff;
            }
            QPushButton#settingsBack:hover { border-color: #72e6d5; }
        """.replace("CHECK_ICON", check_icon))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroller = QScrollArea(self)
        self.scroller.setObjectName("settingsScroll")
        self.scroller.setFrameShape(QFrame.NoFrame)
        self.scroller.viewport().setObjectName("settingsViewport")
        self.scroller.setWidgetResizable(True)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        body = QWidget()
        body.setObjectName("settingsContent")
        outer = QHBoxLayout(body)
        outer.setContentsMargins(18, 18, 18, 22)
        outer.setSpacing(0)
        outer.addStretch(1)
        self.dashboard = QWidget(body)
        self.dashboard.setObjectName("settingsDashboard")
        self.dashboard.setMaximumWidth(1080)
        content = QVBoxLayout(self.dashboard)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(18)
        outer.addWidget(self.dashboard, 10)
        outer.addStretch(1)

        head = QHBoxLayout()
        heading_column = QVBoxLayout()
        heading_column.setSpacing(4)
        heading = QLabel("Configurações")
        heading.setObjectName("settingsPageTitle")
        heading_column.addWidget(heading)
        intro = QLabel("Personalize o AURORA e gerencie suas ferramentas.")
        intro.setObjectName("settingsIntro")
        intro.setWordWrap(True)
        heading_column.addWidget(intro)
        head.addLayout(heading_column, 1)
        back = apply_icon(QPushButton("Voltar"), "back")
        back.setObjectName("settingsBack")
        back.clicked.connect(self.close_requested.emit)
        head.addWidget(back, 0, Qt.AlignTop)
        content.addLayout(head)

        # Independent vertical stacks avoid tall, empty grid rows.
        self.columns_layout = QHBoxLayout()
        self.columns_layout.setSpacing(16)
        self.left_host = QWidget()
        self.left_host.setObjectName("settingsLeftColumn")
        self.left_column = QVBoxLayout(self.left_host)
        self.left_column.setContentsMargins(0, 0, 0, 0)
        self.left_column.setSpacing(16)
        self.right_host = QWidget()
        self.right_host.setObjectName("settingsRightColumn")
        self.right_column = QVBoxLayout(self.right_host)
        self.right_column.setContentsMargins(0, 0, 0, 0)
        self.right_column.setSpacing(16)
        self.columns_layout.addWidget(self.left_host, 1, Qt.AlignTop)
        self.columns_layout.addWidget(self.right_host, 1, Qt.AlignTop)
        content.addLayout(self.columns_layout, 1)

        self.cards = {}
        self._appearance_card(prefs)
        self._productivity_card(prefs)
        self._audio_card(prefs)
        self._startup_card(prefs, startup_supported, startup_enabled)
        self._backup_card()
        self._updates_card(prefs)

        self._compact_columns = None
        self._reflow_cards(force=True)
        self.scroller.setWidget(body)
        root.addWidget(self.scroller)
        # The actual viewport width is only reliable after the stacked page
        # is laid out. Re-evaluate then and after every resize.
        QTimer.singleShot(0, self._reflow_cards)

    def _card(self, key: str, title: str, summary: str = "") -> QVBoxLayout:
        frame = QFrame(self.dashboard)
        frame.setObjectName("settingsCard")
        self.cards[key] = frame
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(17, 16, 17, 18)
        layout.setSpacing(11)
        header = QHBoxLayout()
        header.setSpacing(9)
        accent = QFrame()
        accent.setObjectName("settingsAccent")
        accent.setFixedSize(4, 19)
        header.addWidget(accent, 0, Qt.AlignVCenter)
        title_widget = QLabel(title)
        title_widget.setObjectName("settingsCardTitle")
        header.addWidget(title_widget)
        header.addStretch()
        layout.addLayout(header)
        if summary:
            layout.addWidget(self._hint(summary, name="settingsCardIntro"))
        return layout

    @staticmethod
    def _hint(text: str, name: str = "settingsHint") -> QLabel:
        label = QLabel(text)
        label.setObjectName(name)
        label.setWordWrap(True)
        return label

    @staticmethod
    def _action(text: str, *, name: str = "", icon: str = "") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(name or "settingsAction")
        if name:
            # Target by a semantic name while retaining the same card style.
            set_ui_style(button, r"""
                QPushButton {
                    min-height: 31px; padding: 3px 12px;
                    border: 1px solid #416777; border-radius: 7px;
                    background: #19364b; color: #eaf4ff;
                }
                QPushButton:hover {
                    border-color: #72e6d5; background: #28546a;
                }
                QPushButton:pressed { background: #24445f; }
            """)
        if icon:
            apply_icon(button, icon)
        return button

    @staticmethod
    def _button_row(layout: QVBoxLayout, button: QPushButton, width: int = 245):
        button.setMaximumWidth(width)
        row = QHBoxLayout()
        row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)

    def _tool_tile(self, layout: QVBoxLayout, title: str, help_text: str,
                   button: QPushButton):
        tile = QFrame()
        tile.setObjectName("settingsToolTile")
        inner = QVBoxLayout(tile)
        inner.setContentsMargins(12, 11, 12, 11)
        inner.setSpacing(7)
        name = QLabel(title)
        name.setObjectName("settingsToolName")
        inner.addWidget(name)
        inner.addWidget(self._hint(help_text))
        self._button_row(inner, button, 240)
        layout.addWidget(tile)

    def _appearance_card(self, prefs: dict):
        area = self._card("appearance", "Aparência", "Escolha a identidade visual do aplicativo.")
        title = QLabel("Tema do aplicativo")
        title.setObjectName("settingsFieldLabel")
        area.addWidget(title)
        self.theme = QComboBox()
        self.theme.setObjectName("themePicker")
        self.theme.setAccessibleName("Tema do aplicativo")
        self.theme.setMaximumWidth(260)
        for text, value in (("Claro", "light"), ("Escuro", "dark"),
                            ("Seguir o sistema", "system")):
            self.theme.addItem(text, value)
        self.theme.setCurrentIndex(self.theme.findData(prefs.get("theme", "dark")))
        self.theme.currentIndexChanged.connect(
            lambda _: self.theme_changed.emit(self.theme.currentData()))
        title.setBuddy(self.theme)
        row = QHBoxLayout()
        row.addWidget(self.theme)
        row.addStretch()
        area.addLayout(row)
        area.addWidget(self._hint(
            "As alterações são aplicadas imediatamente. Se o sistema não "
            "informar sua preferência, será utilizado o tema escuro."))

    def _productivity_card(self, prefs: dict):
        area = self._card("productivity", "Produtividade",
                          "Acesse seus comandos com mais rapidez.")
        self.suggestions = QCheckBox(
            "Mostrar sugestões de atalhos enquanto digito em outros aplicativos")
        self.suggestions.setToolTip(
            "Opcional e desativado por padrão. Pode mostrar dicas sobre campos privados.")
        self.suggestions.setChecked(prefs.get("suggest_shortcuts", False))
        self.suggestions.toggled.connect(self.suggestions_toggled.emit)
        area.addWidget(self.suggestions)
        area.addWidget(self._hint(
            "Digite / para abrir o menu de comandos. Use ↑/↓ para navegar, "
            "Tab ou Enter para inserir e Esc para fechar. Não use em campos de senha."))

        search_button = self._action(
            "Abrir Pesquisa global", name="globalSearchSettingsButton")
        search_button.setAccessibleName("Abrir Pesquisa global")
        search_button.clicked.connect(self.global_search_requested.emit)
        self._tool_tile(area, "Pesquisa global",
                        "Localize comandos pelo nome, atalho ou conteúdo. "
                        "Atalho: Ctrl + Shift + Espaço.", search_button)

        statistics_button = self._action(
            "Abrir Estatísticas locais", name="statisticsSettingsButton")
        statistics_button.setAccessibleName("Abrir Estatísticas locais")
        statistics_button.clicked.connect(self.statistics_requested.emit)
        self._tool_tile(area, "Estatísticas",
                        "Consulte usos por dia em um calendário, navegue pelos "
                        "meses e veja os totais. Os dados ficam neste computador.",
                        statistics_button)
        if sys.platform.startswith("linux"):
            setup = self._action("Configurar atalhos no Linux Wayland")
            setup.clicked.connect(self.linux_setup_requested.emit)
            self._button_row(area, setup, 290)

    def _audio_card(self, prefs: dict):
        area = self._card("audio", "Áudio",
                          "Personalize a confirmação sonora dos comandos.")
        self.sound = QCheckBox("Reproduzir som ao salvar e acionar comandos")
        self.sound.setChecked(prefs["sound_enabled"])
        self.sound.toggled.connect(self.sound_toggled.emit)
        area.addWidget(self.sound)
        area.addWidget(self._hint(
            "O som indica que a colagem foi acionada. Alguns navegadores não "
            "permitem confirmar se o texto foi aceito."))
        area.addWidget(self._field_label("Volume"))
        volume_row = QHBoxLayout()
        self.volume = QSlider(Qt.Horizontal)
        self.volume.setObjectName("volumeSlider")
        self.volume.setRange(0, 100)
        self.volume.setValue(prefs["sound_volume"])
        self.volume.setMaximumWidth(270)
        self.volume.valueChanged.connect(self.volume_changed.emit)
        volume_row.addWidget(self.volume, 1)
        self.volume_label = QLabel(str(self.volume.value()) + "%")
        self.volume_label.setMinimumWidth(42)
        self.volume_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.volume.valueChanged.connect(
            lambda value: self.volume_label.setText(str(value) + "%"))
        volume_row.addWidget(self.volume_label)
        volume_row.addStretch(1)
        area.addLayout(volume_row)
        self.sound.toggled.connect(self.volume.setEnabled)
        self.volume.setEnabled(self.sound.isChecked())
        self.sample_button = self._action("Ouvir gota de confirmação", icon="volume")
        self.sample_button.setToolTip("Ouvir o som com o volume escolhido")
        self.sample_button.setEnabled(self.sound.isChecked())
        self.sound.toggled.connect(self.sample_button.setEnabled)
        self.sound.toggled.connect(self.volume_label.setEnabled)
        self.volume_label.setEnabled(self.sound.isChecked())
        self.sample_button.clicked.connect(self.play_requested.emit)
        self._button_row(area, self.sample_button, 265)

    @staticmethod
    def _field_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("settingsFieldLabel")
        return label

    def _startup_card(self, prefs, startup_supported, startup_enabled):
        area = self._card("startup", "Inicialização",
                          "Escolha como o AURORA inicia com o computador.")
        self.startup = QCheckBox("Iniciar com o Windows")
        self.startup.setEnabled(startup_supported)
        self.startup.setChecked(startup_enabled)
        self.startup.setToolTip("Disponível no AURORA instalado no Windows")
        area.addWidget(self.startup)
        self.start_minimized = QCheckBox("Iniciar minimizado")
        self.start_minimized.setToolTip(
            "Ao iniciar com o Windows, permanece na bandeja do sistema, sem abrir a janela.")
        self.start_minimized.setChecked(prefs.get("start_minimized", False))
        self.start_minimized.setEnabled(startup_supported and startup_enabled)
        self.startup.toggled.connect(
            lambda enabled: self.start_minimized.setEnabled(startup_supported and enabled))
        self.startup.toggled.connect(self.startup_toggled.emit)
        self.start_minimized.toggled.connect(self.start_minimized_toggled.emit)
        area.addWidget(self.start_minimized)
        if not startup_supported:
            area.addWidget(self._hint(
                "A inicialização automática exige o aplicativo instalado no Windows."))

    def _backup_card(self):
        area = self._card("backups", "Segurança dos dados",
                          "Suas pastas e comandos continuam armazenados localmente.")
        area.addWidget(self._hint(
            "O backup inclui pastas, comandos, formatação e ordem. "
            "Outro backup é criado antes da instalação de atualizações."))
        for label, signal, icon, object_name in (
            ("Criar backup completo", self.backup_requested,
             "backup", "settingsBackupCreateButton"),
            ("Restaurar backup", self.restore_requested,
             "restore", "settingsBackupRestoreButton"),
            ("Abrir backups", self.open_backups_requested,
             "folder", "settingsBackupOpenButton"),
        ):
            button = self._action(label, name=object_name, icon=icon)
            button.clicked.connect(signal.emit)
            self._button_row(area, button, 235)

    def _updates_card(self, prefs):
        area = self._card("updates", "Atualizações",
                          "Controle quando e quais versões serão oferecidas.")
        self.updates = QCheckBox("Avisar quando houver uma nova versão")
        self.updates.setChecked(prefs["check_updates"])
        self.updates.toggled.connect(self.updates_toggled.emit)
        area.addWidget(self.updates)
        self.prereleases = QCheckBox("Receber versões de teste")
        self.prereleases.setChecked(
            prefs.get("include_prereleases", IS_PRERELEASE))
        self.prereleases.toggled.connect(self.prereleases_toggled.emit)
        area.addWidget(self.prereleases)
        area.addWidget(self._hint(
            "Verificação ao iniciar e a cada 6 horas de funcionamento. "
            "Após recusar uma atualização, um novo aviso aparece em 3 horas. "
            "A instalação só acontece com sua confirmação."))
        self.check_button = self._action(
            "Verificar atualizações agora", name="settingsCheckUpdatesButton",
            icon="update")
        self.check_button.clicked.connect(self.check_requested.emit)
        self._button_row(area, self.check_button, 270)
        area.addWidget(self._hint(
            "As preferências são salvas automaticamente neste computador."))

    def _reflow_cards(self, *, force: bool = False):
        if not hasattr(self, "cards") or len(self.cards) != 6:
            return
        width = self.scroller.viewport().width()
        if width <= 0:
            width = self.width()
        compact = width < self.TWO_COLUMN_MIN_WIDTH
        if compact == self._compact_columns and not force:
            return
        self._compact_columns = compact

        # First empty both stacks; card QWidgets themselves remain alive,
        # preserving all signal bindings and actual checkbox state.
        for column in (self.left_column, self.right_column):
            while column.count():
                item = column.takeAt(0)
                # QLayoutItem is not a QWidget, and stretch items do not own widgets.
                del item

        if compact:
            left = ("appearance", "productivity", "audio",
                    "startup", "backups", "updates")
            right = ()
        else:
            left = ("appearance", "productivity", "backups")
            right = ("audio", "startup", "updates")

        for name in left:
            self.left_column.addWidget(self.cards[name])
            self.cards[name].show()
        self.left_column.addStretch(1)
        for name in right:
            self.right_column.addWidget(self.cards[name])
            self.cards[name].show()
        if right:
            self.right_column.addStretch(1)
        self.right_host.setVisible(bool(right))
        self.columns_layout.setStretch(0, 1)
        self.columns_layout.setStretch(1, 1 if right else 0)
        self.dashboard.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_compact_columns"):
            self._reflow_cards()
