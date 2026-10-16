"""Prevent duplicate global keyboard listeners for the same user profile."""
from pathlib import Path

from PySide6.QtCore import QLockFile


def acquire_instance_lock(directory: Path) -> QLockFile | None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(directory / "aurora-instance.lock"))
    # This lock lives for the entire process. Recover a dead PID, but never
    # consider a healthy process stale merely because it has been open a while.
    lock.setStaleLockTime(0)
    if lock.tryLock(0):
        return lock
    if lock.error() == QLockFile.LockError.LockFailedError:
        return None
    raise OSError("Não foi possível acessar a pasta de dados do AURORA.")
