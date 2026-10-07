"""#67: reject incomplete, shifted, or visual-only audit evidence."""
import copy
import json
from pathlib import Path
import unittest
import sys
import tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))

from build_visual_audit import exact_low_health_pair, observed_low_health_images

ROOT = Path(__file__).resolve().parents[1]


class ExactPairReceipt(unittest.TestCase):
    def setUp(self):
        self.sha = 'a' * 64
        replay = dict(passed=True, rom_sha256=self.sha, native_capture={
            'status': 'COMPLETE_CAPTURE_FILES',
            'restored_replay_epoch': {'status': 'PASS'},
            'hashes': {'native.' + suffix: 'b' * 64
                       for suffix in ('s16le', 'video', 'states', 'timeline.tsv')}})
        self.receipt = dict(schema='penta-low-health-hazard-determinism-v2',
            passed=True, rom_sha256=self.sha, samples=240, statuses=[0, 0],
            replays=[copy.deepcopy(replay), copy.deepcopy(replay)],
            exact_comparison=dict(passed=True, row_counts=[241, 241],
                compared_frames=241, row_mismatch_samples=[],
                image_mismatch_samples=[], extra_images=[[], []]),
            checks={key: True for key in (
                'both low-health hazard replays pass',
                'full unshifted state trace and rendered corpus are byte-exact',
                'complete native audio video state and input timeline are byte-exact')})

    def test_current_complete_pair(self):
        self.assertTrue(exact_low_health_pair(self.receipt, self.sha))

    def test_every_claim_is_required(self):
        for key in self.receipt['checks']:
            mutant = copy.deepcopy(self.receipt)
            mutant['checks'].pop(key)
            self.assertFalse(exact_low_health_pair(mutant, self.sha), key)

    def test_native_mismatch_cannot_hide_behind_outer_pass(self):
        for suffix in ('s16le', 'video', 'states', 'timeline.tsv'):
            mutant = copy.deepcopy(self.receipt)
            mutant['replays'][1]['native_capture']['hashes']['native.' + suffix] = '0' * 64
            self.assertFalse(exact_low_health_pair(mutant, self.sha), suffix)

    def test_pre_restore_output_rejected(self):
        self.receipt['replays'][0]['native_capture']['restored_replay_epoch']['status'] = 'FAIL'
        self.assertFalse(exact_low_health_pair(self.receipt, self.sha))

    def test_incomplete_or_shifted_corpus_rejected(self):
        for field, value in [('row_counts', [240, 239]), ('compared_frames', 239),
                             ('row_mismatch_samples', [1]), ('image_mismatch_samples', [1]),
                             ('extra_images', [['extra'], []])]:
            mutant = copy.deepcopy(self.receipt)
            mutant['exact_comparison'][field] = value
            self.assertFalse(exact_low_health_pair(mutant, self.sha), field)

    def test_legacy_schema_rejected(self):
        self.receipt['schema'] = 'penta-low-health-hazard-determinism-v1'
        self.assertFalse(exact_low_health_pair(self.receipt, self.sha))

    def test_different_candidate_rejected(self):
        self.assertFalse(exact_low_health_pair(self.receipt, '0' * 64))

    def test_gallery_does_not_label_recovery_as_warning(self):
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as folder:
            root = Path(folder)
            (root / 'low-health.frames.tsv').write_text(
                'sample\thealth_phase\tdd06\n1\tpre\t01\n2\tlow\t00\n'
                '3\tlow\t01\n4\trecovery\t01\n')
            for sample in range(1, 5):
                # Selection tests only check existence, not PNG decoding.
                (root / f'low-health.frame{sample:04d}.png').touch()
            self.assertEqual([i for i, _ in observed_low_health_images(root)], [3])
            (root / 'low-health.frame0002.png').unlink()
            with self.assertRaisesRegex(RuntimeError, 'missing'):
                observed_low_health_images(root)

    def test_retained_native_evidence_when_available(self):
        path = ROOT / 'tmp/lowhealth-default-native-01/receipt.json'
        if not path.is_file():
            self.skipTest('optional retained native capture absent')
        receipt = json.loads(path.read_text())
        self.assertTrue(exact_low_health_pair(receipt, receipt['rom_sha256']))


if __name__ == '__main__':
    unittest.main()
