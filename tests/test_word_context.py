import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.expansion import ExpansionCandidate, ExpansionOperation, FocusContext, ClipboardLease
from app.word_context import submit_word


class WordContextTests(unittest.TestCase):
    def operation(self):
        op=ExpansionOperation(ExpansionCandidate(1,'/word',2,FocusContext(123,456)),None,'Antes depois',6,'Antes ')
        op.lease=ClipboardLease(1,None,op.text,b'0123456789abcdef0123456789abcdef',1)
        return op

    def result(self,pending):
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            result=pending.poll()
            if result is not None:return result
            time.sleep(.001)
        self.fail('Word request did not finish')

    def test_timeout_after_dispatch_is_uncertain_and_never_retried(self):
        client=SimpleNamespace(warm=Mock(),ready=True,request=Mock(side_effect=OSError('transport timeout')))
        with patch('app.word_context._client',client),patch('sys.platform','win32'):
            result=self.result(submit_word(self.operation()))
        self.assertEqual(result['status'],'uncertain')
        client.request.assert_called_once()

    def test_cancel_before_worker_ready_does_not_dispatch_any_request(self):
        client=SimpleNamespace(warm=Mock(),ready=False,request=Mock())
        with patch('app.word_context._client',client),patch('sys.platform','win32'):
            pending=submit_word(self.operation());pending.cancelled.set()
            result=self.result(pending)
        self.assertEqual(result['status'],'cancelled')
        client.request.assert_not_called()

    def test_only_original_context_and_resolved_content_are_sent(self):
        client=SimpleNamespace(warm=Mock(),ready=True,request=Mock(return_value={'status':'pasted'}))
        with patch('app.word_context._client',client),patch('sys.platform','win32'):
            self.assertEqual(self.result(submit_word(self.operation()))['status'],'pasted')
        args,fields=client.request.call_args
        self.assertEqual(fields['window'],'123')
        self.assertEqual(fields['control'],'456')
        self.assertEqual(fields['shortcut'],'/word')
        self.assertEqual(fields['cursor_prefix'],'Antes ')
        self.assertEqual(fields['text'],'Antes depois')
