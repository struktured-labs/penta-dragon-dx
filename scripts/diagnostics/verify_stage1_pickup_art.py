#!/usr/bin/env python3
"""Prove Stage-1 pickup colorization is isolated in a cold live run.

The release build uses the canonical semantic-attribute mode: stock pickup
art is retained and each labeled pickup tile selects its YAML palette class.
The older ``--reserved-pickup-gold`` research mode remains supported as an
alternate contract, but is not required of a production ROM.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import subprocess

from PIL import Image

from analyze_stage1_pickup_art import TARGETS, color_words, decode_tile
from verify_pickup_class_palettes import (
    BG_PALETTE_OFFSET,
    BG_TABLE_OFFSET,
    EXPECTED_TABLE,
)


ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_stage1_pickup_art.lua")
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
STAGE1_LOW_TILE_GFX_OFFSET = 0x1D000
STAGE1_HIGH_TILE_GFX_OFFSET = 0x1F000
PICKUP_GOLD = 0x03FF
STOCK_ROM = ROOT / "rom/Penta Dragon (J).gb"
SEMANTIC_TABLE_VARIANT_SHA256 = {
    "6e5e7a61ddd1a44c0db6aed123528477c5531716fa16d73b083c67d64abfcbe9",
    "8234bd8400f7284d115fe622ccccd44bc354e4b5322591c24332028c83dcb2b4",
    "69896bb1ba8f60fee7f5fd8c9044b90972f16255c726f2b00beaffec320d6722",
    "13beaa1b0867dc71153538531838e00c101b355c2b3bdb8823184784ea78cc6b",
    "e8da7fde311acecc6b2fa052a501b18636c7c416091db9df329d59f07fdf5b50",
    "5c49fa5d01a91b2b07e7546d4bd6856cb23697678690cf2e6b734d3fa10ec208",
    "46b498d85bb50f44fac92c6ee67d362236e66cecc3f372df22e7defe2b87aa30",
    "9d44e9d1c03c60e95b91f76752a47d5631cf6062188a7ef80667a289af569855",
    "055a2754355439b60e4e310adf89854f4db16e70a27182edad8ed902e3c43821",
    "4fc5028a50250130c87d6a84414b409e050e55407e9fb2ac0e05af7ce288a4ba",
    "727ee4969da086fe3c62185ca2f0bba1b62cc60d8190710f5db9bfc8b50b260b",
    "681b4668446c547644aaa4924ca0d6dd44782dc59133540c59708fa160c178d3",
    "fe14b0e3c392b3d822208684636e1017cb093613d28e6ca477999535df164576",
    "b93ebc46ed4ac23ec7d2c44d80fae1ae1538b38c038bab0ba8173b93fe252350",  # r536: inherited observer/data ABI
    "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b",  # title row guard: unchanged gameplay observer/data ABI
    "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d",  # death/restart successor: unchanged semantic table
    "4f5a67b8a9afb178ac0760daa2357de74fd7eb7f3de4de010385c50ea4cb08f5",  # #6: unchanged semantic table
    "b691c96c7477473e05f2304705f132c696997dbd2b3a639a35be4cef3713fc96",
    "ffb6a829cfdbf41fc5b2ebd5f6691a5a5bf5fd6ce5bad4dc7ab2e6c874d15f63",
    "15ab73c3c04a3caf1c4186335a073ca49b5dc21199335ca9d85eca56ad7da21b",
    "d82f563d856995fc1844d48cdd317b12f2ac9218f023eec376ee73bc24308074",
    "b331c5e0339c26672651d0592dc658ebd9c42f4d759c1e5227e18115d0661892",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def expected_stage1_table(rom: bytes) -> bytes:
    import playtest_successor_lineage as successor
    if successor.is_candidate(rom):
        return expected_stage1_table(successor.authenticated_parent(
            rom, (BG_TABLE_OFFSET, BG_TABLE_OFFSET + 256)))
    expected = bytearray(EXPECTED_TABLE)
    release_lock = hashlib.sha256(rom).hexdigest() == (
        "ffc29f4e29f2c2f9995f132c08676624ad92a206b822b3afdf835be3ad072feb"
    )
    if release_lock:
        # Issue #22: the four five-point-star tiles move from 0 to BG5.
        for tile in (0x82, 0x83, 0x92, 0x93):
            if expected[tile] != 0:
                raise AssertionError(f"unexpected star palette at tile {tile:02X}")
            expected[tile] = 5
    if release_lock or hashlib.sha256(rom).hexdigest() in SEMANTIC_TABLE_VARIANT_SHA256:
        # Reviewed Stage-1 tooth-art rows intentionally encode BG7+VBK1 as 0x0F.
        for tile in (*range(0x64, 0x6A), *range(0x74, 0x7A)):
            if expected[tile] != 7:
                raise AssertionError(f"unexpected compiled palette at tile {tile:02X}")
            expected[tile] |= 8
    return bytes(expected)


def tile_indices(tile: bytes) -> set[int]:
    values: set[int] = set()
    for row in range(0, 16, 2):
        low, high = tile[row:row + 2]
        for bit in range(8):
            mask = 1 << bit
            values.add(
                (1 if low & mask else 0) | (2 if high & mask else 0)
            )
    return values


def rom_tile(rom: bytes, tile: int) -> bytes:
    source = (
        STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
        if tile < 0x80
        else STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
    )
    return rom[source:source + 16]


def live_tile(vram0: bytes, tile: int) -> bytes:
    offset = tile * 16 if tile >= 0x80 else 0x1000 + tile * 16
    return vram0[offset:offset + 16]


def state_fields(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    rom_path = args.rom.resolve()
    mgba = args.mgba.resolve()
    output = args.output.resolve()
    if not rom_path.is_file():
        parser.error(f"ROM not found: {rom_path}")
    if not mgba.is_file():
        parser.error(f"guarded mGBA frontend not found: {mgba}")
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / "stage1-pickup-art"
    suffixes = (
        ".vram0.bin", ".vram1.bin", ".bg-cram.bin", ".state.txt",
        ".png", ".done",
    )
    for suffix in suffixes:
        Path(str(prefix) + suffix).unlink(missing_ok=True)

    environment = os.environ.copy()
    environment.update({
        "PICKUP_ART_OUT": str(prefix),
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
    })
    log_path = output / "mgba.log"
    with log_path.open("w") as stream:
        completed = subprocess.run(
            [
                str(mgba), "--fastforward", "--script", str(PROBE),
                str(rom_path),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
            check=False,
        )

    required = [Path(str(prefix) + suffix) for suffix in suffixes]
    missing = [path.name for path in required if not path.is_file()]
    if completed.returncode != 0 or missing:
        print(
            f"FAIL: cold pickup probe status={completed.returncode} "
            f"missing={missing}; see {log_path}"
        )
        return 1

    rom = rom_path.read_bytes()
    stock = STOCK_ROM.read_bytes()
    vram0 = Path(str(prefix) + ".vram0.bin").read_bytes()
    vram1 = Path(str(prefix) + ".vram1.bin").read_bytes()
    cram = Path(str(prefix) + ".bg-cram.bin").read_bytes()
    state = state_fields(Path(str(prefix) + ".state.txt"))
    screenshot = Path(str(prefix) + ".png")
    if len(rom) not in (0x40000, 0x80000, 0x100000) or len(vram0) != 0x2000 \
            or len(vram1) != 0x2000 or len(cram) != 64:
        print("FAIL: incomplete ROM/VRAM/CRAM payload")
        return 1

    pickup_source_failures = []
    terrain_source_failures = []
    live_source_mismatches = []
    for tile in range(0x100):
        source = rom_tile(rom, tile)
        indices = tile_indices(source)
        if tile in TARGETS:
            if 1 not in indices or 2 in indices:
                pickup_source_failures.append(f"{tile:02X}")
        elif 1 in indices:
            terrain_source_failures.append(f"{tile:02X}")
        if live_tile(vram0, tile) != source:
            live_source_mismatches.append(f"{tile:02X}")

    lcdc = int(state["LCDC"], 16)
    signed_indices = not bool(lcdc & 0x10)
    map_base = 0x1C00 if lcdc & 0x08 else 0x1800
    tilemap = vram0[map_base:map_base + 0x400]
    attrs = vram1[map_base:map_base + 0x400]
    scx = int(state["SCX"], 16)
    scy = int(state["SCY"], 16)
    # A sub-tile scroll exposes one extra map cell at the right/bottom edge.
    # Restrict the live contract to cells that actually overlap the 160x144
    # viewport; the publisher is allowed to leave hidden map columns staged.
    visible_offsets = {
        (((scy + screen_y) // 8) & 0x1F) * 32
        + (((scx + screen_x) // 8) & 0x1F)
        for screen_y in range(0, 144, 8)
        for screen_x in range(0, 160, 8)
    }
    if scx & 7:
        visible_offsets.update(
            (((scy + screen_y) // 8) & 0x1F) * 32
            + (((scx + 159) // 8) & 0x1F)
            for screen_y in range(0, 144, 8)
        )
    if scy & 7:
        visible_offsets.update(
            (((scy + 143) // 8) & 0x1F) * 32
            + (((scx + screen_x) // 8) & 0x1F)
            for screen_x in range(0, 160, 8)
        )
        if scx & 7:
            visible_offsets.add(
                (((scy + 143) // 8) & 0x1F) * 32
                + (((scx + 159) // 8) & 0x1F)
            )
    visible_targets: Counter[int] = Counter()
    visible_terrain: Counter[int] = Counter()
    visible_target_cells = 0
    visible_target_palette_mismatches = []
    visible_terrain_palette_mismatches = []
    unsafe_attributes = []
    table = rom[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    expected_table = expected_stage1_table(rom)
    vram = vram0 + vram1
    for offset, (tile, attr) in enumerate(zip(tilemap, attrs)):
        if offset not in visible_offsets:
            continue
        pixels = decode_tile(
            vram, tile, (attr >> 3) & 1,
            signed_indices=signed_indices,
        )
        is_target = tile in TARGETS
        (visible_targets if is_target else visible_terrain).update(pixels)
        if attr & 0xF8:
            unsafe_attributes.append(
                f"{offset:03X}:{tile:02X}:{attr:02X}"
            )
        if (attr & 0x07) != table[tile]:
            mismatch = (
                f"{offset:03X}:{tile:02X}:{attr & 7}>{table[tile]}"
            )
            (
                visible_target_palette_mismatches
                if is_target else visible_terrain_palette_mismatches
            ).append(mismatch)
        if is_target:
            visible_target_cells += 1

    bg0 = color_words(cram, 0)
    reserved_art_mode = (
        not pickup_source_failures
        and not terrain_source_failures
        and bg0[1] == PICKUP_GOLD
    )
    pickup_art_matches_stock = all(
        rom_tile(rom, tile) == rom_tile(stock, tile)
        for tile in TARGETS
    )
    live_pickup_rows_match_rom = all(
        cram[slot * 8:(slot + 1) * 8]
        == rom[
            BG_PALETTE_OFFSET + slot * 8:
            BG_PALETTE_OFFSET + (slot + 1) * 8
        ]
        for slot in range(1, 6)
    )
    with Image.open(screenshot) as source:
        image = source.convert("RGB")
    pixels = list(image.getdata())
    chromatic_pixels = sum(max(pixel) - min(pixel) >= 24 for pixel in pixels)
    checks = {
        "cold route reached stable Stage 1 gameplay": (
            state.get("D880") == "02" and state.get("FFC1") == "01"
        ),
        "canonical pickup class contains 73 unique tile IDs": (
            len(TARGETS) == 73
        ),
        "all 256 live tiles exactly match the candidate ROM source": (
            not live_source_mismatches
        ),
        "cold screenshot is 160x144 and chromatic": (
            image.size == (160, 144) and chromatic_pixels > 100
        ),
    }
    if reserved_art_mode:
        colorization_mode = "reserved-pickup-gold"
        checks.update({
            "all pickup source tiles reserve index 1 and exclude index 2": (
                not pickup_source_failures
            ),
            "all 183 ordinary source tiles exclude reserved index 1": (
                len(TARGETS) == 73 and not terrain_source_failures
            ),
            "live BG0 index 1 is bright gold": bg0[1] == PICKUP_GOLD,
            "live map renders pickup pixels through reserved index 1": (
                visible_targets[1] > 0
            ),
            "live map renders zero ordinary-terrain pixels through index 1": (
                visible_terrain[1] == 0
            ),
        })
    else:
        colorization_mode = "semantic-palette-attributes"
        checks.update({
            "pickup art remains byte-exact stock in semantic mode": (
                pickup_art_matches_stock
            ),
            "complete Stage 1 attribute table equals its YAML compilation": (
                table == expected_table
            ),
            "live BG1-BG5 pickup rows equal the candidate YAML rows": (
                live_pickup_rows_match_rom
            ),
            "cold map contains visible semantic pickup cells": (
                visible_target_cells > 0
            ),
            "visible pickup cells select their compiled palette classes": (
                not visible_target_palette_mismatches
            ),
            "visible terrain cells select their compiled palette classes": (
                not visible_terrain_palette_mismatches
            ),
            "visible attributes contain no bank/flip/priority leakage": (
                not unsafe_attributes
            ),
        })
    failures = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "penta-dragon-dx-stage1-pickup-art-v2",
        "status": "pass" if not failures else "fail",
        "colorization_mode": colorization_mode,
        "rom": str(rom_path),
        "rom_sha256": digest(rom_path),
        "checks": checks,
        "state": state,
        "bg0": [f"{word:04X}" for word in bg0],
        "pickup_tile_count": len(TARGETS),
        "ordinary_tile_count": 0x100 - len(TARGETS),
        "visible_pickup_pixel_indices": dict(sorted(visible_targets.items())),
        "visible_terrain_pixel_indices": dict(sorted(visible_terrain.items())),
        "visible_target_cells": visible_target_cells,
        "visible_target_palette_mismatches": (
            visible_target_palette_mismatches
        ),
        "visible_terrain_palette_mismatches": (
            visible_terrain_palette_mismatches
        ),
        "unsafe_attributes": unsafe_attributes,
        "pickup_source_failures": pickup_source_failures,
        "terrain_source_failures": terrain_source_failures,
        "live_source_mismatches": live_source_mismatches,
        "screenshot": {
            "path": str(screenshot),
            "sha256": digest(screenshot),
            "size": list(image.size),
            "chromatic_pixels": chromatic_pixels,
        },
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"Receipt: {receipt_path}")
    if failures:
        return 1
    print(
        "PASS: Stage-1 pickup colorization is live and isolated in "
        f"{colorization_mode} mode."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
