#!/usr/bin/env python3
"""
v2.34: Full Background Colorization Fix

CRITICAL FIX - BG colorizer was broken since v2.28:
  The one-shot row counter processed 18 rows then STOPPED FOREVER.
  When the player scrolled, new tiles came into VRAM but never got
  colorized because the counter was stuck at 18.

FIXES IN v2.34:
1. CONTINUOUS BG colorizer: cycles through all 32 tilemap rows forever
   - Processes 2 rows per VBlank (full refresh every 16 frames = 0.27s)
   - Counter wraps at 32 using AND 0x1F instead of stopping at 18
2. GAME MODE DETECTION: checks 0xFFC1 (gameplay flag)
   - Menu/title: skip tile-based coloring (prevents yellow text corruption)
   - Gameplay: apply full tile-based palette assignment
3. IMPROVED TILE LOOKUP: per-tile granularity from VRAM analysis
   - Floor (0x00-0x12, 0x24-0x25, 0x28-0x30, 0x35): Palette 0 (blue-white)
   - Walls/structure (0x13-0x23, 0x26-0x27, 0x31-0x3F, 0x40-0x7F): Palette 6 (stone gray)
   - Items (0x88-0xDF): Palette 1 (gold/yellow)
   - Void (0xFE-0xFF): Palette 0
4. WALL COLOR FIX: Uses BG palette 6 (blue-gray stone) instead of palette 2 (purple)
   - Walls now look like stone castle walls, not purple blobs

INHERITED from v2.33:
- Multi-boss palette system (8 bosses, table-based)
- Per-entity projectile detection
- Powerup-based Palette 0 (spiral=cyan, shield=gold, turbo=orange)
- Stage detection via 0xFFD0
- Flicker-free pre-DMA shadow buffer modification
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
    # Fixed key mapping to match YAML names
    obj_key_map = {
        0: ('EnemyProjectile', ["0000", "7C1F", "5817", "3010"]),  # Palette 0 default
        1: ('SaraDragon', ["0000", "03E0", "01C0", "0000"]),
        2: ('SaraWitch', ["0000", "2EBE", "511F", "0842"]),
        3: ('SaraProjectileAndCrow', ["0000", "001F", "0017", "000F"]),  # Fixed: was 'Crow'
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
    """
    Tile-based OBJ colorizer with per-entity projectile detection.
    Unchanged from v2.33.
    """
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
    """Shadow colorizer main - unchanged from v2.33."""
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])

    code.extend([0xF0, 0xBE, 0xB7, 0x20, 0x04])
    code.extend([0x16, 0x02, 0x18, 0x02])
    code.extend([0x16, 0x01])

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
    code.extend([0x87])
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
    """
    256-byte lookup table: tile_id -> BG palette number.

    v2.34: Per-tile granularity based on VRAM analysis of Level 1.

    VRAM tile observations (from dynamic analysis):
      Row pattern: FE 17 [wall] [wall] [floor...] [platform] [wall] FE
      - FE = void/border
      - 17, 16 = wall edge tiles
      - 01, 02, 03, 04, 06 = floor checkerboard
      - 24, 25, 30, 35 = platform edges (floor-adjacent)
      - 26, 27, 33, 36 = wall structure
      - 40-5B = wall interiors (doors, windows, columns)
      - 88-DF = items (gold!)

    Palette assignments:
      0 = Floor/platforms (Dungeon blue-white)
      1 = Items (bright gold)
      6 = Walls/structure (blue-gray stone)
    """
    lookup = bytearray(256)

    for i in range(256):
        # === FLOOR / VOID / PLATFORMS (Palette 0) ===
        if i == 0x00:
            lookup[i] = 0   # Empty/transparent
        elif i <= 0x06:
            lookup[i] = 0   # Floor tiles (0x01-0x06 checkerboard)
        elif i <= 0x0F:
            lookup[i] = 0   # Floor variants / empty
        elif i <= 0x12:
            lookup[i] = 0   # More floor/transition

        # === STRUCTURAL DETAILS (Palette 6 = stone gray) ===
        elif i <= 0x23:
            lookup[i] = 6   # Wall edges, corners (0x13-0x23)
                             # Includes 0x16, 0x17 (wall borders),
                             # 0x18, 0x19, 0x1A, 0x1B (transitions)

        # === PLATFORMS (Palette 0 = floor color for continuity) ===
        elif i == 0x24 or i == 0x25:
            lookup[i] = 0   # Platform top edge (floor-adjacent)
        elif i == 0x26 or i == 0x27:
            lookup[i] = 6   # Wall structure (wall-adjacent)
        elif i <= 0x2F:
            lookup[i] = 0   # Platform body (0x28-0x2F)
        elif i == 0x30:
            lookup[i] = 0   # Platform bottom edge
        elif i <= 0x34:
            lookup[i] = 6   # Wall-adjacent structure
        elif i == 0x35:
            lookup[i] = 0   # Platform bottom edge
        elif i <= 0x3F:
            lookup[i] = 6   # Wall structure (0x36-0x3F)

        # === WALLS / DOORS / WINDOWS (Palette 6 = stone gray) ===
        elif i <= 0x7F:
            lookup[i] = 6   # All wall interiors (0x40-0x7F)
                             # Includes doors, windows, columns, decorations

        # === UI / TRANSITION (Palette 0 = safe) ===
        elif i <= 0x87:
            lookup[i] = 0   # UI area / unused in gameplay

        # === ITEMS (Palette 1 = GOLD!) ===
        elif i <= 0xDF:
            lookup[i] = 1   # ALL item pickups (0x88-0xDF)
                             # Health, extra lives, powerups, orbs

        # === MORE STRUCTURE (Palette 6) ===
        elif i <= 0xFD:
            lookup[i] = 6   # Decorative / structural

        # === VOID (Palette 0) ===
        elif i == 0xFE:
            lookup[i] = 0   # Void/border (black)
        else:  # 0xFF
            lookup[i] = 0   # Special void

    return bytes(lookup)


def create_bg_colorizer_continuous(lookup_table_addr: int) -> bytes:
    """
    Continuous BG colorizer with STAT-safe VRAM access - THE KEY FIX for v2.34.

    Processes 2 rows per VBlank call, cycling through all 32 tilemap rows.
    Row counter at HRAM 0xFFE0 wraps at 32 using AND 0x1F.
    Full tilemap refresh every 16 frames = ~0.27 seconds at 60fps.

    CRITICAL: Checks LCD STAT register (0xFF41) before every VRAM read/write.
    Mode 3 (LCD transfer) blocks VRAM access - reads return 0xFF, writes are
    silently dropped. The STAT wait loop ensures 100% accuracy by waiting
    until mode 0 (HBlank), 1 (VBlank), or 2 (OAM scan) before accessing VRAM.

    Also checks 0xFFC1 (gameplay flag) to skip coloring on menus/title screens.

    DUAL TILEMAP FIX: Game double-buffers between 0x9800 and 0x9C00 tilemaps,
    alternating LCDC bit 3 every ~6 frames. We write palette attributes to BOTH
    tilemaps (0x9800 and 0x9C00) for each tile to ensure colors are always visible.

    Code flow per call:
      1. Check 0xFFC1 - if zero (menu), return immediately
      2. For each of 2 rows:
         a. Read row counter from 0xFFE0
         b. Calculate VRAM row address: 0x9800 + (row * 32)
         c. For each of 32 tiles in row:
            - Switch to VRAM bank 0, STAT-wait, read tile ID
            - Look up palette from ROM table (no STAT needed)
            - Switch to VRAM bank 1, STAT-wait, write to 0x9800 attr
            - STAT-wait, write same palette to 0x9C00 attr (+0x0400)
         d. Increment row counter, wrap at 32
      3. Switch back to VRAM bank 0
      4. Return
    """
    code = bytearray()

    # === CHECK GAME MODE ===
    # 0xFFC1 = gameplay active flag
    # 0 = menu/title/score (skip coloring)
    # non-zero = gameplay (apply tile colors)
    code.extend([0xF0, 0xC1])  # LDH A, [0xFFC1]
    code.extend([0xB7])         # OR A
    code.extend([0xC8])         # RET Z (return if menu - all attributes stay palette 0)

    # === PROCESS 2 ROWS ===
    code.extend([0xC5, 0xD5, 0xE5])  # PUSH BC, DE, HL

    code.extend([0x0E, 0x02])  # LD C, 2 (2 rows per VBlank)

    # === ROW LOOP START ===
    row_loop_start = len(code)

    # Load row counter
    code.extend([0xF0, 0xE0])  # LDH A, [0xFFE0]

    # Calculate VRAM address: HL = 0x9800 + (row * 32)
    code.extend([0x6F])         # LD L, A
    code.extend([0x26, 0x00])   # LD H, 0
    code.extend([0x29])         # ADD HL, HL  (*2)
    code.extend([0x29])         # ADD HL, HL  (*4)
    code.extend([0x29])         # ADD HL, HL  (*8)
    code.extend([0x29])         # ADD HL, HL  (*16)
    code.extend([0x29])         # ADD HL, HL  (*32)
    # Add base address 0x9800 to HL without clobbering C (our row counter!)
    # LD BC would clobber C. Instead: H += 0x98
    code.extend([0x7C])         # LD A, H
    code.extend([0xC6, 0x98])   # ADD A, 0x98
    code.extend([0x67])         # LD H, A  (HL = row*32 + 0x9800)

    # B = 32 tiles per row
    code.extend([0x06, 0x20])  # LD B, 32

    # === TILE LOOP ===
    tile_loop_start = len(code)

    # Switch to VRAM bank 0 and read tile ID (with STAT check)
    code.extend([0xAF])         # XOR A (A = 0)
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A (select VRAM bank 0)

    # Wait until VRAM accessible for read (mode 3 returns garbage 0xFF)
    stat_wait_read = len(code)
    code.extend([0xF0, 0x41])   # LDH A, [0xFF41]
    code.extend([0xE6, 0x03])   # AND 0x03
    code.extend([0xFE, 0x03])   # CP 0x03
    stat_read_back = stat_wait_read - (len(code) + 2)
    code.extend([0x28, stat_read_back & 0xFF])  # JR Z, stat_wait_read

    code.extend([0x56])         # LD D, [HL] (D = tile ID from bank 0 - VRAM safe)

    # Look up palette from table
    code.extend([0xE5])         # PUSH HL (save VRAM pointer)
    code.extend([0x26, (lookup_table_addr >> 8) & 0xFF])  # LD H, table_hi_byte
    code.extend([0x7A])         # LD A, D (A = tile ID)
    code.extend([0x6F])         # LD L, A (HL = table + tile_id)
    code.extend([0x5E])         # LD E, [HL] (E = palette number)
    code.extend([0xE1])         # POP HL (restore VRAM pointer)

    # Switch to VRAM bank 1 and write attribute (with STAT check)
    code.extend([0x3E, 0x01])   # LD A, 1
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A (select VRAM bank 1)

    # === STAT CHECK: Wait until VRAM accessible (not mode 3) ===
    # LCD STAT (0xFF41) bits 0-1 = mode: 0=HBlank, 1=VBlank, 2=OAM, 3=Transfer
    # Mode 3 = VRAM locked, writes silently dropped. Wait for any other mode.
    stat_wait = len(code)
    code.extend([0xF0, 0x41])   # LDH A, [0xFF41]  ; Read LCD STAT
    code.extend([0xE6, 0x03])   # AND 0x03          ; Mode bits only
    code.extend([0xFE, 0x03])   # CP 0x03           ; Mode 3?
    stat_back = stat_wait - (len(code) + 2)
    code.extend([0x28, stat_back & 0xFF])  # JR Z, stat_wait (loop if mode 3)

    code.extend([0x73])         # LD [HL], E (write palette to 0x9800 tilemap - VRAM safe)

    # === ALSO WRITE TO 0x9C00 TILEMAP (double-buffer fix) ===
    # Game alternates LCDC bit 3 between 0x9800 and 0x9C00 every ~6 frames.
    # Must color BOTH tilemaps or colors only visible ~50% of frames.
    # 0x9C00 = 0x9800 + 0x0400, so H += 4.
    code.extend([0xE5])         # PUSH HL (save 0x9800 pointer)
    code.extend([0x7C])         # LD A, H
    code.extend([0xC6, 0x04])   # ADD A, 0x04  (0x98xx -> 0x9Cxx)
    code.extend([0x67])         # LD H, A

    # STAT wait for 0x9C00 write
    stat_wait_9c = len(code)
    code.extend([0xF0, 0x41])   # LDH A, [0xFF41]
    code.extend([0xE6, 0x03])   # AND 0x03
    code.extend([0xFE, 0x03])   # CP 0x03
    stat_9c_back = stat_wait_9c - (len(code) + 2)
    code.extend([0x28, stat_9c_back & 0xFF])  # JR Z, stat_wait_9c

    code.extend([0x73])         # LD [HL], E (write palette to 0x9C00 tilemap)
    code.extend([0xE1])         # POP HL (restore 0x9800 pointer)

    # Next tile
    code.extend([0x23])         # INC HL
    code.extend([0x05])         # DEC B
    tile_offset = tile_loop_start - (len(code) + 2)
    code.extend([0x20, tile_offset & 0xFF])  # JR NZ, tile_loop

    # === INCREMENT ROW COUNTER (wrap at 32) ===
    code.extend([0xF0, 0xE0])   # LDH A, [0xFFE0]
    code.extend([0x3C])         # INC A
    code.extend([0xE6, 0x1F])   # AND 0x1F (wrap at 32)
    code.extend([0xE0, 0xE0])   # LDH [0xFFE0], A

    # Next row
    code.extend([0x0D])         # DEC C
    row_offset = row_loop_start - (len(code) + 2)
    code.extend([0x20, row_offset & 0xFF])  # JR NZ, row_loop

    # === CLEANUP ===
    code.extend([0xAF])         # XOR A
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A (back to VRAM bank 0)
    code.extend([0xE1, 0xD1, 0xC1])  # POP HL, DE, BC
    code.extend([0xC9])         # RET

    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int, bg_colorizer_addr: int) -> bytes:
    """Combined function that calls all colorization routines.

    Order: palette_loader -> shadow_main -> bg_colorizer -> DMA
    BG colorizer uses STAT register checks for safe VRAM access.
    """
    code = bytearray()
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF, 0xC9])
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook with input handling (unchanged from v2.33)."""
    simplified_input = bytearray([
        0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,
        0x3E, 0x10, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00, 0x2F, 0xE6, 0x0F, 0xB0,
        0xE0, 0x93, 0x3E, 0x30, 0xE0, 0x00,
    ])
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,  # Switch to bank 13
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,
        0x3E, 0x01, 0xEA, 0x00, 0x20,  # Switch back to bank 1
        0xC9,
    ])
    return bytes(simplified_input + hook_code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    print("=== Penta Dragon DX v2.34 ===")
    print("Full Background Colorization Fix")
    print()
    print("FIXES in v2.34:")
    print("  1. CONTINUOUS BG colorizer (was one-shot, now cycles all 32 rows)")
    print("  2. Game mode detection (0xFFC1 - skip menus)")
    print("  3. Improved tile lookup (per-tile granularity)")
    print("  4. Wall color fix (palette 6 stone gray instead of palette 2 purple)")
    print()
    print("BG Palette Usage:")
    print("  Palette 0: Floor/platforms (blue-white dungeon)")
    print("  Palette 1: Items (bright gold)")
    print("  Palette 6: Walls/structure (blue-gray stone)")
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
        palette_data_addr,
        boss_palette_table_addr,
        boss_slot_table_addr,
        sara_witch_jet_addr,
        sara_dragon_jet_addr,
        spiral_proj_addr,
        shield_proj_addr,
        turbo_proj_addr,
    )
    shadow_main = create_shadow_colorizer_main(colorizer_addr, boss_slot_table_addr)
    colorizer = create_tile_based_colorizer(colorizer_addr)
    lookup_table = create_tile_palette_lookup()
    bg_colorizer = create_bg_colorizer_continuous(lookup_table_addr)
    combined = create_combined_with_dma(palette_loader_addr, shadow_main_addr, bg_colorizer_addr)
    vblank_hook = create_vblank_hook_with_input(combined_addr)

    # Print sizes
    print(f"Palette loader: {len(palette_loader)} bytes at 0x{palette_loader_addr:04X} (ends 0x{palette_loader_addr + len(palette_loader):04X})")
    print(f"Shadow main: {len(shadow_main)} bytes at 0x{shadow_main_addr:04X} (ends 0x{shadow_main_addr + len(shadow_main):04X})")
    print(f"OBJ colorizer: {len(colorizer)} bytes at 0x{colorizer_addr:04X} (ends 0x{colorizer_addr + len(colorizer):04X})")
    print(f"BG lookup table: {len(lookup_table)} bytes at 0x{lookup_table_addr:04X} (ends 0x{lookup_table_addr + len(lookup_table):04X})")
    print(f"BG colorizer: {len(bg_colorizer)} bytes at 0x{bg_colorizer_addr:04X} (ends 0x{bg_colorizer_addr + len(bg_colorizer):04X})")
    print(f"Combined: {len(combined)} bytes at 0x{combined_addr:04X}")

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
    print(f"  ./mgba-qt.sh {output_rom} -t save_states_for_claude/level1_sara_w_gargoyle_mini_boss.ss0")


if __name__ == "__main__":
    main()
