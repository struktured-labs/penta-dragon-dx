import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from build_boss_vblank_guard import build, body, OLD, START, END


class BossVblankGuardTests(unittest.TestCase):
    def test_unknown_parent_rejected(self):
        with self.assertRaises(ValueError):
            build(bytes(1024))

    def test_emitter_calls_and_timer_enable_preserved(self):
        code = body()
        self.assertEqual(len(code), END-START)
        self.assertEqual(code[:7], bytes.fromhex('F0FFF5E6FEE0FF'))
        self.assertIn(OLD[0x2ba3-START:0x2bc5-START], code)
        self.assertEqual(code.count(bytes.fromhex('CDBA10')), 4)
        self.assertIn(bytes.fromhex('F1E0FF3E10B7C9'), code)
        for ie in range(256):
            self.assertEqual((ie & 0xfe) & 6, ie & 6)

    def test_exact_bounded_patch(self):
        path = ROOT/'tmp/sara-atomic-pose-source-16/candidate.gb'
        if not path.exists():
            self.skipTest('retained parent unavailable')
        parent = path.read_bytes()
        candidate = build(parent)
        self.assertEqual(candidate[START:END], body())
        self.assertEqual(len(candidate), len(parent))
        self.assertTrue(all(i in (0x14e, 0x14f) or START <= i < END
                            for i, (a,b) in enumerate(zip(parent,candidate)) if a != b))
