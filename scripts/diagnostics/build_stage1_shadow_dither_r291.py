#!/usr/bin/env python3
"""Replace flat clear BG7 shadow cells with a 50% semantic dither.

Stage-1 tooth cells need white/floor-blue/gold/black on ordinary floor and
floor-blue/dark-blue/gold/black over the cylinder shadow.  One four-color BG
palette cannot carry both white and the native dark-blue while reserving gold.
The current bank-1 fallback collapses native shadow indices 1 and 2 to the
same pale index 1, producing conspicuous flat 8x8 "clear" cells.

For tooth variants whose declared semantic baseline is shadow tile $03/$04,
encode every native dark-blue (index 2) environment pixel as a 50% checker of
BG7 floor-blue (index 1) and black (index 3).  Their BGR555 average closely
matches Dungeon BG0's native dark-blue.  Apply the same transform to immutable
bank-1 neutral tiles $03/$04.  Gold remains confined to the reviewed tooth
silhouettes; floor-baseline variants and every runtime routine are untouched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from stage1_hazard_art import (  # noqa: E402
    decode_tile,
    encode_tile,
    load_stage1_hazard_config,
    remap_hazard_tile,
)


TMP = ROOT / "tmp"
BASE = TMP / "stage1-live-menu-selector-r290/candidate.gb"
BASE_RECEIPT = TMP / "stage1-live-menu-selector-r290/build-receipt.json"
ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"
DEFAULT_OUTPUT = TMP / "stage1-shadow-dither-r291/candidate.gb"
DEFAULT_RECEIPT = TMP / "stage1-shadow-dither-r291/build-receipt.json"
BASE_SHA256 = "48582bed3b9c9746588de9d2de695927788b7b07a511b817da0cb36932d87736"
BASE_RECEIPT_SHA256 = "232ea8935182e2647632e921e7086a76c16d7578be3c32d6058cb58727f91447"
ORIGINAL_SHA256 = "2f32570cff62b8664bfa06b939988c3fd6a7efabf870a990a5fa65bab37eac30"
EXPECTED_SHA256 = "e6bbfb64d4e9274b063efd9f1e7e3af120a931dfd44980d36dcecfa463bbc963"

BANK_SIZE = 0x4000
ROM_SIZE = 32 * BANK_SIZE
NEUTRAL_BANK = 19
NEUTRAL_ADDR = 0x6C10
SHADOW_BASELINES = frozenset({0x03, 0x04})


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


def inside_span(rows: dict[int, tuple[int, int]], x: int, y: int) -> bool:
    span = rows.get(y)
    return bool(span and span[0] <= x < span[1])


def shadow_environment_pixel(source: int, x: int, y: int) -> int:
    if source == 2:
        return 1 if ((x + y) & 1) == 0 else 3
    return (0, 1, 1, 3)[source]


def remap_tooth_dither(config, tile: int, raw: bytes, baseline: bytes) -> bytes:
    source_pixels = decode_tile(raw)
    baseline_pixels = decode_tile(baseline)
    rows = config.tooth_row_spans[tile]
    shadow = config.semantic_base_tiles[tile] in SHADOW_BASELINES
    result: list[int] = []
    for index, (source, background) in enumerate(
        zip(source_pixels, baseline_pixels, strict=True)
    ):
        x, y = index & 7, index >> 3
        if inside_span(rows, x, y):
            result.append(3 if source == 3 else 2)
        elif shadow:
            # Outside the explicit tooth, source and semantic background are
            # required equal.  Refer to background so this cannot accidentally
            # preserve a future moving-art pixel as environment.
            result.append(shadow_environment_pixel(background, x, y))
        else:
            result.append(config.environment_remap[background])
    return encode_tile(result)


def remap_neutral_dither(tile: int, raw: bytes) -> bytes:
    result = []
    for index, source in enumerate(decode_tile(raw)):
        x, y = index & 7, index >> 3
        if tile in SHADOW_BASELINES:
            result.append(shadow_environment_pixel(source, x, y))
        else:
            result.append((0, 1, 1, 3)[source])
    return encode_tile(result)


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    total = (sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF
    rom[0x014E:0x0150] = total.to_bytes(2, "big")


def derive_candidate(source: bytes, original: bytes) -> tuple[bytes, dict[str, object]]:
    require(len(source) == ROM_SIZE, "base is not exactly 512 KiB")
    require(digest(source) == BASE_SHA256, "wrong exact r290 base")
    require(digest(original) == ORIGINAL_SHA256, "wrong original ROM")
    config = load_stage1_hazard_config()
    rom = bytearray(source)
    art_changes: dict[str, object] = {}
    dither_pixels = 0

    for tile in sorted(config.tooth_tiles):
        start = config.source_offset + tile * 16
        raw = original[start:start + 16]
        baseline_tile = config.semantic_base_tiles[tile]
        baseline = original[
            config.source_offset + baseline_tile * 16:
            config.source_offset + (baseline_tile + 1) * 16
        ]
        old_expected = remap_hazard_tile(config, tile, raw, baseline)
        require(source[start:start + 16] == old_expected,
                f"r290 tooth ${tile:02X} is not the canonical preimage")
        new = remap_tooth_dither(config, tile, raw, baseline)
        if baseline_tile in SHADOW_BASELINES:
            old_pixels = decode_tile(old_expected)
            new_pixels = decode_tile(new)
            tile_dither = sum(a != b for a, b in zip(old_pixels, new_pixels))
            require(tile_dither > 0, f"shadow tooth ${tile:02X} did not dither")
            dither_pixels += tile_dither
        else:
            require(new == old_expected,
                    f"floor tooth ${tile:02X} changed unexpectedly")
        if new != old_expected:
            art_changes[f"{tile:02X}"] = {
                "offset": f"0x{start:06X}",
                "changed_bytes": sum(a != b for a, b in zip(old_expected, new)),
                "old": old_expected.hex(),
                "new": new.hex(),
            }
            rom[start:start + 16] = new

    neutral_offset = bank_offset(NEUTRAL_BANK, NEUTRAL_ADDR)
    neutral_changes: dict[str, object] = {}
    for index, tile in enumerate((0x01, 0x02, 0x03, 0x04)):
        source_start = config.source_offset + tile * 16
        raw = original[source_start:source_start + 16]
        old = remap_neutral_dither(tile if tile <= 0x02 else 0x01, raw)
        start = neutral_offset + index * 16
        require(source[start:start + 16] == old,
                f"r290 neutral tile ${tile:02X} preimage changed")
        new = remap_neutral_dither(tile, raw)
        if tile <= 0x02:
            require(new == old, f"floor neutral ${tile:02X} changed")
        else:
            require(new != old, f"shadow neutral ${tile:02X} did not dither")
        if new != old:
            neutral_changes[f"{tile:02X}"] = {
                "offset": f"0x{start:06X}",
                "changed_bytes": sum(a != b for a, b in zip(old, new)),
                "old": old.hex(),
                "new": new.hex(),
            }
            rom[start:start + 16] = new

    update_checksums(rom)
    candidate = bytes(rom)
    details = {
        "tooth_tiles": art_changes,
        "neutral_tiles": neutral_changes,
        "dither_pixels": dither_pixels,
        "changed_bytes": sum(a != b for a, b in zip(source, candidate)),
        "header_checksum": f"{candidate[0x014D]:02X}",
        "global_checksum": candidate[0x014E:0x0150].hex().upper(),
        "candidate_sha256": digest(candidate),
    }
    return candidate, details


def build(source: bytes, base_receipt_bytes: bytes, original: bytes) -> tuple[bytes, dict[str, object]]:
    require(digest(base_receipt_bytes) == BASE_RECEIPT_SHA256,
            "r290 receipt identity changed")
    base_receipt = json.loads(base_receipt_bytes)
    require(base_receipt.get("candidate_sha256") == BASE_SHA256,
            "r290 receipt names another candidate")
    candidate, details = derive_candidate(source, original)
    require(EXPECTED_SHA256 and digest(candidate) == EXPECTED_SHA256,
            f"candidate identity drift: {digest(candidate)}")
    receipt: dict[str, object] = {
        "schema": "penta-stage1-shadow-dither-r291-build-v1",
        "status": "STATIC_PASS_RENDERED_CONTINUITY_REQUIRED",
        "promotable": False,
        "base_sha256": BASE_SHA256,
        "base_receipt_sha256": BASE_RECEIPT_SHA256,
        "original_sha256": ORIGINAL_SHA256,
        "candidate_sha256": EXPECTED_SHA256,
        "patch": details,
        "contract": {
            "floor_tooth_variants_byte_exact": True,
            "shadow_environment_index2": "50% BG7 index1/index3 checker",
            "gold_index2_confined_to_existing_tooth_silhouettes": True,
            "runtime_code_changed": False,
            "palette_changed": False,
        },
        "required_gates": [
            "independent rendered clear-cell/yellow-trail continuity",
            "ROM-owned natural hazard/menu replay without injection",
            "untouched blank-SRAM menu/entry route",
            "strict all-stage speed qualification",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--base-receipt", type=Path, default=BASE_RECEIPT)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    args = parser.parse_args()
    output = checked_output(args.output, "candidate")
    receipt_path = checked_output(args.receipt, "receipt")
    candidate, receipt = build(
        args.base.read_bytes(), args.base_receipt.read_bytes(),
        args.original.read_bytes(),
    )
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
