#!/usr/bin/env python3
"""
v1.04: Pre-DMA Shadow Colorization - FIXES FLICKERING

Key change from v1.03:
- NOP out the DMA call at 0x06D5
- Our hook at 0x0824 now: colorizes shadows → calls DMA → returns
- DMA copies ALREADY-COLORIZED shadow buffers to hardware
- No more flickering!

Previous approach (v1.03 - BROKEN):
  VBlank: DMA copies uncolorized shadow → hardware
  VBlank: Our hook colorizes hardware OAM (TOO LATE!)
  Result: Game writes uncolorized data to shadows, DMA copies it → FLICKER

New approach (v1.04 - FIXED):
  VBlank: 0x06D5 = NOP NOP NOP (DMA delayed)
  VBlank: 0x06DC = CALL 0x0824 (our hook)
  Our hook: Colorize shadows → Call DMA → Return
  Result: DMA always copies colorized data → NO FLICKER
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


def create_simplified_oam_colorizer() -> bytes:
    """
    Simplified slot-based colorizer.
    Input: HL = pointer to first flags byte (0xC003 or 0xC103)
           D = Sara palette, E = enemy/boss palette
    """
    code = bytearray()
    code.extend([0x06, 0x28])        # LD B, 40
    loop_start = len(code)
    code.extend([0x3E, 0x28])        # LD A, 40
    code.append(0x90)                # SUB B
    code.extend([0xFE, 0x04])        # CP 4
    code.extend([0x38, 0x03])        # JR C, +3 (Sara)
    code.append(0x7B)                # LD A, E (enemy)
    code.extend([0x18, 0x01])        # JR +1
    code.append(0x7A)                # LD A, D (Sara)
    code.append(0x4F)                # LD C, A
    code.append(0x7E)                # LD A, [HL]
    code.extend([0xE6, 0xF8])        # AND 0xF8
    code.append(0xB1)                # OR C
    code.append(0x77)                # LD [HL], A
    code.extend([0x23, 0x23, 0x23, 0x23])  # INC HL x4
    code.append(0x05)                # DEC B
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])
    code.append(0xC9)                # RET
    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """
    Colorizes BOTH shadow buffers (0xC000 and 0xC100).
    Called BEFORE DMA so DMA copies already-colorized data.
    """
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # Determine Sara palette (D)
    code.extend([0xF0, 0xBE])        # LDH A, [FFBE]
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x04])        # JR NZ, +4 (Dragon)
    code.extend([0x16, 0x02])        # LD D, 2 (Witch)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x16, 0x01])        # LD D, 1 (Dragon)

    # Determine enemy palette (E)
    code.extend([0xF0, 0xBF])        # LDH A, [FFBF]
    code.append(0xB7)                # OR A
    code.extend([0x28, 0x04])        # JR Z, +4 (no boss)
    code.extend([0x1E, 0x07])        # LD E, 7 (boss)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x1E, 0x04])        # LD E, 4 (normal)

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
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40])
    code.extend([0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA])
    code.extend([0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x30])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.extend([0xF0, 0xBF, 0xFE, 0x01, 0x20, 0x05])
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x18, 0x00, 0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    obj_pal7 = palette_data_addr + 64 + 56
    code.extend([0x21, obj_pal7 & 0xFF, (obj_pal7 >> 8) & 0xFF])
    code.extend([0xF0, 0xBF, 0xFE, 0x02, 0x20, 0x05])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x18, 0x00, 0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])
    code.append(0xC9)
    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int) -> bytes:
    """
    Combined function in bank 13: palette load + colorize shadows + call DMA.
    DMA is at 0xFF80 (HRAM) which is always accessible.
    """
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])  # CALL palette_loader
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])        # CALL shadow_colorizer
    code.extend([0xCD, 0x80, 0xFF])  # CALL $FF80 (DMA) - copies colorized shadows to hardware!
    code.append(0xC9)  # RET
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """
    VBlank hook at 0x0824. v1.04: Input handler + colorize shadows + DMA.

    CRITICAL: Must include input handler - 0x0824 is called for input reading!

    Structure (46 bytes total):
    - Simplified input handler (32 bytes) - reads joypad, stores to 0xFF93
    - Hook code (14 bytes) - bank switch, call combined, bank switch, return
    """
    # Simplified input handler (32 bytes) - same as v1.03
    # This reads button/d-pad state and stores to 0xFF93
    simplified_input = bytearray([
        0x3E, 0x20,       # LD A, 0x20 (select buttons)
        0xE0, 0x00,       # LDH (FF00), A
        0xF0, 0x00,       # LDH A, (FF00)
        0x2F,             # CPL
        0xE6, 0x0F,       # AND 0x0F
        0xCB, 0x37,       # SWAP A
        0x47,             # LD B, A
        0x3E, 0x10,       # LD A, 0x10 (select d-pad)
        0xE0, 0x00,       # LDH (FF00), A
        0xF0, 0x00,       # LDH A, (FF00)
        0xF0, 0x00,       # LDH A, (FF00) (debounce read)
        0x2F,             # CPL
        0xE6, 0x0F,       # AND 0x0F
        0xB0,             # OR B
        0xE0, 0x93,       # LDH (FF93), A  <- Critical: store input state!
        0x3E, 0x30,       # LD A, 0x30 (deselect joypad)
        0xE0, 0x00,       # LDH (FF00), A
    ])  # 32 bytes

    # Hook code (14 bytes)
    hook_code = bytearray([
        0x3E, 0x0D,       # LD A, 0x0D (bank 13)
        0xEA, 0x00, 0x20, # LD (0x2000), A
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,  # CALL combined (palette+color+DMA)
        0x3E, 0x01,       # LD A, 0x01 (bank 1)
        0xEA, 0x00, 0x20, # LD (0x2000), A
        0xC9,             # RET
    ])  # 14 bytes

    # Total: 32 + 14 = 46 bytes
    return bytes(simplified_input + hook_code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_v104.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        return

    rom = bytearray(input_rom.read_bytes())
    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80  # CGB flag

    print(f"Loading palettes from: {palette_yaml}")
    bg_pal, obj_pal, gargoyle_pal, spider_pal = load_palettes_from_yaml(palette_yaml)

    print("\n=== v1.04: Pre-DMA Shadow Colorization ===")
    print("  CRITICAL FIX: NOP out DMA at 0x06D5, call DMA from our hook")
    print("  Sequence: VBlank → Our Hook → Colorize Shadows → DMA → Display")
    print()

    # Bank 13 layout
    BANK13_BASE = 0x034000
    PALETTE_DATA = 0x6800
    GARGOYLE_PAL = 0x6880
    SPIDER_PAL = 0x6888
    COLORIZER = 0x6900
    SHADOW_MAIN = 0x6940
    PALETTE_LOADER = 0x6980
    COMBINED_FUNC = 0x69D0  # New: palette + colorize + DMA

    # Write palette data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_pal
    rom[offset+64:offset+128] = obj_pal
    print(f"Palette data at 0x{PALETTE_DATA:04X}")

    # Write boss palettes
    offset = BANK13_BASE + (GARGOYLE_PAL - 0x4000)
    rom[offset:offset+8] = gargoyle_pal
    offset = BANK13_BASE + (SPIDER_PAL - 0x4000)
    rom[offset:offset+8] = spider_pal

    # Write colorizer
    colorizer = create_simplified_oam_colorizer()
    offset = BANK13_BASE + (COLORIZER - 0x4000)
    rom[offset:offset+len(colorizer)] = colorizer
    print(f"Colorizer: {len(colorizer)} bytes at 0x{COLORIZER:04X}")

    # Write shadow colorizer main
    shadow_main = create_shadow_colorizer_main(COLORIZER)
    offset = BANK13_BASE + (SHADOW_MAIN - 0x4000)
    rom[offset:offset+len(shadow_main)] = shadow_main
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{SHADOW_MAIN:04X}")

    # Write palette loader
    pal_loader = create_palette_loader(PALETTE_DATA, GARGOYLE_PAL, SPIDER_PAL)
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    rom[offset:offset+len(pal_loader)] = pal_loader
    print(f"Palette loader: {len(pal_loader)} bytes at 0x{PALETTE_LOADER:04X}")

    # Write combined function (palette + colorize + DMA)
    combined = create_combined_with_dma(PALETTE_LOADER, SHADOW_MAIN)
    offset = BANK13_BASE + (COMBINED_FUNC - 0x4000)
    rom[offset:offset+len(combined)] = combined
    print(f"Combined func: {len(combined)} bytes at 0x{COMBINED_FUNC:04X}")

    # === CRITICAL: Patch VBlank handler ===

    # Step 1: NOP out the original DMA call at 0x06D5
    # Original: CD 80 FF (CALL $FF80)
    # Patched:  00 00 00 (NOP NOP NOP)
    original_dma = bytes(rom[0x06D5:0x06D8])
    print(f"\nOriginal at 0x06D5: {original_dma.hex()} (expected: cd80ff)")

    rom[0x06D5] = 0x00  # NOP
    rom[0x06D6] = 0x00  # NOP
    rom[0x06D7] = 0x00  # NOP
    print(f"Patched 0x06D5: 00 00 00 (NOP NOP NOP - DMA delayed)")

    # Step 2: Create VBlank hook with input handler + colorization + DMA
    # CRITICAL: 0x0824 is the INPUT HANDLER - we must preserve input reading!
    vblank_hook = create_vblank_hook_with_input(COMBINED_FUNC)
    print(f"\nVBlank hook: {len(vblank_hook)} bytes (input handler + colorizer)")

    # Write hook at 0x0824
    # CRITICAL: Use exact length to avoid Python slice resize bug!
    rom[0x0824:0x0824+len(vblank_hook)] = vblank_hook
    print(f"Wrote VBlank hook at 0x0824")

    # Verify the hook
    verify = bytes(rom[0x0824:0x0824+len(vblank_hook)])
    print(f"Verification: {verify.hex()}")

    # Write ROM
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    print(f"\nWrote: {output_rom}")

    fixed_rom.write_bytes(rom)
    print(f"Wrote: {fixed_rom}")

    print("\n=== v1.04 Build Complete ===")
    print("New sequence:")
    print("  1. VBlank starts at 0x06D1")
    print("  2. 0x06D5: NOP NOP NOP (DMA skipped)")
    print("  3. 0x06D8: Frame counter increment")
    print("  4. 0x06DC: CALL 0x0824 (our hook)")
    print("  5. Our hook: Bank 13 → Colorize shadows → Bank 1 → DMA")
    print("  6. DMA copies COLORIZED shadows to hardware")
    print("  7. Display shows colorized sprites!")


if __name__ == "__main__":
    main()
