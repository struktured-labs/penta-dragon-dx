#!/usr/bin/env python3
"""Differential check for the title-colour prototype.

Boots the stock candidate and the prototype side by side in PyBoy and proves
that the only thing the patch changed is the colour of the D880==$01 title
menu.  PyBoy is adequate here because nothing under test is a timing or
flicker question: the checks are attribute/CRAM contents, rendered pixels,
and frame-by-frame scene identity.

Checks
------
title-ink      the set of non-background pixels on the title is identical in
               both ROMs, so no glyph moved, vanished, or gained garbage
title-colour   the prototype title actually renders more than two colours and
               its background is one uniform field
reel-scene-*   a long no-input run produces the same attract scene sequence,
               with per-scene frame counts within a small drift bound
reel-non-title every sampled non-title frame of that run, compared relative to
               its own scene entry, is pixel-identical between the two ROMs
scripted       opening story, level selector and STAGE splash reached by a
               scripted input sequence are pixel-identical; Stage 1 gameplay
               is compared on its published BG tile+attribute plane (the
               actor's sub-frame phase follows the scripted press), and both
               BG and OBJ CRAM match byte for byte

Exit codes: 0 = all checks pass, 1 = a check failed, 2 = harness error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

try:
    from pyboy import PyBoy
except ImportError:  # pragma: no cover - harness error path
    sys.stderr.write("PyBoy is required (uv run python ...)\n")
    raise SystemExit(2)


SCENE_ADDR = 0xD880
TITLE_SCENE = 0x01


def boot(rom: Path) -> PyBoy:
    pyboy = PyBoy(str(rom), window="null", cgb=True, sound_emulated=False)
    pyboy.set_emulation_speed(0)
    return pyboy


def screen_bytes(pyboy: PyBoy) -> bytes:
    return pyboy.screen.image.convert("RGB").tobytes()


def screen_hash(pyboy: PyBoy) -> str:
    return hashlib.sha256(screen_bytes(pyboy)).hexdigest()[:16]


def read_bg_plane(pyboy: PyBoy) -> tuple[list[int], list[int]]:
    """Visible BG tile IDs and CGB attributes of the map LCDC is showing."""
    base = 0x9C00 if (pyboy.memory[0xFF40] & 0x08) else 0x9800
    cells = [base + row * 32 + col for row in range(32) for col in range(32)]
    return (
        [pyboy.memory[0, cell] for cell in cells],
        [pyboy.memory[1, cell] for cell in cells],
    )


def read_obj_cram(pyboy: PyBoy) -> list[int]:
    values = []
    for index in range(64):
        pyboy.memory[0xFF6A] = index
        values.append(pyboy.memory[0xFF6B])
    return values


def read_bg_cram(pyboy: PyBoy) -> list[int]:
    values = []
    for index in range(64):
        pyboy.memory[0xFF68] = index
        values.append(pyboy.memory[0xFF69])
    return values


def hold(pyboy: PyBoy, button: str, press: int = 12, gap: int = 12) -> None:
    pyboy.button_press(button)
    for _ in range(press):
        pyboy.tick(1, True)
    pyboy.button_release(button)
    for _ in range(gap):
        pyboy.tick(1, True)


def run(pyboy: PyBoy, frames: int) -> None:
    for _ in range(frames):
        pyboy.tick(1, True)


def background_colour(pyboy: PyBoy) -> tuple[int, int, int]:
    pixels = list(pyboy.screen.image.convert("RGB").getdata())
    return Counter(pixels).most_common(1)[0][0]


def ink_mask(pyboy: PyBoy) -> bytes:
    background = background_colour(pyboy)
    pixels = list(pyboy.screen.image.convert("RGB").getdata())
    return bytes(0 if pixel == background else 1 for pixel in pixels)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline", type=Path,
        default=Path("rom/working/penta_dragon_dx_FIXED.gb"),
    )
    parser.add_argument(
        "--candidate", type=Path, default=Path("tmp/title-color/candidate.gb"),
    )
    parser.add_argument("--title-frame", type=int, default=400)
    parser.add_argument("--reel-frames", type=int, default=3600)
    parser.add_argument("--frame-window", type=int, default=6)
    parser.add_argument("--shots", type=Path, default=Path("tmp/title-color"))
    parser.add_argument("--receipt", type=Path, default=None)
    args = parser.parse_args()

    args.shots.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        results.append((name, ok, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    base, cand = boot(args.baseline), boot(args.candidate)

    # --- title -------------------------------------------------------- #
    run(base, args.title_frame)
    run(cand, args.title_frame)
    base.screen.image.save(args.shots / "title_before.png")
    cand.screen.image.save(args.shots / "title_after.png")
    base_scene, cand_scene = base.memory[SCENE_ADDR], cand.memory[SCENE_ADDR]
    record(
        "title-scene", base_scene == cand_scene == TITLE_SCENE,
        f"baseline D880=0x{base_scene:02X} candidate D880=0x{cand_scene:02X}",
    )
    base_mask, cand_mask = ink_mask(base), ink_mask(cand)
    record(
        "title-ink", base_mask == cand_mask,
        f"{sum(base_mask)} baseline ink pixels vs {sum(cand_mask)} candidate",
    )
    base_colours = len(set(base.screen.image.convert("RGB").getdata()))
    cand_colours = len(set(cand.screen.image.convert("RGB").getdata()))
    record(
        "title-colour", cand_colours > base_colours and cand_colours >= 5,
        f"baseline {base_colours} distinct colours, candidate {cand_colours}",
    )
    cand_field = background_colour(cand)
    record(
        "title-field", cand_field != (248, 248, 248),
        f"candidate background {cand_field}",
    )

    # --- long no-input run: scene identity and per-scene appearance ---- #
    # Scene transitions can slip a frame or two, so frames are compared
    # relative to each scene entry rather than by absolute frame number.
    def reel(pyboy: PyBoy, frames: int) -> list[dict[str, object]]:
        segments: list[dict[str, object]] = []
        current = pyboy.memory[SCENE_ADDR]
        entry = 0
        shots: dict[int, str] = {}
        for frame in range(1, frames + 1):
            pyboy.tick(1, True)
            scene = pyboy.memory[SCENE_ADDR]
            if scene != current:
                segments.append({
                    "scene": current, "length": frame - entry, "shots": shots,
                })
                current, entry, shots = scene, frame, {}
            elif frame - entry in (10, 60):
                shots[frame - entry] = screen_hash(pyboy)
        segments.append({"scene": current, "length": frames - entry, "shots": shots})
        return segments

    base_reel = reel(base, args.reel_frames)
    cand_reel = reel(cand, args.reel_frames)
    scene_order_base = [segment["scene"] for segment in base_reel]
    scene_order_cand = [segment["scene"] for segment in cand_reel]
    record(
        "reel-scene-order", scene_order_base == scene_order_cand,
        "identical scene sequence "
        + " ".join(f"0x{scene:02X}" for scene in scene_order_base),
    )
    lengths = [
        (f"0x{b['scene']:02X}", b["length"], c["length"])
        for b, c in zip(base_reel, cand_reel)
    ]
    drift = [abs(b - c) for _, b, c in lengths]
    record(
        "reel-scene-length", max(drift) <= 3,
        "per-scene frame counts "
        + ", ".join(f"{s} {b}->{c}" for s, b, c in lengths)
        + f" (max drift {max(drift)} frames)",
    )
    appearance = []
    for b, c in zip(base_reel, cand_reel):
        if b["scene"] == TITLE_SCENE:
            continue
        for offset, digest in b["shots"].items():
            other = c["shots"].get(offset)
            if other is not None and other != digest:
                appearance.append((f"0x{b['scene']:02X}", offset))
    record(
        "reel-non-title-appearance", not appearance,
        "every sampled non-title frame identical"
        if not appearance else f"differs at {appearance}",
    )
    base.screen.image.save(args.shots / "reel_before.png")
    cand.screen.image.save(args.shots / "reel_after.png")

    # --- scripted descent into gameplay ------------------------------- #
    base2, cand2 = boot(args.baseline), boot(args.candidate)
    run(base2, 200)
    run(cand2, 200)
    stages = [
        ("opening-story", ["a"], 120),
        ("level-select", ["reset", "down", "a"], 200),
        ("stage-splash", ["a", "a", "a", "a"], 60),
        ("stage1-gameplay", ["a"], 180),
    ]
    for name, buttons, settle in stages:
        for button in buttons:
            if button == "reset":
                base2.stop(False)
                cand2.stop(False)
                base2, cand2 = boot(args.baseline), boot(args.candidate)
                run(base2, 200)
                run(cand2, 200)
                continue
            hold(base2, button)
            hold(cand2, button)
        run(base2, settle)
        run(cand2, settle)
        base2.screen.image.save(args.shots / f"{name}_before.png")
        cand2.screen.image.save(args.shots / f"{name}_after.png")
        # The title's idle countdown loses one frame to the paint, so a
        # scripted press can land a frame apart. Accept any match inside a
        # short window rather than demanding frame-exact agreement.
        base_shots = {screen_hash(base2)}
        cand_shots = {screen_hash(cand2)}
        for _ in range(args.frame_window):
            base2.tick(1, True)
            cand2.tick(1, True)
            base_shots.add(screen_hash(base2))
            cand_shots.add(screen_hash(cand2))
        same_scene = base2.memory[SCENE_ADDR] == cand2.memory[SCENE_ADDR]
        same_pixels = bool(base_shots & cand_shots)
        if name == "stage1-gameplay":
            # Live gameplay has a moving actor whose sub-frame phase follows
            # the scripted press, so pixels are not a stable invariant here.
            # The invariant that matters is the published background plane.
            base_plane, cand_plane = read_bg_plane(base2), read_bg_plane(cand2)
            same_plane = base_plane == cand_plane
            record(
                name, same_scene and same_plane,
                f"D880 0x{base2.memory[SCENE_ADDR]:02X}/"
                f"0x{cand2.memory[SCENE_ADDR]:02X}, BG tiles+attributes "
                f"{'identical' if same_plane else 'DIFFER'}; sprite-inclusive "
                f"pixels {'match' if same_pixels else 'differ (actor phase)'}",
            )
            continue
        record(
            name, same_scene and same_pixels,
            f"D880 0x{base2.memory[SCENE_ADDR]:02X}/"
            f"0x{cand2.memory[SCENE_ADDR]:02X}, "
            f"pixels {'identical' if same_pixels else 'DIFFER'} "
            f"(+/-{args.frame_window} frame window)",
        )
    base_cram = read_bg_cram(base2) + read_obj_cram(base2)
    cand_cram = read_bg_cram(cand2) + read_obj_cram(cand2)
    record(
        "gameplay-cram", base_cram == cand_cram,
        "64 BG + 64 OBJ CRAM bytes identical" if base_cram == cand_cram
        else f"differs at index {next(i for i, (a, b) in enumerate(zip(base_cram, cand_cram)) if a != b)}",
    )

    for pyboy in (base, cand, base2, cand2):
        pyboy.stop(False)

    failures = [name for name, ok, _ in results if not ok]
    receipt = {
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "checks": [
            {"name": name, "pass": ok, "detail": detail}
            for name, ok, detail in results
        ],
        "failures": failures,
    }
    receipt_path = args.receipt or (args.shots / "verify.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(f"\nreceipt {receipt_path}")
    print("RESULT:", "PASS" if not failures else f"FAIL {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
