import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
from crystal_transition_contract import verify_transition, offset


class TransitionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / "tmp/arena-palette-storage-r455/candidate.gb"
        if not path.exists():
            raise unittest.SkipTest("local immutable candidate unavailable")
        cls.rom = path.read_bytes()

    def test_source_reconstruction_and_environment_preserved(self):
        before = dict(os.environ)
        self.assertEqual(verify_transition(self.rom), "title-port-r443e3")
        self.assertEqual(dict(os.environ), before)

    def test_every_owned_byte_mutation_rejected(self):
        for address, size in ((0x7CFC, 65), (0x76D7, 14), (0x6E9D, 9),
                              (0x7719, 7), (0x7703, 22), (0x7407, 8)):
            for index in range(size):
                with self.subTest(address=hex(address + index)):
                    mutant = bytearray(self.rom)
                    mutant[offset(address) + index] ^= 1
                    with self.assertRaises(AssertionError):
                        verify_transition(mutant)


if __name__ == "__main__":
    unittest.main()
