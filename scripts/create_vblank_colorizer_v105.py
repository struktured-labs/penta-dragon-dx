#!/usr/bin/env python3
"""
v1.05: Tile-based monster type colorization

Tile ranges → Different palettes per monster type:
- 0x00-0x0F: Projectiles (palette 0)
- 0x20-0x3F: Sara (slot-based, palettes 1/2)
- 0x40-0x4F: Hornets (palette 4 - yellow)
- 0x50-0x5F: Orcs (palette 5 - green)
- 0x60-0x6F: Humanoids (palette 6 - purple)
- 0x70-0x7F: Miniboss/Catfish (palette 7 - red)
- Default: palette 4 (enemies)
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytes, bytes, bytes, bytes]:
    """Load BG, OBJ, and boss palettes from YAML file."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    def pal_to_bytes(colors: list[str]) -> bytes:
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


def create_tile_based_colorizer() -> bytes:
    """
    Tile-based colorizer with monster type detection.

    Input: HL = pointer to flags byte, D = Sara palette, E = boss palette (unused now)

    Logic:
    - Slots 0-3: Sara (palette D)
    - Tile < 0x10: Projectile (palette 0)
    - Tile 0x40-0x4F: Hornets (palette 4)
    - Tile 0x50-0x5F: Orcs (palette 5)
    - Tile 0x60-0x6F: Humanoids (palette 6)
    - Tile 0x70-0x7F: Miniboss (palette 7)
    - Default: palette 4
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []  # (position, target_label)

    # LD B, 40
    code.extend([0x06, 0x28])

    # loop_start:
    labels['loop_start'] = len(code)

    # Check if Sara slot (0-3)
    code.extend([0x3E, 0x28])        # LD A, 40
    code.append(0x90)                # SUB B (A = slot number 0-39)
    code.extend([0xFE, 0x04])        # CP 4
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])        # JR C, sara_palette (placeholder)

    # Read tile (at HL-1)
    code.append(0x2B)                # DEC HL
    code.append(0x7E)                # LD A, [HL] (tile)
    code.append(0x23)                # INC HL
    code.append(0x4F)                # LD C, A (save tile)

    # Check projectile (tile < 0x10)
    code.extend([0xFE, 0x10])        # CP 0x10
    jumps_to_fix.append((len(code), 'projectile_palette'))
    code.extend([0x38, 0x00])        # JR C, projectile_palette (placeholder)

    # Check tile ranges for monster types
    # Tile 0x40-0x4F: Hornets
    code.extend([0xFE, 0x50])        # CP 0x50
    jumps_to_fix.append((len(code), 'check_hornet'))
    code.extend([0x38, 0x00])        # JR C, check_hornet (tile < 0x50)

    # Tile 0x50-0x5F: Orcs
    code.extend([0xFE, 0x60])        # CP 0x60
    jumps_to_fix.append((len(code), 'orc_palette'))
    code.extend([0x38, 0x00])        # JR C, orc_palette (tile 0x50-0x5F)

    # Tile 0x60-0x6F: Humanoids
    code.extend([0xFE, 0x70])        # CP 0x70
    jumps_to_fix.append((len(code), 'humanoid_palette'))
    code.extend([0x38, 0x00])        # JR C, humanoid_palette (tile 0x60-0x6F)

    # Tile 0x70-0x7F: Miniboss
    code.extend([0xFE, 0x80])        # CP 0x80
    jumps_to_fix.append((len(code), 'miniboss_palette'))
    code.extend([0x38, 0x00])        # JR C, miniboss_palette (tile 0x70-0x7F)

    # Default: palette 4
    labels['default_palette'] = len(code)
    code.extend([0x3E, 0x04])        # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette (placeholder)

    # check_hornet: (tile < 0x50, check if >= 0x40)
    labels['check_hornet'] = len(code)
    code.append(0x79)                # LD A, C (restore tile)
    code.extend([0xFE, 0x40])        # CP 0x40
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x30, 0x00])        # JR NC, hornet_palette (tile >= 0x40)
    # tile < 0x40, default palette
    code.extend([0x3E, 0x04])        # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette

    # sara_palette:
    labels['sara_palette'] = len(code)
    code.append(0x7A)                # LD A, D
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette (placeholder)

    # projectile_palette:
    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])        # LD A, 0
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette (placeholder)

    # hornet_palette:
    labels['hornet_palette'] = len(code)
    code.extend([0x3E, 0x04])        # LD A, 4
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette (placeholder)

    # orc_palette:
    labels['orc_palette'] = len(code)
    code.extend([0x3E, 0x05])        # LD A, 5
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette (placeholder)

    # humanoid_palette:
    labels['humanoid_palette'] = len(code)
    code.extend([0x3E, 0x06])        # LD A, 6
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])        # JR apply_palette (placeholder)

    # miniboss_palette:
    labels['miniboss_palette'] = len(code)
    code.extend([0x3E, 0x07])        # LD A, 7
    # Falls through to apply_palette

    # apply_palette:
    labels['apply_palette'] = len(code)
    code.append(0x4F)                # LD C, A
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8
    code.append(0xB1)                # OR C
    code.append(0x77)                # LD [HL], A

    # Next sprite
    code.extend([0x23, 0x23, 0x23, 0x23])  # INC HL x4
    code.append(0x05)                # DEC B
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop_start
    code.append(0xC9)                # RET

    # Fix all jump offsets
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """Colorizes BOTH shadow buffers (0xC000 and 0xC100)."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Determine Sara palette (D)
    code.extend([0xF0, 0xBE])        # LDH A, [FFBE]
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x04])        # JR NZ, +4 (Dragon)
    code.extend([0x16, 0x02])        # LD D, 2 (Witch)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x16, 0x01])        # LD D, 1 (Dragon)

    # E register unused in v1.05 (tile-based)
    code.extend([0x1E, 0x04])        # LD E, 4 (not used)

    # Colorize shadow buffer 1 (0xC000)
    code.extend([0x21, 0x03, 0xC0])  # LD HL, 0xC003
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    # Colorize shadow buffer 2 (0xC100)
    code.extend([0x21, 0x03, 0xC1])  # LD HL, 0xC103
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)                # RET
    return bytes(code)


def create_palette_loader(palette_data_addr: int, gargoyle_addr: int, spider_addr: int) -> bytes:
    """Load CGB palettes."""
    code = bytearray()
    # Load BG palettes
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40])
    code.extend([0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA])
    # Load OBJ palettes
    code.extend([0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x40])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.append(0xC9)
    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int) -> bytes:
    """Combined function: load palettes, colorize shadows, run DMA."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])  # CALL DMA
    code.append(0xC9)
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook at 0x0824 with input handler."""
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
    output_rom = Path("rom/working/penta_dragon_dx_v105.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.05: Tile-based Monster Type Colorization ===")
    print("  Tile ranges → Different palettes per monster type")
    print("  0x00-0x0F: Projectiles (palette 0)")
    print("  0x40-0x4F: Hornets (palette 4)")
    print("  0x50-0x5F: Orcs (palette 5)")
    print("  0x60-0x6F: Humanoids (palette 6)")
    print("  0x70-0x7F: Miniboss (palette 7)")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout
    palette_data_addr = 0x6800
    colorizer_addr = 0x6900
    shadow_main_addr = 0x6980
    palette_loader_addr = 0x69D0
    combined_addr = 0x6A00

    colorizer = create_tile_based_colorizer()
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, palette_data_addr + 64, palette_data_addr + 64)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (colorizer_addr - 0x4000):bank13_offset + (colorizer_addr - 0x4000) + len(colorizer)] = colorizer
    rom[bank13_offset + (shadow_main_addr - 0x4000):bank13_offset + (shadow_main_addr - 0x4000) + len(shadow_main)] = shadow_main
    rom[bank13_offset + (palette_loader_addr - 0x4000):bank13_offset + (palette_loader_addr - 0x4000) + len(palette_loader)] = palette_loader
    rom[bank13_offset + (combined_addr - 0x4000):bank13_offset + (combined_addr - 0x4000) + len(combined)] = combined

    # NOP out DMA at 0x06D5
    print(f"\nOriginal at 0x06D5: {rom[0x06D5:0x06D8].hex()}")
    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    print("Patched 0x06D5: 00 00 00 (NOP)")

    # Write VBlank hook
    print(f"\nVBlank hook: {len(vblank_hook)} bytes")
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    # Set CGB flag
    rom[0x143] = 0x80
    print("Set CGB flag at 0x143")

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v1.05 Build Complete ===")


if __name__ == "__main__":
    main()
