#!/usr/bin/env python3
"""Frame-by-frame comparison: original Penta Dragon vs remake.

Runs both ROMs headlessly with identical input sequences,
captures OAM state + screenshots at specified frames,
and reports behavioral differences.
"""

import os
import subprocess
import sys
from pathlib import Path
from PIL import Image

PROJ = Path(__file__).parent.parent
DX_PROJ = PROJ.parent / "penta-dragon-dx-claude"
ORIG_ROM = DX_PROJ / "rom" / "Penta Dragon (J).gb"
REMAKE_ROM = PROJ / "rom" / "working" / "penta_dragon_dx.gbc"
OUT_DIR = PROJ / "tmp" / "frame_compare"

HEADLESS_ENV = {
    **os.environ,
    "QT_QPA_PLATFORM": "offscreen",
    "SDL_AUDIODRIVER": "dummy",
}
HEADLESS_ENV.pop("DISPLAY", None)
HEADLESS_ENV.pop("WAYLAND_DISPLAY", None)

# Key masks
K_A      = 0x01
K_B      = 0x02
K_SELECT = 0x04
K_START  = 0x08
K_RIGHT  = 0x10
K_LEFT   = 0x20
K_UP     = 0x40
K_DOWN   = 0x80

# ============================================
# Original ROM: menu navigation + gameplay
# ============================================
# Menu: A (title) → wait → DOWN (select GAME START) → A (confirm) → wait → gameplay
# The menu takes roughly:
#   Frame 1-60: title screen animation
#   Frame 60: press A
#   Frame 65: release
#   Frame 90: press DOWN (move cursor to GAME START)
#   Frame 95: release
#   Frame 100: press A (confirm)
#   Frame 105: release
#   Frame 140: press A (start gameplay after transition)
#   Frame 145: release
#   Frame ~180+: gameplay active

ORIG_MENU_PREFIX = [
    (30,  K_START), # Skip logo/title
    (35,  0),
    (80,  K_DOWN),  # Select GAME START (not OPENING START)
    (85,  0),
    (100, K_A),     # Confirm GAME START
    (105, 0),
    (200, K_A),     # Skip transition
    (205, 0),
    (300, K_A),     # Extra A for safety
    (305, 0),
]
ORIG_GAMEPLAY_START = 400  # FFC1=1 at ~250, OAM populated at ~400

# ============================================
# Gameplay input sequence (applied after gameplay starts)
# Same inputs for both ROMs, offset by gameplay start frame
# ============================================
GAMEPLAY_INPUTS = [
    # (offset_from_start, key_mask)
    (0,   0),        # Idle
    (30,  K_RIGHT),  # Move right
    (70,  0),        # Stop
    (80,  K_UP),     # Move up
    (100, 0),        # Stop
    (110, K_LEFT),   # Move left
    (130, 0),        # Stop
    (140, K_DOWN | K_RIGHT),  # Diagonal
    (160, 0),        # Stop
    (170, K_A),      # Shoot
    (200, 0),        # Stop
    (210, K_RIGHT | K_A),  # Move + shoot
    (250, 0),        # Stop
]

# Capture frames (relative to gameplay start)
GAMEPLAY_CAPTURE_OFFSETS = [1, 15, 30, 50, 70, 100, 130, 160, 200, 250, 300]


def build_input_sequence(menu_prefix: list, gameplay_inputs: list,
                         gameplay_start: int) -> list:
    """Combine menu navigation and gameplay inputs."""
    seq = list(menu_prefix)
    for offset, mask in gameplay_inputs:
        seq.append((gameplay_start + offset, mask))
    return seq


def build_capture_frames(offsets: list, gameplay_start: int) -> list:
    return [gameplay_start + o for o in offsets]


def generate_lua_script(label: str, input_seq: list, capture_frames: list,
                        out_prefix: str, max_frame: int) -> str:
    input_lines = ",\n".join(
        f"    {{frame={f}, mask={m}}}" for f, m in input_seq
    )
    capture_set = ", ".join(f"[{f}]=true" for f in capture_frames)

    return f'''-- Frame comparison: {label}
local frame = 0
local input_events = {{
{input_lines}
}}
local input_idx = 1
local capture_frames = {{{capture_set}}}
local oam_log = {{}}

callbacks:add("frame", function()
    frame = frame + 1

    -- Apply inputs
    while input_idx <= #input_events and input_events[input_idx].frame <= frame do
        emu:setKeys(input_events[input_idx].mask)
        input_idx = input_idx + 1
    end

    -- Capture
    if capture_frames[frame] then
        emu:screenshot("{out_prefix}_f" .. string.format("%04d", frame) .. ".png")

        local oam = {{}}
        for i = 0, 9 do
            local base = 0xFE00 + i * 4
            oam[#oam+1] = string.format("%d,%d,%d,%d",
                emu:read8(base), emu:read8(base+1),
                emu:read8(base+2), emu:read8(base+3))
        end
        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)
        oam_log[#oam_log+1] = string.format("F%04d SCX=%d SCY=%d OAM: %s",
            frame, scx, scy, table.concat(oam, " | "))
    end

    if frame >= {max_frame} then
        local f = io.open("{out_prefix}_oam.txt", "w")
        for _, line in ipairs(oam_log) do f:write(line .. "\\n") end
        f:close()
        emu:quit()
    end
end)
'''


def run_rom(rom_path: str, lua_script: str, label: str, timeout: int = 45) -> bool:
    script_path = OUT_DIR / f"{label}_script.lua"
    script_path.write_text(lua_script)
    cmd = ["xvfb-run", "-a", "mgba-qt", str(rom_path),
           "--script", str(script_path), "-l", "0"]
    try:
        subprocess.run(cmd, env=HEADLESS_ENV, timeout=timeout,
                       capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        pass
    return True


def compare_screenshots(dir: Path, orig_prefix: str, remake_prefix: str,
                        capture_frames: list) -> list:
    """Compare screenshots visually — report which frames differ most."""
    diffs = []
    for f in capture_frames:
        orig_path = dir / f"{orig_prefix}_f{f:04d}.png"
        remake_path = dir / f"{remake_prefix}_f{f:04d}.png"
        if not orig_path.exists() or not remake_path.exists():
            diffs.append((f, -1, "MISSING"))
            continue
        try:
            img_o = Image.open(orig_path).convert("RGB")
            img_r = Image.open(remake_path).convert("RGB")
            # Simple pixel difference
            pixels_o = list(img_o.getdata())
            pixels_r = list(img_r.getdata())
            total_diff = sum(
                abs(a[0]-b[0]) + abs(a[1]-b[1]) + abs(a[2]-b[2])
                for a, b in zip(pixels_o, pixels_r)
            )
            avg_diff = total_diff / len(pixels_o) / 3.0
            diffs.append((f, avg_diff, "OK" if avg_diff < 50 else "DIFFERS"))
        except Exception as e:
            diffs.append((f, -1, str(e)))
    return diffs


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Penta Dragon Frame Comparison")
    print("=" * 60)

    if not ORIG_ROM.exists():
        print(f"ERROR: Original ROM not found at {ORIG_ROM}")
        return 1
    if not REMAKE_ROM.exists():
        print("ERROR: Remake ROM not found. Run 'make' first.")
        return 1

    # Build sequences
    # Original: menu prefix + gameplay at frame 200
    orig_inputs = build_input_sequence(ORIG_MENU_PREFIX, GAMEPLAY_INPUTS, ORIG_GAMEPLAY_START)
    orig_captures = build_capture_frames(GAMEPLAY_CAPTURE_OFFSETS, ORIG_GAMEPLAY_START)

    # Remake: no menu, gameplay starts at frame 5
    remake_start = 5
    remake_inputs = build_input_sequence([], GAMEPLAY_INPUTS, remake_start)
    remake_captures = build_capture_frames(GAMEPLAY_CAPTURE_OFFSETS, remake_start)

    max_frame_orig = max(orig_captures) + 20
    max_frame_remake = max(remake_captures) + 20

    orig_prefix = str(OUT_DIR / "orig")
    remake_prefix = str(OUT_DIR / "remake")

    # Run both
    print("\n--- Running Original ROM (with menu navigation) ---")
    orig_lua = generate_lua_script("Original", orig_inputs, orig_captures,
                                    orig_prefix, max_frame_orig)
    run_rom(ORIG_ROM, orig_lua, "orig", timeout=45)

    print("--- Running Remake ROM ---")
    remake_lua = generate_lua_script("Remake", remake_inputs, remake_captures,
                                     remake_prefix, max_frame_remake)
    run_rom(REMAKE_ROM, remake_lua, "remake", timeout=30)

    # Report OAM state
    print("\n--- OAM State ---")
    orig_oam = Path(f"{orig_prefix}_oam.txt")
    remake_oam = Path(f"{remake_prefix}_oam.txt")

    if orig_oam.exists():
        print("Original:")
        for line in orig_oam.read_text().strip().split("\n"):
            print(f"  {line}")
    else:
        print("Original OAM: MISSING")

    if remake_oam.exists():
        print("Remake:")
        for line in remake_oam.read_text().strip().split("\n"):
            print(f"  {line}")
    else:
        print("Remake OAM: MISSING")

    # Visual comparison
    print("\n--- Visual Comparison ---")
    print("(comparing screenshots at aligned gameplay frames)")
    # Pair up: orig capture at ORIG_GAMEPLAY_START+offset vs remake at remake_start+offset
    for offset in GAMEPLAY_CAPTURE_OFFSETS:
        of = ORIG_GAMEPLAY_START + offset
        rf = remake_start + offset
        op = OUT_DIR / f"orig_f{of:04d}.png"
        rp = OUT_DIR / f"remake_f{rf:04d}.png"
        status = "both" if op.exists() and rp.exists() else ("orig_only" if op.exists() else ("remake_only" if rp.exists() else "NEITHER"))
        print(f"  Gameplay +{offset:3d}:  orig_f{of:04d}.png / remake_f{rf:04d}.png  [{status}]")

    print(f"\nScreenshots in: {OUT_DIR}")
    print("View side-by-side to compare behavior.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
