"""#73 menu-frame-reinstall stage (reinstall 00:212E chrome before 1F60)."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import build_menu_frame_reinstall as frame  # noqa: E402

CANDIDATE = "01f8e0b22719a438c9c28f16c09c5bde8ae06f3f8561ffe0c88c08ba02b39d20"
PARENT_CANDIDATES = (
    ROOT / "tmp/death-fade-white-en/JP.gb",
    ROOT / "tmp/death-fade-white-trial11/candidate.gb",
    ROOT / "tmp/roms-main/JP.gbc",
)


def _parent_path():
    for path in PARENT_CANDIDATES:
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == frame.PARENT:
            return path
    return None


class Shape(unittest.TestCase):
    def test_sites_and_payload(self):
        self.assertEqual(frame.ENTRY, 0x1F60)
        self.assertEqual(frame.BODY_CPU, 0x5CE2)
        self.assertEqual(frame.TRAMPOLINE_LEN, 15)
        self.assertEqual(len(frame.trampoline()), 15)
        self.assertEqual(frame.BODY_LEN, 186)
        self.assertEqual(frame.PARENT, "23aa5f44f604d120877169f7dfa32186c3b089afbbadae4618b5cd06e7cb7d6c")
        self.assertEqual(frame.CANDIDATE, CANDIDATE)
        self.assertEqual(frame.F0_PRE, bytes.fromhex("F099F53E30CD6100CD0040F1C36100"))


class ExactCandidate(unittest.TestCase):
    def setUp(self):
        self.parent_path = _parent_path()
        if self.parent_path is None:
            self.skipTest("death-fade-white parent ROM not present")

    def test_round_trip_and_scope(self):
        parent = self.parent_path.read_bytes()
        rom = frame.build(parent)
        self.assertEqual(hashlib.sha256(rom).hexdigest(), CANDIDATE)
        self.assertEqual(frame.reconstruct_parent(rom), parent)
        self.assertEqual(frame.verify_installed(rom), [])
        diff = {i for i in range(len(parent)) if parent[i] != rom[i]}
        allowed = set()
        for lo, hi in frame.changed_spans():
            allowed |= set(range(lo, hi))
        self.assertTrue(diff <= allowed, [hex(i) for i in sorted(diff - allowed)[:16]])
        # Attract / earlier fixes stay byte-identical.
        self.assertEqual(rom[0x00F0:0x00FF], parent[0x00F0:0x00FF])
        self.assertEqual(rom[frame.HOOK81:frame.HOOK81 + 4], parent[frame.HOOK81:frame.HOOK81 + 4])
        self.assertEqual(rom[0x758E:0x7596], parent[0x758E:0x7596])
        isr = 0x0D * 0x4000 + (0x7459 - 0x4000)
        self.assertEqual(rom[isr:isr + 8], parent[isr:isr + 8])
        self.assertEqual(rom[0x0F33:0x0F36], parent[0x0F33:0x0F36])

    def test_rejects_wrong_parent(self):
        bad = bytearray(self.parent_path.read_bytes())
        bad[frame.ENTRY] ^= 1
        with self.assertRaises(Exception):
            frame.build(bytes(bad))


if __name__ == "__main__":
    unittest.main()
