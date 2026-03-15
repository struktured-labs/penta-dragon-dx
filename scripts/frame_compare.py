#!/usr/bin/env python3
"""Frame-by-frame comparison: original Penta Dragon vs remake.

Runs both ROMs headlessly with identical input sequences,
captures OAM state + screenshots at specified frames,
and reports behavioral differences.
"""

import json
import os
import subprocess
import struct
import sys
import tempfile
from pathlib import Path

PROJ = Path(__file__).parent.parent
DX_PROJ = PROJ.parent / "penta-dragon-dx-claude"
ORIG_ROM = DX_PROJ / "rom" / "Penta Dragon (J).gb"
REMAKE_ROM = PROJ / "rom" / "working" / "penta_dragon_dx.gbc"
SAVE_STATES = DX_PROJ / "save_states_for_claude"
OUT_DIR = PROJ / "tmp" / "frame_compare"

# Standard headless env
HEADLESS_ENV = {
    **os.environ,
    "QT_QPA_PLATFORM": "offscreen",
    "SDL_AUDIODRIVER": "dummy",
}
# Remove display vars
HEADLESS_ENV.pop("DISPLAY", None)
HEADLESS_ENV.pop("WAYLAND_DISPLAY", None)


# Input sequence: list of (frame, key_mask) pairs
# Simulates a typical gameplay session
INPUT_SEQUENCE = [
    # Idle for 30 frames
    # Move right for 40 frames
    (30, 0x10),   # RIGHT on
    (70, 0x00),   # release
    # Move up for 20 frames
    (80, 0x40),   # UP on
    (100, 0x00),  # release
    # Move left for 20 frames
    (110, 0x20),  # LEFT on
    (130, 0x00),  # release
    # Move down-right for 20 frames
    (140, 0x90),  # DOWN+RIGHT
    (160, 0x00),  # release
    # Shoot for 30 frames
    (170, 0x01),  # A
    (200, 0x00),  # release
    # Move right + shoot
    (210, 0x11),  # RIGHT+A
    (250, 0x00),  # release
    # Idle
]

# Frames to capture screenshots
CAPTURE_FRAMES = [1, 30, 50, 70, 100, 130, 160, 200, 250, 300]


def generate_lua_script(rom_label: str, input_seq: list, capture_frames: list,
                        out_prefix: str, use_savestate: bool = False) -> str:
    """Generate a Lua script for mGBA that plays inputs and captures data."""

    # Build input event table
    input_lines = []
    for frame, mask in input_seq:
        input_lines.append(f"    {{frame={frame}, mask={mask}}}")
    input_table = ",\n".join(input_lines)

    # Build capture frame set
    capture_set = ", ".join(f"[{f}]=true" for f in capture_frames)

    return f'''-- Auto-generated frame comparison script for {rom_label}
local frame = 0
local input_events = {{
{input_table}
}}
local input_idx = 1
local capture_frames = {{{capture_set}}}
local oam_log = {{}}

callbacks:add("frame", function()
    frame = frame + 1

    -- Apply input events
    while input_idx <= #input_events and input_events[input_idx].frame <= frame do
        emu:setKeys(input_events[input_idx].mask)
        input_idx = input_idx + 1
    end

    -- Capture at specified frames
    if capture_frames[frame] then
        emu:screenshot("{out_prefix}_f" .. string.format("%04d", frame) .. ".png")

        -- Log OAM state (first 10 sprites)
        local oam = {{}}
        for i = 0, 9 do
            local base = 0xFE00 + i * 4
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            oam[#oam+1] = string.format("%d,%d,%d,%d", y, x, tile, flags)
        end

        -- Log scroll position
        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)

        oam_log[#oam_log+1] = string.format("F%04d SCX=%d SCY=%d OAM: %s",
            frame, scx, scy, table.concat(oam, " | "))
    end

    -- Done
    if frame >= {max(capture_frames) + 10} then
        local f = io.open("{out_prefix}_oam.txt", "w")
        for _, line in ipairs(oam_log) do
            f:write(line .. "\\n")
        end
        f:close()
        emu:quit()
    end
end)
'''


def run_rom(rom_path: str, lua_script: str, label: str,
            savestate: str = None, timeout: int = 30) -> bool:
    """Run a ROM with a Lua script headlessly."""
    script_path = OUT_DIR / f"{label}_script.lua"
    script_path.write_text(lua_script)

    cmd = [
        "xvfb-run", "-a", "mgba-qt",
        str(rom_path),
        "--script", str(script_path),
        "-l", "0",
    ]
    if savestate:
        cmd.extend(["-t", str(savestate)])

    try:
        result = subprocess.run(
            cmd,
            env=HEADLESS_ENV,
            timeout=timeout,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        pass  # Expected — mGBA may not quit cleanly
    return True


def compare_oam_logs(orig_path: Path, remake_path: Path) -> list:
    """Compare OAM logs from two runs and report differences."""
    diffs = []

    orig_lines = orig_path.read_text().strip().split("\n") if orig_path.exists() else []
    remake_lines = remake_path.read_text().strip().split("\n") if remake_path.exists() else []

    for i, (o, r) in enumerate(zip(orig_lines, remake_lines)):
        if o != r:
            diffs.append(f"Frame diff #{i+1}:\n  ORIG:   {o}\n  REMAKE: {r}")

    return diffs


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Penta Dragon Frame Comparison")
    print("=" * 60)
    print(f"Original: {ORIG_ROM}")
    print(f"Remake:   {REMAKE_ROM}")

    if not ORIG_ROM.exists():
        print(f"ERROR: Original ROM not found at {ORIG_ROM}")
        return 1

    if not REMAKE_ROM.exists():
        print("ERROR: Remake ROM not found. Run 'make' first.")
        return 1

    orig_prefix = str(OUT_DIR / "orig")
    remake_prefix = str(OUT_DIR / "remake")

    # Generate Lua scripts
    orig_lua = generate_lua_script(
        "Original", INPUT_SEQUENCE, CAPTURE_FRAMES, orig_prefix
    )
    remake_lua = generate_lua_script(
        "Remake", INPUT_SEQUENCE, CAPTURE_FRAMES, remake_prefix
    )

    # Run original
    print("\n--- Running Original ROM ---")
    run_rom(ORIG_ROM, orig_lua, "orig", timeout=30)

    # Run remake
    print("--- Running Remake ROM ---")
    run_rom(REMAKE_ROM, remake_lua, "remake", timeout=30)

    # Compare OAM logs
    print("\n--- Comparing OAM State ---")
    orig_oam = Path(f"{orig_prefix}_oam.txt")
    remake_oam = Path(f"{remake_prefix}_oam.txt")

    if not orig_oam.exists():
        print("WARNING: Original OAM log missing (ROM may not support Lua input)")
    if not remake_oam.exists():
        print("WARNING: Remake OAM log missing")

    if orig_oam.exists():
        print(f"\nOriginal OAM snapshots:")
        print(orig_oam.read_text())

    if remake_oam.exists():
        print(f"Remake OAM snapshots:")
        print(remake_oam.read_text())

    if orig_oam.exists() and remake_oam.exists():
        diffs = compare_oam_logs(orig_oam, remake_oam)
        if diffs:
            print(f"\n{len(diffs)} DIFFERENCES found:")
            for d in diffs:
                print(f"  {d}")
        else:
            print("\nNo differences in OAM state!")

    # List screenshots
    print("\n--- Screenshots ---")
    for f in sorted(OUT_DIR.glob("*.png")):
        print(f"  {f.name}")

    print(f"\nResults in: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
