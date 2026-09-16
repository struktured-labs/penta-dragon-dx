#!/usr/bin/env python3
"""Exercise deep Stage 1 states and require exact packed-source tile copies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v301_gdma import (  # noqa: E402
    create_inline_tile_copy_postcomputed_attrs,
)
from build_v302_title_fix import (  # noqa: E402
    INLINE_ATTR_DECISION_HELPER_ADDR,
    STAGE1_ATOMIC_SETUP_ADDR,
    STAGE1_ATOMIC_WRAP_ADDR,
    STAGE1_HAZARD_PURE_MAP_ADDR,
    STAGE1_SOURCE_GENERATION_RST,
)
from diagnostics.normalize_mgba_state_pc import (  # noqa: E402
    retarget_rom_identity,
)

PROBE = ROOT / "scripts/diagnostics/probe_stage1_tilemap_copy.lua"
STATE_RETARGETER = (
    ROOT / "scripts/diagnostics/normalize_mgba_state_pc.py"
)
DEFAULT_STATES = (
    "level1_sara_w_alone.ss0",
)
STAGE1_SETUP_ROM_OFFSET = 0x37B13
PURE_COMPLETION_PATTERNS = (
    bytes.fromhex("F1 3D 28 03 F5 18 D1 C9"),
    # Live cache hits restore their bounded IE mask through the atomic wrap;
    # title/attract retain the trailing ordinary RET at this second pattern.
    bytes.fromhex("F1 3D 28 03 F5 18 D1 78 B7 C2 98 34 C9"),
    # Current live maps tail-call the fixed-bank hazard stamper after the
    # complete 24x24 tile plane is visible.  Break on the final RET after the
    # stamper and explicit EI; this remains the exact tile-copy completion,
    # not an implementation-internal row address.
    bytes.fromhex(
        "F1 3D 28 03 F5 18 D1 FA FD DC B7 C4 42 08 FB C9"
    ),
    # A register route token avoids even a fixed-bank CALL after ordinary
    # room-$03 and prerecorded copies while retaining hazard publication.
    bytes.fromhex("F1 3D 28 03 F5 18 D1 78 FE 05 C4 44 08 FB C9"),
    # Current three-cell atomic maps gate the Stage-1 post-copy hazard call on
    # D880 bit 3 before restoring IME. The final RET is still the unique point
    # at which the complete 24x24 tile plane is visible.
    bytes.fromhex(
        "F1 3D 28 03 F5 18 D1 FA 80 D8 E6 F7 FE 02 "
        "CC E2 10 FB C9"
    ),
)
STOCK_COPY_PREFIX = bytes.fromhex("2E 00 11 A0 C1 0E 08 06 18 F3")
STOCK_COPY_COMPLETION = 0x436D
WRAM_BG_TABLE_HIGH = 0xC6
STAGE1_WRAM_SCENE_GUARDS = (
    0xDBEA,
    0xDBE5,
    # The Stage-card palette handoff relocates the exact DBE5 guard so its
    # DBDF extension can own the first gameplay map flip.
    0xDBF1,
)
STAGE1_ATOMIC_WRAPS = (
    STAGE1_ATOMIC_WRAP_ADDR,
    # Stage-card handoff extension; the relocated wrapper is byte-identical.
    0xDBDF,
)
DOUBLE_BUFFER_PREFIX = bytes.fromhex(
    "2E 00 FA 80 D8 FE 02 F3 C2"
)
DOUBLE_BUFFER_COMPLETION_PATTERN = bytes.fromhex(
    "AF E0 4F 3C E0 70 AF FB C9"
)
STAGE1_LUT_ROM_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
CANONICAL_STAGE1_LUT_SHA256 = (
    "3b2d1224bb47c68263ff862f1a1c68d8b20f055fe2fcae0fa1028659d492961a"
)
# r438's reviewed tooth-art port uses the CGB VRAM-bank bit for these twelve
# tiles.  The low three bits remain palette 7.  This is deliberately a
# finite, raw-byte allowlist: it does not turn the LUT check into a generic
# "ignore bit 3" rule.
COMPILED_TOOTH_BANK_TILES = (*range(0x64, 0x6A), *range(0x74, 0x7A))
COMPILED_TOOTH_BANK_LUT_SHA256 = (
    "22de0c9f11d8b8f4f050c4e62928e7ea300b1d7483fb9df1d65bb6eec6a0527f"
)
REVIEWED_STAGE1_LUT_SHA256S = frozenset({
    CANONICAL_STAGE1_LUT_SHA256,
    COMPILED_TOOTH_BANK_LUT_SHA256,
})
PUBLICATION_ORACLE_SCHEMA = "penta-stage1-tilemap-publication-oracle-v1"
RECEIPT_SCHEMA = "penta-stage1-tilemap-publication-receipt-v2"
ORDINARY_ATTRIBUTE_SCOPE = "dirty-pre-semantic-overlay"
SEMANTIC_OVERLAY_OWNER = (
    "stage1-hazard-and-low-health-publication-gates"
)
CELLS_PER_PUBLICATION = 24 * 24
ROOM_OVERRIDE_EFFECTIVE_ROOM = 0x01
ROOM_OVERRIDE_TILES = (0x24, 0x27, 0x30, 0x33)
ROOM_OVERRIDE_PALETTE = 0x06
# These hashes own the Lua-side oracle dataflow, not merely its output field
# names.  Any edit to the independent expectation builder or completion
# comparator requires an explicit review and re-pin here.
EXPECTED_PLANE_BUILDER_SHA256 = (
    "5a621debbd6260e74c85f84da8b688823eaff5b41f861450f25e3ffeb2bd7162"
)
COMPLETION_COMPARATOR_SHA256 = (
    "af9e09bd587c056d7968b6b506a23db9db9c5eaa5d6ff9556807688f0c8d3585"
)
CANONICAL_LUT_LOAD_SHA256 = (
    "9527babf3736d9a2e212103fbc8d8762502b84710e0d8f12856db16afe2fe75b"
)
PUBLICATION_HANDOFF_SHA256 = (
    "064b2ccb6e677d2066f6184409a0bdd69c738bd72781c91fcc0e7a4f7f50075a"
)
REVIEWED_PROBE_SHA256 = (
    "fed90fdce1e0c1380aefee3c07be15ef7fd161c1b08c91927df6d625b7acf716"
)
COPIER_START = 0x42A7
COPIER_END = 0x436E
REVIEWED_POSTCOMPUTED_COPIER_SHA256 = (
    "5c63761997a29de257862e9703ec2e7f062d7e414bedb01595717f73749f557d"
)
R354_POSTCOMMIT_COPIER_SHA256 = (
    "6959dd43e9e52fc770c0f51617de59f9713904e730a7719648e9d29a1292ab6f"
)
# The retained r417+ production copier, including the d82/r451c lineage.
# Its distinct prefix is the precomputed two-plane path, not the older r354
# postcomputed form; provenance audit covers 270 immutable candidates.
R417_PRECOMPUTED_COPIER_SHA256 = (
    "e800c49742eba9eca00caf15ae897dcb2b7ddaaede42aa2487c79e3d402f49cf"
)
# r446 routes the separate later-stage stock entry at $42BB through the
# already-qualified mode-C bank-28 helper at $42C7.  The remainder of the
# r417 production copier, including the two publication completion calls, is
# byte-identical.  Keep this as an exact identity rather than treating helper
# routing as a generic equivalent implementation.
R446_LATER_STAGE_HELPER_COPIER_SHA256 = (
    "9022260d9f92cdb5f7a4717ab9f2b7d82ed2fab27da75b0faf12667b3041d08d"
)
REVIEWED_POSTCOMPUTED_COPIER_SHA256S = frozenset({
    REVIEWED_POSTCOMPUTED_COPIER_SHA256,
    R354_POSTCOMMIT_COPIER_SHA256,
})
REVIEWED_COPIER_SHA256S = frozenset({
    *REVIEWED_POSTCOMPUTED_COPIER_SHA256S,
    R417_PRECOMPUTED_COPIER_SHA256,
    R446_LATER_STAGE_HELPER_COPIER_SHA256,
})


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def receipt_tool_identity(mgba: Path) -> dict[str, dict[str, str]]:
    paths = {
        "verifier": Path(__file__).resolve(),
        "probe": PROBE.resolve(),
        "singleflight_launcher": mgba.resolve(),
        "state_retargeter": STATE_RETARGETER.resolve(),
    }
    return {
        name: {"path": str(path), "sha256": sha256_file(path)}
        for name, path in paths.items()
    }


def reviewed_stage1_lut(rom_bytes: bytes) -> bytes:
    """Return the immutable reviewed ordinary Stage-1 attribute table."""
    table = rom_bytes[
        STAGE1_LUT_ROM_OFFSET:STAGE1_LUT_ROM_OFFSET + 0x100
    ]
    digest = sha256_bytes(table)
    if len(table) != 0x100 or digest not in REVIEWED_STAGE1_LUT_SHA256S:
        raise ValueError(
            "candidate Stage-1 LUT is not the reviewed canonical semantic "
            f"table ({digest})"
        )
    return table


def reviewed_lut_identity(table: bytes) -> str:
    """Return the raw reviewed identity; retain canonical for mock controls."""
    raw = sha256_bytes(table)
    return raw if raw in REVIEWED_STAGE1_LUT_SHA256S else CANONICAL_STAGE1_LUT_SHA256


def reviewed_postcomputed_copier(rom_bytes: bytes) -> bytes:
    """Return one exact reviewed ordinary compiler/publication layout."""
    copier = rom_bytes[COPIER_START:COPIER_END]
    digest = sha256_bytes(copier)
    if (
        len(copier) != COPIER_END - COPIER_START
        or digest not in REVIEWED_COPIER_SHA256S
    ):
        raise ValueError(
            "candidate fixed-bank tile copier is not the reviewed "
            f"pre-semantic publication layout ({digest})"
        )
    return copier


def independent_expected_palette(
    tile: int, room: int, ffe5: int, canonical_lut: bytes,
) -> int:
    """Model the ordinary compiler without consulting mutable live C600."""
    if len(canonical_lut) != 0x100:
        raise ValueError("canonical Stage-1 LUT must be exactly 256 bytes")
    effective_room = ffe5 if ffe5 else room
    if (
        effective_room == ROOM_OVERRIDE_EFFECTIVE_ROOM
        and tile in ROOM_OVERRIDE_TILES
    ):
        return ROOM_OVERRIDE_PALETTE
    return canonical_lut[tile]


def independent_expected_plane(
    source: bytes, room: int, ffe5: int, canonical_lut: bytes,
) -> bytes:
    if len(source) != CELLS_PER_PUBLICATION:
        raise ValueError("publication source must be exactly 24x24 bytes")
    return bytes(
        independent_expected_palette(tile, room, ffe5, canonical_lut)
        for tile in source
    )


def probe_publication_oracle_failures(source: str) -> list[str]:
    """Fail closed if the Lua verdict is rewired to mutable live state."""
    failures: list[str] = []
    if sha256_bytes(source.encode()) != REVIEWED_PROBE_SHA256:
        failures.append("probe source differs from the reviewed oracle")
    required = (
        "local completion_source = packed_source()",
        "local wanted = expected[source_offset + 1]",
        "local wanted_attr = expected_attributes[source_offset + 1]",
        "pending_attributes = expected_attribute_plane(",
        "local tag = emu:read8(0xFF01)",
        "if tag == 0x99 then base = 0x9800",
        "elseif tag == 0x9D then base = 0x9C00",
        "ordinary_attribute_scope=dirty-pre-semantic-overlay",
        "semantic_overlay_owner=stage1-hazard-and-low-health-publication-gates",
        'handle:write("copier_sha256=" .. COPIER_SHA256 .. "\\n")',
        "source_changed_copies=%d",
        "publication_model_copies=%d",
        "ordinary_attribute_model_copies=%d",
    )
    for fragment in required:
        if fragment not in source:
            failures.append(f"probe is missing publication-oracle fragment: {fragment}")
    banned = (
        "local wanted = current[source_offset + 1]",
        "local wanted = completion_source[source_offset + 1]",
        "local wanted_attr = emu:read8(0xC600 + wanted)",
        "local wanted_attr = emu:read8(0xC600 + tile)",
    )
    for fragment in banned:
        if fragment in source:
            failures.append(f"probe self-grades through mutable state: {fragment}")

    def block(start: str, end: str, label: str) -> str:
        if source.count(start) != 1 or source.count(end) != 1:
            failures.append(f"probe {label} delimiters are not unique")
            return ""
        return source.split(start, 1)[1].split(end, 1)[0]

    code_without_comments = re.sub(r"--[^\n]*", "", source)
    if re.search(r"emu\s*:\s*read8\s*\(\s*0xC600", code_without_comments):
        failures.append("probe reads mutable live C600")

    lut_load = block(
        'local canonical_lut_file = assert(io.open(CANONICAL_LUT_PATH, "rb"))',
        "local function read_register(name)",
        "canonical-LUT load",
    )
    if sha256_bytes(lut_load.encode()) != CANONICAL_LUT_LOAD_SHA256:
        failures.append("canonical-LUT load differs from reviewed immutable flow")
    if len(re.findall(
        r"(?m)^\s*(?:local\s+)?canonical_lut\s*=", source,
    )) != 1:
        failures.append("canonical LUT is not assigned exactly once")

    builder = block(
        "local function independent_expected_palette(tile, room, ffe5)",
        "local function source_hash(bytes)",
        "expected-plane builder",
    )
    if sha256_bytes(builder.encode()) != EXPECTED_PLANE_BUILDER_SHA256:
        failures.append("expected-plane builder differs from reviewed dataflow")
    if re.search(r"emu\s*:\s*(?:read8|write8)", builder):
        failures.append("expected-plane builder reads or writes emulator state")
    if "raw_vram" in builder or re.search(r"0x(?:9800|9C00)", builder):
        failures.append("expected-plane builder reads a physical output plane")
    room_match = re.search(r"effective_room\s*==\s*0x([0-9A-Fa-f]+)", builder)
    palette_match = re.search(
        r"(?:tile\s*==[\s\S]*?)then\s+return\s+0x([0-9A-Fa-f]+)",
        builder,
    )
    lua_tiles = tuple(
        int(value, 16)
        for value in re.findall(r"tile\s*==\s*0x([0-9A-Fa-f]+)", builder)
    )
    if (
        builder.count(
            "local effective_room = ffe5 ~= 0 and ffe5 or room"
        ) != 1
        or builder.count(
            "return string.byte(canonical_lut, tile + 1)"
        ) != 1
        or builder.count(
            "expected[offset] = "
            "independent_expected_palette(tile, room, ffe5)"
        ) != 1
        or room_match is None
        or int(room_match.group(1), 16) != ROOM_OVERRIDE_EFFECTIVE_ROOM
        or lua_tiles != ROOM_OVERRIDE_TILES
        or palette_match is None
        or int(palette_match.group(1), 16) != ROOM_OVERRIDE_PALETTE
    ):
        failures.append("Lua/Python effective-room attribute semantics differ")

    compare = block(
        "local function compare_completed_copy(",
        "local function write_report()",
        "completion comparator",
    )
    if sha256_bytes(compare.encode()) != COMPLETION_COMPARATOR_SHA256:
        failures.append("completion comparator differs from reviewed dataflow")
    allowed_completion_source_lines = (
        "local completion_source = packed_source()",
        "local completion_tile = completion_source[source_offset + 1]",
        "completion_source = completion_tile,",
        'dump_bytes(OUT .. ".first.completion-source.bin", completion_source)',
    )
    observed_completion_source_lines = tuple(
        line.strip() for line in compare.splitlines()
        if "completion_source" in line
    )
    if observed_completion_source_lines != allowed_completion_source_lines:
        failures.append("completion source escapes its reviewed diagnostic flow")
    if len(re.findall(r"\bpacked_source\s*\(\s*\)", compare)) != 1:
        failures.append("completion comparator does not snapshot C1A0 exactly once")
    if re.search(r"\bexpected(?:_attributes)?\s*\[[^]]+\]\s*=", compare):
        failures.append("completion comparator mutates its entry-owned oracle")
    if len(re.findall(
        r"local\s+wanted\s*=\s*expected\[source_offset\s*\+\s*1\]",
        compare,
    )) != 1:
        failures.append("tile verdict is not uniquely entry-source owned")
    if len(re.findall(
        r"local\s+wanted_attr\s*=\s*"
        r"expected_attributes\[source_offset\s*\+\s*1\]",
        compare,
    )) != 1:
        failures.append("attribute verdict is not uniquely expected-plane owned")
    if re.search(
        r"(?:wanted|wanted_attr)\s*=\s*[^\n]*(?:completion_source|0xC600)",
        compare,
    ):
        failures.append("completion comparator grades from mutable live input")

    handoff = block(
        "  emu:setBreakpoint(function()\n"
        "    if emu:read8(0xD880) ~= 0x02 or "
        "emu:read8(0xFF99) ~= 1 then return end\n"
        '    local h = read_register("H")',
        'end)\n\ncallbacks:add("frame", function()',
        "entry-to-completion publication handoff",
    )
    if sha256_bytes(handoff.encode()) != PUBLICATION_HANDOFF_SHA256:
        failures.append("entry-to-completion handoff differs from reviewed flow")
    exact_handoff_fragments = (
        "pending_source = packed_source()",
        "pending_room = emu:read8(0xFFBD)",
        "pending_ffe5 = emu:read8(0xFFE5)",
        "pending_attributes = expected_attribute_plane(\n"
        "        pending_source, pending_room, pending_ffe5)",
        "compare_completed_copy(base, pending_source, pending_attributes, true)",
        "compare_completed_copy(\n"
        "      pending_base, pending_source, pending_attributes, false)",
    )
    for fragment in exact_handoff_fragments:
        if source.count(fragment) != 1:
            failures.append(
                "publication handoff fragment is not unique: " + fragment
            )
    for name in ("pending_source", "pending_attributes"):
        if len(re.findall(rf"(?m)^\s*{name}\s*=", source)) != 1:
            failures.append(f"{name} is not captured exactly once")
        if re.search(rf"\b{name}\s*\[[^]]+\]\s*=", source):
            failures.append(f"{name} is mutated after entry capture")

    tag_decode = block(
        'if ATOMIC_WRAP_MODE == "direct-map" then',
        "elseif STOCK_ORDER_WRAP then",
        "dirty destination decoder",
    )
    if (
        tag_decode.count("local tag = emu:read8(0xFF01)") != 1
        or tag_decode.count("tag == 0x99") != 1
        or tag_decode.count("tag == 0x9D") != 1
        or tag_decode.count("base = 0x9800") != 1
        or tag_decode.count("base = 0x9C00") != 1
        or not re.search(r"else\s+base\s*=\s*0\s+end", tag_decode)
        or re.search(r"tag\s*(?:&|%|//|>>|<<)", tag_decode)
    ):
        failures.append("dirty destination decoder is not exact 99/9D")
    return failures


def _report_int(
    report: dict[str, str], field: str, failures: list[str], label: str,
) -> int | None:
    try:
        return int(report[field])
    except (KeyError, ValueError):
        failures.append(f"{label}: missing or invalid {field}")
        return None


def publication_oracle_report_failures(
    report: dict[str, str], *, expected_rom_sha256: str,
    expected_copier_sha256: str = REVIEWED_POSTCOMPUTED_COPIER_SHA256,
    expected_lut_sha256: str = CANONICAL_STAGE1_LUT_SHA256,
    require_atomic: bool = True, label: str = "report",
) -> list[str]:
    """Validate one report without trusting aggregate coverage elsewhere."""
    failures: list[str] = []
    expected_text = {
        "oracle_schema": PUBLICATION_ORACLE_SCHEMA,
        "rom_sha256": expected_rom_sha256,
        "copier_sha256": expected_copier_sha256,
        "canonical_lut_sha256": expected_lut_sha256,
        "ordinary_attribute_scope": ORDINARY_ATTRIBUTE_SCOPE,
        "semantic_overlay_owner": SEMANTIC_OVERLAY_OWNER,
    }
    for field, expected in expected_text.items():
        if report.get(field) != expected:
            failures.append(f"{label}: {field} is not {expected}")

    fields = (
        "atomic_completions", "pure_completions", "wrap_hits", "exact_copies",
        "mismatch_copies", "mismatch_cells", "entry_mismatch_copies",
        "entry_mismatch_cells", "source_changed_copies",
        "source_changed_cells", "publication_model_copies",
        "publication_model_cells", "attribute_mismatch_copies",
        "attribute_mismatch_cells", "attribute_checked_copies",
        "attribute_unreadable_copies", "ordinary_attribute_model_copies",
        "ordinary_attribute_model_cells", "unmatched_wrap_hits",
        "wrong_destination_wrap_hits", "invalid_tile_row_events",
        "deferred_attribute_pending",
    )
    values = {
        field: _report_int(report, field, failures, label)
        for field in fields
    }
    if any(value is None for value in values.values()):
        return failures
    counts = {field: int(value) for field, value in values.items()}
    atomic = counts["atomic_completions"]
    pure = counts["pure_completions"]
    completions = atomic + pure
    if completions <= 0:
        failures.append(f"{label}: no tile publication completed")
    if require_atomic and atomic <= 0:
        failures.append(
            f"{label}: no owned dirty two-plane publication completed"
        )
    exact_contract = {
        "exact_copies": completions,
        "wrap_hits": atomic,
        "publication_model_copies": completions,
        "publication_model_cells": completions * CELLS_PER_PUBLICATION,
        "attribute_checked_copies": atomic,
        "ordinary_attribute_model_copies": atomic,
        "ordinary_attribute_model_cells": atomic * CELLS_PER_PUBLICATION,
    }
    for field, expected in exact_contract.items():
        if counts[field] != expected:
            failures.append(
                f"{label}: {field}={counts[field]} does not equal {expected}"
            )
    zero_fields = (
        "mismatch_copies", "mismatch_cells", "entry_mismatch_copies",
        "entry_mismatch_cells", "source_changed_copies",
        "source_changed_cells", "attribute_mismatch_copies",
        "attribute_mismatch_cells", "attribute_unreadable_copies",
        "unmatched_wrap_hits", "wrong_destination_wrap_hits",
        "invalid_tile_row_events", "deferred_attribute_pending",
    )
    for field in zero_fields:
        if counts[field] != 0:
            failures.append(f"{label}: {field}={counts[field]} is nonzero")
    destinations = {
        value for value in report.get("destinations", "").split(",") if value
    }
    if not destinations or not destinations <= {"9800", "9C00"}:
        failures.append(f"{label}: invalid or missing destinations")
    return failures


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def run_state(
    mgba: Path,
    rom: Path,
    state: Path | None,
    report: Path,
    frames: int,
    timeout: float,
    warm_reset: bool,
    force_pure: bool,
    trace_hash: str,
    rom_sha256: str,
    canonical_lut: bytes,
) -> dict[str, str]:
    runtime = report.parent / report.stem
    runtime.mkdir(exist_ok=True)
    report.unlink(missing_ok=True)
    done = runtime / "DONE"
    done.unlink(missing_ok=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    rom_bytes = runtime_rom.read_bytes()
    if sha256_bytes(rom_bytes) != rom_sha256:
        raise RuntimeError("isolated runtime ROM does not match the candidate")
    if reviewed_stage1_lut(rom_bytes) != canonical_lut:
        raise RuntimeError("isolated runtime ROM changed the canonical LUT")
    reviewed_copier = reviewed_postcomputed_copier(rom_bytes)
    reviewed_copier_sha256 = sha256_bytes(reviewed_copier)
    canonical_lut_path = runtime / "canonical-stage1-lut.bin"
    canonical_lut_path.write_bytes(canonical_lut)
    canonical_lut_sha256 = reviewed_lut_identity(canonical_lut)
    stock_copy = rom_bytes[
        0x42A7:0x42A7 + len(STOCK_COPY_PREFIX)
    ] == STOCK_COPY_PREFIX
    double_buffer = rom_bytes[
        0x42A7:0x42A7 + len(DOUBLE_BUFFER_PREFIX)
    ] == DOUBLE_BUFFER_PREFIX
    # Expanded release candidates route both completed-copy calls through an
    # always-mapped WRAM scene guard.  Stage 1 tail-enters the exact historical
    # hazard publisher; later dungeons return before paying its bank switch.
    # Recognize both strict layouts so the verifier locates completion from
    # generated source instead of mistaking a same-bank operand change for an
    # unknown copier.
    postcomputed_variants = [
        create_inline_tile_copy_postcomputed_attrs(
            INLINE_ATTR_DECISION_HELPER_ADDR + 3,
            STAGE1_ATOMIC_SETUP_ADDR,
            atomic_wrap_addr,
            post_copy_helper,
            STAGE1_SOURCE_GENERATION_RST,
            tagged_exact_destination=tagged,
        )
        for post_copy_helper in (
            STAGE1_HAZARD_PURE_MAP_ADDR,
            *STAGE1_WRAM_SCENE_GUARDS,
        )
        for atomic_wrap_addr in STAGE1_ATOMIC_WRAPS
        for tagged in (False, True)
    ]
    postcomputed_matches = [
        variant for variant in postcomputed_variants
        if rom_bytes[0x42A7:0x42A7 + len(variant)] == variant
    ]
    if len(postcomputed_matches) > 1:
        raise RuntimeError("postcomputed copier layout is ambiguous")
    current_postcomputed = (
        reviewed_copier_sha256 in REVIEWED_POSTCOMPUTED_COPIER_SHA256S
    )
    r417_precomputed = reviewed_copier_sha256 in (
        R417_PRECOMPUTED_COPIER_SHA256,
        R446_LATER_STAGE_HELPER_COPIER_SHA256,
    )
    postcomputed = current_postcomputed or bool(postcomputed_matches)
    postcomputed_inline = reviewed_copier if current_postcomputed else (
        postcomputed_matches[0]
        if postcomputed_matches else postcomputed_variants[0]
    )
    tile_row = 0xFFFF
    if r417_precomputed:
        # The r417 production layout is byte-pinned above.  It precomputes
        # attributes through the established $42CF row body. Its two $DBF1
        # calls are the pure and dirty tails respectively; bind completion to
        # the latter, whose FF01 physical-map tag names the actual destination.
        r417_calls = [
            index for index in range(0x42A7, 0x436B)
            if rom_bytes[index:index + 3] == bytes.fromhex("CD F1 DB")
        ]
        if r417_calls != [0x42F5, 0x4354]:
            raise RuntimeError("r417 precomputed completion calls changed")
        if rom_bytes[0x42F9:0x42FB] != bytes.fromhex("FB C9"):
            raise RuntimeError("r417 precomputed pure EI/RET changed")
        pure_completion = 0x42FA
        atomic_wrap = 0x349A
        atomic_row = atomic_first_tile_write = 0x42CF
        atomic_wrap_mode = "stock-order"
        atomic_wrap_segment = -1
    elif postcomputed:
        # Cache hits/title copies finish at this one shared EI/RET. Changed
        # Stage-1 maps branch to the attribute compiler immediately before it.
        pure_calls = [
            bytes([0xCD, helper & 0xFF, helper >> 8])
            for helper in (
                STAGE1_HAZARD_PURE_MAP_ADDR,
                *STAGE1_WRAM_SCENE_GUARDS,
            )
        ]
        pure_matches = [
            postcomputed_inline.find(call)
            for call in pure_calls
            # Tagged exact-destination builds intentionally use the same
            # post-copy guard on both pure and dirty completion.  The first
            # occurrence is the pure completion; the second is audited below
            # as the atomic completion.
            if postcomputed_inline.count(call) in (1, 2)
        ]
        if len(pure_matches) != 1:
            raise RuntimeError("postcomputed pure completion is not unique")
        pure_offset = pure_matches[0]
        pure_tail = postcomputed_inline[pure_offset:pure_offset + 3]
        # Untagged layouts return immediately after CALL. Tagged layouts keep
        # five reserved bytes before the same EI/RET so the dirty branch can
        # retain exact width. Bind completion to that first EI/RET, not to a
        # hard-coded pad length.
        pure_return = postcomputed_inline.find(
            bytes.fromhex("FB C9"), pure_offset + len(pure_tail),
            pure_offset + len(pure_tail) + 8,
        )
        if pure_return < 0:
            raise RuntimeError("postcomputed pure EI/RET is missing")
        pure_completion = 0x42A7 + pure_return + 1
        common_setup = bytes.fromhex("11 A0 C1 3E 18 F5")
        common_offset = postcomputed_inline.find(common_setup)
        if common_offset < 0 or postcomputed_inline.count(common_setup) != 1:
            raise RuntimeError("postcomputed tile-row entry is not unique")
        tile_row = 0x42A7 + common_offset + len(common_setup)
    elif stock_copy or double_buffer:
        # The unmodified game finishes its 24x24 copy at the RET at $436D.
        # Supporting it here lets the same long-running gate prove that a
        # production candidate restored the timing-sensitive stock routine.
        pure_completion = (
            STOCK_COPY_COMPLETION if stock_copy else 0xFFFF
        )
    else:
        pure_matches = [
            (index, pattern)
            for pattern in PURE_COMPLETION_PATTERNS
            for index in range(
                0x42A7, 0x436E - len(pattern) + 1
            )
            if rom_bytes[index:index + len(pattern)] == pattern
        ]
        if len(pure_matches) != 1:
            raise RuntimeError("candidate pure-copy completion is not unique")
        pure_index, pure_pattern = pure_matches[0]
        pure_completion = pure_index + len(pure_pattern) - 1
    atomic_wrap_mode = "stock-order"
    atomic_wrap_segment = -1
    if stock_copy:
        # A stock-copier isolation build intentionally has neither an atomic
        # row nor its exit. Keep inert breakpoint addresses so the same probe
        # can still prove every native tile-only completion byte-for-byte.
        atomic_wrap = atomic_row = atomic_first_tile_write = 0xFFFF
        atomic_wrap_mode = "disabled"
    elif r417_precomputed:
        # Decoded and byte-bound above; do not fall through to the historical
        # atomic-wrapper signature search.
        pass
    elif double_buffer:
        completion_matches = [
            index
            for index in range(
                0x42A7,
                0x436E - len(DOUBLE_BUFFER_COMPLETION_PATTERN) + 1,
            )
            if rom_bytes[
                index:index + len(DOUBLE_BUFFER_COMPLETION_PATTERN)
            ] == DOUBLE_BUFFER_COMPLETION_PATTERN
        ]
        if len(completion_matches) != 1:
            raise RuntimeError(
                "double-buffer completion is not unique"
            )
        # Break on EI after both GDMA planes have completed. Unlike the
        # row-wise atomic copier, H is already the exact $98/$9C map base.
        atomic_wrap = completion_matches[0] + 7
        atomic_row = atomic_first_tile_write = 0xFFFF
        atomic_wrap_mode = "direct-map"
        atomic_wrap_segment = 1
    elif postcomputed:
        # Break at the second post-copy call: the complete tile and attribute
        # planes have been published, but the selective hazard overlay has not
        # yet borrowed registers or intentionally changed tooth attributes.
        # The first identical call belongs to the pure path.
        postcopy_call = pure_tail
        postcopy_offsets = [
            index for index in range(len(postcomputed_inline) - 2)
            if postcomputed_inline[index:index + 3] == postcopy_call
        ]
        if len(postcopy_offsets) != 2:
            raise RuntimeError("postcomputed atomic completion is not unique")
        atomic_wrap = 0x42A7 + postcopy_offsets[-1]
        atomic_row = atomic_first_tile_write = 0xFFFF
        atomic_wrap_mode = "direct-map"
        atomic_wrap_segment = 1
    else:
        # The completed map is already stable on entry to the atomic wrapper.
        # Break before its hazard publisher can legitimately use H as scratch;
        # the older EI/RET/RETI fallback remains for historical candidates.
        atomic_wrap_entries = [
            index
            for index in range(0x3482, 0x34A3)
            if rom_bytes[index:index + 4] in (
                bytes.fromhex("CD 42 08 F3"),
                bytes.fromhex("C4 42 08 F3"),
            )
        ]
        atomic_wrap_returns = [
            index
            for index in range(0x3482, 0x34A3)
            if (
                rom_bytes[index:index + 2] == bytes.fromhex("FB C9")
                or rom_bytes[index] == 0xD9
            )
        ]
        atomic_wrap_matches = atomic_wrap_entries or atomic_wrap_returns
        if len(atomic_wrap_matches) != 1:
            raise RuntimeError(
                "candidate atomic wrapper completion is not unique"
            )
        atomic_wrap = atomic_wrap_matches[0]

        atomic_row_matches = [
            index
            for index in range(0x42A7, pure_completion)
            if rom_bytes[index:index + 6]
            in (
                bytes([0x06, WRAM_BG_TABLE_HIGH, 0x3E, 0x06, 0xE0, 0xE0]),
                bytes([0x06, WRAM_BG_TABLE_HIGH, 0x3E, 0x08, 0xE0, 0xE0]),
            )
        ]
        if len(atomic_row_matches) != 1:
            raise RuntimeError("candidate atomic-row entry is not unique")
        atomic_row = atomic_row_matches[0]
        atomic_first_tile_write = rom_bytes.find(
            bytes.fromhex("1A 13 22"), atomic_row + 6, pure_completion
        )
        if atomic_first_tile_write < 0:
            raise RuntimeError("candidate atomic tile writer is missing")

    setup_path = ""
    runtime_state: Path | None = None
    if state is not None:
        if rom_bytes[
            STAGE1_SETUP_ROM_OFFSET:STAGE1_SETUP_ROM_OFFSET + 4
        ] in (
            bytes.fromhex("78 E0 A5 F3"),
            bytes.fromhex("78 E0 E1 F3"),
            bytes.fromhex("7C E0 A5 F3"),
        ):
            # Current route-caching setup: preserve the caller's B token in
            # the historical latch before entering the bounded interrupt
            # window. The r316 release layout relocates that latch elsewhere.
            setup_length = 14
        elif rom_bytes[
            STAGE1_SETUP_ROM_OFFSET:STAGE1_SETUP_ROM_OFFSET + 2
        ] == bytes.fromhex("F3 C9"):
            setup_length = 2
        elif (
            rom_bytes[STAGE1_SETUP_ROM_OFFSET] == 0xF3
            and rom_bytes[STAGE1_SETUP_ROM_OFFSET + 10] == 0xC9
        ):
            setup_length = 11
        elif rom_bytes[STAGE1_SETUP_ROM_OFFSET] == 0xF3:
            # The compact FFBA setup and former FFE0/direct-D880 variants all
            # begin with DI; their terminal RET distinguishes 13/14/15 bytes.
            if rom_bytes[STAGE1_SETUP_ROM_OFFSET + 12] == 0xC9:
                setup_length = 13
            elif rom_bytes[STAGE1_SETUP_ROM_OFFSET + 13] == 0xC9:
                setup_length = 14
            else:
                setup_length = 15
        else:
            setup_length = 14
        setup = rom_bytes[
            STAGE1_SETUP_ROM_OFFSET:
            STAGE1_SETUP_ROM_OFFSET + setup_length
        ]
        if len(setup) != setup_length or setup[0] not in (0x11, 0x78, 0x7C, 0xF3):
            raise RuntimeError("candidate Stage 1 setup is missing or malformed")
        setup_file = runtime / "stage1_atomic_setup.bin"
        setup_file.write_bytes(setup)
        setup_path = str(setup_file)
        # Historical fixtures carry the source ROM CRC/header identity.  A
        # changed candidate otherwise makes mGBA reject the state and boot the
        # title, producing a vacuous zero-publication run.  Retarget only the
        # five reviewed identity bytes; CPU, mapper, RAM, VRAM, and PPU state
        # remain byte exact.
        runtime_state = runtime / "retargeted-state.ss0"
        retarget_rom_identity(state, runtime_state, runtime_rom)

    env = os.environ.copy()
    env.update(
        {
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "STAGE1_TILEMAP_OUT": str(report),
            "STAGE1_TILEMAP_DONE": str(done),
            "STAGE1_TILEMAP_FRAMES": str(frames),
            "STAGE1_TILEMAP_WARM_RESET": "1" if warm_reset else "0",
            "STAGE1_TILEMAP_SETUP": setup_path,
            "STAGE1_TILEMAP_FORCE_PURE": "1" if force_pure else "0",
            "STAGE1_TILEMAP_TRACE_HASH": trace_hash,
            "STAGE1_TILEMAP_CANONICAL_LUT": str(canonical_lut_path),
            "STAGE1_TILEMAP_CANONICAL_LUT_SHA256": (
                canonical_lut_sha256
            ),
            "STAGE1_TILEMAP_ROM_SHA256": rom_sha256,
            "STAGE1_TILEMAP_COPIER_SHA256": (
                reviewed_copier_sha256
            ),
            "STAGE1_TILEMAP_ORACLE_SCHEMA": PUBLICATION_ORACLE_SCHEMA,
            "STAGE1_TILEMAP_PURE_COMPLETION": f"{pure_completion:04X}",
            "STAGE1_TILEMAP_ATOMIC_WRAP": f"{atomic_wrap:04X}",
            "STAGE1_TILEMAP_ATOMIC_ROW": f"{atomic_row:04X}",
            "STAGE1_TILEMAP_ATOMIC_FIRST_WRITE": (
                f"{atomic_first_tile_write:04X}"
            ),
            "STAGE1_TILEMAP_ATOMIC_WRAP_MODE": atomic_wrap_mode,
            "STAGE1_TILEMAP_ATOMIC_WRAP_SEGMENT": str(atomic_wrap_segment),
            "STAGE1_TILEMAP_TILE_ROW": f"{tile_row:04X}",
            "STAGE1_TILEMAP_R417_PRECOMPUTED": "1" if r417_precomputed else "0",
        }
    )
    command = [str(mgba), "--fastforward"]
    if runtime_state is not None:
        command.extend(["-t", str(runtime_state)])
    command.extend(
        [
            str(runtime_rom),
            "--script",
            str(PROBE),
            "-C",
            f"savegamePath={runtime}",
        ]
    )
    log = (runtime / "mgba.log").open("w")
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if (
                done.is_file()
                and done.read_text() == "complete\n"
                and report.is_file()
                and report.stat().st_size
            ):
                return parse_report(report)
            if process.poll() is not None:
                break
            time.sleep(0.05)
        raise RuntimeError(f"no report within {timeout:.1f}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        log.close()


def _synthetic_passing_report(rom_sha256: str) -> dict[str, str]:
    return {
        "oracle_schema": PUBLICATION_ORACLE_SCHEMA,
        "rom_sha256": rom_sha256,
        "copier_sha256": REVIEWED_POSTCOMPUTED_COPIER_SHA256,
        "canonical_lut_sha256": CANONICAL_STAGE1_LUT_SHA256,
        "ordinary_attribute_scope": ORDINARY_ATTRIBUTE_SCOPE,
        "semantic_overlay_owner": SEMANTIC_OVERLAY_OWNER,
        "atomic_completions": "1",
        "pure_completions": "1",
        "wrap_hits": "1",
        "exact_copies": "2",
        "mismatch_copies": "0",
        "mismatch_cells": "0",
        "entry_mismatch_copies": "0",
        "entry_mismatch_cells": "0",
        "source_changed_copies": "0",
        "source_changed_cells": "0",
        "publication_model_copies": "2",
        "publication_model_cells": str(2 * CELLS_PER_PUBLICATION),
        "attribute_mismatch_copies": "0",
        "attribute_mismatch_cells": "0",
        "attribute_checked_copies": "1",
        "attribute_unreadable_copies": "0",
        "ordinary_attribute_model_copies": "1",
        "ordinary_attribute_model_cells": str(CELLS_PER_PUBLICATION),
        "unmatched_wrap_hits": "0",
        "wrong_destination_wrap_hits": "0",
        "invalid_tile_row_events": "0",
        "deferred_attribute_pending": "0",
        "destinations": "9800,9C00",
    }


def self_test() -> int:
    """Exercise false-pass mutations without starting an emulator."""
    source_text = PROBE.read_text()
    failures = probe_publication_oracle_failures(source_text)
    if failures:
        raise AssertionError(f"current probe contract failed: {failures}")
    source_mutation = source_text.replace(
        "local wanted = expected[source_offset + 1]",
        "local wanted = completion_source[source_offset + 1]",
        1,
    )
    if not probe_publication_oracle_failures(source_mutation):
        raise AssertionError("completion-time C1A0 mutation was accepted")
    lut_mutation = source_text.replace(
        "local wanted_attr = expected_attributes[source_offset + 1]",
        "local wanted_attr = emu:read8(0xC600 + wanted)",
        1,
    )
    if not probe_publication_oracle_failures(lut_mutation):
        raise AssertionError("live-C600 self-grading mutation was accepted")
    probe_controls = {
        "builder reads live C600": (
            "expected[offset] = "
            "independent_expected_palette(tile, room, ffe5)",
            "expected[offset] = emu:read8(0xC600 + tile)",
        ),
        "builder ignores FFE5": (
            "local effective_room = ffe5 ~= 0 and ffe5 or room",
            "local effective_room = room",
        ),
        "builder ignores FFBD fallback": (
            "local effective_room = ffe5 ~= 0 and ffe5 or room",
            "local effective_room = ffe5",
        ),
        "builder discards canonical LUT": (
            "return string.byte(canonical_lut, tile + 1)",
            "return 0x00",
        ),
        "builder bypasses palette model": (
            "expected[offset] = "
            "independent_expected_palette(tile, room, ffe5)",
            "expected[offset] = tile & 0x07",
        ),
        "canonical LUT is replaced after load": (
            "assert(#canonical_lut == 0x100,\n"
            '  "Stage-1 canonical attribute LUT must be exactly 256 bytes")',
            "assert(#canonical_lut == 0x100,\n"
            '  "Stage-1 canonical attribute LUT must be exactly 256 bytes")\n'
            "canonical_lut = string.rep(string.char(0), 0x100)",
        ),
        "entry attributes are overwritten from live C600": (
            "      pending_attributes = expected_attribute_plane(\n"
            "        pending_source, pending_room, pending_ffe5)",
            "      pending_attributes = expected_attribute_plane(\n"
            "        pending_source, pending_room, pending_ffe5)\n"
            "      for offset, tile in ipairs(pending_source) do\n"
            "        pending_attributes[offset] = "
            "emu:read8(0xC600 + tile)\n"
            "      end",
        ),
        "dirty completion recaptures source": (
            "    compare_completed_copy(base, pending_source, "
            "pending_attributes, true)",
            "    pending_source = packed_source()\n"
            "    compare_completed_copy(base, pending_source, "
            "pending_attributes, true)",
        ),
        "dirty completion rebuilds attributes from completion source": (
            "    compare_completed_copy(base, pending_source, "
            "pending_attributes, true)",
            "    pending_attributes = expected_attribute_plane(\n"
            "      packed_source(), pending_room, pending_ffe5)\n"
            "    compare_completed_copy(base, pending_source, "
            "pending_attributes, true)",
        ),
        "comparator overwrites entry oracle": (
            "      local wanted = expected[source_offset + 1]",
            "      expected[source_offset + 1] = "
            "completion_source[source_offset + 1]\n"
            "      local wanted = expected[source_offset + 1]",
        ),
        "comparator aliases completion source": (
            "      local wanted = expected[source_offset + 1]",
            "      local completion_alias = "
            "completion_source[source_offset + 1]\n"
            "      local wanted = completion_alias",
        ),
        "dirty tag decoder accepts aliases": (
            "if tag == 0x99 then base = 0x9800\n"
            "      elseif tag == 0x9D then base = 0x9C00",
            "if (tag & 0xFC) == 0x98 then base = 0x9800\n"
            "      elseif (tag & 0xFC) == 0x9C then base = 0x9C00",
        ),
    }
    for label, (old, new) in probe_controls.items():
        mutation = source_text.replace(old, new, 1)
        if mutation == source_text:
            raise AssertionError(f"offline probe control did not mutate: {label}")
        if not probe_publication_oracle_failures(mutation):
            raise AssertionError(f"offline probe control was accepted: {label}")

    canonical = bytes(index & 0x07 for index in range(0x100))
    entry = bytes([0x24, 0x27, 0x30, 0x33] + [0x41] * 572)
    expected = independent_expected_plane(entry, 0x12, 0x01, canonical)
    completion_source = bytes([0x42]) + entry[1:]
    live_c600 = bytearray(canonical)
    live_c600[0x41] = 0
    if expected[:4] != bytes([6, 6, 6, 6]):
        raise AssertionError("effective-room wall override is not modeled")
    if independent_expected_plane(entry, 0x12, 0x01, canonical) != expected:
        raise AssertionError("entry-owned expected plane is unstable")
    if completion_source == entry or live_c600 == canonical:
        raise AssertionError("offline source/LUT controls did not mutate")
    if expected[4] == live_c600[0x41]:
        raise AssertionError("canonical and corrupt live-LUT controls alias")

    rom_sha256 = "a" * 64
    valid = _synthetic_passing_report(rom_sha256)
    if publication_oracle_report_failures(
        valid, expected_rom_sha256=rom_sha256,
    ):
        raise AssertionError("valid synthetic publication report was rejected")
    controls = {
        "entry A -> completion B -> VRAM B": {
            "source_changed_copies": "1", "source_changed_cells": "1",
        },
        "canonical attr 6 -> live C600 0 -> VRAM 0": {
            "attribute_mismatch_copies": "1",
            "attribute_mismatch_cells": "1",
        },
        "pure-only attribute-vacuity": {
            "atomic_completions": "0", "pure_completions": "2",
            "exact_copies": "2", "attribute_checked_copies": "0",
            "ordinary_attribute_model_copies": "0",
            "ordinary_attribute_model_cells": "0",
        },
        "fixture with no publication": {
            "atomic_completions": "0", "pure_completions": "0",
            "exact_copies": "0", "publication_model_copies": "0",
            "publication_model_cells": "0",
            "attribute_checked_copies": "0",
            "ordinary_attribute_model_copies": "0",
            "ordinary_attribute_model_cells": "0",
        },
        "incomplete expected-plane ownership": {
            "ordinary_attribute_model_copies": "0",
        },
    }
    for label, changes in controls.items():
        mutated = dict(valid)
        mutated.update(changes)
        if not publication_oracle_report_failures(
            mutated, expected_rom_sha256=rom_sha256,
        ):
            raise AssertionError(f"offline false-pass control accepted: {label}")
    print("PASS: Stage-1 tilemap publication oracle mutation controls")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path, nargs="?")
    parser.add_argument(
        "--states", type=Path, default=ROOT / "save_states_for_claude"
    )
    parser.add_argument(
        "--state", action="append", dest="state_names", default=[]
    )
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--timeout", type=float, default=12.0)
    parser.add_argument("--warm-reset", action="store_true")
    parser.add_argument("--force-pure", action="store_true")
    parser.add_argument("--trace-hash", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--mgba", type=Path,
        default=ROOT / "scripts/mgba-qt-singleflight",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="run publication-oracle mutation controls without an emulator",
    )
    args = parser.parse_args()

    if args.self_test:
        if args.rom is not None or args.output is not None:
            parser.error("--self-test does not accept ROM or --output")
        return self_test()
    if args.rom is None:
        parser.error("ROM is required")
    rom = args.rom.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    mgba = args.mgba.resolve()
    guarded_mgba = (ROOT / "scripts/mgba-qt-singleflight").resolve()
    if mgba != guarded_mgba:
        parser.error("--mgba must be the checked-in single-flight wrapper")
    probe_failures = probe_publication_oracle_failures(PROBE.read_text())
    if probe_failures:
        parser.error("; ".join(probe_failures))
    rom_bytes = rom.read_bytes()
    rom_sha256 = sha256_bytes(rom_bytes)
    try:
        canonical_lut = reviewed_stage1_lut(rom_bytes)
        reviewed_copier = reviewed_postcomputed_copier(rom_bytes)
        reviewed_copier_sha256 = sha256_bytes(reviewed_copier)
    except ValueError as error:
        parser.error(str(error))

    names = tuple(args.state_names) or DEFAULT_STATES
    failures: list[str] = []
    total_completions = 0
    total_atomic_completions = 0
    report_receipts: list[dict[str, object]] = []
    all_reports_oracle_exact = True
    owned_temp = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        (ROOT / "tmp").mkdir(parents=True, exist_ok=True)
        owned_temp = tempfile.TemporaryDirectory(
            prefix="penta-stage1-tilemap-", dir=ROOT / "tmp",
        )
        output = Path(owned_temp.name)
    for name in names:
        state = None if name == "cold" else (args.states / name).resolve()
        if state is not None and not state.is_file():
            failures.append(f"{name}: missing state")
            continue
        stem = "cold" if state is None else state.stem
        report_path = output / f"{stem}.report"
        try:
            report = run_state(
                mgba, rom, state,
                report_path, args.frames, args.timeout, args.warm_reset,
                args.force_pure, args.trace_hash, rom_sha256,
                canonical_lut,
            )
            atomic = int(report["atomic_completions"])
            pure = int(report["pure_completions"])
            completions = atomic + pure
            mismatches = int(report["mismatch_cells"])
            attribute_mismatches = int(report["attribute_mismatch_cells"])
            total_completions += completions
            total_atomic_completions += atomic
            print(
                f"{name}: entries={report['copy_entries']} "
                f"atomic={atomic} pure={pure} "
                f"wrap_hits={report['wrap_hits']} "
                f"exact={report['exact_copies']} "
                f"mismatches={mismatches} "
                f"attr_mismatches={attribute_mismatches} "
                f"maps={report['destinations']} "
                f"scene={report['final_scene']} "
                f"active={report['final_active']} "
                f"warm_reset={report['warm_reset']} "
                f"setup={report['runtime_setup']}"
                f" force_pure={report['force_pure']}"
            )
            print(
                f"  entry_h={report['entry_h_values']} "
                f"wrap_a={report['wrap_a_values']} "
                f"wrap_h={report['wrap_h_values']}"
            )
            report_failures = publication_oracle_report_failures(
                report,
                expected_rom_sha256=rom_sha256,
                expected_copier_sha256=reviewed_copier_sha256,
                expected_lut_sha256=reviewed_lut_identity(canonical_lut),
                require_atomic=not args.force_pure,
                label=name,
            )
            if report_failures:
                all_reports_oracle_exact = False
                failures.extend(report_failures)
            if mismatches:
                failures.append(f"{name}: {report['first_mismatch']}")
            if attribute_mismatches:
                failures.append(
                    f"{name}: {report['first_attribute_mismatch']}"
                )
            report_receipts.append({
                "state_name": name,
                "state_path": str(state) if state is not None else None,
                "state_sha256": (
                    sha256_file(state) if state is not None else None
                ),
                "retargeted_state_path": (
                    str((report_path.parent / report_path.stem
                         / "retargeted-state.ss0").resolve())
                    if state is not None else None
                ),
                "retargeted_state_sha256": (
                    sha256_file(
                        report_path.parent / report_path.stem
                        / "retargeted-state.ss0"
                    ) if state is not None else None
                ),
                "retarget_mode": (
                    "ROM_IDENTITY_ONLY" if state is not None else None
                ),
                "report_path": str(report_path.resolve()),
                "report_sha256": sha256_file(report_path),
                "atomic_completions": atomic,
                "pure_completions": pure,
                "exact_copies": int(report["exact_copies"]),
                "destinations": sorted({
                    value for value in report["destinations"].split(",")
                    if value
                }),
            })
        except Exception as exc:
            all_reports_oracle_exact = False
            failures.append(f"{name}: {exc}")

    if total_completions == 0:
        failures.append("no Stage 1 tile publication completed")
    if not args.force_pure and total_atomic_completions == 0:
        failures.append("no Stage 1 dirty two-plane publication completed")
    candidate_unchanged = sha256_file(rom) == rom_sha256
    if not candidate_unchanged:
        failures.append("candidate ROM changed during tilemap verification")
    requested_states_completed = len(report_receipts) == len(names)
    if not requested_states_completed:
        failures.append("not every requested tilemap fixture completed")
    dirty_publication_in_every_report = bool(report_receipts) and all(
        int(item["atomic_completions"]) > 0 for item in report_receipts
    )
    if not args.force_pure and not dirty_publication_in_every_report:
        failures.append(
            "not every tilemap fixture completed a dirty two-plane publication"
        )

    if args.output:
        receipt = {
            "schema": RECEIPT_SCHEMA,
            "status": "PASS" if not failures else "FAIL",
            "candidate": str(rom),
            "candidate_sha256": rom_sha256,
            "configuration": {
                "states_root": str(args.states.resolve()),
                "state_names": list(names),
                "frames": args.frames,
                "timeout_seconds": args.timeout,
                "warm_reset": args.warm_reset,
                "force_pure": args.force_pure,
                "trace_hash": args.trace_hash,
                "mgba": str(mgba),
            },
            "oracle": {
                "schema": PUBLICATION_ORACLE_SCHEMA,
                "canonical_lut_sha256": reviewed_lut_identity(canonical_lut),
                "copier_sha256": reviewed_copier_sha256,
                "ordinary_attribute_scope": ORDINARY_ATTRIBUTE_SCOPE,
                "semantic_overlay_owner": SEMANTIC_OVERLAY_OWNER,
            },
            "tool_identity": receipt_tool_identity(mgba),
            "reports": report_receipts,
            "totals": {
                "requested_states": len(names),
                "completed_reports": len(report_receipts),
                "completions": total_completions,
                "atomic_completions": total_atomic_completions,
                "destinations": sorted({
                    destination
                    for item in report_receipts
                    for destination in item["destinations"]
                }),
            },
            "checks": {
                "candidate ROM unchanged": candidate_unchanged,
                "all requested fixtures completed": requested_states_completed,
                "every report passed the immutable publication oracle": (
                    all_reports_oracle_exact
                ),
                "every fixture exercised dirty two-plane publication": (
                    dirty_publication_in_every_report
                    if not args.force_pure else True
                ),
            },
            "failures": failures,
        }
        (output / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )

    try:
        if failures:
            print("\nFAIL:")
            for failure in failures:
                print(f"  - {failure}")
            return 1
        print(
            f"\nPASS: {total_completions} completed Stage 1 tile publications "
            f"({total_atomic_completions} dirty two-plane) matched their "
            "publication-owned expected planes exactly."
        )
        if args.output:
            print(f"Receipt: {(output / 'receipt.json').resolve()}")
        return 0
    finally:
        if owned_temp is not None:
            owned_temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
