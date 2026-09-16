"""Fail-closed recognition of r527's byte-exact inherited runtime profiles."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import compose_ending_bgp_handoff_r527 as ending
from stage_card_palette_handoff import inspect_stage_card_palette_handoff
from verify_later_stage_soak import sha256 as soak_sha256
from verify_low_health_flicker import (
    bulk_compiler_profile,
    owner_address,
    publication_route_profile,
)
from verify_menu_icon_palettes import BANK20_LUT, MENU_RESERVED_HAZARDS, menu_oracle
from verify_release_candidate import build_gates
from verify_stage1_no_bleed import DUNGEON_TABLE_OFFSET, expected_stage1_table
from verify_stage1_pickup_art import expected_stage1_table as pickup_expected_table
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact


SHA256 = "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b"


class R527InheritedProfiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.path = ending.OUT / "candidate.gb"
        if not cls.path.is_file():
            raise unittest.SkipTest("retained exact r527 candidate is unavailable")
        cls.rom = cls.path.read_bytes()
        if hashlib.sha256(cls.rom).hexdigest() != SHA256:
            raise unittest.SkipTest("retained r527 candidate identity differs")

    def test_runtime_profiles_are_exactly_recognized(self) -> None:
        self.assertEqual(
            publication_boundary(self.rom)["variant"],
            "r527-ending-handoff-13beaa1b",
        )
        self.assertTrue(semantic_expansion_is_exact(self.rom))
        self.assertEqual(publication_route_profile(self.rom),
                         "r451c-bounded-room03")
        self.assertEqual(owner_address(self.rom), 0xFF01)
        self.assertTrue(bulk_compiler_profile(self.rom))
        self.assertTrue(inspect_stage_card_palette_handoff(self.rom)["installed"])
        self.assertEqual(soak_sha256(self.path), SHA256)

    def test_menu_and_stage1_tables_use_inherited_semantics(self) -> None:
        expected_menu, reserved = menu_oracle(self.rom)
        self.assertEqual(reserved, frozenset(MENU_RESERVED_HAZARDS))
        self.assertEqual(expected_menu, self.rom[BANK20_LUT:BANK20_LUT + 0x100])
        table = self.rom[DUNGEON_TABLE_OFFSET:DUNGEON_TABLE_OFFSET + 0x100]
        self.assertEqual(expected_stage1_table(self.rom), table)
        self.assertEqual(pickup_expected_table(self.rom), table)

    def test_unknown_checksum_mutation_is_not_admitted(self) -> None:
        changed = bytearray(self.rom)
        changed[0x14F] ^= 1
        with self.assertRaises(RuntimeError):
            publication_boundary(changed)
        self.assertFalse(semantic_expansion_is_exact(changed))
        self.assertEqual(publication_route_profile(changed), "")
        self.assertEqual(owner_address(changed), 0xFFA5)
        self.assertEqual(bulk_compiler_profile(changed), "")
        self.assertFalse(inspect_stage_card_palette_handoff(changed)["installed"])
        expected_menu, reserved = menu_oracle(changed)
        self.assertFalse(reserved)
        self.assertNotEqual(expected_menu, changed[BANK20_LUT:BANK20_LUT + 0x100])

    def test_release_matrix_selects_current_hazard_route(self) -> None:
        gates = {
            gate.name: gate for gate in build_gates(
                self.path,
                ROOT / "tmp/r527-inherited-profile-contract",
            )
        }
        low = gates["low_health_flicker"]
        self.assertEqual(low.dependencies, ("stage1_current_hazard_state",))
        self.assertIn("--boot-derived-state", low.command)
        self.assertIn("--require-scene0b-low-health", low.command)


if __name__ == "__main__":
    unittest.main()
