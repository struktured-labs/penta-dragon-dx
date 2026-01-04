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


def create_test_lua_script(output_prefix: str, frames: int = 60) -> str:
    """Generate Lua script for testing palette assignments."""
    return f'''
-- Color regression test script
local frame_count = 0
local target_frames = {frames}

local function dump_oam()
    local oam_data = {{}}
    for i = 0, 39 do
        local addr = 0xFE00 + i * 4
        local y = emu:read8(addr)
        local x = emu:read8(addr + 1)
        local tile = emu:read8(addr + 2)
        local flags = emu:read8(addr + 3)
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

callbacks:add("frame", function()
    frame_count = frame_count + 1
    if frame_count >= target_frames then
        -- Take screenshot
        emu:screenshot("{output_prefix}.png")

        -- Dump OAM data
        local oam = dump_oam()
        local boss_flag = emu:read8(0xFFBF)

        -- Write JSON output
        local f = io.open("{output_prefix}.json", "w")
        if f then
            f:write("{{\\"boss_flag\\":" .. boss_flag .. ",\\"oam\\":[")
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


def verify_expectations(oam_data: list, boss_flag: int, expectations: list, expected_boss_flag: int) -> tuple[bool, str]:
    """Verify OAM data matches expectations. Returns (passed, message)."""
    errors = []

    # Check boss flag
    if boss_flag != expected_boss_flag:
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

    # Generate and write Lua script
    lua_script = create_test_lua_script(output_prefix)
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
    boss_flag = data.get("boss_flag", -1)
    expectations = test.get("expectations", [])
    expected_boss_flag = test.get("expected_boss_flag", 0)

    # Verify expectations
    passed, message = verify_expectations(oam_data, boss_flag, expectations, expected_boss_flag)

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
    args = parser.parse_args()

    # Load test configuration
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    test_config = config.get("test_config", {})
    rom_path = test_config.get("rom_path", "rom/working/penta_dragon_dx_FIXED.gb")
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
