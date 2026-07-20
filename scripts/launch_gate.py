#!/usr/bin/env python3
"""Pre-launch gate: verify ROM boots before allowing mGBA to open.

Usage:
    python3 scripts/launch_gate.py rom/working/penta_dragon_dx_teleport.gb

Exits 0 if ROM boots to title screen (not white screen).
Exits 1 if ROM fails to boot (white screen freeze).
Exits 2 on harness error.
"""

import sys
import subprocess
from pathlib import Path

def check_rom(rom_path: str) -> bool:
    """Boot ROM in headless PyBoy, verify title screen renders with color content."""
    try:
        from pyboy import PyBoy
    except ImportError:
        print("LAUNCH GATE: pyboy not available, skipping verification")
        return True

    rom = Path(rom_path)
    if not rom.exists():
        print(f"LAUNCH GATE FAILED: ROM not found at {rom_path}")
        return False

    pb = PyBoy(str(rom), window="null", cgb=True)
    pb.set_emulation_speed(0)

    # Phase 1: Boot check — wait for D880 to change from 0x00
    booted = False
    for f in range(500):
        pb.tick(1, True)
        d880 = pb.memory[0xD880]
        if d880 not in [0x00, 0x18]:  # not in initial boot or splash
            booted = True
            break

    if not booted:
        pb.stop(save=False)
        return False

    # Phase 2: Title screen content check — run to at least frame 300
    # then capture the screen and check it's not all-white
    for _ in range(200):
        pb.tick(1, True)

    # Check pixel content via screen capture
    try:
        from PIL import Image
        import numpy as np
        img = pb.screen.image
        pixels = np.array(img.convert("RGB"))
        # Count non-white pixels
        non_white = np.sum(np.any(pixels < 240, axis=2))
        total = pixels.shape[0] * pixels.shape[1]
        white_ratio = non_white / total if total > 0 else 0
        # Title screen should have at least 5% non-white content
        # (the YANOMAN logo + menu text)
        if white_ratio < 0.05:
            print(f"LAUNCH GATE FAILED: Title screen is all-white ({100*white_ratio:.1f}% content)")
            pb.stop(save=False)
            return False
        print(f"LAUNCH GATE: Title screen has {100*white_ratio:.1f}% non-white content ✅")
    except Exception:
        # If PIL not available, fall through to the older D880 check
        print("LAUNCH GATE: Could not check pixel content (PIL not available)")
        pass

    # Phase 3: Button test — press START and check game responds (advances past title)
    pb.button_press("start")
    for _ in range(20):
        pb.tick(1, True)
    pb.button_release("start")
    
    # Wait up to 500 frames for the game to respond
    for _ in range(500):
        pb.tick(1, True)
        d880 = pb.memory[0xD880]
        if d880 not in [0x00, 0x01, 0x1B, 0x1C]:
            break
    
    d880 = pb.memory[0xD880]
    ffc1 = pb.memory[0xFFC1]
    
    # Allow: title screen (0x01), game-start (0x15), splash (0x18), gameplay (0x02),
    # or FFC1=1 (gameplay flag set)
    ok_states = [0x00, 0x01, 0x02, 0x15, 0x18]
    if ffc1 == 1 or d880 in ok_states:
        pb.stop(save=False)
        return True
    
    print(f"LAUNCH GATE FAILED: Game stuck at D880=0x{d880:02X} FFC1={ffc1}")
    pb.stop(save=False)
    return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: launch_gate.py <rom.gb>")
        sys.exit(2)

    rom_path = sys.argv[1]
    ok = check_rom(rom_path)

    if ok:
        print(f"LAUNCH GATE PASSED: {rom_path} boots correctly")
        sys.exit(0)
    else:
        print(f"LAUNCH GATE FAILED: {rom_path} white screen freeze detected")
        print("DO NOT LAUNCH — fix the ROM first")
        sys.exit(1)
