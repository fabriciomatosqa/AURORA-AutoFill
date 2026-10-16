"""Bounded read-only UIA snapshots via Windows' built-in .NET bridge.

The isolated helper can be terminated if a provider hangs. Field text exists
only transiently in memory/pipes, never in diagnostics or temporary files.
"""
from __future__ import annotations

import atexit
import ctypes
import json
import os
import queue
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from threading import Lock, Thread

from .expansion import EditSnapshot, utf16_length


class AccessibilityUnavailable(ValueError):
    pass


class AccessibilityClient:
    def __init__(self):
        self._lock = Lock()
        self._call_lock = Lock()
        self._process = None
        self._responses = None
        self._starting = False
        self._closed = False

    def warm(self):
        if sys.platform != 'win32':
            return
        with self._lock:
            if self._closed or self._starting or self._process is not None:
                return
            self._starting = True
        Thread(target=self._launch, daemon=True, name='aurora-uia').start()

    def _launch(self):
        process = None
        try:
            executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            script = Path(__file__).with_name('accessibility_worker.ps1').read_text(encoding='utf-8')
            process = subprocess.Popen(
                [str(executable), '-NoLogo', '-NoProfile', '-NonInteractive', '-MTA', '-Command', script],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
            responses = queue.Queue(maxsize=2)
            with self._lock:
                if self._closed:
                    return
                self._process, self._responses = process, responses
                self._starting = False
            for line in iter(lambda: process.stdout.readline(1048577), ''):
                if len(line) > 1048576:
                    break
                try:
                    responses.put_nowait(json.loads(line))
                except (ValueError, queue.Full):
                    break
        except (OSError, ValueError):
            pass
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait()
                for stream in (process.stdin, process.stdout):
                    if stream is not None:
                        stream.close()
            with self._lock:
                if self._process is process:
                    self._process = self._responses = None
                self._starting = False

    def request(self, process_id, timeout=0.5):
        self.warm()
        if not self._call_lock.acquire(blocking=False):
            raise AccessibilityUnavailable('Leitura de acessibilidade ocupada.')
        try:
            with self._lock:
                process, responses = self._process, self._responses
            if (process is None or process.poll() is not None
                    or getattr(process, '_aurora_invalid', False)):
                raise AccessibilityUnavailable('Leitura de acessibilidade inicializando.')
            try:
                # Read the startup handshake once; do not put document data in argv.
                if not getattr(process, '_aurora_ready', False):
                    if responses.get(timeout=timeout) != {'ready': True}:
                        raise ValueError('handshake')
                    process._aurora_ready = True
                process.stdin.write(json.dumps({'process': process_id}) + '\n')
                process.stdin.flush()
                return responses.get(timeout=timeout)
            except (queue.Empty, OSError, ValueError):
                # Never reuse a late response from an older request.
                process._aurora_invalid = True
                if process.poll() is None:
                    process.kill()
                raise AccessibilityUnavailable('O campo não respondeu à leitura de acessibilidade.') from None
        finally:
            self._call_lock.release()

    def stop(self):
        with self._lock:
            self._closed = True
            process = self._process
        if process is not None and process.poll() is None:
            process.kill()


_client = AccessibilityClient()
atexit.register(_client.stop)


def decode_snapshot(context, response):
    if not isinstance(response, dict):
        raise AccessibilityUnavailable('Resposta de acessibilidade inválida.')
    if response.get('status') == 'unsupported':
        return None
    if response.get('status') != 'ok':
        raise AccessibilityUnavailable('Texto ou seleção indisponível pela acessibilidade.')
    text, start, end, identity = (response.get(key) for key in ('text', 'start', 'end', 'identity'))
    if (not isinstance(text, str) or type(start) is not int or type(end) is not int
            or not isinstance(identity, list) or len(identity) != 3
            or not all(isinstance(part, str) and part for part in identity)):
        raise AccessibilityUnavailable('Snapshot de acessibilidade inválido.')
    try:
        length = utf16_length(text)
        if not 0 <= start <= end <= length <= 65534:
            raise ValueError('range')
        # Reject endpoints inside surrogate pairs as well as malformed strings.
        from .expansion import utf16_slice
        utf16_slice(text, 0, start)
        utf16_slice(text, 0, end)
    except (ValueError, UnicodeError):
        raise AccessibilityUnavailable('Intervalo de acessibilidade inválido.') from None
    return EditSnapshot(context, text, start, end, tuple(identity))


def capture_accessible(context):
    api = ctypes.windll.user32
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    process_id = wintypes.DWORD()
    if not api.GetWindowThreadProcessId(context.window, ctypes.byref(process_id)):
        raise AccessibilityUnavailable('Janela de acessibilidade indisponível.')
    response = _client.request(process_id.value)
    snapshot = decode_snapshot(context, response)
    if snapshot is not None and snapshot.identity[0] != str(process_id.value):
        raise AccessibilityUnavailable('O destino de acessibilidade mudou.')
    return snapshot


def warm_accessibility():
    _client.warm()


def stop_accessibility():
    _client.stop()
