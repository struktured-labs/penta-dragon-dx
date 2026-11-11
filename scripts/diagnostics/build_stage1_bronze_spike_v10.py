#!/usr/bin/env python3
"""Stage-1 rotating-spike body uses the weathered-bronze BG7 row (v10).

The cylinder body, wall connectors and terminal caps previously shared BG5
with Stage-1 power pickups (gold/red).  This stage maps those cells onto the
Stage-1-only BG7 material row, retunes that row from gold to weathered bronze,
and remaps body highlight pixels off index 1 (floor-blue on the BG7 row) onto
index 0 (white specular) so the cylinder still reads round.  Teeth already
used BG7 and keep the floor-blue / floor-shadow blend indices.  Support stays
on BG6, pickups stay on their class palettes, and the normal YAML BG7 slot
used outside Stage 1 is left untouched.

Data-only: no new hooks, no attract-path code changes, timing unchanged.
YAML is the source of truth: category palettes come from
``palettes/bg_tile_categories.yaml`` and the bronze row from
``palettes/penta_palettes_v097.yaml`` ``stage1_hazard_palettes.RotatingSpikeTeeth``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "scripts/diagnostics")]

from stage1_hazard_art import (  # noqa: E402
    decode_tile,
    encode_tile,
    load_stage1_hazard_config,
    load_stage1_hazard_palette,
)

# Current main / menu-frame-reinstall tip (PR #88).
PARENT = "01f8e0b22719a438c9c28f16c09c5bde8ae06f3f8561ffe0c88c08ba02b39d20"
# Filled after the first exact rebuild.
CANDIDATE: str | None = "db348784914e4470db2878724c41073cd0fe564602e6788598706a3315fdd8af"

# Immutable / semantic / room-$01 Stage-1 LUTs in the v9 ROM.
LUT_OFFSETS = (0x037000, 0x050400, 0x050600)
GOLD_TEETH_ROW = bytes.fromhex("ff7f947eff034a3d")
GOLD_ROW_COPIES = 5

# Exact parent/candidate delta. Invertible; used only to reconstruct
# the v9 parent for unchanged-component contracts. Never a playback ROM.
DELTA = (
    (0x14E, '708e', '5485'),
    (0x1D602, '8f', '88'),
    (0x1D604, '1f', '10'),
    (0x1D606, '95', '90'),
    (0x1D608, '2a', '20'),
    (0x1D60A, 'a4', 'a0'),
    (0x1D612, 'ff', '00'),
    (0x1D614, 'ff', '00'),
    (0x1D616, '55', '00'),
    (0x1D618, 'aa', '00'),
    (0x1D61A, '11', '00'),
    (0x1D622, 'c0', '40'),
    (0x1D624, 'e0', '20'),
    (0x1D626, 'f0', '10'),
    (0x1D628, 'f8', '08'),
    (0x1D62A, '6c', '04'),
    (0x1D62C, '16', '02'),
    (0x1D62E, '03', '01'),
    (0x1D6B8, '11', '10'),
    (0x1D6BA, '2b', '20'),
    (0x1D6BC, '57', '40'),
    (0x1D6BE, 'bd', '80'),
    (0x1D6C2, 'ff', '00'),
    (0x1D6C4, 'ff', '00'),
    (0x1D6C6, '55', '00'),
    (0x1D6C8, 'ff', '3c'),
    (0x1D6CA, 'ff', '42'),
    (0x1D6CC, 'ff', '81'),
    (0x1D6CE, 'ff', '81'),
    (0x1D6D0, 'ff', '81'),
    (0x1D6D2, 'ff', '81'),
    (0x1D6D4, 'ff', '81'),
    (0x1D6D6, 'ff', '42'),
    (0x1D6D8, 'ff', '3c'),
    (0x1D6DA, '01', '00'),
    (0x1D6E2, 'ff', '00'),
    (0x1D6E4, 'ff', '00'),
    (0x1D6E6, '55', '00'),
    (0x1D6E8, 'aa', '00'),
    (0x1D6EA, '11', '00'),
    (0x1D6F0, 'fb', 'f1'),
    (0x1D6F2, '17', '11'),
    (0x1D6F4, '0b', '09'),
    (0x1D6F6, 'af', '09'),
    (0x1D6F8, '57', '05'),
    (0x1D6FA, 'ed', '05'),
    (0x1D6FC, 'ff', '05'),
    (0x1D6FE, 'dd', '05'),
    (0x1D7B0, 'aa', '80'),
    (0x1D7C0, 'ff', '81'),
    (0x1D7C2, 'ff', '81'),
    (0x1D7C4, 'ff', '42'),
    (0x1D7C6, 'ff', 'bc'),
    (0x1D7D6, 'ff', 'bc'),
    (0x1D7D8, 'ff', '43'),
    (0x1D7DA, 'ff', '81'),
    (0x1D7DC, 'ff', '81'),
    (0x1D7DE, 'ff', '81'),
    (0x1D7F0, 'af', '05'),
    (0x1D7F2, '45', '05'),
    (0x1D7F4, '07', '05'),
    (0x1D7F8, '5b', '59'),
    (0x1D7FC, 'fb', 'f9'),
    (0x1D7FE, 'f7', 'f1'),
    (0x368CC, 'ff03', 'b219'),
    (0x37060, '050505', '070707'),
    (0x3706B, '0505050505050505', '0707070707070707'),
    (0x3707B, '0505050505', '0707070707'),
    (0x428CC, 'ff03', 'b219'),
    (0x50460, '050505', '070707'),
    (0x5046B, '0505050505050505', '0707070707070707'),
    (0x5047B, '0505050505', '0707070707'),
    (0x50660, '050505', '070707'),
    (0x5066B, '0505050505050505', '0707070707070707'),
    (0x5067B, '0505050505', '0707070707'),
    (0x528CC, 'ff03', 'b219'),
    (0xC0252, 'ff03', 'b219'),
    (0xC02E2, 'ff03', 'b219'),
)



def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E:0x0150] = (
        (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    ).to_bytes(2, "big")


def _body_tiles(config) -> frozenset[int]:
    return (
        config.ring_tiles
        | config.body_tiles
        | config.connector_tiles
        | config.terminal_tiles
    )


def _bronze_row() -> bytes:
    slot, payload = load_stage1_hazard_palette()
    if slot != 7 or len(payload) != 8:
        raise ValueError("RotatingSpikeTeeth must be the 8-byte BG7 row")
    if payload == GOLD_TEETH_ROW:
        raise ValueError("RotatingSpikeTeeth is still the gold parent row")
    return payload


def _replace_gold_rows(rom: bytearray, bronze: bytes) -> int:
    if len(bronze) != 8:
        raise ValueError("bronze row must be 8 bytes")
    count = 0
    start = 0
    while True:
        index = bytes(rom).find(GOLD_TEETH_ROW, start)
        if index < 0:
            break
        rom[index:index + 8] = bronze
        count += 1
        start = index + 8
    return count


def _remap_highlights(rom: bytearray, config) -> int:
    """Map leftover BG5 highlight index 1 onto white (index 0)."""
    changed = 0
    tiles = _body_tiles(config)
    for tile in sorted(tiles):
        offset = config.source_offset + tile * 16
        raw = bytes(rom[offset:offset + 16])
        if len(raw) != 16:
            raise ValueError(f"spike tile ${tile:02X} falls outside the ROM")
        pixels = decode_tile(raw)
        remapped = [0 if pixel == 1 else pixel for pixel in pixels]
        encoded = encode_tile(remapped)
        if encoded != raw:
            rom[offset:offset + 16] = encoded
            changed += 1
    return changed


def _patch_luts(rom: bytearray, tiles: frozenset[int]) -> None:
    for offset in LUT_OFFSETS:
        table = bytearray(rom[offset:offset + 256])
        if len(table) != 256:
            raise ValueError(f"LUT at 0x{offset:06X} is truncated")
        for tile in tiles:
            current = table[tile]
            if current & 0x07 != 5:
                raise ValueError(
                    f"LUT 0x{offset:06X} tile ${tile:02X} is pal {current & 7}, not 5"
                )
            table[tile] = (current & 0xF8) | 7
        rom[offset:offset + 256] = table


def build(parent: bytes, original: bytes | None = None) -> bytes:
    if sha(parent) != PARENT:
        raise ValueError("bronze-spike v10 parent is not the exact v9 candidate")
    config = load_stage1_hazard_config()
    if config.body_palette != 7 or config.connector_palette != 7:
        raise ValueError("YAML fire-body / connector categories must be palette 7")
    if config.terminal_palette != 7:
        raise ValueError("YAML terminal-cap category must be palette 7")
    if config.tooth_palette != 7:
        raise ValueError("YAML tooth category must stay on palette 7")
    if config.support_palette != 6:
        raise ValueError("YAML support category must stay on palette 6")
    bronze = _bronze_row()
    tiles = _body_tiles(config)
    result = bytearray(parent)
    _patch_luts(result, tiles)
    replaced = _replace_gold_rows(result, bronze)
    if replaced != GOLD_ROW_COPIES:
        raise ValueError(
            f"expected {GOLD_ROW_COPIES} gold teeth-row copies, found {replaced}"
        )
    remapped = _remap_highlights(result, config)
    if remapped == 0:
        raise ValueError("no body/connector/cap tiles needed a highlight remap")
    update_checksums(result)
    out = bytes(result)
    if CANDIDATE is not None and sha(out) != CANDIDATE:
        raise ValueError(f"candidate identity drift: {sha(out)}")
    return out


def verify_installed(rom: bytes, original: bytes | None = None) -> list[str]:
    errors: list[str] = []
    if CANDIDATE is not None and sha(rom) != CANDIDATE:
        errors.append("candidate sha256 differs")
    config = load_stage1_hazard_config()
    tiles = _body_tiles(config)
    for offset in LUT_OFFSETS:
        table = rom[offset:offset + 256]
        for tile in tiles:
            if table[tile] & 0x07 != 7:
                errors.append(
                    f"LUT 0x{offset:06X} tile ${tile:02X} is pal {table[tile] & 7}"
                )
        for tile in config.support_tiles:
            if table[tile] & 0x07 != 6:
                errors.append(f"support tile ${tile:02X} left LUT 0x{offset:06X}")
        for tile in config.tooth_tiles:
            if table[tile] & 0x07 != 7:
                errors.append(f"tooth tile ${tile:02X} left LUT 0x{offset:06X}")
    bronze = _bronze_row()
    if rom.count(GOLD_TEETH_ROW):
        errors.append("gold teeth row still present")
    if rom.count(bronze) < GOLD_ROW_COPIES:
        errors.append("bronze teeth row copy count is short")
    # Pickups that historically share pal 5 must still be pal 5 in the main table.
    power = (0x8E, 0x8F, 0x9E, 0x9F, 0xA8, 0xA9, 0xB8, 0xB9,
             0xAA, 0xAB, 0xBA, 0xBB, 0xC8, 0xC9, 0xD8, 0xD9,
             0xCE, 0xCF, 0xDE, 0xDF)
    table = rom[LUT_OFFSETS[0]:LUT_OFFSETS[0] + 256]
    for tile in power:
        if table[tile] & 0x07 != 5:
            errors.append(f"power pickup ${tile:02X} is no longer pal 5")
    return errors



def changed_spans(_original: bytes | None = None) -> list[tuple[int, int]]:
    """Owned v10 spans, including checksums."""
    spans: list[tuple[int, int]] = []
    for offset, before_hex, after_hex in DELTA:
        before, after = bytes.fromhex(before_hex), bytes.fromhex(after_hex)
        if len(before) != len(after):
            raise ValueError("bronze-spike delta length mismatch")
        start, end = offset, offset + len(after)
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], max(spans[-1][1], end))
        else:
            spans.append((start, end))
    return spans


def reconstruct_parent(rom: bytes, original: bytes | None = None) -> bytes:
    """Invert the v10 overlay to the exact v9 / menu-frame parent."""
    if CANDIDATE is not None and sha(rom) != CANDIDATE:
        raise ValueError("not the exact bronze-spike v10 candidate")
    parent = bytearray(rom)
    previous_end = 0
    for offset, before_hex, after_hex in DELTA:
        before, after = bytes.fromhex(before_hex), bytes.fromhex(after_hex)
        if len(before) != len(after) or offset < previous_end:
            raise ValueError("invalid bronze-spike delta table")
        if parent[offset:offset + len(after)] != after:
            raise ValueError(f"bronze-spike delta differs at 0x{offset:06X}")
        parent[offset:offset + len(before)] = before
        previous_end = offset + len(after)
    out = bytes(parent)
    if sha(out) != PARENT or build(out, original) != rom:
        raise ValueError("bronze-spike v10 parent reconstruction failed")
    return out

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("parent", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or (ROOT / "tmp").resolve() not in args.output.resolve().parents:
        parser.error("fresh repository-local tmp output required")
    result = build(args.parent.read_bytes())
    args.output.mkdir(parents=True)
    (args.output / "candidate.gb").write_bytes(result)
    receipt = dict(
        schema="penta-stage1-bronze-spike-v10",
        parent_sha256=PARENT,
        candidate_sha256=sha(result),
        builder_sha256=sha(Path(__file__).read_bytes()),
        static_failures=verify_installed(result),
        lut_offsets=[hex(offset) for offset in LUT_OFFSETS],
    )
    (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
