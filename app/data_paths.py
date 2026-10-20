"""Diretório único de dados locais do AURORA AutoFill.

O aplicativo não lê, move ou exclui pastas de versões anteriores.
"""
from __future__ import annotations

from pathlib import Path
import os
import sys


DATA_DIRECTORY = "AuroraAutoFill"


def _profile_root() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))


def application_data_dir() -> Path:
    """Cria e retorna somente o diretório oficial, sem qualquer migração."""
    directory = _profile_root() / DATA_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def application_db_path() -> Path:
    return application_data_dir() / "snippets.sqlite3"
