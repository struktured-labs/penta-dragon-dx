#!/usr/bin/env python3
"""Inventory scene bytes in every checked-in mGBA savestate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_savestate_scene.lua"


def inspect(mgba: str, rom: Path, state: Path, report: Path,
            timeout: float) -> dict[str, int]:
    report.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STATE_SCENE_OUT": str(report),
    })
    proc = subprocess.Popen(
        [mgba, "-t", str(state), "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if report.exists() and report.stat().st_size:
                return {
                    key: int(value, 16)
                    for key, value in re.findall(
                        r"([A-F0-9]{4})=([A-F0-9]{2})", report.read_text()
                    )
                }
            if proc.poll() is not None:
                break
            time.sleep(0.02)
        raise RuntimeError("no report")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--states", type=Path, default=ROOT / "rom")
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-headless-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()

    states = sorted(args.states.resolve().rglob("*.ss?"))
    if not states:
        print("No savestates found.")
        return 1

    ending = []
    failures = []
    with tempfile.TemporaryDirectory(prefix="penta-state-scenes-") as directory:
        report = Path(directory) / "scene.txt"
        for state in states:
            sibling_rom = state.with_suffix(".gb")
            state_rom = sibling_rom if sibling_rom.exists() else args.rom.resolve()
            try:
                values = inspect(
                    args.mgba, state_rom, state, report, args.timeout
                )
            except Exception as exc:
                failures.append(f"{state}: {exc}")
                continue
            relative = state.relative_to(ROOT)
            print(
                f"{relative}: D880={values['D880']:02X} "
                f"FFC1={values['FFC1']} FFBA={values['FFBA']:02X} "
                f"FFBF={values['FFBF']:02X} FFC0={values['FFC0']:02X} "
                f"FFD0={values['FFD0']:02X} FFE4={values['FFE4']:02X} "
                f"DD09={values['DD09']:02X} "
                f"LCDC={values['FF40']:02X} SCY={values['FF42']:02X} "
                f"SCX={values['FF43']:02X} VBK={values['FF4F']:02X} "
                f"rom={state_rom.name}"
            )
            # FFE4 is also used by death/transition paths, so it is not an
            # ending signal by itself. The ending's ambiguous final graphic is
            # specifically D880=00 + FFE4=1 + non-gameplay FFC1=0.
            if (
                values["D880"] in {0x19, 0x1A, 0x16}
                or (
                    values["D880"] == 0
                    and values["FFE4"] == 1
                    and values["FFC1"] == 0
                )
            ):
                ending.append((state, values))

    print(f"\nInspected {len(states) - len(failures)}/{len(states)} savestates.")
    if ending:
        print("Potential ending anchors:")
        for state, values in ending:
            print(
                f"  {state.relative_to(ROOT)} "
                f"(D880={values['D880']:02X}, FFE4={values['FFE4']:02X})"
            )
    else:
        print(
            "No ending-state anchor found "
            "(D880 19/1A/16, or D880=00 + FFE4=1 + FFC1=0)."
        )
    if failures:
        print("Unreadable states:")
        for failure in failures:
            print(f"  {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
