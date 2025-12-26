#!/usr/bin/env python3
"""
AGGRESSIVE GBC COLORIZATION - NO COMPROMISES

Based on analysis: Sprites 0-3 = Player, Sprites 8-11 = Enemies
We use sprite index to determine palette assignment.
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

    rom = bytearray(input_rom_path.read_bytes())
    
    # 1. CGB Flag
    rom[0x143] = 0xC0  # CGB-only
    
    # 2. Ghost Palette Writes
    ghost_count = 0
    for i in range(len(rom) - 1):
        if rom[i] == 0xE0:
            if rom[i+1] == 0x47:
                rom[i+1] = 0xEC
                ghost_count += 1
            elif rom[i+1] == 0x48:
                rom[i+1] = 0xED
                ghost_count += 1
            elif rom[i+1] == 0x49:
                rom[i+1] = 0xEE
                ghost_count += 1
    print(f"Ghosted {ghost_count} palette writes.")

    # 3. Load Palettes
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

    # 4. Storage at 0x7E00
    base = 0x7E00
    rom[base : base + 64] = bg_pals
    rom[base + 64 : base + 128] = obj_pals
    
    # 5. Boot Loader
    boot_loader = [
        0xF5, 0xC5, 0xD5, 0xE5,
        0x3E, 0x80, 0xE0, 0x68, 0x21, 0x00, 0x7E, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        0x3E, 0x80, 0xE0, 0x6A, 0x21, 0x40, 0x7E, 0x0E, 0x40, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
        0xE1, 0xD1, 0xC1, 0xF1,
        0xCD, 0xC8, 0x00,
        0xC9
    ]
    rom[base + 0x80 : base + 0x80 + len(boot_loader)] = boot_loader
    rom[0x015B : 0x015E] = [0xCD, 0x80, 0x7E]

    # 6. Sprite Attribute Setter - sets palette in both shadow and real OAM
    # This function: HL = OAM base, C = sprite index, sets palette attribute
    set_attrs_func = [
        # Input: HL = OAM base (C000 or FE00), C = sprite index
        # Sets palette attribute based on sprite index
        0xE5,  # PUSH HL (save OAM base)
        0x79,  # LD A, C (get sprite index)
        0x87,  # ADD A, A (multiply by 2)
        0x87,  # ADD A, A (multiply by 4 - each sprite is 4 bytes)
        0x85,  # ADD A, L (add to low byte)
        0x6F,  # LD L, A (now HL points to sprite's flags byte + 3)
        0x7D,  # LD A, L (get offset)
        0xC6, 0x03,  # ADD A, 3 (point to flags byte)
        0x6F,  # LD L, A
        0x79,  # LD A, C (get sprite index again)
        0xFE, 0x04,  # CP 4
        0x38, 0x02,  # JR C, .player
        0x3E, 0x01,  # LD A, 1 (enemy)
        0x18, 0x01,  # JR .set
        # .player:
        0x3E, 0x00,  # LD A, 0 (player)
        # .set:
        0x57,  # LD D, A (save palette)
        0x7E,  # LD A, [HL] (get flags)
        0xE6, 0xF8,  # AND 0xF8 (clear palette bits)
        0xB2,  # OR D (OR palette)
        0x77,  # LD [HL], A (write back)
        0xE1,  # POP HL (restore OAM base)
        0xC9   # RET
    ]
    
    # Actually, simpler approach - just iterate and set
    set_attrs_func = [
        # Function to set attributes: HL = OAM base, B = count, C = start index
        0xE5,  # PUSH HL
        0x79,  # LD A, C (sprite index)
        0x87,  # ADD A, A (*2)
        0x87,  # ADD A, A (*4)
        0x85,  # ADD A, L
        0x6F,  # LD L, A (HL now points to sprite Y)
        0x7E,  # LD A, [HL] (get Y)
        0xA7,  # AND A
        0x28, 0x14,  # JR Z, .skip (if Y=0, skip)
        0x23, 0x23, 0x23,  # INC HL x3 (point to flags)
        0x79,  # LD A, C (get sprite index)
        0xFE, 0x04,  # CP 4
        0x38, 0x04,  # JR C, .player
        0x3E, 0x01,  # LD A, 1
        0x18, 0x02,  # JR .set
        # .player:
        0x3E, 0x00,  # LD A, 0
        # .set:
        0x57,  # LD D, A
        0x7E,  # LD A, [HL]
        0xE6, 0xF8,  # AND 0xF8
        0xB2,  # OR D
        0x77,  # LD [HL], A
        # .skip:
        0xE1,  # POP HL
        0x0C,  # INC C
        0x05,  # DEC B
        0x20, 0xD8,  # JR NZ, loop start (but we need to recalc)
        0xC9   # RET
    ]
    
    # 6. SPRITE COLORIZATION - DISABLED (causes white screen crashes)
    # The sprite writing patch at 0x177C causes white screen freezes
    # Reverting to stable minimal version (CGB flag + ghost writes + boot palette load only)
    print("⚠️  Sprite colorization disabled (causes crashes)")
    print("   Using stable minimal version: CGB flag + ghost writes + boot palette load")

    
    # VBlank Hook (Iteration 4) - Reload palettes every frame
    vblank_hook_code = [
        0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF, BC, DE, HL
        0x3E, 0x80, 0xE0, 0x68,  # LDH [FF68], A (BCPS auto-increment)
        0x21, 0x00, 0x7E,        # LD HL, 0x7E00 (BG palettes)
        0x0E, 0x40,              # LD C, 64 (64 bytes)
        0x2A, 0xE0, 0x69,        # loop: LD A, [HL+]; LDH [FF69], A
        0x0D,                    # DEC C
        0x20, 0xFA,              # JR NZ, loop
        0x3E, 0x80, 0xE0, 0x6A,  # LDH [FF6A], A (OCPS auto-increment)
        0x21, 0x40, 0x7E,        # LD HL, 0x7E40 (OBJ palettes)
        0x0E, 0x40,              # LD C, 64
        0x2A, 0xE0, 0x6B,        # loop: LD A, [HL+]; LDH [FF6B], A
        0x0D,                    # DEC C
        0x20, 0xFA,              # JR NZ, loop
        0xE1, 0xD1, 0xC1, 0xF1,  # POP HL, DE, BC, AF
        0xC9                     # RET
    ]
    # Install VBlank hook at 0x0040
    hook_addr = base + 0x100
    rom[0x0040] = 0xC3  # JP
    rom[0x0041] = hook_addr & 0xFF  # Low byte
    rom[0x0042] = (hook_addr >> 8) & 0xFF  # High byte
    rom[hook_addr:hook_addr+len(vblank_hook_code)] = vblank_hook_code
    print("✓ Installed VBlank hook for palette reloading")
# 8. Checksums
    chk = 0
    for i in range(0x134, 0x14D): chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    
    output_rom_path.write_bytes(rom)
    print(f"✅ STABLE MINIMAL COLORIZATION: {output_rom_path}")
    print("")
    print("Features:")
    print("  ✓ CGB-only mode enabled")
    print("  ✓ Ghost palette writes (DMG interference blocked)")
    print("  ✓ Rich 8-palette system loaded at boot")
    print("")
    print("Note: Sprite colorization disabled due to stability issues")
    print("      This ROM should run without crashes")

if __name__ == "__main__":
    main()
