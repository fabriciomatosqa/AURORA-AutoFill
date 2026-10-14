"""Regressões de dados e do editor de texto da versão 0.2 (sem precisar de GUI)."""
import json
from datetime import datetime
from pathlib import Path
import sqlite3
import tempfile
import unittest

from app.core import SnippetStore, render_snippet
from app.formatting import has_rich_formatting, render_rich_html


class CompatibilityTests(unittest.TestCase):
    def test_migrates_v01_database_without_losing_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'data.sqlite'
            conn = sqlite3.connect(path)
            conn.executescript('''
                CREATE TABLE folders (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE COLLATE NOCASE);
                CREATE TABLE snippets (id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folder_id INTEGER NOT NULL REFERENCES folders(id), title TEXT NOT NULL,
                    shortcut TEXT NOT NULL UNIQUE COLLATE NOCASE, content TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO folders (name) VALUES ('Teste');
                INSERT INTO snippets (folder_id,title,shortcut,content) VALUES (1,'Antigo','/antigo','Olá {{cursor}} mundo');
            ''')
            conn.commit()
            conn.close()
            db = SnippetStore(path)
            old = db.snippets()[0]
            self.assertEqual(old.shortcut, '/antigo')
            self.assertEqual(old.rich_content, '')
            db.save(1, old.title, old.shortcut, old.content, old.id, '<b>Olá</b> mundo')
            self.assertIn('<b>Olá</b>', db.snippets()[0].rich_content)
            db.close()

    def test_rich_backup_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            db = SnippetStore(Path(temp) / 'a.db')
            folder = db.create_folder('Suporte')
            db.save(folder, 'Formato', '/formato', 'texto bonito', rich_content='<b>texto</b> bonito')
            backup = Path(temp) / 'backup.json'
            db.export_json(backup)
            self.assertIn('rich_content', json.loads(backup.read_text())['snippets'][0])
            other = SnippetStore(Path(temp) / 'b.db')
            self.assertEqual(other.import_json(backup), (1,0))
            self.assertEqual(other.snippets()[0].rich_content, '<b>texto</b> bonito')
            other.close(); db.close()

    def test_marker_near_diacritics(self):
        result = render_snippet('Meu nome é {{cursor}} e estou testando.')
        self.assertEqual(result.text, 'Meu nome é  e estou testando.')
        self.assertEqual(result.left_moves, len(' e estou testando.'))


class FormattingTests(unittest.TestCase):
    def test_recognizes_rich_styles(self):
        self.assertTrue(has_rich_formatting('<span style="font-weight:700;">texto</span>'))
        self.assertTrue(has_rich_formatting('<span style="font-style:italic">texto</span>'))
        self.assertTrue(has_rich_formatting('<span style="text-decoration: underline">texto</span>'))
        self.assertFalse(has_rich_formatting('<p style="margin:0">texto</p>'))

    def test_renders_and_escapes_dynamic_variables_in_rich_html(self):
        source = '<b>Hoje {{data}}</b> - {{clipboard}} / {{cursor}}'
        html = render_rich_html(source, '<mensagem> & ok', datetime(2026,10,13,12,0))
        self.assertEqual(html, '<b>Hoje 13/10/2026</b> - &lt;mensagem&gt; &amp; ok / ')


if __name__ == '__main__':
    unittest.main()

class WindowsKeyboardTests(unittest.TestCase):
    def test_unicode_injection_order_no_clipboard_race(self):
        import ctypes
        from unittest.mock import patch
        from types import SimpleNamespace
        from app.hotkeys import _send_windows_unicode

        sent = []
        class SendInputStub:
            def __call__(self, count, records, record_size):
                sent.extend((records[i].u.ki.wVk, records[i].u.ki.wScan, records[i].u.ki.dwFlags)
                            for i in range(count))
                return count
        fake_api = SimpleNamespace(SendInput=SendInputStub())
        with patch.object(ctypes, 'windll', SimpleNamespace(user32=fake_api), create=True):
            _send_windows_unicode(2, 'é\n!', 1)
        self.assertEqual([event[0] for event in sent[:4]], [8,8,8,8])
        self.assertEqual(sent[4][1:], (ord('é'), 4))
        self.assertEqual([event[0] for event in sent[6:8]], [13,13])
        self.assertEqual([event[0] for event in sent[-2:]], [37,37])