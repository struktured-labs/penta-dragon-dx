#!/usr/bin/env python3
"""
v2.30: Simplified Projectile Colorization (fixes v2.29 issues)

FIXES in v2.30:
- Removed projectile sub-range detection (was causing direction-dependent colors)
- All projectiles (0x00-0x0F) now use Palette 0 (dynamic)
- Fixed C register usage conflict in palette loader
- Verified BG colorizer unchanged

APPROACH:
- ALL projectiles get dynamic Palette 0 (pink for Sara W, green for Sara D)
- No distinction between Sara and enemy projectiles yet
- This provides form-based coloring without direction dependency

INHERITED from v2.28:
- Stage detection via 0xFFD0 (0x00=Level 1, 0x01=Bonus stage)
- Jet form OBJ palettes for Sara W and Sara D in bonus stage
- Boss detection via 0xFFBF (1=Gargoyle, 2=Spider)
- BG item colorization (gold palette)
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytes, bytes, bytes, bytes, bytes, bytes]:
    """Load BG, OBJ, boss, and jet form palettes from YAML file."""
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

    obj_keys = ['SaraProjectileWitch', 'SaraDragon', 'SaraWitch', 'Crow',
                'Hornets', 'OrcGround', 'Humanoid', 'Catfish']
    obj_data = bytearray()
    for key in obj_keys:
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            # Fallback defaults
            if key == 'SaraProjectileWitch':
                obj_data.extend(pal_to_bytes(["0000", "7C1F", "5817", "3010"]))  # Pink
            else:
                obj_data.extend(pal_to_bytes(["0000", "7FFF", "5294", "2108"]))

    boss_data = data.get('boss_palettes', {})
    gargoyle = pal_to_bytes(boss_data.get('Gargoyle', {}).get('colors', ["0000", "601F", "400F", "0000"]))
    spider = pal_to_bytes(boss_data.get('Spider', {}).get('colors', ["0000", "001F", "00BF", "0000"]))

    # Load jet form palettes
    jet_data = data.get('obj_palettes', {})
    sara_witch_jet = pal_to_bytes(jet_data.get('SaraWitchJet', {}).get('colors', ["0000", "7C1F", "5817", "3010"]))
    sara_dragon_jet = pal_to_bytes(jet_data.get('SaraDragonJet', {}).get('colors', ["0000", "7FE0", "4EC0", "2D80"]))

    return bytes(bg_data), bytes(obj_data), gargoyle, spider, sara_witch_jet, sara_dragon_jet


def create_tile_based_colorizer() -> bytes:
    """
    Tile-based colorizer with SIMPLIFIED projectile detection (v2.30).

    CHANGE from v2.29: All projectiles (0x00-0x0F) use Palette 0 (no sub-range).
    This fixes direction-dependent color issues.
    """
    code = bytearray()
    labels = {}
    jumps_to_fix = []

    code.extend([0x06, 0x28])  # LD B, 40
    labels['loop_start'] = len(code)

    # Check if Sara slot (0-3)
    code.extend([0x3E, 0x28, 0x90, 0xFE, 0x04])
    jumps_to_fix.append((len(code), 'sara_palette'))
    code.extend([0x38, 0x00])

    # Read tile
    code.extend([0x2B, 0x7E, 0x23, 0x4F])

    # SIMPLIFIED: All projectiles (< 0x10) use Palette 0 (dynamic)
    code.extend([0xFE, 0x10])
    jumps_to_fix.append((len(code), 'projectile_palette'))
    code.extend([0x38, 0x00])

    # Check boss mode
    code.extend([0x7B, 0xB7])
    jumps_to_fix.append((len(code), 'boss_palette'))
    code.extend([0x20, 0x00])

    # Tile-based coloring (unchanged from v2.28)
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
    code.extend([0x79, 0xFE, 0x40])
    jumps_to_fix.append((len(code), 'hornet_palette'))
    code.extend([0x30, 0x00])
    code.extend([0xFE, 0x30])
    jumps_to_fix.append((len(code), 'crow_palette'))
    code.extend([0x30, 0x00])
    code.extend([0x3E, 0x04])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['sara_palette'] = len(code)
    code.extend([0x7A])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    # SIMPLIFIED: All projectiles use Palette 0 (dynamic)
    labels['projectile_palette'] = len(code)
    code.extend([0x3E, 0x00])   # LD A, 0 (Palette 0 - dynamically loaded)
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['crow_palette'] = len(code)
    code.extend([0x3E, 0x03])
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

    labels['boss_palette'] = len(code)
    code.extend([0x7B])
    jumps_to_fix.append((len(code), 'apply_palette'))
    code.extend([0x18, 0x00])

    labels['miniboss_palette'] = len(code)
    code.extend([0x3E, 0x07])

    labels['apply_palette'] = len(code)
    code.extend([0x4F, 0x7E, 0xE6, 0xF8, 0xB1, 0x77])
    code.extend([0x23, 0x23, 0x23, 0x23, 0x05])
    loop_offset = labels['loop_start'] - len(code) - 2
    code.extend([0x20, loop_offset & 0xFF])
    code.append(0xC9)

    for jr_pos, target_label in jumps_to_fix:
        target = labels[target_label]
        offset = target - (jr_pos + 2)
        code[jr_pos + 1] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int) -> bytes:
    """Shadow colorizer (unchanged from v2.28)."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    code.extend([0xF0, 0xBE, 0xB7, 0x20, 0x04])
    code.extend([0x16, 0x02, 0x18, 0x02])
    code.extend([0x16, 0x01])

    code.extend([0xF0, 0xBF, 0xFE, 0x01, 0x28, 0x08])
    code.extend([0xFE, 0x02, 0x28, 0x08])
    code.extend([0x1E, 0x00, 0x18, 0x06])
    code.extend([0x1E, 0x06, 0x18, 0x02])
    code.extend([0x1E, 0x07])

    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1, 0xC9])
    return bytes(code)


def create_palette_loader(
    palette_data_addr: int,
    gargoyle_addr: int,
    spider_addr: int,
    sara_witch_jet_addr: int,
    sara_dragon_jet_addr: int,
    sara_projectile_dragon_addr: int
) -> bytes:
    """
    Load CGB palettes with stage, boss, and Sara form detection (v2.30).

    Dynamic Palette 0 loading based on Sara form:
    - Sara W (0xFFBE=0): Pink projectile colors
    - Sara D (0xFFBE≠0): Green projectile colors

    FIXED: Avoid C register conflict by using temporary location
    """
    code = bytearray()

    # Read Sara form flag FIRST (before stage and boss flags)
    code.extend([0xF0, 0xBE])        # LDH A, [0xFFBE]
    code.extend([0xF5])              # PUSH AF (save Sara form on stack)

    # Check stage flag and save in D register
    code.extend([0xF0, 0xD0])        # LDH A, [0xFFD0]
    code.append(0x57)                # LD D, A

    # Check boss flag and save in E register
    code.extend([0xF0, 0xBF])        # LDH A, [0xFFBF]
    code.append(0x5F)                # LD E, A

    # Load BG palettes (64 bytes)
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40])
    code.extend([0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA])  # bg_loop

    # Load OBJ palette 0 (Sara projectiles - dynamic based on form)
    obj_data_addr = palette_data_addr + 64
    code.extend([0x3E, 0x80, 0xE0, 0x6A])  # Set OCPS to palette 0
    # Retrieve Sara form from stack
    code.extend([0xF1])              # POP AF (restore Sara form)
    code.extend([0xB7])              # OR A (check if Sara W = 0)
    # If Sara W (A=0), load SaraProjectileWitch palette
    # If Sara D (A≠0), load SaraProjectileDragon palette
    code.extend([0x20, 0x03])        # JR NZ, +3 (skip to Sara D)
    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])  # Sara W projectile
    code.extend([0x18, 0x02])        # JR +2 (skip Sara D load)
    code.extend([0x21, sara_projectile_dragon_addr & 0xFF, (sara_projectile_dragon_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])  # pal0_loop

    # Load OBJ palette 1 (Sara Dragon - check stage)
    code.extend([0x3E, 0x88, 0xE0, 0x6A])  # Set OCPS to palette 1
    sara_dragon_addr = obj_data_addr + 8
    code.extend([0x21, sara_dragon_addr & 0xFF, (sara_dragon_addr >> 8) & 0xFF])
    code.extend([0x7A, 0xFE, 0x01, 0x20, 0x03])  # LD A, D; CP 1; JR NZ, +3
    code.extend([0x21, sara_dragon_jet_addr & 0xFF, (sara_dragon_jet_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])  # pal1_loop

    # Load OBJ palette 2 (Sara Witch - check stage)
    code.extend([0x3E, 0x90, 0xE0, 0x6A])  # Set OCPS to palette 2
    sara_witch_addr = obj_data_addr + 16
    code.extend([0x21, sara_witch_addr & 0xFF, (sara_witch_addr >> 8) & 0xFF])
    code.extend([0x7A, 0xFE, 0x01, 0x20, 0x03])  # LD A, D; CP 1; JR NZ, +3
    code.extend([0x21, sara_witch_jet_addr & 0xFF, (sara_witch_jet_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])  # pal2_loop

    # Load OBJ palettes 3-5 (Crow, Hornets, Orc)
    code.extend([0x3E, 0x98, 0xE0, 0x6A])  # Set OCPS to palette 3
    crow_addr = obj_data_addr + 24
    code.extend([0x21, crow_addr & 0xFF, (crow_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x18])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])  # pal35_loop

    # Load OBJ palette 6 (Humanoid or Gargoyle)
    code.extend([0x3E, 0xB0, 0xE0, 0x6A])  # Set OCPS to palette 6
    humanoid_addr = obj_data_addr + 48
    code.extend([0x21, humanoid_addr & 0xFF, (humanoid_addr >> 8) & 0xFF])
    code.extend([0x7B, 0xFE, 0x01, 0x20, 0x03])  # LD A, E; CP 1; JR NZ, +3
    code.extend([0x21, gargoyle_addr & 0xFF, (gargoyle_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])  # pal6_loop

    # Load OBJ palette 7 (Catfish or Spider)
    code.extend([0x3E, 0xB8, 0xE0, 0x6A])  # Set OCPS to palette 7
    catfish_addr = obj_data_addr + 56
    code.extend([0x21, catfish_addr & 0xFF, (catfish_addr >> 8) & 0xFF])
    code.extend([0x7B, 0xFE, 0x02, 0x20, 0x03])  # LD A, E; CP 2; JR NZ, +3
    code.extend([0x21, spider_addr & 0xFF, (spider_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])  # pal7_loop

    code.append(0xC9)
    return bytes(code)


def create_tile_palette_lookup() -> bytes:
    """256-byte lookup table: tile_id -> BG palette (unchanged from v2.28)."""
    lookup = bytearray(256)
    for i in range(256):
        if i < 0x20:
            lookup[i] = 0
        elif i < 0x80:
            lookup[i] = 2
        elif i < 0xE0:
            lookup[i] = 1
        elif i == 0xFF:
            lookup[i] = 0
        else:
            lookup[i] = 2
    return bytes(lookup)


def create_bg_colorizer_oneshot(lookup_table_addr: int) -> bytes:
    """One-shot BG colorizer (unchanged from v2.28)."""
    code = bytearray()
    code.extend([0xF0, 0xE0, 0xFE, 0x12, 0xD0])
    code.extend([0xC5, 0xD5, 0x6F, 0x26, 0x00])
    code.extend([0x29, 0x29, 0x29, 0x29, 0x29])
    code.extend([0x01, 0x00, 0x98, 0x09, 0x06, 0x20])

    tile_loop_start = len(code)
    code.extend([0xAF, 0xE0, 0x4F, 0x56])
    code.extend([0xE5, 0x26, (lookup_table_addr >> 8) & 0xFF])
    code.extend([0x7A, 0x6F, 0x5E, 0xE1])
    code.extend([0x3E, 0x01, 0xE0, 0x4F, 0x73])
    code.extend([0x23, 0x05])
    tile_offset = tile_loop_start - len(code) - 2
    code.extend([0x20, tile_offset & 0xFF])

    code.extend([0xD1, 0xC1])
    code.extend([0xF0, 0xE0, 0xC6, 0x01, 0xE0, 0xE0])
    code.extend([0xAF, 0xE0, 0x4F, 0xC9])
    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int, bg_colorizer_addr: int) -> bytes:
    """Combined function (unchanged from v2.28)."""
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF, 0xC9])
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook (unchanged from v2.28)."""
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
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    print("=== Penta Dragon DX v2.30 ===")
    print("Simplified projectile colorization (fixes v2.29 issues)")

    with open(input_rom, "rb") as f:
        rom = bytearray(f.read())

    apply_all_display_patches(rom)

    bg_data, obj_data, gargoyle, spider, sara_witch_jet, sara_dragon_jet = load_palettes_from_yaml(palette_yaml)

    # Extract Sara Dragon projectile palette (8 bytes from obj_data offset 8)
    sara_projectile_dragon = obj_data[8:16]

    # Bank 13 layout - NO OVERLAPS
    palette_data_addr = 0x6800
    gargoyle_addr = 0x6880
    spider_addr = 0x6888
    sara_witch_jet_addr = 0x6890
    sara_dragon_jet_addr = 0x6898
    sara_projectile_dragon_addr = 0x68A0
    palette_loader_addr = 0x6900  # ~158 bytes
    shadow_main_addr = 0x69B0     # 52 bytes
    colorizer_addr = 0x69F0       # 98 bytes (back to v2.28 size)
    lookup_table_addr = 0x6B00    # 256 bytes
    bg_colorizer_addr = 0x6C00    # 53 bytes
    combined_addr = 0x6D00        # 13 bytes

    palette_loader = create_palette_loader(
        palette_data_addr, gargoyle_addr, spider_addr,
        sara_witch_jet_addr, sara_dragon_jet_addr,
        sara_projectile_dragon_addr
    )
    shadow_main = create_shadow_colorizer_main(colorizer_addr)
    colorizer = create_tile_based_colorizer()
    lookup_table = create_tile_palette_lookup()
    bg_colorizer = create_bg_colorizer_oneshot(lookup_table_addr)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr, bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X}")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X}")
    print(f"Colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X}")
    print(f"BG colorizer: {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X}")

    bank13_offset = 13 * 0x4000

    rom[bank13_offset + (palette_data_addr - 0x4000):bank13_offset + (palette_data_addr - 0x4000) + len(bg_data)] = bg_data
    rom[bank13_offset + (palette_data_addr - 0x4000) + 64:bank13_offset + (palette_data_addr - 0x4000) + 64 + len(obj_data)] = obj_data
    rom[bank13_offset + (gargoyle_addr - 0x4000):bank13_offset + (gargoyle_addr - 0x4000) + len(gargoyle)] = gargoyle
    rom[bank13_offset + (spider_addr - 0x4000):bank13_offset + (spider_addr - 0x4000) + len(spider)] = spider
    rom[bank13_offset + (sara_witch_jet_addr - 0x4000):bank13_offset + (sara_witch_jet_addr - 0x4000) + len(sara_witch_jet)] = sara_witch_jet
    rom[bank13_offset + (sara_dragon_jet_addr - 0x4000):bank13_offset + (sara_dragon_jet_addr - 0x4000) + len(sara_dragon_jet)] = sara_dragon_jet
    rom[bank13_offset + (sara_projectile_dragon_addr - 0x4000):bank13_offset + (sara_projectile_dragon_addr - 0x4000) + len(sara_projectile_dragon)] = sara_projectile_dragon
    rom[bank13_offset + (palette_loader_addr - 0x4000):bank13_offset + (palette_loader_addr - 0x4000) + len(palette_loader)] = palette_loader
    rom[bank13_offset + (shadow_main_addr - 0x4000):bank13_offset + (shadow_main_addr - 0x4000) + len(shadow_main)] = shadow_main
    rom[bank13_offset + (colorizer_addr - 0x4000):bank13_offset + (colorizer_addr - 0x4000) + len(colorizer)] = colorizer
    rom[bank13_offset + (lookup_table_addr - 0x4000):bank13_offset + (lookup_table_addr - 0x4000) + len(lookup_table)] = lookup_table
    rom[bank13_offset + (bg_colorizer_addr - 0x4000):bank13_offset + (bg_colorizer_addr - 0x4000) + len(bg_colorizer)] = bg_colorizer
    rom[bank13_offset + (combined_addr - 0x4000):bank13_offset + (combined_addr - 0x4000) + len(combined)] = combined

    rom[0x06D5:0x06D5 + 3] = bytearray([0x00, 0x00, 0x00])
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    # Set CGB flag
    rom[0x143] = 0x80
    print("Set CGB flag at 0x143")

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    with open(output_rom, "wb") as f:
        f.write(rom)

    print(f"\n✓ ROM patched successfully")
    print(f"  Output: {output_rom}")
    print(f"\nProjectile colorization (simplified):")
    print(f"  - ALL projectiles (0x00-0x0F): Palette 0 (dynamic)")
    print(f"  - Palette 0 changes based on Sara form (0xFFBE)")
    print(f"  - Sara W: Pink projectiles")
    print(f"  - Sara D: Green projectiles")
    print(f"  - Enemy projectiles: Also colored (same as Sara's form)")
    print(f"\nFIXES:")
    print(f"  - No more direction-dependent colors")
    print(f"  - Fixed register usage conflict")
    print(f"  - BG colorizer unchanged")


if __name__ == "__main__":
    main()
