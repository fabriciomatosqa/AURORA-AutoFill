"""Correctness contracts: these tests must fail on the Phase 6A defects."""
from types import SimpleNamespace
from unittest.mock import patch

from engine_fixture import EngineFixture, EngineTestCase
from app.expansion import utf16_length
from app.hotkeys import INJECTION_TAG
from app.windows_context import ContextUnavailable
from engine_fixture import key


class ExpansionTransactionTests(EngineTestCase):
    def test_f7_01_typing_at_former_selection_gap_preserves_content(self):
        phrase = 'Olá! Este é um teste do AURORA.'
        for delay in (50, 74, 75, 80, 84, 86, 96):
            with self.subTest(delay=delay), EngineFixture() as e:
                e.save('/ola', phrase)
                e.type('/ola')
                e.schedule(delay, lambda: e.type('x'))
                e.drain()
                self.assertEqual(e.field.text, '/olax' if delay < 75 else phrase + 'x')
                self.assertEqual(e.api_calls, 0 if delay < 75 else 1)
                self.assertEqual(e.clipboard.text(), 'original')
                self.assertFalse(e.shift or e.ctrl)

    def test_replacement_batch_is_not_split_even_above_128_events(self):
        # Exercise backend limit without changing the store's 30-character rule.
        from app.hotkeys import replace_shortcut
        self.engine.field.text = 'a' * 64
        self.engine.field.caret = self.engine.field.anchor = 64
        self.clipboard.setText('OK')
        replace_shortcut(64)
        self.assertEqual(self.engine.field.text, 'OK')
        self.assertEqual(self.engine.api_calls, 1)
        self.assertEqual(len(self.engine.sent), 134)

    def test_final_character_can_settle_after_keyup_without_selecting_wrong_range(self):
        self.engine.save('/ola', 'OK')
        self.engine.type('/ol')
        self.engine.listener._on_press(key('a'))
        self.engine.schedule(100, lambda: self.engine.field.insert('a'))
        self.engine.listener._on_release(key('a'))
        self.engine.drain()
        self.assertEqual(self.engine.field.text, 'OK')
        self.engine.replace.assert_called_once_with(4)

    def test_transient_confirmation_reads_are_polled_without_resending(self):
        failures = {'sent': 2, 'moving': 2}
        self.engine.save('/ola', 'A{{cursor}}B')
        def snapshot(context):
            operation = self.win._expansion_operation
            stage = operation.stage if operation else ''
            if failures.get(stage, 0):
                failures[stage] -= 1
                raise ContextUnavailable('Transient native selection update')
            return self.engine.snapshot(context)
        with patch('app.ui.capture_edit', side_effect=snapshot):
            self.expand()
        self.engine.type('X')
        self.assertEqual(self.engine.field.text, 'AXB')
        self.engine.replace.assert_called_once()
        self.engine.position.assert_called_once()
        self.engine.move.assert_not_called()
        self.win._play_confirmation.assert_called_once()

    def test_new_copy_during_backup_cancels_before_overwriting_clipboard(self):
        original_clone = self.win._clone_clipboard_mime
        def copy_during_backup():
            backup = original_clone()
            self.clipboard.setText('NEW COPY')
            return backup
        with patch.object(self.win, '_clone_clipboard_mime', side_effect=copy_during_backup):
            self.expand()
        self.assertEqual(self.clipboard.text(), 'NEW COPY')
        self.assertEqual(self.engine.field.text, '/ola')
        self.engine.replace.assert_not_called()

    def test_caret_change_while_preparing_payload_is_revalidated(self):
        real_set = self.clipboard.setMimeData
        def change_caret(mime):
            real_set(mime)
            if mime.hasFormat('application/x-aurora-expansion'):
                self.engine.field.caret = self.engine.field.anchor = 0
        with patch.object(self.clipboard, 'setMimeData', side_effect=change_caret):
            self.expand()
        self.assertEqual(self.engine.field.text, '/ola')
        self.engine.replace.assert_not_called()
        self.assertEqual(self.clipboard.text(), 'original')

    def test_expired_queued_candidate_does_not_edit(self):
        self.engine.defer_signal = True
        self.engine.type('/ola')
        self.engine.now = 2000
        self.win._expand_global(self.engine.received[0])
        self.engine.drain()
        self.assertEqual(self.engine.field.text, '/ola')
        self.engine.replace.assert_not_called()

    def test_shortcut_is_replaced_exactly_and_clipboard_restored(self):
        self.engine.save('/ola', 'Olá! Este é um teste do AURORA.')
        self.expand()
        self.assertEqual(self.engine.field.text, 'Olá! Este é um teste do AURORA.')
        self.assertEqual(self.clipboard.text(), 'original')
        self.win._play_confirmation.assert_called_once()

    def test_neighbors_are_preserved(self):
        self.engine.save('/ola', 'OK')
        self.engine.field.text = 'BEFORE  AFTER'
        self.engine.field.caret = self.engine.field.anchor = 7
        self.expand()
        self.assertEqual(self.engine.field.text, 'BEFORE OK AFTER')

    def test_additional_typing_before_selection_cancels_without_editing(self):
        for delay in (0, 20, 50):
            with self.subTest(delay=delay), EngineFixture() as e:
                e.type('/ola')
                e.schedule(delay, lambda: e.type('x'))
                e.drain()
                self.assertEqual(e.field.text, '/olax')
                self.assertEqual(e.api_calls, 0)
                self.assertEqual(e.clipboard.text(), 'original')

    def test_queued_signal_invalidated_by_new_input(self):
        self.engine.defer_signal = True
        self.engine.type('/ola')
        self.engine.type('x')
        self.win._expand_global(self.engine.received[0])
        self.engine.drain()
        self.assertEqual(self.engine.field.text, '/olax')
        self.engine.replace.assert_not_called()

    def test_queued_signal_does_not_capture_new_destination(self):
        self.engine.defer_signal = True
        self.engine.type('/ola')
        self.engine.window_id, self.engine.field_id = 202, 2
        self.win._expand_global(self.engine.received[0])
        self.engine.drain()
        self.assertEqual(self.engine.fields[1].text, '/ola')
        self.assertEqual(self.engine.fields[2].text, 'OTHER')
        self.engine.replace.assert_not_called()

    def test_pause_cancels_already_scheduled_expansion(self):
        self.engine.type('/ola')
        self.win._toggle_listener()
        self.engine.drain()
        self.assertEqual(self.engine.field.text, '/ola')
        self.engine.replace.assert_not_called()

    def test_same_window_different_field_cancels(self):
        self.engine.type('/ola')
        self.engine.field_id = 2
        self.engine.drain()
        self.assertEqual(self.engine.fields[1].text, '/ola')
        self.assertEqual(self.engine.fields[2].text, 'OTHER')
        self.engine.replace.assert_not_called()

    def test_partial_shortcut_does_not_cross_fields(self):
        self.engine.type('/ol')
        self.engine.field_id = 2
        self.engine.type('a')
        self.engine.drain()
        self.assertEqual(self.engine.fields[2].text, 'OTHERa')
        self.engine.replace.assert_not_called()

    def test_focus_history_and_mouse_invalidate_even_after_return(self):
        for activity in (self.engine.listener.invalidate,
                         lambda: self.engine.listener._on_click(0, 0, None, True)):
            self.engine.field.text = ''
            self.engine.field.caret = self.engine.field.anchor = 0
            self.engine.type('/ola')
            activity()
            self.engine.drain()
            self.assertEqual(self.engine.field.text, '/ola')
        self.engine.replace.assert_not_called()

    def test_changed_caret_cancels_before_selecting_neighbors(self):
        self.engine.type('/ola')
        self.engine.field.caret = self.engine.field.anchor = 0
        self.engine.drain()
        self.assertEqual(self.engine.field.text, '/ola')
        self.engine.replace.assert_not_called()

    def test_unhonored_selection_never_reports_success_or_deletes_original(self):
        self.engine.ignore_selection = True
        self.expand()
        self.assertIn('/ola', self.engine.field.text)
        self.engine.replace.assert_called_once()
        self.assertEqual(self.clipboard.text(), 'original')
        self.win._play_confirmation.assert_not_called()

    def test_focus_change_during_payload_preparation_cancels_before_batch(self):
        original_set = self.clipboard.setMimeData
        def change_focus(mime):
            original_set(mime)
            self.engine.field_id = 2
        with patch.object(self.clipboard, 'setMimeData', side_effect=change_focus):
            self.expand()
        self.assertEqual(self.engine.fields[2].text, 'OTHER')
        self.assertEqual(self.engine.fields[1].text, '/ola')
        self.engine.replace.assert_not_called()

    def test_paste_rejection_never_reports_success_or_retries(self):
        self.engine.reject_paste = True
        self.expand()
        self.assertEqual(self.engine.field.text, '/ola')
        self.engine.replace.assert_called_once()
        self.win._play_confirmation.assert_not_called()
        self.assertFalse(any(str(c.args[0]).startswith('Expandido:') for c in self.engine.status.showMessage.call_args_list))
        self.assertEqual(self.clipboard.text(), 'original')

    def test_repeated_fast_expansions_without_waiting_for_clipboard_timer(self):
        self.engine.save('/ola', 'OK')
        for _ in range(10):
            self.engine.type('/ola')
            self.engine.until(self.engine.now + 100)
        self.assertEqual(self.engine.field.text, 'OK' * 10)
        self.assertEqual(self.win._play_confirmation.call_count, 10)
        self.assertEqual(self.clipboard.text(), 'original')

    def test_duplicate_candidate_and_old_callback_are_noops(self):
        self.engine.type('/ola')
        candidate = self.engine.received[-1]
        self.win._expand_global(candidate)
        self.engine.drain()
        first = self.engine.field.text
        self.engine.type('/ola')
        self.win._perform_expansion(candidate)
        self.engine.drain()
        self.assertEqual(self.engine.field.text, first * 2)
        self.assertEqual(self.engine.replace.call_count, 2)

    def test_old_restore_cannot_restore_or_unlock_new_lease(self):
        self.engine.type('/ola')
        self.engine.until(75)
        old = self.win._clipboard_lease
        self.engine.until(100)
        self.engine.type('/ola')
        self.engine.until(175)
        new = self.win._clipboard_lease
        self.assertIsNot(old, new)
        self.win._restore_clipboard(old)
        self.assertIs(self.win._clipboard_lease, new)
        self.assertTrue(self.win._clipboard_pending)
        self.engine.drain()
        self.assertEqual(self.clipboard.text(), 'original')

    def test_clipboard_new_copy_with_same_text_and_token_preserves_sequence(self):
        self.engine.type('/ola')
        self.engine.until(75)
        mime = self.win._clone_clipboard_mime()
        mime.setHtml('<b>NEW COPY</b>')
        self.clipboard.setMimeData(mime)
        self.engine.drain()
        self.assertEqual(self.clipboard.mime.html(), '<b>NEW COPY</b>')

    def test_new_copy_during_delayed_consumption_is_not_overwritten_or_confirmed(self):
        self.engine.paste_delay = 100
        self.engine.type('/ola')
        self.engine.schedule(100, lambda: self.clipboard.setText('NEW COPY'))
        self.engine.drain()
        self.assertEqual(self.clipboard.text(), 'NEW COPY')
        self.win._play_confirmation.assert_not_called()
        self.engine.replace.assert_called_once()

    def test_sent_cursor_expansion_does_not_expire_during_web_confirmation(self):
        self.engine.save('/ola', 'A{{cursor}}B')
        self.engine.type('/ola')
        self.engine.until(75)
        operation = self.win._expansion_operation
        self.assertIsNotNone(operation)
        self.assertEqual(operation.stage, 'sent')
        # Simulate a slow web accessibility provider after SendInput.
        object.__setattr__(operation.candidate, 'created', -2.0)
        self.assertTrue(self.win._candidate_valid(operation.candidate))
        self.engine.drain()
        self.assertEqual(self.engine.field.text, 'AB')
        self.engine.type('X')
        self.assertEqual(self.engine.field.text, 'AXB')
        self.win._play_confirmation.assert_called_once()

    def test_sent_cursor_expansion_still_rejects_real_input_change(self):
        self.engine.save('/ola', 'A{{cursor}}B')
        self.engine.type('/ola')
        self.engine.until(75)
        operation = self.win._expansion_operation
        self.assertIsNotNone(operation)
        self.engine.listener.invalidate()
        self.assertFalse(self.win._candidate_valid(operation.candidate))
        self.engine.drain()
        self.win._play_confirmation.assert_not_called()

    def test_cursor_waits_for_delayed_paste_instead_of_collapsing_selection(self):
        self.engine.save('/ola', 'A{{cursor}}B')
        self.engine.paste_delay = 250
        self.expand()
        self.engine.type('X')
        self.assertEqual(self.engine.field.text, 'AXB')
        self.engine.position.assert_called_once()
        self.assertEqual(self.engine.position.call_args.args[1], 1)
        self.engine.move.assert_not_called()

    def test_late_paste_does_not_move_cursor_or_report_success(self):
        self.engine.save('/ola', 'A{{cursor}}B')
        self.engine.paste_delay = 2000
        self.expand()
        self.engine.move.assert_not_called()
        self.win._play_confirmation.assert_not_called()
        self.assertEqual(self.engine.field.text, 'AB')
        self.assertEqual(self.clipboard.text(), 'original')

    def test_cursor_begin_middle_end_and_unicode(self):
        for content, expected in (('{{cursor}}AB', 'XAB'), ('A{{cursor}}B', 'AXB'),
                                  ('AB{{cursor}}', 'ABX'), ('Olá {{cursor}}😀e\u0301\r\nfim', 'Olá X😀e\u0301\r\nfim')):
            with self.subTest(content=content), EngineFixture() as e:
                e.save('/ola', content)
                e.type('/ola')
                e.drain()
                e.type('X')
                self.assertEqual(e.field.text, expected)
                e.host._play_confirmation.assert_called_once()

    def test_special_and_unicode_shortcuts(self):
        for shortcut in ('/;', '/?', '/ç', '/é', '/e\u0301'):
            with self.subTest(shortcut=shortcut), EngineFixture() as e:
                e.save(shortcut, 'Ação 😀')
                e.type(shortcut)
                e.drain()
                self.assertEqual(e.field.text, 'Ação 😀')

    def test_own_events_are_tagged_and_do_not_invalidate_candidate(self):
        self.expand()
        self.assertTrue(self.engine.sent)
        self.assertTrue(all(tag == INJECTION_TAG for _, _, tag in self.engine.sent))
        self.assertTrue(all(flags & 1 for vk, flags, _ in self.engine.sent if vk == 37))
        self.win._play_confirmation.assert_called_once()
        self.assertTrue(self.engine.listener._win32_event_filter(0, SimpleNamespace(dwExtraInfo=123)))

    def test_expansion_containing_shortcut_does_not_recurse(self):
        self.engine.save('/auto', '/ola')
        self.expand('/auto')
        self.assertEqual(self.engine.field.text, '/ola')
        self.assertEqual(len(self.engine.received), 1)
        self.engine.type(' /ola')
        self.engine.drain()
        self.assertNotIn('/ola', self.engine.field.text[5:])

    def test_partial_send_cleanup_and_next_operation(self):
        for call, size in ((1, 14),):
            for prefix in range(size):
                with self.subTest(call=call, prefix=prefix), EngineFixture() as e:
                    e.fail_call, e.fail_prefix = call, prefix
                    e.type('/ola')
                    e.drain()
                    self.assertFalse(e.shift or e.ctrl)
                    self.assertEqual(e.clipboard.text(), 'original')
                    e.host._play_confirmation.assert_not_called()
                    before = e.field.text
                    e.field.caret = e.field.anchor = utf16_length(before)
                    e.type(' /ola')
                    e.drain()
                    payload = next(s.content for s in e.store.snippets() if s.shortcut == '/ola')
                    self.assertEqual(e.field.text, before + ' ' + payload)
                    self.assertEqual(e.replace.call_count, 2)
                    self.assertEqual(e.host._play_confirmation.call_count, 1)

    def test_unknown_control_reports_unconfirmed_and_cursor_refuses_before_edit(self):
        self.engine.readable = False
        self.expand()
        # O som indica que o Ctrl+V foi acionado, não que o browser confirmou.
        self.win._play_confirmation.assert_called_once()
        self.assertEqual(self.clipboard.text(), 'original')
        with EngineFixture() as e:
            e.readable = False
            e.save('/ola', 'A{{cursor}}B')
            e.type('/ola')
            e.drain()
            self.assertEqual(e.field.text, '/ola')
            e.replace.assert_not_called()

    def test_clipboard_variable_does_not_use_pending_internal_payload(self):
        self.engine.save('/echo', '{{clipboard}}')
        self.engine.type('/ola')
        self.engine.until(95)
        self.engine.type(' /echo')
        self.engine.drain()
        self.assertTrue(self.engine.field.text.endswith(' original'))
