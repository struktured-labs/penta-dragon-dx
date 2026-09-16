#!/usr/bin/env python3
"""Static identity, ownership, and destination gates for r308."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_completed_map_wall_r308 as r308  # noqa: E402


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class CompletedMapWallR308Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r308.BASE.read_bytes()
        cls.base_receipt = r308.BASE_RECEIPT.read_bytes()
        cls.candidate = r308.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r308.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_candidate_receipt_and_rebuild_are_exact(self) -> None:
        self.assertEqual(digest(self.base), r308.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r308.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), r308.EXPECTED_CANDIDATE_SHA256)
        rebuilt, receipt = r308.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(r308.r305.r304.receipt_bytes(receipt), self.receipt_bytes)
        self.assertEqual(self.receipt["candidate_sha256"], digest(self.candidate))
        self.assertEqual(self.receipt["status"], "LIVE_REJECTED")
        self.assertFalse(self.receipt["promotable"])
        self.assertFalse(self.receipt["emulator_invoked"])

    def test_functional_delta_is_exactly_owned_and_bank14_is_untouched(self) -> None:
        functional = r308.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        expected = {
            offset for offset in r308.owned_ranges()
            if self.base[offset] != self.candidate[offset]
        }
        self.assertEqual(functional, expected)
        changed = r308.r305.r304.delta(self.base, self.candidate)
        self.assertLessEqual(changed, r308.owned_ranges() | r308.CHECKSUM_OFFSETS)
        bank14 = slice(14 * r308.BANK_SIZE, 15 * r308.BANK_SIZE)
        self.assertEqual(self.candidate[bank14], self.base[bank14])
        self.assertEqual(self.receipt["ownership"]["escaped_bytes"], 0)

    def test_bank31_ranges_were_erased_and_hold_only_reviewed_payloads(self) -> None:
        for address, payload in (
            (r308.REPAIR_ADDR, r308.REPAIR),
            (r308.ROW_WRITER_ADDR, r308.ROW_WRITER),
            (r308.PAIR_WRITER_ADDR, r308.PAIR_WRITER),
        ):
            offset = r308.bank_offset(r308.AUX_BANK, address)
            self.assertEqual(self.base[offset:offset + len(payload)],
                             bytes([0xFF]) * len(payload))
            self.assertEqual(self.candidate[offset:offset + len(payload)],
                             payload)
        entry = r308.bank_offset(r308.AUX_BANK, r308.AUX_ENTRY_ADDR)
        self.assertEqual(self.base[entry:entry + 8], bytes([0xFF]) * 8)
        self.assertEqual(self.candidate[entry:entry + 3], r308.AUX_ENTRY)
        self.assertEqual(self.candidate[entry + 3:entry + 8], r308.AUX_RETURN)

        mux = r308.bank_offset(r308.r305.BANK31, r308.r305.MUX_ADDR)
        self.assertEqual(
            self.candidate[mux:mux + len(r308.r305.MUX)], r308.r305.MUX
        )
        self.assertLess(r308.r305.MUX_ADDR + len(r308.r305.MUX),
                        r308.REPAIR_ADDR)

    def test_cross_bank_bridge_maps_31_and_restores_bank19(self) -> None:
        live = r308.bank_offset(r308.LIVE_BANK, r308.DISPATCH_ADDR)
        self.assertEqual(
            self.base[live:live + r308.LIVE_DISPATCH_SIZE],
            r308.OLD_LIVE_DISPATCH,
        )
        self.assertEqual(
            self.candidate[live:live + r308.LIVE_DISPATCH_SIZE],
            r308.LIVE_STUB,
        )
        self.assertEqual(r308.LIVE_STUB[:5], bytes.fromhex("3E 1F CD 61 00"))
        self.assertEqual(
            r308.LIVE_STUB[r308.LIVE_RETURN_ADDR-r308.DISPATCH_ADDR], 0xC9
        )
        self.assertEqual(r308.AUX_ENTRY,
                         bytes.fromhex("C3 00 6D"))
        self.assertEqual(r308.AUX_RETURN,
                         bytes.fromhex("3E 13 CD 61 00"))

    def test_relocated_algorithm_changes_only_absolute_helper_operands(self) -> None:
        original = r308.r294.build_repair()
        relocated = r308.REPAIR
        self.assertEqual(len(original), len(relocated), 99)
        changed = {
            index for index, (old, new) in enumerate(zip(original, relocated))
            if old != new
        }
        # Nine CALL sites change both operand bytes:
        # $6CAA->$6D90 and $6C8F->$6D70.
        self.assertEqual(len(changed), 18)
        self.assertTrue(all(original[index] in (0xAA, 0x8F, 0x6C)
                            and relocated[index] in (0x90, 0x70, 0x6D)
                            for index in changed))
        self.assertEqual(
            bytes(value for index, value in enumerate(original)
                  if index not in changed),
            bytes(value for index, value in enumerate(relocated)
                  if index not in changed),
        )
        self.assertEqual(digest(relocated),
                         r308.EXPECTED_COMPONENT_SHA256["repair"])

    def test_room01_exact_positions_map_packed24_to_physical32(self) -> None:
        offsets = r308.room01_offsets()
        self.assertEqual(len(offsets), len(set(offsets)), 35)
        expected = {
            row * 32 + column for row, column in r308.r294.ROOM01_TARGET_CELLS
        }
        self.assertEqual(set(offsets), expected)
        packed = r308.r294.ROOM01_CAPTURE.read_bytes()
        self.assertEqual(len(packed), 24 * 24)
        packed_positions = {
            row * 24 + column for row, column in r308.r294.ROOM01_TARGET_CELLS
        }
        self.assertEqual(
            {packed[index] for index in packed_positions},
            {0x24, 0x27, 0x30, 0x33},
        )

    def test_only_exact_D_map_is_written_for_both_physical_destinations(self) -> None:
        offsets = set(r308.room01_offsets())
        for destination_h, other_h in ((0x98, 0x9C), (0x9C, 0x98)):
            writes = set(r308.writes_for(1, destination_h))
            self.assertEqual(
                writes,
                {(destination_h << 8) + offset for offset in offsets},
            )
            self.assertEqual(len(writes), 35)
            self.assertTrue(
                all(not (other_h << 8) <= address < (other_h << 8) + 0x400
                    for address in writes)
            )
        self.assertEqual(r308.writes_for(5, 0x98), ())
        self.assertEqual(r308.writes_for(5, 0x9C), ())

    def test_room_gates_and_room12_semantics_are_preserved(self) -> None:
        self.assertEqual(r308.REPAIR[:4], bytes.fromhex("F0 BD FE 01"))
        self.assertIn(bytes.fromhex("FE 12 28"), r308.REPAIR[:12])
        # All four original room12 writer sites remain, with the final tail
        # converted from JP to CALL solely so bank 19 can be restored.
        self.assertEqual(r308.REPAIR.count(bytes.fromhex("CD 70 6D")), 4)
        original_body = r308.OLD_LIVE_DISPATCH[5:-3]
        normalized = r308.REPAIR.replace(
            bytes.fromhex("CD 70 6D"), bytes.fromhex("CD 8F 6C")
        )
        self.assertIn(original_body, normalized)
        self.assertEqual(self.receipt["offline_contract"]["abi"]
                         ["room05_writes"], 0)

    def test_rejected_r306_and_bank16_hardening_are_excluded(self) -> None:
        for address in r308.r305.r303.r300.TRAMPOLINE_ADDRS:
            offset = r308.bank_offset(
                r308.r305.r303.r300.SEMANTIC_BANK, address
            )
            self.assertEqual(
                self.candidate[offset:offset + 9],
                r308.r305.r303.r300.CONTEXT_TRAMPOLINE,
            )
        bank16 = slice(16 * r308.BANK_SIZE, 17 * r308.BANK_SIZE)
        self.assertEqual(self.candidate[bank16], self.base[bank16])
        self.assertEqual(
            self.receipt["causal_rejections"]["r306"]["mismatch_frames"],
            56,
        )

    def test_timing_scope_is_transition_only(self) -> None:
        timing = self.receipt["offline_contract"]["timing"]
        self.assertEqual(timing["ordinary_frame_delta_t_cycles"], 0)
        self.assertEqual(timing["renderer_delta_t_cycles"], 0)
        self.assertEqual(timing["room01_hblank_intervals"], 18)
        self.assertEqual(timing["room01_unique_writes"], 35)
        self.assertEqual(timing["room05_dispatch_overhead_t_cycles"], 268)


if __name__ == "__main__":
    unittest.main()
