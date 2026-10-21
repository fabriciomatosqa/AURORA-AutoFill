import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.accessibility_context import (AccessibilityClient, AccessibilityUnavailable,
                                       SELECTION_SUBMITTED, decode_snapshot,
                                       select_accessible, _request_context)
from app.expansion import EditSnapshot, FocusContext
from engine_fixture import EngineFixture


class AccessibilityContextTests(unittest.TestCase):
    def test_snapshot_accepts_utf16_and_rejects_invalid_responses(self):
        context = FocusContext(101, 1)
        valid = dict(status='ok', text='😀/ola', start=6, end=6, identity=['7', '8', '9'])
        snapshot = decode_snapshot(context, valid)
        self.assertEqual(snapshot.shortcut_range('/ola'), (2, 6))
        self.assertEqual(snapshot.identity, ('7', '8', '9'))
        self.assertIsNone(decode_snapshot(context, {'status': 'unsupported'}))
        for changes in ({'start': 1}, {'start': -1}, {'end': 7}, {'identity': []},
                        {'text': 'L' * 65535}, {'status': 'changed'}, {'text': '\ud800'},
                        {'status': 'unavailable'}):
            with self.subTest(changes=list(changes)), self.assertRaises(AccessibilityUnavailable):
                decode_snapshot(context, dict(valid, **changes))

    def test_select_ack_requires_exact_scope_and_identity(self):
        import ctypes
        context = FocusContext(101, 1)
        snapshot = EditSnapshot(context, '/ola', 4, 4, ('7', 'field', 'doc'))
        response = {'status': 'selection_requested', 'window': '101',
                    'control': '1', 'identity': ['7', 'field', 'doc']}
        def pid(_hwnd, pointer):
            pointer._obj.value = 7
            return 1
        api = SimpleNamespace(GetWindowThreadProcessId=pid)
        with patch.object(ctypes, 'windll', SimpleNamespace(user32=api), create=True), \
             patch('app.accessibility_context._client.request', return_value=response) as send:
            self.assertIs(select_accessible(snapshot, 0, 4), SELECTION_SUBMITTED)
            self.assertEqual(send.call_args.kwargs['action'], 'select')
            self.assertEqual(send.call_args.kwargs['selection_start'], 4)
            for changed in ({'identity': ['7', 'other', 'doc']},
                            {'window': '999'}, {'control': '99'},
                            {'status': 'changed'}):
                with self.subTest(changed=changed), \
                     patch('app.accessibility_context._client.request',
                           return_value=dict(response, **changed)):
                    with self.assertRaises(AccessibilityUnavailable):
                        select_accessible(snapshot, 0, 4)
            # ACKs sem ação 'select' nunca devem virar snapshots válidos.
            with self.assertRaises(AccessibilityUnavailable):
                _request_context(context)

    def test_worker_timeout_poisons_late_response(self):
        client = AccessibilityClient()
        process = SimpleNamespace(poll=lambda: None, stdin=Mock(), kill=Mock(), _aurora_ready=True)
        client._process, client._responses = process, queue.Queue()
        with patch.object(client, 'warm'):
            with self.assertRaises(AccessibilityUnavailable):
                client.request(7, timeout=0.001)
            process.kill.assert_called_once()
            client._responses.put({'status': 'ok', 'text': 'STALE'})
            with self.assertRaises(AccessibilityUnavailable):
                client.request(7, timeout=0.001)
            self.assertEqual(process.stdin.write.call_count, 1)
        client.stop()

    def test_cursor_uses_accessible_snapshot_but_literals_do_not_request_it(self):
        for content in ('Bom dia, @{{cursor}}! Espero que esteja bem.', 'L' * 8192,
                        ('Linha longa de teste\n' * 100) + 'A{{cursor}}😀B'):
            with self.subTest(cursor='{{cursor}}' in content), EngineFixture() as e:
                e.save('/diag', content)
                calls = []
                def snapshot(context, *, accessibility=False):
                    calls.append(accessibility)
                    if not accessibility:
                        return None
                    current = e.snapshot(context)
                    return EditSnapshot(context, current.text, current.start, current.end, ('1', 'field', 'doc'))
                with patch('app.ui.capture_edit', side_effect=snapshot):
                    e.type('/diag')
                    e.drain()
                if '{{cursor}}' in content:
                    e.host._play_confirmation.assert_called_once()
                    e.type('X')
                    self.assertEqual(e.field.text, content.replace('{{cursor}}', 'X'))
                    self.assertTrue(any(calls))
                else:
                    self.assertEqual(e.field.text, content)
                    # Mesmo texto simples exige prova de cursor/atalho
                    # antes de substituir campos web não reconhecidos pelo Win32.
                    self.assertTrue(any(calls))
                self.assertEqual(e.api_calls, 1)
                self.assertEqual(e.clipboard.text(), 'original')

    def test_accessible_field_identity_change_prevents_paste(self):
        with EngineFixture() as e:
            e.save('/diag', 'A{{cursor}}B')
            reads = 0
            def snapshot(context, *, accessibility=False):
                nonlocal reads
                if not accessibility:
                    return None
                reads += 1
                current = e.snapshot(context)
                return EditSnapshot(context, current.text, current.start, current.end,
                                    ('1', 'first' if reads == 1 else 'second', 'doc'))
            with patch('app.ui.capture_edit', side_effect=snapshot):
                e.type('/diag')
                e.drain()
            self.assertEqual(e.field.text, '/diag')
            e.replace.assert_not_called()
            self.assertEqual(e.clipboard.text(), 'original')

    def test_accessible_field_identity_change_after_paste_prevents_cursor_move(self):
        with EngineFixture() as e:
            e.save('/diag', 'A{{cursor}}B')
            def snapshot(context, *, accessibility=False):
                if not accessibility:
                    return None
                current = e.snapshot(context)
                return EditSnapshot(context, current.text, current.start, current.end,
                                    ('1', 'first' if not e.sent else 'second', 'doc'))
            with patch('app.ui.capture_edit', side_effect=snapshot):
                e.type('/diag')
                e.drain()
            self.assertEqual(e.field.text, 'AB')
            e.move.assert_not_called()
            # Acionamento de Ctrl+V confirmado; a posterior troca de
            # identidade impede mover o cursor, mas não cancela o som já tocado.
            e.host._play_confirmation.assert_called_once()

    def test_unsupported_or_unresponsive_provider_preserves_shortcut(self):
        for failure in (None, AccessibilityUnavailable('unavailable')):
            with self.subTest(failure=type(failure).__name__), EngineFixture() as e:
                e.save('/diag', 'A{{cursor}}B')
                def snapshot(context, *, accessibility=False):
                    if accessibility and failure is not None:
                        from app.windows_context import ContextUnavailable
                        raise ContextUnavailable('unavailable')
                    return None
                with patch('app.ui.capture_edit', side_effect=snapshot):
                    e.type('/diag')
                    e.drain()
                self.assertEqual(e.field.text, '/diag')
                e.replace.assert_not_called()
                self.assertEqual(e.clipboard.text(), 'original')
