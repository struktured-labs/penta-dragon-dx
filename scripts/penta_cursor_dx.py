#!/usr/bin/env python3
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

    rom = bytearray(input_rom_path.read_bytes())
    rom[0x143] = 0x80  # CGB-compatible
    
    with open(palette_yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
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
    
    original_input = bytes(rom[0x0824:0x0824+46])
    
    # Combined function in bank 13: original input + palette loading + sprite assignment
    combined_bank13 = original_input + bytes([
        # Load BG palettes
        0x21, 0x80, 0x6C, 0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        # Load OBJ palettes
        0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
        
        # Sprite loop (ONE PASS)
        0xF5, 0xC5, 0xD5, 0xE5, 0x21, 0x00, 0xFE, 0x06, 0x28, 0x0E, 0x00,
        0x79, 0x87, 0x87, 0x5F, 0x7B, 0x85, 0x6F, 0x7E, 0xA7, 0x28, 0x26, 0xFE, 0x90, 0x30, 0x24,
        0x23, 0x23, 0x7E, 0x23, 0xE5, 0xFE, 0x04, 0x38, 0x0C, 0xFE, 0x08, 0x38, 0x0C, 0xFE, 0x0A,
        0x38, 0x04, 0xFE, 0x0E, 0x38, 0x04, 0x3E, 0x00, 0x18, 0x02, 0x3E, 0x01, 0xE1, 0x57, 0x7E,
        0xE6, 0xF8, 0xB2, 0x77, 0x21, 0x00, 0xFE, 0x0C, 0x05, 0x20, 0xCC, 0xE1, 0xD1, 0xC1, 0xF1, 0xC9
    ])
    rom[0x036D00:0x036D00+len(combined_bank13)] = combined_bank13

    # Trampoline: switch bank, call custom code, restore bank
    trampoline = bytes([
        0xF5, 0x3E, 0x0D, 0xEA, 0x00, 0x20, 0xCD, 0x00, 0x6D, 0x3E, 0x01, 0xEA, 0x00, 0x20, 0xF1, 0xC9
    ])
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    if len(trampoline) < 46:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    print("✓ Built ROM with single-call and Sara W tiles 4-7, 10-13")
    output_rom_path.write_bytes(rom)

if __name__ == "__main__":
    main()
