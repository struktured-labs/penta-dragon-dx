#!/usr/bin/env python3
"""
Option 4: Hook at level load (0x3B69)
This function is ONLY called during gameplay, not menu initialization.
It should be safe to inject palette loading here.
"""

import sys
sys.path.insert(0, 'src')
from penta_dragon_dx.display_patcher import apply_all_display_patches

def pal(c0, c1, c2, c3):
    """Convert 4 BGR555 colors to 8 bytes"""
    return bytes([
        c0 & 0xFF, (c0 >> 8) & 0xFF,
        c1 & 0xFF, (c1 >> 8) & 0xFF,
        c2 & 0xFF, (c2 >> 8) & 0xFF,
        c3 & 0xFF, (c3 >> 8) & 0xFF,
    ])

# Load original ROM
rom = bytearray(open("rom/Penta Dragon (J).gb", "rb").read())
rom, _ = apply_all_display_patches(rom)

# BG palettes - colorful dungeons
bg_data = bytearray()
bg_data.extend(pal(0x7FFF, 0x03E0, 0x0280, 0x0000))  # Green dungeon
bg_data.extend(pal(0x7FFF, 0x7C00, 0x5000, 0x2000))  # Red/lava
bg_data.extend(pal(0x7FFF, 0x001F, 0x0014, 0x0008))  # Blue/water
bg_data.extend(pal(0x7FFF, 0x7FE0, 0x5CC0, 0x2980))  # Yellow/desert
bg_data.extend(pal(0x7FFF, 0x03FF, 0x02BF, 0x015F))  # Cyan/ice
bg_data.extend(pal(0x7FFF, 0x7C1F, 0x5010, 0x2808))  # Magenta/castle
bg_data.extend(pal(0x7FFF, 0x5EF7, 0x3DEF, 0x1CE7))  # Light cyan/sky
bg_data.extend(pal(0x7FFF, 0x6F7B, 0x4E73, 0x2D6B))  # Pink/boss

# OBJ palettes - distinct character colors
obj_data = bytearray()
obj_data.extend(pal(0x0000, 0x7FFF, 0x7E00, 0x4800))  # Player: white/orange/brown
obj_data.extend(pal(0x0000, 0x7FFF, 0x03E0, 0x0100))  # Enemy: white/green
obj_data.extend(pal(0x0000, 0x7FFF, 0x7C00, 0x2000))  # Enemy: white/red
obj_data.extend(pal(0x0000, 0x7FFF, 0x001F, 0x0008))  # Enemy: white/blue
obj_data.extend(pal(0x0000, 0x7FFF, 0x7FE0, 0x2980))  # Enemy: white/yellow
obj_data.extend(pal(0x0000, 0x7FFF, 0x03FF, 0x015F))  # Enemy: white/cyan
obj_data.extend(pal(0x0000, 0x7FFF, 0x7C1F, 0x2808))  # Boss: white/magenta
obj_data.extend(pal(0x0000, 0x7FFF, 0x4DEF, 0x2108))  # Special: white/light blue

# Write palette data to bank 13 @ 0x6C80
rom[0x036C80:0x036C80+len(bg_data)] = bg_data
rom[0x036C80+len(bg_data):0x036C80+len(bg_data)+len(obj_data)] = obj_data

print("✓ Palette data written to bank 13 @ 0x6C80")

# ONE-TIME palette loader in bank 13 @ 0x6D00
# Uses WRAM flag at C0A0 to ensure it only runs once
one_time_loader = bytes([
    # Check if already loaded
    0xFA, 0xA0, 0xC0,              # LD A,[C0A0]
    0xFE, 0x01,                    # CP 1
    0x28, 0x32,                    # JR Z,+50 (skip if already loaded)
    
    # Mark as loaded
    0x3E, 0x01,                    # LD A,1
    0xEA, 0xA0, 0xC0,              # LD [C0A0],A
    
    # Save registers
    0xF5, 0xC5, 0xE5,              # PUSH AF,BC,HL
    
    # We're already in bank 13 (caller switched us here)
    
    # Load palette data address
    0x21, 0x80, 0x6C,              # LD HL,6C80
    
    # Load BG palettes
    0x3E, 0x80,                    # LD A,80h
    0xE0, 0x68,                    # LDH [FF68],A
    0x0E, 0x40,                    # LD C,64
    0x2A, 0xE0, 0x69,              # loop: LD A,[HL+]; LDH [FF69],A
    0x0D,                          # DEC C
    0x20, 0xFA,                    # JR NZ,loop
    
    # Load OBJ palettes
    0x3E, 0x80,                    # LD A,80h
    0xE0, 0x6A,                    # LDH [FF6A],A
    0x0E, 0x40,                    # LD C,64
    0x2A, 0xE0, 0x6B,              # loop: LD A,[HL+]; LDH [FF6B],A
    0x0D,                          # DEC C
    0x20, 0xFA,                    # JR NZ,loop
    
    # Restore registers
    0xE1, 0xC1, 0xF1,              # POP HL,BC,AF
    
    # Now call original 40A0 (VRAM clear) that 3B69 was supposed to call
    0xCD, 0xA0, 0x40,              # CALL 40A0
    
    # Return to caller
    0xC9,                          # RET
])

rom[0x036D00:0x036D00+len(one_time_loader)] = one_time_loader
print(f"✓ One-time loader at bank 13 @ 0x6D00 ({len(one_time_loader)} bytes)")

# Hook 0x3B69 (level load function)
# Original code:
#   3B69: CD A0 40    CALL 40A0  ; VRAM clear
#   3B6C: CD 16 0A    CALL 0A16  ; Some other function
#   3B6F: C3 62 01    JP 0162    ; Jump elsewhere
#
# We'll replace the first CALL with a jump to our trampoline

# Trampoline at 0x07E0 (bank 0 free space)
trampoline = bytes([
    # Save AF (we need it for bank switch)
    0xF5,                          # PUSH AF
    
    # Switch to bank 13
    0x3E, 0x0D,                    # LD A,13
    0xEA, 0x00, 0x20,              # LD [2000],A
    
    # Restore AF
    0xF1,                          # POP AF
    
    # Call our one-time loader (which will call 40A0)
    0xCD, 0x00, 0x6D,              # CALL 6D00
    
    # Save AF again
    0xF5,                          # PUSH AF
    
    # Restore bank 1
    0x3E, 0x01,                    # LD A,1
    0xEA, 0x00, 0x20,              # LD [2000],A
    
    # Restore AF
    0xF1,                          # POP AF
    
    # Continue with rest of 0x3B69
    # Call 0A16
    0xCD, 0x16, 0x0A,              # CALL 0A16
    
    # Jump to 0162
    0xC3, 0x62, 0x01,              # JP 0162
])

rom[0x07E0:0x07E0+len(trampoline)] = trampoline
print(f"✓ Trampoline at 0x07E0 ({len(trampoline)} bytes)")

# Replace 0x3B69 with JP to our trampoline
rom[0x3B69:0x3B6C] = bytes([0xC3, 0xE0, 0x07])  # JP 07E0
print("✓ Hooked 0x3B69 → 0x07E0")

# Set CGB flag
rom[0x143] = 0x80

# Fix checksum
chk = 0
for i in range(0x134, 0x14D):
    chk = (chk - rom[i] - 1) & 0xFF
rom[0x14D] = chk

# Write final ROM
output_path = "rom/working/penta_dragon_dx_WORKING.gb"
with open(output_path, "wb") as f:
    f.write(rom)

print(f"\n✅ ROM created: {output_path}")
print("\n🎯 OPTION 4: Level Load Hook")
print("   - 0x3B69 is ONLY called during gameplay (not menu)")
print("   - One-time loader with WRAM flag at C0A0")
print("   - Should NOT crash menu")
print("   - Palettes load when first level starts")
print("\n🧪 Test by loading a level (not just menu)")
