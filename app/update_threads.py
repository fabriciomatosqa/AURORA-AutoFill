"""Qt threads for GitHub Release checking and verified installer downloads."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .updates import latest_release, download_verified_installer


class ReleaseCheckThread(QThread):
    result = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.result.emit(latest_release())
        except Exception as error:
            self.failed.emit(str(error))


class InstallerDownloadThread(QThread):
    progress_changed = Signal(int)
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, release, parent=None):
        super().__init__(parent)
        self.release = release
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def _progress(self, percentage):
        if self._cancel_requested:
            raise ValueError("Download cancelado.")
        self.progress_changed.emit(percentage)

    def run(self):
        try:
            if self._cancel_requested:
                raise ValueError("Download cancelado.")
            destination = download_verified_installer(self.release, progress=self._progress)
            self.ready.emit(destination)
        except Exception as error:
            self.failed.emit(str(error))
