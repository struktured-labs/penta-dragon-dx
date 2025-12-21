#!/usr/bin/env python3
"""
GBC-Native Approach: Patch DMG palette register writes
Make the game work like a native GBC game by preventing DMG palette interference
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
        'navy': 0x5000, 'maroon': 0x0010, 'olive': 0x0210,
        'dark green': 0x0280, 'dark red': 0x0010, 'dark yellow': 0x0210
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
    
    # Load monster palettes (preferred) or fall back to penta_palettes
    monster_palette_path = Path("palettes/monster_palettes.yaml")
    if monster_palette_path.exists():
        with open(monster_palette_path, 'r') as f:
            monster_palettes = yaml.safe_load(f)
        
        # Use monster_palettes.yaml for SARA_W, SARA_D, DRAGONFLY
        monster_data = monster_palettes.get('monster_palettes', {})
        
        # Build OBJ palettes: Palette 0=Dragonfly, 1=Sara W, 2-7 from penta_palettes
        obj_pals = (
            create_palette(monster_data.get('DRAGONFLY', {}).get('colors', ['transparent', 'white', 'light blue', 'blue'])) +
            create_palette(monster_data.get('SARA_W', {}).get('colors', ['transparent', 'green', 'orange', 'dark green'])) +
            create_palette(monster_data.get('SARA_D', {}).get('colors', ['transparent', 'red', 'orange', 'dark red']))
        )
        
        # Fill remaining palettes from penta_palettes.yaml
        with open(palette_yaml_path, 'r') as f:
            config = yaml.safe_load(f)
        
        obj_pals += (
            create_palette(config['obj_palettes']['EnemyFire']['colors']) +
            create_palette(config['obj_palettes']['EnemyIce']['colors']) +
            create_palette(config['obj_palettes']['EnemyFlying']['colors']) +
            create_palette(config['obj_palettes']['EnemyPoison']['colors']) +
            create_palette(config['obj_palettes']['MiniBoss']['colors'])
        )
    else:
        # Fall back to original approach
        with open(palette_yaml_path, 'r') as f:
            config = yaml.safe_load(f)
        
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
    
    with open(monster_map_path, 'r') as f:
        monster_map = yaml.safe_load(f)
    
    ultra_bg = ['7FFF', '001F', '7C00', '03E0']
    
    # Load BG palettes from penta_palettes
    if 'config' not in locals():
        with open(palette_yaml_path, 'r') as f:
            config = yaml.safe_load(f)
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
    
    # Create sprite loop
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
    
    # Build: GBC-native approach with DMG register patching
    temp_combined = bytes([
        # Load BG palettes FIRST (needed for menu stability)
        0x21, 0x80, 0x6C, 0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        # Load OBJ palettes (CGB palette RAM - loaded once, used via OAM bits)
        0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40, 0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA,
        # Pass 1: Before game code
    ]) + temp_loop + bytes([
        # Original input handler
    ]) + original_input + bytes([
        # Pass 2: After game code
    ]) + temp_loop + bytes([
        0xC9,
    ])
    
    combined_size = len(temp_combined)
    lookup_table_offset = sprite_loop_start + combined_size
    lookup_table_bank_addr = ((lookup_table_offset - 0x034000) + 0x4000) & 0x7FFF
    
    sprite_loop_code = make_sprite_loop(lookup_table_bank_addr)
    
    combined_bank13 = bytes([
        # Load BG palettes FIRST (needed for menu stability)
        0x21, 0x80, 0x6C, 0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40, 0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA,
        # Load OBJ palettes (CGB palette RAM - GBC-native approach)
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
    
    # Hook OAM DMA completion FIRST (before boot loader, to calculate correct offset)
    # OAM DMA sequence: 0x4190 E0 46 (LDH [FF46], A), then wait loop, then RET at 0x4197
    oam_dma_ret_addr = 0x4197
    is_ret = rom[oam_dma_ret_addr] == 0xC9
    is_already_hooked = rom[oam_dma_ret_addr] == 0xCD
    
    hook_code_offset = lookup_table_offset + 256
    hook_code_size = 0
    
    if is_ret or is_already_hooked:
        sprite_loop_bank_addr = ((sprite_loop_start + 15 - 0x034000) + 0x4000) & 0x7FFF  # After palette load
        
        hook_code = bytes([
            0xF5, 0xC5, 0xD5, 0xE5,
            0x3E, 0x0D, 0xEA, 0x00, 0x20,
            0xCD, sprite_loop_bank_addr & 0xFF, (sprite_loop_bank_addr >> 8) & 0xFF,
            0x3E, 0x01, 0xEA, 0x00, 0x20,
            0xE1, 0xD1, 0xC1, 0xF1, 0xC9,
        ])
        hook_code_size = len(hook_code)
        
        rom[hook_code_offset:hook_code_offset+hook_code_size] = hook_code
        
        hook_bank_addr = ((hook_code_offset - 0x034000) + 0x4000) & 0x7FFF
        rom[oam_dma_ret_addr] = 0xCD
        rom[oam_dma_ret_addr + 1] = hook_bank_addr & 0xFF
        rom[oam_dma_ret_addr + 2] = (hook_bank_addr >> 8) & 0xFF
        
        print(f"✓ Installed OAM DMA completion hook")
        print(f"  - Hook at RET after DMA (0x{oam_dma_ret_addr:04X})")
        print(f"  - Hook code at ROM offset 0x{hook_code_offset:06X} (bank 13 addr 0x{hook_bank_addr:04X})")
        print(f"  - Calls sprite loop at bank 13 addr 0x{sprite_loop_bank_addr:04X}")
    
    # Add boot-time palette loading at 0x0150 (AFTER hook code is written)
    # This ensures palettes are loaded before game starts, not just when input handler runs
    # Calculate offset after hook code (hook_code_size is set above if hook was installed)
    boot_palette_loader_offset = lookup_table_offset + 256 + hook_code_size
    boot_palette_loader_bank_addr = ((boot_palette_loader_offset - 0x034000) + 0x4000) & 0x7FFF
    
    # Boot loader: Load palettes, then RET to continue original boot code
    boot_loader_code = bytes([
        0xF5,                          # PUSH AF
        0xC5,                          # PUSH BC
        0xE5,                          # PUSH HL
        0x3E, 0x0D,                    # LD A, 13
        0xEA, 0x00, 0x20,              # LD [2000], A (switch to bank 13)
        # Load BG palettes
        0x21, 0x80, 0x6C,              # LD HL, 0x6C80 (BG palette data)
        0x3E, 0x80,                    # LD A, 0x80 (auto-increment)
        0xE0, 0x68,                    # LDH [FF68], A (BCPS)
        0x0E, 0x40,                    # LD C, 64
        0x2A,                          # .bg_loop: LD A, [HL+]
        0xE0, 0x69,                    # LDH [FF69], A (BCPD)
        0x0D,                          # DEC C
        0x20, 0xFA,                    # JR NZ, .bg_loop
        # Load OBJ palettes
        0x3E, 0x80,                    # LD A, 0x80 (auto-increment)
        0xE0, 0x6A,                    # LDH [FF6A], A (OCPS)
        0x0E, 0x40,                    # LD C, 64
        0x2A,                          # .obj_loop: LD A, [HL+]
        0xE0, 0x6B,                    # LDH [FF6B], A (OCPD)
        0x0D,                          # DEC C
        0x20, 0xFA,                    # JR NZ, .obj_loop
        0x3E, 0x01,                    # LD A, 1 (restore original bank)
        0xEA, 0x00, 0x20,              # LD [2000], A
        0xE1,                          # POP HL
        0xC1,                          # POP BC
        0xF1,                          # POP AF
        0xC9,                          # RET (return to continue boot)
    ])
    
    rom[boot_palette_loader_offset:boot_palette_loader_offset+len(boot_loader_code)] = boot_loader_code
    
    # Hook boot entry at 0x0150 to call palette loader
    # CRITICAL: Must switch to bank 13 before CALLing loader code in bank 13!
    original_boot_0150 = bytes(rom[0x0150:0x0153])  # Save first 3 bytes
    
    # Create trampoline that switches to bank 13, calls loader, restores bank
    boot_trampoline = bytes([
        0xF5,                          # PUSH AF (save A)
        0x3E, 0x0D,                    # LD A, 13
        0xEA, 0x00, 0x20,              # LD [2000], A (switch to bank 13)
        0xCD, boot_palette_loader_bank_addr & 0xFF, (boot_palette_loader_bank_addr >> 8) & 0xFF,  # CALL loader
        0x3E, 0x01,                    # LD A, 1 (restore original bank)
        0xEA, 0x00, 0x20,              # LD [2000], A
        0xF1,                          # POP AF (restore A)
    ])
    
    # Install trampoline at 0x0150
    rom[0x0150:0x0150+len(boot_trampoline)] = boot_trampoline
    # After trampoline, continue with original boot code
    rom[0x0150+len(boot_trampoline):0x0150+len(boot_trampoline)+len(original_boot_0150)] = original_boot_0150
    
    print(f"✓ Installed boot-time palette loader")
    print(f"  - Boot hook at 0x0150 calls palette loader at bank 13 addr 0x{boot_palette_loader_bank_addr:04X}")
    print(f"  - Boot loader offset: 0x{boot_palette_loader_offset:06X}")
    
    # Hook OAM DMA completion to run sprite loop right after game transfers sprites
    # OAM DMA sequence: 0x4190 E0 46 (LDH [FF46], A), then wait loop, then RET at 0x4197
    # We'll hook the RET at 0x4197 to run sprite loop after DMA completes
    oam_dma_ret_addr = 0x4197
    
    # Check if this is RET (original) or already hooked (CALL)
    is_ret = rom[oam_dma_ret_addr] == 0xC9
    is_already_hooked = rom[oam_dma_ret_addr] == 0xCD
    
    if is_ret or is_already_hooked:
        hook_code_offset = lookup_table_offset + 256
        # Sprite loop code starts after palette loading (15 bytes) in combined_bank13
        palette_load_size = 15
        sprite_loop_code_start = sprite_loop_start + palette_load_size
        sprite_loop_bank_addr = ((sprite_loop_code_start - 0x034000) + 0x4000) & 0x7FFF
        
        # Debug: Verify address calculation
        call_lo = sprite_loop_bank_addr & 0xFF
        call_hi = (sprite_loop_bank_addr >> 8) & 0xFF
        print(f"  DEBUG: sprite_loop_bank_addr=0x{sprite_loop_bank_addr:04X}, CALL bytes: CD {call_lo:02X} {call_hi:02X}")
        
        # Hook code: Run sprite loop, then RET
        hook_code = bytes([
            0xF5,                          # PUSH AF
            0xC5,                          # PUSH BC
            0xD5,                          # PUSH DE
            0xE5,                          # PUSH HL
            0x3E, 0x0D,                    # LD A, 13
            0xEA, 0x00, 0x20,              # LD [2000], A (switch to bank 13)
            0xCD, call_lo, call_hi,       # CALL sprite_loop (little-endian: low byte first)
            0x3E, 0x01,                    # LD A, 1 (restore original bank)
            0xEA, 0x00, 0x20,              # LD [2000], A
            0xE1,                          # POP HL
            0xD1,                          # POP DE
            0xC1,                          # POP BC
            0xF1,                          # POP AF
            0xC9,                          # RET (return to caller)
        ])
        
        rom[hook_code_offset:hook_code_offset+len(hook_code)] = hook_code
        
        # Replace RET with CALL to our hook
        hook_bank_addr = ((hook_code_offset - 0x034000) + 0x4000) & 0x7FFF
        rom[oam_dma_ret_addr] = 0xCD  # CALL
        rom[oam_dma_ret_addr + 1] = hook_bank_addr & 0xFF
        rom[oam_dma_ret_addr + 2] = (hook_bank_addr >> 8) & 0xFF
        
        print(f"✓ Installed OAM DMA completion hook")
        print(f"  - Hook at RET after DMA (0x{oam_dma_ret_addr:04X})")
        print(f"  - Hook code at ROM offset 0x{hook_code_offset:06X} (bank 13 addr 0x{hook_bank_addr:04X})")
        print(f"  - Calls sprite loop at bank 13 addr 0x{sprite_loop_bank_addr:04X}")
    else:
        print(f"⚠️  RET not found at expected address 0x{oam_dma_ret_addr:04X} (found 0x{rom[oam_dma_ret_addr]:02X})")
    
    # CRITICAL: Patch DMG palette register writes (FF47/FF48/FF49)
    # In GBC mode, writes to these registers should be no-ops
    # We'll hook these addresses and make them return immediately
    
    # Find and patch common patterns: E0 47, E0 48, E0 49 (LD [FF47], A, etc.)
    # Strategy: Replace with NOPs or redirect to safe location
    # For now, we'll patch at the hardware level by intercepting writes
    
    # Alternative: Hook VBlank and ensure DMG registers aren't written
    # Or: Patch the write instructions themselves
    
    # Simple approach: Create a hook that intercepts writes to FF47/FF48/FF49
    # and makes them no-ops. This requires memory callbacks which we can't do in ROM.
    
    # Better approach: Find the functions that write to these registers and patch them
    # Search for patterns: E0 47, E0 48, E0 49 (LD [FF47], A)
    
    dmg_patch_count = 0
    # Search for LD [FF47], A patterns (E0 47)
    # In GBC mode, these writes should be ignored (no-op)
    # Safer: Replace with LD [FF00], A (write to unused register) or NOP
    for addr in range(0x0100, len(rom) - 1):
        if rom[addr] == 0xE0:  # LD [nn], A
            reg = rom[addr + 1]
            if reg == 0x47 or reg == 0x48 or reg == 0x49:  # FF47, FF48, FF49
                # Replace with LD [FF00], A (write to P1 register - safe no-op in CGB mode)
                # This preserves register A and doesn't break code flow
                rom[addr] = 0xE0  # LD [nn], A (keep same instruction)
                rom[addr + 1] = 0x00  # FF00 (P1 register - safe to write)
                dmg_patch_count += 1
                if dmg_patch_count <= 10:  # Only print first 10
                    print(f"  Patched DMG palette write at 0x{addr:04X} (register 0xFF{reg:02X} -> FF00)")
    
    if dmg_patch_count > 10:
        print(f"  ... and {dmg_patch_count - 10} more DMG palette writes patched")
    
    # Hook VBlank interrupt (0x0040) to run sprite loop every frame
    # This ensures palette assignments persist even when game updates OAM
    vblank_hook_addr = sprite_loop_start + len(combined_bank13) + 256  # After lookup table
    vblank_hook_bank_addr = ((vblank_hook_addr - 0x034000) + 0x4000) & 0x7FFF
    
    # VBlank hook: Switch to bank 13, run sprite loop, restore bank, call original VBlank
    vblank_hook_code = bytes([
        0xF5,                          # PUSH AF
        0x3E, 0x0D,                    # LD A, 13
        0xEA, 0x00, 0x20,              # LD [2000], A (switch to bank 13)
        0xCD, vblank_hook_bank_addr & 0xFF, (vblank_hook_bank_addr >> 8) & 0xFF,  # CALL sprite_loop
        0x3E, 0x01,                    # LD A, 1 (restore original bank)
        0xEA, 0x00, 0x20,              # LD [2000], A
        0xF1,                          # POP AF
        # Call original VBlank handler (save original first)
    ])
    
    # Save original VBlank handler
    original_vblank = bytes(rom[0x0040:0x0043])  # Original JP instruction
    rom[vblank_hook_addr:vblank_hook_addr+len(vblank_hook_code)] = vblank_hook_code
    
    # Install VBlank hook
    rom[0x0040] = 0xC3  # JP
    rom[0x0041] = vblank_hook_addr & 0xFF
    rom[0x0042] = (vblank_hook_addr >> 8) & 0xFF
    
    # Also keep input handler trampoline for compatibility
    trampoline = bytes([
        0xF5, 0x3E, 0x0D, 0xEA, 0x00, 0x20, 0xCD, 0x00, 0x6D, 0x3E, 0x01, 0xEA, 0x00, 0x20, 0xF1, 0xC9
    ])
    rom[0x0824:0x0824+len(trampoline)] = trampoline
    if len(trampoline) < 46:
        rom[0x0824+len(trampoline):0x0824+46] = bytes([0x00] * (46 - len(trampoline)))
    
    mapped_count = sum(1 for x in lookup_table if x != 0xFF)
    print(f"✓ Built ROM with GBC-NATIVE approach")
    print(f"  - Strategy: Patch DMG palette register writes (FF47/FF48/FF49)")
    print(f"  - DMG patches applied: {dmg_patch_count}")
    print(f"  - CGB palettes loaded once, used via OAM bits (GBC-native)")
    print(f"  - Lookup table: {mapped_count} tiles mapped")
    print(f"  - Sara W (tiles 4-7): Palette 1 (green/orange)")
    print(f"  - Dragonfly (tiles 0-3): Palette 0 (red/black)")
    print(f"  - Overhead: {len(combined_bank13)} bytes")
    output_rom_path.write_bytes(rom)

if __name__ == "__main__":
    main()

