"""Painel visual opcional para backup em nuvem — sem tocar no motor de expansão.

O diálogo realiza OAuth/rede em QThread e cria snapshots SQLite apenas na
thread principal, usando exatamente o mecanismo de backup local existente.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QLayout, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from .backups import create_backup
from .cloud_backups import (
    CloudBackupClient, CloudBackupError, RemoteBackup, import_google_client_configuration,
)
from .cloud_brand import BRAND_NAMES, provider_pixmap
from .icons import icon
from .themes import set_ui_style


class CloudBackupWorker(QThread):
    """Only network/auth work runs in the background. SQLite stays in the GUI thread."""

    def __init__(self, provider: str, action: str, argument=None, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.action = action
        self.argument = argument
        self.result = None
        self.failure = ""

    def run(self):
        try:
            client = CloudBackupClient(self.provider)
            if self.action == "connect":
                client.connect(cancelled=self.isInterruptionRequested)
                self.result = True
            elif self.action == "list":
                self.result = client.list_backups()
            elif self.action == "upload":
                self.result = client.upload_backup(Path(self.argument))
            elif self.action == "download":
                self.result = client.download_backup(self.argument)
            elif self.action == "disconnect":
                client.disconnect()
                self.result = True
            else:
                raise CloudBackupError("Operação desconhecida.")
        except Exception as exc:
            # Never display provider JSON, callback URLs, tokens or untrusted traces.
            self.failure = str(exc) if isinstance(exc, CloudBackupError) else (
                "Não foi possível concluir a operação de backup na nuvem.")


class CloudProviderCard(QFrame):
    """Mouse- and keyboard-accessible provider selection with a bundled SVG mark."""

    clicked = Signal(str)

    def __init__(self, provider: str, subtitle: str, parent=None):
        super().__init__(parent)
        if provider not in BRAND_NAMES:
            raise ValueError("Provedor desconhecido.")
        self.provider = provider
        self.setObjectName("cloudProviderCard")
        self.setProperty("selected", "false")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Selecionar " + BRAND_NAMES[provider])
        self.setMinimumHeight(82)
        self.setToolTip("Selecionar " + BRAND_NAMES[provider])

        row = QHBoxLayout(self)
        row.setContentsMargins(14, 13, 12, 13)
        row.setSpacing(12)
        logo = QLabel()
        logo.setObjectName("cloudProviderLogo")
        logo.setPixmap(provider_pixmap(provider, 44))
        logo.setFixedSize(44, 44)
        logo.setAttribute(Qt.WA_TransparentForMouseEvents)
        row.addWidget(logo)
        text = QVBoxLayout()
        text.setSpacing(3)
        name = QLabel(BRAND_NAMES[provider])
        name.setObjectName("cloudProviderName")
        name.setAttribute(Qt.WA_TransparentForMouseEvents)
        text.addWidget(name)
        description = QLabel(subtitle)
        description.setObjectName("cloudProviderSubtitle")
        description.setWordWrap(True)
        description.setAttribute(Qt.WA_TransparentForMouseEvents)
        text.addWidget(description)
        row.addLayout(text, 1)

    def set_selected(self, selected: bool):
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def mouseReleaseEvent(self, event):
        if (self.isEnabled() and event.button() == Qt.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit(self.provider)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if (self.isEnabled() and event.key() in
                (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space)):
            self.clicked.emit(self.provider)
            event.accept()
            return
        super().keyPressEvent(event)


class CloudBackupDialog(QDialog):
    def __init__(self, store, restore_callback, parent=None):
        super().__init__(parent)
        self.store = store
        self.restore_callback = restore_callback
        self._worker = None
        self._provider_id = "google"
        self._list_loaded = False
        self.setWindowTitle("Backup em nuvem — AURORA AutoFill")
        self.setMinimumSize(660, 580)
        self.resize(750, 650)
        set_ui_style(self, """
            QDialog { background: #091426; color: #eaf4ff; }
            QLabel { color: #d2e9f7; background: transparent; }
            QLabel#cloudDialogTitle {
                color: #f5faff; font-size: 22px; font-weight: 750;
            }
            QLabel#cloudDialogSubtitle, QLabel#cloudFooterNote {
                color: #b8cde0; font-size: 12px;
            }
            QLabel#cloudSectionHeading {
                color: #eaf4ff; font-size: 14px; font-weight: 700;
            }
            QFrame#cloudProviderCard {
                background: #102338; border: 1px solid #416777;
                border-radius: 12px;
            }
            QFrame#cloudProviderCard:hover {
                border: 1px solid #72e6d5; background: #19364b;
            }
            QFrame#cloudProviderCard[selected="true"] {
                background: #143345; border: 2px solid #63dfc9;
                border-radius: 12px;
            }
            QFrame#cloudProviderCard:focus {
                border: 2px solid #72e6d5;
            }
            QLabel#cloudProviderName {
                color: #eaf4ff; font-size: 14px; font-weight: 700;
            }
            QLabel#cloudProviderSubtitle {
                color: #b8cde0; font-size: 11px;
            }
            QFrame#cloudStatusPanel {
                background: #143345; border: 1px solid #28546a;
                border-radius: 11px;
            }
            QLabel#cloudStatusTitle {
                color: #eaf4ff; font-size: 14px; font-weight: 700;
            }
            QLabel#cloudStatusText, QLabel#cloudTechnicalDetails {
                color: #b8cde0; font-size: 12px;
            }
            QLabel#cloudBackupCount {
                color: #b8cde0; font-size: 12px;
            }
            QListWidget#cloudBackupList {
                background: #102338; border: 1px solid #416777;
                border-radius: 10px; padding: 7px; color: #eaf4ff;
                outline: none;
            }
            QListWidget#cloudBackupList::item {
                padding: 10px 8px; border-radius: 6px;
            }
            QListWidget#cloudBackupList::item:selected {
                background: #28546a; color: #eaf4ff;
            }
            QFrame#cloudEmptyPanel {
                background: #102338; border: 1px dashed #416777;
                border-radius: 10px;
            }
            QLabel#cloudEmptyTitle {
                color: #eaf4ff; font-size: 14px; font-weight: 700;
            }
            QLabel#cloudEmptyHint {
                color: #b8cde0; font-size: 12px;
            }
            QPushButton {
                min-height: 30px; padding: 5px 12px;
                background: #19364b; color: #eaf4ff;
                border: 1px solid #416777; border-radius: 8px;
            }
            QPushButton:hover {
                background: #28546a; border-color: #72e6d5;
            }
            QPushButton:disabled {
                background: #132d43; color: #7995ab;
                border-color: #3b5365;
            }
            QPushButton#cloudPrimaryAction:enabled {
                background: #287281; border: 1px solid #72e6d5;
                color: #f5faff; font-weight: 700;
            }
            QPushButton#cloudPrimaryAction:hover:enabled {
                background: #2e817c;
            }
            QPushButton#cloudDetailsButton {
                min-height: 16px; padding: 2px 0;
                border: none; background: transparent;
                color: #72e6d5; text-align: left;
            }
            QPushButton#cloudDetailsButton:hover {
                color: #a0f5e5; background: transparent;
            }
        """)

        root = QVBoxLayout(self)
        # Account configuration and expanded diagnostics must not overlap the
        # backup list/actions when the dialog's requested size is too small.
        root.setSizeConstraint(QLayout.SetMinimumSize)
        root.setContentsMargins(22, 19, 22, 17)
        root.setSpacing(13)

        heading = QLabel("Seu backup, na sua conta")
        heading.setObjectName("cloudDialogTitle")
        root.addWidget(heading)
        subtitle = QLabel(
            "Escolha Google Drive ou OneDrive para guardar cópias dos seus "
            "comandos e restaurá-las quando precisar.")
        subtitle.setObjectName("cloudDialogSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        provider_caption = QLabel("ESCOLHA ONDE SALVAR")
        provider_caption.setObjectName("cloudSectionHeading")
        root.addWidget(provider_caption)
        provider_row = QHBoxLayout()
        provider_row.setSpacing(12)
        self.provider_cards = {
            "google": CloudProviderCard(
                "google", "Pasta privativa do aplicativo", self),
            "onedrive": CloudProviderCard(
                "onedrive", "Sua conta Microsoft", self),
        }
        for provider in ("google", "onedrive"):
            card = self.provider_cards[provider]
            card.clicked.connect(self._select_provider)
            provider_row.addWidget(card, 1)
        root.addLayout(provider_row)
        self._apply_provider_selection()

        self.status_panel = QFrame(self)
        self.status_panel.setObjectName("cloudStatusPanel")
        status_layout = QVBoxLayout(self.status_panel)
        status_layout.setContentsMargins(15, 12, 15, 12)
        status_layout.setSpacing(6)
        self.status_title = QLabel()
        self.status_title.setObjectName("cloudStatusTitle")
        status_layout.addWidget(self.status_title)
        self.status = QLabel()
        self.status.setObjectName("cloudStatusText")
        self.status.setWordWrap(True)
        status_layout.addWidget(self.status)
        self.details_button = QPushButton("Ver detalhes técnicos")
        self.details_button.setObjectName("cloudDetailsButton")
        self.details_button.setCheckable(True)
        self.details_button.toggled.connect(self._toggle_details)
        configuration_actions = QHBoxLayout()
        configuration_actions.addWidget(self.details_button, 0, Qt.AlignLeft)
        configuration_actions.addStretch(1)
        self.configure_google_button = QPushButton("Configurar Google Drive")
        self.configure_google_button.setToolTip(
            "Carregar o JSON do cliente AURORA AutoFill Desktop baixado no Google Cloud")
        self.configure_google_button.clicked.connect(self._configure_google)
        configuration_actions.addWidget(self.configure_google_button)
        status_layout.addLayout(configuration_actions)
        self.technical_details = QLabel()
        self.technical_details.setObjectName("cloudTechnicalDetails")
        self.technical_details.setWordWrap(True)
        self.technical_details.setHidden(True)
        status_layout.addWidget(self.technical_details)
        root.addWidget(self.status_panel)

        account_actions = QHBoxLayout()
        account_actions.setSpacing(9)
        self.connect_button = QPushButton("Conectar minha conta")
        self.connect_button.setObjectName("cloudPrimaryAction")
        self.connect_button.clicked.connect(lambda: self._start("connect"))
        self.disconnect_button = QPushButton("Desconectar conta")
        self.disconnect_button.clicked.connect(self._disconnect)
        self.refresh_button = QPushButton("Atualizar lista")
        self.refresh_button.clicked.connect(lambda: self._start("list"))
        for button in (self.connect_button, self.refresh_button,
                       self.disconnect_button):
            account_actions.addWidget(button)
        root.addLayout(account_actions)

        backups_heading = QHBoxLayout()
        label = QLabel("SEUS BACKUPS NA NUVEM")
        label.setObjectName("cloudSectionHeading")
        backups_heading.addWidget(label)
        backups_heading.addStretch(1)
        self.backup_count = QLabel("")
        self.backup_count.setObjectName("cloudBackupCount")
        backups_heading.addWidget(self.backup_count)
        root.addLayout(backups_heading)

        self.backup_stack = QStackedWidget()
        self.backup_stack.setMinimumHeight(158)
        self.items = QListWidget()
        self.items.setObjectName("cloudBackupList")
        self.items.setAccessibleName("Backups encontrados na conta selecionada")
        self.items.itemSelectionChanged.connect(self._refresh_buttons)
        self.backup_stack.addWidget(self.items)

        self.empty_panel = QFrame(self)
        self.empty_panel.setObjectName("cloudEmptyPanel")
        empty_layout = QVBoxLayout(self.empty_panel)
        empty_layout.setContentsMargins(18, 19, 18, 19)
        empty_layout.setSpacing(8)
        empty_layout.addStretch(1)
        self.empty_icon = QLabel()
        self.empty_icon.setPixmap(icon("backup", "#63dfc9").pixmap(32, 32))
        self.empty_icon.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_icon)
        self.empty_title = QLabel()
        self.empty_title.setObjectName("cloudEmptyTitle")
        self.empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(self.empty_title)
        self.empty_hint = QLabel()
        self.empty_hint.setObjectName("cloudEmptyHint")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        empty_layout.addWidget(self.empty_hint)
        empty_layout.addStretch(1)
        self.backup_stack.addWidget(self.empty_panel)
        root.addWidget(self.backup_stack, 1)

        backup_actions = QHBoxLayout()
        backup_actions.setSpacing(9)
        self.upload_button = QPushButton("Enviar backup agora")
        self.upload_button.setObjectName("cloudPrimaryAction")
        self.upload_button.clicked.connect(self._upload)
        self.download_button = QPushButton("Baixar e restaurar")
        self.download_button.clicked.connect(self._download)
        self.cancel_button = QPushButton("Cancelar autorização")
        self.cancel_button.clicked.connect(self._cancel)
        for button in (self.upload_button, self.download_button,
                       self.cancel_button):
            backup_actions.addWidget(button)
        root.addLayout(backup_actions)

        bottom = QHBoxLayout()
        disclaimer = QLabel(
            "Envio manual • Restauração com confirmação • "
            "ZIP sem criptografia ponta a ponta")
        disclaimer.setObjectName("cloudFooterNote")
        disclaimer.setWordWrap(True)
        bottom.addWidget(disclaimer, 1)
        close = QPushButton("Fechar")
        close.setObjectName("cloudCloseButton")
        close.clicked.connect(self.reject)
        bottom.addWidget(close, 0, Qt.AlignBottom)
        root.addLayout(bottom)
        self._refresh_buttons()

    def _client(self):
        return CloudBackupClient(self._provider_id)

    def _configure_google(self):
        if self._provider_id != "google" or (
                self._worker is not None and self._worker.isRunning()):
            return
        filename, _ = QFileDialog.getOpenFileName(
            self, "Configuração do Google Drive", "", "Configuração Google (*.json)")
        if not filename:
            return
        try:
            import_google_client_configuration(Path(filename))
        except CloudBackupError as exc:
            QMessageBox.warning(self, "Configuração do Google Drive", str(exc))
            return
        self._refresh_buttons()
        QMessageBox.information(
            self, "Google Drive configurado",
            "Configuração guardada no cofre deste computador. "
            "Agora clique em Conectar minha conta para autorizar o backup.")

    def _apply_provider_selection(self):
        for provider, card in self.provider_cards.items():
            card.set_selected(provider == self._provider_id)

    def _select_provider(self, provider: str):
        if provider not in self.provider_cards:
            return
        if self._worker is not None and self._worker.isRunning():
            return
        if self._provider_id != provider:
            self._provider_id = provider
            self.items.clear()
            self._list_loaded = False
            self.details_button.setChecked(False)
            self._apply_provider_selection()
            self._refresh_buttons()

    def _toggle_details(self, expanded: bool):
        self.technical_details.setHidden(not expanded)
        self.details_button.setText(
            "Ocultar detalhes técnicos" if expanded else "Ver detalhes técnicos")

    def _refresh_empty_state(self, connected: bool):
        count = self.items.count()
        self.backup_count.setText(f"{count} backup(s)" if self._list_loaded else "")
        if count:
            self.backup_stack.setCurrentWidget(self.items)
            return
        self.backup_stack.setCurrentWidget(self.empty_panel)
        if not connected:
            title = "Conecte sua conta para começar"
            hint = "Seus backups aparecerão aqui depois da conexão."
        elif not self._list_loaded:
            title = "Consulte seus backups"
            hint = "Clique em Atualizar lista para procurar cópias na sua conta."
        else:
            title = "Nenhum backup encontrado"
            hint = "Use Enviar backup agora para guardar sua primeira cópia."
        self.empty_title.setText(title)
        self.empty_hint.setText(hint)

    def _refresh_buttons(self):
        active = self._worker is not None and self._worker.isRunning()
        self.cancel_button.setEnabled(active and self._worker.action == "connect")
        self.configure_google_button.setVisible(self._provider_id == "google")
        self.configure_google_button.setEnabled(not active)
        provider_name = BRAND_NAMES[self._provider_id]
        connected, ready, technical = False, False, ""
        try:
            connected = self._client().connected()
            ready = True
        except CloudBackupError as exc:
            technical = str(exc)
        if active:
            title = "Operação em andamento"
            description = (
                "Aguarde a conclusão antes de trocar de conta ou fechar a janela.")
        elif not ready:
            title = provider_name + " ainda não está disponível"
            description = (
                "A integração precisa ser configurada pelo aplicativo antes "
                "de permitir a conexão. Seus backups locais continuam funcionando.")
        elif connected:
            title = provider_name + " conectado"
            description = (
                "Sua conta está autorizada neste computador. Você pode enviar "
                "uma nova cópia ou recuperar backups existentes.")
        else:
            title = "Conecte sua conta " + provider_name
            description = (
                "O login acontece no navegador. Sua senha não é informada ao AURORA.")
        self.status_title.setText(title)
        self.status.setText(description)
        self.technical_details.setText(technical)
        self.details_button.setVisible(bool(technical))
        if not technical:
            self.details_button.setChecked(False)
        for card in self.provider_cards.values():
            card.setEnabled(not active)
        self.connect_button.setEnabled(ready and not connected and not active)
        self.disconnect_button.setEnabled(ready and connected and not active)
        self.refresh_button.setEnabled(ready and connected and not active)
        self.upload_button.setEnabled(ready and connected and not active)
        self.download_button.setEnabled(
            ready and connected and not active and
            self.items.currentItem() is not None)
        self._refresh_empty_state(connected)

    def _start(self, action, argument=None):
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = CloudBackupWorker(self._provider_id, action, argument, self)
        self._worker.finished.connect(lambda a=action: self._finished(a))
        self._worker.start()
        self._refresh_buttons()

    def _finished(self, action):
        worker = self._worker
        if worker is None:
            return
        failure, result = worker.failure, worker.result
        worker.deleteLater()
        self._worker = None
        self._refresh_buttons()
        if failure:
            QMessageBox.warning(self, "Backup em nuvem", failure)
            return
        if action == "connect":
            self._start("list")
        elif action == "list":
            self.items.clear()
            for backup in result:
                if not isinstance(backup, RemoteBackup):
                    continue
                size = f"{backup.size / (1024 * 1024):.1f} MiB"
                entry = QListWidgetItem(f"{backup.name}   ·   {size}")
                entry.setData(Qt.UserRole, backup.identifier)
                entry.setToolTip(backup.modified or backup.name)
                self.items.addItem(entry)
            self._list_loaded = True
            self._refresh_buttons()
        elif action == "upload":
            QMessageBox.information(self, "Backup enviado",
                                    "Cópia enviada com sucesso: " + result)
            self._list_loaded = False
            self._start("list")
        elif action == "download":
            if QMessageBox.question(
                    self, "Restaurar backup baixado",
                    "O backup foi baixado, validado e preservado em:\n"
                    + str(result) + "\n\nDeseja RESTAURAR os comandos agora? "
                    "O AURORA solicitará uma segunda confirmação e fará uma "
                    "cópia do estado atual antes da substituição.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) == QMessageBox.Yes:
                self.accept()
                QTimer.singleShot(0, lambda path=result: self.restore_callback(path))
        elif action == "disconnect":
            self.items.clear()
            self._list_loaded = False
            self._refresh_buttons()

    def _upload(self):
        if QMessageBox.question(
                self, "Enviar backup completo",
                "Enviar uma nova cópia dos seus comandos, pastas, formatação "
                "e preferências à conta selecionada? O ZIP não terá senha própria.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            # The SQLite connection is bound to the GUI thread.
            path = create_backup(self.store, reason="nuvem")
        except Exception as exc:
            QMessageBox.warning(self, "Backup local", str(exc))
            return
        self._start("upload", str(path))

    def _download(self):
        item = self.items.currentItem()
        if item is not None:
            self._start("download", item.data(Qt.UserRole))

    def _disconnect(self):
        if QMessageBox.question(
                self, "Desconectar conta",
                "Remover a autorização deste computador? Os backups na nuvem "
                "continuarão disponíveis na sua conta.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No) == QMessageBox.Yes:
            self._start("disconnect")

    def _cancel(self):
        if self._worker is not None and self._worker.action == "connect":
            self._worker.requestInterruption()
            self.status.setText("Cancelamento da autorização solicitado.")

    def reject(self):
        if self._worker is not None and self._worker.isRunning():
            self._cancel()
            QMessageBox.information(
                self, "Backup em nuvem",
                "A operação precisa terminar antes de fechar esta janela.")
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._cancel()
            event.ignore()
        else:
            super().closeEvent(event)
