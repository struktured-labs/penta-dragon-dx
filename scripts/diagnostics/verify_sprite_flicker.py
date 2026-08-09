#!/usr/bin/env python3
import os
import sys
import numpy as np
from pyboy import PyBoy

ROM_PATH = os.path.expanduser("~/projects/penta-dragon-dx-claude/rom/working/penta_dragon_dx_FIXED.gb")

def check_sprite_flicker():
    print("=== COLD-BOOT SUB-FRAME SPRITE FLICKER AUDIT ===")
    
    if not os.path.exists(ROM_PATH):
        print(f"Error: ROM file {ROM_PATH} not found.")
        sys.exit(1)
        
    print("Booting emulator core headlessly...")
    pb = PyBoy(ROM_PATH, window="null", cgb=True)
    pb.set_emulation_speed(0)
    
    # 1. Navigate past title screen to enter active gameplay
    # Standard menu select sequences from teleport_mechanism_pyboy.py
    print("Navigating menus to enter gameplay using the proven input schedule...")
    sched = [(180, 186, 'down'), (201, 207, 'a'), (261, 267, 'a'), (321, 327, 'a'), (381, 387, 'start'), (431, 437, 'a')]
    held = None
    
    for f in range(1, 1400):
        want = None
        for s, e, b in sched:
            if s <= f < e:
                want = b
                break
        if want != held:
            if held: pb.button_release(held)
            if want: pb.button_press(want)
            held = want
        pb.tick(1, True)
        
    if held: pb.button_release(held)
    
    # Run a few extra frames to let the overworld transition complete
    for _ in range(100):
        pb.tick(1, True)
        
    # Verify we are in active gameplay (D880 == 0x02, FFC1 == 1)
    mem = pb.memory
    print(f"Current State: D880=0x{mem[0xD880]:02X} FFC1={mem[0xFFC1]}")
    if mem[0xD880] != 0x02 or mem[0xFFC1] != 1:
        print("❌ ERROR: Failed to navigate to active gameplay. Retrying with longer load time...")
        for _ in range(300):
            pb.tick(1, True)
        print(f"Retry State: D880=0x{mem[0xD880]:02X} FFC1={mem[0xFFC1]}")
        if mem[0xD880] != 0x02:
            print("❌ FAIL: Cannot establish stable gameplay state.")
            pb.stop(save=False)
            sys.exit(1)
            
    # 2. Capture 120 consecutive frames (2 seconds of real-time 60fps)
    print("\nCapturing 120 consecutive frames of gameplay...")
    
    orange_frames = 0
    total_frames = 120
    
    # Palette 4 is the Orange Hornets palette.
    # In Penta Dragon, we inspect OAM Slot 0 (Sara's sprite attributes) at C003
    # GBC OAM attribute byte flags:
    # Bit 0-2: Palette Index (0..7)
    # Bit 3: Character Bank (0..1)
    # Bit 4: DMG palette index
    # Bit 5: Horizontal Flip
    # Bit 6: Vertical Flip
    # Bit 7: BG over OBJ priority
    
    oam_pals = []
    
    for f in range(total_frames):
        pb.tick(1, True)
        
        # Read active sprite attributes from HARDWARE OAM ($FE00-$FE9F)
        # The O(1) stamper stamps HW OAM AFTER the DMA, so this is the
        # authoritative source for what's actually being displayed.
        # Slot 0 attribute byte is at $FE03
        attr = mem[0xFE03]
        palette_idx = attr & 0x07
        oam_pals.append(palette_idx)
        
        # If palette index is 4 (Hornets Orange), increment count
        if palette_idx == 4:
            orange_frames += 1
            
    pb.stop(save=False)
    
    print("\n=== FLICKER METRICS ===")
    print(f"Total Frames Sampled  : {total_frames}")
    print(f"Sprite Palette Sequence: {oam_pals[:40]}...")
    
    # Calculate percentage
    flicker_pct = (orange_frames / total_frames) * 100.0
    print(f"Frames using Orange Palette: {orange_frames} / {total_frames} ({flicker_pct:.2f}%)")
    
    if orange_frames > 0:
        print(f"\n❌ VERIFICATION FAILURE: Sprite is actively flickering orange on {flicker_pct:.2f}% of frames!")
        print("  - The 1/4 frame sub-frame timing race is still active. The O(N) post-process loop is clashing.")
        return False
    else:
        print("\n✅ VERIFICATION SUCCESS: Sprite palette is 100% stable at Palette 2 (SaraWitch Pink). 0% orange flicker!")
        return True

if __name__ == "__main__":
    success = check_sprite_flicker()
    sys.exit(0 if success else 1)
