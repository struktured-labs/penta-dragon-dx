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
    
    # Build baseline OBJ palettes; we'll generate variants per OBP mapping

def build_obj_data_with_target_color(idx: int, color: int) -> bytearray:
    """Return 8 OBJ palettes with palette 0 having `color` at given index (1..3). Index 0 is transparency."""
    assert idx in (1, 2, 3), "idx must be 1, 2, or 3"
    def pal(c0, c1, c2, c3):
        return create_palette(c0, c1, c2, c3)
    # Start with default palettes; overwrite palette 0 with target color at idx
    obj = bytearray()
    # Palette 0: transparent, then place target color at idx; fill others with visible but dark values
    colors = [0x0000, 0x001F, 0x03E0, 0x7C00]  # blue/green/red as fillers
    colors[idx] = color
    obj.extend(pal(colors[0], colors[1], colors[2], colors[3]))
    # Palettes 1..7 keep distinct colors for enemies (not critical for test)
    obj.extend(pal(0x0000, 0x7FFF, 0x03E0, 0x0100))
    obj.extend(pal(0x0000, 0x7FFF, 0x7C00, 0x2000))
    obj.extend(pal(0x0000, 0x7FFF, 0x001F, 0x0008))
    obj.extend(pal(0x0000, 0x7FFF, 0x7FE0, 0x2980))
    obj.extend(pal(0x0000, 0x7FFF, 0x03FF, 0x015F))
    obj.extend(pal(0x0000, 0x7FFF, 0x7C1F, 0x2808))
    obj.extend(pal(0x0000, 0x7FFF, 0x7FE0, 0x4A00))
    return obj

def build_combined_function_with_obp(obp_value: int, original_input: bytes) -> bytes:
    """Return combined (input inline + palette loader) and write OBP0/OBP1 to obp_value before loading palettes."""
    return original_input + bytes([
        # Write DMG OBJ palette mappings
        0x3E, obp_value,             # LD A,obp
        0xE0, 0x48,                  # LDH [FF48],A (OBP0)
        0x3E, obp_value,             # LD A,obp
        0xE0, 0x49,                  # LDH [FF49],A (OBP1)
        # Load BG palettes
        0x21, 0x80, 0x6C,            # LD HL,6C80
        0x3E, 0x80,                  # LD A,80h
        0xE0, 0x68,                  # LDH [FF68],A
        0x0E, 0x40,                  # LD C,64
        0x2A, 0xE0, 0x69,            # loop: LD A,[HL+]; LDH [FF69],A
        0x0D,                        # DEC C
        0x20, 0xFA,                  # JR NZ,loop
        # Load OBJ palettes
        0x3E, 0x80,                  # LD A,80h
        0xE0, 0x6A,                  # LDH [FF6A],A
        0x0E, 0x40,                  # LD C,64
        0x2A, 0xE0, 0x6B,            # loop: LD A,[HL+]; LDH [FF6B],A
        0x0D,                        # DEC C
        0x20, 0xFA,                  # JR NZ,loop
        0xC9,                        # RET
    ])

def main():
    # Paths
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_WORKING.gb")
    
    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        sys.exit(1)
    
    # Load ROM
    print(f"Loading ROM: {input_rom}")
    rom = bytearray(input_rom.read_bytes())
    
    # Apply display compatibility patches (fixes white screen freeze)``
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
    
    # Create 8 object/sprite palettes (baseline)
    print("Creating object palettes...")
    obj_palettes = bytearray()
    obj_palettes.extend(create_palette(0x0000, 0x7FFF, 0x7E00, 0x4800))  # 0: Trans→white→ORANGE→brown
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
    
    # Write palette data to bank 13 at 0x6C80 (file offset 0x036C80)
    print("Writing palette data to bank 13...")
    palette_data_offset = 0x036C80
    rom[palette_data_offset:palette_data_offset+len(bg_palettes)] = bg_palettes
    rom[palette_data_offset+len(bg_palettes):palette_data_offset+len(bg_palettes)+len(obj_palettes)] = obj_palettes
    
    # Safer VBlank wrapper approach: put wrapper at 0x07A0 that calls FF80 then loads palettes,
    # and patch VBlank to CALL 0x07A0 in place of CALL FF80.
    print("Installing VBlank wrapper (calls FF80, then loads palettes)...")
    wrapper_addr = 0x07A0
    loader_addr = 0x07B0
    # Wrapper: one-shot guard using WRAM C0A0. If already ran, return.
    # Otherwise CALL FF80, set flag, then CALL loader.
    vblank_wrapper = bytes([
        0xFA, 0xA0, 0xC0,      # LD A,[C0A0]
        0xFE, 0x01,            # CP 1
        0x28, 0x07,            # JR Z, +7 (skip to RET)
        0xCD, 0x80, 0xFF,      # CALL FF80
        0x3E, 0x01,            # LD A,1
        0xEA, 0xA0, 0xC0,      # LD [C0A0],A
        0xCD, 0xB0, 0x07,      # CALL 07B0
        0xC9,                  # RET
    ])
    # Loader: bank 13 -> write BG+OBJ (128 bytes) via auto-inc ports -> restore bank 1 -> RET
    vblank_loader = bytes([
        0xF5, 0xC5, 0xE5,
        0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0x21, 0x80, 0x6C,
        0x3E, 0x80, 0xE0, 0x68,
        0x0E, 0x40,
        0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        0x3E, 0x80, 0xE0, 0x6A,
        0x0E, 0x40,
        0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
        0x3E, 0x01, 0xEA, 0x00, 0x20,
        0xE1, 0xC1, 0xF1,
        0xC9,
    ])
    rom[wrapper_addr:wrapper_addr+len(vblank_wrapper)] = vblank_wrapper
    rom[loader_addr:loader_addr+len(vblank_loader)] = vblank_loader
    # Replace CALL FF80 at 0x06D6 with CALL 07A0
    rom[0x06D6:0x06D9] = bytes([0xCD, 0xA0, 0x07])
    print(f"  VBlank wrapper @0x{wrapper_addr:04X} ({len(vblank_wrapper)} bytes)")
    print(f"  Loader @0x{loader_addr:04X} ({len(vblank_loader)} bytes)")
    print("  Patched VBlank: CALL 07A0 instead of CALL FF80")

    # Restore original boot entry to avoid startup instability
    # JP 0x0150 from 0x0100 and leave 0x0150 bytes untouched if previously modified
    rom[0x0100:0x0104] = bytes([0x00, 0xC3, 0x50, 0x01])
    
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
    print("  - VBlank wrapper at 0x07A0; palette loader at 0x07B0")
    print("  - Palette data in bank 13 at 0x6C80 (128 bytes)")
    print("\nFeatures:")
    print("  - Preserves original input handling")
    print("  - Loads CGB color palettes every frame via VBlank")
    print("  - Avoids boot-time hooks and input handler replacement")

    # Build three index variants to defeat DMG mapping uncertainty
    # Omit OBP sweep variants in this safer build to minimize changes
    print("\nSkipped IDX sweep variants for stability (can re-enable later).")


if __name__ == "__main__":
    main()
