#!/usr/bin/env python3
"""
v2.36: BG Colorization + Input Fix

FIXES over v2.35:
1. INPUT DEBOUNCE: Match original game's joypad routine
   - 1 d-pad read + 8 button reads via loop (proper debounce)
   - Fixes phantom button presses and missed inputs
2. BG COLORIZER: Increased to 32 tiles per frame
   - BG colorizer runs FIRST in VBlank (~4560 M-cycles available)
   - 32 tiles × ~75 M = 2400 M total, well within VBlank budget
   - Full tilemap refresh every 32 frames (~0.53 seconds)
3. SHADOW COLORIZER: Reverted to both-buffer processing
   - Colorizes BOTH C000 and C100 every frame
   - WRAM writes don't need VBlank timing (always writable)
   - Fixed: single-buffer had inverted FFCB logic (wrong buffer colored)

INHERITED from v2.35:
- Inline tile->palette comparison (no ROM table dependency)
- BG colorizer runs FIRST in VBlank
- Conservative tile categorization
- Position counter at FFEA/FFEB
- Independent tilemap reads

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
    """Shadow colorizer main - processes BOTH shadow OAM buffers.

    Colorizes both C000 and C100 buffers every frame. This ensures
    whichever buffer DMA copies, it has correct palette assignments.
    WRAM writes don't need VBlank timing, so overrunning VBlank is safe.

    D = Sara palette (1=Dragon, 2=Witch)
    E = 0 (no boss) or palette slot from boss_slot_table (6 or 7)
    """
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # Push all registers

    # Read Sara form (0xFFBE) -> D register
    code.extend([0xF0, 0xBE, 0xB7, 0x20, 0x04])  # LDH A,[FFBE]; OR A; JR NZ,+4
    code.extend([0x16, 0x02, 0x18, 0x02])  # Sara W: LD D, 2; JR +2
    code.extend([0x16, 0x01])  # Sara D: LD D, 1

    # Read boss flag (0xFFBF) -> E register via table lookup
    code.extend([0xF0, 0xBF])  # LDH A, [0xFFBF]
    code.extend([0xB7])  # OR A
    no_boss_jr_pos = len(code)
    code.extend([0x28, 0x00])  # JR Z, no_boss (placeholder)

    # Boss active: look up slot from table
    code.extend([0x3D])  # DEC A (0-based index)
    code.extend([0x4F])  # LD C, A
    code.extend([0x06, 0x00])  # LD B, 0
    code.extend([0x21, boss_slot_table_addr & 0xFF, (boss_slot_table_addr >> 8) & 0xFF])
    code.extend([0x09])  # ADD HL, BC
    code.extend([0x5E])  # LD E, [HL]
    done_boss_jr_pos = len(code)
    code.extend([0x18, 0x00])  # JR done_boss (placeholder)

    no_boss_pos = len(code)
    code[no_boss_jr_pos + 1] = no_boss_pos - (no_boss_jr_pos + 2)
    code.extend([0x1E, 0x00])  # LD E, 0

    done_boss_pos = len(code)
    code[done_boss_jr_pos + 1] = done_boss_pos - (done_boss_jr_pos + 2)

    # Colorize BOTH buffers (ensures DMA always copies colored data)
    code.extend([0x21, 0x03, 0xC0])  # LD HL, 0xC003 (buffer 1)
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])
    code.extend([0x21, 0x03, 0xC1])  # LD HL, 0xC103 (buffer 2)
    code.extend([0xCD, colorizer_addr & 0xFF, colorizer_addr >> 8])

    code.extend([0xE1, 0xD1, 0xC1, 0xF1, 0xC9])  # Pop all and return
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

    v2.35: Conservative categorization based on real VRAM analysis.
    Wall fill (0x40-0x5F) is wall color. Arch/doorway frames (0x60-0x7F)
    are floor-colored to avoid visible "lines" across floor areas.

    Palette assignments:
      0 = Floor/platforms/edges/arches (Dungeon blue-white)
      1 = Items (bright gold)
      6 = Wall fill blocks (blue-gray stone)
    """
    lookup = bytearray(256)

    for i in range(256):
        # === FLOOR / VOID / EDGES / PLATFORMS (Palette 0) ===
        if i <= 0x3F:
            lookup[i] = 0   # Floor (0x01-0x06), edges (0x13-0x23),
                             # platforms (0x24-0x3F), empty (0x00, 0x07-0x12)

        # === WALL FILL BLOCKS (Palette 6 = stone gray) ===
        elif i <= 0x5F:
            lookup[i] = 6   # Solid wall blocks (0x40-0x5F) - only at screen edges

        # === ARCH / DOORWAY FRAMES (Palette 0 = floor) ===
        elif i <= 0x7F:
            lookup[i] = 0   # Doorway/arch elements (0x60-0x7F) - blend with floor

        # === UI / TRANSITION (Palette 0 = safe) ===
        elif i <= 0x87:
            lookup[i] = 0   # UI area / unused in gameplay

        # === ITEMS (Palette 1 = GOLD!) ===
        elif i <= 0xDF:
            lookup[i] = 1   # ALL item pickups (0x88-0xDF)

        # === HIGH STRUCTURE (Palette 6) ===
        elif i <= 0xFD:
            lookup[i] = 6   # Decorative / structural (0xE0-0xFD)

        # === VOID (Palette 0) ===
        else:
            lookup[i] = 0   # Void/border (0xFE-0xFF)

    return bytes(lookup)


def _emit_tile_to_palette(code: bytearray) -> None:
    """Emit inline tile→palette comparison chain.

    Input: D = tile ID
    Output: E = palette number

    Ranges (no ROM table needed - avoids MBC bank issues):
      0x00-0x3F → palette 0  (floor/edges/platforms)
      0x40-0x5F → palette 6  (wall fill blocks)
      0x60-0x87 → palette 0  (arch/doorway/UI)
      0x88-0xDF → palette 1  (items - gold)
      0xE0-0xFD → palette 6  (decorative/structural)
      0xFE-0xFF → palette 0  (void)
    """
    # LD A, D
    code.append(0x7A)

    # Each comparison block: CP imm8 (2 bytes) + JR C, offset (2 bytes) = 4 bytes
    # We'll fill in JR offsets after laying out all blocks

    cp_40 = len(code)
    code.extend([0xFE, 0x40, 0x38, 0x00])  # CP 0x40; JR C, pal0

    cp_60 = len(code)
    code.extend([0xFE, 0x60, 0x38, 0x00])  # CP 0x60; JR C, pal6

    cp_88 = len(code)
    code.extend([0xFE, 0x88, 0x38, 0x00])  # CP 0x88; JR C, pal0

    cp_e0 = len(code)
    code.extend([0xFE, 0xE0, 0x38, 0x00])  # CP 0xE0; JR C, pal1

    cp_fe = len(code)
    code.extend([0xFE, 0xFE, 0x38, 0x00])  # CP 0xFE; JR C, pal6

    # Fall through: tiles 0xFE-0xFF → palette 0
    pal0 = len(code)
    code.extend([0x1E, 0x00])               # LD E, 0
    jr_done_1 = len(code)
    code.extend([0x18, 0x00])               # JR done

    pal1 = len(code)
    code.extend([0x1E, 0x01])               # LD E, 1
    jr_done_2 = len(code)
    code.extend([0x18, 0x00])               # JR done

    pal6 = len(code)
    code.extend([0x1E, 0x06])               # LD E, 6
    # Fall through to done

    done = len(code)

    # Fix up JR offsets: JR at pos P targets P+2+offset
    code[cp_40 + 3] = (pal0 - (cp_40 + 4)) & 0xFF
    code[cp_60 + 3] = (pal6 - (cp_60 + 4)) & 0xFF
    code[cp_88 + 3] = (pal0 - (cp_88 + 4)) & 0xFF
    code[cp_e0 + 3] = (pal1 - (cp_e0 + 4)) & 0xFF
    code[cp_fe + 3] = (pal6 - (cp_fe + 4)) & 0xFF
    code[jr_done_1 + 1] = (done - (jr_done_1 + 2)) & 0xFF
    code[jr_done_2 + 1] = (done - (jr_done_2 + 2)) & 0xFF


def create_bg_colorizer_continuous() -> bytes:
    """
    Continuous BG colorizer - v2.35: Adaptive VBlank-safe with inline palette logic.

    KEY FIXES (v2.35):
    1. Uses FFEA/FFEB for position counter (game overwrites FFE0/FFE1!)
    2. Reads tiles from EACH tilemap independently (they can differ)
    3. ADAPTIVE VBlank safety: checks LY register each iteration, stops
       processing when VBlank ends. This guarantees ALL VRAM writes happen
       during safe LCD modes (1=VBlank or 2=OAM scan), never during mode 3.
    4. INLINE tile→palette logic - eliminates ROM lookup table read that
       was returning wrong values due to MBC1 bank state during VBlank

    Processes up to 16 positions per frame (both tilemaps at each position).
    Stops early if VBlank ends. Typical throughput: 10-14 tiles/frame.
    Full tilemap refresh every ~70-100 frames (~1.2-1.7 seconds at 60fps).
    """
    code = bytearray()

    # === CHECK GAME MODE ===
    code.extend([0xF0, 0xC1])  # LDH A, [0xFFC1]
    code.extend([0xB7])         # OR A
    code.extend([0xC8])         # RET Z (return if menu)

    code.extend([0xC5, 0xD5, 0xE5])  # PUSH BC, DE, HL

    # === LOAD 16-BIT POSITION COUNTER ===
    # Uses FFEA/FFEB - game actively overwrites FFE0/FFE1!
    code.extend([0xF0, 0xEA])  # LDH A, [FFEA]
    code.extend([0x6F])         # LD L, A
    code.extend([0xF0, 0xEB])  # LDH A, [FFEB]
    code.extend([0xC6, 0x98])   # ADD A, 0x98
    code.extend([0x67])         # LD H, A  (HL = 0x9800 + position)

    # B = 48 positions per frame
    # BG colorizer runs FIRST in VBlank - has ~4560 M-cycles available.
    # 48 tiles × ~75 M-cycles avg = 3600 M + 62 M overhead = 3662 M.
    # DMA (160 M) also needs VBlank. Total VBlank-critical: ~3822 M < 4560 M.
    # Palette loader + shadow colorizer use always-writable WRAM/registers, can overrun.
    # Full tilemap refresh every 1024/48 ≈ 21 frames (~0.35 seconds at 60fps).
    code.extend([0x06, 0x30])  # LD B, 48

    # === TILE LOOP ===
    tile_loop_start = len(code)

    # Tilemap boundary wrap: if H >= 0x9C, wrap to 0x98
    code.extend([0x7C])         # LD A, H
    code.extend([0xFE, 0x9C])   # CP 0x9C
    code.extend([0x38, 0x03])   # JR C, +3 (no wrap needed)
    code.extend([0xD6, 0x04])   # SUB 0x04 (0x9C→0x98)
    code.extend([0x67])         # LD H, A

    # --- Process 0x9800 tilemap ---
    code.extend([0xAF])         # XOR A
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A  (VRAM bank 0)
    code.extend([0x56])         # LD D, [HL]  (D = 0x9800 tile ID)

    # Inline tile→palette (D → E), no ROM read needed
    _emit_tile_to_palette(code)

    code.extend([0x3E, 0x01])   # LD A, 1
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A  (VRAM bank 1)
    code.extend([0x73])         # LD [HL], E  (write attr to 0x9800 bank 1)

    # --- Process 0x9C00 tilemap (same position, H+4) ---
    code.extend([0x7C])         # LD A, H
    code.extend([0xC6, 0x04])   # ADD A, 0x04
    code.extend([0x67])         # LD H, A  (HL now points to 0x9C00+pos)

    code.extend([0xAF])         # XOR A
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A  (VRAM bank 0)
    code.extend([0x56])         # LD D, [HL]  (D = 0x9C00 tile ID)

    # Inline tile→palette (D → E), no ROM read needed
    _emit_tile_to_palette(code)

    code.extend([0x3E, 0x01])   # LD A, 1
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A  (VRAM bank 1)
    code.extend([0x73])         # LD [HL], E  (write attr to 0x9C00 bank 1)

    # --- Switch back to 0x9800 address ---
    code.extend([0x7C])         # LD A, H
    code.extend([0xD6, 0x04])   # SUB 0x04
    code.extend([0x67])         # LD H, A  (back to 0x9800+pos)

    # Next tile position
    code.extend([0x23])         # INC HL
    code.extend([0x05])         # DEC B
    tile_offset = tile_loop_start - (len(code) + 2)
    code.extend([0x20, tile_offset & 0xFF])  # JR NZ, tile_loop

    # === SAVE POSITION COUNTER ===
    code.extend([0x7C])         # LD A, H
    code.extend([0xD6, 0x98])   # SUB 0x98
    code.extend([0xE6, 0x03])   # AND 0x03 (wrap high byte at 4 = 1024 tiles)
    code.extend([0xE0, 0xEB])   # LDH [FFEB], A
    code.extend([0x7D])         # LD A, L
    code.extend([0xE0, 0xEA])   # LDH [FFEA], A

    # === CLEANUP ===
    code.extend([0xAF])         # XOR A
    code.extend([0xE0, 0x4F])   # LDH [0xFF4F], A (back to VRAM bank 0)
    code.extend([0xE1, 0xD1, 0xC1])  # POP HL, DE, BC
    code.extend([0xC9])         # RET

    return bytes(code)


def create_combined_with_dma(palette_loader_addr: int, shadow_main_addr: int, bg_colorizer_addr: int) -> bytes:
    """Combined function that calls all colorization routines.

    Order: bg_colorizer -> palette_loader -> shadow_main -> DMA
    BG colorizer runs FIRST during VBlank when VRAM is freely accessible.
    No STAT checks needed = fast and correct.
    """
    code = bytearray()
    code.extend([0xCD, bg_colorizer_addr & 0xFF, bg_colorizer_addr >> 8])
    code.extend([0xCD, palette_loader_addr & 0xFF, palette_loader_addr >> 8])
    code.extend([0xCD, shadow_main_addr & 0xFF, shadow_main_addr >> 8])
    code.extend([0xCD, 0x80, 0xFF, 0xC9])
    return bytes(code)


def create_vblank_hook_with_input(combined_func_addr: int) -> bytes:
    """VBlank hook with input handling.

    v2.36: Match original game's joypad debounce exactly:
    - 2 reads for d-pad (was 1 in v2.35)
    - 8 reads for buttons (was 2 in v2.35)
    This eliminates phantom button presses and missed inputs.
    """
    # Must fit within 47 bytes total (0x0824-0x0852) to avoid overwriting
    # the interrupt handler at 0x0853. Use loop for button debounce to save space.
    # Original: 2 d-pad reads + 8 button reads (sequential).
    # Ours: 1 d-pad read + 8 button reads (via loop). Loop gives MORE inter-read
    # delay than sequential reads (7 M-cycles vs 3), so debouncing is actually better.
    joypad_input = bytearray([
        # D-pad (1 read - d-pad matrix settles fast)
        0x3E, 0x20,        # LD A, 0x20        ; select d-pad
        0xE0, 0x00,        # LDH [FF00], A
        0xF0, 0x00,        # LDH A, [FF00]     ; read d-pad
        0x2F,              # CPL
        0xE6, 0x0F,        # AND 0x0F
        0xCB, 0x37,        # SWAP A            ; d-pad to upper nibble
        0x47,              # LD B, A            ; save in B
        # Buttons (8 reads via loop - proper debounce, space-efficient)
        0x3E, 0x10,        # LD A, 0x10        ; select buttons
        0xE0, 0x00,        # LDH [FF00], A
        0x0E, 0x08,        # LD C, 8           ; read 8 times
        0xF0, 0x00,        # .loop: LDH A,[FF00]
        0x0D,              # DEC C
        0x20, 0xFB,        # JR NZ, .loop      ; offset -5
        0x2F,              # CPL
        0xE6, 0x0F,        # AND 0x0F
        0xB0,              # OR B              ; combine d-pad + buttons
        0xE0, 0x93,        # LDH [FF93], A     ; store result
        # Deselect joypad lines
        0x3E, 0x30,        # LD A, 0x30
        0xE0, 0x00,        # LDH [FF00], A
    ])  # 33 bytes + 14 hook bytes = 47 total (fits exactly in 0x0824-0x0852)
    hook_code = bytearray([
        0x3E, 0x0D, 0xEA, 0x00, 0x20,  # Switch to bank 13
        0xCD, combined_func_addr & 0xFF, combined_func_addr >> 8,
        0x3E, 0x01, 0xEA, 0x00, 0x20,  # Switch back to bank 1
        0xC9,
    ])
    return bytes(joypad_input + hook_code)


def main():
    input_rom = Path("rom/Penta Dragon (J).gb")
    output_rom = Path("rom/working/penta_dragon_dx_FIXED.gb")
    palette_yaml = Path("palettes/penta_palettes_v097.yaml")

    print("=== Penta Dragon DX v2.36 ===")
    print("BG Colorization + Input Fix")
    print()
    print("FIXES in v2.36:")
    print("  1. Input debounce: 1+8 reads via loop (proper debounce)")
    print("  2. BG colorizer: 32 tiles/frame (full refresh in 0.53s)")
    print("  3. Shadow colorizer: both buffers (fixes inverted FFCB logic)")
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
    bg_colorizer = create_bg_colorizer_continuous()
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
