#!/usr/bin/env python3
"""
STEP 1: Boot-Time Palette Loading ONLY
Goal: Load ONE palette at boot, verify it's in RAM
No sprite assignment, no OAM hooks - just palette loading
"""
import sys
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
    print("STEP 1: Boot-Time Palette Loading ONLY")
    print("=" * 60)
    print("Goal: Load Palette 1 (SARA_W) at boot")
    print("No sprite assignment, no OAM hooks - just palette loading")
    print()
    
    rom = bytearray(input_rom_path.read_bytes())
    rom[0x143] = 0x80  # CGB-compatible flag
    
    # Palette 1: SARA_W (green/orange)
    sara_w_colors = ['transparent', 'green', 'orange', 'dark green']
    palette_1 = create_palette(sara_w_colors)
    
    print("📦 Palette Data:")
    print(f"   Colors: {sara_w_colors}")
    print(f"   Bytes: {[hex(b) for b in palette_1]}")
    print(f"   Expected in RAM:")
    for i, color in enumerate(sara_w_colors):
        val = parse_color(color)
        print(f"     Color {i}: 0x{val:04X} ({color})")
    print()
    
    # Store palette data in bank 13 (free space)
    palette_data_addr = 0x036C80  # Bank 13, file offset
    rom[palette_data_addr : palette_data_addr + 8] = palette_1
    print(f"💾 Stored palette data at ROM offset: 0x{palette_data_addr:06X} (bank 13)")
    
    # Boot loader: Load OBJ Palette 1 into palette RAM
    # Place loader in bank 13 (free space)
    # OBJ Palette 1 = index 8-15 (palette 0 = 0-7, palette 1 = 8-15)
    
    # Calculate bank 13 address for palette data (relative to bank start)
    palette_bank = 13
    palette_bank_addr = ((palette_data_addr - 0x034000) + 0x4000) & 0x7FFF
    
    boot_loader_code = bytearray([
        0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF,BC,DE,HL (save registers)
        
        # Load OBJ Palette 1 into palette RAM
        # Set palette index to 8 (Palette 1, color 0) with auto-increment
        0x3E, 0x88,              # LD A, 0x88 (bit 7=auto-increment, bit 6=OBJ palette, bits 0-5=index 8)
        0xE0, 0x6A,              # LDH [0xFF6A], A (OCPS - OBJ Color Palette Specification)
        
        # Load 4 colors (8 bytes) from ROM into palette RAM
        0x21, palette_bank_addr & 0xFF, (palette_bank_addr >> 8) & 0xFF,  # LD HL, palette_bank_addr (bank 13)
        0x0E, 0x08,              # LD C, 8 (8 bytes = 4 colors × 2 bytes)
        
        # Loop: Load byte from ROM, write to palette RAM
        0x2A,                    # LD A, [HL+] (load byte from ROM, increment HL)
        0xE0, 0x6B,              # LDH [0xFF6B], A (OCPD - OBJ Color Palette Data)
        0x0D,                    # DEC C
        0x20, 0xFA,              # JR NZ, -6 (loop until C=0)
        
        0xE1, 0xD1, 0xC1, 0xF1,  # POP HL,DE,BC,AF (restore registers)
        0xC9,                    # RET
    ])
    
    # Write boot loader to bank 13 (free space after palette data)
    boot_loader_offset = palette_data_addr + 16  # After palette data
    boot_loader_bank_addr = ((boot_loader_offset - 0x034000) + 0x4000) & 0x7FFF
    rom[boot_loader_offset : boot_loader_offset + len(boot_loader_code)] = boot_loader_code
    
    print(f"🔧 Boot loader code:")
    print(f"   Size: {len(boot_loader_code)} bytes")
    print(f"   Location: Bank 13 address 0x{boot_loader_bank_addr:04X}")
    print(f"   ROM offset: 0x{boot_loader_offset:06X}")
    print(f"   Function: Loads Palette 1 into CGB palette RAM (0xFF6A-0xFF6B)")
    print()
    
    # Hook boot entry at 0x0150
    # Replace code at 0x0150 with: switch to bank 13, call loader, restore bank, continue
    boot_hook_addr = 0x0150
    
    # Save original bytes (we'll skip over them after loader)
    original_bytes = rom[boot_hook_addr : boot_hook_addr + 5]
    
    # Entry hook: Switch bank, call loader, restore bank, skip original code
    entry_hook = bytearray([
        0x3E, palette_bank,      # LD A, 13
        0xEA, 0x00, 0x20,        # LD [0x2000], A (switch to bank 13)
        0xCD,                    # CALL loader in bank 13
        boot_loader_bank_addr & 0xFF,
        (boot_loader_bank_addr >> 8) & 0xFF,
        0x3E, 0x01,              # LD A, 1 (restore bank 1 - game's default)
        0xEA, 0x00, 0x20,        # LD [0x2000], A
        0xC3,                    # JP skip original code
        (boot_hook_addr + len(original_bytes)) & 0xFF,
        ((boot_hook_addr + len(original_bytes)) >> 8) & 0xFF,
    ])
    
    # Write entry hook at 0x0150
    rom[boot_hook_addr : boot_hook_addr + len(entry_hook)] = entry_hook
    
    print(f"🔗 Boot hook:")
    print(f"   Address: 0x{boot_hook_addr:04X}")
    print(f"   Original: {[hex(b) for b in original_bytes]}")
    print(f"   Patched: Switch to bank 13 → CALL loader → Restore bank → Continue")
    print(f"   Loader: Bank 13 address 0x{boot_loader_bank_addr:04X}")
    print()
    
    # Write ROM
    output_rom_path.parent.mkdir(parents=True, exist_ok=True)
    output_rom_path.write_bytes(bytes(rom))
    
    print("=" * 60)
    print("✅ STEP 1 Complete: Boot-Time Palette Loader Installed")
    print("=" * 60)
    print(f"   Output ROM: {output_rom_path}")
    print()
    print("📋 Next: Run verification script to check if palette is loaded")
    print("   python3 scripts/verify_step1.py")

if __name__ == '__main__':
    main()

