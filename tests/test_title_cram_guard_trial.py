"""#35: a safe-access result must not hide the trial's title/start regression."""
import csv
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from build_title_cram_guard_trial import build, PARENT, OFFSET, OLD, NEW
from check_cram_timing import check

TRIAL = 'd8fe220ef8dbf5a435ef41f5226d6f0346f63f8449ac54a02500b434fc77a831'


class TitleCramGuardTests(unittest.TestCase):
    def test_reject_unknown_parent(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            build(bytes(1024))

    def test_exact_patch_scope(self):
        path = ROOT / 'tmp/handheld-palette-trial-01/candidate.gb'
        if not path.exists():
            self.skipTest('experimental parent unavailable')
        parent = path.read_bytes()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), PARENT)
        trial = build(parent)
        self.assertEqual(hashlib.sha256(trial).hexdigest(), TRIAL)
        self.assertEqual(parent[OFFSET:OFFSET + len(OLD)], OLD)
        self.assertEqual(trial[OFFSET:OFFSET + len(NEW)], NEW)
        allowed = {0x14e, 0x14f} | set(range(OFFSET, OFFSET + len(NEW)))
        self.assertEqual(len(trial), len(parent))
        self.assertFalse([i for i, (a, b) in enumerate(zip(parent, trial))
                          if a != b and i not in allowed])

    def test_retained_trial_is_not_behaviorally_qualified(self):
        runs = [ROOT / 'tmp/title-cram-control-cold-01',
                ROOT / 'tmp/title-cram-guard-cold-01']
        if not all((p / 'frame-0600.ss0').exists() for p in runs):
            self.skipTest('retained cold-boot evidence unavailable')
        entries = []
        for path, sha, writes, blocked in zip(runs, (PARENT, TRIAL),
                                             (3248, 2992), (333, 0)):
            with self.subTest(run=path.name):
                self.assertEqual(hashlib.sha256((path / 'candidate.gb').read_bytes()).hexdigest(), sha)
                with (path / 'cram-timing.tsv').open() as stream:
                    result = check(csv.DictReader(stream, delimiter='\t'))
                self.assertEqual(result['writes'], writes)
                self.assertEqual(len(result['blocked_writes']), blocked)
                self.assertEqual(result['status'], 'FAIL' if blocked else 'PASS_OBSERVED_WRITES')
                with (path / 'trace.tsv').open() as stream:
                    rows = list(csv.DictReader(stream, delimiter='\t'))
                self.assertEqual(len(rows), 600)
                entries.append(next(int(row['frame']) for row in rows if row['scene'] == '02'))
        # This is retained rejection evidence, not permission to accept the delay.
        self.assertEqual(entries, [499, 596])
        self.assertEqual(entries[1] - entries[0], 97)
        self.assertEqual((runs[0] / 'inputs.tsv').read_bytes(),
                         (runs[1] / 'inputs.tsv').read_bytes())
