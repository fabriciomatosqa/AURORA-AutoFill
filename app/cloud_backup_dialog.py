"""Tela opcional de backup em nuvem, sem alterações no editor ou motor."""
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QVBoxLayout,
)

from .backups import create_backup
from .cloud_backups import CloudBackupClient, CloudBackupError, RemoteBackup
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
            # Do not show provider JSON, tokens, or OAuth callback parameters.
            self.failure = str(exc) if isinstance(exc, CloudBackupError) else (
                "Não foi possível concluir a operação de backup na nuvem.")


class CloudBackupDialog(QDialog):
    def __init__(self, store, restore_callback, parent=None):
        super().__init__(parent)
        self.store = store
        self.restore_callback = restore_callback
        self._worker = None
        self.setWindowTitle("Backup em nuvem — AURORA AutoFill")
        self.setMinimumSize(560, 440)
        set_ui_style(self, """
            QDialog { background: #0a1b2e; color: #edf8ff; }
            QLabel { color: #d2e9f8; }
            QComboBox, QListWidget {
                background: #132d43; color: #eaf4ff;
                border: 1px solid #3c627a; border-radius: 6px;
                padding: 6px;
            }
            QPushButton {
                background: #194058; color: #f0ffff;
                border: 1px solid #44828e; border-radius: 6px;
                padding: 8px;
            }
            QPushButton:disabled { color: #7c929e; border-color: #29495d; }
        """)
        root = QVBoxLayout(self)
        title = QLabel("Proteja seus comandos em uma conta de nuvem")
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        root.addWidget(title)
        note = QLabel(
            "Somente cópias completas são enviadas. Seus comandos continuam "
            "no computador e a restauração nunca é automática. "
            "Os arquivos são protegidos pelo serviço de nuvem, mas esta "
            "versão não aplica criptografia de ponta a ponta ao ZIP.")
        note.setWordWrap(True)
        root.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel("Provedor:"))
        self.provider = QComboBox()
        self.provider.addItem("Google Drive — pasta oculta do aplicativo", "google")
        self.provider.addItem("Microsoft OneDrive — pasta Apps do aplicativo", "onedrive")
        self.provider.currentIndexChanged.connect(self._provider_changed)
        row.addWidget(self.provider, 1)
        root.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        first = QHBoxLayout()
        self.connect_button = QPushButton("Conectar conta")
        self.connect_button.clicked.connect(lambda: self._start("connect"))
        self.disconnect_button = QPushButton("Desconectar")
        self.disconnect_button.clicked.connect(self._disconnect)
        self.refresh_button = QPushButton("Atualizar lista")
        self.refresh_button.clicked.connect(lambda: self._start("list"))
        for b in (self.connect_button, self.disconnect_button, self.refresh_button):
            first.addWidget(b)
        root.addLayout(first)
        root.addWidget(QLabel("Backups disponíveis nesta conta:"))
        self.items = QListWidget()
        self.items.itemSelectionChanged.connect(self._refresh_buttons)
        root.addWidget(self.items, 1)
        actions = QHBoxLayout()
        self.upload_button = QPushButton("Enviar backup completo")
        self.upload_button.clicked.connect(self._upload)
        self.download_button = QPushButton("Baixar / restaurar")
        self.download_button.clicked.connect(self._download)
        self.cancel_button = QPushButton("Cancelar autorização")
        self.cancel_button.clicked.connect(self._cancel)
        for button in (self.upload_button, self.download_button, self.cancel_button):
            actions.addWidget(button)
        root.addLayout(actions)
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        root.addWidget(close, 0, Qt.AlignRight)
        self._refresh_buttons()

    def _client(self):
        return CloudBackupClient(self.provider.currentData())

    def _provider_changed(self):
        self.items.clear()
        self._refresh_buttons()

    def _refresh_buttons(self):
        active = self._worker is not None and self._worker.isRunning()
        self.cancel_button.setEnabled(active and self._worker.action == "connect")
        try:
            connected = self._client().connected()
            message = ("Conta conectada neste dispositivo." if connected
                       else "Nenhuma conta conectada. Autorize no navegador para usar o backup.")
            ready = True
        except CloudBackupError as exc:
            connected, ready, message = False, False, str(exc)
        self.status.setText(message if not active else "Operação em andamento…")
        self.provider.setEnabled(not active)
        self.connect_button.setEnabled(ready and not connected and not active)
        self.disconnect_button.setEnabled(ready and connected and not active)
        self.refresh_button.setEnabled(ready and connected and not active)
        self.upload_button.setEnabled(ready and connected and not active)
        self.download_button.setEnabled(ready and connected and not active
                                        and self.items.currentItem() is not None)

    def _start(self, action, argument=None):
        if self._worker is not None and self._worker.isRunning():
            return
        provider = self.provider.currentData()
        self._worker = CloudBackupWorker(provider, action, argument, self)
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
                self.items.addItem(entry)
            self._refresh_buttons()
        elif action == "upload":
            QMessageBox.information(self, "Backup enviado",
                                    "Cópia enviada com sucesso: " + result)
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
            # The current store's SQLite connection is bound to the GUI thread.
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
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self._start("disconnect")

    def _cancel(self):
        if self._worker is not None and self._worker.action == "connect":
            self._worker.requestInterruption()
            self.status.setText("Cancelamento da autorização solicitado.")

    def reject(self):
        if self._worker is not None and self._worker.isRunning():
            self._cancel()
            QMessageBox.information(self, "Backup em nuvem",
                                    "A operação precisa terminar antes de fechar esta janela.")
            return
        super().reject()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            self._cancel()
            event.ignore()
        else:
            super().closeEvent(event)
