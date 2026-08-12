#!/usr/bin/env python3
"""Compare v3.02 vs v3.03 screenshots."""
from pyboy import PyBoy
import os, sys

def boot_and_navigate(rom_path):
    pb = PyBoy(rom_path, window="null", cgb=True)
    pb.set_emulation_speed(0)
    
    sched = [(180, 186, 'down'), (201, 207, 'a'), (261, 267, 'a'), (321, 327, 'a'), 
             (381, 387, 'start'), (431, 437, 'a')]
    held = None
    for f in range(1, 1800):
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
    for _ in range(100):
        pb.tick(1, True)
    
    mem = pb.memory
    print(f"  State: D880=0x{mem[0xD880]:02X} FFC1={mem[0xFFC1]}")
    
    # Read all OAM to find sprites
    sprites = []
    for slot in range(40):
        base = 0xFE00 + slot * 4
        y = mem[base]
        x = mem[base+1]
        tile = mem[base+2]
        attr = mem[base+3]
        if y > 0 and y < 160:
            pal = attr & 0x07
            sprites.append({"slot": slot, "y": y, "x": x, "tile": tile, "pal": pal})
    
    return pb, sprites

# Test v302
print("=== v3.02 FIXED.gb ===")
pb302, sp302 = boot_and_navigate("rom/working/penta_dragon_dx_FIXED.gb")
print(f"  Sprites found: {len(sp302)}")
for s in sp302[:8]:
    print(f"  Slot {s['slot']}: Y={s['y']} X={s['x']} Tile=0x{s['tile']:02X} pal={s['pal']}")

# Get screen
try:
    from PIL import Image
    import numpy as np
    
    # v302 screen
    screen302 = pb302.screen
    # screen is a pyboy Screen object, needs to be rendered first
    screen302_image = screen302.image
    img302 = Image.fromarray(np.array(screen302_image)).convert('RGB')
    img302.save("/tmp/v302_gameplay.png")
    print(f"  v302 screen saved: {img302.size}")
    
    # Check pixel colors at sprite area
    arr302 = np.array(img302)
    # Sara is at Y=80, X=80 area, 16x16 sprite (tiles 0x24-0x27)
    sara_area = arr302[72:104, 72:104]  # rough crop
    has_pink = np.any((sara_area[:,:,0] > 180) & (sara_area[:,:,1] < 120) & (sara_area[:,:,2] > 60))
    has_blue = np.any((sara_area[:,:,2] > 150) & (sara_area[:,:,0] < 60) & (sara_area[:,:,1] < 80))
    if has_pink:
        print("  ✓ Sara area has PINK pixels")
    if has_blue:
        print("  ✓ Sara area has BLUE pixels")
    
    avg_color = sara_area.mean(axis=(0,1))
    print(f"  Avg color in Sara area: R={avg_color[0]:.0f} G={avg_color[1]:.0f} B={avg_color[2]:.0f}")
    
except ImportError:
    print("  Can't import PIL/numpy for screen analysis")

pb302.stop(save=False)
print()

# Test v303
print("=== v3.03 v303.gb ===")
pb303, sp303 = boot_and_navigate("rom/working/penta_dragon_dx_v303.gb")
print(f"  Sprites found: {len(sp303)}")
for s in sp303[:8]:
    print(f"  Slot {s['slot']}: Y={s['y']} X={s['x']} Tile=0x{s['tile']:02X} pal={s['pal']}")

try:
    screen303 = pb303.screen
    screen303_image = screen303.image
    img303 = Image.fromarray(np.array(screen303_image)).convert('RGB')
    img303.save("/tmp/v303_gameplay.png")
    print(f"  v303 screen saved: {img303.size}")
    
    arr303 = np.array(img303)
    sara_area303 = arr303[72:104, 72:104]
    has_pink = np.any((sara_area303[:,:,0] > 180) & (sara_area303[:,:,1] < 120) & (sara_area303[:,:,2] > 60))
    has_blue = np.any((sara_area303[:,:,2] > 150) & (sara_area303[:,:,0] < 60) & (sara_area303[:,:,1] < 80))
    if has_pink:
        print("  ✓ Sara area has PINK pixels")
    if has_blue:
        print("  ✓ Sara area has BLUE pixels")
    
    avg_color303 = sara_area303.mean(axis=(0,1))
    print(f"  Avg color in Sara area: R={avg_color303[0]:.0f} G={avg_color303[1]:.0f} B={avg_color303[2]:.0f}")
    
    # Compare
    if np.array_equal(arr302, arr303):
        print("\n  ⚠ SCREENS ARE IDENTICAL!")
    else:
        diff = np.abs(arr302.astype(int) - arr303.astype(int))
        diff_pixels = np.sum(diff > 5) / 3
        print(f"\n  ⚠ Screens differ: {diff_pixels} pixels with >5 difference")
        
except Exception as e:
    print(f"  Error analyzing screen: {e}")

pb303.stop(save=False)
