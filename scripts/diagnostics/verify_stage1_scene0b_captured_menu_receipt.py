#!/usr/bin/env python3
"""Bind live scene-$0B menu evidence to authenticated incident captures.

This command never launches an emulator. It authenticates the incompatible
corrupted-wall archive, the compatible operator state, and a candidate-native
closed state derived from that compatible state with SELECT-only input. It
then validates duplicate live menu roundtrips from both safe replay sources.
Static savestate inspection alone is therefore intentionally insufficient.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any, Mapping
import zlib

from PIL import Image

from stage1_scene0b_hazard_tile_oracle import (
    evaluate_scene0b_hazard_tiles,
    load_contract as load_hazard_tile_contract,
)


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
FIXTURE = (
    Path(__file__).with_name("fixtures")
    / "stage1_scene0b_capture_contract.json"
)
LIVE_VERIFIER = Path(__file__).with_name(
    "verify_stage1_scene0b_live_menu_roundtrip.py"
)
LIVE_PROBE = Path(__file__).with_name(
    "probe_stage1_scene0b_live_menu_roundtrip.lua"
)
VISUAL_ORACLE_FIXTURE = (
    Path(__file__).with_name("fixtures")
    / "stage1_scene0b_visual_oracle.json"
)
HAZARD_TILE_ORACLE = Path(__file__).with_name(
    "stage1_scene0b_hazard_tile_oracle.py"
)
HAZARD_TILE_ORACLE_FIXTURE = (
    Path(__file__).with_name("fixtures")
    / "stage1_scene0b_hazard_tile_oracle.json"
)
SINGLEFLIGHT = ROOT / "scripts" / "mgba-qt-singleflight"
SINGLEFLIGHT_IMPLEMENTATION = ROOT / "scripts" / "mgba_singleflight.py"
STATE_RETARGETER = Path(__file__).with_name("normalize_mgba_state_pc.py")
NATIVE_CAPTURE_GENERATOR = Path(__file__).with_name(
    "generate_stage1_scene0b_native_capture.py"
)
NATIVE_CAPTURE_PROBE = Path(__file__).with_name(
    "probe_generate_stage1_scene0b_native_capture.lua"
)

FIXTURE_SCHEMA = "penta-stage1-scene0b-capture-contract-v3"
LIVE_SCHEMA = "penta-stage1-scene0b-live-menu-roundtrip-v6"
BOUND_SCHEMA = "penta-stage1-scene0b-captured-menu-bound-v3"
NATIVE_CAPTURE_SCHEMA = "penta-stage1-scene0b-native-capture-v1"
LIVE_IMPLEMENTATION_READY = "IMPLEMENTED_REVIEWED"
GBAS_SIZE = 0x11800
GBAS_MAGIC = 0x00400003
GBAS_MODEL_OFFSET = 0x0008
GBAS_TITLE_OFFSET = 0x0010
GBAS_TITLE_SIZE = 16
GBAS_BOOT_REGISTER_OFFSET = 0x0350
GB_MODEL_CGB = 0x80
ROM_TITLE_OFFSET = 0x0134
CGB_COMPATIBLE_FLAG = 0x80
CGB_ONLY_FLAG = 0xC0
IO_OFFSET = 0x0300
HRAM_OFFSET = 0x0380
WRAM_OFFSET = 0x4400
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

ADDRESS_BY_NAME = {
    "D880": 0xD880,
    "DCDC": 0xDCDC,
    "DCDD": 0xDCDD,
    "FFBD": 0xFFBD,
    "FFC1": 0xFFC1,
    "FFE4": 0xFFE4,
    "FFBA": 0xFFBA,
    "FFBE": 0xFFBE,
    "LCDC": 0xFF40,
    "SCY": 0xFF42,
    "SCX": 0xFF43,
}
HAZARD_CAPTURE_LABELS = frozenset({
    "candidate-native-closed-after-operator-low-health",
    "operator-low-health-menu-loaded",
})

LIVE_CHECKS = frozenset({
    "archived incompatible wall capture remains exact and unnormalized",
    "compatible operator and candidate-native captures are exact scene-$0B states",
    "both safe captures have duplicate live replays",
    "every live replay starts from its exact authenticated capture",
    "every sampled route frame remains in scene $0B",
    "candidate-native closed capture opens, holds, and closes the native menu",
    "menu-loaded capture closes, reopens, holds, and closes the native menu",
    "menu transitions are native and injection-free",
    "captured-state, repair-settle, menu-entry, held, exit, and post-close frames exist",
    "immutable semantic attrs are clean in every post-repair phase",
    "wall and right-edge tiles are exact outside hazard animation",
    "Stage-1 background CRAM is exact in every post-repair phase",
    "final referenced background CHR is independently exact",
    "scene-$0B changes only the four reviewed terminal runtime attrs",
    "native semantic and all-frame state observations are complete",
    "operator screenshots retain both archived negative signatures",
    "live replay semantics are byte-deterministic",
})

LIVE_TOP_KEYS = frozenset({
    "schema", "status", "candidate", "candidate_sha256",
    "archived_incompatible_capture", "source_captures", "route_policy",
    "replays", "checks", "failures", "tool_identity",
})

REPLAY_KEYS = frozenset({
    "capture_label", "replay_index", "source_capture_path",
    "source_capture_sha256", "source_state_loaded", "initial_scene",
    "initial_menu_flag", "scene_values", "normalization",
    "normalization_writes", "fixture_writes", "scene_injection",
    "vram_injection_bytes", "retargeted_state_sha256",
    "retargeted_state", "retarget_changed_gbAs_offsets",
    "retargeted_state_rom_crc32", "retargeted_state_rom_identity",
    "native_menu_transitions",
    "process_teardown",
    "menu_open_events", "menu_close_events", "captured_state_frames",
    "repair_settle_frames", "menu_entry_frames", "menu_held_frames",
    "menu_exit_frames",
    "post_close_frames", "rendered_frames", "wall_edge_artifact_frames",
    "red_green_artifact_frames", "clear_tile_frames",
    "weird_edge_tile_frames", "visible_attr_mismatch_frames",
    "postsettle_wall_edge_artifact_frames",
    "postsettle_red_green_artifact_frames",
    "postsettle_weird_edge_tile_frames",
    "yellow_trail_frames", "gray_spike_frames",
    "runtime_lut_mutation_frames",
    "runtime_oracles", "launch_contract", "final_bg_chr",
    "postrepair_semantic_attr_mismatch_frames",
    "postsettle_semantic_attr_mismatch_frames",
    "semantic_checked_samples", "semantic_unreadable_samples",
    "postrepair_immutable_tile_mismatch_frames",
    "postsettle_immutable_tile_mismatch_frames",
    "late_tile_art_mismatch_frames",
    "immutable_tile_checked_samples", "immutable_tile_unreadable_samples",
    "postrepair_bg_cram_mismatch_frames",
    "cram_checked_samples", "cram_unreadable_samples",
    "final_physical_planes",
    "baseline_ready", "attr_checked_samples", "attr_unreadable_samples",
    "observation_restore_failures", "scene_violation_frames",
    "active_violation_frames", "oam_dma_unreadable_frames",
    "semantic_fingerprint_sha256", "state_trace", "rendered_manifest",
})

ARTIFACT_KEYS = frozenset({"path", "sha256"})
LAUNCH_ARTIFACT_KEYS = frozenset({"path", "sha256", "modified_at_ns"})
FINAL_BG_CHR_KEYS = frozenset({
    "path", "sha256", "bytes", "referenced_patterns", "bank0_patterns",
    "bank1_patterns", "illegal_bank1_patterns", "pattern_mismatches",
    "byte_mismatches", "first_mismatches",
})
LAUNCH_CONTRACT_KEYS = frozenset({
    "schema", "command", "cwd", "output_prefix", "capture_label",
    "replay_index", "startup_token_sha256", "launch_started_at_ns",
    "launch_completed_at_ns",
    "initial_menu", "frame_limit", "capture_frames",
    "repair_settle_frames", "menu_hold_frames", "post_close_frames",
    "launcher_sha256", "singleflight_implementation_sha256",
    "emulator_path", "emulator_sha256", "probe_sha256", "runtime_rom_path",
    "runtime_rom_sha256", "runtime_state_path", "runtime_state_sha256",
    "immutable_source_sha256", "immutable_stage1_tables_sha256",
    "canonical_bg_art_sha256", "canonical_hazard_bank1_art_sha256",
    "hazard_oracle_fixture_sha256", "hazard_phase_payload_sha256",
    "expected_bg_cram_sha256", "runtime_oracle_bundle_sha256",
    "startup", "ready", "core_ready", "config_ready", "trace_ready",
    "done", "report", "raw_trace", "emulator_log",
    "cache_audit", "cache_audit_ready", "startup_timeout_seconds",
    "ready_timeout_seconds", "core_timeout_seconds", "teardown_policy",
    "provisional_process_outcome", "validated_process_teardown",
})
LAUNCH_PROCESS_OUTCOME_KEYS = frozenset({
    "exact_child_terminated", "termination_method", "return_code",
    "completion_status",
})
PHYSICAL_PLANE_KEYS = frozenset({
    "path", "sha256", "metadata_path", "metadata_sha256", "frame",
    "sample", "lcdc", "scx", "scy", "scene", "room",
    "runtime_lut_sha256", "runtime_lut_matches_canonical",
    "source_sha256", "immutable_source_sha256",
    "exact_hazard_oracle",
    "source_immutable_mismatches_outside_hazard_visible",
    "source_immutable_mismatches_right_edge_visible", "maps",
})
PHYSICAL_MAP_KEYS = frozenset({
    "active", "tiles_sha256", "attrs_sha256", "exact_hazard_oracle",
    "hazard_positions",
    "hazard_animation_envelope", "semantic_mismatches_full_map",
    "semantic_mismatches_visible", "tile_source_mismatches_visible",
    "tile_source_mismatches_hazard_owned_visible",
    "tile_source_mismatches_outside_hazard_visible",
    "tile_source_mismatches_right_edge_visible",
    "tile_immutable_mismatches_visible",
    "tile_immutable_mismatches_outside_hazard_visible",
    "tile_immutable_mismatches_right_edge_visible",
    "first_visible_semantic_mismatches",
    "first_visible_tile_source_mismatches",
})
STAGE1_LUT_SHA256 = (
    "487c1443ddec16171cc0f2744b3fbbd013cdcac5e1d7fd8145fe46f277805734"
)
STAGE1_RELEASE_LUT_SHA256 = (
    "3b2d1224bb47c68263ff862f1a1c68d8b20f055fe2fcae0fa1028659d492961a"
)
STAGE1_COMPILED_TOOTH_LUT_SHA256 = (
    "22de0c9f11d8b8f4f050c4e62928e7ea300b1d7483fb9df1d65bb6eec6a0527f"
)
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
STAGE1_BG_PALETTE_OFFSET = 13 * 0x4000 + (0x6800 - 0x4000)
STAGE1_HAZARD_BG7_OFFSET = 13 * 0x4000 + (0x68C8 - 0x4000)
STAGE1_LOW_TILE_GFX_OFFSET = 0x1D000
STAGE1_HIGH_TILE_GFX_OFFSET = 0x1F000
STAGE1_BG_ART_SHA256 = (
    "aaf4f2596e74abc19f75cf094b432c5f1c504a6e34f7cf2622403f86fe562d95"
)
STAGE1_HAZARD_BANK1_ART_SHA256 = (
    "1fe86832f5508392a809a58e8d10e566f2fcafff553b07df914e614713dc7e4f"
)
STAGE1_HAZARD_PHASE_PAYLOAD_SHA256 = (
    "ca0e91b5df9c9ceceabd1a53d845efcc6562f8b4dc88fd3d705be53d1975e2b2"
)
STAGE1_BG_CRAM_SHA256 = (
    "2df58b72d35dbcd9de2a0144ae721ce248db1f73b0baa6f5eb29a755bb8c4952"
)
RUNTIME_ORACLE_BYTES = 0x1E40
FINAL_BG_CHR_BYTES = 0x4000
FRAME_LIMIT = 900
CAPTURE_FRAMES = 1
MENU_HOLD_FRAMES = 60
POST_CLOSE_FRAMES = 60
STARTUP_TIMEOUT_SECONDS = 8.0
READY_TIMEOUT_SECONDS = 5.0
CORE_TIMEOUT_SECONDS = 8.0
TEARDOWN_POLICY = {
    "probe_action": "stop-core-after-token-bound-receipts",
    "launcher_action": "terminate-exact-child-after-done-marker",
    "acceptance": (
        "natural-zero-or-verifier-owned-signal-after-token-bound-"
        "trace-report-done-validation"
    ),
}
PHYSICAL_PLANE_DUMP_SIZE = 0x1340
REPAIR_SETTLE_FRAMES = 24
PHYSICAL_METADATA_KEYS = frozenset({
    "frame", "sample", "phase", "lcdc", "scx", "scy", "scene", "room",
    "menu", "schema", "bytes",
})
STATE_TRACE_SCHEMA = "penta-stage1-scene0b-state-sample-v1"
STATE_TRACE_KEYS = frozenset({
    "schema", "sample", "frame", "phase", "scene", "room", "active",
    "menu", "lcdc", "scx", "scy", "attr_mismatches",
    "semantic_attr_mismatches", "immutable_tile_mismatches",
    "tile_publication_mismatches", "tile_phase_mismatches",
    "tile_plane_mismatches", "tile_source_mismatches",
    "tile_art_mismatches",
    "bg_cram_mismatches", "lut_mismatches",
})
STATE_TRACE_VALUE_KEYS = STATE_TRACE_KEYS - {"schema", "phase"}
TRACE_PHASES = (
    "captured", "repair_settle", "menu_entry", "menu_hold", "menu_exit",
    "post_close",
)
RAW_TRACE_FIELDS = (
    "sample", "frame", "phase", "scene", "room", "active", "menu",
    "lcdc", "scx", "scy", "attr_mismatches", "semantic_attr_mismatches",
    "immutable_tile_mismatches", "tile_publication_mismatches",
    "tile_phase_mismatches", "tile_plane_mismatches",
    "tile_source_mismatches", "tile_art_mismatches",
    "bg_cram_mismatches", "lut_mismatches",
    "startup_token",
)
RENDERED_MANIFEST_SCHEMA = "penta-stage1-scene0b-rendered-manifest-v1"
RENDERED_MANIFEST_KEYS = frozenset({
    "schema", "capture_label", "replay_index", "semantic_sha256", "frames",
})
RENDERED_FRAME_KEYS = frozenset({
    "sample", "phase", "path", "sha256", "rgb_sha256",
})
SCREEN_SIZE = (160, 144)
IMMUTABLE_WORLD_ROWS = 20
IMMUTABLE_WORLD_COLUMNS = 22
GBAX_SRAM_KIND = 2
GBAX_SRAM_SIZE = 0x2000
PROCESS_TEARDOWN_KEYS = frozenset({
    "policy", "completion_authenticated", "exact_child_terminated",
    "termination_method", "return_code",
})
TOOL_KEYS = frozenset({"path", "sha256"})
LIVE_TOOL_NAMES = frozenset({
    "live_verifier", "live_probe", "singleflight_launcher",
    "singleflight_implementation", "emulator_binary",
    "state_retargeter", "native_capture_generator", "native_capture_probe",
    "visual_oracle_fixture", "hazard_tile_oracle",
    "hazard_tile_oracle_fixture",
})
BOUND_TOOL_NAMES = frozenset({
    "receipt_binder", "capture_fixture", *LIVE_TOOL_NAMES,
})


class ContractError(RuntimeError):
    """The scene-$0B live evidence cannot qualify a candidate."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def sha256(path: Path) -> str:
    require(path.is_file(), f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_runtime_oracles(
    candidate: bytes,
    immutable_source: bytes,
    immutable_stage1_tables: bytes,
) -> bytes:
    """Independently rebuild the exact bytes parsed by the live child."""
    require(len(immutable_source) == 24 * 24,
            "runtime oracle immutable source has the wrong size")
    require(len(immutable_stage1_tables) == 0x800,
            "runtime oracle Stage-1 tables have the wrong size")
    bg_art = b"".join(
        candidate[offset:offset + 16]
        for tile in range(0x100)
        for offset in ((
            STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
            if tile < 0x80
            else STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
        ),)
    )
    require(len(bg_art) == 0x1000
            and sha256_bytes(bg_art) == STAGE1_BG_ART_SHA256,
            "candidate lacks the canonical Stage-1 background art")
    bank1_art = (
        candidate[0x1D640:0x1D6A0] + candidate[0x1D740:0x1D7A0]
    )
    require(len(bank1_art) == 192
            and sha256_bytes(bank1_art) == STAGE1_HAZARD_BANK1_ART_SHA256,
            "candidate lacks the canonical Stage-1 bank-one hazard art")
    contract = load_hazard_tile_contract()
    phases = b"".join(
        phase.tiles
        for hazard_object in contract.objects
        for phase in contract.family(hazard_object.family).phases
    )
    require(len(phases) == 768
            and sha256_bytes(phases) == STAGE1_HAZARD_PHASE_PAYLOAD_SHA256,
            "pinned Scene-$0B hazard phase payload changed")
    require(len(candidate) >= STAGE1_HAZARD_BG7_OFFSET + 8,
            "candidate is too small for the Stage-1 CRAM contract")
    cram = bytearray(candidate[
        STAGE1_BG_PALETTE_OFFSET:STAGE1_BG_PALETTE_OFFSET + 64
    ])
    require(len(cram) == 64,
            "candidate Stage-1 background palette table is incomplete")
    cram[7 * 8:8 * 8] = candidate[
        STAGE1_HAZARD_BG7_OFFSET:STAGE1_HAZARD_BG7_OFFSET + 8
    ]
    expected_cram = bytes(cram)
    require(sha256_bytes(expected_cram) == STAGE1_BG_CRAM_SHA256,
            "candidate lacks the reviewed canonical Stage-1 BG CRAM")
    payload = (
        immutable_source + immutable_stage1_tables + bg_art + bank1_art
        + phases + expected_cram
    )
    require(len(payload) == RUNTIME_ORACLE_BYTES,
            "runtime oracle bundle size changed")
    return payload


def load_object(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ContractError(f"{label} is not valid JSON: {error}") from error
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def exact_keys(value: Any, expected: frozenset[str], label: str) -> None:
    require(isinstance(value, dict), f"{label} is not an object")
    actual = set(value)
    require(
        actual == set(expected),
        f"{label} fields changed; missing={sorted(expected - actual)}, "
        f"unexpected={sorted(actual - expected)}",
    )


def state_byte(state: bytes, address: int) -> int:
    if 0xC000 <= address <= 0xDFFF:
        return state[WRAM_OFFSET + address - 0xC000]
    if 0xFF00 <= address <= 0xFF7F:
        return state[IO_OFFSET + address - 0xFF00]
    if 0xFF80 <= address <= 0xFFFF:
        return state[HRAM_OFFSET + address - 0xFF80]
    raise ContractError(f"unsupported serialized address ${address:04X}")


def gbas_payload(path: Path) -> bytes:
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"operator capture is not an mGBA PNG state: {path}")
    offset = 8
    states: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        require(offset + 12 <= len(data), f"truncated PNG chunk: {path}")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc = data[offset + 8 + length:offset + 12 + length]
        require(len(payload) == length and len(crc) == 4,
                f"truncated PNG payload: {path}")
        require(
            int.from_bytes(crc, "big")
            == (zlib.crc32(kind + payload) & 0xFFFFFFFF),
            f"bad PNG chunk CRC: {path}",
        )
        if kind == b"gbAs":
            try:
                states.append(zlib.decompress(payload))
            except zlib.error as error:
                raise ContractError(
                    f"malformed compressed gbAs payload: {path}"
                ) from error
        if kind == b"IEND":
            saw_iend = True
        offset += 12 + length
    require(offset == len(data) and saw_iend,
            f"operator capture PNG is incomplete: {path}")
    require(len(states) == 1,
            f"operator capture must contain exactly one gbAs payload: {path}")
    state = states[0]
    require(len(state) == GBAS_SIZE,
            f"operator capture gbAs size changed: {path}")
    require(int.from_bytes(state[:4], "little") == GBAS_MAGIC,
            f"operator capture gbAs version changed: {path}")
    return state


def gbax_sram_payload(path: Path) -> bytes:
    """Extract and authenticate mGBA's serialized 8 KiB cartridge SRAM."""
    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"operator capture is not an mGBA PNG state: {path}")
    offset = 8
    payloads: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        require(offset + 12 <= len(data), f"truncated PNG chunk: {path}")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        crc = data[offset + 8 + length:offset + 12 + length]
        require(len(payload) == length and len(crc) == 4,
                f"truncated PNG payload: {path}")
        require(
            int.from_bytes(crc, "big")
            == (zlib.crc32(kind + payload) & 0xFFFFFFFF),
            f"bad PNG chunk CRC: {path}",
        )
        if kind == b"gbAx":
            require(len(payload) >= 8,
                    f"malformed gbAx header: {path}")
            extension_kind = int.from_bytes(payload[:4], "little")
            declared_size = int.from_bytes(payload[4:8], "little")
            if extension_kind == GBAX_SRAM_KIND:
                require(declared_size == GBAX_SRAM_SIZE,
                        f"operator capture SRAM size changed: {path}")
                inflater = zlib.decompressobj()
                try:
                    expanded = inflater.decompress(payload[8:])
                    expanded += inflater.flush()
                except zlib.error as error:
                    raise ContractError(
                        f"malformed compressed gbAx SRAM payload: {path}"
                    ) from error
                require(inflater.eof and not inflater.unused_data
                        and not inflater.unconsumed_tail,
                        f"operator capture SRAM stream is not exact: {path}")
                require(len(expanded) == declared_size,
                        f"operator capture SRAM payload is incomplete: {path}")
                payloads.append(expanded)
        if kind == b"IEND":
            saw_iend = True
        offset += 12 + length
    require(offset == len(data) and saw_iend,
            f"operator capture PNG is incomplete: {path}")
    require(len(payloads) == 1,
            f"operator capture must contain exactly one SRAM gbAx: {path}")
    return payloads[0]


def immutable_source_from_capture(path: Path, state: bytes) -> bytes:
    """Rebuild the complete immutable C1A0 baseline from world/SRAM data.

    The publisher owns 20 rows and 22 columns of world-derived content.  Its
    remaining bottom/right padding is canonically zero, so no C1A0 byte is
    allowed to define its own expected value.
    """
    sram = gbax_sram_payload(path)

    def wram(address: int) -> int:
        require(0xC000 <= address <= 0xDFFF,
                f"world reconstruction address is invalid: ${address:04X}")
        return state[WRAM_OFFSET + address - 0xC000]

    camera_x = (wram(0xDC00) | (wram(0xDC01) << 8)) >> 5
    camera_y = (wram(0xDC02) | (wram(0xDC03) << 8)) >> 5
    final_grid_address = 0xC780 + (camera_y + 5) * 0x40 + camera_x + 5
    require(final_grid_address <= 0xDFFF,
            "operator world-grid window escapes serialized WRAM")

    reconstructed = bytearray(24 * 24)
    for room_row in range(6):
        for room_column in range(6):
            room_id = wram(
                0xC780 + (camera_y + room_row) * 0x40
                + camera_x + room_column
            )
            metatile_base = 0x400 + room_id * 4
            require(metatile_base + 4 <= len(sram),
                    "operator room metatile table escapes SRAM")
            for metatile_row in range(2):
                for metatile_column in range(2):
                    metatile = sram[
                        metatile_base + metatile_row * 2 + metatile_column
                    ]
                    tile_base = metatile * 4
                    require(tile_base + 4 <= len(sram),
                            "operator metatile tile table escapes SRAM")
                    for tile_row in range(2):
                        for tile_column in range(2):
                            output_row = room_row * 4 + metatile_row * 2 + tile_row
                            output_column = (
                                room_column * 4
                                + metatile_column * 2 + tile_column
                            )
                            reconstructed[output_row * 24 + output_column] = sram[
                                tile_base + tile_row * 2 + tile_column
                            ]

    for row in range(24):
        for column in range(24):
            if (
                row >= IMMUTABLE_WORLD_ROWS
                or column >= IMMUTABLE_WORLD_COLUMNS
            ):
                reconstructed[row * 24 + column] = 0

    start = WRAM_OFFSET + (0xC1A0 - 0xC000)
    captured = state[start:start + 24 * 24]
    require(len(captured) == 24 * 24,
            "operator capture has no complete C1A0 map")
    require(captured == reconstructed,
            "operator C1A0 differs from world/SRAM reconstruction")
    return bytes(reconstructed)


def load_capture_contract() -> dict[str, Any]:
    contract = load_object(FIXTURE, "scene-$0B capture fixture")
    require(contract.get("schema") == FIXTURE_SCHEMA,
            "wrong scene-$0B capture fixture schema")
    exact_keys(contract, frozenset({
        "schema", "archived_incompatible_capture", "captures", "live_policy",
    }),
               "scene-$0B capture fixture")
    captures = contract["captures"]
    require(isinstance(captures, list) and len(captures) == 2,
            "scene-$0B fixture must pin exactly two operator captures")
    policy = contract["live_policy"]
    exact_keys(policy, frozenset({
        "replays_per_capture", "minimum_captured_state_frames",
        "minimum_menu_held_frames", "minimum_menu_entry_frames",
        "minimum_menu_exit_frames", "minimum_post_close_frames",
        "scene_values", "normalization", "normalization_writes",
        "machine_state_writes", "identity_retarget_gbAs_offsets",
        "source_serialized_model", "source_identity_flag",
        "target_identity_flag", "vram_injection_bytes",
    }), "scene-$0B live policy")
    require(policy["normalization"] == "rom-identity-only"
            and policy["normalization_writes"] == 0
            and policy["machine_state_writes"] == 0
            and policy["identity_retarget_gbAs_offsets"]
            == [4, 5, 6, 7, 0x1F]
            and policy["source_serialized_model"] == "80"
            and policy["source_identity_flag"] == "80"
            and policy["target_identity_flag"] == "C0",
            "scene-$0B ROM-identity retarget policy changed")
    return contract


def capture_evidence(contract: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    labels: set[str] = set()
    for index, spec in enumerate(contract["captures"]):
        exact_keys(spec, frozenset({
            "label", "path", "sha256", "gbas_sha256",
            "serialized_rom_crc32", "serialized_model",
            "serialized_rom_identity", "serialized_boot_register",
            "state", "live_route", "hazard_oracle", "provenance",
        }), f"capture fixture {index}")
        label = spec["label"]
        require(isinstance(label, str) and label and label not in labels,
                f"capture fixture {index} label is invalid")
        labels.add(label)
        raw_path = Path(spec["path"])
        require(not raw_path.is_absolute(),
                f"capture fixture {label} path must be repo-relative")
        path = (ROOT / raw_path).resolve()
        require(path.is_relative_to(ROOT),
                f"capture fixture {label} escapes the repository")
        require(sha256(path) == spec["sha256"],
                f"operator capture hash changed: {label}")
        state = gbas_payload(path)
        require(hashlib.sha256(state).hexdigest() == spec["gbas_sha256"],
                f"operator capture gbAs hash changed: {label}")
        state_fields = spec["state"]
        exact_keys(state_fields, frozenset(ADDRESS_BY_NAME),
                   f"capture fixture {label} state")
        actual_state = {
            name: f"{state_byte(state, address):02X}"
            for name, address in ADDRESS_BY_NAME.items()
        }
        require(actual_state == state_fields,
                f"operator capture state bytes changed: {label}")
        require(actual_state["D880"] == "0B",
                f"operator capture is not scene $0B: {label}")
        serialized_crc = f"{int.from_bytes(state[4:8], 'little'):08x}"
        require(serialized_crc == spec["serialized_rom_crc32"],
                f"operator capture serialized ROM CRC changed: {label}")
        serialized_model = f"{state[GBAS_MODEL_OFFSET]:02X}"
        serialized_identity = state[
            GBAS_TITLE_OFFSET:GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE
        ].hex()
        serialized_boot_register = (
            f"{state[GBAS_BOOT_REGISTER_OFFSET]:02X}"
        )
        require(serialized_model == spec["serialized_model"] == "80",
                f"operator capture serialized model changed: {label}")
        require(serialized_identity == spec["serialized_rom_identity"],
                f"operator capture serialized ROM identity changed: {label}")
        require(serialized_identity.endswith("80"),
                f"operator capture is not CGB-compatible identity: {label}")
        require(serialized_boot_register
                == spec["serialized_boot_register"]
                and state[GBAS_BOOT_REGISTER_OFFSET] != 0xFF,
                f"operator capture is not post-BIOS: {label}")
        require(spec["hazard_oracle"] == "scene0b-four-object",
                f"capture fixture {label} hazard oracle changed")
        provenance = spec["provenance"]
        exact_keys(provenance, frozenset({
            "kind", "receipt", "receipt_sha256",
        }), f"capture fixture {label} provenance")
        if provenance["kind"] == "operator-capture":
            require(provenance["receipt"] is None
                    and provenance["receipt_sha256"] is None,
                    f"operator capture {label} has derived provenance")
        elif provenance["kind"] == "candidate-native-select-close":
            require(isinstance(provenance["receipt"], str)
                    and provenance["receipt"]
                    and isinstance(provenance["receipt_sha256"], str)
                    and SHA256_RE.fullmatch(provenance["receipt_sha256"]),
                    f"derived capture {label} has malformed provenance")
        else:
            require(False, f"capture fixture {label} provenance changed")
        evidence.append({
            "label": label,
            "path": str(path),
            "sha256": spec["sha256"],
            "gbas_sha256": spec["gbas_sha256"],
            "serialized_rom_crc32": serialized_crc,
            "serialized_model": serialized_model,
            "serialized_rom_identity": serialized_identity,
            "serialized_boot_register": serialized_boot_register,
            "captured_state": actual_state,
            "live_route": spec["live_route"],
            "hazard_oracle": spec["hazard_oracle"],
            "provenance": provenance,
        })
    require({item["captured_state"]["FFE4"] for item in evidence}
            == {"00", "01"},
            "safe captures must include menu-closed and menu-loaded states")
    require({item["label"] for item in evidence} == {
        "candidate-native-closed-after-operator-low-health",
        "operator-low-health-menu-loaded",
    }, "scene-$0B safe capture labels changed")
    return evidence


def archived_incompatible_evidence(
    contract: Mapping[str, Any], candidate: Path, candidate_sha256: str,
) -> dict[str, Any]:
    spec = contract["archived_incompatible_capture"]
    exact_keys(spec, frozenset({
        "label", "path", "sha256", "gbas_sha256",
        "serialized_rom_crc32", "serialized_model",
        "serialized_rom_identity", "serialized_boot_register",
        "state", "live_route", "incompatibility",
    }), "archived incompatible scene-$0B capture")
    require(spec["label"] == "operator-corrupted-walls",
            "archived incompatible capture label changed")
    raw_path = Path(spec["path"])
    require(not raw_path.is_absolute(),
            "archived incompatible capture path must be repo-relative")
    path = (ROOT / raw_path).resolve()
    require(path.is_relative_to(ROOT) and sha256(path) == spec["sha256"],
            "archived incompatible wall capture hash changed")
    state = gbas_payload(path)
    require(sha256_bytes(state) == spec["gbas_sha256"],
            "archived incompatible wall gbAs hash changed")
    actual_state = {
        name: f"{state_byte(state, address):02X}"
        for name, address in ADDRESS_BY_NAME.items()
    }
    require(actual_state == spec["state"]
            and actual_state["D880"] == "0B"
            and actual_state["FFE4"] == "00",
            "archived incompatible wall state bytes changed")
    require(f"{int.from_bytes(state[4:8], 'little'):08x}"
            == spec["serialized_rom_crc32"] == "ca97c15e",
            "archived incompatible wall ROM CRC changed")
    require(f"{state[GBAS_MODEL_OFFSET]:02X}"
            == spec["serialized_model"] == "80"
            and state[GBAS_TITLE_OFFSET:
                      GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE].hex()
            == spec["serialized_rom_identity"]
            and spec["serialized_rom_identity"].endswith("80")
            and f"{state[GBAS_BOOT_REGISTER_OFFSET]:02X}"
            == spec["serialized_boot_register"] == "01",
            "archived incompatible wall identity changed")
    incompatibility = spec["incompatibility"]
    exact_keys(incompatibility, frozenset({
        "candidate_sha256", "saved_irq_return", "candidate_window_offset",
        "candidate_window_bytes", "policy", "live_replays",
    }), "archived incompatible wall resume policy")
    require(candidate_sha256 == sha256(candidate)
            == incompatibility["candidate_sha256"],
            "archived wall incompatibility names another candidate")
    require(incompatibility == {
        "candidate_sha256": candidate_sha256,
        "saved_irq_return": "13C2",
        "candidate_window_offset": "13C0",
        "candidate_window_bytes": "F5F0BAB720",
        "policy": (
            "archive-exact-and-reject-live-resume-without-"
            "cpu-stack-normalization"
        ),
        "live_replays": 0,
    }, "archived wall incompatibility contract changed")
    require(candidate.read_bytes()[0x13C0:0x13C5]
            == bytes.fromhex(incompatibility["candidate_window_bytes"]),
            "candidate no longer has the reviewed archived-wall conflict")
    return {
        "label": spec["label"],
        "path": str(path),
        "sha256": spec["sha256"],
        "gbas_sha256": spec["gbas_sha256"],
        "serialized_rom_crc32": spec["serialized_rom_crc32"],
        "serialized_model": spec["serialized_model"],
        "serialized_rom_identity": spec["serialized_rom_identity"],
        "serialized_boot_register": spec["serialized_boot_register"],
        "captured_state": actual_state,
        "live_route": spec["live_route"],
        "incompatibility": incompatibility,
    }


def identity(paths: Mapping[str, Path]) -> dict[str, dict[str, str]]:
    return {
        name: {"path": str(path.resolve()), "sha256": sha256(path.resolve())}
        for name, path in paths.items()
    }


def default_qt_emulator() -> Path:
    """Resolve the same override-free Qt binary as the checked guard."""
    for candidate in (
        Path("/home/struktured/bin/mgba-qt"),
        Path("/usr/bin/mgba-qt"),
        Path("/usr/local/bin/mgba-qt"),
    ):
        if candidate.is_file():
            return candidate.resolve()
    raise ContractError("default checked Qt emulator executable is missing")


def expected_live_tool_identity() -> dict[str, dict[str, str]]:
    return identity({
        "live_verifier": LIVE_VERIFIER,
        "live_probe": LIVE_PROBE,
        "singleflight_launcher": SINGLEFLIGHT,
        "singleflight_implementation": SINGLEFLIGHT_IMPLEMENTATION,
        "emulator_binary": default_qt_emulator(),
        "state_retargeter": STATE_RETARGETER,
        "native_capture_generator": NATIVE_CAPTURE_GENERATOR,
        "native_capture_probe": NATIVE_CAPTURE_PROBE,
        "visual_oracle_fixture": VISUAL_ORACLE_FIXTURE,
        "hazard_tile_oracle": HAZARD_TILE_ORACLE,
        "hazard_tile_oracle_fixture": HAZARD_TILE_ORACLE_FIXTURE,
    })


def expected_bound_tool_identity() -> dict[str, dict[str, str]]:
    return identity({
        "receipt_binder": SELF,
        "capture_fixture": FIXTURE,
        "live_verifier": LIVE_VERIFIER,
        "live_probe": LIVE_PROBE,
        "singleflight_launcher": SINGLEFLIGHT,
        "singleflight_implementation": SINGLEFLIGHT_IMPLEMENTATION,
        "emulator_binary": default_qt_emulator(),
        "state_retargeter": STATE_RETARGETER,
        "native_capture_generator": NATIVE_CAPTURE_GENERATOR,
        "native_capture_probe": NATIVE_CAPTURE_PROBE,
        "visual_oracle_fixture": VISUAL_ORACLE_FIXTURE,
        "hazard_tile_oracle": HAZARD_TILE_ORACLE,
        "hazard_tile_oracle_fixture": HAZARD_TILE_ORACLE_FIXTURE,
    })


def validate_native_capture_provenance(
    captures: list[dict[str, Any]], candidate: Path, candidate_sha256: str,
) -> dict[str, Any]:
    by_label = {capture["label"]: capture for capture in captures}
    derived = by_label.get(
        "candidate-native-closed-after-operator-low-health"
    )
    source = by_label.get("operator-low-health-menu-loaded")
    require(derived is not None and source is not None,
            "native-capture provenance lacks its derived/source pair")
    provenance = derived["provenance"]
    require(provenance["kind"] == "candidate-native-select-close",
            "closed capture lacks native SELECT provenance")
    raw_receipt_path = Path(provenance["receipt"])
    require(not raw_receipt_path.is_absolute(),
            "native-capture provenance receipt must be repo-relative")
    receipt_path = (ROOT / raw_receipt_path).resolve()
    require(receipt_path.is_relative_to(ROOT),
            "native-capture provenance receipt escapes the repository")
    require(sha256(receipt_path) == provenance["receipt_sha256"],
            "native-capture provenance receipt hash changed")
    receipt = load_object(receipt_path, "native scene-$0B capture receipt")
    exact_keys(receipt, frozenset({
        "schema", "status", "candidate", "candidate_sha256",
        "candidate_crc32", "candidate_rom_identity", "source_capture",
        "identity_retarget", "native_route", "generated_candidate_state",
        "exported_legacy_identity_state", "screenshot", "probe_report",
        "launch", "probe_contract", "tool_identity", "checks",
        "process_check", "failures",
    }), "native scene-$0B capture receipt")
    require(receipt["schema"] == NATIVE_CAPTURE_SCHEMA
            and receipt["status"] == "PASS"
            and receipt["failures"] == [],
            "native scene-$0B capture receipt is not zero-failure PASS")
    candidate = candidate.resolve()
    require(Path(receipt["candidate"]).resolve() == candidate
            and receipt["candidate_sha256"] == candidate_sha256
            and sha256(candidate) == candidate_sha256,
            "native scene-$0B capture receipt targets another candidate")
    candidate_bytes = candidate.read_bytes()
    candidate_crc32 = f"{zlib.crc32(candidate_bytes) & 0xFFFFFFFF:08x}"
    candidate_identity = candidate_bytes[
        ROM_TITLE_OFFSET:ROM_TITLE_OFFSET + GBAS_TITLE_SIZE
    ].hex()
    require(receipt["candidate_crc32"] == candidate_crc32
            and receipt["candidate_rom_identity"] == candidate_identity
            and candidate_identity.endswith("c0"),
            "native scene-$0B receipt candidate identity changed")

    source_record = receipt["source_capture"]
    exact_keys(source_record, frozenset({
        "label", "path", "sha256", "gbas_sha256",
        "serialized_rom_crc32", "serialized_rom_identity", "state",
    }), "native scene-$0B source capture")
    require(source_record == {
        "label": source["label"],
        "path": source["path"],
        "sha256": source["sha256"],
        "gbas_sha256": source["gbas_sha256"],
        "serialized_rom_crc32": source["serialized_rom_crc32"],
        "serialized_rom_identity": source["serialized_rom_identity"],
        "state": source["captured_state"],
    }, "native scene-$0B source capture differs from its fixture")
    source_payload = gbas_payload(Path(source["path"]))

    retarget = receipt["identity_retarget"]
    exact_keys(retarget, frozenset({
        "path", "sha256", "gbas_sha256", "changed_gbAs_offsets",
        "normalization_writes", "machine_state_writes",
    }), "native scene-$0B identity retarget")
    retarget_path = Path(retarget["path"]).resolve()
    require(sha256(retarget_path) == retarget["sha256"],
            "native scene-$0B retargeted state hash changed")
    retarget_payload = gbas_payload(retarget_path)
    require(sha256_bytes(retarget_payload) == retarget["gbas_sha256"],
            "native scene-$0B retargeted gbAs hash changed")
    source_to_retarget = [
        offset for offset, pair in enumerate(zip(
            source_payload, retarget_payload, strict=True
        )) if pair[0] != pair[1]
    ]
    require(source_to_retarget == retarget["changed_gbAs_offsets"]
            == [4, 5, 6, 7, 0x1F]
            and retarget["normalization_writes"] == 0
            and retarget["machine_state_writes"] == 0,
            "native scene-$0B retarget changes machine state")

    route = receipt["native_route"]
    exact_keys(route, frozenset({
        "input", "initial_menu", "final_menu", "scene_values",
        "select_frames", "closed_settle_frames", "menu_open_events",
        "menu_close_events", "deferred_wram_frames", "gameplay_writes",
        "fixture_writes", "vram_injection_bytes",
    }), "native scene-$0B derivation route")
    require(route["input"] == "SELECT-only"
            and route["initial_menu"] == "01"
            and route["final_menu"] == "00"
            and route["scene_values"] == ["0B"]
            and isinstance(route["select_frames"], int)
            and route["select_frames"] > 0
            and isinstance(route["closed_settle_frames"], int)
            and route["closed_settle_frames"] >= 60
            and route["menu_open_events"] == 0
            and route["menu_close_events"] == 1
            and isinstance(route["deferred_wram_frames"], int)
            and route["deferred_wram_frames"] >= 0
            and route["gameplay_writes"] == 0
            and route["fixture_writes"] == 0
            and route["vram_injection_bytes"] == 0,
            "native scene-$0B derivation route changed")

    generated = receipt["generated_candidate_state"]
    exact_keys(generated, frozenset({
        "path", "sha256", "gbas_sha256", "serialized_rom_crc32",
        "serialized_rom_identity", "state",
    }), "native scene-$0B generated candidate state")
    generated_path = Path(generated["path"]).resolve()
    require(sha256(generated_path) == generated["sha256"],
            "native scene-$0B generated state hash changed")
    generated_payload = gbas_payload(generated_path)
    require(sha256_bytes(generated_payload) == generated["gbas_sha256"]
            and generated["serialized_rom_crc32"] == candidate_crc32
            and generated["serialized_rom_identity"] == candidate_identity
            and generated["state"] == derived["captured_state"],
            "native scene-$0B generated candidate state changed")

    exported = receipt["exported_legacy_identity_state"]
    exact_keys(exported, frozenset({
        "path", "sha256", "gbas_sha256", "serialized_rom_crc32",
        "serialized_rom_identity", "state", "changed_gbAs_offsets",
        "machine_state_writes",
    }), "native scene-$0B exported legacy-identity state")
    exported_path = Path(exported["path"]).resolve()
    require(exported_path == Path(derived["path"]).resolve()
            and exported["sha256"] == derived["sha256"]
            and exported["gbas_sha256"] == derived["gbas_sha256"]
            and sha256(exported_path) == exported["sha256"],
            "native scene-$0B exported state differs from fixture")
    exported_payload = gbas_payload(exported_path)
    require(sha256_bytes(exported_payload) == exported["gbas_sha256"]
            and exported["serialized_rom_crc32"]
            == source["serialized_rom_crc32"]
            and exported["serialized_rom_identity"]
            == source["serialized_rom_identity"]
            and exported["state"] == generated["state"]
            == derived["captured_state"]
            and exported["changed_gbAs_offsets"] == [4, 5, 6, 7, 0x1F]
            and exported["machine_state_writes"] == 0,
            "native scene-$0B legacy export changed machine state")
    generated_to_exported = [
        offset for offset, pair in enumerate(zip(
            generated_payload, exported_payload, strict=True
        )) if pair[0] != pair[1]
    ]
    require(generated_to_exported == exported["changed_gbAs_offsets"],
            "native scene-$0B legacy export delta changed")

    for key, label in (("screenshot", "screenshot"),
                       ("probe_report", "probe report")):
        artifact = receipt[key]
        required_keys = {"path", "sha256"}
        if key == "probe_report":
            required_keys.add("values")
        exact_keys(artifact, frozenset(required_keys),
                   f"native scene-$0B {label}")
        require(sha256(Path(artifact["path"]).resolve())
                == artifact["sha256"],
                f"native scene-$0B {label} hash changed")

    report_values = receipt["probe_report"]["values"]
    require(report_values["status"] == "pass"
            and report_values["reason"] == "candidate-native-select-close"
            and report_values["scene"] == "0B"
            and report_values["active"] == "01"
            and report_values["menu"] == "00"
            and int(report_values["select_frames"])
            == route["select_frames"]
            and int(report_values["closed_settle_frames"])
            == route["closed_settle_frames"]
            and int(report_values["deferred_wram_frames"])
            == route["deferred_wram_frames"],
            "native scene-$0B probe report differs from route")

    launch = receipt["launch"]
    exact_keys(launch, frozenset({
        "command", "cwd", "startup_token_sha256", "started_at_ns",
        "completed_at_ns", "completion_authenticated",
        "exact_child_terminated", "termination_method", "return_code",
    }), "native scene-$0B generation launch")
    require(isinstance(launch["started_at_ns"], int)
            and isinstance(launch["completed_at_ns"], int)
            and launch["started_at_ns"] < launch["completed_at_ns"]
            and launch["completion_authenticated"] is True
            and launch["termination_method"]
            in {"already-exited", "SIGTERM", "SIGKILL-after-SIGTERM-timeout"}
            and launch["return_code"] in {0, -15, -9}
            and sha256_bytes(report_values["startup_token"].encode())
            == launch["startup_token_sha256"],
            "native scene-$0B launch authentication changed")
    command = launch["command"]
    require(isinstance(command, list) and len(command) >= 4
            and Path(command[0]).resolve() == SINGLEFLIGHT.resolve()
            and "--script" in command
            and Path(command[command.index("--script") + 1]).resolve()
            == NATIVE_CAPTURE_PROBE.resolve()
            and Path(command[-1]).resolve().is_file()
            and sha256(Path(command[-1]).resolve()) == candidate_sha256,
            "native scene-$0B generation command is not exact single-flight")
    for artifact_path in (
        generated_path, Path(receipt["screenshot"]["path"]).resolve(),
        Path(receipt["probe_report"]["path"]).resolve(),
    ):
        require(launch["started_at_ns"] <= artifact_path.stat().st_mtime_ns
                <= launch["completed_at_ns"],
                "native scene-$0B artifact is outside its launch window")

    expected_probe_contract = {
        "probe_sha256": sha256(NATIVE_CAPTURE_PROBE),
        "native_select_only": True,
        "source_state_loads": 1,
        "derived_state_saves": 1,
        "gameplay_writes": 0,
        "fixture_writes": 0,
        "vram_injection_bytes": 0,
    }
    require(receipt["probe_contract"] == expected_probe_contract,
            "native scene-$0B probe contract changed")
    expected_generator_tools = identity({
        "generator": NATIVE_CAPTURE_GENERATOR,
        "probe": NATIVE_CAPTURE_PROBE,
        "singleflight_launcher": SINGLEFLIGHT,
        "singleflight_implementation": SINGLEFLIGHT_IMPLEMENTATION,
        "emulator_binary": default_qt_emulator(),
        "state_retargeter": STATE_RETARGETER,
    })
    validate_tool_identity(
        receipt["tool_identity"], expected_generator_tools,
        "native scene-$0B generator tool identity",
    )
    expected_checks = {
        "exact compatible operator capture is authenticated",
        "source retarget changes identity metadata only",
        "native SELECT closes the menu without machine writes",
        "candidate-native state remains active scene $0B",
        "closed menu remains settled for sixty frames",
        "legacy export changes identity metadata only",
    }
    require(set(receipt["checks"]) == expected_checks
            and all(receipt["checks"].values()),
            "native scene-$0B derivation checks changed")
    require(receipt["process_check"] == {
        "return_code": 0,
        "output": "No mGBA emulator processes are running.",
    }, "native scene-$0B generation left an emulator process")
    return {
        "receipt": str(receipt_path),
        "receipt_sha256": sha256(receipt_path),
        "generated_candidate_state_sha256": generated["sha256"],
        "exported_capture_sha256": exported["sha256"],
        "source_capture_sha256": source["sha256"],
        "native_select_only": True,
        "machine_state_writes": 0,
    }


def live_producer_implementation_status() -> str:
    """Read the producer's reviewed-status literal without executing it."""
    try:
        tree = ast.parse(LIVE_VERIFIER.read_text(), filename=str(LIVE_VERIFIER))
    except (OSError, SyntaxError) as error:
        raise ContractError(
            f"cannot inspect live scene-$0B producer status: {error}"
        ) from error
    values: list[str] = []
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if (
            isinstance(target, ast.Name)
            and target.id == "IMPLEMENTATION_STATUS"
            and value is not None
        ):
            try:
                literal = ast.literal_eval(value)
            except (ValueError, TypeError) as error:
                raise ContractError(
                    "live scene-$0B producer status is not a literal"
                ) from error
            require(isinstance(literal, str),
                    "live scene-$0B producer status is not text")
            values.append(literal)
    require(len(values) == 1,
            "live scene-$0B producer must declare exactly one implementation status")
    return values[0]


def audit_live_probe_bank_contract(source: str | None = None) -> dict[str, Any]:
    """Independently pin the live probe's physical VRAM-bank observations."""
    if source is None:
        try:
            source = LIVE_PROBE.read_text()
        except (OSError, UnicodeError) as error:
            raise ContractError(
                f"cannot inspect live scene-$0B probe: {error}"
            ) from error
    required = (
        "local function read_vbk1(offsets)",
        "if not vram_cpu_readable() then return nil end",
        "local old_vbk = emu:read8(0xFF4F)",
        "values[index] = emu:read8(0x8000 + offset)",
        "if emu:read8(0xFF4F) ~= old_vbk then",
        "local attrs = read_vbk1(offsets)",
        "local bank1_chr = read_vbk1(chr_offsets)",
        "observed_bank1 = read_vbk1(pattern_offsets)",
        "chr_handle:write(byte_blob(bank0_chr))",
        "chr_handle:write(byte_blob(bank1_chr))",
    )
    for snippet in required:
        require(snippet in source,
                f"live scene-$0B probe lacks bank contract: {snippet}")
    raw_reads = re.findall(r"raw_vram:read8\(([^)\n]+)\)", source)
    require(raw_reads == ["offset", "offset", "address + byte"],
            "live scene-$0B raw VRAM reads are not bank-zero-only")
    require(source.count("read_vbk1(") == 4,
            "live scene-$0B bank-one consumers bypass the VBK helper")
    require(source.count("emu:read8(0x8000 + offset)") == 1,
            "live scene-$0B bank-one CPU-window read is not unique")
    bank_dispatch = (
        "if bank == 0 then\n"
        "              observed = raw_vram:read8(address + byte)\n"
        "            else\n"
        "              observed = observed_bank1[byte + 1]\n"
        "            end"
    )
    require(bank_dispatch in source,
            "live scene-$0B CHR grader does not dispatch bank one to VBK data")
    start = source.index("local function read_vbk1(offsets)")
    end = source.index("\nlocal function read_planes(offsets)", start)
    helper = source[start:end]
    require("raw_vram" not in helper,
            "live scene-$0B VBK helper aliases the raw bank-zero domain")
    writes = re.findall(r"emu:write8\(([^\n]+)\)", source)
    require(
        len(writes) == 4
        and writes[0].startswith("0xFF4F, 1")
        and writes[1].startswith("0xFF4F, old_vbk")
        and writes[2].startswith("0xFF68, index")
        and writes[3].startswith("0xFF68, old_index"),
        "live scene-$0B probe writes outside selector-only observation pairs",
    )
    require(
        source.index("chr_handle:write(byte_blob(bank0_chr))")
        < source.index("chr_handle:write(byte_blob(bank1_chr))"),
        "live scene-$0B final CHR bank order changed",
    )
    return {
        "raw_vram_bank0_only": True,
        "bank1_cpu_window_only": True,
        "final_chr_bank_order": [0, 1],
        "observation_only_write_sites": 4,
    }


def require_live_producer_implemented() -> None:
    status = live_producer_implementation_status()
    require(
        status == LIVE_IMPLEMENTATION_READY,
        "live scene-$0B captured-state/menu producer is not implemented and "
        f"reviewed (status {status!r})",
    )
    audit_live_probe_bank_contract()


def validate_artifact(
    value: Any, receipt_root: Path, label: str
) -> dict[str, str]:
    exact_keys(value, ARTIFACT_KEYS, label)
    raw = value["path"]
    require(isinstance(raw, str) and raw, f"{label} path is missing")
    path = Path(raw).resolve()
    require(path.is_relative_to(receipt_root),
            f"{label} is outside the live receipt directory")
    require(SHA256_RE.fullmatch(value["sha256"] or "") is not None,
            f"{label} hash is malformed")
    require(sha256(path) == value["sha256"], f"{label} hash differs")
    return {"path": str(path), "sha256": value["sha256"]}


def validate_launch_artifact(
    value: Any,
    receipt_root: Path,
    expected_path: Path,
    started_at_ns: int,
    completed_at_ns: int,
    label: str,
) -> dict[str, Any]:
    """Authenticate one child-created file and its launch-window timestamp."""
    exact_keys(value, LAUNCH_ARTIFACT_KEYS, label)
    artifact = validate_artifact(
        {"path": value["path"], "sha256": value["sha256"]},
        receipt_root,
        label,
    )
    path = Path(artifact["path"])
    require(path == expected_path.resolve(), f"{label} path changed")
    require(type(value["modified_at_ns"]) is int,
            f"{label} timestamp is not an integer")
    require(value["modified_at_ns"] == path.stat().st_mtime_ns,
            f"{label} timestamp differs from the bound file")
    require(started_at_ns <= value["modified_at_ns"] <= completed_at_ns,
            f"{label} is outside this replay's launch window")
    return {**artifact, "modified_at_ns": value["modified_at_ns"]}


def parse_token_bound_raw_trace(
    path: Path, startup_token: str, label: str,
) -> list[dict[str, Any]]:
    """Parse the child TSV independently and authenticate every row token."""
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError) as error:
        raise ContractError(f"{label} is unreadable: {error}") from error
    require(lines, f"{label} is empty")
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        values = line.split("\t")
        require(len(values) == len(RAW_TRACE_FIELDS),
                f"{label} line {number} has the wrong field count")
        row: dict[str, Any] = dict(zip(
            RAW_TRACE_FIELDS, values, strict=True
        ))
        require(row.pop("startup_token") == startup_token,
                f"{label} token differs on line {number}")
        for name in RAW_TRACE_FIELDS:
            if name in {"phase", "startup_token"}:
                continue
            base = 16 if name in {
                "scene", "room", "active", "menu", "lcdc", "scx", "scy"
            } else 10
            try:
                row[name] = int(row[name], base)
            except ValueError as error:
                raise ContractError(
                    f"{label} line {number} has invalid {name}"
                ) from error
        require(row["sample"] == number,
                f"{label} sample sequence breaks at line {number}")
        rows.append(row)
    return rows


def require_causal_launch_artifact_order(
    artifacts: Mapping[str, Mapping[str, Any]],
) -> None:
    ordered_names = (
        "startup", "ready", "core_ready", "config_ready", "trace_ready",
        "raw_trace", "report", "done",
    )
    require(all(
        artifacts[left]["modified_at_ns"]
        <= artifacts[right]["modified_at_ns"]
        for left, right in zip(ordered_names, ordered_names[1:])
    ), "live replay launch artifact ordering is non-causal")


def register_replay_freshness(
    replay_root: Path,
    startup_token_sha256: str,
    replay_roots: set[Path],
    startup_token_hashes: set[str],
    label: str,
) -> None:
    """Reject equal, nested, or token-aliased replay evidence domains."""
    require(all(
        not replay_root.is_relative_to(other)
        and not other.is_relative_to(replay_root)
        for other in replay_roots
    ), f"{label} overlaps another replay root")
    require(startup_token_sha256 not in startup_token_hashes,
            f"{label} reuses another startup token")
    replay_roots.add(replay_root)
    startup_token_hashes.add(startup_token_sha256)


def parse_key_values(path: Path, label: str) -> dict[str, str]:
    """Parse an authenticated key/value sidecar without trusting its claims."""
    result: dict[str, str] = {}
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError) as error:
        raise ContractError(f"{label} is unreadable: {error}") from error
    require(lines, f"{label} is empty")
    for number, line in enumerate(lines, 1):
        require(line and "=" in line,
                f"{label} line {number} is malformed")
        key, value = line.split("=", 1)
        require(key and key not in result,
                f"{label} repeats or omits a key on line {number}")
        result[key] = value
    return result


def _metadata_integer(
    metadata: Mapping[str, str], key: str, base: int, label: str,
) -> int:
    try:
        value = int(metadata[key], base)
    except (KeyError, ValueError) as error:
        raise ContractError(f"{label} has malformed {key}") from error
    return value


def _stage1_tooth(tile: int) -> bool:
    return 0x64 <= (tile & 0xEF) < 0x6A


def _stage1_hazard_positions(tiles: bytes) -> set[int]:
    """Recompute the reviewed geometry scanner solely from physical tiles."""
    require(len(tiles) == 0x400, "physical BG tile map has wrong size")
    positions: set[int] = set()
    for row in range(32):
        start = row * 32
        values = tiles[start:start + 32]
        columns: range | tuple[int, ...] = ()
        if _stage1_tooth(values[0]) or _stage1_tooth(values[1]):
            width = 11 if _stage1_tooth(values[10]) else (
                10 if _stage1_tooth(values[9]) else 9
            )
            columns = range(width)
        elif values[4] == 0x6A:
            columns = range(5, 15)
        elif _stage1_tooth(values[4]) or _stage1_tooth(values[5]):
            columns = range(4, 13)
        elif _stage1_tooth(values[6]):
            columns = tuple(
                column for column in range(4, 14)
                if _stage1_tooth(values[column])
            )
        positions.update(start + column for column in columns)
    return positions


def _stage1_semantic_attrs(
    tiles: bytes,
    canonical_lut: bytes,
    room: int,
    immutable_hazard_positions: set[int],
) -> bytes:
    require(len(canonical_lut) == 0x100,
            "canonical Stage-1 LUT has wrong size")
    expected = bytearray(canonical_lut[tile] & 0x07 for tile in tiles)
    if room == 0x01:
        for offset, tile in enumerate(tiles):
            if tile in {0x24, 0x27, 0x30, 0x33}:
                expected[offset] = 0x06
    for offset in immutable_hazard_positions:
        if _stage1_tooth(tiles[offset]):
            expected[offset] = 0x0F
    return bytes(expected)


def recompute_physical_planes(
    dump_path: Path,
    metadata_path: Path,
    canonical_lut: bytes,
    immutable_source: bytes,
    capture_label: str = "",
) -> dict[str, Any]:
    """Rebuild every physical-plane claim from the bound binary artifacts."""
    try:
        payload = dump_path.read_bytes()
    except OSError as error:
        raise ContractError(
            f"physical-plane dump is unreadable: {error}"
        ) from error
    require(len(payload) == PHYSICAL_PLANE_DUMP_SIZE,
            f"physical-plane dump size changed: {len(payload)}")
    metadata = parse_key_values(metadata_path, "physical-plane metadata")
    require(set(metadata) == set(PHYSICAL_METADATA_KEYS),
            "physical-plane metadata fields changed")
    require(metadata["schema"] == "maps-v1"
            and metadata["phase"] == "post_close",
            "physical-plane metadata contract changed")
    frame = _metadata_integer(metadata, "frame", 10, "physical-plane metadata")
    sample = _metadata_integer(
        metadata, "sample", 10, "physical-plane metadata"
    )
    lcdc = _metadata_integer(metadata, "lcdc", 16, "physical-plane metadata")
    scx = _metadata_integer(metadata, "scx", 16, "physical-plane metadata")
    scy = _metadata_integer(metadata, "scy", 16, "physical-plane metadata")
    scene = _metadata_integer(metadata, "scene", 16, "physical-plane metadata")
    room = _metadata_integer(metadata, "room", 16, "physical-plane metadata")
    menu = _metadata_integer(metadata, "menu", 16, "physical-plane metadata")
    byte_count = _metadata_integer(
        metadata, "bytes", 10, "physical-plane metadata"
    )
    require(frame >= 1 and sample >= 1,
            "physical-plane metadata has invalid frame/sample")
    require(all(0 <= value <= 0xFF for value in (
        lcdc, scx, scy, scene, room, menu,
    )), "physical-plane metadata has an out-of-range byte")
    require(byte_count == PHYSICAL_PLANE_DUMP_SIZE,
            "physical-plane metadata byte count changed")
    require(scene == 0x0B and menu == 0,
            "physical-plane dump is not a scene-$0B post-close sample")

    tiles_blob = payload[:0x800]
    attrs_blob = payload[0x800:0x1000]
    source = payload[0x1000:0x1240]
    runtime_lut = payload[0x1240:0x1340]
    require(len(source) == 24 * 24 and len(runtime_lut) == 0x100,
            "physical-plane source/LUT payload is incomplete")
    if capture_label in HAZARD_CAPTURE_LABELS:
        require(sha256_bytes(runtime_lut) == STAGE1_RELEASE_LUT_SHA256,
                "physical-plane inherited runtime LUT is not reviewed release")
    else:
        require(runtime_lut == canonical_lut,
                "physical-plane runtime LUT differs from candidate canonical LUT")
    require(len(immutable_source) == 24 * 24,
            "immutable operator source map has wrong size")

    # The native compiler owns 24x24 cells, not merely the current viewport.
    # Keep the established "visible" receipt keys for schema compatibility,
    # while recomputing them over the complete owned plane and zero padding.
    owned = [
        row * 32 + column
        for row in range(24)
        for column in range(24)
    ]
    immutable_map = bytearray(0x400)
    for row in range(24):
        immutable_map[row * 32:row * 32 + 24] = immutable_source[
            row * 24:(row + 1) * 24
        ]
    immutable_hazard_positions = _stage1_hazard_positions(
        bytes(immutable_map)
    )
    immutable_hazard_envelope: set[int] = set()
    for position in immutable_hazard_positions:
        hazard_row, hazard_column = divmod(position, 32)
        for envelope_row in range(
            max(0, hazard_row - 1), min(32, hazard_row + 2)
        ):
            for envelope_column in range(
                max(0, hazard_column - 1), min(32, hazard_column + 2)
            ):
                immutable_hazard_envelope.add(
                    envelope_row * 32 + envelope_column
                )
    exact_source_hazard = None
    hazard_contract = None
    if capture_label in HAZARD_CAPTURE_LABELS:
        hazard_contract = load_hazard_tile_contract()
        exact_source_hazard = evaluate_scene0b_hazard_tiles(
            source, source=immutable_source, contract=hazard_contract
        )
        immutable_hazard_envelope = {
            (offset // 24) * 32 + offset % 24
            for offset in hazard_contract.coverage.exact_object_cells
        }

    source_immutable_diffs: list[int] = []
    for offset in owned:
        source_row, source_column = divmod(offset, 32)
        if (
            source_row < 24
            and source_column < 24
            and source[source_row * 24 + source_column]
            != immutable_source[source_row * 24 + source_column]
        ):
            source_immutable_diffs.append(offset)
    source_immutable_outside_hazard = [
        offset for offset in source_immutable_diffs
        if offset not in immutable_hazard_envelope
    ]
    source_immutable_right_edge = [
        offset for offset in source_immutable_outside_hazard
        if offset % 32 >= 17
    ]

    maps: dict[str, Any] = {}
    for index, name in enumerate(("9800", "9C00")):
        tiles = tiles_blob[index * 0x400:(index + 1) * 0x400]
        attrs = attrs_blob[index * 0x400:(index + 1) * 0x400]
        exact_map_hazard = None
        semantic_hazard_positions = immutable_hazard_positions
        if hazard_contract is not None:
            exact_map_hazard = evaluate_scene0b_hazard_tiles(
                tiles, source=immutable_source, contract=hazard_contract
            )
            semantic_hazard_positions = _stage1_hazard_positions(tiles)
        expected = _stage1_semantic_attrs(
            tiles, canonical_lut, room, semantic_hazard_positions
        )
        semantic_diffs = [
            offset for offset in range(0x400)
            if attrs[offset] != expected[offset]
        ]
        visible_semantic_diffs = [
            offset for offset in owned if attrs[offset] != expected[offset]
        ]
        source_diffs: list[int] = []
        for offset in owned:
            source_row, source_column = divmod(offset, 32)
            if (
                source_row < 24
                and source_column < 24
                and tiles[offset]
                != source[source_row * 24 + source_column]
            ):
                source_diffs.append(offset)
        hazard_owned_source_diffs = [
            offset for offset in source_diffs
            if offset in immutable_hazard_envelope
        ]
        outside_hazard_source_diffs = [
            offset for offset in source_diffs
            if offset not in immutable_hazard_envelope
        ]
        right_edge_source_diffs = [
            offset for offset in source_diffs if offset % 32 >= 17
        ]
        immutable_diffs: list[int] = []
        for offset in owned:
            immutable_row, immutable_column = divmod(offset, 32)
            if (
                immutable_row < 24
                and immutable_column < 24
                and tiles[offset]
                != immutable_source[immutable_row * 24 + immutable_column]
            ):
                immutable_diffs.append(offset)
        immutable_outside_hazard = [
            offset for offset in immutable_diffs
            if offset not in immutable_hazard_envelope
        ]
        immutable_right_edge = [
            offset for offset in immutable_outside_hazard
            if offset % 32 >= 17
        ]
        maps[name] = {
            "active": (name == "9C00") == bool(lcdc & 0x08),
            "tiles_sha256": sha256_bytes(tiles),
            "attrs_sha256": sha256_bytes(attrs),
            "exact_hazard_oracle": (
                None if exact_map_hazard is None
                else exact_map_hazard.to_receipt()
            ),
            "hazard_positions": len(immutable_hazard_positions),
            "hazard_animation_envelope": len(immutable_hazard_envelope),
            "semantic_mismatches_full_map": len(semantic_diffs),
            "semantic_mismatches_visible": len(visible_semantic_diffs),
            "tile_source_mismatches_visible": len(source_diffs),
            "tile_source_mismatches_hazard_owned_visible": len(
                hazard_owned_source_diffs
            ),
            "tile_source_mismatches_outside_hazard_visible": len(
                outside_hazard_source_diffs
            ),
            "tile_source_mismatches_right_edge_visible": len(
                right_edge_source_diffs
            ),
            "tile_immutable_mismatches_visible": len(immutable_diffs),
            "tile_immutable_mismatches_outside_hazard_visible": len(
                immutable_outside_hazard
            ),
            "tile_immutable_mismatches_right_edge_visible": len(
                immutable_right_edge
            ),
            "first_visible_semantic_mismatches": [
                {
                    "offset": f"{offset:03X}",
                    "tile": f"{tiles[offset]:02X}",
                    "actual": f"{attrs[offset]:02X}",
                    "expected": f"{expected[offset]:02X}",
                    "hazard_position": offset in immutable_hazard_positions,
                }
                for offset in visible_semantic_diffs[:32]
            ],
            "first_visible_tile_source_mismatches": [
                {
                    "offset": f"{offset:03X}",
                    "actual": f"{tiles[offset]:02X}",
                    "source": f"{source[(offset // 32) * 24 + offset % 32]:02X}",
                }
                for offset in source_diffs[:32]
            ],
        }
    return {
        "path": str(dump_path.resolve()),
        "sha256": sha256(dump_path),
        "metadata_path": str(metadata_path.resolve()),
        "metadata_sha256": sha256(metadata_path),
        "frame": frame,
        "sample": sample,
        "lcdc": f"{lcdc:02X}",
        "scx": f"{scx:02X}",
        "scy": f"{scy:02X}",
        "scene": f"{scene:02X}",
        "room": f"{room:02X}",
        "runtime_lut_sha256": sha256_bytes(runtime_lut),
        "runtime_lut_matches_canonical": runtime_lut == canonical_lut,
        "source_sha256": sha256_bytes(source),
        "immutable_source_sha256": sha256_bytes(immutable_source),
        "exact_hazard_oracle": (
            None if exact_source_hazard is None
            else exact_source_hazard.to_receipt()
        ),
        "source_immutable_mismatches_outside_hazard_visible": len(
            source_immutable_outside_hazard
        ),
        "source_immutable_mismatches_right_edge_visible": len(
            source_immutable_right_edge
        ),
        "maps": maps,
    }


def _stage1_chr_address(tile: int, lcdc: int) -> int:
    address = tile * 16
    if not (lcdc & 0x10) and tile < 0x80:
        address += 0x1000
    return address


def recompute_final_bg_chr(
    chr_path: Path,
    plane_dump_path: Path,
    metadata_path: Path,
    candidate: bytes,
    capture_label: str,
) -> dict[str, Any]:
    """Independently grade the final physical CHR referenced by both maps."""
    try:
        actual = chr_path.read_bytes()
        planes = plane_dump_path.read_bytes()
    except OSError as error:
        raise ContractError(f"final BG CHR evidence is unreadable: {error}") from error
    require(len(actual) == FINAL_BG_CHR_BYTES,
            f"final physical CHR size changed: {len(actual)}")
    require(len(planes) == PHYSICAL_PLANE_DUMP_SIZE,
            "final CHR grading lacks the exact physical-plane dump")
    metadata = parse_key_values(metadata_path, "final CHR metadata")
    lcdc = _metadata_integer(metadata, "lcdc", 16, "final CHR metadata")

    canonical_bg_art = b"".join(
        candidate[offset:offset + 16]
        for tile in range(0x100)
        for offset in (((
            STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
            if tile < 0x80
            else STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
        )),)
    )
    require(len(canonical_bg_art) == 0x1000
            and sha256_bytes(canonical_bg_art) == STAGE1_BG_ART_SHA256,
            "candidate lacks canonical final Stage-1 BG art")
    canonical_bank1 = (
        candidate[0x1D640:0x1D6A0] + candidate[0x1D740:0x1D7A0]
    )
    require(len(canonical_bank1) == 192
            and sha256_bytes(canonical_bank1)
            == STAGE1_HAZARD_BANK1_ART_SHA256,
            "candidate lacks canonical final bank-one hazard art")

    tiles_blob = planes[:0x800]
    attrs_blob = planes[0x800:0x1000]
    owned = tuple(
        row * 32 + column
        for row in range(24)
        for column in range(24)
    )
    references: dict[tuple[int, int], tuple[str, int]] = {}
    for map_index, map_name in enumerate(("9800", "9C00")):
        tiles = tiles_blob[map_index * 0x400:(map_index + 1) * 0x400]
        attrs = attrs_blob[map_index * 0x400:(map_index + 1) * 0x400]
        for offset in owned:
            key = ((attrs[offset] >> 3) & 1, tiles[offset])
            references.setdefault(key, (map_name, offset))

    illegal: list[tuple[int, int]] = []
    mismatches: list[dict[str, Any]] = []
    byte_mismatches = 0
    for bank, tile in sorted(references):
        expected: bytes | None = None
        if bank == 0:
            expected = canonical_bg_art[tile * 16:(tile + 1) * 16]
        elif capture_label in HAZARD_CAPTURE_LABELS:
            if 0x64 <= tile <= 0x69:
                base = (tile - 0x64) * 16
                expected = canonical_bank1[base:base + 16]
            elif 0x74 <= tile <= 0x79:
                base = 96 + (tile - 0x74) * 16
                expected = canonical_bank1[base:base + 16]
        if expected is None:
            illegal.append((bank, tile))
            continue
        address = bank * 0x2000 + _stage1_chr_address(tile, lcdc)
        observed = actual[address:address + 16]
        differences = sum(
            left != right for left, right in zip(
                observed, expected, strict=True
            )
        )
        if differences:
            byte_mismatches += differences
            map_name, offset = references[(bank, tile)]
            mismatches.append({
                "bank": bank,
                "tile": f"{tile:02X}",
                "address": f"{address:04X}",
                "map": map_name,
                "offset": f"{offset:03X}",
                "actual_sha256": sha256_bytes(observed),
                "expected_sha256": sha256_bytes(expected),
                "byte_mismatches": differences,
            })
    return {
        "path": str(chr_path.resolve()),
        "sha256": sha256(chr_path),
        "bytes": len(actual),
        "referenced_patterns": len(references),
        "bank0_patterns": sum(bank == 0 for bank, _tile in references),
        "bank1_patterns": sum(bank == 1 for bank, _tile in references),
        "illegal_bank1_patterns": len(illegal),
        "pattern_mismatches": len(mismatches),
        "byte_mismatches": byte_mismatches,
        "first_mismatches": mismatches[:32],
    }


def parse_state_trace(path: Path, label: str) -> list[dict[str, Any]]:
    """Parse the saved JSONL trace and recover the producer's raw rows."""
    try:
        lines = path.read_text().splitlines()
    except (OSError, UnicodeError) as error:
        raise ContractError(f"{label} is unreadable: {error}") from error
    require(lines, f"{label} is empty")
    rows: list[dict[str, Any]] = []
    previous_frame = -1
    phase_rank = {phase: index for index, phase in enumerate(TRACE_PHASES)}
    for number, line in enumerate(lines, 1):
        try:
            serialized = json.loads(line)
        except json.JSONDecodeError as error:
            raise ContractError(
                f"{label} line {number} is not valid JSON"
            ) from error
        exact_keys(serialized, STATE_TRACE_KEYS, f"{label} line {number}")
        require(serialized["schema"] == STATE_TRACE_SCHEMA,
                f"{label} line {number} schema changed")
        phase = serialized["phase"]
        require(phase in phase_rank,
                f"{label} line {number} phase is invalid")
        require(all(type(serialized[key]) is int
                    for key in STATE_TRACE_VALUE_KEYS),
                f"{label} line {number} has a non-integer observation")
        require(serialized["sample"] == number,
                f"{label} sample sequence breaks on line {number}")
        require(serialized["frame"] > previous_frame,
                f"{label} frame sequence breaks on line {number}")
        previous_frame = serialized["frame"]
        require(serialized["scene"] == 0x0B
                and serialized["active"] == 1,
                f"{label} leaves active scene $0B on line {number}")
        require((serialized["lcdc"] & 0x97) == 0x83,
                f"{label} changes required Stage-1 LCDC bits on line {number}")
        require(serialized["menu"] in {0, 1},
                f"{label} menu state is invalid on line {number}")
        require(all(0 <= serialized[key] <= 0xFF for key in (
            "scene", "room", "active", "menu", "lcdc", "scx", "scy",
        )), f"{label} has an out-of-range byte on line {number}")
        require(all(serialized[key] >= 0 for key in (
            "sample", "frame", "attr_mismatches",
            "semantic_attr_mismatches", "immutable_tile_mismatches",
            "bg_cram_mismatches", "lut_mismatches",
        )), f"{label} has a negative counter on line {number}")
        raw = dict(serialized)
        raw.pop("schema")
        rows.append(raw)
    return rows


def parse_rendered_manifest(
    path: Path,
    receipt_root: Path,
    capture_label: str,
    replay_index: int,
    trace_rows: list[dict[str, Any]],
    label: str,
) -> list[dict[str, Any]]:
    """Authenticate every rendered frame and rebuild manifest semantics."""
    manifest = load_object(path, label)
    exact_keys(manifest, RENDERED_MANIFEST_KEYS, label)
    require(manifest["schema"] == RENDERED_MANIFEST_SCHEMA,
            f"{label} schema changed")
    require(manifest["capture_label"] == capture_label
            and manifest["replay_index"] == replay_index,
            f"{label} replay identity changed")
    require(SHA256_RE.fullmatch(manifest["semantic_sha256"] or "") is not None,
            f"{label} semantic hash is malformed")
    frames = manifest["frames"]
    require(isinstance(frames, list) and len(frames) == len(trace_rows),
            f"{label} frame/trace counts differ")
    validated: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for offset, (frame, trace) in enumerate(
        zip(frames, trace_rows, strict=True), 1
    ):
        exact_keys(frame, RENDERED_FRAME_KEYS, f"{label} frame {offset}")
        require(type(frame["sample"]) is int
                and frame["sample"] == trace["sample"]
                and frame["phase"] == trace["phase"],
                f"{label} frame/trace ordering differs at {offset}")
        require(SHA256_RE.fullmatch(frame["sha256"] or "") is not None
                and SHA256_RE.fullmatch(frame["rgb_sha256"] or "") is not None,
                f"{label} frame {offset} hash is malformed")
        raw_path = frame["path"]
        require(isinstance(raw_path, str) and raw_path,
                f"{label} frame {offset} path is missing")
        frame_path = Path(raw_path).resolve()
        require(frame_path.is_relative_to(receipt_root),
                f"{label} frame {offset} escapes the live receipt directory")
        require(frame_path not in seen_paths,
                f"{label} repeats a rendered frame path")
        seen_paths.add(frame_path)
        require(sha256(frame_path) == frame["sha256"],
                f"{label} frame {offset} file hash differs")
        try:
            with Image.open(frame_path) as source:
                image = source.convert("RGB")
                require(image.size == SCREEN_SIZE,
                        f"{label} frame {offset} geometry changed")
                rgb_sha256 = sha256_bytes(image.tobytes())
        except (OSError, ValueError) as error:
            raise ContractError(
                f"{label} frame {offset} is not a readable image"
            ) from error
        require(rgb_sha256 == frame["rgb_sha256"],
                f"{label} frame {offset} RGB hash differs")
        validated_frame = dict(frame)
        # Kept only in memory so rendered counters can be recomputed from the
        # authenticated PNG rather than trusted from the receipt.
        validated_frame["pixels"] = tuple(image.getdata())
        validated.append(validated_frame)
    semantic = sha256_bytes(json.dumps(
        [
            {key: frame[key] for key in ("sample", "phase", "rgb_sha256")}
            for frame in validated
        ],
        sort_keys=True, separators=(",", ":"),
    ).encode())
    require(semantic == manifest["semantic_sha256"],
            f"{label} semantic hash differs")
    return validated


def trace_rendered_fingerprint(
    trace_rows: list[dict[str, Any]], frames: list[dict[str, Any]],
) -> str:
    payload = {
        "trace": trace_rows,
        "rendered": [
            (frame["sample"], frame["phase"], frame["rgb_sha256"])
            for frame in frames
        ],
    }
    return sha256_bytes(json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode())


def validate_tool_identity(
    value: Any, expected: Mapping[str, dict[str, str]], label: str
) -> None:
    exact_keys(value, frozenset(expected), label)
    for name, tool in value.items():
        exact_keys(tool, TOOL_KEYS, f"{label} {name}")
    require(value == expected, f"{label} differs from current checked tools")


def validate_launch_contract(
    claim: Any,
    receipt_root: Path,
    *,
    capture: Mapping[str, Any],
    replay: Mapping[str, Any],
    candidate_sha256: str,
    immutable_source: bytes,
    immutable_stage1_tables: bytes,
    runtime_oracles: bytes,
) -> dict[str, Any]:
    """Authenticate and independently reconstruct the exact launch contract."""
    artifact = validate_artifact(
        claim, receipt_root, "live replay launch contract"
    )
    path = Path(artifact["path"])
    contract = load_object(path, "live replay launch contract")
    exact_keys(contract, LAUNCH_CONTRACT_KEYS, "live replay launch contract")
    require(contract["schema"] == "penta-stage1-scene0b-launch-contract-v6",
            "live replay launch contract schema changed")

    output = path.parent.resolve()
    runtime = output / "runtime"
    runtime_rom = runtime / "candidate.gb"
    runtime_state = runtime / "capture.ss0"
    prefix = output / "scene0b"
    expected_command = [
        str(SINGLEFLIGHT), "--fastforward",
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        "--script", str(LIVE_PROBE), str(runtime_rom),
    ]
    require(contract["command"] == expected_command,
            "live replay launched another command")
    require(Path(contract["cwd"]).resolve() == output
            and Path(contract["output_prefix"]).resolve() == prefix,
            "live replay launch cwd/output prefix changed")
    require(
        contract["capture_label"] == capture["label"]
        and contract["replay_index"] == replay["replay_index"]
        and contract["initial_menu"]
        == int(capture["captured_state"]["FFE4"], 16)
        and contract["frame_limit"] == FRAME_LIMIT
        and contract["capture_frames"] == CAPTURE_FRAMES
        and contract["repair_settle_frames"] == REPAIR_SETTLE_FRAMES
        and contract["menu_hold_frames"] == MENU_HOLD_FRAMES
        and contract["post_close_frames"] == POST_CLOSE_FRAMES,
        "live replay launch route/timing contract changed",
    )
    require(type(contract["launch_started_at_ns"]) is int
            and type(contract["launch_completed_at_ns"]) is int
            and 0 < contract["launch_started_at_ns"]
            <= contract["launch_completed_at_ns"],
            "live replay launch time window is invalid")
    require(SHA256_RE.fullmatch(
        contract["startup_token_sha256"] or ""
    ) is not None, "live replay startup-token hash is malformed")
    emulator = default_qt_emulator()
    require(
        contract["launcher_sha256"] == sha256(SINGLEFLIGHT)
        and contract["singleflight_implementation_sha256"]
        == sha256(SINGLEFLIGHT_IMPLEMENTATION)
        and Path(contract["emulator_path"]).resolve() == emulator
        and contract["emulator_sha256"] == sha256(emulator)
        and contract["probe_sha256"] == sha256(LIVE_PROBE),
        "live replay launch tools differ from checked tools",
    )
    require(Path(contract["runtime_rom_path"]).resolve() == runtime_rom
            and sha256(runtime_rom) == candidate_sha256
            and contract["runtime_rom_sha256"] == candidate_sha256,
            "live replay runtime ROM is not the bound candidate")
    require(
        Path(contract["runtime_state_path"]).resolve() == runtime_state
        and Path(replay["retargeted_state"]["path"]).resolve()
        == runtime_state
        and contract["runtime_state_sha256"]
        == replay["retargeted_state_sha256"]
        == sha256(runtime_state),
        "live replay runtime state is not the bound retargeted capture",
    )
    expected_hashes = {
        "immutable_source_sha256": sha256_bytes(immutable_source),
        "immutable_stage1_tables_sha256": sha256_bytes(
            immutable_stage1_tables
        ),
        "canonical_bg_art_sha256": STAGE1_BG_ART_SHA256,
        "canonical_hazard_bank1_art_sha256": (
            STAGE1_HAZARD_BANK1_ART_SHA256
        ),
        "hazard_oracle_fixture_sha256": sha256(
            HAZARD_TILE_ORACLE_FIXTURE
        ),
        "hazard_phase_payload_sha256": (
            STAGE1_HAZARD_PHASE_PAYLOAD_SHA256
        ),
        "expected_bg_cram_sha256": STAGE1_BG_CRAM_SHA256,
        "runtime_oracle_bundle_sha256": sha256_bytes(runtime_oracles),
    }
    require(all(contract[key] == value for key, value in expected_hashes.items()),
            "live replay launch oracle hashes changed")
    expected_artifacts = {
        "startup": Path(str(prefix) + ".startup"),
        "ready": Path(str(prefix) + ".ready"),
        "core_ready": Path(str(prefix) + ".core-ready"),
        "config_ready": Path(str(prefix) + ".config-ready"),
        "trace_ready": Path(str(prefix) + ".trace-ready"),
        "done": Path(str(prefix) + ".done"),
        "report": Path(str(prefix) + ".report"),
        "raw_trace": Path(str(prefix) + ".trace.tsv"),
        "emulator_log": output / "emulator.log",
    }
    launch_artifacts = {
        name: validate_launch_artifact(
            contract[name], receipt_root, expected_path,
            contract["launch_started_at_ns"],
            contract["launch_completed_at_ns"],
            f"live replay launch {name}",
        )
        for name, expected_path in expected_artifacts.items()
    }
    require_causal_launch_artifact_order(launch_artifacts)
    try:
        startup_token = Path(
            launch_artifacts["startup"]["path"]
        ).read_text().strip()
    except (OSError, UnicodeError) as error:
        raise ContractError(
            f"live replay startup marker is unreadable: {error}"
        ) from error
    require(re.fullmatch(r"[0-9a-f]{64}", startup_token) is not None,
            "live replay startup token is malformed")
    require(sha256_bytes(startup_token.encode())
            == contract["startup_token_sha256"],
            "live replay startup-token hash differs")
    for name in ("ready", "core_ready", "config_ready", "trace_ready"):
        require(Path(launch_artifacts[name]["path"]).read_text().strip()
                == startup_token,
                f"live replay {name} marker token differs")
    completion = parse_key_values(
        Path(launch_artifacts["done"]["path"]),
        "live replay completion marker",
    )
    require(completion == {"status": "ok", "startup_token": startup_token},
            "live replay completion marker differs")
    report = parse_key_values(
        Path(launch_artifacts["report"]["path"]),
        "live replay report",
    )
    require(report.get("status") == "ok"
            and report.get("reason") == "complete"
            and report.get("startup_token") == startup_token,
            "live replay report token/status differs")
    try:
        reported_oam_dma_unreadable = int(
            report.get("oam_dma_unreadable_frames", "-1")
        )
    except ValueError as error:
        raise AssertionError(
            "live replay report OAM-DMA deferral count is malformed"
        ) from error
    require(
        reported_oam_dma_unreadable == replay["oam_dma_unreadable_frames"],
        "live replay OAM-DMA deferral count differs from its report",
    )
    raw_trace_rows = parse_token_bound_raw_trace(
        Path(launch_artifacts["raw_trace"]["path"]),
        startup_token,
        "live replay raw trace",
    )
    require(contract["cache_audit"] is None
            and contract["cache_audit_ready"] is None,
            "release replay unexpectedly enabled diagnostic breakpoints")
    require(
        contract["startup_timeout_seconds"] == STARTUP_TIMEOUT_SECONDS
        and contract["ready_timeout_seconds"] == READY_TIMEOUT_SECONDS
        and contract["core_timeout_seconds"] == CORE_TIMEOUT_SECONDS
        and contract["teardown_policy"] == TEARDOWN_POLICY,
        "live replay launch timeout/teardown policy changed",
    )
    provisional = contract["provisional_process_outcome"]
    exact_keys(provisional, LAUNCH_PROCESS_OUTCOME_KEYS,
               "live replay provisional process outcome")
    teardown = replay["process_teardown"]
    require(provisional == {
        "exact_child_terminated": teardown["exact_child_terminated"],
        "termination_method": teardown["termination_method"],
        "return_code": teardown["return_code"],
        "completion_status": "ok",
    }, "live replay provisional process outcome differs")
    require(contract["validated_process_teardown"] == teardown,
            "live replay validated process teardown differs")
    # Some filesystems quantize inode mtime a few microseconds below the
    # userspace time_ns sampled immediately before this contract is written.
    # Launch-owned artifacts above remain strictly inside the replay window;
    # allow only a 1 ms metadata-resolution margin for the contract inode.
    require(path.stat().st_mtime_ns + 1_000_000
            >= contract["launch_completed_at_ns"],
            "live replay launch contract predates child completion")
    return {
        **artifact,
        "replay_root": str(output),
        "startup_token_sha256": contract["startup_token_sha256"],
        "launch_completed_at_ns": contract["launch_completed_at_ns"],
        "raw_trace_rows": raw_trace_rows,
        "evidence_paths": [
            row["path"] for row in launch_artifacts.values()
        ] + [str(runtime_rom.resolve()), str(runtime_state.resolve())],
    }


def validate_live_receipt(
    path: Path, candidate: Path, candidate_sha256: str
) -> dict[str, Any]:
    # Fail before trusting even a schema-perfect receipt if the checked live
    # producer ever loses its explicit reviewed implementation latch.
    require_live_producer_implemented()
    resolved = path.resolve()
    scratch_roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(
        root.exists() and resolved != root and resolved.is_relative_to(root)
        for root in scratch_roots
    ), "live scene-$0B receipt must be below repo tmp/ or /mnt/data/tmp/")
    receipt = load_object(resolved, "live scene-$0B menu receipt")
    exact_keys(receipt, LIVE_TOP_KEYS, "live scene-$0B menu receipt")
    require(receipt["schema"] == LIVE_SCHEMA,
            "wrong live scene-$0B menu receipt schema")
    require(receipt["status"] == "PASS" and receipt["failures"] == [],
            "live scene-$0B menu receipt is not zero-failure PASS")
    require(Path(receipt["candidate"]).resolve() == candidate.resolve(),
            "live scene-$0B menu receipt targets another candidate path")
    require(receipt["candidate_sha256"] == candidate_sha256,
            "live scene-$0B menu receipt targets another candidate hash")
    require(sha256(candidate.resolve()) == candidate_sha256,
            "candidate changed during scene-$0B receipt validation")
    candidate_bytes = candidate.read_bytes()
    candidate_identity = candidate_bytes[
        ROM_TITLE_OFFSET:ROM_TITLE_OFFSET + GBAS_TITLE_SIZE
    ]
    require(len(candidate_identity) == GBAS_TITLE_SIZE
            and candidate_identity[15] == CGB_ONLY_FLAG,
            "candidate is not an exact CGB-only ROM identity")
    canonical_lut = candidate_bytes[
        STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 0x100
    ]
    require(len(canonical_lut) == 0x100
            and sha256_bytes(canonical_lut) in {
                STAGE1_LUT_SHA256,
                STAGE1_RELEASE_LUT_SHA256,
                STAGE1_COMPILED_TOOTH_LUT_SHA256,
            },
            "candidate lacks the reviewed canonical Stage-1 LUT")
    contract = load_capture_contract()
    captures = capture_evidence(contract)
    archived_incompatible = archived_incompatible_evidence(
        contract, candidate, candidate_sha256
    )
    native_provenance = validate_native_capture_provenance(
        captures, candidate, candidate_sha256
    )
    require(receipt["archived_incompatible_capture"]
            == archived_incompatible,
            "live receipt does not bind the archived incompatible capture")
    reported_captures = receipt["source_captures"]
    require(
        isinstance(reported_captures, list)
        and len(reported_captures) == len(captures)
        and {row["label"]: row for row in reported_captures}
            == {row["label"]: row for row in captures},
        "live receipt does not bind both exact operator captures",
    )
    policy = contract["live_policy"]
    require(receipt["route_policy"] == policy,
            "live scene-$0B route policy changed")
    checks = receipt["checks"]
    exact_keys(checks, LIVE_CHECKS, "live scene-$0B checks")
    require(all(checks[name] is True for name in LIVE_CHECKS),
            "one or more live scene-$0B checks failed")
    validate_tool_identity(
        receipt["tool_identity"], expected_live_tool_identity(),
        "live scene-$0B tool identity",
    )

    replays = receipt["replays"]
    replay_count = int(policy["replays_per_capture"])
    require(isinstance(replays, list)
            and len(replays) == len(captures) * replay_count,
            "live receipt must contain two replays of both captures")
    expected_pairs = {
        (capture["label"], replay_index)
        for capture in captures
        for replay_index in range(1, replay_count + 1)
    }
    actual_pairs: set[tuple[str, int]] = set()
    fingerprints: dict[str, set[str]] = {
        capture["label"]: set() for capture in captures
    }
    replay_roots: set[Path] = set()
    replay_evidence_paths: set[Path] = set()
    startup_token_hashes: set[str] = set()
    root = resolved.parent
    candidate_crc32 = f"{zlib.crc32(candidate.read_bytes()) & 0xFFFFFFFF:08x}"
    by_label = {capture["label"]: capture for capture in captures}
    legacy_visual_fields = (
        "wall_edge_artifact_frames", "red_green_artifact_frames",
        "clear_tile_frames", "weird_edge_tile_frames",
        "visible_attr_mismatch_frames", "yellow_trail_frames",
        "gray_spike_frames", "postsettle_wall_edge_artifact_frames",
        "postsettle_red_green_artifact_frames",
        "postsettle_weird_edge_tile_frames",
    )
    validated_replays: list[dict[str, Any]] = []
    for index, replay in enumerate(replays):
        exact_keys(replay, REPLAY_KEYS, f"live replay {index}")
        label = replay["capture_label"]
        require(label in by_label, f"live replay {index} capture is unknown")
        require(isinstance(replay["replay_index"], int),
                f"live replay {index} index is not an integer")
        pair = (label, replay["replay_index"])
        require(pair not in actual_pairs, f"duplicate live replay pair: {pair}")
        actual_pairs.add(pair)
        capture = by_label[label]
        expected_state = capture["captured_state"]
        require(replay["source_capture_path"] == capture["path"]
                and replay["source_capture_sha256"] == capture["sha256"],
                f"live replay {index} uses another capture")
        require(replay["source_state_loaded"] is True,
                f"live replay {index} did not load its captured state")
        require(replay["initial_scene"] == "0B"
                and replay["initial_menu_flag"] == expected_state["FFE4"],
                f"live replay {index} starts in the wrong captured state")
        require(replay["scene_values"] == policy["scene_values"],
                f"live replay {index} leaves scene $0B")
        require(replay["normalization"] == policy["normalization"]
                and replay["normalization_writes"]
                == policy["normalization_writes"]
                and replay["fixture_writes"] == 0
                and replay["scene_injection"] is False
                and replay["vram_injection_bytes"]
                == policy["vram_injection_bytes"],
                f"live replay {index} injects or normalizes gameplay state")
        require(SHA256_RE.fullmatch(
            replay["retargeted_state_sha256"] or ""
        ) is not None, f"live replay {index} retargeted state hash is malformed")
        require(replay["retargeted_state_rom_crc32"] == candidate_crc32,
                f"live replay {index} state is not identity-retargeted to candidate")
        retargeted_state = validate_artifact(
            replay["retargeted_state"], root,
            f"live replay {index} retargeted state",
        )
        require(retargeted_state["sha256"]
                == replay["retargeted_state_sha256"],
                f"live replay {index} retargeted state hashes differ")
        source_state = gbas_payload(Path(capture["path"]))
        source_identity = source_state[
            GBAS_TITLE_OFFSET:GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE
        ]
        require(source_state[GBAS_MODEL_OFFSET] == GB_MODEL_CGB
                and source_state[GBAS_BOOT_REGISTER_OFFSET] != 0xFF,
                f"live replay {index} source is not post-BIOS CGB")
        require(source_identity[:15] == candidate_identity[:15]
                and source_identity[15] == CGB_COMPATIBLE_FLAG
                and candidate_identity[15] == CGB_ONLY_FLAG,
                f"live replay {index} is not the exact $80->$C0 identity")
        immutable_source = immutable_source_from_capture(
            Path(capture["path"]), source_state
        )
        immutable_stage1_tables = gbax_sram_payload(
            Path(capture["path"])
        )[:0x800]
        canonical_oracles = canonical_runtime_oracles(
            candidate_bytes, immutable_source, immutable_stage1_tables
        )
        retargeted_payload = gbas_payload(Path(retargeted_state["path"]))
        changed_offsets = [
            offset
            for offset, values in enumerate(zip(
                source_state, retargeted_payload, strict=True
            ))
            if values[0] != values[1]
        ]
        candidate_crc_bytes = (
            zlib.crc32(candidate_bytes) & 0xFFFFFFFF
        ).to_bytes(4, "little")
        expected_changed_offsets = [
            4 + offset for offset, values in enumerate(zip(
                source_state[4:8], candidate_crc_bytes, strict=True
            )) if values[0] != values[1]
        ] + [GBAS_TITLE_OFFSET + 15]
        require(changed_offsets == expected_changed_offsets,
                f"live replay {index} changes captured machine state")
        require(replay["retarget_changed_gbAs_offsets"] == changed_offsets,
                f"live replay {index} ROM-identity delta differs")
        require(int.from_bytes(retargeted_payload[4:8], "little")
                == (zlib.crc32(candidate.read_bytes()) & 0xFFFFFFFF),
                f"live replay {index} retargeted payload CRC differs")
        require(retargeted_payload[
            GBAS_TITLE_OFFSET:GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE
        ] == candidate_identity,
                f"live replay {index} retargeted ROM identity differs")
        require(replay["retargeted_state_rom_identity"]
                == candidate_identity.hex(),
                f"live replay {index} reported ROM identity differs")
        require(source_state[:4] == retargeted_payload[:4]
                and source_state[8:GBAS_TITLE_OFFSET + 15]
                == retargeted_payload[8:GBAS_TITLE_OFFSET + 15]
                and source_state[GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE:]
                == retargeted_payload[GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE:],
                f"live replay {index} changes CPU/mapper/WRAM/VRAM/video")
        require(replay["native_menu_transitions"] is True,
                f"live replay {index} did not use native menu transitions")
        teardown = replay["process_teardown"]
        exact_keys(teardown, PROCESS_TEARDOWN_KEYS,
                   f"live replay {index} process teardown")
        require(teardown["completion_authenticated"] is True,
                f"live replay {index} completion is not authenticated")
        if teardown["exact_child_terminated"] is True:
            require(
                teardown["policy"] == "authenticated-exact-child-termination"
                and teardown["termination_method"] in {
                    "SIGTERM", "SIGKILL-after-SIGTERM-timeout",
                }
                and teardown["return_code"] in {0, -15, -9},
                f"live replay {index} exact-child teardown is invalid",
            )
        else:
            require(
                teardown == {
                    "policy": "natural-zero-exit",
                    "completion_authenticated": True,
                    "exact_child_terminated": False,
                    "termination_method": "already-exited",
                    "return_code": 0,
                },
                f"live replay {index} accepts an arbitrary launcher exit",
            )
        require(replay["baseline_ready"] is True,
                f"live replay {index} has no native repaired baseline")
        require(isinstance(replay["attr_checked_samples"], int)
                and replay["attr_checked_samples"] >= 24,
                f"live replay {index} has inadequate attribute observations")
        require(type(replay["attr_unreadable_samples"]) is int
                and replay["attr_unreadable_samples"] == 0,
                f"live replay {index} has unreadable attribute samples")
        require(isinstance(replay["semantic_checked_samples"], int)
                and replay["semantic_checked_samples"] >= 24,
                f"live replay {index} has inadequate semantic observations")
        require(type(replay["semantic_unreadable_samples"]) is int
                and replay["semantic_unreadable_samples"] == 0,
                f"live replay {index} has unreadable semantic samples")
        require(replay["postsettle_semantic_attr_mismatch_frames"] == 0,
                f"live replay {index} has a post-settle semantic mismatch")
        require(replay["postsettle_immutable_tile_mismatch_frames"] == 0,
                f"live replay {index} has a post-settle immutable-tile mismatch")
        require(replay["late_tile_art_mismatch_frames"] == 0,
                f"live replay {index} retains stale tile art after repair")
        require(replay["postrepair_bg_cram_mismatch_frames"] == 0,
                f"live replay {index} has a post-repair BG CRAM mismatch")
        require(replay["runtime_lut_mutation_frames"] == 0,
                f"live replay {index} mutates the canonical runtime LUT")
        runtime_oracle_artifact = validate_artifact(
            replay["runtime_oracles"], root,
            f"live replay {index} child runtime oracles",
        )
        require(
            Path(runtime_oracle_artifact["path"]).read_bytes()
            == canonical_oracles,
            f"live replay {index} child parsed noncanonical oracle bytes",
        )
        launch_evidence = validate_launch_contract(
            replay["launch_contract"],
            root,
            capture=capture,
            replay=replay,
            candidate_sha256=candidate_sha256,
            immutable_source=immutable_source,
            immutable_stage1_tables=immutable_stage1_tables,
            runtime_oracles=canonical_oracles,
        )
        replay_root = Path(launch_evidence["replay_root"]).resolve()
        require(replay_root != root and replay_root.is_relative_to(root),
                f"live replay {index} has no isolated evidence root")
        token_hash = launch_evidence["startup_token_sha256"]
        register_replay_freshness(
            replay_root, token_hash, replay_roots, startup_token_hashes,
            f"live replay {index}",
        )
        require(launch_evidence["launch_completed_at_ns"]
                <= resolved.stat().st_mtime_ns,
                f"live replay {index} completes after its live receipt")

        planes = replay["final_physical_planes"]
        exact_keys(planes, PHYSICAL_PLANE_KEYS,
                   f"live replay {index} physical planes")
        plane_artifact = validate_artifact(
            {"path": planes["path"], "sha256": planes["sha256"]}, root,
            f"live replay {index} physical-plane dump",
        )
        metadata_artifact = validate_artifact(
            {
                "path": planes["metadata_path"],
                "sha256": planes["metadata_sha256"],
            }, root, f"live replay {index} physical-plane metadata",
        )
        final_chr_claim = replay["final_bg_chr"]
        exact_keys(final_chr_claim, FINAL_BG_CHR_KEYS,
                   f"live replay {index} final BG CHR")
        final_chr_artifact = validate_artifact(
            {
                "path": final_chr_claim["path"],
                "sha256": final_chr_claim["sha256"],
            },
            root,
            f"live replay {index} final BG CHR",
        )
        recomputed_planes = recompute_physical_planes(
            Path(plane_artifact["path"]), Path(metadata_artifact["path"]),
            canonical_lut,
            immutable_source,
            label,
        )
        require(planes == recomputed_planes,
                f"live replay {index} physical-plane claims differ from "
                "the bound dump/metadata")
        recomputed_chr = recompute_final_bg_chr(
            Path(final_chr_artifact["path"]),
            Path(plane_artifact["path"]),
            Path(metadata_artifact["path"]),
            candidate_bytes,
            label,
        )
        require(final_chr_claim == recomputed_chr,
                f"live replay {index} final BG CHR claims differ from "
                "the bound physical bytes")
        require(
            recomputed_chr["referenced_patterns"] > 0
            and recomputed_chr["illegal_bank1_patterns"] == 0
            and recomputed_chr["pattern_mismatches"] == 0
            and recomputed_chr["byte_mismatches"] == 0,
            f"live replay {index} final referenced BG CHR is noncanonical",
        )
        if label in HAZARD_CAPTURE_LABELS:
            require(recomputed_chr["bank1_patterns"] > 0,
                    f"live replay {index} did not exercise hazard bank-one CHR")
        maps = planes["maps"]
        require(isinstance(maps, dict) and set(maps) == {"9800", "9C00"}
                and all(isinstance(row, dict) for row in maps.values()),
                f"live replay {index} physical-map set changed")
        require(sum(map_row.get("active") is True for map_row in maps.values()) == 1,
                f"live replay {index} physical-map active owner is ambiguous")
        if label in HAZARD_CAPTURE_LABELS:
            require(
                isinstance(planes["exact_hazard_oracle"], dict)
                and planes["exact_hazard_oracle"].get("legal") is True
                and all(
                    isinstance(map_row["exact_hazard_oracle"], dict)
                    and map_row["exact_hazard_oracle"].get("legal") is True
                    for map_row in maps.values()
                ),
                f"live replay {index} exact hazard phase is illegal",
            )
        else:
            require(
                planes["exact_hazard_oracle"] is None
                and all(map_row["exact_hazard_oracle"] is None
                        for map_row in maps.values()),
                f"live replay {index} has a hazard oracle on another route",
            )
        require(type(planes[
            "source_immutable_mismatches_outside_hazard_visible"
        ]) is int
                and planes[
                    "source_immutable_mismatches_outside_hazard_visible"
                ] == 0
                and type(planes[
                    "source_immutable_mismatches_right_edge_visible"
                ]) is int
                and planes[
                    "source_immutable_mismatches_right_edge_visible"
                ] == 0,
                f"live replay {index} mutable source differs from the "
                "operator baseline")
        for map_name, map_row in maps.items():
            exact_keys(map_row, PHYSICAL_MAP_KEYS,
                       f"live replay {index} map {map_name}")
            require(all(
                isinstance(map_row[name], int) and map_row[name] >= 0
                for name in (
                    "hazard_positions", "hazard_animation_envelope",
                    "semantic_mismatches_full_map",
                    "semantic_mismatches_visible",
                    "tile_source_mismatches_visible",
                    "tile_source_mismatches_hazard_owned_visible",
                    "tile_source_mismatches_outside_hazard_visible",
                    "tile_source_mismatches_right_edge_visible",
                    "tile_immutable_mismatches_visible",
                    "tile_immutable_mismatches_outside_hazard_visible",
                    "tile_immutable_mismatches_right_edge_visible",
                )
            ), f"live replay {index} map {map_name} counters are invalid")
            require(map_row["semantic_mismatches_visible"] == 0
                    and map_row[
                        "tile_source_mismatches_outside_hazard_visible"
                    ] == 0
                    and map_row["tile_source_mismatches_right_edge_visible"] == 0,
                    f"live replay {index} map {map_name} is not semantic-clean")
            require(
                map_row[
                    "tile_immutable_mismatches_outside_hazard_visible"
                ] == 0
                and map_row[
                    "tile_immutable_mismatches_right_edge_visible"
                ] == 0,
                f"live replay {index} map {map_name} differs from the "
                "immutable operator baseline",
            )
            require(
                not map_row["active"]
                or map_row["tile_source_mismatches_visible"] == 0
                or (
                    label in HAZARD_CAPTURE_LABELS
                    and map_row["tile_source_mismatches_visible"]
                    == map_row[
                        "tile_source_mismatches_hazard_owned_visible"
                    ]
                ),
                f"live replay {index} active map {map_name} differs from "
                "C1A0 outside exact hazard-owned animation",
            )

        trace_artifact = validate_artifact(
            replay["state_trace"], root, f"live replay {index} state trace"
        )
        trace_rows = parse_state_trace(
            Path(trace_artifact["path"]), f"live replay {index} state trace"
        )
        require(launch_evidence["raw_trace_rows"] == trace_rows,
                f"live replay {index} raw/token trace differs from its "
                "derived state trace")
        require(trace_rows[0]["phase"] == "captured"
                and trace_rows[0]["menu"] == int(expected_state["FFE4"], 16),
                f"live replay {index} trace starts outside its capture")
        phase_sequence = [trace_rows[0]["phase"]]
        for row in trace_rows[1:]:
            if row["phase"] != phase_sequence[-1]:
                phase_sequence.append(row["phase"])
        normal_sequence = [
            "captured", "repair_settle", "menu_entry", "menu_hold",
            "menu_exit", "post_close",
        ]
        require(phase_sequence == normal_sequence,
                f"live replay {index} phase route changed: {phase_sequence}")
        captured_bytes = {
            "scene": int(expected_state["D880"], 16),
            "room": int(expected_state["FFBD"], 16),
            "active": int(expected_state["FFC1"], 16),
            "menu": int(expected_state["FFE4"], 16),
            "lcdc": int(expected_state["LCDC"], 16),
            "scx": int(expected_state["SCX"], 16),
            "scy": int(expected_state["SCY"], 16),
        }
        require(all(trace_rows[0][key] == value
                    for key, value in captured_bytes.items()),
                f"live replay {index} first trace row differs from capture")
        require(all(row["room"] == captured_bytes["room"]
                    and row["scx"] == captured_bytes["scx"]
                    and row["scy"] == captured_bytes["scy"]
                    for row in trace_rows),
                f"live replay {index} moves during the menu-only route")
        require(all(
            (
                row["menu"] == 0 and (row["lcdc"] & 0x20) == 0
                if row["phase"] in {"repair_settle", "post_close"}
                else row["menu"] == 1 and (row["lcdc"] & 0x20) != 0
                if row["phase"] == "menu_hold"
                else True
            )
            for row in trace_rows
        ), f"live replay {index} phase/menu/window semantics differ")
        menu_opens = sum(
            left["menu"] == 0 and right["menu"] == 1
            for left, right in zip(trace_rows, trace_rows[1:])
        )
        menu_closes = sum(
            left["menu"] == 1 and right["menu"] == 0
            for left, right in zip(trace_rows, trace_rows[1:])
        )
        expected_closes = 1 if expected_state["FFE4"] == "00" else 2
        require(menu_opens == 1 and menu_closes == expected_closes
                and replay["menu_open_events"] == menu_opens
                and replay["menu_close_events"] == menu_closes,
                f"live replay {index} menu transition count differs from trace")
        final_trace = trace_rows[-1]
        require(final_trace["phase"] == "post_close"
                and final_trace["menu"] == 0,
                f"live replay {index} trace does not end post-close")
        require(
            planes["sample"] == final_trace["sample"]
            and planes["frame"] == final_trace["frame"],
            f"live replay {index} physical planes are not the final "
            "post-close sample",
        )
        plane_trace_rows = [
            row for row in trace_rows if row["sample"] == planes["sample"]
        ]
        require(len(plane_trace_rows) == 1,
                f"live replay {index} physical-plane sample is absent")
        plane_trace = plane_trace_rows[0]
        require(
            plane_trace["phase"] == "post_close"
            and plane_trace["menu"] == 0
            and plane_trace["frame"] == planes["frame"]
            and plane_trace["lcdc"] == int(planes["lcdc"], 16)
            and plane_trace["scx"] == int(planes["scx"], 16)
            and plane_trace["scy"] == int(planes["scy"], 16)
            and plane_trace["scene"] == int(planes["scene"], 16)
            and plane_trace["room"] == int(planes["room"], 16),
            f"live replay {index} trace and physical-plane sample state differ",
        )
        phase_counts = {
            phase: sum(row["phase"] == phase for row in trace_rows)
            for phase in TRACE_PHASES
        }
        phase_claims = {
            "captured": "captured_state_frames",
            "repair_settle": "repair_settle_frames",
            "menu_entry": "menu_entry_frames",
            "menu_hold": "menu_held_frames",
            "menu_exit": "menu_exit_frames",
            "post_close": "post_close_frames",
        }
        for phase, field in phase_claims.items():
            require(type(replay[field]) is int
                    and replay[field] == phase_counts[phase],
                    f"live replay {index} {field} differs from state trace")
        require(replay["repair_settle_frames"] >= REPAIR_SETTLE_FRAMES,
                f"live replay {index} repair_settle_frames is below "
                f"{REPAIR_SETTLE_FRAMES}")
        trace_metric_claims = {
            "visible_attr_mismatch_frames": sum(
                row["attr_mismatches"] > 0 for row in trace_rows
            ),
            "postrepair_semantic_attr_mismatch_frames": sum(
                row["phase"] != "captured"
                and row["semantic_attr_mismatches"] > 0
                for row in trace_rows
            ),
            "postsettle_semantic_attr_mismatch_frames": sum(
                row["phase"] not in {"captured", "repair_settle"}
                and row["semantic_attr_mismatches"] > 0
                for row in trace_rows
            ),
            "postrepair_immutable_tile_mismatch_frames": sum(
                row["phase"] != "captured"
                and row["immutable_tile_mismatches"] > 0
                for row in trace_rows
            ),
            "postsettle_immutable_tile_mismatch_frames": sum(
                row["phase"] not in {"captured", "repair_settle"}
                and row["immutable_tile_mismatches"] > 0
                for row in trace_rows
            ),
            "late_tile_art_mismatch_frames": sum(
                row["tile_art_mismatches"] > 0
                for row in [
                    item for item in trace_rows
                    if item["phase"] == "repair_settle"
                ][6:]
            ) + sum(
                row["tile_art_mismatches"] > 0
                for row in trace_rows
                if row["phase"] not in {"captured", "repair_settle"}
            ),
            "postrepair_bg_cram_mismatch_frames": sum(
                row["phase"] != "captured"
                and row["bg_cram_mismatches"] > 0
                for row in trace_rows
            ),
            "runtime_lut_mutation_frames": sum(
                row["lut_mismatches"] > 0 for row in trace_rows
            ),
        }
        require(all(replay[field] == value
                    for field, value in trace_metric_claims.items()),
                f"live replay {index} trace mismatch counters differ")
        for prefix in ("semantic", "immutable_tile", "cram"):
            require(type(replay[f"{prefix}_checked_samples"]) is int
                    and replay[f"{prefix}_checked_samples"] == len(trace_rows)
                    and type(replay[f"{prefix}_unreadable_samples"]) is int
                    and replay[f"{prefix}_unreadable_samples"] == 0,
                    f"live replay {index} {prefix} sample coverage differs")
        manifest_artifact = validate_artifact(
            replay["rendered_manifest"], root,
            f"live replay {index} rendered manifest",
        )
        rendered_rows = parse_rendered_manifest(
            Path(manifest_artifact["path"]), root, label,
            replay["replay_index"], trace_rows,
            f"live replay {index} rendered manifest",
        )
        local_evidence_paths = {
            Path(path).resolve()
            for path in launch_evidence["evidence_paths"]
        } | {
            Path(retargeted_state["path"]).resolve(),
            Path(runtime_oracle_artifact["path"]).resolve(),
            Path(launch_evidence["path"]).resolve(),
            Path(plane_artifact["path"]).resolve(),
            Path(metadata_artifact["path"]).resolve(),
            Path(final_chr_artifact["path"]).resolve(),
            Path(trace_artifact["path"]).resolve(),
            Path(manifest_artifact["path"]).resolve(),
            *(Path(row["path"]).resolve() for row in rendered_rows),
        }
        require(all(path.is_relative_to(replay_root)
                    for path in local_evidence_paths),
                f"live replay {index} aliases evidence outside its root")
        require(not (local_evidence_paths & replay_evidence_paths),
                f"live replay {index} reuses another replay's artifact path")
        replay_evidence_paths.update(local_evidence_paths)
        require(type(replay["rendered_frames"]) is int
                and replay["rendered_frames"] == len(rendered_rows),
                f"live replay {index} rendered frame count differs")
        recomputed_fingerprint = trace_rendered_fingerprint(
            trace_rows, rendered_rows
        )
        require(replay["semantic_fingerprint_sha256"]
                == recomputed_fingerprint,
                f"live replay {index} semantic fingerprint differs from "
                "trace/rendered artifacts")
        # The producer is itself hash-pinned in tool_identity. Import its
        # reviewed classifier lazily (avoiding the module-import cycle) and
        # recompute all six metrics from the bound PNG pixels.
        from verify_stage1_scene0b_live_menu_roundtrip import (  # noqa: PLC0415
            visual_metrics,
        )
        rendered_metric_claims = visual_metrics(rendered_rows, label)
        require(all(
            replay[field] == value
            for field, value in rendered_metric_claims.items()
        ), f"live replay {index} rendered visual counters differ")

        for field in (
            "observation_restore_failures", "scene_violation_frames",
            "active_violation_frames",
        ):
            require(replay[field] == 0,
                    f"live replay {index} reports {field}={replay[field]}")
        require(
            type(replay["oam_dma_unreadable_frames"]) is int
            and replay["oam_dma_unreadable_frames"] >= 0,
            f"live replay {index} has an invalid OAM-DMA deferral count",
        )
        for field in (
            "captured_state_frames", "menu_held_frames", "menu_entry_frames",
            "menu_exit_frames", "post_close_frames",
        ):
            minimum = int(policy[f"minimum_{field}"])
            require(replay[field] >= minimum,
                    f"live replay {index} {field} is below {minimum}")
        for field in legacy_visual_fields:
            require(isinstance(replay[field], int) and replay[field] >= 0,
                    f"live replay {index} reports invalid {field}")
        require(
            replay["clear_tile_frames"] == 0,
            f"live replay {index} contains a reviewed clear-tile artifact",
        )
        require(
            replay["postsettle_wall_edge_artifact_frames"] == 0
            and replay["postsettle_red_green_artifact_frames"] == 0
            and replay["postsettle_weird_edge_tile_frames"] == 0,
            f"live replay {index} contains a reviewed wall-edge/color "
            "artifact",
        )
        fingerprint = replay["semantic_fingerprint_sha256"]
        require(SHA256_RE.fullmatch(fingerprint or "") is not None,
                f"live replay {index} semantic fingerprint is malformed")
        fingerprints[label].add(fingerprint)
        validated = dict(replay)
        validated["retargeted_state"] = retargeted_state
        validated["state_trace"] = trace_artifact
        validated["rendered_manifest"] = manifest_artifact
        validated_replays.append(validated)
    require(actual_pairs == expected_pairs,
            "live receipt replay matrix is incomplete")
    require(all(len(values) == 1 for values in fingerprints.values()),
            "duplicate live replays are not semantically deterministic")
    return {
        "receipt": str(resolved),
        "receipt_sha256": sha256(resolved),
        "schema": LIVE_SCHEMA,
        "archived_incompatible_capture": archived_incompatible,
        "native_capture_provenance": native_provenance,
        "captures": captures,
        "replays": validated_replays,
        "capture_count": len(captures),
        "replay_count": len(validated_replays),
        "scene0b_live": True,
        "menu_roundtrip": True,
        "deterministic": True,
    }


def bound_payload(
    live_path: Path, candidate: Path, candidate_sha256: str
) -> dict[str, Any]:
    live = validate_live_receipt(live_path, candidate, candidate_sha256)
    return {
        "schema": BOUND_SCHEMA,
        "status": "PASS",
        "candidate": str(candidate.resolve()),
        "candidate_sha256": candidate_sha256,
        "fixture": str(FIXTURE.resolve()),
        "fixture_sha256": sha256(FIXTURE),
        "archived_incompatible_capture": (
            live["archived_incompatible_capture"]
        ),
        "native_capture_provenance": live["native_capture_provenance"],
        "captures": live["captures"],
        "live_receipt": live["receipt"],
        "live_receipt_sha256": live["receipt_sha256"],
        "live_receipt_schema": live["schema"],
        "coverage": {
            "archived_incompatible_capture_count": 1,
            "candidate_native_capture_count": 1,
            "capture_count": live["capture_count"],
            "replay_count": live["replay_count"],
            "scene0b_live": live["scene0b_live"],
            "menu_roundtrip": live["menu_roundtrip"],
            "deterministic": live["deterministic"],
        },
        "tool_identity": expected_bound_tool_identity(),
        "failures": [],
    }


def validate_bound_receipt(
    path: Path,
    candidate: Path,
    candidate_sha256: str,
    expected_live_receipt: Path | None = None,
) -> dict[str, Any]:
    receipt = load_object(path.resolve(), "bound scene-$0B menu receipt")
    live_value = receipt.get("live_receipt")
    require(isinstance(live_value, str) and live_value,
            "bound scene-$0B receipt has no live receipt")
    live_path = Path(live_value).resolve()
    if expected_live_receipt is not None:
        require(live_path == expected_live_receipt.resolve(),
                "bound scene-$0B receipt uses an unconfigured live receipt")
    expected = bound_payload(live_path, candidate, candidate_sha256)
    require(receipt == expected,
            "bound scene-$0B receipt differs from revalidated live evidence")
    return expected


def scratch_output(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(
        root.exists() and resolved != root and resolved.is_relative_to(root)
        for root in roots
    ), "output must be below repo tmp/ or /mnt/data/tmp/")
    require(not resolved.exists(), f"refusing to overwrite output: {resolved}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--live-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate = args.rom.resolve()
    if not candidate.is_file():
        parser.error(f"candidate ROM is missing: {candidate}")
    try:
        output = scratch_output(args.output)
        payload = bound_payload(
            args.live_receipt.resolve(), candidate, sha256(candidate)
        )
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    except (ContractError, OSError, KeyError, TypeError, ValueError) as error:
        print(f"FAIL: scene-$0B captured/menu receipt: {error}")
        return 1
        print("PASS: both safe scene-$0B captures have live menu roundtrips")
    print(f"Receipt: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
