"""Deterministic build, ABI, call-graph, and inheritance tests for r532."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]
import compose_ending_bgp_handoff_r518 as base_builder
import compose_ending_bgp_handoff_r527 as parent_builder
import compose_palette_publisher_atomic_r532 as palette
from arena_palette_storage import arena_palette_table
from generate_stream_boss_states import relocated_ted_latches
from stage_card_palette_handoff import inspect_stage_card_palette_handoff
from verify_low_health_flicker import bulk_compiler_profile, publication_route_profile
from verify_menu_icon_palettes import BANK20_LUT, menu_oracle
from verify_stage1_no_bleed import DUNGEON_TABLE_OFFSET, expected_stage1_table
from verify_stage1_spike_palettes import publication_boundary, semantic_expansion_is_exact


EXPECTED_SHA256 = (
    "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821"
)
EXPECTED_ROUTER = bytes.fromhex(
    "78 C1 D5 57 F0 FF 5F AF E0 FF F0 40 CB 7F 28 16 "
    "F0 41 E6 03 FE 01 28 0E F0 41 E6 03 FE 03 20 F8 "
    "F0 41 E6 03 20 FA 7A E5 21 E3 71 E5 C3 61 00"
)
EXPECTED_WRITER = bytes.fromhex(
    "E1 2A E2 2A E2 2A E2 2A E2 7B D1 E0 FF C9"
)


class PalettePublisherAtomicR532(unittest.TestCase):
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

    def test_router_masks_ie_without_changing_ime(self) -> None:
        self.assertEqual(palette.build_router(), EXPECTED_ROUTER)
        self.assertEqual(EXPECTED_ROUTER[:10],
                         bytes.fromhex("78 C1 D5 57 F0 FF 5F AF E0 FF"))
        self.assertEqual(EXPECTED_ROUTER[-9:],
                         bytes.fromhex("7A E5 21 E3 71 E5 C3 61 00"))
        self.assertNotIn(0xF3, EXPECTED_ROUTER)
        self.assertNotIn(0xFB, EXPECTED_ROUTER)

    def test_writer_restores_de_and_ie_last(self) -> None:
        self.assertEqual(palette.source_writer(), EXPECTED_WRITER)
        self.assertEqual(EXPECTED_WRITER.count(bytes.fromhex("2A E2")), 4)
        self.assertEqual(EXPECTED_WRITER[-5:], bytes.fromhex("7B D1 E0 FF C9"))

    def test_exact_parent_delta_is_bounded(self) -> None:
        native = self.labels["palette_guard_native"]
        allowed = set(range(0x14D, 0x150))
        allowed.update(range(base_builder.off(20, native),
                             base_builder.off(20, native) + 3))
        allowed.update(range(base_builder.off(20, palette.ROUTER),
                             base_builder.off(20, palette.ROUTER) + 47))
        for bank in (13, 16):
            allowed.update(range(base_builder.off(bank, palette.SOURCE_WRITER_ENTRY),
                                 base_builder.off(bank, palette.SOURCE_WRITER_ENTRY) + 14))
        changed = {
            index for index, (before, after) in enumerate(
                zip(self.parent, self.candidate)
            ) if before != after
        }
        self.assertEqual(len(changed), 78)
        self.assertLessEqual(changed, allowed)
        self.assertEqual(
            changed,
            {int(value, 16) for value in self.receipt["changed_from_parent"]},
        )

    def test_a_is_dead_at_exact_call_graph(self) -> None:
        for bank in (13, 16):
            wrapper = self.parent[
                base_builder.off(bank, 0x7FE0):base_builder.off(bank, 0x7FE0) + 7
            ]
            continuation = self.parent[
                base_builder.off(bank, 0x717C):base_builder.off(bank, 0x717C) + 6
            ]
            self.assertEqual(wrapper, bytes.fromhex("CD DB 71 CD DB 71 C9"))
            self.assertEqual(continuation, bytes.fromhex("CD E0 7F 15 20 F7"))

    def test_inherited_profiles_remain_exact(self) -> None:
        self.assertEqual(publication_boundary(self.candidate)["variant"],
                         "r532-palette-atomic-055a2754")
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
