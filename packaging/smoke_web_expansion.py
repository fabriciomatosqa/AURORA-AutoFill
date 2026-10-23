"""Real Windows SendInput/clipboard against disposable Chromium editors.

Exercises contenteditable and iframe editors, not a Teams account or a public
site. UIA is deliberately unavailable; copy proof must guard the only paste.
"""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import MethodType, SimpleNamespace
from unittest.mock import Mock
from urllib.request import urlopen

import websocket

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if sys.platform != "win32":
        raise SystemExit("This smoke test requires Windows")
    os.environ["QT_QPA_PLATFORM"] = "windows"
    from PySide6.QtWidgets import QApplication
    from app.clipboard_content import clone_mime
    from app.expansion import ExpansionCandidate, ExpansionOperation
    from app.ui import AutoFillWindow
    from app.windows_context import capture_focus

    app = QApplication([])
    clipboard = app.clipboard()
    original = clone_mime(clipboard.mimeData())
    browser = connection = None
    temporary = tempfile.TemporaryDirectory()

    def wait(predicate, seconds=8):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError("Synthetic Chromium operation timed out")
            app.processEvents()
            time.sleep(.005)

    request_id = 0
    def command(method, params=None):
        nonlocal request_id
        request_id += 1
        connection.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            result = json.loads(connection.recv())
            if result.get("id") == request_id:
                assert "error" not in result, result
                return result["result"]

    def js(source):
        result = command("Runtime.evaluate", {"expression": source, "returnByValue": True})
        assert "exceptionDetails" not in result, result
        return result["result"].get("value")

    try:
        # An external Chrome process exercises the same OS clipboard boundary
        # as the user's browser. QtWebEngine in the writer process does not.
        chrome = next((Path(root) / "Google/Chrome/Application/chrome.exe"
                       for root in (os.environ.get("PROGRAMFILES", ""),
                                    os.environ.get("PROGRAMFILES(X86)", ""))
                       if (Path(root) / "Google/Chrome/Application/chrome.exe").is_file()), None)
        assert chrome is not None, "Chrome is required on the Windows runner"
        fixture = ("<html><head><meta charset='utf-8'><title>AURORA synthetic editor</title>"
                           "</head><body><div id='editor' contenteditable='true' style='white-space:pre-wrap;min-height:120px'></div>"
                           "<iframe id='frame' srcdoc=\"<div id='editor' contenteditable='true'></div>\">"
                           "</iframe></body></html>")
        profile = Path(temporary.name) / "profile"
        browser = subprocess.Popen([str(chrome), "--user-data-dir=" + str(profile),
                                    "--remote-debugging-port=0", "--remote-allow-origins=*",
                                    "--no-first-run", "--no-default-browser-check",
                                    "--disable-background-networking", "about:blank"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port_file = profile / "DevToolsActivePort"
        wait(lambda: port_file.exists(), seconds=20)
        port = int(port_file.read_text().splitlines()[0])
        def targets():
            with urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as response:
                return json.load(response)
        def fixture_page():
            return next((t for t in targets() if t.get("url") == "about:blank"), None)
        wait(lambda: fixture_page() is not None)
        page = fixture_page()
        connection = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=8,
                                                 suppress_origin=True)
        command("Page.bringToFront")
        command("Page.navigate", {"url": "data:text/html;base64," +
                                 base64.b64encode(fixture.encode("utf-8")).decode("ascii")})
        # Accept only this owned Chrome process before sending any input.
        import ctypes
        from ctypes import wintypes
        api = ctypes.windll.user32
        api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        def owned_focus():
            context = capture_focus()
            pid = wintypes.DWORD()
            api.GetWindowThreadProcessId(context.window, ctypes.byref(pid))
            return bool(context.window and context.control and pid.value == browser.pid)
        wait(owned_focus)
        wait(lambda: js("Boolean(document.getElementById('editor') && "
                        "document.getElementById('frame')?.contentDocument?.getElementById('editor'))"),
             seconds=20)
        # Focus the renderer, rather than the browser's initial address bar.
        command("Input.dispatchMouseEvent", {"type": "mousePressed", "x": 20, "y": 20,
                                             "button": "left", "clickCount": 1})
        command("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": 20, "y": 20,
                                             "button": "left", "clickCount": 1})
        # The production stages run unchanged. Only the disposable host and
        # candidate validity are supplied here; no input/clipboard mocks.
        host = SimpleNamespace(
            _expansion_operation=None, _clipboard_lease=None,
            _clipboard_pending=False, _clipboard_revision=0,
            _active_candidate=None, _queued_candidate=None, _quitting=False,
            isActiveWindow=lambda: False, focusWidget=lambda: None,
            test_box=object(), statusBar=lambda: Mock(), _play_confirmation=Mock())
        names = ("_submit_expansion", "_begin_keyboard_verification",
                 "_confirm_keyboard_verification", "_restore_keyboard_probe",
                 "_expansion_sent", "_confirm_expansion", "_clear_failed_selection",
                 "_finish_expansion", "_resume_queued_expansion", "_restore_clipboard",
                 "_owns_clipboard", "_clipboard_sequence")
        for name in names:
            setattr(host, name, MethodType(getattr(AutoFillWindow, name), host))
        host._clone_clipboard_mime = AutoFillWindow._clone_clipboard_mime
        host._normal_text = AutoFillWindow._normal_text
        report = []
        failures = []
        for framed, rich, mismatch in ((False, False, False), (False, True, False),
                                       (True, False, False), (True, True, False),
                                       (True, True, True)):
            doc = "document.getElementById('frame').contentDocument" if framed else "document"
            prefix = "Earlier /ação\nSynthetic 😀 "
            shortcut = "/ação"
            initial = prefix + ("/other" if mismatch else shortcut) + " tail"
            caret = len((prefix + ("/other" if mismatch else shortcut)).encode("utf-16-le")) // 2
            js("(() => { const d = " + doc + "; const e = d.getElementById('editor');"
               "e.textContent = " + json.dumps(initial) + "; e.focus();"
               "const r = d.createRange(); r.setStart(e.firstChild," + str(caret) + ");"
               "r.collapse(true); const s = d.getSelection(); s.removeAllRanges(); s.addRange(r);"
               "window.pastes=0; e.onpaste=x=>{window.pastes++;"
               "window.pasteHTML=x.clipboardData.getData('text/html');"
               "window.pasteTypes=Array.from(x.clipboardData.types);}; return true; })()")
            context = capture_focus()
            assert owned_focus()
            clipboard.setText("synthetic original clipboard")
            candidate = ExpansionCandidate(len(report) + 1, shortcut, 0, context)
            host._candidate_valid = lambda c: owned_focus() and capture_focus() == c.context
            host._active_candidate = candidate
            operation = ExpansionOperation(candidate, None, "Resposta 😀", 0,
                                           rich_html="<b>Resposta 😀</b>" if rich else "",
                                           keyboard_verify=True, teams_web_html=framed and rich)
            host._expansion_operation = operation
            host._submit_expansion(operation)
            wait(lambda: host._expansion_operation is None and host._clipboard_lease is None)
            actual = js("(() => { const e=(" + doc + ").getElementById('editor');"
                        "return JSON.stringify({text:e.textContent,html:e.innerHTML,pastes:window.pastes,"
                        "pasteHTML:window.pasteHTML,pasteTypes:window.pasteTypes});})()")
            actual = json.loads(actual)
            # Chromium may preserve boundary spaces with NBSP during rich paste.
            assert actual["text"].replace("\u00a0", " ") == (
                initial if mismatch else prefix + "Resposta 😀 tail"), actual
            assert actual["pastes"] == (0 if mismatch else 1), actual
            if rich and not mismatch:
                bold = js("(() => { const e=(" + doc + ").getElementById('editor');"
                          "return Array.from(e.querySelectorAll('*')).some(n=>"
                          "Number(n.ownerDocument.defaultView.getComputedStyle(n).fontWeight)>=700);})()")
                if not bold:
                    failures.append({"iframe": framed, **actual})
            if clipboard.text() != "synthetic original clipboard":
                failures.append({"iframe": framed, "mismatch": mismatch,
                                 "clipboard": clipboard.text()})
            report.append({"iframe": framed, "rich": rich, "mismatch": mismatch,
                           "pastes": actual["pastes"]})
        print("Chromium native expansion cases:", json.dumps(report))
        assert not failures, failures
        print("Chromium native expansion passed")
    finally:
        clipboard.setMimeData(original)
        app.processEvents()
        if connection is not None:
            connection.close()
        if browser is not None:
            subprocess.run(["taskkill", "/PID", str(browser.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            browser.wait(timeout=10)
        temporary.cleanup()


if __name__ == "__main__":
    main()
