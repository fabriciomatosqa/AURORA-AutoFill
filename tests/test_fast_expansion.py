"""Performance contracts with real data/query counts, not wall-clock guesses."""
import queue
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.accessibility_context import AccessibilityClient, AccessibilityUnavailable
from app.core import SnippetStore
from app.expansion import EditSnapshot
from engine_fixture import EngineFixture


class FastExpansionTests(unittest.TestCase):
    def test_unicode_lookup_and_matching_use_the_same_key(self):
        for saved, typed in [('/ação', '/AÇÃO'), ('/straße', '/STRASSE'), ('/σ', '/ς')]:
            with self.subTest(typed=typed), EngineFixture() as e:
                e.save(saved, 'Resposta correta 😀')
                e.type(typed)
                e.until(0)
                self.assertEqual(e.field.text, 'Resposta correta 😀')
                self.assertEqual(e.api_calls, 1)
                e.drain()
                self.assertEqual(e.clipboard.text(), 'original')

    def test_cache_does_not_reread_bodies_and_invalidates_on_edit_delete_undo(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnippetStore(Path(tmp) / 'snippets.db')
            try:
                folder = store.create_folder('Teste')
                identifier = store.save(folder, 'Modelo', '/ação', 'Primeiro', rich_content='<b>Primeiro</b>')
                calls = []
                store.connection.set_trace_callback(calls.append)
                self.assertEqual(store.snippet_by_shortcut('/AÇÃO').content, 'Primeiro')
                calls.clear()
                for _ in range(10):
                    self.assertEqual(store.snippet_by_shortcut('/ação').rich_content, '<b>Primeiro</b>')
                self.assertFalse(any('FROM snippets' in sql for sql in calls))
                store.update_snippet_fields(identifier, content='Segundo', rich_content='<i>Segundo</i>')
                self.assertEqual(store.snippet_by_shortcut('/AÇÃO').content, 'Segundo')
                saved = store.delete_with_undo(identifier)
                self.assertIsNone(store.snippet_by_shortcut('/ação'))
                store.restore_deleted_snippet(saved)
                self.assertEqual(store.snippet_by_shortcut('/AÇÃO').content, 'Segundo')
                store.update_snippet_fields(identifier, shortcut='/novo')
                self.assertIsNone(store.snippet_by_shortcut('/ação'))
                self.assertEqual(store.snippet_by_shortcut('/novo').id, identifier)
            finally:
                store.close()

    def test_external_edit_and_transaction_rollback_never_leave_stale_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'snippets.db'
            store = SnippetStore(db)
            try:
                folder = store.create_folder('Teste')
                identifier = store.save(folder, 'Modelo', '/x', 'Antes')
                self.assertEqual(store.snippet_by_shortcut('/x').content, 'Antes')
                with sqlite3.connect(db) as external:
                    external.execute('UPDATE snippets SET content=? WHERE id=?', ('Externo', identifier))
                self.assertEqual(store.snippet_by_shortcut('/x').content, 'Externo')
                try:
                    with store.connection:
                        store.connection.execute('UPDATE snippets SET content=? WHERE id=?', ('Rollback', identifier))
                        self.assertEqual(store.snippet_by_shortcut('/x').content, 'Rollback')
                        raise ValueError('synthetic rollback')
                except ValueError:
                    pass
                self.assertEqual(store.snippet_by_shortcut('/x').content, 'Externo')
            finally:
                store.close()

    def test_cache_is_bounded_by_payload_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnippetStore(Path(tmp) / 'snippets.db')
            try:
                folder = store.create_folder('Teste')
                # Populate without per-row conflict scans; this models a large
                # imported library and keeps the test focused on bounded cache.
                with store.connection:
                    for i in range(20):
                        store.connection.execute(
                            'INSERT INTO snippets(folder_id,title,shortcut,content) VALUES (?,?,?,?)',
                            (folder, str(i), '/item%02d' % i, 'X' * 300000))
                for i in range(20):
                    self.assertIsNotNone(store.snippet_by_shortcut('/item%02d' % i))
                self.assertLessEqual(len(store._snippet_cache), 16)
                self.assertLessEqual(store._snippet_cache_size, 4_000_000)
                self.assertEqual(store._snippet_cache_size, sum(
                    len(item.content) + len(item.rich_content) for item in store._snippet_cache.values()))
            finally:
                store.close()

    def test_cached_model_renders_date_clipboard_and_cursor_again_each_time(self):
        from datetime import datetime
        with EngineFixture() as e:
            e.save('/dinamico', '{{data}}|{{hora}}|{{data_hora}}|{{clipboard}}|{{cursor}}fim')
            with patch('app.ui.datetime') as clock:
                clock.now.side_effect = [datetime(2026, 10, 23, 10, 15), datetime(2026, 10, 24, 11, 20)]
                for date, hour, copied in [('23/10/2026', '10:15', 'primeiro'),
                                           ('24/10/2026', '11:20', 'segundo')]:
                    e.field.text = ''
                    e.field.caret = e.field.anchor = 0
                    e.listener.invalidate()
                    e.clipboard.setText(copied)
                    e.type('/dinamico')
                    e.drain()
                    expected = date + '|' + hour + '|' + date + ' ' + hour + '|' + copied + '|fim'
                    self.assertEqual(e.field.text, expected)
                    self.assertEqual(e.field.caret, len(expected) - 3)
                    self.assertEqual(e.clipboard.text(), copied)

    def test_legacy_unicode_collision_is_not_expanded_arbitrarily(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SnippetStore(Path(tmp) / 'snippets.db')
            try:
                folder = store.create_folder('Teste')
                store.save(folder, 'Um', '/ação', 'Um')
                # Simulates a legacy SQLite NOCASE profile (ASCII-only uniqueness).
                with store.connection:
                    store.connection.execute('INSERT INTO snippets(folder_id,title,shortcut,content) VALUES (?,?,?,?)',
                                             (folder, 'Outro', '/AÇÃO', 'Outro'))
                self.assertIsNone(store.snippet_by_shortcut('/ação'))
                self.assertNotIn('/ação', store.shortcuts())
            finally:
                store.close()

    def test_shortcut_metadata_never_loads_rich_bodies(self):
        with EngineFixture() as e:
            e.save('/meta', 'Texto', '<p>' + 'X' * 1000000 + '</p>')
            calls = []
            e.store.connection.set_trace_callback(calls.append)
            e.store.shortcuts()
            self.assertFalse(any('rich_content' in sql for sql in calls))
            with patch.object(e.store, 'snippets', side_effect=AssertionError('Bodies must not be read')):
                # Bind this UI method explicitly: the fixture only binds engine stages.
                from app.ui import AutoFillWindow
                AutoFillWindow._update_listener_shortcuts(e.host)

    def test_confirmed_selection_reuses_proof_but_pending_ack_still_polls(self):
        with EngineFixture() as e:
            e.save('/fast', 'OK')
            reads = []
            def snapshot(context, **_):
                reads.append(1)
                current = e.snapshot(context)
                return EditSnapshot(context, current.text, current.start, current.end, ('pid', 'field', 'doc'))
            with patch('app.ui.capture_edit', side_effect=snapshot):
                e.type('/fast')
                e.until(0)
                self.assertEqual(e.field.text, 'OK')
                self.assertEqual(len(reads), 2)
                e.drain()
            self.assertEqual(e.api_calls, 1)

    def test_worker_warmup_is_nonblocking_and_does_not_recompile_on_each_request(self):
        client = AccessibilityClient()
        process = SimpleNamespace(poll=lambda: None, stdin=Mock(), kill=Mock(),
                                  _aurora_ready=False, _aurora_started=100)
        client._process, client._responses = process, queue.Queue()
        with patch.object(client, 'warm'), patch('app.accessibility_context.monotonic', return_value=101):
            with self.assertRaises(AccessibilityUnavailable):
                client.request(7, timeout=5)
            process.stdin.write.assert_not_called()
            process.kill.assert_not_called()
        with patch.object(client, 'warm'), patch('app.accessibility_context.monotonic', return_value=116):
            with self.assertRaises(AccessibilityUnavailable):
                client.request(7)
            process.kill.assert_called_once()
        client.stop()


if __name__ == '__main__':
    unittest.main()
