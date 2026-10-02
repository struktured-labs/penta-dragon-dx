"""Structural guards for the rejected native-publisher #23 experiment."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_secret_native_pipeline_trial as trial


class NativePipelineTrialTests(unittest.TestCase):
    def test_reject_unbound_parent(self):
        with self.assertRaisesRegex(ValueError, 'exact source07'):
            trial.build(bytes(0x100000))

    def test_helper_uses_existing_atomic_setup_without_scratch_switch(self):
        h = trial.helper()
        self.assertEqual(h[:4], bytes.fromhex('f3cd13da'))
        self.assertNotIn(bytes.fromhex('e070'), h)
        self.assertLess(0x6c80 + len(h), 0x7f00)

    def test_exact_experiment_and_unchanged_native_copy_body(self):
        path = ROOT / 'tmp/stream-regressions-source-07/candidate.gb'
        if not path.exists():
            self.skipTest('local exact parent unavailable')
        parent = path.read_bytes()
        rom = trial.build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(),
                         'f1b981ed779f61fa95911f9124e7ce8747988592e49b32b97baa28c7c6f815e6')
        self.assertEqual(rom[trial.HOOK+5:29*0x4000], parent[trial.HOOK+5:29*0x4000])
        self.assertEqual(rom[0x42ed:0x435a], parent[0x42ed:0x435a])


if __name__ == '__main__':
    unittest.main()
