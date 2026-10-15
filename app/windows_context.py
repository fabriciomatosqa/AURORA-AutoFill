"""Bounded Win32/UIA read-only context queries; no clipboard access.

Edit messages are used only for Edit/RichEdit controls. Unknown controls expose
focus identity by default. Cursor operations may opt into UI Automation.
Snapshots are transient and never logged or persisted.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from .expansion import EditSnapshot, FocusContext
from .accessibility_context import (AccessibilityUnavailable, capture_accessible,
                                    warm_accessibility, stop_accessibility)

MAX_TEXT_UNITS = 65534  # EM_GETSEL's packed return cannot represent larger ranges.


class ContextUnavailable(ValueError):
    pass


class _GUIInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                *[(name, wintypes.HWND) for name in
                  ("active", "focus", "capture", "menu", "move", "caret")],
                ("rect", wintypes.RECT)]


def _api():
    api = ctypes.windll.user32
    api.GetForegroundWindow.restype = wintypes.HWND
    api.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(_GUIInfo)]
    api.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    api.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                      wintypes.LPARAM, wintypes.UINT, wintypes.UINT,
                                      ctypes.POINTER(ctypes.c_size_t)]
    api.SendMessageTimeoutW.restype = wintypes.LPARAM
    return api


def capture_focus() -> FocusContext:
    if sys.platform != "win32":
        return FocusContext()
    try:
        api = _api()
        info = _GUIInfo(cbSize=ctypes.sizeof(_GUIInfo))
        window = api.GetForegroundWindow()
        if not api.GetGUIThreadInfo(0, ctypes.byref(info)):
            return FocusContext(window, None)
        return FocusContext(window, info.focus)
    except (OSError, AttributeError):
        return FocusContext()


def _message(api, control, message, wparam=0, lparam=0):
    result = ctypes.c_size_t()
    if not api.SendMessageTimeoutW(control, message, wparam, lparam, 2, 40, ctypes.byref(result)):
        raise OSError("O campo não respondeu à consulta de edição.")
    return result.value


def capture_edit(context: FocusContext, *, accessibility=False) -> EditSnapshot | None:
    if sys.platform != "win32" or not context.control:
        return None
    if capture_focus() != context:
        raise ContextUnavailable("O foco mudou durante a consulta do campo.")
    api = _api()
    name = ctypes.create_unicode_buffer(128)
    if not api.GetClassNameW(context.control, name, len(name)):
        raise ContextUnavailable("Não foi possível identificar o campo de destino.")
    class_name = name.value.lower()
    if class_name != "edit" and not class_name.startswith("richedit"):
        if not accessibility:
            return None
        try:
            snapshot = capture_accessible(context)
            if capture_focus() != context:
                raise ContextUnavailable("O foco mudou durante a leitura de acessibilidade.")
            return snapshot
        except AccessibilityUnavailable as exc:
            raise ContextUnavailable(str(exc)) from exc
    try:
        length = _message(api, context.control, 0x0E)  # WM_GETTEXTLENGTH
        if length > MAX_TEXT_UNITS:
            raise ContextUnavailable("Campo maior que o limite de validação segura desta versão.")
        selection = _message(api, context.control, 0xB0)  # EM_GETSEL (no remote pointers)
        if selection & 0xFFFFFFFF == 0xFFFFFFFF:
            raise ContextUnavailable("A seleção não pode ser validada neste campo.")
        start, end = selection & 0xFFFF, (selection >> 16) & 0xFFFF
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = _message(api, context.control, 0x0D, length + 1, ctypes.addressof(buffer))
        if copied != length or end > length or capture_focus() != context:
            raise ContextUnavailable("O campo mudou durante a consulta do texto.")
        # Recheck selection: do not combine text and a caret from different edits.
        if _message(api, context.control, 0xB0) != selection:
            raise ContextUnavailable("A seleção mudou durante a consulta do texto.")
        # RichEdit caret/selection offsets count a paragraph as one CR, while
        # WM_GETTEXT exports CRLF. Keep text in the control's coordinate system.
        text = buffer.value.replace("\r\n", "\r") if class_name.startswith("richedit") else buffer.value
        return EditSnapshot(context, text, start, end)
    except OSError as exc:
        raise ContextUnavailable(str(exc)) from exc


class FocusMonitor:
    """Invalidates history even if foreground/focus changes away and then back."""
    def __init__(self, changed):
        self._hooks = []
        self._callback = None
        if sys.platform != "win32":
            return
        warm_accessibility()
        api = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD,
                                         wintypes.HWND, wintypes.LONG, wintypes.LONG,
                                         wintypes.DWORD, wintypes.DWORD)
        self._callback = callback_type(lambda *_: changed())
        api.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
                                      callback_type, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        api.SetWinEventHook.restype = wintypes.HANDLE
        for event in (3, 0x8005):  # EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_FOCUS
            hook = api.SetWinEventHook(event, event, None, self._callback, 0, 0, 0)
            if hook:
                self._hooks.append(hook)

    def stop(self):
        stop_accessibility()
        if self._hooks:
            api = ctypes.windll.user32
            api.UnhookWinEvent.argtypes = [wintypes.HANDLE]
            for hook in self._hooks:
                api.UnhookWinEvent(hook)
            self._hooks.clear()
