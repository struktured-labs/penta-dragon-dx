import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts/diagnostics'))
import verify_stage1_no_bleed as gate


class ToothBankOracle(unittest.TestCase):
    def test_only_reviewed_bank_bits_change(self):
        rom = (ROOT/'tmp/stage2-seven-rows-r441/candidate.gb').read_bytes()
        expected = gate.expected_stage1_table(rom)
        self.assertEqual(expected, rom[gate.DUNGEON_TABLE_OFFSET:gate.DUNGEON_TABLE_OFFSET+256])
        teeth = set(range(0x64,0x6A)) | set(range(0x74,0x7A))
        self.assertEqual({i for i in range(256) if expected[i]!=gate.EXPECTED_TABLE[i]}, teeth)
        for i in teeth:
            self.assertEqual(expected[i],15)
        for tile in (0,0x64,0x6B,0x88,0xFF):
            bad = bytearray(rom);bad[gate.DUNGEON_TABLE_OFFSET+tile] ^= 1
            self.assertNotEqual(gate.expected_stage1_table(bad),
                                bad[gate.DUNGEON_TABLE_OFFSET:gate.DUNGEON_TABLE_OFFSET+256])
        self.assertEqual(gate.expected_stage1_table(b'unknown'), gate.EXPECTED_TABLE)
