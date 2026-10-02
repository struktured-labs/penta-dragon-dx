"""#43 boundary acceptance must reject the retained real startup failure."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'epoch', ROOT / 'scripts/diagnostics/verify_native_capture_epoch.py')
epoch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(epoch)
HEADER = 'event\temulator_frame\tvideo_frames\tpcm_samples\tsuccess\n'


class CaptureEpoch(unittest.TestCase):
    def check_text(self, text):
        with patch.object(Path, 'is_file', return_value=True), \
             patch.object(Path, 'read_bytes', return_value=(HEADER + text).encode()):
            return epoch.verify(ROOT / 'tmp/unused-epoch-unit-fixture')

    def test_valid(self):
        self.assertEqual(self.check_text('load_begin\t0\t0\t0\t-1\n'
                                        'load_end\t3553\t0\t0\t1\n')['status'], 'PASS')

    def test_rejects_bad_boundaries(self):
        for text in ('', 'load_begin\t0\t0\t0\t-1\n',
                     'load_begin\t0\t0\t32\t-1\nload_end\t3553\t0\t32\t1\n',
                     'load_begin\t0\t0\t0\t-1\nload_end\t3553\t1\t0\t1\n',
                     'load_begin\t0\t0\t0\t-1\nload_end\t3553\t0\t0\t0\n'):
            with self.subTest(text=text):
                self.assertEqual(self.check_text(text)['status'], 'FAIL')

    def test_missing(self):
        with patch.object(Path, 'is_file', return_value=False):
            self.assertEqual(epoch.verify(ROOT / 'tmp/unused')['status'], 'FAIL')

    def test_retained_real_controls(self):
        for name, expected in [('secret-stock-startup-short-01', 'PASS'),
                               ('secret-stock-startup-delay-01', 'FAIL')]:
            directory = Path('/mnt/data/tmp') / f'penta-{name}-av'
            if not directory.exists():
                self.skipTest('retained capture unavailable')
            with self.subTest(name=name):
                self.assertEqual(epoch.verify(directory)['status'], expected)


if __name__ == '__main__':
    unittest.main()
