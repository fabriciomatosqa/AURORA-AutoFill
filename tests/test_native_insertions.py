"""Tracked web replacement and Word's source-formatting handoff."""
import unittest
from threading import Event
from unittest.mock import Mock, patch

from engine_fixture import EngineFixture


class NativeInsertions(unittest.TestCase):
    def test_copy_and_selection_handlers_cannot_block_tracked_web_expansion(self):
        for executable in ('ms-teams.exe','teams.exe','chrome.exe','msedge.exe','firefox.exe'):
            with self.subTest(executable=executable), EngineFixture() as e:
                e.save('/teste','Colorida 😀','<span style="color:#ff0000;background-color:#00ff00">Colorida 😀</span>')
                e.field.insert('Earlier /teste\nPrefix 😀 ')
                with patch('app.verified_fallback.focused_executable',return_value=executable), \
                     patch('app.ui.capture_edit',side_effect=AssertionError('No UIA read required')), \
                     patch('app.ui.copy_selected_text',side_effect=AssertionError('No Ctrl+C')), \
                     patch('app.ui.select_previous_characters',side_effect=AssertionError('No Shift+Left')):
                    e.type('/teste');e.drain()
                self.assertEqual(e.field.text,'Earlier /teste\nPrefix 😀 Colorida 😀')
                self.assertEqual(e.api_calls,1)
                self.assertEqual(sum(vk==86 and not f&2 for vk,f,_ in e.sent),1)
                self.assertFalse(any(vk in (67,37,16,13) for vk,_,_ in e.sent))
                self.assertEqual(e.clipboard.text(),'original')

    def test_stale_or_changed_candidates_never_erase_text(self):
        for mutation in ('typing','focus','mouse','paused','stale'):
            with self.subTest(mutation=mutation), EngineFixture() as e:
                e.save('/teste','Resposta');e.defer_signal=True
                with patch('app.verified_fallback.focused_executable',return_value='ms-teams.exe'):
                    e.type('/teste');candidate=e.received[-1]
                    if mutation=='typing':e.type('X')
                    elif mutation=='focus':e.field_id=2
                    elif mutation=='mouse':e.listener.invalidate()
                    elif mutation=='paused':e.host._hotkeys_enabled=False
                    else:e.now=2000
                    e.host._expand_global(candidate);e.drain()
                self.assertEqual(e.fields[1].text,'/testeX' if mutation=='typing' else '/teste')
                self.assertEqual(e.api_calls,0)

    def test_partial_native_input_is_never_repeated(self):
        with EngineFixture() as e:
            e.save('/teste','Resposta');e.fail_call=1;e.fail_prefix=4
            with patch('app.verified_fallback.focused_executable',return_value='ms-teams.exe'):
                e.type('/teste');e.drain()
            # One attempted batch plus modifier cleanup, no second insertion.
            self.assertEqual(e.api_calls,2)
            self.assertFalse(any(vk==86 for vk,_,_ in e.sent))
            self.assertEqual(e.clipboard.text(),'original')

    def test_hardware_scan_codes_are_supplied_with_virtual_keys(self):
        import ctypes
        from app.hotkeys import replace_tracked_shortcut
        with EngineFixture() as e:
            e.field.insert('/t')
            codes={8:14,17:29,86:47}
            ctypes.windll.user32.MapVirtualKeyW=Mock(side_effect=lambda vk,_:codes[vk])
            e.clipboard.setText('R')
            original=e.send
            captured=[]
            def send(count,records,size):
                captured.extend((r.u.ki.wVk,r.u.ki.wScan) for r in list(records))
                return original(count,records,size)
            e.send=send
            replace_tracked_shortcut(2)
            self.assertEqual(e.field.text,'R')
            self.assertTrue(all(scan==codes[vk] for vk,scan in captured))

    def test_word_uses_native_range_and_keeps_rich_cursor_payload(self):
        with EngineFixture() as e:
            e.save('/word','Antes {{cursor}}depois','<b style="color:#ff0000">Antes {{cursor}}depois</b>')
            pending=Mock(cancelled=Event())
            pending.poll.return_value={'status':'pasted','confirmed':True,'cursor':True}
            captured=[]
            def submit(op):
                captured.append((op.cursor_prefix,op.rich_html,op.lease.token,
                                 bytes(e.clipboard.mimeData().data('application/x-qt-windows-mime;value="AURORA Expansion"'))))
                return pending
            with patch('app.verified_fallback.focused_executable',return_value='winword.exe'), \
                 patch('app.ui.capture_edit',side_effect=AssertionError('Word uses native range')), \
                 patch('app.ui.submit_word',side_effect=submit) as call:
                e.type('/word');e.drain()
            call.assert_called_once()
            self.assertEqual(e.api_calls,0)
            self.assertEqual(captured[0][0],'Antes ')
            self.assertIn('#ff0000',captured[0][1])
            self.assertNotIn('{{cursor}}',captured[0][1])
            self.assertEqual(captured[0][2],captured[0][3])
            self.assertEqual(e.clipboard.text(),'original')

    def test_word_uncertain_or_changed_result_never_falls_back_to_ctrl_v(self):
        for status in ('uncertain','changed','unavailable'):
            with self.subTest(status=status), EngineFixture() as e:
                e.save('/word','Resposta','<b>Resposta</b>')
                pending=Mock(cancelled=Event());pending.poll.return_value={'status':status}
                with patch('app.verified_fallback.focused_executable',return_value='winword.exe'), \
                     patch('app.ui.submit_word',return_value=pending) as submit:
                    e.type('/word');e.drain()
                self.assertEqual(e.field.text,'/word')
                self.assertEqual(e.api_calls,0)
                submit.assert_called_once()
                self.assertEqual(e.clipboard.text(),'original')

    def test_word_request_is_cancelled_when_focus_changes_while_pending(self):
        with EngineFixture() as e:
            e.save('/word','Resposta')
            pending=Mock(cancelled=Event())
            pending.poll.side_effect=[None,{'status':'changed'}]
            with patch('app.verified_fallback.focused_executable',return_value='winword.exe'), \
                 patch('app.ui.submit_word',return_value=pending):
                e.type('/word');e.schedule(15,lambda:setattr(e,'field_id',2));e.drain()
            self.assertTrue(pending.cancelled.is_set())
            self.assertEqual(e.fields[1].text,'/word')
            self.assertEqual(e.fields[2].text,'OTHER')
            self.assertEqual(e.api_calls,0)
