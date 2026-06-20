#!/usr/bin/env python3
"""Fresh-boot end-to-end test.

Unlike the YAML-driven savestate tests, this loads the ROM from cold-
boot, presses the title-menu input sequence, and samples Sara W's
rendered colors after she reaches gameplay. Catches ROM-source palette
corruptions that the savestate tests miss — savestate CRAM persists
through the test sample window so OBJ palette source corruptions don't
propagate (see project_adversarial_coverage.md iter 70/73/74).

Iter 75: Verified that this catches a SaraWitch ROM-source corruption
(0x4210 over both 0x2EBE and 0x511F at 0x36852-0x36856). Clean ROM
shows pink=26, peach=34 stably across 5 fresh runs. Corrupted ROM
shows pink=0, peach=0 at f=1500+.

Usage:
    uv run python scripts/diagnostics/test_fresh_boot.py [--rom PATH]
    Exit code 0 if all expectations pass, 1 otherwise.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROM_DEFAULT = REPO_ROOT / "rom/working/penta_dragon_dx_teleport.gb"

LUA_SCRIPT = r"""
-- Title-menu auto-input sequence (verified working — same one used by
-- scripts/verify_boot.lua).
local TITLE = {
    {180, 185, 0x80},  -- DOWN
    {193, 198, 0x01},  -- A
    {241, 246, 0x01},  -- A
    {291, 296, 0x01},  -- A
    {341, 346, 0x08},  -- START
    {391, 396, 0x01},  -- A
}

local frame = 0

callbacks:add("keysRead", function()
    local keys = 0
    for _, seq in ipairs(TITLE) do
        if frame >= seq[1] and frame <= seq[2] then
            keys = seq[3]
            break
        end
    end
    emu:setKeys(keys)
end)

callbacks:add("frame", function()
    frame = frame + 1
    if frame == %d then
        emu:screenshot("%s")
        emu:stop()
    end
end)
"""

EXPECTED = [
    # (color_hex, min_pixels, label)
    # Sara W OBJ (catches SaraWitch palette source corruption)
    ("FF42A5", 15, "SaraWitch pink-red (OBP 2 idx 1)"),
    ("F7AD5A", 15, "SaraWitch peach (OBP 2 idx 2)"),
    # BG palettes — iter 76 found these are stable at f=1500 fresh-boot
    # and catch ROM-source corruption of the respective BG palette slots:
    ("A5A5FF", 5000, "Dungeon BG idx 1 light-lavender (catches BG-pal-0 corruption)"),
    ("52527B", 1500, "Dungeon BG idx 2 dark-blue (catches BG-pal-0 corruption)"),
    ("940000", 50, "BG1 cherry red (idx 1, catches items/font palette corruption)"),
    ("FF0000", 20, "BG5 vivid red (catches BG-pal-5 corruption)"),
]
SAMPLE_FRAME = 1500


def run_mgba(rom_path: Path, lua_path: Path, timeout: int = 90) -> bool:
    cmd = [
        "timeout", str(timeout),
        "xvfb-run", "-a", "mgba-qt",
        str(rom_path),
        "--script", str(lua_path),
        "-l", "0",
    ]
    env = os.environ.copy()
    env["SDL_AUDIODRIVER"] = "dummy"
    env["QT_QPA_PLATFORM"] = "offscreen"
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout + 10, env=env)
        return result.returncode in (0, 124)
    except subprocess.TimeoutExpired:
        return True


def count_color(image_path: Path, target_hex: str) -> int:
    from PIL import Image
    target = (int(target_hex[0:2], 16), int(target_hex[2:4], 16), int(target_hex[4:6], 16))
    img = Image.open(image_path).convert("RGB")
    px = img.load()
    count = 0
    w, h = img.size
    for y in range(h):
        for x in range(w):
            if px[x, y] == target:
                count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom", default=str(ROM_DEFAULT), help="ROM path")
    parser.add_argument("--keep-artifacts", action="store_true")
    args = parser.parse_args()
    rom_path = Path(args.rom)
    if not rom_path.exists():
        print(f"[FAIL] ROM not found: {rom_path}")
        return 1

    tmp_dir = REPO_ROOT / "tests/results"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    lua_path = tmp_dir / "fresh_boot_test.lua"
    screenshot_path = tmp_dir / "fresh_boot.png"
    if screenshot_path.exists():
        screenshot_path.unlink()
    lua_path.write_text(LUA_SCRIPT % (SAMPLE_FRAME, screenshot_path))

    print(f"[fresh-boot] Running mGBA from cold boot, sampling at f={SAMPLE_FRAME}...")
    success = run_mgba(rom_path, lua_path)
    if not success:
        print("  [FAIL] mGBA execution failed")
        return 1
    if not screenshot_path.exists():
        print(f"  [FAIL] No screenshot at {screenshot_path}")
        return 1

    errors = []
    for color, min_px, label in EXPECTED:
        count = count_color(screenshot_path, color)
        marker = "[PASS]" if count >= min_px else "[FAIL]"
        print(f"  {marker} #{color} = {count} pixels (>= {min_px}) — {label}")
        if count < min_px:
            errors.append(f"#{color}: count {count} < min {min_px}")

    if not args.keep_artifacts:
        lua_path.unlink(missing_ok=True)

    if errors:
        print(f"\n[fresh-boot] {len(errors)} expectation(s) failed.")
        return 1
    print("\n[fresh-boot] All expectations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
