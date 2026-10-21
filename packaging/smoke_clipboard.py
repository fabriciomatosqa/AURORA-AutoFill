"""Native Windows clipboard interoperability, read from a second process.

Only synthetic payloads are asserted. No keystrokes or application messages
are sent. Previous MIME data is restored unless clipboard ownership changes.
This does not prove compatibility with Word, Teams or ChatGPT.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_native(case):
    api = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    api.GetClipboardData.argtypes = [wintypes.UINT]
    api.GetClipboardData.restype = wintypes.HANDLE
    api.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    kernel.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel.GlobalLock.restype = ctypes.c_void_p
    kernel.GlobalSize.argtypes = [wintypes.HANDLE]
    kernel.GlobalSize.restype = ctypes.c_size_t
    kernel.GlobalUnlock.argtypes = [wintypes.HANDLE]

    if not api.OpenClipboard(None):
        raise RuntimeError("Native clipboard unavailable")
    try:
        def data(fmt):
            handle = api.GetClipboardData(fmt)
            if not handle:
                raise AssertionError(f"Missing native format {fmt}")
            pointer = kernel.GlobalLock(handle)
            if not pointer:
                raise AssertionError("Clipboard data could not be locked")
            try:
                return ctypes.string_at(pointer, kernel.GlobalSize(handle))
            finally:
                kernel.GlobalUnlock(handle)

        raw = data(api.RegisterClipboardFormatW("HTML Format"))
        fields = {key: int(re.search(key.encode() + rb":(\d+)", raw).group(1))
                  for key in ("StartHTML", "EndHTML", "StartFragment", "EndFragment")}
        fragment = raw[fields["StartFragment"]:fields["EndFragment"]].decode("utf-8")
        assert "data:image/png;base64," in fragment
        assert fields["StartHTML"] <= fields["StartFragment"] < fields["EndFragment"] <= fields["EndHTML"] <= len(raw)
        # CF_UNICODETEXT is optional for a pure native image.
        text = (data(13).decode("utf-16-le").rstrip("\x00")
                if api.IsClipboardFormatAvailable(13) else "")
        assert "[Imagem" not in text and "cole separadamente" not in text
        formats = ["CF_HTML"]
        if api.IsClipboardFormatAvailable(13):
            formats.append("CF_UNICODETEXT")
        if case == "isolated":
            assert not text
            assert data(api.RegisterClipboardFormatW("PNG")).startswith(b"\x89PNG")
            bitmap_format = 17 if api.IsClipboardFormatAvailable(17) else 8
            bitmap = data(bitmap_format)  # DIBV5 / DIB
            assert int.from_bytes(bitmap[:4], "little") >= 40
            formats += ["PNG", "CF_DIBV5" if bitmap_format == 17 else "CF_DIB"]
        else:
            assert not api.IsClipboardFormatAvailable(8) and not api.IsClipboardFormatAvailable(17)
            assert "Antes 😀" in fragment and "Depois" in fragment
            assert "Antes 😀" in text and "Depois" in text
        return formats
    finally:
        api.CloseClipboard()


def main():
    if sys.platform != "win32":
        raise SystemExit("This smoke test requires Windows")
    if len(sys.argv) > 1 and sys.argv[1] == "--reader":
        print(json.dumps(read_native(sys.argv[2])))
        return
    # Run against Windows OLE, never the offscreen test plugin.
    os.environ["QT_QPA_PLATFORM"] = "windows"
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication
    from app.inline_images import AuroraImageEditor, image_sources
    from app.clipboard_content import clone_mime, expansion_mime, prepare_mixed_content
    from datetime import datetime

    app = QApplication([])
    clipboard = app.clipboard()
    original = clone_mime(clipboard.mimeData())
    owned = None
    report = {}
    try:
        editor = AuroraImageEditor()
        image = QImage(32, 16, QImage.Format_ARGB32)
        image.fill(Qt.cyan)
        assert editor.insert_image(image)
        source = image_sources(editor.toHtml())[0]
        for case, html in (("mixed", f'<p>Antes 😀</p><p><img src="{source}"></p><p>Depois</p>'),
                           ("isolated", f'<p><img src="{source}"></p>')):
            mixed = prepare_mixed_content(html, "", datetime.now())
            clipboard.setMimeData(expansion_mime(mixed.text, mixed.html, image_only=mixed.image_only))
            owned = ctypes.windll.user32.GetClipboardSequenceNumber()
            child = subprocess.Popen([sys.executable, __file__, "--reader", case],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     text=True, encoding="utf-8", creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 15
            while child.poll() is None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.005)
            if child.poll() is None:
                child.kill()
                child.communicate()
                raise AssertionError("Native clipboard reader timed out")
            output, errors = child.communicate()
            assert child.returncode == 0, errors
            report[case] = json.loads(output)
            assert ctypes.windll.user32.GetClipboardSequenceNumber() == owned, "Clipboard ownership changed"
        print(json.dumps(report))
    finally:
        if owned is not None and ctypes.windll.user32.GetClipboardSequenceNumber() == owned:
            clipboard.setMimeData(original)
            app.processEvents()


if __name__ == "__main__":
    main()
