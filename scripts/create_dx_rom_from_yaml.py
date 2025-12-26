#!/usr/bin/env python3
"""
Create Penta Dragon DX from YAML palette configuration
Loads palettes from palettes/penta_palettes.yaml for easy customization
"""
import sys
from pathlib import Path
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def hex_to_bgr555(hex_str: str) -> int:
    """Convert 4-digit hex string to BGR555 integer"""
    return int(hex_str, 16)


def bgr555_to_bytes(color: int) -> bytes:
    """Convert BGR555 integer to little-endian bytes"""
    return bytes([color & 0xFF, (color >> 8) & 0xFF])


def palette_to_bytes(colors: list[str]) -> bytes:
    """Convert list of 4 hex color strings to 8-byte palette data"""
    if len(colors) != 4:
        raise ValueError(f"Palette must have exactly 4 colors, got {len(colors)}")
    
    result = bytearray()
    for hex_color in colors:
        color = hex_to_bgr555(hex_color)
        result.extend(bgr555_to_bytes(color))
    return bytes(result)


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytes, bytes]:
    """
    Load palettes from YAML file and return (bg_palettes, obj_palettes) as bytes
    Returns 64 bytes each (8 palettes × 8 bytes per palette)
    """
    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
    bg_palettes = bytearray()
    obj_palettes = bytearray()
    
    # Load BG palettes (8 palettes required)
    bg_config = config.get('bg_palettes', {})
    bg_entries = []
    
    for key, value in bg_config.items():
        if isinstance(value, dict) and 'colors' in value:
            bg_entries.append((key, value['colors'], value.get('name', key)))
    
    if len(bg_entries) < 8:
        print(f"Warning: Only {len(bg_entries)} BG palettes defined, need 8")
        print("  Filling remaining with default palettes")
        # Fill with defaults
        default = ["7FFF", "5294", "2108", "0000"]  # White to black gradient
        while len(bg_entries) < 8:
            bg_entries.append((f"Default{len(bg_entries)}", default, "Default"))
    
    print("\nBackground Palettes:")
    for i, (key, colors, name) in enumerate(bg_entries[:8]):
        print(f"  {i}: {name} ({key})")
        bg_palettes.extend(palette_to_bytes(colors))
    
    # Load OBJ/Sprite palettes (8 palettes required)
    obj_config = config.get('obj_palettes', {})
    obj_entries = []
    
    for key, value in obj_config.items():
        if isinstance(value, dict) and 'colors' in value:
            obj_entries.append((key, value['colors'], value.get('name', key)))
    
    if len(obj_entries) < 8:
        print(f"\nWarning: Only {len(obj_entries)} OBJ palettes defined, need 8")
        print("  Filling remaining with default palettes")
        # Fill with defaults
        default = ["0000", "7FFF", "5294", "2108"]  # Transparent, white to dark
        while len(obj_entries) < 8:
            obj_entries.append((f"Default{len(obj_entries)}", default, "Default"))
    
    print("\nSprite/Object Palettes:")
    for i, (key, colors, name) in enumerate(obj_entries[:8]):
        print(f"  {i}: {name} ({key})")
        obj_palettes.extend(palette_to_bytes(colors))
    
    return bytes(bg_palettes), bytes(obj_palettes)


def main():
    # Paths
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes.yaml")
    
    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        sys.exit(1)
    
    if not palette_yaml.exists():
        print(f"ERROR: Palette configuration not found: {palette_yaml}")
        sys.exit(1)
    
    # Load ROM
    print(f"Loading ROM: {input_rom}")
    rom = bytearray(input_rom.read_bytes())
    
    # Apply display compatibility patches (fixes white screen freeze)
    print("Applying display compatibility patches...")
    rom, _ = apply_all_display_patches(rom)
    
    # Load palettes from YAML
    print(f"\nLoading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes = load_palettes_from_yaml(palette_yaml)
    
    # Write palette data to bank 13 at 0x6C80 (file offset 0x036C80)
    print("\nWriting palette data to bank 13...")
    palette_data_offset = 0x036C80
    rom[palette_data_offset:palette_data_offset+len(bg_palettes)] = bg_palettes
    rom[palette_data_offset+len(bg_palettes):palette_data_offset+len(bg_palettes)+len(obj_palettes)] = obj_palettes
    
    # Save original input handler (46 bytes at 0x0824)
    print("\nPreserving original input handler...")
    original_input = rom[0x0824:0x0824+46]
    
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
    
    # Set CGB compatibility flag
    print("Setting CGB compatibility flag...")
    rom[0x143] = 0x80  # CGB compatible
    
    # Fix header checksum
    print("Fixing header checksum...")
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    
    # Write output ROM
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    print(f"\n✓ Created: {output_rom}")
    print(f"  Size: {len(rom)} bytes ({len(rom)//1024}KB)")
    print("\nTo customize palettes:")
    print(f"  1. Edit {palette_yaml}")
    print(f"  2. Run this script again")
    print(f"  3. Test in emulator: mgba-qt {output_rom}")


if __name__ == "__main__":
    main()
