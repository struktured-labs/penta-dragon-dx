#!/usr/bin/env python3
"""Capture a current-build visual receipt for all 16 miniboss indices.

The stock game reaches the indices through eight long, chained spawn tables.
For a bounded visual inventory this verifier copies the requested ROM to a
temporary file and changes only the confirmed Stage 1 miniboss selector byte
at file offset 0x3402F. The source ROM is never modified. Gameplay then boots
normally and the game itself performs the DC04 -> FFBF detection, entity
initialization, animation, OAM composition, and palette selection.

This is a visual-inventory route, not proof that every encounter is naturally
reachable at that location. The JSON receipt records the one-byte selector
patch and explicitly distinguishes defined YAML palettes (FFBF 1..8) from the
currently undefined entries (FFBF 9..16).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw
from pyboy import PyBoy
import yaml


ROOT = Path(__file__).resolve().parents[2]
PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
SPAWN_SELECTOR_OFFSET = 0x3402F
SPAWN_SELECTOR_ORIGINAL = 0x30
ENTITY_SLOTS = (0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5)
BOSS_YAML_KEYS = (
    "Gargoyle",
    "Spider",
    "Boss3_Crimson",
    "Boss4_Ice",
    "Boss5_Void",
    "Boss6_Poison",
    "Boss7_Knight",
    "Angela",
)
BOSS_NAMES = (
    "Gargoyle",
    "Spider",
    "Crimson",
    "Ice",
    "Void",
    "Poison",
    "Knight",
    "Angela",
    "Boss 9 (unnamed)",
    "Boss 10 (unnamed)",
    "Boss 11 (unnamed)",
    "Boss 12 (unnamed)",
    "Boss 13 (unnamed)",
    "Boss 14 (unnamed)",
    "Boss 15 (unnamed)",
    "Boss 16 (unfinished / unnamed)",
)
TITLE_INPUT = (
    (180, 185, "down"),
    (201, 206, "a"),
    (261, 266, "a"),
    (321, 326, "a"),
)


def bgr555_to_rgb(value: str) -> str:
    packed = int(value, 16)
    channels = (
        packed & 0x1F,
        (packed >> 5) & 0x1F,
        (packed >> 10) & 0x1F,
    )
    return "#" + "".join(f"{round(channel * 255 / 31):02X}" for channel in channels)


def visible_boss_oam(pyboy: PyBoy) -> list[dict[str, int]]:
    sprites = []
    for slot in range(4, 40):
        address = 0xFE00 + slot * 4
        y, x, tile, attr = (
            int(pyboy.memory[address + offset]) for offset in range(4)
        )
        if 0 < y < 160 and 0 < x < 168 and tile >= 0x30:
            sprites.append(
                {
                    "slot": slot,
                    "y": y,
                    "x": x,
                    "tile": tile,
                    "palette": attr & 7,
                }
            )
    return sprites


def capture_one(
    source_rom: bytes,
    boss_index: int,
    output: Path,
    palette_document: dict[str, object],
) -> dict[str, object]:
    dc04 = 0x30 + (boss_index - 1) * 5
    patched_rom = bytearray(source_rom)
    patched_rom[SPAWN_SELECTOR_OFFSET] = dc04
    with tempfile.NamedTemporaryFile(suffix=".gb") as temporary:
        temporary.write(patched_rom)
        temporary.flush()
        pyboy = PyBoy(
            temporary.name, window="null", cgb=True,
            sound_emulated=False, log_level=5,
        )
        pyboy.set_emulation_speed(0)
        armed = False
        spawn_frame = None
        best = None
        try:
            for frame in range(1, 1_650):
                for first, last, button in TITLE_INPUT:
                    if frame == first:
                        pyboy.button_press(button)
                    elif frame == last + 1:
                        pyboy.button_release(button)

                if frame >= 560 and not armed:
                    pyboy.memory[0xDCB8] = 0
                    pyboy.memory[0xDCBA] = 1
                    pyboy.memory[0xFFD6] = 0x1E
                    for address in ENTITY_SLOTS:
                        pyboy.memory[address] = 0
                    armed = True

                if armed and int(pyboy.memory[0xFFBF]) == 0:
                    pyboy.memory[0xDCDD] = 0x17
                    pyboy.memory[0xDCDC] = 0xFF
                    pyboy.memory[0xDCBA] = 1
                    pyboy.memory[0xFFD6] = 0x1E
                    for address in ENTITY_SLOTS:
                        pyboy.memory[address] = 0

                pyboy.tick(1, True)
                actual_index = int(pyboy.memory[0xFFBF])
                if actual_index == boss_index and spawn_frame is None:
                    spawn_frame = frame
                if spawn_frame is None or frame - spawn_frame < 150:
                    continue

                sprites = visible_boss_oam(pyboy)
                score = (len(sprites), -abs((frame - spawn_frame) - 420))
                if best is None or score > best[0]:
                    best = (
                        score,
                        frame,
                        int(pyboy.memory[0xD880]),
                        sprites,
                        pyboy.screen.image.copy(),
                    )
                if frame - spawn_frame >= 660:
                    break
        finally:
            pyboy.stop(save=False)

    if spawn_frame is None:
        raise RuntimeError(f"FFBF={boss_index} never spawned")
    if best is None:
        raise RuntimeError(f"FFBF={boss_index} never produced a capture candidate")
    _score, frame, scene, sprites, image = best
    screenshot = output / f"miniboss-{boss_index:02d}.png"
    image.save(screenshot)

    palette_entry = None
    if boss_index <= len(BOSS_YAML_KEYS):
        yaml_key = BOSS_YAML_KEYS[boss_index - 1]
        raw = palette_document["boss_palettes"][yaml_key]
        colors_bgr555 = [str(value) for value in raw["colors"]]
        palette_entry = {
            "yaml_key": yaml_key,
            "slot": int(raw["slot"]),
            "colors_bgr555": colors_bgr555,
            "colors_rgb888": [bgr555_to_rgb(value) for value in colors_bgr555],
        }

    return {
        "ffbf": boss_index,
        "dc04": dc04,
        "name": BOSS_NAMES[boss_index - 1],
        "spawn_frame": spawn_frame,
        "capture_frame": frame,
        "scene": scene,
        "screenshot": str(screenshot),
        "visible_boss_oam": sprites,
        "hardware_palette_slots": sorted({sprite["palette"] for sprite in sprites}),
        "expected_palette": palette_entry,
        "palette_status": "defined" if palette_entry else "undefined",
    }


def create_contact_sheet(entries: list[dict[str, object]], output: Path) -> None:
    columns = 4
    label_height = 28
    cell_width, cell_height = 160, 144 + label_height
    rows = (len(entries) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "black")
    draw = ImageDraw.Draw(sheet)
    for position, entry in enumerate(entries):
        x = position % columns * cell_width
        y = position // columns * cell_height
        image = Image.open(str(entry["screenshot"])).convert("RGB")
        sheet.paste(image, (x, y + label_height))
        palette = entry["expected_palette"]
        expected = (
            f"OBJ{palette['slot']} {palette['yaml_key']}"
            if palette
            else "PALETTE UNDEFINED"
        )
        draw.text((x + 2, y + 2), f"{entry['ffbf']:02d} {entry['name']}", fill="white")
        draw.text(
            (x + 2, y + 14),
            expected,
            fill="#77edaa" if palette else "#ff7f8f",
        )
    sheet.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/tmp/penta-minibosses"))
    args = parser.parse_args()
    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Remove only artifacts owned by this capture. Never recursively delete a
    # caller-supplied output directory merely because it already exists.
    for owned in output.glob("miniboss-*.png"):
        owned.unlink()
    for owned in (output / "miniboss-contact-sheet.png", output / "receipt.json"):
        owned.unlink(missing_ok=True)

    source_rom = rom.read_bytes()
    if source_rom[SPAWN_SELECTOR_OFFSET] != SPAWN_SELECTOR_ORIGINAL:
        raise SystemExit(
            f"unexpected selector byte at 0x{SPAWN_SELECTOR_OFFSET:X}: "
            f"0x{source_rom[SPAWN_SELECTOR_OFFSET]:02X}"
        )
    palette_document = yaml.safe_load(PALETTE_YAML.read_text())
    entries = [
        capture_one(source_rom, boss_index, output, palette_document)
        for boss_index in range(1, 17)
    ]
    contact_sheet = output / "miniboss-contact-sheet.png"
    create_contact_sheet(entries, contact_sheet)
    failures = []
    for entry in entries:
        palette = entry["expected_palette"]
        if palette and palette["slot"] not in entry["hardware_palette_slots"]:
            failures.append(
                f"FFBF={entry['ffbf']} expected OBJ{palette['slot']}, "
                f"saw {entry['hardware_palette_slots']}"
            )
    receipt = {
        "status": "failed" if failures else "ok_with_known_palette_gaps",
        "rom": str(rom),
        "capture_method": {
            "temporary_selector_patch_offset": SPAWN_SELECTOR_OFFSET,
            "source_byte": SPAWN_SELECTOR_ORIGINAL,
            "selected_bytes": [0x30 + index * 5 for index in range(16)],
            "source_rom_modified": False,
        },
        "captured": len(entries),
        "expected": 16,
        "defined_palette_entries": sum(
            entry["palette_status"] == "defined" for entry in entries
        ),
        "undefined_palette_entries": [
            entry["ffbf"]
            for entry in entries
            if entry["palette_status"] == "undefined"
        ],
        "contact_sheet": str(contact_sheet),
        "entries": entries,
        "failures": failures,
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"Captured {len(entries)}/16 minibosses")
    print("Defined palette entries: 1..8")
    print("Undefined palette entries: 9..16")
    print(f"Contact sheet: {contact_sheet}")
    print(f"Receipt: {receipt_path}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
