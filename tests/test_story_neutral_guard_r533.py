"""Deterministic build and inheritance tests for r533."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import build_v302_title_fix as base_build
import compose_ending_bgp_handoff_r518 as base_builder
import compose_palette_publisher_atomic_r532 as parent_builder
import compose_story_neutral_guard_r533 as story
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches
from stage_card_palette_handoff import inspect_stage_card_palette_handoff
from verify_low_health_flicker import bulk_compiler_profile, publication_route_profile
from verify_menu_icon_palettes import BANK20_LUT, menu_oracle
from verify_stage1_no_bleed import DUNGEON_TABLE_OFFSET, expected_stage1_table
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact


EXPECTED_SHA256 = (
    "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba"
)
EXPECTED_HALF_ROW = bytes.fromhex(
    "FE 12 D2 9A 6A FE 08 38 02 0E 80 16 00 C3 00 7F"
)


class StoryNeutralGuardR533(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not base_builder.BASE.is_file():
            raise unittest.SkipTest("retained exact r475 base is unavailable")
        cls.source = base_builder.BASE.read_bytes()
        cls.parent, _ = parent_builder.build(cls.source)
        cls.candidate, cls.receipt = story.build(cls.source)

    def test_exact_identity_and_retained_output(self) -> None:
        self.assertEqual(hashlib.sha256(self.candidate).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(self.receipt["parent_sha256"], story.PARENT_SHA256)
        self.assertFalse(self.receipt["promotable"])
        self.assertEqual((story.OUT / "candidate.gb").read_bytes(), self.candidate)

    def test_exact_two_byte_parent_delta(self) -> None:
        changed = {
            index for index, (before, after) in enumerate(
                zip(self.parent, self.candidate)
            ) if before != after
        }
        self.assertEqual(
            changed,
            {0x14F, base_builder.off(13, story.NEUTRAL_STORY_MARKER)},
        )
        self.assertEqual(
            changed,
            {int(value, 16) for value in self.receipt["changed_from_parent"]},
        )

    def test_neutral_marker_preserves_story_route(self) -> None:
        offset = base_builder.off(13, story.STORY_HALF_ROW_HELPER)
        self.assertEqual(self.candidate[offset:offset + 16], EXPECTED_HALF_ROW)
        self.assertEqual(EXPECTED_HALF_ROW[10] & 0x07, 0)
        self.assertNotEqual(EXPECTED_HALF_ROW[10] & 0x80, 0)
        self.assertEqual(
            base_build.build_story_half_row_helper(0x7F00),
            EXPECTED_HALF_ROW,
        )

    def test_inherited_profiles_remain_exact(self) -> None:
        self.assertEqual(
            publication_boundary(self.candidate)["variant"],
            "r533-story-neutral-guard-4fc5028a",
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

    def test_exact_base_mutations_reject(self) -> None:
        for offset in (0x14F, base_builder.off(20, base_builder.BODY)):
            damaged = bytearray(self.source)
            damaged[offset] ^= 1
            with self.assertRaises(ValueError):
                story.build(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
