#!/usr/bin/env python3
"""Direct-enter and inventory the original pre/post-final story sequences.

This is a diagnostic entry, not a ROM patch.  It cold-boots the production
ROM, maps bank 1, and starts at either the stock pre-Penta bridge at 0x54C0
or post-Penta continuation at 0x5514.
"""

from __future__ import annotations

import argparse
import json
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pyboy import PyBoy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = PROJECT_ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = Path("/tmp/penta-final-cutscene")

D880 = 0xD880
FFC1 = 0xFFC1
FF99 = 0xFF99
FFBA = 0xFFBA
FFE4 = 0xFFE4
DD09 = 0xDD09
DF02 = 0xDF02
DF0D = 0xDF0D
WRAM_BG_TABLE = 0xCC00
IE = 0xFFFF
MBC_ROM_BANK = 0x2000
ENDING_BANK = 1
PRE_FINAL_ENTRY = 0x54C0
POST_FINAL_ENTRY = 0x5514
STORY_STATE_BYTES = {
    "d889": 0xD889,
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
    # Stock ending-script phase flag: 0 through the credit pages, 1 after the
    # terminal 0xFF command invokes the final page.
    "fff9": 0xFFF9,
}


@dataclass
class Panel:
    frame: int
    scene: int
    ffc1: int
    ffba: int
    ffe4: int
    palettes: Counter[int]
    unsafe_attrs: int
    table_values: Counter[int]
    df02: int
    df0d: int
    tilemap: bytes
    tilemap_crc32: int
    image_crc32: int
    story_state: dict[str, int]
    path: Path


def visible_bg(
    pyboy: PyBoy,
) -> tuple[Counter[int], int, bytes]:
    """Return palette usage and tile IDs for the visible BG viewport."""
    memory = pyboy.memory
    lcdc = memory[0xFF40]
    scy = memory[0xFF42]
    scx = memory[0xFF43]
    base = 0x9C00 if lcdc & 0x08 else 0x9800
    palettes: Counter[int] = Counter()
    unsafe_attrs = 0
    tilemap = bytearray()
    for row in range(18):
        for column in range(20):
            map_y = ((scy + row * 8) >> 3) & 0x1F
            map_x = ((scx + column * 8) >> 3) & 0x1F
            address = base + map_y * 32 + map_x
            tilemap.append(pyboy.memory[0, address])
            attribute = pyboy.memory[1, address]
            palettes[attribute & 7] += 1
            if attribute & 0xF8:
                unsafe_attrs += 1
    return palettes, unsafe_attrs, bytes(tilemap)


def story_state(pyboy: PyBoy) -> dict[str, int]:
    return {
        name: pyboy.memory[address]
        for name, address in STORY_STATE_BYTES.items()
    }


def pulse(pyboy: PyBoy, button: str, hold: int = 3, gap: int = 5) -> int:
    pyboy.button_press(button)
    pyboy.tick(hold, True)
    pyboy.button_release(button)
    pyboy.tick(gap, True)
    return hold + gap


def direct_enter_final(pyboy: PyBoy, entry: str) -> None:
    """Start a stock bank-1 final-game path in a clean title context."""
    memory = pyboy.memory
    registers = pyboy.register_file

    # Match the state produced after the final boss sufficiently for the stock
    # story/ending path.  Interrupts are masked only while the bank and PC are
    # changed; live VBlank timing and the DX colorizer run during the capture.
    saved_ie = memory[IE]
    memory[IE] = 0
    memory[FFC1] = 0
    memory[FFBA] = 6 if entry == "pre-final" else 8
    memory[FFE4] = 0 if entry == "pre-final" else 1
    # DD09=1 is the title demo/input-block flag.  The real ending dialogue
    # needs ordinary input enabled so its per-page wait can observe A.
    memory[DD09] = 0
    memory[MBC_ROM_BANK] = ENDING_BANK
    memory[FF99] = ENDING_BANK

    return_pc = registers.PC
    stack_pointer = (registers.SP - 2) & 0xFFFF
    memory[stack_pointer] = return_pc & 0xFF
    memory[(stack_pointer + 1) & 0xFFFF] = return_pc >> 8
    registers.SP = stack_pointer
    registers.PC = (
        PRE_FINAL_ENTRY if entry == "pre-final" else POST_FINAL_ENTRY
    )
    memory[IE] = saved_ie


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--frames", type=int, default=10000)
    parser.add_argument(
        "--entry",
        choices=("post-final", "pre-final"),
        default="post-final",
        help="which original bank-1 final-game path to inventory",
    )
    parser.add_argument(
        "--expect-neutral",
        action="store_true",
        help="fail if any sampled ending viewport cell uses BG palette 1-7",
    )
    parser.add_argument(
        "--expect-production",
        action="store_true",
        help=(
            "require the ROM-native story split and credits/END/epilogue "
            "palette families, allowing only bounded phase transitions"
        ),
    )
    args = parser.parse_args()
    if args.expect_neutral and args.expect_production:
        parser.error("--expect-neutral and --expect-production conflict")

    rom = args.rom.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)

    pyboy = PyBoy(str(rom), window="null", cgb=True, sound=False)
    pyboy.set_emulation_speed(0)
    transitions: list[tuple[int, int, int, int, int]] = []
    panels: list[Panel] = []
    previous_scene: int | None = None
    previous_capture_key: tuple | None = None
    last_capture = -1000
    entered = False
    finished = False
    frame = 0
    try:
        # Let the stock title initialize VRAM/CRAM and the DX VBlank hook.
        pyboy.tick(600, True)
        direct_enter_final(pyboy, args.entry)
        entered = True

        while frame < args.frames:
            pyboy.tick(1, True)
            frame += 1
            scene = pyboy.memory[D880]
            ffc1 = pyboy.memory[FFC1]
            ffba = pyboy.memory[FFBA]
            ffe4 = pyboy.memory[FFE4]
            if scene != previous_scene:
                transitions.append((frame, scene, ffc1, ffba, ffe4))
                previous_scene = scene

            capture_scenes = (
                {0x19, 0x18} if args.entry == "pre-final" else {0x1A, 0x16}
            )
            ending = scene in capture_scenes or (
                args.entry == "post-final"
                and scene == 0x00
                and ffe4 == 1
                and ffc1 == 0
            )
            if ending and frame >= 60 and frame - last_capture >= 90:
                image = pyboy.screen.image
                image_crc = zlib.crc32(image.tobytes())
                palettes, unsafe_attrs, tilemap = visible_bg(pyboy)
                current_story_state = story_state(pyboy)
                tilemap_crc = zlib.crc32(tilemap)
                # Attribute repairs can progress while the rendered pixels
                # remain visually identical (notably the static END page).
                # Key captures on the underlying production state as well as
                # the framebuffer so the inventory cannot skip a fully
                # committed palette phase.
                capture_key = (
                    image_crc,
                    tilemap_crc,
                    tuple(sorted(palettes.items())),
                    unsafe_attrs,
                    scene,
                    current_story_state["fff9"],
                    current_story_state["dce2"],
                )
                if capture_key != previous_capture_key:
                    path = output / (
                        f"panel{len(panels) + 1:02d}_f{frame}_s{scene:02X}.png"
                    )
                    image.save(path)
                    panels.append(
                        Panel(
                            frame,
                            scene,
                            ffc1,
                            ffba,
                            ffe4,
                            palettes,
                            unsafe_attrs,
                            Counter(
                                pyboy.memory[WRAM_BG_TABLE + index]
                                for index in range(0x100)
                            ),
                            pyboy.memory[DF02],
                            pyboy.memory[DF0D],
                            tilemap,
                            tilemap_crc,
                            image_crc,
                            current_story_state,
                            path,
                        )
                    )
                    previous_capture_key = capture_key
                    last_capture = frame

            # Advance dialogue deliberately, slowly enough to render each page.
            if frame >= 180 and frame % 90 == 0:
                frame += pulse(pyboy, "a")

            # The pre-final bridge ends at the Penta arena. The post-final
            # ending eventually clears FFE4 and initializes a new title.
            if (
                args.entry == "pre-final"
                and frame > 120
                and 0x0C <= scene <= 0x14
            ):
                finished = True
                break
            if (
                args.entry == "post-final"
                and entered
                and frame > 600
                and scene < 0x02
                and ffe4 == 0
            ):
                pyboy.tick(120, True)
                frame += 120
                finished = True
                break
    finally:
        pyboy.stop()

    print("Scene transitions:")
    print(
        "  "
        + " ".join(
            f"f{f}:{scene:02X}/g{ffc1}/ba{ffba:02X}/e4{ffe4}"
            for f, scene, ffc1, ffba, ffe4 in transitions
        )
    )
    print("\nEnding panels:")
    for panel in panels:
        print(
            f"  f{panel.frame} s{panel.scene:02X}: "
            f"attrs={dict(sorted(panel.palettes.items()))} "
            f"unsafe={panel.unsafe_attrs} "
            f"table={dict(sorted(panel.table_values.items()))} "
            f"df02={panel.df02:02X} df0d={panel.df0d:02X} "
            f"map={panel.tilemap_crc32:08X} image={panel.image_crc32:08X} "
            + " ".join(
                f"{name}={value:02X}"
                for name, value in panel.story_state.items()
            )
            + f" {panel.path.name}"
        )

    expected_scene = 0x19 if args.entry == "pre-final" else 0x1A
    if not any(
        scene == expected_scene for _f, scene, _g, _ba, _e4 in transitions
    ):
        print(
            f"FAIL: stock {args.entry} entry did not publish "
            f"D880={expected_scene:02X}"
        )
        return 1
    if not panels:
        print("FAIL: no ending panels were captured")
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
            f"FAIL: ending has {contaminated} sampled non-neutral "
            f"and {unsafe} unsafe high-bit BG-attribute cells"
        )
        return 1
    if args.expect_neutral:
        print("PASS: every sampled ending panel is 360/360 palette 0.")
    elif contaminated:
        print(
            f"OBSERVED: ending has {contaminated} sampled non-neutral "
            "BG-attribute cells."
        )
    if args.expect_production:
        failures = []
        full_story_arts: set[int] = set()
        full_phases: set[str] = set()
        previous_full_story_art: int | None = None
        story_transition_art: int | None = None
        story_transition_samples = 0
        for index, panel in enumerate(panels, 1):
            palettes = panel.palettes
            state = panel.story_state
            if panel.unsafe_attrs:
                failures.append(
                    f"panel {index} f{panel.frame}: "
                    f"{panel.unsafe_attrs} unsafe high-bit attributes"
                )
            if panel.table_values != Counter({0: 256}):
                failures.append(
                    f"panel {index} f{panel.frame}: active table is "
                    f"{dict(sorted(panel.table_values.items()))}"
                )
            if panel.scene in {0x19, 0x1A}:
                art = state["dcf0"]
                sequence = 0x04 if panel.scene == 0x19 else 0x05
                art_committed = (
                    state["dce8"] == sequence
                    and state["dcea"] == 0x01
                    and 1 <= art <= 7
                    and ((state["dd07"] + 1) & 0xFF) == art
                )
                expected = (
                    Counter({art: 160, 0: 200})
                    if art_committed
                    else Counter({0: 360})
                )
                if palettes == expected:
                    if art_committed:
                        full_story_arts.add(art)
                        previous_full_story_art = art
                    story_transition_art = None
                    story_transition_samples = 0
                    continue

                nonneutral = sum(
                    count
                    for palette, count in palettes.items()
                    if palette != 0
                )
                committed_transition = (
                    art_committed
                    and previous_full_story_art is not None
                    and previous_full_story_art != art
                    and palettes.get(0, 0) == 200
                    and nonneutral == 160
                    and set(palettes)
                    <= {0, previous_full_story_art, art}
                )
                precommit_transition = (
                    not art_committed
                    and state["dce8"] == sequence
                    and state["dcea"] == 0x01
                    and 1 <= art <= 7
                    and previous_full_story_art is not None
                    and previous_full_story_art != art
                    and palettes
                    == Counter({previous_full_story_art: 160, 0: 200})
                )
                bounded_transition = (
                    committed_transition or precommit_transition
                )
                if bounded_transition:
                    if story_transition_art != art:
                        story_transition_art = art
                        story_transition_samples = 0
                    story_transition_samples += 1
                    if story_transition_samples <= 1:
                        continue
                else:
                    story_transition_art = None
                    story_transition_samples = 0

                if palettes != expected:
                    failures.append(
                        f"panel {index} f{panel.frame}: story attrs "
                        f"{dict(sorted(palettes.items()))} != "
                        f"{dict(sorted(expected.items()))}"
                    )
                continue

            allowed: set[int] | None = None
            phase: str | None = None
            target: int | None = None
            if panel.scene == 0x16 and state["fff9"] == 0:
                allowed, phase, target = {0, 1}, "credits", 1
            elif panel.scene == 0x16 and state["fff9"] == 1:
                allowed, phase, target = {1, 2}, "end", 2
            elif (
                panel.scene == 0x00
                and panel.ffe4 == 1
                and state["d889"] == 0x0C
                and state["dce2"] == 0
            ):
                allowed, phase, target = {0, 2}, "epilogue_preamble", 0
            elif (
                panel.scene == 0x00
                and panel.ffe4 == 1
                and state["d889"] == 0x0C
                and state["dce2"] == 1
            ):
                allowed, phase, target = {0, 3}, "epilogue_text", 3
            if allowed is not None:
                unexpected = set(palettes) - allowed
                if unexpected:
                    failures.append(
                        f"panel {index} f{panel.frame}: {phase} uses "
                        f"unexpected palettes {sorted(unexpected)}"
                    )
                if palettes == Counter({target: 360}):
                    full_phases.add(phase)

        required_arts = {4, 7} if args.entry == "pre-final" else {5, 6, 7}
        missing_arts = required_arts - full_story_arts
        if missing_arts:
            failures.append(
                f"missing full story art palettes {sorted(missing_arts)}"
            )
        if args.entry == "post-final":
            required_phases = {
                "credits", "end", "epilogue_preamble", "epilogue_text"
            }
            missing_phases = required_phases - full_phases
            if missing_phases:
                failures.append(
                    f"missing full production phases {sorted(missing_phases)}"
                )
            if not finished:
                failures.append("ending did not return to a settled title")
        if failures:
            print("FAIL: final-story production palette inventory:")
            for failure in failures[:16]:
                print(f"  - {failure}")
            return 1
        print(
            "PASS: final story, credits, END, and epilogue use only their "
            "production palette families and complete every required phase."
        )
    if not finished:
        print(
            "NOTE: capture reached the frame limit before the ending returned "
            "to a settled title."
        )
    manifest = {
        "route": args.entry,
        "rom": str(rom),
        "story_state_bytes": STORY_STATE_BYTES,
        "panels": [
            {
                "frame": panel.frame,
                "scene": panel.scene,
                "ffc1": panel.ffc1,
                "ffba": panel.ffba,
                "ffe4": panel.ffe4,
                "palettes": dict(sorted(panel.palettes.items())),
                "unsafe_attr_cells": panel.unsafe_attrs,
                "tilemap_crc32": f"{panel.tilemap_crc32:08X}",
                "image_crc32": f"{panel.image_crc32:08X}",
                "tilemap_hex": panel.tilemap.hex().upper(),
                "story_state": panel.story_state,
                "image": panel.path.name,
            }
            for panel in panels
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(f"Captured {len(panels)} ending panels in {output}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
