#!/usr/bin/env python3
"""
v2.38: Active-Tilemap-Only BG Colorizer

FIXES over v2.37:
1. SINGLE TILEMAP: Only writes attributes to the ACTIVE tilemap (LCDC bit 3).
   Cuts per-tile cost from ~48M (both tilemaps) to ~20M (one tilemap).
2. ~140 TILES PER VBLANK: 3x throughput vs v2.37's 48 tiles.
   Full 1024-tile sweep completes in ~7.3 frames (vs ~21 in v2.37).
3. FLIP DETECTION: When LCDC bit 3 changes (game swaps active tilemap),
   reset sweep counter to 0. New tilemap gets fully colored in ~7 frames.
4. SCROLL-EDGE COLUMN: Still prioritizes the newly-visible column (32 tiles)
   when SCX changes, but only on the active tilemap.

Key insight: The game swaps tilemaps every ~7 frames. v2.37 wrote to BOTH
tilemaps (48 tiles/frame), taking 21 frames for a full sweep - 3x too slow.
v2.38 writes only to the active tilemap, completing a sweep BEFORE the next swap.

HRAM usage:
  FFEA: sweep position counter (low byte = E offset)
  FFEB: sweep position counter (high, 0-3, relative to tilemap base)
  FFEC: saved LCDC bit 3 value (for flip detection)
  FFED: previous SCX/8 (for scroll-edge detection)

INHERITED from v2.37/v2.36:
- Input debounce (1 d-pad + 8 button reads via loop)
- Both-buffer shadow OBJ colorization (C000 + C100)
- Multi-boss palette system (8 bosses, table-based)
- Per-entity projectile detection
- Powerup-based Palette 0
- Stage detection via 0xFFD0
- ROM lookup table at 0x6B00 for tile→palette mapping
"""
import sys
import yaml
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from penta_dragon_dx.display_patcher import apply_all_display_patches


def load_palettes_from_yaml(yaml_path: Path) -> dict:
    """Load all palette data from YAML file. Returns dict of named byte arrays."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    def pal_to_bytes(colors: list[str]) -> bytes:
        result = bytearray()
        for c in colors:
            val = int(c, 16) & 0x7FFF
            result.extend([val & 0xFF, (val >> 8) & 0xFF])
        return bytes(result)

    # BG palettes (64 bytes total)
    bg_keys = ['Dungeon', 'BG1', 'BG2', 'BG3', 'BG4', 'BG5', 'BG6', 'BG7']
    bg_data = bytearray()
    for key in bg_keys:
        if key in data.get('bg_palettes', {}):
            bg_data.extend(pal_to_bytes(data['bg_palettes'][key]['colors']))
        else:
            bg_data.extend(pal_to_bytes(["7FFF", "5294", "2108", "0000"]))

    # OBJ palettes (64 bytes total)
    obj_key_map = {
        0: ('EnemyProjectile', ["0000", "7C1F", "5817", "3010"]),
        1: ('SaraDragon', ["0000", "03E0", "01C0", "0000"]),
        2: ('SaraWitch', ["0000", "2EBE", "511F", "0842"]),
        3: ('SaraProjectileAndCrow', ["0000", "001F", "0017", "000F"]),
        4: ('Hornets', ["0000", "03FF", "00DF", "0000"]),
        5: ('OrcGround', ["0000", "02A0", "0160", "0000"]),
        6: ('Humanoid', ["0000", "7C1F", "4C0F", "0000"]),
        7: ('Catfish', ["0000", "7FE0", "3CC0", "0000"]),
    }
    obj_data = bytearray()
    for i in range(8):
        key, fallback = obj_key_map[i]
        if key in data.get('obj_palettes', {}):
            obj_data.extend(pal_to_bytes(data['obj_palettes'][key]['colors']))
        else:
            obj_data.extend(pal_to_bytes(fallback))

    # Boss palette table (8 bosses x 8 bytes = 64 bytes)
    boss_keys = ['Gargoyle', 'Spider', 'Boss3_Crimson', 'Boss4_Ice',
                 'Boss5_Void', 'Boss6_Poison', 'Boss7_Knight', 'Angela']
    boss_data = data.get('boss_palettes', {})
    boss_palette_table = bytearray()
    boss_slot_table = bytearray()
    for key in boss_keys:
        entry = boss_data.get(key, {})
        colors = entry.get('colors', ["0000", "7FFF", "5294", "2108"])
        slot = entry.get('slot', 6)
        boss_palette_table.extend(pal_to_bytes(colors))
        boss_slot_table.append(slot)

    # Jet palettes
    jet_data = data.get('obj_palettes', {})
    sara_witch_jet = pal_to_bytes(jet_data.get('SaraWitchJet', {}).get('colors', ["0000", "7C1F", "5817", "3010"]))
    sara_dragon_jet = pal_to_bytes(jet_data.get('SaraDragonJet', {}).get('colors', ["0000", "7FE0", "4EC0", "2D80"]))

    # Powerup projectile palettes
    powerup_data = data.get('powerup_palettes', {})
    spiral_proj = pal_to_bytes(powerup_data.get('SpiralProjectile', {}).get('colors', ["0000", "7FE0", "5EC0", "3E80"]))
    shield_proj = pal_to_bytes(powerup_data.get('ShieldProjectile', {}).get('colors', ["0000", "03FF", "02BF", "019F"]))
    turbo_proj = pal_to_bytes(powerup_data.get('TurboProjectile', {}).get('colors', ["0000", "00FF", "00BF", "005F"]))

    return {
        'bg_data': bytes(bg_data),
        'obj_data': bytes(obj_data),
        'boss_palette_table': bytes(boss_palette_table),
        'boss_slot_table': bytes(boss_slot_table),
        'sara_witch_jet': sara_witch_jet,
        'sara_dragon_jet': sara_dragon_jet,
        'spiral_proj': spiral_proj,
        'shield_proj': shield_proj,
        'turbo_proj': turbo_proj,
    }


def create_tile_based_colorizer(colorizer_base_addr: int) -> bytes:
    """Tile-based OBJ colorizer with per-entity projectile detection. Unchanged from v2.33."""
    code = bytearray()
    labels = {}
    forward_jumps = []

    def emit(opcodes):
        code.extend(opcodes if isinstance(opcodes, (list, bytes, bytearray)) else [opcodes])

    def emit_jr(opcode, target_label):
        code.append(opcode)
        forward_jumps.append((len(code), target_label))
        code.append(0x00)

    emit([0x06, 0x28])  # LD B, 40
    labels['loop_start'] = len(code)

    emit([0x3E, 0x28, 0x90, 0xFE, 0x04])  # LD A, 40; SUB B; CP 4
    emit_jr(0x38, 'sara_palette')

    emit([0x2B, 0x7E, 0x23, 0x4F])  # DEC HL; LD A, [HL]; INC HL; LD C, A

    emit([0xFE, 0x10])
    emit_jr(0x30, 'check_higher_tiles')

    emit([0xFE, 0x0F])
    emit_jr(0x28, 'pal_sara_w_proj')
    emit([0xFE, 0x06])
    emit_jr(0x28, 'pal_sara_d_proj')
    emit([0xFE, 0x09])
    emit_jr(0x28, 'pal_sara_d_proj')
    emit([0xFE, 0x0A])
    emit_jr(0x28, 'pal_sara_d_proj')

    emit([0xFE, 0x02])
    emit_jr(0x38, 'pal_enemy_proj')

    emit([0x3E, 0x00])
    emit_jr(0x18, 'apply_palette')

    labels['check_higher_tiles'] = len(code)
    emit([0xFE, 0x20])
    emit_jr(0x30, 'check_sara_sprite')
    emit([0x3E, 0x04])
    emit_jr(0x18, 'apply_palette')

    labels['check_sara_sprite'] = len(code)
    emit([0xFE, 0x30])
    emit_jr(0x38, 'sara_palette')

    emit([0x7B, 0xB7])
    emit_jr(0x20, 'boss_palette')

    emit(0x79)
    emit([0xFE, 0x50])
    emit_jr(0x38, 'check_crow_hornet')
    emit([0xFE, 0x60])
    emit_jr(0x38, 'pal_orc')
    emit([0xFE, 0x70])
    emit_jr(0x38, 'pal_humanoid')
    emit([0xFE, 0x80])
    emit_jr(0x38, 'pal_catfish')
    emit([0x3E, 0x04])
    emit_jr(0x18, 'apply_palette')

    labels['check_crow_hornet'] = len(code)
    emit([0x79, 0xFE, 0x40])
    emit_jr(0x30, 'pal_hornet')
    emit([0x3E, 0x03])
    emit_jr(0x18, 'apply_palette')

    labels['pal_sara_w_proj'] = len(code)
    emit([0x3E, 0x00])
    emit_jr(0x18, 'apply_palette')

    labels['pal_sara_d_proj'] = len(code)
    emit([0x3E, 0x00])
    emit_jr(0x18, 'apply_palette')

    labels['pal_enemy_proj'] = len(code)
    emit([0x3E, 0x03])
    emit_jr(0x18, 'apply_palette')

    labels['pal_hornet'] = len(code)
    emit([0x3E, 0x04])
    emit_jr(0x18, 'apply_palette')

    labels['pal_orc'] = len(code)
    emit([0x3E, 0x05])
    emit_jr(0x18, 'apply_palette')

    labels['pal_humanoid'] = len(code)
    emit([0x3E, 0x06])
    emit_jr(0x18, 'apply_palette')

    labels['pal_catfish'] = len(code)
    emit([0x3E, 0x07])
    emit_jr(0x18, 'apply_palette')

    labels['sara_palette'] = len(code)
    emit(0x7A)
    emit_jr(0x18, 'apply_palette')

    labels['boss_palette'] = len(code)
    emit(0x7B)

    labels['apply_palette'] = len(code)
    emit([0x4F, 0x7E, 0xE6, 0xF8, 0xB1, 0x77])

    emit([0x23, 0x23, 0x23, 0x23, 0x05])
    loop_abs_addr = colorizer_base_addr + labels['loop_start']
    emit([0xC2, loop_abs_addr & 0xFF, (loop_abs_addr >> 8) & 0xFF])
    emit([0xC9])

    for offset_pos, target_label in forward_jumps:
        target = labels[target_label]
        offset = target - (offset_pos + 1)
        if offset < -128 or offset > 127:
            raise ValueError(f"Jump to {target_label} out of range: {offset}")
        code[offset_pos] = offset & 0xFF

    return bytes(code)


def create_shadow_colorizer_main(colorizer_addr: int, boss_slot_table_addr: int) -> bytes:
    """Shadow colorizer main - processes BOTH shadow OAM buffers. Unchanged from v2.36."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # Push all registers

    # Read Sara form (0xFFBE) -> D register
    code.extend([0xF0, 0xBE, 0xB7, 0x20, 0x04])
    code.extend([0x16, 0x02, 0x18, 0x02])  # Sara W: LD D, 2; JR +2
    code.extend([0x16, 0x01])  # Sara D: LD D, 1

    # Read boss flag (0xFFBF) -> E register via table lookup
    code.extend([0xF0, 0xBF])
    code.extend([0xB7])
    no_boss_jr_pos = len(code)
    code.extend([0x28, 0x00])

    code.extend([0x3D])
    code.extend([0x4F])
    code.extend([0x06, 0x00])
    code.extend([0x21, boss_slot_table_addr & 0xFF, (boss_slot_table_addr >> 8) & 0xFF])
    code.extend([0x09])
    code.extend([0x5E])
    done_boss_jr_pos = len(code)
    code.extend([0x18, 0x00])

    no_boss_pos = len(code)
    code[no_boss_jr_pos + 1] = no_boss_pos - (no_boss_jr_pos + 2)
    code.extend([0x1E, 0x00])

    done_boss_pos = len(code)
    code[done_boss_jr_pos + 1] = done_boss_pos - (done_boss_jr_pos + 2)

    # Colorize BOTH buffers
    code.extend([0x21, 0x03, 0xC0])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0x21, 0x03, 0xC1])
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1, 0xC9])
    return bytes(code)


def create_palette_loader(
    palette_data_addr: int,
    boss_palette_table_addr: int,
    boss_slot_table_addr: int,
    sara_witch_jet_addr: int,
    sara_dragon_jet_addr: int,
    spiral_proj_addr: int,
    shield_proj_addr: int,
    turbo_proj_addr: int,
) -> bytes:
    """Palette loader - unchanged from v2.33."""
    code = bytearray()

    code.extend([0xF0, 0xD0])
    code.append(0x57)

    # Load BG palettes (64 bytes)
    code.extend([0x21, palette_data_addr & 0xFF, (palette_data_addr >> 8) & 0xFF])
    code.extend([0x3E, 0x80, 0xE0, 0x68, 0x0E, 0x40])
    code.extend([0x2A, 0xE0, 0x69, 0x0D, 0x20, 0xFA])

    # Load OBJ palette 0 (dynamic: powerup > form)
    obj_data_addr = palette_data_addr + 64
    code.extend([0x3E, 0x80, 0xE0, 0x6A])

    code.extend([0xF0, 0xC0])
    code.extend([0xB7])
    code.extend([0x28, 23])

    code.extend([0xFE, 0x01])
    code.extend([0x20, 0x05])
    code.extend([0x21, spiral_proj_addr & 0xFF, (spiral_proj_addr >> 8) & 0xFF])
    code.extend([0x18, 17])

    code.extend([0xFE, 0x02])
    code.extend([0x20, 0x05])
    code.extend([0x21, shield_proj_addr & 0xFF, (shield_proj_addr >> 8) & 0xFF])
    code.extend([0x18, 8])

    code.extend([0x21, turbo_proj_addr & 0xFF, (turbo_proj_addr >> 8) & 0xFF])
    code.extend([0x18, 3])

    code.extend([0x21, obj_data_addr & 0xFF, (obj_data_addr >> 8) & 0xFF])

    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # OBJ palette 1
    code.extend([0x3E, 0x88, 0xE0, 0x6A])
    sara_dragon_addr = obj_data_addr + 8
    code.extend([0x21, sara_dragon_addr & 0xFF, (sara_dragon_addr >> 8) & 0xFF])
    code.extend([0x7A, 0xFE, 0x01, 0x20, 0x03])
    code.extend([0x21, sara_dragon_jet_addr & 0xFF, (sara_dragon_jet_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # OBJ palette 2
    code.extend([0x3E, 0x90, 0xE0, 0x6A])
    sara_witch_addr = obj_data_addr + 16
    code.extend([0x21, sara_witch_addr & 0xFF, (sara_witch_addr >> 8) & 0xFF])
    code.extend([0x7A, 0xFE, 0x01, 0x20, 0x03])
    code.extend([0x21, sara_witch_jet_addr & 0xFF, (sara_witch_jet_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # OBJ palettes 3-5
    code.extend([0x3E, 0x98, 0xE0, 0x6A])
    crow_addr = obj_data_addr + 24
    code.extend([0x21, crow_addr & 0xFF, (crow_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x18])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # OBJ palette 6
    code.extend([0x3E, 0xB0, 0xE0, 0x6A])
    humanoid_addr = obj_data_addr + 48
    code.extend([0x21, humanoid_addr & 0xFF, (humanoid_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # OBJ palette 7
    code.extend([0x3E, 0xB8, 0xE0, 0x6A])
    catfish_addr = obj_data_addr + 56
    code.extend([0x21, catfish_addr & 0xFF, (catfish_addr >> 8) & 0xFF])
    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    # Boss override
    code.extend([0xF0, 0xBF])
    code.extend([0xB7])
    boss_skip_pos = len(code)
    code.extend([0x28, 0x00])

    code.extend([0x3D])
    code.extend([0x5F])

    code.extend([0x4F])
    code.extend([0x06, 0x00])
    code.extend([0x21, boss_slot_table_addr & 0xFF, (boss_slot_table_addr >> 8) & 0xFF])
    code.extend([0x09])
    code.extend([0x7E])

    code.extend([0x87])
    code.extend([0xF6, 0x80])
    code.extend([0xE0, 0x6A])

    code.extend([0x7B])
    code.extend([0x87])
    code.extend([0x87])
    code.extend([0x87])
    code.extend([0x4F])
    code.extend([0x06, 0x00])
    code.extend([0x21, boss_palette_table_addr & 0xFF, (boss_palette_table_addr >> 8) & 0xFF])
    code.extend([0x09])

    code.extend([0x0E, 0x08])
    code.extend([0x2A, 0xE0, 0x6B, 0x0D, 0x20, 0xFA])

    no_boss_pos = len(code)
    code[boss_skip_pos + 1] = no_boss_pos - (boss_skip_pos + 2)

    code.append(0xC9)
    return bytes(code)


def create_tile_palette_lookup() -> bytes:
    """256-byte lookup table: tile_id -> BG palette number.

    Palette assignments:
      0 = Floor/platforms/edges/arches (Dungeon blue-white)
      1 = Items (bright gold)
      6 = Wall fill blocks (blue-gray stone)
    """
    lookup = bytearray(256)

    for i in range(256):
        if i <= 0x3F:
            lookup[i] = 0   # Floor, edges, platforms
        elif i <= 0x5F:
            lookup[i] = 6   # Solid wall blocks
        elif i <= 0x87:
            lookup[i] = 0   # Doorway/arch/UI - blend with floor
        elif i <= 0xDF:
            lookup[i] = 1   # ALL item pickups
        elif i <= 0xFD:
            lookup[i] = 6   # Decorative / structural
        else:
            lookup[i] = 0   # Void/border

    return bytes(lookup)


def _emit_process_tile_at_de_single(code: bytearray, lookup_table_high: int = 0x6B) -> None:
    """Emit code to process ONE tile at [DE] on the ACTIVE tilemap only.

    Reads tile from VRAM bank 0, looks up palette in ROM table, writes attr to bank 1.
    DE points to active tilemap (0x98xx or 0x9Cxx based on LCDC bit 3).

    IMPORTANT: Does NOT clobber C. Uses HRAM FFEE as temporary for palette value.
    C is preserved for the caller's use (tilemap base high byte).

    Per-tile cost: 26 M-cycles
      XOR A (1M) + LDH [FF4F],A (3M) = 4M    ; bank 0
      LD A,[DE] (2M)                            ; read tile
      LD L,A (1M) + LD H,imm (2M) = 3M         ; lookup setup
      LD A,[HL] (2M)                            ; get palette
      LDH [FFEE],A (3M)                         ; store palette
      LD A,1 (2M) + LDH [FF4F],A (3M) = 5M     ; bank 1
      LD H,D (1M) + LD L,E (1M) = 2M           ; HL = DE
      LDH A,[FFEE] (3M)                         ; reload palette
      LD [HL],A (2M)                            ; write attr
      TOTAL: 4+2+3+2+3+5+2+3+2 = 26M

    Registers used: A (scratch), H,L (lookup then write)
    Preserves: B (loop counter), C (tilemap base), DE (tilemap position)
    """
    # Bank 0: read tile
    code.extend([0xAF])              # XOR A           ; A = 0
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A   ; VRAM bank 0
    code.extend([0x1A])              # LD A, [DE]       ; A = tile ID

    # Lookup palette from table at 0x6Bxx
    code.extend([0x6F])              # LD L, A          ; L = tile ID
    code.extend([0x26, lookup_table_high])  # LD H, high byte
    code.extend([0x7E])              # LD A, [HL]       ; A = palette
    code.extend([0xE0, 0xEE])        # LDH [FFEE], A   ; store palette temporarily

    # Bank 1: write attribute
    code.extend([0x3E, 0x01])        # LD A, 1
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A   ; VRAM bank 1
    code.extend([0x62])              # LD H, D
    code.extend([0x6B])              # LD L, E
    code.extend([0xF0, 0xEE])        # LDH A, [FFEE]   ; reload palette
    code.extend([0x77])              # LD [HL], A       ; write palette attr


def create_bg_colorizer_active_tilemap(lookup_table_addr: int) -> bytes:
    """BG colorizer that writes ONLY to the active tilemap.

    v2.38 key insight: Writing to both tilemaps wastes half the VBlank budget.
    The game alternates LCDC bit 3 every ~7 frames. By writing only to the
    ACTIVE tilemap and detecting flips, we get 3x throughput.

    Flow:
    1. Check game mode (FFC1), skip on menus
    2. Read LCDC bit 3 → determine tilemap base (0x98 or 0x9C)
    3. Compare with saved LCDC bit 3 at FFEC → if changed, reset counter
    4. Check SCX change → if scrolled, colorize edge column (32 tiles)
    5. Sweep loop: process up to 140 tiles from current position
    6. Save counter back to FFEA/FFEB

    Per-tile cost: ~32M (20M tile + 12M loop overhead)
    Budget: ~4200M available (4560 VBlank - ~360 overhead)
    Tiles per VBlank: ~130 (conservative) → full sweep in ~8 frames

    HRAM layout:
      FFEA: counter low (E offset within tilemap, 0x00-0xFF)
      FFEB: counter high (0-3, added to tilemap base high byte)
      FFEC: saved LCDC bit 3 (0x00 or 0x08)
      FFED: previous SCX/8 (0-31, for scroll detection)
    """
    lookup_high = (lookup_table_addr >> 8) & 0xFF  # 0x6B

    code = bytearray()

    # === CHECK GAME MODE ===
    code.extend([0xF0, 0xC1])        # LDH A, [FFC1]
    code.extend([0xB7])              # OR A
    code.extend([0xC8])              # RET Z (skip on menus)

    code.extend([0xC5, 0xD5, 0xE5])  # PUSH BC, DE, HL

    # === DETERMINE ACTIVE TILEMAP ===
    # Read LCDC bit 3 to determine which tilemap is active
    code.extend([0xF0, 0x40])        # LDH A, [FF40]   ; LCDC register
    code.extend([0xE6, 0x08])        # AND 0x08         ; isolate bit 3
    code.extend([0x4F])              # LD C, A           ; C = current LCDC bit 3 (0x00 or 0x08)

    # === FLIP DETECTION ===
    # Compare with saved value
    code.extend([0xF0, 0xEC])        # LDH A, [FFEC]   ; saved LCDC bit 3
    code.extend([0xB9])              # CP C              ; same?
    flip_skip_pos = len(code)
    code.extend([0x28, 0x00])        # JR Z, no_flip

    # TILEMAP FLIPPED: reset sweep counter to 0
    code.extend([0x79])              # LD A, C           ; new LCDC bit 3
    code.extend([0xE0, 0xEC])        # LDH [FFEC], A    ; save it
    code.extend([0xAF])              # XOR A             ; A = 0
    code.extend([0xE0, 0xEA])        # LDH [FFEA], A    ; counter low = 0
    code.extend([0xE0, 0xEB])        # LDH [FFEB], A    ; counter high = 0

    no_flip_pos = len(code)
    code[flip_skip_pos + 1] = no_flip_pos - (flip_skip_pos + 2)

    # === COMPUTE TILEMAP BASE HIGH BYTE ===
    # C has LCDC bit 3: 0x00 → 0x98, 0x08 → 0x9C
    # Method: 0x98 + (C >> 1) = 0x98 + 0 or 0x98 + 4 = 0x9C
    # Actually: C is 0x00 or 0x08. We want base_high = 0x98 or 0x9C.
    # 0x08 >> 1 = 0x04. So base_high = 0x98 + (C >> 1).
    code.extend([0x79])              # LD A, C           ; 0x00 or 0x08
    code.extend([0xCB, 0x3F])        # SRL A             ; 0x00 or 0x04
    code.extend([0xC6, 0x98])        # ADD A, 0x98       ; 0x98 or 0x9C
    code.extend([0x4F])              # LD C, A           ; C = tilemap base high byte

    # === PHASE 1: SCROLL-EDGE DETECTION ===
    code.extend([0xF0, 0x43])        # LDH A, [FF43]   ; read SCX
    code.extend([0xCB, 0x3F])        # SRL A
    code.extend([0xCB, 0x3F])        # SRL A
    code.extend([0xCB, 0x3F])        # SRL A            ; A = SCX/8 (0-31)
    code.extend([0xE6, 0x1F])        # AND 0x1F         ; mask

    # Compare with previous SCX/8
    code.extend([0x47])              # LD B, A           ; B = current SCX/8
    code.extend([0xF0, 0xED])        # LDH A, [FFED]   ; previous SCX/8
    code.extend([0xB8])              # CP B
    skip_col_pos = len(code)
    code.extend([0x28, 0x00])        # JR Z, no_scroll

    # === SCX CHANGED: COLORIZE EDGE COLUMN ===
    code.extend([0x78])              # LD A, B           ; current SCX/8
    code.extend([0xE0, 0xED])        # LDH [FFED], A    ; save it

    # Compute right-edge column: (SCX/8 + 20) & 31
    code.extend([0xC6, 0x14])        # ADD A, 20
    code.extend([0xE6, 0x1F])        # AND 0x1F         ; wrap to 0-31
    code.extend([0x5F])              # LD E, A           ; E = column
    code.extend([0x51])              # LD D, C           ; D = tilemap base high

    # Colorize 32 rows of this column on ACTIVE tilemap only
    code.extend([0x06, 0x20])        # LD B, 32

    col_loop_start = len(code)

    # Process single tile at DE
    _emit_process_tile_at_de_single(code, lookup_high)

    # Next row: E += 32
    code.extend([0x7B])              # LD A, E
    code.extend([0xC6, 0x20])        # ADD A, 0x20
    code.extend([0x5F])              # LD E, A
    code.extend([0x30, 0x01])        # JR NC, +1
    code.extend([0x14])              # INC D

    # Wrap D: if D >= base+4, subtract 4
    code.extend([0x7A])              # LD A, D
    code.extend([0x91])              # SUB C             ; A = D - base
    code.extend([0xFE, 0x04])        # CP 4              ; past end?
    code.extend([0x38, 0x02])        # JR C, +2          ; no wrap
    code.extend([0x51])              # LD D, C           ; D = base (wrap to start)
    # (E already has the right low byte after ADD)

    code.extend([0x05])              # DEC B
    col_loop_end = len(code)
    col_offset = col_loop_start - (col_loop_end + 2)
    code.extend([0x20, col_offset & 0xFF])  # JR NZ, col_loop

    # After column: load sweep position, reduced tile count
    code.extend([0xF0, 0xEA])        # LDH A, [FFEA]   ; counter low
    code.extend([0x5F])              # LD E, A
    code.extend([0xF0, 0xEB])        # LDH A, [FFEB]   ; counter high
    code.extend([0x81])              # ADD A, C          ; + tilemap base
    code.extend([0x57])              # LD D, A           ; DE = sweep position
    code.extend([0x06, 0x60])        # LD B, 96          ; reduced sweep after column
    jr_to_sweep_pos = len(code)
    code.extend([0x18, 0x00])        # JR sweep_loop

    # === NO SCROLL: FULL SWEEP BUDGET ===
    no_scroll_pos = len(code)
    code[skip_col_pos + 1] = no_scroll_pos - (skip_col_pos + 2)

    code.extend([0xF0, 0xEA])        # LDH A, [FFEA]   ; counter low
    code.extend([0x5F])              # LD E, A
    code.extend([0xF0, 0xEB])        # LDH A, [FFEB]   ; counter high
    code.extend([0x81])              # ADD A, C          ; + tilemap base
    code.extend([0x57])              # LD D, A           ; DE = sweep position
    code.extend([0x06, 0x80])        # LD B, 128         ; full sweep budget

    # === SWEEP LOOP ===
    sweep_start = len(code)
    code[jr_to_sweep_pos + 1] = (sweep_start - (jr_to_sweep_pos + 2)) & 0xFF

    # Process single tile at DE (active tilemap only)
    _emit_process_tile_at_de_single(code, lookup_high)

    # Next position: INC DE
    code.extend([0x13])              # INC DE

    # Wrap check: if D >= base+4, reset to base
    code.extend([0x7A])              # LD A, D
    code.extend([0x91])              # SUB C             ; A = D - base
    code.extend([0xFE, 0x04])        # CP 4
    code.extend([0x38, 0x02])        # JR C, +2          ; no wrap
    code.extend([0x51])              # LD D, C           ; wrap: D = base

    code.extend([0x05])              # DEC B
    sweep_end = len(code)
    sweep_offset = sweep_start - (sweep_end + 2)
    code.extend([0x20, sweep_offset & 0xFF])  # JR NZ, sweep_loop

    # === SAVE POSITION COUNTER ===
    # Convert DE back to relative offset: D - tilemap_base = high, E = low
    code.extend([0x7A])              # LD A, D
    code.extend([0x91])              # SUB C             ; relative high
    code.extend([0xE6, 0x03])        # AND 0x03          ; wrap 0-3
    code.extend([0xE0, 0xEB])        # LDH [FFEB], A
    code.extend([0x7B])              # LD A, E
    code.extend([0xE0, 0xEA])        # LDH [FFEA], A

    # === CLEANUP ===
    code.extend([0xAF])              # XOR A
    code.extend([0xE0, 0x4F])        # LDH [FF4F], A   ; back to VRAM bank 0
    code.extend([0xE1, 0xD1, 0xC1])  # POP HL, DE, BC
    code.extend([0xC9])              # RET

    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int, bg_colorizer_addr: int) -> bytes:
    """Combined function: bg_colorizer -> palette_loader -> shadow_main -> DMA.
    BG colorizer runs FIRST during VBlank when VRAM is freely accessible.
    """
    code = bytearray()
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF, 0xC9])
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook with input handling. Unchanged from v2.36."""
    joypad_input = bytearray([
        # D-pad (1 read)
        0x3E, 0x20,        # LD A, 0x20
        0xE0, 0x00,        # LDH [FF00], A
        0xF0, 0x00,        # LDH A, [FF00]
        0x2F,              # CPL
        0xE6, 0x0F,        # AND 0x0F
        0xCB, 0x37,        # SWAP A
        0x47,              # LD B, A
        # Buttons (8 reads via loop)
        0x3E, 0x10,        # LD A, 0x10
        0xE0, 0x00,        # LDH [FF00], A
        0x0E, 0x08,        # LD C, 8
        0xF0, 0x00,        # .loop: LDH A,[FF00]
        0x0D,              # DEC C
        0x20, 0xFB,        # JR NZ, .loop
        0x2F,              # CPL
        0xE6, 0x0F,        # AND 0x0F
        0xB0,              # OR B
        0xE0, 0x93,        # LDH [FF93], A
        # Deselect
        0x3E, 0x30,        # LD A, 0x30
        0xE0, 0x00,        # LDH [FF00], A
    ])  # 33 bytes
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,  # Switch to bank 13
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,
        0x3E, 0x01, 0xEA, 0x00, 0x20,  # Switch back to bank 1
        0xC9,
    ])  # 14 bytes
    total = joypad_input + hook_code
    assert len(total) <= 47, f"Hook is {len(total)} bytes, max 47!"
    return bytes(total)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    print("=== Penta Dragon DX v2.38 ===")
    print("Active-Tilemap-Only BG Colorizer")
    print()
    print("NEW in v2.38:")
    print("  1. Single tilemap: writes only to ACTIVE tilemap (LCDC bit 3)")
    print("  2. ~128 tiles/VBlank: 3x throughput vs v2.37's 48")
    print("  3. Flip detection: resets sweep when game swaps tilemap")
    print("  4. Full sweep in ~8 frames (matches game's ~7-frame swap)")
    print("  5. Scroll-edge column still prioritized (32 tiles)")
    print()

    with open(input_rom, "rb") as f:
        rom = bytearray(f.read())

    apply_all_display_patches(rom)

    palettes = load_palettes_from_yaml(palette_yaml)

    # === DATA LAYOUT (Bank 13) ===
    palette_data_addr = 0x6800
    boss_palette_table_addr = 0x6880
    boss_slot_table_addr = 0x68C0
    sara_witch_jet_addr = 0x68D0
    sara_dragon_jet_addr = 0x68D8
    spiral_proj_addr = 0x68E0
    shield_proj_addr = 0x68E8
    turbo_proj_addr = 0x68F0

    # === CODE LAYOUT (Bank 13) ===
    palette_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    lookup_table_addr = 0x6B00
    bg_colorizer_addr = 0x6C00
    combined_addr = 0x6D00

    # Generate code
    palette_loader = create_palette_loader(
        palette_data_addr, boss_palette_table_addr, boss_slot_table_addr,
        sara_witch_jet_addr, sara_dragon_jet_addr,
        spiral_proj_addr, shield_proj_addr, turbo_proj_addr,
    )
    shadow_main = create_shadow_colorizer_main(colorizer_addr, boss_slot_table_addr)
    colorizer = create_tile_based_colorizer(colorizer_addr)
    lookup_table = create_tile_palette_lookup()
    bg_colorizer = create_bg_colorizer_active_tilemap(lookup_table_addr)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr, bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    # Print sizes
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X} (ends 0x{palette_loader_addr + len(palette_loader):04X})")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X} (ends 0x{shadow_main_addr + len(shadow_main):04X})")
    print(f"OBJ colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X} (ends 0x{colorizer_addr + len(colorizer):04X})")
    print(f"BG lookup table: {len(lookup_table)} bytes at 0x{lookup_table_addr:04X} (ends 0x{lookup_table_addr + len(lookup_table):04X})")
    print(f"BG colorizer: {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X} (ends 0x{bg_colorizer_addr + len(bg_colorizer):04X})")
    print(f"Combined: {len(combined)} bytes at 0x{combined_addr:04X}")
    print(f"VBlank hook: {len(vblank_hook)} bytes at 0x0824")

    # Verify no overlaps
    regions = [
        ('palette_loader', palette_loader_addr, len(palette_loader)),
        ('shadow_main', shadow_main_addr, len(shadow_main)),
        ('colorizer', colorizer_addr, len(colorizer)),
        ('lookup_table', lookup_table_addr, len(lookup_table)),
        ('bg_colorizer', bg_colorizer_addr, len(bg_colorizer)),
        ('combined', combined_addr, len(combined)),
    ]
    for i, (name_a, start_a, size_a) in enumerate(regions):
        for name_b, start_b, size_b in regions[i+1:]:
            end_a = start_a + size_a
            end_b = start_b + size_b
            if start_a < end_b and start_b < end_a:
                raise ValueError(f"OVERLAP: {name_a} (0x{start_a:04X}-0x{end_a:04X}) "
                                 f"and {name_b} (0x{start_b:04X}-0x{end_b:04X})")

    bank13_offset = 13 * 0x4000

    def write_bank13(addr, data):
        rom_offset = bank13_offset + (addr - 0x4000)
        rom[rom_offset:rom_offset + len(data)] = data

    # Write palette data
    write_bank13(palette_data_addr, palettes['bg_data'])
    write_bank13(palette_data_addr + 64, palettes['obj_data'])
    write_bank13(boss_palette_table_addr, palettes['boss_palette_table'])
    write_bank13(boss_slot_table_addr, palettes['boss_slot_table'])
    write_bank13(sara_witch_jet_addr, palettes['sara_witch_jet'])
    write_bank13(sara_dragon_jet_addr, palettes['sara_dragon_jet'])
    write_bank13(spiral_proj_addr, palettes['spiral_proj'])
    write_bank13(shield_proj_addr, palettes['shield_proj'])
    write_bank13(turbo_proj_addr, palettes['turbo_proj'])

    # Write code
    write_bank13(palette_loader_addr, palette_loader)
    write_bank13(shadow_main_addr, shadow_main)
    write_bank13(colorizer_addr, colorizer)
    write_bank13(lookup_table_addr, lookup_table)
    write_bank13(bg_colorizer_addr, bg_colorizer)
    write_bank13(combined_addr, combined)

    # Patch original ROM hooks
    rom[0x06D5:0x06D5 + 3] = bytearray([0x00, 0x00, 0x00])
    rom[0x0824:0x0824 + len(vblank_hook)] = vblank_hook

    # Set CGB flag
    rom[0x143] = 0x80
    print(f"\nSet CGB flag at 0x143")

    # Verify BG lookup table distribution
    pal_counts = [0] * 8
    for p in lookup_table:
        pal_counts[p] += 1
    print(f"\nBG Lookup Table Distribution:")
    pal_names = ['Floor/Void', 'Items(Gold)', 'Purple', 'Green', 'Cyan', 'Fire', 'Walls(Stone)', 'Mystery']
    for i, (count, name) in enumerate(zip(pal_counts, pal_names)):
        if count > 0:
            print(f"  Palette {i} ({name}): {count} tiles")

    output_rom.parent.mkdir(parents=True, exist_ok=True)
    with open(output_rom, "wb") as f:
        f.write(rom)

    print(f"\nROM patched successfully")
    print(f"  Output: {output_rom}")
    print(f"\nTest with:")
    print(f"  ./mgba-qt.sh {output_rom} -t save_states_for_claude/v2.31_sara_w_mid_level1.ss0")


if __name__ == "__main__":
    main()
