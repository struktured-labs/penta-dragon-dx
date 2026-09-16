#!/usr/bin/env python3
"""Focused static controls for r301's scene-$0B SELECT invalidation."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import build_stage1_scene0b_menu_invalidation_r301 as r301  # noqa: E402


EXPECTED_SHA256 = "e5c307c59c6232f808ffb6cd026c8d4427682364d2b4f0b9fe221ca5842079c8"


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class Stage1Scene0BMenuInvalidationR301Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base = r301.BASE.read_bytes()
        cls.base_receipt = r301.BASE_RECEIPT.read_bytes()
        cls.r297_full, _ = r301.r297.build(cls.base, cls.base_receipt, variant="full")
        cls.candidate, cls.receipt = r301.build(cls.base, cls.base_receipt)

    def test_identity_is_exact_r292_plus_r297_full_plus_r301(self) -> None:
        self.assertEqual(sha256(self.r297_full), r301.R297_FULL_SHA256)
        self.assertEqual(sha256(self.candidate), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertFalse(self.receipt["promotable"])
        # The component is independent of the bank20 row experiment.
        start, end = 20 * r301.r297.BANK_SIZE, 21 * r301.r297.BANK_SIZE
        self.assertEqual(self.candidate[start:end], self.r297_full[start:end])

    def test_ffe4_zero_prefix_and_cycle_cost_are_byte_exact(self) -> None:
        offset = r301.r297.bank_offset(13, r301.MENU_HELPER_ADDR)
        self.assertEqual(self.r297_full[offset:offset + 4], r301.MENU_PREFIX)
        self.assertEqual(self.candidate[offset:offset + 4], r301.MENU_PREFIX)
        timing = self.receipt["offline_contract"]["timing"]["FFE4_zero"]
        self.assertEqual(timing, {"r297": 36, "r301": 36, "delta": 0})
        closed = r301.model(ffe4=0, ffb7=2, d880=0x0B,
                            caches={0xDF53: 0x19, 0xDF57: 0x1A})
        self.assertTrue(closed["z"])
        self.assertEqual(closed["caches"], {0xDF53: 0x19, 0xDF57: 0x1A})

    def test_nonzero_body_uses_fixed_mapper_tail_not_r297_dispatcher(self) -> None:
        body = r301.r297.bank_offset(13, r301.MENU_HELPER_ADDR + 4)
        self.assertEqual(self.candidate[body:body + len(r301.NEW_MENU_BODY)],
                         r301.NEW_MENU_BODY)
        self.assertEqual(self.candidate[r301.FIXED_MAPPER_TAIL_ADDR:r301.FIXED_MAPPER_TAIL_ADDR + 4],
                         r301.FIXED_MAPPER_TAIL)
        self.assertEqual(self.candidate[r301.r297.MAPPER_DISPATCH_ADDR:r301.r297.MAPPER_DISPATCH_ADDR + len(r301.r297.MAPPER_DISPATCH)],
                         r301.r297.MAPPER_DISPATCH)
        self.assertEqual(self.candidate[r301.r297.RST0_ADDR:r301.r297.RST0_ADDR + len(r301.r297.NEW_RST0)],
                         r301.r297.NEW_RST0)

    def test_caves_are_erased_before_install_and_preserve_r297_wall_owner(self) -> None:
        ingress = r301.r297.bank_offset(21, r301.INGRESS_ADDR)
        cave = r301.r297.bank_offset(21, r301.CONTEXT_HELPER_ADDR)
        wall = r301.r297.bank_offset(21, r301.R297_WALL_START)
        self.assertEqual(self.r297_full[ingress:ingress + len(r301.INGRESS)], b"\xFF" * len(r301.INGRESS))
        self.assertEqual(self.r297_full[cave:cave + len(r301.CONTEXT_HELPER)], b"\xFF" * len(r301.CONTEXT_HELPER))
        self.assertEqual(self.candidate[ingress:ingress + len(r301.INGRESS)], r301.INGRESS)
        self.assertEqual(self.candidate[cave:cave + len(r301.CONTEXT_HELPER)], r301.CONTEXT_HELPER)
        self.assertEqual(self.candidate[wall:wall + len(r301.r297.WALL_HELPER)], r301.r297.WALL_HELPER)
        self.assertEqual(r301.CONTEXT_HELPER_ADDR, r301.R297_WALL_END)
        self.assertEqual(r301.CONTEXT_HELPER_END, 0x6CD9)

    def test_scene0b_repeated_menu_closes_rearm_the_fail_closed_sentinel(self) -> None:
        # Each SELECT/menu refresh can replace the cache with any valid stale
        # value.  Every independent close must force both physical maps to FF.
        for stale in ((0, 0), (0x12, 0x34), (0xFF, 0), (0x66, 0x77)):
            result = r301.model(
                ffe4=1, ffb7=2, d880=0x0B,
                caches={0xDF53: stale[0], 0xDF57: stale[1]},
            )
            self.assertEqual(result["action"], "stage1-sentinel")
            self.assertEqual(result["caches"], {0xDF53: 0xFF, 0xDF57: 0xFF})
            self.assertEqual((result["a"], result["z"]), (0x0D, False))

    def test_later_stage_and_non_gameplay_contexts_are_scoped(self) -> None:
        seed = {0xDF53: 0x12, 0xDF57: 0x34}
        for stage in range(3, 9):
            result = r301.model(ffe4=1, ffb7=stage, d880=0x0B, caches=seed)
            self.assertEqual(result["action"], "later-stage-clear")
            self.assertEqual(result["caches"], {0xDF53: 0, 0xDF57: 0})
        for stage in (0, 1, 9, 0x18, 0xFF):
            result = r301.model(ffe4=1, ffb7=stage, d880=0x0B, caches=seed)
            self.assertEqual(result["action"], "unchanged")
            self.assertEqual(result["caches"], seed)

    def test_exhaustive_model_stack_and_register_contracts_are_pinned(self) -> None:
        semantic = self.receipt["offline_contract"]["semantic"]
        self.assertEqual(semantic["ffe4_ffb7_pairs"], 65536)
        self.assertEqual(semantic["logical_ffe4_ffb7_d880_states"], 256 ** 3)
        self.assertTrue(semantic["all_D880_values_ignored"])
        stack = self.receipt["offline_contract"]["stack_bank"]
        self.assertEqual(stack["stack_delta"], 0)
        self.assertTrue(stack["BC_DE_HL_SP_FF99_DC09_untouched"])
        self.assertEqual((stack["returned_A"], stack["returned_Z"]), ("$0D", False))


if __name__ == "__main__":
    unittest.main()
