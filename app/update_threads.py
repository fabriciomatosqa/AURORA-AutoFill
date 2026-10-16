"""Qt threads for GitHub Release checking and verified installer downloads."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from .updates import latest_release, download_verified_installer


class ReleaseCheckThread(QThread):
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, parent=None, *, include_prereleases=True):
        super().__init__(parent)
        self.include_prereleases = include_prereleases

    def run(self):
        try:
            release = latest_release(include_prereleases=self.include_prereleases)
            if not self.isInterruptionRequested():
                self.result.emit(release)
        except Exception as error:
            if not self.isInterruptionRequested():
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
        self.requestInterruption()

    def _cancelled(self):
        return self._cancel_requested or self.isInterruptionRequested()

    def _progress(self, percentage):
        if self._cancelled():
            raise ValueError("Download cancelado.")
        self.progress_changed.emit(percentage)

    def run(self):
        try:
            if self._cancelled():
                raise ValueError("Download cancelado.")
            destination = download_verified_installer(
                self.release, progress=self._progress, cancelled=self._cancelled)
            if not self._cancelled():
                self.ready.emit(destination)
        except Exception as error:
            self.failed.emit(str(error))
