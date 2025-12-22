#!/usr/bin/env python3
"""
Minimal Test: ONE palette, ONE sprite
Professional approach: Start simple, verify each step
"""
import sys
import yaml
from pathlib import Path

def parse_color(c) -> int:
    """Parse color name or hex to BGR555"""
    COLOR_NAMES = {
        'black': 0x0000, 'white': 0x7FFF, 'red': 0x001F, 'green': 0x03E0,
        'blue': 0x7C00, 'yellow': 0x03FF, 'cyan': 0x7FE0, 'magenta': 0x7C1F,
        'transparent': 0x0000, 'orange': 0x021F, 'dark green': 0x0280,
    }
    if isinstance(c, int): 
        return c & 0x7FFF
    s = str(c).lower().strip().strip('"').strip("'")
    if s.startswith('0x'): 
        s = s[2:]
    if s in COLOR_NAMES: 
        return COLOR_NAMES[s]
    try:
        if len(s) == 4: 
            return int(s, 16) & 0x7FFF
    except: 
        pass
    return 0x7FFF

def create_palette(colors) -> bytes:
    """Create 8-byte palette (4 colors × 2 bytes each)"""
    data = bytearray()
    for c in colors[:4]:
        val = parse_color(c)
        data.append(val & 0xFF)
        data.append((val >> 8) & 0xFF)
    return bytes(data)

def main():
    input_rom_path = Path("rom/Penta Dragon (J).gb")
    output_rom_path = Path("rom/working/Penta Dragon (J).gb")
    
    print("=" * 60)
    print("Minimal Test: ONE Palette, ONE Sprite")
    print("=" * 60)
    
    rom = bytearray(input_rom_path.read_bytes())
    rom[0x143] = 0x80  # CGB-compatible flag
    
    # STEP 1: Load ONE palette (Palette 1: SARA_W green/orange)
    print("\n📦 Step 1: Loading Palette 1 (SARA_W)")
    sara_w_colors = ['transparent', 'green', 'orange', 'dark green']
    palette_1 = create_palette(sara_w_colors)
    
    # Write palette to OBJ Palette 1 (0xFF6A-0xFF6B)
    # OBJ Palette 1 starts at index 8 (palette 0 = 0-7, palette 1 = 8-15)
    palette_data_addr = 0x036C80  # Free space in ROM
    
    # Store palette data in ROM
    rom[palette_data_addr : palette_data_addr + 8] = palette_1
    
    print(f"   Palette data: {[hex(b) for b in palette_1]}")
    print(f"   Stored at ROM offset: 0x{palette_data_addr:06X}")
    
    # STEP 2: Boot loader - Load palette into RAM
    print("\n🔧 Step 2: Creating boot loader")
    boot_loader_code = bytearray([
        0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF,BC,DE,HL (save registers)
        
        # Load OBJ Palette 1 into palette RAM
        # Set palette index to 8 (Palette 1, color 0)
        0x3E, 0x88,              # LD A, 0x88 (auto-increment, OBJ palette, index 8)
        0xE0, 0x6A,              # LDH [0xFF6A], A
        
        # Load 4 colors (8 bytes) from ROM
        0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF,  # LD HL, palette_data_addr
        0x0E, 0x08,              # LD C, 8 (8 bytes)
        0x2A,                    # LD A, [HL+] (load byte, increment HL)
        0xE0, 0x6B,              # LDH [0xFF6B], A (write to palette data)
        0x0D,                    # DEC C
        0x20, 0xFA,              # JR NZ, loop (continue until C=0)
        
        0xE1, 0xD1, 0xC1, 0xF1,  # POP HL,DE,BC,AF (restore registers)
        0xC9,                    # RET
    ])
    
    boot_loader_addr = 0x0150  # Hook point (after boot, before game starts)
    boot_loader_offset = palette_data_addr + 16  # After palette data
    
    # Write boot loader to ROM
    rom[boot_loader_offset : boot_loader_offset + len(boot_loader_code)] = boot_loader_code
    
    # Hook boot entry to call loader
    rom[boot_loader_addr : boot_loader_addr + 3] = [
        0xCD,  # CALL
        boot_loader_offset & 0xFF,
        (boot_loader_offset >> 8) & 0xFF
    ]
    
    print(f"   Boot loader at: 0x{boot_loader_offset:06X}")
    print(f"   Hooked at: 0x{boot_loader_addr:04X}")
    
    # STEP 3: Sprite loop - Assign Palette 1 to tiles 4-7
    print("\n🎯 Step 3: Creating sprite loop")
    sprite_loop_code = bytearray([
        0xF5, 0xC5, 0xE5,  # PUSH AF,BC,HL
        
        # Iterate OAM (0xFE00-0xFE9F, 40 sprites × 4 bytes)
        0x21, 0x00, 0xFE,  # LD HL, 0xFE00 (OAM start)
        0x0E, 0x28,         # LD C, 40 (40 sprites)
        
        # Loop: Check each sprite
        0x7E,               # LD A, [HL] (Y position)
        0xFE, 0x00,         # CP 0 (sprite off-screen?)
        0x28, 0x0A,         # JR Z, skip (if Y=0, skip sprite)
        
        # Check tile ID (byte 2)
        0x23,               # INC HL (skip to byte 2)
        0x7E,               # LD A, [HL] (tile ID)
        0xFE, 0x04,         # CP 4
        0x38, 0x05,         # JR C, skip (if tile < 4, skip)
        0xFE, 0x08,         # CP 8
        0x30, 0x01,         # JR NC, skip (if tile >= 8, skip)
        
        # Set palette bit to 1 (tiles 4-7)
        0x23,               # INC HL (skip to byte 3)
        0x7E,               # LD A, [HL] (flags)
        0xE6, 0xF8,         # AND 0xF8 (clear palette bits)
        0xF6, 0x01,         # OR 0x01 (set palette to 1)
        0x77,               # LD [HL], A (write back)
        0x2B,               # DEC HL (back to byte 2)
        
        # Skip to next sprite
        0x23,               # INC HL (to byte 3)
        0x23,               # INC HL (to next sprite)
        0x0D,               # DEC C
        0x20, 0xE0,         # JR NZ, loop
        
        0xE1, 0xC1, 0xF1,   # POP HL,BC,AF
        0xC9,               # RET
    ])
    
    sprite_loop_offset = boot_loader_offset + len(boot_loader_code) + 4
    rom[sprite_loop_offset : sprite_loop_offset + len(sprite_loop_code)] = sprite_loop_code
    
    # Hook OAM DMA completion (0x4197) to run sprite loop
    oam_dma_ret = 0x4197
    if rom[oam_dma_ret] == 0xC9:  # RET instruction
        rom[oam_dma_ret : oam_dma_ret + 3] = [
            0xCD,  # CALL
            sprite_loop_offset & 0xFF,
            (sprite_loop_offset >> 8) & 0xFF
        ]
        print(f"   Sprite loop at: 0x{sprite_loop_offset:06X}")
        print(f"   Hooked OAM DMA completion at: 0x{oam_dma_ret:04X}")
    else:
        print(f"   ⚠️  Warning: Expected RET at 0x{oam_dma_ret:04X}, found 0x{rom[oam_dma_ret]:02X}")
    
    # STEP 4: Patch DMG palette registers (prevent interference)
    print("\n🛡️  Step 4: Patching DMG palette registers")
    dmg_patches = 0
    for addr in range(0x4000, len(rom) - 2):
        # Look for writes to FF47, FF48, FF49 (DMG palettes)
        if rom[addr] == 0xE0:  # LDH [imm8], A
            reg = rom[addr + 1]
            if reg in [0x47, 0x48, 0x49]:  # DMG palette registers
                rom[addr + 1] = 0x00  # Change to FF00 (unused register)
                dmg_patches += 1
                if dmg_patches <= 5:
                    print(f"   Patched DMG palette write at 0x{addr:04X}")
    
    if dmg_patches > 5:
        print(f"   ... and {dmg_patches - 5} more patches")
    
    # Write ROM
    output_rom_path.parent.mkdir(parents=True, exist_ok=True)
    output_rom_path.write_bytes(bytes(rom))
    
    print("\n" + "=" * 60)
    print("✅ Minimal Test ROM Created")
    print("=" * 60)
    print(f"   Output: {output_rom_path}")
    print(f"   Palette 1: {sara_w_colors}")
    print(f"   Tiles 4-7 → Palette 1")
    print(f"   Boot loader: Loads palette at startup")
    print(f"   Sprite loop: Assigns palette after OAM DMA")
    print("\n📋 Next: Run automated verification")

if __name__ == '__main__':
    main()

