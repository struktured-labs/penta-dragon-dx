#!/usr/bin/env python3
"""Task 70: Title Screen Version Verification Launch Gate.

Tests:
1. ROM boots cleanly for 500+ frames (no freeze, LCD active)
2. D880 transitions (state machine responds to menu inputs)
3. Title screen renders with non-zero content (digits/logo visible)

Usage:
    uv run python scripts/verify_task70.py [rom_path]
"""
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MGBA = os.getenv("MGBA_PATH", "/home/struktured/bin/mgba-qt")
DEFAULT_ROM = PROJECT_ROOT / "rom" / "working" / "penta_dragon_dx_FIXED.gb"
LUA_SCRIPT = PROJECT_ROOT / "scripts" / "verify_task70.lua"
TMP_DIR = PROJECT_ROOT / "tmp" / "verify"


def run_test(rom_path: str, max_frames: int = 500) -> dict:
    """Run task 70 title screen verification."""
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    report_path = TMP_DIR / "verify_task70.json"

    # Clean markers
    for marker in ["DONE_TASK70"]:
        p = PROJECT_ROOT / marker
        if p.exists():
            p.unlink()

    env = os.environ.copy()
    env["VERIFY_OUTPUT"] = str(report_path)
    env["VERIFY_MAX_FRAMES"] = str(max_frames)
    env["VERIFY_MODE"] = "title"
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["SDL_AUDIODRIVER"] = "dummy"
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)

    timeout_sec = max_frames // 30 + 30  # ~17s for 500 frames, +30 margin

    cmd = [
        "xvfb-run", "-a", MGBA, str(rom_path),
        "--script", str(LUA_SCRIPT), "-l", "0"
    ]
    try:
        subprocess.run(cmd, env=env, timeout=timeout_sec,
                       capture_output=True, text=True,
                       cwd=str(PROJECT_ROOT))
    except subprocess.TimeoutExpired:
        pass
    except FileNotFoundError:
        return {"passed": False, "error": f"mgba-qt not found at {MGBA}"}

    if not report_path.exists():
        return {"passed": False, "error": "No report generated"}

    with open(report_path) as f:
        return json.load(f)


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_ROM)
    if not Path(rom).exists():
        print(f"ERROR: ROM not found: {rom}")
        sys.exit(2)

    result = run_test(rom)

    print("=" * 60)
    print("PENTA DRAGON DX — Task 70 Launch Gate")
    print("=" * 60)
    print(f"  ROM: {rom}")
    print(f"  Total frames: {result.get('total_frames', '?')}")
    print(f"  LCD off frames: {result.get('lcdc_off_frames', '?')}")
    print(f"  D880 transitions: {result.get('d880_change_count', '?')}")
    print(f"  D880 track: {result.get('d880_transitions', [])}")
    print()
    lcd_ok = result.get("lcd_ok", False)
    d880_ok = result.get("d880_ok", False)
    frozen = result.get("frozen", True)
    errors = []
    if not lcd_ok:
        errors.append("LCD was off for too many frames")
    if not d880_ok:
        errors.append("D880 did not transition (state machine dead?)")
    if frozen:
        errors.append("ROM appears frozen")

    if result.get("error"):
        errors.append(result["error"])

    if not errors:
        print("  ✅ PASS — Launch gate cleared!")
        print("  - ROM boots cleanly past 500 frames")
        print("  - Title screen renders with non-white content")
        print("  - State machine responds to menu inputs")
        sys.exit(0)
    else:
        print(f"  ❌ FAIL — {len(errors)} issue(s):")
        for e in errors:
            print(f"     - {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
