"""Verify the actual public update path after publishing both installers."""
from pathlib import Path
import argparse
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.updates import download_verified_installer, is_newer, latest_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    for system in ("win32", "linux"):
        for attempt in range(3):
            try:
                release = latest_release(platform_name=system, machine="amd64")
                if release is None or is_newer(args.version, release.version):
                    raise ValueError("A versão publicada ainda não está disponível no atualizador.")
                with tempfile.TemporaryDirectory(prefix="aurora-online-check-") as folder:
                    installer = download_verified_installer(release, Path(folder))
                    print(f"{system}: v{release.version}; download e SHA256 conferidos ({installer.stat().st_size} bytes).")
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(2)


if __name__ == "__main__":
    main()
