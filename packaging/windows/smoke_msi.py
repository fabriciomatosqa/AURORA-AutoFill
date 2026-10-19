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
        # Keep INSTALLFOLDER inside the user's LocalAppData profile.
        local = Path(os.environ["LOCALAPPDATA"])
        install = local / "Programs" / f"AURORA AutoFill MSI smoke {root.name}"
        log = root / "msi-install.log"
        uninstall_log = root / "msi-uninstall.log"

        def show_log(path):
            if path.exists():
                raw = path.read_bytes()
                encoding = "utf-16" if raw.startswith((bytes((255, 254)), bytes((254, 255)))) else "utf-8"
                print(raw.decode(encoding, errors="replace")[-12000:], flush=True)

        def invoke(*args, logfile):
            command = ["msiexec.exe", *args, "/qn", "/norestart", "/L*V", str(logfile)]
            print(f"MSI smoke starting: {args}", flush=True)
            # Windows Installer child processes may keep inherited capture
            # pipes open after msiexec exits. Never use capture_output=True.
            proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                code = proc.wait(timeout=180)
            except subprocess.TimeoutExpired:
                show_log(logfile)
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=20, check=False)
                proc.wait(timeout=15)
                raise RuntimeError(f"msiexec timed out for {args}") from None
            print(f"MSI smoke exit={code}", flush=True)
            if code not in (0, 3010):
                show_log(logfile)
                raise RuntimeError(f"msiexec returned {code} for {args}")

        # A dedicated MSI UpgradeCode, separate folder and distinct Start Menu
        # entry ensure existing Inno installations never get overwritten.
        installed = False
        try:
            invoke("/i", str(msi), f"INSTALLFOLDER={install}", logfile=log)
            installed = True
            assert (install / "AURORA AutoFill.exe").is_file(), "MSI did not install the executable"
            assert (install / "AURORA-MSI-CHANNEL.txt").is_file(), "MSI marker missing"
            assert (install / "SOURCE-COMMIT.txt").is_file(), "MSI did not copy bundled provenance"
            print("MSI installation verified", flush=True)
        finally:
            # Do not mask the original install failure with a 1605 uninstall
            # error when the product was never installed.
            if installed:
                invoke("/x", str(msi), logfile=uninstall_log)
        if installed:
            assert not (install / "AURORA AutoFill.exe").exists(), "Uninstall left app files"
        print("MSI uninstall verified", flush=True)


if __name__ == "__main__":
    main()
