#!/usr/bin/env python3
"""Restore exact Stage-1 tooth-cell backgrounds while retaining gold teeth.

Exact r290 correctly loads the immutable bank-1 hazard art and selects BG7,
but its BG7-safe environment remap collapses native Dungeon shade 2 onto
shade 1.  The stock shadow baselines (tiles $03/$04) consequently become flat
light-lavender squares around active/retracted teeth.

Keep BG7 index 2 gold, move the native Dungeon dark lavender to BG7 index 3,
and map non-tooth shadow pixels onto that index.  Floor pixels remain exact,
shadow pixels become exact, and tooth fills remain gold.  The deliberate
four-color compromise is that the black tooth outline becomes dark lavender;
the red/gold cylinder and every non-hazard palette remain unchanged.

This is a data-only diagnostic candidate.  It changes no executable byte and
therefore adds no runtime or transition timing cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-live-menu-selector-r290/candidate.gb"
BASE_RECEIPT = TMP / "stage1-live-menu-selector-r290/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-exact-background-r292/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-exact-background-r292/build-receipt.json"
BASE_SHA256 = "48582bed3b9c9746588de9d2de695927788b7b07a511b817da0cb36932d87736"
BASE_RECEIPT_SHA256 = (
    "232ea8935182e2647632e921e7086a76c16d7578be3c32d6058cb58727f91447"
)
EXPECTED_SHA256 = "924173f3cd82ea0ee2aeb9d520746d60d97ae6b224a965e3f15a150d047d1cb1"

ROM_SIZE = 32 * 0x4000
BANK_SIZE = 0x4000
STAGE1_ART_OFFSET = 0x1D000
NEUTRAL_ART_BANK = 19
NEUTRAL_ART_ADDR = 0x6C10
PALETTE_BANKS = (13, 16)
PALETTE_ADDR = 0x68C8

OLD_PALETTE = bytes.fromhex("FF 7F 94 7E FF 03 00 00")
NEW_PALETTE = bytes.fromhex("FF 7F 94 7E FF 03 4A 3D")

SOURCE_PATCHES = {
    0x68: (
        bytes.fromhex("C3 7E E7 3C FF 18 FF 00 FF 00 FF 00 FF 00 FF 00"),
        bytes.fromhex("C3 7F E7 3D FF 18 FF 55 FF 80 FF D4 FF E0 FF F0"),
    ),
    0x69: (
        bytes.fromhex("C3 7E E7 3C FF 18 FF 00 FF 00 FF 00 FF 00 FF 00"),
        bytes.fromhex("C3 FE E7 FC FF 98 FF 55 FF 00 FF 15 FF 03 FF 07"),
    ),
    0x76: (
        bytes.fromhex("D1 FF A1 FF C3 7E C3 7E E7 3C E7 3C FF 18 FF 00"),
        bytes.fromhex("D1 FF A1 FF C3 7E C3 7F E7 BC E7 FC FF F8 FF F0"),
    ),
    0x77: (
        bytes.fromhex("D1 FF A1 FF C3 7E C3 7E E7 3C E7 3C FF 18 FF 00"),
        bytes.fromhex("D1 FF A1 FF C3 FE C3 7F E7 3C E7 3D FF 1B FF 07"),
    ),
    0x78: (
        bytes.fromhex("C3 7E C3 7E E7 3C E7 3C FF 18 FF 00 FF 00 FF 00"),
        bytes.fromhex("C3 7F C3 7F E7 3C E7 7D FF 98 FF D4 FF E0 FF F0"),
    ),
    0x79: (
        bytes.fromhex("C3 7E C3 7E E7 3C E7 3C FF 18 FF 00 FF 00 FF 00"),
        bytes.fromhex("C3 FE C3 FE E7 BC E7 7D FF 18 FF 15 FF 03 FF 07"),
    ),
}

NEUTRAL_PATCHES = {
    0x03: (
        bytes.fromhex("FF 00 FF 00 FF 00 FF 00 FF 00 FF 00 FF 00 FF 00"),
        bytes.fromhex("FF E0 FF D4 FF 80 FF 55 FF 00 FF 15 FF 03 FF 07"),
    ),
    0x04: (
        bytes.fromhex("FF 00 FF 00 FF 00 FF 00 FF 00 FF 00 FF 00 FF 00"),
        bytes.fromhex("FF 03 FF 15 FF 00 FF 55 FF 80 FF D4 FF E0 FF F0"),
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def bank_offset(bank: int, address: int) -> int:
    require(bank > 0 and 0x4000 <= address < 0x8000, "bad banked address")
    return bank * BANK_SIZE + address - 0x4000


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    require(resolved != scratch and scratch in resolved.parents,
            f"{label} must be inside repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r290 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r290 receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r290 receipt names another candidate")
    require(len(OLD_PALETTE) == len(NEW_PALETTE) == 8,
            "Stage-1 BG7 row width changed")
    require(
        [int.from_bytes(NEW_PALETTE[index:index + 2], "little")
         for index in range(0, 8, 2)]
        == [0x7FFF, 0x7E94, 0x03FF, 0x3D4A],
        "new Stage-1 BG7 does not preserve white/light/gold/dark",
    )

    rom = bytearray(source)
    source_receipts = []
    allowed: set[int] = {0x014D, 0x014E, 0x014F}
    for tile, (old, new) in SOURCE_PATCHES.items():
        offset = STAGE1_ART_OFFSET + tile * 16
        require(len(old) == len(new) == 16, f"tile ${tile:02X} width changed")
        require(source[offset:offset + 16] == old,
                f"tooth tile ${tile:02X} preimage changed")
        rom[offset:offset + 16] = new
        allowed.update(range(offset, offset + 16))
        source_receipts.append({
            "tile": f"${tile:02X}",
            "file_range": f"0x{offset:06X}-0x{offset + 15:06X}",
            "old": old.hex(" ").upper(),
            "new": new.hex(" ").upper(),
            "changed_bytes": sum(left != right for left, right in zip(old, new)),
        })

    neutral_base = bank_offset(NEUTRAL_ART_BANK, NEUTRAL_ART_ADDR)
    neutral_receipts = []
    for tile, (old, new) in NEUTRAL_PATCHES.items():
        offset = neutral_base + (tile - 1) * 16
        require(len(old) == len(new) == 16, f"neutral tile ${tile:02X} width changed")
        require(source[offset:offset + 16] == old,
                f"bank-1 neutral tile ${tile:02X} preimage changed")
        rom[offset:offset + 16] = new
        allowed.update(range(offset, offset + 16))
        neutral_receipts.append({
            "tile": f"${tile:02X}",
            "bank": NEUTRAL_ART_BANK,
            "address": (
                f"${NEUTRAL_ART_ADDR + (tile - 1) * 16:04X}-"
                f"${NEUTRAL_ART_ADDR + tile * 16 - 1:04X}"
            ),
            "file_range": f"0x{offset:06X}-0x{offset + 15:06X}",
            "old": old.hex(" ").upper(),
            "new": new.hex(" ").upper(),
            "changed_bytes": sum(left != right for left, right in zip(old, new)),
        })

    palette_receipts = []
    for bank in PALETTE_BANKS:
        offset = bank_offset(bank, PALETTE_ADDR)
        require(source[offset:offset + 8] == OLD_PALETTE,
                f"bank{bank} Stage-1 BG7 preimage changed")
        rom[offset:offset + 8] = NEW_PALETTE
        allowed.update(range(offset, offset + 8))
        palette_receipts.append({
            "bank": bank,
            "address": f"${PALETTE_ADDR:04X}-${PALETTE_ADDR + 7:04X}",
            "file_range": f"0x{offset:06X}-0x{offset + 7:06X}",
            "old": OLD_PALETTE.hex(" ").upper(),
            "new": NEW_PALETTE.hex(" ").upper(),
        })

    update_checksums(rom)
    candidate = bytes(rom)
    require(digest(candidate) == EXPECTED_SHA256,
            f"candidate identity drift: {digest(candidate)}")
    require(candidate[0x014D] == 0xF9, "header checksum changed")
    require(candidate[0x014E:0x0150] == bytes.fromhex("57 02"),
            "global checksum changed")

    changed = [
        index for index, (old, new) in enumerate(zip(source, candidate, strict=True))
        if old != new
    ]
    require(set(changed) <= allowed,
            "r292 escaped art/palette/checksum ownership")
    functional = [offset for offset in changed if offset >= 0x0150]
    require(len(functional) == 56,
            f"functional delta changed: {len(functional)} bytes")
    require(not any(
        source[offset] != candidate[offset]
        for offset in range(0x0150, len(source))
        if offset not in allowed
    ), "an executable or unrelated data byte changed")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-exact-background-r292-build-v1",
        "status": "STATIC_PASS_RENDERED_GATES_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": EXPECTED_SHA256,
        "checksums": {"header": "F9", "global": "5702"},
        "patch": {
            "source_tooth_tiles": source_receipts,
            "bank1_neutral_tiles": neutral_receipts,
            "palette_mirrors": palette_receipts,
            "functional_changed_bytes": len(functional),
            "changed_offsets": [f"0x{value:06X}" for value in changed],
        },
        "render_contract": {
            "Dungeon_BG0_words": ["7FFF", "7E94", "3D4A", "0000"],
            "Stage1_BG7_words": ["7FFF", "7E94", "03FF", "3D4A"],
            "floor_environment_pixels_exact": True,
            "shadow_environment_pixels_exact": True,
            "tooth_fill_remains_gold_03FF": True,
            "tooth_outline_is_dark_lavender_3D4A": True,
            "pure_black_tooth_outline_preserved": False,
        },
        "timing_contract": {
            "executable_bytes_changed": 0,
            "loader_bytes_changed": 0,
            "attribute_bytes_changed": 0,
            "runtime_t_cycle_delta": 0,
        },
        "transferred_r290_contracts": {
            "live_BG_selector_uses_LCDC": True,
            "Stage1_menu_cache_uses_FF_sentinel": True,
            "natural_Stage1_bank1_art_rearm": True,
            "tooth_fill_is_gold": True,
        },
        "required_gates": [
            "offline rendered tooth backgrounds equal semantic Dungeon baselines",
            "natural blank-SRAM Stage-1 bank-1 art matches the r292 candidate",
            "room01 and room12 live captures contain no flat pale tooth cells",
            "menu entry/exit retains zero red-green wall bleed and yellow trails",
            "human review accepts dark-lavender tooth outlines",
            "strict all-stage speed qualification remains unchanged",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(args.base.read_bytes(), args.base_receipt.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(candidate)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
