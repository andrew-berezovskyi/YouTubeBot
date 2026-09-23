import tempfile
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import config
from discovery import sources,store,service
from discovery.settings import DEFAULTS

class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.patch=patch.object(config,'BASE_DIR',Path(self.tmp.name));self.patch.start()
        self.cfg={**DEFAULTS,'reddit_search':False,'max_candidates_per_cycle':1}
    def tearDown(self):self.patch.stop();self.tmp.cleanup()
    def test_disabled_source_and_exhausted_retry_do_not_consume_limit(self):
        store.add('https://www.reddit.com/r/test/comments/1','Old','reddit')
        store.add('https://www.youtube.com/watch?v=old','Old failure','youtube')
        store.update(store.rows()[0]['id'],status='error',attempts=3)
        store.add('https://www.youtube.com/watch?v=new','Fresh','youtube')
        result=service.pending_candidates(self.cfg)
        self.assertEqual([r['title'] for r in result],['Fresh'])
    def test_cooldown_does_not_consume_limit(self):
        store.add('https://www.youtube.com/watch?v=old','Waiting','youtube')
        store.update(store.rows()[0]['id'],status='error',attempts=1)
        store.add('https://www.youtube.com/watch?v=new','Fresh','youtube')
        self.assertEqual(service.pending_candidates(self.cfg)[0]['title'],'Fresh')
    def test_timeouts_are_separate(self):
        self.assertEqual(sources.request_timeout(self.cfg,kind='search'),45)
        self.assertEqual(sources.request_timeout(self.cfg),60)
        self.assertEqual(sources.request_timeout(self.cfg,True),600)
    def test_metadata_interruption_recovers(self):
        store.add('https://www.youtube.com/watch?v=a','Test','youtube')
        store.update(store.rows()[0]['id'],status='metadata')
        service.recover()
        self.assertEqual(store.rows()[0]['status'],'error')
    def test_progress_and_heartbeat(self):
        store.progress('Metadata 7',60);before=store.current_progress()
        store.heartbeat();after=store.current_progress()
        self.assertEqual(after['phase'],'Metadata 7')
        self.assertEqual(after['started'],before['started'])
        self.assertGreaterEqual(after['heartbeat'],before['heartbeat'])
    def test_error_redaction_keeps_cause(self):
        raw='ERROR: HTTP Error 403: Forbidden https://host/video?token=abc\nAuthorization: Bearer SECRET\ntoken=PRIVATE'
        result=sources.sanitize_error(raw)
        self.assertIn('403',result)
        for secret in ('SECRET','PRIVATE','abc','https://host'):self.assertNotIn(secret,result)
    def test_real_subprocess_timeout_kills_child(self):
        with subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as child:
            start=time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):sources.wait_for_process(child,.1)
            self.assertIsNotNone(child.poll())
            self.assertLess(time.monotonic()-start,5)
    def test_subprocess_success(self):
        with subprocess.Popen([sys.executable,'-c','pass']) as child:
            self.assertEqual(sources.wait_for_process(child,5),0)
    def test_disabled_source_blocks_ready(self):
        self.assertFalse(sources.enabled_candidate({'url':'https://www.reddit.com/r/x/comments/y','source':'configured'},self.cfg))
        self.assertTrue(sources.enabled_candidate({'url':'https://www.youtube.com/watch?v=x','source':'youtube'},self.cfg))

if __name__=='__main__':unittest.main()
