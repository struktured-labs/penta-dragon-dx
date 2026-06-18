#!/usr/bin/env python3
"""
Color Regression Test Suite for Penta Dragon DX

Runs automated tests to verify sprite palette assignments are correct
across different game scenarios using save states.

Usage:
    uv run python scripts/run_color_regression.py
    uv run python scripts/run_color_regression.py --test gargoyle_miniboss
    uv run python scripts/run_color_regression.py --verbose
"""

import subprocess
import sys
import os
import yaml
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import argparse


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    screenshot: Optional[str] = None
    oam_data: Optional[list] = None


def create_test_lua_script(output_prefix: str, frames: int = 60,
                           force_d880: int | None = None,
                           force_dcfd: int | None = None,
                           force_ffba: int | None = None) -> str:
    """Generate Lua script for testing palette assignments + BG attrs."""
    force_block = ""
    if force_d880 is not None:
        force_block += f"        emu:write8(0xD880, 0x{force_d880:02X})\n"
    if force_dcfd is not None:
        force_block += f"        emu:write8(0xDCFD, 0x{force_dcfd:02X})\n"
    if force_ffba is not None:
        force_block += f"        emu:write8(0xFFBA, 0x{force_ffba:02X})\n"
    return f'''
-- Color regression test script (OAM + BG attr histogram)
local frame_count = 0
local target_frames = {frames}

local function dump_oam()
    -- Iteration 15: use emu.memory.oam:readRange (relative offsets) instead
    -- of emu:readRange (absolute) — the dedicated OAM accessor returns
    -- a snapshot at a single emulator-time point AND avoids whatever
    -- cross-region timing leakage the absolute readRange has (which
    -- caused iter 8/14 tests to fail with phantom transient palettes
    -- in slots NOT touched by the change-under-test).
    local raw = emu.memory.oam:readRange(0, 0xA0)  -- 40 sprites x 4 bytes = 160
    local oam_data = {{}}
    for i = 0, 39 do
        local off = i * 4 + 1  -- Lua strings are 1-indexed
        local y = raw:byte(off)
        local x = raw:byte(off + 1)
        local tile = raw:byte(off + 2)
        local flags = raw:byte(off + 3)
        local palette = flags & 0x07
        table.insert(oam_data, {{
            slot = i,
            y = y,
            x = x,
            tile = tile,
            flags = flags,
            palette = palette,
            visible = (y > 0 and y < 160)
        }})
    end
    return oam_data
end

local function dump_bg_attr_histo()
    -- Count visible BG cells per palette index (0-7).
    -- Reads VBK=1 attr byte for each cell in the 20x18 visible window.
    local base = ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800
    emu:write8(0xFF4F, 1)
    local histo = {{0, 0, 0, 0, 0, 0, 0, 0}}
    for r = 0, 17 do
        for c = 0, 19 do
            local p = emu:read8(base + r*32 + c) & 7
            histo[p+1] = histo[p+1] + 1
        end
    end
    emu:write8(0xFF4F, 0)
    return histo
end

local function dump_bg_table_palettes()
    -- Sample 0xDA00 (the WRAM tile->palette table that scene_detect copies
    -- and the per-scene overrides patch). Returns palette index for each of
    -- the 256 tile IDs. Lets tests assert "after scene_detect at D880=0x1B,
    -- tile 0xE0 maps to pal 6" without needing the game to draw the banner.
    local t = {{}}
    for i = 0, 255 do
        t[i+1] = emu:read8(0xDA00 + i) & 7
    end
    return t
end

-- Optional state forcing (per-test). Re-applied EVERY frame from frame 10
-- onwards because the game's main loop frequently rewrites D880/DCFD as
-- part of its own state machine. One-shot writes get clobbered on the next
-- main-loop tick; pinning the value each frame holds the target scene
-- stable so scene_detect (which compares D880 to DF23) re-fires every
-- transition and bg_sweep has all ~50 frames to propagate.
local function maybe_force_state()
    if frame_count >= 10 then
{force_block}    end
end

-- Multi-sample OAM ring (filter the Lua "frame" callback timing transient):
-- the callback can fire BEFORE the VBlank IRQ's hwoam_recolor writes HW OAM,
-- so a single read can catch a pre-recolor state where slot N has the post-
-- DMA race-residue palette instead of the final colorizer assignment. Take
-- N samples across the post-target_frames window and majority-vote per slot
-- so the steady-state palette wins even when one sample is transient.
local oam_samples = {{}}  -- list of 40-entry tables, one per sample
local function record_oam_sample()
    table.insert(oam_samples, dump_oam())
end
local function consensus_oam()
    -- Returns a 40-entry table where each slot's palette is the mode across
    -- all samples (ties broken by latest sample — newer = closer to truth).
    -- Other fields (y/x/tile/flags) come from the latest sample.
    local out = {{}}
    local last = oam_samples[#oam_samples]
    for slot_idx = 1, 40 do
        local counts = {{}}
        for _, sample in ipairs(oam_samples) do
            local pal = sample[slot_idx].palette
            counts[pal] = (counts[pal] or 0) + 1
        end
        local best_pal, best_count = last[slot_idx].palette, 0
        for pal, count in pairs(counts) do
            if count > best_count or (count == best_count and pal == last[slot_idx].palette) then
                best_pal, best_count = pal, count
            end
        end
        local s = last[slot_idx]
        out[slot_idx] = {{
            slot = s.slot, y = s.y, x = s.x, tile = s.tile,
            flags = (s.flags & 0xF8) | best_pal,  -- rebuild attr with consensus pal
            palette = best_pal,
            visible = s.visible,
        }}
    end
    return out
end

callbacks:add("frame", function()
    frame_count = frame_count + 1
    maybe_force_state()
    -- Take OAM samples at target_frames-2, target_frames, target_frames+2,
    -- target_frames+5, target_frames+8 (5 samples spanning ~10 frames so the
    -- recolor's writes propagate to the displayed HW OAM. Each sample is
    -- captured *after* the colorize IRQ for that frame has had a chance to
    -- run, so consensus filters out the early-callback transient.
    if frame_count == target_frames - 2 or frame_count == target_frames or
       frame_count == target_frames + 2 or frame_count == target_frames + 5 then
        record_oam_sample()
    end
    if frame_count >= target_frames + 8 then
        record_oam_sample()
        emu:screenshot("{output_prefix}.png")

        -- Dump consensus OAM + BG attr histogram + bg_table + scene state
        local oam = consensus_oam()
        local bg_histo = dump_bg_attr_histo()
        local bg_table = dump_bg_table_palettes()
        local boss_flag = emu:read8(0xFFBF)
        local d880 = emu:read8(0xD880)
        local ffc1 = emu:read8(0xFFC1)
        local ffba = emu:read8(0xFFBA)
        local ffbe = emu:read8(0xFFBE)

        -- Write JSON output
        local f = io.open("{output_prefix}.json", "w")
        if f then
            f:write(string.format(
                "{{\\"boss_flag\\":%d,\\"d880\\":%d,\\"ffc1\\":%d,\\"ffba\\":%d,\\"ffbe\\":%d,",
                boss_flag, d880, ffc1, ffba, ffbe))
            f:write("\\"bg_histo\\":[")
            for i = 1, 8 do
                if i > 1 then f:write(",") end
                f:write(tostring(bg_histo[i]))
            end
            f:write("],\\"bg_table\\":[")
            for i = 1, 256 do
                if i > 1 then f:write(",") end
                f:write(tostring(bg_table[i]))
            end
            f:write("],\\"oam\\":[")
            for i, sprite in ipairs(oam) do
                if i > 1 then f:write(",") end
                f:write(string.format(
                    "{{\\"slot\\":%d,\\"y\\":%d,\\"x\\":%d,\\"tile\\":%d,\\"flags\\":%d,\\"palette\\":%d,\\"visible\\":%s}}",
                    sprite.slot, sprite.y, sprite.x, sprite.tile, sprite.flags, sprite.palette,
                    sprite.visible and "true" or "false"
                ))
            end
            f:write("]}}")
            f:close()
        end

        emu:quit()
    end
end)
'''


def run_test_with_mgba(rom_path: str, savestate_path: str, lua_script_path: str, timeout: int = 30) -> bool:
    """Run mGBA with savestate and lua script, return True if successful."""
    cmd = [
        "timeout", str(timeout),
        "xvfb-run", "-a", "mgba-qt",
        rom_path,
        "-t", savestate_path,
        "--script", lua_script_path,
        "-l", "0"
    ]

    # Use dummy audio driver for headless testing
    env = os.environ.copy()
    env["SDL_AUDIODRIVER"] = "dummy"

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5, env=env)
        return result.returncode == 0 or result.returncode == 124  # 124 = timeout (expected)
    except subprocess.TimeoutExpired:
        return True  # Timeout is expected - script should quit
    except Exception as e:
        print(f"Error running mGBA: {e}")
        return False


def verify_bg_table_expectations(bg_table: list, exps: list) -> list:
    """Verify that WRAM 0xDA00's tile->palette map matches expectations.

    Each entry: {tile_range: [lo, hi], palette: int, description: str}
    For each tile_id in [lo, hi], asserts bg_table[tile_id] == palette.
    Useful because forcing D880 doesn't redraw the tilemap; the only way
    to confirm scene_detect + per-scene overrides ran correctly is to
    sample the table they wrote to 0xDA00 directly.
    """
    errors = []
    for exp in exps:
        rng = exp.get("tile_range")
        pal = exp.get("palette")
        if not rng or pal is None:
            errors.append(f"Invalid bg_table_expectation: {exp}")
            continue
        lo, hi = rng
        mismatched = [(tid, bg_table[tid]) for tid in range(lo, hi+1)
                      if bg_table[tid] != pal]
        if mismatched:
            sample = ", ".join(f"0x{tid:02X}=p{got}" for tid, got in mismatched[:5])
            errors.append(
                f"bg_table[0x{lo:02X}-0x{hi:02X}] expected pal{pal}, "
                f"{len(mismatched)}/{hi-lo+1} mismatched (e.g. {sample}) - "
                f"{exp.get('description', '')}")
    return errors


def verify_bg_expectations(bg_histo: list, bg_expectations: list) -> list:
    """Verify BG attr histogram matches expectations. Returns list of errors.

    Each bg_expectation is a dict with:
      palette: int (0-7)
      min_cells: int (optional, default 0)
      max_cells: int (optional, default unlimited)
      description: str (optional)
    Useful for asserting things like "banner has >= 20 pal6 cells (letters)"
    or "level-select has zero pal1 cells (no red flood)".
    """
    errors = []
    for exp in bg_expectations:
        pal = exp.get("palette")
        if pal is None or not (0 <= pal <= 7):
            errors.append(f"Invalid bg_expectation palette: {pal}")
            continue
        count = bg_histo[pal]
        min_c = exp.get("min_cells", 0)
        max_c = exp.get("max_cells")
        desc = exp.get("description", "")
        if count < min_c:
            errors.append(f"BG pal{pal} count {count} < min {min_c} - {desc}")
        if max_c is not None and count > max_c:
            errors.append(f"BG pal{pal} count {count} > max {max_c} - {desc}")
    return errors


def verify_expectations(oam_data: list, boss_flag: int, expectations: list, expected_boss_flag: int,
                        bg_histo: list = None, bg_expectations: list = None,
                        bg_table: list = None, bg_table_expectations: list = None,
                        check_boss_flag: bool = True) -> tuple[bool, str]:
    """Verify OAM + BG data matches expectations. Returns (passed, message)."""
    errors = []

    # Check boss flag (skip for non-gameplay tests where FFBF is meaningless)
    if check_boss_flag and boss_flag != expected_boss_flag:
        errors.append(f"Boss flag mismatch: expected {expected_boss_flag}, got {boss_flag}")

    for exp in expectations:
        if "slots" in exp:
            # Check specific slots
            for slot in exp["slots"]:
                if slot < len(oam_data):
                    sprite = oam_data[slot]
                    if sprite["visible"] and sprite["palette"] != exp["palette"]:
                        errors.append(
                            f"Slot {slot}: expected palette {exp['palette']}, "
                            f"got {sprite['palette']} (tile=0x{sprite['tile']:02X}) - {exp.get('description', '')}"
                        )

        elif "tile_range" in exp:
            # Check sprites by tile range
            tile_min, tile_max = exp["tile_range"]
            found_any = False
            for sprite in oam_data:
                if sprite["visible"] and tile_min <= sprite["tile"] <= tile_max:
                    found_any = True
                    if sprite["palette"] != exp["palette"]:
                        errors.append(
                            f"Tile 0x{sprite['tile']:02X} (slot {sprite['slot']}): "
                            f"expected palette {exp['palette']}, got {sprite['palette']} - {exp.get('description', '')}"
                        )

            if not found_any and exp.get("required", False):
                errors.append(f"No visible sprites found in tile range 0x{tile_min:02X}-0x{tile_max:02X}")

    # BG expectations (new, additive — old tests with no bg_expectations are unaffected)
    if bg_histo is not None and bg_expectations:
        errors.extend(verify_bg_expectations(bg_histo, bg_expectations))

    # bg_table (WRAM 0xDA00 mapping) expectations — used by scene tests that
    # force D880 to verify scene_detect + per-scene overrides patched 0xDA00.
    if bg_table is not None and bg_table_expectations:
        errors.extend(verify_bg_table_expectations(bg_table, bg_table_expectations))

    if errors:
        return False, "\n".join(errors)
    return True, "All expectations passed"


def run_single_test(test: dict, rom_path: str, savestate_dir: str, output_dir: str, verbose: bool = False) -> TestResult:
    """Run a single regression test."""
    name = test["name"]
    savestate = test["savestate"]
    savestate_path = os.path.join(savestate_dir, savestate)

    if not os.path.exists(savestate_path):
        return TestResult(name, False, f"Savestate not found: {savestate_path}")

    output_prefix = os.path.join(output_dir, name)
    lua_script_path = os.path.join(output_dir, f"{name}_test.lua")

    # Generate and write Lua script (with optional state-forcing)
    lua_script = create_test_lua_script(
        output_prefix,
        force_d880=test.get("force_d880"),
        force_dcfd=test.get("force_dcfd"),
        force_ffba=test.get("force_ffba"),
    )
    with open(lua_script_path, "w") as f:
        f.write(lua_script)

    if verbose:
        print(f"  Running mGBA with savestate {savestate}...")

    # Run the test
    success = run_test_with_mgba(rom_path, savestate_path, lua_script_path)

    if not success:
        return TestResult(name, False, "mGBA execution failed")

    # Read results
    json_path = f"{output_prefix}.json"
    if not os.path.exists(json_path):
        return TestResult(name, False, f"No output generated (expected {json_path})")

    try:
        with open(json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return TestResult(name, False, f"Invalid JSON output: {e}")

    oam_data = data.get("oam", [])
    bg_histo = data.get("bg_histo", [0]*8)
    bg_table = data.get("bg_table", [0]*256)
    boss_flag = data.get("boss_flag", -1)
    expectations = test.get("expectations", [])
    bg_expectations = test.get("bg_expectations", [])
    bg_table_expectations = test.get("bg_table_expectations", [])
    expected_boss_flag = test.get("expected_boss_flag", 0)
    # For non-gameplay tests (cutscene/menu/title), the boss flag is undefined.
    # YAML can set `check_boss_flag: false` to skip that check.
    check_boss_flag = test.get("check_boss_flag", True)

    # Verify expectations
    passed, message = verify_expectations(
        oam_data, boss_flag, expectations, expected_boss_flag,
        bg_histo=bg_histo, bg_expectations=bg_expectations,
        bg_table=bg_table, bg_table_expectations=bg_table_expectations,
        check_boss_flag=check_boss_flag,
    )

    screenshot_path = f"{output_prefix}.png"
    if not os.path.exists(screenshot_path):
        screenshot_path = None

    return TestResult(
        name=name,
        passed=passed,
        message=message,
        screenshot=screenshot_path,
        oam_data=oam_data
    )


def main():
    parser = argparse.ArgumentParser(description="Run color regression tests")
    parser.add_argument("--test", "-t", help="Run only specific test by name")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--config", "-c", default="tests/color_regression_tests.yaml", help="Test config file")
    parser.add_argument("--rom", help="ROM path override (takes precedence over config)")
    args = parser.parse_args()

    # Load test configuration
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    test_config = config.get("test_config", {})
    rom_path = args.rom or test_config.get("rom_path", "rom/working/penta_dragon_dx_FIXED.gb")
    savestate_dir = test_config.get("savestate_dir", "save_states_for_claude")
    output_dir = test_config.get("output_dir", "tests/results")

    # Check ROM exists
    if not os.path.exists(rom_path):
        print(f"Error: ROM not found: {rom_path}")
        print("Build the ROM first with: uv run python scripts/create_vblank_colorizer_v109.py")
        sys.exit(1)

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    tests = config.get("tests", [])

    # Filter to specific test if requested
    if args.test:
        tests = [t for t in tests if t["name"] == args.test]
        if not tests:
            print(f"Error: Test '{args.test}' not found")
            sys.exit(1)

    print(f"Running {len(tests)} color regression tests...")
    print(f"ROM: {rom_path}")
    print(f"Output: {output_dir}/")
    print()

    results = []
    passed = 0
    failed = 0

    for test in tests:
        name = test["name"]
        description = test.get("description", "")
        print(f"[TEST] {name}: {description}")

        result = run_single_test(test, rom_path, savestate_dir, output_dir, verbose=args.verbose)
        results.append(result)

        if result.passed:
            passed += 1
            print(f"  [PASS] {result.message}")
        else:
            failed += 1
            print(f"  [FAIL] {result.message}")

        if result.screenshot:
            print(f"  Screenshot: {result.screenshot}")
        print()

    # Summary
    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed, {len(tests)} total")

    if failed > 0:
        print("\nFailed tests:")
        for r in results:
            if not r.passed:
                print(f"  - {r.name}: {r.message}")
        sys.exit(1)
    else:
        print("\nAll tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
