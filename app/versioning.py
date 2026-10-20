"""Date-based release names with a compatible bridge for older updaters.

The public name uses DDMMYY. The bridge uses an alphabetic prerelease
identifier so installed SemVer updaters consider it newer than ``dev``.
Both names describe the same release and have identical comparison keys.
"""
from __future__ import annotations

from datetime import date
import re


VERSION_PATTERN = re.compile(
    r"^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$")
_CANONICAL = re.compile(r"([0-9]{6})(?:\.([1-9][0-9]*))?")
_BRIDGE = re.compile(r"update\.([0-9]{8})(?:\.([1-9][0-9]*))?")


def _raw_version(version: str) -> re.Match:
    if not isinstance(version, str) or len(version) > 160:
        raise ValueError("Número de versão desconhecido.")
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError("Número de versão desconhecido.")
    return match


def _dated_parts(match: re.Match) -> tuple[tuple[int, int, int], date, int] | None:
    identifiers = match.group(4)
    if not identifiers:
        return None
    canonical = _CANONICAL.fullmatch(identifiers)
    bridge = _BRIDGE.fullmatch(identifiers)
    if canonical is None and bridge is None:
        # A misspelled date must not silently become a different legacy channel.
        if (re.match(r"[0-9]{6}(?:\.|$)", identifiers)
                or identifiers.startswith("update.")):
            raise ValueError("Data ou revisão da atualização inválida.")
        return None
    selected = canonical or bridge
    stamp, revision = selected.groups()
    try:
        if canonical is not None:
            released = date(2000 + int(stamp[4:]), int(stamp[2:4]), int(stamp[:2]))
        else:
            released = date(int(stamp[:4]), int(stamp[4:6]), int(stamp[6:]))
            if not 2000 <= released.year <= 2099:
                raise ValueError("Ano da atualização fora do intervalo permitido.")
    except ValueError as exc:
        raise ValueError("Data da atualização inválida.") from exc
    core = tuple(int(match.group(index)) for index in (1, 2, 3))
    return core, released, int(revision or "1")


def parse_version(version: str) -> re.Match:
    """Return the familiar SemVer groups, also accepting real DDMMYY dates."""
    match = _raw_version(version)
    if _dated_parts(match) is None:
        identifiers = match.group(4)
        if identifiers and any(part.isdigit() and len(part) > 1 and part[0] == "0"
                               for part in identifiers.split(".")):
            raise ValueError("Número de versão de teste inválido.")
    return match


def parse_dated_version(version: str) -> tuple[tuple[int, int, int], date, int] | None:
    """Return core, release date and revision; legacy SemVer returns None."""
    return _dated_parts(parse_version(version))


def _date_name(core: tuple[int, int, int], released: date, revision: int) -> str:
    base = ".".join(str(part) for part in core)
    suffix = f".{revision}" if revision > 1 else ""
    return f"{base}-{released:%d%m%y}{suffix}"


def canonical_to_bridge(version: str) -> str:
    """Create an old-updater-compatible tag name for a canonical dated release."""
    match = parse_version(version)
    dated = _dated_parts(match)
    if dated is None or _CANONICAL.fullmatch(match.group(4)) is None:
        raise ValueError("Informe uma versão com data no formato DDMMYY.")
    core, released, revision = dated
    base = ".".join(str(part) for part in core)
    suffix = f".{revision}" if revision > 1 else ""
    return f"{base}-update.{released:%Y%m%d}{suffix}"


def display_version(version: str) -> str:
    """Show the requested DDMMYY name even when discovery used the bridge tag."""
    match = parse_version(version)
    dated = _dated_parts(match)
    if dated is not None:
        return _date_name(*dated)
    return version.removeprefix("v")


def version_key(version: str) -> tuple:
    """Order core first, legacy tests, dated tests chronologically, then stable."""
    match = parse_version(version)
    core = tuple(int(match.group(index)) for index in (1, 2, 3))
    dated = _dated_parts(match)
    if dated is not None:
        return (*core, 2, (dated[1].toordinal(), dated[2]))
    identifiers = match.group(4)
    if identifiers is None:
        return (*core, 3, ())
    prerelease = tuple((0, int(part)) if part.isdigit() else (1, part)
                       for part in identifiers.split("."))
    return (*core, 1, prerelease)
