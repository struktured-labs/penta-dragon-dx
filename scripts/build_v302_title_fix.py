#!/usr/bin/env python3
"""Penta Dragon DX — title cursor and v3.01 release footer fix.

Features & Fixes:
1. **Exact release footer**: writes `DX V3.01 STRUK LABS` to row 17.
2. **Native title digits**: reuses the title's built-in 3, 0, and 1 glyphs.
3. **Reversible period tile**: temporarily replaces unused title digit 9 with
   a period via GDMA, then restores 9 when leaving the title.
4. **Title-safe inline hook** — keeps the proven tile-only path on the title
   screen and full tile+attr writes in gameplay. Arena remains tile-only for
   position-sweep compatibility.
5. **OBJ palette LUT** — tiles 0x70-0x7F → pal 7, matching cursor 'A' at tile 0x73 requirements.
6. **Title bg_sweep** — reads the per-scene WRAM table with its FFC1 gate
   removed so the title receives initialized attributes.
7. **Clean item-menu HUD** — keeps the six visible window attribute rows on
   palette 0 and pauses the background sweep until the menu closes, so
   off-screen dungeon palettes cannot bleed back into HP or MEDICAL text.
8. **Release-safe inputs** — removes the unstable SELECT+START IRQ stack
   redirect while retaining scene-aware palettes, lava, and level-select setup.
9. **Intentional title colors** — routes title attrs to palette 0 and safely
   reloads its blue-gray ramp after the game's partial cold-boot CRAM writes.
10. **Vanilla stage-intro timing** — bypasses the heavy colorizer while the
    all-palette-0 `STAGE XX` splash is active so its LCD-mode wait sees every
    VBlank instead of stretching the 100-frame ditty across several loops.
11. **Complete gameplay OBJ pass** — colorizes the exact shadow-OAM buffer
    selected by the immediately-following DMA, covering all 40 slots once
    instead of partially processing both alternating buffers.
12. **Palette round-trip** — honors all eight YAML BG palettes in gameplay,
    while preserving the proven BG7→BG0 boot/title mask until the normal
    game-state palette reload restores independently tuned BG7.
13. **ROM-native story palettes** — colors committed OPENING/final-story art
    above a neutral dialogue frame and colors the guarded credits, END, and
    epilogue pages without changing their stock control flow.
14. **Death/game-over containment** — clears stale arena attributes from both
    tilemaps over seven bounded VBlanks before the stock GAME OVER window
    appears, so the neutral DMG-authored cinematic cannot inherit boss colors.
"""
import argparse
import hashlib
import os as _os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Ensure we run from the project root
_script_dir = Path(__file__).parent.parent
_os.chdir(str(_script_dir))

import yaml
from arena_position import (
    parse_footprint_posmaps, rle_encode_posmap, create_rle_expander,
    _Asm,
)
from build_v296_phantomsafe import create_bg_sweep_viewport_gated
from build_v301_gdma import (
    build_v301, load_palettes_from_yaml,
    create_shadow_colorizer_main, create_tile_based_colorizer,
    create_tile_to_palette_subroutine, create_conditional_palette_cached,
    create_inline_tile_copy_tileonly, create_inline_tile_copy_pure_tileonly,
    create_inline_tile_copy_stage1_precomputed_attrs,
    create_inline_tile_copy_stage1_buffered_attrs,
    create_inline_tile_copy_stage1_double_buffered_attrs,
    create_inline_tile_copy_row_precomputed_attrs,
    create_inline_tile_copy_stage1_cached_atomic,
    BG_TABLE_BYTES, _bg_table,
)
from build_v301_teleport import (
    _table_from_dict, build_scene_detect, build_lava_override,
    build_obj_pal_table,
    build_levelsel_attr_clear_stub,
    ARENA_TILE_PAL, FOOTPRINT_LOG, ARENA_ORDER,
    _bg_table_shalamar, _bg_table_riff, _bg_table_crystal_dragon,
    _bg_table_cameo, _bg_table_ted, _bg_table_troop,
    _bg_table_faze, _bg_table_angela, _bg_table_penta_dragon,
    SPLASH_TABLE_ADDR,
    LEVELSEL_STUB_ROM_ADDR, LEVELSEL_STUB_WRAM, LEVELSEL_PATCH_ADDR,
)
from stage1_hazard_art import (
    apply_stage1_hazard_variants,
    load_stage1_hazard_config,
    load_stage1_hazard_palette,
)
from cutscene_region_palettes import (
    ART_COLUMNS as CUTSCENE_ART_COLUMNS,
    ART_ROWS as CUTSCENE_ART_ROWS,
    Panel as CutscenePanel,
    load_cutscene_region_palettes,
    panel_mask as cutscene_panel_mask,
)

BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
OUTPUT_PATH = Path("rom/working/penta_dragon_dx_FIXED.gb")  # Overwrite FIXED.gb
PALETTE_YAML = Path("palettes/penta_palettes_v097.yaml")
SPOTLIGHT_MAP_YAML = Path("palettes/spotlight_palette_map.yaml")

# Constants
BANK13 = 13 * 0x4000
BANK14 = 14 * 0x4000
STAGE1_LOW_TILE_GFX_OFFSET = 0x1D000
STAGE1_HIGH_TILE_GFX_OFFSET = 0x1F000
STAGE1_PICKUP_GOLD = 0x03FF
DEMO_COMPACT_COPY_ADDR = 0x69F8
BG_SWEEP_ADDR = 0x6CD0
# Keep the palette LUT out of the stock $C780-$CFFF dungeon world map.
# $C600-$C6FF is the fixed-WRAM gap between tile buffers and $C700 state.
WRAM_BG_TABLE = 0xC600
COLORIZE_ADDR = 0x6E00
COLORIZE_PRELUDE_ADDR = 0x6E80
TITLE_PALETTE_FIX_ADDR = 0x6A60
TITLE_PALETTE_COPY_HELPER_ADDR = 0x6A52
WINDOW_ATTR_CLEAR_HELPER_ADDR = 0x6F0F
TITLE_DELAY_ADDR = 0x7D63
TITLE_PALETTE_SOURCE_ADDR = 0x6800
NATIVE_BG0_ALIAS_ADDR = TITLE_PALETTE_SOURCE_ADDR + 0x38
TUNED_BG7_SOURCE_ADDR = 0x68F8
# Eight-byte gap between the boss-slot table and jet palettes. This contains
# the YAML-owned Stage-1-only BG7 tooth/drill row.
STAGE1_HAZARD_BG7_SOURCE_ADDR = 0x68C8
PALETTE_LOADER_ADDR = 0x6900
PALETTE_LOADER_EXT_ADDR = 0x71A0
# Stable entry in the retired position-map pointer cave that copies one
# eight-byte palette as two LCD-mode-safe four-byte halves.  Keeping this tiny
# trampoline outside the phased-loader extension leaves enough room for the
# cycle-neutral, scene-local Stage-1 BG7 selector.
PALETTE_COPY_CRAM8_ADDR = 0x7FE0
LATER_STAGE_BG0_REPAIR_ADDR = 0x69B8
LATER_STAGE_BG0_FORCE_ADDR = LATER_STAGE_BG0_REPAIR_ADDR + 6
LATER_STAGE_BG0_ENTRY_ADDR = LATER_STAGE_BG0_REPAIR_ADDR + 18
CONDITIONAL_PALETTE_ADDR = 0x6C90
# Keep the established $6C90 ABI as a three-byte trampoline. The expanded
# idle-throttled implementation lives in the unused tail after the title
# transition service and before the spotlight identity map.
CONDITIONAL_PALETTE_IMPL_ADDR = 0x6BA4
SPOTLIGHT_PALETTE_HELPER_ADDR = 0x6C93
PALETTE_PHASE_ADDR = 0xDF4C
SPOTLIGHT_PALETTE_CACHE_ADDR = 0xDF4D
BG_SWEEP_COUNT_ADDR = 0xDF4E
BG_SWEEP_REARM_ROWS = 18
# Native FFBD writers set this one-shot marker. The main-loop room copier
# consumes it exactly once to commit the matching attribute plane atomically.
BG_SWEEP_ROOM_CACHE_ADDR = 0xDF4F
ROOM_ATTR_PENDING_VALUE = 0xA6
ROOM_ATTR_READY_VALUE = 0xA7
# The old $6B00 tile->palette LUT had no live reader outside the mistaken
# attract helper. Reclaim the page for the title/gameplay OAM dispatcher.
# The complete 38-entry spotlight roster is packed as 19 palette nibbles in
# the four-byte gap after the conditional service and the free page tail.
OBJ_PAL_TABLE_ADDR = 0x6B00
ATTRACT_OBJ_COLORIZER_ADDR = 0x6B00
DEATH_LATE_FIX_ADDR = 0x6B60
ATTRACT_PICKUP_SWEEP_STUB_ADDR = 0x6B56
# The title wrapper is cycle-locked to the stock menu input phase.  Keep its
# per-frame glyph call byte-for-byte stable and put expanded transition-only
# work in the reclaimed position-sweep region instead.
TITLE_TRANSITION_SERVICE_ADDR = 0x7D00
# The retired gameplay OBJ scan is explicitly cleared through $6A6F. Keep the
# gameplay-only hardware-Window guard in its free tail below the title helper.
STALE_WINDOW_CLEANUP_ADDR = 0x6A40
# The former attract-row helper slot and the exact gap after the YAML OBJ LUT
# initializer are both in the explicitly retired $7B00-$7DFF position-map
# allocation. Split the cutscene scheduler across them so the entire 18-byte
# pointer-table allocation at $7FE0 remains byte-exact (seven-byte copier plus
# eleven required zero bytes) for timing-sensitive Stage-1/demo paths.
CUTSCENE_PALETTE_CONT_ADDR = 0x7B49
CUTSCENE_PALETTE_CONT_END = 0x7B60
CUTSCENE_PALETTE_BRIDGE_ADDR = 0x7DF4
CUTSCENE_PALETTE_BRIDGE_END = 0x7E00
SPOTLIGHT_PALETTE_MAP_ADDR = 0x6BE8
SPOTLIGHT_ROSTER_TABLE_ADDR = 0x522A
SPOTLIGHT_ROSTER_SIZE = 0x26
ENDING_ABSOLUTE_ROW_HELPER_ADDR = 0x6AB5
STORY_COLUMN_HELPER_ADDR = 0x6AF5
STORY_QUARTER_HELPER_ADDR = 0x6C00
STORY_SEPARATOR_HELPER_ADDR = 0x6A9A
STORY_VIEWPORT_KEY_HELPER_ADDR = 0x6CC3
BASE_SHADOW_MAIN_ADDR = 0x69D0
# The retired all-40-slot gameplay scan leaves a 64-byte cave before the
# tile colorizer. The GAME OVER fade uses it for bounded BG0 steps plus an
# all-white fill during the stock fully blank transition phase.
DEATH_FADE_HELPER_ADDR = BASE_SHADOW_MAIN_ADDR
# The exact 36-byte gap after death-tail containment holds the cycle-exact room
# repair instead of truncating it into the Stage 7 source at $7C4D.
ROOM_BG_REPAIR_ADDR = 0x6B80
# The production room repair has an exact 36-byte cave. Its shared tails stay
# fixed while the adjacent ten-byte dispatcher distinguishes prerecorded and
# live D880=$0A before entering the two-map Shield-row helper.
ROOM_BG_REPAIR_STANDARD_ADDR = ROOM_BG_REPAIR_ADDR + 18
ROOM_BG_REPAIR_CLEAR_ADDR = ROOM_BG_REPAIR_ADDR + 30
SHADOW_MAIN_ADDR = 0x69D8
TILE_COLORIZER_ADDR = 0x6A10
BOSS_SLOT_TABLE_ADDR = 0x68C0
# The former $6F35 placement left an unused gap after the uniform-clear helper.
# Reclaim it for an inline palette scheduler so idle VBlanks avoid a CALL.
WRAPPER_ADDR = 0x6F20
NATIVE_DMG_FADE_SITE = 0x0F5E
# The stock damage/effect animator cycles the global DMG BG mapping through
# $90/$E4/$F9.  On CGB that remaps the entire already-colorized background,
# producing the user-visible white checker pulse in both attract-demo and
# ordinary gameplay.  Keep the stock branches/RET cadence and neutralize only
# the two non-normal immediate values.
NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR = 0x281C
# The semantic free-slot OAM wrapper retires its original $3482-$34A2 tail.
# Its exact 33-byte cave hosts the cache/lava decision helper used by the
# register-staged, stock-width atomic map copier.
INLINE_ATTR_DECISION_HELPER_ADDR = 0x3482
SEMANTIC_STAGE1_PROTOTYPE_ADDR = 0x73FC
STAGE1_VBLANK_PROTOTYPE_ADDR = 0x6BA7
# Bank 14's verified-zero $6BA7-$6C57 cave is mapped only after the native
# 24x24 tile copier finishes.  It holds the Stage-1 animation attribute
# publisher: no tile IDs and no HBlank waits, just WRAM LUT compilation plus
# bounded 32-byte general-DMA rows.
STAGE1_HAZARD_ROW_HELPER_ADDR = STAGE1_VBLANK_PROTOTYPE_ADDR
STAGE1_HAZARD_ROW_HELPER_END = 0x6C58
STAGE1_HAZARD_ROW_COMPILER_ADDR = 0x6C88
STAGE1_HAZARD_ROW_COMPILER_END = 0x6CFC
STAGE1_VBLANK_PALETTE_TABLE_ADDR = 0x6D6B
STAGE1_PICKUP_WRITER_ADDR = 0x6C88
STAGE1_PICKUP_APPENDER_ADDR = 0x6CC8
STAGE1_PICKUP_SCANNER_ADDR = 0x6F3B
STAGE1_VBLANK_TRAMPOLINE_ADDR = INLINE_ATTR_DECISION_HELPER_ADDR + 15
STAGE1_PICKUP_ACTIVE_ADDR = 0xDF60
STAGE1_PICKUP_COUNT0_ADDR = 0xDF61
STAGE1_PICKUP_ENTRIES0_ADDR = 0xDF62
STAGE1_PICKUP_COUNT1_ADDR = 0xDF6E
STAGE1_PICKUP_ENTRIES1_ADDR = 0xDF6F
STAGE1_PICKUP_ID_ADDR = 0xDF7B
STAGE1_PICKUP_BUILD_KEY_ADDR = 0xDF7C
STAGE1_PICKUP_OLD_REMAIN_ADDR = 0xDF7D
STAGE1_PICKUP_NEW_INDEX_ADDR = 0xDF7E
STAGE1_PICKUP_SCAN_POS_ADDR = 0xDF7B
STAGE1_PICKUP_QUEUE_CAPACITY = 6
STAGE1_PICKUP_SCAN_ONE_ADDR = 0x69F8
STAGE1_PICKUP_WRITE_TAIL_ADDR = 0x6B62
STAGE1_PICKUP_PACKED_TABLE_ADDR = 0x6C80
STAGE1_PICKUP_DECODER_ADDR = 0x6E6F
STAGE1_PICKUP_SCAN_MAIN_ADDR = 0x7B49
STAGE1_SYNC_SCANNER_ADDR = 0x6BA7
STAGE1_SYNC_DECODER_ADDR = 0x6C30
STAGE1_SYNC_TABLE_ADDR = 0x6C40
STAGE1_SYNC_WRITER_ADDR = 0x6C88
STAGE1_PICKUP_VBLANK_HELPER_ADDR = 0x69F8
STAGE1_PICKUP_RESIDENT_WRITER_ADDR = 0x6A1A
STAGE1_PICKUP_RESIDENT_TAIL1_ADDR = 0x7B49
STAGE1_PICKUP_RESIDENT_TAIL2_ADDR = 0x6E6F
STAGE1_SCROLL_EDGE_SERVICE_ADDR = 0x69F8
STAGE1_SCROLL_TILE_Y_CACHE_ADDR = 0xDF7D
# Three title-delay bytes plus the 19-byte readiness/demo dispatcher occupy
# $3482-$3497. The next two bytes restore the copier's EI/RET contract.
STAGE1_ATOMIC_WRAP_ADDR = INLINE_ATTR_DECISION_HELPER_ADDR + 22
NATIVE_DMG_FADE_DISPATCH_ADDR = 0x10D5
STAGE1_DEMO_DELAY_ADDR = NATIVE_DMG_FADE_DISPATCH_ADDR + 18
# The retired attract-delay service remains in the fixed cave for historical
# build reproduction. Current builds branch on DCFD before doing live-room
# signature work and return DCFD=0 through the pure, stock-width copier.
STAGE1_DEMO_WAIT_LINE = 96
LEVELSEL_STUB_MAX = 36
# Keep a guard gap after the RC3 wrapper while retaining ample room below the
# 0x7000 dungeon table.
SCENE_DETECT_ADDR = 0x6F90
DUNGEON_TABLE_ADDR = 0x7000
ARENA_BASE_ADDR = 0x7200
SHALAMAR_TABLE_ADDR = 0x7200
RIFF_TABLE_ADDR = 0x7300
CRYSTAL_DRAGON_TABLE_ADDR = 0x7400
CAMEO_TABLE_ADDR = 0x7500
TED_TABLE_ADDR = 0x7600
TROOP_TABLE_ADDR = 0x7700
FAZE_TABLE_ADDR = 0x7800
ANGELA_TABLE_ADDR = 0x7900
PENTA_DRAGON_TABLE_ADDR = 0x7A00
LAVA_OVERRIDE_ADDR = 0x7E00
# The old position-sweep blob at $7100 was never called by the production
# colorizer. Reclaim its pre-palette-extension region for the guarded
# death/game-over attribute service.
DEATH_ATTR_DISPATCH_ADDR = 0x7100
# Compatibility aliases for the retired experimental v303/v304 builders.
POSSWEEP_ADDR = DEATH_ATTR_DISPATCH_ADDR
EXPAND_ADDR = 0x6D80
STORY_HALF_ROW_HELPER_ADDR = 0x6D70
POSMAP_DATA_ADDR = 0x7B00
POSMAP_PTR_TABLE = 0x7FE0
# The position-sweep RLE blob and pointer table had no production caller.
# Reclaim that dead region for main-loop semantic OAM and lava helpers.
OAM_PALETTE_RESOLVER_ADDR = 0x7B00
OAM_BOSS_LUT_SERVICE_ADDR = 0x7B21
ATTRACT_PICKUP_SWEEP_HELPER_ADDR = 0x6A2D
OAM_CENTRAL_EMITTER_ADDR = 0x7B60
OAM_FREE_EMITTER_ADDR = 0x7BE0
LAVA_ATTR_STAGE5_SIGNATURE_ADDR = 0x7C13
DEATH_FADE_NORMAL_ADDR = 0x7C2C
DEATH_FADE_INTERMEDIATE_ADDR = 0x7C34
DEATH_FADE_WHITE_ADDR = 0x7C3C
OAM_WRAM_COPY_ADDR = 0x7CC0
NATIVE_GLYPH_RESTORE_ADDR = 0x7D80
OAM_LUT_INIT_ADDR = 0x7DA8
# Bank 14's native-zero caves host a demo-only metatile scanner.  It runs once
# at the stock Stage-1 room-expander return and stamps only actual pickups into
# both maps; no per-frame tilemap scan or full attribute sweep remains.
DEMO_PICKUP_DIRECT_WRITER_ADDR = 0x67A2
DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR = 0x6832
DEMO_PICKUP_TABLE_ADDR = 0x6D6B
DEMO_PICKUP_SCANNER_ADDR = 0x6EAA
DEMO_PICKUP_APPENDER_ADDR = 0x6F3B
# The final VBlank hook occupies only 20 of its 47-byte bank-0 allocation.
# Its padding is always mapped, making it a safe home for the room-change
# rearm target used by the otherwise-unused RST $00 vector.
ROOM_BG_REARM_BANK0_ADDR = 0x0838
# Receipt-covered lava desired-palette signatures. Both decider fragments and
# the sample helpers occupy explicit gaps in the already-retired position-map
# region; do not reuse unproven stock data near the end of the bank.
LAVA_ATTR_DECIDER_ADDR = 0x7B9C
LAVA_ATTR_DECIDER_END = OAM_FREE_EMITTER_ADDR
# The old 22-byte Stage-5 front is relocated into the verified-zero tail of
# the retired gameplay OAM scan.  Do not use $70E0 even though its current LUT
# entries are zero: that address is still the live C600 tile-palette table's
# E0-FF range after the bank-13 initializer copies it to WRAM.
LAVA_ATTR_STAGE5_FRONT_ADDR = 0x69F8
LAVA_ATTR_STAGE5_FRONT_END = STALE_WINDOW_CLEANUP_ADDR
LAVA_ATTR_DECIDER_CONT_ADDR = 0x7D3B
LAVA_ATTR_ROOM_MATCH_ADDR = 0x7D6D
LAVA_ATTR_DECIDER_CONT_END = NATIVE_GLYPH_RESTORE_ADDR
LAVA_ATTR_DECIDER_BANK0_ADDR = 0x0847
LAVA_ATTR_STAGE7_SOURCE_A_ADDR = 0x7BB2
LAVA_ATTR_STAGE7_SOURCE_B_ADDR = 0x7C4D
LAVA_ATTR_DECISION_HRAM = 0xE0
LAVA_ATTR_STAGE5_9800_META_ADDR = 0xDF53
LAVA_ATTR_STAGE5_9C00_META_ADDR = 0xDF56
# Stage 1 reuses one signature byte from each Stage-5 metadata record while
# its own scene is active. Scene detection clears them on every Stage 1 entry;
# its keys can never publish the A7 validity marker consumed later by Stage 5.
STAGE1_ATTR_CACHE_9800_ADDR = LAVA_ATTR_STAGE5_9800_META_ADDR
STAGE1_ATTR_CACHE_9C00_ADDR = LAVA_ATTR_STAGE5_9C00_META_ADDR + 1
# Stage 1 owns otherwise-dormant bytes below the pickup scratch page while its
# copier runs. Keep the caller's IE mask separate from the completed-layout
# signature used by the native metatile-expander tail hook.
STAGE1_HAZARD_CACHE_9800_ADDR = LAVA_ATTR_STAGE5_9800_META_ADDR + 2
STAGE1_HAZARD_CACHE_9C00_ADDR = LAVA_ATTR_STAGE5_9C00_META_ADDR + 2
STAGE1_IE_CACHE_ADDR = 0xDF5A
STAGE1_SOURCE_BUILD_RET_ADDR = 0x13E4
STAGE1_SOURCE_GENERATION_RST = 0xDF             # RST $18
# Raw-tile XOR discriminators covered by the moving/stationary/patrol traces
# plus the multi-room corruption routes.  These keys are injective across all
# captured desired-palette layouts and stable across every duplicate raw-tile
# variant in that corpus (Stage 5: 20 layouts/22 variants; Stage 7: 26/28).
# Keep the claim receipt-bounded: unseen room layouts still require a soak.
LAVA_ATTR_STAGE5_SAMPLES = (175, 203, 236, 425, 456)
LAVA_ATTR_STAGE7_SAMPLES = (6, 69, 169, 452)
OAM_WRAM_BASE = 0xDA00
OAM_PALETTE_LUT_WRAM = 0xD900
OAM_PALETTE_RESOLVER_RUNTIME_ADDR = OAM_WRAM_BASE
OAM_CENTRAL_EMITTER_RUNTIME_ADDR = OAM_WRAM_BASE + 0x21
LAVA_ATTR_STAGE7_RUNTIME_ADDR = OAM_WRAM_BASE + 0x60
# The Stage 7 runtime ends at $DABC. Its verified-unused padding before the
# two destination metadata records hosts a common Stage 5/7 scene dispatcher.
LAVA_ATTR_SCENE_DISPATCH_ADDR = OAM_WRAM_BASE + 0xBC
# The direct-result Stage-7 dispatcher ends at DAD3. Stage 1 uses the remaining
# gap before the existing Stage-7 metadata for a vertical-safe, per-map cache;
# the pickup-first atomic setup rides in the verified resolver-copy gap at
# DA13 instead of competing with it.
STAGE1_ATTR_RUNTIME_ADDR = OAM_WRAM_BASE + 0xD5
STAGE1_ATOMIC_SETUP_ADDR = OAM_WRAM_BASE + 0x13
# Two raw cells complete the DC0E room-builder key for ordinary Stage-1 map
# transitions.  Animated hazard phases are intentionally absent here: they
# use the much cheaper post-copy bank-14 attribute publisher below.
STAGE1_ATTR_TRANSITION_SAMPLES = (247, 251)
# These four raw cells form an injective key for all eight desired hazard
# layouts in the committed natural trace.  They cover both independently
# animated 60-7F cylinder rows and the older 2A-5D spike strip.
STAGE1_HAZARD_PHASE_SAMPLES = (48, 120, 336, 408)
# Three cells fit the shortest vertically-scrolled VRAM-safe interval. The
# full atomic path now runs only for room transitions; animated hazard rows use
# the selective post-expander service in bank 14.
STAGE1_ATOMIC_GROUP_WIDTH = 3
LAVA_ATTR_STAGE7_9800_META_ADDR = OAM_WRAM_BASE + 0xFA
LAVA_ATTR_STAGE7_9C00_META_ADDR = OAM_WRAM_BASE + 0xFD
OAM_WRAM_SENTINEL_ADDR = 0xDF51
OAM_BOSS_LUT_CACHE_ADDR = 0xDF52
# D880=$00/FFC1=$00 describes both the title and save-present level select.
# The selector publishes an out-of-range palette phase. Stage 1 entry replaces
# it with the normal 0x11 phase, so the marker expires without touching stock
# state or the title/reel counters.
LEVELSEL_ACTIVE_ADDR = PALETTE_PHASE_ADDR
LEVELSEL_ACTIVE_VALUE = 0xA0
DEATH_ATTR_PHASE_ADDR = 0xDF40
DEATH_ATTR_ACTIVE_ADDR = 0xDF46
# Keep the established scene cache at DF0D. An attempted move to the retired
# position-sweep flag at DF46 changed Ted's stock arena timing, proving that the
# byte is not inert enough to reuse as live scene state.
SCENE_CACHE_ADDR = 0xDF0D
ROW_CURSOR_ADDR = DEATH_ATTR_PHASE_ADDR
POSMAP_FLAG_ADDR = DEATH_ATTR_ACTIVE_ADDR
POSMAP_SCRATCH_ADDR = 0xDF47
# The base builder reserves 0x7E40-0x7F3F as a literal 256-byte zero table.
# The release builder replaces that redundant blob with two routines while
# retaining the exact WRAM table result through build_uniform_bg_clear().
STORY_ATTR_ADDR = SPLASH_TABLE_ADDR
STORY_ATTR_REGION_END = SPLASH_TABLE_ADDR + 0x100
# The 13-byte retired-sweep gap below the title glyphs holds the exact all-pal0
# WRAM clear. This leaves the prelude enough room for its stale-Window branch
# without adding any cycles to ordinary gameplay frames.
UNIFORM_CLEAR_ADDR = 0x6D43
STORY_ATTR_KEY_ADDR = 0xDF49
STORY_ATTR_ROW_ADDR = 0xDF4A
STORY_ATTR_MAP_DONE_ADDR = 0xDF4B
TITLE_GLYPH_DATA_ADDR = 0x6D50  # 16-byte-aligned period + digit-9 tiles
VRAM_GLYPH_COPY_ADDR = 0x6DA7   # gap: end of RLE expander -> COLORIZE_ADDR
STORY_INACTIVE_HELPER_ADDR = 0x6D9E
# The story writer is mapped in bank 13. A five-byte bridge in a verified-zero
# bank-13 asset gap maps bank 6, whose matching return address lands in a
# stock-zero 216-byte cave. The bank-6 helper selects one YAML region palette
# per art cell, remaps bank 13, and returns to the bounded VBlank writer.
STORY_REGION_BANK = 6
STORY_REGION_CAVE_START_ADDR = 0x4C54
STORY_REGION_CAVE_END_ADDR = 0x4D2C
# Use the tail of the exact stock-zero $4CE4-$4CF1 bank-13 gap.  Its return
# address leaves the bank-6 row writer enough room for the explicit neutral
# dialogue path before the matching bank-6 landing JP.
STORY_REGION_BRIDGE_ADDR = 0x4CED
STORY_REGION_BANK6_RETURN_ADDR = STORY_REGION_BRIDGE_ADDR + 5
STORY_REGION_WRITER_ADDR = 0x4CC3
STORY_REGION_LANDING_SIZE = 9
STORY_REGION_ROW_WRITER_ADDR = (
    STORY_REGION_BANK6_RETURN_ADDR + STORY_REGION_LANDING_SIZE
)
TITLE_FOOTER = "DX V3.01 STRUK LABS"
CUSTOM_TITLE_TILES = {
    # 0x75 is swallowed by the title command parser as a control value.
    ".": 0x7F,
    "0": 0x76,
    "1": 0x77,
    "3": 0x79,
}

PERIOD_TILE = bytes.fromhex("00 00 00 00 00 00 00 00 00 00 00 00 18 18 00 00")
NATIVE_DIGIT_9_TILE = bytes.fromhex(
    "00 00 7C 7C C6 C6 C6 C6 7E 7E 06 06 C6 C6 7C 7C"
)

# DF10-DF2F is bg_sweep scratch. DF0F sits beside the established DF0D scene
# cache and DF0E cold-boot sentinel, outside that clobber range.
MENU_WINDOW_SENTINEL = 0xDF0F
MENU_WINDOW_ATTR_ROWS = 6
DEATH_FADE_NORMAL = bytes.fromhex("FF7F B556 4A29 0000")
DEATH_FADE_INTERMEDIATE = bytes.fromhex("FF7F FF7F B556 4A29")
DEATH_FADE_WHITE = bytes.fromhex("FF7F FF7F FF7F FF7F")


def build_uniform_bg_clear() -> bytes:
    """Replace the 256-byte all-pal0 ROM table with an exact WRAM zero-fill."""
    c = bytearray([
        0x21, WRAM_BG_TABLE & 0xFF,
        WRAM_BG_TABLE >> 8,                  # LD HL, palette LUT
        0xAF,                                # XOR A
        0x06, 0x00,                          # LD B,0 (256 iterations)
        0x22, 0x05, 0x20, 0xFC,              # [HL+]=A; DEC B; JR NZ
        0xC9,                                # RET
    ])
    assert len(c) == 11
    return bytes(c)


def build_mirrored_gdma_bg_sweep() -> bytes:
    """Mirror the resolved 32-byte attribute row with one CGB GDMA.

    The original CPU loop still computes and writes exactly one active-map
    row. DF10-DF2F already contains that complete semantic row, so a two-block
    GDMA can copy it to the peer physical map without a second lookup/write
    loop and without extending the 18-frame room-repair counter.
    """
    sweep = bytearray(
        create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR)
    )
    old_tail = bytes.fromhex(
        "3E 01 E0 4F E1 11 10 DF 06 20 "
        "1A 22 1C 05 20 FA "
        "AF E0 4F E1 D1 C1 C9"
    )
    new_tail = bytes.fromhex(
        "3E 01 E0 4F E1 E5 11 10 DF 06 20 "
        "1A 22 1C 05 20 FA "
        "E1 7C EE 04 67 "
        "3E DF E0 51 3E 10 E0 52 "
        "7C E0 53 7D E0 54 3E 01 E0 55 "
        "AF E0 4F E1 D1 C1 C9"
    )
    matches = [
        index for index in range(len(sweep) - len(old_tail) + 1)
        if sweep[index:index + len(old_tail)] == old_tail
    ]
    assert matches == [len(sweep) - len(old_tail)]
    sweep[matches[0]:] = new_tail
    assert len(sweep) == 139
    return bytes(sweep)


def build_semantic_stage1_prototype(address: int) -> bytes:
    """Diagnostic native-copy tail: clear attrs, then stamp pickup metatiles.

    This intentionally lives in arena-table storage only for a Stage-1 timing
    experiment.  It must never be enabled in a release build; a passing timing
    result is expected to be relocated into the reclaimed Stage-1 services.
    """
    pickup_palettes = bytes([
        4, 4, 4, 4, 4, 5, 5, 5,
        1, 1, 1, 3, 3, 4, 4, 4,
        0, 0, 2, 5, 2, 2, 5, 2,
    ])

    def assemble(table_address: int) -> bytes:
        a = _Asm()
        a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02, 0xC0)
        a.db(
            0x7C, 0xD6, 0x03, 0x47,
            0x3E, 0x02, 0xE0, 0x70,
            0x78, 0xEA, 0xFE, 0xD3,
        )
        a.db(0xFA, 0xFF, 0xD3, 0xFE, 0xA5)
        a.jr(0x28, "initialized")
        a.db(0x21, 0x00, 0xD0, 0xAF, 0x06, 0x03)
        a.label("zero_page")
        a.db(0x0E, 0x00)
        a.label("zero_byte")
        a.db(0x22, 0x0D)
        a.jr(0x20, "zero_byte")
        a.db(0x05)
        a.jr(0x20, "zero_page")
        a.db(
            0x21, 0xF8, 0xD3, 0xAF,
            0x22, 0x22, 0x22, 0x77,
            0x3E, 0xA5, 0xEA, 0xFF, 0xD3,
        )

        a.label("initialized")
        # The native scroll path repeatedly recopies an unchanged packed map.
        # Key each physical destination with the same content discriminator
        # used by the receipt-covered Stage-1 runtime so only real content
        # transitions pay for the semantic metatile scan.
        a.db(
            0xFA, 0xFE, 0xD3, 0xE6, 0x04, 0x0F, 0xC6, 0xF8,
            0x5F, 0x16, 0xD3,
            0xFA, 0x0E, 0xDC, 0x47,
            0xFA, 0x97, 0xC2, 0xA8, 0x47,
            0xFA, 0x9B, 0xC2, 0xA8, 0x3C, 0x47,
            0x1A, 0xB8,
        )
        a.jr(0x20, "content_changed")
        a.db(0x3E, 0x01, 0xE0, 0x70, 0xC9)
        a.label("content_changed")
        a.db(0x78, 0x12, 0xFA, 0xFB, 0xD3, 0xB8)
        a.jr(0x20, "rebuild_stage")
        # The other physical map usually follows with the same content key.
        # Reuse the already-staged sparse plane instead of rescanning all 110
        # metatiles or clearing WRAM a second time.
        a.db(
            0x3E, 0x01, 0xE0, 0x4F,
            0x3E, 0xD0, 0xE0, 0x51,
            0xAF, 0xE0, 0x52,
            0xFA, 0xFE, 0xD3, 0xE0, 0x53,
            0xAF, 0xE0, 0x54,
            0x3E, 0x00, 0xE0, 0x55,
            0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70, 0xC9,
        )
        a.label("rebuild_stage")
        a.db(0x4F, 0x78, 0xEA, 0xFB, 0xD3, 0x79, 0xB7)
        a.jr(0x28, "stage_empty")
        a.db(0x21, 0x00, 0xD0, 0x06, 0x03, 0xAF)
        a.label("clear_old_page")
        a.db(0x0E, 0x00)
        a.label("clear_old_byte")
        a.db(0x22, 0x0D)
        a.jr(0x20, "clear_old_byte")
        a.db(0x05)
        a.jr(0x20, "clear_old_page")
        a.label("stage_empty")
        a.db(
            0xFA, 0x0E, 0xDC, 0x5F,
            0xFA, 0x0F, 0xDC, 0x57,
            0x26, 0xD0, 0x2E, 0x00,
            0x3E, 0x0A, 0xEA, 0xFC, 0xD3,
        )
        a.label("row")
        a.db(0x3E, 0x0B, 0xEA, 0xFD, 0xD3)
        a.label("cell")
        a.db(0x1A, 0x13, 0xD6, 0x26, 0xFE, 0x18)
        a.jr(0x30, "neutral")
        a.db(
            0xC6, table_address & 0xFF,
            0x4F, 0x06, table_address >> 8, 0x0A, 0xB7,
        )
        a.jr(0x28, "neutral")
        a.db(0x4F)
        a.db(0x79, 0x22, 0x22, 0x7D, 0xC6, 0x1E, 0x6F)
        a.jr(0x30, "top_no_carry")
        a.db(0x24)
        a.label("top_no_carry")
        a.db(0x79, 0x22, 0x22, 0x7D, 0xD6, 0x20, 0x6F)
        a.jr(0x30, "advance")
        a.db(0x25)
        a.jr(0x18, "advance")
        a.label("neutral")
        a.db(0x7D, 0xC6, 0x02, 0x6F)
        a.jr(0x30, "advance")
        a.db(0x24)
        a.label("advance")
        a.db(0xFA, 0xFD, 0xD3, 0x3D, 0xEA, 0xFD, 0xD3)
        a.jr(0x20, "cell")
        a.db(0x7B, 0xC6, 0x05, 0x5F)
        a.jr(0x30, "source_no_carry")
        a.db(0x14)
        a.label("source_no_carry")
        a.db(0x7D, 0xC6, 0x2A, 0x6F)
        a.jr(0x30, "destination_no_carry")
        a.db(0x24)
        a.label("destination_no_carry")
        a.db(0xFA, 0xFC, 0xD3, 0x3D, 0xEA, 0xFC, 0xD3)
        a.jr(0x20, "row")
        # Publish the completed sparse plane in one fixed-duration transfer.
        # It remains staged so the alternate physical map can reuse it.
        a.db(
            0x3E, 0x01, 0xE0, 0x4F,
            0x3E, 0xD0, 0xE0, 0x51,
            0xAF, 0xE0, 0x52,
            0xFA, 0xFE, 0xD3, 0xE0, 0x53,
            0xAF, 0xE0, 0x54,
            0x3E, 0x00, 0xE0, 0x55,
            0xAF, 0xE0, 0x4F,
            0x3C, 0xE0, 0x70, 0xC9,
        )
        return a.finish()

    provisional = assemble(address)
    table_address = address + len(provisional)
    code = assemble(table_address)
    assert len(code) == len(provisional)
    assert (table_address >> 8) == ((table_address + 23) >> 8)
    return code + pickup_palettes


def build_stage1_vblank_pickup_service(
    address: int,
    table_address: int,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Build a two-cell-per-VBlank native-source pickup scanner.

    Native FFBD room writers arm the service without touching the stock map
    copier. Each VBlank clears at most one old pickup or examines two packed
    metatile IDs; only actual pickups produce four attribute writes.
    """
    pickup_palettes = bytes([
        4, 4, 4, 4, 4, 5, 5, 5,
        1, 1, 1, 3, 3, 4, 4, 4,
        0, 0, 2, 5, 2, 2, 5, 2,
    ])
    assert (table_address & 0xFF) + len(pickup_palettes) <= 0x100

    worker = _Asm()
    worker.db(0xC5, 0xD5, 0xE5)
    worker.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xFE, 0xFF,
    )
    worker.jr(0x20, "not_init")
    # Normalize the active selector, clear the inactive queue, retain the old
    # count for bounded cleanup, and delay scanning until the next VBlank.
    worker.db(
        0xFA, STAGE1_PICKUP_ACTIVE_ADDR & 0xFF, 0xDF,
        0xE6, 0x01,
        0xEA, STAGE1_PICKUP_ACTIVE_ADDR & 0xFF, 0xDF,
        0x47, 0xEE, 0x01, 0xB7,
    )
    worker.jr(0x28, "clear_inactive0")
    worker.db(0x21, STAGE1_PICKUP_COUNT1_ADDR & 0xFF, 0xDF)
    worker.jr(0x18, "inactive_selected")
    worker.label("clear_inactive0")
    worker.db(0x21, STAGE1_PICKUP_COUNT0_ADDR & 0xFF, 0xDF)
    worker.label("inactive_selected")
    worker.db(0xAF, 0x77, 0x78, 0xB7)
    worker.jr(0x28, "old_count0")
    worker.db(0xFA, STAGE1_PICKUP_COUNT1_ADDR & 0xFF, 0xDF)
    worker.jr(0x18, "old_count_ready")
    worker.label("old_count0")
    worker.db(0xFA, STAGE1_PICKUP_COUNT0_ADDR & 0xFF, 0xDF)
    worker.label("old_count_ready")
    worker.db(
        0xEA, STAGE1_PICKUP_OLD_REMAIN_ADDR & 0xFF, 0xDF,
        0xAF,
        0xEA, STAGE1_PICKUP_SCAN_POS_ADDR & 0xFF, 0xDF,
        0x3E, 0xFE,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
    )
    worker.jr(0x18, "done")

    worker.label("not_init")
    worker.db(0xFE, 0xFE)
    worker.jr(0x20, "scan")
    worker.db(
        0xFA, STAGE1_PICKUP_OLD_REMAIN_ADDR & 0xFF,
        STAGE1_PICKUP_OLD_REMAIN_ADDR >> 8,
        0xB7,
    )
    worker.jr(0x28, "start_scan")
    worker.db(
        0x3D,
        0xEA, STAGE1_PICKUP_OLD_REMAIN_ADDR & 0xFF,
        STAGE1_PICKUP_OLD_REMAIN_ADDR >> 8,
        0x4F,
        0xFA, STAGE1_PICKUP_ACTIVE_ADDR & 0xFF,
        STAGE1_PICKUP_ACTIVE_ADDR >> 8,
        0xB7,
    )
    worker.jr(0x28, "old_buffer0")
    worker.db(0x21, STAGE1_PICKUP_ENTRIES1_ADDR & 0xFF, 0xDF)
    worker.jr(0x18, "old_address")
    worker.label("old_buffer0")
    worker.db(0x21, STAGE1_PICKUP_ENTRIES0_ADDR & 0xFF, 0xDF)
    worker.label("old_address")
    worker.db(0x79, 0x87, 0x85, 0x6F, 0x7E, 0x06, 0x00)
    worker.db(
        0xCD,
        STAGE1_PICKUP_WRITER_ADDR & 0xFF,
        STAGE1_PICKUP_WRITER_ADDR >> 8,
    )
    worker.jr(0x18, "done")

    worker.label("start_scan")
    worker.db(
        0x3E, 0xFD,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
    )
    worker.label("scan")
    worker.db(
        0xCD,
        STAGE1_PICKUP_SCANNER_ADDR & 0xFF,
        STAGE1_PICKUP_SCANNER_ADDR >> 8,
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xB7,
    )
    worker.jr(0x28, "done")
    worker.db(
        0xCD,
        STAGE1_PICKUP_SCANNER_ADDR & 0xFF,
        STAGE1_PICKUP_SCANNER_ADDR >> 8,
    )
    worker.label("done")
    worker.db(0xE1, 0xD1, 0xC1, 0xC9)
    worker_code = worker.finish()

    writer = _Asm()
    writer.db(
        0x57, 0xE6, 0x0F, 0x87, 0x5F,
        0x7A, 0xCB, 0x37, 0xE6, 0x0F, 0x4F,
        0xE6, 0x03, 0x0F, 0x0F, 0xB3, 0x6F,
        0x79, 0xCB, 0x3F, 0xCB, 0x3F, 0xC6, 0x98, 0x67,
        0x3E, 0x01, 0xE0, 0x4F,
        0x78, 0x22, 0x77, 0x2D,
        0x7C, 0xEE, 0x04, 0x67,
        0x78, 0x22, 0x77, 0x2D,
        # Stay on the alternate map for its bottom pair, then toggle back.
        # This removes one redundant H-map toggle from the VBlank budget.
        0x7D, 0xC6, 0x20, 0x6F,
        0x78, 0x22, 0x77, 0x2D,
        0x7C, 0xEE, 0x04, 0x67,
        0x78, 0x22, 0x77, 0x2D,
        0xAF, 0xE0, 0x4F, 0xC9,
    )
    writer_code = writer.finish()
    assert STAGE1_PICKUP_WRITER_ADDR + len(writer_code) <= STAGE1_PICKUP_APPENDER_ADDR

    appender = _Asm()
    appender.db(0xF5)
    appender.db(
        0xFA, STAGE1_PICKUP_ACTIVE_ADDR & 0xFF, 0xDF,
        0xEE, 0x01, 0xB7,
    )
    appender.jr(0x28, "append_buffer0")
    appender.db(0x21, STAGE1_PICKUP_COUNT1_ADDR & 0xFF, 0xDF)
    appender.jr(0x18, "append_selected")
    appender.label("append_buffer0")
    appender.db(0x21, STAGE1_PICKUP_COUNT0_ADDR & 0xFF, 0xDF)
    appender.label("append_selected")
    appender.db(0x7E, 0xFE, STAGE1_PICKUP_QUEUE_CAPACITY)
    appender.jr(0x30, "write")
    appender.db(0x4F, 0x34, 0x79, 0x87, 0x3C, 0x85, 0x6F)
    appender.db(0xF1, 0x77, 0x23, 0x70)
    appender.jr(0x18, "tail")
    appender.label("write")
    appender.db(0xF1)
    appender.label("tail")
    appender.db(
        0xC3,
        STAGE1_PICKUP_WRITER_ADDR & 0xFF,
        STAGE1_PICKUP_WRITER_ADDR >> 8,
    )
    appender_code = appender.finish()
    appender_blob = (
        writer_code
        + bytes(STAGE1_PICKUP_APPENDER_ADDR - (
            STAGE1_PICKUP_WRITER_ADDR + len(writer_code)
        ))
        + appender_code
    )

    scanner = _Asm()
    scanner.db(
        0xFA, STAGE1_PICKUP_SCAN_POS_ADDR & 0xFF, 0xDF,
        0xFE, 0xA0,
    )
    scanner.jr(0x38, "have_cell")
    scanner.db(
        0x21, STAGE1_PICKUP_ACTIVE_ADDR & 0xFF, 0xDF,
        0x7E, 0xEE, 0x01, 0x77,
        0xAF,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xC9,
    )
    scanner.label("have_cell")
    scanner.db(0x4F, 0x3C, 0x47, 0xE6, 0x0F, 0xFE, 0x0B, 0x78)
    scanner.jr(0x20, "store_next")
    scanner.db(0xC6, 0x05)
    scanner.label("store_next")
    scanner.db(
        0xEA, STAGE1_PICKUP_SCAN_POS_ADDR & 0xFF, 0xDF,
        0xFA, 0x0E, 0xDC, 0x6F,
        0xFA, 0x0F, 0xDC, 0x67,
        0x79, 0x85, 0x6F,
    )
    scanner.jr(0x30, "source_ready")
    scanner.db(0x24)
    scanner.label("source_ready")
    scanner.db(0x7E, 0xFE, 0xD7)
    scanner.jr(0x38, "low_band")
    scanner.db(0xD6, 0xB1)
    scanner.label("low_band")
    scanner.db(0xFE, 0x26)
    scanner.jr(0x38, "neutral")
    scanner.db(0xFE, 0x3E)
    scanner.jr(0x30, "neutral")
    scanner.db(
        0xD6, 0x26,
        0xC6, table_address & 0xFF,
        0x6F, 0x26, table_address >> 8,
        0x7E, 0xB7,
    )
    scanner.jr(0x28, "neutral")
    scanner.db(
        0x47, 0x79,
        0xC3,
        STAGE1_PICKUP_APPENDER_ADDR & 0xFF,
        STAGE1_PICKUP_APPENDER_ADDR >> 8,
    )
    scanner.label("neutral")
    scanner.db(0xC9)

    return (
        worker_code,
        appender_blob,
        scanner.finish(),
        pickup_palettes,
    )


def build_stage1_pickup_capture_hook() -> bytes:
    """Classify native metatile IDs and call the sparse appender on demand."""
    a = _Asm()
    # B/C count down from 10/11; only the first cell sums to 21.
    a.db(0xF5, 0x78, 0x81, 0xFE, 0x15)
    a.jr(0x28, "capture")
    a.label("classify")
    a.db(0xF1, 0xF5, 0xFE, 0xD7)
    a.jr(0x38, "low_band")
    a.db(0xD6, 0xB1)
    a.label("low_band")
    a.db(0xFE, 0x26)
    a.jr(0x38, "neutral")
    a.db(0xFE, 0x3E)
    a.jr(0x30, "neutral")
    a.label("capture")
    a.db(0xF1, 0xC3, 0x38, 0x08)
    a.label("neutral")
    a.db(0xF1, 0xC1, 0xD5, 0xC5, 0xC9)
    return a.finish()


def build_stage1_resident_pickup_service() -> tuple[
    bytes, bytes, bytes, bytes, bytes, bytes, bytes,
]:
    """Build the bank-13 sparse pickup pass used after native room repair."""
    palettes = bytes([
        4, 4, 4, 4, 4, 5, 5, 5,
        1, 1, 1, 3, 3, 4, 4, 4,
        0, 0, 2, 5, 2, 2, 5, 2,
    ])
    packed = bytes(
        (palettes[index] << 4) | palettes[index + 1]
        for index in range(0, len(palettes), 2)
    )

    write_front = bytes([
        0x57, 0xE6, 0x0F, 0x87, 0x5F,
        0x7A, 0xCB, 0x37, 0xE6, 0x0F, 0x4F,
        0xE6, 0x03, 0x0F, 0x0F, 0xB3, 0x6F,
        0x79, 0xCB, 0x3F, 0xCB, 0x3F, 0xC6, 0x98, 0x67,
        0x3E, 0x01, 0xE0, 0x4F,
        0xC3,
        STAGE1_PICKUP_WRITE_TAIL_ADDR & 0xFF,
        STAGE1_PICKUP_WRITE_TAIL_ADDR >> 8,
    ])
    assert len(write_front) == 32

    # The computed destination always begins in $9800. SET/RES bit 2 of H is
    # two bytes cheaper than a generic XOR and updates the matching $9C00 map.
    write_tail = bytes([
        0x78, 0x22, 0x77, 0x2D,
        0xCB, 0xD4,
        0x78, 0x22, 0x77, 0x2D,
        0x7D, 0xC6, 0x20, 0x6F,
        0x78, 0x22, 0x77, 0x2D,
        0xCB, 0x94,
        0x78, 0x22, 0x77, 0x2D,
        0xAF, 0xE0, 0x4F, 0xC9,
    ])
    assert len(write_tail) == 28

    decoder = _Asm()
    decoder.db(0x4F, 0xCB, 0x3F)
    decoder.db(0xC6, STAGE1_PICKUP_PACKED_TABLE_ADDR & 0xFF, 0x6F, 0x7E)
    decoder.db(0xCB, 0x41)
    decoder.jr(0x20, "low_nibble")
    decoder.db(0xCB, 0x37)
    decoder.label("low_nibble")
    decoder.db(0xE6, 0x0F, 0xC9)
    decoder_code = decoder.finish()
    assert len(decoder_code) <= 0x6E80 - STAGE1_PICKUP_DECODER_ADDR

    scan_one = _Asm()
    scan_one.db(
        0xFA, STAGE1_PICKUP_SCAN_POS_ADDR & 0xFF, 0xDF,
        0xFE, 0xA0,
    )
    scan_one.jr(0x38, "have_cell")
    scan_one.db(
        0xAF,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xC9,
    )
    scan_one.label("have_cell")
    scan_one.db(0x4F, 0x3C, 0x47, 0xE6, 0x0F, 0xFE, 0x0B, 0x78)
    scan_one.jr(0x20, "store_next")
    scan_one.db(0xC6, 0x05)
    scan_one.label("store_next")
    scan_one.db(
        0xEA, STAGE1_PICKUP_SCAN_POS_ADDR & 0xFF, 0xDF,
        0xFA, 0x0E, 0xDC, 0x6F,
        0xFA, 0x0F, 0xDC, 0x67,
        0x79, 0x85, 0x6F,
    )
    scan_one.jr(0x30, "source_ready")
    scan_one.db(0x24)
    scan_one.label("source_ready")
    scan_one.db(0x7E, 0xFE, 0xD7)
    scan_one.jr(0x38, "low_band")
    scan_one.db(0xD6, 0xB1)
    scan_one.label("low_band")
    scan_one.db(0xD6, 0x26, 0xFE, 0x18)
    scan_one.jr(0x30, "neutral")
    scan_one.db(
        0x26, STAGE1_PICKUP_PACKED_TABLE_ADDR >> 8,
        0xCD,
        STAGE1_PICKUP_DECODER_ADDR & 0xFF,
        STAGE1_PICKUP_DECODER_ADDR >> 8,
        0xB7,
    )
    scan_one.jr(0x28, "neutral")
    scan_one.db(
        0x47, 0x79,
        0xC3,
        INLINE_ATTR_DECISION_HELPER_ADDR & 0xFF,
        INLINE_ATTR_DECISION_HELPER_ADDR >> 8,
    )
    scan_one.label("neutral")
    scan_one.db(0xC9)
    scan_one_code = scan_one.finish()
    assert len(scan_one_code) <= 0x6A40 - STAGE1_PICKUP_SCAN_ONE_ADDR

    scan_main = _Asm()
    scan_main.db(0xC5, 0xD5, 0xE5, 0x06, 0x0A)
    scan_main.label("cell")
    scan_main.db(
        0xC5,
        0xCD,
        STAGE1_PICKUP_SCAN_ONE_ADDR & 0xFF,
        STAGE1_PICKUP_SCAN_ONE_ADDR >> 8,
        0xC1,
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xB7,
    )
    scan_main.jr(0x28, "done")
    scan_main.db(0x05)
    scan_main.jr(0x20, "cell")
    scan_main.label("done")
    scan_main.db(0xE1, 0xD1, 0xC1, 0xC9)
    scan_main_code = scan_main.finish()
    assert len(scan_main_code) <= 0x7B60 - STAGE1_PICKUP_SCAN_MAIN_ADDR

    room_service = _Asm()
    room_service.db(
        0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xFE, 0xA7,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xFE, 0x19,
    )
    room_service.jr(0x30, "scan")
    room_service.db(0xB7, 0xC8, 0x3D)
    room_service.jr(0x20, "store")
    room_service.db(
        0xAF,
        0xEA, STAGE1_PICKUP_SCAN_POS_ADDR & 0xFF, 0xDF,
        0x3E, 0xFF,
    )
    room_service.label("store")
    room_service.db(
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    )
    room_service.label("scan")
    room_service.db(
        0xC3,
        STAGE1_PICKUP_SCAN_MAIN_ADDR & 0xFF,
        STAGE1_PICKUP_SCAN_MAIN_ADDR >> 8,
    )
    room_service_code = room_service.finish()
    assert len(room_service_code) <= CONDITIONAL_PALETTE_IMPL_ADDR - ROOM_BG_REPAIR_ADDR

    return (
        write_front,
        write_tail,
        packed,
        decoder_code,
        scan_one_code,
        scan_main_code,
        room_service_code,
    )


def build_stage1_sync_pickup_service() -> tuple[
    bytes, bytes, bytes, bytes, bytes, bytes, bytes,
]:
    """Build a room-return queue scanner plus pickup-only VBlank publisher."""
    palettes = bytes([
        4, 4, 4, 4, 4, 5, 5, 5,
        1, 1, 1, 3, 3, 4, 4, 4,
        0, 0, 2, 5, 2, 2, 5, 2,
    ])
    packed = bytes(
        (palettes[index] << 4) | palettes[index + 1]
        for index in range(0, len(palettes), 2)
    )

    decoder = _Asm()
    decoder.db(0x5F, 0xCB, 0x3F)
    decoder.db(0xC6, STAGE1_SYNC_TABLE_ADDR & 0xFF, 0x6F, 0x7E)
    decoder.db(0xCB, 0x43)
    decoder.jr(0x20, "low_nibble")
    decoder.db(0xCB, 0x37)
    decoder.label("low_nibble")
    decoder.db(0xE6, 0x0F, 0xC9)
    decoder_code = decoder.finish()
    assert len(decoder_code) <= STAGE1_SYNC_TABLE_ADDR - STAGE1_SYNC_DECODER_ADDR

    scanner = _Asm()
    scanner.db(
        0xC5, 0xD5, 0xE5,
        0xFA, 0x0E, 0xDC, 0x47,
        0xFA, 0x97, 0xC2, 0xA8, 0x47,
        0xFA, 0x9B, 0xC2, 0xA8, 0x3C,
        0x21, STAGE1_PICKUP_BUILD_KEY_ADDR & 0xFF, 0xDF,
        0xBE,
    )
    scanner.jr(0x28, "done")
    scanner.db(
        0x77,
        0xAF,
        0xEA, STAGE1_PICKUP_COUNT0_ADDR & 0xFF, 0xDF,
        0xFA, 0x0E, 0xDC, 0x5F,
        0xFA, 0x0F, 0xDC, 0x57,
        0x06, 0x0A,
    )
    scanner.label("row")
    scanner.db(0x0E, 0x0B)
    scanner.label("cell")
    scanner.db(0x1A, 0x13, 0xFE, 0xD7)
    scanner.jr(0x38, "low_band")
    scanner.db(0xD6, 0xB1)
    scanner.label("low_band")
    scanner.db(0xD6, 0x26, 0xFE, 0x18)
    scanner.jr(0x30, "next_cell")
    scanner.db(
        0xC5, 0xD5,
        0x26, STAGE1_SYNC_TABLE_ADDR >> 8,
        0xCD,
        STAGE1_SYNC_DECODER_ADDR & 0xFF,
        STAGE1_SYNC_DECODER_ADDR >> 8,
        0xB7,
    )
    scanner.jr(0x28, "restore_cell")
    scanner.db(
        0x67,                               # H = palette
        0xD1, 0xC1,                        # restore source + row/column
        0x3E, 0x0A, 0x90, 0xCB, 0x37, 0xE6, 0xF0, 0x6F,
        0x3E, 0x0B, 0x91, 0xB5,            # A = packed row/column
        0xC5, 0xD5,
        0x5F, 0x44,                        # E = position; B = palette
        0x21, STAGE1_PICKUP_COUNT0_ADDR & 0xFF, 0xDF,
        0x7E, 0xFE, STAGE1_PICKUP_QUEUE_CAPACITY,
    )
    scanner.jr(0x30, "append_done")
    scanner.db(
        0x4F, 0x34, 0x79, 0x87, 0x3C, 0x85, 0x6F,
        0x73, 0x23, 0x70,
    )
    scanner.label("append_done")
    scanner.db(0xD1, 0xC1)
    scanner.jr(0x18, "next_cell")
    scanner.label("restore_cell")
    scanner.db(0xD1, 0xC1)
    scanner.label("next_cell")
    scanner.db(0x0D)
    scanner.jr(0x20, "cell")
    scanner.db(0x7B, 0xC6, 0x05, 0x5F)
    scanner.jr(0x30, "source_ready")
    scanner.db(0x14)
    scanner.label("source_ready")
    scanner.db(0x05)
    scanner.jr(0x20, "row")
    scanner.label("done")
    scanner.db(
        0xE1, 0xD1, 0xC1,
        0x3E, 0x01,
        0xC3, 0x61, 0x00,
    )
    scanner_code = scanner.finish()
    assert len(scanner_code) <= STAGE1_SYNC_DECODER_ADDR - STAGE1_SYNC_SCANNER_ADDR

    # Replace only the final RET of the native $139A metatile expander. This
    # runs once per packed-map build, not once per tilemap copy or metatile.
    # The fixed secondary discards the synthetic RST return, preserves AF,
    # and admits only ordinary gameplay scene $02.
    # Diagnostic neutral return: isolate the one-time RST seam itself from
    # all scan/publication work.
    fixed_asm = _Asm()
    fixed_asm.db(0x33, 0x33, 0xC9)
    fixed = fixed_asm.finish()
    assert len(fixed) <= 0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR

    writer_front = bytes([
        0x57, 0xE6, 0x0F, 0x87, 0x5F,
        0x7A, 0xCB, 0x37, 0xE6, 0x0F, 0x4F,
        0xE6, 0x03, 0x0F, 0x0F, 0xB3, 0x6F,
        0x79, 0xCB, 0x3F, 0xCB, 0x3F, 0xC6, 0x98, 0x67,
        0x3E, 0x01, 0xE0, 0x4F,
        0xC3,
        STAGE1_PICKUP_RESIDENT_TAIL1_ADDR & 0xFF,
        STAGE1_PICKUP_RESIDENT_TAIL1_ADDR >> 8,
    ])
    assert len(writer_front) == 32
    writer_tail1 = bytes([
        0x78, 0x22, 0x77, 0x2D,
        0xCB, 0xD4,
        0x78, 0x22, 0x77, 0x2D,
        0x7D, 0xC6, 0x20, 0x6F,
        0x78, 0x22, 0x77, 0x2D,
        0xC3,
        STAGE1_PICKUP_RESIDENT_TAIL2_ADDR & 0xFF,
        STAGE1_PICKUP_RESIDENT_TAIL2_ADDR >> 8,
    ])
    assert len(writer_tail1) <= 0x7B60 - STAGE1_PICKUP_RESIDENT_TAIL1_ADDR
    writer_tail2 = bytes([
        0xCB, 0x94,
        0x78, 0x22, 0x77, 0x2D,
        0xAF, 0xE0, 0x4F,
        0xC9,
    ])
    assert len(writer_tail2) <= 0x6E80 - STAGE1_PICKUP_RESIDENT_TAIL2_ADDR

    publish = _Asm()
    publish.db(
        0xC5, 0xD5, 0xE5,
        0xFA, STAGE1_PICKUP_COUNT0_ADDR & 0xFF, 0xDF,
        0xB7,
    )
    publish.jr(0x28, "done")
    publish.db(
        0x4F,
        0x21, STAGE1_PICKUP_ENTRIES0_ADDR & 0xFF, 0xDF,
    )
    publish.label("next")
    publish.db(
        0x2A, 0x46, 0x23,
        0xC5, 0xE5,
        0xCD,
        STAGE1_PICKUP_RESIDENT_WRITER_ADDR & 0xFF,
        STAGE1_PICKUP_RESIDENT_WRITER_ADDR >> 8,
        0xE1, 0xC1, 0x0D,
    )
    publish.jr(0x20, "next")
    publish.label("done")
    publish.db(0xE1, 0xD1, 0xC1, 0xC9)
    publish_code = publish.finish()
    assert len(publish_code) <= 0x6A40 - STAGE1_PICKUP_VBLANK_HELPER_ADDR

    room = _Asm()
    room.db(
        0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xFE, 0xA7,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xB7, 0xC8, 0x3D,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    )
    room_code = room.finish()
    assert len(room_code) <= CONDITIONAL_PALETTE_IMPL_ADDR - ROOM_BG_REPAIR_ADDR

    writer = (writer_front, writer_tail1, writer_tail2)
    return fixed, scanner_code, decoder_code, packed, writer, publish_code, room_code


def build_stage1_scroll_edge_room_service() -> bytes:
    """Color only the row exposed by an eight-pixel Stage-1 Y scroll.

    Native room writers retain the proven 18-row repair. Once that bounded
    pass completes, DF4E=$80 keeps this lightweight guard reachable from the
    existing VBlank call site. Ordinary frames return after one masked SCY
    comparison; an actual tile-row crossing reuses the exact production
    tile-to-palette sweep for the newly exposed edge. Terrain VRAM is never
    written here. The title demo retains its established alternating repair,
    and all later scenes keep the ordinary bounded counter contract.
    """
    a = _Asm()
    a.db(
        0xFA, 0x80, 0xD8,
        0xFE, 0x0A,
    )
    a.jr(0x28, "demo")
    a.db(0xFE, 0x02)
    a.jr(0x28, "stage1")

    # Later stages: preserve the existing room-bounded sweep exactly.
    a.label("ordinary")
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xB7, 0xC8, 0x3D,
    )
    a.label("store_sweep")
    a.db(
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    )

    a.label("stage1")
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xFE, 0x80,
    )
    a.jr(0x28, "edge")
    a.db(0xB7, 0xC8, 0x3D)
    a.jr(0x20, "store_sweep")
    # Arm steady edge mode after the receipt-proven final repair row.
    a.db(0x3E, 0x80)
    a.jr(0x18, "store_sweep")

    a.label("demo")
    a.db(
        0xC3,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR & 0xFF,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR >> 8,
    )

    a.label("edge")
    a.db(
        0xC5,
        0xF0, 0x42, 0xE6, 0xF8,
        0x21, STAGE1_SCROLL_TILE_Y_CACHE_ADDR & 0xFF,
        STAGE1_SCROLL_TILE_Y_CACHE_ADDR >> 8,
        0x46, 0xB8,
    )
    a.jr(0x28, "edge_done")
    a.db(
        0x77, 0x90, 0xFE, 0x08,
        0x3E, 0x11,
    )
    a.jr(0x20, "phase_ready")
    a.db(0x3D)
    a.label("phase_ready")
    a.db(
        0xEA, 0x04, 0xDF,
        0xC1,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    )
    a.label("edge_done")
    a.db(0xC1, 0xC9)
    code = a.finish()
    assert len(code) <= 0x6A40 - STAGE1_SCROLL_EDGE_SERVICE_ADDR, len(code)
    return code


def build_stage1_dualpass_room_service() -> bytes:
    """Spend 36 bounded rows on Stage 1 and preserve 18 elsewhere."""
    a = _Asm()
    a.db(
        0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xFE, 0xA7,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
        0xFA, 0x80, 0xD8,
        0xFE, 0x02,
    )
    a.jr(0x28, "stage1")
    a.db(0xFE, 0x0A)
    a.jr(0x28, "demo")

    # All later scenes retain the production 18-row upper bound even though
    # the shared FFBD hook arms 36 for live Stage 1.
    a.label("ordinary")
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xFE, 0x13,
    )
    a.jr(0x38, "ordinary_ready")
    a.db(0x3E, 0x12)
    a.label("ordinary_ready")
    a.db(0xB7, 0xC8, 0x3D)
    a.label("store_sweep")
    a.db(
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    )

    a.label("stage1")
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xB7, 0xC8, 0x3D,
    )
    a.jr(0x18, "store_sweep")

    a.label("demo")
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
        0xFE, 0x13,
    )
    a.jr(0x38, "demo_ready")
    a.db(
        0x3E, 0x12,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
        BG_SWEEP_COUNT_ADDR >> 8,
    )
    a.label("demo_ready")
    a.db(
        0xC3,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR & 0xFF,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR >> 8,
    )
    code = a.finish()
    assert len(code) <= 0x6A40 - STAGE1_SCROLL_EDGE_SERVICE_ADDR, len(code)
    return code


def build_story_region_classifier(
    panels: dict[int, CutscenePanel],
) -> tuple[bytes, bytes, dict[str, int]]:
    """Compile exact YAML story masks into a bounded bank-6 row lookup.

    The runtime writer receives an art ID, row, and five-cell quarter. Seven
    eight-row pointer slots select one deduplicated row: slot 0 is the
    neutral dialogue area, slots 1..6 are art IDs 1..6, and stock-equivalent
    Sara art ID 7 aliases slot 2.  Each row is run-length encoded as
    ``(inclusive_end_column << 3) | palette``; the final run always ends at
    column 19, so no sentinel or rectangle scan is needed. The writer tests
    only the few row runs that touch each quarter, including the most detailed
    Sara and Lisa panels, while preserving the exact YAML mask.
    """
    masks = {
        art_id: cutscene_panel_mask(panels[art_id])
        for art_id in range(1, 8)
    }
    assert masks[7] == masks[2], (
        "the compact story table requires stock Sara art IDs 2 and 7 to "
        "share one YAML mask"
    )
    neutral_row = tuple(0 for _ in range(CUTSCENE_ART_COLUMNS))
    unique_rows: list[tuple[int, ...]] = [neutral_row]
    for art_id in range(1, 7):
        for row in masks[art_id]:
            if row not in unique_rows:
                unique_rows.append(row)

    pointer_table_size = 7 * CUTSCENE_ART_ROWS
    row_data_start = STORY_REGION_CAVE_START_ADDR + pointer_table_size
    row_data = bytearray()
    row_addresses: dict[tuple[int, ...], int] = {}
    row_runs = 0
    for row in unique_rows:
        assert len(row) == CUTSCENE_ART_COLUMNS
        address = row_data_start + len(row_data)
        if address >> 8 != STORY_REGION_CAVE_START_ADDR >> 8:
            raise AssertionError("story row data escaped bank-6 page $4C")
        row_addresses[row] = address
        start = 0
        while start < CUTSCENE_ART_COLUMNS:
            palette = row[start]
            assert 0 <= palette < 8
            end = start
            while (
                end + 1 < CUTSCENE_ART_COLUMNS
                and row[end + 1] == palette
            ):
                end += 1
            row_data.append((end << 3) | palette)
            row_runs += 1
            start = end + 1
        assert row_data[-1] >> 3 == CUTSCENE_ART_COLUMNS - 1

    pointers = bytearray(pointer_table_size)
    neutral_address = row_addresses[neutral_row] & 0xFF
    for row_index in range(CUTSCENE_ART_ROWS):
        pointers[row_index] = neutral_address
    for art_id in range(1, 7):
        for row_index, row in enumerate(masks[art_id]):
            pointers[art_id * CUTSCENE_ART_ROWS + row_index] = (
                row_addresses[row] & 0xFF
            )

    data = bytes(pointers + row_data)
    assert (
        STORY_REGION_CAVE_START_ADDR + len(data)
        <= STORY_REGION_WRITER_ADDR
    ), "YAML story row data collides with the bank-6 writer"

    writer = _Asm()
    writer.db(
        0xE5,                               # preserve destination HL
        0x79, 0xE6, 0x07,                  # art ID / neutral separator slot
    )
    writer.jr(0x20, "art_pointer")
    writer.db(0x0E, neutral_address)         # lower dialogue uses neutral row
    writer.jr(0x18, "have_pointer")
    writer.label("art_pointer")
    writer.db(
        0xFE, 0x07,
    )
    writer.jr(0x20, "mapped_art")
    writer.db(0x3E, 0x02)                   # stock Sara ID 7 aliases ID 2
    writer.label("mapped_art")
    writer.db(
        0x07, 0x07, 0x07,                  # table slot * eight rows
        0x80,                               # add visible row B
        0xC6, STORY_REGION_CAVE_START_ADDR & 0xFF,
        0x6F, 0x26, 0x4C,                  # HL = row-pointer entry
        0x4E,                               # C = row-list low byte
    )
    writer.label("have_pointer")
    writer.db(
        0xE1,                               # restore destination HL
        0x06, 0x4C,                         # BC = selected row-list address
        0x1E, 0x05,                         # E = five cells in this quarter
        0xC3,
        STORY_REGION_ROW_WRITER_ADDR & 0xFF,
        STORY_REGION_ROW_WRITER_ADDR >> 8,
    )
    writer_code = writer.finish()
    assert (
        STORY_REGION_WRITER_ADDR + len(writer_code)
        <= STORY_REGION_BANK6_RETURN_ADDR
    ), "story region writer collides with the bank-switch return bridge"

    row_writer = _Asm()
    row_writer.label("scan")
    row_writer.db(
        0x0A,                               # packed end/palette at [BC]
        0xC5, 0x4F,                         # save source; C = packed byte
        0x0F, 0x0F, 0x0F, 0xE6, 0x1F,      # inclusive end column
        0xBA,                               # end column < current D?
    )
    row_writer.jr(0x30, "selected")         # current run covers this cell
    row_writer.db(0xC1, 0x03)                # restore/advance row-list source
    row_writer.jr(0x18, "scan")

    # B becomes the number of cells from current D through this run's end;
    # C becomes its palette. The source pointer remains on the stack until
    # the run or the five-cell quarter finishes.
    row_writer.label("selected")
    row_writer.db(
        0x92, 0x3C, 0x47,                  # B = end - column + 1
        0x79, 0xE6, 0x07, 0x4F,            # C = palette
    )
    row_writer.label("write")
    # The stock story renderer can consume the remaining VBlank before this
    # late service point. Wait out modes 2/3 so no palette cell is silently
    # dropped at the LCD's VRAM boundary; HBlank/VBlank both remain writable.
    row_writer.label("wait_vram")
    row_writer.db(0xF0, 0x41, 0xE6, 0x02)
    row_writer.jr(0x20, "wait_vram")
    row_writer.db(
        0x79,                               # reload cached palette
        0x22,                               # write palette; advance VRAM HL
        0x14,                               # next visible column
        0x1D,
    )
    row_writer.jr(0x28, "done")             # five-cell quarter is complete
    row_writer.db(0x05)                      # remaining cells in current run
    row_writer.jr(0x20, "write")
    row_writer.db(0xC1, 0x03)                # advance to the next encoded run
    row_writer.jr(0x18, "scan")
    row_writer.label("done")
    row_writer.db(
        0xC1,                               # discard saved source pointer
        0x3E, 0x0D, 0xB7,                  # restore bank 13; return NZ
        0xC3, 0x61, 0x00,
    )
    row_writer_code = row_writer.finish()
    assert (
        STORY_REGION_ROW_WRITER_ADDR + len(row_writer_code)
        <= STORY_REGION_CAVE_END_ADDR
    ), "story region row writer overruns the verified bank-6 cave"

    bank6 = bytearray(
        STORY_REGION_CAVE_END_ADDR - STORY_REGION_CAVE_START_ADDR
    )
    bank6[:len(data)] = data
    writer_offset = STORY_REGION_WRITER_ADDR - STORY_REGION_CAVE_START_ADDR
    bank6[writer_offset:writer_offset + len(writer_code)] = writer_code
    row_writer_offset = (
        STORY_REGION_ROW_WRITER_ADDR - STORY_REGION_CAVE_START_ADDR
    )
    bank6[
        row_writer_offset:row_writer_offset + len(row_writer_code)
    ] = row_writer_code
    return_offset = (
        STORY_REGION_BANK6_RETURN_ADDR - STORY_REGION_CAVE_START_ADDR
    )
    # The landing is also reachable from historical gameplay states captured
    # inside the interrupted bank wrapper. Only non-gameplay story entry may
    # continue into the YAML writer; gameplay jumps backward to a five-byte
    # bank-13 restore tail and then returns through its saved caller stack.
    landing = bytes([
        0xF0, 0xC1, 0xB7,
        0xC2,
        STORY_REGION_BRIDGE_ADDR & 0xFF,
        STORY_REGION_BRIDGE_ADDR >> 8,      # FFC1 != 0 -> restore bank 13
        0xC3,
        STORY_REGION_WRITER_ADDR & 0xFF,
        STORY_REGION_WRITER_ADDR >> 8,
    ])
    assert len(landing) == STORY_REGION_LANDING_SIZE
    bank6[return_offset:return_offset + len(landing)] = landing
    # This bank-6 shadow is skipped by production story entry, which resumes
    # at bridge+5. It restores bank 13 for the guarded stale-gameplay landing.
    wrong_bank_guard_offset = (
        STORY_REGION_BRIDGE_ADDR - STORY_REGION_CAVE_START_ADDR
    )
    wrong_bank_restore = bytes([0x3E, 0x0D, 0xC3, 0x61, 0x00])
    assert bank6[
        wrong_bank_guard_offset:
        wrong_bank_guard_offset + len(wrong_bank_restore)
    ] == bytes(len(wrong_bank_restore))
    bank6[
        wrong_bank_guard_offset:
        wrong_bank_guard_offset + len(wrong_bank_restore)
    ] = wrong_bank_restore

    bridge = bytes([
        0x3E, STORY_REGION_BANK,
        0xCD, 0x61, 0x00,
    ])
    return bridge, bytes(bank6), {
        "art_ids": len(panels),
        "unique_panels": len({panel.name for panel in panels.values()}),
        "rectangles": sum(
            len(panel.regions)
            for panel in {panel.name: panel for panel in panels.values()}.values()
        ),
        "unique_rows": len(unique_rows),
        "row_runs": row_runs,
        "data_bytes": len(data),
        "writer_bytes": len(writer_code),
        "row_writer_bytes": len(row_writer_code),
        "landing_bytes": len(landing),
        "wrong_bank_guard": STORY_REGION_BRIDGE_ADDR,
    }


def build_story_attr_sweep() -> tuple[bytes, int, int, int]:
    """Color one committed story/ending attribute row per VBlank.

    Story artwork uses BG1..BG7 according to its committed DCF0/DD07 art ID;
    the dialogue rows stay on neutral BG0.  Credits, END, and epilogue use
    BG1, BG2, and BG3 across the full viewport.  Every state guard comes from
    the deterministic full-story inventories.

    DF49 caches the guarded page key and DF4A advances the row.  The pass waits
    for the existing two-map neutral cleaner (DF07) to finish, then writes only
    one 32-cell map row per VBlank.  That bounded cost avoids the progression
    delay caused by the discarded whole-viewport per-frame prototype.
    """
    a = _Asm()

    # Every supported story page is non-gameplay.
    a.db(0xF0, 0xC1, 0xB7)                    # LDH A,[FFC1]; OR A
    a.jr(0x20, "inactive")                   # JR NZ,inactive
    a.label("story_dispatch")

    # Dispatch exact story families and direct-written ending phases.
    a.db(0xFA, 0x80, 0xD8)                   # LD A,[D880]
    a.db(0xFE, 0x15)
    a.jr(0x28, "story_opening")
    a.db(0xFE, 0x19)
    a.jr(0x28, "story_pre_final")
    a.db(0xFE, 0x1A)
    a.jr(0x28, "story_post_final")
    a.db(0xFE, 0x16)
    a.jr(0x28, "ending_credits_or_end")
    a.db(0xB7)
    a.jr(0x28, "ending_epilogue")

    # Any unclassified scene clears the page cache.  A later page with the same
    # palette ID therefore starts at row zero instead of inheriting a done row.
    a.label("inactive")
    a.db(
        0xC3,
        STORY_INACTIVE_HELPER_ADDR & 0xFF,
        STORY_INACTIVE_HELPER_ADDR >> 8,
    )

    # B carries the exact sequence discriminator into the shared story guard.
    a.label("story_opening")
    a.db(0x06, 0x02)
    a.jr(0x18, "story_guard")
    a.label("story_pre_final")
    a.db(0x06, 0x04)
    a.jr(0x18, "story_guard")
    a.label("story_post_final")
    a.db(0x06, 0x05)

    a.label("story_guard")
    a.db(0xFA, 0xE8, 0xDC, 0xB8)            # DCE8 == B
    a.jr(0x20, "inactive")
    a.db(0xFA, 0xEA, 0xDC, 0xFE, 0x01)      # DCEA == 1
    a.jr(0x20, "inactive")
    a.db(0xFA, 0xF0, 0xDC, 0x4F)            # C = DCF0 art ID
    a.db(0xB7)
    a.jr(0x28, "inactive")                  # reject art 0
    a.db(0xFE, 0x08)
    a.jr(0x30, "inactive")                  # reject IDs outside BG1..BG7
    a.db(0xFA, 0x07, 0xDD, 0x3C, 0xB9)      # DD07+1 == art ID
    a.jr(0x20, "inactive")
    # Include the production viewport's one-tile SCY/SCX offset in bit 4.
    # The opening book commits at 0/0, then settles at 8/8; restarting at that
    # boundary prevents a completed pre-scroll pass from leaving holes.
    a.db(
        0xCD,
        STORY_VIEWPORT_KEY_HELPER_ADDR & 0xFF,
        STORY_VIEWPORT_KEY_HELPER_ADDR >> 8,
    )
    a.jr(0x18, "have_key")

    # Credits and END share all guards except FFF9, which is exactly 0 or 1.
    a.label("ending_credits_or_end")
    a.db(0xF0, 0xE4, 0xFE, 0x01)            # FFE4 == 1
    a.jr(0x20, "inactive")
    a.db(0xFA, 0x89, 0xD8, 0xFE, 0x01)      # D889 == 1
    a.jr(0x20, "inactive")
    a.db(0xFA, 0xE2, 0xDC, 0xB7)            # DCE2 == 0
    a.jr(0x20, "inactive")
    a.db(0xF0, 0xF9, 0xFE, 0x02)            # FFF9 in {0,1}
    a.jr(0x30, "inactive")
    a.db(0x3C, 0xF6, 0x40)                  # key = $41 credits / $42 END
    a.jr(0x18, "have_key")

    a.label("ending_epilogue")
    a.db(0xF0, 0xE4, 0xFE, 0x01)            # FFE4 == 1
    a.jr(0x20, "inactive")
    a.db(0xFA, 0x89, 0xD8, 0xFE, 0x0C)      # D889 == $0C
    a.jr(0x20, "inactive")
    a.db(0xF0, 0xF9, 0xFE, 0x01)            # FFF9 == 1
    a.jr(0x20, "inactive")
    a.db(0xFA, 0xE2, 0xDC, 0xB7)            # DCE2 0=preamble, 1=text
    a.jr(0x28, "ending_epilogue_preamble")
    a.db(0xFE, 0x01)
    a.jr(0x20, "inactive")
    a.db(0x3E, 0x43)                        # key = epilogue text BG3
    a.jr(0x18, "have_key")
    a.label("ending_epilogue_preamble")
    a.db(0x3E, 0x40)                        # key = neutral full viewport

    a.label("have_key")
    # Fold the active BG-map select into the cache key. The epilogue changes
    # 0x9800 -> 0x9C00 while D880/D889/DCE2 remain otherwise stable; this one
    # bit restarts the bounded pass exactly when the destination map changes.
    a.db(0x4F, 0xF0, 0x40, 0xE6, 0x08, 0xB1)
    a.db(0x4F)                              # C = guarded page/map key
    a.db(0xFA, STORY_ATTR_KEY_ADDR & 0xFF,
         STORY_ATTR_KEY_ADDR >> 8, 0xB9)    # same page?
    a.jr(0x28, "same_key")
    a.db(0x79, 0xEA, STORY_ATTR_KEY_ADDR & 0xFF,
         STORY_ATTR_KEY_ADDR >> 8)
    a.db(0xAF, 0xEA, STORY_ATTR_ROW_ADDR & 0xFF,
         STORY_ATTR_ROW_ADDR >> 8)          # new page starts at row 0

    a.label("same_key")
    # Pre/post-final entry deliberately restarts the neutral cleaner.  Do not
    # let that later erase rows which this pass has already colored.
    a.db(0xFA, 0x07, 0xDF, 0xB7)            # LD A,[DF07]; OR A
    a.db(0xC0)                              # RET NZ
    a.db(0xFA, STORY_ATTR_ROW_ADDR & 0xFF,
         STORY_ATTR_ROW_ADDR >> 8, 0x47)    # B = row

    # Story pages color top rows 0..7. Ending pages make finite passes
    # over all 32 rows of the active tilemap; this covers direct VRAM writes
    # that fall beyond a crowded VBlank while ensuring later epilogue SCY
    # motion cannot expose a stale off-viewport row after the pass goes dormant.
    a.db(0xCB, 0x79)                        # BIT 7,C (story key)
    a.jr(0x28, "ending_limit")
    # Each story row is split into four five-cell quarters. The bank-6 writer
    # waits for writable LCD modes, so one exact 32-quarter art pass replaces
    # the old three-pass retry strategy. The lower dialogue rows are then
    # explicitly neutralized before the service goes dormant.
    a.db(0x16, 0x00)                        # D = left-half offset by default
    a.db(
        0xC3,
        STORY_HALF_ROW_HELPER_ADDR & 0xFF,
        STORY_HALF_ROW_HELPER_ADDR >> 8,
    )
    a.label("ending_limit")
    # Credits and the epilogue scroll SCY while this bounded pass runs. A
    # helper converts the row counter to an SCY-relative B value so the shared
    # address calculation still lands on each absolute map row exactly once.
    a.db(
        0xC3,
        ENDING_ABSOLUTE_ROW_HELPER_ADDR & 0xFF,
        ENDING_ABSOLUTE_ROW_HELPER_ADDR >> 8,
    )

    a.label("row_in_range")
    # Tilemap row = ((SCY >> 3) + visible_row) & 31. Start at the current
    # viewport column and touch only its 20 cells. The previous 32-cell write
    # overran the crowded story VBlank, leaving the right side of some book
    # rows unchanged even after repeated passes.
    a.db(0xF0, 0x42, 0x0F, 0x0F, 0x0F, 0xE6, 0x1F)
    a.db(0x80, 0xE6, 0x1F)                  # ADD B; AND $1F
    a.db(0x6F, 0x26, 0x00)                  # HL = row
    a.db(0x29, 0x29, 0x29, 0x29, 0x29)      # HL *= 32
    a.db(
        0xC3,
        STORY_COLUMN_HELPER_ADDR & 0xFF,
        STORY_COLUMN_HELPER_ADDR >> 8,
    )
    a.label("after_column")
    a.db(0xF0, 0x40, 0xE6, 0x08)            # active BG map
    a.jr(0x28, "map_9800")
    a.db(0x3E, 0x9C)
    a.jr(0x18, "have_map")
    a.label("map_9800")
    a.db(0x3E, 0x98)
    a.label("have_map")
    a.db(0x84, 0x67)                        # H += map base high byte

    # These are DMG-authored screens with no intentional CGB bank/flip/
    # priority metadata. Story quarters call the YAML rectangle classifier;
    # ending rows retain one exact palette byte across the viewport. Both paths
    # clear stale bank/flip/priority bits by writing only values 0..7.
    a.db(0xF0, 0x4F, 0xF5, 0x3E, 0x01, 0xE0, 0x4F)
    a.db(0xCB, 0x79)                        # BIT 7,C (story key)
    a.db(
        0xC4,
        STORY_REGION_BRIDGE_ADDR & 0xFF,
        STORY_REGION_BRIDGE_ADDR >> 8,
    )                                      # CALL NZ: writes story five-cell run
    a.jr(0x20, "after_write")              # helper deliberately returns NZ
    a.db(0x79, 0xE6, 0x07, 0x06, 0x04)      # ending palette; four five-cell runs
    a.label("write_five")
    a.db(0x22, 0x22, 0x22, 0x22, 0x22, 0x05)
    a.jr(0x20, "write_five")
    a.label("after_write")
    a.db(0xF1, 0xE0, 0x4F)                  # restore VBK
    a.db(0xFA, STORY_ATTR_ROW_ADDR & 0xFF,
         STORY_ATTR_ROW_ADDR >> 8, 0x3C)
    a.db(0xEA, STORY_ATTR_ROW_ADDR & 0xFF,
         STORY_ATTR_ROW_ADDR >> 8, 0xC9)
    code = a.finish()
    return (
        code,
        STORY_ATTR_ADDR + a.labels["story_dispatch"],
        STORY_ATTR_ADDR + a.labels["row_in_range"],
        STORY_ATTR_ADDR + a.labels["after_column"],
    )


def build_cutscene_palette_bridge(
    story_dispatch_addr: int,
) -> tuple[bytes, bytes]:
    """Preload all YAML BG rows before guarded story attributes run.

    The death dispatcher enters with A=D880. The tiny entry accepts only
    $15/$16/$19/$1A. Subtracting $15 and bounding at six excludes title
    $1B/$1C; the two intervening death scenes are handled earlier. Unsupported
    scenes return immediately. The earlier title-palette service dispatches
    the exact D880=$00/FFE4=$01 epilogue without reloading the complete deck.

    The body tags D880 into DF4D's high-bit namespace, disjoint from spotlight
    identity+1 values. A new family starts at BG phase 9. Cached families tail
    to the ordinary story dispatcher only after phase 16 clears the cursor.
    """
    bridge = bytes([
        # A already equals D880 from the death service's exact scene guard.
        0xD6, 0x15,                        # supported offset
        0xFE, 0x06,
        0xD0,                              # title/other -> fast RET NC
        0xC3,                              # supported -> loader body
        CUTSCENE_PALETTE_CONT_ADDR & 0xFF,
        CUTSCENE_PALETTE_CONT_ADDR >> 8,
    ])
    a = _Asm()
    a.db(
        0xF6, 0x80,                        # tagged family key
        0x21,
        SPOTLIGHT_PALETTE_CACHE_ADDR & 0xFF,
        SPOTLIGHT_PALETTE_CACHE_ADDR >> 8,
        0xBE,                              # same family?
    )
    a.jr(0x28, "cached")
    a.db(
        0x32,                              # cache tag; HL -> phase byte
        0x3E, 0x09,
        0x77,                              # begin with YAML BG phase 9
    )
    a.jr(0x18, "service")
    a.label("cached")
    a.db(0x2D, 0x7E, 0xB7)                 # active palette phase?
    a.db(0xCA, story_dispatch_addr & 0xFF, story_dispatch_addr >> 8)
    a.label("service")
    a.db(0xC3, PALETTE_LOADER_ADDR & 0xFF, PALETTE_LOADER_ADDR >> 8)
    continuation = a.finish()
    assert (
        CUTSCENE_PALETTE_BRIDGE_ADDR + len(bridge)
        <= CUTSCENE_PALETTE_BRIDGE_END
    )
    assert (
        CUTSCENE_PALETTE_CONT_ADDR + len(continuation)
        <= CUTSCENE_PALETTE_CONT_END
    )
    return bridge, continuation


def build_death_attr_service(story_dispatch_addr: int) -> bytes:
    """Neutralize both stock death/game-over tilemaps over seven VBlanks.

    D880=$17 first renders a scrolled illustration on the stock $9C00 BG map,
    then enables a window backed by the stock $9800 map roughly 35 frames
    later. The gameplay colorizer previously treated this as a dungeon-family
    scene, so arena palette attributes survived in both maps.

    Three rows of each map are cleared per call. Seven calls cover 21 rows:
    all 18 visible rows plus the partial scroll edge. Attribute byte zero
    selects BG0 and also removes stale bank, flip, and priority bits.
    """
    a = _Asm()

    # This is the wrapper's first service point. Normal gameplay takes a
    # shorter path than the old story-inactive helper: if its story cache is
    # already clear, return immediately. Non-gameplay jumps directly past the
    # story routine's redundant FFC1 gate. Death enters the cleanup below.
    # Preserve the last known-good demo/gameplay instruction order exactly.
    # Death can also enter with FFC1=0 (dungeon collision), so that uncommon
    # branch goes through a local dispatcher appended below.
    a.db(
        0xF0, 0xC1, 0xB7,                   # LDH A,[FFC1]; OR A
        0xCA, 0x00, 0x00,                   # JP Z,FFC1-zero dispatcher
    )
    ffc1_zero_operand = len(a.code) - 2
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x17)
    a.jr(0x28, "death")
    a.db(0xC9)                              # transition service cleared cache
    a.label("death")

    # This first wrapper service runs before scene_detect updates DF0D. Reset
    # the phase on the exact transition into death; later death frames cycle
    # 0..6 without spending a separate persistent marker byte.
    a.db(
        0xFA, SCENE_CACHE_ADDR & 0xFF, SCENE_CACHE_ADDR >> 8,
        0xFE, 0x17,
    )
    a.jr(0x28, "phase_ready")
    a.db(0xCD)
    death_oam_clear_operand = len(a.code)
    a.db(0x00, 0x00)
    a.db(
        0x3E, 0x01,
        0xEA, DEATH_ATTR_PHASE_ADDR & 0xFF,
        DEATH_ATTR_PHASE_ADDR >> 8,
    )

    a.label("phase_ready")
    a.db(
        0xFA, DEATH_ATTR_PHASE_ADDR & 0xFF,
        DEATH_ATTR_PHASE_ADDR >> 8,
        0x47,                               # B = phase across VBK setup
        0xF0, 0x4F,
        0xF5,                               # preserve VBK
        0x3E, 0x01,
        0xE0, 0x4F,                         # VBK = attributes
    )
    # Clear both physical maps with the same 24-column death viewport. The
    # stock cinematic can flip which map is BG/window at enable time, so roles
    # selected from an earlier LCDC value are not reliable. Seven calls cover
    # row 31 plus rows 0..19, including every exact release-state viewport.
    a.db(
        0x78, 0x87, 0x80, 0x3D, 0xE6, 0x1F,  # phase*3 - 1
        0x6F, 0x26, 0x00,
        0x29, 0x29, 0x29, 0x29, 0x29,      # HL = row*32
        0x1E, 0x9C,                         # E = stock BG map high
        0x7C, 0x83, 0x67,                   # H += map base
        0x0E, 0x18,                         # C = 24 columns
        0x16, 0x03,                         # D = 3 rows
    )
    a.jr(0x18, "clear_rows_call")

    a.label("after_active")
    # Future GAME OVER window map uses the same phase. Clearing it before LCDC
    # bit 5 turns on prevents a one-frame arena-colored flash.
    a.db(
        0xFA, DEATH_ATTR_PHASE_ADDR & 0xFF,
        DEATH_ATTR_PHASE_ADDR >> 8,
        0x47, 0x87, 0x80, 0x3D, 0xE6, 0x1F,  # phase*3 - 1
        0x6F, 0x26, 0x00,
        0x29, 0x29, 0x29, 0x29, 0x29,
        0x1E, 0x98,                         # E = stock window map high
        0x7C, 0x83, 0x67,
        0x16, 0x03,                         # D = 3 rows
        0xCD,                               # CALL clear_rows
    )
    clear_rows_call_operand = len(a.code)
    a.db(0x00, 0x00)
    a.db(
        0xF1, 0xE0, 0x4F,                   # restore VBK
        0x21, DEATH_ATTR_PHASE_ADDR & 0xFF,
        DEATH_ATTR_PHASE_ADDR >> 8,
        0x34, 0x7E, 0xFE, 0x08,             # INC [HL]; wrap after phase 7
        0x38, 0x02,                        # JR C,restore
        0xAF, 0x77,                         # phase = 0
        0xAF, 0xC9,                         # death returns Z to wrapper
    )

    # A short forward trampoline lets the active-map path share the same
    # subroutine without needing an out-of-range JR to after_active.
    a.label("clear_rows_call")
    a.db(0xCD)
    active_call_operand = len(a.code)
    a.db(0x00, 0x00)
    a.jr(0x18, "after_active")

    a.label("clear_rows")
    a.label("row_loop")
    a.db(0x41, 0xAF)                        # B=C; A=0
    a.label("cell_loop")
    a.db(0x22, 0x05)                        # [HL+]=0; DEC B
    a.jr(0x20, "cell_loop")
    a.db(0x7D, 0xC6, 0x08, 0x6F)           # HL += 32-24
    a.jr(0x30, "no_carry")
    a.db(0x24)
    a.label("no_carry")
    # Keep row wrap inside the selected 0x400-byte tilemap.
    a.db(0x7C, 0xE6, 0x03, 0xB3, 0x67)
    a.db(0x15)
    a.jr(0x20, "row_loop")
    a.db(0xC9)

    a.label("death_oam_clear")
    a.db(
        0x21, 0x00, 0xFE,                   # HL = hardware OAM
        0x06, 0x28,                         # all 40 sprite Y positions
        0xAF,
    )
    a.label("death_oam_loop")
    a.db(0x22, 0x23, 0x23, 0x23, 0x05)
    a.jr(0x20, "death_oam_loop")
    a.db(0xC9)

    # Only the FFC1=0 path reaches this tail. Keep it out of the cycle-locked
    # demo/live return path while still routing dungeon death to containment.
    a.label("ffc1_zero")
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x17, 0xCA)
    ffc1_zero_death_operand = len(a.code)
    a.db(0x00, 0x00)
    a.db(
        0xC3,
        story_dispatch_addr & 0xFF,
        story_dispatch_addr >> 8,
    )

    clear_rows_addr = DEATH_ATTR_DISPATCH_ADDR + a.labels["clear_rows"]
    a.code[
        clear_rows_call_operand:clear_rows_call_operand + 2
    ] = bytes([clear_rows_addr & 0xFF, clear_rows_addr >> 8])
    a.code[
        active_call_operand:active_call_operand + 2
    ] = bytes([clear_rows_addr & 0xFF, clear_rows_addr >> 8])
    death_oam_clear_addr = (
        DEATH_ATTR_DISPATCH_ADDR + a.labels["death_oam_clear"]
    )
    a.code[
        death_oam_clear_operand:death_oam_clear_operand + 2
    ] = bytes([
        death_oam_clear_addr & 0xFF,
        death_oam_clear_addr >> 8,
    ])
    ffc1_zero_addr = (
        DEATH_ATTR_DISPATCH_ADDR + a.labels["ffc1_zero"]
    )
    a.code[
        ffc1_zero_operand:ffc1_zero_operand + 2
    ] = bytes([ffc1_zero_addr & 0xFF, ffc1_zero_addr >> 8])
    death_addr = DEATH_ATTR_DISPATCH_ADDR + a.labels["death"]
    a.code[
        ffc1_zero_death_operand:ffc1_zero_death_operand + 2
    ] = bytes([death_addr & 0xFF, death_addr >> 8])
    return a.finish()


def build_death_fade_helper() -> bytes:
    """Mirror the stock DMG death fade into visible CGB BG0.

    The CGB core does not apply BGP remapping to CRAM colors. Without this
    bounded update, stock BGP=$00 exposes the in-progress GAME OVER tilemap in
    dungeon colors instead of producing a white transition. The proven
    two-map neutralizer maps the viewport to BG0. One eight-byte palette is
    updated per frame, keyed by the same eight-phase cleanup cursor, so all
    stale attribute slots become neutral without overrunning the late VBlank
    hook. Once BGP reaches its fully blank $00 phase, the attribute sweep is
    already complete, so BG0 is made white on every frame to hide the stock
    construction map. The shared CRAM copier waits for two safe HBlanks; raw
    eight-byte loops here used to lose writes silently in LCD mode 3.
    """
    a = _Asm()
    a.db(
        0xF0, 0x47,                         # A = stock BGP
        0xB7,
    )
    a.jr(0x28, "white_all")
    a.db(
        0xF5,                               # preserve BGP across slot setup
        0xFA,
        DEATH_ATTR_PHASE_ADDR & 0xFF,
        DEATH_ATTR_PHASE_ADDR >> 8,
        0x07, 0x07, 0x07,                   # phase * 8
        0xF6, 0x80, 0xE0, 0x68,             # palette slot, auto-increment
        0xF1,
        0x21,
        DEATH_FADE_NORMAL_ADDR & 0xFF,
        DEATH_FADE_NORMAL_ADDR >> 8,
        0xFE, 0xE4,
    )
    a.jr(0x28, "copy")
    a.db(0x2E, DEATH_FADE_INTERMEDIATE_ADDR & 0xFF)
    a.label("copy")
    a.db(
        0x0E, 0x69,                         # C = BGPD for shared copier
        0xC3,
        PALETTE_COPY_CRAM8_ADDR & 0xFF,
        PALETTE_COPY_CRAM8_ADDR >> 8,
    )

    # BGP=$00 begins well after all visible attributes have become BG0.
    a.label("white_all")
    a.db(
        0x3E, 0x80, 0xE0, 0x68,             # BG0, auto-increment
        0x21,
        DEATH_FADE_WHITE_ADDR & 0xFF,
        DEATH_FADE_WHITE_ADDR >> 8,
    )
    a.jr(0x18, "copy")
    code = a.finish()
    assert (
        DEATH_FADE_HELPER_ADDR + len(code)
        <= TILE_COLORIZER_ADDR
    )
    return code


def build_title_delay() -> bytes:
    """Balance the early CRAM repair to the proven title cadence."""
    code = bytes([
        0x00, 0x00, 0x00,                   # 12T
        0xC9,
    ])
    # 28T total. Together with the post-copy CALL/RET sequence below this
    # exactly replaces the former 84T pre-copy delay while moving both CRAM
    # writes 116T earlier inside VBlank.
    assert len(code) == 4
    return code


def build_death_late_fix() -> bytes:
    """Contain Faze's two persistent death-art attributes at wrapper tail."""
    a = _Asm()
    a.db(0x47)                              # B = saved VBK
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x17)
    a.jr(0x20, "done")
    a.db(
        0xCD,
        DEATH_FADE_HELPER_ADDR & 0xFF,
        DEATH_FADE_HELPER_ADDR >> 8,
    )
    a.label("wait_vram")
    # Only mode 3 maps to zero after (STAT+1)&3.
    a.db(0xF0, 0x41, 0x3C, 0xE6, 0x03)
    a.jr(0x28, "wait_vram")
    a.db(
        0x3E, 0x01, 0xE0, 0x4F,
        0x21, 0xCC, 0x9D,
        0xAF, 0x22, 0x77,
    )
    a.label("done")
    a.db(0x78, 0xE0, 0x4F, 0xC9)
    return a.finish()


def build_story_half_row_helper(row_entry_addr: int) -> bytes:
    """Dispatch art quarters and expose a shared neutral lower-panel tail."""
    code = bytes([
        0xFE, 0x20,                         # one 8-row * 4-quarter art pass
        0xD2,                               # JP NC,separator helper
        STORY_SEPARATOR_HELPER_ADDR & 0xFF,
        STORY_SEPARATOR_HELPER_ADDR >> 8,
        0xC3,                               # JP quarter mapper
        STORY_QUARTER_HELPER_ADDR & 0xFF,
        STORY_QUARTER_HELPER_ADDR >> 8,
        # Entry + 8: shared tail used by the separator helper.
        0x0E, 0x80,                         # story-family key / BG0
        0x06, 0x08,                         # visible separator row 8
        0xC3, row_entry_addr & 0xFF, row_entry_addr >> 8,
    ])
    assert len(code) == 15
    return code


def build_story_quarter_helper(row_entry_addr: int) -> bytes:
    """Map the art counter to rows 0..7 and offsets 0/5/10/15."""
    code = bytes([
        0xE6, 0x18,                         # quarter bits from counter
        0x0F,                               # 0/4/8/12
        0x57,                               # D = 4 * quarter
        0x0F, 0x0F,                         # A = quarter
        0x82,                               # A = 5 * quarter
        0x57,                               # D = cell offset
        0x78, 0xE6, 0x07, 0x47,             # B = visible row
        0xC3, row_entry_addr & 0xFF, row_entry_addr >> 8,
    ])
    assert len(code) == 15
    return code


def build_story_separator_helper(row_entry_addr: int) -> bytes:
    """Clear neutral visible rows 8..17, then leave the pass dormant.

    The stock pre-final writer can leave a late palette-1 cell at the dialogue
    box edge after the two-map cleaner has finished. Clearing all ten lower
    viewport rows in bounded five-cell quarters removes that whole stale-attr
    class without spending a full-screen write in any VBlank.
    """
    code = bytes([
        0xFE, 0x48,                         # 32 art + 40 dialogue quarters
        0xD0,                               # RET NC
        0xD6, 0x20,                         # lower-panel counter 0..39
        0x47,                               # B = row/quarter counter
        0xE6, 0x03, 0x57,                   # D = quarter 0..3
        0x87, 0x87, 0x82, 0x57,             # D = 5 * quarter
        0xCB, 0x38, 0xCB, 0x38,             # B = row offset 0..9
        0x78, 0xC6, 0x08, 0x47,             # B = visible row 8..17
        0x0E, 0x80,                         # story-family key / BG0
        0xC3, row_entry_addr & 0xFF, row_entry_addr >> 8,
    ])
    assert len(code) == 26
    return code


def build_story_viewport_key_helper() -> bytes:
    """Return a story key that restarts after the aligned 0→8 viewport move."""
    code = bytes([
        0xF0, 0x42,                         # A = SCY
        0x47,                               # B = SCY
        0xF0, 0x43,                         # A = SCX
        0xB0,                               # combine their tile-offset bit
        0xE6, 0x08,
        0x07,                               # bit 3 -> cache-key bit 4
        0xB1,                               # include C = art palette
        0xF6, 0x80,                         # story-family bit
        0xC9,
    ])
    assert len(code) == 13
    return code


def build_ending_absolute_row_helper(row_entry_addr: int) -> bytes:
    """Make three finite passes once for each physical ending BG map.

    The epilogue alternates LCDC's active map while scrolling. DF4B records
    which of its two maps have completed so returning to an already-colored
    map does not restart the expensive pass.
    """
    a = _Asm()
    a.db(0x79, 0xE6, 0xF7, 0xFE, 0x43)       # epilogue key ignoring map bit?
    a.jr(0x20, "limit")
    a.db(
        0xFA,
        STORY_ATTR_MAP_DONE_ADDR & 0xFF,
        STORY_ATTR_MAP_DONE_ADDR >> 8,
    )
    a.db(0xCB, 0x59)                          # BIT 3,C (9C00 map)
    a.jr(0x28, "check_done")
    a.db(0x0F)                                # 9C00 done bit 1 -> bit 0
    a.label("check_done")
    a.db(0xE6, 0x01, 0xC0)                   # RET NZ if selected map is done

    a.label("limit")
    a.db(0x78, 0xFE, 0x60)                   # three 32-row passes
    a.jr(0x38, "write_row")

    # Only epilogue keys need persistent per-map completion bits. Credits and
    # END simply become dormant at row $60.
    a.db(0x79, 0xE6, 0xF7, 0xFE, 0x43, 0xC0)
    a.db(
        0xFA,
        STORY_ATTR_MAP_DONE_ADDR & 0xFF,
        STORY_ATTR_MAP_DONE_ADDR >> 8,
    )
    a.db(0xCB, 0x59)                          # BIT 3,C
    a.jr(0x28, "mark_map_9800")
    a.db(0xCB, 0xCF)                          # SET 1,A
    a.jr(0x18, "store_done")
    a.label("mark_map_9800")
    a.db(0xCB, 0xC7)                          # SET 0,A
    a.label("store_done")
    a.db(
        0xEA,
        STORY_ATTR_MAP_DONE_ADDR & 0xFF,
        STORY_ATTR_MAP_DONE_ADDR >> 8,
        0xC9,
    )

    a.label("write_row")
    a.db(0xF0, 0x42, 0x0F, 0x0F, 0x0F)       # A = SCY >> 3
    a.db(0xE6, 0x1F, 0x57)                   # D = SCY tile row
    a.db(0x78, 0x92, 0xE6, 0x1F, 0x47)       # B = (counter-D) & 31
    a.db(0x16, 0x00)                          # ending starts at left half
    a.db(0xC3, row_entry_addr & 0xFF, row_entry_addr >> 8)
    code = a.finish()
    assert len(code) <= OBJ_PAL_TABLE_ADDR - ENDING_ABSOLUTE_ROW_HELPER_ADDR
    return code


def build_story_column_helper(resume_addr: int) -> bytes:
    """Set L to the aligned viewport column, then resume the row writer.

    All guarded story/ending phases use a tile-aligned SCX (0 or 8 in the
    production inventories), so three rotates produce the exact map column.
    This ten-byte tail occupies the final gap before the OBJ palette LUT.
    """
    code = bytes([
        0xF0, 0x43,                         # LDH A,[SCX]
        0x0F, 0x0F, 0x0F,                   # RRCA x3: aligned SCX / 8
        0xB5,                               # OR L (row base is 32-aligned)
        0x82,                               # ADD D (story half 0/16)
        0x6F,                               # LD L,A
        0xC3, resume_addr & 0xFF, resume_addr >> 8,
    ])
    assert len(code) == 11
    return code


def build_story_inactive_helper() -> bytes:
    """Clear the story page key and epilogue two-map completion cache."""
    code = bytes([
        0xAF,
        0xEA, STORY_ATTR_KEY_ADDR & 0xFF, STORY_ATTR_KEY_ADDR >> 8,
        0xEA,
        STORY_ATTR_MAP_DONE_ADDR & 0xFF,
        STORY_ATTR_MAP_DONE_ADDR >> 8,
        0xC9,
    ])
    assert len(code) == 8
    return code


def build_next_dma_shadow_colorizer() -> bytes:
    """Color all slots in the one shadow buffer that FF80 will DMA next.

    The historical helper processed ten entries in *both* C000 and C100.
    Besides missing later monster quadrants, that let the game's main loop
    rebuild the future DMA buffer with palette 0 after it had been colored.
    This helper retains the existing gameplay tile-range and boss semantics,
    but selects the exact buffer from FFCB immediately before the caller's
    FF80 DMA. One 40-slot pass is both complete and ordering-safe.
    """
    code = bytearray()
    code.extend([0xF5, 0xC5, 0xD5, 0xE5])  # preserve AF,BC,DE,HL

    # D = Sara palette: Witch 2 when FFBE=0, Dragon 1 otherwise.
    code.extend([
        0xF0, 0xBE, 0xB7,
        0x20, 0x04,
        0x16, 0x02,
        0x18, 0x02,
        0x16, 0x01,
    ])

    # E = active boss OBJ slot, or zero for ordinary range dispatch.
    code.extend([0xF0, 0xBF, 0xB7])
    no_boss = len(code) + 1
    code.extend([0x28, 0x00])
    code.extend([
        0x3D, 0x4F, 0x06, 0x00,
        0x21, BOSS_SLOT_TABLE_ADDR & 0xFF, BOSS_SLOT_TABLE_ADDR >> 8,
        0x09, 0x5E,
    ])
    boss_done = len(code) + 1
    code.extend([0x18, 0x00])
    no_boss_target = len(code)
    code[no_boss] = (no_boss_target - no_boss - 1) & 0xFF
    code.extend([0x1E, 0x00])
    boss_done_target = len(code)
    code[boss_done] = (boss_done_target - boss_done - 1) & 0xFF

    # FFCB records the last DMA buffer. FF80 increments it before choosing
    # C000/C100, so compute that same next buffer now.
    code.extend([
        0xF0, 0xCB,
        0x3C,
        0xE6, 0x01,
        0xC6, 0xC0,
        0x67,
        0x2E, 0x03,
        0xCD, TILE_COLORIZER_ADDR & 0xFF, TILE_COLORIZER_ADDR >> 8,
        0xE1, 0xD1, 0xC1, 0xF1,
        0xC9,
    ])
    assert len(code) <= TILE_COLORIZER_ADDR - SHADOW_MAIN_ADDR
    return bytes(code)


def build_attract_obj_colorizer(
    stage1_semantic_vblank: bool = False,
) -> bytes:
    """Dispatch BG/OAM work and color the real title spotlight actors.

    The title spotlight is D880=$1B, not the later D880=$0A gameplay demo.
    Its four 8x8 quadrants live in shadow-OAM slots 0..3, and FFF2 selects one
    of all 38 stock roster identities. The helper returns the palette compiled
    from spotlight_palette_map.yaml and monster_palette_map.yaml in C.

    Cold title frames have FFC1=0, while returned title frames retain FFC1=1.
    Both title paths bypass the expensive gameplay BG sweep. The stock title
    engine owns its OAM build and DMA cadence. Its private bank-1 emitter stays
    byte-for-byte native; this dispatcher lazy-loads the actor's OBJ CRAM slot
    and merges the identity palette into both shadows between native builds.
    Non-title gameplay keeps the normal BG sweep and semantic OBJ emitters.
    """
    a = _Asm()
    # Recognize the full title family independently of FFC1:
    #   $00/$01 = title/menu, $1B = spotlight, $1C = sliding banner.
    # Preserve the receipt-proven SUB-$1B classifier byte-for-byte. Its
    # unsigned underflow deliberately routes the later D880=$0A demo through
    # the same replacement FF80 publish as active gameplay. Replacing this
    # with a range check was logically cleaner but shifted the cycle-sensitive
    # attract path enough to overrun Gargoyle and return through D880=$02.
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.jr(0x38, "title_no_oam")
    a.db(0xD6, 0x1B, 0xFE, 0x02)
    a.jr(0x30, "gameplay")
    a.db(0xB7)
    a.jr(0x28, "spotlight")
    a.label("title_no_oam")
    # Keep helper initialization on title-only paths. Moving this readiness
    # check after title classification preserves the exact total title cycles
    # while steady gameplay avoids shifting the later joypad sample.
    a.db(
        0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xFE, 0xA7,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
    )
    a.db(0xC9)

    a.label("spotlight")
    a.db(
        0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xFE, 0xA7,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
    )
    # FFF2 briefly retains a non-actor value while D880 first enters $1B.
    # Do not index the packed map until the stock reel publishes one of its
    # 38 stable identities.
    a.db(
        0xF0, 0xF2, 0xFE, SPOTLIGHT_ROSTER_SIZE, 0xD0
    )                                       # RET NC unless FFF2 is 0..37
    a.db(0xF5, 0xC5, 0xD5, 0xE5)            # preserve AF,BC,DE,HL
    a.db(
        0xCD,
        SPOTLIGHT_PALETTE_HELPER_ADDR & 0xFF,
        SPOTLIGHT_PALETTE_HELPER_ADDR >> 8,
    )                                       # lazy-load this actor's OBJ CRAM
    a.db(0x21, 0x03, 0xC0)                  # HL = C000 slot-0 attr
    a.db(
        0x11, 0x04, 0x00,                   # DE = OAM entry stride
        0x06, 0x04,                         # four spotlight quadrants
    )
    a.label("spotlight_loop")
    a.db(
        0x7E, 0xE6, 0xF8, 0xB1, 0x77,       # C000: preserve flags; palette
        0x24, 0x77, 0x25,                   # mirror attr into C100
        0x19, 0x05,
    )
    a.jr(0x20, "spotlight_loop")
    a.db(0xE1, 0xD1, 0xC1, 0xF1)
    # The base colorizer retires the original bank-0 $06D5 FF80 call. Publish
    # the now-colored native shadow exactly once from this replacement path.
    a.db(0xC3, 0x80, 0xFF)

    a.label("gameplay")
    # The active flag is part of the proven transition contract: it prevents
    # a stale publish after the stock demo has started returning to title.
    a.db(0xF0, 0xC1, 0xB7, 0xC8)
    if stage1_semantic_vblank:
        a.db(
            0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
            0xB7,
        )
        a.jr(0x28, "gameplay_publish")
        # CALL $0061 switches to bank 14 and returns at the following address.
        # The builder overlays these eight padding bytes in bank 14 with a
        # call to the semantic row service and a bank-13 restore. Execution
        # then resumes at the shared FF80 publish tail in this bank.
        a.db(0x3E, 0x0E, 0xCD, 0x61, 0x00)
        a.db(*bytes(8))
    else:
        a.db(
            0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
            0xB7,
            0xC4, ROOM_BG_REPAIR_ADDR & 0xFF, ROOM_BG_REPAIR_ADDR >> 8,
        )
    # Sprite attributes are now assigned by the three stock emitters. No
    # all-40-slot scan remains in this VBlank path.
    a.label("gameplay_publish")
    a.db(0xC3, 0x80, 0xFF)                  # tail-call stock OAM DMA
    code = a.finish()
    assert ATTRACT_OBJ_COLORIZER_ADDR + len(code) <= SPOTLIGHT_PALETTE_MAP_ADDR
    return code


def build_room_bg_repair(
    stage1_atomic_attrs: bool = True,
    stage1_semantic_vblank: bool = False,
) -> bytes:
    """Run one pending BG row.

    The stock tilemap copier is restored to its single-wait, tile-only path.
    Native FFBD writers rearm the counter exactly when the room changes, so
    the VBlank path stays dormant during steady gameplay. Stage 1 packed-map
    commits use the inline copier's atomic tile+attribute path instead.
    The room-change slow path also recovers the hot OAM helpers after loading
    a legacy gameplay save state.  Cold-boot gameplay already has the A7
    sentinel. Both callees preserve BC/DE/HL.
    """
    if not stage1_atomic_attrs:
        if stage1_semantic_vblank:
            # A three-byte source-pointer key captures every transition in the
            # live north-route trace while keeping the no-work VBlank path in
            # the already-mapped bank. Bank 14 is entered only for ten bounded
            # semantic rows after a real packed-map transition.
            code = bytearray([
                0xFA, 0x80, 0xD8, 0xFE, 0x02, 0xC0,
                0xFA, 0x0E, 0xDC,
                0x21,
                STAGE1_ATTR_CACHE_9800_ADDR & 0xFF,
                STAGE1_ATTR_CACHE_9800_ADDR >> 8,
                0xBE,
                0x28, 0x06,
                0x77,
                0x3E, 0x0A,
                0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
                BG_SWEEP_COUNT_ADDR >> 8,
                0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
                BG_SWEEP_COUNT_ADDR >> 8,
                0xB7, 0xC8,
                0xCD,
                STAGE1_VBLANK_TRAMPOLINE_ADDR & 0xFF,
                STAGE1_VBLANK_TRAMPOLINE_ADDR >> 8,
                0xC9,
            ])
            capacity = CONDITIONAL_PALETTE_IMPL_ADDR - ROOM_BG_REPAIR_ADDR
            assert len(code) <= capacity
            return bytes(code) + bytes(capacity - len(code))

        # The production-safe native Stage-1 copier keeps terrain at stock
        # cadence. Spend the existing room-bounded DF4E budget on one
        # attribute row per VBlank, including legacy states whose saved DF4E
        # counter is already armed. Scene $0A retains its alternating pickup
        # row repair; all other scenes use the ordinary sequential sweep.
        code = bytearray([
            0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
            OAM_WRAM_SENTINEL_ADDR >> 8,
            0xFE, 0xA7,
            0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
        ])
        code.extend([0xFA, 0x80, 0xD8, 0xD6, 0x0A])
        code.extend([
            0xCA,
            ATTRACT_PICKUP_SWEEP_HELPER_ADDR & 0xFF,
            ATTRACT_PICKUP_SWEEP_HELPER_ADDR >> 8,
        ])
        code.extend([
            0xFA, BG_SWEEP_COUNT_ADDR & 0xFF,
            BG_SWEEP_COUNT_ADDR >> 8,
            0xB7, 0xC8,
            0x3D,
            0xEA, BG_SWEEP_COUNT_ADDR & 0xFF,
            BG_SWEEP_COUNT_ADDR >> 8,
            0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
        ])
        capacity = CONDITIONAL_PALETTE_IMPL_ADDR - ROOM_BG_REPAIR_ADDR
        assert len(code) <= capacity
        return bytes(code) + bytes(capacity - len(code))

    a = _Asm()
    a.db(
        0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xFE, 0xA7,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
    )
    # Stage 1 owns attrs in the atomic/direct publishers, so discard its stale
    # native rearm marker. D880=$0A is shared by prerecorded Gargoyle and
    # historical live Shield states; the adjacent dispatcher uses DCFD to
    # clear the former and run the two-map row helper for the latter. Scenes
    # above $0A retain the ordinary bounded repair path.
    a.db(0xFA, 0x80, 0xD8, 0xD6, 0x0A)
    a.jr(0x38, "clear")                    # JR C: scenes below $0A
    a.db(
        0xCA,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR & 0xFF,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR >> 8,
    )                                      # JP Z: shared $0A dispatcher
    a.label("pending")
    assert (
        ROOM_BG_REPAIR_ADDR + len(a.code)
        == ROOM_BG_REPAIR_STANDARD_ADDR
    )
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xB7, 0xC8,                        # no pending rows -> RET Z
        0x3D,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    )                                      # tail-call one row
    a.label("clear")
    assert ROOM_BG_REPAIR_ADDR + len(a.code) == ROOM_BG_REPAIR_CLEAR_ADDR
    a.db(
        0xAF,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xC9,
    )
    code = a.finish()
    assert len(code) <= CONDITIONAL_PALETTE_IMPL_ADDR - ROOM_BG_REPAIR_ADDR
    code += bytes(
        CONDITIONAL_PALETTE_IMPL_ADDR - ROOM_BG_REPAIR_ADDR - len(code)
    )
    return code


def build_attract_pickup_sweep_helper() -> bytes:
    """Spend the bounded live-$0A repair alternating Shield rows 6 and 7."""
    return bytes([
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xB7, 0xC8,                         # no pending rows -> RET Z
        0x3D,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xE6, 0x01, 0xC6, 0x04,             # DF04 input 4/5 -> row 6/7
        0xEA, 0x04, 0xDF,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    ])


def build_attract_pickup_sweep_dispatcher() -> bytes:
    """Route shared D880=$0A by live-play discriminator DCFD."""
    code = bytes([
        0xFA, 0xFD, 0xDC, 0xB7,
        0xCA, ROOM_BG_REPAIR_CLEAR_ADDR & 0xFF,
        ROOM_BG_REPAIR_CLEAR_ADDR >> 8,
        0xC3, ATTRACT_PICKUP_SWEEP_HELPER_ADDR & 0xFF,
        ATTRACT_PICKUP_SWEEP_HELPER_ADDR >> 8,
    ])
    assert len(code) == DEATH_LATE_FIX_ADDR - ATTRACT_PICKUP_SWEEP_STUB_ADDR
    return code


DEMO_PICKUP_METATILE_PALETTES = bytes([
    4, 4, 4, 4, 4, 5, 5, 5,
    1, 1, 1, 3, 3, 4, 4, 4,
    0, 0, 2, 5, 2, 2, 5, 2,
])

# The prerecorded input stream is cycle-sensitive at semantic-pickup publish
# boundaries. Nine NOPs (36 CPU cycles) after each completed dual-map pickup
# write reproduce the OG-parity route: 1,940 Stage-1 frames and 387 Gargoyle
# frames versus 1,856/395 in the unmodified ROM. Keep this named and guarded
# by the title-reel and pickup-live receipts rather than hiding the alignment
# in an unrelated helper.
DEMO_PICKUP_WRITER_PHASE_NOPS = 9


def build_demo_pickup_scanner() -> tuple[bytes, bytes, bytes]:
    """Stamp semantic pickups once at the native room-expander return.

    The stock packed room is a 10x11 visible metatile grid with a five-byte
    source stride. Pickup metatiles occupy the engine's $26-$3D family (and
    its $D7 alias). The scanner runs with the packed source stable, maps each
    real pickup to its YAML palette slot, stamps both physical BG maps during
    fresh HBlanks, then restores bank 1 and the original return path. The
    classifier is split into a second verified-zero bank-14 cave so no game
    data is displaced.
    """
    scan = _Asm()
    scan.db(0xC5, 0xD5, 0xE5)              # preserve BC/DE/HL
    scan.db(
        # Suppress the engine's repeated copies of an unchanged completed
        # source. The three-byte content key is already collision-free across
        # the committed Stage-1 transition corpus; INC keeps cold WRAM zero
        # outside its valid range.
        0xFA, 0x0E, 0xDC, 0x47,
        0xFA, 0x97, 0xC2, 0xA8, 0x47,
        0xFA, 0x9B, 0xC2, 0xA8, 0x3C,
        0x21, STAGE1_PICKUP_BUILD_KEY_ADDR & 0xFF,
        STAGE1_PICKUP_BUILD_KEY_ADDR >> 8,
        0xBE,
    )
    scan.jr(0x28, "done")
    scan.db(
        0x77,
        0xCD,
        STAGE1_ATOMIC_SETUP_ADDR & 0xFF,
        STAGE1_ATOMIC_SETUP_ADDR >> 8,
        0xFA, 0x0E, 0xDC, 0x5F,
        0xFA, 0x0F, 0xDC, 0x57,
        0x06, 0x0A,
    )
    scan.label("row")
    scan.db(0x0E, 0x0B)
    scan.label("cell")
    scan.db(0x1A, 0x13, 0xFE, 0xD7)
    scan.jr(0x38, "low_band")
    scan.db(0xD6, 0xB1)
    scan.label("low_band")
    scan.db(0xD6, 0x26, 0xFE, 0x18)
    scan.jr(0x30, "next_cell")
    scan.db(
        0xCD,
        DEMO_PICKUP_APPENDER_ADDR & 0xFF,
        DEMO_PICKUP_APPENDER_ADDR >> 8,
    )
    scan.label("next_cell")
    scan.db(0x0D)
    scan.jr(0x20, "cell")
    scan.db(0x7B, 0xC6, 0x05, 0x5F)
    scan.jr(0x30, "source_ready")
    scan.db(0x14)
    scan.label("source_ready")
    scan.db(0x05)
    scan.jr(0x20, "row")
    scan.db(
        0xCD,
        STAGE1_ATOMIC_WRAP_ADDR & 0xFF,
        STAGE1_ATOMIC_WRAP_ADDR >> 8,
    )
    scan.label("done")
    scan.db(0xE1, 0xD1, 0xC1, 0x3E, 0x01, 0xC3, 0x61, 0x00)
    scan_code = scan.finish()
    assert len(scan_code) <= 0x6EFB - DEMO_PICKUP_SCANNER_ADDR

    append = _Asm()
    append.db(
        0xC5, 0xD5,                        # save row/column + source
        0xC6, DEMO_PICKUP_TABLE_ADDR & 0xFF,
        0x6F, 0x26, DEMO_PICKUP_TABLE_ADDR >> 8,
        0x7E, 0xB7,
    )
    append.jr(0x28, "done")
    append.db(
        0x67,                               # H = palette
        0x3E, 0x0A, 0x90, 0xCB, 0x37, 0xE6, 0xF0, 0x6F,
        0x3E, 0x0B, 0x91, 0xB5, 0x5F,      # E = packed row/column
        0x44,                               # B = palette
        0x7B,
        0xCD,
        DEMO_PICKUP_DIRECT_WRITER_ADDR & 0xFF,
        DEMO_PICKUP_DIRECT_WRITER_ADDR >> 8,
    )
    append.label("done")
    append.db(0xD1, 0xC1, 0xC9)
    append_code = append.finish()
    assert len(append_code) <= 0x6F8B - DEMO_PICKUP_APPENDER_ADDR
    assert len(DEMO_PICKUP_METATILE_PALETTES) == 24
    return scan_code, append_code, DEMO_PICKUP_METATILE_PALETTES


def build_demo_pickup_writer() -> tuple[bytes, bytes]:
    """Write one 2x2 pickup to both maps in two fresh HBlanks.

    The writer runs only from the native room-expander completion hook, before
    the stock VBK0 tile copier can expose the new room. Four byte writes fit in
    one HBlank; using a second fresh HBlank for the peer map avoids both a
    visible one-frame neutral pickup and any unsafe mode-3 VRAM access.
    """
    front = _Asm()
    front.db(
        0x57, 0xE6, 0x0F, 0x87, 0x5F,
        0x7A, 0xCB, 0x37, 0xE6, 0x0F, 0x4F,
        0xE6, 0x03, 0x0F, 0x0F, 0xB3, 0x6F,
        0x79, 0xCB, 0x3F, 0xCB, 0x3F, 0xC6, 0x98, 0x67,
        0x3E, 0x01, 0xE0, 0x4F,
    )
    front.label("mode3")
    front.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    front.jr(0x20, "mode3")
    front.label("hblank")
    front.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    front.jr(0x28, "hblank")
    front.db(
        0x78, 0x22, 0x77, 0x2D,            # $9800 top pair
        0x7D, 0xC6, 0x20, 0x6F,
        0x78, 0x22, 0x77, 0x2D,            # $9800 bottom pair
        0x7D, 0xD6, 0x20, 0x6F,
        0xCB, 0xD4,                        # matching $9C00 top-left
        0xC3,
        DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR & 0xFF,
        DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR >> 8,
    )
    front_code = front.finish()

    tail = _Asm()
    tail.label("mode3")
    tail.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    tail.jr(0x20, "mode3")
    tail.label("hblank")
    tail.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    tail.jr(0x28, "hblank")
    tail.db(
        0x78, 0x22, 0x77, 0x2D,
        0x7D, 0xC6, 0x20, 0x6F,
        0x78, 0x22, 0x77, 0x2D,
        *bytes(DEMO_PICKUP_WRITER_PHASE_NOPS),
        0xAF, 0xE0, 0x4F,
        0xC9,
    )
    tail_code = tail.finish()
    assert len(front_code) <= 0x67F3 - DEMO_PICKUP_DIRECT_WRITER_ADDR
    assert len(tail_code) <= 0x6883 - DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR
    return front_code, tail_code


def build_room_bg_rearm_bank0(rows: int = BG_SWEEP_REARM_ROWS) -> bytes:
    """Preserve stock ``LDH [FFBD],A`` and arm an 18-row BG repair.

    Each native FFBD store is replaced by the two-byte ``RST $00; NOP``.
    RST $00 jumps here from its eight-byte vector. AF and flags are preserved,
    so every patched site retains the original store's register contract.
    """
    return bytes([
        0xE0, 0xBD,                         # stock LDH [FFBD],A
        0xF5,                               # PUSH AF
        0x3E, rows,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0x3E, ROOM_ATTR_PENDING_VALUE,
        0xEA,
        BG_SWEEP_ROOM_CACHE_ADDR & 0xFF,
        BG_SWEEP_ROOM_CACHE_ADDR >> 8,
        0xF1,                               # restore A and flags
        0xC9,
    ])


def install_room_bg_rearm_hooks(
    rom: bytearray,
    target_addr: int = ROOM_BG_REARM_BANK0_ADDR,
) -> None:
    """Rearm BG attributes at all four executable native FFBD writers."""
    vanilla = Path("rom/Penta Dragon (J).gb").read_bytes()
    # The fifth E0 BD byte pair at file $30CAF is compressed/data, not code.
    for offset in (0x0B7E, 0x11D2, 0x11FC, 0x4106):
        assert rom[offset:offset + 2] == vanilla[offset:offset + 2] == bytes(
            [0xE0, 0xBD]
        ), f"FFBD writer changed at file ${offset:05X}"
        rom[offset:offset + 2] = bytes([0xC7, 0x00])  # RST $00; NOP

    # RST $00 is unused by the stock game; retain a strict vector assertion so
    # a future base revision cannot silently collide with this hook.
    assert rom[0x0000:0x0003] == vanilla[0x0000:0x0003]
    rom[0x0000:0x0003] = bytes([
        0xC3,
        target_addr & 0xFF,
        target_addr >> 8,
    ])


def build_lava_attr_sample_signature(
    samples: tuple[int, ...],
    address: int,
    end: int,
) -> bytes:
    """Return the receipt-proven XOR of selected raw C1A0 cells in B."""
    a = _Asm()
    assert samples
    for index, offset in enumerate(samples):
        assert 0 <= offset < 576
        source = 0xC1A0 + offset
        a.db(0xFA, source & 0xFF, source >> 8)
        if index:
            a.db(0xA8)                      # XOR B
        a.db(0x47)                          # B = rolling XOR
    a.db(0xC9)
    code = a.finish()
    assert address + len(code) <= end
    return code


def build_lava_attr_room_match() -> bytes:
    """Return Z iff selected map metadata matches signature B and FFBD.

    DE points at an adjacent signature/valid/room triplet. DE and the compare
    flags are preserved across the return, allowing all marker and ordinary
    paths to share this compact predicate.
    """
    a = _Asm()
    a.db(0xD5, 0x1A, 0xB8)                  # save DE; cached sig CP B
    a.jr(0x20, "done")
    a.db(0x13, 0x1A, 0xFE, ROOM_ATTR_READY_VALUE)
    a.jr(0x20, "done")
    a.db(
        0x13, 0x1A, 0x4F,                  # C = cached room
        0xF0, 0xBD, 0xB9,                  # current room CP C
    )
    a.label("done")
    a.db(0xD1, 0xC9)
    code = a.finish()
    assert (
        LAVA_ATTR_ROOM_MATCH_ADDR + len(code)
        <= NATIVE_GLYPH_RESTORE_ADDR
    )
    return code


def build_lava_attr_decision_core(
    room_match_addr: int,
    *,
    bank1_restore_arg: bool,
) -> bytes:
    """Consume signature B with metadata DE and return the FFE0 decision."""
    a = _Asm()
    a.db(
        0xFA,
        BG_SWEEP_ROOM_CACHE_ADDR & 0xFF,
        BG_SWEEP_ROOM_CACHE_ADDR >> 8,
        0xFE, ROOM_ATTR_PENDING_VALUE,
    )
    # A6 is published before the native tile buffer is ready. Copying attrs
    # here commits the preceding map and merely duplicates the later A7/map
    # transition. Wait until the corresponding tile-copy call can compare the
    # actual desired signature.
    a.jr(0x28, "done")
    a.db(0xFE, ROOM_ATTR_READY_VALUE)
    a.jr(0x20, "compare")
    # Consume A7, then use the same exact signature/room predicate as an
    # ordinary tile-copy call.
    a.db(
        0xAF,
        0xEA,
        BG_SWEEP_ROOM_CACHE_ADDR & 0xFF,
        BG_SWEEP_ROOM_CACHE_ADDR >> 8,
    )
    a.label("compare")
    a.db(0xCD, room_match_addr & 0xFF, room_match_addr >> 8)
    a.jr(0x28, "done")

    # Every metadata miss requests the proven full atomic attribute prefix.
    # Store the exact signature and room so the matching destination map may
    # use the stock-speed tile-only path until its next observed transition.
    a.db(
        0x78, 0x12, 0x13,                  # signature = B; DE -> valid
        0x3E, ROOM_ATTR_READY_VALUE, 0x12,
        0x13, 0xF0, 0xBD, 0x12,            # room = current FFBD
        0x3E, 0x01, 0xE0, LAVA_ATTR_DECISION_HRAM,
    )
    a.label("done")
    a.db(0xE1, 0xD1, 0xC1)
    if bank1_restore_arg:
        a.db(0x3E, 0x01)                   # bank-1 trampoline tail argument
    a.db(0xC9)
    return a.finish()


def build_lava_attr_decider() -> tuple[bytes, bytes]:
    """Build the relocated bank-13 Stage 5 front and its shared core."""
    front_asm = _Asm()
    front_asm.db(
        0xC5, 0xD5, 0xE5,                  # preserve caller BC/DE/HL
        0xAF, 0xE0, LAVA_ATTR_DECISION_HRAM,
        0x11,
        LAVA_ATTR_STAGE5_9800_META_ADDR & 0xFF,
        LAVA_ATTR_STAGE5_9800_META_ADDR >> 8,
        0x7C, 0xFE, 0x9C,                  # select destination-map metadata
    )
    front_asm.jr(0x20, "metadata_selected")
    front_asm.db(0x1E, LAVA_ATTR_STAGE5_9C00_META_ADDR & 0xFF)
    front_asm.label("metadata_selected")
    front_asm.db(
        0xCD,
        LAVA_ATTR_STAGE5_SIGNATURE_ADDR & 0xFF,
        LAVA_ATTR_STAGE5_SIGNATURE_ADDR >> 8,
        0xC3,
        LAVA_ATTR_DECIDER_CONT_ADDR & 0xFF,
        LAVA_ATTR_DECIDER_CONT_ADDR >> 8,
    )
    front = front_asm.finish()
    assert len(front) == 22
    assert LAVA_ATTR_STAGE5_FRONT_ADDR + len(front) <= LAVA_ATTR_STAGE5_FRONT_END
    core = build_lava_attr_decision_core(
        LAVA_ATTR_ROOM_MATCH_ADDR,
        bank1_restore_arg=True,
    )
    assert LAVA_ATTR_DECIDER_CONT_ADDR + len(core) <= LAVA_ATTR_DECIDER_CONT_END
    return front, core


def build_stage1_hazard_dispatcher() -> bytes:
    """Dispatch the shared bank-0 trampoline by live gameplay scene.

    The ordinary Stage-1 tile copier reaches this only after completing its
    24x24 VBK0 map.  Stage 5 reaches it through the pre-existing WRAM decision
    path.  Both callers require A=1 on return so the bank-0 trampoline's final
    JP $0061 restores bank 1 and returns to the original caller.
    """
    a = _Asm()
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)     # D880 == Stage 1?
    a.jr(0x20, "stage5")
    # Switching banks with CALL $0061 from switchable ROM would return into
    # the same address in the newly mapped bank. Push the intended bank-14
    # entry explicitly and tail-jump through the fixed helper instead. The
    # publisher's RET then consumes this dispatcher's original bank-0 return.
    a.db(
        0x01,
        STAGE1_HAZARD_ROW_HELPER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_HELPER_ADDR >> 8,
        0xC5,
        0x3E, 0x0E,
        0xC3, 0x61, 0x00,
    )
    a.label("stage5")
    a.db(
        0xC3,
        LAVA_ATTR_STAGE5_FRONT_ADDR & 0xFF,
        LAVA_ATTR_STAGE5_FRONT_ADDR >> 8,
    )
    code = a.finish()
    capacity = LAVA_ATTR_STAGE7_SOURCE_A_ADDR - LAVA_ATTR_DECIDER_ADDR
    assert len(code) <= capacity
    return code + bytes(capacity - len(code))


def build_lava_attr_scene_dispatcher() -> bytes:
    """Return NZ only when Stage 5/7 need an atomic attribute-map copy.

    The caller already handles Stage 1 locally. Stage 5 temporarily maps bank
    13 through the fixed trampoline; Stage 7 calls its neighbor in the same
    always-mapped WRAM page. Both deciders publish their result in FFE0.
    Neutral scenes return Z without touching the shared HRAM scratch byte;
    stock actors use otherwise-idle HRAM indirectly in some crowded states.
    """
    a = _Asm()
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x06)     # D880 == Stage 5?
    a.jr(0x28, "stage5")
    a.db(0xFE, 0x08)                       # D880 == Stage 7?
    a.jr(0x28, "stage7")
    a.db(0xAF, 0xC9)                        # Z, preserve neutral-scene HRAM
    a.label("stage5")
    a.db(
        0xCD,
        LAVA_ATTR_DECIDER_BANK0_ADDR & 0xFF,
        LAVA_ATTR_DECIDER_BANK0_ADDR >> 8,
    )
    a.jr(0x18, "decision")
    a.label("stage7")
    a.db(
        0xCD,
        LAVA_ATTR_STAGE7_RUNTIME_ADDR & 0xFF,
        LAVA_ATTR_STAGE7_RUNTIME_ADDR >> 8,
    )
    a.label("decision")
    a.db(0xF0, LAVA_ATTR_DECISION_HRAM, 0xB7, 0xC9)
    return a.finish()


def build_stage1_attr_runtime(always_stage1: bool = False) -> bytes:
    """Return NZ once per changed Stage-1 layout on each physical BG map.

    A room ID is too coarse: the native scroller republishes shifted packed
    layouts while FFBD remains unchanged. Caching only FFBD left attributes
    two columns behind otherwise-correct tile IDs. The source low byte plus
    two receipt-proven raw cells distinguish every desired layout transition
    in the horizontal/vertical corpus. Rotating spike phases remain handled
    by the selective bank-14 row service rather than broad palette scans.
    """
    a = _Asm()
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.jr(0x20, "other_scene")
    if always_stage1:
        # The buffered copier has stock-width tile timing and one off-screen
        # attribute GDMA, so every Stage-1 source copy can safely take it.
        a.db(0x3E, 0x01, 0xB7, 0xC9)       # A=1/NZ; RET
        a.label("other_scene")
        a.db(
            0xC3,
            LAVA_ATTR_SCENE_DISPATCH_ADDR & 0xFF,
            LAVA_ATTR_SCENE_DISPATCH_ADDR >> 8,
        )
        code = a.finish()
        assert len(code) == 14
        return code
    a.db(
        0x7C,                               # A = destination H ($98/$9C)
        0xEE, 0xCB,                         # low cache = H XOR $CB
        0x5F,                               # E = $53/$57; D preset $DF
        0xFA, 0x0E, 0xDC, 0x47,            # B = source low byte
    )
    for index, sample in enumerate(STAGE1_ATTR_TRANSITION_SAMPLES):
        source = 0xC1A0 + sample
        a.db(0xFA, source & 0xFF, source >> 8, 0xA8)
        if index + 1 < len(STAGE1_ATTR_TRANSITION_SAMPLES):
            a.db(0x47)                      # B = rolling XOR
    a.db(0x3C, 0x47)                        # nonzero current content key
    a.db(
        0x1A, 0xB8, 0xC8,                  # same layout -> RET Z
        0x78, 0x12, 0xC9,                  # publish key; retain NZ
    )
    a.label("other_scene")
    a.db(
        0xC3,
        LAVA_ATTR_SCENE_DISPATCH_ADDR & 0xFF,
        LAVA_ATTR_SCENE_DISPATCH_ADDR >> 8,
    )
    code = a.finish()
    assert len(code) == 35
    assert STAGE1_ATTR_RUNTIME_ADDR + len(code) <= LAVA_ATTR_STAGE7_9800_META_ADDR
    return code


def build_stage1_hazard_row_helper() -> tuple[bytes, bytes]:
    """Atomically publish only rows containing Stage-1 spike hazards.

    The hook runs at the native metatile expander's final RET, when C1A0 is a
    complete 24x24 layout and immediately before the stock tile-map copy. A
    four-cell phase signature suppresses unchanged builds. Changed layouts are
    scanned for the 60-7F rotating-cylinder family and legacy 2A-2E/3A-3D
    spikes; only those rows take the three-cell tile+attribute HBlank writer.
    The stock copier then writes the same tile IDs without changing attrs.

    The first blob owns phase detection, row selection, Timer service points,
    bank restoration, and the original CALL return. The second blob is the
    compact same-bank atomic row writer.
    """
    a = _Asm()
    a.db(0xE1)                              # discard synthetic RST return
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.jr(0x28, "stage1")
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)     # other scene: bank 1; RET

    a.label("stage1")
    # The prerecorded Stage-1 demo shares D880=$02 with live play but keeps
    # DCFD clear. Queue only its semantic pickup metatiles; live play retains
    # the independently receipt-covered rotating-hazard path below.
    a.db(0xFA, 0xFD, 0xDC, 0xB7)
    a.jr(0x20, "live_stage1")
    a.db(
        0xC3,
        DEMO_PICKUP_SCANNER_ADDR & 0xFF,
        DEMO_PICKUP_SCANNER_ADDR >> 8,
    )
    a.label("live_stage1")
    # The reviewed rotating-cylinder assembly is the Stage-1 room-$12
    # mechanism. Other rooms reuse 60-7F IDs for ordinary terrain, so a broad
    # family scan there both recolors unrelated cells and destroys cadence.
    a.db(0xF0, 0xBD, 0xFE, 0x12)
    a.jr(0x28, "cylinder_room")
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)
    a.label("cylinder_room")
    a.db(0xFA, 0x0E, 0xDC, 0x47)           # completed-layout signature
    for index, sample in enumerate(STAGE1_HAZARD_PHASE_SAMPLES):
        source = 0xC1A0 + sample
        a.db(0xFA, source & 0xFF, source >> 8, 0xA8)
        if index + 1 < len(STAGE1_HAZARD_PHASE_SAMPLES):
            a.db(0x47)
    # Each physical map must consume a phase independently: the stock engine
    # publishes the same completed phase to $9C00 and then $9800 on adjacent
    # copies. A shared cache made the second map lag by one phase.
    a.db(
        0x47,                               # B = completed signature
        0x21,
        STAGE1_HAZARD_CACHE_9C00_ADDR & 0xFF,
        STAGE1_HAZARD_CACHE_9C00_ADDR >> 8,
        0xFA, 0x0B, 0xDC, 0xB7,
    )
    a.jr(0x28, "phase_cache_ready")         # old 0 -> target $9C00
    a.db(0x2E, STAGE1_HAZARD_CACHE_9800_ADDR & 0xFF)
    a.label("phase_cache_ready")
    a.db(0x78, 0xBE)
    a.jr(0x20, "changed")
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)     # unchanged: bank 1; RET
    a.label("changed")
    a.db(
        0x77,
        0xFA, 0x0B, 0xDC,                  # pre-toggle destination map
        0x26, 0x9C, 0xB7,
    )
    a.jr(0x28, "map_ready")
    a.db(0x26, 0x98)
    a.label("map_ready")
    a.db(0x2E, 0x00, 0x11, 0xA0, 0xC1, 0x0E, 0x18)

    a.label("row")
    a.db(0xC5, 0xD5, 0x06, 0x18)           # save row count/source start
    a.label("scan")
    a.db(0x1A, 0x13, 0xFE, 0x60)
    a.jr(0x38, "legacy")
    a.db(0xFE, 0x80)
    a.jr(0x38, "hazard")                   # 60-7F rotating cylinder
    a.label("next_cell")
    a.db(0x05)
    a.jr(0x20, "scan")
    a.db(0xD1, 0x7B, 0xC6, 0x18, 0x5F)
    a.jr(0x30, "row_ready")
    a.db(0x14)
    a.jr(0x18, "row_ready")

    a.label("legacy")
    a.db(0xFE, 0x2A)
    a.jr(0x38, "next_cell")
    a.db(0xFE, 0x2F)
    a.jr(0x38, "hazard")                   # 2A-2E legacy spikes
    a.db(0xFE, 0x3A)
    a.jr(0x38, "next_cell")
    a.db(0xFE, 0x3E)
    a.jr(0x30, "next_cell")
    a.label("hazard")
    a.db(
        0xD1,
        # Mask interrupts only for the row that actually needs paired tile and
        # attribute writes. Ordinary rows retain the caller's normal cadence.
        0xCD,
        STAGE1_ATOMIC_SETUP_ADDR & 0xFF,
        STAGE1_ATOMIC_SETUP_ADDR >> 8,
        0xCD,
        STAGE1_HAZARD_ROW_COMPILER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_COMPILER_ADDR >> 8,
        0xCD,
        STAGE1_ATOMIC_WRAP_ADDR & 0xFF,
        STAGE1_ATOMIC_WRAP_ADDR >> 8,
        # The atomic writer advanced through 24 visible cells; add only the
        # eight-cell tilemap padding before the next packed source row.
        0x7D, 0xC6, 0x08, 0x6F,
    )
    a.jr(0x30, "destination_ready")
    a.db(0x24)
    a.jr(0x18, "destination_ready")

    a.label("row_ready")
    # A non-hazard scan did not touch VRAM HL, so advance the complete row.
    a.db(0x7D, 0xC6, 0x20, 0x6F)
    a.jr(0x30, "destination_ready")
    a.db(0x24)
    a.label("destination_ready")
    a.db(0xC1, 0x0D)
    a.jr(0x20, "row")
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)     # restore bank 1; original RET
    main = a.finish()

    row = _Asm()
    row.db(0x06, WRAM_BG_TABLE >> 8, 0x3E, 0x08, 0xE0, 0xE0)
    row.label("group")
    row.db(0x13, 0x13, 0x13)                # source group end
    for _ in range(3):
        row.db(0x1B, 0x1A, 0x4F, 0x0A, 0xF5)
    row.label("stat3")
    row.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    row.jr(0x20, "stat3")
    row.label("stat0")
    row.db(0xF0, 0x41, 0xE6, 0x03)
    row.jr(0x20, "stat0")
    for _ in range(3):
        row.db(0x1A, 0x13, 0x22)            # VBK0 tile IDs
    row.db(0x3E, 0x01, 0xE0, 0x4F, 0x7D, 0xD6, 0x03, 0x6F)
    for _ in range(3):
        row.db(0xF1, 0x22)                  # VBK1 YAML attributes
    row.db(0xAF, 0xE0, 0x4F, 0xF0, 0xE0, 0x3D, 0xE0, 0xE0)
    row.jr(0x20, "group")
    row.db(0xC9)
    row_compiler = row.finish()
    assert (
        STAGE1_HAZARD_ROW_HELPER_ADDR + len(main)
        <= STAGE1_HAZARD_ROW_HELPER_END
    )
    assert (
        STAGE1_HAZARD_ROW_COMPILER_ADDR + len(row_compiler)
        <= STAGE1_HAZARD_ROW_COMPILER_END
    )
    return main, row_compiler


def build_stage1_atomic_setup() -> bytes:
    """Admit only Timer/audio while the packed map source is live."""
    code = bytes([
        0xF3,                               # DI before changing IE
        0xF0, 0xFF,                         # A = caller's IE
        0xEA, STAGE1_IE_CACHE_ADDR & 0xFF,
        STAGE1_IE_CACHE_ADDR >> 8,
        0xE6, 0x04,                         # retain Timer only
        0xE0, 0xFF,                         # publish bounded in-copy IE
        0xC9,
    ])
    assert len(code) == 11
    return code


def build_stage1_atomic_wrap() -> bytes:
    """Restore the stock interrupt-enabled return contract."""
    code = bytes([
        0xF3,
        0xFA, STAGE1_IE_CACHE_ADDR & 0xFF,
        STAGE1_IE_CACHE_ADDR >> 8,
        0xE0, 0xFF,                         # restore caller's IE
        0xFB, 0xC9,                         # EI; RET
    ])
    assert len(code) == 8
    return code


def build_stage1_gdma_register_helper() -> bytes:
    """Commit a $300-byte WRAM plane from A:$D000 to H:$00 in VRAM."""
    code = bytes([
        0xE0, 0x51,                         # source high = A
        0xAF, 0xE0, 0x52,                  # source low = 0
        0x7C, 0xE0, 0x53,                  # destination high = H
        0x3E, 0x2F, 0xE0, 0x55,            # 48 * 16 = $300 bytes
        0xC9,
    ])
    assert len(code) == 13
    return code


def build_stage1_demo_delay(wait_line: int = STAGE1_DEMO_WAIT_LINE) -> bytes:
    """Phase-align only title-demo Stage-1 cache misses to a proven scanline."""
    assert 0 <= wait_line <= 153
    code = bytes([
        0xF0, 0x44,                         # LDH A,[LY]
        0xFE, wait_line,
        0x20, 0xFA,                         # JR NZ,-6
        0xC9,
    ])
    assert len(code) == 7
    return code


def build_demo_compact_dispatcher() -> bytes:
    """Use the compact pure copier only for prerecorded attract gameplay.

    Entry $3482 supplies the normal $9800 map base; entry $3484 preserves a
    caller-supplied $9800/$9C00 base. Real play has DCFD=$01 and title drawing
    has FFC1=$00, so both tail directly to the byte-exact native copier. Only
    DCFD=$00 + FFC1=$01 maps bank 13 for the position-independent compact
    copier, then restores bank 1 before returning to the original caller.
    """
    common = INLINE_ATTR_DECISION_HELPER_ADDR + 2
    code = bytes([
        0x26, 0x98,                         # $3482: H = $98
        0xFA, 0xFD, 0xDC, 0xB7,             # $3484: DCFD == attract?
        0xC2, 0xA7, 0x42,                   # real play -> native copier
        0xF0, 0xC1, 0xB7,                   # title drawing stays native
        0xCA, 0xA7, 0x42,
        0x3E, 0x0D, 0xCD, 0x61, 0x00,       # map bank 13
        0xCD, DEMO_COMPACT_COPY_ADDR & 0xFF,
        DEMO_COMPACT_COPY_ADDR >> 8,
        0x3E, 0x01,                         # restore bank 1
        0xC3, 0x61, 0x00,                   # helper RET returns to caller
    ])
    assert common == INLINE_ATTR_DECISION_HELPER_ADDR + 2
    assert len(code) <= 0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR
    return code


def build_lava_attr_stage7_runtime(always_stage1: bool = False) -> bytes:
    """Build the always-mapped WRAM Stage 7 decider.

    Stage 7's two lava IDs are classified directly: `(tile-$19) < 2`. The
    two-cell raw XOR discriminator, decision core, and room predicate all
    fit in the verified vanilla-unused DA60-DAFF tail.
    """
    prefix = _Asm()
    prefix.db(
        0xC5, 0xD5, 0xE5,
        0xAF, 0xE0, LAVA_ATTR_DECISION_HRAM,
        0x11,
        LAVA_ATTR_STAGE7_9800_META_ADDR & 0xFF,
        LAVA_ATTR_STAGE7_9800_META_ADDR >> 8,
        0x7C, 0xFE, 0x9C,                  # select destination-map metadata
    )
    prefix.jr(0x20, "metadata_selected")
    prefix.db(0x1E, LAVA_ATTR_STAGE7_9C00_META_ADDR & 0xFF)
    prefix.label("metadata_selected")
    for index, offset in enumerate(LAVA_ATTR_STAGE7_SAMPLES):
        source = 0xC1A0 + offset
        prefix.db(0xFA, source & 0xFF, source >> 8)
        if index:
            prefix.db(0xA8)                 # XOR B
        prefix.db(0x47)                     # B = rolling XOR
    prefix_code = prefix.finish()
    probe_core = build_lava_attr_decision_core(
        0x0000,
        bank1_restore_arg=False,
    )
    runtime_match_addr = (
        LAVA_ATTR_STAGE7_RUNTIME_ADDR + len(prefix_code) + len(probe_core)
    )
    core = build_lava_attr_decision_core(
        runtime_match_addr,
        bank1_restore_arg=False,
    )
    assert len(core) == len(probe_core)
    code = prefix_code + core + build_lava_attr_room_match()
    assert (
        LAVA_ATTR_STAGE7_RUNTIME_ADDR + len(code)
        <= LAVA_ATTR_SCENE_DISPATCH_ADDR
    )
    padding_before_dispatch = bytes(
        LAVA_ATTR_SCENE_DISPATCH_ADDR
        - (LAVA_ATTR_STAGE7_RUNTIME_ADDR + len(code))
    )
    dispatcher = build_lava_attr_scene_dispatcher()
    assert (
        LAVA_ATTR_SCENE_DISPATCH_ADDR + len(dispatcher)
        == STAGE1_ATTR_RUNTIME_ADDR
    )
    stage1_runtime = build_stage1_attr_runtime(always_stage1=always_stage1)
    padding_before_metadata = bytes(
        LAVA_ATTR_STAGE7_9800_META_ADDR
        - (STAGE1_ATTR_RUNTIME_ADDR + len(stage1_runtime))
    )
    blob = (
        code
        + padding_before_dispatch
        + dispatcher
        + stage1_runtime
        + padding_before_metadata
        + bytes(6)
    )
    assert LAVA_ATTR_STAGE7_RUNTIME_ADDR + len(blob) == OAM_WRAM_BASE + 0x100
    return blob


def build_lava_attr_decider_bank0() -> bytes:
    """Map bank 13, call the exact decider, and tail-restore bank 1.

    Stock helper 0x0061 updates both FF99 and the MBC register.  The decider
    returns A=1 while its full-vs-tile-only result remains in FFE0, allowing
    the final JP to use 0x0061's RET as this trampoline's own return.
    """
    code = bytes([
        0x3E, 0x0D,
        0xCD, 0x61, 0x00,
        0xCD, LAVA_ATTR_DECIDER_ADDR & 0xFF,
        LAVA_ATTR_DECIDER_ADDR >> 8,
        0xC3, 0x61, 0x00,
    ])
    assert len(code) == 11
    return code


def build_inline_attr_decision_helper(atomic_row_addr: int) -> bytes:
    """Title-timed prefix plus gameplay attribute decision helper.

    Gameplay calls this readiness trampoline and enters the expanded WRAM
    helper. The title path uses the RET byte at the end of the adjacent GDMA
    helper as an exact fixed-delay target and bypasses this decision entirely.
    Old combat states can resume before the room-change slow path initializes
    WRAM, so legacy states return Z without entering an uncopied routine.

    The caller presets D=$DF. The readiness path preserves B because neutral
    scenes take the pure copier without reinitializing it; the WRAM helper
    reloads D880 itself. C and E remain scratch on Stage 1 cache decisions.
    """
    a = _Asm()
    # The title entry calls three bytes before the gameplay decision. This
    # exact 28T delay preserves A=0/Z and the established title copier phase.
    a.db(0x18, 0x00, 0xC9)
    a.db(
        0xFA,
        OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xB7, 0xC8,                         # zero legacy state: return Z
        0xFA, 0xFD, 0xDC, 0xB7, 0xC8,       # attract: stock-width pure copy
        0xCD,
        STAGE1_ATTR_RUNTIME_ADDR & 0xFF,
        STAGE1_ATTR_RUNTIME_ADDR >> 8,
        0x00, 0xC9,                         # live: restore atomic return phase
    )
    # The prerecorded attract stream was authored against the stock four-tile
    # cadence. Its early return avoids both the live three-tile 8/6 cadence
    # penalty and a room-signature calculation whose answer it cannot use.
    a.db(0x00, 0x00, 0x00, 0x00)           # fixed-address padding
    del atomic_row_addr                     # stock-order path needs no wrap
    code = a.finish()
    assert len(code) == 22
    return code


def build_oam_palette_resolver() -> bytes:
    """Return the production gameplay OBJ palette for tile A.

    The YAML-compiled 256-byte LUT is initialized once at D900. A page-aligned
    WRAM lookup is both faster and more faithful than duplicating the old CP
    cascade at each emitter. The $FF Sara marker remains dynamic via FFBE.
    HL is preserved for the free-slot and bank-1 emitters.
    """
    a = _Asm()
    a.db(
        0xE5,                               # preserve caller's HL
        0x6F,                               # L = tile
        0x26, OAM_PALETTE_LUT_WRAM >> 8,
        0x7E,                               # A = YAML LUT[tile]
        0xFE, 0xFF,
    )
    a.jr(0x20, "done")
    a.db(0xF0, 0xBE, 0xB7, 0x3E, 0x02)
    a.jr(0x28, "done")                      # Sara W
    a.db(0x3D)                              # Sara D -> OBJ1
    a.label("done")
    a.db(0xE1, 0xC9)
    return a.finish()


def build_oam_lut_init() -> bytes:
    """Expand the YAML OBJ LUT directly into its page-aligned WRAM page."""
    lut = build_obj_pal_table()
    assert len(lut) == 0x100
    runs = []
    start = 0
    for index in range(1, len(lut) + 1):
        if index == len(lut) or lut[index] != lut[start]:
            runs.append((index - start, lut[start]))
            start = index

    a = _Asm()
    a.db(
        0x21,
        OAM_PALETTE_LUT_WRAM & 0xFF,
        OAM_PALETTE_LUT_WRAM >> 8,
    )
    for run_index, (length, value) in enumerate(runs):
        assert 0 < length <= 0xFF
        a.db(0x06, length, 0x3E, value)      # B = run length; A = value
        label = f"run_{run_index}"
        a.label(label)
        a.db(0x22, 0x05)                    # [HL+] = A; DEC B
        a.jr(0x20, label)
    a.db(0xC9)
    code = a.finish()
    assert OAM_LUT_INIT_ADDR + len(code) <= LAVA_OVERRIDE_ADDR
    return code


def build_oam_boss_lut_service() -> bytes:
    """Patch the miniboss animation pages $30-$7F when FFBF changes.

    The attract-mode Gargoyle walks through five 16-tile pages. Restricting
    the boss override to $30-$4F recreates the reported periodic palette flip
    when its animation selects $50-$7F. On boss exit, tail-call the canonical
    YAML LUT initializer so every ordinary monster range is restored exactly.
    The cache stores FFBF+1 so a cleared cache forces one safe refresh.
    """
    a = _Asm()
    a.db(
        0xF0, 0xBF, 0x47,                   # B = FFBF boss identity
        0x3C, 0x4F,                         # C = cache key FFBF+1
        0xFA,
        OAM_BOSS_LUT_CACHE_ADDR & 0xFF,
        OAM_BOSS_LUT_CACHE_ADDR >> 8,
        0xB9, 0xC8,                         # unchanged -> RET Z
        0x79,
        0xEA,
        OAM_BOSS_LUT_CACHE_ADDR & 0xFF,
        OAM_BOSS_LUT_CACHE_ADDR >> 8,
        0x78, 0xB7,
    )
    a.jr(0x28, "base_palette")
    a.db(
        0x3D,                               # zero-based boss index
        0xC6, BOSS_SLOT_TABLE_ADDR & 0xFF,
        0x6F,
        0x26, BOSS_SLOT_TABLE_ADDR >> 8,
        0x7E,                               # boss OBJ slot 6/7
        0x21, 0x30, OAM_PALETTE_LUT_WRAM >> 8,
        0x06, 0x50,                         # all pages $30-$7F
    )
    a.jr(0x18, "fill_loop")
    a.label("base_palette")
    # Restore every independently tuned YAML range on boss exit.
    a.db(
        0xC3,
        OAM_LUT_INIT_ADDR & 0xFF,
        OAM_LUT_INIT_ADDR >> 8,
    )
    a.label("fill_loop")
    a.db(0x22, 0x05)
    a.jr(0x20, "fill_loop")
    a.db(0xC9)
    code = a.finish()
    assert OAM_BOSS_LUT_SERVICE_ADDR + len(code) <= OAM_CENTRAL_EMITTER_ADDR
    return code


def _emit_semantic_attr_merge(a: _Asm, *, mirror_alternate: bool) -> None:
    """Emit attr merge for DE=entry+3, A=stock attr, tile at DE-1."""
    a.db(
        0xC5, 0xF5,                        # preserve BC and stock attr
        0x1B, 0x1A, 0x13,                  # fetch tile without moving DE
        0xCD,
        OAM_PALETTE_RESOLVER_RUNTIME_ADDR & 0xFF,
        OAM_PALETTE_RESOLVER_RUNTIME_ADDR >> 8,
        0x4F,                              # C = palette
        0xF1, 0xE6, 0xF8, 0xB1,           # merge into stock attr
        0x12,                              # store current-buffer attr
    )
    if mirror_alternate:
        # The game can DMA the alternate shadow before rebuilding that entry.
        # Resolve that buffer's own high tile with the same compact high-nibble
        # rule; never copy the current buffer's palette across different tiles.
        a.db(
            0x7A, 0xEE, 0x01, 0x57,        # toggle C0xx <-> C1xx
            0x1B, 0x1A, 0x13, 0xFE, 0x30,
        )
        a.jr(0x38, "alternate_done")
        a.db(0x47)                          # B = alternate tile
        a.db(0xF0, 0xBF, 0xB7)
        a.jr(0x28, "alternate_regular")
        a.db(
            0xE5, 0x3D, 0xC6,
            BOSS_SLOT_TABLE_ADDR & 0xFF,
            0x6F, 0x26, BOSS_SLOT_TABLE_ADDR >> 8,
            0x7E, 0xE1,
        )
        a.jr(0x18, "alternate_apply")
        a.label("alternate_regular")
        a.db(0x78, 0xCB, 0x37, 0xE6, 0x0F, 0xFE, 0x08)
        a.jr(0x38, "alternate_apply")
        a.db(0x3E, 0x04)
        a.label("alternate_apply")
        a.db(
            0x4F,
            0x1A, 0xE6, 0xF8, 0xB1, 0x12,
        )
        a.label("alternate_done")
        a.db(
            0x7A, 0xEE, 0x01, 0x57,        # restore original DE high
        )
    a.db(0xC1, 0x13)                       # restore BC; advance DE


def build_oam_central_emitter() -> bytes:
    """WRAM-hot replacement for stock sprite emitter $10D1.

    Palette selection is a page-aligned D900 lookup generated from the monster
    YAML. This removes the old CP cascade as well as a resolver CALL/RET pair.
    The stock $09CE/$09D6 helpers only preserve A around one write to $1FFF;
    A is dead at entry and replaced with C before return, so emit those exact
    flag-preserving writes inline on this 3,900+-calls-per-route hot path.
    """
    a = _Asm()
    a.db(0x3E, 0x0A, 0xEA, 0xFF, 0x1F)     # inline stock $09CE effect
    a.db(0x78, 0x12, 0x13)                  # Y
    a.db(0x79, 0x12, 0x13)                  # X
    a.db(0xC5)                              # preserve stock Y/X in BC
    a.db(0x2A, 0x12, 0x13, 0x47)            # tile; B = tile
    a.db(
        0x4F,                               # C = tile
        0x06, OAM_PALETTE_LUT_WRAM >> 8,   # BC = D900 + tile
        0x0A,                               # A = YAML LUT[tile]
        0xFE, 0xFF,
    )
    a.jr(0x28, "sara_palette")
    a.db(0x4F)                              # C = resolved palette
    a.label("palette_ready")
    a.db(0x2A, 0xCD, 0xA2, 0x11, 0xCD, 0x88, 0x11)
    a.db(0xE6, 0xF8, 0xB1, 0x12, 0x13)     # merge/store attr
    a.db(0xC1)                              # restore stock Y/X
    a.db(0x79, 0xC6, 0x08, 0x4F)
    a.db(
        0x3E, 0x00, 0xEA, 0xFF, 0x1F,     # inline stock $09D6 effect
        0xFB,                               # EI after atomic tile+attr emission
        0x79,                               # stock contract: return A=C
        0xC9,
    )

    # The only dynamic LUT value is Sara's $FF marker.
    a.label("sara_palette")
    a.db(0xF0, 0xBE, 0xB7, 0x0E, 0x02)
    a.jr(0x28, "palette_ready")
    a.db(0x0D)
    a.jr(0x18, "palette_ready")
    return a.finish()


def build_oam_free_emitter() -> bytes:
    """Bank-13 body replacing the free-slot emitter at bank 0:$346F."""
    a = _Asm()
    a.db(0x21, 0x00, 0xC0, 0x1E, 0x27)
    a.label("scan")
    a.db(0x7E, 0xB7)
    a.jr(0x28, "found")
    a.db(0x23, 0x23, 0x23, 0x23, 0x1D)
    a.jr(0x20, "scan")
    a.db(0x7A, 0xC9)                        # full: preserve tile in A

    a.label("found")
    a.db(0xCD, 0xA3, 0x34)                  # stock coordinate conversion
    a.db(0x78, 0x22, 0x79, 0x22, 0x7A, 0x22)
    a.db(
        0xCD,
        OAM_PALETTE_RESOLVER_RUNTIME_ADDR & 0xFF,
        OAM_PALETTE_RESOLVER_RUNTIME_ADDR >> 8,
        0x77,                              # write attr at entry+3
        0xC5, 0xD5, 0xE5,
        0x2B, 0x2B, 0x2B,                  # source = C000 entry base
        0x16, 0xC1, 0x5D,                  # corresponding C100 entry
        0x01, 0x04, 0x00,                  # mirror all four bytes
        0xCD, 0xB3, 0x09,
        0xE1, 0xD1, 0xC1,
        0x7A, 0xC9,
    )
    return a.finish()


def build_oam_bank_wrapper(helper_addr: int, final_a_opcode: int) -> bytes:
    """Map bank 13 and keep the four-byte sprite emission DMA-atomic."""
    return bytes([
        0xF3,                              # DI: DMA cannot split tile/attr
        0xF0, 0x99, 0xF5,                  # save current FF99 bank
        0x3E, 0x0D, 0xCD, 0x61, 0x00,     # map bank 13 via stock helper
        0xCD, helper_addr & 0xFF, helper_addr >> 8,
        0xF1, 0xCD, 0x61, 0x00,            # restore caller's bank + FF99
        0xFB,                               # EI after the WRAM-bank restore
        final_a_opcode,                     # central/bank1 A=C; free A=D
        0xC9,                               # RET (EI takes effect after return)
    ])


def build_oam_wram_tail_wrapper(helper_addr: int, final_a_opcode: int) -> bytes:
    """Tail-jump to the WRAM emitter using the original caller's return.

    The WRAM body owns EI, the final LD A,C contract, and RET. Avoiding a
    nested CALL/RET pair is the key steady-gameplay saving.
    """
    assert final_a_opcode == 0x79
    return bytes([
        0xF3,                              # DI: DMA cannot split tile/attr
        0xC3, helper_addr & 0xFF, helper_addr >> 8,
    ])


def build_oam_wram_copy() -> bytes:
    """Copy compact hot helpers into the verified-unused DA00-DAFF page.

    Resolver and central-emitter code are packed instead of copying their ROM
    padding and transition-only boss service. The reclaimed tail then holds
    the Stage 7 palette-signature decider, avoiding two ROM-bank switches on
    every Stage 7 tilemap copy.
    """
    resolver = build_oam_palette_resolver()
    stage1_setup = build_stage1_atomic_setup()
    central = build_oam_central_emitter()
    stage7 = build_lava_attr_stage7_runtime()
    first_capacity = OAM_FREE_EMITTER_ADDR - LAVA_ATTR_STAGE7_SOURCE_A_ADDR
    first_length = min(first_capacity, len(stage7))
    second_length = len(stage7) - first_length
    assert (
        LAVA_ATTR_STAGE7_SOURCE_B_ADDR + second_length
        <= OAM_WRAM_COPY_ADDR
    )
    chunks = (
        (
            OAM_PALETTE_RESOLVER_ADDR,
            OAM_PALETTE_RESOLVER_RUNTIME_ADDR,
            len(resolver) + len(stage1_setup),
        ),
        (
            OAM_CENTRAL_EMITTER_ADDR,
            OAM_CENTRAL_EMITTER_RUNTIME_ADDR,
            len(central),
        ),
        (
            LAVA_ATTR_STAGE7_SOURCE_A_ADDR,
            LAVA_ATTR_STAGE7_RUNTIME_ADDR,
            first_length,
        ),
        (
            LAVA_ATTR_STAGE7_SOURCE_B_ADDR,
            LAVA_ATTR_STAGE7_RUNTIME_ADDR + first_length,
            second_length,
        ),
    )
    a = _Asm()
    a.db(0xC5, 0xD5, 0xE5)
    for source, destination, length in chunks:
        assert 0 < length <= 0xFF
        a.db(
            0x21, source & 0xFF, source >> 8,
            0x11, destination & 0xFF, destination >> 8,
            0x01, length & 0xFF, length >> 8,
            0xCD, 0xB3, 0x09,              # stock BC-byte memcpy
        )
    a.db(
        0xCD, OAM_LUT_INIT_ADDR & 0xFF, OAM_LUT_INIT_ADDR >> 8,
        0x3E, 0xA7,
        0xEA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xE1, 0xD1, 0xC1, 0xC9,
    )
    code = a.finish()
    assert OAM_WRAM_COPY_ADDR + len(code) <= TITLE_TRANSITION_SERVICE_ADDR
    return code


def build_native_glyph_restore() -> bytes:
    """Restore the native digit-9 tile with one guarded 16-byte GDMA."""
    a = _Asm()
    a.db(0xF0, 0x4F, 0xF5, 0xAF, 0xE0, 0x4F)
    a.db(0xFA, 0xFC, 0x97, 0xFE, 0x18)
    a.jr(0x20, "done")
    for register, value in (
        (0x51, ((TITLE_GLYPH_DATA_ADDR + 0x10) >> 8) & 0xFF),
        (0x52, (TITLE_GLYPH_DATA_ADDR + 0x10) & 0xF0),
        (0x53, 0x17),
        (0x54, 0xF0),
        (0x55, 0x00),
    ):
        a.db(0x3E, value, 0xE0, register)
    a.label("done")
    a.db(0xF1, 0xE0, 0x4F, 0xC9)
    return a.finish()


def install_semantic_oam_intercepts(rom: bytearray) -> None:
    """Install complete sprite-emission palette hooks and fixed-slot attr."""
    vanilla = Path("rom/Penta Dragon (J).gb").read_bytes()
    sites = (
        (
            0x10D1, 0x10EE, OAM_CENTRAL_EMITTER_RUNTIME_ADDR, 0x79,
            build_oam_wram_tail_wrapper,
        ),
        (
            0x346F, 0x34A3, OAM_FREE_EMITTER_ADDR, 0x7A,
            build_oam_bank_wrapper,
        ),
    )
    for start, end, helper, final_a, wrapper_builder in sites:
        assert rom[start:end] == vanilla[start:end], (
            f"semantic OAM emitter changed at ${start:04X}"
        )
        wrapper = wrapper_builder(helper, final_a)
        assert len(wrapper) <= end - start
        rom[start:end] = wrapper + bytes(end - start - len(wrapper))

    # Fixed slot 31 uses tile $1D, which the production cascade maps to OBJ4.
    assert rom[0x1F02:0x1F05] == bytes([0xAF, 0x77, 0xAF])
    rom[0x1F02:0x1F05] = bytes([0x36, 0x04, 0xAF])


def build_title_transition_service() -> bytes:
    """Service title entry on the scene-change path before DF0D is replaced.

    Returning from the demo enters $01 with FFC1 still set; re-arm the existing
    two-map neutral cleaner once and publish the already-empty title shadow OAM.
    Without that transition-only DMA, gameplay Sara remains in hardware OAM
    over the returned title menu until the later $1C banner transition. Entry
    to $1C keeps its defensive OAM DMA as well. The helper preserves all
    registers expected by the scene dispatcher.
    """
    a = _Asm()
    a.db(0xF5, 0xC5, 0xD5, 0xE5)            # preserve AF,BC,DE,HL
    a.db(0xFE, 0x01)                        # A is new D880
    a.jr(0x20, "check_gameplay")
    a.db(
        0xAF,
        0xEA, 0x08, 0xDF,                  # rearm both-map title cleaner
        0xCD, 0x80, 0xFF,                  # one transition-only OAM clear
    )
    a.jr(0x18, "done")

    a.label("check_gameplay")
    a.db(0xFE, 0x02)
    a.jr(0x20, "check_banner")
    # Arm the complete gameplay palette pass immediately on Stage 1 entry.
    # The fade-aware scheduler waits for native BGP=$E4, but no longer loses
    # up to seven idle-probe frames before beginning the bounded 17 phases.
    a.db(
        0x3E, 0x11,
        0xEA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
    )
    a.jr(0x18, "done")

    a.label("check_banner")
    a.db(0xFE, 0x1C)
    a.jr(0x20, "done")
    a.db(0xCD, 0x80, 0xFF)                  # one transition-only OAM clear

    a.label("done")
    a.db(
        # Story caches only need clearing once when FFC1-active play resumes;
        # the former per-VBlank test was pure steady-state gameplay overhead.
        0xF0, 0xC1, 0xB7,
        0xC4, STORY_INACTIVE_HELPER_ADDR & 0xFF,
        STORY_INACTIVE_HELPER_ADDR >> 8,
        0x3E, 0x12,
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        # The title footer temporarily replaces native digit 9 with a period.
        # Restore it once after an accepted transition, outside the cycle-
        # locked per-frame title wrapper.
        0xFA, 0x80, 0xD8, 0xFE, 0x02,
        0xD4, NATIVE_GLYPH_RESTORE_ADDR & 0xFF,
        NATIVE_GLYPH_RESTORE_ADDR >> 8,
        0xE1, 0xD1, 0xC1, 0xF1, 0xC9,
    )
    return a.finish()


def build_stale_window_cleanup() -> bytes:
    """Hide a stale item-menu Window before it can cover dungeon gameplay.

    Stock marks both item-menu entry paths with FFE4=1 and clears it on their
    normal exits.  Only the live Stage 1 scene ($02) is receipt-covered here;
    later dungeon-family scenes use the Window for legitimate transitions and
    remain outside this guard.
    """
    return bytes.fromhex(
        "F0 E4 B7 C0 "    # FFE4!=0: legitimate item menu
        "FA 80 D8 FE 02 C0 " # only live Stage 1 scene $02
        "F0 40 CB AF "    # clear the already-confirmed Window bit
        "E0 40 AF C9"     # publish; return A=0/Z for window-off path
    )


def build_title_palette_copy_helper() -> bytes:
    """Copy one eight-byte palette from HL to the selected CRAM data port."""
    return bytes.fromhex("0E 08 2A E0 69 0D 20 FA C9")


def build_title_glyph_blob() -> bytes:
    """Period tile plus the CGB boot-font 9 tile restored after the title."""
    return PERIOD_TILE + NATIVE_DIGIT_9_TILE


def build_vram_glyph_copy(
    death_late_fix_addr: int = DEATH_LATE_FIX_ADDR,
) -> bytes:
    """Build the gated VBlank helper for the exact v3.01 footer glyphs.

    LCDC uses signed BG tile addressing on the title, so IDs 0x76-0x7F are at
    VRAM 0x9760-0x97FF, not 0x8760. Native tiles already provide 0, 1, and 3.
    Tile 0x7F is temporarily replaced with a period, then its native 9 glyph is
    restored after leaving the title. Both writes use one-block CGB GDMA.
    """
    c = bytearray()

    # Route ordinary gameplay before touching VBK. The previous version saved
    # and restored VBK, then tail-called a second D880 checker every VBlank
    # even though scenes $02-$14 cannot need either title glyph or death-art
    # repair. Keeping the VBK setup after the title branch preserves the exact
    # 80-cycle entry timing of the proven D880 $00/$01 title path.
    c.extend([0xFA, 0x80, 0xD8, 0xFE, 0x02])
    j_title = len(c) + 1
    c.extend([0x38, 0x00])                # JR C, title
    c.extend([0xFE, 0x15, 0xD8])          # RET C for ordinary gameplay

    def emit_vbk_setup() -> None:
        c.extend([0xF0, 0x4F, 0xF5])      # LDH A,[FF4F]; PUSH AF
        c.extend([0xAF, 0xE0, 0x4F])      # select VRAM bank 0

    def emit_gdma(source_addr: int) -> None:
        for register, value in (
            (0x51, (source_addr >> 8) & 0xFF),
            (0x52, source_addr & 0xF0),
            (0x53, 0x17),                  # destination 0x9700 page
            (0x54, 0xF0),                  # destination 0x97F0
            (0x55, 0x00),                  # one 16-byte block, GDMA mode
        ):
            c.extend([0x3E, value, 0xE0, register])

    # Lay out the non-title restore first so its VBK setup falls through and
    # costs exactly what the former setup-plus-JR route cost.
    emit_vbk_setup()
    restore_nine_pos = len(c)
    c.extend([0xFA, 0xFC, 0x97, 0xFE, 0x18])
    j_skip_restore = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, copy_done
    emit_gdma(TITLE_GLYPH_DATA_ADDR + 0x10)

    copy_done_pos = len(c)
    c.extend([
        0xF1,                              # POP AF (saved VBK)
        0xC3,
        death_late_fix_addr & 0xFF,
        death_late_fix_addr >> 8,
    ])                                    # tail-call VBK restore/death fix

    # Title code lives after the shared tail and branches backward to it. This
    # saves the two-byte forward jump that otherwise exceeded the 0x6E00 slot.
    title_path = len(c)
    c[j_title] = (title_path - j_title - 1) & 0xFF
    emit_vbk_setup()

    # Wait until the footer's native 3 has been placed in the active tilemap.
    c.extend([0xFA, 0x45, 0x9A])          # LD A, [0x9A45]
    c.extend([0xFE, CUSTOM_TITLE_TILES["3"]])
    j_skip_footer = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, copy_done
    c.extend([0xFA, 0xFC, 0x97])          # LD A, [0x97FC] (tile 0x7F row 6)
    c.extend([0xFE, 0x18])
    j_skip_loaded = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z, copy_done
    emit_gdma(TITLE_GLYPH_DATA_ADDR)
    j_title_done = len(c) + 1
    c.extend([0x18, 0x00])                # JR copy_done

    for jump_pos in (
        j_skip_restore, j_skip_footer, j_skip_loaded, j_title_done
    ):
        delta = copy_done_pos - jump_pos - 1
        assert -128 <= delta <= 127
        c[jump_pos] = delta & 0xFF
    code = bytes(c)
    assert VRAM_GLYPH_COPY_ADDR + len(code) <= COLORIZE_ADDR
    return code


def build_colorize_prelude() -> bytes:
    """Build the safe per-VBlank setup that replaces the teleport monolith.

    The old routine bundled useful scene/palette setup with a SELECT+START
    stack redirect out of the VBlank IRQ. The redirect was timing- and wrapper-
    layout-sensitive and could freeze the game. This prelude keeps only the
    release features: scene table selection, lava overrides, the level-select
    WRAM stub copy, and bounded item-menu window attribute maintenance.
    """
    c = bytearray()

    c.extend([0xCD, SCENE_DETECT_ADDR & 0xFF, SCENE_DETECT_ADDR >> 8])

    # Stage and arena setup can clear the colorizer's cold-boot sentinel well
    # after scene_detect has copied the correct table. Preserve every selected
    # non-title table before colorize runs:
    #   - any scene >= $0C (all arenas, story, splash, death/ending)
    #   - later dungeon-family scenes selected by FFBA > 0
    # Without the arena branch Ted eventually recopies the Stage 1 table about
    # 250 frames after entry, even though its own table initially loaded.
    c.extend([0xFA, 0x80, 0xD8, 0xFE, 0x0C])  # dungeon-family upper bound
    j_preserve_high_scene = len(c) + 1
    c.extend([0x30, 0x00])                    # JR NC,preserve table
    c.extend([0xFE, 0x02])
    j_not_later_lo = len(c) + 1
    c.extend([0x38, 0x00])                    # JR C,not_later
    c.extend([0xF0, 0xBA, 0xB7])              # LDH A,[FFBA]; OR A
    j_not_later_stage1 = len(c) + 1
    c.extend([0x28, 0x00])                    # JR Z,not_later
    # Stage 1 takes the branch above with exactly its receipt-proven cadence.
    # Later stages repair BG0 only on the phased-loader frame that just copied
    # slot 0, avoiding both a permanent CRAM tax and yellow snowfields.
    c.extend([
        0xCD,
        LATER_STAGE_BG0_REPAIR_ADDR & 0xFF,
        LATER_STAGE_BG0_REPAIR_ADDR >> 8,
    ])
    preserve_table = len(c)
    c.extend([0x3E, 0x5A, 0xEA, 0x02, 0xDF])  # preserve neutral table
    not_later = len(c)
    c[j_preserve_high_scene] = (
        preserve_table - j_preserve_high_scene - 1
    ) & 0xFF
    for jump_pos in (j_not_later_lo, j_not_later_stage1):
        c[jump_pos] = (not_later - jump_pos - 1) & 0xFF

    # The path into not_later preserves Carry only for D880<2 (title and
    # save-present level select); every gameplay/attract route arrives NC.
    # Use that existing flag instead of reading another live WRAM byte. Menu
    # frames retain the historical CFAA validation/copy verbatim. Gameplay
    # skips terrain-owned CFAA and pays an equal 32T padding path. A final 16T
    # padding pair plus a tail JP to lava replaces CALL+RET and the prelude RET,
    # balancing both fast routes and the rare menu repair cycle-for-cycle with
    # the prior release while keeping CFAA untouched during active play.
    j_live_cfaa = len(c) + 1
    c.extend([0x30, 0x00])                # JR NC,live_cfaa
    levelsel_stub = build_levelsel_attr_clear_stub()
    assert len(levelsel_stub) == LEVELSEL_STUB_MAX
    c.extend([
        0xFA, LEVELSEL_STUB_WRAM & 0xFF, LEVELSEL_STUB_WRAM >> 8,
        0xFE, levelsel_stub[0],
    ])
    j_stub_ready = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z,window_maintenance
    c.extend([
        0x21, LEVELSEL_STUB_ROM_ADDR & 0xFF, LEVELSEL_STUB_ROM_ADDR >> 8,
        0x11, LEVELSEL_STUB_WRAM & 0xFF, LEVELSEL_STUB_WRAM >> 8,
    ])
    c.extend([0x06, LEVELSEL_STUB_MAX])
    copy_loop = len(c)
    c.extend([0x2A, 0x12, 0x13, 0x05])    # ROM -> title-owned CFAA
    c.extend([0x20, (copy_loop - (len(c) + 2)) & 0xFF])
    c.extend([0x3E, 0x5A, 0xEA, 0x0E, 0xDF])
    window_maintenance = len(c)
    c[j_stub_ready] = (window_maintenance - j_stub_ready - 1) & 0xFF

    # The item menu is a hardware window at WY=96. The game rewrites its tile
    # IDs but leaves VBK=1 untouched, so the window inherits dungeon item/wall
    # attributes from the off-screen map. Clear three 20-cell rows per VBlank,
    # alternating the MEDICAL/HP group (0,4,5) with the middle group (1,2,3).
    # The former six-row burst occasionally crossed out of VBlank before row 5,
    # leaving the exact intermittent red C0/F4 artifacts reported on the HP
    # line. Two bounded 60-cell passes keep every row neutral within one frame.
    c.extend([0xF0, 0x40, 0xE6, 0x20])    # LDH A,[LCDC]; AND window-enable
    j_window_on = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ, window_on
    window_off = len(c)
    c.extend([0xEA, 0x0F, 0xDF])          # DF0F = 0 (A is already zero)
    j_colorize_off = len(c) + 1
    c.extend([0x18, 0x00])                # JR colorize

    window_on = len(c)
    c[j_window_on] = (window_on - j_window_on - 1) & 0xFF
    c.extend([
        0xCD,
        STALE_WINDOW_CLEANUP_ADDR & 0xFF,
        STALE_WINDOW_CLEANUP_ADDR >> 8,
    ])
    j_stale_window_hidden = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z,window_off
    c.extend([0xF0, 0x4F, 0xF5, 0x3E, 0x01, 0xE0, 0x4F])
    c.extend([0xF0, 0x40, 0xE6, 0x40])    # LCDC window-map select
    c.extend([0x26, 0x98, 0x28, 0x02, 0x26, 0x9C])

    # DF0F is a menu-open two-phase toggle. Its zero state is restored when
    # the window closes, so every opening starts with the visible HUD rows.
    c.extend([0xFA, 0x0F, 0xDF, 0xEE, 0x01, 0xEA, 0x0F, 0xDF])
    j_middle_rows = len(c) + 1
    c.extend([0x28, 0x00])                  # JR Z,middle_rows

    clear_calls: list[int] = []

    def emit_clear_row(row: int) -> None:
        c.extend([0x2E, (row * 0x20) & 0xFF])  # LD L,row*32
        clear_calls.append(len(c) + 1)
        c.extend([0xCD, 0x00, 0x00])           # CALL clear_20

    # First/odd phase: the rows that contain MEDICAL, both HP lines, and F.
    for row in (0, 4, 5):
        emit_clear_row(row)
    j_rows_done = len(c) + 1
    c.extend([0x18, 0x00])                  # JR rows_done

    middle_rows = len(c)
    c[j_middle_rows] = (middle_rows - j_middle_rows - 1) & 0xFF
    for row in (1, 2, 3):
        emit_clear_row(row)

    rows_done = len(c)
    c[j_rows_done] = (rows_done - j_rows_done - 1) & 0xFF
    c.extend([0xF1, 0xE0, 0x4F])          # restore VBK

    c[j_stale_window_hidden] = (
        window_off - j_stale_window_hidden - 1
    ) & 0xFF

    finish = len(c)
    c[j_colorize_off] = (finish - j_colorize_off - 1) & 0xFF
    c.extend([
        0x23, 0x2B,                         # common 16T balance, preserve HL
        0xC3, LAVA_OVERRIDE_ADDR & 0xFF, LAVA_OVERRIDE_ADDR >> 8,
    ])

    # The live branch is out of line so the rare menu repair can fall straight
    # into window maintenance. Branch (12T) + padding (20T) + JR (12T) equals
    # the menu branch-not-taken plus ready-stub check (44T).
    live_cfaa = len(c)
    c[j_live_cfaa] = (live_cfaa - j_live_cfaa - 1) & 0xFF
    c.extend([0x00, 0x23, 0x2B])            # 20T, preserve HL and flags
    c.extend([
        0x18,
        (window_maintenance - (len(c) + 2)) & 0xFF,
    ])

    # Shared bounded row primitive. It is placed after the public RET so the
    # prelude's normal return cannot fall through into it.
    clear_20_addr = WINDOW_ATTR_CLEAR_HELPER_ADDR
    assert COLORIZE_PRELUDE_ADDR + len(c) <= clear_20_addr
    c.extend(bytes(clear_20_addr - (COLORIZE_PRELUDE_ADDR + len(c))))
    for call_operand in clear_calls:
        c[call_operand] = clear_20_addr & 0xFF
        c[call_operand + 1] = (clear_20_addr >> 8) & 0xFF
    c.extend([0x0E, 0x14, 0xAF])            # C=20, A=exact attr 0
    clear_cell = len(c)
    c.extend([0x22, 0x0D])                  # LD [HL+],A; DEC C
    c.extend([0x20, (clear_cell - (len(c) + 2)) & 0xFF])
    c.extend([0xC9])
    assert (
        COLORIZE_PRELUDE_ADDR + len(c)
        == WINDOW_ATTR_CLEAR_HELPER_ADDR + 8
    )
    return bytes(c)


def build_title_palette_fix(story_dispatch_addr: int) -> bytes:
    """Safely restore YAML BG0 and its title-safe BG7 alias on title screens.

    The stock cold-boot path can cross out of VBlank while loading CRAM, leaving
    either palette partially white. This helper runs in menu states $00/$01,
    including the returned title where stock leaves FFC1 set. The long menu
    dwell repairs both palettes before $1C/$1B without taxing their animation
    cadence. Gameplay still receives independently tuned YAML BG7.
    """
    c = bytearray()
    c.extend([0xFA, 0x80, 0xD8, 0xFE, 0x02, 0xD0])
    # FFC1=1,D880=0 is also the normal GAME START transition. Do not mask that
    # stock state as a returned title: only D880=1 owns returned-title repairs.
    c.extend([0x47, 0xF0, 0xC1, 0xB7])
    j_title = len(c) + 1
    c.extend([0x28, 0x00])                # JR Z,title (cold title)
    c.extend([0x78, 0x3D, 0xC0])          # returned title only when D880==1
    title = len(c)
    c[j_title] = (title - j_title - 1) & 0xFF
    # D880=0 also identifies the epilogue. Tail-dispatch its guarded story
    # attributes without doing title palette/cadence work; true title states
    # remain FFE4=0 and continue below. The service itself was CALLed, so the
    # story routine's RET still returns to the VBlank wrapper correctly.
    c.extend([0xF0, 0xE4, 0xB7])
    j_epilogue = len(c) + 1
    c.extend([0x20, 0x00])                # JR NZ,epilogue trampoline
    # The save-present selector publishes an out-of-range palette phase. The
    # normal title path pays 32T here. The post-copy cadence sequence below
    # preserves the receipt-proven title/reel cadence exactly.
    c.extend([
        0xFA, LEVELSEL_ACTIVE_ADDR & 0xFF, LEVELSEL_ACTIVE_ADDR >> 8,
        0xFE, LEVELSEL_ACTIVE_VALUE,
        0xC8,
    ])
    # The fixed-bank fade service now leaves title/menu CRAM untouched. Repair
    # the CGB boot-white BG0/BG7 immediately instead of waiting for BGP=$E4;
    # that old wait exposed two receipt-confirmed white title frames.
    c.extend([0x3E, 0x80, 0xE0, 0x68])    # BCPS index 0, auto-increment
    # Stage 1 reserves BG0[1] for pickup gold. The title must retain its
    # untouched blue-gray ramp, already stored in the boot-safe BG7 alias.
    c.extend([
        0x21, NATIVE_BG0_ALIAS_ADDR & 0xFF,
        NATIVE_BG0_ALIAS_ADDR >> 8,
    ])
    c.extend([
        0xCD,
        TITLE_PALETTE_COPY_HELPER_ADDR & 0xFF,
        TITLE_PALETTE_COPY_HELPER_ADDR >> 8,
    ])
    c.extend([0x3E, 0xB8, 0xE0, 0x68])    # BG7 byte 0, auto-increment
    c.extend([0x2E, 0x38])                # HL=$6838 (H remains $68)
    c.extend([
        0xCD,
        TITLE_PALETTE_COPY_HELPER_ADDR & 0xFF,
        TITLE_PALETTE_COPY_HELPER_ADDR >> 8,
        # Returned title keeps FFC1 set. Cancel any stale gameplay phase here,
        # before the wrapper reaches its palette scheduler, so it cannot
        # advance far enough to repaint BG0. This title-only path leaves the
        # receipt-proven demo/gameplay CRAM service timing untouched.
        0xAF,
        0xEA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        # 20T clear + 32T balance exactly replaces the old 52T delay call.
        # PUSH/POP preserves C; B is deliberately normalized just below.
        0xC5, 0xC1, 0x00,
        0x06, 0x00,                         # match old B=0 postcondition
        0xC9,
    ])
    epilogue = len(c)
    c[j_epilogue] = (epilogue - j_epilogue - 1) & 0xFF
    c.extend([
        0xC3, story_dispatch_addr & 0xFF, story_dispatch_addr >> 8,
    ])
    return bytes(c)


def build_native_dmg_fade_fixed_service() -> bytes:
    """Keep native fades from remapping a colorized active-play background.

    The stock four-step table writes ``E4/F9/FE/FF`` through this site.  In CGB
    mode, F9 briefly remaps every already-colorized BG palette and produces the
    user-visible white pulse.  The older workaround rewrote all 64 BG CRAM
    bytes to black on each non-E4 step; besides being expensive, that still
    exposed the bad BGP value for a rendered frame.

    The RST vector has already performed the original write. During active
    colorized play, normalize every non-E4 step back to E4. The two HRAM gates
    and unconditional RST dispatch preserve the exact 36/36 receipt-proven
    attract cadence; changing even an equivalent-looking prefix desynchronizes
    the prerecorded miniboss reel.
    """
    code = bytes([
        0xF0, 0xC1, 0xB7, 0xC8,             # inactive title: RET Z
        0xF0, 0xE4, 0xB7, 0xC0,             # native fade owner: RET NZ
        0xF0, 0x47,                         # LDH A,[BGP]
        0xFE, 0xE4,                         # already normal?
        0xC8,                               # RET Z
        0x3E, 0xE4,                         # active play always uses DMG order
        0xE0, 0x47,                         # LDH [BGP],A
        0xC9,                               # RET
    ])
    assert len(code) == 18
    return code


def build_conditional_palette_phased() -> bytes:
    """Hash palette state sparingly and service pending CRAM every VBlank.

    The full six-byte state hash was previously recomputed on every VBlank,
    even when no palette work was pending. On the timing-sensitive GAME START
    path that small permanent cost was enough to make the stock loop take
    roughly two display frames per logical tick. Probe for a new state once
    every eight stock VBlank ticks while idle; once a change is found, service
    all bounded one-palette phases on consecutive VBlanks.
    """
    c = bytearray([
        # Native BGP transitions own all CGB BG palettes until $E4. Leave the
        # pending phase intact and resume it after the fade.
        0xF0, 0x47, 0xFE, 0xE4, 0xC0,
        0xFA, PALETTE_PHASE_ADDR & 0xFF,
        PALETTE_PHASE_ADDR >> 8,            # A = pending phase
        0xB7,                               # OR A
        0xC2, PALETTE_LOADER_ADDR & 0xFF,
        PALETTE_LOADER_ADDR >> 8,           # pending: service every VBlank
        0xF0, 0xD4,                         # idle: stock VBlank tick
        0xE6, 0x07,                         # probe state once per 8 frames
        0xC0,                               # RET NZ
        0xCD,
        OAM_BOSS_LUT_SERVICE_ADDR & 0xFF,
        OAM_BOSS_LUT_SERVICE_ADDR >> 8,     # transition-only miniboss LUT
        0xF0, 0xBE, 0x47,                  # B = FFBE
        0xF0, 0xBF, 0xA8, 0x47,            # B ^= FFBF
        0xF0, 0xC0, 0xA8, 0x47,            # B ^= FFC0
        0xF0, 0xD0, 0xA8, 0x47,            # B ^= FFD0
        0xF0, 0xC1, 0xA8, 0x47,            # B ^= FFC1
        # Keep the receipt-proven room-transition cadence. Stage transitions
        # also change this key (and other hashed gameplay flags), which starts
        # the bounded BG reload that selects the stage-specific BG0 source.
        0xF0, 0xBD, 0xA8, 0x3C, 0x47,      # B = (B ^ FFBD) + 1
        0xFA, 0x00, 0xDF, 0xB8,            # compare cached DF00
    ])
    j_same = len(c) + 1
    c.extend([0x28, 0x00])                  # JR Z,service_pending
    c.extend([
        0x78, 0xEA, 0x00, 0xDF,            # cache the new hash
        0x3E, 0x11,
        0xEA, PALETTE_PHASE_ADDR & 0xFF,
        PALETTE_PHASE_ADDR >> 8,            # boss pre-pass, then phase 1
    ])
    service_pending = len(c)
    c[j_same] = (service_pending - j_same - 1) & 0xFF
    c.extend([
        0xFA, PALETTE_PHASE_ADDR & 0xFF,
        PALETTE_PHASE_ADDR >> 8,
        0xB7, 0xC8,                         # no pending work -> RET Z
        0xC3, PALETTE_LOADER_ADDR & 0xFF,
        PALETTE_LOADER_ADDR >> 8,
    ])
    assert (
        CONDITIONAL_PALETTE_IMPL_ADDR + len(c)
        <= SPOTLIGHT_PALETTE_MAP_ADDR
    )
    return bytes(c)


def build_phased_palette_loader() -> tuple[bytes, bytes, bytes]:
    """Build a one-palette-per-VBlank loader with no mode-3 CRAM writes.

    The former monolithic loader attempted 128-136 CRAM bytes in one VBlank.
    Even 32-byte quarters proved too large at the game's late IRQ hook. Phase
    17 performs an optional active-boss pre-pass, phases 1..8 load one OBJ
    palette each, and phases 9..16 load one BG palette each. Every service call
    therefore writes at most the same proven-safe eight CRAM bytes.
    """

    class Blob:
        def __init__(self, base: int):
            self.base = base
            self.code = bytearray()
            self.labels: dict[str, int] = {}
            self.abs_fixups: list[tuple[int, str]] = []
            self.rel_fixups: list[tuple[int, str]] = []

        def db(self, *values: int) -> None:
            self.code.extend(value & 0xFF for value in values)

        def label(self, name: str) -> None:
            self.labels[name] = self.base + len(self.code)

        def absolute(self, opcode: int, target: str) -> None:
            self.db(opcode, 0x00, 0x00)
            self.abs_fixups.append((len(self.code) - 2, target))

        def jr(self, opcode: int, target: str) -> None:
            self.db(opcode, 0x00)
            self.rel_fixups.append((len(self.code) - 1, target))

        def finish(self, labels: dict[str, int]) -> bytes:
            for pos, target in self.abs_fixups:
                address = labels[target]
                self.code[pos] = address & 0xFF
                self.code[pos + 1] = (address >> 8) & 0xFF
            for pos, target in self.rel_fixups:
                source_after = self.base + pos + 1
                offset = labels[target] - source_after
                assert -128 <= offset <= 127, (
                    f"palette JR {target} out of range: {offset}"
                )
                self.code[pos] = offset & 0xFF
            return bytes(self.code)

    main = Blob(PALETTE_LOADER_ADDR)
    ext = Blob(PALETTE_LOADER_EXT_ADDR)

    main.label("entry")
    main.db(0xFE, 0x11)
    main.absolute(0xCA, "boss_first")       # phase 17
    main.db(0xFE, 0x01)
    main.absolute(0xDA, "palette_done")     # phase 0/invalid
    main.db(0xFE, 0x09)
    main.absolute(0xDA, "obj_phase")        # phases 1..8
    main.db(0xFE, 0x11)
    main.absolute(0xDA, "bg_phase")         # phases 9..16
    main.label("palette_done")
    main.db(0xAF)
    main.absolute(0xC3, "store_phase")

    main.label("obj_phase")
    main.db(0x3D, 0x5F)                    # E = OBJ slot (phase - 1)

    # If this slot currently belongs to a boss, the phase-17 pre-pass already
    # owns it. Skip the base palette so it cannot overwrite the boss colors.
    main.db(0xF0, 0xBF, 0xB7)
    main.jr(0x28, "obj_normal")
    main.db(
        0x3D, 0x4F, 0x06, 0x00,
        0x21, BOSS_SLOT_TABLE_ADDR & 0xFF,
        BOSS_SLOT_TABLE_ADDR >> 8,
        0x09, 0x7E, 0xBB,                  # CP E
    )
    main.jr(0x28, "obj_advance")

    main.label("obj_normal")
    main.db(
        0x6B, 0x26, 0x00,                  # HL = slot
        0x29, 0x29, 0x29,                  # * 8
        0x01, 0x40, 0x68, 0x09,            # + base OBJ table
        0x7B, 0xB7,                        # slot 0?
    )
    main.jr(0x28, "obj0_variant")
    main.db(0xFE, 0x03)
    main.jr(0x30, "obj_source_ready")       # slots 3..7 use base source
    main.db(0xF0, 0xD0, 0xFE, 0x01)
    main.jr(0x20, "obj_source_ready")
    main.db(0x7B, 0xFE, 0x01)
    main.jr(0x20, "obj2_jet")
    main.db(0x21, 0xD8, 0x68)              # OBJ1 dragon jet
    main.jr(0x18, "obj_source_ready")
    main.label("obj2_jet")
    main.db(0x21, 0xD0, 0x68)              # OBJ2 witch jet
    main.jr(0x18, "obj_source_ready")

    main.label("obj0_variant")
    main.db(0xF0, 0xC0, 0xB7)
    main.jr(0x28, "obj_source_ready")
    main.db(0xFE, 0x01)
    main.jr(0x20, "obj0_check_shield")
    main.db(0x21, 0xE0, 0x68)
    main.jr(0x18, "obj_source_ready")
    main.label("obj0_check_shield")
    main.db(0xFE, 0x02)
    main.jr(0x20, "obj0_turbo")
    main.db(0x21, 0xE8, 0x68)
    main.jr(0x18, "obj_source_ready")
    main.label("obj0_turbo")
    main.db(0x21, 0xF0, 0x68)

    main.label("obj_source_ready")
    main.db(0x7B, 0x87, 0x87, 0x87, 0xF6, 0x80)
    main.absolute(0xCD, "copy_obj")

    main.label("obj_advance")
    main.db(0x7B, 0xC6, 0x02)              # next phase = slot + 2
    main.absolute(0xC3, "store_phase")

    main.label("boss_first")
    main.absolute(0xCD, "load_boss")
    main.db(0x3E, 0x01)
    main.absolute(0xC3, "store_phase")

    main.label("load_boss")
    main.db(0xF0, 0xBF, 0xB7, 0xC8)        # no active boss -> RET Z
    main.db(
        0x3D, 0x5F, 0x4F, 0x06, 0x00,     # E/C = boss index
        0x21, BOSS_SLOT_TABLE_ADDR & 0xFF,
        BOSS_SLOT_TABLE_ADDR >> 8,
        0x09, 0x7E,
        0x87, 0x87, 0x87, 0xF6, 0x80,     # destination OBJ slot
        0xF5,
        0x6B, 0x26, 0x00,
        0x29, 0x29, 0x29,
        0x01, 0x80, 0x68, 0x09,            # boss palette source
        0xF1,
    )
    main.absolute(0xCD, "copy_obj")
    main.db(0xC9)

    main.label("store_phase")
    main.db(
        0xEA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        0xC9,
    )

    main.label("copy_obj")
    main.db(0xE0, 0x6A, 0x0E, 0x6B)        # OCPS; C = OCPD
    main.absolute(0xC3, "copy_cram8")

    main.label("copy_bg")
    main.db(0xE0, 0x68, 0x0E, 0x69)        # BCPS; C = BCPD
    main.absolute(0xC3, "copy_cram8")

    ext.label("bg_phase")
    # Stage 1 visibly uses BG6, BG0, and BG1. Load the rotated order
    # 6,7,0,1,2,3,4,5 so every active Stage 1 palette is ready before sustained
    # scrolling begins; the remaining writes affect inactive slots only.
    ext.db(
        0xD6, 0x09,                         # A = phase index 0..7
        0x57,                               # D = phase index
        0xC6, 0x06,
        0xE6, 0x07,
        0x5F,                               # E = rotated BG slot
    )
    # Compute $6800 + slot*8 in 28 cycles rather than the former 56-cycle
    # 16-bit multiply/add.  The saved cycles pay for an inline slot-7 scene
    # selector, avoiding a timing-visible helper call in attract/demo play.
    ext.db(
        0x7B,                               # LD A,E
        0x07, 0x07, 0x07,                   # RLCA x3
        0x6F, 0x26, 0x68,                   # HL=$6800 + slot*8
        0x7B, 0xFE, 0x07,                   # slot 7?
    )
    ext.jr(0x20, "bg_source_pad")          # other slots: timing pad
    ext.db(
        0x2E, TUNED_BG7_SOURCE_ADDR & 0xFF, # cutscene/default: YAML BG7
        # Hazard BG7 is selected iff FFC1=1 and FFD0=0. Transform FFC1
        # 1->0 and 0->FF, then OR it with FFD0; this preserves the prior
        # Stage-1/demo path at exactly 64 cycles while cutscenes keep YAML
        # BG7. The prerecorded input stream is cycle-sensitive here.
        0xF0, 0xC1, 0x4F, 0x0D,
        0xF0, 0xD0, 0xB1,
    )
    ext.jr(0x20, "bg_source_ready")
    ext.db(
        0x2E, STAGE1_HAZARD_BG7_SOURCE_ADDR & 0xFF,
        0x00,                               # exact old Stage-1 64T cadence
    )
    ext.label("bg_source_ready")
    ext.db(0x7B, 0x87, 0x87, 0x87, 0xF6, 0x80)
    ext.absolute(0xCD, "copy_bg")
    ext.db(0x7A, 0xFE, 0x07)
    ext.absolute(0xCA, "palette_done")
    ext.db(0xC6, 0x0A)                    # next phase = slot + 10
    ext.absolute(0xC3, "store_phase")

    # Non-slot-7 and inactive/title paths use the 28 cycles saved above, so
    # their palette-service timing remains byte-for-byte equivalent in frame
    # cadence to the proven loader.  LY is sampled only as a harmless pad.
    ext.label("bg_source_pad")
    ext.db(0xF0, 0x44)                     # LDH A,[LY] (12 cycles)
    ext.absolute(0xC3, "bg_source_ready")  # JP (16 cycles)

    # CGB palette data is inaccessible only in LCD mode 3. The game's VBlank
    # hook can arrive after mode 1 has already ended, so each four-byte half
    # waits for a fresh HBlank. During mode 1 (or with LCD off), it writes
    # immediately. Four unrolled LDH [C],A writes fit inside one HBlank.
    ext.label("copy_cram4")
    ext.db(0xF0, 0x40, 0xCB, 0x7F)         # LCDC bit 7
    ext.jr(0x28, "copy_cram4_write")        # LCD off: always accessible
    ext.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x01)
    ext.jr(0x28, "copy_cram4_write")        # mode 1: VBlank
    ext.label("copy_cram4_wait3")
    ext.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    ext.jr(0x20, "copy_cram4_wait3")
    ext.label("copy_cram4_wait0")
    ext.db(0xF0, 0x41, 0xE6, 0x03)
    ext.jr(0x20, "copy_cram4_wait0")
    ext.label("copy_cram4_write")
    for _ in range(4):
        ext.db(0x2A, 0xE2)                  # LD A,[HL+]; LDH [C],A
    ext.db(0xC9)

    labels = {
        **main.labels,
        **ext.labels,
        "copy_cram8": PALETTE_COPY_CRAM8_ADDR,
    }
    main_code = main.finish(labels)
    ext_code = ext.finish(labels)
    copy_cram4_addr = ext.labels["copy_cram4"]
    copy_cram8_code = bytes([
        0xCD, copy_cram4_addr & 0xFF, copy_cram4_addr >> 8,
        0xCD, copy_cram4_addr & 0xFF, copy_cram4_addr >> 8,
        0xC9,
    ])
    assert PALETTE_LOADER_ADDR + len(main_code) <= SHADOW_MAIN_ADDR
    assert PALETTE_LOADER_EXT_ADDR + len(ext_code) <= ARENA_BASE_ADDR
    assert len(copy_cram8_code) <= 18
    return main_code, ext_code, copy_cram8_code


def build_later_stage_bg0_repair() -> bytes:
    """Restore native BG0 after the Stage-1 pickup palette is reloaded.

    The phased loader enters BG slot 0 with phase $0B and stores its next
    phase ($0C) before the VBlank wrapper reaches the colorize prelude. Only
    later-stage dungeon paths call this helper, so Stage 1 executes no added
    instructions. The title-safe BG7 source at $6838 remains a byte-exact copy
    of the native BG0 ramp.
    """
    code = bytes([
        0xFA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        0xFE, 0x0C,
        0xC0,                               # RET NZ
        # Force entry starts here for a newly entered later-stage dungeon.
        0x3E, 0x80, 0xE0, 0x68,             # BG0, auto-increment
        0x21, NATIVE_BG0_ALIAS_ADDR & 0xFF,
        NATIVE_BG0_ALIAS_ADDR >> 8,         # native BG0 alias
        0x0E, 0x69,                         # BCPD
        0xC3, PALETTE_COPY_CRAM8_ADDR & 0xFF,
        PALETTE_COPY_CRAM8_ADDR >> 8,
        # Scene-detect entry: repair, then preserve its original all-pal0
        # later-dungeon table initialization via the existing helper.
        0xCD, LATER_STAGE_BG0_FORCE_ADDR & 0xFF,
        LATER_STAGE_BG0_FORCE_ADDR >> 8,
        0xC3, UNIFORM_CLEAR_ADDR & 0xFF, UNIFORM_CLEAR_ADDR >> 8,
    ])
    assert LATER_STAGE_BG0_FORCE_ADDR == LATER_STAGE_BG0_REPAIR_ADDR + 6
    assert LATER_STAGE_BG0_ENTRY_ADDR == LATER_STAGE_BG0_REPAIR_ADDR + 18
    assert len(code) == 24
    assert LATER_STAGE_BG0_REPAIR_ADDR + len(code) <= DEATH_FADE_HELPER_ADDR
    return code


def compile_spotlight_palette_map(
    path: Path = SPOTLIGHT_MAP_YAML,
) -> tuple[bytes, list[int], list[int]]:
    """Compile the complete spotlight roster to two palette slots per byte.

    Each non-Sara entry points to the byte-identical graphics block's ordinary
    gameplay tile. Resolving that tile through build_obj_pal_table() makes the
    title reel follow monster_palette_map.yaml automatically.
    """
    config = yaml.safe_load(Path(path).read_text())
    entries = sorted(config.get("roster", []), key=lambda row: row["identity"])
    identities = [int(row["identity"]) for row in entries]
    assert identities == list(range(SPOTLIGHT_ROSTER_SIZE)), (
        "spotlight_palette_map.yaml must define identities 0..37 exactly once"
    )

    gameplay_lut = build_obj_pal_table()
    palette_slots: list[int] = []
    resource_ids: list[int] = []
    for row in entries:
        resource = int(row["resource_id"])
        gameplay_tile = int(row["gameplay_tile"])
        assert 0 <= resource <= 0xFF
        assert 0 <= gameplay_tile <= 0xFF
        resource_ids.append(resource)
        palette = gameplay_lut[gameplay_tile]
        if palette == 0xFF:
            form = row.get("form")
            assert form in {"witch", "dragon"}, (
                f"dynamic spotlight identity {row['identity']} needs a form"
            )
            palette = 2 if form == "witch" else 1
        assert 0 <= palette <= 7
        palette_slots.append(palette)

    packed = bytearray()
    for identity in range(0, SPOTLIGHT_ROSTER_SIZE, 2):
        packed.append(
            palette_slots[identity]
            | (palette_slots[identity + 1] << 4)
        )
    assert len(packed) == 19
    return bytes(packed), palette_slots, resource_ids


def build_spotlight_palette_loader() -> bytes:
    """Resolve and load the current spotlight actor's OBJ palette on demand.

    No OBJ CRAM work is needed while the player is navigating the title and
    GAME START screens. FFF2 identifies all 38 idle-reel actors. Decode its
    packed YAML-derived palette into C, cache identity+1 in DF4D, and load only
    that OBJ slot when the actor first appears. The normal gameplay scheduler
    remains independent and DF4C returns to its idle zero state.
    """
    a = _Asm()
    a.db(
        0xF0, 0xF2,                         # A = FFF2 identity
        0x47,                               # B = identity/parity
        0xCB, 0x3F,                         # SRL A: packed byte index
        0xC6, SPOTLIGHT_PALETTE_MAP_ADDR & 0xFF,
        0x6F,                               # L = map low + index
        0x26, SPOTLIGHT_PALETTE_MAP_ADDR >> 8,
        0x7E,                               # A = packed palettes
        0xCB, 0x40,                         # BIT 0,B
    )
    a.jr(0x28, "decoded")
    a.db(0xCB, 0x37)                        # odd identity: SWAP A
    a.label("decoded")
    a.db(
        0xE6, 0x0F,
        0x4F,                               # C = YAML OBJ palette
        0x04,                               # B = identity + 1
        0xFA,
        SPOTLIGHT_PALETTE_CACHE_ADDR & 0xFF,
        SPOTLIGHT_PALETTE_CACHE_ADDR >> 8,
        0xB8, 0xC8,                        # already loaded -> RET Z
        0x78,
        0xEA,
        SPOTLIGHT_PALETTE_CACHE_ADDR & 0xFF,
        SPOTLIGHT_PALETTE_CACHE_ADDR >> 8,
        0x79, 0x3C,                        # A = mapped OBJ slot + 1 phase
        0xC5,                              # preserve returned B/C
        0xCD, PALETTE_LOADER_ADDR & 0xFF,
        PALETTE_LOADER_ADDR >> 8,
        0xC1,
        0xAF,
        0xEA, PALETTE_PHASE_ADDR & 0xFF,
        PALETTE_PHASE_ADDR >> 8,
        0xC9,
    )
    code = a.finish()
    assert (
        SPOTLIGHT_PALETTE_HELPER_ADDR + len(code)
        <= STORY_VIEWPORT_KEY_HELPER_ADDR
    )
    return code


def map_title_string_to_tiles(s: str) -> list[int]:
    """Map alphanumeric string to title screen tile indices.

    Mapping:
      Space  -> 0x00
      A-Z    -> 0x80 - 0x99
      0,1,3  -> 0x76, 0x77, 0x79 (native title digit tiles)
      .      -> 0x7F (temporary period; 0x75 is a parser control value)
    """
    tiles = []
    for char in s.upper():
        if char == ' ':
            tiles.append(0x00)
        elif 'A' <= char <= 'Z':
            tiles.append(0x80 + (ord(char) - ord('A')))
        elif char in CUSTOM_TITLE_TILES:
            tiles.append(CUSTOM_TITLE_TILES[char])
        else:
            raise ValueError(f"unsupported title character: {char!r}")
    return tiles


def write_output_with_backup(
    output_path: Path,
    rom: bytes | bytearray,
    *,
    backup_existing: bool,
) -> Path | None:
    """Write a ROM, preserving a hash-named rollback copy when requested."""
    output_path = Path(output_path)
    payload = bytes(rom)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists():
        output_path.write_bytes(payload)
        return None

    existing = output_path.read_bytes()
    if existing == payload:
        print(f"  output unchanged: {output_path}")
        return None
    if not backup_existing:
        output_path.write_bytes(payload)
        return None

    digest = hashlib.md5(existing).hexdigest()
    backup_path = output_path.with_name(
        f"{output_path.stem}.prebuild_{digest[:8]}.backup{output_path.suffix}"
    )
    if backup_path.exists():
        if backup_path.read_bytes() != existing:
            raise RuntimeError(
                f"refusing to replace mismatched backup: {backup_path}"
            )
        print(f"  rollback backup already present: {backup_path}")
    else:
        shutil.copy2(output_path, backup_path)
        print(f"  rollback backup: {backup_path} (MD5 {digest})")
    output_path.write_bytes(payload)
    return backup_path


def _remap_2bpp_indices(tile: bytes, mapping: tuple[int, int, int, int]) -> bytes:
    """Remap a Game Boy tile's four pixel indices without changing its shape."""
    assert len(tile) == 16
    assert len(mapping) == 4 and all(0 <= value <= 3 for value in mapping)
    result = bytearray()
    for row in range(0, 16, 2):
        low, high = tile[row:row + 2]
        remapped_low = 0
        remapped_high = 0
        for bit in range(8):
            mask = 1 << bit
            old = (1 if low & mask else 0) | (2 if high & mask else 0)
            new = mapping[old]
            if new & 1:
                remapped_low |= mask
            if new & 2:
                remapped_high |= mask
        result.extend((remapped_low, remapped_high))
    return bytes(result)


def _tile_indices(tile: bytes) -> set[int]:
    values: set[int] = set()
    for row in range(0, len(tile), 2):
        low, high = tile[row:row + 2]
        for bit in range(8):
            mask = 1 << bit
            values.add(
                (1 if low & mask else 0) | (2 if high & mask else 0)
            )
    return values


def apply_stage1_reserved_pickup_gold(
    rom: bytearray,
    vanilla_rom: bytes,
) -> None:
    """Reserve BG0 index 1 for pickups with no runtime hooks or attr scans.

    Stage 1's signed-index tileset is stored as two raw 0x800-byte halves:
    IDs 00-7F at 0x1D000 and IDs 80-FF at 0x1F000.  Pickup art collapses
    its two middle DMG shades onto index 1; every other Stage-1 tile collapses
    index 1 onto index 2.  Changing only BG0[1] can therefore make pickups
    gold without painting a single ordinary terrain pixel gold.
    """
    pickup_tiles = {
        tile for tile, palette in enumerate(BG_TABLE_BYTES)
        if 1 <= palette <= 5
    }
    assert len(pickup_tiles) == 73
    pickup_mapping = (0, 1, 1, 3)
    terrain_mapping = (0, 2, 2, 3)
    for tile in range(0x100):
        source = (
            STAGE1_LOW_TILE_GFX_OFFSET + tile * 16
            if tile < 0x80
            else STAGE1_HIGH_TILE_GFX_OFFSET + tile * 16
        )
        original = vanilla_rom[source:source + 16]
        assert len(original) == 16
        assert rom[source:source + 16] == original, (
            f"Stage-1 tile source {tile:02X} changed before art remap"
        )
        mapping = pickup_mapping if tile in pickup_tiles else terrain_mapping
        remapped = _remap_2bpp_indices(original, mapping)
        indices = _tile_indices(remapped)
        if tile in pickup_tiles:
            assert 1 in indices and 2 not in indices, f"pickup {tile:02X}"
        else:
            assert 1 not in indices, f"terrain {tile:02X}"
        rom[source:source + 16] = remapped

    bg0_color1 = BANK13 + (TITLE_PALETTE_SOURCE_ADDR - 0x4000) + 2
    rom[bg0_color1:bg0_color1 + 2] = STAGE1_PICKUP_GOLD.to_bytes(2, "little")
    print(
        "  Stage-1 pickup art: BG0[1]=gold; 73 pickup tiles reserve index 1; "
        "183 non-pickup tiles exclude it; later stages retain native BG0 "
        "(zero gameplay runtime cycles)"
    )


def main(
    palette_yaml: Path = PALETTE_YAML,
    output_path: Path = OUTPUT_PATH,
    base_output: Path | None = None,
    stage1_demo_wait_line: int = STAGE1_DEMO_WAIT_LINE,
    stock_tile_copy: bool = False,
    native_room_writers: bool = False,
    stock_vblank: bool = False,
    disabled_vblank_service: str | None = None,
    stock_oam_emitters: bool = False,
    minimal_prelude: bool = False,
    disable_lava_override: bool = False,
    buffered_stage1_attrs: bool = False,
    compact_tile_copy: bool = False,
    demo_compact_tile_copy: bool = False,
    semantic_stage1_prototype: bool = False,
    semantic_stage1_vblank_prototype: bool = False,
    reserved_pickup_gold: bool = False,
):
    death_late_fix_addr = DEATH_LATE_FIX_ADDR
    palette_yaml = Path(palette_yaml)
    output_path = Path(output_path)
    if base_output is None:
        base_output = (
            BASE_OUT
            if output_path == OUTPUT_PATH
            else output_path.with_name(output_path.stem + ".base.gb")
        )
    base_output = Path(base_output)

    # 1. Build base v3.01 production ROM
    build_v301(palette_yaml=palette_yaml, output_path=base_output)
    rom = bytearray(base_output.read_bytes())
    tuned_palettes = load_palettes_from_yaml(palette_yaml)
    cutscene_panels = load_cutscene_region_palettes(palette_yaml)
    (
        spotlight_map,
        spotlight_palette_slots,
        spotlight_resource_ids,
    ) = compile_spotlight_palette_map()
    stock_spotlight_resources = list(
        rom[
            SPOTLIGHT_ROSTER_TABLE_ADDR:
            SPOTLIGHT_ROSTER_TABLE_ADDR + SPOTLIGHT_ROSTER_SIZE
        ]
    )
    assert stock_spotlight_resources == spotlight_resource_ids, (
        "spotlight_palette_map.yaml resource IDs no longer match ROM 0x522A"
    )

    # v3.01 aliases BG7 to BG0 in its primary table to hide untouched CGB boot
    # attributes. Keep that proven title mask, store independently tuned YAML
    # BG7 in the free data slot at 0x68F8, and load the complete BG/OBJ set over
    # four bounded VBlanks whenever the palette-state hash changes.
    palette_source_off = BANK13 + (TITLE_PALETTE_SOURCE_ADDR - 0x4000)
    expected_bg0 = tuned_palettes["bg_data"][0:8]
    expected_bg7 = tuned_palettes["bg_data"][56:64]
    hazard_config = load_stage1_hazard_config()
    hazard_slot, hazard_bg7 = load_stage1_hazard_palette(palette_yaml)
    assert hazard_slot == hazard_config.tooth_palette == 7
    assert rom[palette_source_off:palette_source_off + 8] == expected_bg0
    assert rom[palette_source_off + 56:palette_source_off + 64] == expected_bg0
    tuned_bg7_off = BANK13 + (TUNED_BG7_SOURCE_ADDR - 0x4000)
    assert rom[tuned_bg7_off:tuned_bg7_off + 8] == bytes(8)
    rom[tuned_bg7_off:tuned_bg7_off + 8] = expected_bg7
    hazard_bg7_off = (
        BANK13 + (STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000)
    )
    assert rom[hazard_bg7_off:hazard_bg7_off + 8] == bytes(8), (
        "Stage-1 hazard palette source gap is no longer free"
    )
    rom[hazard_bg7_off:hazard_bg7_off + 8] = hazard_bg7
    (
        palette_loader,
        palette_loader_ext,
        palette_copy_cram8,
    ) = build_phased_palette_loader()
    assert len(palette_copy_cram8) == 7
    assert palette_copy_cram8[:1] == bytes([0xCD])
    assert palette_copy_cram8[3:4] == bytes([0xCD])
    assert palette_copy_cram8[1:3] == palette_copy_cram8[4:6]
    assert palette_copy_cram8[-1:] == bytes([0xC9])
    palette_loader_off = BANK13 + (PALETTE_LOADER_ADDR - 0x4000)
    rom[
        palette_loader_off:palette_loader_off + len(palette_loader)
    ] = palette_loader
    palette_loader_ext_off = (
        BANK13 + (PALETTE_LOADER_EXT_ADDR - 0x4000)
    )
    vanilla_rom = Path("rom/Penta Dragon (J).gb").read_bytes()
    hazard_art_stats = apply_stage1_hazard_variants(
        rom, vanilla_rom, hazard_config
    )
    print(
        "  Stage-1 rotating spike: "
        f"{hazard_art_stats['tiles']} YAML-owned art tiles, "
        f"{hazard_art_stats['changed_bytes']}/"
        f"{hazard_art_stats['raw_bytes']} bytes changed; "
        f"teeth use scene-local BG{hazard_slot}"
    )
    later_stage_bg0_repair = build_later_stage_bg0_repair()
    # The new palette loader retires the base build's old $69B8-$69CF tail.
    # Reuse that now-unreachable gap up to the fixed death-fade helper.
    assert (
        PALETTE_LOADER_ADDR + len(palette_loader)
        == LATER_STAGE_BG0_REPAIR_ADDR
    )
    later_stage_bg0_repair_off = (
        BANK13 + (LATER_STAGE_BG0_REPAIR_ADDR - 0x4000)
    )
    assert (
        LATER_STAGE_BG0_REPAIR_ADDR + len(later_stage_bg0_repair)
        <= DEATH_FADE_HELPER_ADDR
    )
    rom[
        later_stage_bg0_repair_off:
        later_stage_bg0_repair_off + len(later_stage_bg0_repair)
    ] = later_stage_bg0_repair

    # The stock item-menu entries enable the hardware Window and execute EI
    # before copying the prepared C4E0 HUD into its six visible rows.  Stock's
    # short VBlank normally hides that tiny ordering window; DX's additional
    # palette work can let an IRQ land there and expose the stale dungeon map
    # as lower-screen walls/gaps for a rendered frame.  Keep the same native
    # HUD builder/copier and byte budget, but publish the Window only after its
    # complete 6x20 tile map is ready.  The first entry has an extra stock
    # service call between enable and copy; retain it after publication.
    menu_setup = bytes.fromhex("F3 3E 07 E0 4B 3E 60 E0 4A")
    window_publish = bytes.fromhex("F0 40 CB EF E0 40 FB")
    hud_copy = bytes.fromhex("CD 0E 20")
    menu_entries = (
        (0x1B48, bytes.fromhex("CD E4 41")),
        (0x1D78, b""),
    )
    for address, middle_service in menu_entries:
        original = menu_setup + window_publish + middle_service + hud_copy
        reordered = menu_setup + middle_service + hud_copy + window_publish
        assert len(original) == len(reordered)
        assert rom[address:address + len(original)] == original, (
            f"native menu Window sequence moved at 0x{address:04X}"
        )
        rom[address:address + len(reordered)] = reordered

    # The interactive item menu loops back to the old $1D88 HUD-copy call
    # after input and item updates.  That call now begins at $1D81, followed
    # by the delayed Window publication. Retarget every native loop edge so
    # later redraws retain both operations instead of entering halfway through
    # the reordered sequence with a stale accumulator.
    menu_loop_entry = 0x1D81
    relative_menu_edges = (
        (0x1DC0, bytes.fromhex("28 C6")),
        (0x1DD9, bytes.fromhex("28 AD")),
    )
    for address, original in relative_menu_edges:
        assert rom[address:address + 2] == original
        displacement = menu_loop_entry - (address + 2)
        assert -128 <= displacement <= 127
        rom[address + 1] = displacement & 0xFF
    absolute_menu_edges = (
        (0x1DF3, 0xCA),
        (0x1E05, 0xC3),
        (0x1EBD, 0xC3),
        (0x1F5D, 0xC3),
    )
    for address, opcode in absolute_menu_edges:
        assert rom[address:address + 3] == bytes([opcode, 0x88, 0x1D])
        rom[address + 1:address + 3] = menu_loop_entry.to_bytes(2, "little")
    print("  item-menu publish order: native HUD copy precedes Window enable")

    assert rom[
        palette_loader_ext_off:
        palette_loader_ext_off + len(palette_loader_ext)
    ] == vanilla_rom[
        palette_loader_ext_off:
        palette_loader_ext_off + len(palette_loader_ext)
    ], "phased palette-loader extension region changed in the base build"
    rom[
        palette_loader_ext_off:
        palette_loader_ext_off + len(palette_loader_ext)
    ] = palette_loader_ext

    conditional_palette = build_conditional_palette_phased()
    spotlight_palette_loader = build_spotlight_palette_loader()
    conditional_palette_off = (
        BANK13 + (CONDITIONAL_PALETTE_ADDR - 0x4000)
    )
    rom[
        conditional_palette_off:conditional_palette_off + 3
    ] = bytes([
        0xC3,
        CONDITIONAL_PALETTE_IMPL_ADDR & 0xFF,
        CONDITIONAL_PALETTE_IMPL_ADDR >> 8,
    ])
    spotlight_palette_off = (
        BANK13 + (SPOTLIGHT_PALETTE_HELPER_ADDR - 0x4000)
    )
    rom[
        spotlight_palette_off:
        spotlight_palette_off + len(spotlight_palette_loader)
    ] = spotlight_palette_loader

    # The early wrapper call below is the sole gameplay phase service point.
    # Title actors load their own palette lazily only when the idle reel starts,
    # so the base handler's unconditional cold/menu call must be removed.
    colorize_off = BANK13 + (COLORIZE_ADDR - 0x4000)
    old_conditional_call = bytes([
        0xCD,
        CONDITIONAL_PALETTE_ADDR & 0xFF,
        CONDITIONAL_PALETTE_ADDR >> 8,
    ])
    colorize = rom[colorize_off:colorize_off + 0x80]
    call_offsets = [
        index
        for index in range(len(colorize) - 2)
        if colorize[index:index + 3] == old_conditional_call
    ]
    assert call_offsets == [0x2A], (
        f"base colorizer conditional call moved: {call_offsets}"
    )
    call_off = colorize_off + call_offsets[0]
    rom[call_off:call_off + 3] = bytes(3)
    print(
        "  palette round-trip: lazy title-actor OBJ load + one palette per "
        "CRAM-safe gameplay VBlank, "
        "title-safe BG7 alias "
        f"+ independent gameplay BG7 ({len(palette_loader)}+"
        f"{len(palette_loader_ext)} bytes)"
    )
    print(
        "  later-stage BG0: native ramp restored only after the slot-0 "
        f"palette phase ({len(later_stage_bg0_repair)} bytes at "
        f"bank13:0x{LATER_STAGE_BG0_REPAIR_ADDR:04X})"
    )

    # 2. Encode the exact release identity. This intentionally does not depend
    # on the current git tag: detached/debug tags must not rename the ROM.
    row17_text = TITLE_FOOTER
    row17_tiles = map_title_string_to_tiles(row17_text)
    assert len(row17_tiles) == 19
    print(f"  release footer: '{row17_text}'")

    # Construct title command list
    E = 0x9A
    def _txt(s):
        return [0x00 if c == ' ' else 0x80 + (ord(c) - 65) for c in s]
    JAM = [0xD0, 0xD7, 0xD8, 0xD9, 0x00, 0x89, 0x80, 0x8F, 0x80, 0x8D, 0x00,
           0x80, 0x91, 0x93, 0x00, 0x8C, 0x84, 0x83, 0x88, 0x80]

    title_list = bytes(
        [0x07, 0x03, 0xC1, 0xC2, 0xC3, 0xC4, 0xC5, E]          # logo row 0 (screen row 3)
        + [0x07, 0x04, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, E]        # logo row 1 (screen row 4)
        + [0x07, 0x05, 0xC6, 0xC7, 0xC8, 0xC9, 0xD6, E]        # logo row 2 (screen row 5)
        + [0x03, 0x06] + _txt("PENTA DRAGON DX") + [E]         # game name + DX (row 6 -> screen row 6)
        + [0x04, 0x08] + _txt("OPENING START") + [E]           # OPENING START (row 8 -> screen row 8)
        + [0x04, 0x0A] + _txt("GAME    START") + [E]           # GAME START (row 10 -> screen row 10)
        + [0x00, 0x0E, 0xC0, E]                                 # (c) symbol (row 14 -> screen row 14)
        + [0x00, 0x0F] + JAM + [E]                              # JAPAN ART MEDIA (row 15 -> screen row 15)
        + [0x00, 0x11] + row17_tiles + [E]                      # "DX V3.01 STRUK LABS"
        + [E]                                                   # Explicit list terminator 0x9A
    )
    assert len(title_list) <= 125, f"title list {len(title_list)} > 125 bytes"
    assert rom[0x4EA5:0x4EA7] == bytes([0x07, 0x03]), "title list head moved"
    rom[0x4EA5:0x4EA5 + len(title_list)] = title_list
    print(f"  title: PENTA DRAGON DX header + '{row17_text}' ({len(title_list)}/125 bytes @0x4EA5)")

    # 3. Store the period and native digit-9 restore tiles in the aligned gap
    # between bg_sweep and the RLE expander.
    glyph_blob = build_title_glyph_blob()
    assert len(glyph_blob) == 32
    assert TITLE_GLYPH_DATA_ADDR + len(glyph_blob) <= EXPAND_ADDR
    off = BANK13 + (TITLE_GLYPH_DATA_ADDR - 0x4000)
    assert rom[off:off + len(glyph_blob)] == bytes(len(glyph_blob)), \
        "title glyph data region is no longer free"
    rom[off:off + len(glyph_blob)] = glyph_blob
    print(f"  period + digit-9 restore: {len(glyph_blob)} bytes at bank13:0x{TITLE_GLYPH_DATA_ADDR:04X}")

    # 4. Store the glyph loader immediately after the RLE expander's reserved
    # range. A later boundary assertion verifies the generated expander fits.
    vram_copy_code = build_vram_glyph_copy(death_late_fix_addr)
    assert VRAM_GLYPH_COPY_ADDR + len(vram_copy_code) <= COLORIZE_ADDR
    off = BANK13 + (VRAM_GLYPH_COPY_ADDR - 0x4000)
    assert rom[off:off + len(vram_copy_code)] == bytes(len(vram_copy_code)), \
        "VRAM glyph-copy region is no longer free"
    rom[off:off + len(vram_copy_code)] = vram_copy_code
    print(f"  VRAM glyph loader: {len(vram_copy_code)} bytes at bank13:0x{VRAM_GLYPH_COPY_ADDR:04X}")

    # 5. Levelsel attr-clear stub
    ls = build_levelsel_attr_clear_stub()
    assert len(ls) <= LEVELSEL_STUB_MAX
    off = BANK13 + (LEVELSEL_STUB_ROM_ADDR - 0x4000)
    for i in range(LEVELSEL_STUB_MAX):
        assert rom[off + i] == 0x00, f"levelsel site not free at +{i}"
    rom[off:off + len(ls)] = ls
    print(f"  levelsel attr-clear stub: {len(ls)} bytes at bank13:0x{LEVELSEL_STUB_ROM_ADDR:04X}")

    # 6. Arena bg_tables (all 9 bosses)
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
    for i, (name, addr, _) in enumerate(arena_tables):
        expected = ARENA_BASE_ADDR + i * 0x100
        assert addr == expected
    for name, addr, build_fn in arena_tables:
        table = build_fn()
        assert len(table) == 256
        off = BANK13 + (addr - 0x4000)
        rom[off:off + 256] = table
        print(f"  {name:14s} bg_table: 256 bytes at bank13:0x{addr:04X}")

    # 7. Scene-detect routine
    sd = build_scene_detect(
        DUNGEON_TABLE_ADDR, ARENA_BASE_ADDR, SPLASH_TABLE_ADDR,
        title_addr=SPLASH_TABLE_ADDR,
        later_dungeon_addr=SPLASH_TABLE_ADDR,
        uniform_clear_addr=UNIFORM_CLEAR_ADDR,
        later_dungeon_service_addr=LATER_STAGE_BG0_ENTRY_ADDR,
        scene_change_service_addr=TITLE_TRANSITION_SERVICE_ADDR,
        cache_addr=SCENE_CACHE_ADDR,
        stage1_attr_cache_addrs=(
            STAGE1_ATTR_CACHE_9800_ADDR,
            STAGE1_ATTR_CACHE_9C00_ADDR,
        ),
    )
    assert SCENE_DETECT_ADDR + len(sd) <= DUNGEON_TABLE_ADDR
    off = BANK13 + (SCENE_DETECT_ADDR - 0x4000)
    rom[off:off + len(sd)] = sd
    print(f"  scene-detect: {len(sd)} bytes at bank13:0x{SCENE_DETECT_ADDR:04X}")

    # 8. Lava override
    lava = build_lava_override(
        LAVA_OVERRIDE_ADDR,
        room_sweep_count_addr=BG_SWEEP_COUNT_ADDR,
        room_attr_pending_addr=BG_SWEEP_ROOM_CACHE_ADDR,
    )
    off = BANK13 + (LAVA_OVERRIDE_ADDR - 0x4000)
    rom[off:off + len(lava)] = lava
    print(f"  lava override: {len(lava)} bytes at bank13:0x{LAVA_OVERRIDE_ADDR:04X}")

    # 9. Reclaim the literal 256-byte all-zero splash table. Scene detection
    # now tail-jumps to an exact WRAM zero-fill helper; the rest of this region
    # holds the bounded, guarded story/ending attribute sweep.
    (
        story_attr,
        story_dispatch,
        story_row_entry,
        story_column_resume,
    ) = build_story_attr_sweep()
    (
        story_region_bridge,
        story_region_bank6,
        story_region_stats,
    ) = build_story_region_classifier(cutscene_panels)
    (
        cutscene_palette_bridge,
        cutscene_palette_continuation,
    ) = build_cutscene_palette_bridge(story_dispatch)
    death_attr_service = build_death_attr_service(
        CUTSCENE_PALETTE_BRIDGE_ADDR
    )
    title_delay = build_title_delay()
    story_half_row = build_story_half_row_helper(story_row_entry)
    story_quarter = build_story_quarter_helper(story_row_entry)
    story_separator = build_story_separator_helper(story_row_entry)
    story_viewport_key = build_story_viewport_key_helper()
    ending_absolute_row = build_ending_absolute_row_helper(story_row_entry)
    story_column = build_story_column_helper(story_column_resume)
    story_inactive = build_story_inactive_helper()
    uniform_clear = build_uniform_bg_clear()
    assert STORY_ATTR_ADDR + len(story_attr) <= STORY_ATTR_REGION_END, \
        "story attr sweep overruns reclaimed zero-table region"
    assert (
        DEATH_ATTR_DISPATCH_ADDR + len(death_attr_service)
        <= PALETTE_LOADER_EXT_ADDR
    ), "death attr service collides with phased palette-loader extension"
    assert (
        TITLE_DELAY_ADDR + len(title_delay) <= LAVA_ATTR_ROOM_MATCH_ADDR
    ), "title-delay helper collides with lava room matcher"
    assert SCENE_DETECT_ADDR + len(sd) <= DUNGEON_TABLE_ADDR, \
        "scene detection collides with dungeon table"
    assert UNIFORM_CLEAR_ADDR + len(uniform_clear) <= WRAPPER_ADDR, \
        "uniform-table clear helper collides with VBlank wrapper"
    assert (
        STORY_HALF_ROW_HELPER_ADDR + len(story_half_row) <= EXPAND_ADDR
    ), "story half-row helper collides with RLE expander"
    assert (
        STORY_QUARTER_HELPER_ADDR + len(story_quarter) <= 0x6C10
    ), "story quarter helper collides with reserved tile data"
    assert (
        STORY_VIEWPORT_KEY_HELPER_ADDR + len(story_viewport_key)
        <= BG_SWEEP_ADDR
    ), "story viewport-key helper collides with BG sweep"
    assert (
        STORY_SEPARATOR_HELPER_ADDR + len(story_separator)
        <= ENDING_ABSOLUTE_ROW_HELPER_ADDR
    ), "story lower-panel helper collides with ending row helper"
    assert (
        ENDING_ABSOLUTE_ROW_HELPER_ADDR + len(ending_absolute_row)
        <= STORY_COLUMN_HELPER_ADDR
    ), "ending absolute-row helper collides with OBJ palette LUT"
    assert (
        STORY_COLUMN_HELPER_ADDR + len(story_column) <= OBJ_PAL_TABLE_ADDR
    ), "story viewport-column helper collides with OBJ palette LUT"
    assert (
        STORY_INACTIVE_HELPER_ADDR + len(story_inactive)
        <= VRAM_GLYPH_COPY_ADDR
    ), "story inactive helper collides with VRAM glyph loader"
    off = BANK13 + (SPLASH_TABLE_ADDR - 0x4000)
    vanilla = Path("rom/Penta Dragon (J).gb").read_bytes()
    assert rom[off:off + 0x100] == vanilla[off:off + 0x100], \
        "reclaimed bank-13 region changed in the base build"
    rom[off:off + 0x100] = bytes(0x100)
    rom[off:off + len(story_attr)] = story_attr
    story_region_bridge_off = (
        BANK13 + (STORY_REGION_BRIDGE_ADDR - 0x4000)
    )
    assert rom[
        story_region_bridge_off:
        story_region_bridge_off + len(story_region_bridge)
    ] == bytes(len(story_region_bridge)), (
        "bank-13 story-region bridge slot is no longer free"
    )
    story_region_bank6_off = (
        STORY_REGION_BANK * 0x4000
        + (STORY_REGION_CAVE_START_ADDR - 0x4000)
    )
    assert rom[
        story_region_bank6_off:
        story_region_bank6_off + len(story_region_bank6)
    ] == bytes(len(story_region_bank6)), (
        "bank-6 story-region classifier cave is no longer free"
    )
    rom[
        story_region_bridge_off:
        story_region_bridge_off + len(story_region_bridge)
    ] = story_region_bridge
    rom[
        story_region_bank6_off:
        story_region_bank6_off + len(story_region_bank6)
    ] = story_region_bank6
    story_half_off = BANK13 + (STORY_HALF_ROW_HELPER_ADDR - 0x4000)
    assert rom[
        story_half_off:story_half_off + len(story_half_row)
    ] == bytes(len(story_half_row)), \
        "story half-row helper slot is no longer free"
    rom[
        story_half_off:story_half_off + len(story_half_row)
    ] = story_half_row
    quarter_off = BANK13 + (STORY_QUARTER_HELPER_ADDR - 0x4000)
    assert rom[
        quarter_off:quarter_off + len(story_quarter)
    ] == bytes(len(story_quarter)), \
        "story quarter helper slot is no longer free"
    rom[quarter_off:quarter_off + len(story_quarter)] = story_quarter
    separator_off = BANK13 + (STORY_SEPARATOR_HELPER_ADDR - 0x4000)
    assert rom[
        separator_off:separator_off + len(story_separator)
    ] == bytes(len(story_separator)), \
        "story separator helper slot is no longer free"
    rom[
        separator_off:separator_off + len(story_separator)
    ] = story_separator
    viewport_key_off = (
        BANK13 + (STORY_VIEWPORT_KEY_HELPER_ADDR - 0x4000)
    )
    assert rom[
        viewport_key_off:viewport_key_off + len(story_viewport_key)
    ] == bytes(len(story_viewport_key)), \
        "story viewport-key helper slot is no longer free"
    rom[
        viewport_key_off:viewport_key_off + len(story_viewport_key)
    ] = story_viewport_key
    ending_row_off = BANK13 + (ENDING_ABSOLUTE_ROW_HELPER_ADDR - 0x4000)
    assert rom[
        ending_row_off:ending_row_off + len(ending_absolute_row)
    ] == bytes(len(ending_absolute_row)), \
        "ending absolute-row helper slot is no longer free"
    rom[
        ending_row_off:ending_row_off + len(ending_absolute_row)
    ] = ending_absolute_row
    column_off = BANK13 + (STORY_COLUMN_HELPER_ADDR - 0x4000)
    assert rom[
        column_off:column_off + len(story_column)
    ] == bytes(len(story_column)), \
        "story viewport-column helper slot is no longer free"
    rom[column_off:column_off + len(story_column)] = story_column
    inactive_off = BANK13 + (STORY_INACTIVE_HELPER_ADDR - 0x4000)
    expected_retired_gdma_tail = bytes.fromhex(
        "3E 0F E0 55 FB AF E0 4F"
    )
    assert rom[
        inactive_off:inactive_off + len(story_inactive)
    ] == expected_retired_gdma_tail, \
        "retired base-GDMA tail changed at story inactive helper slot"
    rom[
        inactive_off:inactive_off + len(story_inactive)
    ] = story_inactive
    clear_off = BANK13 + (UNIFORM_CLEAR_ADDR - 0x4000)
    expected_base_wrapper_prefix = bytes(len(uniform_clear))
    assert rom[
        clear_off:clear_off + len(uniform_clear)
    ] == expected_base_wrapper_prefix, \
        "retired sweep gap changed at uniform clear helper slot"
    rom[clear_off:clear_off + len(uniform_clear)] = uniform_clear
    print(
        f"  story/ending attr sweep: {len(story_attr)} bytes at "
        f"bank13:0x{STORY_ATTR_ADDR:04X}"
    )
    print(
        "  YAML story regions: "
        f"{story_region_stats['art_ids']} art IDs / "
        f"{story_region_stats['unique_panels']} masks / "
        f"{story_region_stats['rectangles']} rectangles; "
        f"{story_region_stats['unique_rows']} rows / "
        f"{story_region_stats['row_runs']} runs / "
        f"{story_region_stats['data_bytes']} data bytes; "
        f"bridge={len(story_region_bridge)} bytes at "
        f"bank13:0x{STORY_REGION_BRIDGE_ADDR:04X}, "
        f"writer={story_region_stats['writer_bytes']} bytes, "
        f"row-writer={story_region_stats['row_writer_bytes']} bytes at "
        f"bank6:0x{STORY_REGION_CAVE_START_ADDR:04X}"
    )
    print(
        f"  story row dispatcher: {len(story_half_row)} bytes at "
        f"bank13:0x{STORY_HALF_ROW_HELPER_ADDR:04X}"
    )
    print(
        f"  story quarter helper: {len(story_quarter)} bytes at "
        f"bank13:0x{STORY_QUARTER_HELPER_ADDR:04X}"
    )
    print(
        f"  story separator helper: {len(story_separator)} bytes at "
        f"bank13:0x{STORY_SEPARATOR_HELPER_ADDR:04X}"
    )
    print(
        f"  story viewport-key helper: {len(story_viewport_key)} bytes at "
        f"bank13:0x{STORY_VIEWPORT_KEY_HELPER_ADDR:04X}"
    )
    print(
        f"  ending absolute-row helper: {len(ending_absolute_row)} bytes at "
        f"bank13:0x{ENDING_ABSOLUTE_ROW_HELPER_ADDR:04X}"
    )
    print(
        f"  story viewport-column helper: {len(story_column)} bytes at "
        f"bank13:0x{STORY_COLUMN_HELPER_ADDR:04X}"
    )
    print(
        f"  story inactive/cache clear: {len(story_inactive)} bytes at "
        f"bank13:0x{STORY_INACTIVE_HELPER_ADDR:04X}"
    )
    print(
        f"  uniform all-pal0 clear: {len(uniform_clear)} bytes at "
        f"bank13:0x{UNIFORM_CLEAR_ADDR:04X}"
    )

    # 10. Validate the generated OBJ assignments, then reclaim the dead LUT
    # page for the dispatcher. The real title spotlight reuses tiles $08-$0F
    # for all 38 actors, so tile identity cannot select a palette. Its stable
    # FFF2 roster ID indexes the packed map compiled from the exact matching
    # gameplay graphics block and monster_palette_map.yaml.
    _obj_pal = bytearray(build_obj_pal_table())
    assert len(_obj_pal) == 256
    _obj_pal_off = BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)
    _vb = sum(1 for _v in _obj_pal if _v > 7 and _v != 0xFF)
    assert _vb == 0
    rom[_obj_pal_off:_obj_pal_off + 0x100] = bytes(0x100)

    # 10b. Retire the all-40-slot gameplay VBlank scan. Palette assignment is
    # installed at the stock semantic emitters below; the separate title
    # spotlight dispatcher still updates its four exact next-DMA slots. The
    # old tile-colorizer tail through $6A6F is reachable only from that retired
    # scan, so reclaim its final 16 bytes for the fade-aware title repair.
    shadow_off = BANK13 + (BASE_SHADOW_MAIN_ADDR - 0x4000)
    rom[
        shadow_off:
        BANK13 + (0x6A70 - 0x4000)
    ] = bytes(0x6A70 - BASE_SHADOW_MAIN_ADDR)
    print("  gameplay OBJ VBlank scan: retired")

    attract_obj = build_attract_obj_colorizer(
        stage1_semantic_vblank=False,
    )
    death_late_fix = build_death_late_fix()
    title_transition = build_title_transition_service()
    stale_window_cleanup = build_stale_window_cleanup()
    title_palette_copy = build_title_palette_copy_helper()
    assert (
        ATTRACT_OBJ_COLORIZER_ADDR + len(attract_obj)
        <= death_late_fix_addr
    )
    assert (
        death_late_fix_addr + len(death_late_fix)
        <= CONDITIONAL_PALETTE_IMPL_ADDR
    )
    assert (
        ROOM_BG_REPAIR_ADDR + len(
            build_room_bg_repair(
                stage1_atomic_attrs=(not stock_tile_copy or native_room_writers)
            )
        )
        <= CONDITIONAL_PALETTE_IMPL_ADDR
    )
    assert (
        CONDITIONAL_PALETTE_IMPL_ADDR + len(conditional_palette)
        <= SPOTLIGHT_PALETTE_MAP_ADDR
    )
    off = BANK13 + (ATTRACT_OBJ_COLORIZER_ADDR - 0x4000)
    rom[off:off + len(attract_obj)] = attract_obj
    death_late_off = BANK13 + (death_late_fix_addr - 0x4000)
    rom[
        death_late_off:death_late_off + len(death_late_fix)
    ] = death_late_fix
    transition_off = (
        BANK13 + (TITLE_TRANSITION_SERVICE_ADDR - 0x4000)
    )
    rom[
        transition_off:transition_off + len(title_transition)
    ] = title_transition
    stale_window_off = (
        BANK13 + (STALE_WINDOW_CLEANUP_ADDR - 0x4000)
    )
    assert (
        STALE_WINDOW_CLEANUP_ADDR + len(stale_window_cleanup)
        <= TITLE_PALETTE_FIX_ADDR
    )
    assert rom[
        stale_window_off:stale_window_off + len(stale_window_cleanup)
    ] == bytes(len(stale_window_cleanup)), (
        "stale-Window cleanup slot is no longer free"
    )
    rom[
        stale_window_off:stale_window_off + len(stale_window_cleanup)
    ] = stale_window_cleanup
    title_palette_copy_off = (
        BANK13 + (TITLE_PALETTE_COPY_HELPER_ADDR - 0x4000)
    )
    assert (
        STALE_WINDOW_CLEANUP_ADDR + len(stale_window_cleanup)
        == TITLE_PALETTE_COPY_HELPER_ADDR
    )
    assert (
        TITLE_PALETTE_COPY_HELPER_ADDR + len(title_palette_copy)
        <= TITLE_PALETTE_FIX_ADDR
    )
    assert rom[
        title_palette_copy_off:
        title_palette_copy_off + len(title_palette_copy)
    ] == bytes(len(title_palette_copy)), (
        "title palette copier slot is no longer free"
    )
    rom[
        title_palette_copy_off:
        title_palette_copy_off + len(title_palette_copy)
    ] = title_palette_copy
    conditional_impl_off = (
        BANK13 + (CONDITIONAL_PALETTE_IMPL_ADDR - 0x4000)
    )
    rom[
        conditional_impl_off:
        conditional_impl_off + len(conditional_palette)
    ] = conditional_palette
    map_off = BANK13 + (SPOTLIGHT_PALETTE_MAP_ADDR - 0x4000)
    rom[map_off:map_off + len(spotlight_map)] = spotlight_map
    print(
        f"  title spotlight/gameplay OAM dispatch: {len(attract_obj)} bytes at "
        f"bank13:0x{ATTRACT_OBJ_COLORIZER_ADDR:04X}"
    )
    print(
        f"  death wrapper-tail containment: {len(death_late_fix)} bytes at "
        f"bank13:0x{death_late_fix_addr:04X}"
    )
    print(
        f"  title transition service: {len(title_transition)} bytes at "
        f"bank13:0x{TITLE_TRANSITION_SERVICE_ADDR:04X}"
    )
    print(
        f"  stale gameplay Window cleanup: {len(stale_window_cleanup)} bytes "
        f"at bank13:0x{STALE_WINDOW_CLEANUP_ADDR:04X}"
    )
    print(
        "  idle-throttled palette service: "
        f"{len(conditional_palette)} bytes at "
        f"bank13:0x{CONDITIONAL_PALETTE_IMPL_ADDR:04X} "
        f"(trampoline ${CONDITIONAL_PALETTE_ADDR:04X})"
    )
    print(
        "  spotlight identity map: all 38 FFF2 roster entries -> "
        "gameplay YAML OBJ families "
        f"({len(spotlight_map)} packed bytes at "
        f"bank13:0x{SPOTLIGHT_PALETTE_MAP_ADDR:04X}; "
        f"slots={spotlight_palette_slots})"
    )

    # Replace the whole FFC1-gated BG/OAM tail with one dispatcher call. The
    # dispatcher preserves the old active-gameplay sequence, while also
    # servicing cold-title D880=$1B where FFC1 is zero.
    colorize_off = BANK13 + (COLORIZE_ADDR - 0x4000)
    colorize = rom[colorize_off:colorize_off + 0x80]
    old_pipeline = bytes([
        0xF0, 0xC1, 0xB7, 0x28, 0x09,
        0xCD, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
        0xCD, BASE_SHADOW_MAIN_ADDR & 0xFF, BASE_SHADOW_MAIN_ADDR >> 8,
        0xCD, 0x80, 0xFF,
    ])
    matches = [
        index for index in range(len(colorize) - len(old_pipeline) + 1)
        if colorize[index:index + len(old_pipeline)] == old_pipeline
    ]
    assert len(matches) == 1, f"expected one BG/OAM pipeline, found {matches}"
    patch_at = colorize_off + matches[0]
    rom[patch_at:patch_at + len(old_pipeline)] = bytes([
        0xCD,
        ATTRACT_OBJ_COLORIZER_ADDR & 0xFF,
        ATTRACT_OBJ_COLORIZER_ADDR >> 8,
    ]) + bytes(len(old_pipeline) - 3)
    print(
        f"  colorize BG/OAM pipeline -> ${ATTRACT_OBJ_COLORIZER_ADDR:04X}"
    )

    # 11. Re-patch bg_sweep to read the per-scene WRAM palette LUT, including
    # title. The title-safe inline hook avoids the input corruption; this
    # sweep is still required to replace all-white boot attributes.
    sweep = bytearray(
        create_bg_sweep_viewport_gated(WRAM_BG_TABLE, BG_SWEEP_ADDR)
    )
    assert sweep[:4] == bytearray([0xF0, 0xC1, 0xB7, 0xC8])
    sweep[0:4] = bytearray([0x00, 0x00, 0x00, 0x00])
    assert BG_SWEEP_ADDR + len(sweep) <= UNIFORM_CLEAR_ADDR, (
        "bg_sweep collides with uniform clear"
    )
    off = BANK13 + (BG_SWEEP_ADDR - 0x4000)
    rom[off:off + len(sweep)] = sweep
    print(
        f"  bg_sweep: WRAM 0x{WRAM_BG_TABLE:04X}, title-enabled "
        f"({len(sweep)} bytes)"
    )

    # 12. The retired position-sweep RLE and pointer table had no production
    # reader. Reclaim them for the room-aware bounded attribute repair and the
    # shared seven-byte LCD-safe CRAM copier.
    posmap_off = BANK13 + (POSMAP_DATA_ADDR - 0x4000)
    rom[posmap_off:posmap_off + (0x7E00 - POSMAP_DATA_ADDR)] = bytes(
        0x7E00 - POSMAP_DATA_ADDR
    )
    ptr_off = BANK13 + (POSMAP_PTR_TABLE - 0x4000)
    rom[ptr_off:ptr_off + 18] = bytes(18)
    rom[
        ptr_off:ptr_off + len(palette_copy_cram8)
    ] = palette_copy_cram8
    print(
        "  Stage-1 BG7 selector: inline cycle-neutral title / normal YAML / "
        "hazard YAML; shared LCD-safe copier "
        f"({len(palette_copy_cram8)}/18 bytes at "
        f"bank13:0x{PALETTE_COPY_CRAM8_ADDR:04X})"
    )
    room_bg_repair = build_room_bg_repair(
        stage1_atomic_attrs=(not stock_tile_copy or native_room_writers)
    )
    death_fade_helper = build_death_fade_helper()
    lava_attr_stage5_signature = build_lava_attr_sample_signature(
        LAVA_ATTR_STAGE5_SAMPLES,
        LAVA_ATTR_STAGE5_SIGNATURE_ADDR,
        LAVA_ATTR_STAGE7_SOURCE_B_ADDR,
    )
    lava_attr_room_match = build_lava_attr_room_match()
    lava_attr_stage7_runtime = build_lava_attr_stage7_runtime()
    lava_stage7_first_capacity = (
        OAM_FREE_EMITTER_ADDR - LAVA_ATTR_STAGE7_SOURCE_A_ADDR
    )
    lava_attr_stage7_source_a = lava_attr_stage7_runtime[
        :lava_stage7_first_capacity
    ]
    lava_attr_stage7_source_b = lava_attr_stage7_runtime[
        lava_stage7_first_capacity:
    ]
    assert (
        ROOM_BG_REPAIR_ADDR + len(room_bg_repair)
        <= CONDITIONAL_PALETTE_IMPL_ADDR
    ), "room BG repair exceeds the retired gameplay-scan cave"
    assert (
        DEATH_FADE_HELPER_ADDR + len(death_fade_helper)
        <= TILE_COLORIZER_ADDR
    )
    assert (
        DEATH_FADE_WHITE_ADDR + len(DEATH_FADE_WHITE)
        <= LAVA_ATTR_STAGE7_SOURCE_B_ADDR
    )
    assert (
        LAVA_ATTR_STAGE7_SOURCE_B_ADDR + len(lava_attr_stage7_source_b)
        <= OAM_WRAM_COPY_ADDR
    )
    lava_attr_stage5_front, lava_attr_decider_cont = build_lava_attr_decider()
    stage1_hazard_dispatcher = build_stage1_hazard_dispatcher()
    (
        stage1_hazard_row_helper,
        stage1_hazard_row_compiler,
    ) = build_stage1_hazard_row_helper()
    (
        demo_pickup_scanner,
        demo_pickup_appender,
        demo_pickup_table,
    ) = build_demo_pickup_scanner()
    (
        demo_pickup_writer,
        demo_pickup_writer_tail,
    ) = build_demo_pickup_writer()
    semantic_helpers = (
        (
            OAM_PALETTE_RESOLVER_ADDR,
            build_oam_palette_resolver() + build_stage1_atomic_setup(),
        ),
        (OAM_BOSS_LUT_SERVICE_ADDR, build_oam_boss_lut_service()),
        (OAM_CENTRAL_EMITTER_ADDR, build_oam_central_emitter()),
        (OAM_FREE_EMITTER_ADDR, build_oam_free_emitter()),
        (OAM_WRAM_COPY_ADDR, build_oam_wram_copy()),
        (TITLE_TRANSITION_SERVICE_ADDR, title_transition),
        (NATIVE_GLYPH_RESTORE_ADDR, build_native_glyph_restore()),
        (OAM_LUT_INIT_ADDR, build_oam_lut_init()),
    )
    room_bg_repair_off = BANK13 + (ROOM_BG_REPAIR_ADDR - 0x4000)
    rom[
        room_bg_repair_off:
        room_bg_repair_off + len(room_bg_repair)
    ] = room_bg_repair
    death_fade_helper_off = (
        BANK13 + (DEATH_FADE_HELPER_ADDR - 0x4000)
    )
    rom[
        death_fade_helper_off:
        death_fade_helper_off + len(death_fade_helper)
    ] = death_fade_helper
    assert (
        OAM_FREE_EMITTER_ADDR + len(semantic_helpers[3][1])
        <= LAVA_ATTR_STAGE5_SIGNATURE_ADDR
    )
    for index, (addr, code) in enumerate(semantic_helpers):
        next_addr = (
            semantic_helpers[index + 1][0]
            if index + 1 < len(semantic_helpers)
            else 0x7E00
        )
        assert addr + len(code) <= next_addr
        off = BANK13 + (addr - 0x4000)
        rom[off:off + len(code)] = code

    attract_pickup_helpers = (
        (
            ATTRACT_PICKUP_SWEEP_HELPER_ADDR,
            build_attract_pickup_sweep_helper(),
        ),
        (
            ATTRACT_PICKUP_SWEEP_STUB_ADDR,
            build_attract_pickup_sweep_dispatcher(),
        ),
    )
    for addr, code in attract_pickup_helpers:
        off = BANK13 + (addr - 0x4000)
        assert rom[off:off + len(code)] == bytes(len(code)), (
            f"attract pickup helper slot at ${addr:04X} is no longer free: "
            f"{rom[off:off + len(code)].hex()}"
        )
        rom[off:off + len(code)] = code
    lava_stage5_signature_off = (
        BANK13 + (LAVA_ATTR_STAGE5_SIGNATURE_ADDR - 0x4000)
    )
    rom[
        lava_stage5_signature_off:
        lava_stage5_signature_off + len(lava_attr_stage5_signature)
    ] = lava_attr_stage5_signature
    for address, palette in (
        (DEATH_FADE_NORMAL_ADDR, DEATH_FADE_NORMAL),
        (DEATH_FADE_INTERMEDIATE_ADDR, DEATH_FADE_INTERMEDIATE),
        (DEATH_FADE_WHITE_ADDR, DEATH_FADE_WHITE),
    ):
        palette_off = BANK13 + (address - 0x4000)
        rom[palette_off:palette_off + len(palette)] = palette
    lava_room_match_off = BANK13 + (LAVA_ATTR_ROOM_MATCH_ADDR - 0x4000)
    rom[
        lava_room_match_off:
        lava_room_match_off + len(lava_attr_room_match)
    ] = lava_attr_room_match
    lava_stage7_source_a_off = (
        BANK13 + (LAVA_ATTR_STAGE7_SOURCE_A_ADDR - 0x4000)
    )
    rom[
        lava_stage7_source_a_off:
        lava_stage7_source_a_off + len(lava_attr_stage7_source_a)
    ] = lava_attr_stage7_source_a
    lava_stage7_source_b_off = (
        BANK13 + (LAVA_ATTR_STAGE7_SOURCE_B_ADDR - 0x4000)
    )
    rom[
        lava_stage7_source_b_off:
        lava_stage7_source_b_off + len(lava_attr_stage7_source_b)
    ] = lava_attr_stage7_source_b
    lava_stage5_front_off = (
        BANK13 + (LAVA_ATTR_STAGE5_FRONT_ADDR - 0x4000)
    )
    assert rom[
        lava_stage5_front_off:
        lava_stage5_front_off + len(lava_attr_stage5_front)
    ] == bytes(len(lava_attr_stage5_front)), (
        "relocated Stage-5 front cave is no longer free"
    )
    rom[
        lava_stage5_front_off:
        lava_stage5_front_off + len(lava_attr_stage5_front)
    ] = lava_attr_stage5_front
    lava_decider_off = BANK13 + (LAVA_ATTR_DECIDER_ADDR - 0x4000)
    rom[
        lava_decider_off:lava_decider_off + len(stage1_hazard_dispatcher)
    ] = stage1_hazard_dispatcher
    lava_decider_cont_off = (
        BANK13 + (LAVA_ATTR_DECIDER_CONT_ADDR - 0x4000)
    )
    rom[
        lava_decider_cont_off:
        lava_decider_cont_off + len(lava_attr_decider_cont)
    ] = lava_attr_decider_cont
    stage1_hazard_helper_off = (
        BANK14 + (STAGE1_HAZARD_ROW_HELPER_ADDR - 0x4000)
    )
    assert rom[
        stage1_hazard_helper_off:
        stage1_hazard_helper_off + len(stage1_hazard_row_helper)
    ] == bytes(len(stage1_hazard_row_helper)), (
        "Stage-1 animation helper cave is no longer free"
    )
    rom[
        stage1_hazard_helper_off:
        stage1_hazard_helper_off + len(stage1_hazard_row_helper)
    ] = stage1_hazard_row_helper
    stage1_hazard_compiler_off = (
        BANK14 + (STAGE1_HAZARD_ROW_COMPILER_ADDR - 0x4000)
    )
    assert rom[
        stage1_hazard_compiler_off:
        stage1_hazard_compiler_off + len(stage1_hazard_row_compiler)
    ] == bytes(len(stage1_hazard_row_compiler)), (
        "Stage-1 animation row-compiler cave is no longer free"
    )
    rom[
        stage1_hazard_compiler_off:
        stage1_hazard_compiler_off + len(stage1_hazard_row_compiler)
    ] = stage1_hazard_row_compiler
    demo_pickup_bank14 = (
        (DEMO_PICKUP_DIRECT_WRITER_ADDR, demo_pickup_writer),
        (DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR, demo_pickup_writer_tail),
        (DEMO_PICKUP_TABLE_ADDR, demo_pickup_table),
        (DEMO_PICKUP_SCANNER_ADDR, demo_pickup_scanner),
        (DEMO_PICKUP_APPENDER_ADDR, demo_pickup_appender),
    )
    for addr, code in demo_pickup_bank14:
        off = BANK14 + (addr - 0x4000)
        assert rom[off:off + len(code)] == bytes(len(code)), (
            f"demo pickup scanner slot at ${addr:04X} is no longer free"
        )
        rom[off:off + len(code)] = code
    install_semantic_oam_intercepts(rom)
    print(
        "  semantic gameplay OBJ emitters: "
        f"resolver={len(semantic_helpers[0][1])}, "
        f"boss_lut={len(semantic_helpers[1][1])}, "
        f"central_fused={len(semantic_helpers[2][1])}, "
        f"free={len(semantic_helpers[3][1])} bytes"
    )
    print(
        f"  room-aware bounded BG repair: {len(room_bg_repair)} bytes at "
        f"bank13:0x{ROOM_BG_REPAIR_ADDR:04X}"
    )
    print(
        "  prerecorded Stage-1 pickups: cached native-expander sparse stamp "
        f"({len(demo_pickup_scanner)}+{len(demo_pickup_appender)} scanner, "
        f"{len(demo_pickup_writer)}+{len(demo_pickup_writer_tail)} dual-map "
        "HBlank writer bytes in bank14)"
    )
    print(
        f"  CGB GAME OVER fade: helper={len(death_fade_helper)} bytes at "
        f"bank13:0x{DEATH_FADE_HELPER_ADDR:04X}, tables=24 bytes at "
        f"bank13:0x{DEATH_FADE_NORMAL_ADDR:04X}"
    )
    print(
        "  lava palette-map signatures: "
        f"stage5={len(lava_attr_stage5_signature)} bytes at "
        f"bank13:0x{LAVA_ATTR_STAGE5_SIGNATURE_ADDR:04X}, "
        f"room_match={len(lava_attr_room_match)} bytes at "
        f"bank13:0x{LAVA_ATTR_ROOM_MATCH_ADDR:04X}, "
        f"stage7_runtime={len(lava_attr_stage7_runtime)} bytes from "
        f"bank13:0x{LAVA_ATTR_STAGE7_SOURCE_A_ADDR:04X}/"
        f"0x{LAVA_ATTR_STAGE7_SOURCE_B_ADDR:04X} to "
        f"WRAM 0x{LAVA_ATTR_STAGE7_RUNTIME_ADDR:04X}, "
        f"dispatcher/stage5={len(stage1_hazard_dispatcher)}+"
        f"{len(lava_attr_stage5_front)}+{len(lava_attr_decider_cont)} bytes at "
        f"bank13:0x{LAVA_ATTR_DECIDER_ADDR:04X}/"
        f"0x{LAVA_ATTR_STAGE5_FRONT_ADDR:04X}/"
        f"0x{LAVA_ATTR_DECIDER_CONT_ADDR:04X}; "
        f"Stage-1 selective hazard-row publisher="
        f"{len(stage1_hazard_row_helper)}+"
        f"{len(stage1_hazard_row_compiler)} bytes at "
        f"bank14:0x{STAGE1_HAZARD_ROW_HELPER_ADDR:04X}/"
        f"0x{STAGE1_HAZARD_ROW_COMPILER_ADDR:04X}"
    )
    print(
        "  hot OBJ WRAM copy: "
        f"{len(semantic_helpers[4][1])} bytes at "
        f"bank13:0x{OAM_WRAM_COPY_ADDR:04X} -> WRAM 0x{OAM_WRAM_BASE:04X}"
    )
    print(
        "  transition-only native glyph restore: "
        f"transition={len(semantic_helpers[5][1])}, "
        f"native_restore={len(semantic_helpers[6][1])} bytes"
    )
    print(
        "  YAML OBJ LUT initializer: "
        f"{len(semantic_helpers[7][1])} bytes at "
        f"bank13:0x{OAM_LUT_INIT_ADDR:04X} -> "
        f"WRAM 0x{OAM_PALETTE_LUT_WRAM:04X}"
    )

    # RLE expander
    expander = create_rle_expander()
    assert EXPAND_ADDR + len(expander) <= VRAM_GLYPH_COPY_ADDR, \
        "RLE expander collides with VRAM glyph loader"
    off = BANK13 + (EXPAND_ADDR - 0x4000)
    rom[off:off + len(expander)] = expander
    print(f"  RLE expander: {len(expander)} bytes at bank13:0x{EXPAND_ADDR:04X}")

    # The production colorizer never called the retired position-sweep blob.
    # Its free $7100-$719F range now hosts the story-entry dispatcher and the
    # bounded two-map death/game-over neutralizer.
    off = BANK13 + (DEATH_ATTR_DISPATCH_ADDR - 0x4000)
    rom[off:off + len(death_attr_service)] = death_attr_service
    title_delay_off = BANK13 + (TITLE_DELAY_ADDR - 0x4000)
    rom[title_delay_off:title_delay_off + len(title_delay)] = title_delay
    print(
        f"  death/game-over attr service: {len(death_attr_service)} bytes "
        f"at bank13:0x{DEATH_ATTR_DISPATCH_ADDR:04X}"
    )
    print(
        f"  title cadence helper: {len(title_delay)} bytes at "
        f"bank13:0x{TITLE_DELAY_ADDR:04X}"
    )

    # 13. INLINE HOOK: unchanged Stage 1 maps keep the native four-tiles-per-
    # HBlank cadence. A room-signature change takes the vertically safe
    # three-tile atomic path exactly once per destination map. Rotating hazards
    # are handled by the selective post-expander service, so their animation
    # never replays an expensive whole-map atomic copy.
    if buffered_stage1_attrs:
        assert (
            not stock_tile_copy
            and not compact_tile_copy
            and not semantic_stage1_prototype
            and not semantic_stage1_vblank_prototype
        ), (
            "buffered Stage-1 attrs and the tile-copy isolation flags are "
            "mutually exclusive"
        )
        # RST $30 is title-family drawing only; live room publishers enter the
        # shared copier at $42A7 after selecting H themselves. Keep the title
        # vector on its byte-exact tail and use the fixed cave solely for the
        # tiny DMA register helper.
        gdma_helper_addr = INLINE_ATTR_DECISION_HELPER_ADDR
        inline_blob = create_inline_tile_copy_stage1_double_buffered_attrs(
            0,
            gdma_helper_addr,
            always_stage1=True,
        )
        atomic_row_addr = 0
        print(
            "  diagnostic isolation: double-buffered Stage-1 tile/attr GDMA"
        )
    else:
        inline_blob = create_inline_tile_copy_stage1_precomputed_attrs(
            INLINE_ATTR_DECISION_HELPER_ADDR + 3,
            STAGE1_ATOMIC_SETUP_ADDR,
            STAGE1_ATOMIC_WRAP_ADDR,
            atomic_group_width=STAGE1_ATOMIC_GROUP_WIDTH,
        )
        # INC BC / DEC BC is register-neutral but deliberately retained: the
        # 16-cycle phase pair aligns every later HBlank commit. Removing it
        # reproduced transient walls/voids in the 20,000-frame Stage-1 copy
        # receipt even though the packed source itself remained byte-stable.
        assert inline_blob[:7] == bytes.fromhex("2E 00 03 0B 16 DF CD")
        atomic_row_marker = bytes([
            0x06, WRAM_BG_TABLE >> 8,
            0x3E,
            24 // STAGE1_ATOMIC_GROUP_WIDTH,
            0xE0, 0xE0,
        ])
        atomic_row_offsets = [
            index
            for index in range(len(inline_blob) - len(atomic_row_marker) + 1)
            if inline_blob[index:index + len(atomic_row_marker)] == atomic_row_marker
        ]
        assert len(atomic_row_offsets) == 1
        atomic_row_addr = 0x42A7 + atomic_row_offsets[0]
        # Locate the fixed pure-copy branch target. No extra gate is required:
        # the completed-source hook updates only hazard rows, and the ordinary
        # pure copier immediately republishes their identical tile IDs.
        pure_setup_marker = bytes.fromhex("11 A0 C1 3E 18 F5 0E 06")
        pure_setup_offsets = [
            index
            for index in range(len(inline_blob) - len(pure_setup_marker) + 1)
            if inline_blob[
                index:index + len(pure_setup_marker)
            ] == pure_setup_marker
        ]
        assert len(pure_setup_offsets) == 1
        fast_phase_gate = bytes()
        pure_setup_offset = pure_setup_offsets[0]
        inline_blob = (
            inline_blob[:pure_setup_offset]
            + fast_phase_gate
            + inline_blob[pure_setup_offset:]
        )
    inline_attr_decision = build_inline_attr_decision_helper(atomic_row_addr)
    stage1_atomic_wrap = build_stage1_atomic_wrap()
    available = 0x436D - 0x42A7 + 1
    assert len(inline_blob) <= available
    if buffered_stage1_attrs:
        title_pure_entry = 0x42A7 + len(inline_blob) - 11
        assert inline_blob[-11:-4] == bytes([
            0x26, 0x98, 0xAF, 0x6F, 0xCD,
            (gdma_helper_addr + 13) & 0xFF,
            (gdma_helper_addr + 13) >> 8,
        ])
    else:
        title_pure_entry = 0x42A7 + len(inline_blob) - 10
        assert inline_blob[-10:-3] == bytes.fromhex(
            "26 98 AF 6F CD 82 34"
        )
    inline_padding = bytes(available - len(inline_blob))
    rom[0x42A7:0x436E] = inline_blob + inline_padding
    assert 0x42A7 + len(inline_blob) <= 0x436E
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])
    assert rom[0x0030:0x0033] == bytes.fromhex("C3 A5 42")
    assert STAGE1_ATOMIC_WRAP_ADDR + len(stage1_atomic_wrap) <= 0x34A3
    assert rom[
        INLINE_ATTR_DECISION_HELPER_ADDR:0x34A3
    ] == bytes(0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR)
    if buffered_stage1_attrs:
        title_delay = bytes.fromhex("00 00 00 00 18 00 C9")
        fixed_inline_helpers = (
            build_stage1_gdma_register_helper() + title_delay
        )
        assert len(fixed_inline_helpers) == 20
        rom[0x0030:0x0033] = bytes([
            0xC3, title_pure_entry & 0xFF, title_pure_entry >> 8,
        ])
    else:
        fixed_inline_helpers = (
            inline_attr_decision
            + stage1_atomic_wrap
        )
        rom[0x0030:0x0033] = bytes([
            0xC3, title_pure_entry & 0xFF, title_pure_entry >> 8,
        ])
    assert len(fixed_inline_helpers) <= 0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR
    rom[INLINE_ATTR_DECISION_HELPER_ADDR:0x34A3] = (
        fixed_inline_helpers
        + bytes(0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR - len(fixed_inline_helpers))
    )
    if (
        stock_tile_copy
        or compact_tile_copy
        or semantic_stage1_prototype
        or semantic_stage1_vblank_prototype
    ):
        # Diagnostic escape hatch: preserve every other DX subsystem while
        # restoring the stock 24x24 tile copier and its RST $30 entry. This is
        # intentionally selectable so terrain regressions can be attributed
        # independently of palette/OAM/title work.
        if compact_tile_copy:
            compact_blob = create_inline_tile_copy_pure_tileonly()
            rom[0x42A7:0x436E] = compact_blob + bytes(
                available - len(compact_blob)
            )
            print(
                "  diagnostic isolation: compact four-tile/single-wait "
                "copier"
            )
        else:
            rom[0x42A7:0x436E] = vanilla_rom[0x42A7:0x436E]
        rom[0x0030:0x0033] = vanilla_rom[0x0030:0x0033]

    if demo_compact_tile_copy:
        assert stock_tile_copy and native_room_writers, (
            "demo-only compact copy requires native live terrain/call sites"
        )
        assert not compact_tile_copy, (
            "demo-only and all-scene compact copy are mutually exclusive"
        )
        demo_compact = create_inline_tile_copy_pure_tileonly()
        demo_compact_off = BANK13 + (DEMO_COMPACT_COPY_ADDR - 0x4000)
        assert (
            DEMO_COMPACT_COPY_ADDR + len(demo_compact)
            <= STALE_WINDOW_CLEANUP_ADDR
        )
        assert rom[
            demo_compact_off:demo_compact_off + len(demo_compact)
        ] == bytes(len(demo_compact)), (
            "demo compact-copy cave is no longer free"
        )
        rom[
            demo_compact_off:demo_compact_off + len(demo_compact)
        ] = demo_compact
        demo_dispatch = build_demo_compact_dispatcher()
        rom[
            INLINE_ATTR_DECISION_HELPER_ADDR:0x34A3
        ] = demo_dispatch + bytes(
            0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR - len(demo_dispatch)
        )
        assert rom[0x42A0:0x42A7] == vanilla_rom[0x42A0:0x42A7]
        # $9C00 entry preserves its selected H through the common dispatcher.
        # $9800 entry uses RST $30 so direct CALL $42A5 sites remain valid.
        demo_common = INLINE_ATTR_DECISION_HELPER_ADDR + 2
        rom[0x42A0:0x42A7] = bytes([
            0x26, 0x9C,
            0xC3, demo_common & 0xFF, demo_common >> 8,
            0xF7, 0xC9,
        ])
        assert rom[0x0030:0x0033] == vanilla_rom[0x0030:0x0033]
        rom[0x0030:0x0033] = bytes([
            0xC3,
            INLINE_ATTR_DECISION_HELPER_ADDR & 0xFF,
            INLINE_ATTR_DECISION_HELPER_ADDR >> 8,
        ])
        print(
            "  attract-only compact pure copier: "
            f"{len(demo_compact)} bytes at bank13:0x"
            f"{DEMO_COMPACT_COPY_ADDR:04X}; live/title remain native"
        )

    use_stage1_hazard_hook = not (
        stock_tile_copy
        or compact_tile_copy
        or demo_compact_tile_copy
        or semantic_stage1_prototype
        or semantic_stage1_vblank_prototype
    )
    if use_stage1_hazard_hook:
        # RST $18 has no stock caller. Map bank 14 and tail-jump directly to
        # the completed-source hazard service. It discards the synthetic
        # $13E5 return, publishes only changed hazard rows, restores bank 1 and
        # the caller's IE mask, then returns to the expander's original caller.
        assert rom[0x0018:0x0020] == vanilla_rom[0x0018:0x0020]
        assert (
            rom[STAGE1_SOURCE_BUILD_RET_ADDR]
            == vanilla_rom[STAGE1_SOURCE_BUILD_RET_ADDR]
            == 0xC9
        )
        rom[0x0018:0x0020] = bytes([
            0x3E, 0x0E,
            0xCD, 0x61, 0x00,
            0xC3,
            STAGE1_HAZARD_ROW_HELPER_ADDR & 0xFF,
            STAGE1_HAZARD_ROW_HELPER_ADDR >> 8,
        ])
        rom[STAGE1_SOURCE_BUILD_RET_ADDR] = STAGE1_SOURCE_GENERATION_RST
        print(
            "  Stage-1 selective hazard hook: native $13E4 RET -> RST $18; "
            "completed C1A0 phases publish only spike-bearing rows"
        )

    if semantic_stage1_prototype:
        assert (
            not stock_tile_copy
            and not compact_tile_copy
            and not semantic_stage1_vblank_prototype
        )
        semantic = build_semantic_stage1_prototype(
            SEMANTIC_STAGE1_PROTOTYPE_ADDR
        )
        semantic_off = BANK13 + (
            SEMANTIC_STAGE1_PROTOTYPE_ADDR - 0x4000
        )
        rom[semantic_off:semantic_off + len(semantic)] = semantic
        assert len(semantic) <= 0x180

        # Redirect the native map-toggle entry through an always-mapped
        # wrapper. It reproduces the stock toggle, calls the byte-exact native
        # copier, then invokes the otherwise-unused RST $18 semantic tail.
        wrapper = bytes.fromhex(
            "FA 0B DC 3C E6 01 EA 0B DC 28 04 26 9C 18 02 26 98 "
            "CD A7 42 F3 F5 C5 D5 E5 DF E1 D1 C1 F1 FB C9"
        )
        assert len(wrapper) <= 0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR
        rom[
            INLINE_ATTR_DECISION_HELPER_ADDR:0x34A3
        ] = wrapper + bytes(
            0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR - len(wrapper)
        )
        assert rom[0x4295:0x4298] == vanilla_rom[0x4295:0x4298]
        rom[0x4295:0x4298] = bytes([
            0xC3,
            INLINE_ATTR_DECISION_HELPER_ADDR & 0xFF,
            INLINE_ATTR_DECISION_HELPER_ADDR >> 8,
        ])
        assert rom[0x0018:0x001B] == vanilla_rom[0x0018:0x001B]
        rom[0x0018:0x001B] = bytes([0xC3, 0x38, 0x08])
        print(
            "  diagnostic isolation: native copier + Stage-1 semantic "
            f"pickup tail ({len(semantic)} bytes; arena tables intentionally "
            "sacrificed in this non-release ROM)"
        )

    if semantic_stage1_vblank_prototype:
        assert not compact_tile_copy and not semantic_stage1_prototype
        # The peer-map GDMA happens wholly inside the bounded room sweep.
        # Every native terrain path and RST vector remains byte-exact.
        assert rom[0x13AA] == vanilla_rom[0x13AA] == 0xD5
        assert rom[0x13E4] == vanilla_rom[0x13E4] == 0xC9
        assert rom[0x4295:0x4298] == vanilla_rom[0x4295:0x4298]
        assert rom[0x0018:0x0020] == vanilla_rom[0x0018:0x0020]
        assert rom[0x436D] == vanilla_rom[0x436D] == 0xC9
        print(
            "  diagnostic isolation: byte-exact native terrain copier + "
            "18 bounded CPU+GDMA mirrored attribute rows"
        )

    # The original RST $08 vector jumps to $0000 and has no viable caller.
    # Reuse it for the stock BGP write plus a fixed-bank dispatcher. Keep the
    # original unconditional dispatch cadence: the attract reel is sensitive
    # even to equivalent-looking changes on the common E4 path.
    # RST $18 remains untouched except in the older synchronous diagnostic.
    assert rom[0x0008:0x0010] == bytes.fromhex(
        "C3 00 00 FE FF 9F FF FF"
    )
    assert rom[
        NATIVE_DMG_FADE_SITE:NATIVE_DMG_FADE_SITE + 2
    ] == bytes.fromhex("E0 47")
    assert rom[
        NATIVE_DMG_FADE_DISPATCH_ADDR:
        NATIVE_DMG_FADE_DISPATCH_ADDR + 25
    ] == bytes(25)
    rom[0x0008:0x0010] = bytes([
        0xE0, 0x47,                         # original LDH [BGP],A
        0xC3,
        NATIVE_DMG_FADE_DISPATCH_ADDR & 0xFF,
        NATIVE_DMG_FADE_DISPATCH_ADDR >> 8,
        0x00, 0x00, 0x00,
    ])
    native_fade_service = build_native_dmg_fade_fixed_service()
    stage1_demo_delay = build_stage1_demo_delay(stage1_demo_wait_line)
    assert (
        NATIVE_DMG_FADE_DISPATCH_ADDR + len(native_fade_service)
        == STAGE1_DEMO_DELAY_ADDR
    )
    fixed_services = native_fade_service + stage1_demo_delay
    rom[
        NATIVE_DMG_FADE_DISPATCH_ADDR:
        NATIVE_DMG_FADE_DISPATCH_ADDR + 25
    ] = fixed_services + bytes(25 - len(fixed_services))
    rom[
        NATIVE_DMG_FADE_SITE:NATIVE_DMG_FADE_SITE + 2
    ] = bytes([0xCF, 0x00])                 # RST $08; stock DEC B follows

    # Suppress the stock whole-screen $90/$F9 pulse on CGB without changing
    # any branch, RET, or instruction width. This one routine is shared by
    # attract-demo and live gameplay, so both paths receive the same bounded
    # fix while title/transition BGP writers remain untouched.
    native_gameplay_bgp = bytes.fromhex(
        "3E 90 E0 47 C9 3E E4 E0 47 C9 3E F9 E0 47 C9"
    )
    native_gameplay_bgp_end = (
        NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR + len(native_gameplay_bgp)
    )
    assert rom[
        NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR:native_gameplay_bgp_end
    ] == native_gameplay_bgp
    rom[NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR + 1] = 0xE4
    rom[NATIVE_GAMEPLAY_BGP_ROUTINE_ADDR + 11] = 0xE4
    print(
        "  inline hook: fixed-helper cached register-staged atomic attrs + "
        "stock-width tile-only steady maps "
        f"({len(inline_blob)}+{len(inline_attr_decision)} bytes); "
        f"uniform native DMG fade service={len(native_fade_service)} bytes "
        f"at fixed:0x{NATIVE_DMG_FADE_DISPATCH_ADDR:04X}; "
        "demo/gameplay BGP pulse $90/$F9 -> $E4"
    )

    # 14. Safe scene/colorize prelude at bank13:0x6E80. It deliberately has no
    # SELECT+START handling and no IRQ stack redirection.
    prelude = build_colorize_prelude()
    if disable_lava_override:
        lava_tail = bytes([
            0xC3, LAVA_OVERRIDE_ADDR & 0xFF, LAVA_OVERRIDE_ADDR >> 8,
        ])
        assert prelude.count(lava_tail) == 1
        lava_tail_offset = prelude.index(lava_tail)
        prelude = (
            prelude[:lava_tail_offset]
            + bytes([0xC9, 0x00, 0x00])
            + prelude[lava_tail_offset + len(lava_tail):]
        )
        print(
            "  diagnostic isolation: lava override disabled at constant "
            "instruction width"
        )
    if minimal_prelude:
        prelude = bytes([
            0xCD, SCENE_DETECT_ADDR & 0xFF, SCENE_DETECT_ADDR >> 8, 0xC9,
        ]) + bytes(len(prelude) - 4)
        print(
            "  diagnostic isolation: prelude reduced to scene detection "
            "while the shared title-palette copier remains out of line"
        )
    assert COLORIZE_PRELUDE_ADDR + len(prelude) <= WRAPPER_ADDR
    off = BANK13 + (COLORIZE_PRELUDE_ADDR - 0x4000)
    rom[off:off + len(prelude)] = prelude
    print(f"  safe colorize prelude: {len(prelude)} bytes at bank13:0x{COLORIZE_PRELUDE_ADDR:04X}")

    title_palette_fix = build_title_palette_fix(story_dispatch)
    assert (
        TITLE_PALETTE_FIX_ADDR + len(title_palette_fix)
        <= STORY_SEPARATOR_HELPER_ADDR
    ), "title palette repair collides with story lower-panel helper"
    assert rom[palette_source_off:palette_source_off + 8] == expected_bg0, \
        "title palette source no longer matches YAML BG0"
    off = BANK13 + (TITLE_PALETTE_FIX_ADDR - 0x4000)
    assert rom[off:off + len(title_palette_fix)] == bytes(len(title_palette_fix)), \
        "title palette repair slot is no longer free"
    rom[off:off + len(title_palette_fix)] = title_palette_fix
    print(f"  title palette repair: {len(title_palette_fix)} bytes at bank13:0x{TITLE_PALETTE_FIX_ADDR:04X}")

    # 15. VBlank wrapper at 0x6F30. Preserve the proven v3.01 cold-boot timing:
    # joypad -> scene/colorizer first, then the one-shot footer helper.
    # Sound remains owned by the original game; a second call here churns it.
    wrapper = bytearray([
        0xC5,                                 # PUSH BC
        0xD5,                                 # PUSH DE
        0xE5,                                 # PUSH HL
        # Story rows and death/game-over containment retain their proven first
        # wrapper service point. Title entry work is now called exactly once by
        # scene_detect; adding it to this per-frame path stole enough VBlank
        # time to make the final-cutscene attribute writer miss cells.
        # Preserve the proven GAME START instruction order and sampling phase.
        # Moving even a cycle-equivalent scene gate ahead of these calls makes
        # the scripted/menu A pulse land one stock cadence late.
        0xCD, DEATH_ATTR_DISPATCH_ADDR & 0xFF,
        DEATH_ATTR_DISPATCH_ADDR >> 8,
        0xCD, TITLE_PALETTE_FIX_ADDR & 0xFF,
        TITLE_PALETTE_FIX_ADDR >> 8,
        0xF0, 0xC1,                        # LDH A,[FFC1]
        0xB7,                              # OR A
        0x28, 0x12,                        # JR Z,palette_done
        # Gameplay services pending phases on consecutive VBlanks and probes
        # an idle hash once per eight stock ticks.
        0xFA, PALETTE_PHASE_ADDR & 0xFF,
        PALETTE_PHASE_ADDR >> 8,           # LD A,[pending phase]
        0xB7,                              # OR A
        0x28, 0x05,                        # JR Z,palette_idle_probe
        0xCD, CONDITIONAL_PALETTE_ADDR & 0xFF,
        CONDITIONAL_PALETTE_ADDR >> 8,     # pending: service this VBlank
        0x18, 0x07,                        # JR palette_done
        0xF0, 0xD4,                        # idle: stock VBlank tick
        0xE6, 0x07,                        # once per eight frames
        0xCC, CONDITIONAL_PALETTE_ADDR & 0xFF,
        CONDITIONAL_PALETTE_ADDR >> 8,     # CALL Z,palette state probe
        # Robust joypad sampler inherited from the proven v3.01 wrapper.
        # FF93 is consumed by the game. SELECT+START is no longer intercepted.
        0x3E, 0x20,                           # LD A, 0x20 (directions)
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00, 0xF0, 0x00,              # settle reads
        0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,  # CPL; AND 0x0F; SWAP A; LD B,A
        0x3E, 0x10,                           # LD A, 0x10 (buttons)
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00, 0xF0, 0x00,              # eight settle reads
        0xF0, 0x00, 0xF0, 0x00,
        0xF0, 0x00, 0xF0, 0x00,
        0xF0, 0x00, 0xF0, 0x00,
        0x2F, 0xE6, 0x0F, 0xB0,              # CPL; AND 0x0F; OR B
        0xE0, 0x93,                           # LDH [FF93], A
        0x47,                                 # LD B, A
        0x3E, 0x30, 0xE0, 0x00, 0x78,        # deselect; restore buttons in A
        # CALL safe prelude (scene_detect + lava + menu/window init)
        0xCD, COLORIZE_PRELUDE_ADDR & 0xFF, (COLORIZE_PRELUDE_ADDR >> 8) & 0xFF,
        # Gameplay is paused while the item-menu window is visible. The
        # prelude has just cleared the active window map; do not let the
        # background sweep repaint those HUD cells later in this VBlank.
        0xF0, 0x40,                        # LDH A,[LCDC]
        0xE6, 0x20,                        # AND window-enable
        0x20, 0x0A,                        # JR NZ, skip full colorizer
        # Death ($17) owns a bounded two-map neutral pass above; STAGE XX ($18)
        # uses its all-pal0 inline path. Both skip the gameplay colorizer:
        # death must not be repainted from the stale dungeon/arena table, and
        # the splash must retain stock VBlank/ditty timing.
        0xFA, 0x80, 0xD8,                  # LD A,[D880]
        0xD6, 0x17,                        # SUB first skipped scene
        0xFE, 0x02,                        # $17/$18 leave carry set
        0xD4, COLORIZE_ADDR & 0xFF, (COLORIZE_ADDR >> 8) & 0xFF,
        # One-shot period + v3.01 digits + footer attributes. Keeping this
        # after colorize prevents it from delaying first-VBlank CRAM writes.
        0xCD, VRAM_GLYPH_COPY_ADDR & 0xFF,
        VRAM_GLYPH_COPY_ADDR >> 8,
        # Restore registers
        0xE1,                                 # POP HL
        0xD1,                                 # POP DE
        0xC1,                                 # POP BC
        0xC9,                                 # RET
    ])

    if disabled_vblank_service is not None:
        service_calls = {
            "death": [bytes([
                0xCD, DEATH_ATTR_DISPATCH_ADDR & 0xFF,
                DEATH_ATTR_DISPATCH_ADDR >> 8,
            ])],
            "title-palette": [bytes([
                0xCD, TITLE_PALETTE_FIX_ADDR & 0xFF,
                TITLE_PALETTE_FIX_ADDR >> 8,
            ])],
            "palette-scheduler": [
                bytes([
                    0xCD, CONDITIONAL_PALETTE_ADDR & 0xFF,
                    CONDITIONAL_PALETTE_ADDR >> 8,
                ]),
                bytes([
                    0xCC, CONDITIONAL_PALETTE_ADDR & 0xFF,
                    CONDITIONAL_PALETTE_ADDR >> 8,
                ]),
            ],
            "prelude": [bytes([
                0xCD, COLORIZE_PRELUDE_ADDR & 0xFF,
                COLORIZE_PRELUDE_ADDR >> 8,
            ])],
            "colorizer": [bytes([
                0xD4, COLORIZE_ADDR & 0xFF, COLORIZE_ADDR >> 8,
            ])],
            "glyph-copy": [bytes([
                0xCD, VRAM_GLYPH_COPY_ADDR & 0xFF,
                VRAM_GLYPH_COPY_ADDR >> 8,
            ])],
        }
        for call in service_calls[disabled_vblank_service]:
            assert wrapper.count(call) == 1, (
                disabled_vblank_service,
                call.hex(),
                wrapper.count(call),
            )
            offset = wrapper.index(call)
            wrapper[offset:offset + len(call)] = bytes(len(call))
        print(
            "  diagnostic isolation: disabled VBlank service "
            f"{disabled_vblank_service} at constant instruction width"
        )
    assert WRAPPER_ADDR + len(wrapper) <= SCENE_DETECT_ADDR
    wrapper_off = BANK13 + (WRAPPER_ADDR - 0x4000)
    rom[wrapper_off:wrapper_off + len(wrapper)] = wrapper
    print(f"  VBlank wrapper (with VRAM glyph copy): {len(wrapper)} bytes at bank13:0x{WRAPPER_ADDR:04X}")

    # 16. VBlank hook at 0x0824
    new_hook = bytearray([
        0xF0, 0x99,                           # LDH A, [FF99]
        0xF5,                                 # PUSH AF
        0x3E, 0x0D,                           # LD A, 13
        0xE0, 0x99,                           # LDH [FF99], A
        0xEA, 0x00, 0x21,                     # LD [0x2100], A
        0xCD, WRAPPER_ADDR & 0xFF, (WRAPPER_ADDR >> 8) & 0xFF,  # CALL wrapper
        0xF1,                                 # POP AF
        0xE0, 0x99,                           # LDH [FF99], A
        0xEA, 0x00, 0x21,                     # LD [0x2100], A
        0xC9,                                 # RET
    ])
    assert WRAPPER_ADDR == 0x6F20
    assert 0x0824 + len(new_hook) == ROOM_BG_REARM_BANK0_ADDR
    # The production-safe native Stage-1 copier uses the room-change hooks to
    # arm its bounded attribute sweep. ``--native-room-writers`` remains the
    # explicit diagnostic escape hatch that removes this instrumentation.
    use_room_rearm_hooks = not (
        native_room_writers
        or semantic_stage1_prototype
    )
    if use_room_rearm_hooks:
        new_hook.extend(build_room_bg_rearm_bank0())
    elif semantic_stage1_prototype:
        # RST $18 trampoline: preserve the caller's mapped bank, map bank 13,
        # call the diagnostic semantic tail, then tail-restore the bank.
        new_hook.extend(bytes([
            0xF0, 0x99, 0xF5,
            0x3E, 0x0D, 0xCD, 0x61, 0x00,
            0xCD,
            SEMANTIC_STAGE1_PROTOTYPE_ADDR & 0xFF,
            SEMANTIC_STAGE1_PROTOTYPE_ADDR >> 8,
            0xF1, 0xC3, 0x61, 0x00,
        ]))
    assert len(new_hook) <= 47
    new_hook_padded = (new_hook + bytearray(47 - len(new_hook)))[:47]
    rom[0x0824:0x0824 + 47] = new_hook_padded
    if use_room_rearm_hooks:
        install_room_bg_rearm_hooks(
            rom,
            target_addr=ROOM_BG_REARM_BANK0_ADDR,
        )
    lava_decider_bank0 = build_lava_attr_decider_bank0()
    bank0_decider_end = (
        LAVA_ATTR_DECIDER_BANK0_ADDR + len(lava_decider_bank0)
    )
    assert bank0_decider_end <= 0x0853
    assert rom[
        LAVA_ATTR_DECIDER_BANK0_ADDR:bank0_decider_end
    ] == bytes(len(lava_decider_bank0))
    rom[
        LAVA_ATTR_DECIDER_BANK0_ADDR:bank0_decider_end
    ] = lava_decider_bank0
    if not use_room_rearm_hooks:
        room_hook_status = "native FFBD writers/RST $00 retained"
    else:
        room_hook_status = "RST $00 hooks at four native room writers"
    print(
        f"  VBlank hook + optional FFBD rearm target: {len(new_hook)} bytes "
        f"at 0x0824; {room_hook_status}; "
        f"lava-decider trampoline={len(lava_decider_bank0)} bytes"
    )

    if stock_vblank:
        # Diagnostic isolation: retain all ROM data/palettes/title work but
        # restore the stock VBlank DMA + joypad service and remove every room
        # writer trampoline installed above. This proves whether terrain
        # corruption is caused by the runtime VBlank family rather than ROM
        # room data or the inline 24x24 copier.
        rom[0x06D5:0x06D8] = vanilla_rom[0x06D5:0x06D8]
        rom[0x0824:0x0853] = vanilla_rom[0x0824:0x0853]
        for offset in (0x0B7E, 0x11D2, 0x11FC, 0x4106):
            rom[offset:offset + 2] = vanilla_rom[offset:offset + 2]
        rom[0x0000:0x0003] = vanilla_rom[0x0000:0x0003]
        print("  diagnostic isolation: stock VBlank + room writers restored")

    if stock_oam_emitters:
        assert stock_tile_copy, (
            "native OAM emitters overlap the DX inline decision cave; "
            "use --stock-tile-copy for this diagnostic"
        )
        rom[0x0008:0x0010] = vanilla_rom[0x0008:0x0010]
        rom[NATIVE_DMG_FADE_SITE:NATIVE_DMG_FADE_SITE + 2] = vanilla_rom[
            NATIVE_DMG_FADE_SITE:NATIVE_DMG_FADE_SITE + 2
        ]
        rom[0x10D1:0x10EE] = vanilla_rom[0x10D1:0x10EE]
        rom[0x346F:0x34A3] = vanilla_rom[0x346F:0x34A3]
        print(
            "  diagnostic isolation: native gameplay OAM emitters and "
            "their overlapping DMG-fade sites restored"
        )

    if reserved_pickup_gold:
        apply_stage1_reserved_pickup_gold(rom, vanilla_rom)

    # Every cutscene now owns its visible colors instead of inheriting CRAM
    # from whichever title/gameplay path happened to precede it. The existing
    # phased loader copies the YAML BG table (including tuneable BG7) through
    # the same LCD-safe path already proven by live gameplay.
    cutscene_regions = (
        (
            BANK13 + (CUTSCENE_PALETTE_BRIDGE_ADDR - 0x4000),
            cutscene_palette_bridge,
            "bank13 bridge",
        ),
        (
            BANK13 + (CUTSCENE_PALETTE_CONT_ADDR - 0x4000),
            cutscene_palette_continuation,
            "bank13 body",
        ),
    )
    for offset, payload, label in cutscene_regions:
        assert rom[offset:offset + len(payload)] == bytes(len(payload)), (
            f"cutscene palette {label} cave is no longer free"
        )
        rom[offset:offset + len(payload)] = payload
    print(
        "  cutscene CRAM ownership: 8 YAML BG rows loaded once per "
        "opening/pre-final/post-final/ending family; "
        f"entry={len(cutscene_palette_bridge)} bytes at "
        f"${CUTSCENE_PALETTE_BRIDGE_ADDR:04X}, body="
        f"{len(cutscene_palette_continuation)} bytes at "
        f"${CUTSCENE_PALETTE_CONT_ADDR:04X}; epilogue dispatches through "
        "the title-palette service"
    )

    # 17. Levelsel JP NZ patch
    expected = bytes([0xC2, 0x93, 0x73])
    actual = bytes(rom[LEVELSEL_PATCH_ADDR:LEVELSEL_PATCH_ADDR + 3])
    assert actual == expected, f"levelsel patch site corrupted: {actual.hex()}"
    if minimal_prelude:
        print("  diagnostic isolation: native level-select branch retained")
    else:
        rom[LEVELSEL_PATCH_ADDR + 1] = LEVELSEL_STUB_WRAM & 0xFF
        rom[LEVELSEL_PATCH_ADDR + 2] = (LEVELSEL_STUB_WRAM >> 8) & 0xFF
        print(f"  Levelsel JP NZ patched: 0x{LEVELSEL_PATCH_ADDR:04X} → 0x{LEVELSEL_STUB_WRAM:04X}")

    # Header checksum
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    # Final dispatcher/identity-map verification.
    _dispatch = rom[
        BANK13 + (ATTRACT_OBJ_COLORIZER_ADDR - 0x4000):
        BANK13 + (ATTRACT_OBJ_COLORIZER_ADDR - 0x4000) + len(attract_obj)
    ]
    assert _dispatch == attract_obj
    _transition = rom[
        BANK13 + (TITLE_TRANSITION_SERVICE_ADDR - 0x4000):
        BANK13 + (TITLE_TRANSITION_SERVICE_ADDR - 0x4000)
        + len(title_transition)
    ]
    assert _transition == title_transition
    _map = rom[
        BANK13 + (SPOTLIGHT_PALETTE_MAP_ADDR - 0x4000):
        BANK13 + (SPOTLIGHT_PALETTE_MAP_ADDR - 0x4000)
        + len(spotlight_map)
    ]
    assert _map == spotlight_map
    for offset, payload, label in cutscene_regions:
        assert rom[offset:offset + len(payload)] == payload, label
    print(
        "  ✅ title/gameplay OAM dispatcher + transition service + "
        "complete spotlight roster map + cutscene CRAM loader verified"
    )

    write_output_with_backup(
        output_path,
        rom,
        backup_existing=output_path.resolve() == OUTPUT_PATH.resolve(),
    )
    print(f"Wrote {output_path} ({len(rom)} bytes)")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the Penta Dragon DX stream release candidate"
    )
    parser.add_argument("--palette-yaml", type=Path, default=PALETTE_YAML)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument(
        "--base-output",
        type=Path,
        help="Intermediate v3.01 path (defaults beside a custom output)",
    )
    parser.add_argument(
        "--stage1-demo-wait-line",
        type=int,
        default=STAGE1_DEMO_WAIT_LINE,
        help="diagnostic LY phase for attract Stage 1 cache misses",
    )
    parser.add_argument(
        "--stock-tile-copy",
        action="store_true",
        help="restore the native 24x24 tile copier for isolation testing",
    )
    parser.add_argument(
        "--stock-vblank",
        action="store_true",
        help="restore native VBlank/input/DMA and room writers for isolation",
    )
    parser.add_argument(
        "--native-room-writers",
        action="store_true",
        help="retain native FFBD writers/RST $00 while testing the DX copier",
    )
    parser.add_argument(
        "--disable-vblank-service",
        choices=(
            "death",
            "title-palette",
            "palette-scheduler",
            "prelude",
            "colorizer",
            "glyph-copy",
        ),
        help="diagnostically NOP one fixed-width per-VBlank service",
    )
    parser.add_argument(
        "--stock-oam-emitters",
        action="store_true",
        help="retain the two native gameplay OAM emitters for isolation",
    )
    parser.add_argument(
        "--minimal-prelude",
        action="store_true",
        help="run only scene detection in the per-VBlank prelude",
    )
    parser.add_argument(
        "--disable-lava-override",
        action="store_true",
        help="NOP the per-VBlank lava override while retaining the prelude",
    )
    parser.add_argument(
        "--buffered-stage1-attrs",
        action="store_true",
        help=(
            "diagnostically stage Stage-1 attrs in WRAM and publish them "
            "with one GDMA instead of per-group VRAM attr writes"
        ),
    )
    parser.add_argument(
        "--compact-tile-copy",
        action="store_true",
        help="diagnostically use the compact four-tile single-wait copier",
    )
    parser.add_argument(
        "--semantic-stage1-prototype",
        action="store_true",
        help=(
            "diagnostically keep the native copier and stamp only Stage-1 "
            "pickup metatiles; overwrites later-arena tables and is never a "
            "release build"
        ),
    )
    parser.add_argument(
        "--semantic-stage1-vblank-prototype",
        action="store_true",
        help=(
            "diagnostically keep the native copier and color one semantic "
            "Stage-1 pickup metatile row per VBlank from a bank-14 cave"
        ),
    )
    parser.add_argument(
        "--reserved-pickup-gold",
        action="store_true",
        help=(
            "reserve Stage-1 BG0 color index 1 for gold pickup art without "
            "runtime attribute writes"
        ),
    )
    parser.add_argument(
        "--demo-compact-tile-copy",
        action="store_true",
        help=(
            "use the compact pure tile copier only for DCFD=0 prerecorded "
            "gameplay while retaining byte-exact native live terrain"
        ),
    )
    arguments = parser.parse_args()
    main(
        palette_yaml=arguments.palette_yaml,
        output_path=arguments.output,
        base_output=arguments.base_output,
        stage1_demo_wait_line=arguments.stage1_demo_wait_line,
        stock_tile_copy=arguments.stock_tile_copy,
        native_room_writers=arguments.native_room_writers,
        stock_vblank=arguments.stock_vblank,
        disabled_vblank_service=arguments.disable_vblank_service,
        stock_oam_emitters=arguments.stock_oam_emitters,
        minimal_prelude=arguments.minimal_prelude,
        disable_lava_override=arguments.disable_lava_override,
        buffered_stage1_attrs=arguments.buffered_stage1_attrs,
        compact_tile_copy=arguments.compact_tile_copy,
        demo_compact_tile_copy=arguments.demo_compact_tile_copy,
        semantic_stage1_prototype=arguments.semantic_stage1_prototype,
        semantic_stage1_vblank_prototype=(
            arguments.semantic_stage1_vblank_prototype
        ),
        reserved_pickup_gold=arguments.reserved_pickup_gold,
    )
