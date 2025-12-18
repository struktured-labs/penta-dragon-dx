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
    
    # 1. Extend ROM to 512KB (Bank 16+)
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
    
    # Code: BootInit
    # This code will be in Bank 16 (0x40000)
    boot_init = bytearray([
        0xF3,                   # 0: DI
        
        # 1. Enable Double Speed
        0xF0, 0x4D,             # 1: LDH A, [FF4D]
        0xCB, 0x7F,             # 3: BIT 7, A
        0x20, 0x07,             # 5: JR NZ, .already_double
        0x3E, 0x01,             # 7: LD A, 01
        0xE0, 0x4D,             # 9: LDH [FF4D], A
        0x10, 0x00,             # 11: STOP
        # 13: .already_double:
        
        # 2. Load Palettes to Hardware
        0x3E, 0x80,             # 13: LD A, 80 (auto-increment)
        0xE0, 0x68,             # 15: LDH [FF68], A
        0x21, 0x00, 0x41,       # 17: LD HL, 4100 (BG Palettes data)
        0x0E, 0x40,             # 20: LD C, 64
        0x2A, 0xE0, 0x69,       # 22: .bg_loop: LD A,[HL+]; LDH [FF69],A
        0x0D, 0x20, 0xFA,       # 25: DEC C; JR NZ, .bg_loop
        
        0x3E, 0x80,             # 28: LD A, 80 (auto-increment)
        0xE0, 0x6A,             # 30: LDH [FF6A], A
        0x21, 0x40, 0x41,       # 32: LD HL, 4140 (OBJ Palettes data)
        0x0E, 0x40,             # 35: LD C, 64
        0x2A, 0xE0, 0x6B,       # 37: .obj_loop: LD A,[HL+]; LDH [FF6B],A
        0x0D, 0x20, 0xFA,       # 40: DEC C; JR NZ, .obj_loop

        # 3. Copy Palettes to WRAM D000
        0x21, 0x00, 0x41,       # 43: LD HL, 4100
        0x11, 0x00, 0xD0,       # 46: LD DE, D000
        0x01, 0x80, 0x00,       # 49: LD BC, 128
        # 52: .pal_copy:
        0x2A, 0x12, 0x13, 0x0B, # 52: LD A,[HL+]; LD [DE],A; INC DE; DEC BC
        0x78, 0xB1, 0x20, 0xF9, # 56: LD A,B; OR C; JR NZ, .pal_copy

        # 4. Copy Colorizer to WRAM D080
        0x21, 0x00, 0x42,       # 60: LD HL, 4200 (Colorizer in Bank 16)
        0x11, 0x80, 0xD0,       # 63: LD DE, D080
        0x06, 0x40,             # 66: LD B, 64
        # 68: .code_copy:
        0x2A, 0x12, 0x13, 0x05, # 68: LD A,[HL+]; LD [DE],A; INC DE; DEC B
        0x20, 0xFA,             # 72: JR NZ, .code_copy

        0xC9,                   # 74: RET
    ])
    
    # Code: Colorizer (WRAM Engine)
    # This will be copied to WRAM D080
    colorizer_wram = bytearray([
        0x21, 0x00, 0xC0,       # 0: LD HL, C000
        0x06, 0x28,             # 3: LD B, 40
        # 5: .sprite_loop
        0x7E,                   # 5: LD A, [HL] (Y)
        0xA7,                   # 6: AND A
        0x28, 0x18,             # 7: JR Z, .skip (7+2+24=33)
        0xE5,                   # 9: PUSH HL
        0x23, 0x23,             # 10: INC HL, INC HL
        0x7E,                   # 12: LD A, [HL] (Tile)
        0x4F,                   # 13: LD C, A
        0x23,                   # 14: INC HL (Attr)
        0x7E,                   # 15: LD A, [HL]
        0x5F,                   # 16: LD E, A
        0x79,                   # 17: LD A, C
        0xFE, 0x80, 0x38, 0x06, # 18: CP 80; JR C, .pal0 (18+4+6=28)
        0xFE, 0xB0, 0x38, 0x04, # 22: CP B0; JR C, .pal1 (22+4+4=30)
        0x3E, 0x07, 0x18, 0x02, # 26: LD A, 07; JR .apply (26+4+2=32)
        0x3E, 0x00, 0x18, 0x02, # 30: .pal0: LD A, 00; JR .apply (30+4+2=36)
        0x3E, 0x01,             # 34: .pal1: LD A, 01
        # 36: .apply
        0x57,                   # 36: LD D, A
        0x7B,                   # 37: LD A, E
        0xE6, 0xF8,             # 38: AND F8
        0xB2,                   # 40: OR D
        0x77,                   # 41: LD [HL], A
        0xE1,                   # 42: POP HL
        # 43: .skip
        0x11, 0x04, 0x00,       # 43: LD DE, 4
        0x19,                   # 46: ADD HL, DE
        0x05,                   # 47: DEC B
        0x20, 0xD2,             # 48: JR NZ, .sprite_loop (48+2-46=4 -> offset D2)
        
        # Load Palettes from WRAM to Hardware
        0x3E, 0x80,             # 50: LD A, 80
        0xE0, 0x68,             # 52: LDH [68], A
        0x21, 0x00, 0xD0,       # 54: LD HL, D000
        0x0E, 0x40,             # 57: LD C, 64
        0x2A, 0xE0, 0x69,       # 59: .bg_loop: LD A,[HL+]; LDH [69],A
        0x0D, 0x20, 0xFA,       # 62: DEC C; JR NZ, .bg_loop
        0x3E, 0x80,             # 65: LD A, 80
        0xE0, 0x6A,             # 67: LDH [6A], A
        0x0E, 0x40,             # 69: LD C, 64
        0x2A, 0xE0, 0x6B,       # 71: .obj_loop: LD A,[HL+]; LDH [6B],A
        0x0D, 0x20, 0xFA,       # 74: DEC C; JR NZ, .obj_loop
        0xC9,                   # 77: RET
    ])
    
    # Fix offsets for Colorizer
    colorizer_wram[8] = 0x22 # JR Z skip
    colorizer_wram[49] = 0xD2 # JR NZ loop

    # 4. Write data to Bank 16
    rom[bank16_base : bank16_base + len(boot_init)] = boot_init
    # Palettes at 0x4100 in Bank 16
    rom[bank16_base + 0x100 : bank16_base + 0x100 + 64] = b''.join(bg_palettes)
    rom[bank16_base + 0x140 : bank16_base + 0x140 + 64] = b''.join(obj_palettes)
    # Colorizer code at 0x4200 in Bank 16
    rom[bank16_base + 0x200 : bank16_base + 0x200 + len(colorizer_wram)] = colorizer_wram
    
    # 5. Startup Hook (0x150)
    # Switches to Bank 16, calls Init, then jumps to Shim
    startup_hook = [
        0x3E, 0x10,             # LD A, 16
        0xEA, 0x00, 0x20,       # LD [2000], A
        0xCD, 0x00, 0x40,       # CALL 4000 (Init)
        0xC3, 0x34, 0x01        # JP 0134 (Shim)
    ]
    rom[0x0150:0x0150+len(startup_hook)] = startup_hook
    for i in range(0x0150 + len(startup_hook), 0x0162):
        rom[i] = 0x00
        
    # 6. Startup Shim (0x0134) - Title space
    # Restores Bank 1 and runs original startup
    startup_shim = [
        0x3E, 0x01,             # LD A, 1
        0xEA, 0x00, 0x20,       # LD [2000], A
        0xEF,                   # RST 28h
        0xCD, 0x67, 0x00,       # CALL 0067
        0x31, 0xFF, 0xDF,       # LD SP, DFFF
        0xCD, 0x00, 0x40,       # CALL 0040
        0xCD, 0xC8, 0x00,       # CALL 00C8
        0xFB,                   # EI
        0xC3, 0x62, 0x01        # JP 0162
    ]
    rom[0x0134 : 0x0134 + len(startup_shim)] = startup_shim
    
    # 7. VBlank Trampoline (0x0048) - Vector space
    # Checks if WRAM is initialized, calls colorizer
    trampoline = [
        0xF5,                   # PUSH AF
        0xFA, 0x80, 0xD0,       # LD A, [D080] (Check if WRAM code exists)
        0xFE, 0x21,             # CP 21 (First byte of colorizer: LD HL, C000)
        0x28, 0x0F,             # JR Z, .ok (0x0F = 15)
        # Re-init WRAM if needed (e.g. after save state load)
        0xC5, 0xD5, 0xE5,       # PUSH BC, DE, HL
        0x3E, 0x10,             # LD A, 16
        0xEA, 0x00, 0x20,       # LD [2000], A
        0xCD, 0x00, 0x40,       # CALL 4000 (Init)
        0x3E, 0x01,             # LD A, 1
        0xEA, 0x00, 0x20,       # LD [2000], A
        0xE1, 0xD1, 0xC1,       # POP HL, DE, BC
        # .ok:
        0xCD, 0x80, 0xD0,       # CALL D080 (Colorizer)
        0xF1,                   # POP AF
        0xC3, 0x24, 0x08        # JP 0824
    ]
    rom[0x0048 : 0x0048 + len(trampoline)] = trampoline
    
    # 8. VBlank Hook at 0x06DD
    rom[0x06DD:0x06E0] = [0xCD, 0x48, 0x00]

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
