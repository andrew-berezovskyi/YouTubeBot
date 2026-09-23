import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import config
from discovery import screening, sources, service, store
from discovery.settings import DEFAULTS,load

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.p=patch.object(config,'BASE_DIR',self.root);self.p.start()
        self.db=patch.object(config,'DATABASE_FILE',self.root/'original.db');self.db.start()
        self.cfg={**DEFAULTS,'queries':['funny'],'youtube_search':True,'reddit_search':False,'approved_video_urls':['https://www.youtube.com/watch?v=abc'],'min_height':100}
    def tearDown(self):self.db.stop();self.p.stop();self.temp.cleanup()
    def test_canonical_video_and_host_validation(self):
        self.assertEqual(sources.canonical_url('https://youtu.be/abc?si=tracking'),sources.canonical_url('https://www.youtube.com/shorts/abc'))
        for url in ('file:///tmp/video','https://youtube.com.evil.test/a','https://localhost/a','https://user:pass@youtube.com/a'):
            with self.assertRaises(ValueError):sources.canonical_url(url)
    def test_permission_exact_not_substring(self):
        self.assertTrue(sources.permitted('https://youtu.be/abc',{},self.cfg))
        self.assertFalse(sources.permitted('https://youtu.be/abcd',{'license':'Creative Commons'},self.cfg))
    def test_no_silent_clear_on_ocr_or_model_failure(self):
        clear={'status':'clear','confidence':.95,'topic_score':.9}
        self.assertEqual(screening.classify([clear],self.cfg)[0],'clear')
        self.assertEqual(screening.classify([{**clear,'ocr_suspect':True}],self.cfg)[0],'uncertain')
        self.assertEqual(screening.classify([clear,{'status':'uncertain'}],self.cfg)[0],'uncertain')
        self.assertEqual(screening.classify([{**clear,'status':'detected','confirmed':True,'mark_kind':'overlay'}],self.cfg)[0],'detected')
    def test_sampling_includes_end_and_is_bounded(self):
        times=screening.sample_times(90,self.cfg)
        self.assertEqual(times[0],0);self.assertAlmostEqual(times[-1],89.85)
        self.assertLessEqual(len(times),self.cfg['max_frames'])
    def test_fingerprints(self):
        a={'duration':20,'hashes':['a123456789abcdef']*6}
        self.assertTrue(screening.near_duplicate(a,a))
        self.assertFalse(screening.near_duplicate(a,{**a,'duration':40}))
        self.assertFalse(screening.near_duplicate(a,{'duration':20,'hashes':['0000000000000000']*6}))
    def test_limits_and_crash_recovery(self):
        store.add('https://youtu.be/abc','Test','youtube');r=store.rows()[0]
        store.update(r['id'],status='uploading')
        service.recover();self.assertEqual(store.rows()[0]['status'],'upload_uncertain')
        self.assertIsNotNone(store.reserve_upload(r['id'],self.cfg))
        self.assertIsNone(store.reserve_upload(r['id'],self.cfg))
    def test_worker_lock(self):
        with service.worker_lock():
            with self.assertRaises(RuntimeError):
                with service.worker_lock():pass
        with service.worker_lock():pass
    def test_invalid_settings(self):
        (self.root/'discovery_settings.json').write_text('{"max_frames":1}')
        with self.assertRaises(ValueError):load()
    def test_download_screen_and_deduplicate_flow(self):
        store.add('https://www.youtube.com/watch?v=abc','Test','youtube')
        info={'title':'Test','duration':10,'width':180,'height':320}
        def download(url,cfg,folder):
            p=folder/'video.mp4';p.write_bytes(b'fake-media-fixture');return p
        report={'status':'clear','reason':'clear','fingerprint':{'duration':10,'hashes':['abcd123412341234']*3},'evidence':[]}
        with patch.object(sources,'discover'),patch.object(sources,'metadata',return_value=info),patch.object(sources,'ytdlp',side_effect=download),patch.object(screening,'screen',return_value=report):
            service.cycle(self.cfg)
            self.assertEqual(store.rows()[0]['status'],'ready')
            store.add('https://www.youtube.com/watch?v=def','Copy','youtube')
            cfg={**self.cfg,'approved_video_urls':self.cfg['approved_video_urls']+['https://www.youtube.com/watch?v=def']}
            service.cycle(cfg)
            self.assertEqual(store.rows()[0]['status'],'duplicate')
    def test_permission_block_does_not_download(self):
        store.add('https://www.youtube.com/watch?v=unapproved','Test','youtube')
        with patch.object(sources,'discover'),patch.object(sources,'metadata',return_value={}),patch.object(sources,'ytdlp') as dl:
            service.cycle(self.cfg)
            dl.assert_not_called();self.assertEqual(store.rows()[0]['status'],'needs_permission')
    def test_stdlib_queue_still_works(self):
        import queue
        q=queue.Queue();q.put(3);self.assertEqual(q.get(),3)
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:self.assertEqual(pool.submit(lambda:4).result(),4)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe') and shutil.which('tesseract'),'Requires FFmpeg and Tesseract')
class MediaTests(unittest.TestCase):
    def test_real_media_and_ocr_with_mocked_vision(self):
        import pytesseract
        from PIL import Image,ImageDraw,ImageFont
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);still=folder/'source.png'
            im=Image.new('RGB',(360,640),'white');draw=ImageDraw.Draw(im)
            font=ImageFont.truetype('DejaVuSans.ttf',28)
            draw.text((25,40),'@TestCreator',fill='black',font=font);im.save(still)
            video=folder/'input.mp4'
            subprocess.run(['ffmpeg','-loglevel','error','-y','-loop','1','-i',str(still),'-t','6','-r','5','-pix_fmt','yuv420p',str(video)],check=True)
            cfg={**DEFAULTS,'min_height':100,'max_frames':3}
            with patch.object(config,'FFMPEG',Path(shutil.which('ffmpeg'))),patch.object(config,'FFPROBE',Path(shutil.which('ffprobe'))),patch.object(screening,'vision',return_value={'status':'clear','confidence':.99,'topic_score':.99}):
                report=screening.screen(video,folder/'frames',cfg)
            self.assertEqual(report['status'],'uncertain')
            self.assertTrue(any('@TestCreator' in e.get('ocr_text','') for e in report['evidence']))
            self.assertTrue(all(Path(e['frame']).is_file() for e in report['evidence']))



class PipelineIntegrationTests(unittest.TestCase):
    setUp = DiscoveryTests.setUp
    tearDown = DiscoveryTests.tearDown
    # Only the integration test is selected in the suite below through normal discovery;
    # inherited tests also exercise an independent database fixture.
    def test_original_queue_handoff_without_real_upload(self):
        import main
        from database import db
        from queue import manager
        media=self.root/'download.mp4';media.write_bytes(b'fixture-accepted')
        store.add('https://www.youtube.com/watch?v=abc','Ready video','youtube')
        row=store.rows()[0]
        store.update(row['id'],status='ready',path=str(media),sha256=screening.sha256(media),info='{}')
        def fake_pipeline(state,item):
            db.update_video(item['video_id'],status='published',youtube_url='https://www.youtube.com/watch?v=test_result')
            manager.mark_done(item['id'])
        with patch.object(db,'DATABASE_FILE',self.root/'bot.db'),patch.object(config,'TO_UPLOAD',self.root/'ToUpload'),patch.object(main,'process_queue_item',side_effect=fake_pipeline) as pipe:
            service.process_ready(self.cfg)
            self.assertEqual(pipe.call_count,1)
            self.assertEqual(store.rows()[0]['status'],'published')
            self.assertFalse(media.exists())
            self.assertEqual(main.UPLOAD_VISIBILITY,'private')

if __name__=="__main__": unittest.main()
