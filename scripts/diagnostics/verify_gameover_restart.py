#!/usr/bin/env python3
"""Exercise two Game Over/title/new-game cycles through guarded mGBA.

HP=0 accelerates loss of each life; all transitions and initialization remain
game-owned. This is emulator regression evidence, not a MiSTer hardware pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, ImageChops
from restart_terrain import compare_terrain_captures

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_gameover_restart.lua")
GUARD = ROOT / "scripts/mgba-qt-singleflight"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_images(before: Path, after: Path, region: tuple[int, int, int, int]) -> None:
    with Image.open(before) as a, Image.open(after) as b:
        if a.size != (160, 144) or b.size != a.size:
            raise ValueError("capture must be an unscaled 160x144 native frame")
        # Compare the same settled phase. Any change needs investigation;
        # never bless a damaged but still colourful screen by colour count.
        if ImageChops.difference(a.convert("RGB").crop(region),
                                 b.convert("RGB").crop(region)).getbbox():
            raise ValueError(f"rendering changed: {before.name} -> {after.name}")


def validate_stage_cards(output: Path, saved_game: bool = True) -> None:
    """Issue #9: require both card variants, excluding variable score text."""
    for label in (("stage-selector", "stage-card") if saved_game else ("stage-card",)):
        for suffix in ("before", "after-1", "after-2"):
            path = output / f"{label}-{suffix}.png"
            with Image.open(path) as image:
                if len(set(image.convert("RGB").crop((0, 0, 160, 72)).getdata())) < 2:
                    raise ValueError(f"blank stage screen is not evidence: {path.name}")
        for cycle in (1, 2):
            compare_images(output / f"{label}-before.png",
                           output / f"{label}-after-{cycle}.png", (0, 0, 160, 72))
            if label == "stage-selector":
                # Score digits may vary; the surrounding labels must not.
                for region in ((0, 72, 64, 144), (104, 72, 160, 144)):
                    compare_images(output / f"{label}-before.png",
                                   output / f"{label}-after-{cycle}.png", region)


def check_ceiling(frame: Path, background: Path, mask: Path) -> None:
    """Detect sprite pixels leaking into a reviewed opaque ceiling mask.

    The mask must describe an actual solid ceiling at a fixed room/camera,
    never the entire top edge. Collision penetration requires a separate
    world-position trace; this assertion covers visual priority only.
    """
    with Image.open(frame) as a, Image.open(background) as b, Image.open(mask) as m:
        if a.size != (160, 144) or b.size != a.size or m.size != a.size:
            raise ValueError("ceiling captures/mask must be native 160x144")
        m = m.convert("L")
        if not m.getbbox():
            raise ValueError("empty ceiling mask is not evidence")
        delta = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
        if Image.composite(delta, Image.new("RGB", a.size), m).getbbox():
            raise ValueError("sprite/rendering leaked into solid ceiling")


def validate(output: Path, traverse: bool = False) -> None:
    route = (output / "route.txt").read_text().split()
    if len(route) != 4 or route[0] != "ok" or int(route[1]) != 2 or int(route[3]) < 2:
        raise ValueError("two complete Game Over -> title -> new-game cycles required")
    if int(route[2]) < 2:
        raise ValueError("no verified death stimulus for both cycles")
    # Known native GAME OVER window from the existing death verifier.
    from verify_death_gameover import GAMEOVER_RGB_SHA256
    for i in range(1, int(route[3]) + 1):
        with Image.open(output / f"gameover-{i}.png") as image:
            if image.size != (160, 144) or hashlib.sha256(image.convert("RGB").tobytes()).hexdigest() != GAMEOVER_RGB_SHA256:
                raise ValueError(f"Game Over rendering corrupted in capture {i}")
    for i in (1, 2):
        labels = ("title", "stage") + (("travel-0668", "travel-05AC", "travel-03A4") if traverse else ())
        for label in labels:
            a, b = output / f"{label}-before", output / f"{label}-after-{i}"
            ac = a.with_suffix(".context").read_text().strip().split(":")
            bc = b.with_suffix(".context").read_text().strip().split(":")
            # Title legitimately retains the prior gameplay-active/room bytes.
            # Compare only its scene and camera, not inactive gameplay state.
            indices = (0, 2, 3) if label == "title" else (0, 1, 2, 3, 4)
            if len(ac) != 5 or len(bc) != 5 or any(ac[k] != bc[k] for k in indices):
                raise ValueError(f"{label}: room/camera context changed on cycle {i}")
            # Exclude title cursor and gameplay HUD/enemy band; the remaining
            # image still includes the level floor/walls and their colours.
            roi = (40, 8, 152, 64) if label == "title" else (0, 32, 160, 128)
            if label != "title":
                compare_terrain_captures(a, b)
            else:
                compare_images(a.with_suffix(".png"), b.with_suffix(".png"), roi)
            if label == "title":
                compare_images(a.with_suffix(".png"), b.with_suffix(".png"), (0, 112, 160, 144))
            for plane in (("chr", "room") if label != "title" else ("chr",)):
                expected_size = 2048 if plane == "chr" else 576
                expected = a.with_suffix("." + plane).read_bytes()
                actual = b.with_suffix("." + plane).read_bytes()
                if len(expected) != expected_size or len(set(expected)) < 2 or actual != expected:
                    raise ValueError(f"{label} {plane} lost or changed on cycle {i}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--traverse", action="store_true",
                        help="repeat upward movement/fire with three settled room/camera-matched checkpoints")
    parser.add_argument("--sequence", action="store_true",
                        help="check consecutive Game Over and returned-title frames, not only settled snapshots")
    parser.add_argument("--natural-damage", action="store_true",
                        help="die from game-owned damage using movement only, without HP writes")
    parser.add_argument("--hazard-death", action="store_true",
                        help="walk into rotating hazard tiles before the accelerated HP-zero death")
    parser.add_argument("--saved-game", action="store_true",
                        help="set native save-present flag before each start to test score/level selector too")
    parser.add_argument("--wait-disarm", action="store_true",
                        help="diagnostic: wait for native FF91 disarming before accelerated death")
    args = parser.parse_args()
    if args.hazard_death and (args.traverse or args.natural_damage):
        parser.error("hazard-death is a separate route; do not combine with traverse or natural-damage")
    if args.wait_disarm and not args.hazard_death:
        parser.error("wait-disarm requires hazard-death")
    rom, output = args.rom.resolve(strict=True), args.output.resolve()
    if not (ROOT / "tmp").resolve() in output.parents:
        parser.error("output must be a fresh directory beneath repository tmp/")
    output.mkdir(parents=True, exist_ok=False)
    identity = sha(rom)
    runtime = output / "runtime"
    runtime.mkdir()
    tested_rom = runtime / "candidate.gb"
    shutil.copy2(rom, tested_rom)
    environment = os.environ.copy()
    environment.pop("PENTA_MGBA_QT_BIN", None)
    environment.update(QT_QPA_PLATFORM="offscreen", SDL_AUDIODRIVER="dummy",
                       PENTA_RESTART_OUT=str(output),
                       PENTA_RESTART_TRAVERSE="1" if args.traverse else "0",
                       PENTA_RESTART_SEQUENCE="1" if args.sequence else "0",
                       PENTA_RESTART_HAZARD_DEATH="1" if args.hazard_death else "0",
                       PENTA_RESTART_SAVED_GAME="1" if args.saved_game else "0",
                       PENTA_RESTART_WAIT_DISARM="1" if args.wait_disarm else "0",
                       PENTA_RESTART_NATURAL_DAMAGE="1" if args.natural_damage else "0")
    receipt = {"schema": "penta-gameover-restart-v1", "rom_sha256": identity,
               "probe_sha256": sha(PROBE), "verifier_sha256": sha(Path(__file__)),
               "scope": "emulator", "status": "failed",
               "stimulus": ("movement-only native damage" if args.natural_damage else
                            "hazard-area movement followed by HP=0 once per life" if args.hazard_death else
                            "HP=0 once per life")}
    receipt["traverse"] = args.traverse
    receipt["sequence"] = args.sequence
    receipt["hazard_death"] = args.hazard_death
    receipt["saved_game_fixture"] = args.saved_game
    receipt["tested_rom"] = str(tested_rom)
    receipt["blank_sram_at_launch"] = True
    receipt["wait_disarm"] = args.wait_disarm
    receipt["hazard_walk_frames"] = int(environment.get("PENTA_RESTART_SPIKE_WALK", "1600"))
    if args.sequence:
        receipt["sequence_oracle_sha256"] = sha(Path(__file__).with_name('gameover_sequence.py'))
    receipt["terrain_oracle_sha256"] = sha(Path(__file__).with_name('restart_terrain.py'))
    result_code = 1
    try:
        with (output / "emulator.log").open("w") as log:
            result = subprocess.run([str(GUARD), "--fastforward", "--script", str(PROBE), str(tested_rom)],
                                    cwd=ROOT, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=args.timeout)
        if result.returncode == 75:
            result_code = 75
            raise ValueError("emulator slot occupied; no retry or lock bypass")
        if result.returncode:
            raise ValueError(f"route failed: exit {result.returncode}; inspect emulator.log and trace.tsv")
        if sha(rom) != identity or sha(tested_rom) != identity:
            raise ValueError("ROM changed during test")
        validate(output, args.traverse)
        if args.hazard_death or args.saved_game:
            validate_stage_cards(output, args.saved_game)
        if args.sequence:
            from gameover_sequence import validate_sequence
            receipt["sequence_checks"] = validate_sequence(output)
        receipt["status"] = "pass"
        result_code = 0
    except subprocess.TimeoutExpired:
        receipt["error"] = "route timed out"
        subprocess.run([str(ROOT / "scripts/check_emulator_processes.sh")], check=False)
    except (ValueError, OSError) as exc:
        receipt["error"] = str(exc)
    receipt["artifacts"] = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({k: v for k, v in receipt.items() if k != 'artifacts'}, indent=2))
    return result_code


if __name__ == "__main__":
    sys.exit(main())
