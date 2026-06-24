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
     to WRAM 0xDB00 (which is executable on CGB). Sentinel: DF0E = 0x5A.
  2. Teleport routine (called every VBlank from our hook): detect combo,
     debounce, cycle boss counter, set FFBA/FFBF. Then modify the stack:
       - Read the CPU-pushed PC at SP+14 (main-loop return), save to DF20/21.
       - Overwrite SP+14 with 0xDB00 (landing pad address).
     RET normally.
  3. The IRQ chain unwinds: our routine RETs → hook tail RETs → 0x06D1
     pops its 4 saved regs → RETI. CPU pops the modified PC (= 0xDB00),
     execution resumes at the landing pad — in MAIN-LOOP context (IME=1).
  4. Landing pad at DB00: disables VBlank IRQ (so the colorize handler
     can't re-enter the teleport), keeps other IRQs, maps bank 3, EIs,
     CALLs 0x1A2B (proven safe in main-loop context). If 0x1A2B returns,
     restore IE and JP the saved main-loop PC.

WRAM allocation (DF0E + DF20-DF22):
  DF0E — landing pad / stub copy sentinel (0x5A = copied);
         shared across landing-pad, levelsel-stub, and STAT-stub
         copy blocks so the cold-boot section runs once.
  DF20/21 — saved main-loop PC low/high (for the JP back)
  DF22 — saved IE
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_v301_gdma import build_v301, create_inline_tile_copy_tileonly
from build_v296_phantomsafe import create_bg_sweep_viewport_gated
from arena_position import (
    parse_footprint_posmaps, rle_encode_posmap, create_rle_expander,
    create_position_sweep,
)

BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
TP_OUT = Path("rom/working/penta_dragon_dx_teleport.gb")

BANK13 = 13 * 0x4000
COLORIZE_ADDR = 0x6E00
BG_SWEEP_ADDR = 0x6CD0     # bg_sweep safety-net (re-patched to read WRAM 0xDA00)
WRAM_BG_TABLE = 0xDA00     # per-scene table kept current by scene_detect

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
TELEPORT_ADDR = 0x6E80     # teleport check + state setup + stack redirect
LANDING_PAD_ROM_ADDR = 0x6F80  # landing pad source (gets copied to WRAM DB00)
                              # — moved from 0x6F00 because the teleport
                              # routine grew past 128 bytes and was
                              # overwriting the landing pad source.
LANDING_PAD_WRAM = 0xDB00      # runtime landing pad location
# Level-select score-screen attr-clear stub. The game's GAME-START path
# (DCFD != 0) JPs to bank1:0x7393 which runs its own DI'd input loop, so our
# VBlank colorizer is dark while shown. Stale attrs from earlier screens
# bleed (orange/red). Patch the JP NZ at bank1:0x3B47 to point HERE instead;
# this stub clears VBK=1 attrs at 0x9800-0x9FFF (LCD-off, fast), then JPs
# to the original 0x7393. Diagnosed in commit 306f73e / docs/audit/levelselect_score_bleed.md.
LEVELSEL_STUB_ROM_ADDR = 0x53C2  # 36-byte free run in bank 13 (not contiguous
                                 # with landing pad — separate cold-boot copy)
LEVELSEL_STUB_WRAM = 0xDB28      # 0xDB00 + 40 — right after landing pad in WRAM
LEVELSEL_PATCH_ADDR = 0x3B47     # bank0 (always-mapped); JP NZ target
LEVELSEL_STUB_MAX = 36           # size cap (the free run is 36 bytes)

# ---- STAT IRQ WRAM stub (fixes Sara slot-1 alternation in boss fights) ----
# Iteration 9 plan: relocate the STAT prelude to WRAM with an FFBF != 0
# gate so dungeon scenes (where the iteration-8 prelude introduced a
# parallax-scroll timing side-effect that broke sara_w_alone) are NOT
# affected. Boss scenes (FFBF != 0) see the prelude — alternation fixed.
#
# Cold-boot copy from ROM bank 13 (free at 0x53F2) to WRAM (0xDB50, right
# after the levelsel stub). WRAM is always-mapped → IRQ vector at 0x0048
# can JP into WRAM. The stub ends with a hard JP 0x0853 to chain to the
# original game STAT handler (parallax scroll).
STAT_STUB_ROM_ADDR = 0x53F2      # bank 13, 36 bytes free
STAT_STUB_WRAM = 0xDB50          # 0xDB28 + 40 — right after levelsel stub
STAT_STUB_MAX = 36               # cap (matches the 36-byte free run at 0x53F2)
STAT_IRQ_VECTOR_LO_BYTE = 0x0049 # low byte of "JP nn" at 0x0048

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
# Post-DMA HW-OAM recolor (items 3,4,6,11): enemies render OBJ pal0 (blue/black)
# because the colorizer assigns the right palette in the SHADOW buffer but the
# game's main-loop OAM rebuild + the double-buffer DMA leave the DISPLAYED HW OAM
# at pal0. This routine runs in the wrapper AFTER colorize+DMA and re-stamps the
# palette bits of HW OAM (0xFE00) by tile range, reusing the existing colorizer
# at 0x6A10. mGBA-verified only; VBlank-budget/hardware risk -> teleport build
# (opt-in branch) only. See docs/audit/obj_enemy_color_race.md.
HWOAM_RECOLOR_ADDR = 0x6B27       # iter 278e: pure relocation test (same 49-byte routine at new addr)
# Banner colorize override (showcase, D880=0x1B). Per-monster preview is
# infeasible (the cycled names are a shared font, no monster sprites), so this
# just gives the title banner intentional colors: "PENTA DRAGON" art (0xE0-0xFF)
# -> p4 cyan (NO red, so it can't re-trigger the old red-bands complaint), monster
# name glyphs (0x80-0x99) -> p5 gold, JAM logo (0xCA-0xCF/0xDA-0xDE) -> p1 red.
# Patches 0xDA00 (loaded all-p0 by scene_detect at 0x1B) every frame at 0x1B.
BANNER_OVERRIDE_ADDR = 0x7F70
# Intro cutscene overlay (D880=0x15: opening "treasure scroll", "Sara face closeup",
# "dragon eyes", and Japanese-text textbox panels — all share one D880 value, per
# the 2026-06-15 cutscene probe). The dungeon table's 0x80-0xDF->pal1 (red font)
# rule floods every panel red. This overlay (called every frame from teleport)
# patches the WRAM bg_table after scene_detect's copy: textbox border (0x6B-0x72)
# -> pal4 cyan, font glyphs + Sara portrait band (0x80-0xC9) -> pal2 warm beige
# (legible on white textbox AND reads as skin tones for Sara's portrait), dragon-
# eye highlights (0xF0-0xFF) -> pal1 red. Scroll/brick low-band art (0x10-0x4F)
# -> pal3 parchment/gold (matches the cap-110 scroll). No-op at other scenes.
CUTSCENE_OVERRIDE_ADDR = 0x7FB0   # right after BANNER_OVERRIDE (~63 bytes ends 0x7FB0 incl. burst-sweep loop)
OBJ_COLORIZER_ADDR = 0x6A10      # create_tile_based_colorizer install addr (gdma)
BOSS_SLOT_TABLE_ADDR = 0x68C0    # boss_slot_addr (gdma)
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
    c.extend([0x11, 0x00, 0xDA])          # LD DE, 0xDA00
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
    c.extend([0x16, 0xDA])                # LD D, 0xDA    (DE = 0xDA00 + id)
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


def build_stat_irq_wram_stub() -> bytes:
    """WRAM-resident STAT IRQ prelude that runs ONLY in boss scenes (FFBF != 0)
    to re-stamp OAM slot 1 attr with Sara's correct form palette.

    Iteration 8 demonstrated that an unconditional ROM-resident prelude
    (at 0x0838, falling through to 0x0853) introduced a ~30-cycle delay
    that shifted the chained parallax-scroll handler's SCY/SCX writes,
    which exposed a slot 0/2 transient pal-4 read in dungeon scenes
    (sara_w_alone OAM dump failed even though LCD rendered correctly).

    Solution: relocate to WRAM (size-unconstrained), add an FFBF gate so
    the work only runs when there's actually a boss to fight. Dungeon
    scenes (FFBF=0) take a fast-path that just chains to the original
    handler with no timing impact.

    Ends with JP 0x0853 (hard jump, not fall-through, because WRAM and
    ROM are different address spaces).
    """
    c = bytearray()
    # Iteration 10 conclusion: ungated WRAM stub achieves the Sara slot-1
    # alternation fix (gargoyle pal-6 frequency drops 62% → 0.13%) WITHOUT
    # the parallax-scroll timing regression that the iteration-8 ROM-
    # resident prelude caused. The WRAM placement avoids the timing impact
    # somehow (possibly because WRAM access is consistent across modes,
    # vs ROM bank-0 having different timing). sara_w_alone still passes.
    c.extend([0xF5])              # PUSH AF
    c.extend([0xC5])              # PUSH BC
    c.extend([0xF0, 0xBE])        # LDH A, [FFBE]
    c.extend([0xB7])              # OR A
    c.extend([0x20, 0x04])        # JR NZ, +4
    c.extend([0x3E, 0x02])        # LD A, 2 (Sara W)
    c.extend([0x18, 0x02])        # JR +2
    c.extend([0x3E, 0x01])        # LD A, 1 (Sara D)
    c.extend([0x47])              # LD B, A
    c.extend([0xFA, 0x07, 0xFE])  # LD A, [0xFE07]
    c.extend([0xE6, 0xF8])        # AND 0xF8
    c.extend([0xB0])              # OR B
    c.extend([0xEA, 0x07, 0xFE])  # LD [0xFE07], A
    c.extend([0xC1])              # POP BC
    c.extend([0xF1])              # POP AF
    c.extend([0xC3, 0x53, 0x08])  # JP 0x0853
    assert len(c) <= STAT_STUB_MAX, f"STAT WRAM stub {len(c)} > {STAT_STUB_MAX}-byte budget"
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


def build_hwoam_recolor() -> bytes:
    """Re-stamp HW OAM (0xFE00) palette bits by tile range, AFTER colorize+DMA.

    Runs from the wrapper once colorize (which DMAs the shadow buffer to HW OAM)
    has returned, so it fixes the DISPLAYED sprites that the game's pal0 rebuild
    + double-buffer DMA leaves uncolored. Sets up D (Sara form palette from FFBE)
    and E (boss slot from FFBF + boss_slot_table) exactly like shadow_main, points
    HL at the first HW-OAM attr byte, and tail-calls the existing tile-based
    colorizer at 0x6A10 (which loops 40 sprites: read tile [HL-1], map to palette,
    OR into attr [HL], advance 4). The colorizer RETs, so this RETs.
    """
    c = bytearray()
    # Scope: dungeon-family scenes only (D880 < 0x0C). This covers the gameplay
    # demo + dungeon enemies + the mini-boss (0x0A), but EXCLUDES the 9 stage-boss
    # arenas (0x0C-0x14), death (0x17), splash/title (0x16/0x18/0x1B/0x1C) — those
    # color their sprites natively (verified-good) and must not be re-stamped by
    # the tile-range recolor.
    c.extend([0xFA, 0x80, 0xD8])          # LD A, [D880]
    c.extend([0xFE, 0x0C])                # CP 0x0C
    c.extend([0xD0])                      # RET NC  (>= 0x0C -> skip)
    # D = Sara form palette: FFBE==0 -> 2 (witch), else -> 1 (dragon)
    c.extend([0xF0, 0xBE, 0xB7, 0x20, 0x04, 0x16, 0x02, 0x18, 0x02, 0x16, 0x01])
    # E = boss slot: FFBF==0 -> 0, else boss_slot_table[FFBF-1]
    c.extend([0xF0, 0xBF, 0xB7])
    j_noboss = len(c) + 1
    c.extend([0x28, 0x00])                 # JR Z, no_boss
    c.extend([0x3D, 0x4F, 0x06, 0x00])     # DEC A; LD C,A; LD B,0
    c.extend([0x21, BOSS_SLOT_TABLE_ADDR & 0xFF, (BOSS_SLOT_TABLE_ADDR >> 8) & 0xFF])
    c.extend([0x09, 0x5E])                 # ADD HL,BC; LD E,[HL]
    j_done = len(c) + 1
    c.extend([0x18, 0x00])                 # JR done
    no_boss = len(c)
    c[j_noboss] = (no_boss - j_noboss - 1) & 0xFF
    c.extend([0x1E, 0x00])                 # LD E, 0
    done = len(c)
    c[j_done] = (done - j_done - 1) & 0xFF
    # HL = HW OAM first attr byte; B = 10 (match shadow pass coverage).
    # Tail-jump to the colorizer's loop_start (addr+2) to skip its own `LD B,n`.
    #
    # B=10 was selected after a parallel investigation probe (2026-06-15) found
    # that B=40 stamped slots 10-39 with tile-range-derived palettes, but
    # tiles 0x10-0x1F are Sara's secondary body sprites (X=93/101 Y=79-87,
    # immediately adjacent to Sara). The colorizer's fall-through for
    # tile<0x20 paints them pal4 (Hornet ORANGE per penta_palettes_v097.yaml)
    # → "Sara half-orange" + pause-menu quadrant flicker as the game keeps
    # updating shadow OAM during pause.
    #
    # Trade-off: enemies allocated to OAM slots 10+ stay at pal0 (the
    # original DMA-race issue from items 3,4,11 is partially un-fixed for
    # those rare cases). But that affects only frames with >10 active
    # sprites and is visually MUCH less loud than the half-orange Sara,
    # which was immediate and disturbing.
    c.extend([0x21, 0x03, 0xFE])           # LD HL, 0xFE03
    # Iter 31: raise from B=10 → B=40 for full 40-slot post-DMA stamp.
    # Combined with the bg_experiment.py iter-31 tile-0x10-0x1F → sara_palette
    # remap, the previously documented "Sara half-orange" regression at
    # slots 10-11 is GONE — secondary Sara tiles map to D (Sara pal) instead
    # of pal_4. This unlocks orc/soldier/orc_with_items by post-stamping
    # HW OAM AFTER the DMA, so the shadow-side race documented in iter 29
    # no longer matters. mGBA-verified; MiSTer hardware verification gated
    # on this commit.
    #
    # Iter 277 ATTEMPTED B=20 (slot 2 race 113→23, 80% reduction of half-
    # orange Sara visible in dungeon gameplay). REVERTED because B=20
    # introduces 4 fresh-boot CRAM regressions: Sara jet form (OBP-2.1=2EBE
    # vs expected 7C1F, OBP-2.2=511F vs 5817), Gargoyle (OBP-6.1=601F vs
    # 607E), Spider (OBP-7.1=001F vs 00E0). Mechanism: hwoam_recolor's
    # shorter runtime changes when cond_pal/palette_loader fire relative
    # to LCD STAT-mode transitions, breaking palette write+modify
    # sequencing. See docs/audit/iter277_b_sweep_attempted_reverted.md
    # for B-sweep findings + the trade-off analysis.
    c.extend([0x06, 0x28])                 # LD B, 40
    loop_start = OBJ_COLORIZER_ADDR + 2    # after the colorizer's LD B,n
    c.extend([0xC3, loop_start & 0xFF, (loop_start >> 8) & 0xFF])  # JP colorizer loop_start
    return bytes(c)


def build_banner_override() -> bytes:
    """At D880=0x1B (title banner), patch 0xDA00 so the showcase has intentional
    colors. CALLed every frame from the teleport routine (after the splash table
    is in 0xDA00); no-op at any other scene. Letters use cyan (p4, no red)."""
    c = bytearray()
    c.extend([0xFA, 0x80, 0xD8])          # LD A,[D880]
    c.extend([0xFE, 0x1B])                # CP 0x1B
    c.extend([0xC0])                      # RET NZ
    def fill(lo, n, pal):                 # 0xDA00+lo .. +lo+n-1 = pal
        c.extend([0x3E, pal])             # LD A, pal
        c.extend([0x21, lo, 0xDA])        # LD HL, 0xDA00+lo
        c.extend([0x06, n])               # LD B, n
        lp = len(c)
        c.extend([0x22, 0x05])            # LD [HL+],A; DEC B
        c.extend([0x20, (lp - (len(c) + 2)) & 0xFF])  # JR NZ, lp
    # Banner-readable palette assignment:
    # - Letters (0xE0-0xFF) → pal6 BG (white/blue-gray/dark-slate/black) reads
    #   as bold blue-gray on white — vibrant, distinct from red JAM logo, and
    #   doesn't reuse pal4 (which is YAML-cyan/white-white-teal-black — invisible
    #   on the white banner backdrop, per the 2026-06-15 banner probe).
    # - Names (0x80-0x99) → pal3 BG (white/forest-green/dark-green/black) — green
    #   names POP against the blue-gray letters and red JAM logo, no need for a
    #   per-scene CRAM rewrite (which would consume bank13 space we don't have).
    # - JAM logo (0xCA-0xCF, 0xDA-0xDE) → pal1 red (unchanged).
    fill(0xE0, 0x20, 6)
    fill(0x80, 0x1A, 3)
    fill(0xCA, 0x06, 1)
    fill(0xDA, 0x05, 1)

    # Burst bg_sweep: call BG_SWEEP_ADDR 4 extra times so the VRAM attr plane
    # catches up to 0xDA00 changes within ~4 frames instead of bg_sweep's
    # default ~18 frames. Without this, mid-cycle tile-data rewrites (the
    # cycled monster name + scroll-in animation) show transient checkered
    # palettes because bg_sweep is rate-limited to 1 row/frame. Banner is
    # non-gameplay so the extra VBlank cost (~2700 cycles) is safe.
    # Loop form (9 bytes vs 12 unrolled) — saves space for cutscene_override.
    c.extend([0x06, 0x04])                # LD B, 4
    burst_loop = len(c)
    c.extend([0xC5])                      # PUSH BC   (bg_sweep clobbers BC)
    c.extend([0xCD, BG_SWEEP_ADDR & 0xFF, (BG_SWEEP_ADDR >> 8) & 0xFF])
    c.extend([0xC1])                      # POP BC
    c.extend([0x05])                      # DEC B
    c.extend([0x20, (burst_loop - (len(c) + 2)) & 0xFF])  # JR NZ, burst_loop

    c.extend([0xC9])                      # RET
    return bytes(c)


def build_cutscene_override() -> bytes:
    """At D880=0x15 (intro cutscenes: treasure scroll, Sara face closeup,
    dragon eyes, Japanese-text textbox — all 4 share one D880 value per the
    2026-06-15 probe), patch 0xDA00 to give panels intentional palettes
    instead of red-flooding (the dungeon table's 0x80-0xDF->pal1 rule).

    Per-panel art is in low tile bands (treasure 0x01-0x5B, dragon 0x01-0x2D
    + 0xF0-0xFC). Textbox border (0x6B-0x72) and font/portrait band
    (0x80-0xC9) are present in EVERY panel, safe to color with one stable
    overlay. CALLed every frame from teleport routine; cheap no-op at other
    scenes (CP+RET in 6 cycles).
    """
    c = bytearray()
    c.extend([0xFA, 0x80, 0xD8])          # LD A,[D880]
    c.extend([0xFE, 0x15])                # CP 0x15
    c.extend([0xC0])                      # RET NZ (no-op at any other scene)

    def fill(lo, n, pal):                 # 0xDA00+lo .. +lo+n-1 = pal
        c.extend([0x3E, pal])             # LD A, pal
        c.extend([0x21, lo, 0xDA])        # LD HL, 0xDA00+lo
        c.extend([0x06, n])               # LD B, n
        lp = len(c)
        c.extend([0x22, 0x05])            # LD [HL+],A; DEC B
        c.extend([0x20, (lp - (len(c) + 2)) & 0xFF])  # JR NZ, lp

    # Textbox border tiles (cyan) — visible blue outline on all panels
    fill(0x6B, 0x08, 4)
    # Font glyphs + Sara portrait band (warm beige — legible on white textbox
    # AND reads as skin tones for the Sara portrait that shares this tile band)
    fill(0x80, 0x4A, 2)
    # Dragon-eye highlights + JAM-logo art (red).
    # Dungeon table already maps 0xF0-0xFF to pal1 (red), so this matches
    # without an explicit fill — saved 11 bytes for bank13 layout.
    # Treasure scroll low-range art (0x10-0x4F) intentionally NOT overridden;
    # falls through to dungeon table mapping (mostly readable, no red flood
    # because the dungeon table only maps 0x80-0xDF to red).
    c.extend([0xC9])                      # RET
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

    # ---- Banner colorize: at D880=0x1B (animated title banner), patch 0xDA00
    # (the all-p0 splash table) so the showcase reads as gold names / cyan
    # "PENTA DRAGON" letters / red JAM logo. No-op elsewhere. ----
    c.extend([0xCD, BANNER_OVERRIDE_ADDR & 0xFF, (BANNER_OVERRIDE_ADDR >> 8) & 0xFF])

    # ---- Cutscene colorize: at D880=0x15 (intro cutscenes — treasure, Sara
    # face, dragon eyes, Japanese-text), patch 0xDA00 with intentional palettes
    # for the textbox, font/portrait, dragon highlights, and scroll art bands.
    # No-op elsewhere. ----
    c.extend([0xCD, CUTSCENE_OVERRIDE_ADDR & 0xFF, (CUTSCENE_OVERRIDE_ADDR >> 8) & 0xFF])

    # ---- One-shot: ensure landing pad is copied to WRAM 0xDB00 ----
    # Check sentinel DF0E (iter 178: was stale "DF1E" comment; bytes
    # have always been DF0E — see also lines 756/767/780).
    c.extend([0xFA, 0x0E, 0xDF])          # LD A, [DF0E]
    c.extend([0xFE, 0x5A])                # CP 0x5A
    j_copy_done = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, copy_done
    # Copy 40 bytes (landing pad) from bank13 ROM to WRAM DB00.
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

    # Third copy: STAT IRQ WRAM stub from STAT_STUB_ROM_ADDR (bank13 0x53F2)
    # to STAT_STUB_WRAM (0xDB50). Cold-boot only (gated by DF0E sentinel
    # check at the head of this whole copy block).
    c.extend([0x21, STAT_STUB_ROM_ADDR & 0xFF, (STAT_STUB_ROM_ADDR >> 8) & 0xFF])
    c.extend([0x11, STAT_STUB_WRAM & 0xFF, (STAT_STUB_WRAM >> 8) & 0xFF])
    c.extend([0x06, STAT_STUB_MAX])       # LD B, 36
    stat_loop = len(c)
    c.extend([0x2A, 0x12, 0x13, 0x05])    # LD A,[HL+]; LD [DE],A; INC DE; DEC B
    off = stat_loop - (len(c) + 2)
    c.extend([0x20, off & 0xFF])          # JR NZ, stat_loop
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
        + [0x03, 0x11] + _txt("STRUKTURED LABS") + [E]         # attribution (row 17)
        + [E]                                                   # list end
    )
    assert len(title_list) <= 126, f"title list {len(title_list)} > 126 (overruns region)"
    assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
    rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
    print(f"  title: PENTA DRAGON DX header + STRUKTURED LABS ({len(title_list)}/126 bytes @0x4EA5)")

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

    # 2c. STAT IRQ WRAM stub source. Stored at bank13:0x53F2 (36-byte free
    # run, copied to WRAM at 0xDB50 at cold-boot by the teleport routine's
    # third copy block). The IRQ vector at 0x0048 is patched below to JP
    # 0xDB50, so STAT IRQ executes the WRAM stub (FFBF-gated slot-1
    # re-stamp) then chains to original 0x0853 (parallax scroll).
    stat_stub = build_stat_irq_wram_stub()
    print(f"  STAT IRQ WRAM stub: {len(stat_stub)} bytes at bank13:0x{STAT_STUB_ROM_ADDR:04X} "
          f"→ copied to WRAM 0x{STAT_STUB_WRAM:04X}")
    off = BANK13 + (STAT_STUB_ROM_ADDR - 0x4000)
    # Iter 43: build_v301_gdma now also installs the same STAT stub at this
    # address. Accept either "all zeros" (legacy v3.01 base) or "already the
    # iter-43 stub bytes" — both cases get overwritten harmlessly. Anything
    # else means a build-script drift the caller should debug.
    existing = bytes(rom[off:off + len(stat_stub)])
    assert existing == bytes(len(stat_stub)) or existing == stat_stub, (
        f"STAT stub site at 0x{STAT_STUB_ROM_ADDR:04X} has unexpected bytes: "
        f"{existing.hex()} — expected zeros or the iter-43 stub")
    # Also enforce that the remaining padding bytes (past the stub) are zero
    # so the cold-boot copy doesn't drag garbage into WRAM.
    for i in range(len(stat_stub), STAT_STUB_MAX):
        assert rom[off + i] == 0x00, (
            f"STAT stub padding at 0x{STAT_STUB_ROM_ADDR + i:04X} not free "
            f"(byte {rom[off + i]:02X}) — choose a different free run")
    rom[off:off + len(stat_stub)] = stat_stub

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
    # Iter 234 attempted: letter tiles 0x2C-0x7F → pal 1 for splash legibility.
    # REVERTED iter 236: scene_detect's fast-path (RET Z when scene unchanged)
    # keeps splash_table cached in WRAM 0xDA00 across savestate-captured
    # transitions, so iter 234's pal-1 letters bleed into stage 6 BG render
    # (stage6_decorative_pal5 lavender count: 7822 → 5554, FAIL).
    # Future fix needs scene_detect to always reload on splash→dungeon
    # transition, OR a different mechanism that doesn't share WRAM 0xDA00.
    rom[off:off + 256] = bytes(256)   # all pal0 (original)
    print(f"  splash table: 256 bytes (all pal0) at bank13:0x{SPLASH_TABLE_ADDR:04X}")

    # Post-DMA HW-OAM recolor (enemies items 3,4,6,11), CALLed from the wrapper.
    # Iter 278e: relocated to 0x6B27 (217 bytes free) — pure address change.
    hwoam = build_hwoam_recolor()
    assert HWOAM_RECOLOR_ADDR + len(hwoam) < 0x6C00, \
        f"hwoam recolor 0x{HWOAM_RECOLOR_ADDR + len(hwoam):04X} overruns 0x6C00 free region"
    off = BANK13 + (HWOAM_RECOLOR_ADDR - 0x4000)
    rom[off:off + len(hwoam)] = hwoam
    print(f"  hwoam recolor: {len(hwoam)} bytes at bank13:0x{HWOAM_RECOLOR_ADDR:04X}")

    # Banner colorize override (showcase, D880=0x1B), CALLed from teleport routine.
    banner = build_banner_override()
    assert BANNER_OVERRIDE_ADDR + len(banner) <= POSMAP_PTR_TABLE, \
        f"banner override 0x{BANNER_OVERRIDE_ADDR + len(banner):04X} overruns posmap ptr table 0x{POSMAP_PTR_TABLE:04X}"
    off = BANK13 + (BANNER_OVERRIDE_ADDR - 0x4000)
    rom[off:off + len(banner)] = banner
    print(f"  banner override: {len(banner)} bytes at bank13:0x{BANNER_OVERRIDE_ADDR:04X}")

    # Cutscene colorize override (D880=0x15 intro panels), CALLed from teleport routine.
    cutscene = build_cutscene_override()
    assert BANNER_OVERRIDE_ADDR + len(banner) <= CUTSCENE_OVERRIDE_ADDR, \
        f"banner 0x{BANNER_OVERRIDE_ADDR + len(banner):04X} overruns cutscene 0x{CUTSCENE_OVERRIDE_ADDR:04X}"
    assert CUTSCENE_OVERRIDE_ADDR + len(cutscene) <= POSMAP_PTR_TABLE, \
        f"cutscene override 0x{CUTSCENE_OVERRIDE_ADDR + len(cutscene):04X} overruns posmap ptr table 0x{POSMAP_PTR_TABLE:04X}"
    off = BANK13 + (CUTSCENE_OVERRIDE_ADDR - 0x4000)
    rom[off:off + len(cutscene)] = cutscene
    print(f"  cutscene override: {len(cutscene)} bytes at bank13:0x{CUTSCENE_OVERRIDE_ADDR:04X}")

    # 2b. Re-patch bg_sweep to read the PER-SCENE WRAM table (0xDA00) instead
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

    # 2d. Neutralize the inline hook's ATTR writes in arenas.
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98]), \
        "inline hook entry point changed — neutralize would corrupt it"
    neut = create_inline_tile_copy_tileonly(arena_neutralize_d880=None)
    hook_budget = 0x436D - 0x42A7 + 1   # 199 bytes
    assert len(neut) <= hook_budget, f"neutralized hook too big: {len(neut)} > {hook_budget}"
    rom[0x42A7:0x42A7 + len(neut)] = neut
    if 0x42A7 + len(neut) < 0x436E:      # re-pad leftover tail with zeros
        rom[0x42A7 + len(neut):0x436E] = bytes(0x436E - (0x42A7 + len(neut)))
    print(f"  inline hook restored (full tile+attr copy) in arenas: {len(neut)} bytes at 0x42A7")

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

    # 4. Write new VBlank hook at 0x0824 and wrapper at WRAPPER_ADDR.
    # Wrapper moved 0x6F10 -> 0x6F20 -> 0x6F30: the teleport routine grew (per-
    # frame CALL lava_override, then the levelsel-stub cold-boot copy block)
    # — each bump frees ~16 bytes for the teleport routine. The 40 bytes
    # between WRAPPER_ADDR end and LANDING_PAD_ROM_ADDR=0x6F80 are unused.
    # would clobber the teleport routine's final `JP colorize`, breaking the
    # whole colorize chain (symptom: entire screen renders uncolored/white).
    WRAPPER_ADDR = 0x6F40  # iter 9 bumped from 0x6F30 to accommodate
                           # teleport routine's added STAT-stub cold-boot
                           # copy block (third copy of ~14 bytes).
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

        # --- CALL Teleport routine (runs scene_detect + lava + JP colorize+DMA) ---
        0xCD, TELEPORT_ADDR & 0xFF, (TELEPORT_ADDR >> 8) & 0xFF,

        # --- Post-DMA HW-OAM recolor (enemies; items 3,4,6,11) ---
        0xCD, HWOAM_RECOLOR_ADDR & 0xFF, (HWOAM_RECOLOR_ADDR >> 8) & 0xFF,

        # --- RESTORE REGISTERS ---
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC

        0xC9,                                 # RET
    ])

    assert WRAPPER_ADDR + len(wrapper) <= LANDING_PAD_ROM_ADDR, \
        f"wrapper 0x{WRAPPER_ADDR + len(wrapper):04X} overruns landing pad 0x{LANDING_PAD_ROM_ADDR:04X}"
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

    # ---- Patch IRQ vector 0x0048 (STAT) to JP into our WRAM stub ----
    # Pre-condition: 0x0048 must be JP — either C3 53 08 (legacy v3.01 base) or
    # already C3 50 DB (iter 43: build_v301_gdma patches the same vector).
    expected_legacy = bytes([0xC3, 0x53, 0x08])
    expected_iter43 = bytes([0xC3, STAT_STUB_WRAM & 0xFF, (STAT_STUB_WRAM >> 8) & 0xFF])
    actual = bytes(rom[0x0048:0x004B])
    assert actual == expected_legacy or actual == expected_iter43, (
        f"STAT vector at 0x0048 not the expected JP 0x0853 or JP 0x{STAT_STUB_WRAM:04X}: "
        f"{actual.hex()}")
    rom[0x0049] = STAT_STUB_WRAM & 0xFF
    rom[0x004A] = (STAT_STUB_WRAM >> 8) & 0xFF
    print(f"  STAT IRQ vector patched: 0x0048 JP target 0x0853 → "
          f"0x{STAT_STUB_WRAM:04X} (WRAM stub gates on FFBF, chains to 0x0853)")

    # Header checksum (recompute for safety)
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

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
