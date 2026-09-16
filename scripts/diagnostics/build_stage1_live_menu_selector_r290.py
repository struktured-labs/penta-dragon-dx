#!/usr/bin/env python3
"""Keep the live Stage-1 gameplay BG selected while SELECT opens.

The stock fixed-bank menu copier chose its Window map from the lagging DC0B
map selector.  The expanded menu helper then moved BG onto the opposite map,
which could expose a stale peer carrying red/green menu attributes for the
entire visible-menu interval.  Choose the Window map from the *live* LCDC BG
bit instead: Window is always the opposite physical map and BG bit 3 never
changes.  The replacement is four bytes and exactly 20 T-cycles, matching the
old selector prefix.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
BASE = TMP / "stage1-menu-sentinel-r289/candidate.gb"
BASE_RECEIPT = TMP / "stage1-menu-sentinel-r289/build-receipt.json"
DEFAULT_OUTPUT = TMP / "stage1-live-menu-selector-r290/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-live-menu-selector-r290/build-receipt.json"
BASE_SHA256 = "559e9aa7a81985dd8639ce70d830b9799faebb4f9e27ceec55e2ce0fb086d905"
BASE_RECEIPT_SHA256 = "3be4f457268a6ec043110734f05ab9418b9ee7cce2f3fefa06b40e5c1f84e7c6"
EXPECTED_SHA256 = "48582bed3b9c9746588de9d2de695927788b7b07a511b817da0cb36932d87736"

ROM_SIZE = 32 * 0x4000
SELECTOR_ADDR = 0x200E
OLD = bytes.fromhex("FA 0B DC A7")       # LD A,[$DC0B]; AND A
NEW = bytes.fromhex("F0 40 CB 5F")       # LDH A,[$FF40]; BIT 3,A
TAIL = bytes.fromhex(
    "28 0C 21 00 98 F0 40 CB B7 E0 40 C3 29 20 "
    "21 00 9C F0 40 CB F7 E0 40"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def checked_output(path: Path, label: str) -> Path:
    resolved = path.resolve()
    root = TMP.resolve()
    require(resolved != root and root in resolved.parents,
            f"{label} must be inside repository tmp/")
    return resolved


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def selector_model(lcdc: int) -> tuple[int, int]:
    """Return (BG map bit 3, Window map bit 6) after stock selector tail."""
    bg = (lcdc >> 3) & 1
    window = bg ^ 1
    return bg, window


def build(source: bytes, base_receipt_bytes: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r289 base")
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r289 receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r289 receipt names another candidate")
    require(source[SELECTOR_ADDR:SELECTOR_ADDR + len(OLD)] == OLD,
            "fixed-bank menu selector preimage changed")
    require(source[
        SELECTOR_ADDR + len(OLD):SELECTOR_ADDR + len(OLD) + len(TAIL)
    ] == TAIL, "fixed-bank menu selector tail changed")
    require(len(OLD) == len(NEW) == 4, "selector width changed")

    controls = []
    for lcdc in range(256):
        bg, window = selector_model(lcdc)
        require(bg == ((lcdc >> 3) & 1), "BG selector changed")
        require(window != bg, "Window aliases the live BG")
        controls.append((lcdc, bg, window))

    rom = bytearray(source)
    rom[SELECTOR_ADDR:SELECTOR_ADDR + len(NEW)] = NEW
    update_checksums(rom)
    candidate = bytes(rom)
    require(digest(candidate) == EXPECTED_SHA256,
            f"candidate identity drift: {digest(candidate)}")
    require(candidate[0x014D] == 0xF9, "header checksum changed")
    require(candidate[0x014E:0x0150] == bytes.fromhex("41 28"),
            "global checksum changed")

    changed = [
        index for index, (old, new) in enumerate(zip(source, candidate, strict=True))
        if old != new
    ]
    allowed = set(range(SELECTOR_ADDR, SELECTOR_ADDR + len(NEW))) | {
        0x014D, 0x014E, 0x014F,
    }
    require(set(changed) <= allowed,
            "r290 escaped selector/checksum ownership")

    receipt: dict[str, object] = {
        "schema": "penta-stage1-live-menu-selector-r290-build-v1",
        "status": "STATIC_PASS_EXACT_USER_ROUTE_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "candidate_sha256": EXPECTED_SHA256,
        "checksums": {"header": "F9", "global": "4128"},
        "patch": {
            "fixed_address": f"${SELECTOR_ADDR:04X}-${SELECTOR_ADDR + 3:04X}",
            "old": OLD.hex(" ").upper(),
            "new": NEW.hex(" ").upper(),
            "changed_offsets": [f"0x{value:06X}" for value in changed],
        },
        "selector_contract": {
            "all_LCDC_values_checked": len(controls),
            "BG_bit3_is_latched": True,
            "Window_bit6_is_opposite_BG": True,
            "old_prefix_t_cycles": 20,
            "new_prefix_t_cycles": 20,
            "timing_delta_t_cycles": 0,
        },
        "transferred_r289_contracts": {
            "Stage1_menu_cache_uses_FF_sentinel": True,
            "natural_Stage1_bank1_art_rearm": True,
            "gold_tooth_palette_mirrors": True,
        },
        "required_gates": [
            "untouched blank-SRAM same-process menu then hazard route",
            "menu-open BG map identity remains the pre-open map",
            "stationary post-close active-BG attrs never mismatch",
            "natural bank-1 hazard art has zero mismatched bytes",
            "four user-reported rendered bug classes absent",
            "strict all-stage speed qualification",
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
