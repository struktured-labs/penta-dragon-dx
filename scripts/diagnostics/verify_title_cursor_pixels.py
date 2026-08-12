#!/usr/bin/env python3
"""Verify the real title cursor and the OPENING/GAME START option order.

The retired probe hard-coded the teleport ROM and cropped copyright text,
which made whitespace symmetry look like a letter-shaped cursor. This gate
uses the release candidate, checks the exact 8x7 right-pointing marker through
PyBoy's rendered pixel pipeline, and proves that DOWN moves it from the default
OPENING START row to GAME START without leaving the title scene.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image
from pyboy import PyBoy


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = Path("/tmp/penta-title-cursor-gate")

D880 = 0xD880
FFC1 = 0xFFC1
TITLE_SCENE = 0x01

CURSOR_X = 24
CURSOR_WIDTH = 8
CURSOR_HEIGHT = 7
OPENING_Y = 65
GAME_Y = 81

# Native 8x7 right-pointing marker visible beside the title choices:
#   ##......
#   ####....
#   ######..
#   ########
#   ######..
#   ####....
#   ##......
EXPECTED_MARKER = (
    "##......",
    "####....",
    "######..",
    "########",
    "######..",
    "####....",
    "##......",
)
EMPTY = tuple("." * CURSOR_WIDTH for _ in range(CURSOR_HEIGHT))


def native_marker_phase(rows: tuple[str, ...]) -> bool:
    """Accept the stock game's raster-visible blink transition.

    The original ROM can expose one frame with only the top or bottom
    contiguous portion of the marker visible while it blinks.  Each visible
    row must still be the exact native row, and the visible rows may have only
    one empty/non-empty boundary.
    """

    visible: list[bool] = []
    for row, expected in zip(rows, EXPECTED_MARKER, strict=True):
        if row == expected:
            visible.append(True)
        elif row == "." * CURSOR_WIDTH:
            visible.append(False)
        else:
            return False
    transitions = sum(a != b for a, b in zip(visible, visible[1:]))
    return transitions <= 1


def dark(pixel: tuple[int, ...]) -> bool:
    return max(pixel[:3]) < 128


def marker_rows(image: Image.Image, y_start: int) -> tuple[str, ...]:
    rgb = image.convert("RGB")
    return tuple(
        "".join(
            "#" if dark(rgb.getpixel((x, y))) else "."
            for x in range(CURSOR_X, CURSOR_X + CURSOR_WIDTH)
        )
        for y in range(y_start, y_start + CURSOR_HEIGHT)
    )


def pulse(pyboy: PyBoy, button: str) -> None:
    pyboy.button_press(button)
    pyboy.tick(3, True)
    pyboy.button_release(button)
    # Let the release edge finish drawing before judging the stationary cursor.
    # The first render immediately after DOWN is a legitimate one-frame move
    # transition; the following three complete blink periods must retain the
    # stock marker's exact row shapes, including its raster-visible partial
    # draw/erase frame.
    pyboy.tick(2, True)


def observe_cursor(
    pyboy: PyBoy,
    output: Path,
    stem: str,
    expected_row: str,
    frames: int = 180,
) -> dict:
    expected_marker_frames: list[int] = []
    wrong_marker_frames: list[int] = []
    unexpected_pattern_frames: list[int] = []
    unexpected_patterns: list[dict[str, object]] = []
    context_failures: list[str] = []
    marker_image_saved = False
    first_image_saved = False

    for frame in range(frames):
        image = pyboy.screen.image.copy()
        opening = marker_rows(image, OPENING_Y)
        game = marker_rows(image, GAME_Y)
        if not first_image_saved:
            image.save(output / f"{stem}.first.png")
            first_image_saved = True

        expected = opening if expected_row == "opening" else game
        wrong = game if expected_row == "opening" else opening
        if expected == EXPECTED_MARKER:
            expected_marker_frames.append(frame)
            if not marker_image_saved:
                image.save(output / f"{stem}.marker.png")
                marker_image_saved = True
        if wrong != EMPTY:
            wrong_marker_frames.append(frame)
        if not native_marker_phase(opening) or not native_marker_phase(game):
            unexpected_pattern_frames.append(frame)
            unexpected_patterns.append(
                {
                    "frame": frame,
                    "opening": opening,
                    "game": game,
                }
            )
            image.save(output / f"{stem}.unexpected-f{frame:03d}.png")

        scene = pyboy.memory[D880]
        gameplay = pyboy.memory[FFC1]
        if scene != TITLE_SCENE or gameplay != 0:
            context_failures.append(
                f"f{frame}:D880={scene:02X}/FFC1={gameplay}"
            )
        if frame + 1 < frames:
            pyboy.tick(1, True)

    return {
        "expected_row": expected_row,
        "frames": frames,
        "expected_marker_frames": expected_marker_frames,
        "wrong_marker_frames": wrong_marker_frames,
        "unexpected_pattern_frames": unexpected_pattern_frames,
        "unexpected_patterns": unexpected_patterns,
        "context_failures": context_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    output.mkdir(parents=True, exist_ok=True)

    pyboy = PyBoy(
        str(rom), window="null", cgb=True,
        sound_emulated=False, log_level=5,
    )
    pyboy.set_emulation_speed(0)
    failures: list[str] = []
    try:
        pyboy.tick(300, True)
        initial = observe_cursor(
            pyboy, output, "default-opening", "opening"
        )

        pulse(pyboy, "down")
        down = observe_cursor(
            pyboy, output, "down-game-start", "game"
        )

        pulse(pyboy, "up")
        restored = observe_cursor(
            pyboy, output, "up-opening-restored", "opening"
        )
    finally:
        pyboy.stop(save=False)

    states = {
        "default": initial,
        "down": down,
        "restored": restored,
    }

    for name, state in states.items():
        if state["context_failures"]:
            failures.append(
                f"{name}: left title context at "
                f"{', '.join(state['context_failures'])}"
            )
        if not state["expected_marker_frames"]:
            failures.append(
                f"{name}: cursor never appeared on {state['expected_row']}"
            )
        if state["wrong_marker_frames"]:
            failures.append(
                f"{name}: cursor appeared on the wrong row at frames "
                f"{state['wrong_marker_frames']}"
            )
        if state["unexpected_pattern_frames"]:
            failures.append(
                f"{name}: non-native cursor pixels at frames "
                f"{state['unexpected_pattern_frames']}"
            )

    report = {
        "status": "failed" if failures else "ok",
        "rom": str(rom),
        "cursor_box": {
            "x": CURSOR_X,
            "width": CURSOR_WIDTH,
            "height": CURSOR_HEIGHT,
            "opening_y": OPENING_Y,
            "game_y": GAME_Y,
        },
        "expected_marker": EXPECTED_MARKER,
        "states": states,
        "failures": failures,
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    for name, state in states.items():
        print(
            f"{name:8s}: expected={state['expected_row']} "
            f"visible={len(state['expected_marker_frames'])}/{state['frames']} "
            f"wrong={len(state['wrong_marker_frames'])} "
            f"other={len(state['unexpected_pattern_frames'])} "
            f"context_bad={len(state['context_failures'])}"
        )
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print(
        "PASS: the native right-pointing cursor defaults to OPENING START; "
        "DOWN moves it to GAME START and UP restores it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
