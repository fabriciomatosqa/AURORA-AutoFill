"""Disposable engine fixture: original stages + fake desktop, no global hooks."""
import ctypes
import heapq
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QMimeData, QTextBoundaryFinder
from app import ui, hotkeys
from app.core import SnippetStore
from app.expansion import EditSnapshot, FocusContext, utf16_length, utf16_slice


def key(char=None, name=""):
    return SimpleNamespace(char=char, name=name, vk=ord(char) if char else None)


class Clipboard:
    def __init__(self):
        self.sequence = 0
        self.setText('original')

    def mimeData(self):
        return self.mime

    def text(self):
        return self.mime.text()

    def setMimeData(self, mime):
        self.mime = mime
        self.sequence += 1

    def setText(self, text):
        mime = QMimeData()
        mime.setText(text)
        self.setMimeData(mime)

    def clear(self):
        self.setMimeData(QMimeData())


class Field:
    def __init__(self, text=''):
        self.text = text
        self.caret = self.anchor = utf16_length(text)

    def insert(self, text):
        lo, hi = sorted((self.anchor, self.caret))
        self.text = utf16_slice(self.text, 0, lo) + text + utf16_slice(self.text, hi)
        self.caret = self.anchor = lo + utf16_length(text)

    def left(self, select):
        if not select and self.caret != self.anchor:
            self.caret = self.anchor = min(self.caret, self.anchor)
            return
        finder = QTextBoundaryFinder(QTextBoundaryFinder.Grapheme, self.text)
        finder.setPosition(self.caret)
        self.caret = max(0, finder.toPreviousBoundary())
        if not select:
            self.anchor = self.caret

    def backspace(self):
        if self.anchor == self.caret:
            self.left(True)
        self.insert('')


class EngineFixture:
    def __init__(self):
        self.now = 0
        self.queue = []
        self.order = 0
        self.clipboard = Clipboard()
        self.fields = {1: Field(), 2: Field('OTHER')}
        self.field_id = 1
        self.window_id = 101
        self.readable = True
        self.reject_paste = False
        self.ignore_selection = False
        self.paste_delay = 0
        self.held_modifier = False
        self.shift = self.ctrl = False
        self.api_calls = 0
        self.fail_call = None
        self.fail_prefix = 0
        self.sent = []
        self.received = []
        self.defer_signal = False
        self.status = Mock()
        self.temp = tempfile.TemporaryDirectory()
        self.store = SnippetStore(Path(self.temp.name) / 'test.db')
        self.store.seed_if_empty()
        # O /ola não é mais um modelo padrão. Testes legados criam o seu
        # próprio comando para validar os mesmos contratos do motor antigo,
        # sem depender dos modelos de primeira instalação.
        test_folder = self.store.folders()[0][0]
        self.store.save(test_folder, "Saudação para testes", "/ola",
                        "Olá! Tudo bem? Posso ajudar em alguma coisa?")
        self.listener = hotkeys.GlobalHotkeyListener(self.emit)
        self.listener.update_shortcuts([s.shortcut for s in self.store.snippets()])
        self.host = SimpleNamespace(
            store=self.store, hotkeys=self.listener, test_box=object(),
            _hotkeys_enabled=True, _quitting=False, _clipboard_pending=False,
            _active_candidate=None, _expansion_operation=None, _queued_candidate=None,
            _clipboard_lease=None, isActiveWindow=lambda: False, focusWidget=lambda: None,
            _clipboard_revision=0,
            statusBar=lambda: self.status, _play_confirmation=Mock(),
            listen_button=Mock(), tray_toggle_action=None,
            _quick_search_hotkey=SimpleNamespace(unregister=Mock(), register=Mock(return_value=(True, ""))))
        for name, value in ui.AutoFillWindow.__dict__.items():
            if name in {'_clone_clipboard_mime', '_normal_text'}:
                setattr(self.host, name, value.__func__)
            elif name.startswith(('_expand', '_expansion_succeeded', '_candidate', '_edit_snapshot', '_owns_clipboard',
                                  '_clipboard_', '_perform_expansion', '_submit_expansion', '_begin_keyboard_verification',
                                  '_begin_word_expansion', '_poll_word_expansion',
                                  '_confirm_', '_check_cursor', '_set_caret', '_clear_failed_selection', '_paste_verified_selection', '_expansion_sent', '_finish_', '_resume_', '_restore_', '_toggle_listener', '_sync_quick_search_hotkey')):
                setattr(self.host, name, MethodType(value, self.host))

    @property
    def field(self):
        return self.fields[self.field_id]

    def context(self):
        return FocusContext(self.window_id, self.field_id)

    def snapshot(self, context, *, accessibility=False):
        if not self.readable:
            return None
        return EditSnapshot(context, self.field.text, min(self.field.caret, self.field.anchor),
                            max(self.field.caret, self.field.anchor))

    def schedule(self, delay, callback):
        self.order += 1
        heapq.heappush(self.queue, (self.now + delay, self.order, callback))

    def select(self, snapshot, start, end):
        current = self.host._edit_snapshot(accessibility=bool(snapshot.identity))
        if current != snapshot:
            from app.windows_context import ContextUnavailable
            raise ContextUnavailable('Field changed')
        self.field.anchor, self.field.caret = start, end
        return EditSnapshot(snapshot.context, snapshot.text, start, end, snapshot.identity)

    def until(self, time_ms):
        while self.queue and self.queue[0][0] <= time_ms:
            self.now, _, callback = heapq.heappop(self.queue)
            callback()
        self.now = max(self.now, time_ms)

    def drain(self):
        count = 0
        while self.queue:
            self.until(self.queue[0][0])
            count += 1
            if count > 1000:
                raise AssertionError('Timer loop')

    def save(self, shortcut, content, rich_content=''):
        existing = next((s for s in self.store.snippets() if s.shortcut == shortcut), None)
        folder = self.store.folders()[0][0]
        self.store.save(folder, shortcut, shortcut, content, existing.id if existing else None, rich_content)
        self.listener.update_shortcuts([s.shortcut for s in self.store.snippets()])

    def type(self, text):
        for character in text:
            k = key(character)
            self.listener._on_press(k)
            self.field.insert(character)
            self.listener._on_release(k)

    def emit(self, candidate):
        self.received.append(candidate)
        if not self.defer_signal:
            self.host._expand_global(candidate)

    def consume(self):
        if not self.reject_paste:
            self.field.insert(self.clipboard.text())

    def send(self, count, records, size):
        self.api_calls += 1
        accepted = self.fail_prefix if self.api_calls == self.fail_call else count
        for record in list(records)[:accepted]:
            vk, flags, tag = record.u.ki.wVk, record.u.ki.dwFlags, record.u.ki.dwExtraInfo
            self.sent.append((vk, flags, tag))
            up = bool(flags & 2)
            k = key('v' if vk == 86 else None, {16: 'shift', 17: 'ctrl_l', 37: 'left'}.get(vk, ''))
            if self.listener._win32_event_filter(0, SimpleNamespace(dwExtraInfo=tag)):
                (self.listener._on_release if up else self.listener._on_press)(k)
            if vk == 16:
                self.shift = not up
            elif vk == 17:
                self.ctrl = not up
            elif vk == 37 and not up:
                # Native baseline established that unextended Left loses selection.
                self.field.left(self.shift and bool(flags & 1) and not self.ignore_selection)
            elif vk == 8 and not up:
                self.field.backspace()
            elif vk == 86 and not up and self.ctrl:
                if self.paste_delay:
                    self.schedule(self.paste_delay, self.consume)
                else:
                    self.consume()
        return accepted

    def __enter__(self):
        self.stack = ExitStack()
        # This fixture simulates Win32 input; never call a real host's X11 driver.
        self.stack.enter_context(patch('sys.platform', 'win32'))
        def dispatch(*args):
            return self.send(*args)
        api = SimpleNamespace(SendInput=dispatch, GetAsyncKeyState=lambda _: 0x8000 if self.held_modifier else 0)
        self.stack.enter_context(patch.object(ctypes, 'windll', SimpleNamespace(user32=api), create=True))
        for path in ('app.ui.capture_focus', 'app.hotkeys.capture_focus'):
            self.stack.enter_context(patch(path, side_effect=self.context))
        self.stack.enter_context(patch('app.ui.capture_edit', side_effect=self.snapshot))
        self.stack.enter_context(patch('app.ui.QApplication.clipboard', return_value=self.clipboard))
        self.stack.enter_context(patch('app.ui.materialize_clipboard'))
        self.stack.enter_context(patch('app.ui.windows_clipboard_sequence', side_effect=lambda: self.clipboard.sequence))
        self.stack.enter_context(patch('app.ui.QTimer.singleShot', side_effect=self.schedule))
        for path in ('app.ui.monotonic', 'app.hotkeys.monotonic'):
            self.stack.enter_context(patch(path, side_effect=lambda: self.now / 1000))
        self.replace = self.stack.enter_context(patch('app.ui.replace_shortcut', wraps=hotkeys.replace_shortcut))
        self.move = self.stack.enter_context(patch('app.hotkeys.move_cursor_left', wraps=hotkeys.move_cursor_left))
        self.position = self.stack.enter_context(patch('app.ui.set_caret', side_effect=lambda s, p: self.select(s, p, p)))
        self.selection = self.stack.enter_context(patch('app.ui.select_text_range', side_effect=self.select))
        return self

    def __exit__(self, *args):
        self.stack.__exit__(*args)
        self.store.close()
        self.temp.cleanup()


class EngineTestCase(unittest.TestCase):
    def setUp(self):
        self.engine = EngineFixture().__enter__()
        self.addCleanup(self.engine.__exit__, None, None, None)
        self.win = self.engine.host
        self.clipboard = self.engine.clipboard

    def expand(self, shortcut='/ola', replacement=None):
        self.engine.type(shortcut)
        self.engine.until(75)
        if replacement:
            replacement()
        self.engine.drain()
        return self.engine.replace
