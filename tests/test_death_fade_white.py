"""#74 death-fade-white stage (CGB white when gameplay death fade hits BGP=00)."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import build_death_fade_white as fade  # noqa: E402

CANDIDATE = "23aa5f44f604d120877169f7dfa32186c3b089afbbadae4618b5cd06e7cb7d6c"
PARENT_CANDIDATES = (
    ROOT / "tmp/roms-main/JP.gbc",
    ROOT / "tmp/roms-official-1110b/Penta-Dragon-DX-menu-hold-JP.gbc",
    ROOT / "tmp/roms-trial/JP-maphold.gbc",
)


def _parent_path():
    for path in PARENT_CANDIDATES:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == fade.PARENT:
            return path
    return None


class Shape(unittest.TestCase):
    def test_sites_and_payload(self):
        self.assertEqual(fade.SITES, (0x4A5C,))
        self.assertEqual(fade.CALL_FADE, bytes.fromhex("CD330F"))
        self.assertEqual(fade.STUB, 0x758E)
        self.assertEqual(len(fade.STUB_NEW), 8)
        self.assertEqual(fade.PARENT, "952f9b9f2b3feafb1882282e8ac7e5d0f462a597b79da49e74587469d8f6888a")
        self.assertEqual(fade.CANDIDATE, CANDIDATE)


class ExactCandidate(unittest.TestCase):
    def setUp(self):
        self.parent_path = _parent_path()
        if self.parent_path is None:
            self.skipTest("menu-open-map-hold parent ROM not present")

    def test_round_trip_and_scope(self):
        parent = self.parent_path.read_bytes()
        rom = fade.build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(), CANDIDATE)
        self.assertEqual(fade.reconstruct_parent(rom), parent)
        self.assertEqual(fade.verify_installed(rom), [])
        diff = {i for i in range(len(parent)) if parent[i] != rom[i]}
        allowed = set()
        for lo, hi in fade.changed_spans():
            allowed |= set(range(lo, hi))
        self.assertTrue(diff <= allowed, [hex(i) for i in sorted(diff - allowed)[:16]])
        for site in fade.SITES:
            self.assertEqual(rom[site:site + 3], bytes([0xCD, fade.STUB & 0xFF, fade.STUB >> 8]))

    def test_rejects_wrong_parent(self):
        bad = bytearray(self.parent_path.read_bytes())
        bad[fade.SITE_DEATH] ^= 1
        with self.assertRaises(Exception):
            fade.build(bytes(bad))


if __name__ == "__main__":
    unittest.main()
