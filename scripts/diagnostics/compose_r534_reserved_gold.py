#!/usr/bin/env python3
"""Apply the zero-runtime reserved-gold pickup policy to exact r534.

The r534 candidate already passes the complete emulator matrix and has strict
Stage-1 cadence.  This overlay changes only the two Stage-1 source-art halves,
their private bank-1 neutral-art mirror, BG0 color 1, and cartridge checksums.
It retains r534's complete copier, semantic hazard publisher, menu containment,
and later-stage architecture.

The art remap operates on r534 itself.  Its rotating-hazard variants therefore
remain the geometric input; this builder never substitutes an older tileset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v302_title_fix import (  # noqa: E402
    BANK13,
    STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR,
    STAGE1_HAZARD_PURE_MAP_ADDR,
    STAGE1_HIGH_TILE_GFX_OFFSET,
    STAGE1_LOW_TILE_GFX_OFFSET,
    TITLE_PALETTE_SOURCE_ADDR,
    apply_stage1_reserved_pickup_gold,
    build_stage1_hazard_bank1_neutral_art,
)


DEFAULT_BASE = ROOT / "tmp/stage4-cache-key-r534/candidate.gb"
DEFAULT_OUTPUT = ROOT / "tmp/r534-reserved-gold/candidate.gb"
DEFAULT_RECEIPT = ROOT / "tmp/r534-reserved-gold/build-receipt.json"
NATIVE_ROM = ROOT / "rom/Penta Dragon (J).gb"

BASE_SHA256 = (
    "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b"
)
CANDIDATE_SHA256 = (
    "c67cea343c448d35319f5381d0d15674fa1a2744515de3ff45ad20fda06296fa"
)
NATIVE_SHA256 = (
    "2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30"
)
ROM_SIZE = 32 * 0x4000
NATIVE_SIZE = 16 * 0x4000
TILE_HALF_SIZE = 0x800
HIGH_TILE_START = STAGE1_HIGH_TILE_GFX_OFFSET + TILE_HALF_SIZE
BG0_COLOR1_OFFSET = BANK13 + TITLE_PALETTE_SOURCE_ADDR - 0x4000 + 2
STAGE1_CODE_BANK = 0x13
NEUTRAL_ART_OFFSET = (
    STAGE1_CODE_BANK * 0x4000
    + STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR - 0x4000
)
NEUTRAL_ART_SIZE = 4 * 16
CHECKSUM_OFFSETS = frozenset((0x014D, 0x014E, 0x014F))
RESERVED_LOW_SHA256 = (
    "ee621badf3670fb77e5692bd4e885169975bf49a1d2820dd9fb096a932bc45b2"
)
RESERVED_HIGH_SHA256 = (
    "0e06fe32f85620ec591ef3d0eb620ec7c34fad0709a73f87891de255e82d6f3d"
)
RESERVED_NEUTRAL_ART_SHA256 = (
    "7b19bb3e71f5637b513fc907e477ed9dce2e699fc6a7aed3b358919d3f3fc3cb"
)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E] = 0
    rom[0x014F] = 0
    total = sum(rom) & 0xFFFF
    rom[0x014E] = total >> 8
    rom[0x014F] = total & 0xFF


def owned_offsets() -> set[int]:
    offsets = set(CHECKSUM_OFFSETS)
    offsets.update(range(
        STAGE1_LOW_TILE_GFX_OFFSET,
        STAGE1_LOW_TILE_GFX_OFFSET + TILE_HALF_SIZE,
    ))
    offsets.update(range(HIGH_TILE_START, HIGH_TILE_START + TILE_HALF_SIZE))
    offsets.update(range(BG0_COLOR1_OFFSET, BG0_COLOR1_OFFSET + 2))
    offsets.update(range(
        NEUTRAL_ART_OFFSET, NEUTRAL_ART_OFFSET + NEUTRAL_ART_SIZE,
    ))
    return offsets


def build(source: bytes, native: bytes) -> tuple[bytes, dict[str, object]]:
    if len(source) != ROM_SIZE or digest(source) != BASE_SHA256:
        raise ValueError("requires exact r534 base")
    if len(native) != NATIVE_SIZE or digest(native) != NATIVE_SHA256:
        raise ValueError("requires exact native ROM")

    rom = bytearray(source)
    if rom[STAGE1_HAZARD_PURE_MAP_ADDR + 1] != STAGE1_CODE_BANK:
        raise AssertionError("r534 Stage-1 code-bank selector changed")
    apply_stage1_reserved_pickup_gold(rom, native)
    neutral_art = build_stage1_hazard_bank1_neutral_art(rom)
    if len(neutral_art) != NEUTRAL_ART_SIZE:
        raise AssertionError("reserved-gold neutral-art mirror has wrong size")
    if digest(neutral_art) != RESERVED_NEUTRAL_ART_SHA256:
        raise AssertionError("reserved-gold neutral-art identity changed")
    rom[
        NEUTRAL_ART_OFFSET:NEUTRAL_ART_OFFSET + NEUTRAL_ART_SIZE
    ] = neutral_art
    low = rom[
        STAGE1_LOW_TILE_GFX_OFFSET:
        STAGE1_LOW_TILE_GFX_OFFSET + TILE_HALF_SIZE
    ]
    high = rom[HIGH_TILE_START:HIGH_TILE_START + TILE_HALF_SIZE]
    if digest(low) != RESERVED_LOW_SHA256:
        raise AssertionError("r534 reserved-gold low tile art identity changed")
    if digest(high) != RESERVED_HIGH_SHA256:
        raise AssertionError("r534 reserved-gold high tile art identity changed")
    update_checksums(rom)

    changed = {
        index for index, (before, after) in enumerate(zip(source, rom))
        if before != after
    }
    if not changed <= owned_offsets():
        raise AssertionError(
            "overlay changed bytes outside ownership: "
            f"{sorted(changed - owned_offsets())[:8]}"
        )

    report: dict[str, object] = {
        "schema": "penta.r534-reserved-gold-build.v1",
        "experimental": True,
        "promotable": False,
        "rejected_by": [
            "menu_window_publish_order",
            "shared_stage1_art_raster_equivalence",
        ],
        "visual_equivalence_retained": False,
        "base_sha256": BASE_SHA256,
        "candidate_sha256": digest(rom),
        "stage1_pickup_art_mode": "reserved-pickup-gold",
        "stage1_reserved_low_art_sha256": digest(low),
        "stage1_reserved_high_art_sha256": digest(high),
        "stage1_reserved_bank1_neutral_art_sha256": digest(neutral_art),
        "runtime_code_changed": False,
        "r534_copier_and_publication_retained": True,
        "later_stage_code_and_data_retained": True,
        "changed_bytes": len(changed),
    }
    if report["candidate_sha256"] != CANDIDATE_SHA256:
        raise AssertionError("exact r534 reserved-gold candidate identity changed")
    return bytes(rom), report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--native-rom", type=Path, default=NATIVE_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()

    result, report = build(args.base.read_bytes(), args.native_rom.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_bytes() != result:
        raise SystemExit(f"immutable candidate collision: {args.output}")
    args.output.write_bytes(result)
    args.receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
