"""Presentation actions for Aurora settings, backups, undo and consensual updates."""
from __future__ import annotations

from pathlib import Path
from time import monotonic
import os
import subprocess
import sys
import webbrowser

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QProgressDialog, QPushButton, QWidget)

from . import audio
from .backups import BACKUP_SUFFIX, backups_directory, create_backup, restore_backup
from .preferences import (load_preferences, save_preferences, set_windows_startup,
                          windows_startup_enabled, windows_startup_supported)
from .settings_panel import SettingsPage
from .update_threads import ReleaseCheckThread, InstallerDownloadThread
from .updates import is_newer
from .version import APP_VERSION, GITHUB_RELEASES_URL


class AuroraFeaturesMixin:
    def _initialize_features(self):
        self.preferences = load_preferences()
        self._undo_actions = []
        self._next_undo_id = 0
        self._check_thread = None
        self._download_thread = None
        self._download_progress = None

    def _build_features_page(self):
        self.settings_page = SettingsPage(
            self.preferences, startup_supported=windows_startup_supported(),
            startup_enabled=windows_startup_enabled())
        self.settings_page.sound_toggled.connect(
            lambda checked: self._change_preference("sound_enabled", checked))
        self.settings_page.volume_changed.connect(
            lambda value: self._change_preference("sound_volume", value))
        self.settings_page.updates_toggled.connect(
            lambda checked: self._change_preference("check_updates", checked))
        self.settings_page.startup_toggled.connect(self._change_startup)
        self.settings_page.play_requested.connect(self._play_confirmation)
        self.settings_page.backup_requested.connect(self._create_manual_backup)
        self.settings_page.restore_requested.connect(self._restore_user_backup)
        self.settings_page.open_backups_requested.connect(self._open_backups)
        self.settings_page.check_requested.connect(
            lambda: self._check_updates(manual=True))
        self.settings_page.close_requested.connect(self._show_welcome)
        self.stack.addWidget(self.settings_page)

    def _show_settings(self):
        if not self._confirm_change():
            return
        self.stack.setCurrentWidget(self.settings_page)

    def _change_preference(self, key, value):
        previous = self.preferences.get(key)
        self.preferences[key] = value
        try:
            save_preferences(self.preferences)
        except OSError as exc:
            self.preferences[key] = previous
            QMessageBox.warning(self, "Configurações", f"Não foi possível salvar: {exc}")

    def _change_startup(self, enabled):
        try:
            set_windows_startup(enabled)
        except OSError as exc:
            self.settings_page.startup.blockSignals(True)
            self.settings_page.startup.setChecked(windows_startup_enabled())
            self.settings_page.startup.blockSignals(False)
            QMessageBox.warning(self, "Inicialização automática", str(exc))

    def _play_feedback(self):
        sound_file = Path(__file__).resolve().parent.parent / "assets" / "command_click.wav"
        try:
            audio.play_feedback(sound_file,
                                enabled=self.preferences["sound_enabled"],
                                volume=self.preferences["sound_volume"])
        except Exception as exc:
            self.statusBar().showMessage(f"Som indisponível: {exc}", 3500)

    def _create_manual_backup(self):
        try:
            archive = create_backup(self.store, reason="manual")
            QMessageBox.information(
                self, "Backup concluído",
                f"Todas as pastas e comandos foram salvos em:\n{archive}")
        except Exception as exc:
            QMessageBox.warning(self, "Backup", str(exc))

    def _open_backups(self):
        folder = backups_directory()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        else:
            subprocess.Popen(["xdg-open", str(folder)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)

    def _restore_user_backup(self):
        selected, _ = QFileDialog.getOpenFileName(
            self, "Restaurar backup completo", str(backups_directory()),
            f"Backup AURORA (*{BACKUP_SUFFIX})")
        if not selected:
            return
        if QMessageBox.question(
                self, "Restaurar backup",
                "Os comandos atuais serão substituídos pelos do backup selecionado.\n"
                "Uma cópia de segurança será criada antes da restauração. Continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            safety = create_backup(self.store, reason="antes-restauracao")
            if hasattr(self, "hotkeys"):
                self.hotkeys.invalidate()
            restore_backup(self.store, Path(selected))
            from .core import SnippetStore, application_db_path
            self.store.close()
            self.store = SnippetStore(application_db_path())
            self.preferences = load_preferences()
            for widget, setting in ((self.settings_page.sound, "sound_enabled"),
                                    (self.settings_page.updates, "check_updates")):
                widget.blockSignals(True)
                widget.setChecked(self.preferences[setting])
                widget.blockSignals(False)
            self.settings_page.volume.blockSignals(True)
            self.settings_page.volume.setValue(self.preferences["sound_volume"])
            self.settings_page.volume.blockSignals(False)
            self._refresh_all()
            self.dirty = False
            self._show_welcome()
            self.statusBar().showMessage("Backup restaurado com sucesso.", 5000)
            QMessageBox.information(self, "Restauração concluída",
                                    f"Pastas e comandos restaurados.\nCópia anterior: {safety}")
        except Exception as exc:
            # The safety backup remains on disk; never discard it on errors.
            QMessageBox.warning(self, "Restauração não concluída",
                                f"{exc}\nSeu backup de segurança foi mantido.")

    def _setup_undo_ui(self):
        bar = QWidget(self)
        line = QHBoxLayout(bar)
        line.setContentsMargins(5, 0, 6, 0)
        line.setSpacing(7)
        self.undo_label = QLabel()
        self.undo_label.setStyleSheet("color: #9aefda;")
        line.addWidget(self.undo_label)
        self.undo_button = QPushButton("Desfazer")
        self.undo_button.setObjectName("primary")
        self.undo_button.setFixedHeight(27)
        self.undo_button.clicked.connect(self._undo_last)
        line.addWidget(self.undo_button)
        self.statusBar().addWidget(bar, 1)
        self.undo_bar = bar
        self._undo_tick = QTimer(self)
        self._undo_tick.setInterval(1000)
        self._undo_tick.timeout.connect(self._render_undo)
        bar.hide()

    def _offer_undo(self, kind: str, snapshot: dict, label: str):
        self._next_undo_id += 1
        identifier = self._next_undo_id
        self._undo_actions.append({
            "id": identifier, "kind": kind, "snapshot": snapshot,
            "label": label, "expires": monotonic() + 10.0,
        })
        QTimer.singleShot(10000, lambda undo_id=identifier: self._expire_undo(undo_id))
        self._render_undo()

    def _expire_undo(self, identifier):
        self._undo_actions = [entry for entry in self._undo_actions if entry["id"] != identifier]
        self._render_undo()

    def _render_undo(self):
        self._undo_actions = [entry for entry in self._undo_actions
                              if entry["expires"] > monotonic()]
        if self._undo_actions:
            last = self._undo_actions[-1]
            remaining = max(1, round(last["expires"] - monotonic()))
            self.undo_label.setText(f"{last['label']} · {remaining}s")
            self.undo_bar.show()
            if not self._undo_tick.isActive():
                self._undo_tick.start()
        else:
            self._undo_tick.stop()
            self.undo_bar.hide()

    def _undo_last(self):
        self._undo_actions = [entry for entry in self._undo_actions
                              if entry["expires"] > monotonic()]
        if not self._undo_actions:
            self._render_undo()
            return
        entry = self._undo_actions.pop()
        try:
            if entry["kind"] == "snippet":
                self.store.restore_deleted_snippet(entry["snapshot"])
            else:
                self.store.restore_deleted_folder(entry["snapshot"])
            self._refresh_all()
            self.statusBar().showMessage("Exclusão desfeita!", 4000)
        except Exception as exc:
            QMessageBox.warning(self, "Não foi possível desfazer",
                                f"{exc}\nUse um backup caso precise recuperar os dados.")
        self._render_undo()

    def _initial_release_check(self):
        if os.environ.get("AURORA_AUTOFILL_SMOKE_TEST") != "1" and self.preferences["check_updates"]:
            self._check_updates(manual=False)

    def _check_updates(self, *, manual: bool):
        if self._check_thread is not None:
            return
        self.settings_page.check_button.setEnabled(False)
        self.statusBar().showMessage("Consultando versões estáveis no GitHub...", 4000)
        thread = ReleaseCheckThread(self)
        self._check_thread = thread
        thread.result.connect(lambda release: self._handle_release(release, manual))
        thread.failed.connect(lambda detail: self._update_error(detail, manual))
        thread.finished.connect(self._release_check_done)
        thread.start()

    def _release_check_done(self):
        self.settings_page.check_button.setEnabled(True)
        old, self._check_thread = self._check_thread, None
        if old is not None:
            old.deleteLater()

    def _update_error(self, detail, manual):
        if manual:
            QMessageBox.warning(self, "Atualizações",
                                f"Não foi possível consultar o GitHub: {detail}")
        else:
            self.statusBar().showMessage("Não foi possível verificar atualizações.", 3000)

    def _handle_release(self, release, manual):
        if release is None:
            if manual:
                QMessageBox.information(self, "Atualizações",
                                        "Ainda não há lançamentos estáveis publicados no GitHub.")
            return
        if not is_newer(release.version, APP_VERSION):
            if manual:
                QMessageBox.information(self, "Atualizações",
                                        f"O AURORA v{APP_VERSION} já está atualizado.")
            return
        text = (f"Nova versão estável disponível: v{release.version}\n"
                f"Versão instalada: v{APP_VERSION}\n\n")
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            text += "Deseja abrir a página oficial para baixar a atualização?"
            if QMessageBox.question(self, "Nova versão AURORA", text,
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes:
                webbrowser.open(release.page_url)
            return
        if not (release.installer_url and release.checksum_url):
            if manual:
                QMessageBox.information(self, "Atualizações",
                                        "O lançamento ainda não possui instalador e checksum Windows.")
            return
        text += "Deseja baixar o instalador oficial verificado por SHA256?"
        if QMessageBox.question(self, "Atualização disponível", text,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) == QMessageBox.Yes:
            self._download_update(release)

    def _download_update(self, release):
        if self._download_thread is not None:
            return
        thread = InstallerDownloadThread(release, self)
        self._download_thread = thread
        progress = QProgressDialog("Baixando atualização oficial...", "Cancelar", 0, 100, self)
        progress.setWindowTitle("Atualização do AURORA")
        progress.setWindowModality(Qt.NonModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(thread.request_cancel)
        self._download_progress = progress
        thread.progress_changed.connect(progress.setValue)
        thread.ready.connect(self._installer_ready)
        thread.failed.connect(self._installer_failed)
        thread.finished.connect(self._download_done)
        progress.show()
        thread.start()

    def _download_done(self):
        if self._download_progress is not None:
            self._download_progress.close()
            self._download_progress = None
        old, self._download_thread = self._download_thread, None
        if old is not None:
            old.deleteLater()

    def _installer_failed(self, error):
        if error != "Download cancelado.":
            QMessageBox.warning(self, "Atualização", error)

    def _installer_ready(self, installer: Path):
        if not self._confirm_change():
            return
        if QMessageBox.question(
                self, "Instalar atualização",
                "O instalador foi baixado e validado por SHA256.\n"
                "O AURORA será fechado para atualizar. Criar backup e continuar?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            archived = create_backup(self.store, reason="pre-update")
            subprocess.Popen([str(installer)], close_fds=True)
        except Exception as exc:
            QMessageBox.warning(self, "Atualização não iniciada",
                                f"{exc}\nVerifique seus backups antes de tentar novamente.")
            return
        self.statusBar().showMessage(f"Backup criado em: {archived}", 1500)
        self._exit_application()
