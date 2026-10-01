"""#27 scoped mapper dispatch contracts; emulator qualification is separate."""
import hashlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
from build_arena_alias_only_miss_trial import build, PARENT


class AliasOnlyMiss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT/'tmp/arena-completion-safe-trial-01/candidate.gb'
        if not path.exists():
            raise unittest.SkipTest('local exact parent unavailable')
        cls.parent = path.read_bytes()
        cls.rom = build(cls.parent)

    def test_layout_and_branch_destination(self):
        self.assertEqual(hashlib.sha256(self.parent).hexdigest(), PARENT)
        old = self.parent[0x36f90:0x37000]
        new = self.rom[0x36f90:0x37000]
        self.assertEqual(new[:8], old[:8])
        self.assertEqual(new[8:12], bytes.fromhex('FE0B2007'))
        self.assertEqual(new[12:], old[8:-4])
        # JR NZ skips exactly mapper dispatch/pop/early-return, to CALL7CFC.
        self.assertEqual(new[12+7:12+10], bytes.fromhex('CDFC7C'))
        self.assertEqual(new[22:25], bytes.fromhex('77FE02'))
        start = 20*0x4000 + 0x6f9e-0x4000
        self.assertEqual(self.rom[start:start+6], bytes.fromhex('CDBE09C3E06D'))
        ret = 20*0x4000+0x6dfc-0x4000
        self.assertEqual(self.rom[ret:ret+3], bytes.fromhex('C39E6F'))

    def test_all_raw_and_canonical_scenes_preserve_lookup_decision(self):
        # Old resolver changes identity ONLY for raw0B/canonical0C..14.
        # Check hits, misses, and resolved-identity hits; the byte layout test
        # binds the new branch predicate to CP0B / JR NZ.
        for raw in range(256):
            for canonical in range(256):
                effective = canonical if raw == 11 and 12 <= canonical <= 20 else raw
                for cached in {raw, effective, raw ^ 255}:
                    old = ('return', raw) if raw == cached else (
                        ('return', effective) if effective == cached else ('publish', effective))
                    new = ('return', raw) if raw == cached else (
                        ('return', effective) if raw == 11 and effective == cached
                        else ('publish', effective if raw == 11 else raw))
                    self.assertEqual(new, old, (raw, canonical, cached))

    def test_completion_and_other_runtime_sources_unchanged(self):
        for first,last in ((0x42f0,0x4360),(0x35600,0x35900),
                           (0x37c70,0x37ca0),(0x41500,0x41600),
                           (0x7f196,0x7f1ef)):
            self.assertEqual(self.rom[first:last], self.parent[first:last])

    def test_rejects_other_parent(self):
        changed = bytearray(self.parent)
        changed[0] ^= 1
        with self.assertRaises(ValueError):
            build(changed)


if __name__ == '__main__':
    unittest.main()
