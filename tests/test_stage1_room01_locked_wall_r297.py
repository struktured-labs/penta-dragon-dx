#!/usr/bin/env python3
"""Independent static controls for the minimal r297 Stage-1 repair."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_room01_locked_wall_r297 as r297  # noqa: E402


EXPECTED_SHA256 = (
    "4a7c3f6bae9e79e767326fcdf07a18fb0707783e2023db8b5f2c9fa3f5b14e1c"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Room01LockedWallR297Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r297.BASE.read_bytes()
        cls.base_receipt = r297.BASE_RECEIPT.read_bytes()
        cls.candidate, cls.receipt = r297.build(cls.base, cls.base_receipt)

    def test_candidate_identity_checksums_and_isolation(self) -> None:
        self.assertEqual(sha256(self.candidate), EXPECTED_SHA256)
        self.assertEqual(self.candidate, r297.DEFAULT_OUTPUT.read_bytes())
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertFalse(self.receipt["promotable"])
        self.assertEqual(
            self.candidate[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE],
            self.base[14 * r297.BANK_SIZE:15 * r297.BANK_SIZE],
        )
        header = 0
        for value in self.candidate[0x0134:0x014D]:
            header = (header - value - 1) & 0xFF
        self.assertEqual(self.candidate[0x014D], header)
        total = (
            sum(self.candidate[:0x014E]) + sum(self.candidate[0x0150:])
        ) & 0xFFFF
        self.assertEqual(
            int.from_bytes(self.candidate[0x014E:0x0150], "big"), total
        )

    def test_room_hook_stack_and_mapper_abi_is_exact(self) -> None:
        self.assertEqual(
            self.candidate[0:8],
            bytes.fromhex("E0 BD F5 F0 99 C3 38 08"),
        )
        self.assertEqual(
            self.candidate[0x0838:0x0842],
            bytes.fromhex("F5 3E 15 C3 47 08 F1 F1 C9 00"),
        )
        self.assertEqual(
            self.candidate[0x0847:0x0850], r297.MAPPER_DISPATCH
        )
        helper = r297.bank_offset(r297.EXPANSION_BANK, r297.WALL_HELPER_ADDR)
        self.assertEqual(
            self.candidate[helper:helper + len(r297.WALL_HELPER)],
            r297.WALL_HELPER,
        )
        self.assertEqual(len(r297.WALL_HELPER), 52)
        # The helper's only explicit register save is HL; BC/DE are never
        # addressed.  SP+7 fetches room A, SP+2 rewrites $084D->$083E, and
        # SP+5 fetches the arbitrary original ROM bank before POP HL/tail-map.
        self.assertIn(bytes.fromhex("F8 07 7E 3D"), r297.WALL_HELPER)
        self.assertIn(bytes.fromhex("F8 02 36 3E 23 36 08"), r297.WALL_HELPER)
        self.assertTrue(r297.WALL_HELPER.endswith(
            bytes.fromhex("F8 05 7E E1 C3 61 00")
        ))
        for offset in r297.ROOM_HOOK_SITES:
            self.assertEqual(self.candidate[offset:offset + 2], b"\xC7\x00")

    def test_wall_context_is_stage_and_room_scoped(self) -> None:
        initial = {
            tile: 0x80 + index
            for index, tile in enumerate(r297.TARGET_TILES)
        }
        self.assertEqual(
            r297.wall_values(initial, stage=0, room=1),
            {tile: 0x06 for tile in r297.TARGET_TILES},
        )
        self.assertEqual(
            r297.wall_values(initial, stage=0, room=5),
            {tile: 0x00 for tile in r297.TARGET_TILES},
        )
        self.assertEqual(r297.wall_values(initial, stage=1, room=1), initial)
        lut = r297.bank_offset(13, 0x7000)
        self.assertEqual(
            self.candidate[lut:lut + 0x100], self.base[lut:lut + 0x100]
        )

    def test_reachable_attr_slow_path_adds_only_locked_stage1(self) -> None:
        added = set()
        for ffb7 in range(256):
            for dd06 in range(4):
                for ffbf in range(4):
                    scene = r297.reachable_scene(ffb7, dd06=dd06, ffbf=ffbf)
                    old = r297.old_attr_accepts(scene)
                    new = r297.r297_attr_accepts(scene, ffb7)
                    if new and not old:
                        added.add((ffb7, scene))
        self.assertEqual(added, {(0x02, 0x0B)})
        self.assertFalse(r297.r297_attr_accepts(0x18, 0x02))
        self.assertFalse(r297.r297_attr_accepts(0x03, 0x03))

    def test_normal_attr_gateway_is_cycle_and_state_exact(self) -> None:
        for bank, helper in r297.ATTR_HELPER_BY_BANK.items():
            offset = r297.bank_offset(bank, r297.ATTR_GATEWAY_ADDR)
            self.assertEqual(
                self.candidate[offset:offset + 10],
                bytes.fromhex("FA 80 D8 E6 F7 FE 02")
                + bytes((0xC4, helper & 0xFF, helper >> 8)),
            )
        self.assertEqual(
            self.receipt["offline_contract"]["scene"]
            ["normal_02_0A_gateway_t_cycles"],
            {"r292": 44, "r297": 44},
        )

    def test_row_and_transition_are_one_byte_mask_changes(self) -> None:
        row = r297.bank_offset(r297.ROW_BANK, 0x6BA7)
        end = r297.bank_offset(r297.ROW_BANK, 0x6BEB)
        changed = {
            index
            for index, (old, new) in enumerate(
                zip(self.base[row:end], self.candidate[row:end], strict=True)
            )
            if old != new
        }
        self.assertEqual(changed, {r297.ROW_MASK_ADDR - 0x6BA7})
        self.assertEqual(self.candidate[row], 0xC1)  # POP BC
        self.assertEqual(self.candidate[row + 4], 0x47)  # LD B,A
        bit = r297.bank_offset(r297.ROW_BANK, 0x6BBA)
        self.assertEqual(
            self.candidate[bit:bit + 4], bytes.fromhex("CB 58 20 0C")
        )
        transition = r297.bank_offset(r297.ROW_BANK, r297.TRANSITION_MASK_ADDR)
        self.assertEqual(self.base[transition], 0xF7)
        self.assertEqual(self.candidate[transition], 0xF6)

    def test_failed_r296_hot_path_is_absent(self) -> None:
        self.assertEqual(
            self.candidate[0x4303:0x4319], self.base[0x4303:0x4319]
        )
        self.assertEqual(
            self.candidate[0x4309:0x430F],
            bytes.fromhex("3E 03 E0 70 06 C6"),
        )

    def test_diagnostic_variants_are_disjoint(self) -> None:
        wall, wall_receipt = r297.build(
            self.base, self.base_receipt, variant="wall-only"
        )
        scene, scene_receipt = r297.build(
            self.base, self.base_receipt, variant="scene-only"
        )
        wall_delta = {
            index for index, pair in enumerate(zip(self.base, wall, strict=True))
            if pair[0] != pair[1] and index >= 0x0150
        }
        scene_delta = {
            index for index, pair in enumerate(zip(self.base, scene, strict=True))
            if pair[0] != pair[1] and index >= 0x0150
        }
        self.assertTrue(wall_delta)
        self.assertTrue(scene_delta)
        self.assertTrue(wall_delta.isdisjoint(scene_delta))
        self.assertTrue(wall_receipt["wall_patch"]["installed"])
        self.assertFalse(wall_receipt["scene0b_patch"]["installed"])
        self.assertFalse(scene_receipt["wall_patch"]["installed"])
        self.assertTrue(scene_receipt["scene0b_patch"]["installed"])


if __name__ == "__main__":
    unittest.main()
