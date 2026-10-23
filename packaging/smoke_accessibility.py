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
$edit.Text = "/diag earlier`nSynthetic " + [char]::ConvertFromUtf32(128512) + "`nAB /diag`nTail"
$form.Controls.Add($edit)
$form.Add_Shown({
    $form.Activate(); $edit.Focus() | Out-Null
    $edit.SelectionStart = $edit.Text.LastIndexOf('/diag') + 5
    [Console]::WriteLine((@{ window = $form.Handle.ToInt64(); control = $edit.Handle.ToInt64() } | ConvertTo-Json -Compress))
})
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 60000
$timer.Add_Tick({ $form.Close() })
$timer.Start()
[System.Windows.Forms.Application]::Run($form)
'''


def launch_synthetic_editor(powershell):
    """Start just the synthetic WinForms fixture before warming the UIA helper.

    A Windows hosted runner may cold-start PowerShell/.NET slowly. We do not
    weaken the UIA assertions; failure to create the window remains fatal.
    """
    failures = []
    for attempt in range(3):
        fixture = subprocess.Popen(
            [str(powershell), '-NoProfile', '-NonInteractive', '-STA',
             '-Command', FIXTURE], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        lines = queue.Queue()
        Thread(target=lambda proc=fixture, target=lines:
               target.put(proc.stdout.readline()), daemon=True).start()
        try:
            handles = json.loads(lines.get(timeout=15))
            if (not isinstance(handles, dict)
                    or not all(type(handles.get(k)) is int and handles[k] > 0
                               for k in ('window', 'control'))):
                raise ValueError('invalid HWND values')
            return fixture, handles
        except (queue.Empty, ValueError) as exc:
            if fixture.poll() is None:
                fixture.kill()
            _, errors = fixture.communicate(timeout=5)
            # Only synthetic fixture diagnostics; never dump document data.
            failures.append(f'attempt {attempt + 1}: {type(exc).__name__}, '
                            f'exit={fixture.returncode}, stderr={errors[-240:]}')
    raise RuntimeError('Synthetic Windows editor unavailable: ' + '; '.join(failures))


def main():
    if sys.platform != 'win32':
        raise SystemExit('This smoke test requires Windows')
    from app.accessibility_context import (capture_accessible, select_accessible,
                                           warm_accessibility, stop_accessibility,
                                           AccessibilityUnavailable, SELECTION_SUBMITTED)
    from app.expansion import FocusContext, utf16_length, utf16_slice
    from app.windows_context import capture_focus
    powershell = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    fixture = None

    def select_verified_with_retry(previous, start, end):
        """Retry only cold UIA transport delays against the SAME synthetic field.

        A request can time out after a selection reached the target. Re-read the
        actual selection and identity before considering the test successful.
        Never retry if any unrelated mutation occurred; do not weaken the
        stale-selection rejection checked below.
        """
        deadline = time.monotonic() + 9
        acknowledged = False
        while True:
            if not acknowledged:
                try:
                    request_result = select_accessible(previous, start, end)
                    if request_result is SELECTION_SUBMITTED:
                        acknowledged = True
                    else:
                        return request_result
                except AccessibilityUnavailable:
                    if time.monotonic() >= deadline:
                        raise
            try:
                actual = capture_accessible(previous.context)
            except AccessibilityUnavailable:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.1)
                continue
            if (actual is None or actual.context != previous.context
                    or actual.identity != previous.identity
                    or actual.text != previous.text):
                raise AssertionError('Synthetic UIA document changed during selection')
            if (actual.start, actual.end) == (start, end):
                return actual
            if (actual.start, actual.end) != (previous.start, previous.end):
                raise AssertionError('Synthetic UIA selection changed unexpectedly')
            if time.monotonic() >= deadline:
                raise AssertionError('Synthetic UIA selection was not confirmed')
            previous = actual
            # O ACK representa uma única chamada nativa Select(); nunca
            # reenviar a seleção enquanto aguardamos o WebView refletir.
            time.sleep(.05)

    try:
        # Starting two cold PowerShell/.NET processes concurrently caused
        # intermittent fixture timeouts on GitHub-hosted Windows runners.
        fixture, handles = launch_synthetic_editor(powershell)
        warm_accessibility()
        context = FocusContext(handles['window'], handles['control'])
        api = ctypes.windll.user32
        api.SetForegroundWindow.argtypes = [wintypes.HWND]
        api.SetForegroundWindow(context.window)
        # Wait only for our synthetic editor and the cold bridge handshake.
        deadline = time.monotonic() + 20
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
        selected = select_verified_with_retry(snapshot, begin, end)
        assert utf16_slice(selected.text, selected.start, selected.end) == '/diag'
        # Check beginning, multiline/emoji prefix, and document end. The actual
        # worker must map each prefix and collapse the native selection exactly.
        current = selected
        # RichEdit exposes an implicit final paragraph terminator in UIA; it
        # cannot host a caret after that virtual character.
        last_caret = utf16_length(snapshot.text.rstrip('\r\n'))
        for offset in (0, begin, last_caret, begin):
            try:
                current = select_verified_with_retry(current, offset, offset)
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
        # Warm compiled loop: real cross-process requests, not mocks. Report
        # observed latency without inventing a universal threshold for runners.
        measurements = []
        for _ in range(8):
            started = time.perf_counter()
            actual = capture_accessible(context)
            measurements.append((time.perf_counter() - started) * 1000)
            assert actual and actual.text == snapshot.text and actual.start == actual.end == begin
        print('Warm UIA snapshots (ms):', ', '.join('%.1f' % item for item in measurements))
        print('UIA smoke passed: repeated shortcuts, direct caret, Unicode, stale request rejection')
    finally:
        stop_accessibility()
        if fixture is not None:
            if fixture.poll() is None:
                fixture.kill()
            fixture.communicate(timeout=5)


if __name__ == '__main__':
    main()
