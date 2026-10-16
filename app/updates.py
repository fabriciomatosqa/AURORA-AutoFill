"""Explicit, checksum-verified updates from official stable GitHub Releases."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import json
import re
import tempfile

from .version import APP_VERSION, GITHUB_LATEST_API, GITHUB_RELEASES_URL

VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
MAX_INSTALLER_BYTES = 500 * 1024 * 1024


def version_parts(version: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(version)
    if not match:
        raise ValueError("Número de versão desconhecido.")
    return tuple(int(part) for part in match.groups())


def is_newer(release_version: str, local_version: str = APP_VERSION) -> bool:
    return version_parts(release_version) > version_parts(local_version)


def _get(url: str, *, timeout: float = 8, max_bytes: int = 1024 * 1024) -> bytes:
    address = urlparse(url)
    if address.scheme != "https" or address.hostname not in {"api.github.com", "github.com"}:
        raise ValueError("Origem de atualização não autorizada.")
    request = Request(url, headers={"User-Agent": "AURORA-AutoFill-Updater",
                                    "Accept": "application/vnd.github+json"})
    with urlopen(request, timeout=timeout) as result:
        data = result.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Resposta de atualização maior que o permitido.")
        return data


@dataclass(frozen=True)
class StableRelease:
    version: str
    tag: str
    page_url: str
    installer_url: str | None
    checksum_url: str | None


def latest_release() -> StableRelease | None:
    """Only official stable releases are offered. No artifacts or dev snapshots."""
    try:
        payload = json.loads(_get(GITHUB_LATEST_API))
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if not isinstance(payload, dict) or payload.get("draft") or payload.get("prerelease"):
        return None
    tag = payload.get("tag_name")
    if not isinstance(tag, str):
        return None
    version_parts(tag)
    page = payload.get("html_url", "")
    if (not isinstance(page, str) or
            not page.startswith(GITHUB_RELEASES_URL + "/tag/")):
        raise ValueError("A página de lançamento não pertence ao repositório oficial.")
    installer = checksum = None
    for asset in payload.get("assets", []):
        if not isinstance(asset, dict):
            continue
        name, url = asset.get("name"), asset.get("browser_download_url")
        if not isinstance(url, str) or not url.startswith(
                GITHUB_RELEASES_URL + "/download/" + tag + "/"):
            continue
        if name == f"AURORA-AutoFill-v{tag.lstrip('v')}-Windows-Setup.exe":
            installer = url
        elif name == "SHA256SUMS-Windows.txt":
            checksum = url
    return StableRelease(tag.lstrip("v"), tag, page, installer, checksum)


def download_verified_installer(release: StableRelease, directory: Path | None = None,
                                progress=None) -> Path:
    """Download only the official release installer; verify its SHA256 first."""
    if not is_newer(release.version):
        raise ValueError("A versão remota não é mais recente que a instalada.")
    if not release.installer_url or not release.checksum_url:
        raise ValueError("Este lançamento não contém instalador e SHA256 Windows.")
    filename = f"AURORA-AutoFill-v{release.version}-Windows-Setup.exe"
    checksums = _get(release.checksum_url, max_bytes=65536).decode("ascii")
    allowed = [line.split() for line in checksums.splitlines()]
    matching = [parts[0].lower() for parts in allowed
                if len(parts) == 2 and parts[1].lstrip("*") == filename
                and re.fullmatch(r"[a-fA-F0-9]{64}", parts[0])]
    if len(matching) != 1:
        raise ValueError("Não foi possível validar o SHA256 do instalador.")
    output_folder = Path(directory) if directory else Path(tempfile.gettempdir()) / "AURORA-AutoFill-Updates"
    output_folder.mkdir(parents=True, exist_ok=True)
    destination = output_folder / filename
    partial = output_folder / (filename + ".part")
    request = Request(release.installer_url, headers={"User-Agent": "AURORA-AutoFill-Updater"})
    digest = sha256()
    downloaded = 0
    try:
        with urlopen(request, timeout=30) as response, partial.open("wb") as handle:
            declared_size = int(response.headers.get("Content-Length", "0"))
            if declared_size > MAX_INSTALLER_BYTES:
                raise ValueError("Instalador maior que o permitido.")
            while True:
                chunk = response.read(128 * 1024)
                if not chunk:
                    break
                downloaded += len(chunk)
                if downloaded > MAX_INSTALLER_BYTES:
                    raise ValueError("Instalador maior que o permitido.")
                handle.write(chunk)
                digest.update(chunk)
                if progress and declared_size:
                    progress(min(100, int(100 * downloaded / declared_size)))
        if not downloaded or digest.hexdigest() != matching[0]:
            raise ValueError("O instalador não passou na verificação SHA256.")
        partial.replace(destination)
        return destination
    finally:
        partial.unlink(missing_ok=True)
