"""Monitor em memória para detectar atalhos em aplicativos externos.

O buffer contém no máximo 64 caracteres, não é gravado em disco nem enviado à rede.
No Linux, pynput exige sessão X11; Wayland não suporta esta integração global.
"""
from __future__ import annotations

from threading import RLock
from typing import Callable


class ShortcutMatcher:
    """Separado da UI para testes automatizados, sem capturar caracteres persistentes."""

    def __init__(self, shortcuts: list[str] | None = None):
        self._lock = RLock()
        self._shortcuts: list[str] = []
        self._buffer = ""
        self.configure(shortcuts or [])

    def configure(self, shortcuts: list[str]) -> None:
        with self._lock:
            self._shortcuts = sorted(set(shortcuts), key=len, reverse=True)
            self._buffer = ""

    def feed(self, character: str | None, key_name: str = "") -> str | None:
        with self._lock:
            if key_name == "backspace":
                self._buffer = self._buffer[:-1]
                return None
            if key_name in {"enter", "tab", "esc", "delete", "left", "right", "up", "down", "home", "end"}:
                self._buffer = ""
                return None
            if not character or len(character) != 1 or character in "\r\n\t":
                return None
            self._buffer = (self._buffer + character)[-64:]
            for shortcut in self._shortcuts:
                if self._buffer.endswith(shortcut):
                    self._buffer = ""
                    return shortcut
            return None

    def clear(self) -> None:
        with self._lock:
            self._buffer = ""


class GlobalHotkeyListener:
    def __init__(self, on_trigger: Callable[[str], None]):
        self._on_trigger = on_trigger
        self._matcher = ShortcutMatcher()
        self._listener = None
        self._enabled = True
        self._keyboard = None

    def update_shortcuts(self, shortcuts: list[str]) -> None:
        self._matcher.configure(shortcuts)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._matcher.clear()

    def start(self) -> tuple[bool, str]:
        import os
        import sys
        if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return False, "Wayland restringe atalhos globais. Use uma sessão X11/Xorg para essa função."
        try:
            from pynput import keyboard
            self._keyboard = keyboard
            self._listener = keyboard.Listener(on_press=self._on_press)
            self._listener.start()
            return True, "Atalhos globais ativados"
        except Exception as exc:
            return False, f"Atalhos globais indisponíveis: {exc}"

    def _on_press(self, key: object) -> None:
        if not self._enabled:
            return
        try:
            character = getattr(key, "char", None)
            name = getattr(key, "name", "")
            matched = self._matcher.feed(character, name)
            if matched:
                self._on_trigger(matched)
        except Exception:
            # Um erro no callback não deve encerrar o aplicativo.
            self._matcher.clear()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()


def type_backspace_and_paste(backspaces: int, cursor_left_moves: int = 0) -> None:
    """Usado no thread da UI, depois que o clipboard recebe o texto resolvido."""
    from pynput.keyboard import Controller, Key
    from time import sleep
    kb = Controller()
    for _ in range(backspaces):
        kb.press(Key.backspace)
        kb.release(Key.backspace)
        sleep(0.008)
    sleep(0.035)
    with kb.pressed(Key.ctrl):
        kb.press("v")
        kb.release("v")
    if cursor_left_moves:
        # Espera o texto ser aplicado pelo aplicativo de destino.
        sleep(0.15)
        for _ in range(min(cursor_left_moves, 10000)):
            kb.press(Key.left)
            kb.release(Key.left)


def type_backspace_and_text(backspaces: int, text: str, cursor_left_moves: int = 0) -> None:
    """Expande por eventos de teclado ordenados, sem esperar um Ctrl+V assíncrono.

    No Windows, SendInput entrega os caracteres Unicode e as setas em ordem.
    Isso evita a corrida original de colar e aguardar 150 ms, que deixava o
    marcador {{cursor}} em posições aleatórias. Em Linux/X11 usa pynput.
    """
    import sys
    if sys.platform == "win32":
        _send_windows_unicode(backspaces, text, cursor_left_moves)
        return
    from pynput.keyboard import Controller, Key
    kb = Controller()
    for _ in range(backspaces):
        kb.press(Key.backspace)
        kb.release(Key.backspace)
    kb.type(text)
    for _ in range(cursor_left_moves):
        kb.press(Key.left)
        kb.release(Key.left)


def _send_windows_unicode(backspaces: int, text: str, left_moves: int) -> None:
    """Sequencia VK_BACK, caracteres Unicode, VK_LEFT com Win32 SendInput.

    Os eventos são inseridos em sequência, inclusive quebras de linha.
    Algumas aplicações protegidas/elevadas não aceitam entradas simuladas.
    """
    import ctypes
    from ctypes import wintypes

    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]

    KEYUP, UNICODE = 0x0002, 0x0004

    def ev(vk: int = 0, scan: int = 0, flags: int = 0):
        return INPUT(1, INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))

    def vk_pair(vk):
        return [ev(vk), ev(vk, flags=KEYUP)]

    def unicode_pairs(char):
        if char == "\n":
            return vk_pair(0x0D)  # Enter, inclusive em editores multilinha
        if char == "\t":
            return vk_pair(0x09)
        # UTF-16 preserva acentos e pares substitutos de emojis no Windows.
        data = char.encode("utf-16-le")
        values = [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]
        return [event for unit in values for event in (ev(scan=unit, flags=UNICODE), ev(scan=unit, flags=UNICODE | KEYUP))]

    events = []
    for _ in range(backspaces):
        events.extend(vk_pair(0x08))
    for char in text:
        events.extend(unicode_pairs(char))
    for _ in range(left_moves):
        events.extend(vk_pair(0x25))

    user32 = ctypes.windll.user32
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    # Blocos grandes ficam rápidos, sem sleep arbitrário entre colar e mover.
    for start in range(0, len(events), 256):
        chunk = events[start:start + 256]
        packed = (INPUT * len(chunk))(*chunk)
        sent = user32.SendInput(len(chunk), packed, ctypes.sizeof(INPUT))
        if sent != len(chunk):
            raise OSError("O Windows não permitiu enviar todas as teclas simuladas.")