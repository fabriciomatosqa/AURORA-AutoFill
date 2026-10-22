"""Destino autorizado para fallback de colagem por seleção copiada.

Essa rota não lê o documento inteiro: somente permite confirmar um trecho
selecionado, comparando-o ao atalho exato. Não é usada em campos desconhecidos
ou em janelas elevadas que não permitam identificar seu executável.
"""
from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

SAFE_EDITORS = frozenset({
    "ms-teams.exe", "teams.exe", "winword.exe", "outlook.exe", "olk.exe",
    "chrome.exe", "msedge.exe", "msedgewebview2.exe", "firefox.exe",
    "brave.exe", "opera.exe",
})


def supports_verified_copy(context) -> bool:
    if sys.platform != "win32" or not context.window or not context.control:
        return False
    try:
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        pid = wintypes.DWORD()
        if not user32.GetWindowThreadProcessId(context.window, ctypes.byref(pid)):
            return False
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return False
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if not kernel32.QueryFullProcessImageNameW(
                    handle, 0, buffer, ctypes.byref(size)):
                return False
            name = os.path.basename(buffer.value.replace("\\", "/")).casefold()
            return name in SAFE_EDITORS
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError, TypeError):
        return False


def copied_shortcut_matches(selected: str, shortcut: str) -> bool:
    """Aceita só o atalho literal, sem trim nem normalização permissiva."""
    return isinstance(selected, str) and selected == shortcut
