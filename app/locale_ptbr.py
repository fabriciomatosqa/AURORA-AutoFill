"""Portuguese strings for Qt-provided dialogs, alongside AURORA's PT-BR UI.

Qt may use English when the operating system is Portuguese if its catalog was
not installed. ColorDialog also has a per-widget fallback for bundled builds.
"""
from __future__ import annotations

from PySide6.QtCore import QLibraryInfo, QTranslator


def install_portuguese_qt(app) -> bool:
    """Load an available bundled Qt base translation and retain its lifetime."""
    path = QLibraryInfo.path(QLibraryInfo.TranslationsPath)
    for catalog in ("qtbase_pt_BR", "qtbase_pt", "qt_pt_BR", "qt_pt"):
        translator = QTranslator(app)
        if translator.load(catalog, path):
            app.installTranslator(translator)
            # Python owns the wrapper; keeping it avoids garbage collection.
            app._aurora_pt_translator = translator
            return True
    return False
