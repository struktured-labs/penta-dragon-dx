"""#59/#66 narrow static checks, not emulator/rendering qualification."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/diagnostics'))
from build_stage7_lowhealth_fastpath import RESOLVER, CACHE_RESOLVER, build


class Stage7LowHealthFastpath(unittest.TestCase):
    def test_only_raw_alias_may_consult_canonical_scene(self):
        # Decode the actual fixed instruction sequence. The caller's CP08
        # replaces the resolver's flags, and no other register is modified.
        self.assertEqual(RESOLVER, bytes.fromhex('FA80D8 FE0B C0 F0B7 C9'))
        for raw in range(256):
            for canonical in range(256):
                result = raw if raw != RESOLVER[4] else canonical
                self.assertEqual(result == 8, raw == 8 or (raw == 11 and canonical == 8))

    def test_non_alias_does_not_admit_stale_canonical_stage7(self):
        for raw in (0, 1, 2, 3, 9, 12, 20, 255):
            result = raw if raw != RESOLVER[4] else 8
            self.assertNotEqual(result, 8)

    def test_unknown_parent_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'exact'):
            build(bytes(1048576))

    def test_cache_lookup_changes_only_stage7_lowhealth_alias(self):
        self.assertEqual(CACHE_RESOLVER,
                         bytes.fromhex('FA80D8 FE0B C0 F0B7 FE08 C8 3E0B C9'))
        for raw in range(256):
            for canonical in range(256):
                result = raw
                if raw == CACHE_RESOLVER[4]:
                    result = canonical if canonical == CACHE_RESOLVER[9] else CACHE_RESOLVER[12]
                self.assertEqual(result, 8 if (raw, canonical) == (11, 8) else raw)


if __name__ == '__main__':
    unittest.main()
