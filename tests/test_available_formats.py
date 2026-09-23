import unittest
from unittest.mock import patch
from discovery.sources import metadata,youtube_candidate
from discovery.settings import DEFAULTS

class FormatTests(unittest.TestCase):
    def test_hd_stream_beats_low_selected_format(self):
        result=dict(width=360,height=640,formats=[dict(width=1080,height=1920,vcodec='avc1',url='https://example.com/video')])
        with patch('discovery.sources.ytdlp',return_value=result),patch('discovery.store.event'):
            self.assertEqual(metadata('https://youtu.be/x',DEFAULTS)['height'],1920)
    def test_audio_storyboard_and_drm_ignored(self):
        result=dict(width=360,height=640,formats=[dict(width=1080,height=1920,vcodec='none',url='x'),dict(width=1080,height=1920,vcodec='avc1',url='x',has_drm=True)])
        with patch('discovery.sources.ytdlp',return_value=result),patch('discovery.store.event'):
            self.assertEqual(metadata('https://youtu.be/x',DEFAULTS)['height'],640)
    def test_low_search_resolution_reaches_metadata(self):
        self.assertTrue(youtube_candidate(dict(url='https://youtube.com/shorts/x',width=360,height=640,duration=20),DEFAULTS))
