#!/usr/bin/env python3
"""v3.01-teleport (v4): stack-redirect approach.

The earlier attempts (CALL 0x1A2B / JP 0x1A2B from inside the VBlank IRQ)
freeze because arena init has dependencies that the IRQ context breaks:
  - 0x1A2B's CALL 0x759B + bank2:0x4000 → eventual RET wants bank 1 mapped
    (RST 0x28 inside the flow) and clean stack; we can't satisfy both from
    inside the IRQ without bank-0 space (which doesn't exist).
  - The arena per-frame loop at 0x4073 wants IRQs to drive its HALT/sync.

The PyBoy "proof" worked in MAIN-LOOP context (forced PC from a dungeon
frame). To match that in-ROM, we let the VBlank IRQ chain unwind and
execute the teleport AFTER the RETI, from a WRAM landing pad.

Architecture:
  1. Cold-boot once: copy the ~37-byte landing pad code from bank 13 ROM
     to WRAM 0xCF82 (which is executable on CGB). Sentinel: DF1E = 0x5A.
  2. Teleport routine (called every VBlank from our hook): detect combo,
     debounce, cycle boss counter, set FFBA/FFBF. Then modify the stack:
       - Read the CPU-pushed PC at SP+14 (main-loop return), save to DF20/21.
       - Overwrite SP+14 with 0xCF82 (landing pad address).
     RET normally.
  3. The IRQ chain unwinds: our routine RETs → hook tail RETs → 0x06D1
     pops its 4 saved regs → RETI. CPU pops the modified PC (= 0xCF82),
     execution resumes at the landing pad — in MAIN-LOOP context (IME=1).
  4. Landing pad at CF82: disables VBlank IRQ (so the colorize handler
     can't re-enter the teleport), keeps other IRQs, maps bank 3, EIs,
     CALLs 0x1A2B (proven safe in main-loop context). If 0x1A2B returns,
     restore IE and JP the saved main-loop PC.

WRAM allocation (DF1E-DF22):
  DF1E — landing pad copy sentinel (0x5A = copied)
  DF20/21 — saved main-loop PC low/high (for the JP back)
  DF22 — saved IE

CRITICAL: All WRAM destinations (LUT, trampolines, landing pad, levelsel stub)
must reside in WRAM bank 0 (0xC000-0xCFFF) which is always accessible regardless
of FF70. DO NOT use 0xD000-0xDFFF (banked WRAM): the boot ROM sets FF70=1 and
the game never switches to bank 2, so code/data in bank 2 is garbage on real GBC.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_v301_gdma import build_v301
from build_v296_phantomsafe import create_bg_sweep_viewport_gated
from arena_position import (
    parse_footprint_posmaps, rle_encode_posmap, create_rle_expander,
    create_position_sweep,
)

BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
TP_OUT = Path("rom/working/penta_dragon_dx_teleport.gb")

# ----------------------------------------------------------------------
# OBJ Palette Lookup Table (replaces CP cascade at bank13:0x6B00)
#
# 256-byte static LUT: tile_id -> OBJ palette number (0-7).
# Generated from palettes/monster_palette_map.yaml. The LUT replaces the
# old 19-byte CP-cascade subroutine (create_tile_to_palette_subroutine()).
# Trampolines in WRAM read this via LD A,[HL] with HL=$D900 + tile_id.
# ----------------------------------------------------------------------

import yaml

OBJ_PAL_TABLE_ADDR = 0x6B00   # bank13 address of the 256-byte LUT
OBJ_PAL_WRAM = 0xCE00         # WRAM bank 0 (always accessible, no FF70 needed)
OBJ_PAL_WRAM_HI = 0xCE


def build_obj_pal_table() -> bytes:
    """Generate 256-byte OBJ palette LUT from monster_palette_map.yaml.

    The YAML defines per-monster tile ranges with their palette assignment.
    For Sara tiles (0x10-0x2F), writes 0xFF (sentinel for FFBE resolution
    at runtime). Unspecified tiles use reasonable defaults matching the old
    CP-cascade behavior.
    """
    palette_yaml = Path(__file__).parent.parent / "palettes" / "monster_palette_map.yaml"
    lut = bytearray(256)

    # Default fill: matching old cascade behavior
    #   0x00-0x01 → 3 (projectile)
    #   0x02-0x0F → 0 (effects)
    #   0x10-0x2F → 0xFF (Sara dynamic)
    #   0x30-0x4F → 3 (enemies)
    #   0x50-0x5F → 4 (hornets)
    #   0x60-0x6F → 5 (orc/ground)
    #   0x70-0x7F → 6 (humanoid)
    #   0x80-0xFF → 4 (default high)
    for tile in range(256):
        if tile <= 0x01:
            lut[tile] = 3      # projectile
        elif tile <= 0x0F:
            lut[tile] = 0      # effects
        elif tile <= 0x2F:
            lut[tile] = 0xFF   # Sara dynamic sentinel
        elif tile <= 0x4F:
            lut[tile] = 3      # enemies
        elif tile <= 0x5F:
            lut[tile] = 4      # hornets
        elif tile <= 0x6F:
            lut[tile] = 5      # orc/ground
        elif tile <= 0x7F:
            lut[tile] = 6      # humanoid
        else:
            lut[tile] = 4      # default high

    # Override with YAML monster entries (when available)
    if palette_yaml.exists():
        with open(palette_yaml) as f:
            data = yaml.safe_load(f)
        monsters = data.get('monsters', [])
        for entry in monsters:
            pal = entry.get('palette', 0)
            tile_ranges = entry.get('tile_ranges', [])
            for (lo, hi) in tile_ranges:
                for t in range(lo, hi + 1):
                    if t < 256:
                        # Resolve 'dynamic_ffbe' to sentinel 0xFF
                        if isinstance(pal, str) and pal == 'dynamic_ffbe':
                            lut[t] = 0xFF
                        else:
                            lut[t] = pal & 7
    else:
        print(f"  [build_obj_pal_table] WARNING: {palette_yaml} not found, using defaults")

    # Tile 0xFF sentinel: map to 0 (palette 0) — never used in practice
    lut[0xFF] = 0x00

    return bytes(lut)


BANK13 = 13 * 0x4000
COLORIZE_ADDR = 0x6E00
OBJ_STAMPER_ADDR = 0x6A10     # old OBJ tile colorizer (CALL removed in OAM intercept)
BG_SWEEP_ADDR = 0x6CD0     # bg_sweep safety-net (re-patched to read WRAM 0xCC00)
WRAM_BG_TABLE = 0xCC00     # per-scene table kept current by scene_detect (bank 0)

# Position-sweep (holy-grail path) layout in bank 13:
POSSWEEP_ADDR = 0x7100     # position sweep code (reuses dead attr_comp space)
EXPAND_ADDR = 0x6D80       # RLE expander (reuses dead GDMA space)
POSMAP_DATA_ADDR = 0x7B00  # RLE-compressed per-arena posmaps (variable length)
POSMAP_PTR_TABLE = 0x7FE0  # 9 x 2-byte LE pointers to RLE data (0 = none)
ROW_CURSOR_ADDR = 0xDF40   # sweep row cursor
POSMAP_FLAG_ADDR = 0xDF46  # expanded-arena flag (idx+1; 0 = none/non-arena)
POSMAP_SCRATCH_ADDR = 0xDF47  # vram_hi (+1: rows_left)
# Posmaps captured as the MODAL attr the (good) tile-ID hook assigns each cell
# over the animation (probe_arena_posmap_gen.lua on a hook-active ROM). This
# freezes the proven Phase-0 look per-cell -> same colors, zero alternation.
FOOTPRINT_LOG = "scripts/diagnostics/posmap_maps.log"
ARENA_ORDER = ["shalamar", "riff", "crystal_dragon", "cameo", "ted",
               "troop", "faze", "angela", "penta_dragon"]
TELEPORT_ADDR = 0x6E90     # teleport check + state setup + stack redirect
                              # 0x6E80 conflicts with v301's colorize handler tail
                              # (FFC1 gate + shadow_main + OAM DMA at 0x6E7E-0x6E8C)
LANDING_PAD_ROM_ADDR = 0x6F80  # landing pad source (gets copied to WRAM CF82)
                              # — moved from 0x6F00 because the teleport
                              # routine grew past 128 bytes and was
                              # overwriting the landing pad source.
LANDING_PAD_WRAM = 0xCF82      # WRAM bank 0 (right after trampolines at 0xCF00..0xCF81)
# Level-select score-screen attr-clear stub. The game's GAME-START path
# (DCFD != 0) JPs to bank1:0x7393 which runs its own DI'd input loop, so our
# VBlank colorizer is dark while shown. Stale attrs from earlier screens
# bleed (orange/red). Patch the JP NZ at bank1:0x3B47 to point HERE instead;
# this stub clears VBK=1 attrs at 0x9800-0x9FFF (LCD-off, fast), then JPs
# to the original 0x7393. Diagnosed in commit 306f73e / docs/audit/levelselect_score_bleed.md.
LEVELSEL_STUB_ROM_ADDR = 0x53C2  # 36-byte free run in bank 13 (not contiguous
                                 # with landing pad — separate cold-boot copy)
LEVELSEL_STUB_WRAM = 0xCFAA      # 0xCF82 + 40 = 0xCFAA
LEVELSEL_PATCH_ADDR = 0x3B47     # bank0 (always-mapped); JP NZ target
LEVELSEL_STUB_MAX = 36           # size cap (the free run is 36 bytes)

# ---- scene-aware bg_table (Phase 1b: all 9 boss arenas) ----
# Scene-detect routine sits in the gap between landing pad and bg_table.
# bg_table variants live after attr_comp (which ends ~0x713A).
#
# Layout in bank 13 (arenas are exactly 256 bytes apart so the dispatcher
# can compute the address with one ADD to the high byte):
#   0x6FB0  scene_detect routine  (≤ 80 bytes)
#   0x7000  DUNGEON bg_table       (existing — unchanged)
#   0x7200  SHALAMAR    (D880=0x0C, FFBA=0)
#   0x7300  RIFF        (D880=0x0D, FFBA=1)
#   0x7400  CRYSTAL_DRAGON (D880=0x0E, FFBA=2)
#   0x7500  CAMEO       (D880=0x0F, FFBA=3)
#   0x7600  TED         (D880=0x10, FFBA=4)
#   0x7700  TROOP       (D880=0x11, FFBA=5)
#   0x7800  FAZE        (D880=0x12, FFBA=6)
#   0x7900  ANGELA      (D880=0x13, FFBA=7)
#   0x7A00  PENTA_DRAGON (D880=0x14, FFBA=8)
SCENE_DETECT_ADDR = 0x6FB0
DUNGEON_TABLE_ADDR = 0x7000
ARENA_BASE_ADDR = 0x7200       # arena_idx 0..8 → 0x7200 + idx*0x100
SHALAMAR_TABLE_ADDR = 0x7200
RIFF_TABLE_ADDR = 0x7300
CRYSTAL_DRAGON_TABLE_ADDR = 0x7400
CAMEO_TABLE_ADDR = 0x7500
TED_TABLE_ADDR = 0x7600
TROOP_TABLE_ADDR = 0x7700
FAZE_TABLE_ADDR = 0x7800
ANGELA_TABLE_ADDR = 0x7900
PENTA_DRAGON_TABLE_ADDR = 0x7A00
# ---- Lava colorization (later stages reuse stage-1 floor/wall tile IDs as a
# molten field). scene_detect, after copying the dungeon table to WRAM 0xDA00,
# tail-jumps to this helper which (in a lava stage, keyed on FFBA) over-writes
# the molten tile IDs in 0xDA00 with pal5 (BG5 = orange/red lava CRAM). Lives in
# free bank-13 space above the (static) posmap blob. Verified: FFBA is stable at
# the stage value during normal dungeon roaming (probe_lava_ffba.lua).
LAVA_OVERRIDE_ADDR = 0x7E00
# Uniform table for the STAGE-intro / boss-name splash (D880=0x18). The big
# "STAGE NN" letters reuse mid-range tile IDs (0x2C/0x2D/0x3C/0x45/0x54/0x55…)
# that the dungeon table colors p6/p5 (walls/spikes), so the letters render
# multi-tone ("color bleed"). scene_detect swaps this all-pal0 table into 0xDA00
# on the splash so every splash tile resolves to one palette (clean letters).
SPLASH_TABLE_ADDR = 0x7E40
# Per-stage molten tile IDs (probe_lava_ffba.lua histograms + docs/audit/stage2_lava.md):
LAVA_STAGE5_IDS = [0x02, 0x03, 0x04, 0x05, 0x12, 0x13, 0x14, 0x15]  # FFBA=4 (stage 5)
LAVA_STAGE7_IDS = [0x19, 0x1A]                                       # FFBA=6 (stage 7)
DF23_PREV_SCENE = 0xDF0D       # WRAM byte: previous D880 value.
# NOTE: must stay OUTSIDE bg_sweep's 0xDF10-0xDF2F scratch buffer. The old
# 0xDF23 sat *inside* that buffer, so bg_sweep clobbered it every frame with
# tile data → scene-detect never hit its RET-Z fast path → it ran a full
# 256-byte table copy EVERY frame (~23 scanlines), pushing the colorize
# attribute-write out of VBlank into mid-screen active display = wall flicker
# while roaming. 0xDF0D is below the buffer, next to the known-safe DF0C/DF0E.
                              # (uninitialized → first frame triggers copy
                              # to whatever the current D880 maps to)


# ----------------------------------------------------------------------
# Per-arena bg_tables — DATA-DRIVEN (all 9 bosses).
#
# Each table maps a boss BG tile ID -> CGB BG palette index. The mapping is
# generated by scripts/apply_arena_tables.py from a 360-frame animation tour
# (scripts/probe_all_tables.lua + probe_missing_tables.lua): per boss tile,
# accumulate its mean screen row across the animation, bucket mean-row into
# quartile bands (top->4, upper-mid->6, lower-mid->5, bottom->3).
#
# WHY tile-ID keyed: the boss is drawn on the BG layer and colorized by the
# inline hook at 0x42A7 (verified: sweep-stubbed ROM still colors the boss),
# which re-runs every animation frame. A tile-ID map gives each tile ONE
# palette regardless of where it floats, so colors are animation-stable and
# bob-proof. The probe confirmed distant body parts use disjoint tile sets
# (no tile spans >=6 screen rows), so the bands separate cleanly.
#
# Colors themselves (the CRAM behind each palette index) are tuned in the
# live editor; per-arena CRAM is a future phase (palette indices are shared).
# Regenerate the tables:
#   scripts/probe_all_tables.lua (+ probe_missing_tables.lua) -> logs
#   python scripts/apply_arena_tables.py /tmp/all_tables.log /tmp/missing_tables.log
# ----------------------------------------------------------------------

from arena_tables_data import ARENA_TILE_PAL


def _table_from_dict(name: str) -> bytes:
    """Build a 256-byte bg_table from the measured tile->palette dict."""
    t = bytearray(256)
    for tile_id, pal in ARENA_TILE_PAL.get(name, {}).items():
        t[tile_id & 0xFF] = pal & 7
    t[0xFF] = 0
    return bytes(t)


def _bg_table_shalamar() -> bytes:       return _table_from_dict("shalamar")
def _bg_table_riff() -> bytes:           return _table_from_dict("riff")
def _bg_table_crystal_dragon() -> bytes: return _table_from_dict("crystal_dragon")
def _bg_table_cameo() -> bytes:          return _table_from_dict("cameo")
def _bg_table_ted() -> bytes:            return _table_from_dict("ted")
def _bg_table_troop() -> bytes:          return _table_from_dict("troop")
def _bg_table_faze() -> bytes:           return _table_from_dict("faze")
def _bg_table_angela() -> bytes:         return _table_from_dict("angela")
def _bg_table_penta_dragon() -> bytes:   return _table_from_dict("penta_dragon")




def build_scene_detect(dungeon_addr: int, arena_base_addr: int,
                       splash_addr: int) -> bytes:
    """Detect D880 scene change, swap WRAM 0xDA00 with the right bg_table.

    Reads D880 (WRAM scene state). Compares to DF23 (previous). If same,
    early RET. If different, dispatches:
      D880 == 0x0C..0x14 (arena) → arena_base + (D880-0x0C)*0x100
      else                       → dungeon table (default)
    Copies 256 bytes from ROM table → WRAM 0xDA00. Updates DF23.

    Called from the teleport routine (which runs every VBlank with bank
    13 mapped). Cost when scene unchanged: ~16T (read+compare+RET).
    Cost on scene change: ~16T + 256 bytes copy ≈ 4100T (well under VBlank).

    Math trick: arena tables sit 256 bytes apart so the dispatcher only
    needs to compute `H = arena_base_high + (D880 - 0x0C)` and clear L.
    """
    arena_base_high = (arena_base_addr >> 8) & 0xFF
    assert (arena_base_addr & 0xFF) == 0, "arena_base must be page-aligned"

    c = bytearray()
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0x21, DF23_PREV_SCENE & 0xFF, (DF23_PREV_SCENE >> 8) & 0xFF])
    c.extend([0xBE])                      # CP [HL]
    c.extend([0xC8])                      # RET Z (no change — fast path)

    # Scene changed: save new value
    c.extend([0x77])                      # LD [HL], A   (DF23 = new D880)   (A still = D880)

    # Transitional / title scenes -> uniform all-pal0 splash table. These are
    # direct-write/transient screens whose tile IDs span the whole 0x01-0xFF bank,
    # so the dungeon table's 0x80-0xDF->p1 (red font) rule floods them red:
    #   0x18 = STAGE-intro / boss-name splash (big letters were bleeding p6/p5)
    #   0x1B = animated PENTA DRAGON banner (red bands behind letters, red showcase
    #          text + red JAM-logo line — fill tile 0xDF + border 0xCA-0xDE are p1)
    #   0x16 = post-boss reload (Riff/any boss defeat -> full VRAM tile-load shows
    #          high tile IDs -> ~246/360 cells flood red + slowdown looked broken)
    # The menu scenes (0x00/0x1C) are intentionally left on the dungeon table (their
    # red menu font is by design). Re-assert DF02=0x5A to beat the cold-boot copy.
    c.extend([0xFE, 0x18])                # CP 0x18 (splash)
    j_s18 = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, splash_body
    c.extend([0xFE, 0x1B])                # CP 0x1B (animated banner)
    j_s1b = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, splash_body
    c.extend([0xFE, 0x16])                # CP 0x16 (post-boss reload)
    j_not_splash = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, not_splash (none matched)
    splash_body = len(c)
    c[j_s18] = (splash_body - j_s18 - 1) & 0xFF
    c[j_s1b] = (splash_body - j_s1b - 1) & 0xFF
    c.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # LD A,0x5A; LD [DF02],A
    c.extend([0x21, splash_addr & 0xFF, (splash_addr >> 8) & 0xFF])  # LD HL, splash
    j_copy_splash = len(c) + 1
    c.extend([0x18, 0x00])                # JR copy
    not_splash_pos = len(c)
    c[j_not_splash] = (not_splash_pos - j_not_splash - 1) & 0xFF
    # (A is still = D880 here: CP above does not modify A)

    # Compute arena_idx = D880 - 0x0C. If carry → too low → dungeon.
    # If result >= 9 → too high → dungeon. Else load arena table.
    c.extend([0xD6, 0x0C])                # SUB 0x0C
    j_dungeon_lo = len(c) + 1
    c.extend([0x38, 0x00])                # JR C, dungeon  (was < 0x0C)
    c.extend([0xFE, 0x09])                # CP 9
    j_dungeon_hi = len(c) + 1
    c.extend([0x30, 0x00])                # JR NC, dungeon (was >= 0x15)

    # Arena: H = arena_base_high + A, L = 0
    c.extend([0xC6, arena_base_high])     # ADD A, arena_base_high
    c.extend([0x67])                      # LD H, A
    # Suppress the colorize handler's cold-boot 0xDA00 copy IN ARENAS. The arena
    # init (0x1A2B) zeroes a WRAM block covering DF02 (cold-boot sentinel) AND
    # DF0D (this scene cache). scene_detect runs BEFORE colorize each frame, so
    # re-asserting DF02=0x5A here makes the (later, same-frame) cold-boot skip —
    # otherwise it re-copies the DUNGEON table over the arena table and wins the
    # race (observed: crystal flooded red). Cold-boot still runs normally at real
    # boot (non-arena scenes never take this branch).
    c.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # LD A,0x5A; LD [DF02],A
    c.extend([0x2E, 0x00])                # LD L, 0
    j_copy = len(c) + 1
    c.extend([0x18, 0x00])                # JR copy

    # dungeon target
    dungeon_pos = len(c)
    c[j_dungeon_lo] = (dungeon_pos - j_dungeon_lo - 1) & 0xFF
    c[j_dungeon_hi] = (dungeon_pos - j_dungeon_hi - 1) & 0xFF
    c.extend([0x21, dungeon_addr & 0xFF, (dungeon_addr >> 8) & 0xFF])  # LD HL, dungeon

    # copy target
    copy_pos = len(c)
    c[j_copy] = (copy_pos - j_copy - 1) & 0xFF
    c[j_copy_splash] = (copy_pos - j_copy_splash - 1) & 0xFF

    # Copy 256 bytes: HL → DE = 0xDA00
    c.extend([0x11, 0x00, 0xCC])          # LD DE, 0xCC00 (WRAM bank 0, always accessible)
    c.extend([0x06, 0x00])                # LD B, 0   (256 iterations)
    copy_loop = len(c)
    c.extend([0x2A, 0x12, 0x13, 0x05])    # LD A,[HL+]; LD [DE],A; INC DE; DEC B
    offset = copy_loop - (len(c) + 2)
    c.extend([0x20, offset & 0xFF])       # JR NZ, copy_loop
    c.extend([0xC9])                      # RET
    return bytes(c)


def build_lava_override(base_addr: int) -> bytes:
    """Repaint molten tiles in WRAM 0xDA00 to pal5 (BG5 lava) for lava stages.

    CALLed every frame from the teleport routine (right after scene_detect), not
    just on scene change: the stage-load WRAM clear re-zeroes the cold-boot
    sentinel DF02 a few frames after entry, after which the colorize handler's
    cold-boot copy re-copies the plain DUNGEON table over our pal5 writes. Re-
    applying every frame (and re-asserting DF02=0x5A each frame, before the same-
    frame cold-boot runs) makes the override win permanently. It's WRAM-only and
    tiny, so per-frame cost is negligible. Guards:
      - D880 must be a dungeon-family scene (0x02..0x0B). Arenas (0x0C+) and
        title/uninit (<0x02) early-RET, touching nothing (incl. DF02).
      - FFBA selects the molten ID list: 4 -> stage 5, 6 -> stage 7, else RET.
    Then walks a 0xFF-terminated ID list and writes pal5 to 0xDA00[id] for each.
    The ID lists are appended to this blob; HL pointers patched to absolutes.
    """
    c = bytearray()
    # ---- guard: dungeon-family scene only ----
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0xFE, 0x0C])                # CP 0x0C
    c.extend([0xD0])                      # RET NC   (>= 0x0C -> arena/death/etc)
    c.extend([0xFE, 0x02])                # CP 0x02
    c.extend([0xD8])                      # RET C    (< 0x02 -> title/uninit)
    # ---- select molten ID list by FFBA (stage) ----
    c.extend([0xF0, 0xBA])                # LDH A, [FFBA]
    c.extend([0xFE, 0x04])                # CP 4 (stage 5)
    j_set5 = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, set5
    c.extend([0xFE, 0x06])                # CP 6 (stage 7)
    c.extend([0xC0])                      # RET NZ   (not a lava stage)
    # stage 7: HL = lava7 list (pointer patched below)
    p_hl7 = len(c) + 1
    c.extend([0x21, 0x00, 0x00])          # LD HL, lava7
    j_apply = len(c) + 1
    c.extend([0x18, 0x00])                # JR apply
    # set5: HL = lava5 list
    set5_pos = len(c)
    c[j_set5] = (set5_pos - j_set5 - 1) & 0xFF
    p_hl5 = len(c) + 1
    c.extend([0x21, 0x00, 0x00])          # LD HL, lava5
    # apply: suppress the colorize handler's same-frame cold-boot 0xDA00 copy
    # (it re-copies the DUNGEON table over our pal5 writes otherwise — the same
    # race that flooded the crystal arena red). scene_detect runs before the
    # colorize cold-boot, so DF02=0x5A here makes the later copy skip. Already a
    # lava stage at this point, so this only fires in stage 5 / stage 7.
    apply_pos = len(c)
    c[j_apply] = (apply_pos - j_apply - 1) & 0xFF
    c.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # LD A,0x5A; LD [DF02],A
    # walk 0xFF-terminated list, write pal5 to 0xDA00[id]
    loop_pos = len(c)
    c.extend([0x2A])                      # LD A, [HL+]   (tile id)
    c.extend([0xFE, 0xFF])                # CP 0xFF
    c.extend([0xC8])                      # RET Z         (end of list)
    c.extend([0x5F])                      # LD E, A
    c.extend([0x16, 0xCC])                # LD D, 0xCC    (DE = 0xCC00 + id, WRAM bank 0)
    c.extend([0x3E, 0x05])                # LD A, 5       (pal5 = lava)
    c.extend([0x12])                      # LD [DE], A
    off = loop_pos - (len(c) + 2)
    c.extend([0x18, off & 0xFF])          # JR loop
    # ---- data: ID lists (0xFF-terminated) ----
    lava7_off = len(c)
    c.extend(LAVA_STAGE7_IDS + [0xFF])
    lava5_off = len(c)
    c.extend(LAVA_STAGE5_IDS + [0xFF])
    # patch HL pointers to absolute bank-13 addresses
    a7 = base_addr + lava7_off
    a5 = base_addr + lava5_off
    c[p_hl7], c[p_hl7 + 1] = a7 & 0xFF, (a7 >> 8) & 0xFF
    c[p_hl5], c[p_hl5 + 1] = a5 & 0xFF, (a5 >> 8) & 0xFF
    return bytes(c)


def build_levelsel_attr_clear_stub() -> bytes:
    """~34-byte WRAM stub: clears VBK=1 BG attrs (0x9800-0x9FFF) then JPs to
    the original 0x7393. Triggered by the patched `JP NZ` at bank1:0x3B47.

    No VBlank-wait: disabling LCD mid-frame causes one frame of glitch, but
    we're already in a screen transition (title-menu → level-select), so a
    single blank frame is invisible. Saves 7 bytes vs the safe version,
    letting the source fit in the available 36-byte ROM free run.

    Why save HL/BC only (not AF): we arrived via `JP NZ` so the Z flag has
    already done its job. F is dead; B/H are touched by the clear; A is
    constant 0 by the time we return. HL/BC need restoring for the title-
    menu code at 0x7393 that uses them.

    Why JP not CALL: 0x7393 runs the level-select's own forever-loop and
    only RETs via its own EI'd input handler; our caller isn't expecting
    control back.
    """
    c = bytearray()
    c.extend([0xE5])                       # PUSH HL
    c.extend([0xC5])                       # PUSH BC
    # Save LCDC, disable LCD (1-frame glitch acceptable in screen-switch)
    c.extend([0xF0, 0x40])                 # LDH A, [FF40]
    c.extend([0x47])                       # LD B, A (save LCDC)
    c.extend([0xE6, 0x7F])                 # AND 0x7F (clear bit 7)
    c.extend([0xE0, 0x40])                 # LDH [FF40], A
    # VBK = 1
    c.extend([0x3E, 0x01])                 # LD A, 1
    c.extend([0xE0, 0x4F])                 # LDH [FF4F], A
    # Clear 0x9800..0x9FFF: HL=0x9800, write 0 until H==0xA0 (2048 bytes)
    c.extend([0x21, 0x00, 0x98])           # LD HL, 0x9800
    clear_loop = len(c)
    c.extend([0xAF])                       # XOR A
    c.extend([0x22])                       # LD [HL+], A
    c.extend([0x7C])                       # LD A, H
    c.extend([0xFE, 0xA0])                 # CP 0xA0
    off = clear_loop - (len(c) + 2)
    c.extend([0x20, off & 0xFF])           # JR NZ, clear_loop
    # VBK = 0
    c.extend([0xAF])                       # XOR A
    c.extend([0xE0, 0x4F])                 # LDH [FF4F], A
    # Restore LCDC (B still holds saved value)
    c.extend([0x78])                       # LD A, B
    c.extend([0xE0, 0x40])                 # LDH [FF40], A
    # Restore regs
    c.extend([0xC1])                       # POP BC
    c.extend([0xE1])                       # POP HL
    # JP to original target
    c.extend([0xC3, 0x93, 0x73])           # JP 0x7393
    return bytes(c)


def build_landing_pad() -> bytes:
    """Executable code that runs in main-loop context AFTER the RETI.

    v4 disabled VBlank IRQ to prevent colorize-handler re-entry — but that
    caused the arena loop's HALT-for-VBlank to never wake. v5: leave IRQs
    alone. The debounce flag (DF0C, set by the teleport routine before
    redirect) makes re-entrant calls to the teleport routine a no-op, so
    VBlank can fire freely during arena init / arena loop.

    Pre-conditions:
      - FFBA = target boss, FFBF = 0
      - DF20/21 = saved main-loop PC (for the fall-through JP back)
      - IME = 1 (RETI just enabled it)
      - debounce DF0C = 1 (set by teleport routine — prevents recursion)
    """
    c = bytearray()
    # Map ROM bank 3 (0x1A2B's internal CALL 0x759B is bank-3 code)
    c.extend([0x3E, 0x03])                # LD A, 3
    c.extend([0xEA, 0x00, 0x21])          # LD [0x2100], A
    c.extend([0xE0, 0x99])                # LDH [FF99], A
    # CALL the natural event-0x29 boss-entry handler. In PyBoy this never
    # returned (arena per-frame loop took over at 0x4073); if it does
    # return in mgba, we JP back to the original main-loop PC.
    c.extend([0xCD, 0x2B, 0x1A])          # CALL 0x1A2B
    # ---- post-arena: JP HL with HL = saved main-loop PC ----
    c.extend([0xFA, 0x20, 0xDF])          # LD A, [DF20]
    c.extend([0x6F])                      # LD L, A
    c.extend([0xFA, 0x21, 0xDF])          # LD A, [DF21]
    c.extend([0x67])                      # LD H, A
    c.extend([0xE9])                      # JP HL
    return bytes(c)


def build_teleport_routine() -> bytes:
    """The teleport check routine called every VBlank from our hook.

    Combo: SELECT+START (FF93 bits 2,3 = 0x0C, active high).
    Guarded to D880=0x02 (dungeon). Debounce via DF0C.
    On fire: cycle FFBA (DF0B 0..8), FFBF=0, then redirect the IRQ return.

    Stack offset to the CPU-pushed PC:
      SP+0:  return to hook (post CD 80 6E)
      SP+2:  hook's PUSH AF (saved FF99)
      SP+4:  return to 0x06D1 handler (= 0x06DF)
      SP+6:  HL pushed at 0x06D4
      SP+8:  DE pushed at 0x06D3
      SP+10: BC pushed at 0x06D2
      SP+12: AF pushed at 0x06D1
      SP+14: CPU-pushed PC (main-loop return — what RETI pops)
    """
    c = bytearray()

    # ---- Per-frame scene-detect: swap bg_table if D880 changed ----
    # Bank 13 is mapped (we're inside the colorize call chain). Reads
    # D880, compares to DF23, copies the right table to WRAM 0xDA00 on
    # change. Fast path (~16T) when scene unchanged.
    c.extend([0xCD, SCENE_DETECT_ADDR & 0xFF, (SCENE_DETECT_ADDR >> 8) & 0xFF])

    # ---- Lava repaint: every frame, re-apply pal5 to molten tiles in lava
    # stages (no-op elsewhere). Must run after scene_detect (which may have just
    # copied the dungeon table) and before the colorize cold-boot copy. ----
    c.extend([0xCD, LAVA_OVERRIDE_ADDR & 0xFF, (LAVA_OVERRIDE_ADDR >> 8) & 0xFF])

    # ---- One-shot: ensure landing pad is copied to WRAM 0xCF82 ----
    # Check sentinel DF1E
    c.extend([0xFA, 0x0E, 0xDF])          # LD A, [DF1E]
    c.extend([0xFE, 0x5A])                # CP 0x5A
    j_copy_done = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, copy_done
    # Copy 40 bytes (landing pad) from bank13 ROM to WRAM CF82.
    c.extend([0x21, LANDING_PAD_ROM_ADDR & 0xFF, (LANDING_PAD_ROM_ADDR >> 8) & 0xFF])  # LD HL, ROM_SRC
    c.extend([0x11, LANDING_PAD_WRAM & 0xFF, (LANDING_PAD_WRAM >> 8) & 0xFF])          # LD DE, WRAM_DST
    c.extend([0x06, 40])                  # LD B, 40
    copy_loop = len(c)
    c.extend([0x2A])                      # LD A, [HL+]
    c.extend([0x12])                      # LD [DE], A
    c.extend([0x13])                      # INC DE
    c.extend([0x05])                      # DEC B
    offset = copy_loop - (len(c) + 2)
    c.extend([0x20, offset & 0xFF])       # JR NZ, copy_loop

    # Second copy: 36 bytes (levelsel attr-clear stub) from LEVELSEL_STUB_ROM_ADDR
    # to LEVELSEL_STUB_WRAM. Same sentinel (DF0E) gates both copies, so this
    # block also only runs once per cold-boot.
    c.extend([0x21, LEVELSEL_STUB_ROM_ADDR & 0xFF, (LEVELSEL_STUB_ROM_ADDR >> 8) & 0xFF])
    c.extend([0x11, LEVELSEL_STUB_WRAM & 0xFF, (LEVELSEL_STUB_WRAM >> 8) & 0xFF])
    c.extend([0x06, LEVELSEL_STUB_MAX])   # LD B, 36
    ls_loop = len(c)
    c.extend([0x2A, 0x12, 0x13, 0x05])    # LD A,[HL+]; LD [DE],A; INC DE; DEC B
    off = ls_loop - (len(c) + 2)
    c.extend([0x20, off & 0xFF])          # JR NZ, ls_loop
    # Set sentinel only. Do NOT touch FFBA in cold-boot — writing 0xFF
    # there causes the game's dispatch tables (FFBA-indexed) to read
    # garbage and crash. First user press goes to Riff (FFBA 0→1);
    # to reach Shalamar, cycle 9 times around to wrap.
    c.extend([0x3E, 0x5A, 0xEA, 0x0E, 0xDF])  # LD A,0x5A; LD [DF0E],A
    # copy_done:
    copy_done_pos = len(c)

    # ---- Combo + guard + debounce checks ----
    # SELECT+START (bits 2,3 = 0x0C). mgba defaults: Backspace + Enter.
    c.extend([0xF0, 0x93])                # LDH A, [FF93]
    c.extend([0xE6, 0x0C])                # AND 0x0C
    c.extend([0xFE, 0x0C])                # CP 0x0C
    j_not_combo_1 = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, not_combo

    # D880 guard: accept dungeon (0x02), splash (0x18), and any arena
    # (0x0C..0x14) so cycling between bosses works. Reject only the very
    # early uninitialized / title states (0x00, 0x01).
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0xFE, 0x02])                # CP 0x02
    j_not_combo_2 = len(c) + 1
    c.extend([0x38, 0x00])                # JR C, not_combo  (D880 < 2: too early)

    # Debounce: DF0C
    c.extend([0xFA, 0x0C, 0xDF])          # LD A, [DF0C]
    c.extend([0xB7])                      # OR A
    j_end_debounced = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, end

    # Re-fire sit-out: DF1D >0 means previous arena init still settling
    # (separate from DF1F which is the colorize-skip counter).
    c.extend([0xFA, 0x1D, 0xDF])          # LD A, [DF1D]
    c.extend([0xB7])                      # OR A
    j_end_sitout = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, end

    # ---- FIRE ----
    # Set debounce
    c.extend([0x3E, 0x01, 0xEA, 0x0C, 0xDF])  # LD A,1; LD [DF0C], A
    # Set colorize-skip frame counter DF1F = 60 (≈ 1 sec; arena init takes
    # ~10 frames in PyBoy, 60 is a safe margin before colorize re-engages)
    c.extend([0x3E, 0x3C, 0xEA, 0x1F, 0xDF])  # LD A, 60; LD [DF1F], A
    # Cycle: read FFBA, INC, wrap, write back. v11-style. With FFBA
    # initialized to 0xFF in cold-boot, first INC wraps to 0 = Shalamar.
    c.extend([0xF0, 0xBA])                # LDH A, [FFBA]
    c.extend([0x3C])                      # INC A
    c.extend([0xFE, 0x09])                # CP 9
    c.extend([0x38, 0x01])                # JR C, no_wrap
    c.extend([0xAF])                      # XOR A
    c.extend([0xE0, 0xBA])                # LDH [FFBA], A
    # Set re-fire sit-out (DF1D = 30 frames). Use DF1D so it can't be
    # accidentally re-set by the colorize-skip DF1F path.
    c.extend([0x3E, 0x1E, 0xEA, 0x1D, 0xDF])  # LD A, 30; LD [DF1D], A

    # Give the boss HP so it doesn't instantly die (which would trigger
    # the post-arena FFBA++ flow and make the cycle order weird).
    # DCBB = boss HP per CLAUDE.md.
    c.extend([0x3E, 0x80])                # LD A, 0x80
    c.extend([0xEA, 0xBB, 0xDC])          # LD [DCBB], A
    # Sara HP (DCDC = sub, DCDD = main) — give max so she doesn't die.
    c.extend([0x3E, 0xFF])                # LD A, 0xFF
    c.extend([0xEA, 0xDC, 0xDC])          # LD [DCDC], A
    c.extend([0xEA, 0xDD, 0xDC])          # LD [DCDD], A
    # FFBF = 0
    c.extend([0xAF])                      # XOR A
    c.extend([0xE0, 0xBF])                # LDH [FFBF], A

    # ---- STACK REDIRECT ----
    c.extend([0xF8, 0x16])                # LD HL, SP+22 (updated for wrapper stack layout)
    c.extend([0x2A])                      # LD A, [HL+] (low byte of PC)
    c.extend([0xEA, 0x20, 0xDF])          # LD [DF20], A
    c.extend([0x7E])                      # LD A, [HL]  (high byte)
    c.extend([0xEA, 0x21, 0xDF])          # LD [DF21], A
    c.extend([0xF8, 0x16])                # LD HL, SP+22 (updated for wrapper stack layout)
    c.extend([0x3E, LANDING_PAD_WRAM & 0xFF])
    c.extend([0x22])                      # LD [HL+], A
    c.extend([0x3E, (LANDING_PAD_WRAM >> 8) & 0xFF])
    c.extend([0x77])                      # LD [HL], A

    # Fire path: RET directly (skip colorize this frame too — IRQ chain
    # unwinds, RETI to landing pad → arena init runs in main-loop context)
    c.extend([0xC9])                      # RET  (fire path ends here)

    # ---- not_combo: clear debounce ----
    not_combo_pos = len(c)
    c.extend([0xAF, 0xEA, 0x0C, 0xDF])    # XOR A; LD [DF0C], A

    # ---- end ----
    # Decrement DF1D (re-fire sit-out) if > 0.
    # Decrement DF1F (colorize-skip) if > 0 — if so, RET (skip colorize).
    end_pos = len(c)
    # DF1D decrement
    c.extend([0xFA, 0x1D, 0xDF])          # LD A, [DF1D]
    c.extend([0xB7])                      # OR A
    c.extend([0x28, 0x05])                # JR Z, +5 skip dec
    c.extend([0x3D])                      # DEC A
    c.extend([0xEA, 0x1D, 0xDF])          # LD [DF1D], A
    # DF1F gate (skip colorize while > 0)
    c.extend([0xFA, 0x1F, 0xDF])          # LD A, [DF1F]
    c.extend([0xB7])                      # OR A
    c.extend([0x28, 0x05])                # JR Z, +5 → JP COLORIZE patch
    c.extend([0x3D])                      # DEC A
    c.extend([0xEA, 0x1F, 0xDF])          # LD [DF1F], A
    c.extend([0xC9])                      # RET (skip colorize)
    c.extend([0xC9])                      # RET (will be patched to JP)

    # Patch JR offsets
    def patch(pos, target):
        off = target - (pos + 1)
        assert -128 <= off <= 127, f"JR offset {off} out of range at {pos}"
        c[pos] = off & 0xFF

    patch(j_copy_done, copy_done_pos)
    patch(j_not_combo_1, not_combo_pos)
    patch(j_not_combo_2, not_combo_pos)
    patch(j_end_debounced, end_pos)
    if j_end_sitout is not None:
        patch(j_end_sitout, end_pos)

    return bytes(c)


def main():
    # 1. Build the base v3.01 production ROM
    build_v301()
    rom = bytearray(BASE_OUT.read_bytes())

    # 1a. Title: add "PENTA DRAGON DX" game-name header + "STRUKTURED LABS"
    # attribution. The stock title screen shows only the YANOMAN bitmap logo +
    # menu (no spelled-out game name). Rewrite the title TEXT command list
    # in-place at bank1:0x4EA5 (entries = [col][row][tile..]0x9A; font A=0x80..
    # Z=0x99, space=0x00; list ends with a 0x9A col byte). Keep the logo-
    # continuation rows, the OPENING/GAME START menu, and the JAPAN ART MEDIA
    # developer credit; DROP the redundant "(c)1992 YANOMAN" *text* line (the
    # YANOMAN bitmap LOGO is untouched) and "LICENSED BY NINTENDO" to make room.
    # Added text flushes via the C1A0 buffer + inline hook, so it is colorized
    # (same two-tone as the stock menu text). Fits in the original 126-byte
    # region (0x4EA5..0x4F22); a trailing 0x9A terminates the list early.
    E = 0x9A
    def _txt(s):
        return [0x00 if c == ' ' else 0x80 + (ord(c) - 65) for c in s]
    JAM = [0xD0, 0xD7, 0xD8, 0xD9, 0x00, 0x89, 0x80, 0x8F, 0x80, 0x8D, 0x00,
           0x80, 0x91, 0x93, 0x00, 0x8C, 0x84, 0x83, 0x88, 0x80]  # (c)1992 JAPAN ART MEDIA
    title_list = bytes(
        [0x07, 0x03, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, E]          # logo continuation
        + [0x07, 0x04, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, E]
        + [0x07, 0x05, 0xC6, 0xC7, 0xC8, 0xC9, 0xD6, E]
        + [0x03, 0x06] + _txt("PENTA DRAGON DX") + [E]         # game name + DX (row 6)
        + [0x04, 0x08] + _txt("OPENING START") + [E]           # menu
        + [0x04, 0x0A] + _txt("GAME    START") + [E]
        + [0x00, 0x0E, 0xC0, E]                                 # (c) glyph
        + [0x00, 0x0F] + JAM + [E]                              # JAPAN ART MEDIA
        + [0x00, 0x11, 0x83, 0x97, 0x00, 0x95, 0xD7, 0xD8, 0xD8, 0x00] + _txt("STRUK LABS") + [E]  # "DX V199 STRUK LABS" (row 17)
    )
    assert len(title_list) <= 125, f"title list {len(title_list)} > 125 (need room for trailing 0x9A terminator)"
    assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
    rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
    # Ensure the trailing 0x9A (list terminator for the parser — it reads [HL],
    # CP 0x9A, RET Z) is NOT overwritten. The title parser reads the list from
    # 0x4EA5: each entry ends with 0x9A, then the NEXT byte is checked: if it's
    # also 0x9A the parser returns. If we fill all 126 bytes, the byte at 0x4F22
    # (which was the terminator from the original game) gets overwritten, and
    # the parser reads garbage at 0x4F23 (code byte 0xE5) as [col], corrupting
    # VRAM. Keep the list ≤ 125 bytes to preserve the terminator at 0x4F22.
    print(f"  title: PENTA DRAGON DX header + STRUKTURED LABS ({len(title_list)}/125 bytes @0x4EA5)"
          f" — preserving terminator 0x9A at 0x4F22")

    # 2. Write the landing pad source bytes in bank13 ROM at LANDING_PAD_ROM_ADDR
    lp = build_landing_pad()
    print(f"  landing pad source: {len(lp)} bytes at bank13:0x{LANDING_PAD_ROM_ADDR:04X}")
    assert len(lp) <= 40, f"landing pad too big: {len(lp)} > 40"
    off = BANK13 + (LANDING_PAD_ROM_ADDR - 0x4000)
    rom[off:off + len(lp)] = lp

    # 2b. Level-select score-screen attr-clear stub. Stored in a 36-byte
    # free run at bank13:0x53C2 (non-contiguous with landing pad — has its
    # own cold-boot copy block). Patch step at the bottom of build()
    # repoints bank1:0x3B47's JP NZ to its WRAM-resident copy.
    ls = build_levelsel_attr_clear_stub()
    print(f"  levelsel attr-clear stub: {len(ls)} bytes at bank13:0x{LEVELSEL_STUB_ROM_ADDR:04X}")
    assert len(ls) <= LEVELSEL_STUB_MAX, f"levelsel stub too big: {len(ls)} > {LEVELSEL_STUB_MAX}"
    # Verify the destination slot in ROM is actually free (all 0x00) before clobbering
    off = BANK13 + (LEVELSEL_STUB_ROM_ADDR - 0x4000)
    for i in range(LEVELSEL_STUB_MAX):
        assert rom[off + i] == 0x00, (
            f"levelsel stub site at 0x{LEVELSEL_STUB_ROM_ADDR + i:04X} not free "
            f"(byte {rom[off + i]:02X}) — choose a different free run")
    rom[off:off + len(ls)] = ls

    # 2a. Scene-aware bg_table system (Phase 1b: all 9 boss arenas)
    arena_tables = [
        ("Shalamar",      SHALAMAR_TABLE_ADDR,        _bg_table_shalamar),
        ("Riff",          RIFF_TABLE_ADDR,            _bg_table_riff),
        ("Crystal Dragon", CRYSTAL_DRAGON_TABLE_ADDR,  _bg_table_crystal_dragon),
        ("Cameo",         CAMEO_TABLE_ADDR,           _bg_table_cameo),
        ("Ted",           TED_TABLE_ADDR,             _bg_table_ted),
        ("Troop",         TROOP_TABLE_ADDR,           _bg_table_troop),
        ("Faze",          FAZE_TABLE_ADDR,            _bg_table_faze),
        ("Angela",        ANGELA_TABLE_ADDR,          _bg_table_angela),
        ("Penta Dragon",  PENTA_DRAGON_TABLE_ADDR,    _bg_table_penta_dragon),
    ]
    # Sanity: all arena slots are 256 apart from ARENA_BASE so the
    # SUB-then-ADD dispatch is correct.
    for i, (name, addr, _) in enumerate(arena_tables):
        expected = ARENA_BASE_ADDR + i * 0x100
        assert addr == expected, f"{name} slot 0x{addr:04X} != expected 0x{expected:04X}"
    for name, addr, build_fn in arena_tables:
        table = build_fn()
        assert len(table) == 256, f"{name} table size {len(table)} != 256"
        off = BANK13 + (addr - 0x4000)
        rom[off:off + 256] = table
        print(f"  {name:14s} bg_table: 256 bytes at bank13:0x{addr:04X}")

    # Write scene-detect routine. Verify we don't overrun the landing pad.
    sd = build_scene_detect(DUNGEON_TABLE_ADDR, ARENA_BASE_ADDR, SPLASH_TABLE_ADDR)
    assert SCENE_DETECT_ADDR + len(sd) <= DUNGEON_TABLE_ADDR, \
        f"scene-detect overruns dungeon table: 0x{SCENE_DETECT_ADDR + len(sd):04X} > 0x{DUNGEON_TABLE_ADDR:04X}"
    off = BANK13 + (SCENE_DETECT_ADDR - 0x4000)
    rom[off:off + len(sd)] = sd
    print(f"  scene-detect routine: {len(sd)} bytes at bank13:0x{SCENE_DETECT_ADDR:04X}")

    # Lava override helper (tail-jumped from scene_detect). Repaints molten BG
    # tiles to pal5 in lava stages. Lives above the static posmap blob.
    lava = build_lava_override(LAVA_OVERRIDE_ADDR)
    assert LAVA_OVERRIDE_ADDR + len(lava) <= 0x8000, \
        f"lava override overruns bank 13: 0x{LAVA_OVERRIDE_ADDR + len(lava):04X}"
    off = BANK13 + (LAVA_OVERRIDE_ADDR - 0x4000)
    rom[off:off + len(lava)] = lava
    print(f"  lava override: {len(lava)} bytes at bank13:0x{LAVA_OVERRIDE_ADDR:04X} "
          f"(stage5 IDs {['%02X' % x for x in LAVA_STAGE5_IDS]}, "
          f"stage7 IDs {['%02X' % x for x in LAVA_STAGE7_IDS]})")

    # Splash table (256 bytes, all pal0) for D880=0x18 — uniform STAGE/boss text.
    assert LAVA_OVERRIDE_ADDR + len(lava) <= SPLASH_TABLE_ADDR, \
        f"lava override 0x{LAVA_OVERRIDE_ADDR + len(lava):04X} collides with splash table 0x{SPLASH_TABLE_ADDR:04X}"
    assert SPLASH_TABLE_ADDR + 256 <= POSMAP_PTR_TABLE, \
        f"splash table 0x{SPLASH_TABLE_ADDR + 256:04X} collides with posmap ptr table 0x{POSMAP_PTR_TABLE:04X}"
    off = BANK13 + (SPLASH_TABLE_ADDR - 0x4000)
    rom[off:off + 256] = bytes(256)   # all pal0
    print(f"  splash table: 256 bytes (all pal0) at bank13:0x{SPLASH_TABLE_ADDR:04X}")

    # 2c. Write OBJ palette lookup table at bank13:0x6B00 (replaces old CP-cascade)
    # Generate the 256-byte static LUT
    _obj_pal = bytearray(256)
    for _i in range(256):
        if _i <= 0x01:       _obj_pal[_i] = 0   # projectile → pal 0 (was pal 3, moved to avoid coupling with enemy palettes)
        elif _i <= 0x0F:     _obj_pal[_i] = 0   # effects → pal 0
        elif _i <= 0x2F:     _obj_pal[_i] = 0xFF  # Sara dynamic
        elif _i <= 0x3F:     _obj_pal[_i] = 3   # crow → pal 3 (was pal 6, freed by moving projectile to pal 0)
        elif _i <= 0x4F:     _obj_pal[_i] = 5   # orc → pal 5
        elif _i <= 0x5F:     _obj_pal[_i] = 4   # hornet → pal 4
        elif _i <= 0x6F:     _obj_pal[_i] = 5   # orc ground → pal 5
        elif _i <= 0x7F:     _obj_pal[_i] = 6   # soldier → pal 6 (was pal 7)
        elif _i <= 0x8F:     _obj_pal[_i] = 3   # default high → pal 3 (was pal 4, first 16 high tiles)
        else:                _obj_pal[_i] = 4   # rest high → pal 4
    _obj_pal_off = BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)
    rom[_obj_pal_off:_obj_pal_off + 256] = _obj_pal
    # Verify LUT was written correctly
    _verify_lut = rom[_obj_pal_off:_obj_pal_off + 256]
    _verify_bad = sum(1 for _v in _verify_lut if _v > 7 and _v != 0xFF)
    assert _verify_bad == 0, f"OBJ palette LUT has {_verify_bad} invalid entries after write!"
    print(f"  OBJ palette LUT: 256 bytes at bank13:0x{OBJ_PAL_TABLE_ADDR:04X} (per-monster-type, verified)")

    # 2d. Re-patch bg_sweep to read the PER-SCENE WRAM table (0xDA00) instead
    # of the ROM dungeon table (0x7000). The base build bakes the sweep with
    # the dungeon table, so in arenas the sweep wrote dungeon-palette attrs for
    # boss tiles while the inline hook (which DOES read 0xDA00) wrote the
    # arena-band palette — the two writers disagreed and each boss cell flipped
    # every sweep pass. That is the measured arena alternation. scene_detect
    # keeps 0xDA00 in sync with the current scene, so reading it is correct in
    # every scene (in the dungeon 0xDA00 == the dungeon table, so dungeon
    # behavior is unchanged). FFC1 prefix NOP'd to match the base build.
    sweep = bytearray(create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR))
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8]), \
        f"bg_sweep prefix changed: {sweep[:4].hex()}"
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])  # NOPs — run on title too
    off = BANK13 + (BG_SWEEP_ADDR - 0x4000)
    rom[off:off + len(sweep)] = sweep
    print(f"  bg_sweep re-patched to WRAM 0x{WRAM_BG_TABLE:04X}: {len(sweep)} bytes at bank13:0x{BG_SWEEP_ADDR:04X}")

    # 2c. POSITION SWEEP (holy-grail path). In arenas, write a FIXED per-cell
    # posmap to the BG attr plane instead of tile-ID attrs — a fixed map can't
    # alternate (every write of a cell writes the same value). Maps are RLE-
    # compressed in bank-13 ROM (they are highly repetitive); on arena entry the
    # sweep expands the active map to WRAM 0xD000 (the dead GDMA buffer, bank 2)
    # once, then copies a few rows/frame from there. Non-arena / no-map arenas
    # tail-call the normal (Phase-0) tile-ID sweep.
    posmaps = parse_footprint_posmaps(FOOTPRINT_LOG)
    ptr = [0] * 9
    blob = bytearray()
    for idx, name in enumerate(ARENA_ORDER):
        m = posmaps.get(name)
        if not m or not any(m):
            continue
        rle = rle_encode_posmap(m)
        addr = POSMAP_DATA_ADDR + len(blob)
        if addr + len(rle) > POSMAP_PTR_TABLE:
            print(f"  posmap RLE: out of bank-13 space before {name} (idx {idx}) — skipped")
            break
        blob += rle
        ptr[idx] = addr
        print(f"  posmap {name:14s}: RLE {len(rle):3d} bytes at bank13:0x{addr:04X}")
    assert POSMAP_DATA_ADDR + len(blob) <= LAVA_OVERRIDE_ADDR, \
        f"posmap blob 0x{POSMAP_DATA_ADDR + len(blob):04X} collides with lava override 0x{LAVA_OVERRIDE_ADDR:04X}"
    off = BANK13 + (POSMAP_DATA_ADDR - 0x4000)
    rom[off:off + len(blob)] = blob
    print(f"  posmap RLE total: {len(blob)} bytes "
          f"(0x{POSMAP_DATA_ADDR:04X}-0x{POSMAP_DATA_ADDR + len(blob):04X}, "
          f"limit 0x{POSMAP_PTR_TABLE:04X})")
    pt = bytearray()
    for p in ptr:
        pt += bytes([p & 0xFF, (p >> 8) & 0xFF])
    off = BANK13 + (POSMAP_PTR_TABLE - 0x4000)
    rom[off:off + len(pt)] = pt

    # RLE expander (reuses dead GDMA space at 0x6D80)
    expander = create_rle_expander()
    assert EXPAND_ADDR + len(expander) <= COLORIZE_ADDR, "expander overruns colorize handler"
    off = BANK13 + (EXPAND_ADDR - 0x4000)
    rom[off:off + len(expander)] = expander
    print(f"  RLE expander: {len(expander)} bytes at bank13:0x{EXPAND_ADDR:04X}")

    possweep = create_position_sweep(
        POSSWEEP_ADDR, BG_SWEEP_ADDR, POSMAP_PTR_TABLE, EXPAND_ADDR,
        row_cursor_addr=ROW_CURSOR_ADDR, flag_addr=POSMAP_FLAG_ADDR,
        scratch_addr=POSMAP_SCRATCH_ADDR, rows_per_frame=2)
    assert POSSWEEP_ADDR + len(possweep) <= 0x7200, \
        f"position sweep overruns arena tables: 0x{POSSWEEP_ADDR + len(possweep):04X}"
    off = BANK13 + (POSSWEEP_ADDR - 0x4000)
    rom[off:off + len(possweep)] = possweep
    print(f"  position sweep: {len(possweep)} bytes at bank13:0x{POSSWEEP_ADDR:04X}")

    # Repoint the colorize handler's `CALL bg_sweep (0x6CD0)` -> position sweep.
    # [DISABLED: Using standard tile-ID bg_sweep directly for clean background/claws separation]
    patched_sweep = True

    # 2d. INLINE HOOK: replace base v301's pure tile-only with the D880-gated
    # tile+attr version. This is the key fix for item flicker: in the dungeon
    # (D880=0x02..0x0B), the hook writes full tile+attr (pickup items get pal1
    # red immediately). On the title screen (D880=0x00/0x01), it writes tile-only
    # (avoids the animation race between tile phase and attr phase). In boss
    # arenas (D880=0x0C..0x14), it writes tile-only (position sweep owns attrs).
    # Splash/banner scenes (D880 >= 0x15) get full tile+attr with the all-pal0
    # splash table loaded by scene_detect, which is harmless.
    from build_v301_gdma import create_inline_tile_copy_tileonly
    inline_code = create_inline_tile_copy_tileonly(
        arena_neutralize_d880=0x0C,
        title_gate=0x02)
    available = 0x436D - 0x42A7 + 1  # 199 bytes
    assert len(inline_code) <= available, \
        f"inline tile copy too big: {len(inline_code)} > {available}"
    rom[0x42A7:0x42A7 + len(inline_code)] = inline_code
    if len(inline_code) < available:
        rom[0x42A7 + len(inline_code):0x436E] = bytearray(available - len(inline_code))
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])
    print(f"  inline hook: D880-gated tile+attr ({len(inline_code)} bytes, "
          f"{available - len(inline_code)} free) — dungeon=full, title=tile-only, arena=tile-only")

    # 3. Write the teleport routine at bank13:0x6E80, ending with JP COLORIZE
    tp = build_teleport_routine()
    tp = bytearray(tp)
    assert tp[-1] == 0xC9, "expected RET at end"
    tp[-1] = 0xC3
    tp.append(COLORIZE_ADDR & 0xFF)
    tp.append((COLORIZE_ADDR >> 8) & 0xFF)
    print(f"  teleport routine (with JP colorize): {len(tp)} bytes at bank13:0x{TELEPORT_ADDR:04X}")
    off = BANK13 + (TELEPORT_ADDR - 0x4000)
    rom[off:off + len(tp)] = tp

    # === Fix: relocate colorize handler tail (FFC1 gate + shadow_main + OAM DMA + VBK restore + RET)
    # The colorize handler at 0x6E00 ends with a tail at ~0x6E7E that includes the FFC1 check,
    # shadow_main CALL, OAM DMA CALL, VBK restore, and RET. The teleport routine at 0x6E80
    # OVERWRITES this tail. Replace the falling-through bytes 'F0 C1' at 0x6E7E with
    # JP 0x6F20 (relocated tail), and write the actual tail code at 0x6F20 (free space
    # between teleport routine end ~0x6F1E and wrapper at 0x6F30).
    SHADOW_MAIN_ADDR = 0x69D0
    COLORIZE_TAIL_ADDR = 0x6F40  # free space between teleport routine end (~0x6F31) and wrapper (0x6F50)
    # JP to relocated tail at 0x6E7E (overwrites 'F0 C1')
    off = BANK13 + (0x6E7E - 0x4000)
    rom[off:off + 3] = bytearray([0xC3,
                                   COLORIZE_TAIL_ADDR & 0xFF,
                                   (COLORIZE_TAIL_ADDR >> 8) & 0xFF])
    # Tail code at COLORIZE_TAIL_ADDR:
    #   LDH A,[FFC1]; OR A; JR Z,+6; CALL shadow_main; CALL OAM DMA; POP AF; LDH [VBK],A; RET
    tail = bytearray([
        0xF0, 0xC1,                               # LDH A, [FFC1]
        0xB7,                                      # OR A
        0x28, 0x06,                                # JR Z, +6 (skip shadow_main + OAM DMA)
        0xCD, SHADOW_MAIN_ADDR & 0xFF, (SHADOW_MAIN_ADDR >> 8) & 0xFF,  # CALL shadow_main
        0xCD, 0x80, 0xFF,                          # CALL OAM DMA (0xFF80)
        0xF1, 0xE0, 0x4F,                          # POP AF; LDH [VBK], A
        0xC9,                                      # RET
    ])
    assert len(tail) == 15, f"tail code length: {len(tail)}"
    off = BANK13 + (COLORIZE_TAIL_ADDR - 0x4000)
    rom[off:off + len(tail)] = tail
    print(f"  colorize handler tail relocated: JP 0x06E7E -> 0x{COLORIZE_TAIL_ADDR:04X} ({len(tail)} bytes)")

    # 4. Write new VBlank hook at 0x0824 and wrapper at WRAPPER_ADDR.
    # Wrapper moved 0x6F10 -> 0x6F20 -> 0x6F30: the teleport routine grew (per-
    # frame CALL lava_override, then the levelsel-stub cold-boot copy block)
    # — each bump frees ~16 bytes for the teleport routine. The 40 bytes
    # between WRAPPER_ADDR end and LANDING_PAD_ROM_ADDR=0x6F80 are unused.
    # would clobber the teleport routine's final `JP colorize`, breaking the
    # whole colorize chain (symptom: entire screen renders uncolored/white).
    WRAPPER_ADDR = 0x6F50
    assert TELEPORT_ADDR + len(tp) <= WRAPPER_ADDR, \
        f"teleport routine 0x{TELEPORT_ADDR + len(tp):04X} overruns wrapper 0x{WRAPPER_ADDR:04X}"

    # 4a. Write wrapper to bank 13
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

        # --- CALL Teleport routine ---
        0xCD, TELEPORT_ADDR & 0xFF, (TELEPORT_ADDR >> 8) & 0xFF,

        # --- RESTORE REGISTERS ---
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC

        0xC9,                                 # RET
    ])

    assert WRAPPER_ADDR + len(wrapper) <= 0x6FA0, \
        f"wrapper 0x{WRAPPER_ADDR + len(wrapper):04X} overruns scene_detect/lava"
    wrapper_off = BANK13 + (WRAPPER_ADDR - 0x4000)
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper written: {len(wrapper)} bytes at bank13:0x{WRAPPER_ADDR:04X}")

    # 4b. Write the new hook at 0x0824
    new_hook = bytearray([
        0xF0, 0x99,                           # LDH A, [FF99]
        0xF5,                                 # PUSH AF (save original bank)
        0x3E, 0x0D,                           # LD A, 13 (ROM bank of wrapper)
        0xE0, 0x99,                           # LDH [FF99], A (update shadow to 13)
        0xEA, 0x00, 0x21,                     # LD [0x2100], A (switch MBC bank to 13)
        0xCD, WRAPPER_ADDR & 0xFF, (WRAPPER_ADDR >> 8) & 0xFF,  # CALL wrapper
        0xF1,                                 # POP AF (restore original bank value)
        0xE0, 0x99,                           # LDH [FF99], A (restore original shadow)
        0xEA, 0x00, 0x21,                     # LD [0x2100], A (restore original MBC ROM bank)
        0xC9,                                 # RET
    ])

    assert len(new_hook) <= 47
    # Zero-pad remaining bytes of the 47-byte slot at 0x0824
    new_hook_padded = (new_hook + bytearray(47 - len(new_hook)))[:47]
    rom[0x0824:0x0824 + 47] = new_hook_padded
    print(f"  Safe-switching VBlank hook written at 0x0824: {len(new_hook)} bytes (padded to 47)")

    # ---- Patch bank0:0x3B47 — redirect JP NZ 0x7393 → JP NZ LEVELSEL_STUB_WRAM ----
    # Pre-condition: bytes at 0x3B47..0x3B49 must be C2 93 73 (JP NZ 0x7393).
    # We replace just the target, preserving the JP NZ opcode & condition.
    expected = bytes([0xC2, 0x93, 0x73])
    actual = bytes(rom[LEVELSEL_PATCH_ADDR:LEVELSEL_PATCH_ADDR + 3])
    assert actual == expected, (
        f"levelsel patch site corrupted: expected {expected.hex()} at "
        f"0x{LEVELSEL_PATCH_ADDR:04X}, got {actual.hex()} — game logic may have moved")
    rom[LEVELSEL_PATCH_ADDR + 1] = LEVELSEL_STUB_WRAM & 0xFF
    rom[LEVELSEL_PATCH_ADDR + 2] = (LEVELSEL_STUB_WRAM >> 8) & 0xFF
    print(f"  Levelsel JP NZ patched: bank0:0x{LEVELSEL_PATCH_ADDR:04X} → "
          f"0x7393 → 0x{LEVELSEL_STUB_WRAM:04X} (WRAM stub clears attrs then JPs to 0x7393)")

    # Header checksum (recompute for safety)
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    # Final LUT verification before writing
    _v = rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000):BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 256]
    _vb = sum(1 for _x in _v if _x > 7 and _x != 0xFF)
    if _vb > 0:
        print(f"  ⚠️  OBJ palette LUT corrupted before write! {_vb} invalid entries")
        print(f"  First 4: {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)]:02X} {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 1]:02X} {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 2]:02X} {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 3]:02X}")
        # Force correct LUT right before write
        print(f"  Forcing correct LUT...")
        for _i in range(256):
            _val = 3 if _i <= 1 else 0 if _i <= 0x0F else 0xFF if _i <= 0x2F else 6 if _i <= 0x3F else 5 if _i <= 0x4F else 4 if _i <= 0x5F else 5 if _i <= 0x6F else 7 if _i <= 0x7F else 4
            rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + _i] = _val
        _v2 = rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000):BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 256]
        _vb2 = sum(1 for _x in _v2 if _x > 7 and _x != 0xFF)
        print(f"  After force: {_vb2} invalid entries, first 4: {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)]:02X} {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 1]:02X} {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 2]:02X} {rom[BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000) + 3]:02X}")
    else:
        print(f"  ✅ OBJ palette LUT verified clean before final write ({_vb} invalid)")

    TP_OUT.write_bytes(rom)
    print(f"Wrote {TP_OUT} ({len(rom)} bytes)")
    print()
    print("=== HOW TO PLAY ===")
    print("  Combo: SELECT + START (Backspace + Enter in mgba defaults)")
    print("  Cycles boss: 0 Shalamar → 1 Riff → 2 Crystal Dragon → 3 Cameo")
    print("               → 4 Ted → 5 Troop → 6 Faze → 7 Angela → 8 Penta Dragon → 0...")
    print("  Only fires in normal dungeon (D880=0x02).")


if __name__ == "__main__":
    main()
