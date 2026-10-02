#!/usr/bin/env python3
"""Offline mutation controls for the exact Scene-$0B hazard tile oracle."""

from __future__ import annotations

import hashlib
from itertools import product
from pathlib import Path
import sys
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "scripts/diagnostics"
sys.path.insert(0, str(DIAGNOSTICS))

from stage1_scene0b_hazard_tile_oracle import (  # noqa: E402
    FIXTURE_PATH,
    PACKED_WIDTH,
    PINNED_FIXTURE_SHA256,
    PINNED_NATIVE_ROM_SHA256,
    PINNED_OPERATOR_SAVEDATA_SHA256,
    PINNED_OPERATOR_STATE_SHA256,
    PINNED_STAGE1_TABLES_SHA256,
    PINNED_TILE_TABLE_SHA256,
    PINNED_WORLD_WINDOW_SHA256,
    HazardTileAssertionError,
    HazardTileContractError,
    assert_scene0b_hazard_tiles_legal,
    captured_phase_selection,
    derive_phase_from_native_authorities,
    evaluate_scene0b_hazard_tiles,
    load_contract,
    render_legal_map,
)


NATIVE_ROM = ROOT / "rom/Penta Dragon (J).gb"
OPERATOR_STATE = (
    ROOT / "save_states_for_claude/rc11_low-health-degradation.ss0"
)
PHASE_IDS = ("P0", "P1", "P2", "P3")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def extract_savedata(path: Path) -> bytes:
    """Read the one CRC-valid mGBA savedata extension without emulation."""
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError("operator state is not an mGBA PNG state")
    offset = 8
    payloads = []
    saw_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            raise AssertionError("operator state has a truncated PNG chunk")
        size = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        crc = data[offset + 8 + size:offset + 12 + size]
        if len(payload) != size or len(crc) != 4:
            raise AssertionError("operator state has a truncated PNG payload")
        if int.from_bytes(crc, "big") != zlib.crc32(kind + payload) & 0xFFFFFFFF:
            raise AssertionError("operator state has a bad PNG chunk CRC")
        if kind == b"gbAx" and len(payload) >= 8:
            extension = int.from_bytes(payload[:4], "little")
            declared_size = int.from_bytes(payload[4:8], "little")
            if extension == 2:
                expanded = zlib.decompress(payload[8:])
                if len(expanded) != declared_size:
                    raise AssertionError("mGBA savedata extension is incomplete")
                payloads.append(expanded)
        if kind == b"IEND":
            saw_iend = True
        offset += 12 + size
    if offset != len(data) or not saw_iend or len(payloads) != 1:
        raise AssertionError("operator state lacks one exact savedata payload")
    return payloads[0]


def extract_serialized_state(path: Path) -> bytes:
    """Read the one CRC-valid compressed mGBA core-state payload."""
    data = path.read_bytes()
    offset = 8
    payloads = []
    while offset < len(data):
        size = int.from_bytes(data[offset:offset + 4], "big")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        crc = data[offset + 8 + size:offset + 12 + size]
        if (
            len(payload) != size
            or len(crc) != 4
            or int.from_bytes(crc, "big")
            != zlib.crc32(kind + payload) & 0xFFFFFFFF
        ):
            raise AssertionError("operator state has an invalid PNG chunk")
        if kind == b"gbAs":
            payloads.append(zlib.decompress(payload))
        offset += 12 + size
    if len(payloads) != 1:
        raise AssertionError("operator state lacks one exact gbAs payload")
    state = payloads[0]
    if (
        len(state) != 0x11800
        or int.from_bytes(state[:4], "little") != 0x00400003
    ):
        raise AssertionError("operator gbAs size/version changed")
    return state


class Stage1Scene0BHazardTileOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = load_contract(FIXTURE_PATH)
        cls.captured_phases = captured_phase_selection(cls.contract)

    def object_result(self, evaluation, name: str):
        return next(result for result in evaluation.objects if result.name == name)

    def overwrite_object(
        self, payload: bytearray, object_name: str, tiles: bytes
    ) -> None:
        hazard_object = self.contract.object(object_name)
        family = self.contract.family(hazard_object.family)
        self.assertEqual(len(tiles), family.width * family.height)
        for local_row in range(family.height):
            start = (hazard_object.row + local_row) * PACKED_WIDTH
            start += hazard_object.column
            phase_start = local_row * family.width
            payload[start:start + family.width] = tiles[
                phase_start:phase_start + family.width
            ]

    def test_fixture_and_native_derivation_are_hash_pinned(self) -> None:
        self.assertEqual(sha256(FIXTURE_PATH.read_bytes()), PINNED_FIXTURE_SHA256)
        native_rom = NATIVE_ROM.read_bytes()
        state = OPERATOR_STATE.read_bytes()
        self.assertEqual(sha256(native_rom), PINNED_NATIVE_ROM_SHA256)
        self.assertEqual(sha256(state), PINNED_OPERATOR_STATE_SHA256)
        savedata = extract_savedata(OPERATOR_STATE)
        self.assertEqual(sha256(savedata), PINNED_OPERATOR_SAVEDATA_SHA256)
        tables = savedata[:0x800]
        self.assertEqual(sha256(tables), PINNED_STAGE1_TABLES_SHA256)
        self.assertEqual(sha256(tables[:0x400]), PINNED_TILE_TABLE_SHA256)

        derived = 0
        for family in self.contract.families:
            for phase in family.phases:
                self.assertEqual(
                    derive_phase_from_native_authorities(
                        native_rom,
                        tables,
                        family.name,
                        phase.id,
                        contract=self.contract,
                    ),
                    phase.tiles,
                )
                derived += 1
        self.assertEqual(derived, 12)

    def test_coverage_closes_the_legacy_broad_exemption(self) -> None:
        self.assertEqual(
            self.contract.coverage.counts(),
            {
                "legacy_hazard_positions": 45,
                "legacy_broad_envelope_cells": 156,
                "exact_object_cells": 192,
                "exact_object_cells_outside_legacy_envelope": 48,
                "immutable_guard_cells": 12,
                "audited_union_cells": 204,
            },
        )
        self.assertEqual(
            set(self.contract.coverage.immutable_guard_cells),
            {
                row * PACKED_WIDTH + column
                for row in range(3, 9)
                for column in (12, 13)
            },
        )

    def test_immutable_source_rebuilds_from_world_grid_and_sram(self) -> None:
        state = extract_serialized_state(OPERATOR_STATE)
        tables = extract_savedata(OPERATOR_STATE)[:0x800]

        def wram(address: int) -> int:
            return state[0x4400 + address - 0xC000]

        camera_x = (wram(0xDC00) | wram(0xDC01) << 8) >> 5
        camera_y = (wram(0xDC02) | wram(0xDC03) << 8) >> 5
        self.assertEqual((camera_x, camera_y), (3, 10))
        world_window = bytes(
            wram(
                0xC780 + (camera_y + row) * 0x40
                + camera_x + column
            )
            for row in range(6)
            for column in range(6)
        )
        self.assertEqual(sha256(world_window), PINNED_WORLD_WINDOW_SHA256)

        rebuilt = bytearray(24 * 24)
        for world_row in range(6):
            for world_column in range(6):
                world_id = world_window[world_row * 6 + world_column]
                definition = tables[
                    0x400 + world_id * 4:0x400 + (world_id + 1) * 4
                ]
                self.assertEqual(len(definition), 4)
                for metatile_row in range(2):
                    for metatile_column in range(2):
                        metatile = definition[
                            metatile_row * 2 + metatile_column
                        ]
                        tile_quad = tables[metatile * 4:(metatile + 1) * 4]
                        for tile_row in range(2):
                            for tile_column in range(2):
                                output_row = (
                                    world_row * 4 + metatile_row * 2
                                    + tile_row
                                )
                                output_column = (
                                    world_column * 4 + metatile_column * 2
                                    + tile_column
                                )
                                rebuilt[
                                    output_row * 24 + output_column
                                ] = tile_quad[tile_row * 2 + tile_column]
        for row in range(24):
            for column in range(24):
                if row >= 20 or column >= 22:
                    rebuilt[row * 24 + column] = 0
        self.assertEqual(bytes(rebuilt), self.contract.immutable_source)
        c1a0 = state[0x4400 + 0x1A0:0x4400 + 0x1A0 + 24 * 24]
        self.assertEqual(c1a0, self.contract.immutable_source)

    def test_operator_source_has_four_independent_pinned_phases(self) -> None:
        evaluation = evaluate_scene0b_hazard_tiles(
            self.contract.immutable_source, contract=self.contract
        )
        self.assertTrue(evaluation.legal)
        self.assertEqual(
            evaluation.matched_phases,
            {
                "north_standard": "P3",
                "connector_thrust": "P2",
                "upper_cylinder": "P2",
                "south_standard": "P2",
            },
        )
        self.assertEqual(evaluation.mismatch_count, 0)

    def test_all_256_cartesian_phase_combinations_are_legal(self) -> None:
        names = tuple(item.name for item in self.contract.objects)
        accepted = 0
        for values in product(PHASE_IDS, repeat=4):
            phases = dict(zip(names, values, strict=True))
            observed = render_legal_map(phases, contract=self.contract)
            evaluation = evaluate_scene0b_hazard_tiles(
                observed, contract=self.contract
            )
            self.assertTrue(evaluation.legal, phases)
            self.assertEqual(evaluation.matched_phases, phases)
            accepted += 1
        self.assertEqual(accepted, 4 ** 4)

    def test_physical_32x32_input_preserves_independent_phases(self) -> None:
        phases = {
            "north_standard": "P0",
            "connector_thrust": "P1",
            "upper_cylinder": "P2",
            "south_standard": "P3",
        }
        physical = render_legal_map(
            phases, layout="physical", contract=self.contract
        )
        self.assertEqual(len(physical), 32 * 32)
        evaluation = assert_scene0b_hazard_tiles_legal(
            physical, contract=self.contract
        )
        self.assertEqual(evaluation.matched_phases, phases)

    def test_stray_legal_tooth_inside_legacy_envelope_rejects(self) -> None:
        mutant = bytearray(self.contract.immutable_source)
        offset = next(
            offset
            for offset in self.contract.coverage.immutable_guard_cells
            if mutant[offset] != 0x64
        )
        mutant[offset] = 0x64
        evaluation = evaluate_scene0b_hazard_tiles(
            mutant, contract=self.contract
        )
        self.assertFalse(evaluation.legal)
        self.assertEqual(len(evaluation.immutable_guard_mismatches), 1)
        self.assertEqual(
            evaluation.immutable_guard_mismatches[0].actual, 0x64
        )
        self.assertTrue(all(item.exact for item in evaluation.objects))

    def test_stray_legal_tooth_outside_legacy_envelope_rejects(self) -> None:
        mutant = bytearray(self.contract.immutable_source)
        excluded = set(self.contract.coverage.audited_union_cells)
        offset = next(
            index
            for index, tile in enumerate(mutant)
            if index not in excluded and tile not in range(0x60, 0x80)
        )
        mutant[offset] = 0x64
        evaluation = evaluate_scene0b_hazard_tiles(
            mutant, contract=self.contract
        )
        self.assertFalse(evaluation.legal)
        self.assertEqual(len(evaluation.unexpected_hazard_tiles), 1)
        self.assertEqual(evaluation.unexpected_hazard_tiles[0].actual, 0x64)

    def test_one_legal_tile_from_wrong_phase_rejects(self) -> None:
        mutant = bytearray(self.contract.immutable_source)
        hazard_object = self.contract.object("connector_thrust")
        family = self.contract.family(hazard_object.family)
        correct = family.phase("P2")
        wrong = family.phase("P1")
        local_offset = next(
            index
            for index, (left, right) in enumerate(
                zip(correct.tiles, wrong.tiles, strict=True)
            )
            if left != right
        )
        local_row, local_column = divmod(local_offset, family.width)
        offset = (
            (hazard_object.row + local_row) * PACKED_WIDTH
            + hazard_object.column + local_column
        )
        mutant[offset] = wrong.tiles[local_offset]
        evaluation = evaluate_scene0b_hazard_tiles(
            mutant, contract=self.contract
        )
        connector = self.object_result(evaluation, "connector_thrust")
        self.assertFalse(evaluation.legal)
        self.assertIsNone(connector.matched_phase)
        self.assertEqual(connector.best_phase, "P2")
        self.assertEqual(connector.mismatch_count, 1)

    def test_spliced_row_from_another_phase_rejects(self) -> None:
        mutant = bytearray(self.contract.immutable_source)
        hazard_object = self.contract.object("south_standard")
        family = self.contract.family(hazard_object.family)
        wrong = family.phase("P1")
        row = 0
        start = (hazard_object.row + row) * PACKED_WIDTH
        mutant[start:start + family.width] = wrong.tiles[
            row * family.width:(row + 1) * family.width
        ]
        evaluation = evaluate_scene0b_hazard_tiles(
            mutant, contract=self.contract
        )
        south = self.object_result(evaluation, "south_standard")
        self.assertFalse(evaluation.legal)
        self.assertIsNone(south.matched_phase)

    def test_coherent_phase_from_wrong_family_rejects(self) -> None:
        mutant = bytearray(self.contract.immutable_source)
        wrong_family_phase = self.contract.family(
            "standard_cylinder"
        ).phase("P2")
        self.overwrite_object(
            mutant, "upper_cylinder", wrong_family_phase.tiles
        )
        evaluation = evaluate_scene0b_hazard_tiles(
            mutant, contract=self.contract
        )
        upper = self.object_result(evaluation, "upper_cylinder")
        self.assertFalse(evaluation.legal)
        self.assertIsNone(upper.matched_phase)
        self.assertTrue(
            all(
                result.exact
                for result in evaluation.objects
                if result.name != "upper_cylinder"
            )
        )

    def test_wrong_caller_source_cannot_become_a_baseline(self) -> None:
        source = bytearray(self.contract.immutable_source)
        source[-1] ^= 1
        with self.assertRaisesRegex(
            HazardTileContractError, "not the pinned independent"
        ):
            evaluate_scene0b_hazard_tiles(
                self.contract.immutable_source,
                source=source,
                contract=self.contract,
            )

    def test_assertion_includes_deterministic_failure_receipt(self) -> None:
        mutant = bytearray(self.contract.immutable_source)
        mutant[0] ^= 1
        with self.assertRaises(HazardTileAssertionError) as raised:
            assert_scene0b_hazard_tiles_legal(
                mutant, contract=self.contract
            )
        receipt = raised.exception.evaluation.to_receipt()
        self.assertFalse(receipt["legal"])
        self.assertEqual(receipt["fixture_sha256"], PINNED_FIXTURE_SHA256)
        self.assertGreater(receipt["mismatch_count"], 0)


if __name__ == "__main__":
    unittest.main()
