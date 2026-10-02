#!/usr/bin/env python3
"""Candidate-bound r273 Stage-7 SELECT-menu roundtrip containment gate.

The default static mode does not launch an emulator.  It binds the frozen
dual-plane candidate and static receipt to one exact publication savestate
from the deterministic r273 visual pair, audits the Lua probe contract,
validates both VRAM
planes in the fixture, and executes fail-closed mutation controls.

The explicitly requested live mode launches only through the checked-in
single-flight wrapper.  It requires a SHA-bound static receipt, then proves a
complete optimized helper before and after SELECT, no helper/DMA activity
while the native Window/menu owns the display, an exact C4E0 6x20 Window with
no BG-map alias, restored DMA/bank/interrupt state, and an exact displayed
r273 populated tile+attribute plane after close.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import time
from typing import Any
import zlib


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage7_dual_plane_menu_roundtrip.lua"
VERIFIER = Path(__file__).resolve()
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
CANDIDATE = ROOT / "tmp/stage7-skip-invisible-padding-r273/candidate.gb"
STATIC_CANDIDATE_RECEIPT = (
    ROOT / "tmp/stage7-skip-invisible-padding-r273/abi-static-receipt.json"
)
R4A = ROOT / "tmp/stage7-skip-invisible-padding-r273/visual-live-r1b"
FIXTURE = R4A / "stage7.flip000039.ss0"
R4A_MANIFEST = R4A / "run-manifest.json"
R4A_FLIPS = R4A / "stage7.flip-events.tsv"
DEFAULT_STATIC_OUTPUT = (
    ROOT / "tmp/stage7-skip-invisible-padding-r273/menu-roundtrip-static-receipt.json"
)

EXPECTED_CANDIDATE_SHA256 = (
    "09d75d4461d911f4ed55c929c676346b1f7851e015bdbd867f307f8d9f1cc1d8"
)
EXPECTED_CANDIDATE_STATIC_RECEIPT_SHA256 = (
    "4e35d5f659a5ab7339bb37fe630118d69b541368deeab7f4aae4cabf121abac0"
)
EXPECTED_FIXTURE_SHA256 = (
    "db6b02ce3d385751ad8130952ae5cac8952982ef237b5e2e3d4da3d60e61e9c2"
)
EXPECTED_FIXTURE_GBAS_SHA256 = (
    "c0c232d57181f2f1873951f12933ed9b9e593f49997c23049b63f9721da227ef"
)
EXPECTED_R4A_MANIFEST_SHA256 = (
    "9e2f8ee0a01812f7e6355a06896c71bf54546e01329788b09734102501d67575"
)
EXPECTED_R4A_FLIPS_SHA256 = (
    "35f7154bb53c54c75b076751ff37709b91e452173dbd67d352a6f1863aa81895"
)
EXPECTED_LAUNCHER_SHA256 = (
    "46fe5b57771627e9141e359bd93c9d821c2b873d34162e355dfec33896649570"
)
EXPECTED_FLIP_ROW = (
    "39\t172\t12E0\t0\t01\t9C00\t07\t04\t0C\t00\t00\t0\t"
    "\tflip000039.ss0"
)

GB_STATE_SIZE = 0x11800
GB_STATE_MAGIC = 0x00400003
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

HELPER_BANK = 22
HELPER_ENTRY = 0x6C80
FASTPATH_START = 0x6CE8
ATTR_DMA_STORE = 0x713D
TILE_DMA_STORE = 0x7187
EXACT_EXIT = 0x436D
OUTER_RETURN = 0x12E0
POST_PUBLISH = 0x1302
FALLBACK_NATIVE = 0x71B3
CALLER_REJECT = 0x71BD
ATOMIC_FALLBACK = 0x71C1
STAGE7_LUT_ROM_OFFSET = HELPER_BANK * 0x4000 + 0x7600 - 0x4000
STAGE7_LUT_SHA256 = (
    "cfb5fe66cecfb2887abd8f8e828d311265217831888713ddeb50d8b0f4a6a84a"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path.resolve())


def validated_scratch_path(path: Path, *, label: str) -> Path:
    """Restrict generated artifacts to project-approved scratch roots."""

    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(resolved != root and resolved.is_relative_to(root)
                for root in roots),
            f"{label} must be a child of repo tmp/ or /mnt/data/tmp/")
    return resolved


def serialized_state(path: Path) -> bytes:
    """Extract one CRC-valid exact-size mGBA Game Boy machine state."""

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
            require(end == len(data), f"trailing bytes after IEND: {path}")
        offset = end
    require(saw_iend, f"PNG savestate lacks IEND: {path}")
    require(len(states) == 1,
            f"expected one gbAs chunk, found {len(states)}: {path}")
    state = states[0]
    require(len(state) == GB_STATE_SIZE,
            f"gbAs size is {len(state):#x}, expected {GB_STATE_SIZE:#x}")
    require(int.from_bytes(state[0:4], "little") == GB_STATE_MAGIC,
            "unsupported Game Boy savestate version")
    require(state[0x0008] & 0x80, "savestate is not a CGB machine")
    return state


def io_byte(state: bytes | bytearray, address: int) -> int:
    require(0xFF00 <= address <= 0xFF7F, f"not I/O: ${address:04X}")
    return state[IO + address - 0xFF00]


def hram_byte(state: bytes | bytearray, address: int) -> int:
    require(0xFF80 <= address <= 0xFFFE, f"not HRAM: ${address:04X}")
    return state[HRAM + address - 0xFF80]


def wram0_bytes(
    state: bytes | bytearray, address: int, size: int = 1,
) -> bytes:
    require(0xC000 <= address <= 0xCFFF, f"not WRAM0: ${address:04X}")
    offset = WRAM0 + address - 0xC000
    require(offset + size <= WRAM1, "WRAM0 read crosses its bank")
    return bytes(state[offset:offset + size])


def wram1_byte(state: bytes | bytearray, address: int) -> int:
    require(0xD000 <= address <= 0xDFFF, f"not WRAM1: ${address:04X}")
    return state[WRAM1 + address - 0xD000]


def set_io(state: bytearray, address: int, value: int) -> None:
    state[IO + address - 0xFF00] = value


def set_hram(state: bytearray, address: int, value: int) -> None:
    state[HRAM + address - 0xFF80] = value


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address <= 0x7FFF,
            "invalid switchable-bank address")
    return bank * 0x4000 + address - 0x4000


def candidate_lut(rom: bytes) -> bytes:
    lut = rom[STAGE7_LUT_ROM_OFFSET:STAGE7_LUT_ROM_OFFSET + 0x100]
    require(len(lut) == 0x100, "candidate Stage-7 LUT is truncated")
    require(sha256_bytes(lut) == STAGE7_LUT_SHA256,
            "candidate Stage-7 LUT identity changed")
    require(set(lut) == {0, 2, 4, 5},
            f"candidate LUT has unexpected slots: {sorted(set(lut))}")
    return lut


def compare_plane(
    state: bytes | bytearray, base: int, lut: bytes,
) -> dict[str, Any]:
    require(base in {0x9800, 0x9C00}, "invalid BG map base")
    source = wram0_bytes(state, 0xC1A0, 24 * 24)
    map_offset = base - 0x8000
    tile_mismatches: list[str] = []
    attr_mismatches: list[str] = []
    histogram: dict[int, int] = {}
    for row in range(20):
        for col in range(24):
            source_offset = row * 24 + col
            map_index = map_offset + row * 32 + col
            wanted_tile = source[source_offset]
            actual_tile = state[VRAM0 + map_index]
            if actual_tile != wanted_tile and len(tile_mismatches) < 16:
                tile_mismatches.append(
                    f"{col},{row}:${actual_tile:02X}>${wanted_tile:02X}"
                )
            actual_attr = state[VRAM1 + map_index]
            wanted_attr = lut[wanted_tile]
            histogram[wanted_attr] = histogram.get(wanted_attr, 0) + 1
            if actual_attr != wanted_attr and len(attr_mismatches) < 16:
                attr_mismatches.append(
                    f"{col},{row}:${actual_attr:02X}>${wanted_attr:02X}"
                )
    require(not tile_mismatches,
            f"displayed 480-tile plane mismatches: {tile_mismatches}")
    require(not attr_mismatches,
            f"displayed 480-attribute plane has semantic trails: "
            f"{attr_mismatches}")
    return {
        "base": f"${base:04X}",
        "tile_cells": 480,
        "attribute_cells": 480,
        "attribute_rows": list(range(20)),
        "semantic_columns": list(range(24)),
        "tile_mismatches": 0,
        "attribute_mismatches": 0,
        "semantic_trails": 0,
        "desired_attr_histogram": {
            str(key): value for key, value in sorted(histogram.items())
        },
        "source_sha256": sha256_bytes(source),
    }


def audit_fixture(state: bytes, rom: bytes) -> dict[str, Any]:
    """Prove r4a flip 9 is a clean candidate-owned publication state."""

    require(sha256_bytes(state) == EXPECTED_FIXTURE_GBAS_SHA256,
            "fixture gbAs identity changed")
    require(int.from_bytes(state[CPU_PC:CPU_PC + 2], "little") == 0x12EC,
            "fixture is not at exact primary LCDC publication store")
    require(int.from_bytes(
        state[MEMORY_CURRENT_ROM_BANK:MEMORY_CURRENT_ROM_BANK + 2], "little"
    ) == 1, "fixture ROM bank is not 1")
    require(state[MEMORY_CURRENT_WRAM_BANK] == 1,
            "fixture serialized WRAM bank is not 1")
    require(state[VIDEO_CURRENT_VRAM_BANK] == 0,
            "fixture serialized VRAM bank is not 0")
    require(io_byte(state, 0xFF55) == 0xFF,
            "fixture FF55 is not exactly idle")
    require(io_byte(state, 0xFF4F) & 1 == 0, "fixture VBK is not 0")
    require(io_byte(state, 0xFF70) & 7 == 1, "fixture SVBK is not 1")
    require(state[IE] == 0x07, "fixture IE is not $07")
    flags = int.from_bytes(state[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little")
    require(flags & MEMORY_FLAG_IME, "fixture IME is not enabled")
    require(not flags & MEMORY_FLAG_HDMA_ACTIVE,
            "fixture serialized HDMA-active flag is set")
    require(hram_byte(state, 0xFFC1) == 1, "fixture is not gameplay")
    require(hram_byte(state, 0xFFBA) == 6, "fixture is not Stage 7")
    require(wram1_byte(state, 0xD880) == 8, "fixture scene is not $08")
    require(hram_byte(state, 0xFFBD) == 7, "fixture room is not $07")
    require(hram_byte(state, 0xFFA5) == 0 and hram_byte(state, 0xFFE0) == 0,
            "fixture helper latches were not restored")
    lcdc = io_byte(state, 0xFF40)
    require(lcdc & 0x80, "fixture LCD is disabled")
    require(not lcdc & 0x20, "fixture Window is enabled")
    displayed = 0x9C00 if lcdc & 0x08 else 0x9800
    target = 0x9C00
    require(displayed != target, "fixture target is not hidden")
    require(wram1_byte(state, 0xDC0B) & 1 == 1,
            "fixture selector does not choose $9C00")
    lut = candidate_lut(rom)
    require(wram0_bytes(state, 0xC600, 0x100) == lut,
            "fixture C600 differs from candidate immutable LUT")
    plane = compare_plane(state, target, lut)
    return {
        "pc": "$12EC",
        "publisher": "$12E0",
        "target": "$9C00",
        "displayed_before_store": f"${displayed:04X}",
        "room": "$07",
        "ff55": "$FF",
        "vbk": 0,
        "svbk": 1,
        "ie": "$07",
        "ime": True,
        "plane": plane,
    }


def audit_post_state(state: bytes | bytearray, rom: bytes) -> dict[str, Any]:
    """Audit the exact post-menu state saved after the primary publisher."""

    pc = int.from_bytes(state[CPU_PC:CPU_PC + 2], "little")
    require(pc == POST_PUBLISH,
            f"post-close state PC=${pc:04X}, expected ${POST_PUBLISH:04X}")
    require(int.from_bytes(
        state[MEMORY_CURRENT_ROM_BANK:MEMORY_CURRENT_ROM_BANK + 2], "little"
    ) == 1, "post-close mapped ROM bank is not 1")
    require(state[MEMORY_CURRENT_WRAM_BANK] == 1,
            "post-close serialized WRAM bank is not 1")
    require(state[VIDEO_CURRENT_VRAM_BANK] == 0,
            "post-close serialized VRAM bank is not 0")
    require(io_byte(state, 0xFF55) == 0xFF,
            "post-close FF55 is not exactly idle")
    require(io_byte(state, 0xFF4F) & 1 == 0, "post-close VBK is not 0")
    require(io_byte(state, 0xFF70) & 7 == 1, "post-close SVBK is not 1")
    require(state[IE] == 0x07, "post-close IE is not $07")
    flags = int.from_bytes(state[MEMORY_FLAGS:MEMORY_FLAGS + 2], "little")
    require(flags & MEMORY_FLAG_IME, "post-close IME is not enabled")
    require(not flags & MEMORY_FLAG_HDMA_ACTIVE,
            "post-close serialized HDMA-active flag is set")
    require(hram_byte(state, 0xFFC1) == 1,
            "post-close state is not gameplay")
    require(hram_byte(state, 0xFFE4) == 0,
            "post-close native menu flag is still set")
    require(hram_byte(state, 0xFFBA) == 6, "post-close state is not Stage 7")
    require(wram1_byte(state, 0xD880) == 8,
            "post-close scene is not Stage-7 gameplay")
    require(hram_byte(state, 0xFFA5) == 0 and hram_byte(state, 0xFFE0) == 0,
            "post-close helper latches were not restored")
    require(io_byte(state, 0xFF47) == 0xE4,
            "post-close DMG palette is not stable")
    require(wram1_byte(state, 0xDF4C) == 0,
            "post-close palette scheduler is not idle")
    lcdc = io_byte(state, 0xFF40)
    require(lcdc & 0x80, "post-close LCD is disabled")
    require(not lcdc & 0x20, "post-close Window remains enabled")
    base = 0x9C00 if lcdc & 0x08 else 0x9800
    lut = candidate_lut(rom)
    require(wram0_bytes(state, 0xC600, 0x100) == lut,
            "post-close C600 differs from candidate immutable LUT")
    expected_crc = zlib.crc32(rom) & 0xFFFFFFFF
    require(int.from_bytes(state[4:8], "little") == expected_crc,
            "post-close state ROM CRC does not bind the candidate")
    plane = compare_plane(state, base, lut)
    return {
        "pc": f"${pc:04X}",
        "displayed_base": f"${base:04X}",
        "window_enabled": False,
        "ff55": "$FF",
        "vbk": 0,
        "svbk": 1,
        "ie": "$07",
        "ime": True,
        "plane": plane,
    }


def parse_banked_label(raw: object, bank: int, label: str) -> int:
    prefix = f"bank{bank}:$"
    require(isinstance(raw, str) and raw.startswith(prefix),
            f"invalid {label}: {raw!r}")
    return int(raw[len(prefix):], 16)


def audit_candidate_contract(rom: bytes) -> dict[str, Any]:
    require(sha256_bytes(rom) == EXPECTED_CANDIDATE_SHA256,
            "candidate identity changed")
    require(sha256(STATIC_CANDIDATE_RECEIPT)
            == EXPECTED_CANDIDATE_STATIC_RECEIPT_SHA256,
            "candidate static receipt identity changed")
    receipt = json.loads(STATIC_CANDIDATE_RECEIPT.read_text())
    require(receipt.get("status") == "STATIC_PASS_LIVE_GATES_REQUIRED",
            "candidate static audit is not green")
    require(receipt.get("emulator_run") is False,
            "candidate static receipt unexpectedly claims emulator evidence")
    require(receipt.get("in_memory_candidate", {}).get("sha256")
            == EXPECTED_CANDIDATE_SHA256,
            "candidate receipt binds another ROM")
    helper = receipt.get("helper", {})
    require(helper.get("bank") == HELPER_BANK, "wrong helper bank")
    require(helper.get("entry") == "$6C80", "wrong helper entry")
    require(helper.get("end") == "$7232", "wrong helper end")
    labels = helper.get("trace_labels", {})
    expected_labels = {
        "entry": HELPER_ENTRY,
        "phase1_attr_compile": FASTPATH_START,
        "attr_FF55_store": ATTR_DMA_STORE,
        "tile_FF55_store": TILE_DMA_STORE,
        "fallback_native": FALLBACK_NATIVE,
        "caller_reject": CALLER_REJECT,
        "fallback_after_atomic": ATOMIC_FALLBACK,
    }
    for name, address in expected_labels.items():
        require(parse_banked_label(labels.get(name), HELPER_BANK, name)
                == address, f"candidate receipt changed {name}")
    require(labels.get("exact_pre_RETI_ABI") == "bank1:$436D",
            "candidate exact exit label changed")
    require(labels.get("post_RETI_outer_returns") == ["fixed:$12E0"],
            "candidate admitted caller set changed")
    guards = receipt.get("runtime_guards", {})
    require(guards.get("gameplay_guard")
            == "$FFC1 < $02 (exactly $00/$01)",
            "candidate lacks the exact r273 transition/gameplay guard")
    require(guards.get("camera_domain") == ["$00", "$04", "$08", "$0C"],
            "candidate camera domain changed")
    require("LCDC.5 must be clear" in receipt.get("runtime_guards", {}).get(
        "window_guard", ""), "candidate lacks Window guard")
    crop = receipt.get("visible_crop_rebind", {})
    require(crop.get("schema") == "penta-stage7-r273-static-rebind-v1",
            "candidate lacks the r273 visible-crop proof")
    require(crop.get("visible_rows") == list(range(20))
            and crop.get("visible_columns") == list(range(22))
            and crop.get("semantic_columns_compiled") == list(range(24)),
            "candidate visible/semantic crop geometry changed")
    require(crop.get("attribute_blocks") == 40
            and crop.get("tile_rows") == 20
            and crop.get("tile_blocks") == 40,
            "candidate DMA crop geometry changed")
    require(rom[bank_offset(HELPER_BANK, ATTR_DMA_STORE):
                bank_offset(HELPER_BANK, ATTR_DMA_STORE) + 2] == b"\xE0\x55",
            "attribute DMA store is no longer inline LDH [$FF55],A")
    require(rom[bank_offset(HELPER_BANK, TILE_DMA_STORE):
                bank_offset(HELPER_BANK, TILE_DMA_STORE) + 2] == b"\xE0\x55",
            "tile DMA store is no longer inline LDH [$FF55],A")
    candidate_lut(rom)
    return {
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "candidate_static_receipt_sha256": (
            EXPECTED_CANDIDATE_STATIC_RECEIPT_SHA256
        ),
        "helper_range": "bank22:$6C80-$7232",
        "helper_entry": "bank22:$6C80",
        "optimized_start": "bank22:$6CE8",
        "dma_sites": ["bank22:$713D", "bank22:$7187"],
        "exact_exit": "bank1:$436D",
        "outer_return": "fixed:$12E0",
    }


PROBE_CONSTANTS = {
    "HELPER_BANK": 0x16,
    "HELPER_ENTRY": HELPER_ENTRY,
    "FASTPATH_START": FASTPATH_START,
    "ATTR_DMA_STORE": ATTR_DMA_STORE,
    "TILE_DMA_STORE": TILE_DMA_STORE,
    "EXACT_EXIT": EXACT_EXIT,
    "OUTER_RETURN": OUTER_RETURN,
    "POST_PUBLISH": POST_PUBLISH,
    "FALLBACK_NATIVE": FALLBACK_NATIVE,
    "CALLER_REJECT": CALLER_REJECT,
    "ATOMIC_FALLBACK": ATOMIC_FALLBACK,
}

PROBE_REQUIRED_SNIPPETS = (
    "local raw_vram = assert(emu.memory.vram)",
    "for row = 0, 5 do",
    "for col = 0, 19 do",
    "for row = 0, 19 do",
    "emu:read8(0xC4E0 + row * 20 + col)",
    "emu:read8(0xFF4B) ~= 0x07 or emu:read8(0xFF4A) ~= 0x60",
    "raw_vram:read8(base - 0x8000 + row * 32 + col)",
    "if menu_owned() then\n"
    "    helper_entries_menu_owned = helper_entries_menu_owned + 1",
    "if window_visible() then\n"
    "    helper_entries_window_visible = helper_entries_window_visible + 1",
    "if menu_owned() then dma_menu_owned = dma_menu_owned + 1 end",
    "if window_visible() then dma_window_visible = dma_window_visible + 1 end",
    "if helper_depth ~= 0 or fastpath_active then\n"
    "      helper_active_menu_owned_frames =",
    "menu_hardware_mismatch_frames = menu_hardware_mismatch_frames + 1",
    "menu_ff55_nonidle_frames = menu_ff55_nonidle_frames + 1",
    "menu_vbk_nonzero_frames = menu_vbk_nonzero_frames + 1",
    "menu_svbk_non1_frames = menu_svbk_non1_frames + 1",
    "menu_ie_non07_frames = menu_ie_non07_frames + 1",
    "if ff55_bad or svbk_bad or ie_bad then",
    "return emu:read8(0xFFE4) ~= 0 or window_visible()",
    "local function vram_cpu_readable()",
    "or (emu:read8(0xFF41) & 3) <= 1",
    "or not vram_cpu_readable() then",
    "and (emu:read8(0xFF70) & 7) == 1 and vram_cpu_readable() then",
    "capture_pre_snapshot()",
    'dump_snapshot(OUT .. ".pre.9800.tiles.bin", pre_snapshot_tiles[0x9800])',
    'dump_snapshot(OUT .. ".pre.9800.attrs.bin", pre_snapshot_attrs[0x9800])',
    'dump_snapshot(OUT .. ".pre.9c00.tiles.bin", pre_snapshot_tiles[0x9C00])',
    'dump_snapshot(OUT .. ".pre.9c00.attrs.bin", pre_snapshot_attrs[0x9C00])',
    "compare_intervening_visible_frame()",
    "local expected_tiles = pre_snapshot_tiles[current_base]",
    "local expected_attrs = pre_snapshot_attrs[current_base]",
    "actual_attr ~= emu:read8(0xC600 + tile)",
    "pre_snapshot_attrs[base][index] ~= emu:read8(0xC600 + tile)",
    "pre_snapshot_semantic_checked_cells =\n"
    "          pre_snapshot_semantic_checked_cells + 1",
    "current_helper_target ~= current_base",
    'current_helper_target = read_register("HL") & 0xFFFF',
    "current_helper_target == bg_map(emu:read8(0xFF40))",
    "intervening_attr_unchecked_helper_frames =\n"
    "      intervening_attr_unchecked_helper_frames + 1",
    "intervening_attr_ppu_blocked_frames =\n"
    "      intervening_attr_ppu_blocked_frames + 1",
    "intervening_attr_unjustified_frames =\n"
    "      intervening_attr_unjustified_frames + 1",
    "intervening_visible_map_write_events =",
    "C.WATCHPOINT_TYPE.WRITE_CHANGE",
    "stage7_lut_write_events = stage7_lut_write_events + 1",
    "expected = lcd_on and 0xA7 or 0x27",
    "current_attr_commands ~= 1 or current_tile_commands ~= 20",
    'type(result) ~= "number" or result <= 0',
    'install(FALLBACK_NATIVE, function() fallback_hit("native") end)',
    'install(CALLER_REJECT, function() fallback_hit("caller") end)',
    'install(ATOMIC_FALLBACK, function() fallback_hit("atomic") end)',
    'return emu:loadStateFile(STATE_FILE)',
    'return emu:saveStateFile(FINAL_STATE)',
    'local marker = assert(io.open(OUT .. ".done", "w"))',
    'tail:sub(5, 8) ~= "IEND"',
    "state_save_stable_frames >= 2",
    'keys = KEY_SELECT',
    'finish("fail", "select-open-not-acknowledged")',
    'finish("fail", "select-close-not-acknowledged")',
)


def audit_probe_source(source: str) -> dict[str, Any]:
    require("raw_vram:read8(0x2000 +" not in source,
            "probe treats out-of-domain raw VRAM as bank 1")
    for name, expected in PROBE_CONSTANTS.items():
        match = re.search(
            rf"^local {re.escape(name)} = (0x[0-9A-Fa-f]+|[0-9]+)$",
            source, re.MULTILINE,
        )
        require(match is not None, f"probe lacks exact constant {name}")
        require(int(match.group(1), 0) == expected,
                f"probe changed {name}")
    for snippet in PROBE_REQUIRED_SNIPPETS:
        require(snippet in source, f"probe lacks contract: {snippet}")
    require(source.count("install(HELPER_ENTRY") == 1,
            "helper entry breakpoint is not unique")
    require(source.count("install(FASTPATH_START") == 1,
            "optimized-start breakpoint is not unique")
    require(source.count("install(ATTR_DMA_STORE") == 1,
            "attribute DMA breakpoint is not unique")
    require(source.count("install(TILE_DMA_STORE") == 1,
            "tile DMA breakpoint is not unique")
    require(source.count("install(EXACT_EXIT") == 1,
            "exact-exit breakpoint is not unique")
    require(source.count("install(POST_PUBLISH") == 1,
            "post-publication breakpoint is not unique")
    require(source.count('type(result) ~= "number" or result <= 0') == 2,
            "both range watchpoints must require positive installation IDs")
    require(source.count("pre_snapshot_semantic_mismatch_cells = 0") == 1,
            "pre-menu semantic failures must accumulate across refreshes")
    return {
        "probe_sha256": sha256_bytes(source.encode()),
        "constants": {name: f"${value:04X}" if value > 0xFF else value
                      for name, value in PROBE_CONSTANTS.items()},
        "window_cells_per_visible_frame": 120,
        "raw_vram_bank1_assumptions": 0,
    }


def audit_r4a_provenance(state: bytes) -> dict[str, Any]:
    require(sha256(R4A_MANIFEST) == EXPECTED_R4A_MANIFEST_SHA256,
            "r4a manifest identity changed")
    require(sha256(R4A_FLIPS) == EXPECTED_R4A_FLIPS_SHA256,
            "r4a flip trace identity changed")
    require(sha256(FIXTURE) == EXPECTED_FIXTURE_SHA256,
            "r4a fixture identity changed")
    require(sha256_bytes(state) == EXPECTED_FIXTURE_GBAS_SHA256,
            "r4a fixture machine identity changed")
    manifest = json.loads(R4A_MANIFEST.read_text())
    require(manifest.get("status") == "PASS", "r4a soak did not pass")
    require(manifest.get("identity_intact") is True,
            "r4a identities changed during its run")
    require(manifest.get("identity_before", {}).get("candidate_sha256")
            == EXPECTED_CANDIDATE_SHA256, "r4a used another candidate")
    invocation = manifest.get("invocation", {})
    require(invocation.get("stages") == [7], "r4a was not Stage-7-only")
    require(invocation.get("frames") == 8000, "r4a was not 8000 frames")
    require(invocation.get("flip_states") is True,
            "r4a did not capture publication states")
    rows = R4A_FLIPS.read_text().splitlines()
    require(EXPECTED_FLIP_ROW in rows, "r4a flip-9 trace row changed")
    return {
        "manifest_sha256": EXPECTED_R4A_MANIFEST_SHA256,
        "flip_trace_sha256": EXPECTED_R4A_FLIPS_SHA256,
        "fixture_sha256": EXPECTED_FIXTURE_SHA256,
        "fixture_gbAs_sha256": EXPECTED_FIXTURE_GBAS_SHA256,
        "flip_record": EXPECTED_FLIP_ROW,
        "candidate_owned": True,
    }


def parse_probe_report(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        require(key and key not in result, f"duplicate probe field: {key}")
        result[key] = value
    return result


def audit_snapshot_plane(
    tiles: bytes, attrs: bytes, lut: bytes, *, label: str,
) -> dict[str, Any]:
    """Independently bind one dumped physical map to immutable semantics."""

    require(len(tiles) == 0x400 and len(attrs) == 0x400,
            f"{label} snapshot plane has wrong size")
    mismatches: list[str] = []
    for row in range(20):
        for col in range(24):
            index = row * 32 + col
            wanted = lut[tiles[index]]
            if attrs[index] != wanted and len(mismatches) < 16:
                mismatches.append(
                    f"{col},{row}:${attrs[index]:02X}>${wanted:02X}"
                )
    require(not mismatches,
            f"{label} pre-menu snapshot has semantic attr trails: "
            f"{mismatches}")
    return {
        "semantic_cells": 480,
        "semantic_rows": list(range(20)),
        "semantic_columns": list(range(24)),
        "semantic_mismatches": 0,
    }


REPORT_INT_FIELDS = (
    "frames", "state_loaded", "breakpoint_failures", "menu_seen",
    "menu_closed", "menu_visible_frames", "menu_owned_frames",
    "select_open_frames", "select_close_frames", "ffc1_non1_frames",
    "ffe4_nonzero_frames",
    "window_mismatch_cells", "window_mismatch_frames",
    "worst_window_mismatches", "window_geometry_mismatch_frames",
    "map_alias_frames", "helper_entries_pre",
    "helper_entries_post", "helper_entries_menu_owned",
    "helper_entries_window_visible", "helper_exits_menu_owned",
    "helper_active_menu_owned_frames", "menu_hardware_mismatch_frames",
    "menu_ff55_nonidle_frames", "menu_vbk_nonzero_frames",
    "menu_svbk_non1_frames", "menu_ie_non07_frames",
    "fastpath_hits_pre",
    "fastpath_hits_post", "fastpath_hits_menu_owned",
    "fastpath_visible_target_hits", "helper_exits_pre",
    "helper_exits_post", "attr_dma_pre", "attr_dma_post", "tile_dma_pre",
    "tile_dma_post", "dma_menu_owned", "dma_window_visible",
    "invalid_dma_commands", "helper_command_shape_violations",
    "abi_violations", "scene_violations", "watchpoint_failures",
    "fallback_native_hits", "caller_reject_hits", "atomic_fallback_hits",
    "pre_snapshot_ok", "pre_snapshot_refreshes",
    "pre_snapshot_semantic_mismatch_cells",
    "pre_snapshot_semantic_checked_cells", "intervening_visible_frames",
    "intervening_base_9800_frames", "intervening_base_9c00_frames",
    "intervening_tile_mismatch_frames",
    "intervening_tile_mismatch_cells", "intervening_attr_checked_frames",
    "intervening_attr_unchecked_helper_frames",
    "intervening_attr_ppu_blocked_frames",
    "intervening_attr_unjustified_frames",
    "intervening_attr_mismatch_frames", "intervening_attr_mismatch_cells",
    "intervening_semantic_attr_mismatch_frames",
    "intervening_semantic_attr_mismatch_cells",
    "intervening_visible_map_write_events", "state_save_request_ok",
    "stage7_lut_write_events", "state_save_ok", "state_save_wait_frames",
    "state_save_stable_frames",
)

FINAL_HARDWARE_PATTERN = re.compile(
    r"^ff55:FF,vbk:00,svbk:01,ie:07,ffc1:01,ffe4:00,"
    r"lcdc:([0-9A-F]{2}),scene:08,stage:06,room:([0-9A-F]{2})$"
)


def report_failures(
    report: dict[str, str], *, menu_hold: int, frame_limit: int,
) -> list[str]:
    failures: list[str] = []
    values: dict[str, int] = {}
    for key in REPORT_INT_FIELDS:
        try:
            values[key] = int(report.get(key, ""), 10)
        except ValueError:
            failures.append(f"missing/invalid integer {key}")
    if failures:
        return failures

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    check(report.get("status") == "ok" and report.get("reason") == "complete",
          "probe did not complete")
    check(values["state_loaded"] == 1, "fixture was not loaded")
    check(values["breakpoint_failures"] == 0, "breakpoint install failed")
    check(0 < values["frames"] <= frame_limit, "invalid frame count")
    check(values["menu_seen"] == 1 and values["menu_closed"] == 1,
          "SELECT did not open and close the native menu")
    check(values["menu_visible_frames"] >= menu_hold,
          "too few exact visible Window frames")
    check(values["menu_owned_frames"] >= values["menu_visible_frames"],
          "menu ownership was shorter than Window visibility")
    check(values["select_open_frames"] >= 2
          and values["select_close_frames"] >= 2,
          "SELECT open/close pulses were not emitted")
    check(values["ffc1_non1_frames"] == 0,
          "FFC1 left the candidate's exact gameplay value during roundtrip")
    check(values["ffe4_nonzero_frames"] > 0,
          "native FFE4 menu ownership was not observed")
    check(0 <= values["menu_vbk_nonzero_frames"]
          <= values["menu_owned_frames"],
          "menu VBK telemetry exceeds native ownership")
    check(values["pre_snapshot_ok"] == 1,
          "pre-menu physical planes were not captured")
    check(values["pre_snapshot_refreshes"] >= 1,
          "pre-menu physical-plane authority was never refreshed")
    check(values["pre_snapshot_semantic_checked_cells"]
          == 960 * values["pre_snapshot_refreshes"],
          "pre-menu dual-map semantic coverage is incomplete")
    check(report.get("pre_snapshot_active_base") in {"9800", "9C00"},
          "pre-menu snapshot has an invalid active BG base")
    check(values["intervening_visible_frames"] >= 1,
          "no post-close/pre-flip visible frame was audited")
    check(values["intervening_attr_checked_frames"] >= 1,
          "no safe post-close/pre-flip attribute frame was audited")
    check(
        values["intervening_attr_checked_frames"]
        + values["intervening_attr_unchecked_helper_frames"]
        + values["intervening_attr_ppu_blocked_frames"]
        == values["intervening_visible_frames"],
        "post-close attribute-frame accounting is incomplete",
    )
    check(
        values["intervening_base_9800_frames"]
        + values["intervening_base_9c00_frames"]
        == values["intervening_visible_frames"],
        "post-close physical-map frame accounting is incomplete",
    )
    for key in (
        "window_mismatch_cells", "window_mismatch_frames",
        "worst_window_mismatches", "window_geometry_mismatch_frames",
        "map_alias_frames",
        "helper_entries_menu_owned", "helper_entries_window_visible",
        "helper_exits_menu_owned", "helper_active_menu_owned_frames",
        "menu_hardware_mismatch_frames", "menu_ff55_nonidle_frames",
        "menu_svbk_non1_frames",
        "menu_ie_non07_frames", "fastpath_hits_menu_owned",
        "fastpath_visible_target_hits",
        "dma_menu_owned", "dma_window_visible",
        "invalid_dma_commands", "helper_command_shape_violations",
        "abi_violations", "scene_violations", "watchpoint_failures",
        "fallback_native_hits", "caller_reject_hits", "atomic_fallback_hits",
        "pre_snapshot_semantic_mismatch_cells",
        "intervening_tile_mismatch_frames", "intervening_tile_mismatch_cells",
        "intervening_attr_mismatch_frames", "intervening_attr_mismatch_cells",
        "intervening_semantic_attr_mismatch_frames",
        "intervening_semantic_attr_mismatch_cells",
        "intervening_attr_unjustified_frames",
        "intervening_visible_map_write_events", "stage7_lut_write_events",
    ):
        check(values[key] == 0, f"nonzero containment field {key}")
    for period in ("pre", "post"):
        entries = values[f"helper_entries_{period}"]
        fast = values[f"fastpath_hits_{period}"]
        exits = values[f"helper_exits_{period}"]
        attrs = values[f"attr_dma_{period}"]
        tiles = values[f"tile_dma_{period}"]
        check(entries >= 1, f"no helper entry {period}-menu")
        check(fast >= 1, f"optimized helper not active {period}-menu")
        check(entries == fast == exits,
              f"unbalanced helper lifecycle {period}-menu")
        check(attrs == fast and tiles == 20 * fast,
              f"wrong DMA command shape {period}-menu")
    check(values["state_save_request_ok"] == 1,
          "post-close state save was not requested")
    check(values["state_save_ok"] == 1,
          "post-close state did not reach a stable complete PNG")
    check(values["state_save_wait_frames"] >= 2
          and values["state_save_stable_frames"] >= 2,
          "post-close state completion barrier was not exercised")
    hardware = report.get("final_hardware", "")
    hardware_match = FINAL_HARDWARE_PATTERN.fullmatch(hardware)
    check(hardware_match is not None, "final hardware summary was not restored")
    if hardware_match is not None:
        lcdc = int(hardware_match.group(1), 16)
        check(lcdc & 0x80 != 0 and lcdc & 0x20 == 0,
              "final LCD/Window state was not restored")
    transitions = report.get("transitions", "")
    for phase in (":open:", ":menu:", ":close:", ":post:"):
        check(phase in transitions, f"transition log lacks {phase[1:-1]}")
    return failures


def passing_report(menu_hold: int = 80) -> dict[str, str]:
    report = {key: "0" for key in REPORT_INT_FIELDS}
    report.update({
        "status": "ok",
        "reason": "complete",
        "frames": "400",
        "state_loaded": "1",
        "menu_seen": "1",
        "menu_closed": "1",
        "menu_visible_frames": str(menu_hold),
        "menu_owned_frames": str(menu_hold + 8),
        "select_open_frames": "2",
        "select_close_frames": "2",
        "ffc1_non1_frames": "0",
        "ffe4_nonzero_frames": str(menu_hold + 2),
        "helper_entries_pre": "1",
        "fastpath_hits_pre": "1",
        "helper_exits_pre": "1",
        "attr_dma_pre": "1",
        "tile_dma_pre": "20",
        "helper_entries_post": "1",
        "fastpath_hits_post": "1",
        "helper_exits_post": "1",
        "attr_dma_post": "1",
        "tile_dma_post": "20",
        "pre_snapshot_ok": "1",
        "pre_snapshot_active_base": "9C00",
        "pre_snapshot_refreshes": "2",
        "pre_snapshot_semantic_checked_cells": "1920",
        "intervening_visible_frames": "2",
        "intervening_base_9800_frames": "1",
        "intervening_base_9c00_frames": "1",
        "intervening_attr_checked_frames": "1",
        "intervening_attr_unchecked_helper_frames": "1",
        "state_save_request_ok": "1",
        "state_save_ok": "1",
        "state_save_wait_frames": "2",
        "state_save_stable_frames": "2",
        "final_hardware": (
            "ff55:FF,vbk:00,svbk:01,ie:07,ffc1:01,ffe4:00,"
            "lcdc:8B,scene:08,stage:06,room:07"
        ),
        "transitions": "f1:open:x;f2:menu:x;f82:close:x;f90:post:x",
    })
    return report


def determinism_checks(replays: list[dict[str, Any]]) -> dict[str, bool]:
    checks = {
        "two_replays": len(replays) == 2,
        "parsed_reports_exact": False,
        "pre_menu_9800_tile_planes_exact": False,
        "pre_menu_9800_attribute_planes_exact": False,
        "pre_menu_9c00_tile_planes_exact": False,
        "pre_menu_9c00_attribute_planes_exact": False,
        "post_close_gbAs_exact": False,
    }
    if len(replays) != 2:
        return checks
    first, second = replays
    first_snapshot = first.get("pre_menu_snapshot")
    second_snapshot = second.get("pre_menu_snapshot")
    checks.update({
        "parsed_reports_exact": (
            first.get("probe_report") == second.get("probe_report")
        ),
        "pre_menu_9800_tile_planes_exact": (
            isinstance(first_snapshot, dict)
            and isinstance(second_snapshot, dict)
            and first_snapshot.get("9800_tile_sha256") is not None
            and first_snapshot.get("9800_tile_sha256")
            == second_snapshot.get("9800_tile_sha256")
        ),
        "pre_menu_9800_attribute_planes_exact": (
            isinstance(first_snapshot, dict)
            and isinstance(second_snapshot, dict)
            and first_snapshot.get("9800_attribute_sha256") is not None
            and first_snapshot.get("9800_attribute_sha256")
            == second_snapshot.get("9800_attribute_sha256")
        ),
        "pre_menu_9c00_tile_planes_exact": (
            isinstance(first_snapshot, dict)
            and isinstance(second_snapshot, dict)
            and first_snapshot.get("9c00_tile_sha256") is not None
            and first_snapshot.get("9c00_tile_sha256")
            == second_snapshot.get("9c00_tile_sha256")
        ),
        "pre_menu_9c00_attribute_planes_exact": (
            isinstance(first_snapshot, dict)
            and isinstance(second_snapshot, dict)
            and first_snapshot.get("9c00_attribute_sha256") is not None
            and first_snapshot.get("9c00_attribute_sha256")
            == second_snapshot.get("9c00_attribute_sha256")
        ),
        "post_close_gbAs_exact": (
            first.get("post_close_gbAs_sha256") is not None
            and first.get("post_close_gbAs_sha256")
            == second.get("post_close_gbAs_sha256")
        ),
    })
    return checks


def mutation_controls(
    source: str, fixture_state: bytes, rom: bytes,
) -> dict[str, bool]:
    controls: dict[str, bool] = {}

    source_mutations = {
        "helper_entry": ("0x6C80", "0x6C81"),
        "fastpath_start": ("0x6CE8", "0x6CE9"),
        "attr_dma_site": ("0x713D", "0x713E"),
        "tile_dma_site": ("0x7187", "0x7188"),
        "attr_dma_command": (
            "expected = lcd_on and 0xA7 or 0x27",
            "expected = lcd_on and 0xAF or 0x2F",
        ),
        "tile_dma_count": (
            "current_attr_commands ~= 1 or current_tile_commands ~= 20",
            "current_attr_commands ~= 1 or current_tile_commands ~= 24",
        ),
        "window_width": ("for col = 0, 19 do", "for col = 0, 18 do"),
        "window_source": (
            "emu:read8(0xC4E0 + row * 20 + col)",
            "emu:read8(0xC4E1 + row * 20 + col)",
        ),
        "window_geometry": (
            "emu:read8(0xFF4B) ~= 0x07 or emu:read8(0xFF4A) ~= 0x60",
            "emu:read8(0xFF4B) ~= 0x08 or emu:read8(0xFF4A) ~= 0x60",
        ),
        "native_menu_vbk_nonfatal": (
            "if ff55_bad or svbk_bad or ie_bad then",
            "if ff55_bad or vbk_bad or svbk_bad or ie_bad then",
        ),
        "helper_menu_counter": (
            "if menu_owned() then\n"
            "    helper_entries_menu_owned = helper_entries_menu_owned + 1",
            "if false then\n"
            "    helper_entries_menu_owned = helper_entries_menu_owned + 1",
        ),
        "helper_window_counter": (
            "if window_visible() then\n"
            "    helper_entries_window_visible = helper_entries_window_visible + 1",
            "if false then\n"
            "    helper_entries_window_visible = helper_entries_window_visible + 1",
        ),
        "dma_menu_counter": (
            "if menu_owned() then dma_menu_owned = dma_menu_owned + 1 end",
            "if false then dma_menu_owned = dma_menu_owned + 1 end",
        ),
        "dma_window_counter": (
            "if window_visible() then dma_window_visible = dma_window_visible + 1 end",
            "if false then dma_window_visible = dma_window_visible + 1 end",
        ),
        "watchpoint_positive_id": (
            'type(result) ~= "number" or result <= 0',
            'type(result) ~= "number"',
        ),
        "hidden_helper_target": (
            "current_helper_target ~= current_base",
            "current_helper_target == current_base",
        ),
        "exact_helper_target_HL": (
            'current_helper_target = read_register("HL") & 0xFFFF',
            'current_helper_target = (read_register("H") & 0xFF) << 8',
        ),
        "visible_target_detector": (
            "current_helper_target == bg_map(emu:read8(0xFF40))",
            "current_helper_target ~= bg_map(emu:read8(0xFF40))",
        ),
        "attr_frame_partition": (
            "intervening_attr_unchecked_helper_frames =\n"
            "      intervening_attr_unchecked_helper_frames + 1",
            "intervening_attr_unchecked_helper_frames =\n"
            "      intervening_attr_unchecked_helper_frames + 0",
        ),
        "ppu_read_guard": (
            "or (emu:read8(0xFF41) & 3) <= 1",
            "or (emu:read8(0xFF41) & 3) <= 3",
        ),
        "ppu_blocked_partition": (
            "intervening_attr_ppu_blocked_frames =\n"
            "      intervening_attr_ppu_blocked_frames + 1",
            "intervening_attr_ppu_blocked_frames =\n"
            "      intervening_attr_ppu_blocked_frames + 0",
        ),
        "attr_unjustified_detector": (
            "intervening_attr_unjustified_frames =\n"
            "      intervening_attr_unjustified_frames + 1",
            "intervening_attr_unjustified_frames =\n"
            "      intervening_attr_unjustified_frames + 0",
        ),
        "dual_map_tile_authority": (
            "local expected_tiles = pre_snapshot_tiles[current_base]",
            "local expected_tiles = pre_snapshot_tiles[0x9800]",
        ),
        "dual_map_attr_authority": (
            "local expected_attrs = pre_snapshot_attrs[current_base]",
            "local expected_attrs = pre_snapshot_attrs[0x9800]",
        ),
        "live_semantic_attr_authority": (
            "actual_attr ~= emu:read8(0xC600 + tile)",
            "actual_attr == emu:read8(0xC600 + tile)",
        ),
        "snapshot_semantic_attr_authority": (
            "pre_snapshot_attrs[base][index] ~= emu:read8(0xC600 + tile)",
            "pre_snapshot_attrs[base][index] == emu:read8(0xC600 + tile)",
        ),
        "cumulative_snapshot_semantics": (
            "pre_snapshot_semantic_checked_cells =\n"
            "          pre_snapshot_semantic_checked_cells + 1",
            "pre_snapshot_semantic_mismatch_cells = 0\n"
            "        pre_snapshot_semantic_checked_cells =\n"
            "          pre_snapshot_semantic_checked_cells + 1",
        ),
        "lut_write_counter": (
            "stage7_lut_write_events = stage7_lut_write_events + 1",
            "stage7_lut_write_events = stage7_lut_write_events + 0",
        ),
        "native_menu_owner": (
            "return emu:read8(0xFFE4) ~= 0 or window_visible()",
            "return window_visible()",
        ),
        "state_IEND_barrier": (
            'tail:sub(5, 8) ~= "IEND"',
            'tail:sub(5, 8) ~= "NOPE"',
        ),
        "state_stability_barrier": (
            "state_save_stable_frames >= 2",
            "state_save_stable_frames >= 0",
        ),
        "completion_marker": (
            'local marker = assert(io.open(OUT .. ".done", "w"))',
            'local marker = assert(io.open(OUT .. ".not-done", "w"))',
        ),
    }
    for name, (old, new) in source_mutations.items():
        require(old in source, f"source mutation anchor missing: {name}")
        mutant = source.replace(old, new, 1)
        try:
            audit_probe_source(mutant)
        except AssertionError:
            controls[f"mutated_probe_{name}_rejected"] = True
        else:
            controls[f"mutated_probe_{name}_rejected"] = False

    base_report = passing_report()
    require(not report_failures(base_report, menu_hold=80, frame_limit=1800),
            "synthetic passing report does not pass")
    report_mutations: dict[str, tuple[str, str]] = {
        "pre_fastpath": ("fastpath_hits_pre", "0"),
        "helper_menu": ("helper_entries_menu_owned", "1"),
        "helper_window": ("helper_entries_window_visible", "1"),
        "dma_menu": ("dma_menu_owned", "1"),
        "dma_window": ("dma_window_visible", "1"),
        "helper_exit_menu": ("helper_exits_menu_owned", "1"),
        "helper_active_menu": ("helper_active_menu_owned_frames", "1"),
        "menu_hardware": ("menu_hardware_mismatch_frames", "1"),
        "menu_ff55": ("menu_ff55_nonidle_frames", "1"),
        "menu_svbk": ("menu_svbk_non1_frames", "1"),
        "menu_ie": ("menu_ie_non07_frames", "1"),
        "window_cell": ("window_mismatch_cells", "1"),
        "window_frame": ("window_mismatch_frames", "1"),
        "window_geometry": ("window_geometry_mismatch_frames", "1"),
        "map_alias": ("map_alias_frames", "1"),
        "missing_select_open": ("select_open_frames", "0"),
        "missing_select_close": ("select_close_frames", "0"),
        "wrong_ffc1": ("ffc1_non1_frames", "1"),
        "missing_ffe4": ("ffe4_nonzero_frames", "0"),
        "missing_snapshot": ("pre_snapshot_ok", "0"),
        "missing_snapshot_refresh": ("pre_snapshot_refreshes", "0"),
        "missing_snapshot_semantic_coverage": (
            "pre_snapshot_semantic_checked_cells", "0"
        ),
        "stale_snapshot_semantics": (
            "pre_snapshot_semantic_mismatch_cells", "1"
        ),
        "missing_intervening_frame": ("intervening_visible_frames", "0"),
        "missing_map_partition": ("intervening_base_9c00_frames", "0"),
        "missing_intervening_attrs": ("intervening_attr_checked_frames", "0"),
        "intervening_tile_trail": ("intervening_tile_mismatch_cells", "1"),
        "intervening_attr_trail": ("intervening_attr_mismatch_cells", "1"),
        "intervening_semantic_attr_trail": (
            "intervening_semantic_attr_mismatch_cells", "1"
        ),
        "intervening_attr_unjustified": (
            "intervening_attr_unjustified_frames", "1"
        ),
        "visible_fastpath_target": ("fastpath_visible_target_hits", "1"),
        "intervening_visible_write": (
            "intervening_visible_map_write_events", "1"
        ),
        "stage7_lut_write": ("stage7_lut_write_events", "1"),
        "wrong_tile_count": ("tile_dma_post", "23"),
        "invalid_dma": ("invalid_dma_commands", "1"),
        "bad_abi": ("abi_violations", "1"),
        "bad_scene": ("scene_violations", "1"),
        "watchpoint_missing": ("watchpoint_failures", "1"),
        "native_fallback": ("fallback_native_hits", "1"),
        "caller_fallback": ("caller_reject_hits", "1"),
        "atomic_fallback": ("atomic_fallback_hits", "1"),
        "missing_state_request": ("state_save_request_ok", "0"),
        "missing_state": ("state_save_ok", "0"),
        "missing_state_wait": ("state_save_wait_frames", "0"),
        "missing_state_stability": ("state_save_stable_frames", "0"),
    }
    for name, (key, value) in report_mutations.items():
        mutant = dict(base_report)
        mutant[key] = value
        controls[f"mutated_report_{name}_rejected"] = bool(
            report_failures(mutant, menu_hold=80, frame_limit=1800)
        )

    deterministic_replay = {
        "probe_report": base_report,
        "pre_menu_snapshot": {
            "9800_tile_sha256": "11" * 32,
            "9800_attribute_sha256": "22" * 32,
            "9c00_tile_sha256": "33" * 32,
            "9c00_attribute_sha256": "44" * 32,
        },
        "post_close_gbAs_sha256": "55" * 32,
    }
    deterministic_pair = [
        copy.deepcopy(deterministic_replay),
        copy.deepcopy(deterministic_replay),
    ]
    require(all(determinism_checks(deterministic_pair).values()),
            "synthetic deterministic pair does not pass")
    deterministic_mutants = {
        "missing_replay": deterministic_pair[:1],
        "report": copy.deepcopy(deterministic_pair),
        "pre_9800_tiles": copy.deepcopy(deterministic_pair),
        "pre_9800_attrs": copy.deepcopy(deterministic_pair),
        "pre_9c00_tiles": copy.deepcopy(deterministic_pair),
        "pre_9c00_attrs": copy.deepcopy(deterministic_pair),
        "post_state": copy.deepcopy(deterministic_pair),
    }
    deterministic_mutants["report"][1]["probe_report"]["frames"] = "401"
    deterministic_mutants["pre_9800_tiles"][1]["pre_menu_snapshot"][
        "9800_tile_sha256"
    ] = "66" * 32
    deterministic_mutants["pre_9800_attrs"][1]["pre_menu_snapshot"][
        "9800_attribute_sha256"
    ] = "77" * 32
    deterministic_mutants["pre_9c00_tiles"][1]["pre_menu_snapshot"][
        "9c00_tile_sha256"
    ] = "88" * 32
    deterministic_mutants["pre_9c00_attrs"][1]["pre_menu_snapshot"][
        "9c00_attribute_sha256"
    ] = "99" * 32
    deterministic_mutants["post_state"][1]["post_close_gbAs_sha256"] = (
        "AA" * 32
    )
    for name, mutant in deterministic_mutants.items():
        controls[f"mutated_determinism_{name}_rejected"] = not all(
            determinism_checks(mutant).values()
        )

    lut = candidate_lut(rom)
    snapshot_tiles = bytes(0x400)
    snapshot_attrs = bytes([lut[0]]) * 0x400
    require(audit_snapshot_plane(
        snapshot_tiles, snapshot_attrs, lut, label="synthetic"
    )["semantic_mismatches"] == 0, "synthetic snapshot does not pass")
    mutated_snapshot_attrs = bytearray(snapshot_attrs)
    mutated_snapshot_attrs[0] ^= 1
    try:
        audit_snapshot_plane(
            snapshot_tiles, bytes(mutated_snapshot_attrs), lut,
            label="mutated synthetic",
        )
    except AssertionError:
        controls["mutated_snapshot_semantic_attr_rejected"] = True
    else:
        controls["mutated_snapshot_semantic_attr_rejected"] = False
    cropped_snapshot_attrs = bytearray(snapshot_attrs)
    cropped_snapshot_attrs[20 * 32] ^= 1
    audit_snapshot_plane(
        snapshot_tiles, bytes(cropped_snapshot_attrs), lut,
        label="cropped-row synthetic",
    )
    controls["snapshot_cropped_row_excluded"] = True

    synthetic = bytearray(fixture_state)
    synthetic[CPU_PC:CPU_PC + 2] = POST_PUBLISH.to_bytes(2, "little")
    set_io(synthetic, 0xFF40, io_byte(synthetic, 0xFF40) | 0x08)
    synthetic_plane = audit_post_state(synthetic, rom)["plane"]
    require(synthetic_plane["tile_cells"] == 480
            and synthetic_plane["attribute_cells"] == 480,
            "synthetic post-close state does not pass")
    displayed = 0x9C00
    tile_offset = VRAM0 + displayed - 0x8000
    attr_offset = VRAM1 + displayed - 0x8000
    state_mutations: dict[str, tuple[int, int]] = {
        "tile_trail": (tile_offset, synthetic[tile_offset] ^ 1),
        "attr_trail": (attr_offset, synthetic[attr_offset] ^ 1),
        "ff55_active": (IO + 0x55, 0x00),
        "vbk1": (IO + 0x4F, io_byte(synthetic, 0xFF4F) | 1),
        "svbk2": (IO + 0x70, 2),
        "ie_wrong": (IE, 0x04),
        "ffc1_menu": (HRAM + 0x41, 0),
        "ffe4_menu": (HRAM + 0x64, 1),
        "window_enabled": (IO + 0x40, io_byte(synthetic, 0xFF40) | 0x20),
        "scene_wrong": (WRAM1 + 0x880, 7),
        "stage_wrong": (HRAM + 0x3A, 5),
        "lut_changed": (WRAM0 + 0x600, synthetic[WRAM0 + 0x600] ^ 1),
        "hdma_active": (
            MEMORY_FLAGS,
            synthetic[MEMORY_FLAGS] | MEMORY_FLAG_HDMA_ACTIVE,
        ),
        "pc_wrong": (CPU_PC, 0x01),
    }
    for name, (offset, value) in state_mutations.items():
        mutant = bytearray(synthetic)
        mutant[offset] = value
        try:
            audit_post_state(mutant, rom)
        except AssertionError:
            controls[f"mutated_state_{name}_rejected"] = True
        else:
            controls[f"mutated_state_{name}_rejected"] = False

    controls["mutated_candidate_identity_rejected"] = (
        sha256_bytes(rom[:-1] + bytes([rom[-1] ^ 1]))
        != EXPECTED_CANDIDATE_SHA256
    )
    controls["mutated_fixture_identity_rejected"] = (
        sha256_bytes(FIXTURE.read_bytes()[:-1]
                     + bytes([FIXTURE.read_bytes()[-1] ^ 1]))
        != EXPECTED_FIXTURE_SHA256
    )
    require(all(controls.values()),
            f"one or more mutation controls escaped: "
            f"{[name for name, passed in controls.items() if not passed]}")
    return controls


def identity() -> dict[str, str]:
    return {
        "candidate_sha256": sha256(CANDIDATE),
        "candidate_static_receipt_sha256": sha256(STATIC_CANDIDATE_RECEIPT),
        "fixture_sha256": sha256(FIXTURE),
        "fixture_gbAs_sha256": sha256_bytes(serialized_state(FIXTURE)),
        "r4a_manifest_sha256": sha256(R4A_MANIFEST),
        "r4a_flip_trace_sha256": sha256(R4A_FLIPS),
        "probe_sha256": sha256(PROBE),
        "verifier_sha256": sha256(VERIFIER),
        "launcher_sha256": sha256(LAUNCHER),
    }


def build_static_receipt() -> dict[str, Any]:
    for path in (
        CANDIDATE, STATIC_CANDIDATE_RECEIPT, FIXTURE, R4A_MANIFEST,
        R4A_FLIPS, PROBE, VERIFIER, LAUNCHER,
    ):
        require(path.is_file(), f"required artifact missing: {path}")
    rom = CANDIDATE.read_bytes()
    state = serialized_state(FIXTURE)
    source = PROBE.read_text()
    candidate_contract = audit_candidate_contract(rom)
    provenance = audit_r4a_provenance(state)
    fixture = audit_fixture(state, rom)
    probe_contract = audit_probe_source(source)
    controls = mutation_controls(source, state, rom)
    identities = identity()
    require(identities["launcher_sha256"] == EXPECTED_LAUNCHER_SHA256,
            "single-flight launcher identity changed")
    return {
        "schema": "penta-stage7-dual-plane-menu-roundtrip-static-v3",
        "status": "STATIC_PASS_LIVE_MENU_GATE_REQUIRED",
        "emulator_run": False,
        "candidate": {
            "path": relative(CANDIDATE),
            **candidate_contract,
        },
        "fixture_provenance": {
            "path": relative(FIXTURE),
            **provenance,
            "machine_contract": fixture,
        },
        "probe_contract": probe_contract,
        "identities": identities,
        "live_contract": {
            "deterministic_replays": 2,
            "replay_equivalence": (
                "exact parsed probe report, pre-menu tile/attr blobs, and "
                "decompressed post-close gbAs state"
            ),
            "input": "native SELECT open and native SELECT close",
            "native_menu_ownership": (
                "FFE4 $00->$01->$00 plus visible Window; FFC1 remains exact $01"
            ),
            "optimized_helper_before_menu": True,
            "optimized_helper_after_menu": True,
            "helper_entries_while_menu_or_window_owned": 0,
            "DMA_commands_while_menu_or_window_owned": 0,
            "menu_time_hardware": (
                "fatal: FF55!=$FF, SVBK!=1, or IE!=$07; native Window "
                "maintenance intentionally leaves VBK1 selected on some frames"
            ),
            "menu_time_VBK1": "telemetry only; never part of unsafe aggregate",
            "visible_window": (
                "all 120 bank-0 tile IDs equal packed C4E0 6x20; menu "
                "attribute/color styling is outside this containment gate"
            ),
            "visible_window_BG_alias_frames": 0,
            "post_close_hardware": "FF55=$FF, VBK=0, SVBK=1, IE=$07",
            "post_close_display": (
                "tile IDs and attributes in r273 rows 0..19 and semantic "
                "columns 0..23 equal C1A0 and C600[tile], respectively"
            ),
            "post_close_semantic_trails": (
                "both pre-menu physical tile+attr maps are refreshed after "
                "every pre-menu helper; each active physical map remains exact "
                "on every audited close-to-flip frame, with zero visible-map "
                "write events, then exact 480-tile/480-attribute "
                "post-publication plane"
            ),
            "state_completion": (
                "Lua requires two equal complete-IEND sizes and writes ordered "
                ".done; Python then requires two equal CRC-valid gbAs parses"
            ),
            "final_state_PC": "$1302",
        },
        "mutation_controls": controls,
        "decision": "STATIC_GO_FOR_TWO_SEQUENTIAL_SINGLE_FLIGHT_MENU_REPLAYS",
    }


def write_static_receipt(path: Path) -> tuple[dict[str, Any], str]:
    path = validated_scratch_path(path, label="static receipt")
    receipt = build_static_receipt()
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
    return receipt, sha256_bytes(payload.encode())


def validate_bound_static_receipt(path: Path, expected_sha: str) -> dict[str, Any]:
    require(path.is_file(), f"static menu receipt missing: {path}")
    require(sha256(path) == expected_sha,
            "static menu receipt SHA does not match command binding")
    receipt = json.loads(path.read_text())
    require(receipt.get("schema")
            == "penta-stage7-dual-plane-menu-roundtrip-static-v3",
            "wrong static menu receipt schema")
    require(receipt.get("status") == "STATIC_PASS_LIVE_MENU_GATE_REQUIRED",
            "static menu audit did not pass")
    require(receipt.get("emulator_run") is False,
            "static menu receipt unexpectedly claims emulator evidence")
    require(receipt.get("decision")
            == "STATIC_GO_FOR_TWO_SEQUENTIAL_SINGLE_FLIGHT_MENU_REPLAYS",
            "static menu receipt did not grant a bounded live gate")
    require(receipt.get("identities") == identity(),
            "tool/candidate/fixture identity changed since static audit")
    fresh = build_static_receipt()
    require(receipt == fresh, "static menu receipt is stale or modified")
    return receipt


def stop_owned_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run_replay(output: Path, args: argparse.Namespace) -> dict[str, Any]:
    """Run one exact replay through the guarded launcher and audit artifacts."""

    output.mkdir()
    runtime = output / "runtime"
    runtime.mkdir()
    runtime_rom = runtime / "candidate.gb"
    runtime_state = runtime / "publication.ss0"
    shutil.copy2(CANDIDATE, runtime_rom)
    shutil.copy2(FIXTURE, runtime_state)
    require(sha256(runtime_rom) == EXPECTED_CANDIDATE_SHA256,
            "runtime ROM copy changed")
    require(sha256(runtime_state) == EXPECTED_FIXTURE_SHA256,
            "runtime fixture copy changed")

    raw_report = output / "probe.report"
    completion_marker = Path(str(raw_report) + ".done")
    final_state = output / "post-close.ss0"
    emulator_log = output / "emulator.log"
    identity_before = identity()
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE7_MENU_OUT": str(raw_report),
        "STAGE7_MENU_STATE": str(runtime_state),
        "STAGE7_MENU_FINAL_STATE": str(final_state),
        "STAGE7_MENU_FRAMES": str(args.frames),
        "STAGE7_MENU_HOLD": str(args.menu_hold),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    command = [
        str(LAUNCHER), "--fastforward",
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        str(runtime_rom), "--script", str(PROBE), "-l", "0",
    ]
    return_code: int | None = None
    timed_out = False
    completion_observed = False
    stable_state_observed = False
    stable_signature: tuple[int, str] | None = None
    stable_samples = 0
    with emulator_log.open("wb") as stream:
        process = subprocess.Popen(
            command, cwd=output, env=environment,
            stdout=stream, stderr=subprocess.STDOUT,
        )
        deadline = time.monotonic() + args.timeout
        try:
            while time.monotonic() < deadline:
                marker_status = None
                if completion_marker.is_file():
                    observed_status = completion_marker.read_text().strip()
                    if observed_status in {"ok", "fail"}:
                        marker_status = observed_status
                if marker_status is not None:
                    completion_observed = True
                    if marker_status != "ok":
                        break
                    if raw_report.is_file() and final_state.is_file():
                        try:
                            state = serialized_state(final_state)
                            signature = (
                                final_state.stat().st_size,
                                sha256_bytes(state),
                            )
                        except (AssertionError, OSError):
                            stable_signature = None
                            stable_samples = 0
                        else:
                            if signature == stable_signature:
                                stable_samples += 1
                            else:
                                stable_signature = signature
                                stable_samples = 1
                            if stable_samples >= 2:
                                stable_state_observed = True
                                break
                if process.poll() is not None and marker_status is None:
                    break
                time.sleep(0.05)
            else:
                timed_out = True
        finally:
            stop_owned_process(process)
            return_code = process.returncode

    identity_after = identity()
    failures: list[str] = []
    if timed_out:
        failures.append(f"live menu gate timed out after {args.timeout:.1f}s")
    if return_code == 75:
        failures.append("single-flight slot was already owned (exit 75)")
    if not completion_observed:
        failures.append("ordered probe completion marker missing")
    if completion_marker.is_file() \
            and completion_marker.read_text().strip() == "ok" \
            and not stable_state_observed:
        failures.append("post-close savestate was not CRC-valid and stable")
    if identity_before != identity_after:
        failures.append("candidate, fixture, receipt dependency, or tool changed")
    report: dict[str, str] = {}
    post_audit: dict[str, Any] | None = None
    if not raw_report.is_file():
        failures.append("probe report missing")
    else:
        report = parse_probe_report(raw_report)
        failures.extend(report_failures(
            report, menu_hold=args.menu_hold, frame_limit=args.frames,
        ))
    post_gbas_sha: str | None = None
    if not final_state.is_file():
        failures.append("post-close savestate missing")
    else:
        try:
            post_state = serialized_state(final_state)
            post_audit = audit_post_state(
                post_state, CANDIDATE.read_bytes(),
            )
            post_gbas_sha = sha256_bytes(post_state)
        except AssertionError as error:
            failures.append(str(error))
    snapshot_paths = {
        "9800_tile_sha256": Path(str(raw_report) + ".pre.9800.tiles.bin"),
        "9800_attribute_sha256": Path(str(raw_report) + ".pre.9800.attrs.bin"),
        "9c00_tile_sha256": Path(str(raw_report) + ".pre.9c00.tiles.bin"),
        "9c00_attribute_sha256": Path(str(raw_report) + ".pre.9c00.attrs.bin"),
    }
    snapshot: dict[str, Any] | None = None
    if any(not path.is_file() for path in snapshot_paths.values()):
        failures.append("pre-menu dual-physical-plane snapshot artifacts missing")
    elif any(path.stat().st_size != 0x400
             for path in snapshot_paths.values()):
        failures.append("pre-menu dual-physical-plane snapshot has wrong size")
    else:
        snapshot = {name: sha256(path)
                    for name, path in snapshot_paths.items()}
        snapshot["bytes_per_physical_bank_plane"] = 0x400
        lut = candidate_lut(CANDIDATE.read_bytes())
        for base in ("9800", "9c00"):
            try:
                semantic = audit_snapshot_plane(
                    snapshot_paths[f"{base}_tile_sha256"].read_bytes(),
                    snapshot_paths[f"{base}_attribute_sha256"].read_bytes(),
                    lut,
                    label=f"${base.upper()}",
                )
            except AssertionError as error:
                failures.append(str(error))
            else:
                snapshot[f"{base}_semantic_cells"] = semantic[
                    "semantic_cells"
                ]
                snapshot[f"{base}_semantic_mismatches"] = semantic[
                    "semantic_mismatches"
                ]
    return {
        "status": "PASS" if not failures else "FAIL",
        "path": relative(output),
        "identity_before": identity_before,
        "identity_after": identity_after,
        "runtime_candidate_sha256": sha256(runtime_rom),
        "runtime_fixture_sha256": sha256(runtime_state),
        "return_code": return_code,
        "timed_out": timed_out,
        "completion_observed": completion_observed,
        "stable_state_observed": stable_state_observed,
        "single_flight_busy": return_code == 75,
        "pre_menu_snapshot": snapshot,
        "post_close_state_sha256": (
            sha256(final_state) if final_state.is_file() else None
        ),
        "post_close_gbAs_sha256": post_gbas_sha,
        "probe_report": report,
        "post_close_state_audit": post_audit,
        "failures": failures,
    }


def run_live(args: argparse.Namespace) -> int:
    require(args.static_receipt is not None,
            "--run requires --static-receipt")
    require(args.static_receipt_sha is not None,
            "--run requires --static-receipt-sha")
    require(args.output is not None, "--run requires --output")
    static_receipt = validate_bound_static_receipt(
        args.static_receipt.resolve(), args.static_receipt_sha,
    )
    output = validated_scratch_path(args.output, label="live output")
    require(not output.exists(),
            f"output already exists; use a fresh receipt directory: {output}")
    output.mkdir(parents=True)
    gate_identity_before = identity()
    replays: list[dict[str, Any]] = []
    for replay_index in (1, 2):
        replay = run_replay(output / f"replay-{replay_index}", args)
        replays.append(replay)
        # Exit 75 means another exact owner has the project slot.  Fail closed
        # without racing it with the second requested replay.
        if replay["single_flight_busy"]:
            break

    failures = [
        f"replay-{index}: {failure}"
        for index, replay in enumerate(replays, 1)
        for failure in replay["failures"]
    ]
    if len(replays) != 2:
        failures.append("both deterministic sequential replays did not run")
    deterministic = determinism_checks(replays)
    for name, passed in deterministic.items():
        if not passed:
            failures.append(f"determinism check failed: {name}")
    gate_identity_after = identity()
    if gate_identity_before != gate_identity_after:
        failures.append("gate identities changed across duplicate replays")

    run_receipt = {
        "schema": "penta-stage7-dual-plane-menu-roundtrip-live-v3",
        "status": "PASS" if not failures else "FAIL",
        "candidate": relative(CANDIDATE),
        "fixture": relative(FIXTURE),
        "static_receipt": relative(args.static_receipt.resolve()),
        "static_receipt_sha256": args.static_receipt_sha,
        "static_decision": static_receipt["decision"],
        "identity_before": gate_identity_before,
        "identity_after": gate_identity_after,
        "invocation": {
            "replays": 2,
            "frames": args.frames,
            "menu_hold": args.menu_hold,
            "timeout_per_replay": args.timeout,
            "single_flight_launcher": relative(LAUNCHER),
            "parallel_emulators": 0,
        },
        "replays": replays,
        "determinism": deterministic,
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(run_receipt, indent=2, sort_keys=True) + "\n")
    if failures:
        print("FAIL: Stage-7 menu roundtrip containment gate")
        for failure in failures:
            print(f"  - {failure}")
        print(f"Receipt: {receipt_path}")
        return 1
    print("PASS: deterministic Stage-7 helper containment across SELECT menu")
    print(f"Receipt: {receipt_path}")
    return 0


def parse_sha(raw: str) -> str:
    value = raw.lower()
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise argparse.ArgumentTypeError("SHA-256 must be 64 hex digits")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--static-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--static-output", type=Path,
                        default=DEFAULT_STATIC_OUTPUT)
    parser.add_argument("--static-receipt", type=Path)
    parser.add_argument("--static-receipt-sha", type=parse_sha)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--frames", type=int, default=1800)
    parser.add_argument("--menu-hold", type=int, default=80)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    require(300 <= args.frames <= 5000, "--frames must be 300..5000")
    require(40 <= args.menu_hold <= 600, "--menu-hold must be 40..600")
    if args.static_only:
        static_output = validated_scratch_path(
            args.static_output, label="static receipt"
        )
        receipt, receipt_sha = write_static_receipt(static_output)
        print("STATIC GO: two sequential single-flight menu replays are authorized")
        print(f"Receipt: {static_output}")
        print(f"Receipt SHA-256: {receipt_sha}")
        print("Candidate: " + receipt["candidate"]["candidate_sha256"])
        print("Fixture: " + receipt["fixture_provenance"]["fixture_sha256"])
        print("Live command:")
        print(
            "python3 scripts/diagnostics/verify_stage7_dual_plane_menu_roundtrip.py "
            f"--run --static-receipt {relative(static_output)} "
            f"--static-receipt-sha {receipt_sha} "
            "--output tmp/stage7-skip-invisible-padding-r273/menu-roundtrip-live-r1"
        )
        return 0
    return run_live(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
