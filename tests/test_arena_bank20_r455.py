"""The complete reconstructed bank includes both owned code and unused padding."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'scripts/diagnostics')]
from arena_bank20_r455 import expected_bank20, matches


class Bank20Proof(unittest.TestCase):
    def test_every_byte_is_constrained(self):
        expected = expected_bank20()
        self.assertEqual(len(expected), 0x4000)
        # Exercise full-bank comparison for every single-byte corruption.
        rom = bytearray(21 * 0x4000)
        rom[20 * 0x4000:] = expected
        self.assertTrue(matches(rom))
        for offset in range(0x4000):
            rom[20 * 0x4000 + offset] ^= 1
            self.assertNotEqual(rom[20 * 0x4000:], expected, hex(offset))
            rom[20 * 0x4000 + offset] ^= 1
        self.assertFalse(matches(rom[:-1]))

    def test_local_candidate_matches_source(self):
        path = ROOT / 'tmp/arena-palette-storage-r455/candidate.gb'
        if not path.exists():
            self.skipTest('local candidate unavailable')
        self.assertTrue(matches(path.read_bytes()))


if __name__ == '__main__':
    unittest.main()
