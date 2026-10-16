"""Artifacts with multiple upload roots retain their relative directories."""
from hashlib import sha256
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("aurora_release_assets", ROOT / "packaging/prepare_release_assets.py")
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)
VERSION = "0.6.1-dev.20.1"


class ReleaseAssetsTests(unittest.TestCase):
    def fixture(self, root):
        windows = root / "windows"
        linux = root / "linux"
        (windows / "installer-win").mkdir(parents=True)
        linux.mkdir()
        exe = windows / "installer-win" / f"AURORA-AutoFill-v{VERSION}-Windows-Setup.exe"
        deb = linux / f"AURORA-AutoFill-v{VERSION}-Linux-amd64.deb"
        tar = linux / f"AURORA-AutoFill-v{VERSION}-Linux-portable-amd64.tar.gz"
        for path in (exe, deb, tar):
            path.write_bytes(path.name.encode())
        (windows / "SHA256SUMS-Windows.txt").write_text(
            sha256(exe.read_bytes()).hexdigest() + "  " + exe.name + "\n", encoding="ascii")
        (linux / "SHA256SUMS-Linux.txt").write_text("".join(
            sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in (deb, tar)), encoding="ascii")
        return exe, deb, tar

    def test_nested_windows_and_flat_linux_are_normalized_to_five_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root, destination = Path(folder) / "input", Path(folder) / "output"
            exe, deb, tar = self.fixture(root)
            result = assets.prepare_assets(root, destination, VERSION)
            self.assertEqual(len(result), 5)
            self.assertTrue(all(path.parent == destination for path in result))
            for source in (exe, deb, tar):
                self.assertEqual((destination / source.name).read_bytes(), source.read_bytes())

    def test_bad_checksum_prevents_any_publication_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root, destination = Path(folder) / "input", Path(folder) / "output"
            exe, _, _ = self.fixture(root)
            exe.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                assets.prepare_assets(root, destination, VERSION)
            self.assertFalse(destination.exists())

    def test_missing_or_duplicate_installer_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root, destination = Path(folder) / "input", Path(folder) / "output"
            exe, _, _ = self.fixture(root)
            (root / exe.name).write_bytes(exe.read_bytes())
            with self.assertRaisesRegex(ValueError, "exatamente um"):
                assets.prepare_assets(root, destination, VERSION)
            (root / exe.name).unlink()
            exe.unlink()
            with self.assertRaisesRegex(ValueError, "exatamente um"):
                assets.prepare_assets(root, destination, VERSION)
