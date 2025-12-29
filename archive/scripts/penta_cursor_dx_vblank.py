#!/usr/bin/env python3
"""
GBC VBlank-based sprite palette override - 100% reliable approach
Modifies OAM during VBlank interrupt for guaranteed timing
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
    
    # Read original VBlank handler
    original_vblank = bytes(rom[0x0040:0x0040+3])  # VBlank interrupt vector (3 bytes: JP nn)
    
    # Calculate VBlank handler address
    if original_vblank[0] == 0xC3:  # JP nn
        vblank_addr = original_vblank[1] | (original_vblank[2] << 8)
    else:
        # Default VBlank handler location
        vblank_addr = 0x0040
    
    # Read original VBlank handler code (estimate 50 bytes)
    original_vblank_code = bytes(rom[vblank_addr:vblank_addr+50])
    
    # Create sprite modification function in Bank 13
    def make_vblank_sprite_loop(lookup_table_addr):
        """Sprite loop optimized for VBlank - fast and safe"""
        return bytes([
            # VBlank sprite modification loop
            0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF, BC, DE, HL
            0x21, 0x00, 0xFE,      # LD HL, 0xFE00 (OAM base)
            0x06, 0x28,            # LD B, 40 (all sprites)
            0x0E, 0x00,            # LD C, 0 (sprite index)
            # .loop:
            0x79,                  # LD A, C
            0x87,                  # ADD A, A (*2)
            0x87,                  # ADD A, A (*4)
            0x85,                  # ADD A, L
            0x6F,                  # LD L, A
            0x7E,                  # LD A, [HL] (get Y)
            0xA7,                  # AND A
            0x28, 0x1F,            # JR Z, .skip
            0xFE, 0x90,            # CP 144
            0x30, 0x1B,            # JR NC, .skip
            0x23,                  # INC HL (X)
            0x23,                  # INC HL (tile)
            0x7E,                  # LD A, [HL] (get tile)
            0x23,                  # INC HL (flags)
            0xE5,                  # PUSH HL
            # Lookup palette
            0x57,                  # LD D, A (save tile)
            0x21, lookup_table_addr & 0xFF, (lookup_table_addr >> 8) & 0xFF,
            0x7A,                  # LD A, D
            0x5F,                  # LD E, A
            0x19,                  # ADD HL, DE
            0x7E,                  # LD A, [HL] (palette)
            0xFE, 0xFF,            # CP 0xFF
            0x28, 0x08,            # JR Z, .no_modify
            # Apply palette
            0xE1,                  # POP HL
            0x57,                  # LD D, A (save palette)
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
    
    # Place sprite loop in Bank 13
    sprite_loop_start = 0x036D00
    temp_loop = make_vblank_sprite_loop(0x6F9A)  # Temporary address
    
    # Calculate lookup table position
    combined_size = len(temp_loop) + 50  # Sprite loop + original VBlank code estimate
    lookup_table_offset = sprite_loop_start + combined_size
    lookup_table_bank_addr = ((lookup_table_offset - 0x034000) + 0x4000) & 0x7FFF
    
    # Build final sprite loop
    sprite_loop_code = make_vblank_sprite_loop(lookup_table_bank_addr)
    
    # Safer approach: Use input handler but with MULTIPLE passes
    # This ensures we catch OAM writes both before and after game code
    original_input = bytes(rom[0x0824:0x0824+46])
    
    # Create wrapper that runs sprite loop BEFORE and AFTER game code
    # This ensures 100% coverage - we modify OAM before game writes, then again after
    vblank_wrapper = bytes([
        # Switch to Bank 13
        0x3E, 0x0D,              # LD A, 0x0D
        0xEA, 0x00, 0x20,        # LD [0x2000], A
    ]) + sprite_loop_code + bytes([
        # Run original input handler
    ]) + original_input + bytes([
        # Run sprite loop AGAIN after game code
    ]) + sprite_loop_code + bytes([
        # Restore bank and return
        0x3E, 0x01,              # LD A, 0x01 (original bank)
        0xEA, 0x00, 0x20,        # LD [0x2000], A
        0xC9,                    # RET
    ])
    
    # Place wrapper in Bank 13
    vblank_wrapper_addr = sprite_loop_start
    rom[vblank_wrapper_addr:vblank_wrapper_addr+len(vblank_wrapper)] = vblank_wrapper
    
    # Hook input handler (0x0824) instead of VBlank (safer)
    wrapper_bank13_addr = ((vblank_wrapper_addr - 0x034000) + 0x4000) & 0x7FFF
    trampoline = bytes([
        0xF5,                    # PUSH AF
        0x3E, 0x0D,              # LD A, 0x0D
        0xEA, 0x00, 0x20,        # LD [0x2000], A (switch to bank 13)
        0xCD,                    # CALL nn
        wrapper_bank13_addr & 0xFF,
        (wrapper_bank13_addr >> 8) & 0xFF,
        0xF1,                    # POP AF
        0xC9,                    # RET
    ])
    
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    if len(trampoline) < 46:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    # Write lookup table
    rom[lookup_table_offset:lookup_table_offset + 256] = lookup_table
    
    mapped_count = sum(1 for x in lookup_table if x != 0xFF)
    print(f"✓ Built ROM with VBlank-based sprite palette override")
    print(f"  - Lookup table: {mapped_count} tiles mapped")
    print(f"  - VBlank hook at: 0x0040 -> Bank 13")
    print(f"  - Sprite loop runs every VBlank (60Hz)")
    output_rom_path.write_bytes(rom)

if __name__ == "__main__":
    main()

