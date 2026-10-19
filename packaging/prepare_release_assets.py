"""Flatten Actions artifacts and verify every installer before publication."""
from hashlib import sha256
from pathlib import Path
import argparse
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.versioning import canonical_to_bridge, parse_version


def _asset_names(version: str) -> tuple[str, ...]:
    parse_version(version)
    windows = f"AURORA-AutoFill-v{version}-Windows-Setup.exe"
    msi = f"AURORA-AutoFill-v{version}-Windows-x64.msi"
    linux = f"AURORA-AutoFill-v{version}-Linux-amd64.deb"
    portable = f"AURORA-AutoFill-v{version}-Linux-portable-amd64.tar.gz"
    return (windows, msi, linux, portable, "SHA256SUMS-Windows.txt", "SHA256SUMS-Linux.txt")


def _validated_sources(root: Path, version: str) -> tuple[dict[str, Path], dict[str, str]]:
    """Locate and verify all three payloads before creating any output files."""
    names = _asset_names(version)
    windows, msi, linux, portable, windows_manifest, linux_manifest = names
    sources = {}
    for name in names:
        matches = [path for path in Path(root).rglob(name) if path.is_file() and not path.is_symlink()]
        if len(matches) != 1:
            raise ValueError(f"Esperado exatamente um arquivo de publicação: {name}")
        sources[name] = matches[0]
    digests = {}
    for name, manifest in ((windows, windows_manifest), (msi, windows_manifest),
                           (linux, linux_manifest), (portable, linux_manifest)):
        if sources[manifest].stat().st_size > 65536:
            raise ValueError("Manifesto SHA256 maior que o permitido.")
        checksums = [parts[0].lower() for line in sources[manifest].read_text(encoding="ascii").splitlines()
                     if len(parts := line.split()) == 2 and parts[1].removeprefix("*") == name
                     and re.fullmatch(r"[a-fA-F0-9]{64}", parts[0])]
        digest = sha256()
        with sources[name].open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        if len(checksums) != 1 or digest.hexdigest() != checksums[0]:
            raise ValueError(f"Falha na verificação SHA256: {name}")
        digests[name] = digest.hexdigest()
    return sources, digests


def prepare_assets(root: Path, destination: Path, version: str) -> list[Path]:
    sources, _ = _validated_sources(root, version)
    # Nothing is staged for publication until all four payloads pass.
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    return [Path(shutil.copy2(source, destination / name)) for name, source in sources.items()]


def prepare_bridge_assets(root: Path, destination: Path, version: str) -> list[Path]:
    """Rename verified canonical bytes for the already-installed SemVer updater."""
    bridge = canonical_to_bridge(version)
    sources, digests = _validated_sources(root, version)
    names, bridge_names = _asset_names(version), _asset_names(bridge)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, alias in zip(names[:4], bridge_names[:4]):
        paths.append(Path(shutil.copy2(sources[name], destination / alias)))
    for manifest, indexes in ((bridge_names[4], (0, 1)), (bridge_names[5], (2, 3))):
        path = destination / manifest
        path.write_text("".join(f"{digests[names[index]]}  {bridge_names[index]}\n"
                                for index in indexes), encoding="ascii")
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("release-assets"))
    parser.add_argument("--out", type=Path, default=Path("release-publish"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--bridge", action="store_true",
                        help="Preparar também os mesmos instaladores para o atualizador anterior.")
    parser.add_argument("--bridge-out", type=Path, default=Path("release-bridge"))
    args = parser.parse_args()
    paths = prepare_assets(args.root, args.out, args.version)
    print("Instaladores e checksums conferidos para publicação:")
    for path in paths:
        print(path)
    if args.bridge:
        print("Instaladores de transição conferidos para o atualizador anterior:")
        for path in prepare_bridge_assets(args.out, args.bridge_out, args.version):
            print(path)


if __name__ == "__main__":
    main()
