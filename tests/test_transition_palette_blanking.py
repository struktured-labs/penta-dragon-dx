"""#55/#83 transition palette blanking (stage transition-palette-blanking)."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import build_transition_palette_blanking as blanking  # noqa: E402

CANDIDATE = '91d58599d3df5dde80131ce20d0a639d7056d015dc91cedd2e699b66a141ba18'
ORIGINAL_PATH = ROOT / 'rom/Penta Dragon (J).gb'
CANDIDATE_PATH = ROOT / 'tmp/tpb-ime2/candidate.gb'


class Shape(unittest.TestCase):
    def test_trampoline_and_sites(self):
        # LDH A,[FF99]; PUSH AF; LD A,$30; CALL 0061; CALL 4000; POP AF; JP 0061
        self.assertEqual(blanking.trampoline(), bytes.fromhex('F099F53E30CD6100CD0040F1C36100'))
        self.assertEqual(blanking.TRAMP, 0x00F0)
        self.assertLessEqual(blanking.TRAMP + len(blanking.trampoline()), 0x0100)
        self.assertEqual((blanking.FADE_SITE, blanking.SECRET_SITE, blanking.CARD_SITE),
                         (0x0F8B, 0x1494, 0x159F))
        self.assertEqual(blanking.BANK, 0x30)


@unittest.skipUnless(ORIGINAL_PATH.exists() and CANDIDATE_PATH.exists(), 'ROMs not present')
class ExactCandidate(unittest.TestCase):
    def setUp(self):
        self.original = ORIGINAL_PATH.read_bytes()
        self.rom = CANDIDATE_PATH.read_bytes()

    def test_round_trip_and_scope(self):
        self.assertEqual(hashlib.sha256(self.rom).hexdigest(), CANDIDATE)
        parent = blanking.reconstruct_parent(self.rom, self.original)
        self.assertEqual(hashlib.sha256(parent).hexdigest(), blanking.PARENT)
        self.assertEqual(blanking.build(parent, self.original), self.rom)
        self.assertEqual(blanking.verify_installed(self.rom, self.original), [])
        diff = {i for i in range(len(parent)) if parent[i] != self.rom[i]}
        allowed = {0x14D, 0x14E, 0x14F}
        for lo, hi in blanking.changed_spans(self.original):
            allowed |= set(range(lo, hi))
        self.assertTrue(diff <= allowed, [hex(i) for i in diff - allowed])
        self.assertEqual(self.rom[0x0F8B:0x0F8E], bytes.fromhex('CDF000'))
        self.assertEqual(self.rom[blanking.WAIT_SITE:blanking.WAIT_SITE + 6], bytes.fromhex('F044FE903004'))
        self.assertEqual(self.rom[0x1494:0x149E], bytes.fromhex('CDF0003E01CD9C1618CE'))
        self.assertEqual(self.rom[0x159F:0x15A2], bytes.fromhex('CDF000'))

    def test_rejects_wrong_parent(self):
        bad = bytearray(blanking.reconstruct_parent(self.rom, self.original))
        bad[0x1494] ^= 1
        with self.assertRaises(Exception):
            blanking.build(bytes(bad), self.original)


if __name__ == '__main__':
    unittest.main()
