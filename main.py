"""Inicialização da interface desktop."""
import sys
import os


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from app.ui import AutoFillWindow
    except ImportError as exc:
        print("Dependências ausentes. Execute: python -m pip install -r requirements.txt", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName("AURORA AutoFill")
    app.setOrganizationName("Aurora")
    app.setStyle("Fusion")
    window = AutoFillWindow()
    app.setQuitOnLastWindowClosed(window.tray_icon is None)
    window.show()
    # Smoke test used by build jobs; never active for normal users.
    if os.environ.get("AURORA_AUTOFILL_SMOKE_TEST") == "1":
        from PySide6.QtCore import QTimer
        def exit_smoke():
            window._quitting = True
            window.close()
            app.quit()
        QTimer.singleShot(900, exit_smoke)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())