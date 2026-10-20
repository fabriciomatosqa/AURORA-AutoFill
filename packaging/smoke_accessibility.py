"""Exercise the actual UIA bridge against an owned, synthetic Windows editor.

No application data or clipboard is read. Only the fixture's HWND is accepted.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
from threading import Thread
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURE = r'''
Add-Type -AssemblyName System.Windows.Forms
$form = New-Object System.Windows.Forms.Form
$form.Text = 'AURORA synthetic accessibility test'
$form.Width = 600; $form.Height = 300
$edit = New-Object System.Windows.Forms.RichTextBox
$edit.Dock = 'Fill'
$edit.Text = "Synthetic " + [char]::ConvertFromUtf32(128512) + "`nAB /diag`nTail"
$form.Controls.Add($edit)
$form.Add_Shown({
    $form.Activate(); $edit.Focus() | Out-Null
    $edit.SelectionStart = $edit.Text.IndexOf('/diag') + 5
    [Console]::WriteLine((@{ window = $form.Handle.ToInt64(); control = $edit.Handle.ToInt64() } | ConvertTo-Json -Compress))
})
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 15000
$timer.Add_Tick({ $form.Close() })
$timer.Start()
[System.Windows.Forms.Application]::Run($form)
'''


def main():
    if sys.platform != 'win32':
        raise SystemExit('This smoke test requires Windows')
    from app.accessibility_context import (capture_accessible, select_accessible,
                                           warm_accessibility, stop_accessibility)
    from app.expansion import FocusContext, utf16_length, utf16_slice
    from app.windows_context import capture_focus
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    fixture = subprocess.Popen([str(powershell), '-NoProfile', '-NonInteractive', '-STA',
                                '-Command', FIXTURE], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    lines = queue.Queue()
    Thread(target=lambda: lines.put(fixture.stdout.readline()), daemon=True).start()
    try:
        warm_accessibility()
        handles = json.loads(lines.get(timeout=10))
        context = FocusContext(handles['window'], handles['control'])
        api = ctypes.windll.user32
        api.SetForegroundWindow.argtypes = [wintypes.HWND]
        api.SetForegroundWindow(context.window)
        # Wait only for our synthetic editor and the cold bridge handshake.
        deadline = time.monotonic() + 6
        snapshot = None
        while time.monotonic() < deadline:
            if capture_focus() == context:
                try:
                    snapshot = capture_accessible(context)
                    if snapshot and snapshot.shortcut_range('/diag'):
                        break
                except ValueError:
                    pass
            time.sleep(0.05)
        if snapshot is None or snapshot.shortcut_range('/diag') is None:
            raise RuntimeError('Synthetic editor did not expose a usable UIA snapshot')
        begin, end = snapshot.shortcut_range('/diag')
        selected = select_accessible(snapshot, begin, end)
        assert utf16_slice(selected.text, selected.start, selected.end) == '/diag'
        # Check beginning, multiline/emoji prefix, and document end. The actual
        # worker must map each prefix and collapse the native selection exactly.
        current = selected
        # RichEdit exposes an implicit final paragraph terminator in UIA; it
        # cannot host a caret after that virtual character.
        last_caret = utf16_length(snapshot.text.rstrip('\r\n'))
        for offset in (0, begin, last_caret, begin):
            try:
                current = select_accessible(current, offset, offset)
            except ValueError:
                actual = capture_accessible(context)
                print('Synthetic selection mismatch:', offset,
                      (actual.start, actual.end) if actual else None)
                raise
            assert current.text == snapshot.text and current.start == current.end == offset
        try:
            select_accessible(snapshot, 0, 0)  # stale original selection
        except ValueError:
            pass
        else:
            raise AssertionError('Stale selection was accepted')
        print('UIA smoke passed: exact shortcut selection, direct caret, Unicode, stale request rejection')
    finally:
        stop_accessibility()
        if fixture.poll() is None:
            fixture.kill()
        fixture.communicate(timeout=5)


if __name__ == '__main__':
    main()
