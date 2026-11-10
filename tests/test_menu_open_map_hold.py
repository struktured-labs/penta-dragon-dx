"""#81 menu-open-map-hold stage (Select during the post-room-change publish window)."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import build_menu_open_map_hold as hold  # noqa: E402

CANDIDATE = '952f9b9f2b3feafb1882282e8ac7e5d0f462a597b79da49e74587469d8f6888a'
ORIGINAL_PATH = ROOT / 'rom/Penta Dragon (J).gb'
CANDIDATE_PATH = ROOT / 'tmp/roms-trial/JP-maphold.gbc'
PARENT_PATH = ROOT / 'tmp/roms-main/JP.gbc'


class Shape(unittest.TestCase):
    def test_site_and_payload(self):
        self.assertEqual(hold.SITE, 0x14 * 0x4000 + (0x7F32 - 0x4000))
        self.assertEqual(hold.PRE, bytes.fromhex('C9FFFFFF'))
        self.assertEqual(hold.NEW, bytes.fromhex('AFE0C4C9'))
        self.assertEqual(hold.PARENT, '91d58599d3df5dde80131ce20d0a639d7056d015dc91cedd2e699b66a141ba18')
        self.assertEqual(hold.CANDIDATE, CANDIDATE)


@unittest.skipUnless(PARENT_PATH.exists(), 'parent ROM not present')
class ExactCandidate(unittest.TestCase):
    def test_round_trip_and_scope(self):
        parent = PARENT_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(parent).hexdigest(), hold.PARENT)
        rom = hold.build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(), CANDIDATE)
        self.assertEqual(hold.reconstruct_parent(rom), parent)
        self.assertEqual(hold.verify_installed(rom), [])
        if CANDIDATE_PATH.exists():
            self.assertEqual(CANDIDATE_PATH.read_bytes(), rom)
        diff = {i for i in range(len(parent)) if parent[i] != rom[i]}
        allowed = set()
        for lo, hi in hold.changed_spans():
            allowed |= set(range(lo, hi))
        self.assertTrue(diff <= allowed, [hex(i) for i in sorted(diff - allowed)[:16]])
        self.assertEqual(rom[hold.SITE:hold.SITE + 4], hold.NEW)

    def test_rejects_wrong_parent(self):
        bad = bytearray(PARENT_PATH.read_bytes())
        bad[hold.SITE] ^= 1
        with self.assertRaises(Exception):
            hold.build(bytes(bad))


if __name__ == '__main__':
    unittest.main()
