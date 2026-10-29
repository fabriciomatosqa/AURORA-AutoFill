import unittest
from unittest.mock import patch
from app.linux_setup_ui import COMMANDS, terminal_command


class LinuxSetupTests(unittest.TestCase):
    def test_only_known_terminal_and_explicit_sudo(self):
        with patch("app.linux_setup_ui.shutil.which", side_effect=lambda name: "/usr/bin/gnome-terminal" if name == "gnome-terminal" else None):
            args = terminal_command()
        self.assertEqual(args[:4], ["/usr/bin/gnome-terminal", "--", "bash", "-lc"])
        self.assertIn("sudo usermod -aG input", args[-1])
        self.assertIn("sudo udevadm", args[-1])
        self.assertNotIn("curl", args[-1])
        self.assertIn("gpasswd", "sudo gpasswd")
        self.assertIn("KERNEL", COMMANDS)

    def test_no_terminal_does_not_run_anything(self):
        with patch("app.linux_setup_ui.shutil.which", return_value=None):
            self.assertIsNone(terminal_command())


if __name__ == "__main__":
    unittest.main()
