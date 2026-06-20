#!/usr/bin/env python3
"""Fresh-boot end-to-end test.

Unlike the YAML-driven savestate tests, this loads the ROM from cold-
boot, presses the title-menu input sequence, and samples the rendered
screen at two distinct moments — first as Sara Witch in the default
gameplay state, then after forcing FFBE=1 to transform her to Dragon
form so the cond_pal cache miss reloads OBP 1 from ROM source. Catches
ROM-source palette corruptions that the savestate tests miss because
savestate CRAM persists through their test sample window (see
project_adversarial_coverage.md iter 70/73/74).

Iter 75: First version, single screenshot at f=1500, caught SaraWitch
  corruption (2 OBP-2 colors).
Iter 76: Added 4 BG palette guards (Dungeon, BG1, BG5) from the same
  screenshot.
Iter 78: Added second screenshot at f=1800 with FFBE forced to 1
  (Sara Dragon). The form change forces a cond_pal cache miss, so
  palette_loader reloads OBP 1 from ROM source — and the rendered
  SaraDragon green pixels at f=1800 catch SaraDragon corruption
  (which iter 70-74 could not catch via any savestate-based test).

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
    -- Sara Witch screenshot at f=1500 (gameplay reached, palettes loaded)
    if frame == %d then
        emu:screenshot("%s")
    end
    -- After SW screenshot, force Sara to Dragon form. The FFBE change
    -- causes cond_pal's hash to mismatch the DF00 cache, so palette_
    -- loader reloads — overwriting OBP 1 CRAM from the ROM source.
    if frame >= %d then
        emu:write8(0xFFBE, 0x01)
    end
    if frame == %d then
        emu:screenshot("%s")
        emu:stop()
    end
end)
"""

EXPECTED_SW = [
    # Sara W OBJ — catches SaraWitch (OBP 2) palette source corruption
    ("FF42A5", 15, "SaraWitch pink-red (OBP 2 idx 1)"),
    ("F7AD5A", 15, "SaraWitch peach (OBP 2 idx 2)"),
    # BG palettes — iter 76 found these are stable at f=1500 fresh-boot
    # and catch ROM-source corruption of the respective BG palette slots:
    ("A5A5FF", 5000, "Dungeon BG idx 1 light-lavender (catches BG-pal-0 corruption)"),
    ("52527B", 1500, "Dungeon BG idx 2 dark-blue (catches BG-pal-0 corruption)"),
    ("940000", 50, "BG1 cherry red (idx 1, catches items/font palette corruption)"),
    ("FF0000", 20, "BG5 vivid red (catches BG-pal-5 corruption)"),
]

EXPECTED_SD = [
    # Sara D OBJ — catches SaraDragon (OBP 1) palette source corruption.
    # Forcing FFBE=1 triggers a cond_pal cache miss, palette_loader runs,
    # and OBP 1 CRAM gets reloaded from ROM source. Sara then renders
    # with the SaraDragon green (#00FF00 = 0x03E0 mGBA-corrected).
    ("00FF00", 15, "SaraDragon bright-green (OBP 1 idx 1) after FFBE=1 forced"),
]

SAMPLE_FRAME_SW = 1500
FFBE_FORCE_FRAME = 1500
SAMPLE_FRAME_SD = 1800


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
    sw_screenshot = tmp_dir / "fresh_boot.png"
    sd_screenshot = tmp_dir / "fresh_boot_sd.png"
    for p in (sw_screenshot, sd_screenshot):
        if p.exists():
            p.unlink()
    lua_path.write_text(LUA_SCRIPT % (
        SAMPLE_FRAME_SW, sw_screenshot,
        FFBE_FORCE_FRAME,
        SAMPLE_FRAME_SD, sd_screenshot,
    ))

    print(f"[fresh-boot] Running mGBA from cold boot, sampling SW@f={SAMPLE_FRAME_SW} + SD@f={SAMPLE_FRAME_SD}...")
    success = run_mgba(rom_path, lua_path)
    if not success:
        print("  [FAIL] mGBA execution failed")
        return 1
    for p in (sw_screenshot, sd_screenshot):
        if not p.exists():
            print(f"  [FAIL] No screenshot at {p}")
            return 1

    errors = []
    print("[fresh-boot] Sara Witch (f={}) checks:".format(SAMPLE_FRAME_SW))
    for color, min_px, label in EXPECTED_SW:
        count = count_color(sw_screenshot, color)
        marker = "[PASS]" if count >= min_px else "[FAIL]"
        print(f"  {marker} #{color} = {count} pixels (>= {min_px}) — {label}")
        if count < min_px:
            errors.append(f"SW #{color}: count {count} < min {min_px}")
    print("[fresh-boot] Sara Dragon (f={}, FFBE=1 forced) checks:".format(SAMPLE_FRAME_SD))
    for color, min_px, label in EXPECTED_SD:
        count = count_color(sd_screenshot, color)
        marker = "[PASS]" if count >= min_px else "[FAIL]"
        print(f"  {marker} #{color} = {count} pixels (>= {min_px}) — {label}")
        if count < min_px:
            errors.append(f"SD #{color}: count {count} < min {min_px}")

    if not args.keep_artifacts:
        lua_path.unlink(missing_ok=True)

    if errors:
        print(f"\n[fresh-boot] {len(errors)} expectation(s) failed.")
        return 1
    print("\n[fresh-boot] All expectations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
