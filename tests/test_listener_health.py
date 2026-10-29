"""Capture recovery, missed key-ups, and the user's pause remain independent."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.expansion import FocusContext
from app.hotkeys import GlobalHotkeyListener
from app.input_health import HookHealth, InputSnapshot


def key(char=None, name=""):
    return SimpleNamespace(char=char, name=name, vk=ord(char) if char else None)


class HealthDetectionTests(unittest.TestCase):
    def setUp(self):
        self.health = HookHealth()
        self.health.reset(InputSnapshot(100), now=0)

    def test_hours_idle_do_not_look_like_a_dead_hook(self):
        for now in range(1, 36001):
            self.assertEqual(self.health.recovery_reason(InputSnapshot(100), now=now), "")

    def test_live_thread_without_native_events_is_detected(self):
        self.assertEqual(self.health.recovery_reason(InputSnapshot(200), now=1), "")
        self.assertEqual(self.health.recovery_reason(InputSnapshot(200), now=2), "input")

    def test_normal_keyboard_mouse_and_injected_activity_do_not_rearm(self):
        for now in range(1, 31):
            self.health.observe("keyboard" if now % 2 else "mouse", now * 200)
            self.assertEqual(self.health.recovery_reason(InputSnapshot(now * 200), now=now), "")

    def test_allow_in_flight_callback_to_catch_up(self):
        self.health.recovery_reason(InputSnapshot(200), now=1)
        self.health.observe("keyboard", 200)
        self.assertEqual(self.health.recovery_reason(InputSnapshot(200), now=2), "")

    def test_tick_wrap_is_not_a_permanent_blind_spot(self):
        self.health.reset(InputSnapshot(0xFFFFFFF0), now=0)
        self.health.observe("mouse", 0xFFFFFFFE)
        self.assertEqual(self.health.recovery_reason(InputSnapshot(30), now=1), "")
        self.assertEqual(self.health.recovery_reason(InputSnapshot(31), now=2), "input")

    def test_older_input_timestamp_alone_does_not_prove_loss(self):
        for now in range(1, 5):
            self.assertEqual(self.health.recovery_reason(InputSnapshot(50), now=now), "")

    def test_suspend_and_desktop_return_rearm_even_without_input(self):
        self.assertEqual(self.health.recovery_reason(InputSnapshot(100), now=90), "resume")
        self.health.reset(InputSnapshot(100), now=90)
        self.assertEqual(self.health.recovery_reason(InputSnapshot(110, False), now=91), "")
        self.assertEqual(self.health.recovery_reason(InputSnapshot(110, True), now=92), "desktop")


class ModifierRecoveryTests(unittest.TestCase):
    def test_lost_modifier_release_does_not_disable_future_typing(self):
        for modifier in ("ctrl_l", "alt_r", "cmd", "shift_r"):
            with self.subTest(modifier=modifier):
                received = []
                listener = GlobalHotkeyListener(received.append)
                listener.update_shortcuts(["/ok"])
                listener._on_press(key(name=modifier))
                # The release happened outside our hook (e.g. lock screen).
                with patch("app.hotkeys.windows_modifiers", return_value=set()):
                    for char in "/ok":
                        listener._on_press(key(char))
                        listener._on_release(key(char))
                self.assertEqual([c.shortcut for c in received], ["/ok"])

    def test_modifier_held_before_start_is_respected(self):
        received = []
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(["/ok"])
        with patch("app.hotkeys.windows_modifiers", return_value={"ctrl_l"}):
            for char in "/ok":
                listener._on_press(key(char))
                listener._on_release(key(char))
        self.assertEqual(received, [])

    def test_pausing_discards_partial_command_and_modifiers(self):
        received = []
        listener = GlobalHotkeyListener(received.append)
        listener.update_shortcuts(["/ok"])
        listener._on_press(key(name="ctrl_l"))
        listener.set_enabled(False)
        for char in "/ok":
            listener._on_press(key(char))
            listener._on_release(key(char))
        self.assertEqual(received, [])
        listener.set_enabled(True)
        for char in "/ok":
            listener._on_press(key(char))
            listener._on_release(key(char))
        self.assertEqual([c.shortcut for c in received], ["/ok"])


class FakeListener:
    def __init__(self, **callbacks):
        self.callbacks = callbacks
        self.running = False
        self.alive = False

    def start(self):
        self.running = self.alive = True

    def stop(self):
        self.running = self.alive = False

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        pass


class ListenerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.keyboard = Mock(side_effect=FakeListener)
        self.mouse = Mock(side_effect=FakeListener)
        self.stack.enter_context(patch.dict("sys.modules", {"pynput": SimpleNamespace(
            keyboard=SimpleNamespace(Listener=self.keyboard), mouse=SimpleNamespace(Listener=self.mouse))}))
        self.stack.enter_context(patch("app.hotkeys.Thread"))
        # Estes testes exercitam o backend pynput, não o evdev do Wayland.
        self.stack.enter_context(patch("app.wayland_input.is_wayland_session", return_value=False))
        self.stack.enter_context(patch("app.hotkeys.windows_modifiers", return_value=None))
        self.snapshot = self.stack.enter_context(patch("app.hotkeys.windows_input_snapshot",
                                                     return_value=InputSnapshot(100)))
        self.stack.enter_context(patch("app.hotkeys.capture_focus", return_value=FocusContext(101, 1)))
        self.received = []
        self.states = []
        self.listener = GlobalHotkeyListener(self.received.append, self.states.append)
        self.assertTrue(self.listener.start()[0])
        self.addCleanup(self.listener.stop)
        self.listener.update_shortcuts(["/ok"])

    def type(self, text, source=None):
        source = source or self.listener._listener
        for char in text:
            source.callbacks["on_press"](key(char))
            source.callbacks["on_release"](key(char))

    def test_dead_keyboard_or_mouse_recovers_without_duplicate_expansions(self):
        for device in ("_listener", "_mouse_listener"):
            with self.subTest(device=device):
                previous = self.listener._listener
                getattr(self.listener, device).stop()
                self.listener._check_health()
                self.assertIsNot(previous, self.listener._listener)
                self.type("/ok", previous)  # Retired callbacks cannot fire.
                self.assertEqual(self.received, [])
                self.type("/ok")
                self.assertEqual(len(self.received), 1)
                self.received.clear()

    def test_click_cancels_partial_input_with_old_and_new_pynput_signatures(self):
        click = self.listener._mouse_listener.callbacks["on_click"]
        for args in ((0, 0, None, True), (0, 0, None, True, False)):
            self.type("/o")
            click(*args)
            self.type("k")
            self.assertEqual(self.received, [])
            self.assertFalse(self.listener._callback_failed)
        self.type("/ok")
        self.assertEqual(len(self.received), 1)

    def test_missing_native_events_rearm_even_with_both_threads_alive(self):
        previous = self.listener._listener
        self.listener._health.reset(InputSnapshot(100), now=0)
        self.snapshot.return_value = InputSnapshot(200)
        with patch("app.input_health.monotonic", side_effect=[1, 2, 2]):
            self.listener._check_health()
            self.assertIs(previous, self.listener._listener)
            self.listener._check_health()
        self.assertIsNot(previous, self.listener._listener)
        self.type("/ok")
        self.assertEqual(len(self.received), 1)

    def test_paused_listener_stays_paused_through_fault_and_session_return(self):
        self.listener.set_enabled(False)
        previous = self.listener._listener
        previous.stop()
        for snapshot in (InputSnapshot(200, False), InputSnapshot(300), InputSnapshot(400)):
            self.snapshot.return_value = snapshot
            self.listener._check_health()
        self.assertIs(previous, self.listener._listener)
        self.assertEqual(self.listener.status, "paused")
        self.type("/ok", previous)
        self.assertEqual(self.received, [])
        self.listener.set_enabled(True)
        self.listener._check_health()
        self.type("/ok")
        self.assertEqual(len(self.received), 1)

    def test_user_pause_during_reconnect_wins(self):
        self.listener._listener.stop()
        original = self.keyboard.side_effect
        def create(**callbacks):
            self.listener.set_enabled(False)
            return original(**callbacks)
        self.keyboard.side_effect = create
        self.listener._check_health()
        self.assertFalse(self.listener._enabled)
        self.assertEqual(self.listener.status, "paused")
        self.type("/ok")
        self.assertEqual(self.received, [])

    def test_callback_error_does_not_escape_or_permanently_stop_listening(self):
        previous = self.listener._listener
        with patch("app.hotkeys.capture_focus", side_effect=RuntimeError("temporary provider failure")):
            previous.callbacks["on_press"](key("/"))
        self.assertTrue(self.listener._callback_failed)
        self.listener._check_health()
        self.type("/ok")
        self.assertEqual(len(self.received), 1)

    def test_temporary_installation_failure_keeps_retrying(self):
        self.listener._listener.stop()
        self.keyboard.side_effect = OSError("temporary installation failure")
        with self.assertRaises(OSError):
            self.listener._check_health()
        self.assertTrue(self.listener._enabled)
        self.keyboard.side_effect = FakeListener
        self.listener._check_health()
        self.type("/ok")
        self.assertEqual(len(self.received), 1)

    def test_recovery_discards_old_candidate_and_partial_command(self):
        self.type("/ok")
        candidate = self.received[-1]
        self.type("/o")
        self.listener._listener.stop()
        self.listener._check_health()
        self.assertFalse(self.listener.is_current(candidate))
        self.type("k")
        self.assertEqual(len(self.received), 1)
        self.type("/ok")
        self.assertEqual(len(self.received), 2)

    def test_locked_desktop_defers_reinstall_until_return(self):
        previous = self.listener._listener
        self.snapshot.return_value = InputSnapshot(100, False)
        self.listener._check_health()
        self.assertIs(previous, self.listener._listener)
        self.assertTrue(self.listener._needs_rearm)
        self.type("/ok")
        self.assertEqual(self.received, [])
        self.snapshot.return_value = InputSnapshot(100)
        self.listener._check_health()
        self.type("/ok")
        self.assertEqual(len(self.received), 1)

    def test_start_is_idempotent_and_shutdown_never_restarts(self):
        count = self.keyboard.call_count
        self.listener.start()
        self.assertEqual(self.keyboard.call_count, count)
        previous = self.listener._listener
        self.listener.stop()
        self.listener._check_health()
        self.type("/ok", previous)
        self.assertEqual(self.keyboard.call_count, count)
        self.assertEqual(self.received, [])
        self.assertEqual(self.listener.status, "stopped")
