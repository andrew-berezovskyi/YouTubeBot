import json
import unittest
from unittest.mock import patch
from discovery.settings import DEFAULTS
from discovery.sources import youtube_candidate,discover,sanitize_error
from discovery.screening import technical_reason,probe
from discovery.runtime import available_runtime,runtime_args

class VerticalTests(unittest.TestCase):
    def test_boundaries(self):
        for duration in (91,120,180):
            self.assertEqual(technical_reason(dict(duration=duration,width=1080,height=1920),DEFAULTS),'')
        self.assertIn('181',technical_reason(dict(duration=181),DEFAULTS))
    def test_portrait_not_hashtag(self):
        for w,h in ((1920,1080),(1080,1080)):
            self.assertFalse(youtube_candidate(dict(url='https://www.youtube.com/shorts/x',width=w,height=h,duration=20),DEFAULTS))
        self.assertTrue(youtube_candidate(dict(url='https://www.youtube.com/watch?v=x',width=1080,height=1920,duration=120),DEFAULTS))
    def test_nonfinite_duration(self):
        for d in (float('nan'),float('inf')):self.assertTrue(technical_reason(dict(duration=d),DEFAULTS))
    def test_rotation_and_pixel_aspect(self):
        stream=dict(codec_type='video',width=1920,height=1080,sample_aspect_ratio='1:1',side_data_list=[dict(rotation=-90)])
        with patch('discovery.screening.subprocess.run') as run:
            run.return_value.stdout=json.dumps(dict(streams=[stream],format=dict(duration='120')))
            self.assertEqual(probe('video.mp4')['height'],1920)
            stream.update(width=1000,height=1200,sample_aspect_ratio='2:1',side_data_list=[])
            run.return_value.stdout=json.dumps(dict(streams=[stream],format=dict(duration='120')))
            self.assertIn('Not a vertical',technical_reason(probe('video.mp4'),DEFAULTS))
    def test_known_does_not_consume_quota(self):
        cfg={**DEFAULTS,'queries':['cats'],'results_per_query':1,'reddit_search':False}
        info=dict(entries=[dict(url='https://www.youtube.com/shorts/old',duration=20),dict(url='https://www.youtube.com/shorts/new',duration=20)])
        with patch('discovery.store.rows',return_value=[dict(url='https://www.youtube.com/watch?v=old')]),patch('discovery.sources.ytdlp',return_value=info),patch('discovery.store.event'),patch('discovery.store.add') as add:
            discover(cfg)
            self.assertEqual(add.call_args.args[0],'https://www.youtube.com/watch?v=new')
    def test_actual_error_first(self):
        message=sanitize_error('WARNING: No supported JavaScript runtime could be found\nERROR: This video is not available')
        self.assertTrue(message.startswith('ERROR:'))
    def test_runtime_explicit_argument(self):
        with patch('discovery.runtime.available_runtime',return_value=('deno','C:/Program Files/deno.exe','deno 2.3.0')):
            self.assertEqual(runtime_args(),['--js-runtimes','deno:C:/Program Files/deno.exe'])
