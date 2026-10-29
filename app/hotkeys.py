"""Monitor em memória para detectar atalhos em aplicativos externos.

O buffer contém no máximo 64 caracteres, não é gravado em disco nem enviado à rede.
No Linux, pynput exige sessão X11; Wayland não suporta esta integração global.
"""
from __future__ import annotations

from threading import Event, RLock, Thread, Timer, current_thread
from typing import Callable
import os
import sys
from time import monotonic

from .expansion import ExpansionCandidate
from .core import shortcut_key
from .windows_context import capture_focus
from .input_health import CHECK_INTERVAL, HookHealth, windows_input_snapshot, windows_modifiers

# Only our events are ignored; injected events from other tools are still input.
INJECTION_TAG = 0xA6700000 | (os.getpid() & 0xFFFF)

# Uma entrada curta como /1 pode também iniciar /10, /11...
# Aguarda brevemente a próxima tecla antes de confirmar o comando curto.
AMBIGUOUS_SHORTCUT_PAUSE = 0.22


class ShortcutMatcher:
    """Separado da UI para testes automatizados, sem capturar caracteres persistentes."""

    def __init__(self, shortcuts: list[str] | None = None):
        self._lock = RLock()
        self._shortcuts: set[str] = set()
        self._prefixes: set[str] = set()
        self._buffer = ""
        self.configure(shortcuts or [])

    def configure(self, shortcuts: list[str]) -> None:
        # Compila uma vez o índice dos comandos. O hook de teclado não deve
        # varrer toda a lista (nem carregar imagens) a cada caractere digitado.
        with self._lock:
            self._shortcuts = {shortcut_key(shortcut) for shortcut in shortcuts}
            self._prefixes = {shortcut[:end]
                              for shortcut in self._shortcuts
                              for end in range(1, len(shortcut))}
            self._buffer = ""

    def feed(self, character: str | None, key_name: str = "") -> str | None:
        with self._lock:
            if key_name == "backspace":
                # Corrigir /bomdiq -> /bomdia deve disparar sem espaço ou Enter.
                self._buffer = self._buffer[:-1]
                return None
            if key_name in {"enter", "tab", "esc", "delete", "left", "right", "up", "down", "home", "end"}:
                self._buffer = ""
                return None
            if not character or len(character) != 1 or character in "\r\n\t":
                return None
            self._buffer = (self._buffer + character)[-64:]
            # Todos os comandos válidos começam em / e não têm outra barra.
            # Buscar somente a sequência após a última barra evita trabalho
            # proporcional ao número de atalhos cadastrados.
            pos = self._buffer.rfind("/")
            if pos < 0:
                return None
            typed = self._buffer[pos:]
            if character == " ":
                candidate = typed[:-1]
                if shortcut_key(candidate) in self._shortcuts:
                    self._buffer = ""
                    return typed
                return None
            lowered = shortcut_key(typed)
            if lowered in self._shortcuts and lowered not in self._prefixes:
                self._buffer = ""
                return typed
            return None

    def current_prefix(self) -> str:
        """Compatibilidade: as antigas dicas começavam após dois caracteres."""
        with self._lock:
            pos = self._buffer.rfind("/")
            return self._buffer[pos:] if pos >= 0 and len(self._buffer) - pos >= 3 else ""

    def suggestion_prefix(self) -> str:
        """Menu começa em / e não permanece aberto após espaço ou pontuação."""
        with self._lock:
            pos = self._buffer.rfind("/")
            if pos < 0:
                return ""
            typed = self._buffer[pos:]
            return typed if (1 <= len(typed) <= 31
                             and all(not char.isspace() for char in typed)
                             and self.has_matches(typed)) else ""

    def has_matches(self, prefix: str) -> bool:
        """Only a memory predicate; keyboard hooks never query SQLite."""
        lowered = shortcut_key(prefix)
        return bool(lowered and
                    (lowered in self._shortcuts or lowered in self._prefixes))

    def ambiguous_exact(self) -> str | None:
        """Atalho completo que também é prefixo de outro; sem confirmação ainda."""
        with self._lock:
            pos = self._buffer.rfind("/")
            if pos < 0:
                return None
            typed = self._buffer[pos:]
            normalized = shortcut_key(typed)
            return typed if normalized in self._shortcuts and normalized in self._prefixes else None

    def consume_ambiguous(self, shortcut: str) -> bool:
        """Confirma somente a sequência intacta após uma pausa sem novas teclas."""
        with self._lock:
            pos = self._buffer.rfind("/")
            if (pos < 0 or self._buffer[pos:] != shortcut
                    or shortcut_key(shortcut) not in self._shortcuts
                    or shortcut_key(shortcut) not in self._prefixes):
                return False
            self._buffer = ""
            return True

    def clear(self) -> None:
        with self._lock:
            self._buffer = ""


class GlobalHotkeyListener:
    def __init__(self, on_trigger: Callable[[ExpansionCandidate], None],
                 on_state: Callable[[str], None] | None = None,
                 on_quick_search=None, on_prefix=None,
                 on_suggestion_state=None, on_navigation=None):
        self._on_trigger = on_trigger
        self._on_state = on_state
        self._on_quick_search = on_quick_search
        self._on_prefix = on_prefix
        self._on_suggestion_state = on_suggestion_state
        self._on_navigation = on_navigation
        self._suggestions_enabled = False
        self._visible_suggestion_prefix = ""
        self._visible_suggestion_context = None
        self._suppressed_nav_keys: set[int] = set()
        self._matcher = ShortcutMatcher()
        self._listener = None
        self._mouse_listener = None
        self._enabled = True
        self._keyboard = None
        self._pending = None
        self._pending_key = None
        self._modifiers: set[str] = set()
        self._state_lock = RLock()
        self._revision = 0
        self._latest_id = 0
        self._claimed_id = 0
        self._context = None
        self._ambiguity_timer = None
        self._ambiguity_token = 0
        self._lifecycle_lock = RLock()
        self._running = False
        self._generation = 0
        self._supervisor = None
        self._wake = Event()
        self._needs_rearm = False
        self._callback_failed = False
        self._health = HookHealth()
        self._status = "stopped"

    def update_shortcuts(self, shortcuts: list[str]) -> None:
        # Compile outside the hook's lock; large catalogs must not hold up
        # Windows' message loop long enough for the OS to remove its hook.
        matcher = ShortcutMatcher(shortcuts)
        with self._state_lock:
            self.invalidate()
            self._matcher = matcher

    def _cancel_ambiguity(self) -> None:
        """Chamado sempre com _state_lock; invalida também callback já agendado."""
        self._ambiguity_token += 1
        timer, self._ambiguity_timer = self._ambiguity_timer, None
        if timer is not None:
            timer.cancel()

    def invalidate(self) -> None:
        with self._state_lock:
            self._cancel_ambiguity()
            self._revision += 1
            self._pending = self._pending_key = None
            self._context = None
            self._matcher.clear()
            self._visible_suggestion_prefix = ""
            self._visible_suggestion_context = None
            if self._on_suggestion_state is not None:
                self._on_suggestion_state(("", self._context))

    def is_current(self, candidate: ExpansionCandidate, *, require_fresh: bool = True) -> bool:
        with self._state_lock:
            # Freshness prevents stale shortcuts from starting new edits. Once
            # paste was sent, confirmation may take longer in web editors;
            # revision, identity and focus checks must still be enforced.
            return (self._enabled and candidate.revision == self._revision
                    and candidate.identifier == self._latest_id
                    and (not require_fresh or monotonic() - candidate.created <= 1.5))

    def claim(self, candidate: ExpansionCandidate) -> bool:
        with self._state_lock:
            if not self.is_current(candidate) or self._claimed_id == candidate.identifier:
                return False
            self._claimed_id = candidate.identifier
            return True

    def set_suggestions_enabled(self, enabled: bool) -> None:
        """Opt-in: never intercept navigation when suggestion mode is off."""
        with self._state_lock:
            self._suggestions_enabled = bool(enabled)
            if not enabled:
                self._visible_suggestion_prefix = ""
                self._visible_suggestion_context = None

    def set_suggestion_visible(self, prefix: str, context) -> None:
        """UI acknowledgement; stale popups never claim keyboard keys."""
        with self._state_lock:
            if (self._enabled and self._suggestions_enabled and
                    prefix == self._matcher.suggestion_prefix() and
                    context == self._context):
                self._visible_suggestion_prefix = prefix
                self._visible_suggestion_context = context
            else:
                self._visible_suggestion_prefix = ""
                self._visible_suggestion_context = None

    def choose_suggestion(self, prefix: str, shortcut: str, context):
        """Convert a partial abbreviation into a normal, verified candidate."""
        with self._state_lock:
            if (not self._enabled or not self._suggestions_enabled or
                    not prefix or prefix != self._visible_suggestion_prefix or
                    prefix != self._matcher.suggestion_prefix() or
                    context != self._context or capture_focus() != context or
                    not shortcut_key(shortcut).startswith(shortcut_key(prefix))):
                return None
            self._cancel_ambiguity()
            self._matcher.clear()
            self._visible_suggestion_prefix = ""
            self._visible_suggestion_context = None
            self._revision += 1
            self._latest_id += 1
            return ExpansionCandidate(self._latest_id, prefix, self._revision,
                                      context, monotonic(), shortcut)

    def dismiss_suggestions(self, prefix: str, context) -> None:
        with self._state_lock:
            if prefix == self._visible_suggestion_prefix and context == self._context:
                self._visible_suggestion_prefix = ""
                self._visible_suggestion_context = None
                self._matcher.clear()
                self._revision += 1

    def set_enabled(self, enabled: bool) -> None:
        with self._state_lock:
            self._enabled = bool(enabled)
            self.invalidate()
            self._modifiers.clear()
            if enabled and self._running:
                self._needs_rearm = True
        self._report_state("recovering" if enabled and self._running else "paused")
        self._wake.set()

    def _report_state(self, state: str) -> None:
        if self._status == state:
            return
        self._status = state
        if self._on_state is not None:
            try:
                self._on_state(state)
            except Exception:
                pass

    @property
    def status(self) -> str:
        return self._status

    def _dispatch(self, generation: int, callback, *args) -> None:
        with self._state_lock:
            if (generation != self._generation or not self._running
                    or not self._enabled or self._needs_rearm):
                return
            try:
                callback(*args)
            except Exception:
                # A provider/key translation error must not permanently kill
                # pynput's listener. Invalidate this input and rearm separately.
                self.invalidate()
                self._callback_failed = True
                self._wake.set()

    def _native_filter(self, generation: int, device: str, message, data):
        if generation != self._generation:
            return False
        self._health.observe(device, int(data.time))
        return self._win32_event_filter(message, data) if device == "keyboard" else True

    def _win32_event_filter(self, message, data):
        if int(data.dwExtraInfo or 0) == INJECTION_TAG:
            return False
        vk = int(getattr(data, "vkCode", 0))
        if vk not in (0x26, 0x28, 0x09, 0x0D, 0x1B):
            return True
        down = int(message) in (0x0100, 0x0104)
        up = int(message) in (0x0101, 0x0105)
        if not (down or up):
            return True
        listener = self._listener
        if listener is None or not callable(getattr(listener, "suppress_event", None)):
            return True
        with self._state_lock:
            # Suppress paired key-up, including after Tab/Enter closes the UI.
            if up:
                if vk not in self._suppressed_nav_keys:
                    return True
                self._suppressed_nav_keys.discard(vk)
                listener.suppress_event()
                return False
            if (not self._enabled or not self._suggestions_enabled or
                    not self._running or self._needs_rearm or
                    any(not name.startswith("shift") for name in self._modifiers) or
                    not self._visible_suggestion_prefix or
                    self._visible_suggestion_prefix != self._matcher.suggestion_prefix() or
                    self._context != self._visible_suggestion_context or
                    capture_focus() != self._context or
                    not self._on_navigation):
                return True
            name = {0x26: "up", 0x28: "down", 0x09: "tab",
                    0x0D: "enter", 0x1B: "escape"}[vk]
            prefix, context = self._visible_suggestion_prefix, self._context
            self._suppressed_nav_keys.add(vk)
            self._on_navigation((name, prefix, context))
            # pynput raises SuppressException by design, handled by its hook.
            listener.suppress_event()
            return False

    def _on_click(self, _x, _y, _button, pressed):
        if pressed:
            self.invalidate()

    def start(self) -> tuple[bool, str]:
        import sys
        from .wayland_input import is_wayland_session, diagnose_wayland
        if is_wayland_session():
            problem = diagnose_wayland()
            if problem:
                return False, problem
        try:
            with self._lifecycle_lock:
                if self._running:
                    return True, "Atalhos globais ativados"
                self._running = True
                self._enabled = True
                self._install_hooks()
                self._supervisor = Thread(target=self._supervise, name="AuroraInputHealth", daemon=True)
                self._supervisor.start()
            self._report_state("active")
            return True, "Atalhos globais ativados"
        except Exception as exc:
            self.stop()
            return False, f"Atalhos globais indisponíveis: {exc}"

    def _retire_hooks(self) -> None:
        listeners = self._listener, self._mouse_listener
        self._listener = self._mouse_listener = None
        for listener in listeners:
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        for listener in listeners:
            if listener is not None and listener is not current_thread():
                try:
                    listener.join(timeout=0.2)
                except Exception:
                    # pynput rethrows callback errors on join. The retired
                    # generation is already inert even if it cannot terminate.
                    pass

    def _install_hooks(self) -> None:
        """Only the lifecycle owner may replace listeners; never enable here."""
        from .wayland_input import is_wayland_session
        with self._state_lock:
            self._generation += 1
            generation = self._generation
            self.invalidate()
            self._modifiers.clear()
            self._needs_rearm = False
            self._callback_failed = False
            self._suppressed_nav_keys.clear()
        self._retire_hooks()
        self._health.reset(windows_input_snapshot())
        if is_wayland_session():
            from .wayland_input import WaylandInputListener
            self._keyboard = None
            self._listener = WaylandInputListener(
                lambda key: self._dispatch(generation, self._on_press, key),
                lambda key: self._dispatch(generation, self._on_release, key),
                lambda: self._dispatch(generation, self.invalidate))
            self._mouse_listener = None
        else:
            from pynput import keyboard, mouse
            self._keyboard = keyboard
            kb_args = {}
            ms_args = {}
            if sys.platform == "win32":
                kb_args["win32_event_filter"] = lambda msg, data: self._native_filter(generation, "keyboard", msg, data)
                ms_args["win32_event_filter"] = lambda msg, data: self._native_filter(generation, "mouse", msg, data)
            self._listener = keyboard.Listener(
                on_press=lambda key: self._dispatch(generation, self._on_press, key),
                on_release=lambda key: self._dispatch(generation, self._on_release, key),
                **kb_args)
            self._mouse_listener = mouse.Listener(
                on_click=lambda x, y, button, pressed, _injected=False:
                    self._dispatch(generation, self._on_click, x, y, button, pressed),
                on_scroll=lambda *_: self._dispatch(generation, self.invalidate),
                **ms_args)
        try:
            self._listener.start()
            if self._mouse_listener is not None:
                self._mouse_listener.start()
        except Exception:
            with self._state_lock:
                self._generation += 1
                self.invalidate()
            self._retire_hooks()
            raise

    def _check_health(self) -> None:
        with self._lifecycle_lock:
            if not self._running:
                return
            snapshot = windows_input_snapshot()
            if not self._enabled:
                self._health.reset(snapshot)
                return
            reason = self._health.recovery_reason(snapshot)
            # Secure desktop / lock screen: wait for our desktop to return.
            if snapshot is not None and not snapshot.desktop_available:
                with self._state_lock:
                    self._needs_rearm = True
                    self.invalidate()
                    self._modifiers.clear()
                self._report_state("recovering")
                return
            from .wayland_input import is_wayland_session
            listeners = (self._listener,) if is_wayland_session() else (self._listener, self._mouse_listener)
            if (not self._needs_rearm and not self._callback_failed and not reason
                    and all(listener is not None and listener.is_alive() and listener.running
                            for listener in listeners)):
                return
            self._report_state("recovering")
            self._install_hooks()
            self._report_state("active" if self._enabled else "paused")

    def _supervise(self) -> None:
        while self._running:
            self._wake.wait(CHECK_INTERVAL)
            self._wake.clear()
            try:
                self._check_health()
            except Exception:
                # Keep trying while enabled; a temporary failure must not
                # require the user to restart Aurora or re-enable shortcuts.
                self._report_state("recovering" if self._enabled else "paused")

    def _on_press(self, key: object) -> None:
        with self._state_lock:
            if not self._enabled:
                return
            self._cancel_ambiguity()
            self._revision += 1
            context = capture_focus()
            if self._context is not None and self._context != context:
                self._pending = self._pending_key = None
                self._matcher.clear()
            self._context = context
            self._press(key)

    def _press(self, key: object) -> None:
        name = getattr(key, "name", "")
        if name.startswith(("shift", "ctrl", "alt", "cmd")):
            self._modifiers.add(name)
            if not name.startswith("shift"):
                self._matcher.clear()
                self._pending = self._pending_key = None
            return
        if not self._enabled:
            return
        physical = windows_modifiers()
        if physical is not None:
            self._modifiers = physical
        if self._pending is not None:
            # Outra tecla chegou antes da expansão: não editar texto incerto.
            self._pending = self._pending_key = None
            self._matcher.clear()
        if name == "space" and any(m.startswith("ctrl") for m in self._modifiers) and any(
                m.startswith("shift") for m in self._modifiers):
            self._matcher.clear()
            if self._on_prefix:
                self._on_prefix("")
            if self._on_suggestion_state:
                self._on_suggestion_state(("", self._context))
            if self._on_quick_search:
                self._on_quick_search()
            return
        if any(not m.startswith("shift") for m in self._modifiers):
            return
        try:
            character = getattr(key, "char", None)
            name = getattr(key, "name", "")
            if name == "space":
                character = " "
            matched = self._matcher.feed(character, name)
            if self._on_prefix:
                self._on_prefix(self._matcher.current_prefix() if not matched else "")
            if self._on_suggestion_state:
                self._on_suggestion_state((
                    self._matcher.suggestion_prefix() if not matched else "",
                    self._context))
            if matched:
                self._pending = matched
                self._pending_key = key
        except Exception:
            # Um erro no callback não deve encerrar o aplicativo.
            self._matcher.clear()

    def _on_release(self, key: object) -> None:
        with self._state_lock:
            matched = self._release(key)
            if not matched:
                self._schedule_ambiguous_if_ready(key)
                return
            self._cancel_ambiguity()
            context = capture_focus()
            if context != self._context:
                self.invalidate()
                return
            self._latest_id += 1
            candidate = ExpansionCandidate(self._latest_id, matched, self._revision, context, monotonic())
        try:
            self._on_trigger(candidate)
        except Exception:
            self.invalidate()

    def _schedule_ambiguous_if_ready(self, key: object) -> None:
        """Não bloqueia a digitação /10 para disparar /1 prematuramente."""
        if not self._enabled or self._pending is not None or self._modifiers:
            return
        shortcut = self._matcher.ambiguous_exact()
        if not shortcut:
            return
        name = getattr(key, "name", "")
        character = getattr(key, "char", None)
        # Apenas o keyup final, uma correção por Backspace ou Shift liberado.
        # Keyups antigos (p.ex. o / soltando depois do 1) não reiniciam timer.
        if (character != shortcut[-1]
                and name != "backspace" and not name.startswith("shift")):
            return
        context = capture_focus()
        if context != self._context:
            self.invalidate()
            return
        self._cancel_ambiguity()
        token, revision = self._ambiguity_token, self._revision
        timer = Timer(AMBIGUOUS_SHORTCUT_PAUSE,
                      lambda: self._fire_ambiguous(shortcut, context, revision, token))
        timer.daemon = True
        self._ambiguity_timer = timer
        timer.start()

    def _fire_ambiguous(self, shortcut: str, context, revision: int, token: int) -> None:
        with self._state_lock:
            if (token != self._ambiguity_token or not self._enabled
                    or self._revision != revision or self._modifiers
                    or self._context != context or capture_focus() != context):
                return
            if not self._matcher.consume_ambiguous(shortcut):
                return
            self._ambiguity_timer = None
            self._ambiguity_token += 1
            self._latest_id += 1
            candidate = ExpansionCandidate(self._latest_id, shortcut, revision, context, monotonic())
        try:
            self._on_trigger(candidate)
        except Exception:
            self.invalidate()

    def _release(self, key: object) -> str | None:
        self._modifiers.discard(getattr(key, "name", ""))
        physical = windows_modifiers()
        if physical is not None:
            self._modifiers = physical
        if not self._enabled or self._pending is None:
            return
        # Keyup ends recognition; the destination still needs its own validation.
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
        return matched

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._running = False
            self.set_enabled(False)
            with self._state_lock:
                self._generation += 1
            self._retire_hooks()
        self._wake.set()
        supervisor, self._supervisor = self._supervisor, None
        if supervisor is not None and supervisor is not current_thread():
            supervisor.join(timeout=0.5)
        self._report_state("stopped")


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
        return INPUT(1, INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, INJECTION_TAG)))

    def vk_pair(vk):
        extended = 1 if vk == 0x25 else 0
        return [ev(vk, flags=extended), ev(vk, flags=KEYUP | extended)]

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


def _send_windows_paste(backspaces: int, left_moves: int = 0, *, phase: str = "all") -> None:
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
    VK_BACK, VK_CTRL, VK_V, VK_LEFT, VK_C, VK_RIGHT = 0x08, 0x11, 0x56, 0x25, 0x43, 0x27
    api = ctypes.windll.user32.SendInput
    api.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    api.restype = wintypes.UINT

    def event(vk: int, up: bool = False):
        flags = (KEYUP if up else 0) | (1 if vk in (VK_LEFT, VK_RIGHT) else 0)
        mapper = getattr(ctypes.windll.user32, 'MapVirtualKeyW', None)
        scan = (mapper(vk, 0) & 0xff) if mapper is not None else 0
        return INPUT(1, INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, INJECTION_TAG)))

    def submit(events, *, single_batch=False):
        # Replacement must not expose a selected shortcut between API calls.
        batch_size = len(events) if single_batch else 128
        for start in range(0, len(events), batch_size):
            chunk = events[start:start + batch_size]
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
    if phase == "copy":
        submit([event(VK_CTRL), event(VK_C), event(VK_C, True), event(VK_CTRL, True)],
               single_batch=True)
        return
    if phase == "collapse":
        # Right encerra a seleção preservando o texto, no fim do atalho.
        submit([event(VK_RIGHT), event(VK_RIGHT, True)], single_batch=True)
        return
    if phase == "tracked":
        if not 1 <= backspaces <= 64:
            raise ValueError("Tamanho de atalho fora do limite de substituição.")
        # Apenas o sufixo recebido pelo hook, no mesmo campo e revisão.
        # Uma chamada mantém a ordem Backspace -> Ctrl+V. Nunca repetir se
        # SendInput aceitar somente parte do lote.
        events = []
        for _ in range(backspaces):
            events.extend((event(VK_BACK), event(VK_BACK, True)))
        submit([*events, event(VK_CTRL), event(VK_V), event(VK_V, True), event(VK_CTRL, True)],
               single_batch=True)
        return
    deletion = []
    for _ in range(backspaces):
        deletion.extend((event(VK_LEFT), event(VK_LEFT, True)))
    if phase == "replace":
        if not 1 <= backspaces <= 64:
            raise ValueError("Tamanho de atalho fora do limite de substituição segura.")
        submit([event(0x10), *deletion, event(0x10, True),
                event(VK_CTRL), event(VK_V), event(VK_V, True), event(VK_CTRL, True)],
               single_batch=True)
        return
    if deletion and phase in {"all", "select"}:
        submit([event(0x10), *deletion, event(0x10, True)])
    if phase in {"all", "paste"}:
        submit((event(VK_CTRL), event(VK_V), event(VK_V, True), event(VK_CTRL, True)))
    if left_moves and phase in {"all", "move"}:
        if phase == "all":
            sleep(0.22)  # Legacy helper; the staged UI path waits for confirmation.
        movements = []
        for _ in range(left_moves):
            movements.extend((event(VK_LEFT), event(VK_LEFT, True)))
        submit(movements)


def select_previous_characters(count: int) -> None:
    import sys
    if sys.platform == "win32":
        _send_windows_paste(count, phase="select")
        return
    from pynput.keyboard import Controller, Key
    kb = Controller()
    with kb.pressed(Key.shift):
        for _ in range(count):
            kb.tap(Key.left)


def replace_tracked_shortcut(count: int) -> None:
    """Só chamar para candidato recente validado pelo hook, nunca como retry."""
    from .wayland_input import is_wayland_session, replace_wayland_shortcut
    if is_wayland_session():
        replace_wayland_shortcut(count)
        return
    import sys
    if sys.platform != 'win32':
        raise OSError('Substituição acompanhada disponível apenas no Windows ou Wayland autorizado.')
    _send_windows_paste(count, phase='tracked')


def copy_selected_text() -> None:
    """Ctrl+C nativo; só usado depois de selecionar o atalho para verificá-lo."""
    import sys
    if sys.platform != "win32":
        raise OSError("Verificação por seleção copiada disponível apenas no Windows.")
    _send_windows_paste(0, phase="copy")


def collapse_selection_to_end() -> None:
    """Desfaz a seleção temporária sem apagar ou digitar conteúdo."""
    import sys
    if sys.platform != "win32":
        return
    _send_windows_paste(0, phase="collapse")


def replace_shortcut(count: int) -> None:
    """Select and paste in one Windows input batch, with no intermediate timer."""
    import sys
    if sys.platform != "win32":
        # Preserve X11 compatibility; only Windows has the batch guarantee.
        select_previous_characters(count)
        paste_clipboard()
        return
    _send_windows_paste(count, phase="replace")


def paste_clipboard() -> None:
    import sys
    if sys.platform == "win32":
        _send_windows_paste(0, phase="paste")
        return
    from pynput.keyboard import Controller, Key
    kb = Controller()
    with kb.pressed(Key.ctrl):
        kb.tap('v')


def move_cursor_left(count: int) -> None:
    import sys
    if sys.platform == "win32":
        _send_windows_paste(0, count, phase="move")
        return
    from pynput.keyboard import Controller, Key
    kb = Controller()
    for _ in range(count):
        kb.tap(Key.left)
