#!/usr/bin/env python3
"""Verify the item-menu HUD attrs and SELECT+START release safety."""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LUA_PROBE = Path(__file__).with_name("menu_hud_and_combo.lua")
BANK13 = 13 * 0x4000
PRELUDE_ROM_OFFSET = BANK13 + (0x6E80 - 0x4000)
PRELUDE_LIMIT = BANK13 + (0x6F30 - 0x4000)
TELEPORT_SIGNATURE = bytes.fromhex("F0 93 E6 0C FE 0C")
STACK_REDIRECT_SIGNATURE = bytes.fromhex("F8 16")


def parse_result(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    return result


def run_case(rom: Path, mode: str) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix=f"penta_{mode}_") as temp_dir:
        temp = Path(temp_dir)
        result_path = temp / "result.txt"
        screenshot_path = temp / "screen.png"
        env = os.environ.copy()
        env.update({
            "PROBE_MODE": mode,
            "PROBE_OUT": str(result_path),
            "PROBE_SCREENSHOT": str(screenshot_path),
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
        })
        command = [
            "xvfb-run", "-a", "mgba-qt", str(rom),
            "--script", str(LUA_PROBE), "-l", "0",
        ]
        try:
            subprocess.run(
                command, cwd=PROJECT_ROOT, env=env, capture_output=True,
                timeout=60, check=False,
            )
        except subprocess.TimeoutExpired:
            pass
        if not result_path.exists():
            raise RuntimeError(f"{mode} probe did not reach its result frame")
        return parse_result(result_path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    args = parser.parse_args()
    rom = args.rom.resolve()
    data = rom.read_bytes()

    prelude = data[PRELUDE_ROM_OFFSET:PRELUDE_LIMIT]
    static_failures = []
    if TELEPORT_SIGNATURE in prelude:
        static_failures.append("SELECT+START combo detector remains in prelude")
    if STACK_REDIRECT_SIGNATURE in prelude:
        static_failures.append("IRQ stack redirect remains in prelude")

    title = run_case(rom, "title")
    menu = run_case(rom, "menu")
    combo = run_case(rom, "combo")
    failures = list(static_failures)
    if title.get("reached") != "600":
        failures.append(f"title probe stopped at {title.get('reached')}")
    if title.get("contaminated_cells") != "0":
        failures.append(
            f"title has {title.get('contaminated_cells')} nonzero palette attrs"
        )
    if title.get("palette0") != "FF7F947E4A3D0000":
        failures.append(f"title palette 0 is {title.get('palette0')}")
    if menu.get("reached") != "1245":
        failures.append(f"menu probe stopped at {menu.get('reached')}")
    if menu.get("window_enabled") != "1":
        failures.append("item-menu window was not enabled")
    if menu.get("contaminated_cells") != "0":
        failures.append(
            f"HUD has {menu.get('contaminated_cells')} nonzero palette attrs"
        )
    if combo.get("reached") != "1300":
        failures.append(f"combo probe stopped at {combo.get('reached')}")
    if combo.get("ffba_before") != combo.get("ffba_after"):
        failures.append("SELECT+START changed the boss index")
    if combo.get("d880_before") != combo.get("d880_after"):
        failures.append("SELECT+START changed the scene state")
    if int(combo.get("shadow_states", "0")) < 2:
        failures.append("gameplay shadow OAM did not continue changing")

    print(f"ROM: {rom}")
    print(f"Title: {title}")
    print(f"Menu HUD: {menu}")
    print(f"SELECT+START: {combo}")
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)
    print("PASS: title/HUD attrs are clean and SELECT+START is release-safe.")


if __name__ == "__main__":
    main()
