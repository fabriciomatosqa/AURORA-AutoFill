"""Health of native input capture; stores timestamps, never typed content.

Windows may remove a low-level hook without terminating pynput's thread.
Compare actual input activity with the events observed by our two hooks, and
rearm after returning from another desktop or a suspended session. No synthetic
keys or mouse movements are sent to check health.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import sys
from time import monotonic


CHECK_INTERVAL = 1.0
MISSED_INPUT_GRACE = 1.0
RESUME_GAP = 6.0


@dataclass(frozen=True)
class InputSnapshot:
    last_input: int | None
    desktop_available: bool = True


class _LastInputInfo(ctypes.Structure):
    # ctypes caches pointer types. Reuse this type across every poll instead
    # of retaining a new Structure/POINTER class each second for the app's life.
    _fields_ = [("size", wintypes.UINT), ("tick", wintypes.DWORD)]


def windows_input_snapshot() -> InputSnapshot | None:
    if sys.platform != "win32":
        return None
    try:
        api = ctypes.windll.user32

        api.GetLastInputInfo.argtypes = [ctypes.POINTER(_LastInputInfo)]
        api.GetLastInputInfo.restype = wintypes.BOOL
        info = _LastInputInfo(ctypes.sizeof(_LastInputInfo), 0)
        read = api.GetLastInputInfo(ctypes.byref(info))
        tick = int(info.tick) if read else None
        api.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenInputDesktop.restype = wintypes.HANDLE
        api.CloseDesktop.argtypes = [wintypes.HANDLE]
        desktop = api.OpenInputDesktop(0, False, 1)  # DESKTOP_READOBJECTS
        if not desktop:
            return InputSnapshot(tick, False)
        try:
            api.GetUserObjectInformationW.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                                     ctypes.c_void_p, wintypes.DWORD,
                                                     ctypes.POINTER(wintypes.DWORD)]
            name = ctypes.create_unicode_buffer(256)
            size = wintypes.DWORD()
            available = (bool(api.GetUserObjectInformationW(
                desktop, 2, name, ctypes.sizeof(name), ctypes.byref(size)))
                and name.value.casefold() != "winlogon")
            return InputSnapshot(tick, available)
        finally:
            api.CloseDesktop(desktop)
    except (OSError, AttributeError):
        return None


def windows_modifiers() -> set[str] | None:
    """Use only the high (currently down) bit; key-up events can be missed."""
    if sys.platform != "win32":
        return None
    try:
        get = ctypes.windll.user32.GetAsyncKeyState
        return {name for vk, name in ((0xA0, "shift"), (0xA1, "shift_r"),
                                     (0xA2, "ctrl_l"), (0xA3, "ctrl_r"),
                                     (0xA4, "alt_l"), (0xA5, "alt_r"),
                                     (0x5B, "cmd"), (0x5C, "cmd_r"))
                if get(vk) & 0x8000}
    except (OSError, AttributeError):
        return None


def _newer(tick: int, previous: int) -> bool:
    # LASTINPUTINFO / hook timestamps wrap every ~49 days. SendInput can also
    # supply an older timestamp; such a sample alone is not evidence of loss.
    return 0 < ((tick - previous) & 0xFFFFFFFF) < 0x80000000


class HookHealth:
    def __init__(self):
        self.keyboard_tick = None
        self.mouse_tick = None
        self.reset(None)

    def reset(self, snapshot: InputSnapshot | None, *, now: float | None = None):
        self.keyboard_tick = self.mouse_tick = None
        self._baseline = snapshot.last_input if snapshot else None
        self._desktop_available = snapshot.desktop_available if snapshot else True
        self._last_poll = monotonic() if now is None else now
        self._unobserved_since = None

    def observe(self, device: str, tick: int):
        # Called inside the OS hook: one assignment, no locks, IPC or UI work.
        if device == "keyboard":
            self.keyboard_tick = tick & 0xFFFFFFFF
        else:
            self.mouse_tick = tick & 0xFFFFFFFF

    def recovery_reason(self, snapshot: InputSnapshot | None, *, now: float | None = None) -> str:
        now = monotonic() if now is None else now
        gap = now - self._last_poll
        self._last_poll = now
        if snapshot is not None:
            was_available = self._desktop_available
            self._desktop_available = snapshot.desktop_available
            if not snapshot.desktop_available:
                self._unobserved_since = None
                return ""
            if not was_available:
                return "desktop"
        if gap >= RESUME_GAP:
            return "resume"
        if snapshot is None or snapshot.last_input is None:
            return ""
        latest = snapshot.last_input
        if self._baseline is None:
            self._baseline = latest
        observed = [tick for tick in (self._baseline, self.keyboard_tick, self.mouse_tick)
                    if tick is not None]
        missing = bool(observed) and all(_newer(latest, tick) for tick in observed)
        if not missing:
            self._unobserved_since = None
        elif self._unobserved_since is None:
            self._unobserved_since = now
        elif now - self._unobserved_since >= MISSED_INPUT_GRACE:
            return "input"
        return ""
