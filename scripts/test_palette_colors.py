#!/usr/bin/env python3
"""
Palette Color Verification Tests

Verifies that palette YAML files are correctly loaded into the ROM
by building with different palettes and checking actual CGB palette RAM.

Usage:
    uv run python scripts/test_palette_colors.py
    uv run python scripts/test_palette_colors.py --palette palettes/test_palette_A.yaml
"""

import subprocess
import sys
import os
import json
import yaml
import tempfile
import shutil
from pathlib import Path
from typing import Optional
import argparse


def parse_yaml_palettes(yaml_path: str) -> tuple[list[int], list[int]]:
    """Parse YAML and return expected BG and OBJ palette bytes."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    def color_to_bytes(hex_str: str) -> tuple[int, int]:
        """Convert BGR555 hex string to two bytes (little-endian)."""
        val = int(hex_str, 16) & 0x7FFF
        return val & 0xFF, (val >> 8) & 0xFF

    # BG palettes
    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_bytes = []
    for key in bg_keys:
        colors = data.get('bg_palettes', {}).get(key, {}).get('colors', ["7FFF", "5294", "2108", "0000"])
        for c in colors:
            lo, hi = color_to_bytes(c)
            bg_bytes.extend([lo, hi])

    # OBJ palettes
    obj_keys = ['Effects', 'SaraDragon', 'SaraWitch', 'Crow', 'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
    obj_bytes = []
    for key in obj_keys:
        colors = data.get('obj_palettes', {}).get(key, {}).get('colors', ["0000", "7FFF", "5294", "2108"])
        for c in colors:
            lo, hi = color_to_bytes(c)
            obj_bytes.extend([lo, hi])

    return bg_bytes, obj_bytes


def build_rom_with_palette(palette_path: str, output_rom: str) -> bool:
    """Build ROM using specified palette file."""
    # The v109 script reads from palettes/penta_palettes_v097.yaml by default
    # We need to temporarily copy our test palette there
    default_palette = "palettes/penta_palettes_v097.yaml"
    backup_palette = "palettes/penta_palettes_v097.yaml.bak"

    try:
        # Backup original
        if os.path.exists(default_palette):
            shutil.copy(default_palette, backup_palette)

        # Copy test palette to default location
        shutil.copy(palette_path, default_palette)

        # Build ROM
        result = subprocess.run(
            ["uv", "run", "python", "scripts/create_vblank_colorizer_v109.py"],
            capture_output=True, text=True, timeout=60
        )

        if result.returncode != 0:
            print(f"Build failed: {result.stderr}")
            return False

        # Copy built ROM to specified output
        shutil.copy("rom/working/penta_dragon_dx_FIXED.gb", output_rom)
        return True

    finally:
        # Restore original palette
        if os.path.exists(backup_palette):
            shutil.move(backup_palette, default_palette)


def run_and_dump_palettes(rom_path: str, savestate_path: str) -> Optional[dict]:
    """Run ROM with savestate and dump palette data."""
    env = os.environ.copy()
    env["SDL_AUDIODRIVER"] = "dummy"

    cmd = [
        "timeout", "15",
        "xvfb-run", "-a", "mgba-qt",
        rom_path,
        "-t", savestate_path,
        "--script", "tmp/dump_palettes.lua",
        "-l", "0"
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=20, env=env)
    except subprocess.TimeoutExpired:
        pass  # Expected - script should quit

    dump_path = "tmp/palette_dump.json"
    if not os.path.exists(dump_path):
        print(f"Error: No palette dump generated")
        return None

    with open(dump_path) as f:
        data = json.load(f)

    os.remove(dump_path)
    return data


def compare_palettes(expected_bg: list[int], expected_obj: list[int],
                     actual_bg: list[int], actual_obj: list[int]) -> tuple[bool, list[str]]:
    """Compare expected vs actual palette bytes. Returns (passed, errors)."""
    errors = []

    # Compare BG palettes
    for i, (exp, act) in enumerate(zip(expected_bg, actual_bg)):
        if exp != act:
            pal_num = i // 8
            color_num = (i % 8) // 2
            byte_num = i % 2
            errors.append(f"BG palette {pal_num} color {color_num} byte {byte_num}: expected 0x{exp:02X}, got 0x{act:02X}")

    # Compare OBJ palettes
    for i, (exp, act) in enumerate(zip(expected_obj, actual_obj)):
        if exp != act:
            pal_num = i // 8
            color_num = (i % 8) // 2
            byte_num = i % 2
            errors.append(f"OBJ palette {pal_num} color {color_num} byte {byte_num}: expected 0x{exp:02X}, got 0x{act:02X}")

    return len(errors) == 0, errors


def run_palette_test(palette_path: str, savestate_path: str, verbose: bool = False) -> bool:
    """Run a single palette verification test."""
    palette_name = os.path.basename(palette_path)
    print(f"\n[TEST] Palette: {palette_name}")

    # Parse expected values from YAML
    expected_bg, expected_obj = parse_yaml_palettes(palette_path)
    if verbose:
        print(f"  Expected BG bytes: {len(expected_bg)}")
        print(f"  Expected OBJ bytes: {len(expected_obj)}")

    # Build ROM with this palette
    test_rom = f"tmp/test_{palette_name.replace('.yaml', '')}.gb"
    print(f"  Building ROM with {palette_name}...")
    if not build_rom_with_palette(palette_path, test_rom):
        print(f"  [FAIL] ROM build failed")
        return False

    # Run and dump palettes
    print(f"  Running ROM and dumping palettes...")
    data = run_and_dump_palettes(test_rom, savestate_path)
    if data is None:
        print(f"  [FAIL] Could not read palette data")
        return False

    actual_bg = data.get('bg_palettes', [])
    actual_obj = data.get('obj_palettes', [])

    if len(actual_bg) != 64 or len(actual_obj) != 64:
        print(f"  [FAIL] Unexpected palette data size: BG={len(actual_bg)}, OBJ={len(actual_obj)}")
        return False

    # Compare
    passed, errors = compare_palettes(expected_bg, expected_obj, actual_bg, actual_obj)

    if passed:
        print(f"  [PASS] All palette colors match YAML")
        return True
    else:
        print(f"  [FAIL] {len(errors)} mismatches found:")
        for err in errors[:10]:  # Show first 10 errors
            print(f"    - {err}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")
        return False


def main():
    parser = argparse.ArgumentParser(description="Verify palette YAML is loaded correctly")
    parser.add_argument("--palette", "-p", help="Test specific palette file only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Default savestate for testing
    savestate = "save_states_for_claude/level1_sara_w_alone.ss0"
    if not os.path.exists(savestate):
        print(f"Error: Savestate not found: {savestate}")
        sys.exit(1)

    # Palette files to test
    if args.palette:
        palettes = [args.palette]
    else:
        palettes = [
            "palettes/test_palette_A.yaml",
            "palettes/test_palette_B.yaml",
        ]

    # Filter to existing files
    palettes = [p for p in palettes if os.path.exists(p)]
    if not palettes:
        print("Error: No test palette files found")
        print("Create palettes/test_palette_A.yaml and palettes/test_palette_B.yaml first")
        sys.exit(1)

    print(f"Running {len(palettes)} palette verification test(s)...")
    print(f"Savestate: {savestate}")

    results = []
    for pal in palettes:
        passed = run_palette_test(pal, savestate, verbose=args.verbose)
        results.append((pal, passed))

    # Summary
    print("\n" + "=" * 60)
    passed_count = sum(1 for _, p in results if p)
    print(f"RESULTS: {passed_count}/{len(results)} passed")

    if passed_count < len(results):
        print("\nFailed tests:")
        for pal, passed in results:
            if not passed:
                print(f"  - {pal}")
        sys.exit(1)
    else:
        print("\nAll palette verification tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    main()
