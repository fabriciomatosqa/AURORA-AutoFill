"""Run the full unit suite with a bounded subprocess and streaming logs.

The Qt bindings can occasionally block inside native code rather than raising
a Python exception. Detect that early instead of letting a 30 minute install
pipeline appear active with no useful diagnosis. Preserve unittest output.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 300 if sys.platform == 'win32' else 150


def main() -> int:
    command = [sys.executable, "-u", "-X", "faulthandler",
               "-m", "unittest", "discover", "-s", "tests", "-v"]
    print(f"AURORA tests: bounded to {TIMEOUT_SECONDS}s, output is streamed.", flush=True)
    process = subprocess.Popen(command, cwd=ROOT)
    try:
        return process.wait(timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        print(f"ERROR: unittest did not complete in {TIMEOUT_SECONDS}s. "
              "Check the last test printed above.", file=sys.stderr, flush=True)
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=8)
        return 124


if __name__ == "__main__":
    raise SystemExit(main())
