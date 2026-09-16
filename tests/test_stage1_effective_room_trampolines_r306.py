#!/usr/bin/env python3
"""Static identity/semantic gates for the strict four-byte r306 overlay."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_effective_room_trampolines_r306 as r306  # noqa: E402


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class EffectiveRoomTrampolinesR306Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r306.BASE.read_bytes()
        cls.base_receipt = r306.BASE_RECEIPT.read_bytes()
        cls.candidate = r306.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r306.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_artifact_and_receipt_rebuild_exactly(self) -> None:
        self.assertEqual(digest(self.base), r306.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r306.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), r306.EXPECTED_CANDIDATE_SHA256)
        rebuilt, receipt = r306.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(r306.r305.r304.receipt_bytes(receipt), self.receipt_bytes)
        self.assertEqual(self.receipt["candidate_sha256"], digest(self.candidate))
        self.assertFalse(self.receipt["emulator_invoked"])
        self.assertFalse(self.receipt["promotable"])

    def test_exact_four_functional_bytes_and_checksums_only(self) -> None:
        functional = r306.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        self.assertEqual(functional, r306.owned_ranges())
        self.assertEqual(len(functional), 4)
        self.assertEqual(
            functional,
            {0x0521A1, 0x0527EE, 0x052B71, 0x052D9F},
        )
        changed = r306.r305.r304.delta(self.base, self.candidate)
        self.assertLessEqual(changed, functional | r306.CHECKSUM_OFFSETS)
        for offset in functional:
            self.assertEqual(self.base[offset], 0xBD)
            self.assertEqual(self.candidate[offset], 0xE5)

    def test_each_trampoline_changes_only_the_ldh_operand(self) -> None:
        for address in r306.TRAMPOLINE_ADDRS:
            offset = r306.bank_offset(r306.BANK, address)
            self.assertEqual(
                self.base[offset:offset + len(r306.OLD_TRAMPOLINE)],
                r306.OLD_TRAMPOLINE,
            )
            self.assertEqual(
                self.candidate[offset:offset + len(r306.NEW_TRAMPOLINE)],
                r306.NEW_TRAMPOLINE,
            )
            self.assertEqual(self.base[offset], self.candidate[offset])
            self.assertEqual(
                self.base[offset + 2:offset + len(r306.OLD_TRAMPOLINE)],
                self.candidate[offset + 2:offset + len(r306.NEW_TRAMPOLINE)],
            )

    def test_native_effective_room_setter_is_exact(self) -> None:
        start = r306.EFFECTIVE_ROOM_SETTER_ADDR
        end = start + len(r306.EFFECTIVE_ROOM_SETTER)
        self.assertEqual(self.base[start:end], r306.EFFECTIVE_ROOM_SETTER)
        self.assertEqual(self.candidate[start:end], r306.EFFECTIVE_ROOM_SETTER)
        self.assertEqual(
            r306.EFFECTIVE_ROOM_SETTER,
            bytes.fromhex("7E E0 CE A7 20 02 F0 BD E0 E5"),
        )

    def test_effective_room_and_dispatch_truth_table_is_exhaustive(self) -> None:
        cases = 0
        for table_value in range(256):
            for ffbd in range(256):
                expected = table_value if table_value else ffbd
                room = r306.effective_room(table_value, ffbd)
                self.assertEqual(room, expected)
                self.assertEqual(
                    r306.selected_helper(room),
                    r306.ROOM01_HELPER_ADDR
                    if expected == 1 else r306.PRIMARY_HELPER_ADDR,
                )
                cases += 1
        self.assertEqual(cases, 65536)

    def test_transition_entry_and_exit_controls(self) -> None:
        # Outgoing FFBD must not override a nonzero incoming native table A.
        self.assertEqual(r306.effective_room(1, 5), 1)
        self.assertEqual(
            r306.selected_helper(r306.effective_room(1, 5)), 0x4500
        )
        self.assertEqual(r306.effective_room(5, 1), 5)
        self.assertEqual(
            r306.selected_helper(r306.effective_room(5, 1)), 0x4300
        )
        # A zero native table entry falls back to the settled live room.
        self.assertEqual(r306.effective_room(0, 1), 1)
        self.assertEqual(r306.effective_room(0, 5), 5)

    def test_semantic_helpers_luts_and_bank16_are_causal_controls(self) -> None:
        # The strict diagnostic does not alter either semantic implementation,
        # either LUT, or the separately identified bank-16 installer problem.
        for address, width in (
            (r306.r300.PRIMARY_HELPER_ADDR,
             len(r306.r300.semantic.build_helper())),
            (r306.r300.ROOM01_HELPER_ADDR,
             len(r306.r300.build_room01_helper(
                 r306.r300.semantic.build_helper()))),
            (r306.r300.PRIMARY_LUT_ADDR, 0x100),
            (r306.r300.ROOM01_LUT_ADDR, 0x100),
        ):
            offset = r306.bank_offset(r306.BANK, address)
            self.assertEqual(
                self.candidate[offset:offset + width],
                self.base[offset:offset + width],
            )
        bank16 = slice(16 * 0x4000, 17 * 0x4000)
        self.assertEqual(self.candidate[bank16], self.base[bank16])
        self.assertIn(
            "deliberately excluded",
            self.receipt["excluded_followup"][
                "bank16_resident_installer_hardening"
            ],
        )

    def test_timing_and_abi_contract_is_zero_delta(self) -> None:
        timing = self.receipt["offline_contract"]["timing"]
        self.assertEqual(timing["all_paths_delta_t_cycles"], 0)
        self.assertEqual(timing["renderer_delta_t_cycles"], 0)
        self.assertEqual(timing["transition_delta_t_cycles"], 0)
        abi = self.receipt["offline_contract"]["abi"]
        self.assertTrue(abi["instruction_width_exact"])
        self.assertTrue(abi["flags_exact"])
        self.assertTrue(abi["BC_DE_HL_SP_exact"])


if __name__ == "__main__":
    unittest.main()
