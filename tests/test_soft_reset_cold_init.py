"""Post-ending soft reset re-runs DX cold init (stage soft-reset-cold-init)."""
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
import build_soft_reset_cold_init as soft  # noqa: E402

CANDIDATE = '9642170ac94ebcf8b278eaffd6afea1d3545d851123b33233f08fa69a14fe095'
ORIGINAL_PATH = ROOT / 'rom/Penta Dragon (J).gb'
CANDIDATE_PATH = ROOT / 'tmp/ssc1/candidate.gb'


class StubShape(unittest.TestCase):
    def test_stub_is_single_pass_clear_then_boot(self):
        # DI; LD HL,DF00; LD B,F0; XOR A; loop: LD (HL+),A; DEC B; JR NZ,loop; JP 0150
        self.assertEqual(soft.STUB, bytes.fromhex('F3 2100DF 06F0 AF 22 05 20FC C35001'))
        self.assertEqual(soft.STUB_AT, 0x00E2)
        self.assertLessEqual(soft.STUB_AT + len(soft.STUB), 0x0100)
        self.assertEqual(soft.jp(soft.STUB_AT), bytes.fromhex('C3E200'))


@unittest.skipUnless(ORIGINAL_PATH.exists() and CANDIDATE_PATH.exists(), 'ROMs not present')
class ExactCandidate(unittest.TestCase):
    def setUp(self):
        self.original = ORIGINAL_PATH.read_bytes()
        self.rom = CANDIDATE_PATH.read_bytes()

    def test_round_trip_and_scope(self):
        self.assertEqual(hashlib.sha256(self.rom).hexdigest(), CANDIDATE)
        parent = soft.reconstruct_parent(self.rom, self.original)
        self.assertEqual(hashlib.sha256(parent).hexdigest(), soft.PARENT)
        self.assertEqual(soft.build(parent, self.original), self.rom)
        self.assertEqual(soft.verify_installed(self.rom, self.original), [])
        diff = [i for i in range(len(parent)) if parent[i] != self.rom[i]]
        allowed = {0x14D, 0x14E, 0x14F}
        for lo, hi in soft.changed_spans(self.original):
            allowed |= set(range(lo, hi))
        self.assertTrue(set(diff) <= allowed, [hex(i) for i in set(diff) - allowed])
        self.assertEqual(self.rom[0x5553:0x5559], bytes.fromhex('CD8F42C3E200'))

    def test_rejects_wrong_parent(self):
        bad = bytearray(soft.reconstruct_parent(self.rom, self.original))
        bad[0x5556] ^= 1
        with self.assertRaises(Exception):
            soft.build(bytes(bad), self.original)


if __name__ == '__main__':
    unittest.main()
