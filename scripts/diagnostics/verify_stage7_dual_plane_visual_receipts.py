#!/usr/bin/env python3
"""Fail-closed offline audit for two Stage-7 later-soak receipts.

This does not run an emulator.  It consumes two independently captured
``verify_later_stage_soak.py`` output directories made with Stage 7 only,
``--frames 8000 --sample-interval 1 --capture-stable 4 --layout-trace
--semantic-write-trace --flip-states --wram-audit
--require-r265-window-equivalence``.

The ordinary soak rejects known palette bleed before a map is displayed, but
the installed mGBA Lua raw-VRAM domain exposes bank 0 only.  This companion
gate extracts the official ``gbAs`` payload from a savestate made at every
publication breakpoint and is stricter at every stable room receipt:

* each natural $12E0 destination map's guaranteed populated rectangle must
  equal the same-instruction packed C1A0 source;
* C600 must equal the candidate's immutable Stage-7 LUT, and every guaranteed
  populated bank-1 attribute must exactly equal it for that state's tile ID;
* both physical maps and the four deterministic Stage-7 rooms must be seen;
* no observed viewport may expose the eight padding columns/rows; and
* no active-visible CPU write may transiently mismatch tile and attribute; and
* both runs' ordinary artifacts and decompressed machine states must be
  deterministic.

For r273, the static receipt binds that populated rectangle to rows 0..19 and
semantic columns 0..23.  Every admitted pending viewport is additionally
checked against the smaller visible union (rows 0..19, columns 0..21).  The
cropped rows 20..23 and padding columns 24..31 are deliberately not promoted
to an equality claim.

It checks restored FF55/VBK/SVBK/IE/IME state at each publication boundary,
but deliberately makes no claim about the helper's transient interior,
menus, transitions hidden by the fade, or Crystal Dragon.  Those require the
separate ABI instrumentation and containment routes.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any
import zlib


ROOT = Path(__file__).resolve().parents[2]
SOAK_PROBE = ROOT / "scripts/diagnostics/probe_later_stage_soak.lua"
SOAK_VERIFIER = ROOT / "scripts/diagnostics/verify_later_stage_soak.py"
SOAK_LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
EXPECTED_ROOMS = {0x01, 0x03, 0x05, 0x07}
EXPECTED_MAPS = {0x9800, 0x9C00}
LIVE_EXPECTED_PUBLISHERS = {0x12E0}
KNOWN_PUBLISHERS = {0x12E0, 0x3095}
EXPECTED_CANDIDATE_SHA256 = (
    "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
)
EXPECTED_STATIC_RECEIPT_SHA256 = (
    "4e35d5f659a5ab7339bb37fe630118d69b541368deeab7f4aae4cabf121abac0"
)
MIN_READABLE_FLIPS_PER_MAP = 10
MIN_LAYOUT_SAMPLES = 100
GB_STATE_SIZE = 0x11800
GB_STATE_MAGIC = 0x00400003
CPU_A = 0x0020
CPU_PC = 0x002A
VIDEO_CURRENT_VRAM_BANK = 0x00CC
MEMORY_CURRENT_ROM_BANK = 0x0168
MEMORY_CURRENT_WRAM_BANK = 0x016A
MEMORY_FLAGS = 0x0194
IO = 0x0300
HRAM = 0x0380
IE = 0x03FF
VRAM0 = 0x0400
VRAM1 = 0x2400
WRAM0 = 0x4400
WRAM1 = 0x5400
MEMORY_FLAG_IME = 1 << 3
MEMORY_FLAG_HDMA_ACTIVE = 1 << 4
STAGE7_LUT_SLOTS = {0, 2, 4, 5}
STAGE7_LUT_ROM_OFFSET = 22 * 0x4000 + 0x7600 - 0x4000
STAGE7_REQUIRED_LUT_VALUES = {
    **{tile: 2 for tile in (0xAE, 0xAF, 0xBE, 0xBF,
                            0xC6, 0xC7, 0xD6, 0xD7)},
    **{tile: 4 for tile in (0xA0, 0xA1, 0xB0, 0xB1)},
    **{tile: 5 for tile in (0x19, 0x1A)},
}
R320_PRIMARY_PUBLISHER = bytes.fromhex(
    "F3 F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 FA 0B DC B7 3E 83 28 02 "
    "CB DF E0 40 FB C9"
)
R346_PRIMARY_PUBLISHER = bytes.fromhex(
    "F3 00 F0 40 87 30 06 F0 44 FE 90 38 FA "
    "FA 00 DC E6 0F E0 43 FA 02 DC E6 0F E0 42 "
    "F0 40 EE 08 E0 40 FB C9"
)
LEGACY_PRIMARY_PUBLISHER = bytes.fromhex(
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40 "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 C9"
)
PRIMARY_PUBLISHER_VARIANTS = {
    "legacy-v1": LEGACY_PRIMARY_PUBLISHER,
    "r320-v1": R320_PRIMARY_PUBLISHER,
    "r346-vblank-v1": R346_PRIMARY_PUBLISHER,
}
PRIMARY_PUBLISHER = R346_PRIMARY_PUBLISHER
SECONDARY_PUBLISHER = bytes.fromhex(
    "FA 87 DD E6 1F E0 42 FA 85 DD E6 1F E0 43 "
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40"
)


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def serialized_state(path: Path) -> bytes:
    """Extract one CRC-valid, exact-size mGBA Game Boy machine state."""

    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"not an mGBA PNG savestate: {path}")
    offset = 8
    states: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        require(offset + 12 <= len(data), f"truncated PNG chunk: {path}")
        size = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + 12 + size
        require(end <= len(data), f"truncated PNG payload: {path}")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        observed_crc = struct.unpack(">I", data[offset + 8 + size:end])[0]
        require(
            observed_crc == zlib.crc32(kind + payload) & 0xFFFFFFFF,
            f"PNG chunk CRC mismatch ({kind!r}): {path}",
        )
        if kind == b"gbAs":
            decoder = zlib.decompressobj()
            state = decoder.decompress(payload) + decoder.flush()
            require(decoder.eof and not decoder.unused_data
                    and not decoder.unconsumed_tail,
                    f"malformed compressed gbAs payload: {path}")
            states.append(state)
        if kind == b"IEND":
            require(size == 0, f"non-empty PNG IEND: {path}")
            saw_iend = True
            require(end == len(data), f"trailing bytes after PNG IEND: {path}")
        offset = end
    require(saw_iend, f"PNG savestate lacks IEND: {path}")
    require(len(states) == 1,
            f"expected one gbAs chunk, found {len(states)}: {path}")
    state = states[0]
    require(len(state) == GB_STATE_SIZE,
            f"gbAs state is {len(state):#x}, expected {GB_STATE_SIZE:#x}: {path}")
    require(int.from_bytes(state[0:4], "little") == GB_STATE_MAGIC,
            f"unsupported Game Boy savestate version: {path}")
    require(state[0x0008] & 0x80,
            f"publication savestate is not a CGB machine: {path}")
    return state


def io_byte(state: bytes, address: int) -> int:
    require(0xFF00 <= address <= 0xFF7F,
            f"not a serialized I/O address: ${address:04X}")
    return state[IO + address - 0xFF00]


def hram_byte(state: bytes, address: int) -> int:
    require(0xFF80 <= address <= 0xFFFE,
            f"not a serialized HRAM address: ${address:04X}")
    return state[HRAM + address - 0xFF80]


def wram0_bytes(state: bytes, address: int, size: int = 1) -> bytes:
    require(0xC000 <= address <= 0xCFFF,
            f"not a serialized WRAM0 address: ${address:04X}")
    offset = WRAM0 + address - 0xC000
    require(offset + size <= WRAM1,
            f"WRAM0 read crosses bank boundary: ${address:04X}+{size}")
    return state[offset:offset + size]


def wram1_byte(state: bytes, address: int) -> int:
    require(0xD000 <= address <= 0xDFFF,
            f"not a serialized WRAM1 address: ${address:04X}")
    return state[WRAM1 + address - 0xD000]


def publisher_preimages(payload: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    primary = payload[0x12E0:0x12E0 + len(PRIMARY_PUBLISHER)]
    primary_matches = [
        name for name, expected in PRIMARY_PUBLISHER_VARIANTS.items()
        if primary == expected
    ]
    require(len(primary_matches) == 1,
            "primary_12E0 publisher/camera preimage changed or ambiguous")
    result["primary_12E0"] = {
        "range": "$12E0-$1302",
        "sha256": sha256(primary),
        "variant": primary_matches[0],
    }
    secondary = payload[0x307B:0x307B + len(SECONDARY_PUBLISHER)]
    require(secondary == SECONDARY_PUBLISHER,
            "secondary_307B publisher/camera preimage changed")
    result["secondary_307B"] = {
        "range": f"$307B-${0x307B + len(SECONDARY_PUBLISHER) - 1:04X}",
        "sha256": sha256(secondary),
    }
    return result


def candidate_stage7_lut(payload: bytes) -> bytes:
    """Return the exact immutable LUT installed in the candidate ROM."""

    lut = payload[STAGE7_LUT_ROM_OFFSET:STAGE7_LUT_ROM_OFFSET + 0x100]
    require(len(lut) == 0x100, "candidate Stage-7 LUT is truncated")
    require(set(lut) == STAGE7_LUT_SLOTS,
            f"candidate Stage-7 LUT slots are {sorted(set(lut))}")
    for tile, expected in STAGE7_REQUIRED_LUT_VALUES.items():
        require(lut[tile] == expected,
                f"candidate Stage-7 LUT tile ${tile:02X} is {lut[tile]}, "
                f"expected {expected}")
    return lut


def probe_source_contract() -> dict[str, str]:
    source = SOAK_PROBE.read_text()
    verifier = SOAK_VERIFIER.read_text()
    require("raw_vram:read8(0x2000 +" not in source,
            "probe still treats out-of-domain raw-plus reads as bank 1")
    for text in (
        'local CAPTURE_FLIP_STATES = os.getenv("SOAK_FLIP_STATES") == "1"',
        "return emu:saveStateFile(state_path)",
        'completion:write("DONE\\n")',
        "trace_flip(0x12E0",
        "trace_flip(0x3095",
        'os.getenv("SOAK_WINDOW_HELPER_ADDR")',
        'os.getenv("SOAK_WINDOW_HELPER_BANK")',
        'local sampled_ffe4 = emu:read8(0xFFE4)',
    ):
        require(text in source, f"soak probe lacks exact state contract: {text}")
    for text in (
        '"--flip-states"',
        '"flip_states": args.flip_states',
        'completion.read_text() == "DONE\\n"',
        '"--require-r265-window-equivalence"',
        '"r265_window_execution_receipts": window_execution_receipts',
    ):
        require(text in verifier,
                f"soak verifier lacks flip-state manifest contract: {text}")
    return {
        "probe_sha256": sha256(SOAK_PROBE.read_bytes()),
        "soak_verifier_sha256": sha256(SOAK_VERIFIER.read_bytes()),
    }


def dollar_address(raw: object, label: str) -> int:
    require(isinstance(raw, str) and raw.startswith("$"),
            f"invalid {label}: {raw!r}")
    try:
        return int(raw[1:], 16)
    except ValueError as error:
        raise AssertionError(f"invalid {label}: {raw!r}") from error


def banked_address(raw: object, bank: int, label: str) -> int:
    prefix = f"bank{bank}:$"
    require(isinstance(raw, str) and raw.startswith(prefix),
            f"invalid {label}: {raw!r}")
    try:
        return int(raw[len(prefix):], 16)
    except ValueError as error:
        raise AssertionError(f"invalid {label}: {raw!r}") from error


def static_rejection_contract(
    path: Path, candidate_payload: bytes, candidate_sha256: str,
) -> dict[str, Any]:
    """Bind live-only $12E0 coverage to the emitted $0AB8 rejection."""

    payload = path.read_bytes()
    receipt_digest = sha256(payload)
    require(receipt_digest == EXPECTED_STATIC_RECEIPT_SHA256,
            "Stage-7 static receipt identity changed")
    receipt = json.loads(payload)
    require(
        receipt.get("schema")
        == "penta-stage7-hidden-dual-plane-hdma-r264-static-v1",
        "wrong Stage-7 static receipt schema",
    )
    require(receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "Stage-7 static receipt did not pass")
    require(receipt.get("promotable") is False,
            "static receipt incorrectly claims promotion")
    require(receipt.get("emulator_run") is False,
            "static receipt unexpectedly claims an emulator run")
    built = receipt.get("in_memory_candidate", {})
    require(built.get("sha256") == candidate_sha256,
            "static receipt belongs to a different candidate")
    require(built.get("rom_emitted") is True,
            "static receipt did not emit the audited candidate")

    callers = receipt.get("caller_and_camera_contract", {})
    require(callers.get("whole_ROM_occurrences")
            == ["fixed:$0AB5", "fixed:$12DD"],
            "static $4295 caller census changed")
    require(callers.get("admitted_outer_returns") == ["fixed:$12E0"],
            "static helper does not exclusively admit $12E0")
    require(callers.get("rejected_outer_returns") == ["fixed:$0AB8"],
            "static helper does not explicitly reject $0AB8")
    require(callers.get("rejected_caller_policy")
            == "native fallback before $DA13",
            "$0AB8 rejection is not pre-mutation native fallback")
    secondary = callers.get("secondary", {})
    require(secondary.get("continuation") == "$0AB8 CALL $307B",
            "rejected secondary continuation changed")
    require(secondary.get("fast_path_policy")
            == "rejected; untouched native dirty copier",
            "secondary caller is not bound to untouched native copy")
    require(secondary.get("strict_publisher_preimage")
            == "$307B-$3099 inclusive",
            "secondary native publisher preimage changed")

    emitted = receipt.get("emitted_guard_verification", {})
    require(emitted.get("caller_policy") == {
        "admitted_outer_returns": ["fixed:$12E0"],
        "rejected_outer_returns": ["fixed:$0AB8"],
        "rejected_continuation": "native fallback before $DA13",
    }, "emitted caller policy differs from the static policy")
    controls = emitted.get("mutation_controls", {})
    for name in (
        "mutated_exact_caller_rejected",
        "mutated_caller_reject_POP_HL_rejected",
        "mutated_secondary_0AB8_admission_rejected",
        "mutated_secondary_native_fallback_rejected",
    ):
        require(controls.get(name) is True,
                f"static caller mutation control did not reject: {name}")
    require(emitted.get("first_mutation_after_guards")
            == "$DA13 tagged atomic setup",
            "caller rejection is not proven before first mutation")
    require(emitted.get("secondary_stack_model") == {
        "helper_entry": ["$084D", "$0AB8"],
        "after_balanced_HL_probe": ["$084D", "$0AB8"],
        "native_mapper_entry": ["$42B3", "$0AB8"],
        "after_mapper_RET": ["$0AB8"],
    }, "rejected $0AB8 stack-word simulation differs")

    helper = receipt.get("helper", {})
    require(helper.get("bank") == 22, "static helper is not in bank 22")
    helper_start = dollar_address(helper.get("entry"), "helper entry")
    helper_end = dollar_address(helper.get("end"), "helper end")
    helper_offset = 22 * 0x4000 + helper_start - 0x4000
    helper_blob = candidate_payload[
        helper_offset:helper_offset + helper_end - helper_start + 1
    ]
    require(len(helper_blob) == helper.get("length"),
            "candidate helper length differs from static receipt")
    require(sha256(helper_blob) == helper.get("sha256"),
            "candidate helper bytes differ from static receipt")
    immutable_lut = helper.get("immutable_lut", {})
    require(immutable_lut.get("address") == "$7600"
            and immutable_lut.get("length") == 0x100,
            "static immutable Stage-7 LUT range changed")
    candidate_lut = candidate_stage7_lut(candidate_payload)
    require(sha256(candidate_lut) == immutable_lut.get("sha256"),
            "candidate immutable Stage-7 LUT differs from static receipt")
    labels = helper.get("trace_labels", {})
    fallback = banked_address(
        labels.get("fallback_native"), 22, "native fallback label"
    )
    reject = banked_address(
        labels.get("caller_reject"), 22, "caller reject label"
    )
    fallback_pattern = bytes.fromhex(emitted.get("native_fallback_pattern", ""))
    reject_pattern = bytes.fromhex(emitted.get("caller_reject_pattern", ""))
    caller_pattern = bytes.fromhex(emitted.get("caller_pattern", ""))
    require(fallback_pattern == bytes.fromhex("F1 11 B3 42 D5 3E 01 C3 61 00"),
            "native fallback no longer synthesizes bank1:$42B3")
    require(reject_pattern == bytes((0xE1, 0xC3)) + fallback.to_bytes(2, "little"),
            "caller rejection no longer balances HL then jumps native")
    require(helper_blob[fallback - helper_start:
                        fallback - helper_start + len(fallback_pattern)]
            == fallback_pattern,
            "candidate lacks exact native fallback at declared label")
    require(helper_blob[reject - helper_start:
                        reject - helper_start + len(reject_pattern)]
            == reject_pattern,
            "candidate lacks exact caller rejection at declared label")
    require(caller_pattern and helper_blob.count(caller_pattern) == 1,
            "candidate lacks one exact single-caller guard")

    crop = receipt.get("visible_crop_rebind", {})
    require(
        crop.get("schema") == "penta-stage7-r273-static-rebind-v1",
        "static receipt lacks the exact r273 visible-crop rebind",
    )
    require(crop.get("candidate_sha256") == candidate_sha256,
            "visible-crop rebind belongs to a different candidate")
    require(crop.get("visible_rows") == list(range(20)),
            "r273 visible-row union changed")
    require(crop.get("visible_columns") == list(range(22)),
            "r273 visible-column union changed")
    require(crop.get("semantic_columns_compiled") == list(range(24)),
            "r273 compiled semantic-column range changed")
    require(
        crop.get("invisible_padding_columns_not_written") == list(range(24, 32)),
        "r273 skipped padding-column range changed",
    )
    require(crop.get("attribute_blocks") == 40
            and crop.get("tile_rows") == 20
            and crop.get("tile_blocks") == 40,
            "r273 cropped transfer geometry changed")
    crop_checks = crop.get("contracts", {})
    for name in (
        "all_potentially_visible_rows_compiled_and_transferred",
        "all_visible_and_semantic_attributes_still_compiled",
        "only_never_visible_padding_writes_removed",
        "row_stride_and_40_block_transfer_unchanged",
        "r265_menu_repairs_byte_exact",
    ):
        require(crop_checks.get(name) is True,
                f"r273 crop proof did not pass: {name}")

    plane_contract = {
        "populated_rows": list(range(20)),
        "semantic_columns": list(range(24)),
        "visible_rows": list(range(20)),
        "visible_columns": list(range(22)),
        "excluded_rows": list(range(20, 24)),
        "excluded_padding_columns": list(range(24, 32)),
    }
    return {
        "path": str(path),
        "sha256": receipt_digest,
        "admitted_outer_returns": ["12E0"],
        "rejected_outer_returns": ["0AB8"],
        "rejected_continuation": "native bank1:$42B3 before $DA13",
        "helper_range": f"bank22:${helper_start:04X}-${helper_end:04X}",
        "immutable_lut_sha256": sha256(candidate_lut),
        "plane_contract": plane_contract,
    }


def parse_report(path: Path) -> dict[str, Any]:
    lines = path.read_text().splitlines()
    require(len(lines) >= 3, f"short report: {path}")
    fields = {
        key: int(raw, 16 if key == "expected_scene" else 10)
        for key, raw in re.findall(
            r"([a-z0-9_]+)=(-?[0-9A-Fa-f]+)", lines[0]
        )
    }
    rooms = {
        int(raw, 16)
        for raw in lines[1].split("=", 1)[1].split(",") if raw
    }
    scenes = {
        int(raw, 16)
        for raw in lines[2].split("=", 1)[1].split(",") if raw
    }
    return {"fields": fields, "rooms": rooms, "scenes": scenes}


def parse_meta(path: Path) -> dict[str, int]:
    line = path.read_text().splitlines()[0]
    decimal = {"frame", "target"}
    values = {
        key: int(raw, 10 if key in decimal else 16)
        for key, raw in re.findall(r"([A-Za-z0-9_]+)=([0-9A-Fa-f]+)", line)
    }
    required = {
        "frame", "target", "expected_scene", "D880", "FFC1", "LCDC",
        "SCX", "SCY", "phase", "active_map", "room",
    }
    require(required <= values.keys(), f"short room metadata: {path}")
    return values


def parse_capture_frames(path: Path) -> dict[int, int]:
    result: dict[int, int] = {}
    for line in path.read_text().splitlines():
        match = re.search(r"p(\d+) captured room=([0-9A-Fa-f]{2})", line)
        if not match:
            continue
        play_frame, room = int(match.group(1)), int(match.group(2), 16)
        require(room not in result, f"duplicate captured room {room:02X}")
        result[room] = play_frame
    return result


def parse_layouts(path: Path) -> dict[tuple[int, int], tuple[int, bytes]]:
    layouts: dict[tuple[int, int], tuple[int, bytes]] = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        columns = line.split("\t")
        require(len(columns) >= 14, f"short layout row {path}:{number}")
        try:
            frame = int(columns[0])
            room = int(columns[1], 16)
            active_map = int(columns[2], 16)
            raw = bytes.fromhex(columns[-1])
        except ValueError as error:
            raise AssertionError(f"invalid layout row {path}:{number}") from error
        require(active_map in EXPECTED_MAPS,
                f"invalid layout map ${active_map:04X} at {path}:{number}")
        require(len(raw) == 24 * 24,
                f"layout row {path}:{number} has {len(raw)} source bytes")
        key = (frame, room)
        require(key not in layouts, f"duplicate layout sample {key}")
        layouts[key] = (active_map, raw)
    return layouts


def viewport_indexes(scx: int, scy: int, *, reject_padding: bool) -> list[int]:
    first_col, first_row = scx // 8, scy // 8
    cols = 20 if scx & 7 == 0 else 21
    rows = 18 if scy & 7 == 0 else 19
    indexes: list[int] = []
    for y in range(rows):
        for x in range(cols):
            row = (first_row + y) & 31
            column = (first_col + x) & 31
            if reject_padding:
                require(
                    row < 24 and column < 24,
                    f"viewport SCX={scx:02X} SCY={scy:02X} exposes "
                    f"padding cell ({column},{row})",
                )
            indexes.append(row * 32 + column)
    return indexes


def require_viewport_in_contract(
    scx: int, scy: int, plane_contract: dict[str, Any], *, label: str,
) -> list[int]:
    """Prove the pending viewport is wholly inside r273's updated union."""

    indexes = viewport_indexes(scx, scy, reject_padding=True)
    visible_rows = set(plane_contract["visible_rows"])
    visible_columns = set(plane_contract["visible_columns"])
    escaped = [
        (index % 32, index // 32)
        for index in indexes
        if index // 32 not in visible_rows or index % 32 not in visible_columns
    ]
    require(
        not escaped,
        f"{label} viewport escapes r273 updated union at {escaped[:8]}",
    )
    return indexes


def compare_populated_plane(
    tiles: bytes, attrs: bytes, lut: bytes, raw: bytes, map_base: int,
    plane_contract: dict[str, Any],
) -> dict[str, Any]:
    require(len(tiles) == 0x800, "combined tile-map dump is not 2048 bytes")
    require(len(attrs) == 0x800, "combined attribute dump is not 2048 bytes")
    require(len(lut) == 0x100, "stage LUT dump is not 256 bytes")
    require(len(raw) == 24 * 24, "packed source is not 576 bytes")
    require(map_base in EXPECTED_MAPS, f"invalid physical map ${map_base:04X}")
    map_offset = 0x400 if map_base == 0x9C00 else 0
    tile_mismatches: list[str] = []
    attr_mismatches: list[str] = []
    desired_histogram: Counter[int] = Counter()
    populated_rows = plane_contract["populated_rows"]
    semantic_columns = plane_contract["semantic_columns"]
    require(populated_rows == list(range(20)),
            "unexpected populated-row contract")
    require(semantic_columns == list(range(24)),
            "unexpected semantic-column contract")
    for row in populated_rows:
        for column in semantic_columns:
            source_index = row * 24 + column
            map_index = map_offset + row * 32 + column
            tile = raw[source_index]
            desired = lut[tile]
            desired_histogram[desired] += 1
            if tiles[map_index] != tile and len(tile_mismatches) < 16:
                tile_mismatches.append(
                    f"{column}:{row}:{tiles[map_index]:02X}>{tile:02X}"
                )
            if attrs[map_index] != desired and len(attr_mismatches) < 16:
                attr_mismatches.append(
                    f"{column}:{row}:{tile:02X}:"
                    f"{attrs[map_index]:02X}>{desired:02X}"
                )
    require(not tile_mismatches,
            "populated tile plane differs: " + ",".join(tile_mismatches))
    require(not attr_mismatches,
            "populated attribute plane differs: " + ",".join(attr_mismatches))
    return {
        "cells": len(populated_rows) * len(semantic_columns),
        "rows": populated_rows,
        "semantic_columns": semantic_columns,
        "desired_attr_histogram": {
            str(key): value for key, value in sorted(desired_histogram.items())
        },
    }


def audit_flip_state(
    state: bytes, record: dict[str, int], expected_lut: bytes,
    plane_contract: dict[str, Any], *, label: str,
) -> dict[str, Any]:
    """Validate one exact pre-LCDC-store machine snapshot."""

    site = record["site"]
    require(site in KNOWN_PUBLISHERS, f"{label} has unknown publisher")
    selector = record["selector"]
    base = record["base"]
    scx, scy = record["scx"], record["scy"]
    expected_pc = 0x12EC if site == 0x12E0 else 0x3095
    pc = int.from_bytes(state[CPU_PC:CPU_PC + 2], "little")
    require(pc == expected_pc,
            f"{label} PC=${pc:04X}, expected ${expected_pc:04X}")

    expected_a = 0x8B if base == 0x9C00 else 0x83
    require(state[CPU_A] == expected_a,
            f"{label} A=${state[CPU_A]:02X}, expected ${expected_a:02X}")
    require(int.from_bytes(
        state[MEMORY_CURRENT_ROM_BANK:MEMORY_CURRENT_ROM_BANK + 2], "little"
    ) == 1, f"{label} mapped ROM bank is not 1")
    require(hram_byte(state, 0xFF99) == 1,
            f"{label} FF99 mapper shadow is not 1")
    require(state[MEMORY_CURRENT_WRAM_BANK] == 1,
            f"{label} serialized WRAM bank is not 1")
    require(io_byte(state, 0xFF70) & 0x07 == 1,
            f"{label} SVBK is not 1")
    require(state[VIDEO_CURRENT_VRAM_BANK] == 0,
            f"{label} serialized VRAM bank is not 0")
    require(io_byte(state, 0xFF4F) & 0x01 == 0,
            f"{label} VBK is not 0")
    require(io_byte(state, 0xFF55) == 0xFF,
            f"{label} FF55 is not exactly idle")
    require(state[IE] == 0x07, f"{label} IE=${state[IE]:02X}, expected $07")
    memory_flags = int.from_bytes(
        state[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little"
    )
    require(memory_flags & MEMORY_FLAG_IME,
            f"{label} IME is not enabled after RETI")
    require(not memory_flags & MEMORY_FLAG_HDMA_ACTIVE,
            f"{label} serialized HDMA-active flag is set")
    require(hram_byte(state, 0xFFA5) == 0,
            f"{label} FFA5 was not restored")
    require(hram_byte(state, 0xFFE0) == 0,
            f"{label} FFE0 was not restored")
    require(hram_byte(state, 0xFFC1) == 1,
            f"{label} is not gameplay")
    require(hram_byte(state, 0xFFBA) == 6,
            f"{label} is not Stage 7")
    require(wram1_byte(state, 0xD880) == 8,
            f"{label} is not scene $08")
    require(hram_byte(state, 0xFFBD) == record["room"],
            f"{label} room trace/state mismatch")
    require(wram1_byte(state, 0xDF04) == record["df04"],
            f"{label} DF04 trace/state mismatch")
    require(wram1_byte(state, 0xDF4E) == record["df4e"],
            f"{label} DF4E trace/state mismatch")
    require((io_byte(state, 0xFF41) & 0x03) == record["mode"],
            f"{label} STAT mode trace/state mismatch")
    require(((state[0x00CD] >> 2) & 0x03) == record["mode"],
            f"{label} serialized video mode trace/state mismatch")

    live_selector = wram1_byte(state, 0xDC0B) & 0x01
    require(live_selector == selector,
            f"{label} selector trace/state mismatch")
    expected_base = 0x9C00 if live_selector else 0x9800
    require(base == expected_base,
            f"{label} destination/selector mismatch")
    require((0x9C00 if state[CPU_A] & 0x08 else 0x9800) == base,
            f"{label} LCDC-store A selects the wrong destination")
    old_lcdc = io_byte(state, 0xFF40)
    require(old_lcdc & 0x80, f"{label} LCD was disabled at visual publication")
    require(not old_lcdc & 0x20, f"{label} Window was enabled")
    displayed_base = 0x9C00 if old_lcdc & 0x08 else 0x9800
    require(displayed_base != base,
            f"{label} publisher targeted the currently displayed map")

    if site == 0x12E0:
        if hram_byte(state, 0xFF97) != 2:
            expected_scx = wram1_byte(state, 0xDC00) & 0x0F
            expected_scy = wram1_byte(state, 0xDC02) & 0x0F
        else:
            expected_scx = io_byte(state, 0xFF43)
            expected_scy = io_byte(state, 0xFF42)
    else:
        expected_scx = wram1_byte(state, 0xDD85) & 0x1F
        expected_scy = wram1_byte(state, 0xDD87) & 0x1F
        require(io_byte(state, 0xFF43) == expected_scx
                and io_byte(state, 0xFF42) == expected_scy,
                f"{label} secondary publisher did not install pending camera")
    require((scx, scy) == (expected_scx, expected_scy),
            f"{label} camera trace/state mismatch")
    visible_indexes = require_viewport_in_contract(
        scx, scy, plane_contract, label=label
    )

    raw = wram0_bytes(state, 0xC1A0, 24 * 24)
    lut = wram0_bytes(state, 0xC600, 0x100)
    require(lut == expected_lut,
            f"{label} C600 LUT differs from the candidate's immutable LUT")
    tiles = state[VRAM0 + 0x1800:VRAM0 + 0x2000]
    attrs = state[VRAM1 + 0x1800:VRAM1 + 0x2000]
    exact = compare_populated_plane(
        tiles, attrs, lut, raw, base, plane_contract
    )
    stable_phase = (
        io_byte(state, 0xFF47) == 0xE4
        and wram1_byte(state, 0xDF4C) == 0
    )
    return {
        "gbas_sha256": sha256(state),
        "pc": f"{pc:04X}",
        "displayed_map_before": f"{displayed_base:04X}",
        "phase": "stable" if stable_phase else "transition",
        "visible_cells": len(visible_indexes),
        **exact,
    }


def audit_flips(
    path: Path, root: Path, expected_lut: bytes,
    plane_contract: dict[str, Any],
) -> dict[str, Any]:
    total = 0
    readable_by_map: Counter[int] = Counter()
    readable_by_site_map: Counter[tuple[int, int]] = Counter()
    modes: Counter[int] = Counter()
    sites: Counter[int] = Counter()
    site_phases: Counter[tuple[int, str]] = Counter()
    state_digests: dict[str, str] = {}
    semantic_slots: Counter[int] = Counter()
    expected_state_names: list[str] = []
    for number, line in enumerate(path.read_text().splitlines(), 1):
        columns = line.split("\t")
        require(len(columns) == 14, f"short flip row {path}:{number}")
        try:
            index = int(columns[0])
            site = int(columns[2], 16)
            mode = int(columns[3])
            selector = int(columns[4], 16)
            base = int(columns[5], 16)
            room = int(columns[6], 16)
            scx = int(columns[7], 16)
            scy = int(columns[8], 16)
            df04 = int(columns[9], 16)
            df4e = int(columns[10], 16)
            mismatches = int(columns[11])
        except ValueError as error:
            raise AssertionError(f"invalid flip row {path}:{number}") from error
        require(index == number,
                f"non-sequential flip index at {path}:{number}")
        total += 1
        modes[mode] += 1
        sites[site] += 1
        require(site in LIVE_EXPECTED_PUBLISHERS,
                f"unexpected Stage-7 publication site ${site:04X}")
        expected_base = 0x9C00 if selector & 1 else 0x9800
        require(base == expected_base,
                f"selector/base mismatch at {path}:{number}: "
                f"{selector:02X}/${base:04X}")
        require_viewport_in_contract(
            scx, scy, plane_contract, label=f"{path}:{number}"
        )
        require(mismatches == 0,
                f"pre-display contract/semantic mismatch at {path}:{number}")
        require(columns[12] == "",
                f"zero-count flip retained mismatch detail at {path}:{number}")
        trace_state_name = f"flip{index:06d}.ss0"
        expected_state_name = f"stage7.{trace_state_name}"
        require(columns[13] == trace_state_name,
                f"wrong flip state name at {path}:{number}")
        expected_state_names.append(expected_state_name)
        state_path = root / expected_state_name
        require(state_path.is_file(), f"missing publication state: {state_path}")
        state = serialized_state(state_path)
        state_result = audit_flip_state(
            state,
            {
                "site": site,
                "mode": mode,
                "selector": selector,
                "base": base,
                "room": room,
                "scx": scx,
                "scy": scy,
                "df04": df04,
                "df4e": df4e,
            },
            expected_lut,
            plane_contract,
            label=f"{path}:{number}",
        )
        state_digests[expected_state_name] = state_result["gbas_sha256"]
        site_phases[(site, state_result["phase"])] += 1
        for slot, count in state_result["desired_attr_histogram"].items():
            semantic_slots[int(slot)] += count
        readable_by_map[base] += 1
        readable_by_site_map[(site, base)] += 1
    observed_state_names = sorted(
        candidate.name for candidate in root.glob("stage7.flip*.ss0")
    )
    require(observed_state_names == expected_state_names,
            "publication state set does not exactly match the flip trace")
    require(total >= 20, f"too few Stage-7 publication events: {total}")
    require(set(sites) == LIVE_EXPECTED_PUBLISHERS,
            "Stage-7 route did not exclusively cover natural $12E0 publisher")
    require(site_phases[(0x12E0, "stable")] > 0,
            "primary publisher had no stable-phase receipt")
    for base in EXPECTED_MAPS:
        require(
            readable_by_map[base] >= MIN_READABLE_FLIPS_PER_MAP,
            f"only {readable_by_map[base]} readable ${base:04X} flips",
        )
    for site in LIVE_EXPECTED_PUBLISHERS:
        for base in EXPECTED_MAPS:
            require(readable_by_site_map[(site, base)] > 0,
                    f"publisher ${site:04X} never selected ${base:04X}")
    for slot, name in ((2, "rare pickup"), (4, "arrow pickup"), (5, "lava")):
        require(semantic_slots[slot] > 0,
                f"publication states contain no {name} palette cells")
    return {
        "events": total,
        "readable_by_map": {
            f"{base:04X}": readable_by_map[base]
            for base in sorted(EXPECTED_MAPS)
        },
        "by_publisher_and_map": {
            f"{site:04X}/{base:04X}": readable_by_site_map[(site, base)]
            for site in sorted(LIVE_EXPECTED_PUBLISHERS)
            for base in sorted(EXPECTED_MAPS)
        },
        "stat_modes": {str(key): value for key, value in sorted(modes.items())},
        "sites": {f"{key:04X}": value for key, value in sorted(sites.items())},
        "publisher_phases": {
            f"{site:04X}/{phase}": count
            for (site, phase), count in sorted(site_phases.items())
        },
        "semantic_slot_cells": {
            str(key): value for key, value in sorted(semantic_slots.items())
        },
        "gbas_sha256": state_digests,
    }


def audit_attr_events(path: Path) -> dict[str, Any]:
    """Validate full packed-source receipts at the native copier entry."""

    by_map: Counter[int] = Counter()
    last_index = 0
    rows = 0
    lava_tiles = {0x19, 0x1A}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        columns = line.split("\t")
        require(len(columns) == 14, f"short attr event {path}:{number}")
        try:
            index = int(columns[0])
            raw = bytes.fromhex(columns[12])
            destination = int(columns[13], 16)
            observed_lava_bits = bytes.fromhex(columns[11])
        except ValueError as error:
            raise AssertionError(f"invalid attr event {path}:{number}") from error
        require(index == last_index + 1,
                f"non-sequential attr event index at {path}:{number}")
        last_index = index
        require(destination in EXPECTED_MAPS,
                f"invalid attr-event destination ${destination:04X}")
        require(len(raw) == 24 * 24,
                f"attr event {path}:{number} has {len(raw)} source bytes")
        expected_lava_bits = bytearray()
        packed = 0
        for offset, tile in enumerate(raw):
            if tile in lava_tiles:
                packed |= 1 << (offset & 7)
            if offset & 7 == 7:
                expected_lava_bits.append(packed)
                packed = 0
        require(observed_lava_bits == bytes(expected_lava_bits),
                f"Stage-7 lava bitset/source mismatch at {path}:{number}")
        by_map[destination] += 1
        rows += 1
    require(rows >= 40, f"too few native copier source events: {rows}")
    for destination in EXPECTED_MAPS:
        require(by_map[destination] >= 10,
                f"too few ${destination:04X} copier source events")
    return {
        "events": rows,
        "by_map": {
            f"{destination:04X}": by_map[destination]
            for destination in sorted(EXPECTED_MAPS)
        },
        "raw_cells_checked": rows * 24 * 24,
        "lava_bitsets_exact": True,
    }


def synthetic_flip_state(
    site: int, base: int,
) -> tuple[bytes, dict[str, int]]:
    """Build a ROM-free exact-plane control for the serialized-state gate."""

    require(site in KNOWN_PUBLISHERS, "invalid synthetic publisher")
    require(base in EXPECTED_MAPS, "invalid synthetic map")
    state = bytearray(GB_STATE_SIZE)
    state[0:4] = GB_STATE_MAGIC.to_bytes(4, "little")
    state[0x0008] = 0x80
    state[CPU_PC:CPU_PC + 2] = (
        0x12EC if site == 0x12E0 else 0x3095
    ).to_bytes(2, "little")
    state[CPU_A] = 0x8B if base == 0x9C00 else 0x83
    state[MEMORY_CURRENT_ROM_BANK:MEMORY_CURRENT_ROM_BANK + 2] = (
        1
    ).to_bytes(2, "little")
    state[MEMORY_CURRENT_WRAM_BANK] = 1
    state[MEMORY_FLAGS:MEMORY_FLAGS + 2] = MEMORY_FLAG_IME.to_bytes(
        2, "little"
    )
    state[VIDEO_CURRENT_VRAM_BANK] = 0
    state[IE] = 0x07

    def set_io(address: int, value: int) -> None:
        state[IO + address - 0xFF00] = value

    def set_hram(address: int, value: int) -> None:
        state[HRAM + address - 0xFF80] = value

    def set_wram1(address: int, value: int) -> None:
        state[WRAM1 + address - 0xD000] = value

    mode, room, scx, scy = 0, 1, 0x0C, 0x04
    selector = 1 if base == 0x9C00 else 0
    set_io(0xFF40, 0x83 if base == 0x9C00 else 0x8B)
    set_io(0xFF41, mode)
    state[0x00CD] = mode << 2
    set_io(0xFF42, scy)
    set_io(0xFF43, scx)
    set_io(0xFF47, 0xE4)
    set_io(0xFF4F, 0)
    set_io(0xFF55, 0xFF)
    set_io(0xFF70, 1)
    set_hram(0xFF97, 2)
    set_hram(0xFF99, 1)
    set_hram(0xFFA5, 0)
    set_hram(0xFFBA, 6)
    set_hram(0xFFBD, room)
    set_hram(0xFFC1, 1)
    set_hram(0xFFE0, 0)
    set_wram1(0xD880, 8)
    set_wram1(0xDC0B, selector)
    set_wram1(0xDF04, 0x22)
    set_wram1(0xDF4C, 0)
    set_wram1(0xDF4E, 0x33)
    if site == 0x3095:
        set_wram1(0xDD85, scx)
        set_wram1(0xDD87, scy)

    raw = bytes(index & 0xFF for index in range(24 * 24))
    lut = bytes((0, 2, 4, 5)[tile & 3] for tile in range(0x100))
    state[WRAM0 + 0x1A0:WRAM0 + 0x1A0 + len(raw)] = raw
    state[WRAM0 + 0x600:WRAM0 + 0x700] = lut
    map_offset = base - 0x8000
    for row in range(24):
        for column in range(24):
            source_index = row * 24 + column
            map_index = map_offset + row * 32 + column
            tile = raw[source_index]
            state[VRAM0 + map_index] = tile
            state[VRAM1 + map_index] = lut[tile]
    return bytes(state), {
        "site": site,
        "mode": mode,
        "selector": selector,
        "base": base,
        "room": room,
        "scx": scx,
        "scy": scy,
        "df04": 0x22,
        "df4e": 0x33,
    }


def audit_run(
    root: Path, candidate_sha256: str, expected_lut: bytes,
    plane_contract: dict[str, Any], *,
    allow_legacy_unbound: bool = False,
) -> dict[str, Any]:
    report_path = root / "stage7.report"
    layout_path = root / "stage7.layout-events.tsv"
    flip_path = root / "stage7.flip-events.tsv"
    attr_path = root / "stage7.attr-events.tsv"
    semantic_write_path = root / "stage7.semantic-writes.tsv"
    log_path = root / "stage7.log"
    done_path = root / "stage7.done"
    for path in (report_path, layout_path, flip_path, log_path, done_path):
        require(path.is_file(), f"missing Stage-7 artifact: {path}")
    require(done_path.read_text() == "DONE\n",
            f"invalid Stage-7 completion marker: {done_path}")

    run_manifest_path = root / "run-manifest.json"
    run_manifest: dict[str, Any] | None = None
    if run_manifest_path.is_file():
        run_manifest = json.loads(run_manifest_path.read_text())
        require(run_manifest.get("schema") == "penta-later-stage-soak-run-v1",
                f"wrong soak manifest schema: {run_manifest_path}")
        require(run_manifest.get("status") == "PASS",
                f"soak manifest did not pass: {run_manifest_path}")
        require(run_manifest.get("identity_intact") is True,
                f"soak inputs changed during capture: {run_manifest_path}")
        before = run_manifest.get("identity_before", {})
        after = run_manifest.get("identity_after", {})
        require(before == after, f"soak identity drift: {run_manifest_path}")
        require(before.get("candidate_sha256") == candidate_sha256,
                f"soak candidate SHA mismatch: {run_manifest_path}")
        for key in ("probe_sha256", "verifier_sha256", "launcher_sha256"):
            require(before.get(key), f"soak manifest lacks {key}")
        require(before["probe_sha256"] == sha256(SOAK_PROBE.read_bytes()),
                f"soak probe is not the current checked-in gate: {run_manifest_path}")
        require(before["verifier_sha256"] == sha256(SOAK_VERIFIER.read_bytes()),
                f"soak verifier is not current: {run_manifest_path}")
        require(Path(run_manifest.get("launcher", "")).resolve()
                == SOAK_LAUNCHER.resolve(),
                f"soak did not use the required single-flight launcher")
        require(before["launcher_sha256"] == sha256(SOAK_LAUNCHER.read_bytes()),
                f"soak launcher is not current: {run_manifest_path}")
        invocation = run_manifest.get("invocation", {})
        required_invocation = {
            "stages": [7],
            "frames": 8000,
            "sample_interval": 1,
            "capture_stable": 4,
            "attr_trace": True,
            "layout_trace": True,
            "semantic_write_trace": True,
            "flip_states": True,
            "active_map_strict": True,
            "wram_audit": True,
            "require_stage_base_palette": True,
            "require_semantic_pickups": True,
            "require_r265_window_equivalence": True,
        }
        for key, value in required_invocation.items():
            require(invocation.get(key) == value,
                    f"soak invocation {key}={invocation.get(key)!r}, "
                    f"expected {value!r}")
        probe_contract = run_manifest.get("r265_window_probe_contract", {})
        require(
            probe_contract.get("window_helper") == "bank13:$6A40"
            and probe_contract.get("execution_equivalence")
            == "zero changed-helper executions, or FFE4=0 at every exact entry",
            f"soak Window-helper source contract changed: {run_manifest_path}",
        )
        policy_controls = run_manifest.get("r265_window_policy_controls", {})
        require(policy_controls and all(policy_controls.values()),
                f"soak Window-equivalence controls failed: {run_manifest_path}")
        execution = run_manifest.get(
            "r265_window_execution_receipts", {}
        ).get("stage7", {})
        require(execution.get("passed") is True
                and execution.get("checks")
                and all(execution["checks"].values()),
                f"soak Window execution receipt failed: {run_manifest_path}")
    else:
        require(allow_legacy_unbound,
                f"missing cryptographic soak manifest: {run_manifest_path}")
    if run_manifest is not None:
        require(attr_path.is_file(), f"missing copier source trace: {attr_path}")
        require(semantic_write_path.is_file(),
                f"missing visible-write trail trace: {semantic_write_path}")
        require(not semantic_write_path.read_text().splitlines(),
                f"active-visible tile/attribute trail: {semantic_write_path}")

    report = parse_report(report_path)
    fields = report["fields"]
    require(fields.get("target") == 6, "soak target is not Stage 7")
    require(fields.get("stage") == 7, "reported stage is not 7")
    require(fields.get("expected_scene") == 0x08,
            "expected scene is not $08")
    require(fields.get("frames") == 8000, "soak is not exactly 8000 frames")
    zero_frames = fields.get("ffe4_zero_play_frames", -1)
    nonzero_frames = fields.get("ffe4_nonzero_play_frames", -1)
    first_nonzero_frame = fields.get("first_ffe4_nonzero_play_frame", -2)
    first_nonzero_value = fields.get("first_ffe4_nonzero_value", -2)
    require(zero_frames >= 0 and nonzero_frames >= 0
            and zero_frames + nonzero_frames == fields["frames"],
            "FFE4 callback telemetry does not account for all Stage-7 frames")
    require(
        (nonzero_frames == 0 and first_nonzero_frame == -1
         and first_nonzero_value == -1)
        or (nonzero_frames > 0
            and 1 <= first_nonzero_frame <= fields["frames"]
            and first_nonzero_value > 0),
        "FFE4 first-nonzero callback telemetry is incoherent",
    )
    require(fields.get("window_helper_hits", -1) >= 0
            and fields.get("window_helper_ffe4_nonzero_hits") == 0,
            "changed Window helper executed with nonzero FFE4")
    require(fields.get("samples", 0) >= MIN_LAYOUT_SAMPLES,
            "too few stable Stage-7 layout samples")
    require(report["rooms"] == EXPECTED_ROOMS,
            f"wrong Stage-7 room route: {sorted(report['rooms'])}")
    require(0x08 in report["scenes"], "Stage-7 scene was not sampled")
    for key in (
        "unsafe", "unexpected", "lava_mismatch", "pickup_mismatch",
        "material_mismatch", "wram_changed",
    ):
        require(fields.get(key) == 0, f"report {key}={fields.get(key)}")
    require(fields.get("pickup_expected", 0) > 0,
            "no semantic pickup was sampled")

    layouts = parse_layouts(layout_path)
    require(len(layouts) == fields["samples"],
            "layout trace/sample count differs")
    capture_frames = parse_capture_frames(log_path)
    require(set(capture_frames) == EXPECTED_ROOMS,
            f"wrong captured-room set: {sorted(capture_frames)}")

    captures: list[dict[str, Any]] = []
    captured_maps: set[int] = set()
    semantic_slots: Counter[int] = Counter()
    for room in sorted(EXPECTED_ROOMS):
        meta_path = root / f"stage7.room{room:02X}.meta"
        require(meta_path.is_file(), f"missing room metadata: {meta_path}")
        meta = parse_meta(meta_path)
        require(meta["target"] == 6 and meta["expected_scene"] == 0x08,
                f"room {room:02X} has wrong target/scene metadata")
        require(meta["D880"] == 0x08 and meta["FFC1"] == 0x01,
                f"room {room:02X} is not stable Stage-7 gameplay")
        require(meta["phase"] == 0,
                f"room {room:02X} was captured during palette publication")
        require(meta["room"] == room, f"room metadata/name mismatch {room:02X}")
        expected_active = 0x9C00 if meta["LCDC"] & 0x08 else 0x9800
        require(meta["active_map"] == expected_active,
                f"room {room:02X} LCDC/active-map mismatch")
        captured_maps.add(expected_active)
        play_frame = capture_frames[room]
        key = (play_frame, room)
        require(key in layouts,
                f"room {room:02X} has no same-frame packed-source sample")
        layout_map, raw = layouts[key]
        require(layout_map == expected_active,
                f"room {room:02X} layout/active-map mismatch")
        tiles = meta_path.with_suffix(".map0.bin").read_bytes()
        attrs = meta_path.with_suffix(".attr.bin").read_bytes()
        lut = meta_path.with_suffix(".bg-lut.bin").read_bytes()
        require(lut == expected_lut,
                f"room {room:02X} LUT differs from the candidate immutable LUT")
        exact = compare_populated_plane(
            tiles, attrs, lut, raw, expected_active, plane_contract
        )
        visible_indexes = require_viewport_in_contract(
            meta["SCX"], meta["SCY"], plane_contract,
            label=f"room {room:02X}",
        )
        for slot, count in exact["desired_attr_histogram"].items():
            semantic_slots[int(slot)] += count
        captures.append({
            "room": f"{room:02X}",
            "play_frame": play_frame,
            "active_map": f"{expected_active:04X}",
            "scx": meta["SCX"],
            "scy": meta["SCY"],
            "visible_cells": len(visible_indexes),
            **exact,
        })
    require(captured_maps,
            "stable exact captures did not cover a physical map")
    for slot, name in ((2, "rare pickup"), (4, "arrow pickup"), (5, "lava")):
        require(semantic_slots[slot] > 0,
                f"exact captures contain no {name} palette cells")

    flips = audit_flips(flip_path, root, expected_lut, plane_contract)
    attr_events = audit_attr_events(attr_path) if attr_path.is_file() else None
    required_artifacts = [
        report_path, layout_path, flip_path, log_path, done_path,
    ]
    if run_manifest_path.is_file():
        required_artifacts.append(run_manifest_path)
    if attr_path.is_file():
        required_artifacts.append(attr_path)
    if semantic_write_path.is_file():
        required_artifacts.append(semantic_write_path)
    for room in sorted(EXPECTED_ROOMS):
        stem = root / f"stage7.room{room:02X}.meta"
        required_artifacts.extend([
            stem, stem.with_suffix(".map0.bin"), stem.with_suffix(".attr.bin"),
            stem.with_suffix(".bg-lut.bin"),
        ])
    artifacts = {
        path.name: sha256(path.read_bytes()) for path in required_artifacts
    }
    artifacts["__publication_gbas_sha256__.json"] = sha256(
        json.dumps(
            flips["gbas_sha256"], sort_keys=True, separators=(",", ":")
        ).encode()
    )
    return {
        "root": str(root),
        "cryptographically_bound": run_manifest is not None,
        "report": {
            "frames": fields["frames"],
            "samples": fields["samples"],
            "pickup_expected": fields["pickup_expected"],
            "rooms": [f"{room:02X}" for room in sorted(report["rooms"])],
            "ffe4_zero_play_frames": fields["ffe4_zero_play_frames"],
            "ffe4_nonzero_play_frames": fields["ffe4_nonzero_play_frames"],
            "window_helper_hits": fields["window_helper_hits"],
            "window_helper_ffe4_nonzero_hits": fields[
                "window_helper_ffe4_nonzero_hits"
            ],
        },
        "captures": captures,
        "semantic_slot_cells": {
            str(key): value for key, value in sorted(semantic_slots.items())
        },
        "flips": flips,
        "attr_events": attr_events,
        "active_visible_write_trails": 0,
        "artifact_sha256": artifacts,
    }


def mutation_controls(plane_contract: dict[str, Any]) -> dict[str, bool]:
    controls: dict[str, bool] = {}
    raw = bytes(range(256)) + bytes(range(256)) + bytes(range(64))
    lut = bytes(range(256))
    tiles = bytearray(0x800)
    attrs = bytearray(0x800)
    for row in range(24):
        for column in range(24):
            source_index = row * 24 + column
            map_index = row * 32 + column
            tiles[map_index] = raw[source_index]
            attrs[map_index] = lut[raw[source_index]]
    compare_populated_plane(
        bytes(tiles), bytes(attrs), lut, raw, 0x9800, plane_contract
    )
    controls["exact_plane_passes"] = True

    for name, target in (("tile_mutation_rejected", tiles),
                         ("attr_mutation_rejected", attrs)):
        mutant = bytearray(target)
        mutant[7 * 32 + 9] ^= 1
        try:
            compare_populated_plane(
                bytes(mutant) if target is tiles else bytes(tiles),
                bytes(mutant) if target is attrs else bytes(attrs),
                lut, raw, 0x9800, plane_contract,
            )
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(f"{name} negative control escaped")

    excluded_tile = bytearray(tiles)
    excluded_attr = bytearray(attrs)
    excluded_tile[22 * 32 + 9] ^= 1
    excluded_attr[22 * 32 + 9] ^= 1
    compare_populated_plane(
        bytes(excluded_tile), bytes(excluded_attr), lut, raw, 0x9800,
        plane_contract,
    )
    controls["cropped_row_excluded_from_equality_claim"] = True

    require_viewport_in_contract(
        0x0C, 0x0C, plane_contract, label="fractional-scroll-control"
    )
    controls["fractional_scroll_safe_control_passes"] = True
    try:
        require_viewport_in_contract(
            0x18, 0, plane_contract, label="visible-union-escape-control"
        )
    except AssertionError:
        controls["visible_union_escape_rejected"] = True
    else:
        raise AssertionError("visible-union escape negative control escaped")
    try:
        viewport_indexes(0xC0, 0, reject_padding=True)
    except AssertionError:
        controls["padding_exposure_rejected"] = True
    else:
        raise AssertionError("padding exposure negative control escaped")
    publisher_fixture = bytearray(0x30A0)
    publisher_fixture[0x12E0:0x12E0 + len(PRIMARY_PUBLISHER)] = PRIMARY_PUBLISHER
    publisher_fixture[0x307B:0x307B + len(SECONDARY_PUBLISHER)] = (
        SECONDARY_PUBLISHER
    )
    publisher_preimages(bytes(publisher_fixture))
    for name, offset in (("primary_publisher_mutation_rejected", 0x12E0),
                         ("secondary_publisher_mutation_rejected", 0x307B)):
        mutant = bytearray(publisher_fixture)
        mutant[offset] ^= 1
        try:
            publisher_preimages(bytes(mutant))
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(f"{name} negative control escaped")

    primary_state, primary_record = synthetic_flip_state(0x12E0, 0x9C00)
    secondary_state, secondary_record = synthetic_flip_state(0x3095, 0x9800)
    synthetic_lut = wram0_bytes(primary_state, 0xC600, 0x100)
    audit_flip_state(
        primary_state, primary_record, synthetic_lut,
        plane_contract,
        label="synthetic-primary",
    )
    audit_flip_state(
        secondary_state, secondary_record, synthetic_lut,
        plane_contract,
        label="synthetic-secondary",
    )
    controls["serialized_primary_and_secondary_pass"] = True
    state_mutations = {
        "serialized_attr_mutation_rejected": VRAM1 + 0x1C00 + 5 * 32 + 7,
        "serialized_tile_mutation_rejected": VRAM0 + 0x1C00 + 5 * 32 + 7,
        "serialized_FF55_mutation_rejected": IO + 0x55,
        "serialized_PC_mutation_rejected": CPU_PC,
        "serialized_hidden_map_mutation_rejected": IO + 0x40,
        "serialized_LUT_mutation_rejected": WRAM0 + 0x600 + 0x20,
    }
    for name, offset in state_mutations.items():
        mutant = bytearray(primary_state)
        mutant[offset] ^= 1 if name != "serialized_hidden_map_mutation_rejected" else 8
        try:
            audit_flip_state(
                bytes(mutant), primary_record, synthetic_lut,
                plane_contract, label=name
            )
        except AssertionError:
            controls[name] = True
        else:
            raise AssertionError(f"{name} negative control escaped")
    return controls


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", type=Path)
    parser.add_argument("run_b", type=Path)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--static-receipt", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument(
        "--legacy-unbound-control", action="store_true",
        help=(
            "audit archived pre-manifest receipts as a non-promotable harness "
            "control; never yields a candidate-bound PASS"
        ),
    )
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    require(candidate.is_file(), f"candidate ROM is missing: {candidate}")
    candidate_payload = candidate.read_bytes()
    candidate_digest = sha256(candidate_payload)
    require(candidate_digest == EXPECTED_CANDIDATE_SHA256,
            "visual gate is bound to the Stage-7 candidate "
            f"{EXPECTED_CANDIDATE_SHA256}, got {candidate_digest}")
    expected_lut = candidate_stage7_lut(candidate_payload)
    harness_contract = probe_source_contract()
    publisher_contract = publisher_preimages(candidate_payload)
    static_receipt = args.static_receipt.resolve()
    require(static_receipt.is_file(),
            f"Stage-7 static receipt is missing: {static_receipt}")
    static_contract = static_rejection_contract(
        static_receipt, candidate_payload, candidate_digest
    )
    plane_contract = static_contract["plane_contract"]
    run_a = audit_run(
        args.run_a.resolve(), candidate_digest, expected_lut, plane_contract,
        allow_legacy_unbound=args.legacy_unbound_control,
    )
    run_b = audit_run(
        args.run_b.resolve(), candidate_digest, expected_lut, plane_contract,
        allow_legacy_unbound=args.legacy_unbound_control,
    )
    require(run_a["artifact_sha256"] == run_b["artifact_sha256"],
            "independent Stage-7 visual receipts are not byte-deterministic")
    controls = mutation_controls(plane_contract)
    receipt = {
        "schema": "penta-stage7-dual-plane-visual-receipts-v3",
        "status": (
            "CONTROL_ONLY_UNBOUND"
            if args.legacy_unbound_control
            else "PASS_EXACT_VISUAL_RECEIPTS"
        ),
        "candidate": str(candidate),
        "candidate_sha256": candidate_digest,
        "immutable_stage7_lut_sha256": sha256(expected_lut),
        "harness_contract": harness_contract,
        "static_rejection_contract": static_contract,
        "plane_contract": plane_contract,
        "publisher_preimages": publisher_contract,
        "runs": [run_a, run_b],
        "deterministic_artifacts_and_gbas_payloads": True,
        "mutation_controls": controls,
        "capture_stable_rationale": (
            "Four consecutive room frames are required for frozen room "
            "receipts. Exact first-visible correctness is checked separately "
            "at every $12EC/$3095 publication breakpoint, so capture_stable=0 "
            "would add transition sensitivity without adding display coverage."
        ),
        "covered": [
            "candidate/probe/verifier/launcher identities bound by each soak manifest"
            if not args.legacy_unbound_control
            else "archived visual artifacts audited without candidate provenance",
            "exact bank-0 tile IDs for rows 0..19 and semantic columns 0..23 at every natural $12E0 display publication",
            "r265 execution equivalence: no changed-helper execution, or FFE4=0 at every exact $6A40 entry; all 8000 callback FFE4 samples are accounted as context telemetry",
            "exact serialized bank-1 LUT attributes for rows 0..19 and semantic columns 0..23 at every publication, including pickups and lava",
            "zero active-visible CPU write-boundary tile/attribute trails",
            "native Stage-7 selector/destination pairing before display",
            "$12E0/live-camera publisher across both physical maps",
            "$0AB8 is statically rejected to the native fallback because its $3095 route is unreachable in Stage-7 gameplay",
            "observed SCX/SCY viewports never expose padded cells",
            "every observed viewport is contained by r273's rows 0..19 and columns 0..21 visible union",
            "publication-boundary FF55/VBK/SVBK/IE/IME/FF99/FFA5/FFE0 restoration",
            "byte-deterministic ordinary artifacts and decompressed gbAs payloads across duplicate 8000-frame runs",
        ],
        "not_covered": [
            "cropped rows 20..23 and never-visible padding columns 24..31",
            "transient FF55/VBK/SVBK/IE/IME sequencing inside the helper (separate ABI gate)",
            "Stage-7 menu round trips and non-publication transition code",
            "Crystal Dragon / scene $0E containment",
            "PPU scanout within an individual CPU/DMA write instruction",
        ],
        "promotable_by_itself": False,
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
