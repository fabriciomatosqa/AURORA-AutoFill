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
from threading import Thread
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_devtools_port(path):
    """Chrome can create this file before releasing its Windows write lock."""
    try:
        lines = path.read_text(encoding='ascii').splitlines()
        prefix='/devtools/browser/'
        if len(lines) < 2 or not lines[1].startswith(prefix) or len(lines[1])<=len(prefix):
            return None
        port = int(lines[0])
        return port if 1 <= port <= 65535 else None
    except (OSError, UnicodeError, ValueError):
        return None


def main():
    if sys.platform != "win32":
        raise SystemExit("This smoke test requires Windows")
    import websocket
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
    messages = []

    def wait(predicate, seconds=8):
        deadline = time.monotonic() + seconds
        while not predicate():
            if time.monotonic() >= deadline:
                raise AssertionError("Synthetic Chromium operation timed out; engine status: " + repr(messages[-3:]))
            app.processEvents()
            time.sleep(.005)

    request_id = 0
    def command(method, params=None):
        nonlocal request_id
        request_id += 1
        current_id = request_id
        response, errors = [], []
        def exchange():
            try:
                connection.send(json.dumps({"id": current_id, "method": method, "params": params or {}}))
                while True:
                    result = json.loads(connection.recv())
                    if result.get('id') == current_id:
                        response.append(result)
                        return
            except Exception as exc:
                errors.append(exc)
        thread=Thread(target=exchange,daemon=True)
        thread.start()
        wait(lambda:not thread.is_alive(),seconds=10)
        if errors:raise errors[0]
        result=response[0]
        assert 'error' not in result,result
        return result['result']

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
        port = None
        def port_ready():
            nonlocal port
            if browser.poll() is not None:
                raise AssertionError('Chrome exited before its DevTools port became ready')
            port = read_devtools_port(port_file)
            return port is not None
        wait(port_ready, seconds=20)
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
            test_box=object(), statusBar=lambda: SimpleNamespace(showMessage=lambda text,*_:messages.append(text)),
            _play_confirmation=Mock(), listen_button=Mock(), tray_toggle_action=None)
        for name in AutoFillWindow.__dict__:
            if name.startswith(('_expand', '_expansion_', '_candidate', '_edit_snapshot', '_owns_clipboard',
                                '_clipboard_', '_perform_', '_submit_', '_begin_', '_poll_',
                                '_confirm_', '_restore_', '_finish_', '_resume_', '_clear_',
                                '_paste_verified_', '_check_cursor', '_set_caret')):
                setattr(host, name, MethodType(getattr(AutoFillWindow, name), host))
        host._clone_clipboard_mime = AutoFillWindow._clone_clipboard_mime
        host._normal_text = AutoFillWindow._normal_text
        host._toggle_listener = MethodType(AutoFillWindow._toggle_listener, host)
        class Signals(QObject):
            triggered = Signal(object)
        signals = Signals()
        received = []
        def receive(candidate):
            received.append(candidate)
            host._expand_global(candidate)
        signals.triggered.connect(receive, Qt.QueuedConnection)
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
        def raw_key(vk, up=False):
            assert owned_focus()
            data=(I*1)(I(1,U(ki=KI(vk,api.MapVirtualKeyW(vk,0)&255,2 if up else 0,0,0))))
            api.SendInput.argtypes=[wintypes.UINT,ctypes.POINTER(I),ctypes.c_int]
            assert api.SendInput(1,data,ctypes.sizeof(I))==1

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
        cases = ((False, False, False, ""), (False, True, False, ""),
                 (True, False, False, ""), (True, True, False, ""),
                 (True, True, True, ""),
                 (False, True, False, "keyboard_stopped"),
                 (True, True, False, "mouse_stopped"),
                 (True, True, False, "hook_removed"),
                 (False, True, False, "callback_error"),
                 (True, True, False, "stale_modifier"),
                 (False, True, False, "held_shift"),
                 (True, True, False, "pause_resume"))
        for framed, rich, mismatch, fault in cases:
            doc = "document.getElementById('frame').contentDocument" if framed else "document"
            prefix = "Earlier /teste\nSynthetic 😀|"
            shortcut = "/teste"
            initial = prefix + "|tail"
            caret = len(prefix.encode("utf-16-le")) // 2
            body = "Resposta colorida 😀"
            html = '<span style="color:#ff0000;background-color:#00ff00;font-family:Arial;font-size:14pt;font-weight:700">'+body+'</span>'
            prior = next((s for s in store.snippets() if s.shortcut==shortcut), None)
            store.save(folder,'Synthetic',shortcut,body,prior.id if prior else None, html if rich else '')
            listener.update_shortcuts([shortcut])
            listener.invalidate()
            js("(() => { const d = " + doc + "; const e = " + ("d.body" if framed else "d.getElementById('editor')") + ";"
               + ("d.designMode='on';e.id='editor';e.style.whiteSpace='pre-wrap';" if framed else "") +
               "e.textContent = " + json.dumps(initial) + "; e.focus();"
               "const r = d.createRange(); r.setStart(e.firstChild," + str(caret) + ");"
               "r.collapse(true); const s = d.getSelection(); s.removeAllRanges(); s.addRange(r);"
               "window.pastes=0;window.copies=0;window.edits=[];"
               "d.onbeforeinput=x=>window.edits.push(['before',x.inputType,x.data,x.defaultPrevented]);"
               "d.oninput=x=>window.edits.push(['input',x.inputType,x.data,e.textContent]);"
               "d.oncopy=x=>{window.copies++;x.preventDefault();x.clipboardData.setData('text/plain','WRONG COPY');};"
               "d.onkeydown=x=>{if(x.shiftKey&&x.key==='ArrowLeft')x.preventDefault();};"
               "d.onpaste=x=>{window.pastes++;"
               "window.pasteText=x.clipboardData.getData('text/plain');"
               "window.pasteHTML=x.clipboardData.getData('text/html');"
               "window.pasteTypes=Array.from(x.clipboardData.types);}; return true; })()")
            # A selection in contentDocument does not activate the iframe's
            # native keyboard routing. Focus its browsing context by clicking,
            # then set the exact synthetic caret again.
            rect = json.loads(js("JSON.stringify(document.getElementById(" +
                                 ("'frame'" if framed else "'editor'") + ").getBoundingClientRect())"))
            point = {'x':rect['x']+15,'y':rect['y']+10,'button':'left','clickCount':1}
            command('Input.dispatchMouseEvent',{'type':'mousePressed',**point})
            command('Input.dispatchMouseEvent',{'type':'mouseReleased',**point})
            js("(() => {const d="+doc+";const e=d.getElementById('editor');"
               "d.defaultView.focus();e.focus();const r=d.createRange();"
               "r.setStart(e.firstChild,"+str(caret)+");r.collapse(true);"
               "const s=d.getSelection();s.removeAllRanges();s.addRange(r);return true;})()")
            assert js("document.activeElement===document.getElementById("+
                      ("'frame'" if framed else "'editor'")+")"), 'Synthetic browsing context did not gain focus'
            listener.invalidate()
            context = capture_focus()
            assert owned_focus()
            clipboard.setText("synthetic original clipboard")
            if fault:
                generation = listener._generation
                prior_received = len(received)
                if fault in {"keyboard_stopped", "mouse_stopped"}:
                    getattr(listener, "_listener" if fault == "keyboard_stopped" else "_mouse_listener").stop()
                elif fault == "hook_removed":
                    # Reproduce silent Windows removal: the Python thread
                    # remains alive, so is_alive() alone cannot fix this.
                    from pynput._util.win32 import SystemHook
                    hook = SystemHook._HOOKS[listener._listener.ident]
                    api.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
                    assert api.UnhookWindowsHookEx(hook._hook), "Could not remove owned test hook"
                    assert listener._listener.is_alive()
                    deadline = time.monotonic() + .06
                    wait(lambda: time.monotonic() >= deadline)
                    type_raw("x")  # Activity in this owned page, not a production health probe.
                elif fault == "callback_error":
                    with patch("app.hotkeys.capture_focus", side_effect=RuntimeError("synthetic transient failure")):
                        type_raw("x")
                        wait(lambda: listener._callback_failed or listener._generation > generation)
                elif fault == "stale_modifier":
                    listener._modifiers.add("ctrl_l")  # A key-up lost on another desktop.
                elif fault == "pause_resume":
                    host._toggle_listener()
                    assert not host._hotkeys_enabled
                    listener._listener.stop()
                    type_raw(shortcut)
                    deadline = time.monotonic() + 2.5
                    wait(lambda: time.monotonic() >= deadline)
                    assert listener._generation == generation, "Recovered while user paused"
                    assert len(received) == prior_received, "Expanded while user paused"
                    assert js("window.pastes") == 0
                    host._toggle_listener()
                    assert host._hotkeys_enabled
                if fault not in {"stale_modifier", "held_shift"}:
                    wait(lambda: listener._generation > generation and listener.status == "active")
                    assert len(received) == prior_received
                    assert js("window.pastes") == 0
                # Remove fault-witness input and restore the precise synthetic
                # caret before exercising a real command through the new hook.
                js("(() => {const d=" + doc + ";const e=d.getElementById('editor');"
                   "e.textContent=" + json.dumps(initial) + ";e.focus();"
                   "const r=d.createRange();r.setStart(e.firstChild," + str(caret) + ");r.collapse(true);"
                   "const s=d.getSelection();s.removeAllRanges();s.addRange(r);return true;})()")
                listener.invalidate()
            marker = len(messages)
            if fault == "held_shift":
                type_raw("/")
                raw_key(0x10)
                try:
                    type_raw("teste")
                    deadline = time.monotonic() + .15
                    wait(lambda: time.monotonic() >= deadline)
                    assert len(received) == prior_received, "Expanded before physical Shift release"
                    assert js("window.pastes") == 0
                finally:
                    raw_key(0x10, up=True)
            else:
                type_raw(shortcut + ('X' if mismatch else ''))
            if mismatch:
                deadline=time.monotonic()+.3
                wait(lambda:time.monotonic()>=deadline)
            else:
                # Do not block this GUI with a synchronous CDP call while
                # Chrome is waiting for this process to render OLE clipboard
                # formats. Observe the engine first, inspect DOM afterwards.
                wait(lambda: len(messages)>marker and host._expansion_operation is None
                     and host._clipboard_lease is None)
            wait(lambda: host._expansion_operation is None and host._clipboard_lease is None)
            actual = js("(() => { const e=(" + doc + ").getElementById('editor');"
                        "return JSON.stringify({text:e.textContent,html:e.innerHTML,pastes:window.pastes,"
                        "pasteHTML:window.pasteHTML,pasteText:window.pasteText,pasteTypes:window.pasteTypes,copies:window.copies,"
                        "edits:window.edits,doc:e.ownerDocument.body.innerText});})()")
            actual = json.loads(actual)
            actual['engine']=messages[marker:]
            actual['case']=[framed,rich,mismatch,fault]
            # Chromium may preserve boundary spaces with NBSP during rich paste.
            assert actual["text"].replace("\u00a0", " ") == (
                prefix+shortcut+'X|tail' if mismatch else prefix + body+"|tail"), actual
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
                           "recovery": fault, "pastes": actual["pastes"]})
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
