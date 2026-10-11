"""#54 native stage-record restoration: placement, inversion and gate controls."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/diagnostics'))
import build_native_stage_records as records  # noqa: E402
import verify_native_stage_records as gate  # noqa: E402
import verify_live_regression as live  # noqa: E402

STOCK = ROOT / 'rom/Penta Dragon (J).gb'
TRANSFERS = (0xC3, 0xC2, 0xCA, 0xD2, 0xDA, 0xCD, 0xC4, 0xCC, 0xD4, 0xDC)


@unittest.skipUnless(STOCK.is_file(), 'original cartridge not present')
class NativeStageRecords(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = STOCK.read_bytes()
        parent = bytearray(cls.original) + bytearray([0xFF]) * (0x100000 - len(cls.original))
        start = records.NATIVE_START
        parent[start:records.NATIVE_END] = records.expected_parent_native_region(cls.original)
        for offset, payload in records.interim_bank63(cls.original):
            parent[offset:offset + len(payload)] = payload
        parent[records.TED_JUMP:records.TED_JUMP + 3] = records.jp(records.TED_TAIL_OLD)
        parent[records.DEATH_JUMP:records.DEATH_JUMP + 3] = records.jp(records.DEATH_RETURN_OLD)
        parent[0x14E:0x150] = ((sum(parent[:0x14E]) + sum(parent[0x150:])) & 0xFFFF).to_bytes(2, 'big')
        cls.parent = bytes(parent)

    def build(self, parent=None):
        parent = self.parent if parent is None else bytes(parent)
        with patch.object(records, 'PARENT', records.sha(parent)):
            return records.build(parent, self.original)

    def test_records_and_loader_are_exact_cartridge_bytes(self):
        result = self.build()
        self.assertEqual(result[records.NATIVE_START:records.NATIVE_END],
                         self.original[records.NATIVE_START:records.NATIVE_END])
        for record in (7, 8):
            start = records.TABLE + record * records.RECORD
            self.assertEqual(result[start + 19:start + 28], bytes(9))  # FFAE-FFB6
        self.assertEqual(records.verify_installed(result, self.original), [])
        self.assertEqual(gate.static_failures(result, self.original), [])

    def test_helpers_move_byte_for_byte_with_same_jump_width(self):
        result = self.build()
        self.assertEqual(result[0x00D0:0x00D9], self.parent[0x7C91:0x7C9A])
        self.assertEqual(result[0x00D9:0x00E2], self.parent[0x7CAE:0x7CB7])
        self.assertEqual(result[0x6FEC:0x6FEF], bytes.fromhex('C3D000'))
        self.assertEqual(result[0x0035:0x0038], bytes.fromhex('C3D900'))
        self.assertEqual(result[0x00CF], self.original[0x00CF])
        self.assertEqual(result[0x00E2:0x0100], self.original[0x00E2:0x0100])

    def test_retired_bank63_mirror_is_erased(self):
        result = self.build()
        for offset, payload in records.interim_bank63(self.original):
            self.assertEqual(result[offset:offset + len(payload)], b'\xff' * len(payload))

    def test_changed_spans_are_complete_and_inverse_is_exact(self):
        result = self.build()
        changed = {i for i, (a, b) in enumerate(zip(self.parent, result)) if a != b} - {0x14E, 0x14F}
        allowed = set()
        for start, end in records.changed_spans(self.original):
            allowed.update(range(start, end))
        self.assertTrue(changed <= allowed)
        with patch.object(records, 'PARENT', records.sha(self.parent)):
            self.assertEqual(records.reconstruct_parent(result, self.original), self.parent)

    def test_fill_is_not_a_stock_control_transfer_target(self):
        # No stock bank-0/1 JP/CALL/JR names $00CF-$00FF; the live gate and
        # the attract/patrol watch cover computed or banked entries.
        rom = self.original
        for i in range(0x8000 - 2):
            if rom[i] in TRANSFERS:
                target = rom[i + 1] | rom[i + 2] << 8
                self.assertFalse(records.FILL_START <= target < records.FILL_END, hex(i))
        for i in range(0x0000, 0x0200):
            if rom[i] in (0x18, 0x20, 0x28, 0x30, 0x38):
                target = i + 2 + ((rom[i + 1] ^ 0x80) - 0x80)
                self.assertFalse(records.FILL_START <= target < records.FILL_END, hex(i))
        self.assertEqual(rom[0x00CE], 0xC9)  # RET ends the last stock routine

    def test_rejects_changed_preimages(self):
        for offset in (0x7BB3, 0x7C91, 0x6FED, 0x0036, 0x00E0, records.interim_bank63(self.original)[0][0]):
            data = bytearray(self.parent)
            data[offset] ^= 1
            with self.assertRaises(ValueError):
                self.build(data)
        with self.assertRaisesRegex(ValueError, 'exact title-glyph-retry parent'):
            records.build(self.parent, self.original)

    def test_gate_negative_control_replays_played_defect_only(self):
        result = self.build()
        control = gate.corrupt_control(result)
        changed = {i for i, (a, b) in enumerate(zip(result, control)) if a != b} - {0x14E, 0x14F}
        expected = {address + i
                    for address, payload in ((0x7C91, records.TED_TAIL), (0x7CAE, records.DEATH_RETURN))
                    for i in range(9) if payload[i] != result[address + i]}
        self.assertEqual(changed, expected)
        self.assertTrue(gate.static_failures(control, self.original))

    def test_gate_live_check_rejects_hram_and_timing_drift(self):
        record7 = self.original[0x7C7E:0x7C9B].hex()
        base = dict(header=record7, cycles='3304', **dict.fromkeys(gate.REGISTERS, '1'))
        self.assertEqual(gate.live_failures(base, base, 7, self.original), [])
        bad = dict(base, header=record7[:38] + '3e10210040e5c36100' + record7[56:])
        self.assertTrue(any('FFAE-FFB6' in f for f in gate.live_failures(bad, base, 7, self.original)))
        slow = dict(base, cycles='4104')
        self.assertTrue(any('cycles' in f for f in gate.live_failures(slow, base, 7, self.original)))


class GateRegistration(unittest.TestCase):
    def test_pre_stream_profile_includes_native_stage_records(self):
        self.assertIn('native_stage_records', live.LIVE_GATES)


if __name__ == '__main__':
    unittest.main()
