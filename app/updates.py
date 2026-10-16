"""Checksum-verified updates from official stable and development GitHub Releases."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from .version import APP_VERSION, GITHUB_REPOSITORY, GITHUB_RELEASES_API

VERSION_PATTERN = re.compile(
    r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")
MAX_INSTALLER_BYTES = 500 * 1024 * 1024
MAX_RELEASE_PAGES = 3
_DOWNLOAD_HOSTS = {"github.com", "api.github.com", "release-assets.githubusercontent.com",
                   "objects.githubusercontent.com"}
# In-memory receipts avoid a second network request when the UI launches an installer.
_verified_downloads: dict[Path, tuple[str, str]] = {}


def _parse_version(version):
    if not isinstance(version, str) or len(version) > 160:
        raise ValueError("Número de versão desconhecido.")
    match = VERSION_PATTERN.fullmatch(version)
    if not match:
        raise ValueError("Número de versão desconhecido.")
    identifiers = match.group(4)
    if identifiers and any(part.isdigit() and len(part) > 1 and part[0] == "0"
                           for part in identifiers.split(".")):
        raise ValueError("Número de versão de teste inválido.")
    return match


def version_parts(version: str) -> tuple[int, int, int]:
    """Core version; is_newer also compares prerelease identifiers."""
    match = _parse_version(version)
    return tuple(int(match.group(index)) for index in (1, 2, 3))


def _version_key(version):
    match = _parse_version(version)
    identifiers = match.group(4)
    pre = tuple((0, int(part)) if part.isdigit() else (1, part)
                for part in identifiers.split(".")) if identifiers else ()
    return (*version_parts(version), 0 if identifiers else 1, pre)


def is_newer(release_version: str, local_version: str = APP_VERSION) -> bool:
    return _version_key(release_version) > _version_key(local_version)


def _https_address(url):
    if not isinstance(url, str):
        raise ValueError("Origem de atualização não autorizada.")
    address = urlparse(url)
    if (address.scheme != "https" or address.username or address.password
            or address.netloc.lower() != address.hostname or address.fragment):
        raise ValueError("Origem de atualização não autorizada.")
    return address


def _official_url(url, *, expected_path=None):
    address = _https_address(url)
    api = f"/repos/{GITHUB_REPOSITORY}/releases"
    release = f"/{GITHUB_REPOSITORY}/releases/"
    if not ((address.hostname == "api.github.com" and
             (address.path == api or address.path.startswith(api + "/")))
            or (address.hostname == "github.com" and address.path.startswith(release))):
        raise ValueError("A atualização não pertence ao repositório oficial.")
    if expected_path is not None and (unquote(address.path) != expected_path or address.query):
        raise ValueError("O arquivo não pertence ao lançamento oficial.")
    return address


class _GitHubRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if _https_address(newurl).hostname not in _DOWNLOAD_HOSTS:
            raise ValueError("O GitHub redirecionou para uma origem não autorizada.")
        return super().redirect_request(request, response, code, message, headers, newurl)


_opener = build_opener(_GitHubRedirects())


def urlopen(request, *, timeout):
    return _opener.open(request, timeout=timeout)


def _request(url, *, json_response=False):
    _official_url(url)
    return Request(url, headers={
        "User-Agent": f"AURORA-AutoFill/{APP_VERSION}",
        "Accept": "application/vnd.github+json" if json_response else "application/octet-stream",
        "X-GitHub-Api-Version": "2022-11-28"})


def _get(url: str, *, timeout: float = 8, max_bytes: int = 2 * 1024 * 1024) -> bytes:
    with urlopen(_request(url, json_response=True), timeout=timeout) as result:
        data = result.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("Resposta de atualização maior que o permitido.")
        return data


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    page_url: str
    installer_url: str | None
    checksum_url: str | None
    prerelease: bool = False
    installer_name: str | None = None
    installer_kind: str = "exe"
    sha256: str | None = None
    size: int | None = None


StableRelease = Release  # Compatibility with the previous updater constructor.


def _asset_names(version, platform_name, machine):
    if platform_name == "win32":
        return f"AURORA-AutoFill-v{version}-Windows-Setup.exe", "SHA256SUMS-Windows.txt", "exe"
    if platform_name.startswith("linux") and machine.lower() in {"x86_64", "amd64"}:
        return f"AURORA-AutoFill-v{version}-Linux-amd64.deb", "SHA256SUMS-Linux.txt", "deb"
    return None, None, "unsupported"


def _release_from_payload(payload, *, include_prereleases, platform_name, machine):
    if not isinstance(payload, dict) or payload.get("draft"):
        return None
    tag = payload.get("tag_name")
    try:
        match = _parse_version(tag)
    except ValueError:
        return None
    prerelease = bool(payload.get("prerelease") or match.group(4))
    if prerelease and not include_prereleases:
        return None
    version, page = tag.removeprefix("v"), payload.get("html_url")
    try:
        _official_url(page, expected_path=f"/{GITHUB_REPOSITORY}/releases/tag/{tag}")
    except ValueError:
        return None
    name, checksum_name, kind = _asset_names(version, platform_name, machine)
    assets = payload.get("assets", [])
    if not isinstance(assets, list):
        return None
    wanted = {}
    for asset in assets:
        if (not name or not isinstance(asset, dict) or
                asset.get("name") not in {name, checksum_name}):
            continue
        asset_name, url = asset["name"], asset.get("browser_download_url")
        try:
            _official_url(url, expected_path=(
                f"/{GITHUB_REPOSITORY}/releases/download/{tag}/{asset_name}"))
        except ValueError:
            continue
        if asset.get("state", "uploaded") == "uploaded" and asset_name not in wanted:
            wanted[asset_name] = asset
    installer, checksum = wanted.get(name, {}), wanted.get(checksum_name, {})
    digest = installer.get("digest")
    digest = digest[7:].lower() if isinstance(digest, str) and re.fullmatch(
        r"sha256:[a-fA-F0-9]{64}", digest) else None
    size = installer.get("size")
    if type(size) is not int or size <= 0:
        size = None
    return Release(version, tag, page, installer.get("browser_download_url"),
                   checksum.get("browser_download_url"), prerelease, name, kind, digest, size)


def latest_release(*, include_prereleases: bool = True, platform_name: str | None = None,
                   machine: str | None = None) -> Release | None:
    """Highest official SemVer, including tests; /latest omits prereleases."""
    candidates = []
    for page in range(1, MAX_RELEASE_PAGES + 1):
        try:
            payload = json.loads(_get(f"{GITHUB_RELEASES_API}?per_page=100&page={page}"))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            if exc.code in {403, 429}:
                raise ValueError("O GitHub limitou as consultas. Tente novamente mais tarde.") from exc
            raise
        # Permit existing adapters that return one release instead of a list.
        records = [payload] if isinstance(payload, dict) and "tag_name" in payload else payload
        if not isinstance(records, list):
            raise ValueError("O GitHub retornou uma lista de versões inválida.")
        for record in records:
            release = _release_from_payload(
                record, include_prereleases=include_prereleases,
                platform_name=platform_name or sys.platform, machine=machine or platform.machine())
            if (release and release.installer_url and release.checksum_url
                    and (release.size is None or release.size <= MAX_INSTALLER_BYTES)):
                candidates.append(release)
        if len(records) < 100:
            break
    return max(candidates, key=lambda item: _version_key(item.version), default=None)


def _installer_filename(release):
    _parse_version(release.version)
    if release.tag.removeprefix("v") != release.version:
        raise ValueError("A versão do instalador não corresponde ao lançamento.")
    filename = release.installer_name or f"AURORA-AutoFill-v{release.version}-Windows-Setup.exe"
    names = {
        f"AURORA-AutoFill-v{release.version}-Windows-Setup.exe": ("exe", "SHA256SUMS-Windows.txt"),
        f"AURORA-AutoFill-v{release.version}-Linux-amd64.deb": ("deb", "SHA256SUMS-Linux.txt")}
    if filename not in names or names[filename][0] != release.installer_kind:
        raise ValueError("Formato de instalador não autorizado.")
    if not release.installer_url or not release.checksum_url:
        raise ValueError("Este lançamento não contém instalador e SHA256 para este sistema.")
    _official_url(release.installer_url, expected_path=(
        f"/{GITHUB_REPOSITORY}/releases/download/{release.tag}/{filename}"))
    _official_url(release.checksum_url, expected_path=(
        f"/{GITHUB_REPOSITORY}/releases/download/{release.tag}/{names[filename][1]}"))
    return filename


def _expected_checksum(release, filename):
    checksums = _get(release.checksum_url, max_bytes=65536).decode("ascii")
    matching = [parts[0].lower() for line in checksums.splitlines()
                if len(parts := line.split()) == 2
                and parts[1].removeprefix("*") == filename
                and re.fullmatch(r"[a-fA-F0-9]{64}", parts[0])]
    if len(matching) != 1:
        raise ValueError("Não foi possível validar o SHA256 do instalador.")
    if release.sha256 is not None and release.sha256.lower() != matching[0]:
        raise ValueError("A verificação do GitHub diverge do manifesto SHA256.")
    return matching[0]


def _cancel_if_requested(cancelled):
    if cancelled is not None and cancelled():
        raise ValueError("Download cancelado.")


def download_verified_installer(release: Release, directory: Path | None = None,
                                progress=None, cancelled=None) -> Path:
    """Publish the official installer on disk only after a complete SHA256 check."""
    if not is_newer(release.version):
        raise ValueError("A versão remota não é mais recente que a instalada.")
    filename = _installer_filename(release)
    if release.size is not None and (type(release.size) is not int or
                                     not 0 < release.size <= MAX_INSTALLER_BYTES):
        raise ValueError("Tamanho do instalador inválido.")
    _cancel_if_requested(cancelled)
    expected = _expected_checksum(release, filename)
    _cancel_if_requested(cancelled)
    folder = Path(directory) if directory is not None else Path(
        tempfile.mkdtemp(prefix="AURORA-AutoFill-Update-"))
    folder.mkdir(parents=True, exist_ok=True)
    destination, partial = folder / filename, None
    digest, downloaded = sha256(), 0
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=".aurora-", suffix=".part",
                                         delete=False) as handle:
            partial = Path(handle.name)
            with urlopen(_request(release.installer_url), timeout=20) as response:
                raw_length = response.headers.get("Content-Length")
                try:
                    declared = int(raw_length) if raw_length is not None else None
                except (ValueError, TypeError) as exc:
                    raise ValueError("Tamanho do download inválido.") from exc
                if declared is not None and not 0 < declared <= MAX_INSTALLER_BYTES:
                    raise ValueError("Instalador maior que o permitido ou vazio.")
                if release.size is not None and declared is not None and release.size != declared:
                    raise ValueError("O tamanho do instalador diverge do lançamento.")
                total = declared or release.size
                if progress:
                    progress(0)
                while True:
                    _cancel_if_requested(cancelled)
                    chunk = response.read(128 * 1024)
                    _cancel_if_requested(cancelled)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > MAX_INSTALLER_BYTES:
                        raise ValueError("Instalador maior que o permitido.")
                    if total and downloaded > total:
                        raise ValueError("O download excedeu o tamanho do instalador.")
                    handle.write(chunk)
                    digest.update(chunk)
                    if progress and total:
                        progress(min(99, int(100 * downloaded / total)))
            handle.flush()
            os.fsync(handle.fileno())
        if (not downloaded or (declared is not None and downloaded != declared)
                or (release.size is not None and downloaded != release.size)):
            raise ValueError("O download do instalador está incompleto.")
        if digest.hexdigest() != expected:
            raise ValueError("O instalador não passou na verificação SHA256.")
        _cancel_if_requested(cancelled)
        partial.replace(destination)
        _verified_downloads[destination.resolve()] = (release.installer_url, expected)
        if progress:
            progress(100)
        return destination
    finally:
        if partial is not None:
            partial.unlink(missing_ok=True)


def launch_installer(path: Path, release: Release) -> None:
    """Rehash a download receipt before execution. UI confirms and backs up first."""
    filename = _installer_filename(release)
    path = Path(path)
    if path.name != filename or path.is_symlink() or not path.is_file():
        raise ValueError("O arquivo de instalação não corresponde ao lançamento.")
    if not 0 < path.stat().st_size <= MAX_INSTALLER_BYTES:
        raise ValueError("Tamanho do instalador inválido.")
    verified = _verified_downloads.get(path.resolve())
    if not verified or verified[0] != release.installer_url:
        raise ValueError("Baixe e valide o instalador novamente pelo aplicativo.")
    with path.open("rb") as handle:
        digest = sha256()
        while chunk := handle.read(128 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != verified[1]:
        _verified_downloads.pop(path.resolve(), None)
        raise ValueError("O instalador foi modificado depois do download. Baixe novamente.")
    if release.installer_kind == "exe" and sys.platform == "win32":
        subprocess.Popen([str(path.resolve()), "/NORESTART"], close_fds=True)
    elif release.installer_kind == "deb" and sys.platform.startswith("linux"):
        opener = shutil.which("xdg-open")
        if opener is None:
            raise OSError(f"Abra o instalador no gerenciador de pacotes: {path}")
        subprocess.Popen([opener, str(path.resolve())], close_fds=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        raise ValueError("Este instalador não corresponde ao sistema em uso.")
