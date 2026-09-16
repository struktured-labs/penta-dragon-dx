#!/usr/bin/env python3
"""Static controls for the live Stage-1 room-local wall oracle."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts" / "diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

import verify_stage1_spike_palettes as spike  # noqa: E402
import verify_stage1_hazard_menu as hazard_menu  # noqa: E402


class Stage1SpikeRoomContextOracleTests(unittest.TestCase):
    def test_prehelper_publisher_is_variant_qualified(self) -> None:
        probe = (ROOT / "scripts/diagnostics/probe_stage1_spike_palettes.lua").read_text()
        block = probe.split("PENTA_R449F_PREHELPER_PUBLICATION =", 1)[1]
        block = block.split("PENTA_R351_PUBLICATION", 1)[0]
        self.assertIn("PENTA_EXPECTED_PUBLICATION_VARIANT", block)
        self.assertIn("r449f-prehelper-title-v6-d82f563d", block)

    def test_policy_is_pinned_to_the_independently_reviewed_fixture(self) -> None:
        self.assertEqual(
            hashlib.sha256(spike.ROOM01_WALL_FIXTURE.read_bytes()).hexdigest(),
            spike.ROOM01_WALL_FIXTURE_SHA256,
        )
        self.assertEqual(
            spike.REVIEWED_ROOM_LOCAL_ATTRS,
            {
                (0x01, 0x24): 0x06,
                (0x01, 0x25): 0x06,
                (0x01, 0x26): 0x06,
                (0x01, 0x27): 0x06,
                (0x01, 0x30): 0x06,
                (0x01, 0x33): 0x06,
                (0x01, 0x35): 0x06,
                (0x01, 0x36): 0x06,
            },
        )
        self.assertEqual(
            spike.REVIEWED_ROOM_LOCAL_ATTR_SPEC,
            (
                "01:24:06,01:25:06,01:26:06,01:27:06,"
                "01:30:06,01:33:06,01:35:06,01:36:06"
            ),
        )

    def test_only_four_room01_ids_diverge_from_the_immutable_lut(self) -> None:
        expected_divergences = {
            (0x01, 0x24): 0x06,
            (0x01, 0x27): 0x06,
            (0x01, 0x30): 0x06,
            (0x01, 0x33): 0x06,
        }
        self.assertEqual(
            spike.REVIEWED_ROOM_LOCAL_DIVERGENCES,
            expected_divergences,
        )
        for (room, tile), reviewed_attr in expected_divergences.items():
            with self.subTest(tile=f"{tile:02X}"):
                immutable_attr = spike.EXPECTED_ATTR_TABLE[tile]
                self.assertEqual(immutable_attr, 0x00)
                self.assertEqual(
                    spike.REVIEWED_ROOM_LOCAL_ATTRS.get(
                        (room, tile), immutable_attr
                    ),
                    reviewed_attr,
                )
                # The same tile ID in room $05 remains governed by the
                # immutable BG0 table. Both opposite mutations must reject.
                self.assertNotEqual(immutable_attr, reviewed_attr)
                self.assertEqual(
                    spike.REVIEWED_ROOM_LOCAL_ATTRS.get(
                        (0x05, tile), immutable_attr
                    ),
                    0x00,
                )

    def test_lua_threads_publication_owned_room_into_live_oracles(self) -> None:
        source = spike.PROBE.read_text()
        self.assertIn(
            'os.getenv("STAGE1_SPIKE_REVIEWED_ROOM_LOCAL_ATTRS")',
            source,
        )
        self.assertIn('os.getenv("STAGE1_SPIKE_EXPECTED_ROOM")', source)
        self.assertIn(
            "local function expected_cell_attr(room, offset, tile)",
            source,
        )
        self.assertIn(
            "local reviewed = reviewed_room_local_attrs[room * 0x100 + tile]",
            source,
        )
        self.assertEqual(source.count("expected_cell_attr("), 4)
        self.assertIn("local pending_map_publications = {}", source)
        self.assertIn("local physical_map_owners = {}", source)
        self.assertIn("room = emu:read8(0xFFE5)", source)
        self.assertIn(
            "room, row * 32 + column, source)",
            source,
        )

        visible_start = source.index(
            "local function inspect_visible_attributes()"
        )
        visible_end = source.index(
            "\n\n-- Check the exact left/right attachment cells",
            visible_start,
        )
        visible_oracle = source[visible_start:visible_end]
        self.assertIn("local base, owner = active_map_owner()", visible_oracle)
        self.assertIn("local room = owner.room", visible_oracle)
        self.assertNotIn("local room = emu:read8(0xFFBD)", visible_oracle)

        flip_start = source.index("-- The native publisher selects")
        flip_end = source.index(
            "\n\n  emu:setBreakpoint(function()", flip_start
        )
        flip_oracle = source[flip_start:flip_end]
        self.assertIn(
            "local pending = pending_map_publications[target_base]",
            flip_oracle,
        )
        self.assertIn(
            "local expected_owner = pending or physical_map_owners[target_base]",
            flip_oracle,
        )
        self.assertNotIn("emu:read8(0xFFBD)", flip_oracle)

        endpoint_start = source.index(
            "local function inspect_active_endpoint_rows()"
        )
        endpoint_end = source.index("\n\nlocal function watched_bytes()", endpoint_start)
        endpoint_oracle = source[endpoint_start:endpoint_end]
        self.assertIn("local base, owner = active_map_owner()", endpoint_oracle)
        self.assertNotIn("emu:read8(0xFFBD)", endpoint_oracle)

        static_start = source.index("local function inspect_static_tooth_rows()")
        static_end = source.index("\n\nlocal function bank1_art_mismatches()", static_start)
        static_oracle = source[static_start:static_end]
        self.assertIn("local owner = physical_map_owners[base]", static_oracle)
        self.assertNotIn("emu:read8(0xFFBD)", static_oracle)

        verifier_source = Path(spike.__file__).read_text()
        self.assertIn(
            '"STAGE1_SPIKE_EXPECTED_ROOM": str(expected_room)',
            verifier_source,
        )
        self.assertIn(
            '"live_ffbd_used_as_oracle": False', verifier_source
        )
        self.assertIn(
            "and map_owner_missing_visible_frames == 0", verifier_source
        )

        start = source.index(
            "local function expected_cell_attr(room, offset, tile)"
        )
        end = source.index("\n\n-- Hardware reports", start)
        oracle = source[start:end]
        self.assertNotIn("emu:read8", oracle)
        self.assertNotIn("0xC600", oracle)
        self.assertIn(
            "broad visible/map-flip oracle uses pinned room-local wall context",
            hazard_menu.CURRENT_HAZARD_REQUIRED_CHECKS,
        )

    def test_room05_control_and_room01_mutants_have_opposite_verdicts(self) -> None:
        def matches(room: int, tile: int, actual: int) -> bool:
            fallback = spike.EXPECTED_ATTR_TABLE[tile]
            expected = spike.REVIEWED_ROOM_LOCAL_ATTRS.get(
                (room, tile), fallback
            )
            return actual == expected

        for tile in (0x24, 0x27, 0x30, 0x33):
            with self.subTest(room="01", tile=f"{tile:02X}"):
                self.assertTrue(matches(0x01, tile, 0x06))
                self.assertFalse(matches(0x01, tile, 0x00))
            with self.subTest(room="05", tile=f"{tile:02X}"):
                self.assertTrue(matches(0x05, tile, 0x00))
                self.assertFalse(matches(0x05, tile, 0x06))

    def test_map_owner_entry_is_exactly_bank1_not_numeric_pc_aliases(self) -> None:
        source = spike.PROBE.read_text()
        arm_start = source.index("local function arm_physical_map_publication()")
        arm_end = source.index("\nend\n", arm_start) + len("\nend\n")
        arm = source[arm_start:arm_end]
        self.assertIn('emu:read8(0xFF99) ~= 0x01', arm)
        self.assertIn('destination_high ~= 0x98', arm)
        self.assertIn('destination_high ~= 0x9C', arm)
        self.assertNotIn('& 0xFC00', arm)
        self.assertEqual(source.count("0x42A7, 1)"), 2)
        self.assertIn(
            "if not arm_physical_map_publication() then return end",
            source,
        )

    def test_semantic_write_sites_cover_primary_and_room01_clone_exactly(
        self,
    ) -> None:
        self.assertEqual(
            spike.SEMANTIC_WRITE_SITES,
            (
                0x432E, 0x4330, 0x434D, 0x4359,
                0x452E, 0x4530, 0x454D, 0x4559,
            ),
        )
        helper = spike.build_semantic_helper()
        for address in spike.SEMANTIC_WRITE_SITES:
            helper_base = (
                spike.SEMANTIC_HELPER_ENTRY
                if address < spike.SEMANTIC_ROOM01_HELPER_ADDR
                else spike.SEMANTIC_ROOM01_HELPER_ADDR
            )
            self.assertEqual(helper[address - helper_base], 0x22)
        source = spike.PROBE.read_text()
        self.assertIn("end, address, semantic_helper_bank)", source)
        self.assertNotIn(
            "ipairs({0x432E, 0x4330, 0x434D, 0x4358})",
            source,
        )
        verifier = Path(spike.__file__).read_text()
        self.assertIn(
            '"STAGE1_SPIKE_SEMANTIC_HELPER_BANK": str(SEMANTIC_HELPER_BANK)',
            verifier,
        )
        self.assertIn(
            '"STAGE1_SPIKE_SEMANTIC_WRITE_SITES": ",".join(',
            verifier,
        )

    def test_unbounded_semantic_counters_not_bounded_trace_own_verdict(
        self,
    ) -> None:
        # Both retained diagnostic events happen to be on $9800; unbounded
        # counters still prove later clean writes to both physical pages.
        values = {
            "hazard_attr_write_trace": (
                "f1:p432E:h9800:a9C00:s0:l10:hidden;"
                "f2:p452E:h9801:a9C00:s0:l11:hidden"
            ),
            "semantic_attr_write_hits": "4",
            "hidden_semantic_attr_write_hits": "4",
            "active_hazard_attr_write_hits": "0",
            "semantic_attr_write_invalid_destination_hits": "0",
            "semantic_attr_write_bank_mismatch_hits": "0",
            "semantic_attr_write_installed_sites": "8",
            "hazard_attr_write_trace_dropped": "2",
            "semantic_attr_write_9800_hits": "2",
            "semantic_attr_write_9c00_hits": "2",
        }
        receipt = spike.semantic_attr_write_receipt(values)
        self.assertEqual(receipt["bases"], ["9800", "9C00"])
        self.assertTrue(receipt["partition_exact"])
        self.assertTrue(receipt["clean"])

        mutations = (
            {
                "semantic_attr_write_9800_hits": "4",
                "semantic_attr_write_9c00_hits": "0",
            },
            {
                "hidden_semantic_attr_write_hits": "3",
                "active_hazard_attr_write_hits": "1",
            },
            {
                "hidden_semantic_attr_write_hits": "3",
                "semantic_attr_write_9800_hits": "1",
                "semantic_attr_write_invalid_destination_hits": "1",
            },
            {"semantic_attr_write_bank_mismatch_hits": "1"},
            {"semantic_attr_write_installed_sites": "7"},
            {"hazard_attr_write_trace_dropped": "1"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                mutant = {**values, **mutation}
                self.assertFalse(
                    spike.semantic_attr_write_receipt(mutant)["clean"]
                )
        missing = dict(values)
        del missing["semantic_attr_write_9c00_hits"]
        with self.assertRaises(KeyError):
            spike.semantic_attr_write_receipt(missing)

    def test_semantic_static_identity_includes_contextual_clone_and_dispatch(
        self,
    ) -> None:
        self.assertEqual(
            spike.SEMANTIC_CONTEXT_TRAMPOLINE,
            bytes.fromhex("F0 E5 3D C2 00 43 C3 00 45"),
        )
        self.assertEqual(
            spike.SEMANTIC_LEGACY_CONTEXT_TRAMPOLINE,
            bytes.fromhex("F0 BD 3D C2 00 43 C3 00 45"),
        )
        rom = bytearray(32 * 0x4000)
        table = bytes(spike.EXPECTED_ATTR_TABLE)
        rom[
            spike.BG_TABLE_OFFSET:spike.BG_TABLE_OFFSET + len(table)
        ] = table
        helper = spike.build_semantic_helper()
        lut = spike.build_semantic_lut(table)
        room01_helper = spike.build_semantic_room01_helper(helper)
        room01_lut = spike.build_semantic_room01_lut(lut)

        def write_switchable(bank: int, address: int, payload: bytes) -> int:
            offset = bank * 0x4000 + address - 0x4000
            rom[offset:offset + len(payload)] = payload
            return offset

        component_offsets = [
            write_switchable(
                spike.SEMANTIC_HELPER_BANK,
                spike.SEMANTIC_HELPER_ENTRY,
                helper,
            ),
            write_switchable(
                spike.SEMANTIC_HELPER_BANK,
                spike.SEMANTIC_LUT_ADDR,
                lut,
            ),
            write_switchable(
                spike.SEMANTIC_HELPER_BANK,
                spike.SEMANTIC_ROOM01_HELPER_ADDR,
                room01_helper,
            ),
            write_switchable(
                spike.SEMANTIC_HELPER_BANK,
                spike.SEMANTIC_ROOM01_LUT_ADDR,
                room01_lut,
            ),
        ]
        trampoline_offsets = []
        for address in spike.SEMANTIC_CALLER_RETURNS:
            offset = write_switchable(
                spike.SEMANTIC_HELPER_BANK,
                address,
                spike.SEMANTIC_CONTEXT_TRAMPOLINE,
            )
            trampoline_offsets.append(offset)
            component_offsets.append(offset)
        component_offsets.append(write_switchable(
            spike.SEMANTIC_HELPER_BANK,
            spike.SEMANTIC_RETURN_BRIDGE,
            bytes([
                0x3E, spike.SEMANTIC_PRIVATE_BANK, 0xCD, 0x61, 0x00,
            ]),
        ))
        component_offsets.append(write_switchable(
            spike.SEMANTIC_PRIVATE_BANK,
            spike.SEMANTIC_PRIVATE_RETURN,
            bytes([
                0xC3,
                spike.SEMANTIC_PRIVATE_CONTINUATION & 0xFF,
                spike.SEMANTIC_PRIVATE_CONTINUATION >> 8,
            ]),
        ))
        self.assertTrue(spike.semantic_expansion_is_exact(bytes(rom)))
        for offset in component_offsets:
            with self.subTest(offset=f"{offset:06X}"):
                mutant = bytearray(rom)
                mutant[offset] ^= 0x01
                self.assertFalse(
                    spike.semantic_expansion_is_exact(bytes(mutant))
                )
        for offset in trampoline_offsets:
            with self.subTest(legacy_row_context_at=f"{offset:06X}"):
                legacy = bytearray(rom)
                legacy[
                    offset:offset + len(
                        spike.SEMANTIC_LEGACY_CONTEXT_TRAMPOLINE
                    )
                ] = spike.SEMANTIC_LEGACY_CONTEXT_TRAMPOLINE
                self.assertFalse(
                    spike.semantic_expansion_is_exact(bytes(legacy))
                )
        all_legacy = bytearray(rom)
        for offset in trampoline_offsets:
            all_legacy[
                offset:offset + len(
                    spike.SEMANTIC_LEGACY_CONTEXT_TRAMPOLINE
                )
            ] = spike.SEMANTIC_LEGACY_CONTEXT_TRAMPOLINE
        self.assertFalse(
            spike.semantic_expansion_is_exact(bytes(all_legacy))
        )


if __name__ == "__main__":
    unittest.main()
