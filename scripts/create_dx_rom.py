#!/usr/bin/env python3
"""
Create Penta Dragon DX - Game Boy Color colorization
Generates a working CGB ROM with proper input handling and palette loading
"""
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def create_palette(c0: int, c1: int, c2: int, c3: int) -> bytes:
    """Convert 4 BGR555 colors to 8-byte palette data (little-endian)"""
    return bytes([
        c0 & 0xFF, (c0 >> 8) & 0xFF,
        c1 & 0xFF, (c1 >> 8) & 0xFF,
        c2 & 0xFF, (c2 >> 8) & 0xFF,
        c3 & 0xFF, (c3 >> 8) & 0xFF,
    ])


def main():
    # Paths
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    
    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        sys.exit(1)
    
    # Load ROM
    print(f"Loading ROM: {input_rom}")
    rom = bytearray(input_rom.read_bytes())
    
    # Apply display compatibility patches (fixes white screen freeze)
    print("Applying display compatibility patches...")
    rom, _ = apply_all_display_patches(rom)
    
    # Create 8 background palettes (saturated colors for visibility)
    print("Creating background palettes...")
    bg_palettes = bytearray()
    bg_palettes.extend(create_palette(0x7FFF, 0x03E0, 0x0280, 0x0000))  # 0: White→green→dark green→black
    bg_palettes.extend(create_palette(0x7FFF, 0x7C00, 0x5000, 0x2000))  # 1: White→red→dark red→darker
    bg_palettes.extend(create_palette(0x7FFF, 0x001F, 0x0014, 0x0008))  # 2: White→blue→dark blue→darker
    bg_palettes.extend(create_palette(0x7FFF, 0x7FE0, 0x5CC0, 0x2980))  # 3: White→yellow→orange→brown
    bg_palettes.extend(create_palette(0x7FFF, 0x03FF, 0x02BF, 0x015F))  # 4: White→cyan→teal→dark
    bg_palettes.extend(create_palette(0x7FFF, 0x7C1F, 0x5010, 0x2808))  # 5: White→magenta→purple→dark
    bg_palettes.extend(create_palette(0x7FFF, 0x5EF7, 0x3DEF, 0x1CE7))  # 6: White→light cyan→cyan→blue
    bg_palettes.extend(create_palette(0x7FFF, 0x6F7B, 0x4E73, 0x2D6B))  # 7: White→pink→purple→dark
    
    # Create 8 object/sprite palettes
    print("Creating object palettes...")
    obj_palettes = bytearray()
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x7E00, 0x4800))  # 0: Trans→white→orange→brown
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x03E0, 0x0100))  # 1: Trans→white→green→dark
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x7C00, 0x2000))  # 2: Trans→white→red→dark
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x001F, 0x0008))  # 3: Trans→white→blue→dark
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x7FE0, 0x2980))  # 4: Trans→white→yellow→brown
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x03FF, 0x015F))  # 5: Trans→white→cyan→dark
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x7C1F, 0x2808))  # 6: Trans→white→magenta→dark
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x7FE0, 0x4A00))  # 7: Trans→white→yellow→orange
    
    # Write palette data to bank 13 at 0x6C80 (file offset 0x036C80)
    print("Writing palette data to bank 13...")
    palette_data_offset = 0x036C80
    rom[palette_data_offset:palette_data_offset+len(bg_palettes)] = bg_palettes
    rom[palette_data_offset+len(bg_palettes):palette_data_offset+len(bg_palettes)+len(obj_palettes)] = obj_palettes
    
    # Save original input handler (46 bytes at 0x0824)
    print("Preserving original input handler...")
    original_input = rom[0x0824:0x0824+46]
    print(f"  Original input handler: {original_input.hex()}")
    
    # Create combined function in bank 13 at 0x6D00:
    # - Run original input handler code inline
    # - Then load CGB palettes
    print("Creating combined input+palette function in bank 13...")
    combined_function = original_input + bytes([
        # Load palettes (already in bank 13 context)
        0x21, 0x80, 0x6C,              # LD HL,6C80 - palette data address
        0x3E, 0x80,                    # LD A,80h - auto-increment
        0xE0, 0x68,                    # LDH [FF68],A - BCPS (BG palette index)
        0x0E, 0x40,                    # LD C,64 - 64 bytes (8 palettes × 8 bytes)
        0x2A, 0xE0, 0x69,              # loop: LD A,[HL+]; LDH [FF69],A - write to BCPD
        0x0D,                          # DEC C
        0x20, 0xFA,                    # JR NZ,loop
        0x3E, 0x80,                    # LD A,80h - auto-increment
        0xE0, 0x6A,                    # LDH [FF6A],A - OCPS (OBJ palette index)
        0x0E, 0x40,                    # LD C,64 - 64 bytes
        0x2A, 0xE0, 0x6B,              # loop: LD A,[HL+]; LDH [FF6B],A - write to OCPD
        0x0D,                          # DEC C
        0x20, 0xFA,                    # JR NZ,loop
        0xC9,                          # RET
    ])
    
    combined_offset = 0x036D00  # Bank 13 at 0x6D00
    rom[combined_offset:combined_offset+len(combined_function)] = combined_function
    print(f"  Combined function: {len(combined_function)} bytes at bank 13:0x6D00")
    
    # Create minimal trampoline at 0x0824 (only 18 bytes - well under 46-byte limit)
    # This switches to bank 13, calls combined function, restores bank 1
    print("Creating minimal trampoline at 0x0824...")
    trampoline = bytes([
        0xF5,                          # PUSH AF - save A register
        0x3E, 0x0D,                    # LD A,13 - bank 13
        0xEA, 0x00, 0x20,              # LD [2000],A - switch to bank 13
        0xF1,                          # POP AF - restore A register
        0xCD, 0x00, 0x6D,              # CALL 6D00 - call combined function
        0xF5,                          # PUSH AF - save A register
        0x3E, 0x01,                    # LD A,1 - bank 1
        0xEA, 0x00, 0x20,              # LD [2000],A - restore bank 1
        0xF1,                          # POP AF - restore A register
        0xC9,                          # RET
    ])
    
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    # Pad remaining space with NOPs (0x00)
    if len(trampoline) < 46:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    print(f"  Trampoline: {len(trampoline)} bytes (max 46)")
    print(f"  This is the ONLY code modification in bank 0/1")
    
    # Set CGB compatibility flag
    print("Setting CGB compatibility flag...")
    rom[0x143] = 0x80  # CGB compatible
    
    # Fix header checksum
    print("Fixing header checksum...")
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    print(f"  Checksum: 0x{chk:02X}")
    
    # Write output ROM
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    print(f"\n✓ Created: {output_rom}")
    print(f"  Size: {len(rom)} bytes")
    print("\nROM modifications:")
    print("  - Display patch at 0x0067 (CGB detection)")
    print("  - Trampoline at 0x0824 (18 bytes)")
    print("  - Palette data in bank 13 at 0x6C80 (128 bytes)")
    print("  - Combined function in bank 13 at 0x6D00 (74 bytes)")
    print("\nFeatures:")
    print("  - Preserves original input handling")
    print("  - Loads CGB color palettes every frame")
    print("  - No code overwrites in bank 0 (except 0x0824 slot)")


if __name__ == "__main__":
    main()
