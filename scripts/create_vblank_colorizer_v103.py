#!/usr/bin/env python3
"""
v1.03: Simplified slot-based colorizer with NO tile lookup.

Key changes from v1.01:
1. Removed tile lookup table - uses pure slot-based assignment
2. Only colorizes hardware OAM (0xFE00), not shadow buffers
   (Shadow buffers get overwritten by game during active display anyway)
3. Simpler, smaller, faster colorizer code

Palette assignment:
- Slots 0-3: Palette 1 (Sara Dragon) or 2 (Sara Witch) based on form flag
- Slots 4-39: Palette 4 (enemies) or 7 (boss mode)
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

    # BG palettes
    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    # OBJ palettes (normal mode)
    obj_keys = ['Effects', 'SaraDragon', 'SaraWitch', 'Crow',
                'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    # Boss palettes
    boss_data = data.get('boss_palettes', {})
    gargoyle = pal_to_bytes(boss_data.get('Gargoyle', {}).get('colors', ["0000", "601F", "400F", "0000"]))
    spider = pal_to_bytes(boss_data.get('Spider', {}).get('colors', ["0000", "001F", "00BF", "0000"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider


def create_simplified_oam_colorizer() -> bytes:
    """
    Simplified slot-based colorizer.
    No tile lookup - just uses slot position.

    Input: HL = pointer to first flags byte (e.g., 0xFE03, 0xC003, 0xC103)
           D = Sara palette, E = enemy/boss palette
    Modifies: A, B, C, HL
    """
    code = bytearray()

    # HL is already set by caller to point to first flags byte

    # B = 40 (sprite counter)
    code.extend([0x06, 0x28])        # LD B, 40

    loop_start = len(code)

    # Calculate slot: A = 40 - B (slot 0 when B=40, slot 39 when B=1)
    code.extend([0x3E, 0x28])        # LD A, 40
    code.append(0x90)                # SUB B  ; A = slot number

    # Check if Sara (slots 0-3)
    code.extend([0xFE, 0x04])        # CP 4
    code.extend([0x38, 0x03])        # JR C, +3 (Sara path - skip enemy code)

    # Enemy path: use palette in E
    code.append(0x7B)                # LD A, E
    code.extend([0x18, 0x01])        # JR +1 (skip Sara, go to apply)

    # Sara path: use palette in D
    code.append(0x7A)                # LD A, D

    # Apply palette (A contains palette number 0-7)
    # apply:
    code.append(0x4F)                # LD C, A (save palette)
    code.append(0x7E)                # LD A, [HL] (read flags)
    code.extend([0xE6, 0xF8])        # AND 0xF8 (clear palette bits)
    code.append(0xB1)                # OR C (add new palette)
    code.append(0x77)                # LD [HL], A (write flags)

    # Move to next sprite (HL += 4)
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL
    code.append(0x23)                # INC HL

    # Loop
    code.append(0x05)                # DEC B
    loop_offset = loop_start - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])  # JR NZ, loop

    code.append(0xC9)                # RET

    return bytes(code)


def create_v103_main_loop(colorizer_addr: int) -> bytes:
    """
    Main VBlank hook: Determines Sara form and boss mode, then calls colorizer.
    Colorizes ALL THREE OAM buffers for complete coverage.
    """
    code = bytearray()

    # Save registers
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # PUSH AF, BC, DE, HL

    # === Determine Sara palette (store in D) ===
    # FFBE = Sara form (0 = Witch, non-0 = Dragon)
    code.extend([0xF0, 0xBE])        # LDH A, [0xFFBE]
    code.append(0xB7)                # OR A
    code.extend([0x20, 0x04])        # JR NZ, +4 (Sara Dragon)
    code.extend([0x16, 0x02])        # LD D, 2 (Sara Witch palette)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x16, 0x01])        # LD D, 1 (Sara Dragon palette)

    # === Determine enemy palette (store in E) ===
    # FFBF = Boss flag (non-0 = boss mode)
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.append(0xB7)                # OR A
    code.extend([0x28, 0x04])        # JR Z, +4 (no boss)
    code.extend([0x1E, 0x07])        # LD E, 7 (boss palette - red)
    code.extend([0x18, 0x02])        # JR +2
    code.extend([0x1E, 0x04])        # LD E, 4 (normal enemy palette)

    # === Colorize all three OAM buffers ===
    # Hardware OAM (0xFE00)
    code.extend([0x21, 0x03, 0xFE])  # LD HL, 0xFE03
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    # Shadow buffer 1 (0xC000)
    code.extend([0x21, 0x03, 0xC0])  # LD HL, 0xC003
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    # Shadow buffer 2 (0xC100)
    code.extend([0x21, 0x03, 0xC1])  # LD HL, 0xC103
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    # Restore registers
    code.extend([0xE1, 0xD1, 0xC1, 0xF1])  # POP HL, DE, BC, AF
    code.append(0xC9)                # RET

    return bytes(code)


def create_palette_loader(
    palette_data_addr: int,
    gargoyle_addr: int,
    spider_addr: int
) -> bytes:
    """Load CGB palettes with dynamic boss palette swapping."""
    code = bytearray()

    # BG palettes (8 palettes × 8 bytes = 64 bytes)
    code.extend([
        0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF,  # LD HL, palette_data
        0x3E, 0x80,  # LD A, 0x80 (auto-increment + palette 0)
        0xE0, 0x68,  # LDH (BCPS), A
        0x0E, 0x40,  # LD C, 64
    ])
    code.extend([0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA])  # loop: LDI A, [HL] / LDH (BCPD), A / DEC C / JR NZ

    # OBJ palettes 0-5 (6 palettes × 8 bytes = 48 bytes)
    code.extend([0x3E, 0x80, 0xE0, 0x6A, 0x0E, 0x30])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # OBJ palette 6: check for Gargoyle boss
    code.extend([0xF0, 0xBF])        # LDH A, (FFBF)
    code.extend([0xFE, 0x01])        # CP 1
    code.extend([0x20, 0x05])        # JR NZ, +5 (skip gargoyle)
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])  # LD HL, gargoyle
    code.extend([0x18, 0x00])        # JR +0 (placeholder)
    # Normal OBJ palette 6 continues from main palette data
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # OBJ palette 7: check for Spider boss
    obj_pal7_normal = palette_data_addr + 64 + 56  # After BG (64) + OBJ 0-6 (56)
    code.extend([0x21, obj_pal7_normal & 0xFF, (obj_pal7_normal >> 8) & 0xFF])
    code.extend([0xF0, 0xBF])
    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x05])
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x18, 0x00])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    code.append(0xC9)
    return bytes(code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_v103.gb")
    fixed_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        return

    rom = bytearray(input_rom.read_bytes())
    original_input = bytes(rom[0x0824:0x0824+46])

    # Apply display patches (CGB mode, etc.)
    rom, _ = apply_all_display_patches(rom)
    rom[0x143] = 0x80  # Set CGB flag

    print(f"Loading palettes from: {palette_yaml}")
    bg_palettes, obj_palettes, gargoyle_pal, spider_pal = load_palettes_from_yaml(palette_yaml)

    print("\n=== v1.03: Simplified Slot-Based Colorizer ===")
    print("  Key changes from v1.01:")
    print("    - Removed tile lookup (simpler, faster)")
    print("    - Only colorizes hardware OAM (0xFE00)")
    print("    - Sara: slots 0-3 get palette 1 or 2")
    print("    - Enemies: slots 4-39 get palette 4 or 7 (boss)")
    print()

    # Bank 13 layout
    BANK13_BASE = 0x034000

    PALETTE_DATA = 0x6800      # 128 bytes (64 BG + 64 OBJ)
    GARGOYLE_PAL = 0x6880      # 8 bytes
    SPIDER_PAL = 0x6888        # 8 bytes
    COLORIZER = 0x6900         # ~35 bytes
    MAIN_LOOP = 0x6940         # ~40 bytes
    PALETTE_LOADER = 0x6980    # ~80 bytes
    COMBINED_FUNC = 0x69E0     # Combined entry point

    # Write palette data
    offset = BANK13_BASE + (PALETTE_DATA - 0x4000)
    rom[offset:offset+64] = bg_palettes
    rom[offset+64:offset+128] = obj_palettes
    print(f"Palette data: 128 bytes at 0x{PALETTE_DATA:04X}")

    # Write boss palettes
    offset = BANK13_BASE + (GARGOYLE_PAL - 0x4000)
    rom[offset:offset+8] = gargoyle_pal
    offset = BANK13_BASE + (SPIDER_PAL - 0x4000)
    rom[offset:offset+8] = spider_pal
    print(f"Boss palettes: Gargoyle @ 0x{GARGOYLE_PAL:04X}, Spider @ 0x{SPIDER_PAL:04X}")

    # Write colorizer subroutine
    colorizer = create_simplified_oam_colorizer()
    offset = BANK13_BASE + (COLORIZER - 0x4000)
    rom[offset:offset+len(colorizer)] = colorizer
    print(f"Colorizer: {len(colorizer)} bytes at 0x{COLORIZER:04X}")

    # Write main loop
    main_loop = create_v103_main_loop(COLORIZER)
    offset = BANK13_BASE + (MAIN_LOOP - 0x4000)
    rom[offset:offset+len(main_loop)] = main_loop
    print(f"Main loop: {len(main_loop)} bytes at 0x{MAIN_LOOP:04X}")

    # Write palette loader
    pal_loader = create_palette_loader(PALETTE_DATA, GARGOYLE_PAL, SPIDER_PAL)
    offset = BANK13_BASE + (PALETTE_LOADER - 0x4000)
    rom[offset:offset+len(pal_loader)] = pal_loader
    print(f"Palette loader: {len(pal_loader)} bytes at 0x{PALETTE_LOADER:04X}")

    # Write combined function (palette load + OAM colorize)
    combined = bytearray()
    combined.extend([0xCD, PALETTE_LOADER & 0xFF, PALETTE_LOADER >> 8])  # CALL palette_loader
    combined.extend([0xCD, MAIN_LOOP & 0xFF, MAIN_LOOP >> 8])            # CALL main_loop
    combined.append(0xC9)  # RET
    offset = BANK13_BASE + (COMBINED_FUNC - 0x4000)
    rom[offset:offset+len(combined)] = combined
    print(f"Combined function: {len(combined)} bytes at 0x{COMBINED_FUNC:04X}")

    # Patch VBlank hook at 0x0824
    # Original: Input handler is 46 bytes, stores input to 0xFF93
    # Strategy: Run colorization first, then run the FULL input handler
    #
    # We have 46 bytes total. Our hook code is:
    #   LD A, 0x0D / LD (0x2000), A / CALL / LD A, 0x01 / LD (0x2000), A = 13 bytes
    # Remaining: 46 - 13 = 33 bytes for input handler
    #
    # The critical input store (E0 93) is at offset 38-39 in original.
    # We need to include that! So we need a different approach.
    #
    # NEW APPROACH: Put colorization AFTER input handling.
    # The input handler result is stored to 0xFF93, we don't need to preserve A.

    vblank_hook = bytearray()

    # First, run the essential parts of input handler (first 40 bytes includes the store)
    # The input handler stores to FF93 at offset 38-39
    # We copy bytes 0-40 (41 bytes) which includes the store, but cuts off:
    #   47 = LD B, A
    #   3E 30 = LD A, 0x30
    #   E0 00 = LDH (FF00), A (deselect joypad)
    #   78 = LD A, B
    #   C9 = RET
    #
    # We need at least up to the E0 93 store. Let's calculate:
    # - Offset 38-39: E0 93 (store)
    # - Offset 40-44: Final cleanup code
    # - Offset 45: C9 (RET)
    #
    # We have 46 bytes. If we put colorization at the end:
    # - 40 bytes input handler (up through store)
    # - 6 bytes for: bank switch, call, bank switch, return
    #   That's: 3E 0D EA 00 20 CD xx xx 3E 01 EA 00 20 C9 = 14 bytes
    #   TOO MUCH!
    #
    # Alternative: Skip the joypad deselect (it's just cleanup, won't break things)
    # - 40 bytes input (bytes 0-39, includes store at 38-39)
    # - Leave room for our hook
    #
    # Actually, let's be more surgical. The minimum input handler needs:
    # - Button read (bytes 0-11)
    # - Direction read (bytes 12-37)
    # - Store to FF93 (bytes 38-39)
    # Total: 40 bytes minimum
    #
    # With 46 bytes total and 13 for our hook, we have 33 bytes.
    # That's NOT enough for the 40-byte minimum!
    #
    # SOLUTION: Put our code BEFORE and cut less-critical parts of input handler.
    # The input handler has redundant joypad reads for debouncing. We can cut some.

    # Simplified input handler (read both button types, store to FF93):
    simplified_input = bytearray([
        0x3E, 0x20,       # LD A, 0x20 (buttons)
        0xE0, 0x00,       # LDH (FF00), A
        0xF0, 0x00,       # LDH A, (FF00)
        0x2F,             # CPL
        0xE6, 0x0F,       # AND 0x0F
        0xCB, 0x37,       # SWAP A
        0x47,             # LD B, A
        0x3E, 0x10,       # LD A, 0x10 (d-pad)
        0xE0, 0x00,       # LDH (FF00), A
        0xF0, 0x00,       # LDH A, (FF00)
        0xF0, 0x00,       # LDH A, (FF00)
        0x2F,             # CPL
        0xE6, 0x0F,       # AND 0x0F
        0xB0,             # OR B
        0xE0, 0x93,       # LDH (FF93), A  <- Critical store!
        0x3E, 0x30,       # LD A, 0x30 (deselect)
        0xE0, 0x00,       # LDH (FF00), A
    ])  # 32 bytes

    # Our hook code
    hook_code = bytearray([
        0x3E, 0x0D,       # LD A, 0x0D (bank 13)
        0xEA, 0x00, 0x20, # LD (0x2000), A
        0xCD, COMBINED_FUNC & 0xFF, COMBINED_FUNC >> 8,  # CALL combined
        0x3E, 0x01,       # LD A, 0x01 (bank 1)
        0xEA, 0x00, 0x20, # LD (0x2000), A
        0xC9,             # RET
    ])  # 14 bytes

    # Total: 32 + 14 = 46 bytes. Perfect!
    vblank_hook = simplified_input + hook_code

    rom[0x0824:0x0824+len(vblank_hook)] = vblank_hook
    print(f"VBlank hook: {len(vblank_hook)} bytes at 0x0824 (simplified input + colorizer)")

    # Write ROM
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    print(f"\nWrote: {output_rom}")

    # Also write as FIXED.gb
    fixed_rom.write_bytes(rom)
    print(f"Wrote: {fixed_rom}")

    print("\n=== v1.03 Build Complete ===")


if __name__ == "__main__":
    main()
