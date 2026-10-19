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
    def fixture(self, root, version=VERSION):
        windows = root / "windows"
        linux = root / "linux"
        (windows / "installer-win").mkdir(parents=True)
        linux.mkdir()
        exe = windows / "installer-win" / f"AURORA-AutoFill-v{version}-Windows-Setup.exe"
        msi = windows / "installer-win" / f"AURORA-AutoFill-v{version}-Windows-x64.msi"
        deb = linux / f"AURORA-AutoFill-v{version}-Linux-amd64.deb"
        tar = linux / f"AURORA-AutoFill-v{version}-Linux-portable-amd64.tar.gz"
        for path in (exe, msi, deb, tar):
            path.write_bytes(path.name.encode())
        (windows / "SHA256SUMS-Windows.txt").write_text(
            "".join(sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n"
                    for path in (exe, msi)), encoding="ascii")
        (linux / "SHA256SUMS-Linux.txt").write_text("".join(
            sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in (deb, tar)), encoding="ascii")
        return exe, msi, deb, tar

    def test_nested_windows_and_flat_linux_are_normalized_to_six_assets(self):
        with tempfile.TemporaryDirectory() as folder:
            root, destination = Path(folder) / "input", Path(folder) / "output"
            exe, deb, tar = self.fixture(root)
            result = assets.prepare_assets(root, destination, VERSION)
            self.assertEqual(len(result), 6)
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

    def test_date_version_including_zero_padded_day_is_publishable(self):
        for version in ("0.6.1-161026", "0.6.1-010126"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as folder:
                root, destination = Path(folder) / "input", Path(folder) / "output"
                self.fixture(root, version)
                result = assets.prepare_assets(root, destination, version)
                self.assertEqual(len(result), 6)
                self.assertTrue((destination / f"AURORA-AutoFill-v{version}-Windows-Setup.exe").is_file())

    def test_bridge_keeps_all_payload_bytes_and_rewrites_both_manifests(self):
        for version, bridge in (("0.6.1-161026", "0.6.1-update.20261016"),
                                ("0.6.1-161026.2", "0.6.1-update.20261016.2")):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as folder:
                root, destination = Path(folder) / "input", Path(folder) / "bridge"
                originals = self.fixture(root, version)
                result = assets.prepare_bridge_assets(root, destination, version)
                self.assertEqual(len(result), 6)
                self.assertEqual(len(list(destination.iterdir())), 6)
                for source in originals:
                    target = destination / source.name.replace(f"v{version}-", f"v{bridge}-")
                    self.assertEqual(target.read_bytes(), source.read_bytes())
                windows_manifest = (destination / "SHA256SUMS-Windows.txt").read_text(encoding="ascii")
                linux_manifest = (destination / "SHA256SUMS-Linux.txt").read_text(encoding="ascii")
                for index, source in enumerate(originals):
                    alias = source.name.replace(f"v{version}-", f"v{bridge}-")
                    expected = f"{sha256(source.read_bytes()).hexdigest()}  {alias}\n"
                    self.assertIn(expected, windows_manifest if index < 2 else linux_manifest)
                self.assertNotIn(f"v{version}-", windows_manifest + linux_manifest)
                # Running the normal validator over the alias confirms names and hashes.
                validated = assets.prepare_assets(destination, Path(folder) / "validated", bridge)
                self.assertEqual(len(validated), 6)

    def test_bridge_does_not_stage_any_asset_when_any_canonical_payload_is_corrupt(self):
        for damaged in (0, 1, 2, 3):
            with self.subTest(damaged=damaged), tempfile.TemporaryDirectory() as folder:
                root, destination = Path(folder) / "input", Path(folder) / "bridge"
                paths = self.fixture(root, "0.6.1-161026")
                paths[damaged].write_bytes(b"changed after checksum")
                with self.assertRaisesRegex(ValueError, "SHA256"):
                    assets.prepare_bridge_assets(root, destination, "0.6.1-161026")
                self.assertFalse(destination.exists())

    def test_bridge_requires_a_valid_canonical_date_before_writing(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "bridge"
            for version in (VERSION, "0.6.1-300226", "0.6.1-161026/evil"):
                with self.subTest(version=version), self.assertRaises(ValueError):
                    assets.prepare_bridge_assets(Path(folder), destination, version)
            self.assertFalse(destination.exists())
