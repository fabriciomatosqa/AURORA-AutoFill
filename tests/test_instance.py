"""Two processes must never expand the same keystrokes in one user profile."""
from pathlib import Path
import os
import tempfile
import unittest

from app.instance import acquire_instance_lock


class InstanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_second_listener_is_refused_until_first_instance_exits(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "profile"
            first = acquire_instance_lock(path)
            self.assertIsNotNone(first)
            try:
                self.assertIsNone(acquire_instance_lock(path))
            finally:
                first.unlock()
            replacement = acquire_instance_lock(path)
            self.assertIsNotNone(replacement)
            replacement.unlock()

    def test_separate_profiles_can_run_independently(self):
        with tempfile.TemporaryDirectory() as folder:
            locks = [acquire_instance_lock(Path(folder) / name) for name in ("one", "two")]
            try:
                self.assertTrue(all(lock is not None for lock in locks))
            finally:
                for lock in locks:
                    if lock is not None:
                        lock.unlock()
