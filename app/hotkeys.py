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
            if character == " ":
                for shortcut in self._shortcuts:
                    if self._buffer.endswith(shortcut + " "):
                        self._buffer = ""
                        return shortcut + " "
            for shortcut in self._shortcuts:
                if self._buffer.endswith(shortcut):
                    if any(s != shortcut and s.startswith(shortcut) for s in self._shortcuts):
                        return None
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
        self._pending = None
        self._pending_key = None
        self._modifiers: set[str] = set()

    def update_shortcuts(self, shortcuts: list[str]) -> None:
        self._matcher.configure(shortcuts)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._pending = None
        self._pending_key = None
        self._matcher.clear()

    def start(self) -> tuple[bool, str]:
        import os
        import sys
        if sys.platform.startswith("linux") and os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            return False, "Wayland restringe atalhos globais. Use uma sessão X11/Xorg para essa função."
        try:
            from pynput import keyboard
            self._keyboard = keyboard
            self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
            self._listener.start()
            return True, "Atalhos globais ativados"
        except Exception as exc:
            return False, f"Atalhos globais indisponíveis: {exc}"

    def _on_press(self, key: object) -> None:
        name = getattr(key, "name", "")
        if name.startswith(("shift", "ctrl", "alt", "cmd")):
            self._modifiers.add(name)
            if not name.startswith("shift"):
                self._matcher.clear()
                self._pending = self._pending_key = None
            return
        if not self._enabled:
            return
        if self._pending is not None:
            # Outra tecla chegou antes da expansão: não editar texto incerto.
            self._pending = self._pending_key = None
            self._matcher.clear()
        if any(not m.startswith("shift") for m in self._modifiers):
            return
        try:
            character = getattr(key, "char", None)
            name = getattr(key, "name", "")
            if name == "space":
                character = " "
            matched = self._matcher.feed(character, name)
            if matched:
                self._pending = matched
                self._pending_key = key
        except Exception:
            # Um erro no callback não deve encerrar o aplicativo.
            self._matcher.clear()

    def _on_release(self, key: object) -> None:
        self._modifiers.discard(getattr(key, "name", ""))
        if not self._enabled or self._pending is None:
            return
        # A liberação da tecla é a fronteira mais segura para colar no
        # Bloco de Notas moderno: o caractere final já foi processado.
        same = key == self._pending_key
        if not same:
            same = (getattr(key, 'vk', None) is not None and
                    getattr(key, 'vk', None) == getattr(self._pending_key, 'vk', None))
        if same:
            self._pending_key = None
        if self._pending_key is not None or self._modifiers:
            return
        matched = self._pending
        self._pending = None
        self._pending_key = None
        try:
            self._on_trigger(matched)
        except Exception:
            self._matcher.clear()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()


def type_backspace_and_paste(backspaces: int, cursor_left_moves: int = 0) -> None:
    """Substitui o atalho por texto do clipboard, sem digitar letra a letra.

    Em Windows, usa SendInput para selecionar e enviar Ctrl+V; o clipboard deve
    ter sido preenchido pela GUI antes desta chamada. Em Linux/X11, pynput.
    """
    import sys
    if sys.platform == "win32":
        _send_windows_paste(backspaces, cursor_left_moves)
        return
    from pynput.keyboard import Controller, Key
    from time import sleep
    kb = Controller()
    for _ in range(backspaces):
        kb.press(Key.backspace)
        kb.release(Key.backspace)
        sleep(0.008)
    sleep(0.075)
    with kb.pressed(Key.ctrl):
        kb.press("v")
        kb.release("v")
    if cursor_left_moves:
        sleep(0.22)
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


def _send_windows_paste(backspaces: int, left_moves: int = 0) -> None:
    """Seleciona o atalho e envia Ctrl+V; falha de colagem não o apaga previamente."""
    import ctypes
    from ctypes import wintypes
    from time import sleep

    ptr = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ptr)]
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ptr)]
    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]
    class INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", INPUTUNION)]
    KEYUP = 2
    VK_BACK, VK_CTRL, VK_V, VK_LEFT = 0x08, 0x11, 0x56, 0x25
    api = ctypes.windll.user32.SendInput
    api.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    api.restype = wintypes.UINT

    def event(vk: int, up: bool = False):
        return INPUT(1, INPUTUNION(ki=KEYBDINPUT(vk, 0, KEYUP if up else 0, 0, 0)))

    def submit(events):
        for start in range(0, len(events), 128):
            chunk = events[start:start + 128]
            packed = (INPUT * len(chunk))(*chunk)
            count = api(len(chunk), packed, ctypes.sizeof(INPUT))
            if count != len(chunk):
                # Um envio parcial não deve deixar Shift/Ctrl presos.
                releases = (INPUT * 2)(event(0x10, True), event(VK_CTRL, True))
                api(2, releases, ctypes.sizeof(INPUT))
                raise OSError("O Windows não permitiu enviar as teclas simuladas (SendInput).")

    # Selecionar preserva o atalho se Ctrl+V for rejeitado pelo destino.
    # Não há Backspace nem Delete antes da inserção.
    if any(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000
           for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        raise OSError("Solte as teclas modificadoras antes de expandir.")
    deletion = []
    for _ in range(backspaces):
        deletion.extend((event(VK_LEFT), event(VK_LEFT, True)))
    if deletion:
        submit([event(0x10), *deletion, event(0x10, True)])
    submit((event(VK_CTRL), event(VK_V), event(VK_V, True), event(VK_CTRL, True)))
    if left_moves:
        sleep(0.22)
        movements = []
        for _ in range(left_moves):
            movements.extend((event(VK_LEFT), event(VK_LEFT, True)))
        submit(movements)
