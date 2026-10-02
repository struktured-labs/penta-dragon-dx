#!/usr/bin/env python3
"""Focused static gates for the FFE5-at-precompile r310 candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_precompile_effective_room_r310 as r310  # noqa: E402


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class PrecompileEffectiveRoomR310Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r310.BASE.read_bytes()
        cls.base_receipt = r310.BASE_RECEIPT.read_bytes()
        cls.candidate = r310.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r310.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_identity_and_rebuild(self) -> None:
        self.assertEqual(digest(self.base), r310.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r310.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), r310.EXPECTED_CANDIDATE_SHA256)
        rebuilt, receipt = r310.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(r310.r305.r304.receipt_bytes(receipt), self.receipt_bytes)
        self.assertFalse(self.receipt["promotable"])
        self.assertFalse(self.receipt["emulator_invoked"])

    def test_exact_base_ownership(self) -> None:
        functional = r310.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        expected = {
            offset for offset in r310.owned_ranges()
            if self.base[offset] != self.candidate[offset]
        }
        self.assertEqual(functional, expected)
        self.assertEqual(len(functional), 68)
        changed = r310.r305.r304.delta(self.base, self.candidate)
        self.assertLessEqual(changed, r310.owned_ranges() | r310.CHECKSUM_OFFSETS)

    def test_only_one_functional_byte_differs_from_r309(self) -> None:
        r309_candidate = r310.r309.DEFAULT_OUTPUT.read_bytes()
        differences = r310.r305.r304.delta(
            r309_candidate, self.candidate, functional=True
        )
        helper = r310.bank_offset(r310.HELPER_BANK, r310.HELPER_ADDR)
        self.assertEqual(differences, {helper + r310.ROOM_OPERAND_OFFSET})
        offset = next(iter(differences))
        self.assertEqual(r309_candidate[offset], 0xBD)
        self.assertEqual(self.candidate[offset], 0xE5)

    def test_helper_changes_only_ffbd_to_ffe5_operand(self) -> None:
        differences = {
            index for index, pair in enumerate(
                zip(r310.OLD_HELPER, r310.NEW_HELPER)
            ) if pair[0] != pair[1]
        }
        self.assertEqual(differences, {r310.ROOM_OPERAND_OFFSET})
        self.assertEqual(
            r310.OLD_HELPER[r310.ROOM_OPERAND_OFFSET-1:
                            r310.ROOM_OPERAND_OFFSET+1],
            bytes.fromhex("F0 BD"),
        )
        self.assertEqual(
            r310.NEW_HELPER[r310.ROOM_OPERAND_OFFSET-1:
                            r310.ROOM_OPERAND_OFFSET+1],
            bytes.fromhex("F0 E5"),
        )
        self.assertEqual(digest(r310.NEW_HELPER), r310.NEW_HELPER_SHA256)

    def test_native_effective_room_setter_and_resolver_are_exhaustive(self) -> None:
        start = r310.EFFECTIVE_ROOM_SETTER_ADDR
        end = start + len(r310.EFFECTIVE_ROOM_SETTER)
        self.assertEqual(self.candidate[start:end], r310.EFFECTIVE_ROOM_SETTER)
        cases = 0
        for table_value in range(256):
            for ffbd in range(256):
                self.assertEqual(
                    r310.effective_room(table_value, ffbd),
                    table_value if table_value else ffbd,
                )
                cases += 1
        self.assertEqual(cases, 65536)

    def test_precommit_entry_exit_and_settled_truth_rows(self) -> None:
        initial = {tile: 0x80 + index
                   for index, tile in enumerate(r310.TARGET_TILES)}
        rows = (
            (1, 0x12, 0x02, 0x06),
            (1, 0x12, 0x0B, 0x06),
            (5, 1, 0x02, 0x00),
            (0, 1, 0x0B, 0x06),
            (0, 5, 0x0B, 0x00),
        )
        for table_value, ffbd, scene, expected in rows:
            ffe5 = r310.effective_room(table_value, ffbd)
            self.assertEqual(
                r310.apply_model(initial, ffb7=2, scene=scene, ffe5=ffe5),
                {tile: expected for tile in r310.TARGET_TILES},
            )
        self.assertEqual(
            r310.apply_model(initial, ffb7=2, scene=0x18, ffe5=1), initial
        )
        self.assertEqual(
            r310.apply_model(initial, ffb7=3, scene=0x03, ffe5=1), initial
        )

    def test_reachable_stage_predicate_remains_exhaustive(self) -> None:
        cases = 0
        accepted: set[int] = set()
        for ffb7 in range(256):
            for dd06 in range(4):
                for ffbf in range(4):
                    scene = r310.r296.reachable_scene(
                        ffb7, dd06=dd06, ffbf=ffbf
                    )
                    value = r310.r296.predicate_accepts(scene, ffb7)
                    self.assertEqual(value, ffb7 == 2)
                    if value:
                        accepted.add(scene)
                    cases += 1
        self.assertEqual(cases, 4096)
        self.assertEqual(accepted, {0x02, 0x0A, 0x0B})

    def test_stack_migration_and_timing_are_identical_to_r309(self) -> None:
        # Everything after the room-load operand is byte-identical; stack,
        # SVBK, mapper, and continuation behavior therefore remain exact.
        self.assertEqual(
            r310.NEW_HELPER[r310.ROOM_OPERAND_OFFSET+1:],
            r310.OLD_HELPER[r310.ROOM_OPERAND_OFFSET+1:],
        )
        timing = self.receipt["offline_contract"]["timing"]
        self.assertTrue(timing["exactly_equal_to_r309_all_paths"])
        self.assertEqual(timing["ordinary_frame_delta_t_cycles"], 0)
        self.assertEqual(timing["renderer_delta_t_cycles"], 0)
        self.assertEqual(timing["dirty_compile_delta_t_cycles"], {
            "nonstage_ffb7_reject": 432,
            "nonstage_scene_fold_reject": 472,
            "stage1_room01": 572,
            "stage1_other_room": 568,
        })

    def test_excluded_banks_and_r305_room_hook_are_exact(self) -> None:
        for bank in (14, 16, 31):
            page = slice(bank * r310.BANK_SIZE, (bank + 1) * r310.BANK_SIZE)
            self.assertEqual(self.candidate[page], self.base[page])
        wall21 = r310.bank_offset(r310.r305.WALL_BANK, r310.r305.WALL_ADDR)
        self.assertEqual(
            self.candidate[wall21:wall21 + len(r310.r305.NEW_WALL_HELPER)],
            r310.r305.NEW_WALL_HELPER,
        )


if __name__ == "__main__":
    unittest.main()
