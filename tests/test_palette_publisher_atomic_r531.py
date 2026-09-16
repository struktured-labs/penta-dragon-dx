"""Deterministic build, ABI, and inheritance tests for palette r531."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import compose_ending_bgp_handoff_r518 as base_builder
import compose_ending_bgp_handoff_r527 as parent_builder
import compose_palette_publisher_atomic_r529 as r529
import compose_palette_publisher_atomic_r531 as palette
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches
from stage_card_palette_handoff import inspect_stage_card_palette_handoff
from verify_low_health_flicker import bulk_compiler_profile, publication_route_profile
from verify_menu_icon_palettes import BANK20_LUT, menu_oracle
from verify_stage1_no_bleed import DUNGEON_TABLE_OFFSET, expected_stage1_table
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact


EXPECTED_SHA256 = (
    "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855"
)
EXPECTED_ROUTER = bytes.fromhex(
    "F0 40 CB 7F 28 1F F3 F0 41 E6 03 FE 01 28 0E "
    "F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA "
    "78 C1 E5 21 E3 71 18 06 78 C1 E5 21 F4 71 E5 C3 61 00"
)


class PalettePublisherAtomicR531(unittest.TestCase):
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
        self.assertEqual(self.receipt["router_len"], 47)
        self.assertFalse(self.receipt["promotable"])
        self.assertEqual((palette.OUT / "candidate.gb").read_bytes(), self.candidate)

    def test_router_has_masked_vblank_and_visible_paths(self) -> None:
        self.assertEqual(palette.build_router(), EXPECTED_ROUTER)
        self.assertEqual(EXPECTED_ROUTER[:15], bytes.fromhex(
            "F0 40 CB 7F 28 1F F3 F0 41 E6 03 FE 01 28 0E"
        ))
        self.assertEqual(EXPECTED_ROUTER[15:29], bytes.fromhex(
            "F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA"
        ))
        self.assertEqual(EXPECTED_ROUTER[-4:], bytes.fromhex("E5 C3 61 00"))
        self.assertNotIn(bytes.fromhex("C3 C0 09"), EXPECTED_ROUTER)

    def test_source_entries_have_exact_interrupt_contract(self) -> None:
        self.assertEqual(r529.source_writer(masked=True), bytes.fromhex(
            "E1 2A E2 2A E2 2A E2 2A E2 FB C9"
        ))
        self.assertEqual(r529.source_writer(masked=False), bytes.fromhex(
            "E1 2A E2 2A E2 2A E2 2A E2 C9"
        ))

    def test_exact_parent_delta_is_bounded(self) -> None:
        native = self.labels["palette_guard_native"]
        allowed = set(range(0x14D, 0x150))
        allowed.update(range(base_builder.off(20, native),
                             base_builder.off(20, native) + 3))
        allowed.update(range(base_builder.off(20, palette.ROUTER),
                             base_builder.off(20, palette.ROUTER) + 47))
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
        self.assertEqual(len(changed), 82)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(
            changed,
            {int(value, 16) for value in self.receipt["changed_from_parent"]},
        )

    def test_inherited_profiles_remain_exact(self) -> None:
        self.assertEqual(publication_boundary(self.candidate)["variant"],
                         "r531-palette-atomic-9d44e9d1")
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
