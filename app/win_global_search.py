"""Global Ctrl+Shift+Space handled by Win32, not by character key hooks.

RegisterHotKey consumes the combination before the focused editor receives a
space. The registration belongs to the main Qt window/UI thread so WM_HOTKEY
arrives through QMainWindow.nativeEvent, even when Aurora is in the tray.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys


WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_SPACE = 0x20
QUICK_SEARCH_ID = 0xA670


class WindowsQuickSearchHotkey:
    def __init__(self, api=None):
        self._api = api
        self._hwnd = None

    @property
    def active(self) -> bool:
        return self._hwnd is not None

    def register(self, hwnd: int) -> tuple[bool, str]:
        """Must run on the Qt thread that will receive WM_HOTKEY."""
        if sys.platform != "win32":
            return False, "Registro nativo disponível apenas no Windows."
        hwnd = int(hwnd or 0)
        if not hwnd:
            return False, "Janela do AURORA indisponível para o atalho global."
        if self._hwnd == hwnd:
            return True, ""
        self.unregister()
        try:
            api = self._api if self._api is not None else ctypes.windll.user32
            api.RegisterHotKey.argtypes = [
                wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT,
            ]
            api.RegisterHotKey.restype = wintypes.BOOL
            if not api.RegisterHotKey(
                hwnd, QUICK_SEARCH_ID,
                MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_SPACE,
            ):
                return False, (
                    "Ctrl + Shift + Espaço não pôde ser reservado pelo Windows. "
                    "Verifique se outro aplicativo já está usando esse atalho."
                )
        except (OSError, AttributeError, ValueError) as exc:
            return False, f"Atalho da Pesquisa global indisponível: {exc}"
        self._hwnd = hwnd
        return True, ""

    def unregister(self) -> None:
        hwnd, self._hwnd = self._hwnd, None
        if hwnd is None:
            return
        try:
            api = self._api if self._api is not None else ctypes.windll.user32
            api.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            api.UnregisterHotKey.restype = wintypes.BOOL
            api.UnregisterHotKey(hwnd, QUICK_SEARCH_ID)
        except (OSError, AttributeError, ValueError):
            pass

    def matches(self, message) -> bool:
        """Consume only this window's registered hotkey message."""
        if self._hwnd is None or sys.platform != "win32":
            return False
        try:
            native = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            return (
                native.message == WM_HOTKEY
                and int(native.hWnd or 0) == self._hwnd
                and int(native.wParam) == QUICK_SEARCH_ID
                and (int(native.lParam) >> 16) & 0xFFFF == VK_SPACE
                and (int(native.lParam) & (MOD_CONTROL | MOD_SHIFT))
                    == MOD_CONTROL | MOD_SHIFT
            )
        except (TypeError, ValueError, OSError, OverflowError):
            return False
