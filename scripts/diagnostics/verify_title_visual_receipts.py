#!/usr/bin/env python3
"""Create pixel/VRAM/OAM receipts for cold and returned title cycles."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys

from pyboy import PyBoy


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_v302_title_fix import (  # noqa: E402
    PERIOD_TILE,
    TITLE_FOOTER,
    map_title_string_to_tiles,
)


FOOTER_ADDR = 0x9A41
PERIOD_TILE_ADDR = 0x97F0


def red_dominant_pixels(image) -> int:
    return sum(
        red > 96 and red > green * 1.4 and red > blue * 1.4
        for red, green, blue in image.convert("RGB").getdata()
    )


def visible_oam(pyboy: PyBoy) -> list[tuple[int, int, int, int, int]]:
    sprites = []
    for slot in range(40):
        entry = tuple(
            pyboy.memory[0xFE00 + slot * 4 + offset]
            for offset in range(4)
        )
        y, x, tile, attr = entry
        if 0 < y < 160 and 0 < x < 168:
            sprites.append((slot, y, x, tile, attr))
    return sprites


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/penta-title-visual-receipts"),
    )
    # The second attract cycle reaches the miniboss after frame 14,000 on the
    # current production timing. Keep enough horizon to prove both the
    # returned title and the later miniboss instead of mistaking a valid,
    # slower attract route for a missing receipt.
    parser.add_argument("--max-frames", type=int, default=26000)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    footer_tiles = bytes(map_title_string_to_tiles(TITLE_FOOTER))
    captures: dict[str, dict[str, object]] = {}
    transitions: list[dict[str, int]] = []
    demo_seen = False
    last_scene = None
    banner_start = None
    demo_samples = 0
    demo_sprites = 0
    demo_palette_mismatches = 0

    pyboy = PyBoy(
        str(args.rom.resolve()),
        window="null",
        cgb=True,
        sound_emulated=False,
        log_level=5,
    )
    pyboy.set_emulation_speed(0)
    try:
        for frame in range(1, args.max_frames + 1):
            # Rendering every emulated frame made this 14k-frame inventory take
            # longer than the release gate's 180-second budget. State/VRAM/OAM
            # remain exact without rendering; draw every tenth frame and take
            # each visual receipt at the first rendered frame after its target.
            rendered = frame % 10 == 0
            pyboy.tick(1, rendered)
            scene = pyboy.memory[0xD880]
            ffc1 = pyboy.memory[0xFFC1]
            if scene != last_scene:
                transitions.append({
                    "frame": frame,
                    "d880": scene,
                    "ffc1": ffc1,
                })
                banner_start = frame if scene == 0x1C else None
                last_scene = scene
            if scene == 0x0A:
                demo_seen = True

            phase = "returned" if demo_seen else "cold"
            footer_key = f"{phase}_footer"
            # A receipt can only be captured on a rendered frame. Avoid 35
            # cross-boundary PyBoy memory reads on every one of the 26,000
            # emulated frames (and stop reading entirely once each phase is
            # captured); those reads dominated the old 180-second timeout.
            if footer_key not in captures and rendered:
                footer = bytes(
                    pyboy.memory[0, address]
                    for address in range(
                        FOOTER_ADDR, FOOTER_ADDR + len(footer_tiles)
                    )
                )
                period = bytes(
                    pyboy.memory[0, address]
                    for address in range(PERIOD_TILE_ADDR, PERIOD_TILE_ADDR + 16)
                )
                if footer == footer_tiles and period == PERIOD_TILE:
                    path = output / f"{footer_key}_f{frame}.png"
                    pyboy.screen.image.save(path)
                    captures[footer_key] = {
                        "frame": frame,
                        "d880": scene,
                        "ffc1": ffc1,
                        "footer_address": f"0x{FOOTER_ADDR:04X}",
                        "footer_tiles": footer.hex(),
                        "period_tile_address": f"0x{PERIOD_TILE_ADDR:04X}",
                        "period_tile": period.hex(),
                        "red_dominant_pixels": red_dominant_pixels(
                            pyboy.screen.image
                        ),
                        "visible_oam": visible_oam(pyboy),
                        "screenshot": str(path),
                    }

            if scene == 0x1C and banner_start is not None:
                age = frame - banner_start
                banner_key = f"{phase}_banner"
                if age >= 800 and banner_key not in captures and rendered:
                    image = pyboy.screen.image.convert("RGB")
                    path = output / f"{banner_key}_f{frame}.png"
                    image.save(path)
                    attributes = Counter(
                        pyboy.memory[1, address] & 7
                        for address in range(0x9800, 0xA000)
                    )
                    captures[banner_key] = {
                        "frame": frame,
                        "d880": scene,
                        "ffc1": ffc1,
                        "scene_age": age,
                        "red_dominant_pixels": red_dominant_pixels(image),
                        "attribute_palettes": dict(attributes),
                        "visible_oam": visible_oam(pyboy),
                        "screenshot": str(path),
                    }

            if scene == 0x0A and pyboy.memory[0xFFBF] == 1 and frame % 10 == 0:
                demo_actors = [
                    sprite for sprite in visible_oam(pyboy)
                    if 0x20 <= sprite[3] < 0x50
                ]
                if demo_actors:
                    demo_samples += 1
                    demo_sprites += len(demo_actors)
                    demo_palette_mismatches += sum(
                        (sprite[4] & 7) != (
                            2 if sprite[3] < 0x30 else 6
                        )
                        for sprite in demo_actors
                    )
                    if demo_samples in (1, 20, 40):
                        pyboy.screen.image.save(
                            output / f"demo_miniboss_sample{demo_samples}_f{frame}.png"
                        )
            if (
                all(key in captures for key in (
                    "cold_footer", "returned_footer",
                    "cold_banner", "returned_banner",
                ))
                and demo_samples >= 40
                and any(
                    transition["d880"] == 0x1B
                    and transition["ffc1"] == 1
                    for transition in transitions
                )
            ):
                break
    finally:
        pyboy.stop()

    failures: list[str] = []
    for key in ("cold_footer", "returned_footer", "cold_banner", "returned_banner"):
        if key not in captures:
            failures.append(f"missing {key} receipt")
    for key in ("cold_banner", "returned_banner"):
        receipt = captures.get(key)
        if not receipt:
            continue
        if receipt["red_dominant_pixels"] != 0:
            failures.append(
                f"{key} has {receipt['red_dominant_pixels']} red pixels"
            )
        if receipt["attribute_palettes"] != {0: 2048}:
            failures.append(
                f"{key} attributes={receipt['attribute_palettes']}, expected all 0"
            )
        if receipt["visible_oam"]:
            failures.append(f"{key} retained visible OAM")
    for key in ("cold_footer", "returned_footer"):
        receipt = captures.get(key)
        if not receipt:
            continue
        if receipt["red_dominant_pixels"] != 0:
            failures.append(
                f"{key} has {receipt['red_dominant_pixels']} red pixels"
            )
        if receipt["visible_oam"]:
            failures.append(f"{key} retained visible OAM")
    # The deterministic demo can reach the miniboss arena at slightly
    # different sub-frame phases across emulator cores, so its surviving
    # arena dwell is not a fixed 200 frames. Ten rendered samples still prove
    # a stable 100-frame actor interval. Tiles $20-$2F are Sara (OBJ2);
    # $30-$4F are the miniboss family (OBJ6).
    if demo_samples < 10:
        failures.append(f"only {demo_samples} demo miniboss samples")
    if demo_palette_mismatches:
        failures.append(
            f"{demo_palette_mismatches}/{demo_sprites} demo palette mismatches"
        )
    if not any(
        transition["d880"] == 0x1B and transition["ffc1"] == 1
        for transition in transitions
    ):
        failures.append("returned title never advanced to D880=1B")

    receipt = {
        "status": "failed" if failures else "ok",
        "rom": str(args.rom.resolve()),
        "title_footer": TITLE_FOOTER,
        "transitions": transitions,
        "captures": captures,
        "demo_miniboss": {
            "samples": demo_samples,
            "sprites": demo_sprites,
            "expected_palette_slots": {
                "tiles_20_2F": 2,
                "tiles_30_4F": 6,
            },
            "palette_mismatches": demo_palette_mismatches,
        },
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")

    for key, value in captures.items():
        print(f"{key}: frame={value['frame']} screenshot={value['screenshot']}")
    print(
        f"demo_miniboss: samples={demo_samples} sprites={demo_sprites} "
        f"palette_mismatches={demo_palette_mismatches}"
    )
    print(f"Receipt: {receipt_path}")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "PASS: footer bytes/glyph, cold+returned banner pixels/attributes/OAM, "
        "and stable demo-miniboss palette are verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
