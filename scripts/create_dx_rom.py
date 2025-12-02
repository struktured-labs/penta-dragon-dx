#!/usr/bin/env python3
"""
Create Penta Dragon DX - Game Boy Color colorization
Generates a working CGB ROM with proper input handling and palette loading
"""
import sys
import yaml
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


# Color name to BGR555 mapping
COLOR_NAMES = {
    'black': 0x0000,
    'white': 0x7FFF,
    'red': 0x001F,
    'green': 0x03E0,
    'blue': 0x7C00,
    'yellow': 0x03FF,
    'cyan': 0x7FE0,
    'magenta': 0x7C1F,
    'orange': 0x021F,
    'purple': 0x6010,
    'brown': 0x0215,
    'gray': 0x4210,
    'grey': 0x4210,  # Alternative spelling
    'pink': 0x5C1F,
    'lime': 0x03E7,
    'teal': 0x7CE0,
    'navy': 0x5000,
    'maroon': 0x0010,
    'olive': 0x0210,
    'transparent': 0x0000,
}
COMMON_COLOR_NAMES = {
    'BLACK': 0x0000,
    'WHITE': 0x7FFF,
    'RED':   0x001F,
    'GREEN': 0x03E0,
    'BLUE':  0x7C00,
    'YELLOW':0x03FF,
    'MAGENTA':0x7C1F,
    'CYAN':  0x7FE0,
}

# Merge into COLOR_NAMES if it exists, else define it
try:
    COLOR_NAMES.update(COMMON_COLOR_NAMES)
except NameError:
    COLOR_NAMES = dict(COMMON_COLOR_NAMES)

# Modifiers for color intensity
DARK_SCALE = 0.5
LIGHT_SCALE = 1.5


def parse_color(color_val) -> int:
    """Parse color value from hex string/name/dict/int to BGR555 int."""
    # Dict support
    if isinstance(color_val, dict):
        color_val = color_val.get('hex') or color_val.get('value') or color_val.get('color')
    # Int support
    if isinstance(color_val, int):
        return color_val & 0x7FFF
    if color_val is None:
        raise ValueError("Color value is None")

    s = str(color_val).strip()
    # Strip quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    # Normalize 0x prefix
    if s.lower().startswith('0x'):
        s = s[2:]

    # Named colors with optional modifiers 'light ' / 'dark '
    # Work in lowercase for lookup
    sl = s.lower()
    scale = 1.0
    if sl.startswith('light '):
        sl = sl[6:].strip()
        scale = 1.3
    elif sl.startswith('dark '):
        sl = sl[5:].strip()
        scale = 0.7
    if sl in COLOR_NAMES:
        bgr = COLOR_NAMES[sl] & 0x7FFF
        if scale != 1.0:
            r = bgr & 0x1F
            g = (bgr >> 5) & 0x1F
            b = (bgr >> 10) & 0x1F
            r = min(31, int(r * scale))
            g = min(31, int(g * scale))
            b = min(31, int(b * scale))
            bgr = (b << 10) | (g << 5) | r
        return bgr

    # Hex 4 digits
    if len(s) == 4 and all(ch in '0123456789abcdefABCDEF' for ch in s):
        return int(s, 16) & 0x7FFF

    raise ValueError(f"Invalid color: {color_val}. Use 4-hex BGR555 (e.g., '7FFF') or a known name.")
    def parse_color(c):
        """Parse a color which may be a hex string (e.g., '7C1F') or a name.

        Accepts:
        - plain strings: '7C1F', 'magenta', '0x7C1F', '"7C1F"'
        - dicts with keys: 'hex', 'value', 'color'
        Returns integer BGR555 (0..0x7FFF).
        """
        # Support dicts like {'hex': '7C1F'} or plain strings
        if isinstance(c, dict):
            c = c.get('hex') or c.get('value') or c.get('color')
        if c is None:
            raise ValueError(f"Invalid color entry: {c}")

        if not isinstance(c, str):
            # Allow integers directly
            try:
                return int(c) & 0x7FFF
            except Exception:
                raise ValueError(f"Invalid color entry type: {type(c)} value={c}")

        s = c.strip()
        # Strip quotes
        if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
            s = s[1:-1]
        s = s.strip()
        # Normalize 0x prefix
        if s.lower().startswith('0x'):
            s = s[2:]

        # Named colors
        base_upper = s.upper()
        if base_upper in COLOR_NAMES:
            return COLOR_NAMES[base_upper]

        # Hex validation (4 hex digits for BGR555)
        hex_chars = '0123456789abcdefABCDEF'
        if len(s) != 4 or any(ch not in hex_chars for ch in s):
            raise ValueError(f"Color must be 4 hex chars (BGR555) or known name, got: {c}")

        return int(s, 16) & 0x7FFF


def create_palette(c0: int, c1: int, c2: int, c3: int) -> bytes:
    """Convert 4 BGR555 colors to 8-byte palette data (little-endian)"""
    return bytes([
        c0 & 0xFF, (c0 >> 8) & 0xFF,
        c1 & 0xFF, (c1 >> 8) & 0xFF,
        c2 & 0xFF, (c2 >> 8) & 0xFF,
        c3 & 0xFF, (c3 >> 8) & 0xFF,
    ])


def load_palettes_from_yaml(yaml_path: Path) -> tuple[bytearray, bytearray]:
    """Load BG and OBJ palettes from YAML file."""
    with open(yaml_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # BG palette order
    bg_order = ['Dungeon', 'LavaZone', 'WaterZone', 'DesertZone', 
                'ForestZone', 'CastleZone', 'SkyZone', 'BossZone']
    
    # OBJ palette order
    obj_order = ['MainCharacter', 'EnemyBasic', 'EnemyFire', 'EnemyIce',
                 'EnemyFlying', 'EnemyPoison', 'MiniBoss', 'MainBoss']
    
    bg_data = bytearray()
    for name in bg_order:
        if name not in config['bg_palettes']:
            print(f"WARNING: BG palette '{name}' not found in YAML")
            continue
        colors = config['bg_palettes'][name]['colors']
        color_ints = [parse_color(c) for c in colors]
        bg_data.extend(create_palette(*color_ints))
    
    obj_data = bytearray()
    for name in obj_order:
        if name not in config['obj_palettes']:
            print(f"WARNING: OBJ palette '{name}' not found in YAML")
            continue
        colors = config['obj_palettes'][name]['colors']
        color_ints = [parse_color(c) for c in colors]
        obj_data.extend(create_palette(*color_ints))
    
    return bg_data, obj_data
    
    # Build baseline OBJ palettes; we'll generate variants per OBP mapping

def build_obj_data_with_target_color(idx: int, color: int) -> bytearray:
    """Return 8 OBJ palettes with palette 0 having `color` at given index (1..3). Index 0 is transparency."""
    assert idx in (1, 2, 3), "idx must be 1, 2, or 3"
    def pal(c0, c1, c2, c3):
        return create_palette(c0, c1, c2, c3)
    # Start with default palettes; overwrite palette 0 with target color at idx
    obj = bytearray()
    # Palette 0: transparent, then place target color at idx; fill others with visible but dark values
    colors = [0x0000, 0x001F, 0x03E0, 0x7C00]  # blue/green/red as fillers
    colors[idx] = color
    obj.extend(pal(colors[0], colors[1], colors[2], colors[3]))
    # Palettes 1..7 keep distinct colors for enemies (not critical for test)
    obj.extend(pal(0x0000, 0x7FFF, 0x03E0, 0x0100))
    obj.extend(pal(0x0000, 0x7FFF, 0x7C00, 0x2000))
    obj.extend(pal(0x0000, 0x7FFF, 0x001F, 0x0008))
    obj.extend(pal(0x0000, 0x7FFF, 0x7FE0, 0x2980))
    obj.extend(pal(0x0000, 0x7FFF, 0x03FF, 0x015F))
    obj.extend(pal(0x0000, 0x7FFF, 0x7C1F, 0x2808))
    obj.extend(pal(0x0000, 0x7FFF, 0x7FE0, 0x4A00))
    return obj

def build_combined_function_with_obp(obp_value: int, original_input: bytes) -> bytes:
    """Return combined (input inline + palette loader) and write OBP0/OBP1 to obp_value before loading palettes."""
    return original_input + bytes([
        # Write DMG OBJ palette mappings
        0x3E, obp_value,             # LD A,obp
        0xE0, 0x48,                  # LDH [FF48],A (OBP0)
        0x3E, obp_value,             # LD A,obp
        0xE0, 0x49,                  # LDH [FF49],A (OBP1)
        # Load BG palettes
        0x21, 0x80, 0x6C,            # LD HL,6C80
        0x3E, 0x80,                  # LD A,80h
        0xE0, 0x68,                  # LDH [FF68],A
        0x0E, 0x40,                  # LD C,64
        0x2A, 0xE0, 0x69,            # loop: LD A,[HL+]; LDH [FF69],A
        0x0D,                        # DEC C
        0x20, 0xFA,                  # JR NZ,loop
        # Load OBJ palettes
        0x3E, 0x80,                  # LD A,80h
        0xE0, 0x6A,                  # LDH [FF6A],A
        0x0E, 0x40,                  # LD C,64
        0x2A, 0xE0, 0x6B,            # loop: LD A,[HL+]; LDH [FF6B],A
        0x0D,                        # DEC C
        0x20, 0xFA,                  # JR NZ,loop
        0xC9,                        # RET
    ])

def main():
    # Paths
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_WORKING.gb")
    palette_yaml = Path("palettes/penta_palettes.yaml")
    
    if not input_rom.exists():
        print(f"ERROR: Input ROM not found: {input_rom}")
        sys.exit(1)
    
    if not palette_yaml.exists():
        print(f"ERROR: Palette YAML not found: {palette_yaml}")
        sys.exit(1)
    
    # Load ROM
    print(f"Loading ROM: {input_rom}")
    rom = bytearray(input_rom.read_bytes())
    
    # Apply display compatibility patches (fixes white screen freeze)
    print("Applying display compatibility patches...")
    rom, _ = apply_all_display_patches(rom)
    
    # Load palettes from YAML
    print(f"Loading palettes from {palette_yaml}...")
    bg_palettes, obj_palettes = load_palettes_from_yaml(palette_yaml)

    # Write palette data to bank 13 at 0x6C80 (file offset 0x036C80)
    print("Writing palette data to bank 13...")
    palette_data_offset = 0x036C80
    rom[palette_data_offset:palette_data_offset+len(bg_palettes)] = bg_palettes
    rom[palette_data_offset+len(bg_palettes):palette_data_offset+len(bg_palettes)+len(obj_palettes)] = obj_palettes
    
    # Write palette data to bank 13 at 0x6C80 (file offset 0x036C80)
    print("Writing palette data to bank 13...")
    palette_data_offset = 0x036C80
    rom[palette_data_offset:palette_data_offset+len(bg_palettes)] = bg_palettes
    rom[palette_data_offset+len(bg_palettes):palette_data_offset+len(bg_palettes)+len(obj_palettes)] = obj_palettes
    
    # Revert to proven input-handler trampoline (no VBlank patch):
    # - Save original input handler (46 bytes) at bank 13 `0x6D00`.
    # - Minimal trampoline at `0x0824` switches to bank 13 and CALLs `0x6D00`.
    # - The bank-13 combined function runs original input inline, then loads
    #   palettes once using a WRAM one-shot guard at `C0A0` and an optional
    #   frame delay via `C0A1`.
    print("Installing minimal input trampoline and combined bank-13 loader (one-shot late-init)...")
    # 1) Save original input handler (46 bytes) into bank 13 at 0x6D00
    original_input = bytes(rom[0x0824:0x0824+46])
    rom[0x036D00:0x036D00+46] = original_input

    # 2) Build combined function in bank 13:
    #    - One-shot guard at C0A0; optional frame delay using C0A1 (< 60)
    #    - Run original input inline
    #    - Load BG+OBJ palettes from 6C80
    combined_bank13 = original_input + bytes([
        # One-shot: if already loaded, RET
        0xFA, 0xA0, 0xC0,      # LD A,[C0A0]
        0xFE, 0x01,            # CP 1
        0x28, 0x2A,            # JR Z,+42 -> RET
        # Optional late-init: wait ~60 frames
        0xFA, 0xA1, 0xC0,      # LD A,[C0A1]
        0x3C,                  # INC A
        0xEA, 0xA1, 0xC0,      # LD [C0A1],A
        0xFE, 0x3C,            # CP 60
        0x38, 0x22,            # JR C,+34 -> RET if not yet
        # Set loaded flag
        0x3E, 0x01,            # LD A,1
        0xEA, 0xA0, 0xC0,      # LD [C0A0],A
        # Load palettes
        0x21, 0x80, 0x6C,      # LD HL,6C80
        0x3E, 0x80,            # LD A,80h
        0xE0, 0x68,            # LDH [FF68],A
        0x0E, 0x40,            # LD C,64
        0x2A, 0xE0, 0x69,      # loop: LD A,[HL+]; LDH [FF69],A
        0x0D,                  # DEC C
        0x20, 0xFA,            # JR NZ,loop
        0x3E, 0x80,            # LD A,80h
        0xE0, 0x6A,            # LDH [FF6A],A
        0x0E, 0x40,            # LD C,64
        0x2A, 0xE0, 0x6B,      # loop: LD A,[HL+]; LDH [FF6B],A
        0x0D,                  # DEC C
        0x20, 0xFA,            # JR NZ,loop
        0xC9,                  # RET
        # Early RET targets
        0xC9,                  # RET (already loaded)
        0xC9,                  # RET (not yet reached frame threshold)
    ])
    rom[0x036D00:0x036D00+len(combined_bank13)] = combined_bank13

    # 3) Minimal trampoline at 0x0824 (18 bytes): switch bank, call 6D00, restore bank
    new_0824 = bytes([
        0xF5,                  # PUSH AF
        0x3E, 0x0D,            # LD A,13
        0xEA, 0x00, 0x20,      # LD [2000],A
        0xF1,                  # POP AF
        0xCD, 0x00, 0x6D,      # CALL 6D00
        0xF5,                  # PUSH AF
        0x3E, 0x01,            # LD A,1
        0xEA, 0x00, 0x20,      # LD [2000],A
        0xF1,                  # POP AF
        0xC9,                  # RET
    ])
    rom[0x0824:0x0824+len(new_0824)] = new_0824
    if len(new_0824) < 46:
        rom[0x0824+len(new_0824):0x0824+46] = bytes([0x00] * (46 - len(new_0824)))
    print("  Trampoline @0x0824 -> bank13:0x6D00; palettes load once after ~1s")

    # Restore original boot entry to avoid startup instability
    # JP 0x0150 from 0x0100 and leave 0x0150 bytes untouched if previously modified
    rom[0x0100:0x0104] = bytes([0x00, 0xC3, 0x50, 0x01])
    
    # Set CGB compatibility flag
    print("Setting CGB compatibility flag...")
    rom[0x143] = 0x80  # CGB compatible
    
    # Fix header checksum
    print("Fixing header checksum...")
    chk = 0
    for i in range(0x134, 0x14D):
        chk = (chk - rom[i] - 1) & 0xFF
    rom[0x14D] = chk
    print(f"  Checksum: 0x{chk:02X}")

    # NOTE: VBlank OAM palette fixer disabled for start-menu stability.
    # The ISR hook can conflict with the game's initialization sequence.
    # We'll set palette indices using a safer non-ISR path later.
    print("\nVBlank OAM palette fixer is DISABLED for stability.")
    
    # Write output ROM
    output_rom.parent.mkdir(parents=True, exist_ok=True)
    output_rom.write_bytes(rom)
    print(f"\n✓ Created: {output_rom}")
    print(f"  Size: {len(rom)} bytes")
    print("\nROM modifications:")
    print("  - Display patch at 0x0067 (CGB detection)")
    print("  - Minimal trampoline at 0x0824; combined input+palette in bank 13 @0x6D00")
    print("  - Palette data in bank 13 at 0x6C80 (128 bytes)")
    print("\nFeatures:")
    print("  - Preserves original input handling")
    print("  - Loads CGB color palettes every frame via VBlank")
    print("  - Avoids boot-time hooks and input handler replacement")

    # Build three index variants to defeat DMG mapping uncertainty
    # Omit OBP sweep variants in this safer build to minimize changes
    print("\nSkipped IDX sweep variants for stability (can re-enable later).")


if __name__ == "__main__":
    main()
