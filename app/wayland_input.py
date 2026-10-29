"""Backend Wayland opt-in: leitura evdev e teclado virtual uinput.

Sem XWayland, sem execução como root e sem modificar permissões do sistema.
O usuário autoriza explicitamente acesso aos dispositivos de entrada. O
monitor mantém somente o buffer transitório do ShortcutMatcher (64 caracteres),
nunca grava teclas em log/disco e descarta eventos do teclado virtual AURORA.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
import re
import select
import subprocess
import sys
from threading import Event, Lock, Thread
from time import sleep, monotonic
from types import SimpleNamespace


VIRTUAL_NAME = "AURORA AutoFill Virtual Keyboard"
_DEVICE_HINT = (
    "Para utilizar atalhos no GNOME Wayland, autorize explicitamente acesso "
    "aos dispositivos /dev/input/event* (leitura) e /dev/uinput (teclado virtual). "
    "Consulte docs/linux-wayland.md. Não execute o AURORA com sudo."
)
_ACTIVE = None


def is_wayland_session(env=None, platform=None):
    platform = sys.platform if platform is None else platform
    env = os.environ if env is None else env
    return platform.startswith("linux") and (
        env.get("XDG_SESSION_TYPE", "").casefold() == "wayland" or
        bool(env.get("WAYLAND_DISPLAY")) and env.get("XDG_SESSION_TYPE", "") != "x11"
    )


def diagnose_wayland(evdev_module=None):
    """Faz verificação de permissões antes de inicializar o monitor."""
    if not is_wayland_session():
        return ""
    try:
        evdev = evdev_module or __import__("evdev")
    except ImportError:
        return "Dependência Linux evdev ausente. Reinstale o pacote AURORA para Ubuntu."
    if not os.access("/dev/uinput", os.W_OK):
        return "Teclado virtual /dev/uinput sem permissão de escrita. " + _DEVICE_HINT
    paths = evdev.list_devices()
    if not paths:
        return "Nenhum dispositivo /dev/input acessível ao usuário. " + _DEVICE_HINT
    keyboard_found = False
    for path in paths:
        try:
            device = evdev.InputDevice(path)
            try:
                keys = set(device.capabilities().get(evdev.ecodes.EV_KEY, ()))
                if {evdev.ecodes.KEY_A, evdev.ecodes.KEY_SPACE, evdev.ecodes.KEY_ENTER} <= keys:
                    keyboard_found = True
            finally:
                device.close()
        except (OSError, PermissionError):
            continue
    if not keyboard_found:
        return "Nenhum teclado físico legível foi encontrado. " + _DEVICE_HINT
    return ""


class XkbTranslator:
    """Interpreta teclas físicas com libxkbcommon e o layout GNOME configurado."""

    class Names(ctypes.Structure):
        _fields_ = [("rules", ctypes.c_char_p), ("model", ctypes.c_char_p),
                    ("layout", ctypes.c_char_p), ("variant", ctypes.c_char_p),
                    ("options", ctypes.c_char_p)]

    def __init__(self):
        path = ctypes.util.find_library("xkbcommon") or "libxkbcommon.so.0"
        lib = ctypes.CDLL(path)
        self.lib = lib
        lib.xkb_context_new.argtypes = [ctypes.c_int]
        lib.xkb_context_new.restype = ctypes.c_void_p
        lib.xkb_keymap_new_from_names.argtypes = [ctypes.c_void_p, ctypes.POINTER(self.Names), ctypes.c_int]
        lib.xkb_keymap_new_from_names.restype = ctypes.c_void_p
        lib.xkb_state_new.argtypes = [ctypes.c_void_p]
        lib.xkb_state_new.restype = ctypes.c_void_p
        lib.xkb_state_update_key.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int]
        lib.xkb_state_key_get_utf8.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_char_p, ctypes.c_size_t]
        lib.xkb_state_key_get_utf8.restype = ctypes.c_int
        lib.xkb_state_unref.argtypes = [ctypes.c_void_p]
        lib.xkb_keymap_unref.argtypes = [ctypes.c_void_p]
        lib.xkb_context_unref.argtypes = [ctypes.c_void_p]
        layout, variant = self._layout_name()
        self.context = lib.xkb_context_new(0)
        if not self.context:
            raise RuntimeError("libxkbcommon não conseguiu inicializar.")
        names = self.Names(None, None, layout.encode(), variant.encode() if variant else None, None)
        self.keymap = lib.xkb_keymap_new_from_names(self.context, ctypes.byref(names), 0)
        if not self.keymap:
            lib.xkb_context_unref(self.context)
            raise RuntimeError("Layout de teclado GNOME indisponível.")
        self.state = lib.xkb_state_new(self.keymap)
        if not self.state:
            lib.xkb_keymap_unref(self.keymap)
            lib.xkb_context_unref(self.context)
            raise RuntimeError("Estado de teclado GNOME indisponível.")

    @staticmethod
    def _layout_name():
        override = os.environ.get("AURORA_WAYLAND_LAYOUT", "")
        if override and re.fullmatch(r"[A-Za-z0-9_-]{2,32}", override):
            return override, ""
        try:
            p = subprocess.run(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"],
                               capture_output=True, text=True, timeout=1.5, check=False)
            # Exemplo: [('xkb', 'br'), ('xkb', 'us+intl')]
            match = re.search(r"\('xkb',\s*'([A-Za-z0-9_+-]+)'\)", p.stdout)
            if match:
                return (match.group(1).split("+", 1) + [""])[:2]
        except (OSError, subprocess.TimeoutExpired):
            pass
        return "us", ""

    def event(self, code, pressed):
        xkb_code = code + 8
        if pressed:
            self.lib.xkb_state_update_key(self.state, xkb_code, 1)
            buffer = ctypes.create_string_buffer(64)
            n = self.lib.xkb_state_key_get_utf8(self.state, xkb_code, buffer, len(buffer))
            if n > 0:
                return buffer.value.decode("utf-8", errors="ignore")
            return None
        self.lib.xkb_state_update_key(self.state, xkb_code, 0)
        return None

    def close(self):
        if getattr(self, "state", None):
            self.lib.xkb_state_unref(self.state)
            self.state = None
        if getattr(self, "keymap", None):
            self.lib.xkb_keymap_unref(self.keymap)
            self.keymap = None
        if getattr(self, "context", None):
            self.lib.xkb_context_unref(self.context)
            self.context = None


class WaylandInputListener:
    """Observa teclados físicos sem grab e injeta somente a expansão autorizada."""

    def __init__(self, on_press, on_release, on_activity):
        import evdev
        self.evdev = evdev
        self.on_press, self.on_release, self.on_activity = on_press, on_release, on_activity
        self.running = False
        self._stop = Event()
        self._thread = None
        self._lock = Lock()
        self._devices = {}
        self._translator = None
        self._virtual = None

    def _add_devices(self):
        ec = self.evdev.ecodes
        for path in self.evdev.list_devices():
            if path in self._devices:
                continue
            try:
                d = self.evdev.InputDevice(path)
                keys = set(d.capabilities().get(ec.EV_KEY, ()))
                is_keyboard = {ec.KEY_A, ec.KEY_SPACE, ec.KEY_ENTER} <= keys
                is_mouse = ec.BTN_LEFT in keys
                if d.name == VIRTUAL_NAME or not (is_keyboard or is_mouse):
                    d.close()
                    continue
                self._devices[path] = (d, is_keyboard)
            except (OSError, PermissionError):
                continue

    def start(self):
        global _ACTIVE
        problem = diagnose_wayland(self.evdev)
        if problem:
            raise RuntimeError(problem)
        self._translator = XkbTranslator()
        ec = self.evdev.ecodes
        try:
            self._virtual = self.evdev.UInput(
                {ec.EV_KEY: [ec.KEY_BACKSPACE, ec.KEY_LEFTSHIFT, ec.KEY_LEFT,
                             ec.KEY_LEFTCTRL, ec.KEY_V]}, name=VIRTUAL_NAME)
            self._add_devices()
            if not any(is_keyboard for _, is_keyboard in self._devices.values()):
                raise RuntimeError("Teclado físico inacessível. " + _DEVICE_HINT)
            _ACTIVE = self
            self.running = True
            self._thread = Thread(target=self._run, name="AuroraWaylandInput", daemon=True)
            self._thread.start()
        except Exception:
            self.stop()
            raise

    def _run(self):
        ec = self.evdev.ecodes
        names = {
            ec.KEY_LEFTSHIFT: "shift_l", ec.KEY_RIGHTSHIFT: "shift_r",
            ec.KEY_LEFTCTRL: "ctrl_l", ec.KEY_RIGHTCTRL: "ctrl_r",
            ec.KEY_LEFTALT: "alt_l", ec.KEY_RIGHTALT: "alt_r",
            ec.KEY_LEFTMETA: "cmd_l", ec.KEY_RIGHTMETA: "cmd_r",
            ec.KEY_BACKSPACE: "backspace", ec.KEY_ENTER: "enter",
            ec.KEY_SPACE: "space", ec.KEY_TAB: "tab", ec.KEY_ESC: "esc",
            ec.KEY_LEFT: "left", ec.KEY_RIGHT: "right",
        }
        last_scan = 0.0
        try:
            while not self._stop.is_set():
                if monotonic() - last_scan >= 3.0:
                    self._add_devices()
                    last_scan = monotonic()
                devices = [dev for dev, _ in self._devices.values()]
                if not devices:
                    self._stop.wait(.2)
                    continue
                readable, _, _ = select.select(devices, [], [], .2)
                for dev in readable:
                    try:
                        events = dev.read()
                    except OSError:
                        self._devices.pop(dev.path, None)
                        dev.close()
                        self.on_activity()
                        continue
                    for event in events:
                        if event.type != ec.EV_KEY or event.value == 2:
                            continue
                        if ec.BTN_MOUSE <= event.code < ec.BTN_JOYSTICK:
                            if event.value:
                                self.on_activity()
                            continue
                        name = names.get(event.code, "")
                        char = self._translator.event(event.code, event.value == 1)
                        key = SimpleNamespace(name=name, char=char, vk=event.code)
                        if event.value == 1:
                            self.on_press(key)
                        elif event.value == 0:
                            self.on_release(key)
        finally:
            self.running = False

    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout=None):
        if self._thread is not None and self._thread is not __import__("threading").current_thread():
            self._thread.join(timeout)

    def stop(self):
        global _ACTIVE
        self._stop.set()
        self.running = False
        if _ACTIVE is self:
            _ACTIVE = None
        with self._lock:
            if self._virtual:
                self._virtual.close()
                self._virtual = None
        for dev, _ in list(self._devices.values()):
            dev.close()
        self._devices.clear()
        if self._translator:
            self._translator.close()
            self._translator = None

    def _send(self, code, down):
        ec = self.evdev.ecodes
        self._virtual.write(ec.EV_KEY, code, int(down))
        self._virtual.syn()

    def _tap(self, code):
        self._send(code, True)
        self._send(code, False)

    def replace(self, count):
        """Seleciona os caracteres do atalho e cola uma única vez via Ctrl+V."""
        ec = self.evdev.ecodes
        if not 1 <= count <= 64:
            raise ValueError("Atalho fora do limite seguro de substituição.")
        with self._lock:
            if not self._virtual or not self.running:
                raise RuntimeError("Teclado Wayland não está ativo.")
            # O objeto é próprio e excluído da captura, impedindo loops.
            self._send(ec.KEY_LEFTSHIFT, True)
            try:
                for _ in range(count):
                    self._tap(ec.KEY_LEFT)
            finally:
                self._send(ec.KEY_LEFTSHIFT, False)
            sleep(.045)
            self._send(ec.KEY_LEFTCTRL, True)
            try:
                self._tap(ec.KEY_V)
            finally:
                self._send(ec.KEY_LEFTCTRL, False)


def replace_wayland_shortcut(count):
    if not is_wayland_session() or _ACTIVE is None or not _ACTIVE.running:
        raise RuntimeError("Monitor Wayland não está ativo; nenhuma edição enviada.")
    _ACTIVE.replace(count)
