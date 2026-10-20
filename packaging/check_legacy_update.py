"""Verify migration with the updater shipped in v0.6.1-dev.22.1.

The legacy code is read from an immutable Git commit and loaded in an isolated
package. This checks what the installed app can discover and download, without
executing an installer or substituting the new updater's version comparison.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from types import ModuleType
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from github_api_auth import authenticate_release_metadata

LEGACY_COMMIT = "583ff467efc40c2b6ebfe1fcfa2b7ce216c60730"
LEGACY_VERSION = "0.6.1-dev.22.1"
REPOSITORY = "fabriciomatosqa/AURORA-AutoFill"


def _read_legacy_source(legacy_ref: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{40}", legacy_ref):
        raise ValueError("A referência do atualizador antigo deve ser um commit SHA completo.")
    try:
        result = subprocess.run(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", "show",
             f"{legacy_ref}:app/updates.py"], cwd=ROOT, check=True,
            capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(
            "Não foi possível carregar o atualizador antigo. "
            "O checkout deve conter o histórico do commit de origem.") from exc
    return result.stdout


def load_legacy_updater(legacy_ref: str = LEGACY_COMMIT):
    source = _read_legacy_source(legacy_ref)
    package_name = "_aurora_legacy_" + uuid.uuid4().hex
    package = ModuleType(package_name)
    package.__path__ = []
    version = ModuleType(package_name + ".version")
    version.APP_VERSION = LEGACY_VERSION
    version.GITHUB_REPOSITORY = REPOSITORY
    version.GITHUB_RELEASES_API = f"https://api.github.com/repos/{REPOSITORY}/releases"
    updater = ModuleType(package_name + ".updates")
    updater.__package__ = package_name
    updater.__file__ = f"git:{legacy_ref}:app/updates.py"
    modules = {package_name: package, version.__name__: version,
               updater.__name__: updater}
    # dataclass resolves its module while the class is being created. Keep the
    # private package registered during exec, then leave the app's imports intact.
    sys.modules.update(modules)
    try:
        exec(compile(source, updater.__file__, "exec"), updater.__dict__)
    finally:
        for name in modules:
            sys.modules.pop(name, None)
    return updater


def verify_legacy_update(version: str, *, display_version: str | None = None,
                         legacy_ref: str = LEGACY_COMMIT) -> None:
    legacy = load_legacy_updater(legacy_ref)
    authenticate_release_metadata(legacy, os.environ.get('AURORA_CI_GITHUB_TOKEN'))
    if not legacy.is_newer(version):
        raise ValueError("A versão de migração não é mais recente para o aplicativo antigo.")
    for system in ("win32", "linux"):
        for attempt in range(8):
            try:
                release = legacy.latest_release(
                    include_prereleases=True, platform_name=system, machine="amd64")
                if release is None or release.version != version:
                    raise ValueError(
                        "A versão de migração ainda não está disponível no atualizador antigo.")
                with tempfile.TemporaryDirectory(prefix="aurora-legacy-check-") as folder:
                    installer = legacy.download_verified_installer(release, Path(folder))
                    shown = f"; aplicativo v{display_version}" if display_version else ""
                    print(f"{system}: atualizador v{LEGACY_VERSION} encontrou v{release.version}"
                          f"{shown}; download e SHA256 conferidos ({installer.stat().st_size} bytes).")
                break
            except Exception:
                if attempt == 7:
                    raise
                # Publication can precede propagation of the public Releases list.
                time.sleep(min(5 * (attempt + 1), 20))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True,
                        help="Versão exata do lançamento de compatibilidade.")
    parser.add_argument("--display-version", help="Versão com data exibida no aplicativo novo.")
    parser.add_argument("--legacy-ref", default=LEGACY_COMMIT,
                        help="Commit SHA completo do atualizador instalado.")
    args = parser.parse_args()
    verify_legacy_update(args.version, display_version=args.display_version,
                         legacy_ref=args.legacy_ref)


if __name__ == "__main__":
    main()
