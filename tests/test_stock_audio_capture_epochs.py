"""#43 retain both failed neutrality and successful lifecycle diagnostics."""
import json
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class StockAudioEpochs(unittest.TestCase):
    def receipt(self, name):
        path = ROOT / 'tmp' / name / 'receipt.json'
        if not path.exists():
            self.skipTest('local native capture unavailable')
        return json.loads(path.read_text())

    def test_original_neutrality_failure_is_retained(self):
        a = self.receipt('secret-stock-copy-cadence-01')['native_capture']
        b = self.receipt('secret-stock-copy-unobserved-01')['native_capture']
        self.assertEqual(a['metadata']['samples'] - b['metadata']['samples'], 32)
        self.assertNotEqual(a['hashes']['native.s16le'], b['hashes']['native.s16le'])
        for key in ('native.video', 'native.states'):
            self.assertEqual(a['hashes'][key], b['hashes'][key])

    def test_new_lifecycle_diagnostics_match_without_trimming(self):
        names = ['secret-stock-copy-lifecycle-on-01',
                 'secret-stock-copy-lifecycle-off-01',
                 'secret-stock-copy-lifecycle-repeat-01']
        receipts = [self.receipt(name) for name in names]
        for receipt in receipts:
            self.assertEqual(receipt['native_capture']['hashes'],
                             receipts[0]['native_capture']['hashes'])
            path = Path(receipt['native_capture_directory']) / 'native.lifecycle.tsv'
            self.assertEqual(path.read_text().splitlines()[1:],
                             ['load_begin\t0\t0\t0\t-1',
                              'load_end\t3553\t0\t0\t1'])

    def test_startup_delay_exposes_pre_restore_audio(self):
        receipt = self.receipt('secret-stock-startup-delay-01')
        path = Path(receipt['native_capture_directory']) / 'native.lifecycle.tsv'
        rows = [line.split('\t') for line in path.read_text().splitlines()[1:]]
        self.assertEqual([row[0] for row in rows], ['load_begin', 'load_end'])
        self.assertGreater(int(rows[0][3]), 0)
        self.assertEqual(rows[0][3], rows[1][3])
        self.assertEqual(rows[1][4], '1')

    def test_startup_barrier_preserves_full_capture(self):
        names = ['secret-stock-copy-lifecycle-off-01',
                 'secret-stock-startup-gated-on-01',
                 'secret-stock-startup-gated-off-01']
        receipts = [self.receipt(name) for name in names]
        for receipt in receipts:
            capture = receipt['native_capture']
            for filename, expected in capture['hashes'].items():
                with (Path(receipt['native_capture_directory']) / filename).open('rb') as stream:
                    actual = hashlib.file_digest(stream, 'sha256').hexdigest()
                self.assertEqual(actual, expected)
                self.assertEqual(actual, receipts[0]['native_capture']['hashes'][filename])
        for receipt in receipts[1:]:
            self.assertEqual(receipt['native_capture']['restored_replay_epoch']['status'], 'PASS')
            self.assertEqual(receipt['diagnostic_environment']['ENTRY_NATIVE_START_DELAY_US'], '10000')

    def test_same_tap_without_barrier_still_detects_failure(self):
        good = self.receipt('secret-stock-startup-gated-on-01')
        bad = self.receipt('secret-stock-startup-ungated-negative-02')
        self.assertEqual(good['native_tap_sha256'], bad['native_tap_sha256'])
        self.assertEqual(good['probe_sha256'], bad['probe_sha256'])
        self.assertEqual(bad['native_capture']['restored_replay_epoch']['status'], 'FAIL')
        self.assertEqual(bad['native_capture']['restored_replay_epoch']['events'][0]['pcm_samples'], 512)


if __name__ == '__main__':
    unittest.main()
