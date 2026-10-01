import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from build_boss_shadow_atomic import build, NEW, OLD


class BossShadowAtomicTests(unittest.TestCase):
    def test_unknown_parent_rejected(self):
        with self.assertRaises(ValueError):
            build(bytes(1024))

    def test_exact_patch_and_bounded_delta(self):
        p = ROOT/'tmp/sara-atomic-pose-source-16/candidate.gb'
        if not p.exists():
            self.skipTest('local parent unavailable')
        parent = p.read_bytes()
        candidate = build(parent)
        self.assertEqual(hashlib.sha256(candidate).hexdigest(),
                         '19d042860a71813acbfeab049d9e7c59a94d4ed0c3296aa17872618374dcb5d0')
        self.assertEqual(len(OLD), len(NEW))
        self.assertIn(bytes.fromhex('014000F3CDB309FBC9'), NEW)
        self.assertTrue(all(i in (0x14e,0x14f) or 0x2bc5<=i<0x2bc5+len(OLD)
                            for i,(a,b) in enumerate(zip(parent,candidate)) if a!=b))
