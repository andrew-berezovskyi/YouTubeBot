import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from discovery.vision_checks import validate_mark,InspectionError,analyze,request_json,SCHEMA
from discovery.screening import classify
from discovery.settings import DEFAULTS

class VisionTests(unittest.TestCase):
    def mark(self,kind='none',reason='No visible watermark'):
        return dict(kind=kind,confidence=.95,location='upper left',mark_text='@author',reason=reason)
    def test_contradictions_fail(self):
        for reason in ('No visible watermark in this image','It is not a watermark','Text on the apron','A physical award'):
            with self.assertRaises(InspectionError):validate_mark(self.mark('overlay',reason))
    def test_objects_are_not_watermarks(self):
        for kind in ('none','clothing','physical_object','subtitle'):
            with patch('discovery.vision_checks.request_json',side_effect=[self.mark(kind),dict(topic_score=.9)]):
                result=analyze(Path('frame.jpg'),DEFAULTS)
                self.assertEqual(classify([result],DEFAULTS)[0],'clear')
    def test_requires_confirmation(self):
        with patch('discovery.vision_checks.request_json',side_effect=[self.mark('overlay','Digital handle overlay'),self.mark('physical_object')]):
            result=analyze(Path('frame.jpg'),DEFAULTS)
            self.assertEqual(classify([result],DEFAULTS)[0],'uncertain')
    def test_real_overlay_can_be_rejected(self):
        mark=self.mark('overlay','Digital handle overlay')
        with patch('discovery.vision_checks.request_json',return_value=mark):
            self.assertEqual(classify([analyze(Path('frame.jpg'),DEFAULTS)],DEFAULTS)[0],'detected')
    def test_old_unsubstantiated_detection_not_accepted(self):
        self.assertEqual(classify([dict(status='detected',confidence=.95,topic_score=.9)],DEFAULTS)[0],'uncertain')
    def test_truncated_retries_and_saves_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            frame=Path(tmp)/'frame.jpg';frame.write_bytes(b'fake')
            values=[json.dumps(dict(done=True,done_reason='length',message=dict(content='{'))).encode(),json.dumps(dict(done=True,done_reason='stop',message=dict(content=json.dumps(self.mark())))).encode()]
            with patch('discovery.vision_checks.urlopen') as op:
                op.return_value.__enter__.return_value.read.side_effect=values
                self.assertEqual(request_json(frame,DEFAULTS,'prompt',SCHEMA,validate_mark,'watermark')['kind'],'none')
                self.assertEqual(op.call_count,2)
            self.assertTrue((Path(tmp)/'frame_watermark_diagnostic.json').exists())
    def test_repeated_bad_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            frame=Path(tmp)/'frame.jpg';frame.write_bytes(b'fake')
            with patch('discovery.vision_checks.urlopen') as op:
                op.return_value.__enter__.return_value.read.return_value=b'bad json'
                with self.assertRaises(InspectionError):request_json(frame,DEFAULTS,'p',SCHEMA,validate_mark,'watermark')
                self.assertEqual(op.call_count,2)
    def test_clear_zero_confidence_not_passed(self):
        self.assertEqual(classify([dict(status='clear',confidence=0,topic_score=.9)],DEFAULTS)[0],'uncertain')
