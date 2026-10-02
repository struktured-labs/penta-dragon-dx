#!/usr/bin/env python3
"""Static identity, ABI, semantic, and timing gates for r309."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_precompile_wall_r309 as r309  # noqa: E402


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class PrecompileWallR309Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r309.BASE.read_bytes()
        cls.base_receipt = r309.BASE_RECEIPT.read_bytes()
        cls.candidate = r309.DEFAULT_OUTPUT.read_bytes()
        cls.receipt_bytes = r309.DEFAULT_RECEIPT.read_bytes()
        cls.receipt = json.loads(cls.receipt_bytes)

    def test_pinned_candidate_receipt_and_rebuild_are_exact(self) -> None:
        self.assertEqual(digest(self.base), r309.BASE_SHA256)
        self.assertEqual(digest(self.base_receipt), r309.BASE_RECEIPT_SHA256)
        self.assertEqual(digest(self.candidate), r309.EXPECTED_CANDIDATE_SHA256)
        rebuilt, receipt = r309.build(self.base, self.base_receipt)
        self.assertEqual(rebuilt, self.candidate)
        self.assertEqual(r309.r305.r304.receipt_bytes(receipt), self.receipt_bytes)
        self.assertEqual(self.receipt["candidate_sha256"], digest(self.candidate))
        self.assertFalse(self.receipt["promotable"])
        self.assertFalse(self.receipt["emulator_invoked"])

    def test_exact_functional_ownership(self) -> None:
        functional = r309.r305.r304.delta(
            self.base, self.candidate, functional=True
        )
        expected = {
            offset for offset in r309.owned_ranges()
            if self.base[offset] != self.candidate[offset]
        }
        self.assertEqual(functional, expected)
        self.assertEqual(len(functional), 68)
        changed = r309.r305.r304.delta(self.base, self.candidate)
        self.assertLessEqual(changed, r309.owned_ranges() | r309.CHECKSUM_OFFSETS)
        self.assertEqual(self.receipt["ownership"]["escaped_bytes"], 0)

    def test_precompile_route_is_width_exact_and_unique(self) -> None:
        start = r309.PRECOMPILE_SITE
        end = start + len(r309.OLD_PRECOMPILE)
        self.assertEqual(self.base[start:end], r309.OLD_PRECOMPILE)
        self.assertEqual(self.candidate[start:end], r309.NEW_PRECOMPILE)
        self.assertEqual(len(r309.OLD_PRECOMPILE), len(r309.NEW_PRECOMPILE), 6)
        self.assertEqual(r309.NEW_PRECOMPILE,
                         bytes.fromhex("3E 1E CD 47 08 00"))
        self.assertEqual(self.candidate.count(bytes.fromhex("3E 1E CD 47 08")), 1)
        self.assertEqual(self.candidate.count(bytes.fromhex("3E 1E CD 61 00")), 0)
        self.assertEqual(self.candidate.count(bytes.fromhex("3E 1E C3 61 00")), 0)

    def test_bank30_is_wholly_erased_before_exact_helper_install(self) -> None:
        bank_start = r309.HELPER_BANK * r309.BANK_SIZE
        bank_end = bank_start + r309.BANK_SIZE
        self.assertEqual(self.base[bank_start:bank_end],
                         bytes([0xFF]) * r309.BANK_SIZE)
        helper = r309.bank_offset(r309.HELPER_BANK, r309.HELPER_ADDR)
        self.assertEqual(self.candidate[helper:helper + len(r309.HELPER)],
                         r309.HELPER)
        self.assertEqual(len(r309.HELPER), 63)
        self.assertEqual(digest(r309.HELPER), r309.HELPER_SHA256)
        candidate_bank = self.candidate[bank_start:bank_end]
        self.assertEqual(
            {index for index, value in enumerate(candidate_bank)
             if value != 0xFF},
            {r309.HELPER_ADDR - 0x4000 + index
             for index, value in enumerate(r309.HELPER) if value != 0xFF},
        )

    def test_reachable_scene_predicate_is_exhaustive(self) -> None:
        accepted_scenes: set[int] = set()
        cases = 0
        for ffb7 in range(256):
            for dd06 in range(4):
                for ffbf in range(4):
                    scene = r309.r296.reachable_scene(
                        ffb7, dd06=dd06, ffbf=ffbf
                    )
                    accepted = r309.r296.predicate_accepts(scene, ffb7)
                    self.assertEqual(accepted, ffb7 == 2)
                    if accepted:
                        accepted_scenes.add(scene)
                    cases += 1
        self.assertEqual(cases, 4096)
        self.assertEqual(accepted_scenes, {0x02, 0x0A, 0x0B})
        self.assertFalse(r309.r296.predicate_accepts(0x18, 0x02))
        self.assertFalse(r309.r296.predicate_accepts(0x03, 0x03))

    def test_room01_and_room05_full_byte_truth_rows(self) -> None:
        initial = {tile: 0x80 + index
                   for index, tile in enumerate(r309.TARGET_TILES)}
        for scene in (0x02, 0x0A, 0x0B):
            self.assertEqual(
                r309.apply_model(initial, ffb7=2, scene=scene, room=1),
                {tile: 0x06 for tile in r309.TARGET_TILES},
            )
            self.assertEqual(
                r309.apply_model(initial, ffb7=2, scene=scene, room=5),
                {tile: 0x00 for tile in r309.TARGET_TILES},
            )
        self.assertEqual(
            r309.apply_model(initial, ffb7=2, scene=0x18, room=1), initial
        )
        self.assertEqual(
            r309.apply_model(initial, ffb7=3, scene=0x03, room=1), initial
        )

    def test_room01_capture_owns_exactly_35_target_cells(self) -> None:
        packed = r309.r296.ROOM01_CAPTURE.read_bytes()
        expected = {
            row * 24 + column
            for row, column in r309.r296.ROOM01_TARGET_CELLS
        }
        actual = {
            index for index, tile in enumerate(packed)
            if tile in r309.TARGET_TILES
        }
        self.assertEqual(len(expected), 35)
        self.assertEqual(actual, expected)
        table = r309.bank_offset(13, 0x7000)
        self.assertTrue(all(self.candidate[table + tile] == 0
                            for tile in r309.TARGET_TILES))

    def test_stack_and_svbk_migration_preserves_both_return_frames(self) -> None:
        # r296 pops [084D,430E] from SVBK1, changes SVBK, then pushes in
        # reverse order. Deeper caller frames and SP are unchanged.
        deeper = [0xBEEF, 0xCAFE]
        bank1_stack = [0x084D, 0x430E, *deeper]
        bc = bank1_stack.pop(0)
        de = bank1_stack.pop(0)
        bank3_stack = list(bank1_stack)
        bank3_stack.insert(0, de)
        bank3_stack.insert(0, bc)
        self.assertEqual(bank3_stack, [0x084D, 0x430E, *deeper])
        self.assertEqual(bc, 0x084D)
        self.assertEqual(de, 0x430E)
        self.assertTrue(r309.HELPER.endswith(bytes.fromhex(
            "3E 01 EA 09 DC C1 D1 3E 03 E0 70 D5 C5 11 A0 C1 "
            "06 C6 F0 E0 4F 3E 01 C9"
        )))

    def test_timing_arithmetic_is_exact(self) -> None:
        timing = self.receipt["offline_contract"]["timing"]
        self.assertEqual(timing["ordinary_frame_delta_t_cycles"], 0)
        self.assertEqual(timing["renderer_delta_t_cycles"], 0)
        self.assertEqual(timing["original_setup_t_cycles"], 28)
        self.assertEqual(timing["new_shell_excluding_helper_t_cycles"], 252)
        for path, helper_cycles in timing["helper_t_cycles"].items():
            self.assertEqual(
                timing["delta_t_cycles"][path], helper_cycles + 252 - 28
            )

    def test_r305_owners_are_exact_and_diagnostics_are_excluded(self) -> None:
        wall21 = r309.bank_offset(r309.r305.WALL_BANK, r309.r305.WALL_ADDR)
        self.assertEqual(
            self.candidate[wall21:wall21 + len(r309.r305.NEW_WALL_HELPER)],
            r309.r305.NEW_WALL_HELPER,
        )
        mux31 = r309.bank_offset(r309.r305.BANK31, r309.r305.MUX_ADDR)
        self.assertEqual(
            self.candidate[mux31:mux31 + len(r309.r305.MUX)], r309.r305.MUX
        )
        for bank in (14, 16, 31):
            page = slice(bank * r309.BANK_SIZE, (bank + 1) * r309.BANK_SIZE)
            self.assertEqual(self.candidate[page], self.base[page])
        self.assertEqual(
            self.receipt["causal_rejections"]["r308"]["mismatch_frames"],
            160,
        )


if __name__ == "__main__":
    unittest.main()
