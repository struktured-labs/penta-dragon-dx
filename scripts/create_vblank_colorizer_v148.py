#!/usr/bin/env python3
"""
v1.48: VRAM Bank 1 Initialization with Self-Checking

FIX: v1.46 failed because 0xFFC2 is used by the game for input state!

New approach: Use a signature byte IN VRAM bank 1 itself to detect if
initialization is needed. No external flags that could conflict with game.

Strategy:
1. During VBlank, switch to VRAM bank 1
2. Read signature location (0x9BFF - last byte of tilemap)
3. If != 0x42 (our signature), initialize all attributes to 0 and write 0x42
4. Switch back to bank 0

This only runs initialization once (when signature is missing).
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palettes_from_yaml(yaml_path: Path):
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    def pal_to_bytes(colors):
        result = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            result.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(result)

    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    obj_keys = ['Effects', 'SaraDragon', 'SaraWitch', 'Crow',
                'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    boss_data = data.get('boss_palettes', {})
    gargoyle = pal_to_bytes(boss_data.get('Gargoyle', {}).get('colors', ["0000", "601F", "400F", "0000"]))
    spider = pal_to_bytes(boss_data.get('Spider', {}).get('colors', ["0000", "001F", "00BF", "0000"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider


def create_tile_based_colorizer():
    """Sprite colorizer from v1.09 (unchanged)."""
    code = bytearray()
    labels = {}
    jumps_to_fix = []
    code.extend([0x06, 0x28])
    labels['loop_start'] = len(code)
    code.extend([0x3E, 0x28])
    code.append(0x90)
    code.extend([0xFE, 0x04])
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])
    code.append(0x2B)
    code.append(0x7E)
    code.append(0x23)
    code.append(0x4F)
    code.extend([0xFE, 0x10])
    jumps_to_fix.append((len(code), 'projectile_palette'))
    code.extend([0x38, 0x00])
    code.append(0x7B)
    code.append(0xB7)
    jumps_to_fix.append((len(code), 'boss_palette'))
    code.extend([0x20, 0x00])
    code.append(0x79)
    code.extend([0xFE, 0x50])
    jumps_to_fix.append((len(code), 'check_hornet'))
    code.extend([0x38, 0x00])
    code.extend([0xFE, 0x60])
    jumps_to_fix.append((len(code), 'orc_palette'))
    code.extend([0x38, 0x00])
    code.extend([0xFE, 0x70])
    jumps_to_fix.append((len(code), 'humanoid_palette'))
    code.extend([0x38, 0x00])
    code.extend([0xFE, 0x80])
    jumps_to_fix.append((len(code), 'miniboss_palette'))
    code.extend([0x38, 0x00])
    labels['default_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['check_hornet'] = len(code)
    code.append(0x79)
    code.extend([0xFE, 0x40])
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x30, 0x00])
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['sara_palette'] = len(code)
    code.append(0x7A)
    code.append(0xE5)
    code.extend([0x26, 0xC0])
    code.append(0x6F)
    code.append(0x2B)
    code.append(0x2B)
    code.append(0x7E)
    code.append(0xE1)
    code.extend([0xE6, 0x08])
    jumps_to_fix.append((len(code), 'sara_w'))
    code.extend([0x28, 0x00])
    code.extend([0x3E, 0x01])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['sara_w'] = len(code)
    code.extend([0x3E, 0x02])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['boss_palette'] = len(code)
    code.append(0x5F)
    code.extend([0x3E, 0x06])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['hornet_palette'] = len(code)
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['orc_palette'] = len(code)
    code.extend([0x3E, 0x05])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['humanoid_palette'] = len(code)
    code.extend([0x3E, 0x06])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])
    labels['miniboss_palette'] = len(code)
    code.extend([0x3E, 0x03])
    labels['apply_palette'] = len(code)
    code.append(0x2B)
    code.append(0x46)
    code.extend([0xE6, 0x07])
    code.append(0xB0)
    code.append(0x77)
    code.extend([0x23, 0x23, 0x23, 0x23])
    code.append(0x05)
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])
    code.append(0xC9)
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF
    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr):
    """Shadow OAM colorizer (unchanged from v1.09)."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])
    code.extend([0xF0, 0xBE])
    code.append(0xB7)
    code.extend([0x20, 0x04])
    code.extend([0x16, 0x02])
    code.extend([0x18, 0x02])
    code.extend([0x16, 0x01])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x28, 0x08])
    code.extend([0xFE, 0x02])
    code.extend([0x28, 0x06])
    code.extend([0x1E, 0x00])
    code.extend([0x18, 0x06])
    code.extend([0x1E, 0x06])
    code.extend([0x18, 0x02])
    code.extend([0x1E, 0x07])
    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])
    code.append(0xC9)
    return bytes(code)


def create_vram_bank1_init():
    """
    One-time VRAM bank 1 initialization with self-checking signature.

    Uses signature byte at 0x9BFF (last byte of tilemap area).
    If signature != 0x42, initialize all attributes to 0 and write signature.

    This runs during VBlank and should be safe because:
    1. We're not using any game HRAM/WRAM variables
    2. The initialization only happens ONCE
    3. After signature is set, this becomes a quick no-op
    """
    SIGNATURE = 0x42
    SIGNATURE_ADDR = 0x9BFF  # Last byte of 0x9800-0x9BFF tilemap

    code = bytearray()

    # Save all registers we'll use
    code.extend([0xF5])                 # PUSH AF
    code.extend([0xC5])                 # PUSH BC
    code.extend([0xE5])                 # PUSH HL

    # Switch to VRAM bank 1
    code.extend([0x3E, 0x01])           # LD A, 1
    code.extend([0xE0, 0x4F])           # LDH [VBK], A

    # Check signature at 0x9BFF
    code.extend([0xFA, SIGNATURE_ADDR & 0xFF, SIGNATURE_ADDR >> 8])  # LD A, [0x9BFF]
    code.extend([0xFE, SIGNATURE])      # CP 0x42

    # If signature matches, skip initialization
    skip_init_offset_pos = len(code)
    code.extend([0x28, 0x00])           # JR Z, skip_init (placeholder)

    # --- Initialize VRAM bank 1 ---
    # Fill 0x9800-0x9BFF (1024 bytes) with 0x00 (palette 0, no flip)
    code.extend([0x21, 0x00, 0x98])     # LD HL, 0x9800
    code.extend([0x01, 0x00, 0x04])     # LD BC, 0x0400 (1024 bytes)
    code.extend([0xAF])                 # XOR A (A = 0)

    # Fill loop
    fill_loop = len(code)
    code.append(0x22)                   # LD [HL+], A
    code.append(0x0B)                   # DEC BC
    code.append(0x78)                   # LD A, B
    code.append(0xB1)                   # OR C
    jump_back = fill_loop - len(code) - 2
    code.extend([0x20, jump_back & 0xFF])  # JR NZ, fill_loop

    # Write signature
    code.extend([0x3E, SIGNATURE])      # LD A, 0x42
    code.extend([0xEA, SIGNATURE_ADDR & 0xFF, SIGNATURE_ADDR >> 8])  # LD [0x9BFF], A

    # Fix the skip_init jump offset
    skip_init_target = len(code)
    code[skip_init_offset_pos + 1] = (skip_init_target - skip_init_offset_pos - 2) & 0xFF

    # --- skip_init: ---
    # Switch back to VRAM bank 0
    code.extend([0xAF])                 # XOR A (A = 0)
    code.extend([0xE0, 0x4F])           # LDH [VBK], A

    # Restore registers
    code.extend([0xE1])                 # POP HL
    code.extend([0xC1])                 # POP BC
    code.extend([0xF1])                 # POP AF

    code.append(0xC9)                   # RET

    return bytes(code)


def create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr):
    """Palette loader (unchanged from v1.09)."""
    code = bytearray()
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x68])
    code.extend([0x06, 0x40])
    code.append(0x2A)
    code.extend([0xE0, 0x69])
    code.append(0x05)
    code.extend([0x20, 0xFA])
    obj_data_addr = palette_data_addr + 64
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x6A])
    code.extend([0x06, 0x30])
    code.append(0x2A)
    code.extend([0xE0, 0x6B])
    code.append(0x05)
    code.extend([0x20, 0xFA])
    pal6_normal_addr = obj_data_addr + 48
    code.extend([0x21, pal6_normal_addr & 0xFF, (pal6_normal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x20, 0x03])
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x3E, 0xB0])
    code.extend([0xE0, 0x6A])
    code.extend([0x0E, 0x08])
    code.append(0x2A)
    code.extend([0xE0, 0x6B])
    code.append(0x0D)
    code.extend([0x20, 0xFA])
    pal7_normal_addr = obj_data_addr + 56
    code.extend([0x21, pal7_normal_addr & 0xFF, (pal7_normal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x03])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.append(0x2A)
    code.extend([0xE0, 0x6B])
    code.append(0x0D)
    code.extend([0x20, 0xFA])
    code.append(0xC9)
    return bytes(code)


def create_combined_func(palette_loader_addr, shadow_main_addr, vram_init_addr):
    """Combined function for VBlank - now includes VRAM bank 1 init."""
    code = bytearray()
    # First: one-time VRAM bank 1 initialization
    code.extend([0xCD, vram_init_addr & 0xFF, vram_init_addr >> 8])
    # Then: palette loading
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    # Then: sprite colorization
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    # Finally: original input handler
    code.extend([0xCD, 0x80, 0xFF])
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr):
    """VBlank hook (unchanged)."""
    simplified_input = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xB0,
        0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,
        0x3E, 0x01, 0xEA, 0x00, 0x20,
        0xC9,
    ])
    return bytes(simplified_input + hook_code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_v148.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.48: VRAM Bank 1 Init with Self-Checking ===")
    print("  FIX: v1.46 used 0xFFC2 which conflicts with game input!")
    print("  NEW: Uses signature byte IN VRAM bank 1 itself")
    print("  - Checks 0x9BFF for signature 0x42")
    print("  - If missing, initializes all attributes to 0")
    print("  - Writes signature after init (one-time only)")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    colorizer_addr = 0x6900
    shadow_main_addr = 0x6980
    palette_loader_addr = 0x69E0
    vram_init_addr = 0x6A60      # NEW: VRAM bank 1 initializer
    combined_addr = 0x6AC0

    # Generate code
    colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    vram_init = create_vram_bank1_init()
    combined = create_combined_func(palette_loader_addr, shadow_main_addr, vram_init_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Sprite colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"VRAM init: {len(vram_init)} bytes at 0x{vram_init_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    def write_to_bank13(addr, data):
        offset = bank13_offset + (addr - 0x4000)
        rom[offset:offset + len(data)] = data

    write_to_bank13(palette_data_addr, bg_data)
    write_to_bank13(palette_data_addr + 64, obj_data)
    write_to_bank13(gargoyle_addr, gargoyle)
    write_to_bank13(spider_addr, spider)
    write_to_bank13(colorizer_addr, colorizer)
    write_to_bank13(shadow_main_addr, shadow_main)
    write_to_bank13(palette_loader_addr, palette_loader)
    write_to_bank13(vram_init_addr, vram_init)
    write_to_bank13(combined_addr, combined)

    # Patch original VBlank
    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    rom[0x143] = 0x80  # CGB flag

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v1.48 Build Complete ===")
    print("\nThis version initializes VRAM bank 1 once (when signature missing)")
    print("Should NOT conflict with game variables.")


if __name__ == "__main__":
    main()
