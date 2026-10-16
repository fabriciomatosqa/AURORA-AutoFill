"""Whole-profile SQLite snapshots: every folder, shortcut, format and ordering."""
from __future__ import annotations

from contextlib import closing
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import json
import os
import sqlite3
import tempfile

from .core import SnippetStore, application_db_path, validate_shortcut
from .preferences import normalize_preferences, preferences_path

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
        # Keep manual / emergency restoration backups indefinitely; rotate only
        # automatic pre-update snapshots, leaving the latest five.
        if reason == "pre-update" and destination.parent.resolve() == folder.resolve() and keep >= 1:
            backups = sorted(folder.glob(f"aurora-pre-update-*{BACKUP_SUFFIX}"),
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
            if len(members) != len(archive.infolist()):
                raise ValueError("O backup contém arquivos duplicados.")
            if not {"manifest.json", "snippets.sqlite3"}.issubset(members):
                raise ValueError("Este arquivo não é um backup completo do AURORA.")
            if members["snippets.sqlite3"].file_size > MAX_DATABASE_BYTES:
                raise ValueError("O backup ultrapassa o tamanho permitido.")
            if members["manifest.json"].file_size > 8192:
                raise ValueError("O manifesto do backup é inválido.")
            manifest = json.loads(archive.read("manifest.json"))
            if (not isinstance(manifest, dict)
                    or manifest.get("format") != "AURORA-AutoFill-Backup" or manifest.get("version") != 1):
                raise ValueError("Formato de backup desconhecido.")
            settings = None
            if "settings.json" in members:
                if members["settings.json"].file_size > 8192:
                    raise ValueError("As configurações do backup são inválidas.")
                settings = json.loads(archive.read("settings.json"))
                if not isinstance(settings, dict):
                    raise ValueError("As configurações do backup são inválidas.")
                settings = normalize_preferences(settings)
            application_db_path().parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=application_db_path().parent,
                                             prefix=".aurora-restore-", suffix=".sqlite3",
                                             delete=False) as handle:
                db_file = Path(handle.name)
                with archive.open("snippets.sqlite3") as content:
                    while data := content.read(65536):
                        handle.write(data)
        with closing(sqlite3.connect(db_file)) as source:
            if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("O banco de backup está danificado.")
            if source.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ValueError("O backup contém referências inválidas.")
            names = {row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"folders", "snippets"}.issubset(names):
                raise ValueError("O banco de backup não contém pastas e comandos.")
            columns = {row[1] for row in source.execute("PRAGMA table_info(snippets)")}
            folder_columns = {row[1] for row in source.execute("PRAGMA table_info(folders)")}
            if (not {"id", "name"}.issubset(folder_columns)
                    or not {"id", "folder_id", "title", "shortcut", "content",
                            "created_at", "updated_at"}.issubset(columns)):
                raise ValueError("Estrutura do backup inválida.")
            for table in ("folders", "snippets"):
                identity = next((row for row in source.execute(f"PRAGMA table_info({table})")
                                 if row[1] == "id"), None)
                if identity is None or identity[2].upper() != "INTEGER" or identity[5] != 1:
                    raise ValueError("Os identificadores do backup são inválidos.")
            for name, expected in (("rich_content", "text"), ("sort_order", "integer"),
                                   ("folder_id", "integer")):
                if name in columns and source.execute(
                        f"SELECT 1 FROM snippets WHERE typeof({name})<>? LIMIT 1",
                        (expected,)).fetchone():
                    raise ValueError("O backup contém formatação ou ordem inválida.")
            # Missing foreign-key declarations must not hide orphaned commands.
            if source.execute("SELECT 1 FROM snippets s LEFT JOIN folders f "
                              "ON f.id=s.folder_id WHERE f.id IS NULL LIMIT 1").fetchone():
                raise ValueError("O backup contém comandos sem pasta.")
            for (name,) in source.execute("SELECT name FROM folders"):
                if not isinstance(name, str) or not name.strip():
                    raise ValueError("O backup contém uma pasta inválida.")
            for title, shortcut, content in source.execute("SELECT title, shortcut, content FROM snippets"):
                if (not all(isinstance(value, str) for value in (title, shortcut, content))
                        or not title.strip() or not content.strip()):
                    raise ValueError("O backup contém um comando inválido.")
                validate_shortcut(shortcut)
            for table, column in (("folders", "name"), ("snippets", "shortcut")):
                if source.execute(f"SELECT 1 FROM {table} GROUP BY {column} COLLATE NOCASE "
                                  "HAVING COUNT(*) > 1 LIMIT 1").fetchone():
                    raise ValueError("O backup contém pastas ou atalhos duplicados.")
        # Upgrade only the temporary copy, before replacing any current data.
        migrated = SnippetStore(db_file)
        try:
            migrated.folders()
            migrated.snippets()
        finally:
            migrated.close()
        return db_file, settings
    except Exception:
        if db_file is not None:
            db_file.unlink(missing_ok=True)
        raise


def restore_backup(store, archive_path: Path) -> None:
    """Restore validated data transactionally; caller refreshes the UI after success."""
    file, settings = read_backup(archive_path)
    try:
        # Retain the current database until both data and preferences are saved.
        # SQLite backup replaces its destination atomically, but the settings
        # file is a separate resource and can fail (for example on a full disk).
        with closing(sqlite3.connect(":memory:")) as previous:
            store.connection.backup(previous)
            try:
                with closing(sqlite3.connect(file)) as source:
                    source.backup(store.connection)
                # Settings are optional: old backups do not reset preferences.
                if settings is not None:
                    from .preferences import save_preferences
                    save_preferences(settings)
            except Exception:
                previous.backup(store.connection)
                raise
    finally:
        file.unlink(missing_ok=True)
