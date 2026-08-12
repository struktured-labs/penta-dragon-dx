#!/usr/bin/env python3
"""Retain native screenshots for every release-safe stream scene preset."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
LUA = ROOT / "scripts/lua/live_palettes.lua"
SCENES = (
    "title", "opening", "opening_book", "opening_sara",
    "opening_dragon_eye", "pre_final_story", "pre_final_sara",
    "post_final_story", "post_final_lisa", "post_final_sara",
    "ending_credits", "ending_end", "ending_epilogue",
    "stage2", "stage3", "stage4", "stage5", "stage6", "stage7",
    "boss_shalamar", "boss_riff", "boss_crystal_dragon", "boss_cameo",
    "boss_ted", "boss_troop", "boss_faze", "boss_angela",
    "boss_penta_dragon", "witch", "dragon", "crow", "hornets", "orc",
    "soldier", "mage", "mixed", "gargoyle", "spider", "spiral",
    "shield", "jet", "menu",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_fields(line: str) -> dict[str, str]:
    return dict(field.split("=", 1) for field in line.split() if "=" in field)


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage-states", type=Path, required=True)
    parser.add_argument("--boss-states", type=Path, required=True)
    parser.add_argument("--story-states", type=Path, required=True)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    state_dirs = {
        "stage": args.stage_states.resolve(),
        "boss": args.boss_states.resolve(),
        "story": args.story_states.resolve(),
    }
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    for name, directory in state_dirs.items():
        if not directory.is_dir():
            parser.error(f"{name} state directory not found: {directory}")

    output.mkdir(parents=True, exist_ok=True)
    audit = output / "scene-audit.txt"
    owned = [
        audit,
        Path(f"{audit}.done"),
        output / "live-palettes.txt",
        output / "live-palettes.log",
        output / "manifest.json",
    ] + [Path(f"{audit}.{scene}.png") for scene in SCENES]
    for path in owned:
        path.unlink(missing_ok=True)
    live_file = output / "live-palettes.txt"
    live_file.write_text("# deterministic scene-deck capture; no overrides\n")

    env = os.environ.copy()
    env.update(
        LIVE_PALETTE_FILE=str(live_file),
        LIVE_PALETTE_LOG=str(output / "live-palettes.log"),
        LIVE_PALETTE_SCENE_AUDIT_OUT=str(audit),
        LIVE_PALETTE_STAGE_STATE_DIR=str(state_dirs["stage"]),
        LIVE_PALETTE_BOSS_STATE_DIR=str(state_dirs["boss"]),
        LIVE_PALETTE_STORY_STATE_DIR=str(state_dirs["story"]),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [str(args.mgba), "--fastforward", str(rom), "--script", str(LUA)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    done = Path(f"{audit}.done")
    deadline = time.monotonic() + args.timeout
    try:
        while time.monotonic() < deadline:
            if done.is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        terminate(process)

    rows = []
    if audit.is_file():
        rows = [
            parse_fields(line)
            for line in audit.read_text().splitlines()[1:]
            if line.strip()
        ]
    by_scene = {row.get("scene", ""): row for row in rows}
    failures = []
    for scene in SCENES:
        row = by_scene.get(scene)
        screenshot = Path(f"{audit}.{scene}.png")
        if row is None:
            failures.append(f"{scene}: missing audit row")
        elif row.get("ok") != "true":
            failures.append(f"{scene}: state load failed")
        if not screenshot.is_file() or screenshot.stat().st_size <= 100:
            failures.append(f"{scene}: screenshot missing")
    if not done.is_file() or done.read_text().strip() != "ok":
        failures.append("scene deck did not publish its completion marker")

    manifest = {
        "status": "pass" if not failures else "fail",
        "rom": str(rom),
        "rom_sha256": sha256(rom),
        "scene_count": len(SCENES),
        "captured_count": sum(
            Path(f"{audit}.{scene}.png").is_file() for scene in SCENES
        ),
        "state_directories": {key: str(value) for key, value in state_dirs.items()},
        "scenes": [
            {
                "name": scene,
                "fields": by_scene.get(scene),
                "screenshot": f"scene-audit.txt.{scene}.png",
            }
            for scene in SCENES
        ],
        "failures": failures,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print(f"PASS: retained {len(SCENES)}/{len(SCENES)} stream-scene frames.")
    print(f"Manifest: {output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
