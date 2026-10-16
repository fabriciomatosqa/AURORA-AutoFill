"""Flatten Actions artifacts and verify every installer before publication."""
from hashlib import sha256
from pathlib import Path
import argparse
import re
import shutil


def prepare_assets(root: Path, destination: Path, version: str) -> list[Path]:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-dev\.\d+\.\d+)?", version):
        raise ValueError("Versão de publicação inválida.")
    windows = f"AURORA-AutoFill-v{version}-Windows-Setup.exe"
    linux = f"AURORA-AutoFill-v{version}-Linux-amd64.deb"
    portable = f"AURORA-AutoFill-v{version}-Linux-portable-amd64.tar.gz"
    manifests = ("SHA256SUMS-Windows.txt", "SHA256SUMS-Linux.txt")
    names = (windows, linux, portable, *manifests)
    sources = {}
    for name in names:
        matches = [path for path in Path(root).rglob(name) if path.is_file() and not path.is_symlink()]
        if len(matches) != 1:
            raise ValueError(f"Esperado exatamente um arquivo de publicação: {name}")
        sources[name] = matches[0]
    for name, manifest in ((windows, manifests[0]), (linux, manifests[1]), (portable, manifests[1])):
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
    # Nothing is staged for publication until all three payloads pass.
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    return [Path(shutil.copy2(sources[name], destination / name)) for name in names]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("release-assets"))
    parser.add_argument("--out", type=Path, default=Path("release-publish"))
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    paths = prepare_assets(args.root, args.out, args.version)
    print("Instaladores e checksums conferidos para publicação:")
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
