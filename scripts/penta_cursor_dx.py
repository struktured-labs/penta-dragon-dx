#!/usr/bin/env python3
import sys
import yaml
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

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
    if isinstance(c, int):
        return c & 0x7FFF
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

    if not input_rom_path.exists():
        print(f"Error: {input_rom_path} not found")
        return

    rom = bytearray(input_rom_path.read_bytes())
    
    # 1. Header Updates (DO NOT OVERWRITE TITLE SPACE)
    # Extend ROM to 512KB
    rom.extend([0xFF] * (512 * 1024 - len(rom)))
    rom[0x148] = 0x04 # 512KB
    rom[0x143] = 0x80 # CGB Compatible
    
    # 2. Load Palettes from YAML
    with open(palette_yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
    bg_palettes = []
    for name in ['Dungeon', 'LavaZone', 'WaterZone', 'DesertZone', 'ForestZone', 'CastleZone', 'SkyZone', 'BossZone']:
        colors = config['bg_palettes'].get(name, {}).get('colors', ['white', 'green', 'dark green', 'black'])
        bg_palettes.append(create_palette(colors))
    
    obj_palettes = []
    for name in ['MainCharacter', 'EnemyBasic', 'EnemyFire', 'EnemyIce', 'EnemyFlying', 'EnemyPoison', 'MiniBoss', 'MainBoss']:
        colors = config['obj_palettes'].get(name, {}).get('colors', ['transparent', 'white', 'gray', 'black'])
        obj_palettes.append(create_palette(colors))

    # 3. Bank 16 (Offset 0x40000) - The Engine
    bank16_base = 0x40000
    
    # Init Routine (0x4000 in Bank 16)
    # Copies Palettes and Colorizer to WRAM
    boot_init = bytearray([
        0xF3,                   # DI
        # Enable Double Speed
        0xF0, 0x4D, 0xCB, 0x7F, 0x20, 0x07, 0x3E, 0x01, 0xE0, 0x4D, 0x10, 0x00,
        
        # Load Palettes to Hardware
        0x3E, 0x80, 0xE0, 0x68, 0x21, 0x00, 0x41, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        0x3E, 0x80, 0xE0, 0x6A, 0x21, 0x40, 0x41, 0x0E, 0x40, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,

        # Copy Palettes to WRAM D000
        0x21, 0x00, 0x41, 0x11, 0x00, 0xD0, 0x01, 0x80, 0x00,
        0x2A, 0x12, 0x13, 0x0B, 0x78, 0xB1, 0x20, 0xF9,

        # Copy Colorizer to WRAM D080
        0x21, 0x00, 0x42, 0x11, 0x80, 0xD0, 0x06, 0x40,
        0x2A, 0x12, 0x13, 0x05, 0x20, 0xFA,

        0xC9,                   # RET
    ])
    
    # Colorizer Engine (0x4200 in Bank 16 -> D080 in WRAM)
    colorizer_wram = bytearray([
        0xF5, 0xC5, 0xD5, 0xE5, # PUSH
        0x21, 0x00, 0xC0, 0x06, 0x28,
        0x7E, 0xA7, 0x28, 0x1A, 0xE5, 0x23, 0x23, 0x7E, 0x4F, 0x23, 0x7E, 0x5F,
        0x79, 0xFE, 0x80, 0x38, 0x08, 0xFE, 0xB0, 0x38, 0x06, 0x3E, 0x07, 0x18, 0x04,
        0x3E, 0x00, 0x18, 0x02, 0x3E, 0x01, 0x57, 0x7B, 0xE6, 0xF8, 0xB2, 0x77, 0xE1,
        0x11, 0x04, 0x00, 0x19, 0x05, 0x20, 0xD2,
        
        # Reload palettes from WRAM to Hardware (prevents DMG overrides)
        0x3E, 0x80, 0xE0, 0x68, 0x21, 0x00, 0xD0, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
        0xE1, 0xD1, 0xC1, 0xF1, 0xC9,
    ])
    
    # Fix offsets
    colorizer_wram[12] = 0x22 # JR Z skip
    colorizer_wram[51] = 0xD3 # JR NZ loop

    # Write to Bank 16
    rom[bank16_base : bank16_base + len(boot_init)] = boot_init
    rom[bank16_base + 0x100 : bank16_base + 0x100 + 64] = b''.join(bg_palettes)
    rom[bank16_base + 0x140 : bank16_base + 0x140 + 64] = b''.join(obj_palettes)
    rom[bank16_base + 0x200 : bank16_base + 0x200 + len(colorizer_wram)] = colorizer_wram
    
    # 4. Patch Entry Point (0x0101)
    # Jump to free space in vector table
    rom[0x0101:0x0104] = [0xC3, 0x48, 0x00] # JP 0048
    
    # 5. Startup Routine in Vector Space (0x0048)
    # 24 bytes available (0x48-0x5F)
    startup_code = [
        0x3E, 0x10,             # LD A, 16
        0xEA, 0x00, 0x20,       # LD [2000], A
        0xCD, 0x00, 0x40,       # CALL 4000 (Bank 16 Init)
        0x3E, 0x01,             # LD A, 1
        0xEA, 0x00, 0x20,       # LD [2000], A
        0xC3, 0x50, 0x01        # JP 0150 (Original Entry)
    ]
    rom[0x0048 : 0x0048 + len(startup_code)] = startup_code
    
    # 6. VBlank Trampoline in Vector Space (0x0058)
    # Calls Colorizer then the original handler
    vblank_code = [
        0xCD, 0x80, 0xD0,       # CALL D080 (WRAM Colorizer)
        0xCD, 0x24, 0x08,       # CALL 0824 (Original VBlank logic)
        0xC9                    # RET
    ]
    rom[0x0058 : 0x0058 + len(vblank_code)] = vblank_code
    
    # 7. Hook VBlank (0x06DD)
    rom[0x06DD:0x06E0] = [0xCD, 0x58, 0x00] # CALL 0058
    
    # 8. Patch VBlank Wait at 0x0067 (FIX FOR WHITE SCREEN)
    # Returns early if GBC to prevent timing lockup
    vblank_wait_fix = [
        0xF0, 0x4D,             # LDH A, [FF4D]
        0xCB, 0x7F,             # BIT 7, A
        0xC0                    # RET NZ (If CGB, return immediately)
    ]
    rom[0x0067 : 0x0067 + len(vblank_wait_fix)] = vblank_wait_fix

    # 9. Header Checksum
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    
    # 10. Write output
    output_rom_path.parent.mkdir(parents=True, exist_ok=True)
    output_rom_path.write_bytes(rom)
    print(f"Success! Created {output_rom_path}")

if __name__ == "__main__":
    main()
