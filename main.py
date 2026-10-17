"""Inicialização da interface desktop."""
import sys
import os


def should_start_in_tray(arguments, *, tray_available: bool) -> bool:
    """Show only the tray icon for explicit Windows startup launches."""
    return sys.platform == "win32" and "--minimized" in arguments and tray_available


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from app.ui import AutoFillWindow
    except ImportError as exc:
        print("Dependências ausentes. Execute: python -m pip install -r requirements.txt", file=sys.stderr)
        print(exc, file=sys.stderr)
        return 1

    launch_arguments = sys.argv[1:]
    # Strip our own flag before Qt parses application command-line options.
    qt_arguments = [sys.argv[0], *(arg for arg in launch_arguments if arg != "--minimized")]
    app = QApplication(qt_arguments)
    from app.version import APP_VERSION
    app.setApplicationName("AURORA AutoFill")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("Aurora")
    app.setStyle("Fusion")
    from app.core import application_db_path
    from app.instance import acquire_instance_lock
    try:
        instance_lock = acquire_instance_lock(application_db_path().parent)
    except OSError as exc:
        QMessageBox.warning(None, "AURORA AutoFill", str(exc))
        return 1
    if instance_lock is None:
        QMessageBox.information(
            None, "AURORA já está aberto",
            "O AURORA já está em execução. Abra o ícone próximo ao relógio "
            "para acessar o programa.")
        return 0
    window = AutoFillWindow()
    app.setQuitOnLastWindowClosed(window.tray_icon is None)
    if not should_start_in_tray(launch_arguments, tray_available=window.tray_icon is not None):
        # Manual launches open normally, even when the user has enabled
        # 'Iniciar minimizado' in the Windows startup settings.
        window.show()
    # Smoke test used by build jobs; never active for normal users.
    if os.environ.get("AURORA_AUTOFILL_SMOKE_TEST") == "1":
        from PySide6.QtCore import QTimer
        def exit_smoke():
            window._quitting = True
            window.close()
            app.quit()
        QTimer.singleShot(900, exit_smoke)
    try:
        return app.exec()
    finally:
        instance_lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
