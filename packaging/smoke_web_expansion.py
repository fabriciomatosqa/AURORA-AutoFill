"""Real Windows SendInput/clipboard against disposable Chromium editors.

Exercises contenteditable and iframe editors, not a Teams account or a public
site. UIA is deliberately unavailable; copy proof must guard the only paste.
"""
import json
import os
from pathlib import Path
import sys
import time
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    if sys.platform != "win32":
        raise SystemExit("This smoke test requires Windows")
    os.environ["QT_QPA_PLATFORM"] = "windows"
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"
    from PySide6.QtCore import Qt
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWidgets import QApplication
    from app.clipboard_content import clone_mime
    from app.expansion import ExpansionCandidate, ExpansionOperation
    from app.ui import AutoFillWindow
    from app.windows_context import capture_focus

    app = QApplication([])
    view = QWebEngineView()
    view.resize(800, 500)
    view.setWindowTitle("AURORA synthetic Chromium expansion test")
    clipboard = app.clipboard()
    original = clone_mime(clipboard.mimeData())

    def wait(predicate, seconds=8):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError("Synthetic Chromium operation timed out")
            app.processEvents()
            time.sleep(.005)

    def js(source):
        result = []
        view.page().runJavaScript(source, lambda value: result.append(value))
        wait(lambda: bool(result))
        return result[0]

    try:
        loaded = []
        view.loadFinished.connect(lambda ok: loaded.append(ok))
        view.setHtml("<html><body><div id='editor' contenteditable='true'></div>"
                     "<iframe id='frame' srcdoc=\"<div id='editor' contenteditable='true'></div>\">"
                     "</iframe></body></html>")
        view.show()
        view.activateWindow()
        view.raise_()
        view.setFocus(Qt.OtherFocusReason)
        wait(lambda: bool(loaded))
        assert loaded[-1], "Synthetic page did not load"
        wait(lambda: capture_focus().window == int(view.winId()))
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
            assert context.window == int(view.winId()) and context.control
            clipboard.setText("synthetic original clipboard")
            candidate = ExpansionCandidate(len(report) + 1, shortcut, 0, context)
            host._candidate_valid = lambda c: capture_focus() == c.context
            host._active_candidate = candidate
            operation = ExpansionOperation(candidate, None, "Resposta 😀", 0,
                                           rich_html="<b>Resposta 😀</b>" if rich else "",
                                           keyboard_verify=True, teams_web_html=framed and rich)
            host._expansion_operation = operation
            # Permit only our owned test HWND. python.exe is intentionally not
            # added to production's supported-app list.
            from unittest.mock import patch
            with patch("app.ui.supports_verified_copy",
                       side_effect=lambda c: c == context and capture_focus() == context):
                host._submit_expansion(operation)
                wait(lambda: host._expansion_operation is None and host._clipboard_lease is None)
            actual = js("(() => { const e=(" + doc + ").getElementById('editor');"
                        "return JSON.stringify({text:e.textContent,html:e.innerHTML,pastes:window.pastes,"
                        "pasteHTML:window.pasteHTML,pasteTypes:window.pasteTypes});})()")
            actual = json.loads(actual)
            assert actual["text"] == (initial if mismatch else prefix + "Resposta 😀 tail"), actual
            assert actual["pastes"] == (0 if mismatch else 1), actual
            if rich and not mismatch:
                bold = js("(() => { const e=(" + doc + ").getElementById('editor');"
                          "return Array.from(e.querySelectorAll('*')).some(n=>"
                          "Number(n.ownerDocument.defaultView.getComputedStyle(n).fontWeight)>=700);})()")
                if not bold:
                    failures.append({"iframe": framed, **actual})
            assert clipboard.text() == "synthetic original clipboard"
            report.append({"iframe": framed, "rich": rich, "mismatch": mismatch,
                           "pastes": actual["pastes"]})
        print("Chromium native expansion passed:", json.dumps(report))
        assert not failures, failures
    finally:
        clipboard.setMimeData(original)
        app.processEvents()
        view.close()


if __name__ == "__main__":
    main()
