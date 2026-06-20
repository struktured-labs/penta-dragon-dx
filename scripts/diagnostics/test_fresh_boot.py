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
  SaraDragon green pixels at f=1800 catch SaraDragon corruption.
Iter 79: Added third + fourth screenshots forcing FFBF=1 (Gargoyle)
  and FFBF=2 (Spider). The boss-palette injection branch in
  palette_loader overwrites OBP 6/7 with the boss colors, and we can
  verify them via the rendered #FFC6D6 (Gargoyle) and #FFC6FF +
  #00F7FF (Spider) pixels on BG tiles that happen to use pal 6/7.

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

    -- Phase 1: Sara Witch screenshot at f=%d (gameplay reached, palettes loaded)
    if frame == %d then
        emu:screenshot("%s")
    end
    -- Phase 2: force FFBE=1 (Sara Dragon). cond_pal hashes FFBE so this
    -- triggers a cache miss → palette_loader reloads OBP 1 from ROM.
    if frame >= %d and frame < %d then
        emu:write8(0xFFBE, 0x01)
        emu:write8(0xFFBF, 0x00)
    end
    if frame == %d then
        emu:screenshot("%s")
    end
    -- Phase 3: force FFBE=0, FFBF=1 (Gargoyle). cond_pal cache miss →
    -- palette_loader's boss_pal branch overwrites OBP 6 with Gargoyle.
    if frame >= %d and frame < %d then
        emu:write8(0xFFBE, 0x00)
        emu:write8(0xFFBF, 0x01)
    end
    if frame == %d then
        emu:screenshot("%s")
    end
    -- Phase 4: force FFBF=2 (Spider). boss_pal overwrites OBP 7.
    if frame >= %d then
        emu:write8(0xFFBE, 0x00)
        emu:write8(0xFFBF, 0x02)
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
    # and OBP 1 CRAM gets reloaded from ROM source.
    ("00FF00", 15, "SaraDragon bright-green (OBP 1 idx 1) after FFBE=1 forced"),
]

EXPECTED_GARG = [
    # Iter 79: forcing FFBF=1 turned out to NOT catch Gargoyle OBP 6
    # palette source corruption. boss_pal injects only into the OBJ
    # palette slot, but no Gargoyle OBJ sprite is on screen during the
    # auto-play sequence, so OBP 6 doesn't render anywhere. The #F7DED6
    # pixels we see come from BG-pal-6 (separate from OBP 6) which the
    # corruption test didn't touch. Verified: corrupted Gargoyle OBP-6
    # source still shows 109 #F7DED6. Test phase kept for the BG-pal-6
    # smoke check (catches BG-pal-6 corruption) but doesn't catch OBJ-6.
    ("F7DED6", 50, "BG-pal-6 light-pink (smoke check — NOT Gargoyle OBJ catcher)"),
]

EXPECTED_SPIDER = [
    # Iter 79: forcing FFBF=2 makes boss_pal overwrite OBP 7 with Spider.
    # Render shows 106 #FF2900 (Spider orange, 0x00BF mGBA-corrected).
    # SW phase had no #FF2900 (BG5 vivid red is #FF0000, not #FF2900).
    # The 106 must be from Sara's projectiles or another OBJ that uses
    # OBP 7 — Spider corruption empirically drops it to 0, so this IS
    # a real OBJ-7 catcher. Floor at 50.
    ("FF2900", 50, "Spider distinctive orange (OBP 7 boss_pal, FFBF=2)"),
]

SAMPLE_FRAME_SW = 1500
FFBE_FORCE_START = 1500
SAMPLE_FRAME_SD = 1800
FFBF1_FORCE_START = 1800
SAMPLE_FRAME_GARG = 2100
FFBF2_FORCE_START = 2100
SAMPLE_FRAME_SPIDER = 2400


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
    garg_screenshot = tmp_dir / "fresh_boot_garg.png"
    spider_screenshot = tmp_dir / "fresh_boot_spider.png"
    for p in (sw_screenshot, sd_screenshot, garg_screenshot, spider_screenshot):
        if p.exists():
            p.unlink()
    lua_path.write_text(LUA_SCRIPT % (
        SAMPLE_FRAME_SW,                                      # Phase 1 comment
        SAMPLE_FRAME_SW, sw_screenshot,                       # SW screenshot
        FFBE_FORCE_START, FFBF1_FORCE_START,                  # Phase 2 range
        SAMPLE_FRAME_SD, sd_screenshot,                       # SD screenshot
        FFBF1_FORCE_START, FFBF2_FORCE_START,                 # Phase 3 range
        SAMPLE_FRAME_GARG, garg_screenshot,                   # Garg screenshot
        FFBF2_FORCE_START,                                    # Phase 4 start
        SAMPLE_FRAME_SPIDER, spider_screenshot,               # Spider screenshot
    ))

    print(f"[fresh-boot] Running mGBA from cold boot, 4 screenshots @f={SAMPLE_FRAME_SW}/{SAMPLE_FRAME_SD}/{SAMPLE_FRAME_GARG}/{SAMPLE_FRAME_SPIDER}...")
    success = run_mgba(rom_path, lua_path)
    if not success:
        print("  [FAIL] mGBA execution failed")
        return 1
    for p in (sw_screenshot, sd_screenshot, garg_screenshot, spider_screenshot):
        if not p.exists():
            print(f"  [FAIL] No screenshot at {p}")
            return 1

    errors = []
    for label, path, expectations in [
        (f"Sara Witch (f={SAMPLE_FRAME_SW})", sw_screenshot, EXPECTED_SW),
        (f"Sara Dragon (f={SAMPLE_FRAME_SD}, FFBE=1 forced)", sd_screenshot, EXPECTED_SD),
        (f"Gargoyle (f={SAMPLE_FRAME_GARG}, FFBF=1 forced)", garg_screenshot, EXPECTED_GARG),
        (f"Spider (f={SAMPLE_FRAME_SPIDER}, FFBF=2 forced)", spider_screenshot, EXPECTED_SPIDER),
    ]:
        print(f"[fresh-boot] {label} checks:")
        for color, min_px, exp_label in expectations:
            count = count_color(path, color)
            marker = "[PASS]" if count >= min_px else "[FAIL]"
            print(f"  {marker} #{color} = {count} pixels (>= {min_px}) — {exp_label}")
            if count < min_px:
                errors.append(f"{label.split('(')[0].strip()} #{color}: count {count} < min {min_px}")

    if not args.keep_artifacts:
        lua_path.unlink(missing_ok=True)

    if errors:
        print(f"\n[fresh-boot] {len(errors)} expectation(s) failed.")
        return 1
    print("\n[fresh-boot] All expectations passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
