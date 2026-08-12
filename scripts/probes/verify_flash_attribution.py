#!/usr/bin/env python3
"""Verify that Sara and the first dungeon monster never use OBJ palette 4.

This is a headless PyBoy-only regression probe.  It cold-boots Stage 1, walks
right into the first dungeon room with infinite health, waits until OAM slots
0 and 2 are visible, and then samples their hardware-OAM attributes for 600
consecutive frames.

Exit status 0 means PASS, 1 means a palette-4 attribution was observed, and 2
means the harness could not establish the requested gameplay capture.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from pyboy import PyBoy


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = PROJECT_ROOT / "rom/working/penta_dragon_dx_teleport.gb"

FFC1 = 0xFFC1
D880 = 0xD880
PLAYER_HP_SUB = 0xDCDC
PLAYER_HP_MAIN = 0xDCDD
OAM_START = 0xFE00
OAM_ENTRY_SIZE = 4
SARA_SLOT = 0
MONSTER_SLOT = 2
HORNETS_ORANGE = 4
CAPTURE_FRAMES = 600

# Known-good cold-boot input schedule for this project.  START is pressed once
# the title animation has run for about 180 frames; DOWN then selects the game,
# and the later A/START presses clear the remaining menu/dialog screens.
BOOT_INPUTS = (
    (180, 186, "start"),
    (201, 207, "down"),
    (221, 227, "start"),
    (261, 267, "a"),
    (321, 327, "a"),
    (381, 387, "start"),
    (431, 437, "a"),
)


def tick(pyboy: PyBoy, frames: int = 1) -> None:
    pyboy.tick(frames, True)


def read_byte(pyboy: PyBoy, address: int) -> int:
    """Read one byte using PyBoy's memory API across supported versions.

    Older PyBoy releases expose ``memory_read(address)`` while current releases
    expose the same operation through ``memory[address]``.
    """
    memory_read = getattr(pyboy, "memory_read", None)
    if memory_read is not None:
        return int(memory_read(address))
    return int(pyboy.memory[address])


def write_godmode_health(pyboy: PyBoy) -> None:
    pyboy.memory[PLAYER_HP_SUB] = 0xFF
    pyboy.memory[PLAYER_HP_MAIN] = 0x17


def oam_entry(pyboy: PyBoy, slot: int) -> tuple[int, int, int, int]:
    base = OAM_START + slot * OAM_ENTRY_SIZE
    return tuple(read_byte(pyboy, base + offset) for offset in range(4))  # type: ignore[return-value]


def is_visible(entry: tuple[int, int, int, int]) -> bool:
    # A hidden/unused Game Boy sprite normally has X=0 or Y=0.  These bounds
    # also admit sprites partially clipped at the right or bottom screen edge.
    y, x, _tile, _attributes = entry
    return 0 < y < 160 and 0 < x < 168


def enter_gameplay(pyboy: PyBoy, timeout: int) -> int:
    held: str | None = None
    for frame in range(1, 501):
        wanted = next(
            (button for start, end, button in BOOT_INPUTS if start <= frame < end),
            None,
        )
        if wanted != held:
            if held is not None:
                pyboy.button_release(held)
            if wanted is not None:
                pyboy.button_press(wanted)
            held = wanted
        tick(pyboy)
    if held is not None:
        pyboy.button_release(held)

    # Continue nudging through any remaining menu and walking right.  Once
    # FFC1==1, keep walking so the first dungeon room and its enemies load.
    pyboy.button_press("right")
    try:
        for elapsed in range(timeout):
            if read_byte(pyboy, FFC1) == 1:
                write_godmode_health(pyboy)
                return elapsed
            if elapsed % 180 == 0:
                pyboy.button_press("a")
            elif elapsed % 180 == 6:
                pyboy.button_release("a")
            tick(pyboy)
    finally:
        pyboy.button_release("a")
    raise RuntimeError(
        "gameplay did not become active "
        f"(FFC1=0x{read_byte(pyboy, FFC1):02X}, "
        f"D880=0x{read_byte(pyboy, D880):02X})"
    )


def wait_for_visible_sprites(pyboy: PyBoy, timeout: int) -> int:
    pyboy.button_press("right")
    try:
        for elapsed in range(timeout):
            write_godmode_health(pyboy)
            tick(pyboy)
            if is_visible(oam_entry(pyboy, SARA_SLOT)) and is_visible(
                oam_entry(pyboy, MONSTER_SLOT)
            ):
                return elapsed + 1
    finally:
        pyboy.button_release("right")
    raise RuntimeError(
        f"OAM slots {SARA_SLOT} and {MONSTER_SLOT} were not both visible "
        f"within {timeout} frames"
    )


def format_distribution(distribution: Counter[int]) -> str:
    return ", ".join(
        f"Palette {palette}: {distribution.get(palette, 0)}"
        for palette in range(8)
    )


def run_probe(rom: Path, timeout: int) -> bool:
    # ``sound`` is not the PyBoy 2.x switch for disabling audio emulation.
    # Keeping it here left the audio ring buffer active during unthrottled
    # headless runs, producing one CRITICAL buffer-overrun line per tick.
    pyboy = PyBoy(
        str(rom),
        window="null",
        cgb=True,
        sound_emulated=False,
        log_level=5,
    )
    pyboy.set_emulation_speed(0)
    distributions = {SARA_SLOT: Counter(), MONSTER_SLOT: Counter()}

    try:
        gameplay_wait = enter_gameplay(pyboy, timeout)
        sprite_wait = wait_for_visible_sprites(pyboy, timeout)
        print(
            "Gameplay ready: "
            f"FFC1=1, D880=0x{read_byte(pyboy, D880):02X}; "
            f"visible sprites found after {sprite_wait} additional frames "
            f"({gameplay_wait} frames after boot schedule to gameplay)."
        )

        # One tick followed by one OAM read is one consecutive emulated frame.
        for _frame in range(CAPTURE_FRAMES):
            write_godmode_health(pyboy)
            tick(pyboy)
            for slot in distributions:
                attributes = oam_entry(pyboy, slot)[3]
                distributions[slot][attributes & 0x07] += 1
    finally:
        pyboy.stop(save=False)

    print(f"Captured {CAPTURE_FRAMES} consecutive gameplay frames.")
    print(f"Slot 0 (Sara):          {format_distribution(distributions[SARA_SLOT])}")
    print(f"Slot 2 (first monster): {format_distribution(distributions[MONSTER_SLOT])}")

    sara_orange = distributions[SARA_SLOT][HORNETS_ORANGE]
    monster_orange = distributions[MONSTER_SLOT][HORNETS_ORANGE]
    if sara_orange or monster_orange:
        print(
            "FAIL: Hornets Orange (Palette 4) was wrongly attributed: "
            f"slot 0={sara_orange} frame(s), slot 2={monster_orange} frame(s)."
        )
        return False

    print("PASS: Palette 4 appeared on neither slot during all 600 frames.")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="maximum frames for gameplay and visible-sprite waits (default: 3600)",
    )
    args = parser.parse_args()

    if not args.rom.is_file():
        print(f"HARNESS ERROR: ROM not found: {args.rom}", file=sys.stderr)
        return 2
    try:
        return 0 if run_probe(args.rom, args.timeout) else 1
    except Exception as exc:
        print(f"HARNESS ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
