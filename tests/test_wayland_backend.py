"""Contratos de backend Wayland sem acessar teclados reais ou modificar o host."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch, Mock

from app import wayland_input


class FakeDevice:
    def __init__(self, path, keys):
        self.path, self.name = path, "Physical keyboard"
        self.keys = keys
        self.closed = False

    def capabilities(self):
        return {1: self.keys}

    def close(self):
        self.closed = True


class FakeEvdev:
    def __init__(self, path="/dev/input/event1"):
        self.path = path
        self.ecodes = SimpleNamespace(EV_KEY=1, KEY_A=30, KEY_SPACE=57,
                                      KEY_ENTER=28, KEY_LEFT=105,
                                      KEY_LEFTSHIFT=42, KEY_LEFTCTRL=29,
                                      KEY_BACKSPACE=14, KEY_V=47,
                                      BTN_LEFT=272, BTN_MOUSE=272, BTN_JOYSTICK=288)
        self.device = FakeDevice(self.path, (30, 57, 28, 105, 42, 29, 14, 47))

    def list_devices(self):
        return [self.path]

    def InputDevice(self, path):
        return self.device


class WaylandBackendTests(unittest.TestCase):
    def setUp(self):
        self.wayland = patch("app.wayland_input.is_wayland_session", return_value=True)
        self.wayland.start()
        self.addCleanup(self.wayland.stop)

    def test_detect_session_only_when_linux_wayland(self):
        with patch("app.wayland_input.is_wayland_session", wraps=wayland_input.is_wayland_session):
            self.assertTrue(wayland_input.is_wayland_session(
                {"XDG_SESSION_TYPE": "wayland", "DISPLAY": ":0"}, platform="linux"))
            self.assertTrue(wayland_input.is_wayland_session(
                {"WAYLAND_DISPLAY": "wayland-0"}, platform="linux"))
            self.assertFalse(wayland_input.is_wayland_session(
                {"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"}, platform="linux"))
            self.assertFalse(wayland_input.is_wayland_session(
                {"XDG_SESSION_TYPE": "wayland"}, platform="win32"))

    def test_missing_uinput_permission_is_actionable(self):
        with patch("app.wayland_input.os.access", return_value=False):
            message = wayland_input.diagnose_wayland(FakeEvdev())
        self.assertIn("/dev/uinput", message)
        self.assertIn("docs/linux-wayland.md", message)
        self.assertIn("Não execute", message)

    def test_accessible_devices_and_uinput_allow_start(self):
        fake = FakeEvdev()
        with patch("app.wayland_input.os.access", return_value=True):
            self.assertEqual(wayland_input.diagnose_wayland(fake), "")
        self.assertTrue(fake.device.closed)

    def test_no_keyboard_is_not_false_positive(self):
        fake = FakeEvdev()
        fake.device.keys = [fake.ecodes.BTN_LEFT]
        with patch("app.wayland_input.os.access", return_value=True):
            self.assertIn("Nenhum teclado", wayland_input.diagnose_wayland(fake))

    def test_unicode_layout_uses_gnome_xkb_and_respects_override(self):
        with patch.dict(os.environ, {"AURORA_WAYLAND_LAYOUT": "br"}):
            self.assertEqual(wayland_input.XkbTranslator._layout_name(), ("br", ""))
        with patch.dict(os.environ, {"AURORA_WAYLAND_LAYOUT": ""}), \
             patch("app.wayland_input.subprocess.run",
                   return_value=SimpleNamespace(stdout="[('xkb', 'br+abnt2')]", returncode=0)):
            self.assertEqual(wayland_input.XkbTranslator._layout_name(), ["br", "abnt2"])

    def test_tracked_replace_only_when_running_session_and_single_dispatch(self):
        called = []
        fake = SimpleNamespace(running=True, replace=lambda count: called.append(count))
        with patch.object(wayland_input, "_ACTIVE", fake):
            wayland_input.replace_wayland_shortcut(8)
            self.assertEqual(called, [8])
        with patch.object(wayland_input, "_ACTIVE", None):
            with self.assertRaises(RuntimeError):
                wayland_input.replace_wayland_shortcut(8)

    def test_virtual_keys_are_sent_in_safe_order_and_count_is_bounded(self):
        ec = FakeEvdev().ecodes
        events = []
        with patch.dict("sys.modules", {"evdev": FakeEvdev()}):
            driver = wayland_input.WaylandInputListener(lambda _: None, lambda _: None, lambda: None)
        driver.running = True
        driver._virtual = SimpleNamespace(write=lambda kind, code, pressed: events.append((code, pressed)),
                                           syn=lambda: None)
        driver.evdev = SimpleNamespace(ecodes=ec)
        with patch("app.wayland_input.sleep"):
            driver.replace(3)
        self.assertEqual(events[0], (ec.KEY_LEFTSHIFT, 1))
        self.assertEqual(events[-1], (ec.KEY_LEFTCTRL, 0))
        self.assertEqual(events.count((ec.KEY_LEFT, 1)), 3)
        self.assertEqual(events.count((ec.KEY_V, 1)), 1)
        with self.assertRaises(ValueError):
            driver.replace(65)


if __name__ == "__main__":
    unittest.main()
