"""Verify a genuine MSI install/uninstall without touching a persistent PC."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msi", type=Path, required=True)
    args = parser.parse_args()
    if (sys.platform != "win32" or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted"):
        parser.error("MSI smoke test requires a disposable GitHub-hosted Windows runner.")

    msi = args.msi.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="aurora-msi-", dir=os.environ.get("RUNNER_TEMP")) as directory:
        root = Path(directory)
        install = root / "application MSI with spaces"
        log = root / "msi-install.log"
        uninstall_log = root / "msi-uninstall.log"

        def invoke(*args, logfile):
            command = ["msiexec.exe", *args, "/qn", "/norestart", f"/L*V", str(logfile)]
            proc = subprocess.run(command, capture_output=True, text=True, timeout=240)
            if proc.returncode != 0:
                print(logfile.read_text(encoding="utf-16", errors="replace")[-10000:]
                      if logfile.exists() else proc.stderr)
                raise RuntimeError(f"msiexec returned {proc.returncode} for {args}")
        # A dedicated MSI UpgradeCode, separate folder and distinct Start Menu
        # entry ensure existing Inno installations never get overwritten.
        try:
            invoke("/i", str(msi), f"INSTALLFOLDER={install}", logfile=log)
            assert (install / "AURORA AutoFill.exe").is_file(), "MSI did not install the executable"
            assert (install / "AURORA-MSI-CHANNEL.txt").is_file(), "MSI marker missing"
            assert (install / "SOURCE-COMMIT.txt").is_file(), "MSI did not copy bundled provenance"
            print("MSI installation verified", flush=True)
        finally:
            invoke("/x", str(msi), logfile=uninstall_log)
        assert not (install / "AURORA AutoFill.exe").exists(), "Uninstall left app files"
        print("MSI uninstall verified", flush=True)


if __name__ == "__main__":
    main()
