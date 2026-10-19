"""Presentation actions for Aurora settings, backups, undo and consensual updates."""
from __future__ import annotations

from pathlib import Path
from time import monotonic
import os
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
from .updates import is_newer, launch_installer
from .version import APP_VERSION
from .versioning import display_version
from .icons import apply_icon


def confirm_update(parent, text):
    dialog = QMessageBox(QMessageBox.Information, "Atualizar o AURORA", text,
                         QMessageBox.NoButton, parent)
    update = dialog.addButton("Atualizar agora", QMessageBox.AcceptRole)
    later = dialog.addButton("Agora não", QMessageBox.RejectRole)
    dialog.setDefaultButton(later)
    dialog.setEscapeButton(later)
    dialog.exec()
    return dialog.clickedButton() == update


class AuroraFeaturesMixin:
    def _initialize_features(self):
        self.preferences = load_preferences()
        self._undo_actions = []
        self._next_undo_id = 0
        self._check_thread = None
        self._download_thread = None
        self._download_cancelled = False
        self._download_progress = None
        self._download_release = None
        self._exit_when_updates_done = False

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
        self.settings_page.prereleases_toggled.connect(
            lambda checked: self._change_preference("include_prereleases", checked))
        self.settings_page.startup_toggled.connect(self._change_startup)
        self.settings_page.start_minimized_toggled.connect(self._change_start_minimized)
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
            widget = {"sound_enabled": self.settings_page.sound,
                      "sound_volume": self.settings_page.volume,
                      "check_updates": self.settings_page.updates,
                      "include_prereleases": self.settings_page.prereleases,
                      "start_minimized": self.settings_page.start_minimized}.get(key)
            if widget is not None:
                widget.blockSignals(True)
                if key == "sound_volume":
                    widget.setValue(previous)
                else:
                    widget.setChecked(previous)
                widget.blockSignals(False)
            self._sync_audio_controls()
            QMessageBox.warning(self, "Configurações", f"Não foi possível salvar: {exc}")

    def _sync_audio_controls(self):
        enabled = self.preferences["sound_enabled"]
        self.settings_page.volume.setEnabled(enabled)
        self.settings_page.sample_button.setEnabled(enabled)
        self.settings_page.volume_label.setEnabled(enabled)
        self.settings_page.volume_label.setText(f"{self.preferences['sound_volume']}%")

    def _change_startup(self, enabled):
        try:
            set_windows_startup(
                enabled, minimized=self.preferences.get("start_minimized", False))
        except OSError as exc:
            self.settings_page.startup.blockSignals(True)
            current = windows_startup_enabled()
            self.settings_page.startup.setChecked(current)
            self.settings_page.startup.blockSignals(False)
            self.settings_page.start_minimized.setEnabled(current)
            QMessageBox.warning(self, "Inicialização automática", str(exc))

    def _change_start_minimized(self, enabled):
        previous = self.preferences.get("start_minimized", False)
        try:
            # Only the Windows login launch receives --minimized. Manual
            # launches still open the application window normally.
            if windows_startup_enabled():
                set_windows_startup(True, minimized=enabled)
            self.preferences["start_minimized"] = enabled
            save_preferences(self.preferences)
        except OSError as exc:
            self.preferences["start_minimized"] = previous
            if windows_startup_enabled():
                try:
                    set_windows_startup(True, minimized=previous)
                except OSError:
                    pass
            self.settings_page.start_minimized.blockSignals(True)
            self.settings_page.start_minimized.setChecked(previous)
            self.settings_page.start_minimized.blockSignals(False)
            QMessageBox.warning(self, "Iniciar minimizado", str(exc))

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
        try:
            folder = backups_directory()
            folder.mkdir(parents=True, exist_ok=True)
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))):
                raise OSError(f"Abra a pasta de backups em: {folder}")
        except OSError as exc:
            QMessageBox.warning(self, "Backups", str(exc))

    def _restore_user_backup(self):
        if not self._confirm_change():
            return
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
            self._undo_actions.clear()
            self._render_undo()
            self.current_id = None
            self.dirty = False
            self.preferences = load_preferences()
            for widget, setting in ((self.settings_page.sound, "sound_enabled"),
                                    (self.settings_page.updates, "check_updates"),
                                    (self.settings_page.prereleases, "include_prereleases"),
                                    (self.settings_page.start_minimized, "start_minimized")):
                widget.blockSignals(True)
                widget.setChecked(self.preferences[setting])
                widget.blockSignals(False)
            self.settings_page.volume.blockSignals(True)
            self.settings_page.volume.setValue(self.preferences["sound_volume"])
            self.settings_page.volume.blockSignals(False)
            self._sync_audio_controls()
            if windows_startup_enabled():
                # A restored startup preference should match the Run command
                # for the next Windows sign-in.
                set_windows_startup(
                    True, minimized=self.preferences.get("start_minimized", False))
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
        self.undo_button = apply_icon(QPushButton("Desfazer"), "undo")
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
        entry = self._undo_actions[-1]
        try:
            if entry["kind"] == "snippet":
                self.store.restore_deleted_snippet(entry["snapshot"])
            else:
                self.store.restore_deleted_folder(entry["snapshot"])
            self._undo_actions.pop()
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
        if (self._check_thread is not None or self._download_thread is not None
                or self._exit_when_updates_done):
            return
        self.settings_page.check_button.setEnabled(False)
        include_tests = self.preferences["include_prereleases"]
        label = ("Consultando atualizações, incluindo versões de teste..." if include_tests
                 else "Consultando versões estáveis no GitHub...")
        self.statusBar().showMessage(label, 4000)
        thread = ReleaseCheckThread(self, include_prereleases=include_tests)
        self._check_thread = thread
        thread.result.connect(lambda release: self._handle_release(release, manual))
        thread.failed.connect(lambda detail: self._update_error(detail, manual))
        thread.finished.connect(self._release_check_done)
        thread.start()

    def _release_check_done(self):
        old, self._check_thread = self._check_thread, None
        self.settings_page.check_button.setEnabled(
            self._download_thread is None and not self._exit_when_updates_done)
        if old is not None:
            old.deleteLater()
        self._finish_updates_shutdown()

    def _update_error(self, detail, manual):
        if self._exit_when_updates_done:
            return
        if manual:
            QMessageBox.warning(self, "Atualizações",
                                f"Não foi possível consultar o GitHub: {detail}")
        else:
            self.statusBar().showMessage("Não foi possível verificar atualizações.", 3000)

    def _handle_release(self, release, manual):
        if self._exit_when_updates_done or self._download_thread is not None:
            return
        if release is None:
            if manual:
                QMessageBox.information(self, "Atualizações",
                                        "Ainda não há instaladores publicados para este sistema e canal no GitHub.")
            return
        if not is_newer(release.version, APP_VERSION):
            if manual:
                QMessageBox.information(self, "Atualizações",
                                        f"O AURORA v{APP_VERSION} já está atualizado.")
            return
        channel = " de teste" if getattr(release, "prerelease", False) else ""
        text = (f"Nova versão{channel} disponível: v{display_version(release.version)}\n"
                f"Versão instalada: v{APP_VERSION}\n\n")
        if not getattr(sys, "frozen", False):
            text += "Deseja abrir a página oficial para baixar a atualização?"
            if QMessageBox.question(self, "Nova versão AURORA", text,
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes:
                webbrowser.open(release.page_url)
            return
        # WiX MSI is a separate installation channel from Inno Setup.
        # Never replace an MSI installation with the EXE auto-updater: show
        # the official release so the user can install the next MSI instead.
        if (sys.platform == "win32" and getattr(sys, "frozen", False)
                and (Path(sys.executable).resolve().parent / "AURORA-MSI-CHANNEL.txt").is_file()):
            text += ("Esta instalação usa o formato MSI. Para manter o mesmo tipo "
                     "de instalador, baixe o novo arquivo .msi na página oficial. "
                     "Deseja abrir a página da versão?")
            if QMessageBox.question(self, "Nova versão AURORA (MSI)", text,
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes:
                webbrowser.open(release.page_url)
            return
        if not (release.installer_url and release.checksum_url):
            if manual:
                QMessageBox.information(self, "Atualizações",
                                        "O lançamento ainda não possui instalador compatível e checksum.")
            return
        if getattr(release, "installer_kind", "exe") == "deb":
            text += ("O AURORA fará um backup e abrirá a atualização no gerenciador de pacotes. "
                     "O Linux poderá solicitar sua confirmação ou senha.")
        else:
            text += ("O AURORA fará um backup, instalará a atualização em segundo plano "
                     "e reabrirá automaticamente. Você pode cancelar durante o download.")
        if confirm_update(self, text):
            self._download_update(release)

    def _download_update(self, release):
        if self._download_thread is not None or self._exit_when_updates_done:
            return
        self._download_release = release
        self._download_cancelled = False
        self.settings_page.check_button.setEnabled(False)
        thread = InstallerDownloadThread(release, self)
        self._download_thread = thread
        progress = QProgressDialog("Baixando atualização oficial...", "Cancelar", 0, 100, self)
        progress.setWindowTitle("Atualização do AURORA")
        progress.setWindowModality(Qt.NonModal)
        progress.setMinimumDuration(0)
        progress.canceled.connect(self._cancel_update_download)
        self._download_progress = progress
        thread.progress_changed.connect(progress.setValue)
        thread.ready.connect(self._installer_ready)
        thread.failed.connect(self._installer_failed)
        thread.finished.connect(self._download_done)
        progress.show()
        thread.start()

    def _cancel_update_download(self):
        self._download_cancelled = True
        if self._download_thread is not None:
            self._download_thread.request_cancel()

    def _download_done(self):
        if self._download_progress is not None:
            self._download_progress.blockSignals(True)
            self._download_progress.close()
            self._download_progress = None
        old, self._download_thread = self._download_thread, None
        self.settings_page.check_button.setEnabled(
            self._check_thread is None and not self._exit_when_updates_done)
        if old is not None:
            old.deleteLater()
        self._download_release = None
        self._finish_updates_shutdown()

    def _installer_failed(self, error):
        if error != "Download cancelado." and not self._exit_when_updates_done:
            QMessageBox.warning(self, "Atualização", error)

    def _prepare_updates_shutdown(self):
        """Keep QThreads alive until their bounded network operations finish."""
        if self._check_thread is None and self._download_thread is None:
            self._exit_when_updates_done = False
            return True
        self._exit_when_updates_done = True
        self._quitting = False
        if self._check_thread is not None:
            self._check_thread.requestInterruption()
        if self._download_thread is not None:
            self._download_thread.request_cancel()
        self.statusBar().showMessage("Finalizando a consulta ou cancelando o download para sair...")
        return False

    def _finish_updates_shutdown(self):
        if (self._exit_when_updates_done and self._check_thread is None
                and self._download_thread is None):
            QTimer.singleShot(0, self._exit_application)

    def _installer_ready(self, installer: Path):
        if self._exit_when_updates_done or self._download_cancelled:
            return
        release = self._download_release
        if release is None:
            QMessageBox.warning(self, "Atualização", "A origem deste instalador não está disponível. Baixe novamente.")
            return
        if not self._confirm_change():
            return
        try:
            archived = create_backup(self.store, reason="pre-update")
            launch_installer(installer, release)
        except Exception as exc:
            QMessageBox.warning(self, "Atualização não iniciada",
                                f"{exc}\nVerifique seus backups antes de tentar novamente.")
            return
        self.statusBar().showMessage(f"Backup criado em: {archived}", 1500)
        self.dirty = False
        self._exit_application()
