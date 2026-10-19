"""MSI's ProductVersion uses only THREE fields; derive a dated, increasing build.

MSI and Inno use distinct product identities. The public app version is unchanged.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.versioning import parse_version, parse_dated_version

EPOCH = date(2020, 1, 1)


def msi_version(version: str, *, stable_date: date | None = None) -> str:
    match = parse_version(version)
    major, minor = (int(match.group(1)), int(match.group(2)))
    dated = parse_dated_version(version)
    if dated:
        release_date, revision = dated[1], dated[2]
        # Four revision slots each day, with same-version major upgrades for
        # extra revisions. The date/revision combination remains ordered.
        slot = min(max(1, revision), 4) - 1
    elif match.group(4) is None:
        # A stable release on this date supersedes its dated prereleases.
        release_date, slot = stable_date or date.today(), 3
    else:
        raise ValueError("MSI requer uma versão com data ou uma versão estável.")
    value = (release_date - EPOCH).days * 4 + slot
    if major > 255 or minor > 255 or not 1 <= value <= 65535:
        raise ValueError("Versão fora do intervalo do Windows Installer.")
    return f"{major}.{minor}.{value}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    print(msi_version(args.version))


if __name__ == "__main__":
    main()
