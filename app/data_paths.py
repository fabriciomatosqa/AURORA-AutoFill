"""Pasta de dados AURORA com migração conservadora do nome antigo."""
from __future__ import annotations

from pathlib import Path
import os
import sys


DATA_DIRECTORY = "AuroraAutoFill"
LEGACY_DIRECTORY = "AutoFillStudio"


def _profile_root() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))


def application_data_dir() -> Path:
    """Preserva o perfil completo sem sobrescrever dados de outros perfis.

    Se apenas o diretório antigo existir, renomeia a pasta inteira no mesmo
    volume, mantendo SQLite, WAL, configurações, backups e subpastas.
    Se ambos existirem, dá preferência à pasta nova e não apaga a antiga.
    Falhas de migração interrompem a abertura em vez de criar um perfil vazio.
    """
    root = _profile_root()
    destination = root / DATA_DIRECTORY
    legacy = root / LEGACY_DIRECTORY
    if destination.exists():
        if not destination.is_dir():
            raise OSError(f"O caminho de dados do AURORA não é uma pasta: {destination}")
        return destination
    if legacy.exists() or legacy.is_symlink():
        if not legacy.is_dir() or legacy.is_symlink():
            raise OSError(f"A pasta antiga do AURORA não pôde ser migrada: {legacy}")
        try:
            legacy.rename(destination)
        except FileExistsError:
            if not destination.is_dir():
                raise OSError("Conflito na criação da pasta de dados AURORA.")
        except OSError as exc:
            raise OSError(
                f"Não foi possível migrar {legacy} para {destination}. "
                "Feche outras cópias do AutoFill e confira as permissões. "
                "Os dados originais foram preservados."
            ) from exc
    return destination


def application_db_path() -> Path:
    return application_data_dir() / "snippets.sqlite3"
