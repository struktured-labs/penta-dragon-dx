"""Issue59: source construction is not release qualification."""
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_stream_regression_candidate as stream


class LaterLowHealthSource(unittest.TestCase):
    def test_unqualified_changes_remain_opt_in(self):
        parameters = inspect.signature(stream.build).parameters
        for name in ('later_lowhealth_timer', 'later_lowhealth_camera', 'title_glyph_read_window',
                     'title_glyph_retry_window'):
            self.assertIs(parameters[name].default, False)

    def test_default_source_control_remains_unchanged(self):
        root = ROOT / 'tmp/lowhealth-default-source-control-01'
        if not (root / 'build-receipt.json').is_file():
            self.skipTest('fresh default source control not available')
        receipt = json.loads((root / 'build-receipt.json').read_text())
        expected = '6c4a9654b5c6dad70c8ea21bfd39b6e53766a3cd1a642153c6085774392ec228'
        self.assertEqual(receipt['candidate_sha256'], expected)
        self.assertEqual(hashlib.sha256((root / 'candidate.gb').read_bytes()).hexdigest(), expected)
        nested = json.loads((root / 'stream-source/build-receipt.json').read_text())
        self.assertFalse(nested['experimental_later_lowhealth_timer'])
        self.assertFalse(nested['experimental_later_lowhealth_camera'])
        self.assertFalse(nested['retained_candidate_inputs'])
        self.assertFalse(any(stage['name'].startswith(('later-lowhealth-', 'stage7-lowhealth-'))
                             for stage in nested['stages']))

    def test_requires_exact_preceding_chain(self):
        with self.assertRaisesRegex(ValueError, 'exact boss-rearm chain'):
            stream.build(ROOT / 'tmp/unused-lowhealth-test', later_lowhealth_timer=True)
        with self.assertRaisesRegex(ValueError, 'exact Timer-yield chain'):
            stream.build(ROOT / 'tmp/unused-lowhealth-test', later_lowhealth_camera=True)
        with self.assertRaisesRegex(ValueError, 'exact low-health camera chain'):
            stream.build(ROOT / 'tmp/unused-lowhealth-test', title_glyph_read_window=True)
        with self.assertRaisesRegex(ValueError, 'exact low-health camera chain'):
            stream.build(ROOT / 'tmp/unused-lowhealth-test', title_glyph_retry_window=True)
        with self.assertRaisesRegex(ValueError, 'mutually exclusive'):
            stream.build(ROOT / 'tmp/unused-lowhealth-test', title_glyph_read_window=True,
                         title_glyph_retry_window=True)

    def test_fresh_source_reproduces_emulator_tested_trial(self):
        root = ROOT / 'tmp/later-lowhealth-title-retry-source-01'
        receipt = root / 'build-receipt.json'
        if not receipt.is_file():
            self.skipTest('fresh local source construction not available')
        data = json.loads(receipt.read_text())
        expected = '126861281b75edaf8daace834ccbe41e53ed0c9eebb71e50fe3bd6823e8b6941'
        self.assertEqual(hashlib.sha256((root / 'candidate.gb').read_bytes()).hexdigest(), expected)
        self.assertEqual(data['candidate_sha256'], expected)
        self.assertFalse(data['release_qualified'])
        self.assertFalse(data['retained_candidate_inputs'])
        self.assertTrue(data['experimental_later_lowhealth_timer'])
        self.assertTrue(data['experimental_later_lowhealth_camera'])
        self.assertFalse(data['experimental_title_glyph_read_window'])
        self.assertTrue(data['experimental_title_glyph_retry_window'])
        self.assertIn('remain unresolved', data['qualification_warning'])
        self.assertEqual(data['entrypoint_sha256'],
                         hashlib.sha256(Path(stream.__file__).read_bytes()).hexdigest())
        self.assertEqual([r['name'] for r in data['stages'][-5:]],
                         ['later-lowhealth-dispatch', 'later-lowhealth-timer-yield',
                          'stage7-lowhealth-fastpath', 'stage7-lowhealth-camera',
                          'title-glyph-retry-window'])
        for previous, following in zip(data['stages'][-6:], data['stages'][-5:]):
            self.assertEqual(previous['candidate_sha256'], following['parent_sha256'])
        for name in ('build_later_lowhealth_dispatch.py', 'build_later_compile_timer_yield.py',
                     'build_stage7_lowhealth_fastpath.py', 'build_stage7_lowhealth_camera.py',
                     'build_stage7_r274_low_nibble.py', 'build_title_glyph_retry_window.py'):
            key = 'scripts/diagnostics/' + name
            self.assertEqual(data['loaded_project_python_sources'][key],
                             hashlib.sha256((ROOT / key).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
