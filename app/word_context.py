"""Async, isolated STA bridge to the foreground Word document only.

The GUI keeps pumping Windows/OLE messages while Word reads our clipboard.
No Office preference, document file, macro, or background Word instance is opened.
"""
import atexit
import queue
import sys
from threading import Event, Thread
from time import monotonic

from .accessibility_context import AccessibilityClient

_client = AccessibilityClient('word_worker.ps1', 'word_worker.cs', 'STA')
atexit.register(_client.stop)


def warm_word():
    _client.warm()


def stop_word():
    _client.stop()


class WordRequest:
    def __init__(self):
        self.cancelled = Event()
        self.results = queue.Queue(maxsize=1)

    def poll(self):
        try:
            return self.results.get_nowait()
        except queue.Empty:
            return None


def submit_word(operation):
    pending = WordRequest()
    context = operation.candidate.context
    fields = dict(window=str(context.window), control=str(context.control),
                  shortcut=operation.candidate.shortcut, text=operation.text,
                  cursor_prefix=operation.cursor_prefix if operation.left_moves else None,
                  token=operation.lease.token.decode('ascii'))

    def run():
        sending = False
        try:
            if sys.platform != 'win32':
                raise OSError('Integração com Word disponível apenas no Windows.')
            _client.warm()
            deadline = monotonic() + 8
            while not _client.ready:
                if pending.cancelled.wait(.02):
                    pending.results.put({'status': 'cancelled'})
                    return
                if monotonic() >= deadline:
                    raise OSError('O conector do Word não iniciou.')
            if pending.cancelled.is_set():
                pending.results.put({'status': 'cancelled'})
                return
            # Exactly one mutating request. A timeout is NOT permission to retry.
            sending = True
            result = _client.request(0, timeout=5, **fields)
            pending.results.put(result if isinstance(result, dict) else {'status': 'uncertain'})
        except Exception:
            pending.results.put({'status': 'uncertain' if sending else 'unavailable'})

    Thread(target=run, name='aurora-word-paste', daemon=True).start()
    return pending
