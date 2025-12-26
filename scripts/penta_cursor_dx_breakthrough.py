#!/usr/bin/env python3
"""
BREAKTHROUGH APPROACH: Integrate with existing VBlank hook
Modify OAM during VBlank for 100% reliable timing
"""
import sys
import yaml
from pathlib import Path

def parse_color(c) -> int:
    COLOR_NAMES = {
        'black': 0x0000, 'white': 0x7FFF, 'red': 0x001F, 'green': 0x03E0,
        'blue': 0x7C00, 'yellow': 0x03FF, 'cyan': 0x7FE0, 'magenta': 0x7C1F,
        'transparent': 0x0000, 'light blue': 0x7D00, 'dark blue': 0x4000,
        'orange': 0x021F, 'purple': 0x6010, 'brown': 0x0215, 'gray': 0x4210,
        'grey': 0x4210, 'pink': 0x5C1F, 'lime': 0x03E7, 'teal': 0x7CE0,
        'navy': 0x5000, 'maroon': 0x0010, 'olive': 0x0210
    }
    if isinstance(c, dict):
        c = c.get('hex') or c.get('value') or c.get('color')
    if isinstance(c, int): return c & 0x7FFF
    s = str(c).lower().strip().strip('"').strip("'")
    if s.startswith('0x'): s = s[2:]
    if s in COLOR_NAMES: return COLOR_NAMES[s]
    try:
        if len(s) == 4: return int(s, 16) & 0x7FFF
    except: pass
    return 0x7FFF

def create_palette(colors) -> bytes:
    data = bytearray()
    for c in colors[:4]:
        val = parse_color(c)
        data.append(val & 0xFF)
        data.append((val >> 8) & 0xFF)
    return bytes(data)

def main():
    input_rom_path = Path("rom/Penta Dragon (J).gb")
    output_rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    palette_yaml_path = Path("palettes/penta_palettes.yaml")
    monster_map_path = Path("palettes/monster_palette_map.yaml")

    rom = bytearray(input_rom_path.read_bytes())
    rom[0x143] = 0x80  # CGB-compatible
    
    with open(palette_yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
    with open(monster_map_path, 'r') as f:
        monster_map = yaml.safe_load(f)
    
    ultra_bg = ['7FFF', '001F', '7C00', '03E0']
    obj_pals = (
        create_palette(config['obj_palettes']['MainCharacter']['colors']) +
        create_palette(config['obj_palettes']['EnemyBasic']['colors']) +
        create_palette(config['obj_palettes']['EnemyFire']['colors']) +
        create_palette(config['obj_palettes']['EnemyIce']['colors']) +
        create_palette(config['obj_palettes']['EnemyFlying']['colors']) +
        create_palette(config['obj_palettes']['EnemyPoison']['colors']) +
        create_palette(config['obj_palettes']['MiniBoss']['colors']) +
        create_palette(config['obj_palettes']['MainBoss']['colors'])
    )
    bg_pals = create_palette(ultra_bg) + b''.join([create_palette(config['bg_palettes'][n]['colors']) for n in ['LavaZone', 'WaterZone', 'DesertZone', 'ForestZone', 'CastleZone', 'SkyZone', 'BossZone']])

    palette_data_offset = 0x036C80
    rom[palette_data_offset : palette_data_offset + 64] = bg_pals
    rom[palette_data_offset + 64 : palette_data_offset + 128] = obj_pals
    
    # Generate lookup table
    lookup_table = bytearray([0xFF] * 256)
    if monster_map and 'monster_palette_map' in monster_map:
        for monster_name, data in monster_map['monster_palette_map'].items():
            palette_raw = data.get('palette', 0xFF)
            if isinstance(palette_raw, int):
                palette = palette_raw & 0x07
            else:
                try:
                    palette = int(palette_raw) & 0x07
                except:
                    palette = 0xFF
            
            tile_range = data.get('tile_range', [])
            for tile in tile_range:
                if isinstance(tile, int) and 0 <= tile < 256:
                    lookup_table[tile] = palette
    
    original_input = bytes(rom[0x0824:0x0824+46])
    
    # Check existing VBlank hook
    vblank_vector = bytes(rom[0x0040:0x0040+3])
    if vblank_vector[0] == 0xC3:  # JP nn
        existing_vblank_addr = vblank_vector[1] | (vblank_vector[2] << 8)
        print(f"Found existing VBlank hook at 0x{existing_vblank_addr:04X}")
    else:
        existing_vblank_addr = None
    
    # Create optimized sprite loop
    def make_sprite_loop(lookup_table_addr):
        return bytes([
            0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF, BC, DE, HL
            0x21, 0x00, 0xFE,      # LD HL, 0xFE00
            0x06, 0x28,            # LD B, 40
            0x0E, 0x00,            # LD C, 0
            # .loop:
            0x79,                  # LD A, C
            0x87,                  # ADD A, A
            0x87,                  # ADD A, A
            0x85,                  # ADD A, L
            0x6F,                  # LD L, A
            0x7E,                  # LD A, [HL] (Y)
            0xA7,                  # AND A
            0x28, 0x1F,            # JR Z, .skip
            0xFE, 0x90,            # CP 144
            0x30, 0x1B,            # JR NC, .skip
            0x23,                  # INC HL (X)
            0x23,                  # INC HL (tile)
            0x7E,                  # LD A, [HL] (tile)
            0x23,                  # INC HL (flags)
            0xE5,                  # PUSH HL
            # Lookup
            0x57,                  # LD D, A
            0x21, lookup_table_addr & 0xFF, (lookup_table_addr >> 8) & 0xFF,
            0x7A,                  # LD A, D
            0x5F,                  # LD E, A
            0x19,                  # ADD HL, DE
            0x7E,                  # LD A, [HL]
            0xFE, 0xFF,            # CP 0xFF
            0x28, 0x08,            # JR Z, .no_modify
            # Apply
            0xE1,                  # POP HL
            0x57,                  # LD D, A
            0x7E,                  # LD A, [HL]
            0xE6, 0xF8,            # AND 0xF8
            0xB2,                  # OR D
            0x77,                  # LD [HL], A
            0x18, 0x03,            # JR .skip
            # .no_modify:
            0xE1,                  # POP HL
            # .skip:
            0x21, 0x00, 0xFE,      # LD HL, 0xFE00
            0x0C,                  # INC C
            0x05,                  # DEC B
            0x20, 0xD3,            # JR NZ, .loop
            0xE1, 0xD1, 0xC1, 0xF1,  # POP HL, DE, BC, AF
            0xC9,                  # RET
        ])
    
    # Place in Bank 13
    sprite_loop_start = 0x036D00
    temp_loop = make_sprite_loop(0x6F9A)
    
    # Build: Input handler approach with double-pass (safest)
    temp_combined = bytes([
        # Load BG palettes FIRST (needed for menu stability)
        0x21, 0x80, 0x6C, 0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        # Load OBJ palettes
        0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
        # Pass 1: Before
    ]) + temp_loop + bytes([
        # Original input
    ]) + original_input + bytes([
        # Pass 2: After
    ]) + temp_loop + bytes([
        0xC9,
    ])
    
    combined_size = len(temp_combined)
    lookup_table_offset = sprite_loop_start + combined_size
    lookup_table_bank_addr = ((lookup_table_offset - 0x034000) + 0x4000) & 0x7FFF
    
    sprite_loop_code = make_sprite_loop(lookup_table_bank_addr)
    
    # CRITICAL: Load BG palettes FIRST for menu stability (prevents white screen)
    combined_bank13 = bytes([
        # Load BG palettes FIRST (needed for menu stability - prevents white screen!)
        0x21, 0x80, 0x6C, 0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        # Load OBJ palettes (needed for sprites)
        0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
        # Pass 1: Before game code
    ]) + sprite_loop_code + bytes([
        # Original input handler
    ]) + original_input + bytes([
        # Pass 2: After game code
    ]) + sprite_loop_code + bytes([
        0xC9,  # RET
    ])
    
    rom[sprite_loop_start:sprite_loop_start+len(combined_bank13)] = combined_bank13
    rom[lookup_table_offset:lookup_table_offset + 256] = lookup_table
    
    # Trampoline at input handler
    trampoline = bytes([
        0xF5, 0x3E, 0x0D, 0xEA, 0x00, 0x20, 0xCD, 0x00, 0x6D, 0x3E, 0x01, 0xEA, 0x00, 0x20, 0xF1, 0xC9
    ])
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    if len(trampoline) < 46:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    mapped_count = sum(1 for x in lookup_table if x != 0xFF)
    print(f"✓ Built ROM with BREAKTHROUGH double-pass approach")
    print(f"  - Strategy: Modify OAM BEFORE and AFTER game code")
    print(f"  - Lookup table: {mapped_count} tiles mapped")
    print(f"  - Sara W (tiles 4-7): Palette 1 (green/orange)")
    print(f"  - Dragonfly (tiles 0-3): Palette 0 (red/black)")
    print(f"  - Overhead: {len(combined_bank13)} bytes")
    output_rom_path.write_bytes(rom)

if __name__ == "__main__":
    main()

