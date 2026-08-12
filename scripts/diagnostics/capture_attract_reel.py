#!/usr/bin/env python3
"""Capture one direct-seeded visual receipt for every spotlight identity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from PIL import Image, ImageDraw
from pyboy import PyBoy


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from build_v302_title_fix import (  # noqa: E402
    SPOTLIGHT_ROSTER_SIZE,
    SPOTLIGHT_ROSTER_TABLE_ADDR,
    compile_spotlight_palette_map,
)


def body(pyboy: PyBoy) -> list[tuple[int, int, int, int]]:
    entries = [
        tuple(
            int(pyboy.memory[0xFE00 + slot * 4 + offset])
            for offset in range(4)
        )
        for slot in range(4)
    ]
    if (
        len({entry[2] for entry in entries}) == 4
        and all(0x08 <= entry[2] <= 0x0F for entry in entries)
        and all(0 < entry[0] < 160 and 0 < entry[1] < 168 for entry in entries)
    ):
        return entries
    return []


def create_contact_sheet(actors: list[dict[str, object]], output: Path) -> None:
    columns = 6
    label_height = 14
    cell_width, cell_height = 160, 144 + label_height
    rows = (len(actors) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, actor in enumerate(actors):
        screenshot = Image.open(str(actor["screenshot"])).convert("RGB")
        x = index % columns * cell_width
        y = index // columns * cell_height
        sheet.paste(screenshot, (x, y + label_height))
        draw.text(
            (x + 2, y + 2),
            (
                f"id {int(actor['identity']):02d} "
                f"res {int(actor['resource_id']):02X} "
                f"OBJ{int(actor['expected_palette_slot'])}"
            ),
            fill="black",
        )
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/penta-title-spotlight"),
    )
    parser.add_argument("--frames-per-identity", type=int, default=4_500)
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    _packed, palette_slots, yaml_resources = compile_spotlight_palette_map()
    rom_bytes = rom.read_bytes()
    rom_resources = list(
        rom_bytes[
            SPOTLIGHT_ROSTER_TABLE_ADDR:
            SPOTLIGHT_ROSTER_TABLE_ADDR + SPOTLIGHT_ROSTER_SIZE
        ]
    )
    if rom_resources != yaml_resources:
        raise SystemExit("ROM spotlight roster does not match palette YAML")

    captured: list[dict[str, object]] = []
    failures: list[str] = []
    for target in range(SPOTLIGHT_ROSTER_SIZE):
        pyboy = PyBoy(
            str(rom), window="null", cgb=True,
            sound_emulated=False, log_level=5,
        )
        pyboy.set_emulation_speed(0)
        seeded = False
        first_sample = None
        chosen = None
        try:
            for frame in range(1, args.frames_per_identity + 1):
                # Cold-boot/title frames are used only to reach the seeded
                # identity. Rendering all ~4,500 frames for each of 38 actors
                # made this deterministic audit exceed four minutes. Draw
                # every frame once the requested spotlight scene is active;
                # state/OAM execution remains frame-exact throughout.
                render = (
                    seeded
                    and int(pyboy.memory[0xD880]) == 0x1B
                    and int(pyboy.memory[0xFFF2]) == target
                )
                pyboy.tick(1, render)
                scene = int(pyboy.memory[0xD880])
                if scene == 0x1C and not seeded:
                    pyboy.memory[0xFFF2] = (
                        target - 1
                    ) % SPOTLIGHT_ROSTER_SIZE
                    seeded = True
                if (
                    not render
                    or scene != 0x1B
                    or int(pyboy.memory[0xFFF2]) != target
                ):
                    continue
                sprites = body(pyboy)
                if not sprites:
                    continue
                image = pyboy.screen.image.copy()
                # The actor reaches screen center before the game publishes
                # its English name. Require the later white name glyphs so
                # gallery receipts identify themselves instead of showing an
                # unlabeled sprite on black.
                name_region = image.convert("RGB").crop((50, 80, 150, 104))
                name_pixels = sum(
                    min(pixel) >= 160 and max(pixel) - min(pixel) <= 80
                    for pixel in name_region.getdata()
                )
                sample = (frame, sprites, image, name_pixels)
                if first_sample is None:
                    first_sample = sample
                if name_pixels >= 24:
                    chosen = sample
                    break
        finally:
            pyboy.stop(save=False)

        if chosen is None:
            chosen = first_sample
        if chosen is None:
            failures.append(f"identity {target:02d} never reached hardware OAM")
            continue
        frame, sprites, image, name_pixels = chosen
        expected = palette_slots[target]
        actual = [entry[3] & 7 for entry in sprites]
        path = output / (
            f"id{target:02d}_res{rom_resources[target]:02X}"
            f"_obj{expected}_f{frame}.png"
        )
        image.save(path)
        captured.append(
            {
                "identity": target,
                "resource_id": rom_resources[target],
                "frame": frame,
                "expected_palette_slot": expected,
                "hardware_palette_slots": actual,
                "hardware_oam": sprites,
                "name_glyph_pixels": name_pixels,
                "screenshot": str(path),
            }
        )
        if actual != [expected] * 4:
            failures.append(
                f"identity {target:02d} palette {actual}, expected OBJ{expected}"
            )
        print(
            f"id={target:02d} resource={rom_resources[target]:02X} "
            f"frame={frame} palette={actual} name_pixels={name_pixels} "
            f"screenshot={path}"
        )

    contact_sheet = output / "spotlight-roster-contact-sheet.png"
    if captured:
        create_contact_sheet(captured, contact_sheet)
    receipt = {
        "status": "failed" if failures else "ok",
        "rom": str(rom),
        "captured": len(captured),
        "expected": SPOTLIGHT_ROSTER_SIZE,
        "actors": captured,
        "contact_sheet": str(contact_sheet),
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Receipt: {receipt_path}")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "PASS: all 38 spotlight actors captured with YAML-derived hardware "
        f"palettes. Contact sheet: {contact_sheet}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
