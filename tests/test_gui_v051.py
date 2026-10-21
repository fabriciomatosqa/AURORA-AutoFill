"""Smoke tests for the actual PySide6 widgets on a graphical or offscreen runner."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class InterfaceSmokeTests(unittest.TestCase):
    def test_editor_warns_and_disables_save_for_prefix_overlap(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        try:
            from PySide6.QtWidgets import QApplication
            from app.ui import AutoFillWindow
        except ImportError:
            self.skipTest('PySide6 ausente')
        app = QApplication.instance() or QApplication([])
        type(self)._application = app
        with tempfile.TemporaryDirectory(prefix='aurora-conflict-test-') as tmp:
            with patch('app.ui.application_db_path', return_value=os.path.join(tmp, 'test.db')), \
                 patch('app.ui.GlobalHotkeyListener.start', return_value=(False, 'Modo de teste')), \
                 patch('app.ui.AutoFillWindow._initial_release_check'):
                win = AutoFillWindow()
                try:
                    folder = win.store.create_folder('HUBRASIL')
                    existing = win.store.save(folder, 'CAD', '/2', 'Mensagem antiga')
                    win._refresh_all()
                    win._new_snippet()
                    win.shortcut_input.setText('/23')
                    self.assertTrue(win.shortcut_feedback.isVisibleTo(win.editor_scroll))
                    self.assertIn('/2', win.shortcut_feedback.text())
                    self.assertIn('CAD', win.shortcut_feedback.text())
                    self.assertIn('HUBRASIL', win.shortcut_feedback.text())
                    self.assertFalse(win.save_button.isEnabled())
                    win.shortcut_input.setText('/2')
                    self.assertFalse(win.save_button.isEnabled())
                    win.shortcut_input.setText('/23a')
                    self.assertFalse(win.save_button.isEnabled())
                    win.shortcut_input.setText('/3')
                    self.assertEqual(win.shortcut_feedback.text(), '')
                    self.assertTrue(win.save_button.isEnabled())
                    win._load_editor(win._get_snippet(existing))
                    self.assertEqual(win.shortcut_feedback.text(), '')
                    self.assertTrue(win.save_button.isEnabled())
                    win.shortcut_input.setText('/23')
                    self.assertFalse(win.save_button.isEnabled())
                    # Ao editar o próprio comando, seu ID é ignorado, mas
                    # outro registro com prefixo conflitante seria bloqueado.
                    win.shortcut_input.setText('/2')
                    self.assertTrue(win.save_button.isEnabled())
                finally:
                    app.clipboard().clear()
                    win._quitting = True
                    win.close()
                    win.deleteLater()
                    from PySide6.QtCore import QCoreApplication, QEvent
                    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()

    def test_visual_controls_credit_and_dropdown(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        try:
            from PySide6.QtWidgets import QApplication
            from app.ui import AutoFillWindow, AuroraFolderCombo, AuroraWordmark
        except ImportError:
            self.skipTest('PySide6 ausente')
        app = QApplication.instance() or QApplication([])
        # Qt expects a single QApplication for this test process.
        type(self)._application = app
        app.setStyle('Fusion')
        if os.name == 'nt':
            from PySide6.QtGui import QFontDatabase, QFont
            for filename in ('segoeui.ttf', 'segoeuib.ttf', 'bahnschrift.ttf', 'seguisym.ttf', 'consola.ttf'):
                font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / filename
                if font.is_file():
                    QFontDatabase.addApplicationFont(str(font))
            app.setFont(QFont('Segoe UI', 10))
        with tempfile.TemporaryDirectory(prefix='aurora-test-') as tmp:
            with patch('app.ui.application_db_path', return_value=os.path.join(tmp, 'test.db')):
                with patch('app.ui.GlobalHotkeyListener.start', return_value=(False, 'Modo de teste')), \
                     patch('app.ui.AutoFillWindow._initial_release_check'):
                    win = AutoFillWindow()
                    try:
                        self.assertIsInstance(win.filter_folder, AuroraFolderCombo)
                        self.assertIsInstance(win.editor_folder, AuroraFolderCombo)
                        self.assertTrue(win.findChildren(AuroraWordmark))
                        credit = win.statusBar().findChildren(type(win.edit_heading), 'developerCredit')
                        self.assertEqual(len(credit), 1)
                        self.assertIn('Fabricio Matos', credit[0].text())
                        from app.version import APP_VERSION
                        self.assertTrue(credit[0].text().endswith(f'•  V{APP_VERSION}'))
                        self.assertNotIn('Versão', credit[0].text())
                        self.assertGreaterEqual(win.filter_folder.count(), 2)
                        self.assertFalse(win.windowIcon().isNull())
                        from app.icons import icon
                        self.assertFalse(icon('image').isNull())
                        win._new_snippet()
                        from PySide6.QtGui import QImage
                        from PySide6.QtCore import Qt
                        screenshot = QImage(80, 40, QImage.Format_ARGB32)
                        screenshot.fill(Qt.cyan)
                        win.body_input.setPlainText('Texto antes\\n')
                        self.assertTrue(win.body_input.insert_image(screenshot))
                        win.body_input.insertPlainText('\\nTexto depois')
                        win._prepare_copy_menu()
                        labels = [action.text().lower() for action in
                                  win.copy_content_menu.actions()]
                        self.assertFalse(any('imagem única' in label for label in labels))
                        self.assertTrue(any('copiar trecho de texto' in label for label in labels))
                        self.assertTrue(any('copiar imagem 1' in label for label in labels))
                        win.dirty = False
                        win.filter_folder.showPopup()
                        app.processEvents()
                        menu = win.filter_folder._folder_menu
                        self.assertIsNotNone(menu)
                        self.assertEqual(len(menu.actions()), win.filter_folder.count())
                        if len(menu.actions()) > 1:
                            menu.actions()[1].trigger()
                            self.assertEqual(win.filter_folder.currentIndex(), 1)
                        menu.hide()
                        # Optional local visual evidence, excluded from source
                        # control and absent in CI unless explicitly prepared.
                        evidence = Path(__file__).resolve().parents[1] / 'qa'
                        if evidence.is_dir():
                            for width, height in ((1320, 900), (1000, 720)):
                                win.resize(width, height)
                                win.show()
                                win.dirty = False
                                win._show_welcome()
                                app.processEvents()
                                win.grab().save(str(evidence / f'welcome-{width}.png'))
                                win._show_settings()
                                app.processEvents()
                                win.grab().save(str(evidence / f'settings-{width}.png'))
                                win._new_snippet()
                                app.processEvents()
                                win.grab().save(str(evidence / f'editor-{width}.png'))
                                win.dirty = False
                            win.filter_folder.showPopup()
                            app.processEvents()
                            win.filter_folder._folder_menu.grab().save(str(evidence / 'folder-menu.png'))
                            win.filter_folder._folder_menu.hide()
                    finally:
                        # Solta o PNG do QClipboard antes de desmontar o QApplication;
                        # no Qt offscreen o payload nativo pode causar falha no exit.
                        app.clipboard().clear()
                        win._quitting = True
                        win.close()
                        win.deleteLater()
                        from PySide6.QtCore import QCoreApplication, QEvent
                        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()


if __name__ == '__main__':
    unittest.main()
