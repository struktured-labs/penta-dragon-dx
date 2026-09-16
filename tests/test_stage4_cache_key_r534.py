"""Deterministic build and machine-code contracts for experimental r534."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts/diagnostics"), str(ROOT / "scripts")]
import compose_ending_bgp_handoff_r518 as base_builder
import compose_stage4_cache_key_r534 as cache_key
import compose_story_neutral_guard_r533 as parent_builder
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches
from stage_card_palette_handoff import inspect_stage_card_palette_handoff
from verify_low_health_flicker import bulk_compiler_profile, publication_route_profile
from verify_menu_icon_palettes import BANK20_LUT, menu_oracle
from verify_stage1_no_bleed import DUNGEON_TABLE_OFFSET, expected_stage1_table
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact
from expansion_bank_ownership_r456 import inspect_tail


EXPECTED_SHA256 = (
    "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"
)
EXPECTED_MD5 = "1bd65503ff407e44114dc206087e92f2"


class Stage4CacheKeyR534Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not base_builder.BASE.is_file():
            raise unittest.SkipTest("retained exact r475 base is unavailable")
        cls.source = base_builder.BASE.read_bytes()
        cls.parent, _ = parent_builder.build(cls.source)
        cls.candidate, cls.receipt = cache_key.build(cls.source)

    def test_exact_identity_and_retained_output(self) -> None:
        self.assertEqual(hashlib.sha256(self.candidate).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(hashlib.md5(self.candidate).hexdigest(), EXPECTED_MD5)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertFalse(self.receipt["promotable"])
        self.assertEqual(
            (cache_key.OUT / "candidate.gb").read_bytes(), self.candidate
        )

    def test_exact_parent_delta_is_confined_to_two_fragments(self) -> None:
        changed = {
            index for index, (before, after) in enumerate(
                zip(self.parent, self.candidate)
            ) if before != after
        }
        delay = cache_key.offset(cache_key.DELAY_SOURCE_ADDR)
        helper = cache_key.offset(cache_key.HELPER_KEY_SOURCE_ADDR)
        allowed = (
            set(range(delay, delay + len(cache_key.NEW_DELAY_REGION)))
            | set(range(helper, helper + len(cache_key.NEW_HELPER_REGION)))
            | set(cache_key.CHECKSUM_OFFSETS)
        )
        self.assertLessEqual(changed, allowed)
        self.assertEqual(
            changed,
            {int(value, 16) for value in self.receipt["changed_from_parent"]},
        )

    def test_machine_code_computes_the_declared_key(self) -> None:
        delay = cache_key.offset(cache_key.DELAY_SOURCE_ADDR)
        helper = cache_key.offset(cache_key.HELPER_KEY_SOURCE_ADDR)
        self.assertEqual(
            self.candidate[helper:helper + 10],
            bytes.fromhex("FA 72 C2 21 05 C3 AE 47 18 D1"),
        )
        self.assertEqual(
            self.candidate[delay:delay + 11],
            bytes.fromhex("FA B9 C1 21 5B C2 AE 4F C3 92 DA"),
        )
        self.assertEqual(cache_key.KEY_A, (210, 357))
        self.assertEqual(cache_key.KEY_B, (25, 187))
        runtime_jr_site = 0xDB3A
        self.assertEqual(
            runtime_jr_site + 2
            + int.from_bytes(bytes((0xD1,)), "little", signed=True),
            0xDB0D,
        )

    def test_hot_path_costs_only_four_t_cycles(self) -> None:
        runtime = self.receipt["runtime"]
        self.assertEqual(runtime["old_key_to_compare_t"], 104)
        self.assertEqual(runtime["new_key_to_compare_t"], 108)
        self.assertEqual(runtime["delta_t_per_stage4_decision"], 4)
        self.assertEqual(runtime["native_headroom_t_per_stage4_decision"], 36)

    def test_inherited_profiles_remain_exact(self) -> None:
        self.assertEqual(
            publication_boundary(self.candidate)["variant"],
            "r534-stage4-cache-key-727ee496",
        )
        self.assertTrue(semantic_expansion_is_exact(self.candidate))
        self.assertEqual(
            publication_route_profile(self.candidate),
            "r451c-bounded-room03",
        )
        self.assertTrue(bulk_compiler_profile(self.candidate))
        self.assertTrue(
            inspect_stage_card_palette_handoff(self.candidate)["installed"]
        )
        expected_menu, _reserved = menu_oracle(self.candidate)
        self.assertEqual(
            expected_menu,
            self.candidate[BANK20_LUT:BANK20_LUT + 0x100],
        )
        table = self.candidate[
            DUNGEON_TABLE_OFFSET:DUNGEON_TABLE_OFFSET + 0x100
        ]
        self.assertEqual(expected_stage1_table(self.candidate), table)
        for target in range(9):
            self.assertEqual(
                arena_palette_table(self.candidate, target),
                arena_palette_table(self.parent, target),
            )
        self.assertTrue(relocated_ted_latches(self.candidate))
        tail = inspect_tail(self.candidate)
        self.assertTrue(tail["exact"])
        self.assertEqual(tail["mode"], "reconstructed-r534")

    def test_exact_base_mutations_reject(self) -> None:
        for offset in (0x14F, base_builder.off(20, base_builder.BODY)):
            damaged = bytearray(self.source)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                cache_key.build(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
