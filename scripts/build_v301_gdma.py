#!/usr/bin/env python3
"""Penta Dragon DX v3.01 — GDMA-based BG attr transfer.

Replaces v3.00's dual-STAT-wait inline hook with:
  1. Tile-only inline hook (single STAT wait, vanilla speed)
  2. VBlank attr computation: read tiles from C1A0, lookup bg_table,
     write a 256-byte attr buffer to WRAM bank 0 (CC80-CCFF)
  3. GDMA transfer: hardware DMA 256 bytes from WRAM bank 0 to
     VRAM tilemap VBK=1 every VBlank (~2048T)

All runtime WRAM code/data uses bank 0, which is accessible without FF70.
bg_sweep retained as safety net (mini-boss probe timing dependency).

Palette mapping (bg_table):
  - pal0 (floor/default):  floor, void, structure/transitions, hazards
  - pal1 (pickup accents): confirmed pickup bands + two captured 2x2 blocks
  - pal0 (font/reused art): interleaved 0x80-0xDF bands and 0xF0-0xFF
  - pal6 (walls):          0x14-0x1E, 0x25-0x26, 0x34-0x38, 0x41-0x49,
                           0x54-0x57, 0x59 (slate blue-gray)
  - pal7 overridden to pal0 colors (hides stale CGB boot-ROM attrs)
"""
import sys
from pathlib import Path
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from bg_experiment import (
    load_palettes_from_yaml, create_tile_based_colorizer,
    create_shadow_colorizer_main, create_palette_loader,
    create_tile_to_palette_subroutine,
)
from create_vblank_colorizer_v288 import create_conditional_palette_cached
from build_v296_phantomsafe import create_bg_sweep_viewport_gated


def _bg_table() -> bytes:
    """Compile the canonical Stage 1 tile-to-palette YAML table."""
    source = (
        Path(__file__).parent.parent
        / "palettes"
        / "bg_tile_categories.yaml"
    )
    data = yaml.safe_load(source.read_text())["bg_table"]
    size = int(data.get("size", 256))
    default = int(data.get("default_palette", 0))
    assert size == 256
    assert 0 <= default <= 7
    table = bytearray([default] * size)

    for category in data.get("categories", []):
        palette = int(category["palette"])
        assert 0 <= palette <= 7, category["name"]
        tile_ids = [int(tile) for tile in category.get("tiles", [])]
        for low, high in category.get("tile_ranges", []):
            low, high = int(low), int(high)
            assert 0 <= low <= high < size, category["name"]
            tile_ids.extend(range(low, high + 1))
        for tile in tile_ids:
            assert 0 <= tile < size, category["name"]
            table[tile] = palette

    return bytes(table)


BG_TABLE_BYTES = _bg_table()
WRAM_BG_TABLE = 0xCC00
WRAM_BG_TABLE_HI = (WRAM_BG_TABLE >> 8) & 0xFF
ATTR_BUFFER = 0xCC80  # WRAM bank 0 (dead-code attr buffer, kept consistent)


def create_inline_tile_copy_tileonly(arena_neutralize_d880=None,
                                      title_gate=None,
                                      window_gate=False,
                                      high_scene_tileonly=False,
                                      room_repair_flag_addr=None,
                                      room_repair_flag_value=0x12,
                                      clear_room_repair_flag=False,
                                      dungeon_attr_only=False,
                                      dungeon_lava_only=False,
                                      room_flag_as_scroll_x_cache=False,
                                      scroll_source_hash=False,
                                      compact_row_return=False,
                                      full_attr_rows=24,
                                      external_attr_decider_addr=None,
                                      external_attr_decision_hram=0xE0,
                                      external_stage7_attr_decider_addr=None,
                                      external_stage7_ready_addr=None,
                                      external_stage7_ready_value=0xA7) -> bytes:
    """Inline tile+attr copy with D880-gated attr writes.

    Per group: wait once for HBlank, write 2 tiles (VBK=0), then write their
    2 matching attrs (VBK=1) from WRAM_BG_TABLE in the same short DI window.
    Mode 0 plus the following mode 2 leaves enough VRAM-accessible time for
    both halves and avoids the old extra-scanline wait.

    Dispatch (when gates are set):
      1. D880 < title_gate          -> tile-only (title screen — avoids
         animation race between tile phase and attr phase)
      2. D880 < arena_neutralize    -> full tile+attr (dungeon — pickup
         items get immediate attrs, no palette flicker)
      3. D880 in [base, base+9), or every D880 >= base when
         high_scene_tileonly is set -> tile-only (arena/story position passes
         own the attr plane; tile-ID attrs would fight them)
      4. LCDC window enabled        -> tile-only (item-menu HUD attrs stay 0)
      5. pending room repair must match, when supplied; otherwise tile-only
      6. else                       -> full tile+attr (splash/banner;
         scene_detect loads all-pal0 table, attrs are harmless)

    Replaces 0x42A7..0x436D. H pre-set to 0x98 or 0x9C by entry point.
    24 rows x 6 groups x 4 tiles = 576 tiles.
    """
    code = bytearray()
    targets = {}
    assert 1 <= full_attr_rows <= 24

    def emit(opcodes):
        if isinstance(opcodes, (list, bytes, bytearray)):
            code.extend(opcodes)
        else:
            code.append(opcodes)

    def mark(name):
        targets[name] = len(code)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127
        emit([opcode, offset & 0xFF])

    def emit_jr_fwd(opcode):
        pos = len(code) + 1
        emit([opcode, 0x00])
        return pos

    def patch_jr_fwd(pos):
        offset = len(code) - (pos + 1)
        assert -128 <= offset <= 127
        code[pos] = offset & 0xFF

    def emit_jp_fwd(opcode):
        pos = len(code) + 1
        emit([opcode, 0x00, 0x00])
        return pos

    def patch_jp_fwd(pos):
        target = 0x42A7 + len(code)
        code[pos] = target & 0xFF
        code[pos + 1] = (target >> 8) & 0xFF

    # Setup (H pre-set by entry point to 0x98 or 0x9C)
    emit([0x2E, 0x00])               # LD L, 0x00
    emit([0x11, 0xA0, 0xC1])         # LD DE, 0xC1A0 (WRAM tile source)

    # ---- Dispatch: title gate + arena neutralize ----
    # Both gate the attr phase. When both are set:
    #   1. D880 < title_gate         -> tile-only (title screen)
    #   2. D880 < arena_neutralize   -> full tile+attr (dungeon)
    #   3. D880 in [base, base+9)    -> tile-only (arena)
    #   4. else                      -> full tile+attr (splash/banner)
    # When neither is set: simple full tile+attr copy everywhere.
    j_tileonly = None                # arena dispatch JR patch pos
    j_tileonly_title = None          # title gate JR patch pos
    j_tileonly_window = None         # item-window gate JR patch pos
    j_tileonly_room = None           # room-repair flag JR patch pos
    j_tileonly_external_scene = None # non-lava external dispatch JP patch
    j_full_external_stage1 = None    # Stage 1 atomic tile+attr path
    j_tileonly_resume = None         # lower tile-only rows after attr prefix

    if dungeon_attr_only:
        assert title_gate is None
        assert arena_neutralize_d880 is None
        if external_attr_decider_addr is not None:
            # A fixed-bank trampoline maps the release helper's ROM bank,
            # leaves its exact full-vs-tile-only decision in HRAM, and restores
            # bank 1 before returning here.  Keeping this dispatch to nine
            # bytes leaves both proven copy paths byte-for-byte unchanged.
            assert dungeon_lava_only
            assert room_repair_flag_addr is None
            assert not room_flag_as_scroll_x_cache
            assert not scroll_source_hash
            if external_stage7_attr_decider_addr is None:
                assert external_stage7_ready_addr is None
                emit([
                    0xCD,
                    external_attr_decider_addr & 0xFF,
                    (external_attr_decider_addr >> 8) & 0xFF,
                ])
            else:
                assert external_stage7_ready_addr is not None
                # Normalize from Stage 1. Its packed pickup maps need the full
                # atomic tile+attr path so a formerly-red cell cannot survive
                # beneath a newly copied floor/wall tile. Stage 5 uses the
                # bank-13 signature trampoline and Stage 7 the WRAM decider.
                emit([0xFA, 0x80, 0xD8, 0xD6, 0x02])
                j_full_external_stage1 = emit_jr_fwd(0x28)
                emit([0xD6, 0x04])
                j_stage5 = emit_jr_fwd(0x28)
                emit([0xFE, 0x02])
                j_tileonly_external_scene = emit_jp_fwd(0xC2)
                # The title VBlank path initializes this WRAM service before
                # gameplay can enter a lava scene.
                emit([
                    0xCD,
                    external_stage7_attr_decider_addr & 0xFF,
                    (external_stage7_attr_decider_addr >> 8) & 0xFF,
                ])
                j_decision = emit_jr_fwd(0x18)
                patch_jr_fwd(j_stage5)
                emit([
                    0xCD,
                    external_attr_decider_addr & 0xFF,
                    (external_attr_decider_addr >> 8) & 0xFF,
                ])
                patch_jr_fwd(j_decision)
            emit([
                0xF0,
                external_attr_decision_hram & 0xFF,
                0xB7,
            ])
            j_tileonly = emit_jp_fwd(0xCA)  # JP Z,tileonly
        elif dungeon_lava_only:
            # Only the two lava scenes need an atomic tile+attribute copy on
            # every camera update. For D880 $06/$08, (A-$06)&$FD is zero.
            # All other dungeon scenes use the bounded VBlank row repair.
            emit([0xFA, 0x80, 0xD8, 0xD6, 0x06, 0xE6, 0xFD])
            j_tileonly = emit_jp_fwd(0xC2)  # JP NZ,tileonly
        else:
            # One normalized range test replaces separate title and high-scene
            # gates: only D880 $02..$0B may enter the attribute path.
            emit([0xFA, 0x80, 0xD8, 0xD6, 0x02, 0xFE, 0x0A])
            j_tileonly = emit_jp_fwd(0xD2)  # JP NC,tileonly

    # 1. Title gate: D880 < title_gate -> tile-only
    if title_gate is not None:
        emit([0xFA, 0x80, 0xD8])     # LD A, [D880]
        emit([0xFE, title_gate & 0xFF])  # CP title_gate
        # The full attr path is close to the JR range limit; use an absolute
        # conditional jump so optional dispatch gates cannot break the build.
        j_tileonly_title = emit_jp_fwd(0xDA)  # JP C, tileonly

    # 2. Arena neutralize: D880 in [base, base+9) -> tile-only
    if arena_neutralize_d880 is not None:
        emit([0xFA, 0x80, 0xD8])     # LD A, [D880]
        if high_scene_tileonly:
            emit([0xFE, arena_neutralize_d880 & 0xFF])  # CP base
            # D880 >= base includes arenas and the neutral-table story/splash
            # family. Their dedicated VBlank position passes own attributes.
            j_tileonly = emit_jp_fwd(0xD2)  # JP NC,tileonly
        else:
            emit([0xD6, arena_neutralize_d880 & 0xFF])  # SUB base
            j_full = emit_jr_fwd(0x38)   # JR C, full
            emit([0xFE, 0x09])           # CP 9
            j_tileonly = emit_jr_fwd(0x38)  # JR C,tileonly (arena)
            patch_jr_fwd(j_full)         # else fall through to full

    # Hardware-window tile writes are item-menu HUD text, not dungeon tiles.
    # Its attribute rows are cleared by the VBlank prelude and must stay pal0.
    # Keep this last in the dispatch so its short branch reaches tile-only.
    if window_gate:
        emit([0xF0, 0x40])           # LDH A, [LCDC]
        emit([0xE6, 0x20])           # AND window-enable
        j_tileonly_window = emit_jr_fwd(0x20)  # JR NZ, tileonly

    # A full tile+attribute copy is expensive enough to distort the steady
    # gameplay loop.  Release builders can restrict it to the exact native
    # room-change frame; the lightweight VBlank sweep then owns the remaining
    # off-screen columns while ordinary frames stay on the tile-only path.
    if room_repair_flag_addr is not None:
        if room_flag_as_scroll_x_cache:
            if scroll_source_hash:
                # The byte holds either the odd table-ready marker or an even
                # source/camera signature. Include the early packed-buffer
                # mutation plus SCX/SCY so every camera change commits the
                # matching attribute plane. Forcing bit 0 clear keeps the ready
                # marker unambiguously different.
                assert room_repair_flag_value & 1
                emit([
                    0xF0, 0x43, 0x47,           # B = SCX
                    0xF0, 0x42, 0xA8,            # A = SCX XOR SCY
                    0x4F,                        # C = camera key
                    0xFA, 0xA4, 0xC1,           # LD A,[packed source + 4]
                    0xA9, 0xE6, 0xFE, 0x47,     # B = even combined signature
                    0xFA,
                    room_repair_flag_addr & 0xFF,
                    (room_repair_flag_addr >> 8) & 0xFF,
                    0xB8,
                ])
                j_tileonly_room = emit_jp_fwd(0xCA)  # JP Z,tileonly
                emit([
                    0x78,
                    0xEA,
                    room_repair_flag_addr & 0xFF,
                    (room_repair_flag_addr >> 8) & 0xFF,
                ])
            else:
                # Legacy one-byte raw-SCX cache with an explicit ready marker.
                emit([0xF0, 0x43, 0x47])       # B=current SCX
                emit([
                    0xFA,
                    room_repair_flag_addr & 0xFF,
                    (room_repair_flag_addr >> 8) & 0xFF,
                    0xFE,
                    room_repair_flag_value & 0xFF,
                ])
                j_room_ready = emit_jr_fwd(0x28)
                emit([0xB8])
                j_tileonly_room = emit_jp_fwd(0xCA)
                patch_jr_fwd(j_room_ready)
                emit([
                    0x78,
                    0xEA,
                    room_repair_flag_addr & 0xFF,
                    (room_repair_flag_addr >> 8) & 0xFF,
                ])
        else:
            emit([
                0xFA,
                room_repair_flag_addr & 0xFF,
                (room_repair_flag_addr >> 8) & 0xFF,
                0xFE,
                room_repair_flag_value & 0xFF,
            ])
            j_tileonly_room = emit_jp_fwd(0xC2)  # JP NZ,tileonly

    if clear_room_repair_flag:
        assert room_repair_flag_addr is not None
        assert not room_flag_as_scroll_x_cache
        emit([
            0xAF,
            0xEA,
            room_repair_flag_addr & 0xFF,
            (room_repair_flag_addr >> 8) & 0xFF,
        ])

    if j_full_external_stage1 is not None:
        patch_jr_fwd(j_full_external_stage1)
    emit([0x3E, 0x18])               # LD A, 24
    emit([0xF5])                     # PUSH AF (row counter on stack)

    mark('row_loop')
    emit([0x3E, 0x0C])               # A = 12 groups x 2 tiles = 24

    mark('group_loop')
    # Keep the group counter below the row counter on the stack. This moves
    # its save before the HBlank wait and leaves BC free for table lookup,
    # removing sixteen cycles from the VRAM-accessible critical window.
    emit([0xF5])                     # PUSH AF (group counter)
    # -------- TILE PHASE: VBK=0 (default), 2 tile writes --------
    emit([0xF3])                     # DI
    mark('stat3a')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit([0xFE, 0x03])               # CP 3
    emit_jr_back(0x20, 'stat3a')     # JR NZ, stat3a
    mark('stat0a')
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit_jr_back(0x20, 'stat0a')     # JR NZ, stat0a
    emit([0xD5])                     # preserve source-group start
    for _ in range(2):
        emit([0x1A, 0x13, 0x22])     # LD A,[DE]; INC DE; LD [HL+],A

    # -------- TRANSITION: restore E/D, rewind L by 2; VBK=1 --------
    # Row starts and two-tile groups guarantee L never wrapped within this
    # group, so two DEC L instructions replace the carry-aware subtraction.
    # Restoring DE from the stack is both shorter and faster than equivalent
    # low-byte arithmetic with a possible D borrow.
    emit([0xD1])                     # DE = source-group start
    emit([0x2D, 0x2D])               # L -= 2
    emit([0x06, WRAM_BG_TABLE_HI])   # LD B, 0xCC (bg_table_hi in WRAM)
    emit([0x3E, 0x01])               # LD A, 1
    emit([0xE0, 0x4F])               # LDH [FF4F], A (VBK=1 attr bank)

    # -------- ATTR PHASE: same HBlank, 2 WRAM-table lookups --------
    # 2 attr writes: LD A,[DE]; INC DE; LD C,A; LD A,[BC]; LD [HL+],A
    for _ in range(2):
        emit([0x1A, 0x13, 0x4F, 0x0A, 0x22])
    emit([0xFB])                     # EI

    # -------- POST-ATTR: VBK=0 --------
    emit([0xAF])                     # XOR A
    emit([0xE0, 0x4F])               # LDH [FF4F], A (VBK=0)

    # Group counter
    emit([0xF1, 0x3D])               # POP AF; DEC A
    emit_jr_back(0x20, 'group_loop') # JR NZ, group_loop

    # Row end: HL += 8
    emit([0x7D])                     # LD A, L
    emit([0xC6, 0x08])               # ADD 8
    emit([0x6F])                     # LD L, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x24])                     # INC H

    # Row counter
    emit([0xF1, 0x3D])               # POP AF; DEC A
    if compact_row_return:
        emit([0xC8])                 # RET Z
        if full_attr_rows < 24:
            emit([0xFE, 24 - full_attr_rows])
            j_tileonly_resume = emit_jp_fwd(0xCA)
        emit([0xF5])                 # PUSH AF
        offset = targets['row_loop'] - (len(code) + 2)
        if -128 <= offset <= 127:
            emit([0x18, offset & 0xFF])
        else:
            target_addr = 0x42A7 + targets['row_loop']
            emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])
    else:
        j_done = emit_jr_fwd(0x28)   # JR Z, done
        emit([0xF5])                 # PUSH AF
        offset = targets['row_loop'] - (len(code) + 2)
        if -128 <= offset <= 127:
            emit([0x18, offset & 0xFF])
        else:
            target_addr = 0x42A7 + targets['row_loop']
            emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])
        patch_jr_fwd(j_done)
        emit([0xC9])                 # RET (full tile+attr path)

    # ---- TILE-ONLY PATH: copy tiles, write NO attrs ----
    # Both title gate and arena dispatch jump here (at j_tileonly or
    # j_tileonly_title). Same L/E/HL advancement as full path.
    if (j_tileonly is not None or j_tileonly_title is not None
            or j_tileonly_window is not None
            or j_tileonly_room is not None
            or j_tileonly_external_scene is not None):
        if j_tileonly is not None:
            if high_scene_tileonly or dungeon_attr_only:
                patch_jp_fwd(j_tileonly)
            else:
                patch_jr_fwd(j_tileonly)
        if j_tileonly_title is not None:
            patch_jp_fwd(j_tileonly_title)
        if j_tileonly_window is not None:
            patch_jr_fwd(j_tileonly_window)
        if j_tileonly_room is not None:
            patch_jp_fwd(j_tileonly_room)
        if j_tileonly_external_scene is not None:
            patch_jp_fwd(j_tileonly_external_scene)
        emit([0x3E, 0x18])           # LD A, 24
        if j_tileonly_resume is not None:
            patch_jp_fwd(j_tileonly_resume)
        emit([0xF5])                 # PUSH AF
        mark('to_row')
        emit([0x0E, 0x06])           # LD C, 6
        mark('to_group')
        emit([0xF3])                 # DI
        mark('to_s3')
        emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])  # LDH A,[FF41];AND 3;CP 3
        emit_jr_back(0x20, 'to_s3')                   # JR NZ, to_s3
        mark('to_s0')
        emit([0xF0, 0x41, 0xE6, 0x03])               # LDH A,[FF41];AND 3
        emit_jr_back(0x20, 'to_s0')                   # JR NZ, to_s0
        for _ in range(4):
            emit([0x1A, 0x13, 0x22])  # LD A,[DE]; INC DE; LD [HL+],A
        emit([0xFB])                 # EI
        emit([0x0D])                 # DEC C
        emit_jr_back(0x20, 'to_group')
        # row end: HL += 8 (24 written + 8 skip = 32 stride)
        emit([0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24])
        emit([0xF1, 0x3D])           # POP AF; DEC A
        if compact_row_return:
            emit([0xC8])             # RET Z
            emit([0xF5])             # PUSH AF
            offset = targets['to_row'] - (len(code) + 2)
            if -128 <= offset <= 127:
                emit([0x18, offset & 0xFF])
            else:
                target_addr = 0x42A7 + targets['to_row']
                emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])
        else:
            j_to_done = emit_jr_fwd(0x28)  # JR Z, done
            emit([0xF5])             # PUSH AF
            offset = targets['to_row'] - (len(code) + 2)
            if -128 <= offset <= 127:
                emit([0x18, offset & 0xFF])
            else:
                target_addr = 0x42A7 + targets['to_row']
                emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])
            patch_jr_fwd(j_to_done)
            emit([0xC9])             # RET

    return bytes(code)


def create_inline_tile_copy_pure_tileonly(
    tail_helper_addr=None,
    tail_helper_ready_addr=None,
    tail_helper_ready_value=0xA7,
) -> bytes:
    """PURE tile-only inline hook: copies tiles ONLY, no attr writes.

    Single STAT wait. ~vanilla speed. No VBK=1 writes, no bg_table lookup.
    Attrs are handled by bg_sweep + position sweep in the VBlank handler.

    Replaces 0x42A7..0x436D. H pre-set to 0x98 or 0x9C by entry point.
    24 rows x 6 groups x 4 tiles = 576 tiles.
    Same L/E/HL advancement as the tile phase of the full version.
    """
    code = bytearray()
    targets = {}

    def emit(opcodes):
        if isinstance(opcodes, (list, bytes, bytearray)):
            code.extend(opcodes)
        else:
            code.append(opcodes)

    def mark(name):
        targets[name] = len(code)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127
        emit([opcode, offset & 0xFF])

    def emit_jr_fwd(opcode):
        pos = len(code) + 1
        emit([opcode, 0x00])
        return pos

    def patch_jr_fwd(pos):
        offset = len(code) - (pos + 1)
        assert -128 <= offset <= 127
        code[pos] = offset & 0xFF

    # A release-only tail helper can repair the attribute plane after selected
    # room/scroll commits. Preserve the caller's map-base H for that helper;
    # the stock/pure path otherwise intentionally clobbers HL.
    if tail_helper_addr is not None:
        emit([0xE5])                     # PUSH HL
    else:
        assert tail_helper_ready_addr is None

    # Setup (H pre-set by entry point to 0x98 or 0x9C)
    emit([0x2E, 0x00])               # LD L, 0x00
    emit([0x11, 0xA0, 0xC1])         # LD DE, 0xC1A0 (WRAM tile source)

    # Row counter
    emit([0x3E, 0x18])               # LD A, 24
    emit([0xF5])                     # PUSH AF

    mark("row_loop")
    emit([0x0E, 0x06])               # LD C, 6 (groups per row)

    mark("group_loop")
    # STAT wait (MODE 3 then 0 - single phase)
    emit([0xF3])                     # DI
    mark("stat3")
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit([0xFE, 0x03])               # CP 3
    emit_jr_back(0x20, "stat3")      # JR NZ, stat3
    mark("stat0")
    emit([0xF0, 0x41])               # LDH A,[FF41]
    emit([0xE6, 0x03])               # AND 3
    emit_jr_back(0x20, "stat0")      # JR NZ, stat0
    # 4 tile writes
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])     # LD A,[DE]; INC DE; LD [HL+],A
    emit([0xFB])                     # EI

    # Group counter
    emit([0x0D])                     # DEC C
    emit_jr_back(0x20, "group_loop") # JR NZ, group_loop

    # Row end: HL += 8
    emit([0x7D])                     # LD A, L
    emit([0xC6, 0x08])               # ADD 8
    emit([0x6F])                     # LD L, A
    emit([0x30, 0x01])               # JR NC, +1
    emit([0x24])                     # INC H

    # Row counter
    emit([0xF1])                     # POP AF
    emit([0x3D])                     # DEC A
    j_done = emit_jr_fwd(0x28)       # JR Z, done
    emit([0xF5])                     # PUSH AF
    offset = targets["row_loop"] - (len(code) + 2)
    if -128 <= offset <= 127:
        emit([0x18, offset & 0xFF])
    else:
        target_addr = 0x42A7 + targets["row_loop"]
        emit([0xC3, target_addr & 0xFF, (target_addr >> 8) & 0xFF])

    patch_jr_fwd(j_done)
    if tail_helper_addr is None:
        emit([0xC9])                 # RET
    else:
        emit([0xE1])                 # restore caller's map-base H
        if tail_helper_ready_addr is not None:
            emit([
                0xFA,
                tail_helper_ready_addr & 0xFF,
                (tail_helper_ready_addr >> 8) & 0xFF,
                0xFE,
                tail_helper_ready_value & 0xFF,
                0xC0,                # RET NZ until the WRAM helper is copied
            ])
        emit([
            0xC3,
            tail_helper_addr & 0xFF,
            (tail_helper_addr >> 8) & 0xFF,
        ])                           # tail-call selective attr repair
    return bytes(code)


def create_inline_tile_copy_stage1_precomputed_attrs(
    external_decision_helper_addr: int | None = None,
    external_atomic_setup_addr: int | None = None,
    external_atomic_wrap_addr: int | None = None,
    atomic_group_width: int = 4,
) -> bytes:
    """Atomic Stage 1 attrs with precomputed HBlank-sized tile groups.

    The older atomic copier looked up each tile's palette while the LCD was
    already in its short VRAM-accessible interval.  It therefore had to halve
    the group width to two tiles and made Stage 1 roughly 20% slower.

    This variant performs three or four WRAM LUT lookups *before* waiting for
    HBlank, pushes the resulting attributes, then commits each tile group and
    its matching attributes in the same mode-0/mode-2 interval.  A
    departing pickup is therefore neutralized before its replacement floor
    tile can be rendered. Four-wide matches the stock tile-only cadence;
    three-wide reserves extra PPU margin for vertically scrolling pickup rows.

    With no external helper, only D880=$02 uses the atomic path. When a fixed,
    always-mapped decision helper is supplied, it owns the Stage 1 cache and
    the exact Stage 5/7 lava-signature decision and returns NZ only for a map
    that needs this atomic commit.
    """
    code = bytearray()
    targets = {}

    def emit(opcodes):
        if isinstance(opcodes, (list, bytes, bytearray)):
            code.extend(opcodes)
        else:
            code.append(opcodes)

    def mark(name):
        targets[name] = len(code)

    def emit_jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127
        emit([opcode, offset & 0xFF])

    def emit_jr_fwd(opcode):
        pos = len(code) + 1
        emit([opcode, 0x00])
        return pos

    def patch_jr_fwd(pos):
        offset = len(code) - (pos + 1)
        assert -128 <= offset <= 127
        code[pos] = offset & 0xFF

    def emit_jp_fwd(opcode):
        pos = len(code) + 1
        emit([opcode, 0x00, 0x00])
        return pos

    def patch_jp_fwd(pos):
        target = 0x42A7 + len(code)
        code[pos] = target & 0xFF
        code[pos + 1] = (target >> 8) & 0xFF

    assert atomic_group_width in (3, 4)
    assert 24 % atomic_group_width == 0

    # H is the caller-selected $98/$9C map base.
    emit([0x2E, 0x00])                     # LD L,$00
    if external_decision_helper_addr is None:
        assert external_atomic_setup_addr is None
        assert external_atomic_wrap_addr is None
        emit([0x11, 0xA0, 0xC1])           # DE = packed 24x24 source
        # Stage 1 owns the YAML tile attributes. All other scenes keep the
        # exact stock-speed, tile-only behavior.
        emit([0xFA, 0x80, 0xD8, 0xFE, 0x02])
        j_tileonly = emit_jp_fwd(0xC2)      # JP NZ,tileonly
    else:
        assert external_atomic_setup_addr is not None
        assert external_atomic_wrap_addr is not None
        # The fixed helper reloads the scene after its readiness check and
        # borrows E for Stage 1's destination-specific cache lookup. D=$DF
        # selects the proven metadata page and is replaced by the packed source
        # pointer immediately after the decision.
        emit([
            # The WRAM helper reloads D880 after checking its sentinel. Keep
            # the established 16T setup cadence without a redundant 3-byte
            # load; 16-bit INC/DEC preserve both BC and flags.
            0x03, 0x0B,
            0x16, 0xDF,
            0xCD,
            external_decision_helper_addr & 0xFF,
            external_decision_helper_addr >> 8,
        ])
        mark("common_setup")
        emit([0x11, 0xA0, 0xC1])
        j_tileonly = emit_jr_fwd(0x28)      # Z -> stock tile-only path
        emit([
            0x2E, 0x80,                     # dirty path begins at row 4
            0xCD,
            external_atomic_setup_addr & 0xFF,
            external_atomic_setup_addr >> 8,
        ])
    if external_decision_helper_addr is None:
        emit([0x06, 0x18])                  # B = 24 rows

    mark("atomic_row")
    emit([0x0E, 24 // atomic_group_width])

    mark("atomic_group")
    # Save the group counter, then stage the tile IDs in the statically idle
    # DF30..DF33 gap. Do not borrow ostensibly-unused HRAM here: the stock game
    # accesses several such bytes indirectly, which a rejected prototype
    # proved by suppressing Sara and scrolling despite a clean opcode census.
    tile_scratch = (0xDF30, 0xDF31, 0xDF32, 0xDF33)[:atomic_group_width]
    emit([
        0xC5,                               # PUSH BC
        0xE5,                               # preserve destination HL
        0x21, tile_scratch[0] & 0xFF, tile_scratch[0] >> 8,
    ])
    for _ in tile_scratch:
        emit([0x1A, 0x13, 0x22])            # source -> scratch; advance both
    emit([
        0xE1,                               # restore destination HL
        0xD5,                               # save advanced source DE
        0x11, tile_scratch[0] & 0xFF, tile_scratch[0] >> 8,
        0x06, WRAM_BG_TABLE_HI,              # DE=scratch; B=$CC
    ])
    for index, _ in enumerate(tile_scratch):
        emit([0x1A])                        # tile=[DE]
        if index + 1 < len(tile_scratch):
            emit([0x13])                    # final scratch pointer is dead
        emit([
            0x4F, 0x0A, 0xF5,               # C=tile; PUSH table[tile]
        ])
    if atomic_group_width == 3:
        # Put the trailing attrs in registers and leave attr 1 on the stack.
        emit([
            0xF1, 0x5F,                     # E = attr 3
            0xF1, 0x4F,                     # C = attr 2
        ])
        # BC's outer values are already on the stack and D is not an attr
        # register in the three-wide path. Hoist tiles 2/3 into B/D so only
        # tile 1 needs a 16T absolute read after mode 0 begins.
        emit([
            0xFA, tile_scratch[1] & 0xFF, tile_scratch[1] >> 8, 0x47,
            0xFA, tile_scratch[2] & 0xFF, tile_scratch[2] >> 8, 0x57,
        ])

    # One wait per four tiles, matching the pure/stock cadence.
    emit([0xF3])                            # DI
    mark("atomic_stat3")
    emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])
    emit_jr_back(0x20, "atomic_stat3")
    mark("atomic_stat0")
    emit([0xF0, 0x41, 0xE6, 0x03])
    emit_jr_back(0x20, "atomic_stat0")

    # Tile IDs first in VBK0 even though DE currently holds attrs 3/4.
    if atomic_group_width == 3:
        emit([
            0xFA, tile_scratch[0] & 0xFF, tile_scratch[0] >> 8, 0x22,
            0x78, 0x22,                     # tile 2 from B
            0x7A, 0x22,                     # tile 3 from D
        ])
    else:
        for address in tile_scratch[:-1]:
            emit([0xFA, address & 0xFF, address >> 8, 0x22])
        # DE still points at tile 4 because the attrs remain stacked.
        emit([0x1A, 0x22])

    # Then matching attrs in VBK1.
    emit([0x3E, 0x01, 0xE0, 0x4F])
    if atomic_group_width == 4:
        # Store attr 4 first so a departing pickup is neutralized before its
        # replacement floor reaches the PPU, then walk backward to attr 1.
        emit([0x2D])                         # DEC L -> tile 4 destination
        for _ in range(3):
            emit([0xF1, 0x32])              # attrs 4/3/2
        emit([0xF1, 0x77])                   # attr 1 at group start
        emit([0x7D, 0xC6, 0x04, 0x6F])      # restore group-end HL
    else:
        emit([0x7D, 0xD6, atomic_group_width, 0x6F])
        emit([0xF1, 0x22])                  # attr 1
        for register in (0x79, 0x7B):
            emit([register, 0x22])           # attrs 2/3
    emit([0xAF, 0xE0, 0x4F])                # restore VBK0
    emit([
        0xD1,                               # restore advanced DE
        0xFB, 0xC1, 0x0D,                   # EI; POP BC; DEC C
    ])
    emit_jr_back(0x20, "atomic_group")

    # Destination rows are 32 bytes while packed source rows are 24.
    emit([
        0x7D, 0xC6, 0x08, 0x6F,             # L += 8
        0x30, 0x01, 0x24,                   # carry -> INC H
        0x05,                               # DEC B
    ])
    if external_atomic_wrap_addr is None:
        emit([0xC8])                         # final atomic row -> RET Z
        emit_jr_back(0x18, "atomic_row")
    else:
        emit_jr_back(0x20, "atomic_row")
        emit([
            0xC3,
            external_atomic_wrap_addr & 0xFF,
            external_atomic_wrap_addr >> 8,
        ])

    # Pure tile-only path for every non-Stage-1 caller.
    if external_decision_helper_addr is None:
        patch_jp_fwd(j_tileonly)
    else:
        patch_jr_fwd(j_tileonly)
    mark("pure_setup")
    emit([0x3E, 0x18, 0xF5])               # stock-timed 24-row counter

    mark("pure_row")
    emit([0x0E, 0x06])
    mark("pure_group")
    emit([0xF3])
    mark("pure_stat3")
    emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])
    emit_jr_back(0x20, "pure_stat3")
    mark("pure_stat0")
    emit([0xF0, 0x41, 0xE6, 0x03])
    emit_jr_back(0x20, "pure_stat0")
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])
    emit([0xFB, 0x0D])
    emit_jr_back(0x20, "pure_group")
    emit([
        0x7D, 0xC6, 0x08, 0x6F,
        0x30, 0x01, 0x24,
        0xF1, 0x3D,                         # POP AF; DEC row count
    ])
    j_pure_done = emit_jr_fwd(0x28)
    emit([0xF5])
    emit_jr_back(0x18, "pure_row")
    patch_jr_fwd(j_pure_done)
    emit([0xC9])

    if external_decision_helper_addr is not None:
        # Stock RST $30 enters here for title-family $9800 copies. XOR A,
        # LD L,A, the 28T title helper, and the final JP exactly replace the
        # old title setup and decision cadence. Gameplay enters three bytes
        # after the title-only helper and does not pay an unconditional jump.
        mark("title_pure_entry")
        emit([
            0x26, 0x98,
            0xAF,                           # A=0, Z; exact 4T title delay
            0x6F,                           # L=0; exact 4T title delay
            0xCD,
            (external_decision_helper_addr - 3) & 0xFF,
            (external_decision_helper_addr - 3) >> 8,
        ])
        common_setup_addr = 0x42A7 + targets["common_setup"]
        emit([
            0xC3, common_setup_addr & 0xFF, common_setup_addr >> 8,
        ])

    return bytes(code)


def create_inline_tile_copy_row_precomputed_attrs(
    external_decision_helper_addr: int,
) -> bytes:
    """Atomic four-tile copy with one bounded precompute per 24-tile row.

    The register-staged path performs four LUT lookups between every pair of
    HBlanks. Stage 7 changes layouts frequently enough for that work to miss
    scanline opportunities even though its critical section is safe. This
    variant computes a row's 24 attributes in reverse order on the stack
    during one ~2K-T DI window, then pops them forward across six stock-width
    groups. The critical tile+attribute commit remains four tiles wide, while
    the five later groups no longer repeat LUT/setup work between HBlanks.

    The fixed decision helper returns NZ only for a changed localized map.
    FFE0 is free after that decision and serves as the bounded 24-cell counter.
    """
    code = bytearray()
    targets = {}

    def emit(values):
        code.extend(values)

    def mark(name):
        targets[name] = len(code)

    def jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127
        emit([opcode, offset & 0xFF])

    def jp_back(opcode, name):
        address = 0x42A7 + targets[name]
        emit([opcode, address & 0xFF, address >> 8])

    def jp_fwd(opcode):
        position = len(code) + 1
        emit([opcode, 0, 0])
        return position

    def patch_jp(position):
        address = 0x42A7 + len(code)
        code[position] = address & 0xFF
        code[position + 1] = address >> 8

    # H is the caller-selected $98/$9C map base. The helper borrows DE/C, so
    # initialize the packed source only after its decision flags are final.
    emit([
        0x2E, 0x00,
        0xFA, 0x80, 0xD8,
        0xCD,
        external_decision_helper_addr & 0xFF,
        external_decision_helper_addr >> 8,
        0x11, 0xA0, 0xC1,
    ])
    j_tileonly = jp_fwd(0xCA)               # JP Z,pure

    mark("atomic_row")
    # Move DE to the row end, then walk backward so attr 0 is last pushed and
    # therefore first popped. DE returns to the row start before EI.
    emit([
        0xF3,                               # bounded row-precompute DI
        0x7B, 0xC6, 0x18, 0x5F,
        0x30, 0x01, 0x14,                   # carry -> INC D
        0x06, WRAM_BG_TABLE_HI,
        0x3E, 0x18, 0xE0, 0xE0,
    ])
    mark("precompute_cell")
    emit([
        0x1B, 0x1A, 0x4F, 0x0A, 0xF5,
        0xF0, 0xE0, 0x3D, 0xE0, 0xE0,
    ])
    jr_back(0x20, "precompute_cell")
    emit([
        0xFB, 0x3E, 0x06, 0xE0, 0xE0,
    ])                                      # EI gap; six groups in FFE0

    mark("atomic_group")
    # Stage tile IDs while DE advances normally. Attrs 0/1 move into B/C;
    # attrs 2/3 stay on the stack. This keeps DE intact and adds only two POPs
    # to the proven register-staged critical section (well below stack4).
    tile_scratch = (0xDF30, 0xDF31, 0xDF32, 0xDF33)
    for address in tile_scratch:
        emit([
            0x1A, 0x13,
            0xEA, address & 0xFF, address >> 8,
        ])
    emit([0xF1, 0x47, 0xF1, 0x4F])          # attrs 0/1 -> B/C
    emit([0xF3])
    mark("atomic_stat3")
    emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])
    jr_back(0x20, "atomic_stat3")
    mark("atomic_stat0")
    emit([0xF0, 0x41, 0xE6, 0x03])
    jr_back(0x20, "atomic_stat0")
    for address in tile_scratch:
        emit([0xFA, address & 0xFF, address >> 8, 0x22])
    emit([
        0x3E, 0x01, 0xE0, 0x4F,
        0x7D, 0xD6, 0x04, 0x6F,            # rewind destination by four
        0x78, 0x22, 0x79, 0x22,            # attrs 0/1 from B/C
        0xF1, 0x22, 0xF1, 0x22,            # attrs 2/3 from stack
        0xAF, 0xE0, 0x4F, 0xFB,
        0xF0, 0xE0, 0x3D, 0xE0, 0xE0,
    ])
    jr_back(0x20, "atomic_group")

    # Destination rows are 32 bytes while packed source rows are 24.
    emit([
        0x7D, 0xC6, 0x08, 0x6F,
        0x30, 0x01, 0x24,
        0x7A, 0xFE, 0xC3,
    ])
    jp_back(0xC2, "atomic_row")
    emit([0x7B, 0xFE, 0xE0])
    jp_back(0xC2, "atomic_row")
    emit([0xC9])

    # Pure stock-width path for cache hits and neutral scenes.
    patch_jp(j_tileonly)
    emit([0x3E, 0x18, 0xF5])
    mark("pure_row")
    emit([0x0E, 0x06])
    mark("pure_group")
    emit([0xF3])
    mark("pure_stat3")
    emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])
    jr_back(0x20, "pure_stat3")
    mark("pure_stat0")
    emit([0xF0, 0x41, 0xE6, 0x03])
    jr_back(0x20, "pure_stat0")
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])
    emit([0xFB, 0x0D])
    jr_back(0x20, "pure_group")
    emit([
        0x7D, 0xC6, 0x08, 0x6F,
        0x30, 0x01, 0x24,
        0xF1, 0x3D,
        0xC8, 0xF5,
    ])
    jr_back(0x18, "pure_row")
    return bytes(code)


def create_inline_tile_copy_stage1_cached_atomic(
    cache_9800: int = 0xDF53,
    cache_9c00: int = 0xDF54,
    external_lava_dispatch_addr: int | None = None,
    external_dispatch_ready_addr: int | None = None,
    external_dispatch_ready_value: int = 0xA7,
    atomic_group_width: int = 3,
) -> bytes:
    """Run the atomic path when a localized map changes.

    The stock engine invokes the 24x24 copier far more often than it changes
    the packed layout.  Across the continuous-right and alternating-patrol
    traces, the tuple ``(destination map, DC00)`` covered every Stage 1 pickup
    attribute-map change.  DC00 advances in four-unit camera phases, so bit 0
    is available as a valid marker; zeroed cache bytes cannot alias a live key.

    Each destination tilemap has an independent cache in two DX-owned Stage 5
    metadata bytes that are dormant while D880=$02. A changed key takes the
    precomputed atomic route; an unchanged key takes the pure
    four-tiles-per-HBlank route. The default three-wide critical section is
    conservative. Receipt-gated builds may select four-wide after proving the
    final matching attribute store across sprite-heavy patrol frames.

    When ``external_lava_dispatch_addr`` is supplied, every non-Stage-1 copy
    asks that always-mapped WRAM dispatcher whether its current Stage 5/7
    layout needs the same atomic tile+attribute commit. The dispatcher returns
    Z for the normal pure path and NZ for a changed lava layout, so this costs
    no ROM-bank switch in neutral stages and preserves their stock cadence.
    A supplied ready address gates the WRAM call for old/incompatible save
    states whose helper page has not yet been initialized.
    """
    code = bytearray()
    targets = {}

    def emit(values):
        code.extend(values)

    def mark(name):
        targets[name] = len(code)

    def jr_back(opcode, name):
        offset = targets[name] - (len(code) + 2)
        assert -128 <= offset <= 127
        emit([opcode, offset & 0xFF])

    def jr_fwd(opcode):
        position = len(code) + 1
        emit([opcode, 0])
        return position

    def patch_jr(position):
        offset = len(code) - (position + 1)
        assert -128 <= offset <= 127
        code[position] = offset & 0xFF

    def jp_fwd(opcode):
        position = len(code) + 1
        emit([opcode, 0, 0])
        return position

    def patch_jp(position):
        address = 0x42A7 + len(code)
        code[position] = address & 0xFF
        code[position + 1] = address >> 8

    assert cache_9c00 == cache_9800 + 1
    assert cache_9800 & 0xFF != 0xFF
    assert atomic_group_width in (3, 4)
    assert 24 % atomic_group_width == 0

    # Common tilemap/source setup. H is the caller-selected $98/$9C map.
    emit([0x2E, 0x00, 0x11, 0xA0, 0xC1])
    emit([0xFA, 0x80, 0xD8, 0xFE, 0x02])     # D880 == Stage 1?
    if external_lava_dispatch_addr is None:
        assert external_dispatch_ready_addr is None
        j_nonstage_pure = jr_fwd(0x20)
        j_dispatch_unready_pure = None
        j_stage1_cache = None
        j_nonstage_atomic = None
    else:
        j_stage1_cache = jr_fwd(0x28)
        if external_dispatch_ready_addr is not None:
            emit([
                0xFA,
                external_dispatch_ready_addr & 0xFF,
                external_dispatch_ready_addr >> 8,
                0xFE,
                external_dispatch_ready_value & 0xFF,
            ])
            j_dispatch_unready_pure = jr_fwd(0x20)
        else:
            j_dispatch_unready_pure = None
        emit([
            0xCD,
            external_lava_dispatch_addr & 0xFF,
            external_lava_dispatch_addr >> 8,
        ])
        j_nonstage_pure = jr_fwd(0x28)        # dispatcher returned Z
        j_nonstage_atomic = jr_fwd(0x18)
        patch_jr(j_stage1_cache)

    # Select the cache byte without losing the caller's destination HL.
    emit([
        0xE5,                               # PUSH HL
        0xCB, 0x54,                         # BIT 2,H: map base is $9C?
        0x21, cache_9800 & 0xFF, cache_9800 >> 8,
    ])
    j_cache_selected = jr_fwd(0x28)
    emit([0x2C])                             # $9C00 -> second cache byte
    patch_jr(j_cache_selected)
    emit([
        0xFA, 0x00, 0xDC, 0xF6, 0x01,       # camera phase | valid bit
        0xBE,                               # compare key to cached byte
    ])
    j_dirty = jr_fwd(0x20)
    emit([0xE1])                             # cache hit: restore HL
    j_stage1_pure = jr_fwd(0x18)
    patch_jr(j_dirty)
    emit([0x77, 0xE1])                       # publish key; restore HL

    # ---- Changed localized map: precomputed atomic path ----
    if j_nonstage_atomic is not None:
        patch_jr(j_nonstage_atomic)
    emit([0x3E, 0x18, 0xF5])                # 24 rows
    mark("atomic_row")
    emit([0x0E, 24 // atomic_group_width])
    mark("atomic_group")
    # Compute the three attrs before the LCD wait. The group counter is saved
    # beneath the reverse-order attributes.
    emit([0xC5, 0x06, WRAM_BG_TABLE_HI])
    for _ in range(atomic_group_width):
        emit([0x1A, 0x13, 0x4F, 0x0A, 0xF5])
    emit([0x1B] * atomic_group_width)        # source back to group start
    emit([0xF3])
    mark("atomic_stat3")
    emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])
    jr_back(0x20, "atomic_stat3")
    mark("atomic_stat0")
    emit([0xF0, 0x41, 0xE6, 0x03])
    jr_back(0x20, "atomic_stat0")
    for _ in range(atomic_group_width):
        emit([0x1A, 0x13, 0x22])             # tile IDs in VBK0
    emit([0x3E, 0x01, 0xE0, 0x4F, 0x2D])    # VBK1; last destination
    for _ in range(atomic_group_width):
        emit([0xF1, 0x32])                   # POP AF; LD [HL-],A
    emit([
        0x23,                               # undo final HL decrement
        0xAF, 0xE0, 0x4F,                   # VBK0
        0x7D, 0xC6, atomic_group_width, 0x6F,
        0xFB, 0xC1, 0x0D,                   # EI; group counter
    ])
    jr_back(0x20, "atomic_group")
    emit([
        0x7D, 0xC6, 0x08, 0x6F,
        0x30, 0x01, 0x24,
        0xF1, 0x3D,                         # row counter
        0xC8, 0xF5,                         # RET Z; preserve next row count
    ])
    jr_back(0x18, "atomic_row")

    # ---- Cache hit / unchanged or neutral scene: pure four-tile path ----
    patch_jr(j_nonstage_pure)
    if j_dispatch_unready_pure is not None:
        patch_jr(j_dispatch_unready_pure)
    patch_jr(j_stage1_pure)
    emit([0x3E, 0x18, 0xF5])
    mark("pure_row")
    emit([0x0E, 0x06])
    mark("pure_group")
    emit([0xF3])
    mark("pure_stat3")
    emit([0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03])
    jr_back(0x20, "pure_stat3")
    mark("pure_stat0")
    emit([0xF0, 0x41, 0xE6, 0x03])
    jr_back(0x20, "pure_stat0")
    for _ in range(4):
        emit([0x1A, 0x13, 0x22])
    emit([0xFB, 0x0D])
    jr_back(0x20, "pure_group")
    emit([
        0x7D, 0xC6, 0x08, 0x6F,
        0x30, 0x01, 0x24,
        0xF1, 0x3D,
        0xC8, 0xF5,
    ])
    jr_back(0x18, "pure_row")
    return bytes(code)


def create_gdma_transfer() -> bytes:
    """GDMA 256 bytes from WRAM bank 0:CC80 to displayed tilemap VBK=1.

    Must run during VBlank. DI protects the general-mode transfer.
    Checks LCDC bit 3 for tilemap base (0x9800 or 0x9C00).
    """
    code = bytearray()

    # VBK=1
    code.extend([0x3E, 0x01, 0xE0, 0x4F])

    # DI — protect general-mode GDMA from Timer ISR
    code.extend([0xF3])

    # HDMA source = CC80 (WRAM bank 0, always accessible)
    code.extend([0x3E, 0xCC, 0xE0, 0x51])   # HDMA1 = 0xCC
    code.extend([0x3E, 0x80, 0xE0, 0x52])   # HDMA2 = 0x80

    # HDMA dest = tilemap base (check LCDC bit 3)
    code.extend([0xF0, 0x40])               # LDH A,[LCDC]
    code.extend([0xE6, 0x08])               # AND 0x08
    code.extend([0x28, 0x04])               # JR Z, +4 (use 0x98)
    code.extend([0x3E, 0x9C])               # LD A, 0x9C
    code.extend([0x18, 0x02])               # JR +2
    code.extend([0x3E, 0x98])               # LD A, 0x98
    code.extend([0xE0, 0x53])               # HDMA3 = dest high
    code.extend([0xAF, 0xE0, 0x54])         # HDMA4 = 0x00

    # General-mode GDMA (HDMA5=0x3F): copies 1024 bytes atomically
    # while CPU is halted (~512T). Required because HBlank-mode HDMA
    # (HDMA5=0xBF) continues across multiple HBlanks; once we restore
    # VBK=0 after the call returns, subsequent HBlank steps write to
    # VRAM bank 0 (tile IDs) instead of bank 1 (attributes) — visible
    # as random tile garbage. General mode completes before VBK is
    # restored, keeping every write in VRAM bank 1.
    # HDMA5 = 0x0F → 256-byte general-mode transfer (matches the 8 rows
    # × 32 bytes attr_comp fills). Saves ~768T per frame vs full 1024-byte
    # transfer, and preserves bg_sweep's writes to VRAM rows 8-31.
    code.extend([0x3E, 0x0F, 0xE0, 0x55])   # HDMA5 = 0x0F → general mode 256 bytes

    # GDMA done. Restore interrupts and VBK=0.
    code.extend([0xFB])                     # EI
    code.extend([0xAF, 0xE0, 0x4F])         # VBK=0
    code.extend([0xC9])                     # RET

    return bytes(code)


def create_attr_computation(bg_table_addr: int) -> bytes:
    """Compute an attr buffer in WRAM bank 0 from the tile buffer.

    Reads tiles from WRAM 0xC1A0 (bank 0, always accessible).
    Looks up bg_table from ROM bank 13 (active during VBlank handler).
    Writes to WRAM bank 0:CC80 onward.

    18 rows × 24 tiles + 8 padding cols. Each ROW gets its own DI window.

    Row count is 18 (not 24) to fit the visible viewport height — the
    off-screen rows 19-24 never need attr writes. Going past 22 rows
    starves the game's main loop of CPU time per frame (each row adds
    ~2050T to the handler; >22 rows leaves <25K T for game logic and
    the STAGE LOAD→dungeon transition can't complete). See
    `docs/v301_regression_stage_load_stuck.md` for the binary-search
    cliff data.

    Why one DI per row (not per chunk): the empirical safe DI budget on this
    ROM is ~2000-3000T, NOT the 7000T originally assumed. The chunked design
    (3 rows in one ~6100T DI) freezes at the FFC1=0→1 transition; one-row
    DI (~2000T) does not. Total runtime is similar to the 8-chunk design
    (~50K T) but per-DI stays safe and the EI gaps service Timer ISR.

    Register plan inside DI:
      B  = bg_table high byte (0x70)
      C  = scratch (tile ID for [BC] lookup)
      HL = tile source (C1A0+, bank 0 — unaffected by FF70)
      DE = attr dest (CC80+, bank 0 — always accessible)
      FFE0 (HRAM scratch) = row counter (avoids DI-internal PUSH/POP nesting)
    """
    bg_table_hi = (bg_table_addr >> 8) & 0xFF
    code = bytearray()

    code.extend([0xC5, 0xD5, 0xE5, 0xF5])  # PUSH BC, DE, HL, AF
    code.extend([0x21, 0xA0, 0xC1])         # LD HL, 0xC1A0
    code.extend([0x11, ATTR_BUFFER & 0xFF, (ATTR_BUFFER >> 8) & 0xFF])  # LD DE, 0xCC80 (attr buffer)
    code.extend([0x3E, 0x08])               # LD A, 8 (gameplay-safe cliff; preserves mini-boss + room progression)
    code.extend([0xE0, 0xE0])               # LDH [FFE0], A (row counter in HRAM)

    row_loop = len(code)
    code.extend([0xF3])                     # DI
    code.extend([0x06, bg_table_hi])        # LD B, bg_table_hi
    code.extend([0x3E, 0x18])               # LD A, 24 (tile counter)

    tile_loop = len(code)
    code.extend([0xF5])                     # PUSH AF (tile counter)
    code.extend([0x2A])                     # LD A, [HL+]
    code.extend([0x4F])                     # LD C, A
    code.extend([0x0A])                     # LD A, [BC]
    code.extend([0x12])                     # LD [DE], A
    code.extend([0x13])                     # INC DE
    code.extend([0xF1])                     # POP AF
    code.extend([0x3D])                     # DEC A
    code.extend([0x20, (tile_loop - (len(code) + 2)) & 0xFF])

    code.extend([0xFB])                     # EI

    # DE += 8 (skip padding cols) — outside DI
    code.extend([0x7B, 0xC6, 0x08, 0x5F, 0x30, 0x01, 0x14])

    # Row counter via HRAM
    code.extend([0xF0, 0xE0])               # LDH A, [FFE0]
    code.extend([0x3D])                     # DEC A
    code.extend([0xE0, 0xE0])               # LDH [FFE0], A
    code.extend([0x20, (row_loop - (len(code) + 2)) & 0xFF])

    code.extend([0xF1, 0xE1, 0xD1, 0xC1])  # POP AF, HL, DE, BC
    code.extend([0xC9])
    return bytes(code)


def build_v301(
    palette_yaml: Path | str = Path("palettes/penta_palettes_v097.yaml"),
    output_path: Path | str = Path("rom/working/penta_dragon_dx_v301.gb"),
):
    input_rom = Path("rom/Penta Dragon (J).gb")
    palette_yaml = Path(palette_yaml)
    output_path = Path(output_path)

    rom = bytearray(input_rom.read_bytes())
    palettes = load_palettes_from_yaml(palette_yaml)

    # pal7 ← pal0 (hide stale CGB boot-ROM attrs)
    bg_data = bytearray(palettes['bg_data'])
    bg_data[56:64] = bg_data[0:8]
    palettes = {**palettes, 'bg_data': bytes(bg_data)}

    rom[0x143] = 0x80  # CGB flag

    # Bank 13 layout
    bank13 = 13 * 0x4000
    pal_addr = 0x6800
    boss_pal_addr = 0x6880
    boss_slot_addr = 0x68C0
    swj_addr = 0x68D0; sdj_addr = 0x68D8
    sp_addr = 0x68E0; shp_addr = 0x68E8
    pal_loader_addr = 0x6900
    shadow_main_addr = 0x69D0
    colorizer_addr = 0x6A10
    tile_pal_addr = 0x6B00
    cond_pal_addr = 0x6C90
    bg_sweep_addr = 0x6CD0
    gdma_addr = 0x6D80
    colorize_addr = 0x6E00
    bg_table_addr = 0x7000
    attr_comp_addr = 0x7100

    def w(addr, data):
        off = bank13 + (addr - 0x4000)
        rom[off:off + len(data)] = data

    # Palette data + tables (same as v3.00)
    w(pal_addr, palettes['bg_data'])
    w(pal_addr + 64, palettes['obj_data'])
    w(boss_pal_addr, palettes['boss_palette_table'])
    w(boss_slot_addr, palettes['boss_slot_table'])
    w(swj_addr, palettes['sara_witch_jet'])
    w(sdj_addr, palettes['sara_dragon_jet'])
    w(sp_addr, palettes['spiral_proj'])
    w(shp_addr, palettes['shield_proj'])
    w(0x68F0, palettes['turbo_proj'])

    w(pal_loader_addr, create_palette_loader(
        pal_addr, boss_pal_addr, boss_slot_addr,
        swj_addr, sdj_addr, sp_addr, shp_addr, tp_addr=0x68F0))
    w(shadow_main_addr, create_shadow_colorizer_main(colorizer_addr, boss_slot_addr))

    colorizer = bytearray(create_tile_based_colorizer(colorizer_addr))
    # OAM scan cap (LD B,n at colorizer entry). Kept at 0x0A=10 (the shipped,
    # hardware-verified VBlank-safe value). Raising it to 0x28=40 (full OAM
    # coverage) was TESTED for the black-enemy issue (items 3,4,6,11) but did NOT
    # fix in-game enemies: they still render p0 (blue/black) because the real bug
    # is a DMA-ordering race (the colorizer assigns p6/p7 in the shadow buffer but
    # the game's main-loop OAM rebuild overwrites HW OAM with p0 before display).
    # The full OBJ fix (cap 40 + DMA-ordering rework) is timing-critical and needs
    # MiSTer hardware verification — see docs/audit/obj_enemy_color_race.md.
    colorizer[1] = 0x0A
    w(colorizer_addr, bytes(colorizer))

    w(tile_pal_addr, create_tile_to_palette_subroutine())
    w(bg_table_addr, BG_TABLE_BYTES)
    w(cond_pal_addr, create_conditional_palette_cached(pal_loader_addr))

    # bg_sweep safety net. Strip the internal FFC1 gate (first 4 bytes
    # Strip FFC1 prefix (`F0 C1 B7 C8` = LDH A,[FFC1]; OR A; RET Z).
    # Without this, bg_sweep skips title/menu (FFC1=0). Hardware
    # testing on MiSTer showed white splotches on title screen and
    # inventory menu — the inline tile+attr copy doesn't catch all
    # tile-write paths (e.g., title animation, menu rendering go
    # through other routines that don't update attrs).
    # The previous time I stripped this the issue was COMPOUND with
    # attr_comp + GDMA being called too; with those disabled, bg_sweep
    # ×1 outside the FFC1 gate is the same cycle cost as v3.00's
    # bg_sweep ×1 inside the gate during gameplay, and adds title
    # coverage as a free bonus.
    sweep = bytearray(create_bg_sweep_viewport_gated(bg_table_addr, bg_sweep_addr))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8]), \
        f"bg_sweep prefix changed: {sweep[:4].hex()}"
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # NOPs — run on title too
    w(bg_sweep_addr, bytes(sweep))

    # GDMA transfer routine
    gdma_code = create_gdma_transfer()
    assert gdma_addr + len(gdma_code) <= colorize_addr, \
        f"GDMA overflows: {gdma_addr + len(gdma_code):#X} > {colorize_addr:#X}"
    w(gdma_addr, gdma_code)
    print(f"  GDMA transfer: {len(gdma_code)} bytes at 0x{gdma_addr:04X}")

    # Attr computation routine
    attr_comp = create_attr_computation(bg_table_addr)
    w(attr_comp_addr, attr_comp)
    print(f"  attr computation: {len(attr_comp)} bytes at 0x{attr_comp_addr:04X}")

    # ============================================================
    # COLORIZE HANDLER
    #
    # Order: FF99 save+set → VBK save → cold-boot init → cond_pal → GDMA
    #        → FFC1 gate { DMA, bg_sweep, OBJ colorizer, attr computation }
    #        → VBK restore → FF99 restore
    #
    # FF99 fix (essential): the game's STAT handler at 0x0853 and Timer ISR
    # at 0x06B3 both restore the ROM bank from FF99 at exit. The hook at
    # 0x0824 writes 0x0D to 0x2100 but DOES NOT update FF99 (47-byte budget).
    # If an ISR fires during our colorize handler (after any EI), it would
    # restore bank from FF99 (stale game value, e.g. bank 1) and our
    # subsequent PC fetches would come from the wrong bank — garbage exec,
    # game freeze. Updating FF99 here makes ISRs restore bank 13 correctly.
    # ============================================================
    code = bytearray()
    # FF99 protocol REMOVED — v3.00 doesn't have it and works correctly.
    # Adding it on v3.01 cost ~100T per VBlank and pushed palette_loader
    # writes into LCD mode 3 where CRAM writes are dropped silently,
    # producing the "splotches" the user reported on title screen.
    # The original concern (ISRs restoring wrong ROM bank from FF99) is
    # not a problem in practice: STAT and Timer ISRs in this ROM don't
    # mid-handler restore FF99 in a way that breaks our bank context.
    # code.extend([0xF0, 0x99, 0xF5])           # LDH A,[FF99]; PUSH AF
    # code.extend([0x3E, 0x0D, 0xE0, 0x99])     # FF99 = 0x0D
    code.extend([0xF0, 0x4F, 0xF5])           # save VBK
    code.extend([0xAF, 0xE0, 0x4F])           # VBK = 0

    # DF02 magic byte cold-boot check
    code.extend([0xFA, 0x02, 0xDF, 0xFE, 0x5A])
    df02_jr = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, skip_cold

    # ---- COLD-BOOT PATH ----
    code.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # DF02 = 0x5A
    code.extend([0xAF, 0xEA, 0x00, 0xDF])         # DF00 = 0 (hash)
    code.extend([0xEA, 0x4D, 0xDF])               # DF4D = 0 (cold palette init)
    code.extend([0xEA, 0x0A, 0xDF])               # DF0A = 0 (teleport req — A still 0)
    # DF03 init REMOVED. Was unused (only meaningful for attr_comp+GDMA
    # path which isn't called). Saving 4 bytes / ~25T from cold-boot.
    # Brings v3.01 cold-boot bytes to match v3.00 baseline exactly.
    # code.extend([0xAF, 0xEA, 0x03, 0xDF])

    # Copy bg_table ROM → WRAM 0xCC00 (for inline hook compatibility — not
    # strictly needed for v3.01 since inline hook no longer reads it, but
    # keeping it doesn't hurt and allows fallback)
    code.extend([0x21, bg_table_addr & 0xFF, (bg_table_addr >> 8) & 0xFF])
    code.extend([0x11, WRAM_BG_TABLE & 0xFF, (WRAM_BG_TABLE >> 8) & 0xFF])
    code.extend([0x06, 0x00])                 # B = 0 (256 iters)
    bg_copy = len(code)
    code.extend([0x2A, 0x12, 0x13, 0x05])    # [HL+]→[DE]; INC DE; DEC B
    offset = bg_copy - (len(code) + 2)
    code.extend([0x20, offset & 0xFF])

    # Cold-boot bank-2 zero REMOVED. It took ~5K T on the first VBlank,
    # which spilled the subsequent palette_loader call out of LCD mode 1
    # into modes 2/3. CGB CRAM writes during mode 3 are dropped silently,
    # leaving some OBJ palette bytes at boot defaults (0xFF 0x7F = white).
    # Symptom: Sara's body rendered with white instead of pink because
    # OBJ palette 2 color 1 stayed at 0x7FFF after palette_loader's
    # writes were partially dropped.
    # Since attr_comp + GDMA aren't called in the warm path, WRAM bank 2
    # is never read — zeroing it served no purpose. Removed entirely.

    # ---- skip_cold target ----
    code[df02_jr] = (len(code) - df02_jr - 1) & 0xFF

    # DX TELEPORT hook REMOVED (was: JP bank2:0x4000 from VBlank IRQ).
    # Investigation showed bank2:0x4000 calls bank0:0x0099, which is a
    # STAT-mode busy-wait for LCD mode 3. From VBlank IRQ context the
    # LCD is in mode 1 and stays there until our IRQ returns — so the
    # busy-wait loops forever, and EI'd nested IRQs recurse into the
    # same loop. Result: freeze.
    #
    # True teleport would require either:
    #   a) Hooking the GAME's main loop (no free bank-0 space)
    #   b) Per-boss save states (manual one-time capture)
    #   c) Reverse-engineering the natural boss-spawn trigger flag
    # Pending a follow-up. For now teleport is unsupported; the
    # editor's "State-byte Hold (legacy)" section is still usable for
    # forcing FFBA/D880/FFB7 if user wants to experiment.

    # ---- WARM PATH ----
    # Structure matches v3.00 exactly: cond_pal → FFC1 gate {bg_sweep, OAM,
    # shadow_main}. Running bg_sweep on title added ~3K T per title frame
    # which slowed the title's tile-draw animation visibly: the YANOMAN
    # logo took longer to draw, producing "splotch" artifacts when the
    # user pressed START before the draw completed.
    # Since the inline tile+attr copy at 0x42A7 already handles title
    # tiles when the game's tilemap copy runs, bg_sweep on title was
    # redundant for correctness and harmful for timing.
    code.extend([0xCD, cond_pal_addr & 0xFF, (cond_pal_addr >> 8) & 0xFF])

    # ============================================================
    # ONE-SHOT ATTR CLEANER
    #
    # Uninitialized CGB boot attributes must be cleared in both tilemaps, but
    # the historical implementation spread the work over 32 VBlanks. That
    # repeatedly overran the game's timing-sensitive VBlank path and delayed
    # title -> gameplay by roughly 99 frames.
    #
    # On cold boot (or an explicit title-return rearm), turn the LCD off from
    # VBlank, clear the complete 0x9800-0x9FFF attribute plane in one bounded
    # pass, and restore LCDC. With the LCD off VRAM is immediately writable, so
    # this costs about one frame once instead of stealing time for 32 frames.
    #
    # DF08 remains the 0x5A completion sentinel used by title transitions.
    # DF07 is kept at zero for story/death services that wait for the cleaner.
    # ============================================================
    code.extend([0xFA, 0x08, 0xDF])           # LD A, [DF08]
    code.extend([0xFE, 0x5A])                 # CP 0x5A
    cleaner_skip_jr = len(code) + 1
    code.extend([0x28, 0x00])                 # JR Z, skip_cleaner

    # Save LCDC and disable the LCD. This handler is entered from VBlank, the
    # only safe time to clear LCDC bit 7 while the display is running.
    code.extend([0xF0, 0x40, 0xF5])           # LDH A,[LCDC]; PUSH AF
    code.extend([0xCB, 0xBF, 0xE0, 0x40])     # RES 7,A; LDH [LCDC],A

    # Select attribute bank and clear 8 × 256 bytes (both 1 KiB maps).
    code.extend([0x3E, 0x01, 0xE0, 0x4F])     # VBK = 1
    code.extend([0x21, 0x00, 0x98])           # HL = 0x9800
    code.extend([0x0E, 0x08])                 # C = eight 256-byte pages
    code.extend([0xAF])                       # A = 0
    attr_page_loop = len(code)
    code.extend([0x06, 0x00])                 # B = 0 (256 iterations)
    attr_byte_loop = len(code)
    code.extend([0x22, 0x05])                 # [HL+]=A; DEC B
    code.extend([
        0x20,
        (attr_byte_loop - (len(code) + 2)) & 0xFF,
    ])
    code.extend([0x0D])                       # DEC C
    code.extend([
        0x20,
        (attr_page_loop - (len(code) + 2)) & 0xFF,
    ])

    # Restore VBK 0 and the exact pre-clean LCDC configuration.
    code.extend([0xAF, 0xE0, 0x4F])           # VBK = 0
    code.extend([0xF1, 0xE0, 0x40])           # POP AF; LDH [LCDC],A

    # Publish completion only after the full plane is neutral.
    code.extend([0x3E, 0x5A, 0xEA, 0x08, 0xDF])  # DF08 = 0x5A
    code.extend([0xAF, 0xEA, 0x07, 0xDF])         # DF07 = 0

    # skip_cleaner target
    code[cleaner_skip_jr] = (len(code) - cleaner_skip_jr - 1) & 0xFF

    code.extend([0xF0, 0xC1, 0xB7])
    ffc1_skip = len(code) + 1
    code.extend([0x28, 0x00])
    code.extend([0xCD, bg_sweep_addr & 0xFF, (bg_sweep_addr >> 8) & 0xFF])
    code.extend([0xCD, shadow_main_addr & 0xFF, (shadow_main_addr >> 8) & 0xFF])
    code.extend([0xCD, 0x80, 0xFF])           # OAM DMA
    code[ffc1_skip] = (len(code) - ffc1_skip - 1) & 0xFF

    # Restore VBK, restore FF99, return
    code.extend([0xF1, 0xE0, 0x4F])           # POP AF; LDH [VBK], A
    # code.extend([0xF1, 0xE0, 0x99])           # POP AF; LDH [FF99], A (FF99 protocol removed)
    code.extend([0xC9])

    assert colorize_addr + len(code) <= bg_table_addr, \
        f"colorize handler overflow: {colorize_addr + len(code):#X} > {bg_table_addr:#X}"
    w(colorize_addr, bytes(code))
    print(f"  colorize handler: {len(code)} bytes at 0x{colorize_addr:04X}")

    # ============================================================
    # VBLANK HOOK at 0x0824 and Wrapper at 0x6F10
    # ============================================================
    wrapper_addr = 0x6F10

    # Write wrapper to bank 13 ROM (offset in file is 13 * 0x4000 + (wrapper_addr - 0x4000))
    wrapper_off = 13 * 0x4000 + (wrapper_addr - 0x4000)
    wrapper = bytearray([
        # --- PRESERVE REGISTERS ---
        0xC5,                                 # PUSH BC
        0xD5,                                 # PUSH DE
        0xE5,                                 # PUSH HL

        # --- Robust 8-debounce joypad read ---
        0x3E, 0x20,                           # LD A, 0x20
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0x2F,                                 # CPL
        0xE6, 0x0F,                           # AND 0x0F
        0xCB, 0x37,                           # SWAP A
        0x47,                                 # LD B, A
        0x3E, 0x10,                           # LD A, 0x10
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0xF0, 0x00,                           # LDH A, [FF00]
        0x2F,                                 # CPL
        0xE6, 0x0F,                           # AND 0x0F
        0xB0,                                 # OR B
        0xE0, 0x93,                           # LDH [FF93], A
        0x47,                                 # LD B, A
        0x3E, 0x30,                           # LD A, 0x30
        0xE0, 0x00,                           # LDH [FF00], A
        0x78,                                 # LD A, B

        # --- CALL actual colorize_handler ---
        0xCD, colorize_addr & 0xFF, (colorize_addr >> 8) & 0xFF,

        # --- RESTORE REGISTERS ---
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC

        0xC9,                                 # RET
    ])
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper written: {len(wrapper)} bytes at bank13:0x{wrapper_addr:04X}")

    hook = bytearray([
        0xF0, 0x99,                           # LDH A, [FF99]
        0xF5,                                 # PUSH AF (save original bank)
        0x3E, 0x0D,                           # LD A, 13 (ROM bank of wrapper)
        0xE0, 0x99,                           # LDH [FF99], A (update shadow to 13)
        0xEA, 0x00, 0x21,                     # LD [0x2100], A (switch MBC bank to 13)
        0xCD, wrapper_addr & 0xFF, (wrapper_addr >> 8) & 0xFF,  # CALL wrapper
        0xF1,                                 # POP AF (restore original bank value)
        0xE0, 0x99,                           # LDH [FF99], A (restore original shadow)
        0xEA, 0x00, 0x21,                     # LD [0x2100], A (restore original MBC ROM bank)
        0xC9,                                 # RET
    ])
    assert len(hook) <= 47
    rom[0x0824:0x0824 + 47] = (hook + bytearray(47 - len(hook)))[:47]

    # NOP game DMA
    rom[0x06D5:0x06D8] = bytearray([0x00, 0x00, 0x00])

    # RST $38 RETI → RET
    rom[0x003B] = 0xC9

    # ============================================================
    # INLINE PURE TILE-ONLY HOOK at bank1:0x42A7
    # ============================================================
    inline_code = create_inline_tile_copy_pure_tileonly()
    available = 0x436D - 0x42A7 + 1  # 199 bytes
    assert len(inline_code) <= available, \
        f"inline tile copy too big: {len(inline_code)} > {available}"

    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    if len(inline_code) < available:
        rom[0x42A7 + len(inline_code):0x436E] = bytearray(available - len(inline_code))

    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])

    print(f"  inline tile copy: {len(inline_code)} bytes (tile-only, {available - len(inline_code)} free)")

    # Header checksum
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(rom)
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    return output_path


if __name__ == "__main__":
    build_v301()
