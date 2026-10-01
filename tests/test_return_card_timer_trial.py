"""Issue #45: bounded timer-origin experiment, not release qualification."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
from build_return_card_timer_trial import build, NEW


class CardTimerTrial(unittest.TestCase):
    def test_only_first_timer_origin_moves(self):
        path = ROOT / 'tmp/return-cgb-fade-trial-10/candidate.gb'
        if not path.exists():
            self.skipTest('pinned parent unavailable')
        parent = path.read_bytes()
        result = build(parent)
        self.assertEqual(hashlib.sha256(result).hexdigest(),
                         '1ae1456b4aed771d0e54aec35daec7281dc6e5898a1a7b0fdeb2136a3c4f39d2')
        self.assertEqual(result[0x516ae:0x516b9], NEW)
        self.assertTrue(all(0x516b3 <= i < 0x516b9 or i in (0x14e, 0x14f)
                            for i, (a, b) in enumerate(zip(parent, result)) if a != b))
        with self.assertRaises(ValueError):
            build(result)


if __name__ == '__main__':
    unittest.main()
