"""Per-user preferences and Windows current-user startup (no admin privileges)."""
from __future__ import annotations

from pathlib import Path
import json
import os
import sys
import tempfile

from .core import application_db_path
from .version import IS_PRERELEASE

DEFAULTS = {
    "sound_enabled": True,
    "sound_volume": 65,
    "images_as_single_picture": False,
    "check_updates": True,
    "include_prereleases": IS_PRERELEASE,
    "start_minimized": False,
}
RUN_NAME = "AURORAAutoFill"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def preferences_path() -> Path:
    return application_db_path().parent / "settings.json"


def normalize_preferences(raw: dict) -> dict:
    """Use the same bounded, typed settings for files, imports and writes."""
    settings = dict(DEFAULTS)
    if isinstance(raw, dict):
        for key in ("sound_enabled", "check_updates", "include_prereleases", "start_minimized",
                    "images_as_single_picture"):
            if type(raw.get(key)) is bool:
                settings[key] = raw[key]
        volume = raw.get("sound_volume")
        if type(volume) is int:
            settings["sound_volume"] = max(0, min(100, volume))
    return settings


def load_preferences(path: Path | None = None) -> dict:
    target = Path(path) if path is not None else preferences_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return normalize_preferences(raw)
    except (OSError, ValueError, UnicodeError):
        return dict(DEFAULTS)


def save_preferences(settings: dict, path: Path | None = None) -> None:
    destination = Path(path) if path is not None else preferences_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    safe = normalize_preferences(settings)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=destination.parent,
                                         prefix=".aurora-settings-", suffix=".tmp",
                                         delete=False) as output:
            temporary = Path(output.name)
            json.dump(safe, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def windows_startup_supported() -> bool:
    return sys.platform == "win32" and bool(getattr(sys, "frozen", False))


def windows_startup_command(minimized: bool = False, executable: Path | None = None) -> str:
    """Quote the installed executable and add the tray-only startup option."""
    exe = Path(executable) if executable is not None else Path(sys.executable).resolve()
    return f'"{exe}"' + (" --minimized" if minimized else "")


def windows_startup_enabled() -> bool:
    if not windows_startup_supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            command, _ = winreg.QueryValueEx(key, RUN_NAME)
            return (isinstance(command, str) and command.strip().casefold() in {
                windows_startup_command(False).casefold(),
                windows_startup_command(True).casefold(),
            })
    except OSError:
        return False


def set_windows_startup(enabled: bool, *, minimized: bool = False) -> None:
    if not windows_startup_supported():
        raise OSError("A inicialização automática está disponível somente no aplicativo instalado no Windows.")
    import winreg
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ,
                              windows_startup_command(minimized))
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass
