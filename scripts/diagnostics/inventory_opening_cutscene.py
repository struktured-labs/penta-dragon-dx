#!/usr/bin/env python3
"""Drive the title's OPENING option and inventory its CGB BG attributes."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import sys
import zlib

from pyboy import PyBoy


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from cutscene_region_palettes import (  # noqa: E402
    load_cutscene_region_palettes,
    panel_mask,
)


STORY_STATE_BYTES = {
    "dce2": 0xDCE2,
    "dce5": 0xDCE5,
    "dce6": 0xDCE6,
    "dce7": 0xDCE7,
    "dce8": 0xDCE8,
    "dce9": 0xDCE9,
    "dcea": 0xDCEA,
    "dceb": 0xDCEB,
    "dcee": 0xDCEE,
    "dcef": 0xDCEF,
    "dcf0": 0xDCF0,
    "dd07": 0xDD07,
    "df07": 0xDF07,
    "df49": 0xDF49,
    "df4a": 0xDF4A,
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass
class Panel:
    frame: int
    palettes: Counter[int]
    unsafe_attrs: int
    tiles: Counter[tuple[int, int]]
    tilemap: bytes
    attributes: bytes
    tilemap_crc32: int
    image_crc32: int
    story_state: dict[str, int]
    path: Path


def visible_bg(
    pyboy: PyBoy,
) -> tuple[Counter[int], int, Counter[tuple[int, int]], bytes, bytes]:
    memory = pyboy.memory
    lcdc = memory[0xFF40]
    scy = memory[0xFF42]
    scx = memory[0xFF43]
    base = 0x9C00 if lcdc & 0x08 else 0x9800
    palettes: Counter[int] = Counter()
    unsafe_attrs = 0
    tiles: Counter[tuple[int, int]] = Counter()
    tilemap = bytearray()
    attributes = bytearray()
    for row in range(18):
        for column in range(20):
            map_y = ((scy + row * 8) >> 3) & 0x1F
            map_x = ((scx + column * 8) >> 3) & 0x1F
            address = base + map_y * 32 + map_x
            tile = memory[0, address]
            attribute = memory[1, address]
            palette = attribute & 7
            if attribute & 0xF8:
                unsafe_attrs += 1
            tilemap.append(tile)
            attributes.append(attribute)
            palettes[palette] += 1
            tiles[(tile, palette)] += 1
    return palettes, unsafe_attrs, tiles, bytes(tilemap), bytes(attributes)


def story_state(pyboy: PyBoy) -> dict[str, int]:
    return {
        name: pyboy.memory[address]
        for name, address in STORY_STATE_BYTES.items()
    }


def pulse(pyboy: PyBoy, button: str, hold: int = 4, gap: int = 4) -> int:
    pyboy.button_press(button)
    pyboy.tick(hold, True)
    pyboy.button_release(button)
    pyboy.tick(gap, True)
    return hold + gap


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/tmp/penta-opening"))
    parser.add_argument(
        "--palette-yaml",
        type=Path,
        default=ROOT / "palettes/penta_palettes_v097.yaml",
    )
    parser.add_argument("--frames", type=int, default=12000)
    parser.add_argument(
        "--expect-neutral",
        action="store_true",
        help="fail if any visible OPENING cell uses a non-zero BG palette",
    )
    parser.add_argument(
        "--expect-production",
        action="store_true",
        help=(
            "require committed artwork to use its BG1..BG7 page palette "
            "above a neutral BG0 dialogue region"
        ),
    )
    args = parser.parse_args()
    if args.expect_neutral and args.expect_production:
        parser.error("--expect-neutral and --expect-production conflict")

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    cutscene_panels = load_cutscene_region_palettes(args.palette_yaml)
    expected_story_attrs = {
        art_id: bytes(
            value
            for row in panel_mask(panel)
            for value in row
        ) + bytes(200)
        for art_id, panel in cutscene_panels.items()
    }

    pyboy = PyBoy(
        str(args.rom.resolve()),
        window="null",
        cgb=True,
        sound_emulated=False,
        log_level=5,
    )
    pyboy.set_emulation_speed(0)
    transitions = []
    panels = []
    previous_scene = None
    opening_started = False
    last_panel = -1000
    panel_number = 0
    frame = 0
    try:
        while frame < args.frames:
            pyboy.tick(1, True)
            frame += 1
            scene = pyboy.memory[0xD880]
            if scene != previous_scene:
                transitions.append((
                    frame, scene, pyboy.memory[0xFFC1],
                    pyboy.memory[0xFFBA], pyboy.memory[0xFFE4],
                ))
                previous_scene = scene

            # The title defaults to OPENING START. A selects the highlighted
            # option; repeat once in case the first pulse lands during draw-in.
            if not opening_started and frame in {210, 330}:
                frame += pulse(pyboy, "a")

            if scene == 0x15:
                opening_started = True
                # Sample settled panels, and tap A periodically to advance any
                # text wait without skipping all of the intervening animation.
                if frame - last_panel >= 360:
                    panel_number += 1
                    (
                        palettes,
                        unsafe_attrs,
                        tiles,
                        tilemap,
                        attributes,
                    ) = visible_bg(pyboy)
                    path = output / f"panel{panel_number:02d}_f{frame}.png"
                    image = pyboy.screen.image
                    image.save(path)
                    panels.append(
                        Panel(
                            frame,
                            palettes,
                            unsafe_attrs,
                            tiles,
                            tilemap,
                            attributes,
                            zlib.crc32(tilemap),
                            zlib.crc32(image.tobytes()),
                            story_state(pyboy),
                            path,
                        )
                    )
                    last_panel = frame
                if frame % 300 == 0:
                    frame += pulse(pyboy, "a", 2, 2)
            elif opening_started and scene in {0x00, 0x01, 0x1C}:
                # Opening returned to the title.
                if frame - last_panel > 120:
                    break
    finally:
        pyboy.stop()

    print("Scene transitions:")
    print("  " + " ".join(
        f"f{frame}:{scene:02X}/g{ffc1}/ba{ffba:02X}/e4{ffe4}"
        for frame, scene, ffc1, ffba, ffe4 in transitions
    ))
    print("\nOpening panels:")
    for panel in panels:
        top = " ".join(
            f"{tile:02X}:p{palette}x{count}"
            for (tile, palette), count in panel.tiles.most_common(8)
        )
        state = " ".join(
            f"{name}={value:02X}"
            for name, value in panel.story_state.items()
        )
        print(
            f"  f{panel.frame}: attrs={dict(sorted(panel.palettes.items()))} "
            f"unsafe={panel.unsafe_attrs} "
            f"map={panel.tilemap_crc32:08X} image={panel.image_crc32:08X} "
            f"{state} top=[{top}] {panel.path.name}"
        )
    if not opening_started:
        print("FAIL: OPENING did not reach D880=15")
        return 1
    if not panels:
        print("FAIL: no OPENING panels captured")
        return 1
    contaminated = sum(
        count
        for panel in panels
        for palette, count in panel.palettes.items()
        if palette != 0
    )
    unsafe = sum(panel.unsafe_attrs for panel in panels)
    if args.expect_neutral and (contaminated or unsafe):
        print(
            f"FAIL: OPENING has {contaminated} sampled non-neutral "
            f"and {unsafe} unsafe high-bit BG-attribute cells"
        )
        return 1
    if args.expect_neutral:
        print("PASS: every sampled OPENING panel is 360/360 palette 0.")
    full_story_arts: set[int] = set()
    if args.expect_production:
        failures = []
        previous_full_story_art: int | None = None
        transition_art: int | None = None
        transition_samples = 0
        for index, panel in enumerate(panels, 1):
            state = panel.story_state
            art = state["dcf0"]
            art_committed = (
                state["dce8"] == 0x02
                and state["dcea"] == 0x01
                and 1 <= art <= 7
                and ((state["dd07"] + 1) & 0xFF) == art
            )
            expected_attributes = (
                expected_story_attrs[art]
                if art_committed
                else bytes(360)
            )
            expected = Counter(expected_attributes)
            if panel.unsafe_attrs:
                failures.append(
                    f"panel {index} f{panel.frame}: "
                    f"{panel.unsafe_attrs} unsafe high-bit attributes"
                )
            if panel.attributes == expected_attributes:
                if art_committed:
                    full_story_arts.add(art)
                    previous_full_story_art = art
                transition_art = None
                transition_samples = 0
                continue

            previous_attributes = (
                expected_story_attrs[previous_full_story_art]
                if previous_full_story_art is not None
                else None
            )
            bounded_transition = (
                art_committed
                and previous_attributes is not None
                and previous_full_story_art != art
                and panel.attributes[160:] == bytes(200)
                and all(
                    actual in {old, new}
                    for actual, old, new in zip(
                        panel.attributes[:160],
                        previous_attributes[:160],
                        expected_story_attrs[art][:160],
                    )
                )
            )
            # The stock engine updates DCF0 one render step before DD07 and the
            # tilemap commit. At that exact handoff, the complete previous art
            # page is still what the player sees, so retaining its 160 attrs is
            # correct. Accept only one such sample and only when the very next
            # captured panel commits the announced new art ID.
            next_state = (
                panels[index].story_state
                if index < len(panels)
                else None
            )
            next_commits_art = (
                next_state is not None
                and next_state["dce8"] == 0x02
                and next_state["dcea"] == 0x01
                and next_state["dcf0"] == art
                and ((next_state["dd07"] + 1) & 0xFF) == art
            )
            previous_page_handoff = (
                not art_committed
                and state["dce8"] == 0x02
                and state["dcea"] == 0x01
                and 1 <= art <= 7
                and previous_full_story_art is not None
                and previous_full_story_art != art
                and panel.attributes == previous_attributes
                and next_commits_art
            )
            if bounded_transition or previous_page_handoff:
                if transition_art != art:
                    transition_art = art
                    transition_samples = 0
                transition_samples += 1
                if transition_samples <= 1:
                    continue
            else:
                transition_art = None
                transition_samples = 0

            if panel.attributes != expected_attributes:
                failures.append(
                    f"panel {index} f{panel.frame}: "
                    f"{dict(sorted(panel.palettes.items()))} != "
                    f"{dict(sorted(expected.items()))}"
                )
        missing_arts = {1, 2, 3} - full_story_arts
        if missing_arts:
            failures.append(
                f"missing full OPENING art palettes {sorted(missing_arts)}"
            )
        if failures:
            print("FAIL: OPENING production palette layout:")
            for failure in failures[:12]:
                print(f"  - {failure}")
            return 1
        print(
            "PASS: committed OPENING artwork exactly matches its YAML "
            "160-cell region mask above neutral BG0 dialogue (200 cells)."
        )
    manifest = {
        "schema": "penta-dragon-dx-opening-cutscene-v3",
        "status": "pass",
        "verification_mode": (
            "production"
            if args.expect_production
            else "neutral" if args.expect_neutral else "inventory"
        ),
        "route": "opening",
        "rom": str(args.rom.resolve()),
        "rom_sha256": sha256(args.rom.resolve()),
        "palette_yaml": str(args.palette_yaml.resolve()),
        "palette_yaml_sha256": sha256(args.palette_yaml.resolve()),
        "checks": {
            "opening_reached": opening_started,
            "panels_captured": bool(panels),
            "unsafe_attributes_zero": unsafe == 0,
            "required_region_masks_observed": (
                full_story_arts >= {1, 2, 3}
                if args.expect_production
                else None
            ),
        },
        "full_story_arts": sorted(full_story_arts),
        "story_state_bytes": STORY_STATE_BYTES,
        "panels": [
            {
                "frame": panel.frame,
                "scene": 0x15,
                "palettes": dict(sorted(panel.palettes.items())),
                "unsafe_attr_cells": panel.unsafe_attrs,
                "tilemap_crc32": f"{panel.tilemap_crc32:08X}",
                "image_crc32": f"{panel.image_crc32:08X}",
                "tilemap_hex": panel.tilemap.hex().upper(),
                "attribute_hex": panel.attributes.hex().upper(),
                "story_state": panel.story_state,
                "image": panel.path.name,
            }
            for panel in panels
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(f"\nCaptured {len(panels)} OPENING panels in {output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
