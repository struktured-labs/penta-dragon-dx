"""Deterministic build, ABI, and inheritance tests for palette r529."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import compose_ending_bgp_handoff_r518 as base_builder
import compose_ending_bgp_handoff_r527 as parent_builder
import compose_palette_publisher_atomic_r529 as palette
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches
from stage_card_palette_handoff import inspect_stage_card_palette_handoff
from verify_low_health_flicker import bulk_compiler_profile, publication_route_profile
from verify_menu_icon_palettes import BANK20_LUT, menu_oracle
from verify_stage1_no_bleed import DUNGEON_TABLE_OFFSET, expected_stage1_table
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact


EXPECTED_SHA256 = (
    "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208"
)
EXPECTED_ROUTER = bytes.fromhex(
    "F0 40 CB 7F 78 C1 20 06 "
    "E5 21 F4 71 18 05 F3 E5 21 E3 71 E5 C3 C0 09"
)


class PalettePublisherAtomicR529(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not base_builder.BASE.is_file():
            raise unittest.SkipTest("retained exact r475 base is unavailable")
        cls.source = base_builder.BASE.read_bytes()
        cls.parent, _ = parent_builder.build(cls.source)
        cls.candidate, cls.receipt = palette.build(cls.source)
        _r518_candidate, r518_receipt = base_builder.build(cls.source)
        cls.labels = {
            name: int(address, 16)
            for name, address in r518_receipt["labels"].items()
        }

    def test_exact_identity_and_retained_output(self) -> None:
        self.assertEqual(hashlib.sha256(self.candidate).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(self.receipt["candidate_sha256"], EXPECTED_SHA256)
        self.assertEqual(self.receipt["parent_sha256"], palette.PARENT_SHA256)
        self.assertEqual(self.receipt["router_len"], 23)
        self.assertFalse(self.receipt["promotable"])
        self.assertEqual((palette.OUT / "candidate.gb").read_bytes(), self.candidate)

    def test_router_restores_bc_before_saving_hl(self) -> None:
        self.assertEqual(palette.build_router(), EXPECTED_ROUTER)
        self.assertEqual(EXPECTED_ROUTER[4:8], bytes.fromhex("78 C1 20 06"))
        self.assertEqual(EXPECTED_ROUTER[8], 0xE5)
        self.assertEqual(EXPECTED_ROUTER[14:16], bytes.fromhex("F3 E5"))
        self.assertNotIn(0xFB, EXPECTED_ROUTER)

    def test_source_entries_have_exact_interrupt_contract(self) -> None:
        masked = palette.source_writer(masked=True)
        unmasked = palette.source_writer(masked=False)
        self.assertEqual(masked, bytes.fromhex(
            "E1 2A E2 2A E2 2A E2 2A E2 FB C9"
        ))
        self.assertEqual(unmasked, bytes.fromhex(
            "E1 2A E2 2A E2 2A E2 2A E2 C9"
        ))
        self.assertEqual(masked.count(bytes.fromhex("2A E2")), 4)
        self.assertEqual(unmasked.count(bytes.fromhex("2A E2")), 4)

    def test_exact_parent_delta_is_bounded(self) -> None:
        ready = self.labels["palette_guard_native_ready"]
        allowed = set(range(0x14D, 0x150))
        allowed.update(range(base_builder.off(20, ready),
                             base_builder.off(20, ready) + 3))
        allowed.update(range(base_builder.off(20, palette.ROUTER),
                             base_builder.off(20, palette.ROUTER) + 23))
        for bank in (13, 16):
            allowed.update(range(base_builder.off(bank, palette.SOURCE_MASKED_ENTRY),
                                 base_builder.off(bank, palette.SOURCE_MASKED_ENTRY) + 11))
            allowed.update(range(base_builder.off(bank, palette.SOURCE_UNMASKED_ENTRY),
                                 base_builder.off(bank, palette.SOURCE_UNMASKED_ENTRY) + 10))
        changed = {
            index for index, (before, after) in enumerate(
                zip(self.parent, self.candidate)
            ) if before != after
        }
        self.assertEqual(len(changed), 58)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(
            changed,
            {int(value, 16) for value in self.receipt["changed_from_parent"]},
        )

    def test_inherited_profiles_remain_exact(self) -> None:
        self.assertEqual(publication_boundary(self.candidate)["variant"],
                         "r529-palette-atomic-5c49fa5d")
        self.assertTrue(semantic_expansion_is_exact(self.candidate))
        self.assertEqual(publication_route_profile(self.candidate),
                         "r451c-bounded-room03")
        self.assertTrue(bulk_compiler_profile(self.candidate))
        self.assertTrue(inspect_stage_card_palette_handoff(self.candidate)["installed"])
        expected_menu, _reserved = menu_oracle(self.candidate)
        self.assertEqual(expected_menu,
                         self.candidate[BANK20_LUT:BANK20_LUT + 0x100])
        table = self.candidate[DUNGEON_TABLE_OFFSET:DUNGEON_TABLE_OFFSET + 0x100]
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
                palette.build(bytes(damaged))


if __name__ == "__main__":
    unittest.main()
