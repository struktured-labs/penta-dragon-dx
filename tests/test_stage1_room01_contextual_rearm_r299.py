#!/usr/bin/env python3
"""Focused static controls for the non-promotable r299 contextual rearm."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_room01_contextual_rearm_r299 as r299  # noqa: E402


EXPECTED_SHA256 = "6ed5ca5559b62bcc6ca8baed8c9060161a85a7657a34d918ad9baf8275356ef8"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Room01ContextualRearmR299Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r299.BASE.read_bytes()
        cls.base_receipt = r299.BASE_RECEIPT.read_bytes()
        cls.candidate, cls.receipt = r299.build(cls.base, cls.base_receipt)

    def test_identity_checksums_and_r292_isolation(self) -> None:
        self.assertEqual(sha256(self.candidate), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertFalse(self.receipt["promotable"])
        self.assertEqual(self.candidate[0:8], r299.r297.OLD_RST0)
        self.assertEqual(self.candidate[0x0838:0x0842], r299.r297.OLD_ROOM_STUB)
        self.assertEqual(self.candidate[0x0847:0x0850], r299.r297.MAPPER_DISPATCH)
        self.assertEqual(self.candidate[0x4303:0x4319], self.base[0x4303:0x4319])
        lut = r299.r297.bank_offset(13, 0x7000)
        self.assertEqual(self.candidate[lut:lut + 0x100], self.base[lut:lut + 0x100])
        self.assertEqual(self.candidate[14 * r299.r297.BANK_SIZE:15 * r299.r297.BANK_SIZE],
                         self.base[14 * r299.r297.BANK_SIZE:15 * r299.r297.BANK_SIZE])

    def test_all_contextual_patch_preimages_and_machine_bytes_are_exact(self) -> None:
        self.assertEqual(r299.LAVA_MARKER_ADDR, 0x7E0E)
        expected = (
            (13, r299.SCENE_DISPATCH_ADDR, r299.NEW_SCENE_DISPATCH),
            (13, r299.SCENE_REARM_ADDR, r299.SCENE_REARM + b"\0"),
            (13, r299.LAVA_MARKER_ADDR, r299.NEW_LAVA_MARKER),
            (13, r299.MAPPER_ENTRY_ADDR, r299.MAPPER_ENTRY),
            (21, r299.CONTEXT_HELPER_ADDR, r299.CONTEXT_HELPER),
            (21, r299.RETURN_BANK13_ADDR, r299.RETURN_BANK13),
        )
        for bank, address, payload in expected:
            offset = r299.r297.bank_offset(bank, address)
            self.assertEqual(self.candidate[offset:offset + len(payload)], payload)
        # r299's marker is post-scene and directly reaches the mapping entry;
        # its helper tail-maps bank13 then uses the existing $6BE7 RET.
        self.assertTrue(r299.NEW_LAVA_MARKER.endswith(bytes.fromhex("CD 80 61")))
        self.assertEqual(r299.MAPPER_ENTRY + r299.CONTEXT_HELPER[:1],
                         bytes.fromhex("3E 15 EA 00 21 F0"))
        self.assertTrue(r299.CONTEXT_HELPER.endswith(bytes.fromhex("C3 E2 6B")))
        self.assertEqual(self.base[r299.r297.bank_offset(13, 0x6BE7)], 0xC9)

    def test_repeated_scene_and_menu_refreshes_reapply_room01_after_global_clear(self) -> None:
        # A refresh copies the immutable global LUT (all four IDs are BG0).
        global_clear = {tile: 0 for tile in r299.TARGET_TILES}
        attrs = {tile: 6 for tile in r299.TARGET_TILES}
        for scene in (0x0B, 0x02, 0x0B, 0x0A, 0x0B):
            attrs = dict(global_clear)
            attrs = r299.contextual_values(attrs, ffb7=2, scene=scene, room=1)
            self.assertEqual(attrs, {tile: 6 for tile in r299.TARGET_TILES})
        caches = {0xDF53: 0x11, 0xDF57: 0x22}
        for _ in range(3):
            caches = r299.scene_rearm_caches(caches, stage=0)
            self.assertEqual(caches, {0xDF53: 0, 0xDF57: 0})

    def test_room05_restores_bg0_and_later_stages_are_a_strict_noop(self) -> None:
        values = {tile: 0x80 + index for index, tile in enumerate(r299.TARGET_TILES)}
        self.assertEqual(r299.contextual_values(values, ffb7=2, scene=0x02, room=5),
                         {tile: 0 for tile in r299.TARGET_TILES})
        self.assertEqual(r299.contextual_values(values, ffb7=3, scene=0x03, room=1), values)
        caches = {0xDF53: 0x66, 0xDF57: 0x77}
        self.assertEqual(r299.scene_rearm_caches(caches, stage=1), caches)

    def test_call_abi_stack_bank_and_cycle_contracts_are_pinned(self) -> None:
        contract = self.receipt["offline_contract"]["wall"]
        self.assertEqual(contract["call_ret_stack_delta"], 0)
        self.assertTrue(contract["BC_DE_HL_SP_SVBK_FF99_DC09_preserved"])
        self.assertTrue(contract["bank21_to_bank13_return_exact"])
        self.assertTrue(contract["r297_direct_ffbd_rst_hook_absent"])
        self.assertEqual(contract["scene0b_normal_gateway_t_cycles"],
                         {"r292": 44, "r297": 44, "r299": 44})
        self.assertNotIn(bytes.fromhex("E0 99"), r299.CONTEXT_HELPER)
        self.assertNotIn(bytes.fromhex("EA 09 DC"), r299.CONTEXT_HELPER)
        self.assertNotIn(bytes.fromhex("E0 70"), r299.CONTEXT_HELPER)

    def test_full_scene_only_and_wall_only_variants_are_disjoint(self) -> None:
        wall, wall_receipt = r299.build(self.base, self.base_receipt, variant="wall-only")
        scene, scene_receipt = r299.build(self.base, self.base_receipt, variant="scene-only")
        delta = lambda candidate: {index for index, pair in enumerate(zip(self.base, candidate, strict=True))
                                   if pair[0] != pair[1] and index >= 0x0150}
        self.assertTrue(delta(wall).isdisjoint(delta(scene)))
        self.assertTrue(wall_receipt["wall_patch"]["installed"])
        self.assertFalse(wall_receipt["scene0b_patch"]["installed"])
        self.assertFalse(scene_receipt["wall_patch"]["installed"])
        self.assertTrue(scene_receipt["scene0b_patch"]["installed"])


if __name__ == "__main__":
    unittest.main()
