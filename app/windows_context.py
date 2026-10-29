"""Bounded Win32/UIA context queries and verified selection; no clipboard access.

Edit messages are used only for Edit/RichEdit controls. Chromium/WebView editors
use UI Automation; cursor operations can request it on other custom controls.
Snapshots are transient and never logged or persisted.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from .expansion import EditSnapshot, FocusContext
from .accessibility_context import (AccessibilityUnavailable, SELECTION_SUBMITTED, capture_accessible,
                                    select_accessible, warm_accessibility, stop_accessibility)

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


def restore_focus(context: FocusContext) -> bool:
    """Return to the captured editor, including its child HWND, after a dialog."""
    if sys.platform != 'win32' or not context.window or not context.control:
        return False
    if capture_focus() == context:
        return True
    api = _api()
    api.IsWindow.argtypes = [wintypes.HWND]
    api.IsChild.argtypes = [wintypes.HWND, wintypes.HWND]
    api.SetForegroundWindow.argtypes = [wintypes.HWND]
    api.SetFocus.argtypes = [wintypes.HWND]
    api.SetFocus.restype = wintypes.HWND
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    api.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    if (not api.IsWindow(context.window) or not api.IsWindow(context.control)
            or context.window != context.control and not api.IsChild(context.window, context.control)):
        return False
    thread = api.GetWindowThreadProcessId(context.control, None)
    ctypes.windll.kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    current = ctypes.windll.kernel32.GetCurrentThreadId()
    attached = False
    try:
        api.SetForegroundWindow(context.window)
        if api.GetForegroundWindow() != context.window:
            return False
        if thread != current:
            attached = bool(api.AttachThreadInput(current, thread, True))
            if not attached:
                return False
        api.SetFocus(context.control)
    finally:
        if attached:
            api.AttachThreadInput(current, thread, False)
    return capture_focus() == context


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
        if not accessibility and not class_name.startswith(('chrome_', 'webview')):
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


def select_text_range(snapshot: EditSnapshot, start: int, end: int) -> EditSnapshot:
    """Select a validated range once; no arrow keys, clicks or clipboard edits."""
    from .expansion import utf16_length, utf16_slice
    if capture_focus() != snapshot.context:
        raise ContextUnavailable('O foco mudou antes da seleção.')
    if not 0 <= start <= end <= utf16_length(snapshot.text):
        raise ContextUnavailable('Intervalo de seleção inválido.')
    utf16_slice(snapshot.text, 0, start)
    utf16_slice(snapshot.text, 0, end)
    if snapshot.identity:
        try:
            result = select_accessible(snapshot, start, end)
        except AccessibilityUnavailable as exc:
            raise ContextUnavailable(str(exc)) from exc
    else:
        current = capture_edit(snapshot.context)
        if current != snapshot:
            raise ContextUnavailable('O campo mudou antes da seleção.')
        try:
            _message(_api(), snapshot.context.control, 0xB1, start, end)  # EM_SETSEL
        except OSError as exc:
            raise ContextUnavailable(str(exc)) from exc
        result = capture_edit(snapshot.context)
    if result is SELECTION_SUBMITTED:
        # ACK não equivale a seleção confirmada: quem chamou deverá ler
        # o campo após estabilização e conferir texto, foco e intervalo.
        if capture_focus() != snapshot.context:
            raise ContextUnavailable('O foco mudou após solicitar a seleção.')
        return result
    if (capture_focus() != snapshot.context or result is None or result.text != snapshot.text
            or result.identity != snapshot.identity or (result.start, result.end) != (start, end)):
        raise ContextUnavailable('O campo não confirmou a posição solicitada.')
    return result


def set_caret(snapshot: EditSnapshot, offset: int) -> EditSnapshot:
    return select_text_range(snapshot, offset, offset)


class FocusMonitor:
    """Invalidates history even if foreground/focus changes away and then back."""
    def __init__(self, changed):
        self._hooks = []
        self._callback = None
        self._changed = changed
        self._last_focus = capture_focus()
        if sys.platform != "win32":
            return
        warm_accessibility()
        api = ctypes.windll.user32
        callback_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD,
                                         wintypes.HWND, wintypes.LONG, wintypes.LONG,
                                         wintypes.DWORD, wintypes.DWORD)
        self._callback = callback_type(
            lambda _hook, event, window, *_: self._handle_event(event, window))
        api.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE,
                                      callback_type, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        api.SetWinEventHook.restype = wintypes.HANDLE
        for event in (3, 0x8005):  # EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_FOCUS
            hook = api.SetWinEventHook(event, event, None, self._callback, 0, 0, 0)
            if hook:
                self._hooks.append(hook)

    def _handle_event(self, event, window):
        current = capture_focus()
        # Chromium/WebView providers can announce focus again for the same
        # field while processing a paste or UIA selection. A duplicate event
        # must not cancel that operation. Real changes and away/back events do.
        changed_window = event == 3 and window and window != self._last_focus.window
        if changed_window or current != self._last_focus:
            self._changed()
        self._last_focus = current

    def stop(self):
        stop_accessibility()
        if self._hooks:
            api = ctypes.windll.user32
            api.UnhookWinEvent.argtypes = [wintypes.HANDLE]
            for hook in self._hooks:
                api.UnhookWinEvent(hook)
            self._hooks.clear()
