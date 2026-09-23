import unittest
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
from discovery.sources import youtube_search_url,youtube_candidate,discover
from discovery.settings import DEFAULTS

class ShortsTests(unittest.TestCase):
    def test_search_preserves_query(self):
        u=youtube_search_url('funny #shorts & cats')
        self.assertEqual(parse_qs(urlsplit(u).query)['search_query'],['funny #shorts & cats'])
        self.assertNotIn('sp=',u)
    def test_hashtag_does_not_make_a_short(self):
        self.assertFalse(youtube_candidate({'title':'Funny #shorts','url':'https://www.youtube.com/watch?v=x','duration':20},{**DEFAULTS,'youtube_shorts_only':True}))
    def test_short_unknown_duration_reaches_metadata(self):
        self.assertTrue(youtube_candidate({'url':'https://www.youtube.com/shorts/x'},DEFAULTS))
    def test_known_long_short_excluded(self):
        self.assertFalse(youtube_candidate({'url':'https://www.youtube.com/shorts/x','duration':201},DEFAULTS))
    def test_search_filters_before_saving(self):
        cfg={**DEFAULTS,'queries':['funny'],'reddit_search':False,'source_urls':[]}
        response={'entries':[{'url':'https://www.youtube.com/watch?v=long','title':'#shorts'}, {'url':'https://www.youtube.com/shorts/good','duration':20,'title':'Good'}]}
        with patch('discovery.sources.ytdlp',return_value=response) as call,patch('discovery.store.add') as add,patch('discovery.store.event'),patch('discovery.store.rows',return_value=[]):
            discover(cfg)
        self.assertIn('/results?',call.call_args.args[0])
        add.assert_called_once_with('https://www.youtube.com/watch?v=good','Good','youtube')

if __name__=='__main__':unittest.main()
