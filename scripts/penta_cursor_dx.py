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
    
    # 1. CGB Flag - Enable CGB-compatible mode
    # Original ROM is DMG-only (0x00), change to CGB-compatible (0x80)
    # CGB-compatible works on both DMG and CGB hardware
    rom[0x143] = 0x80  # CGB-compatible
    print("✓ Set CGB-compatible flag (0x80)")
    
    # 2. Ghost Palette Writes - DISABLED (may cause crashes)
    # Ghosting palette writes redirects them to unused registers
    # This might interfere with game logic, so disabling for stability
    ghost_count = 0
    # DISABLED: for i in range(len(rom) - 1):
    #     if rom[i] == 0xE0:
    #         if rom[i+1] == 0x47:
    #             rom[i+1] = 0xEC
    #             ghost_count += 1
    #         elif rom[i+1] == 0x48:
    #             rom[i+1] = 0xED
    #             ghost_count += 1
    #         elif rom[i+1] == 0x49:
    #             rom[i+1] = 0xEE
    #             ghost_count += 1
    print(f"Ghosted {ghost_count} palette writes (DISABLED for stability).")

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

    # 4. Load Palettes via Input Handler (safer than boot hook)
    # Use proven approach from create_dx_rom.py: input handler trampoline with delay
    # Store palette data in bank 13 free space (0x6C80)
    palette_data_offset = 0x036C80  # File offset in bank 13
    palette_data_gb_addr = 0x6C80  # GB address in bank 13
    rom[palette_data_offset : palette_data_offset + 64] = bg_pals
    rom[palette_data_offset + 64 : palette_data_offset + 128] = obj_pals
    print(f"✓ Stored palette data in bank 13 @0x{palette_data_gb_addr:04X}")
    
    # Save original input handler (46 bytes) to bank 13 at 0x6D00
    original_input = bytes(rom[0x0824:0x0824+46])
    rom[0x036D00:0x036D00+46] = original_input
    
    # Build combined function in bank 13: original input + palette loading + sprite assignment
    # Load palettes every frame AND assign palettes to sprites based on sprite index
    combined_bank13 = original_input + bytes([
        # Load BG palettes (every frame)
        0x21, 0x80, 0x6C,      # LD HL,6C80
        0x3E, 0x80,            # LD A,80h
        0xE0, 0x68,            # LDH [FF68],A
        0x0E, 0x40,            # LD C,64
        0x2A, 0xE0, 0x69,      # loop: LD A,[HL+]; LDH [FF69],A
        0x0D,                  # DEC C
        0x20, 0xFA,            # JR NZ,loop
        # Load OBJ palettes (every frame)
        0x3E, 0x80,            # LD A,80h
        0xE0, 0x6A,            # LDH [FF6A],A
        0x0E, 0x40,            # LD C,64
        0x2A, 0xE0, 0x6B,      # loop: LD A,[HL+]; LDH [FF6B],A
        0x0D,                  # DEC C
        0x20, 0xFA,            # JR NZ,loop
        # Assign sprite palettes using TILE-BASED approach (more reliable than position)
        # Tiles 4-7: Palette 1 (Sara W = green)
        # Tiles 0-3: Palette 0 (Sara D/Dragon Fly = red/blue)
        # Note: Tile IDs change during animation, but SARA W consistently uses 4-7
        0xF5, 0xC5, 0xD5, 0xE5,  # PUSH AF, BC, DE, HL
        0x21, 0x00, 0xFE,      # LD HL, 0xFE00 (real OAM - modify directly)
        0x06, 0x28,            # LD B, 40 (40 sprites - DON'T OVERWRITE!)
        0x0E, 0x00,            # LD C, 0 (sprite index)
        # Loop through sprites:
        0x79,                  # LD A, C (sprite index)
        0x87,                  # ADD A, A (*2)
        0x87,                  # ADD A, A (*4)
        0x5F,                  # LD E, A (offset)
        0x7B,                  # LD A, E
        0x85,                  # ADD A, L
        0x6F,                  # LD L, A (HL points to sprite Y)
        0x7E,                  # LD A, [HL] (get Y)
        0xA7,                  # AND A
        0x28, 0x23,            # JR Z, skip (if Y=0, sprite not used) - ~35 bytes to .skip
        0xFE, 0x90,            # CP 144
        0x30, 0x1F,            # JR NC, skip (if Y >= 144, off-screen) - ~31 bytes to .skip
        0x23,                  # INC HL (point to X)
        0x23,                  # INC HL (point to tile)
        0x7E,                  # LD A, [HL] (get tile ID)
        0x23,                  # INC HL (point to flags)
        # Check tile ID: SARA W uses tiles 4-7, SARA D/DRAGONFLY use tiles 0-3
        # Tile ID is in A - check it directly (can't use B - it's the sprite counter!)
        0xE5,                  # PUSH HL (save flags address)
        0xFE, 0x04,            # CP 4
        0x38, 0x08,            # JR C, .check_low (tile < 4)
        0xFE, 0x08,            # CP 8
        0x38, 0x06,            # JR C, .sara_w (4 <= tile < 8, Sara W = Pal1)
        # Tile >= 8: default to Pal0
        0x3E, 0x00,            # LD A, 0 (Pal0)
        0x18, 0x04,            # JR .set
        # .check_low: tile < 4 (Sara D or Dragon Fly)
        0x3E, 0x00,            # LD A, 0 (Pal0 for now)
        0x18, 0x02,            # JR .set (skip 2 bytes = .sara_w's LD A,1 which is 2 bytes)
        # .sara_w: 4 <= tile < 8
        0x3E, 0x01,            # LD A, 1 (Sara W = Pal1)
        # .set:
        0xE1,                  # POP HL (restore flags address)
        0x57,                  # LD D, A (save palette in D)
        0x7E,                  # LD A, [HL] (get flags)
        0xE6, 0xF8,            # AND 0xF8 (clear palette bits 0-2)
        0xB2,                  # OR D (set palette)
        0x77,                  # LD [HL], A (write back to real OAM FE00)
        # .skip:
        0x21, 0x00, 0xFE,      # LD HL, 0xFE00 (reset to real OAM base)
        0x0C,                  # INC C
        0x05,                  # DEC B
        0x20, 0xD0,            # JR NZ, loop
        0xE1, 0xD1, 0xC1, 0xF1,  # POP HL, DE, BC, AF
        0xC9,                  # RET
    ])
    rom[0x036D00:0x036D00+len(combined_bank13)] = combined_bank13
    
    # Minimal trampoline at 0x0824: switch bank, call 6D00, restore bank
    trampoline = bytes([
        0xF5,                  # PUSH AF
        0x3E, 0x0D,            # LD A,13
        0xEA, 0x00, 0x20,      # LD [2000],A (switch to bank 13)
        0xCD, 0x00, 0x6D,      # CALL 6D00 (combined function)
        0x3E, 0x01,            # LD A,1
        0xEA, 0x00, 0x20,      # LD [2000],A (switch back to bank 1)
        0xF1,                  # POP AF
        0xC9,                  # RET
    ])
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    # Fill rest of 46-byte slot with NOPs
    if len(trampoline) < 46:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    print(f"✓ Installed input handler trampoline at 0x0824")
    print(f"✓ Combined function in bank 13 @0x6D00")
    print(f"   - Loads palettes every frame (keeps colors applied)")
    print(f"   - Assigns sprite palettes by tile ID:")
    print(f"     * Tiles 4-7 → Palette 1 (Sara W = green)")
    print(f"     * Tiles 0-3 → Palette 0 (Sara D/Dragon Fly = red/blue)")
    print(f"   - Modifies real OAM (FE00) every frame via input handler")

    # 8. Checksums - DON'T RECALCULATE (may cause crashes)
    # Leave original checksum intact
    # chk = 0
    # for i in range(0x134, 0x14D): chk = (chk - rom[i] - 1) & 0xFF
    # rom[0x14D] = chk
    print("⚠️  Checksum recalculation DISABLED - leaving original checksum")
    
    output_rom_path.write_bytes(rom)
    print(f"✅ ROM BUILT: {output_rom_path}")
    print("")
    print("Current state:")
    print("  ✓ CGB-compatible mode enabled (0x80)")
    print("  ✓ Custom palettes loaded every frame via input handler")
    print("  ✓ Sprite palette assignment enabled (modifies OAM every frame)")
    print("  ⚠️  Checksum recalculation DISABLED (for stability)")
    print("")
    print("ROM should display colors with distinct palettes for different sprites.")

if __name__ == "__main__":
    main()
