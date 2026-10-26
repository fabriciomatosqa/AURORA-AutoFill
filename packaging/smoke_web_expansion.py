"""Real Windows SendInput/clipboard against disposable Chromium editors.

Exercises the real keyboard hook through the production pipeline in Chrome,
including editors that reject Shift+Left and replace Ctrl+C's payload.
Only a disposable browser profile and synthetic page are used.
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
    from PySide6.QtCore import QObject, Signal, Qt
    from app.clipboard_content import clone_mime
    from app.hotkeys import GlobalHotkeyListener
    from app.core import SnippetStore
    from app.ui import AutoFillWindow
    from app.windows_context import capture_focus

    app = QApplication([])
    clipboard = app.clipboard()
    original = clone_mime(clipboard.mimeData())
    browser = connection = listener = store = focus_monitor = None
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
        # Bind the production stages to an owned host. The real hook emits
        # candidates; there is no fabricated candidate or is_current mock.
        host = SimpleNamespace(
            _expansion_operation=None, _clipboard_lease=None,
            _clipboard_pending=False, _clipboard_revision=0,
            _active_candidate=None, _queued_candidate=None, _quitting=False,
            _hotkeys_enabled=True,
            isActiveWindow=lambda: False, focusWidget=lambda: None,
            test_box=object(), statusBar=lambda: Mock(), _play_confirmation=Mock())
        for name in AutoFillWindow.__dict__:
            if name.startswith(('_expand', '_expansion_', '_candidate', '_edit_snapshot', '_owns_clipboard',
                                '_clipboard_', '_perform_', '_submit_', '_begin_', '_poll_',
                                '_confirm_', '_restore_', '_finish_', '_resume_', '_clear_',
                                '_paste_verified_', '_check_cursor', '_set_caret')):
                setattr(host, name, MethodType(getattr(AutoFillWindow, name), host))
        host._clone_clipboard_mime = AutoFillWindow._clone_clipboard_mime
        host._normal_text = AutoFillWindow._normal_text
        class Signals(QObject):
            triggered = Signal(object)
        signals = Signals()
        signals.triggered.connect(host._expand_global, Qt.QueuedConnection)
        listener = GlobalHotkeyListener(signals.triggered.emit)
        host.hotkeys = listener
        store = SnippetStore(Path(temporary.name)/'synthetic.db')
        folder = store.create_folder('Native tests')
        host.store = store
        started, error = listener.start()
        assert started, error
        from app.windows_context import FocusMonitor
        focus_monitor = FocusMonitor(listener.invalidate)
        from app.accessibility_context import warm_accessibility, stop_accessibility
        warm_accessibility()

        # Physical virtual-key events with scan codes, intentionally untagged:
        # the production hook must observe these as the test user's typing.
        class KI(ctypes.Structure):
            _fields_=[('vk',wintypes.WORD),('scan',wintypes.WORD),('flags',wintypes.DWORD),
                      ('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
        class MI(ctypes.Structure):
            _fields_=[('x',wintypes.LONG),('y',wintypes.LONG),('data',wintypes.DWORD),
                      ('flags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
        class U(ctypes.Union):
            _fields_=[('ki',KI),('mi',MI)]
        class I(ctypes.Structure):
            _fields_=[('type',wintypes.DWORD),('u',U)]
        api.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(I),ctypes.c_int]
        api.SendInput.restype=wintypes.UINT
        api.VkKeyScanW.argtypes=[wintypes.WCHAR]
        api.VkKeyScanW.restype=ctypes.c_short
        def type_raw(text):
            assert owned_focus()
            events=[]
            def key(vk, up=False):
                return I(1,U(ki=KI(vk,api.MapVirtualKeyW(vk,0)&255,2 if up else 0,0,0)))
            for character in text:
                mapping=api.VkKeyScanW(character)
                assert mapping!=-1 and not mapping&0x600, 'Unsupported synthetic keyboard layout'
                vk=mapping&255; shifted=bool(mapping&0x100)
                if shifted:events.append(key(16))
                events.extend((key(vk),key(vk,True)))
                if shifted:events.append(key(16,True))
            data=(I*len(events))(*events)
            api.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(I),ctypes.c_int]
            assert api.SendInput(len(events),data,ctypes.sizeof(I))==len(events)

        report = []
        failures = []
        for framed, rich, mismatch in ((False, False, False), (False, True, False),
                                       (True, False, False), (True, True, False),
                                       (True, True, True)):
            doc = "document.getElementById('frame').contentDocument" if framed else "document"
            prefix = "Earlier /teste\nSynthetic 😀 "
            shortcut = "/teste"
            initial = prefix + " tail"
            caret = len(prefix.encode("utf-16-le")) // 2
            body = "Resposta colorida 😀"
            html = '<span style="color:#ff0000;background-color:#00ff00;font-family:Arial;font-size:14pt;font-weight:700">'+body+'</span>'
            prior = next((s for s in store.snippets() if s.shortcut==shortcut), None)
            store.save(folder,'Synthetic',shortcut,body,prior.id if prior else None, html if rich else '')
            listener.update_shortcuts([shortcut])
            listener.invalidate()
            js("(() => { const d = " + doc + "; const e = d.getElementById('editor');"
               + ("d.designMode='on';" if framed else "") +
               "e.textContent = " + json.dumps(initial) + "; e.focus();"
               "const r = d.createRange(); r.setStart(e.firstChild," + str(caret) + ");"
               "r.collapse(true); const s = d.getSelection(); s.removeAllRanges(); s.addRange(r);"
               "window.pastes=0;window.copies=0;"
               "e.oncopy=x=>{window.copies++;x.preventDefault();x.clipboardData.setData('text/plain','WRONG COPY');};"
               "e.onkeydown=x=>{if(x.shiftKey&&x.key==='ArrowLeft')x.preventDefault();};"
               "e.onpaste=x=>{window.pastes++;"
               "window.pasteHTML=x.clipboardData.getData('text/html');"
               "window.pasteTypes=Array.from(x.clipboardData.types);}; return true; })()")
            context = capture_focus()
            assert owned_focus()
            clipboard.setText("synthetic original clipboard")
            type_raw(shortcut + ('X' if mismatch else ''))
            if mismatch:
                deadline=time.monotonic()+.3
                wait(lambda:time.monotonic()>=deadline)
            else:
                wait(lambda: js('window.pastes')==1)
            wait(lambda: host._expansion_operation is None and host._clipboard_lease is None)
            actual = js("(() => { const e=(" + doc + ").getElementById('editor');"
                        "return JSON.stringify({text:e.textContent,html:e.innerHTML,pastes:window.pastes,"
                        "pasteHTML:window.pasteHTML,pasteTypes:window.pasteTypes,copies:window.copies});})()")
            actual = json.loads(actual)
            # Chromium may preserve boundary spaces with NBSP during rich paste.
            assert actual["text"].replace("\u00a0", " ") == (
                prefix+shortcut+'X tail' if mismatch else prefix + body+" tail"), actual
            assert actual["pastes"] == (0 if mismatch else 1), actual
            assert actual['copies']==0,actual
            if rich and not mismatch:
                bold = js("(() => { const e=(" + doc + ").getElementById('editor');"
                          "return Array.from(e.querySelectorAll('*')).some(n=>"
                          "Number(n.ownerDocument.defaultView.getComputedStyle(n).fontWeight)>=700);})()")
                if not bold:
                    failures.append({"iframe": framed, **actual})
                assert js("(() => {const e=("+doc+").getElementById('editor');return Array.from(e.querySelectorAll('*')).some(n=>{"
                          "const s=n.ownerDocument.defaultView.getComputedStyle(n);return s.color==='rgb(255, 0, 0)'&&s.backgroundColor==='rgb(0, 255, 0)';});})()"),actual
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
        if listener is not None:
            listener.stop()
        if focus_monitor is not None:
            focus_monitor.stop()
        if store is not None:
            store.close()
        if browser is not None:
            subprocess.run(["taskkill", "/PID", str(browser.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            browser.wait(timeout=10)
        temporary.cleanup()


if __name__ == "__main__":
    main()
