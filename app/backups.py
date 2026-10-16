"""Whole-profile SQLite snapshots: every folder, shortcut, format and ordering."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import io
import json
import os
import sqlite3
import tempfile

from .core import application_db_path
from .preferences import preferences_path

BACKUP_SUFFIX = ".aurora-backup.zip"
MAX_DATABASE_BYTES = 100 * 1024 * 1024


def backups_directory() -> Path:
    return application_db_path().parent / "backups"


def create_backup(store, *, destination: Path | None = None, reason: str = "manual",
                  keep: int = 5) -> Path:
    """Create a consistent database snapshot using SQLite's backup API."""
    folder = backups_directory()
    folder.mkdir(parents=True, exist_ok=True)
    if destination is None:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = folder / f"aurora-{reason}-{timestamp}{BACKUP_SUFFIX}"
    else:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
    db_file = None
    tmp_zip = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".aurora-db-",
                                         suffix=".sqlite3", delete=False) as temp_db:
            db_file = Path(temp_db.name)
        with closing(sqlite3.connect(db_file)) as snapshot:
            store.connection.backup(snapshot)
            result = snapshot.execute("PRAGMA quick_check").fetchone()[0]
            if result != "ok":
                raise ValueError("O banco não passou na verificação de integridade.")
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".aurora-backup-",
                                         suffix=".zip", delete=False) as temp_zip:
            tmp_zip = Path(temp_zip.name)
        with ZipFile(tmp_zip, "w", compression=ZIP_DEFLATED) as archive:
            archive.write(db_file, "snippets.sqlite3")
            settings = preferences_path()
            if settings.is_file():
                archive.write(settings, "settings.json")
            archive.writestr("manifest.json", json.dumps({
                "format": "AURORA-AutoFill-Backup", "version": 1,
                "reason": reason, "created": datetime.now().isoformat(timespec="seconds"),
            }))
        os.replace(tmp_zip, destination)
        tmp_zip = None
        if destination.parent.resolve() == folder.resolve() and keep >= 1:
            backups = sorted(folder.glob(f"*{BACKUP_SUFFIX}"),
                             key=lambda f: f.stat().st_mtime, reverse=True)
            for old in backups[keep:]:
                old.unlink(missing_ok=True)
        return destination
    finally:
        if db_file is not None:
            db_file.unlink(missing_ok=True)
        if tmp_zip is not None:
            tmp_zip.unlink(missing_ok=True)


def read_backup(archive_path: Path) -> tuple[Path, dict | None]:
    """Validate archive content before touching the current database.

    Caller owns and must remove the returned temporary database file.
    """
    source_path = Path(archive_path)
    db_file = None
    try:
        with ZipFile(source_path) as archive:
            members = {item.filename: item for item in archive.infolist()}
            if not {"manifest.json", "snippets.sqlite3"}.issubset(members):
                raise ValueError("Este arquivo não é um backup completo do AURORA.")
            if members["snippets.sqlite3"].file_size > MAX_DATABASE_BYTES:
                raise ValueError("O backup ultrapassa o tamanho permitido.")
            manifest = json.loads(archive.read("manifest.json"))
            if manifest.get("format") != "AURORA-AutoFill-Backup" or manifest.get("version") != 1:
                raise ValueError("Formato de backup desconhecido.")
            settings = None
            if "settings.json" in members:
                if members["settings.json"].file_size > 8192:
                    raise ValueError("As configurações do backup são inválidas.")
                settings = json.loads(archive.read("settings.json"))
                if not isinstance(settings, dict):
                    raise ValueError("As configurações do backup são inválidas.")
            with tempfile.NamedTemporaryFile(dir=application_db_path().parent,
                                             prefix=".aurora-restore-", suffix=".sqlite3",
                                             delete=False) as handle:
                db_file = Path(handle.name)
                with archive.open("snippets.sqlite3") as content:
                    while data := content.read(65536):
                        handle.write(data)
        with closing(sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)) as source:
            if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("O banco de backup está danificado.")
            if source.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("O backup contém referências inválidas.")
            names = {row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"folders", "snippets"}.issubset(names):
                raise ValueError("O banco de backup não contém pastas e comandos.")
            columns = {row[1] for row in source.execute("PRAGMA table_info(snippets)")}
            if not {"id", "folder_id", "title", "shortcut", "content"}.issubset(columns):
                raise ValueError("Estrutura do backup inválida.")
        return db_file, settings
    except Exception:
        if db_file is not None:
            db_file.unlink(missing_ok=True)
        raise


def restore_backup(store, archive_path: Path) -> None:
    """Restore validated data transactionally; caller refreshes the UI after success."""
    file, settings = read_backup(archive_path)
    try:
        with closing(sqlite3.connect(file)) as source:
            source.backup(store.connection)
        # Settings are optional: importing old backups does not reset preferences.
        if settings is not None:
            from .preferences import save_preferences
            save_preferences(settings)
    finally:
        file.unlink(missing_ok=True)
