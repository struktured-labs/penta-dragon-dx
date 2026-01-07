#!/usr/bin/env python3
"""
v1.16: HDMA-based BG Colorization

Uses GBC HDMA hardware to efficiently copy BG tile attributes.

Architecture:
1. VBlank: Scan C1A0 buffer (192 bytes) → build attribute buffer in WRAM
2. VBlank: Start HDMA to copy attributes to VRAM bank 1
3. HDMA runs during HBlanks, copying 16 bytes per scanline

HDMA Registers:
  FF51-52: Source address (WRAM attribute buffer)
  FF53-54: Destination address (VRAM bank 1 tilemap)
  FF55: Length/Mode (bit 7 = HBlank mode)

Item tiles (0x88-0xDF) get BG palette 1 (gold).
All other tiles get BG palette 0.
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


def create_attr_buffer_prep() -> bytes:
    """
    Prepare attribute buffer from C1A0 tile buffer.

    Reads 192 bytes from C1A0 (8 rows × 24 tiles).
    Writes 256 bytes to D000 (8 rows × 32 tiles, with 8-byte padding per row).

    For each tile:
      - 0x88 <= tile < 0xE0: palette 1 (items)
      - Otherwise: palette 0
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Switch to WRAM bank 2 for our buffer
    code.extend([0x3E, 0x02])        # LD A, 2
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # HL = C1A0 (source: tile buffer in WRAM bank 0, always accessible)
    # DE = D000 (dest: attribute buffer in WRAM bank 2)
    code.extend([0x21, 0xA0, 0xC1])  # LD HL, 0xC1A0
    code.extend([0x11, 0x00, 0xD0])  # LD DE, 0xD000

    # B = 8 rows
    code.extend([0x06, 0x08])        # LD B, 8

    labels['row_loop'] = len(code)
    # C = 24 tiles per row
    code.extend([0x0E, 0x18])        # LD C, 24

    labels['col_loop'] = len(code)
    # Read tile ID from source
    code.append(0x2A)                # LD A, [HL+]

    # Check if item tile (0x88 <= tile < 0xE0)
    code.extend([0xFE, 0x88])        # CP 0x88
    jumps_to_fix.append((len(code), 'not_item'))
    code.extend([0x38, 0x00])        # JR C, not_item

    code.extend([0xFE, 0xE0])        # CP 0xE0
    jumps_to_fix.append((len(code), 'not_item'))
    code.extend([0x30, 0x00])        # JR NC, not_item

    # Item tile - set palette 1
    code.extend([0x3E, 0x01])        # LD A, 1
    jumps_to_fix.append((len(code), 'write_attr'))
    code.extend([0x18, 0x00])        # JR write_attr

    labels['not_item'] = len(code)
    # Not item - set palette 0
    code.extend([0x3E, 0x00])        # LD A, 0

    labels['write_attr'] = len(code)
    # Write attribute to dest
    code.append(0x12)                # LD [DE], A
    code.append(0x13)                # INC DE

    # Loop columns
    code.append(0x0D)                # DEC C
    jumps_to_fix.append((len(code), 'col_loop'))
    code.extend([0x20, 0x00])        # JR NZ, col_loop

    # End of row - add 8 bytes padding to dest (32-24=8)
    # DE += 8
    code.extend([0x3E, 0x08])        # LD A, 8
    code.append(0x83)                # ADD E
    code.append(0x5F)                # LD E, A
    code.extend([0x30, 0x01])        # JR NC, +1
    code.append(0x14)                # INC D

    # Loop rows
    code.append(0x05)                # DEC B
    jumps_to_fix.append((len(code), 'row_loop'))
    code.extend([0x20, 0x00])        # JR NZ, row_loop

    # Switch back to WRAM bank 1
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)                # RET

    # Fix jumps
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_hdma_setup() -> bytes:
    """
    Set up and start HDMA to copy attribute buffer to VRAM bank 1.

    Source: D000 (WRAM bank 2, 256 bytes)
    Dest: 9800 or 9C00 (VRAM bank 1) based on DC0B tilemap toggle

    Uses HBlank DMA mode - copies 16 bytes per HBlank.
    256 bytes = 16 blocks, so 16 HBlanks to complete.
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    # Save registers
    code.extend([0xF5, 0xC5])        # PUSH AF, BC

    # Switch to WRAM bank 2 to access our buffer
    code.extend([0x3E, 0x02])        # LD A, 2
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # Set HDMA source: D000
    code.extend([0x3E, 0xD0])        # LD A, 0xD0
    code.extend([0xE0, 0x51])        # LDH [FF51], A (HDMA1 - source high)
    code.extend([0x3E, 0x00])        # LD A, 0x00
    code.extend([0xE0, 0x52])        # LDH [FF52], A (HDMA2 - source low)

    # Get tilemap base from DC0B (need to read from WRAM bank 1)
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A - switch to bank 1
    code.extend([0xFA, 0x0B, 0xDC])  # LD A, [DC0B]
    code.extend([0xE6, 0x01])        # AND 1
    jumps_to_fix.append((len(code), 'use_9800'))
    code.extend([0x28, 0x00])        # JR Z, use_9800

    # Use 9C00
    code.extend([0x3E, 0x9C])        # LD A, 0x9C
    jumps_to_fix.append((len(code), 'set_dest'))
    code.extend([0x18, 0x00])        # JR set_dest

    labels['use_9800'] = len(code)
    code.extend([0x3E, 0x98])        # LD A, 0x98

    labels['set_dest'] = len(code)
    code.extend([0xE0, 0x53])        # LDH [FF53], A (HDMA3 - dest high)
    code.extend([0x3E, 0x00])        # LD A, 0x00
    code.extend([0xE0, 0x54])        # LDH [FF54], A (HDMA4 - dest low)

    # Switch to VRAM bank 1 for attribute map
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A (VBK)

    # CRITICAL: Switch back to WRAM bank 2 before starting HDMA
    # HDMA reads from the currently selected WRAM bank!
    code.extend([0x3E, 0x02])        # LD A, 2
    code.extend([0xE0, 0x70])        # LDH [FF70], A - switch to bank 2

    # Start General Purpose DMA (not HBlank)
    # 256 bytes = 16 blocks of 16 bytes
    # Length = (16 - 1) = 0x0F
    # Bit 7 = 0 for General Purpose DMA (immediate copy during VBlank)
    # This avoids bank switching issues during multi-scanline HBlank DMA
    code.extend([0x3E, 0x0F])        # LD A, 0x0F
    code.extend([0xE0, 0x55])        # LDH [FF55], A (HDMA5 - start DMA)

    # Switch back to VRAM bank 0
    code.extend([0x3E, 0x00])        # LD A, 0
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A

    # Switch back to WRAM bank 1
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x70])        # LDH [FF70], A

    # Restore registers
    code.extend([0xC1, 0xF1])        # POP BC, AF
    code.append(0xC9)                # RET

    # Fix jumps
    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_tile_based_colorizer() -> bytes:
    """OBJ tile-based colorizer (same as v1.11)."""
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    code.extend([0x06, 0x28])  # LD B, 40
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

    code.extend([0xFE, 0x30])
    jumps_to_fix.append((len(code), 'crow_palette'))
    code.extend([0x30, 0x00])

    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['crow_palette'] = len(code)
    code.extend([0x3E, 0x03])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['sara_palette'] = len(code)
    code.append(0x7A)
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['boss_palette'] = len(code)
    code.extend([0x3E, 0x07])
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
    code.extend([0x3E, 0x07])

    labels['apply_palette'] = len(code)
    code.append(0x4F)
    code.append(0x7E)
    code.extend([0xE6, 0xF8])
    code.append(0xB1)
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


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """Colorizes BOTH shadow buffers."""
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


def create_palette_loader(palette_data_addr: int, gargoyle_addr: int, spider_addr: int) -> bytes:
    """Load CGB palettes with dynamic boss palette swapping."""
    code = bytearray()

    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x68])
    code.extend([0x0E, 0x40])
    code.extend([0x2A])
    code.extend([0xE0, 0x69])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    obj_data_addr = palette_data_addr + 64
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80])
    code.extend([0xE0, 0x6A])
    code.extend([0x0E, 0x30])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x01])
    code.extend([0x20, 0x03])
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    pal7_normal_addr = obj_data_addr + 56
    code.extend([0x21, pal7_normal_addr & 0xFF, (pal7_normal_addr >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x03])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A])
    code.extend([0xE0, 0x6B])
    code.extend([0x0D])
    code.extend([0x20, 0xFA])

    code.append(0xC9)
    return bytes(code)


def create_combined_with_hdma(palette_loader_addr: int, shadow_main_addr: int,
                               attr_prep_addr: int, hdma_setup_addr: int) -> bytes:
    """
    Combined VBlank function with HDMA BG colorization.

    Order:
    1. Load palettes
    2. Colorize OBJ shadows
    3. Prepare BG attribute buffer
    4. Start HDMA transfer
    5. Run OAM DMA
    """
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, attr_prep_addr & 0xFF, attr_prep_addr >> 8])
    code.extend([0xCD, hdma_setup_addr & 0xFF, hdma_setup_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF])  # CALL DMA (OAM)
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
    output_rom = Path("rom/working/penta_dragon_dx_v116.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_path = Path("palettes/penta_palettes_v097.yaml")

    print(f"Loading palettes from: {palette_path}")
    bg_data, obj_data, gargoyle, spider = load_palettes_from_yaml(palette_path)

    print("\n=== v1.16: HDMA-based BG Colorization ===")
    print("  NEW: Uses GBC HDMA for efficient attribute copying")
    print("  Scans C1A0 buffer (192 tiles) during VBlank")
    print("  HDMA copies attributes during HBlanks (16 bytes/scanline)")
    print("  Item tiles 0x88-0xDF → BG palette 1 (gold)")
    print()

    rom = bytearray(input_rom.read_bytes())
    apply_all_display_patches(rom)

    # Bank 13 layout
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    obj_colorizer_addr = 0x6900
    attr_prep_addr = 0x6980       # NEW: Attribute buffer preparation
    hdma_setup_addr = 0x6A00      # NEW: HDMA setup routine
    shadow_main_addr = 0x6A60
    palette_loader_addr = 0x6AC0
    combined_addr = 0x6B20

    obj_colorizer = create_tile_based_colorizer()
    attr_prep = create_attr_buffer_prep()
    hdma_setup = create_hdma_setup()
    shadow_main = create_shadow_colorizer_main(obj_colorizer_addr)
    palette_loader = create_palette_loader(palette_data_addr, gargoyle_addr, spider_addr)
    combined = create_combined_with_hdma(palette_loader_addr, shadow_main_addr,
                                          attr_prep_addr, hdma_setup_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"OBJ Colorizer: {len(obj_colorizer)} bytes at 0x{obj_colorizer_addr:04X}")
    print(f"Attr buffer prep: {len(attr_prep)} bytes at 0x{attr_prep_addr:04X}")
    print(f"HDMA setup: {len(hdma_setup)} bytes at 0x{hdma_setup_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Combined func: {len(combined)} bytes at 0x{combined_addr:04X}")

    # Write to bank 13
    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (gargoyle_addr - 0x4000):bank13_offset + (gargoyle_addr - 0x4000) + len(gargoyle)] = gargoyle
    rom[bank13_offset + (spider_addr - 0x4000):bank13_offset + (spider_addr - 0x4000) + len(spider)] = spider
    rom[bank13_offset + (obj_colorizer_addr - 0x4000):bank13_offset + (obj_colorizer_addr - 0x4000) + len(obj_colorizer)] = obj_colorizer
    rom[bank13_offset + (attr_prep_addr - 0x4000):bank13_offset + (attr_prep_addr - 0x4000) + len(attr_prep)] = attr_prep
    rom[bank13_offset + (hdma_setup_addr - 0x4000):bank13_offset + (hdma_setup_addr - 0x4000) + len(hdma_setup)] = hdma_setup
    rom[bank13_offset + (shadow_main_addr - 0x4000):bank13_offset + (shadow_main_addr - 0x4000) + len(shadow_main)] = shadow_main
    rom[bank13_offset + (palette_loader_addr - 0x4000):bank13_offset + (palette_loader_addr - 0x4000) + len(palette_loader)] = palette_loader
    rom[bank13_offset + (combined_addr - 0x4000):bank13_offset + (combined_addr - 0x4000) + len(combined)] = combined

    print(f"\nOriginal at 0x06D5: {rom[0x06D5:0x06D8].hex()}")
    rom[0x06D5:0x06D8] = bytes([0x00, 0x00, 0x00])
    print("Patched 0x06D5: 00 00 00 (NOP)")

    print(f"\nVBlank hook: {len(vblank_hook)} bytes")
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    rom[0x143] = 0x80
    print("Set CGB flag at 0x143")

    output_rom.write_bytes(rom)
    fixed_rom.write_bytes(rom)

    print(f"\nWrote: {output_rom}")
    print(f"Wrote: {fixed_rom}")
    print("\n=== v1.16 Build Complete ===")
    print("\nKey features:")
    print("  - HDMA hardware-accelerated attribute copying")
    print("  - Scans 192 tiles from C1A0 buffer")
    print("  - No CALL site hooks (stable!)")
    print("  - OBJ colorization unchanged from v1.11")


if __name__ == "__main__":
    main()
