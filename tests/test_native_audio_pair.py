import sys
from pathlib import Path
import unittest
import csv
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from verify_native_audio_pair import compare, load


class NativeAudioPairTests(unittest.TestCase):
    def test_retained_title_guard_sample_count_mismatch_is_not_trimmed(self):
        paths = [Path('/mnt/data/tmp') / f'penta-title-audio-{name}-20260928-01/native.wav'
                 for name in ('control', 'local')]
        if not all(path.is_file() for path in paths):
            self.skipTest('retained title PCM unavailable')
        rate, a = load(paths[0])
        other_rate, b = load(paths[1])
        self.assertEqual((rate, other_rate), (131072, 131072))
        self.assertEqual((len(a), len(b)), (1323232, 1322400))
        with self.assertRaisesRegex(ValueError, 'different native sample counts; do not trim'):
            compare(a, b, rate)

    def test_retained_crystal_first_return_changes_timing_not_write_sequence(self):
        root = Path(__file__).resolve().parents[1]
        paths = [root / f'tmp/crystal-menu-apu-trace-{trial}/apu.tsv'
                 for trial in ('08', '10')]
        if not all(path.is_file() for path in paths):
            self.skipTest('retained local APU traces unavailable')
        rows = []
        for path in paths:
            with path.open() as stream:
                rows.append(list(csv.DictReader(stream, delimiter='\t')))
        a, b = rows
        self.assertEqual(len(a), 298)
        self.assertEqual([(r['address'], r['value']) for r in a],
                         [(r['address'], r['value']) for r in b])
        delta = [int(y['cycle'])-int(x['cycle']) for x, y in zip(a, b)]
        # Describes retained evidence, not an acoustic acceptance threshold.
        self.assertEqual((min(delta), max(delta)), (-48, 16))
        self.assertTrue(any(delta))

    def test_retained_crystal_menu_trial_does_not_qualify_audio(self):
        parent = Path('/mnt/data/tmp/penta-crystal-menu-native-08b/native.wav')
        candidate = Path('/mnt/data/tmp/penta-crystal-menu-native-10b/native.wav')
        if not parent.is_file() or not candidate.is_file():
            self.skipTest('retained local native PCM unavailable')
        rate, a = load(parent)
        other_rate, b = load(candidate)
        self.assertEqual(rate, other_rate)
        result, _ = compare(a, b, rate)
        self.assertEqual(result['status'], 'fail')
        self.assertTrue(result['checks']['reference_has_activity'])
        self.assertTrue(result['checks']['level_within_two_percent'])
        self.assertFalse(result['checks']['no_larger_sample_discontinuity'])
        self.assertEqual(result['first_different_sample'], 546877)

    def setUp(self):
        self.rate = 8000
        wave = np.where(np.arange(self.rate * 2) % 80 < 40, 3000, -3000)
        self.parent = np.column_stack((wave, wave)).astype(np.int32)

    def test_identity_passes(self):
        result, diff = compare(self.parent, self.parent.copy(), self.rate)
        self.assertEqual(result['status'], 'pass')
        self.assertFalse(np.any(diff))

    def test_silence_fails(self):
        result, _ = compare(self.parent, np.zeros_like(self.parent), self.rate)
        self.assertEqual(result['status'], 'fail')

    def test_added_twenty_ms_gap_fails(self):
        altered = self.parent.copy()
        altered[8000:8160] = 0
        result, _ = compare(self.parent, altered, self.rate)
        self.assertFalse(result['checks']['same_digital_silence_intervals'])

    def test_pop_fails(self):
        altered = self.parent.copy()
        altered[8100] = 30000
        result, _ = compare(self.parent, altered, self.rate)
        self.assertFalse(result['checks']['no_larger_sample_discontinuity'])

    def test_clipping_fails(self):
        altered = self.parent.copy()
        altered[8100] = 32767
        result, _ = compare(self.parent, altered, self.rate)
        self.assertFalse(result['checks']['no_added_clipping'])

    def test_no_trimming(self):
        with self.assertRaisesRegex(ValueError, 'do not trim'):
            compare(self.parent, self.parent[:-1], self.rate)

    def test_no_normalization(self):
        result, _ = compare(self.parent, self.parent // 2, self.rate)
        self.assertFalse(result['checks']['level_within_two_percent'])

    def test_silent_reference_cannot_qualify(self):
        samples = np.zeros_like(self.parent)
        result, _ = compare(samples, samples, self.rate)
        self.assertEqual(result['status'], 'fail')


if __name__ == '__main__':
    unittest.main()
