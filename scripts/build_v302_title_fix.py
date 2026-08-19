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
from arena_semantic_key import (
    build_arena_postcopy_dispatcher,
    HELPER_BANK as ARENA_ATTR_KEY_HELPER_BANK,
    HELPER_ENTRY as ARENA_ATTR_KEY_HELPER_ADDR,
)
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
    create_inline_tile_copy_postcomputed_attrs,
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
BANK7 = 7 * 0x4000
BANK2 = 2 * 0x4000
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
TITLE_DELAY_ADDR = 0x7DFC
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
LATER_STAGE_BG0_ARM_ADDR = PALETTE_COPY_CRAM8_ADDR + 7
LATER_STAGE_BG0_REPAIR_ADDR = 0x69B8
CONDITIONAL_PALETTE_ADDR = 0x6C90
# Keep the established $6C90 ABI as a three-byte trampoline. The expanded
# idle-throttled implementation lives in the unused tail after the title
# transition service and before the spotlight identity map.
CONDITIONAL_PALETTE_IMPL_ADDR = 0x6BA4
CRYSTAL_PALETTE_REARM_ADDR = 0x6BDF
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
TITLE_TRANSITION_SERVICE_ADDR = 0x7CFC
# The retired gameplay OBJ scan is explicitly cleared through $6A6F. Keep the
# gameplay-only hardware-Window guard in its free tail below the title helper.
STALE_WINDOW_CLEANUP_ADDR = 0x6A40
# The former attract-row helper slot and the exact gap after the YAML OBJ LUT
# initializer are both in the explicitly retired $7B00-$7DFF position-map
# allocation. Split the cutscene scheduler across them so the entire 18-byte
# pointer-table allocation at $7FE0 remains byte-exact (seven-byte copier plus
# eleven required zero bytes) for timing-sensitive Stage-1/demo paths.
CUTSCENE_PALETTE_CONT_ADDR = 0x7B85
CUTSCENE_PALETTE_CONT_END = 0x7B9C
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
ROOM_BG_REPAIR_STANDARD_ADDR = ROOM_BG_REPAIR_ADDR + 20
ROOM_BG_REPAIR_CLEAR_ADDR = ROOM_BG_REPAIR_ADDR + 29
SHADOW_MAIN_ADDR = 0x69D8
TILE_COLORIZER_ADDR = 0x6A10
BOSS_SLOT_TABLE_ADDR = 0x68C0
CRYSTAL_DRAGON_SCENE = 0x0E
# The former $6F35 placement left an unused gap after the uniform-clear helper.
# Reclaim it for an inline palette scheduler so idle VBlanks avoid a CALL.
WRAPPER_ADDR = 0x6F1D
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
# The diagnostic postcomputed publisher generates an unrolled row helper in
# the census-empty fixed-WRAM page immediately after the native tile buffer.
STAGE1_ATTR_ROW_INIT_ADDR = 0x5516
STAGE1_ATTR_ROW_INIT_TAIL_ADDR = 0x55A8
STAGE1_ATTR_ROW_HELPER_WRAM_ADDR = 0xD400
# A compact bank-13 gate enters the bank-14 loader from a retired colorizer
# gap. Keeping executable bytes out of $7900-$7AFF is mandatory: those two
# pages are the Angela and Penta Dragon arena attribute tables. During the
# first live Stage-1 spike-room VBlank the loader mirrors the four neutral
# floor/shadow patterns plus all twelve tooth phases into otherwise-unused
# VRAM-bank-1 slots. The completed-map stamper can then leave every tooth
# travel cell on one immutable BG7/bank-1 attribute.
STAGE1_HAZARD_BANK1_LOADER_ADDR = 0x6A0E
STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR = 0x6CAA
STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR = 0xDF5B
STAGE1_HAZARD_BANK1_TILE_COUNT = 16
STAGE1_HAZARD_BANK1_REFRESH_COUNT = 3
STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR = 0x6C10
STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR = 0x6BFF
STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR = 0x65FF
STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR = 0x6940
STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR = 0x6BEE
STAGE1_ENTRY_PATCH_GATE_ADDR = 0x6A33
STAGE1_ENTRY_PATCH_BODY_ADDR = 0x55E5
STAGE1_ENTRY_PATCH_LOWER_ADDR = 0x560A
STAGE1_ENTRY_PATCH_TAIL_ADDR = 0x6C30
STAGE1_ENTRY_PATCH_FINISH_ADDR = 0x6E70
# Bank 13's three-byte hazard selector at $6C80 always jumps away. Its
# verified-zero fallthrough gap ends at the fixed $6C90 palette trampoline,
# making it safe executable storage rather than live-path timing padding.
COLD_STAGE1_SWEEP_ARM_ADDR = 0x6C83
COLD_STAGE1_SWEEP_ARM_TAIL_ADDR = 0x7D65
STAGE1_VBLANK_PROTOTYPE_ADDR = 0x6BA7
# Bank 14's verified-zero $6BA7-$6C57 cave is mapped only after the native
# 24x24 tile copier finishes.  It holds the Stage-1 animation attribute
# publisher: no tile IDs and no HBlank waits, just WRAM LUT compilation plus
# bounded 32-byte general-DMA rows.
STAGE1_HAZARD_ROW_HELPER_ADDR = STAGE1_VBLANK_PROTOTYPE_ADDR
STAGE1_HAZARD_ROW_HELPER_END = 0x6C58
STAGE1_HAZARD_ROW_COMPILER_ADDR = 0x6C88
STAGE1_HAZARD_ROW_COMPILER_END = 0x6CFC
STAGE1_HAZARD_ROOM_DISPATCH_ADDR = 0x6CCE
STAGE1_HAZARD_PHASE_KEY_ADDR = 0x6CDE
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
# Three title-delay bytes plus the 18-byte readiness/demo dispatcher occupy
# $3482-$3496. The adjacent twelve-byte wrapper ends at the fixed boundary.
STAGE1_ATOMIC_WRAP_ADDR = INLINE_ATTR_DECISION_HELPER_ADDR + 21
# The production inline copier ends at $4364, leaving an exact nine-byte
# bank-1 tail. Move the atomic wrapper's IE/RETI epilogue there so the fixed
# entry can reload D880 before its completion mapper. The layered v65 lineage
# reached $0842 with A=$01 and silently RET C'd before all arena post-copy
# services.
STAGE1_ATOMIC_WRAP_TAIL_ADDR = 0x4365
NATIVE_DMG_FADE_DISPATCH_ADDR = 0x10D5
STAGE1_DEMO_ATTR_TRAMPOLINE_ADDR = NATIVE_DMG_FADE_DISPATCH_ADDR + 18
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
# Resolver/setup and central-emitter sources are contiguous, just like their
# DA00 runtime destinations, so cold boot copies both with one memcpy.
OAM_CENTRAL_EMITTER_ADDR = 0x7B21
OAM_BOSS_LUT_SERVICE_ADDR = 0x7B5D
OAM_BOSS_LUT_FADE_GATE_ADDR = 0x6500
TED_ENVELOPE_COMPARE_ROM_ADDR = OAM_BOSS_LUT_FADE_GATE_ADDR
# The all-boss geometry corpus observes Angela tiles $01-$BA and background
# tile $FF; $BB-$FE is explicitly unused.  Keep Ted's compact 28-byte envelope
# table in the first part of that receipt-bounded neutral LUT tail ($BB-$D6).
# Do not use Ted's own apparently-zero $D6-$FF tail: the direct-plane build
# copies the whole $7687-$76FF span into WRAM as executable runtime padding.
# Never use $70E0 either: $7000-$70FF is copied verbatim into C600 as Stage 1's
# live tile-palette LUT, including its pickup classes.
TED_ENVELOPE_ROW_TABLE_ROM_ADDR = 0x79BB
ATTRACT_PICKUP_SWEEP_HELPER_ADDR = 0x6A2D
OAM_FREE_EMITTER_ADDR = 0x7BE0
LAVA_ATTR_STAGE5_SIGNATURE_ADDR = 0x7C13
DEATH_FADE_NORMAL_ADDR = 0x7C2C
DEATH_FADE_INTERMEDIATE_ADDR = 0x7C34
DEATH_FADE_WHITE_ADDR = 0x7C3C
OAM_WRAM_COPY_ADDR = 0x7CBF
OAM_WRAM_COPY_TED_HELPER_CONT_ADDR = 0x5546
OAM_WRAM_COPY_TAIL_ADDR = 0x575C
NATIVE_GLYPH_RESTORE_ADDR = 0x7D80
OAM_LUT_INIT_ADDR = 0x7DA8
# The first three bytes of both bank 13 and bank 14's verified-zero $6C80
# slots form a same-address selector for the existing fixed-bank mapper. Bank
# 13 enters the lava/Stage-1 dispatcher; bank 14 enters the hazard publisher.
STAGE1_HAZARD_BANKED_ENTRY_ADDR = 0x6C80
_TED_CACHED_FULL_PLANE_ENV = (
    _os.environ.get("PENTA_TED_CACHED_FULL_PLANE", "0") == "1"
)
STAGE1_HAZARD_BANK0_MAP_ADDR = 0x0842
STAGE1_HAZARD_PURE_MAP_ADDR = 0x10E2
LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR = (
    0x0847
)
# Bank 14's native-zero caves host a demo-only metatile scanner.  It runs once
# at the stock Stage-1 room-expander return and stamps only actual pickups into
# both maps; no per-frame tilemap scan or full attribute sweep remains.
DEMO_PICKUP_DIRECT_WRITER_ADDR = 0x67A2
DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR = 0x6832
# Two native-zero bank-14 caves hold a cycle-for-cycle no-write twin of the
# sparse pickup writer. Its four-byte store groups are replaced with equal-
# length/equal-cycle register-neutral instructions, preserving both mGBA and
# PyBoy prerecorded-input cadence without modifying either attribute map.
DEMO_PICKUP_PHASE_WRITER_ADDR = 0x6B26
DEMO_PICKUP_PHASE_WRITER_TAIL_ADDR = 0x6859
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
LAVA_ATTR_DECIDER_CONT_ADDR = 0x7D3D
LAVA_ATTR_ROOM_MATCH_ADDR = 0x7D6D
LAVA_ATTR_DECIDER_CONT_END = NATIVE_GLYPH_RESTORE_ADDR
LAVA_ATTR_DECIDER_BANK0_ADDR = 0x10E2
LAVA_ATTR_STAGE7_SOURCE_A_ADDR = 0x7BB2
LAVA_ATTR_STAGE7_SOURCE_B_ADDR = 0x7C4D
LAVA_ATTR_DECISION_HRAM = 0xE0
# FF91 has no LDH or absolute references in either the stock ROM or the
# production build outside this service. FFC4 was previously misidentified as
# free, but the original game writes it from 24 sites and could silently
# disable the prelude during a stage fade. Scene transitions publish zero only
# for Gargoyle $0A; ordinary fixtures retain a nonzero armed identity.
ATTRACT_PRELUDE_FLAG_HRAM = 0x91
# FFA5 is verified unused by the original game's all-bank LDH census. FFE1 is
# not scratch: banked sprite code writes it as an input/animation flag, and
# caching the route there can strand Sara in the wrong room state.
# The dirty postcomputed path changes H while compiling its WRAM attribute
# plane. Preserve the native copier's exact $98/$9C destination here so the
# final DMA cannot accidentally target merely "the currently off-screen map."
ATOMIC_DEST_H_HRAM = 0xA5
STAGE1_ATOMIC_ROUTE_HRAM = ATOMIC_DEST_H_HRAM  # compatibility alias
LAVA_ATTR_STAGE5_9800_META_ADDR = 0xDF53
LAVA_ATTR_STAGE5_9C00_META_ADDR = 0xDF57
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
STAGE1_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR = 0x61B7
STAGE1_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR = 0xDB80
STAGE1_ATOMIC_ATTR_STACK_COPY_ADDR = 0x61F6
# The live atomic arena publisher uses the retired Stage-4 material cave as a
# cold-boot source for an always-mapped WRAM geometry sanitizer. Stage 4's
# tiny transition-only material writer is split across three explicit gaps in
# the retired position-map region instead.
ARENA_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR = 0x563A
ARENA_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR = 0xDB80
# Bank-13 native-zero resource records used by the once-per-publication arena
# source sanitizers. Each fragment is independently asserted before use.
TED_SANITIZER_MAIN_ADDR = 0x578C
TED_SANITIZER_CLASSIFY_ADDR = 0x57BC
TED_SANITIZER_CROWN_ADDR = 0x58E0
TED_SANITIZER_ACTIVE_ADDR = 0x5910
TED_SANITIZER_SPECIAL_ADDR = 0x5940
TED_SANITIZER_CLEAR_ADDR = 0x5970
TED_SANITIZER_INSTALL_ADDR = TED_SANITIZER_SPECIAL_ADDR
TED_SANITIZER_INSTALL_MIDDLE_ADDR = TED_SANITIZER_CLEAR_ADDR
TED_SANITIZER_ROW_TABLE_ADDR = 0x5DCC
TED_SANITIZER_ANCHOR_ADDR = 0x5DFC
TED_SANITIZER_INSTALL_TAIL_ADDR = TED_SANITIZER_ANCHOR_ADDR
TED_SANITIZER_GEOMETRY_CONT_ADDR = 0x5E2C
TED_SANITIZER_COMPARE_ADDR = 0x5E5C
TED_SANITIZER_INSTALL_FINAL_ADDR = TED_SANITIZER_COMPARE_ADDR
TED_SANITIZER_RUNTIME_TAIL_SOURCE_ADDR = 0x5516
TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR = 0x54F2
# $5552-$5554 is the live OAM boot continuation, so it is not a ROM cave.
# The cached/sanitizer tail lives in the exact 31-byte zero gap at $56FF.
TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR = 0x56FF
TED_SANITIZER_ANCHOR_PACK_ADDR = 0x5CDA
SHALAMAR_SANITIZER_MAIN_ADDR = 0x5D0A
SHALAMAR_SANITIZER_CELL_ADDR = 0x5D3A
ARENA_SANITIZER_DISPATCH_ADDR = 0x5D6A
ARENA_SANITIZER_FRAGMENT_SIZE = 36
TED_SANITIZER_EXPECTED_HRAM = 0xA9
TED_SANITIZER_COUNTER_HRAM = 0xA8
TED_SANITIZER_TILE_MASK_HRAM = 0xA7
TED_SANITIZER_RUNTIME_ADDR = 0xC4FC
TED_SANITIZER_ANCHOR_INIT_RUNTIME_ADDR = 0xC5CB
TED_MAP_ANCHOR_ACTIVATE_TAIL_ROM_ADDR = 0x7687
TED_MAP_ANCHOR_ACTIVATE_ROM_ADDR = 0x7687
TED_ANCHOR_STATE_HELPER_ROM_ADDR = 0x76AE
TED_SCAN_CROWN_HELPER_ROM_ADDR = 0x76C1
TED_CACHED_RUNTIME_ADDR = 0xC4F5
TED_TILE_COMMIT_RUNTIME_ADDR = 0x61B0
TED_SANITIZER_RUNTIME_SENTINEL_ADDR = 0xC5FF
TED_SANITIZER_RUNTIME_SENTINEL_VALUE = 0xC9
# FFA5/FFA6 are live global palette-scheduler state. A 2,800-frame write
# canary proves C4FA/C4FB are untouched immediately before the lazily installed
# C4FC runtime, so the anchor cannot be mutated between three-cell groups.
TED_SANITIZER_ANCHOR_9800_ROW_ADDR = 0xC4F3
TED_SANITIZER_ANCHOR_9800_COL_ADDR = 0xC4F4
TED_SANITIZER_ANCHOR_9C00_ROW_ADDR = 0xC4F5
TED_SANITIZER_ANCHOR_9C00_COL_ADDR = 0xC4F6
TED_SANITIZER_ANCHOR_ROW_ADDR = 0xC4FA       # $9C00 physical map
TED_SANITIZER_ANCHOR_COL_ADDR = 0xC4FB       # $9C00 physical map
TED_INCREMENTAL_SIGNATURE_SUM_ADDR = TED_SANITIZER_ANCHOR_ROW_ADDR
TED_INCREMENTAL_SIGNATURE_ODD_ADDR = TED_SANITIZER_ANCHOR_COL_ADDR
TED_INCREMENTAL_WRITER_RUNTIME_ADDR = 0xC500
TED_INCREMENTAL_WRITER_SOURCE_ADDR = TED_SANITIZER_ROW_TABLE_ADDR
TED_INCREMENTAL_INSTALL_CONT_ADDR = TED_SANITIZER_CROWN_ADDR
# Writer-mirror mode exclusively owns the canary-proven C500 page. Ted's
# activation clear explicitly zeros C400, while the 2,800-frame receipt shows
# C500 survives. Its two
# compact 12x12 metatile dirty maps are always-addressable, so the native
# writer never switches SVBK on its hot path. The legacy sanitizer constants
# below overlap its tail, but those architectures are mutually exclusive.
TED_WRITER_RUNTIME_ADDR = 0xC500
TED_WRITER_CLEAR_RUNTIME_ADDR = 0xC594
TED_WRITER_MASK_TABLE_ADDR = 0xC5AD
TED_WRITER_DIRTY_9800_ADDR = 0xC5B5
TED_WRITER_DIRTY_9C00_ADDR = 0xC5D9
TED_WRITER_START_D_ADDR = 0xC5FD
TED_WRITER_START_E_ADDR = 0xC5FE
TED_WRITER_RUNTIME_SENTINEL_ADDR = 0xC5FF
TED_WRITER_RUNTIME_SENTINEL_VALUE = 0x01
TED_WRITER_RUNTIME_LIMIT_ADDR = TED_WRITER_CLEAR_RUNTIME_ADDR
TED_WRITER_BITMAP_SIZE = 36
TED_WRITER_CLEAR_GATE_ADDR = 0x6FE4
TED_WRITER_FIXED_STUB_ADDR = 0x0838
TED_CACHED_FIXED_CONT_ADDR = 0x0838
TED_WRITER_ROM_RUNTIME_ADDR = 0x7687
TED_WRITER_BANKED_DIRTY_ADDR = 0xD300
TED_WRITER_BANKED_SCRATCH_ADDR = 0xD324
TED_WRITER_INVALIDATE_MAP_ADDR = 0x578C
TED_WRITER_POINTER_ADVANCE_ADDR = 0x539E
TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR = 0x55D8
TED_CHECKER_ATTR_HELPER_ADDR = TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR
TED_REGISTER_MATERIALIZER_FRONT_ADDR = TED_SANITIZER_ANCHOR_PACK_ADDR
TED_REGISTER_MATERIALIZER_TAIL_ADDR = 0x539E
TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR = 0x5460
TED_DIRTY_POSTCOPY_MAIN_ADDR = TED_SANITIZER_GEOMETRY_CONT_ADDR + 1
TED_DIRTY_POSTCOPY_SCAN_ADDR = 0x6D4E
TED_DIRTY_POSTCOPY_SCAN_TAIL_ADDR = 0x6150
TED_DIRTY_POSTCOPY_SETUP_ADDR = 0x5890
TED_DIRTY_POSTCOPY_BYTE_ADDR = TED_SANITIZER_ANCHOR_PACK_ADDR
TED_DIRTY_POSTCOPY_BIT_ADDR = 0x5D4C
TED_DIRTY_POSTCOPY_BIT_CONT_ADDR = 0x5D7F
TED_DIRTY_POSTCOPY_BIT_TAIL_ADDR = 0x6250
TED_DIRTY_POSTCOPY_ADVANCE_ADDR = 0x5830
TED_DIRTY_POSTCOPY_ADVANCE_CONT_ADDR = 0x5860
TED_DIRTY_POSTCOPY_COMPILE_ADDR = 0x5340
TED_DIRTY_POSTCOPY_COMPILE_TAIL_ADDR = 0x623C
TED_DIRTY_POSTCOPY_COMPILE_BOTTOM_ADDR = 0x6180
TED_DIRTY_POSTCOPY_COMPILE_FINAL_ADDR = 0x6268
TED_DIRTY_POSTCOPY_FINAL_FRONT_ADDR = 0x56FF
TED_DIRTY_POSTCOPY_FINAL_ADDR = TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR
# Two lazy-installer fragments each leave a verified nine-byte tail. The crown
# pair validator is split across them so the active WRAM helper does not grow.
TED_CROWN_PAIR_HELPER_ADDR = TED_SANITIZER_INSTALL_MIDDLE_ADDR + 27
TED_CROWN_PAIR_HELPER_CONT_ADDR = TED_SANITIZER_INSTALL_TAIL_ADDR + 27
TED_POSTCOPY_ATTR_COMPILER_ADDR = TED_SANITIZER_MAIN_ADDR
TED_POSTCOPY_DISPATCH_ADDR = TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR
TED_POSTCOPY_KEY_SAMPLES = (
    350, 182, 86, 403, 173, 437, 101, 186, 370, 303, 431, 82,
    399, 221, 240, 390, 198, 227, 163, 209, 419, 94, 196, 204,
    244, 564, 464, 144, 443, 374, 150, 14,
)
# Ted exclusively reuses the Stage-1/5 fixed-WRAM cache records while scene
# $10 is active.  Switchable banks 2 and 3 each own D000-D305: the exact
# 24x32 attribute plane plus a compact key and generation commit.
TED_POSTCOPY_PHYSICAL_9800_ADDR = 0xDF53
TED_POSTCOPY_GENERATION_ADDR = 0xDF56
TED_POSTCOPY_PHYSICAL_9C00_ADDR = 0xDF57
TED_POSTCOPY_FIFO_ADDR = 0xDF5A
TED_POSTCOPY_PLANE_KEY_ADDR = 0xD300
TED_POSTCOPY_PLANE_ROLL_ADDR = 0xD301
TED_POSTCOPY_PLANE_GENERATION_ADDR = 0xD302
TED_POSTCOPY_SCENE_DISPATCH_ADDR = TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR
TED_POSTCOPY_SCENE_INIT_ADDR = 0x5340
TED_POSTCOPY_CRYSTAL_REARM_ADDR = 0x539E
# Ted-only incremental-key prototype.  The shared fixed-bank writer remains
# byte-for-byte stock; only the complete map-builder body is cloned into
# volatile SVBK4 and its private tail enters this tracker.
TED_INCREMENTAL_TRACKER_ADDR = 0xD300
TED_INCREMENTAL_TRACKER_EXIT_ADDR = 0xD357
TED_INCREMENTAL_TRACKER_CONT_ADDR = TED_INCREMENTAL_TRACKER_EXIT_ADDR
TED_INCREMENTAL_INIT_ADDR = 0xD360
TED_INCREMENTAL_CLONE_ADDR = 0xD400
TED_INCREMENTAL_MIRROR_ADDR = 0xD000
TED_INCREMENTAL_KEY_ADDR = 0xD240
TED_INCREMENTAL_VALID_ADDR = 0xD244
TED_DIRECT_PLANE_POINTER_TABLE_ADDR = 0xD600
TED_DIRECT_TILE_PLANE_ADDR = 0xD900
TED_INWINDOW_SANITIZER_ADDR = 0xD500
TED_INWINDOW_CLASSIFIER_ADDR = TED_INWINDOW_SANITIZER_ADDR + 10
TED_INWINDOW_MASK_CLASSIFIER_ADDR = TED_INWINDOW_SANITIZER_ADDR + 3
TED_INWINDOW_ROW_TABLE_ADDR = 0xD840
TED_INWINDOW_CURRENT_VALID_ADDR = 0xD85C
TED_INWINDOW_DIRTY_ADDR = 0xD85D
TED_INWINDOW_CURRENT_ROW_ADDR = 0xD85E
TED_INWINDOW_CURRENT_COL_ADDR = 0xD85F
TED_INWINDOW_OLD_VALID_ADDR = 0xD860
TED_INWINDOW_OLD_ROW_ADDR = 0xD861
TED_INWINDOW_OLD_COL_ADDR = 0xD862
TED_INWINDOW_BODY_MASK_ADDR = 0xD863
TED_INWINDOW_BODY_MASK_SIZE = 72
TED_INWINDOW_NEXT_MASK_ADDR = 0xD579
TED_INWINDOW_CANDIDATE_COUNT_ADDR = 0xD840
TED_INWINDOW_CANDIDATE_SOURCE_ADDR = 0xD841
TED_INWINDOW_CANDIDATE_ROW_ADDR = 0xD843
TED_INWINDOW_CANDIDATE_COL_ADDR = 0xD844
TED_INWINDOW_RAW_TILE_PLANE_ADDR = 0xDC00
# Ted's editable body materials end at tile $86.  The remaining $87-$FF LUT
# tail is deliberately neutral and is never a publishable colored material;
# use that otherwise-dead span as the cold source for the private sanitizer.
TED_INWINDOW_SANITIZER_SOURCE_ADDR = 0x7687
TED_INWINDOW_SANITIZER_SOURCE_SIZE = 0x79
TED_INWINDOW_ENVELOPE_FRONT_ADDR = 0x54F2
TED_INWINDOW_ENVELOPE_TAIL_ADDR = 0x5890
TED_INWINDOW_ENVELOPE_FINAL_ADDR = 0x53A5
TED_INWINDOW_ANCHOR_FRONT_ADDR = 0x5D4C
TED_INWINDOW_ANCHOR_TAIL_ADDR = 0x5D7F
TED_INWINDOW_PLANE_SETUP_ADDR = 0x7027
TED_INWINDOW_SANITIZER_FINISH_ADDR = 0x61B0
TED_INWINDOW_EPILOGUE_ADDR = 0x5899
TED_INCREMENTAL_FIXED_COPY_LEAF_ADDR = 0x65D4
TED_INWINDOW_TARGET_H_ADDR = 0xC4FC
TED_INCREMENTAL_READY_ADDR = 0xC5FF
TED_INCREMENTAL_READY_VALUE = 0xFF
# Direct-plane HDMA uses the adjacent architecture-exclusive byte as a
# one-shot selector replay after its cold publication. Writer-mirror mode's
# C5FE record is mutually exclusive with this branch.
TED_HDMA_COLD_REPLAY_ADDR = 0xC5FE
TED_INWINDOW_BANK_HRAM = TED_SANITIZER_TILE_MASK_HRAM
TED_INWINDOW_BLOCKS_HRAM = TED_SANITIZER_COUNTER_HRAM
TED_INWINDOW_DMA_ADDR = 0x578C
TED_INWINDOW_ENTRY_ADDR = 0x5830
TED_INWINDOW_SELECT_ADDR = 0x5860
TED_INWINDOW_SETUP_ADDR = 0x58C0
TED_INWINDOW_INIT_ADDR = 0x6530
TED_INWINDOW_WAIT_ADDR = 0x5E5C
TED_INWINDOW_ROW_ADDR = 0x623C
TED_INWINDOW_FINISH_ADDR = 0x6268
TED_INCREMENTAL_FIXED_RUNTIME_ADDR = 0xC500
TED_INCREMENTAL_FIXED_RUNTIME_SOURCE_ADDR = 0x5552
TED_INCREMENTAL_UNUSED_THUNK_ADDR = 0x064A
TED_INCREMENTAL_UNUSED_WRAPPER_ADDR = 0x02F2
# The incremental architecture retires the old sampled-key classifier records
# and uses their asserted-zero, scene-exclusive caves as cold installer data.
# Keep every byte out of $7200-$7AFF: all nine pages there are live boss LUTs.
TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS = (
    (TED_SANITIZER_CLASSIFY_ADDR, 36),
    (TED_SANITIZER_CROWN_ADDR, 36),
    (TED_SANITIZER_ACTIVE_ADDR, 36),
    (TED_SANITIZER_ROW_TABLE_ADDR, 36),
    (TED_DIRTY_POSTCOPY_SCAN_TAIL_ADDR, 11),
)
TED_INCREMENTAL_PHYSICAL_9800_ADDR = 0xDF53
TED_INCREMENTAL_PHYSICAL_9C00_ADDR = 0xDF58
TED_INCREMENTAL_GENERATION_ADDR = 0xDF5D
TED_INCREMENTAL_INSTALL_FINAL_ADDR = 0x6FFF
TED_INCREMENTAL_LAZY_GATE_ADDR = 0x6290
TED_INCREMENTAL_SCENE_CLEAR_ADDR = TED_DIRTY_POSTCOPY_COMPILE_BOTTOM_ADDR
TED_INCREMENTAL_BANK2_CALL_ADDR = 0x40EF
TED_INCREMENTAL_BANK2_ENTRY_ADDR = 0x7A8C
TED_INCREMENTAL_BANK2_FALLBACK_ADDR = 0x7AAD
TED_INCREMENTAL_BANK2_READY_ADDR = 0x7ABB
TED_DIRECT_SINGLE_WRITER_A_PATCH_ADDR = 0x61DF
TED_DIRECT_SINGLE_WRITER_B_PATCH_ADDR = 0x6219
TED_DIRECT_FIXED_HELPER_ADDR = TED_INCREMENTAL_FIXED_RUNTIME_ADDR + 23
TED_INWINDOW_PRIVATE_CROWN_HELPER_ADDR = 0xD579
TED_INWINDOW_PRIVATE_GEOMETRY_HELPER_ADDR = 0xD863
# Default-off architecture flag. This mode is deliberately fail-closed until
# the D863-D8AA mask has a receipt-qualified SVBK4/5 ownership record and the
# publication repair is assembled; static builders and the model gate may
# still audit the hot fragment without producing a candidate ROM.
TED_INCREMENTAL_CELL_ENV = "PENTA_TED_INCREMENTAL_CELL"
TED_BLOCK_MAJOR_ENV = "PENTA_TED_BLOCK_MAJOR"
TED_INCREMENTAL_CELL_PROTECTED_ROM_RANGES = (
    (0x6D50, 0x6D70, "title footer glyphs"),
    (0x7200, 0x7B00, "arena palette LUTs"),
)
TED_DIRECT_FIXED_HELPER_SOURCE_CHUNKS = (
    # These sanitizer-only records are retired by the direct-plane branch.
    (TED_SANITIZER_ANCHOR_ADDR, 36),
    (TED_SANITIZER_GEOMETRY_CONT_ADDR, 36),
)
# The cache-entry stub is 11 bytes.  The publisher begins immediately after
# it; retaining the former +14 entered three bytes late and skipped XOR A /
# VBK0, turning stale A into shifted GDMA source/destination low bytes.
TED_CACHED_PUBLISH_FRONT_ADDR = TED_REGISTER_MATERIALIZER_FRONT_ADDR + 11
TED_CACHED_PUBLISH_TAIL_ADDR = TED_CHECKER_ATTR_HELPER_ADDR
TED_CACHED_PUBLISH_TAIL_CONT_ADDR = TED_CROWN_PAIR_HELPER_ADDR
TED_CACHED_PUBLISH_TAIL_FINAL_ADDR = TED_CROWN_PAIR_HELPER_CONT_ADDR
TED_CACHED_GDMA_WAIT_ADDR = 0x5E79
TED_CACHED_COLUMN_WRAP_ADDR = 0x5830
TED_CACHED_SPARSE_ENTRY_ADDR = 0x539E
TED_CACHED_SPARSE_RESTORE_ADDR = 0x5460
TED_CACHED_SPARSE_SETUP_ADDR = 0x6530
TED_CACHED_SPARSE_SCAN_ADDR = 0x623C
TED_CACHED_SPARSE_SCAN_TAIL_ADDR = 0x6D4E
TED_CACHED_SPARSE_FILTER_ADDR = 0x7687
TED_CACHED_ATTR_CLEAR_ADDR = 0x76AB
TED_CACHED_CADENCE_DELAY_ADDR = 0x76CA
# The sparse filter ends at $76EA.  Its 22-byte asserted-zero tail reaches
# exactly to (but never into) Troop's $7700 palette table.
TED_CACHED_READY_LATCH_ADDR = 0x76EA
TED_CACHED_SPARSE_OVERLAY_A_ADDR = 0x5890
TED_CACHED_SPARSE_OVERLAY_B_ADDR = 0x58C0
TED_CACHED_SPARSE_OVERLAY_C_ADDR = 0x5D4C
TED_CACHED_SPARSE_OVERLAY_D_ADDR = 0x5D7F
TED_CACHED_SPARSE_OVERLAY_E_ADDR = 0x5860
TED_CACHED_SPARSE_OVERLAY_F_ADDR = 0x5340
TED_CACHED_SPARSE_OVERLAY_G_ADDR = 0x6150
TED_CACHED_SPARSE_OVERLAY_H_ADDR = 0x6250
TED_CACHED_ANCHOR_ROW_ADDR = 0xD706
TED_CACHED_ANCHOR_COL_ADDR = 0xD707
TED_CACHED_LIMB_PHASE_ADDR = 0xD708
TED_CACHED_SPARSE_TILE_ADDR = 0xD70A
TED_CACHED_SPARSE_COUNT_9C_ADDR = 0xD77F
TED_CACHED_SPARSE_COUNT_ADDR = 0xD71F
TED_CACHED_SPARSE_RECORDS_ADDR = 0xD720
TED_CACHED_SPARSE_RECORDS_9C_ADDR = 0xD780
TED_CACHED_ABI_FRONT_ADDR = 0x6E60
TED_CACHED_ABI_TAIL_ADDR = 0x7027
TED_CACHED_BANK1_TAIL_ADDR = 0x7C91
TED_CACHED_BANK1_MAP_ADDR = 0x7CAE
TED_CACHED_RUNTIME_EXTRA_SOURCE_ADDR = TED_TILE_COMMIT_RUNTIME_ADDR
TED_CACHED_INSTALL_EXTRA_ADDR = 0x6FFF
TED_CACHED_GDMA_COMMIT_ADDR = TED_CACHED_INSTALL_EXTRA_ADDR + 12
TED_CACHED_PALETTE_GATE_ADDR = TED_CACHED_ABI_TAIL_ADDR
# Four otherwise-empty 36-byte records and the 34-byte tail of the following
# record hold the arena-only semantic attribute decider.  Keeping it in bank
# 13 avoids displacing the receipt-locked dungeon cache from DA60-DAFF.  The
# shared bank-0 mapper enters these fragments only at the map-copy boundary.
ARENA_ATTR_SEMANTIC_DISPATCH_ADDR = 0x566A
ARENA_ATTR_SEMANTIC_SIG_A_ADDR = 0x569A
ARENA_ATTR_SEMANTIC_SIG_B_ADDR = 0x56CA
ARENA_ATTR_SEMANTIC_COMPARE_ADDR = 0x56FA
ARENA_ATTR_SEMANTIC_CHANGED_ADDR = 0x572C
ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE = 36
ARENA_ATTR_SEMANTIC_RUNTIME_ADDR = 0xDBA4
ARENA_ATTR_SEMANTIC_SENTINEL_ADDR = 0xDBFF
ARENA_ATTR_SEMANTIC_SENTINEL_VALUE = 0xB6
# The retired fixed-position stack helper caves now host a three-fragment
# bank-14 scanner. It follows translated cylinder rows through the north-scroll
# and miniboss handoff without adding another ROM-bank switch.
STAGE1_HAZARD_SCANNER_FRONT_ADDR = STAGE1_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR
STAGE1_HAZARD_SCANNER_MIDDLE_ADDR = 0x618F
STAGE1_HAZARD_SCANNER_TAIL_ADDR = STAGE1_ATOMIC_ATTR_STACK_COPY_ADDR
STAGE1_HAZARD_SCANNER_SEAM_ADDR = 0x6CE9
STAGE1_HAZARD_TRANSITION_REPAIR_ADDR = 0x55C0
STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR = 0x6F68
STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR = 0x62C7
STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR = 0x6D99
STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR = 0x6DB5
STAGE1_HAZARD_START4_HELPER_ADDR = 0x6B60
STAGE1_HAZARD_START4_COL5_ADDR = STAGE1_HAZARD_START4_HELPER_ADDR + 4
STAGE1_HAZARD_START4_EDGE_ADDR = 0x67E4
STAGE1_HAZARD_ROW_FOLD_ADDR = STAGE1_HAZARD_ROW_COMPILER_ADDR
STAGE1_HAZARD_ROW_WRITER_ADDR = STAGE1_HAZARD_ROW_COMPILER_ADDR + 7
# Raw-tile XOR discriminators covered by the moving/stationary/patrol traces
# plus the multi-room corruption routes.  These keys are injective across all
# captured desired-palette layouts and stable across every duplicate raw-tile
# variant in that corpus (Stage 5: 20 layouts/22 variants; Stage 7: 26/28).
# Keep the claim receipt-bounded: unseen room layouts still require a soak.
# Collision-free across every distinct Stage-5 lava plane in the committed
# 8,000-frame, dual-map room-shift trace. The previous five-cell XOR collided
# after the bank-1 $13BE room shifter moved lava through neutral terrain.
LAVA_ATTR_STAGE5_SAMPLES = (1, 165, 201)
LAVA_ATTR_STAGE7_SAMPLES = (6, 69, 169, 452)
# Independent four-cell and three-cell XORs distinguish every semantic
# attribute layout in the Stage 2-7 streaming corpus while fitting the existing two-byte map
# signature records. FFBD is the third component, preventing an equal shifted
# layout in another room from suppressing its first publication.
# Offset 148 is inside Crystal Dragon's four-phase portal scratch and changed
# the cached signature every few frames, recreating the always-atomic timing
# fault. Adjacent 149 is stable across the 720-frame Crystal corpus and keeps
# the established later-stage layout corpus collision-free.
# Two independent raw-layout XORs chosen from the deterministic Stage 2-7
# multi-room corpus plus horizontal/vertical Stage 6 movement.  This six-cell
# key changes for every observed semantic attribute-plane transition while
# avoiding the old key's near-every-copy Stage 6 false positives.  Keep the
# groups separate: the receipt corpus proves this 3+3 partition has no XOR
# cancellation across any required transition.
LATER_ATTR_SIGNATURE_A = (15, 83, 230)
LATER_ATTR_SIGNATURE_B = (250, 337, 433)
# The shared arena cache key is computed by the expansion-bank helper from
# ``arena_semantic_key.py``. Crystal and Ted keep their specialized paths.
PENTA_TILE_RAW_KEY_SAMPLE = 60
OAM_WRAM_BASE = 0xDA00
OAM_PALETTE_LUT_WRAM = 0xD900
OAM_PALETTE_RESOLVER_RUNTIME_ADDR = OAM_WRAM_BASE
OAM_CENTRAL_EMITTER_RUNTIME_ADDR = OAM_WRAM_BASE + 0x21
LAVA_ATTR_STAGE7_RUNTIME_ADDR = OAM_WRAM_BASE + 0x60
# The Stage 7 runtime ends at $DABC. Its tail hosts a common Stage 5/7 scene
# dispatcher followed by the Stage-1 layout cache. Crystal Dragon's body is
# entirely OBJ, so its fixed portal/background can use the signature-cached
# path instead of the always-atomic moving-BG-body path used by eight arenas.
LAVA_ATTR_SCENE_DISPATCH_ADDR = OAM_WRAM_BASE + 0xB9
# The compact dispatcher ends at DAD7. Stage 1 uses the remaining 41 bytes;
# the pickup-first atomic setup rides in the resolver-copy gap at DA13.
STAGE1_ATTR_RUNTIME_ADDR = OAM_WRAM_BASE + 0xD7
# The pickup-first atomic setup rides in the verified resolver-copy gap at
# DA13 instead of competing with the scene runtimes.
STAGE1_ATOMIC_SETUP_ADDR = OAM_WRAM_BASE + 0x13
# SCX XOR DC02 XOR this packed cell distinguishes every desired attribute
# transition in the natural demo, box-scroll, and low-health/miniboss corpora.
# It requests 560 publications for 306 real changes across 743 traced copies,
# instead of degenerating into an every-copy/frame counter. Live long-route,
# pickup, spike, speed, and natural-attract gates remain the authority beyond
# those bounded corpora.
STAGE1_ATTR_TRANSITION_SAMPLES = (49,)
# Each reviewed cylinder room owns one packed tooth sample that cycles through
# all four phases. DC0E supplies the physical-map bit and the room-aware key
# prevents an equal phase in room $02/$12 from hitting the other room's cache.
STAGE1_HAZARD_PHASE_SAMPLE_ROOM12 = 49
STAGE1_HAZARD_PHASE_SAMPLE_ROOM02 = 52
# Two cells retain enough margin in the shortest vertically-scrolled HBlank.
# The three-cell publisher was nearly safe but reproducibly dropped one
# attribute byte from otherwise-correct groups in Stages 2, 4, and 7. The full
# atomic path runs only on changed layouts; unchanged maps keep the stock-width
# four-cell tile-only cadence, and animated hazard rows use the selective
# post-expander service in bank 14.
STAGE1_ATOMIC_GROUP_WIDTH = 3
OAM_WRAM_END_ADDR = OAM_WRAM_BASE + 0x100
OAM_WRAM_SENTINEL_ADDR = 0xDF51
OAM_WRAM_SENTINEL_VALUE = 0xA8
OAM_BOSS_LUT_CACHE_ADDR = 0xDF52
# D880=$00/FFC1=$00 describes both the title and save-present level select.
# The selector publishes an out-of-range palette phase. Stage 1 entry replaces
# it with the normal 0x11 phase, so the marker expires without touching stock
# state or the title/reel counters.
LEVELSEL_ACTIVE_ADDR = PALETTE_PHASE_ADDR
LEVELSEL_ACTIVE_VALUE = 0xA0
# Two 36-byte native-zero records beside the proven level-select stub hold a
# transition-only later-stage pickup publisher. Keeping this out of the
# VBlank/prelude path is intentional: the Stage-1 hazard and lava publishers
# have receipt-locked timing, while the neutral C600 LUT only needs these
# collision-audited semantic entries installed once per stage-family entry.
LATER_PICKUP_HELPER_FRONT_ADDR = 0x53F2
LATER_PICKUP_HELPER_AUX_ADDR = 0x5422
LATER_PICKUP_HELPER_TAIL_ADDR = 0x5484
LATER_PICKUP_HELPER_CAVE_SIZE = 36
LATER_PICKUP_SWEEP_ORDER_ADDR = 0x54B4
STAGE4_MATERIAL_HELPER_ADDR = 0x7C22
STAGE4_MATERIAL_HELPER_CONT_ADDR = 0x7C44
# Filled after build_oam_wram_copy() proves its shortened exact length.
STAGE4_MATERIAL_HELPER_TAIL_ADDR = 0x7CF5
LATER_PICKUP_RARE_ADDR = LATER_PICKUP_HELPER_AUX_ADDR
LATER_PICKUP_HEALTH_ADDR = LATER_PICKUP_RARE_ADDR + 20
LATER_PICKUP_ARROW_ADDR = LATER_PICKUP_HELPER_TAIL_ADDR + 24
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
# The story writer is mapped in bank 13. The unused fixed serial vector maps
# bank 6 and jumps directly into its stock-zero 216-byte cave. Keeping this
# bridge in fixed ROM avoids treating zero-valued live bank-13 list records as
# free space. The bank-6 helper selects one YAML region palette per art cell,
# remaps bank 13, and returns to the bounded VBlank writer.
STORY_REGION_BANK = 6
STORY_REGION_CAVE_START_ADDR = 0x4C54
STORY_REGION_CAVE_END_ADDR = 0x4D2C
# Serial IRQ is disabled in every qualified gameplay receipt (IE=$07). Its
# eight-byte vector is therefore a fixed-bank call bridge, not a live handler.
STORY_REGION_FIXED_BRIDGE_ADDR = 0x0058
# Retain the old same-address bank-6 guard solely for historical states saved
# inside the interrupted wrapper. No bank-13 bytes are installed here.
STORY_REGION_BANK6_GUARD_ADDR = 0x4CED
STORY_REGION_BANK6_RETURN_ADDR = STORY_REGION_BANK6_GUARD_ADDR + 5
# Generated-code padding immediately before the DA60 runtime source holds one
# $6800 source low byte per later dungeon. Unlike the old $4CE4 zero records,
# this range is created and owned by this builder rather than referenced by a
# stock pointer table.
LATER_STAGE_BG0_SOURCE_TABLE_ADDR = 0x7BAC
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
    """Clear the shared LUT without coloring title, splash, or story art."""
    c = bytearray([
        0x21, WRAM_BG_TABLE & 0xFF,
        WRAM_BG_TABLE >> 8,                  # LD HL, palette LUT
        0xAF,                                # XOR A
        0x06, 0x00,                          # LD B,0 (256 iterations)
        0x22, 0x05, 0x20, 0xFC,              # [HL+]=A; DEC B; JR NZ
        0xC9,                                # RET: neutral callers stay neutral
    ])
    assert len(c) == 11
    return bytes(c)


def build_later_stage_pickup_helper() -> tuple[bytes, bytes, bytes, bytes]:
    """Publish stage-specific material and pickup IDs from the capture corpus.

    Stable room captures identify the semantic forms per tileset: Stage 2
    rare/extra-life, Stage 3 health, Stage 4 none, Stage 5 health/rare, Stage 6
    health, and Stage 7 arrow/rare. Stage 4 deliberately avoids its ambiguous
    pickup-looking IDs; instead its collision-free floor and bridge families get
    separate material ramps. Shared structural IDs A5/B9/CF remain excluded.
    Palette slots retain the established YAML semantics: BG1 health, BG2 rare,
    BG4 navigation. Stage 4 loads BG6 stone into its base slot, then assigns
    collision-free floor tiles to BG4 and bridge accents to BG2.

    Only the later-dungeon dispatcher enters the common tail. It arms the
    stage-local BG0 reload, calls the neutral 256-byte clear, and then publishes
    the semantic entries. Title, splash, and story callers return from the
    neutral clear directly, even when FFBA still contains a late-stage number.
    The helper uses only A/HL, both scratch in the replaced table-copy path,
    and returns directly to scene_detect's caller.
    """
    front = _Asm()
    front.db(0xF0, 0xBA, 0x3D)               # Stage 2?
    front.db(0xCA, LATER_PICKUP_RARE_ADDR & 0xFF,
             LATER_PICKUP_RARE_ADDR >> 8)
    front.db(0x3D)                            # Stage 3?
    front.db(0xCA, LATER_PICKUP_HEALTH_ADDR & 0xFF,
             LATER_PICKUP_HEALTH_ADDR >> 8)
    front.db(0x3D)                            # Stage 4?
    front.db(0xCA, STAGE4_MATERIAL_HELPER_ADDR & 0xFF,
             STAGE4_MATERIAL_HELPER_ADDR >> 8)
    front.db(0x3D)
    front.jr(0x28, "health_rare")            # Stage 5
    front.db(0x3D)                            # Stage 6?
    front.db(0xCA, LATER_PICKUP_HEALTH_ADDR & 0xFF,
             LATER_PICKUP_HEALTH_ADDR >> 8)
    front.db(0xCD, LATER_PICKUP_ARROW_ADDR & 0xFF,
             LATER_PICKUP_ARROW_ADDR >> 8)   # Stage 7: arrow + rare
    front.db(0xC3, LATER_PICKUP_RARE_ADDR & 0xFF,
             LATER_PICKUP_RARE_ADDR >> 8)
    front.label("health_rare")
    front.db(0xCD, LATER_PICKUP_HEALTH_ADDR & 0xFF,
             LATER_PICKUP_HEALTH_ADDR >> 8)
    front.db(0xC3, LATER_PICKUP_RARE_ADDR & 0xFF,
             LATER_PICKUP_RARE_ADDR >> 8)
    front_code = front.finish()

    health = bytes([
        0x21, 0x88, WRAM_BG_TABLE >> 8,
        0x3E, 0x01,                           # health -> BG1
        0x22, 0x77,                           # 88,89
        0x2E, 0x96,
        0x77, 0x2C, 0x2C, 0x22, 0x77,         # 96,98,99
        0xC9,
    ])
    arrow = bytes([
        0x3E, 0x04,                           # fat arrow -> BG4
        0x21, 0xA0, WRAM_BG_TABLE >> 8,
        0x22, 0x77,                           # A0,A1
        0x2E, 0xB0, 0x22, 0x77,               # B0,B1
        0xC9,
    ])
    common = bytes([
        0x3E, 0x0B,
        0xEA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        0xCD, UNIFORM_CLEAR_ADDR & 0xFF, UNIFORM_CLEAR_ADDR >> 8,
        0x3E, 0xFF,
        0xEA, (LAVA_ATTR_STAGE5_9800_META_ADDR + 2) & 0xFF,
        (LAVA_ATTR_STAGE5_9800_META_ADDR + 2) >> 8,
        0xEA, (LAVA_ATTR_STAGE5_9C00_META_ADDR + 2) & 0xFF,
        (LAVA_ATTR_STAGE5_9C00_META_ADDR + 2) >> 8,
        0x3E, 0x5A, 0xEA, 0x02, 0xDF,
        0xC3, LATER_PICKUP_HELPER_FRONT_ADDR & 0xFF,
        LATER_PICKUP_HELPER_FRONT_ADDR >> 8,
    ])
    rare = bytes([
        0x21, 0xAE, WRAM_BG_TABLE >> 8,
        0x3E, 0x02,                           # extra life/wildcard -> BG2
        0x22, 0x77,                           # AE,AF
        0x2E, 0xBE, 0x22, 0x77,
        0x2E, 0xC6, 0x22, 0x77,               # C6,C7
        0x2E, 0xD6, 0x22, 0x77,               # D6,D7
        0xC9,
    ])
    # This transition-only writer is split across three exact gaps in the
    # retired position-map region. Keeping the loop intact in its middle
    # fragment makes the two jumps semantically invisible.
    stage4_material = bytes([
        0x21, 0x01, WRAM_BG_TABLE >> 8,
        0x3E, 0x04, 0x06, 0x08,              # 01-08 diamond floor -> BG4
        0xC3, STAGE4_MATERIAL_HELPER_CONT_ADDR & 0xFF,
        STAGE4_MATERIAL_HELPER_CONT_ADDR >> 8,
        0x22, 0x05, 0x20, 0xFC,
        0xC3, STAGE4_MATERIAL_HELPER_TAIL_ADDR & 0xFF,
        STAGE4_MATERIAL_HELPER_TAIL_ADDR >> 8,
        0x2E, 0x2D, 0x3E, 0x02,              # 2D/2E bridge -> BG2
        0x22, 0x77,
        0xC9,
    ])
    aux = rare + health
    tail = common + arrow
    assert len(front_code) <= LATER_PICKUP_HELPER_CAVE_SIZE
    assert len(aux) <= LATER_PICKUP_HELPER_CAVE_SIZE
    assert len(tail) <= LATER_PICKUP_HELPER_CAVE_SIZE
    assert len(stage4_material) == 24
    assert LATER_PICKUP_HEALTH_ADDR == LATER_PICKUP_HELPER_AUX_ADDR + len(rare)
    assert LATER_PICKUP_ARROW_ADDR == LATER_PICKUP_HELPER_TAIL_ADDR + len(common)
    return front_code, aux, tail, stage4_material


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
        0xFE, OAM_WRAM_SENTINEL_VALUE,
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
        0xFE, OAM_WRAM_SENTINEL_VALUE,
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
        0xFE, OAM_WRAM_SENTINEL_VALUE,
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
        0x1E, 0x0A,                         # E = ten cells in this half-row
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
    # the run or the ten-cell half-row finishes.
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
    row_writer.jr(0x28, "done")             # ten-cell half-row is complete
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
        STORY_REGION_BANK6_GUARD_ADDR & 0xFF,
        STORY_REGION_BANK6_GUARD_ADDR >> 8, # FFC1 != 0 -> restore bank 13
        0xC3,
        STORY_REGION_WRITER_ADDR & 0xFF,
        STORY_REGION_WRITER_ADDR >> 8,
    ])
    assert len(landing) == STORY_REGION_LANDING_SIZE
    bank6[return_offset:return_offset + len(landing)] = landing
    # This bank-6 shadow is skipped by production story entry, which resumes
    # at bridge+5. It restores bank 13 for the guarded stale-gameplay landing.
    wrong_bank_guard_offset = (
        STORY_REGION_BANK6_GUARD_ADDR - STORY_REGION_CAVE_START_ADDR
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
        0xC3,
        STORY_REGION_WRITER_ADDR & 0xFF,
        STORY_REGION_WRITER_ADDR >> 8,
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
        "wrong_bank_guard": STORY_REGION_BANK6_GUARD_ADDR,
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

    # Dispatch exact story families and direct-written ending phases. The
    # subtraction ladder is two bytes smaller than five independent compares;
    # those bytes help normalize the stock OPENING route without expanding
    # this exact 256-byte reclaimed table.
    a.db(0xFA, 0x80, 0xD8, 0xB7)             # LD A,[D880]; OR A
    a.jr(0x28, "ending_epilogue")
    a.db(0xD6, 0x15)                         # OPENING becomes zero
    a.jr(0x28, "story_opening")
    a.db(0x3D)                               # ENDING becomes zero
    a.jr(0x28, "ending_credits_or_end")
    a.db(0xD6, 0x03)                         # pre-final becomes zero
    a.jr(0x28, "story_pre_final")
    a.db(0x3D)                               # post-final becomes zero
    a.jr(0x20, "inactive")

    # B carries the exact sequence discriminator into the shared story guard.
    a.label("story_post_final")
    a.db(0x06, 0x05)
    a.jr(0x18, "story_guard")
    a.label("story_opening")
    # OPENING completion restarts through the cold-init path rather than the
    # GAME START selector, so stock leaves DX's live/demo discriminator at 0.
    # A is known zero here: publish the live value before the cold-init routine
    # preserves it into Stage 1, then reuse A=2 as the OPENING sequence guard.
    a.db(0x3C, 0xEA, 0xFD, 0xDC, 0x3C, 0x47)
    a.jr(0x18, "story_guard")
    a.label("story_pre_final")
    a.db(0x06, 0x04)

    a.label("story_guard")
    a.db(0xFA, 0xE8, 0xDC, 0xB8)            # DCE8 == B
    a.jr(0x20, "inactive")
    a.db(0xFA, 0xEA, 0xDC, 0x3D)            # DCEA == 1
    a.jr(0x20, "inactive")
    a.db(0xFA, 0xF0, 0xDC, 0x3D, 0xFE, 0x07)
    a.jr(0x30, "inactive")                  # reject original IDs 0 or >= 8
    a.db(0x3C, 0x4F)                        # C = original DCF0 art ID
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

    # Any unclassified scene clears the page cache. A later page with the same
    # palette ID therefore starts at row zero instead of inheriting a done row.
    a.label("inactive")
    a.db(
        0xC3,
        STORY_INACTIVE_HELPER_ADDR & 0xFF,
        STORY_INACTIVE_HELPER_ADDR >> 8,
    )

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
        STORY_REGION_FIXED_BRIDGE_ADDR & 0xFF,
        STORY_REGION_FIXED_BRIDGE_ADDR >> 8,
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
    """Dispatch art half-rows and expose a shared neutral lower-panel tail."""
    code = bytes([
        0xFE, 0x10,                         # one 8-row * 2-half-row art pass
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
    """Map the art counter to rows 0..7 and offsets 0/10."""
    code = bytes([
        0xE6, 0x08,                         # half-row bit from counter
        0x0F, 0x57,                         # A/D = 0/4
        0x0F, 0x0F,                         # A = 0/1
        0x82, 0x87,                         # A = (0/1 + 0/4) * 2 = 0/10
        0x57,                               # D = cell offset
        0x78, 0xE6, 0x07, 0x47,             # B = visible row
        0xC3, row_entry_addr & 0xFF, row_entry_addr >> 8,
    ])
    assert len(code) == 16
    return code


def build_story_separator_helper(row_entry_addr: int) -> bytes:
    """Re-arm a completed story pass if stock redraws its attribute plane.

    Every committed story mask colors all 160 cells in the upper art panel,
    so $9821 is a reliable nonzero sentinel for both observed 0/0 and 8/8
    viewports.  Stock can redraw the same DCF0/DD07 art page without changing
    either identity byte; that late redraw writes palette zero and previously
    left the DX pass dormant at DF4A=$20 or above.  Check the sentinel after
    the first complete art pass and restart at row zero only when it was
    cleared.  The entry neutral cleaner and neutral C600 story table continue
    to own the dialogue rows.
    """
    code = bytes([
        0xF0, 0x4F, 0xF5,                   # preserve VBK
        0x3E, 0x01, 0xE0, 0x4F,             # inspect attributes
        0xFA, 0x21, 0x98, 0xE6, 0x07,       # $9821 palette sentinel
        0x47, 0xF1, 0xE0, 0x4F,             # B=result; restore VBK
        0x78, 0xB7, 0xC0,                   # nonzero -> remain dormant
        0xAF,
        0xEA, STORY_ATTR_ROW_ADDR & 0xFF,
        STORY_ATTR_ROW_ADDR >> 8,           # cleared -> restart next VBlank
        0xC9,
        0x00, 0x00,                         # retain exact 26-byte allocation
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
        0xFE, OAM_WRAM_SENTINEL_VALUE,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
    )
    a.db(0xC9)

    a.label("spotlight")
    a.db(
        0xFA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xFE, OAM_WRAM_SENTINEL_VALUE,
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
            0xFE, OAM_WRAM_SENTINEL_VALUE,
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
        0xFE, OAM_WRAM_SENTINEL_VALUE,
        0xC4, OAM_WRAM_COPY_ADDR & 0xFF, OAM_WRAM_COPY_ADDR >> 8,
    )
    # Stage 1 owns attrs in the atomic/direct publishers, so route only its
    # exact scene to the cold-entry gate. The former `SUB $0A; JP C` admitted
    # every dungeon scene $02-$09 and silently discarded Stage 2-7 native
    # room-rearm markers. That left the initial Stage 5/7 lava plane behind
    # while later rooms streamed new tiles through it. D880=$0A is shared by
    # prerecorded Gargoyle and historical live Shield states; the adjacent
    # dispatcher uses DCFD to clear the former and run the two-map row helper
    # for the latter. Every other scene owns a complete post-copy publisher.
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x02)
    a.db(
        0xCA,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR & 0xFF,
        ATTRACT_PICKUP_SWEEP_STUB_ADDR >> 8,
    )                                      # JP Z: initial Stage-1 sweep gate
    # Every non-Stage-1 scene now owns a complete post-copy attribute
    # publisher.  Retaining the legacy C600 row sweep for later dungeons raced
    # that publisher with stale source data (most visibly in Stage 4).  Keep
    # the dead standard-repair body at its receipt-locked address for binary
    # layout stability, but route every non-Stage-1 scene directly to clear.
    a.db(
        0xC3,
        ROOM_BG_REPAIR_CLEAR_ADDR & 0xFF,
        ROOM_BG_REPAIR_CLEAR_ADDR >> 8,
        0x00,
    )
    a.label("pending")
    assert (
        ROOM_BG_REPAIR_ADDR + len(a.code)
        == ROOM_BG_REPAIR_STANDARD_ADDR
    )
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xB7, 0xC8,                        # no pending rows -> RET Z
        0x3D,
        0xC3,
        LATER_PICKUP_SWEEP_ORDER_ADDR & 0xFF,
        LATER_PICKUP_SWEEP_ORDER_ADDR >> 8,
    )                                      # store count; tail-call one row
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
    """Store one decremented cold-entry row and tail to the safe BG sweep."""
    return bytes([
        0xEA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8,
    ])


def build_later_pickup_sweep_order() -> bytes:
    """Prioritize pickup-bearing rows during later-stage room repair.

    A enters as the decremented 17..0 repair count. The normal BG sweep
    increments DF04 before selecting its row. The base `(count+8) mod 18`
    order is 8,7,6,5,4; swapping seed values 3/4 visits rows 8,7,6,4,5
    instead. That closes the one-frame Stage-7 row-4 seam exposed only by a
    headed screenshot run, then completes the remaining 13 rows exactly once.
    FFBA=0 and out-of-range users retain the established DF04 cursor.
    """
    a = _Asm()
    a.db(0xEA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8)
    a.db(0xF0, 0xBA, 0x3D, 0xFE, 0x06)
    a.jr(0x30, "sweep")
    a.db(
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xD6, 0x0A,
    )
    a.jr(0x30, "row_ready")
    a.db(0xC6, 0x12)
    a.label("row_ready")
    a.db(0xFE, 0x03)
    a.jr(0x38, "store")
    a.db(0xFE, 0x05)
    a.jr(0x30, "store")
    a.db(0xEE, 0x07)                    # seeds 3/4 -> 4/3
    a.label("store")
    a.db(0xEA, 0x04, 0xDF)
    a.label("sweep")
    a.db(0xC3, BG_SWEEP_ADDR & 0xFF, BG_SWEEP_ADDR >> 8)
    code = a.finish()
    assert len(code) <= LATER_PICKUP_HELPER_CAVE_SIZE
    return code


def build_attract_pickup_sweep_dispatcher() -> bytes:
    """Admit only the high-bit-tagged cold Stage-1 attribute repair.

    Native room-change rearm values are below $80 and return immediately.
    The exact D880=$02 scene transition publishes the reserved waiting tag
    $7F after native room rearm. Completion of the third immutable bank-1 art
    upload promotes it to $92; eighteen active-map rows then cover the complete
    viewport and finish at $80. Because $80 differs from the waiting tag, a
    later hazard/miniboss refresh cannot re-arm an already-completed sweep.
    Scene $0A bypasses this helper so a broad LUT sweep can never clear the
    cylinder's immutable VRAM-bank bit.
    """
    code = bytes([
        0xFA, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xFE, 0x81,
        0xD8,                               # RET C: room rearm / upload wait
        0x3D,                               # one cold-entry row consumed
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
# boundaries. Seven NOPs (28 CPU cycles) after each completed dual-map pickup
# write produce 2,000 Stage-1 frames and 418 Gargoyle frames versus 1,856/395
# in the unmodified ROM with the collision-free live/demo transition key and
# all semantic pickups present. Both segments pass their independent timing
# envelopes; the nearby five-NOP phase made the Gargoyle segment take 523.
# Keep this named and guarded by the title-reel and attract-pickup receipts
# rather than hiding the alignment in an unrelated helper.
DEMO_PICKUP_WRITER_PHASE_NOPS = 7


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
        0xFA, 0xFD, 0xDC, 0xB7,
    )
    append.jr(0x28, "demo_phase_only")
    append.db(
        0x7B,
        0xCD,
        DEMO_PICKUP_DIRECT_WRITER_ADDR & 0xFF,
        DEMO_PICKUP_DIRECT_WRITER_ADDR >> 8,
    )
    append.jr(0x18, "done")
    append.label("demo_phase_only")
    append.db(
        0x7B,
        0xCD,
        DEMO_PICKUP_PHASE_WRITER_ADDR & 0xFF,
        DEMO_PICKUP_PHASE_WRITER_ADDR >> 8,
    )
    append.label("done")
    append.db(0xD1, 0xC1, 0xC9)
    append_code = append.finish()
    assert len(append_code) <= 0x6F8B - DEMO_PICKUP_APPENDER_ADDR
    assert len(DEMO_PICKUP_METATILE_PALETTES) == 24
    return scan_code, append_code, DEMO_PICKUP_METATILE_PALETTES


def build_demo_pickup_writer(
    phase_nops: int = DEMO_PICKUP_WRITER_PHASE_NOPS,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Build live writes and a cycle-exact demo no-write twin.

    Live Shield fixtures still need the sparse 2x2 dual-map write. The demo's
    full cached attribute copier owns its VRAM, but the prerecorded input
    stream still needs the original two-HBlank cadence. Its twin replaces
    each net-HL-neutral four-byte store group with ``LD A,B; INC SP; DEC SP;
    NOP``: identical byte count and cycles, no memory write, no flag change.
    """
    assert 0 <= phase_nops <= 7
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
        *bytes(phase_nops),
        0xAF, 0xE0, 0x4F,
        0xC9,
    )
    tail_code = tail.finish()

    write_group = bytes([0x78, 0x22, 0x77, 0x2D])
    no_write_group = bytes([0x78, 0x33, 0x3B, 0x00])
    phase_front = bytearray(front_code)
    phase_tail = bytearray(tail_code)
    assert phase_front.count(write_group) == 2
    assert phase_tail.count(write_group) == 2
    phase_front = phase_front.replace(write_group, no_write_group)
    phase_tail = phase_tail.replace(write_group, no_write_group)
    # The appender's DCFD load/OR/taken-JR costs 32 cycles before this demo
    # twin. Remove exactly 32 dead coordinate-setup cycles so its first STAT
    # poll lands at the same phase as the original direct writer on both
    # emulator cores. These registers feed only addresses on the write path.
    dead_coordinate_prefix = bytes.fromhex("57 E6 0F 87 5F 7A CB 37")
    assert phase_front.startswith(dead_coordinate_prefix)
    del phase_front[:len(dead_coordinate_prefix)]
    assert phase_front[-3] == 0xC3
    phase_front[-2:] = bytes([
        DEMO_PICKUP_PHASE_WRITER_TAIL_ADDR & 0xFF,
        DEMO_PICKUP_PHASE_WRITER_TAIL_ADDR >> 8,
    ])
    assert len(front_code) <= 0x67F3 - DEMO_PICKUP_DIRECT_WRITER_ADDR
    assert (
        DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR + len(tail_code)
        <= DEMO_PICKUP_PHASE_WRITER_TAIL_ADDR
    )
    assert len(phase_front) <= 0x6B77 - DEMO_PICKUP_PHASE_WRITER_ADDR
    assert len(phase_tail) <= 0x6883 - DEMO_PICKUP_PHASE_WRITER_TAIL_ADDR
    return front_code, tail_code, bytes(phase_front), bytes(phase_tail)


def build_room_bg_rearm_bank0(rows: int = BG_SWEEP_REARM_ROWS) -> bytes:
    """Preserve stock ``LDH [FFBD],A`` and arm an 18-row BG repair.

    Each native FFBD store is replaced by the two-byte ``RST $00; NOP``.
    The eight-byte vector performs the stock store, saves AF, loads ``rows``,
    and jumps here. DF4F's pending marker is part of later-stage load
    synchronization: the per-frame lava override promotes it only after the
    scene table is ready, preventing a premature attribute-plane commit.
    """
    return bytes([
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
    assert rom[0x0000:0x0008] == vanilla[0x0000:0x0008]
    rom[0x0000:0x0008] = bytes([
        0xE0, 0xBD,                         # stock LDH [FFBD],A
        0xF5,                               # preserve A and flags
        0x3E, BG_SWEEP_REARM_ROWS,
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
    # A6 is published before the native tile buffer is ready, but later-stage
    # scrolling can retain it through every completed $42A7 map publication.
    # Returning here made Stage 5/7 take the tile-only branch throughout room
    # shifts and left the old lava plane visible for the 18-row fallback sweep.
    # Compare the actual completed source and per-map room metadata instead.
    # An early/pre-shift call may publish the old plane once; the changed
    # signature on the completed call then requests the new plane atomically.
    a.jr(0x28, "compare")
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
    """Enter the bank-13 dungeon/arena semantic dispatcher.

    The bank-14 same-address entry still owns Stage-1 hazards. Bank 13 can
    reach the larger arena decider through native-zero resource padding, so
    this receipt-locked 22-byte slot only needs a tail jump.
    """
    code = build_arena_postcopy_dispatcher()
    # The generated padding immediately before the Stage-7 source now owns
    # the later-stage BG0 selector table.  Stop at that explicit allocation;
    # zero-valued bytes elsewhere are not evidence of free space.
    capacity = LATER_STAGE_BG0_SOURCE_TABLE_ADDR - LAVA_ATTR_DECIDER_ADDR
    assert len(code) <= capacity
    return code + bytes(capacity - len(code))


def build_arena_attr_semantic_runtime() -> bytes:
    """Skip only receipt-proven exact arena publications.

    Crystal Dragon retains its ghost/translucency cache and Ted's private
    post-copy compiler owns its attributes. Every other arena maps the
    expansion-bank decider. Two semantic sums guard the attribute plane; a
    third raw-layout sum permits the old whole-publication
    speed path only when the tile plane is also identical.
    """
    a = _Asm()
    a.db(
        0xE5,                               # preserve destination HL
        0x54,                               # D = destination H
        0xFA, 0x80, 0xD8, 0x5F,            # E = exact arena scene
    )
    # Intermediate $44xx calls are sanitizer/source work, not physical BG-map
    # publications. Ted's private post-copy compiler owns scene $10.
    a.db(0x7A, 0xFE, 0x44)
    a.jr(0x28, "pure_intermediate")
    a.db(0x7B, 0xFE, 0x10)
    a.jr(0x28, "pure_intermediate")

    # WRAM execution survives ROM-bank changes. Stock $0061 updates FF99 and
    # the MBC5 register without clobbering BC/DE/HL or flags. The fused
    # Shalamar path also maps WRAM bank 3 while it prepares the attribute
    # plane, so keep interrupts out of this bounded critical section: the
    # native ISR assumes bank 1 and would otherwise write live game state into
    # the staging plane.
    a.db(
        0xF3,
        0xF0, 0x99, 0xF5,
        0x3E, ARENA_ATTR_KEY_HELPER_BANK,
        0xCD, 0x61, 0x00,
        0xCD, ARENA_ATTR_KEY_HELPER_ADDR & 0xFF,
        ARENA_ATTR_KEY_HELPER_ADDR >> 8,
        0x67,                               # H = helper decision 0/1/2/3
        0xF1, 0xCD, 0x61, 0x00,
        0xFB,
        0x7C, 0xE0, 0xE0, 0xB7,             # publish decision for inline path
    )
    a.jr(0x28, "exact_hit")
    a.db(0xFE, 0x02)
    a.jr(0x28, "raw_only")
    # A=1 rebuilds and publishes the prepared attribute plane. A=3 means the
    # Shalamar helper also prepared a plane while sanitizing its source, but
    # the generic compiler remains the safe publication contract.  In
    # particular, B is live native-copy state here; the rejected fused-path
    # latch in B.6 corrupted Riff, Troop, Faze, Angela, and Penta geometry.
    # Treat both nonzero/non-raw decisions alike, matching the receipt-proven
    # v78 path. Explicitly establish NZ for the caller's atomic attr branch.
    a.db(0x3E, 0x01, 0xB7, 0xE1, 0xC9)
    a.label("raw_only")
    a.db(0xAF, 0xE1, 0xC9)
    a.label("exact_hit")
    a.db(0xE1, 0xF1, 0xF1, 0xC9)
    a.label("pure_intermediate")
    a.db(0xAF, 0xE1, 0xC9)                # execute ordinary pure copy (Z)
    code = a.finish()
    # Keep the receipt-proven 77-byte installed image.  The zero tail is
    # intentional: state-based testing can carry a longer experimental helper
    # in WRAM, and copying only the shortened executable would leave stale
    # fused-path opcodes reachable after an interrupted return.  The v78
    # installer always overwrites this complete bounded slot.
    installed_length = 77
    assert len(code) <= installed_length
    code += bytes(installed_length - len(code))
    assert len(code) <= (
        ARENA_ATTR_SEMANTIC_SENTINEL_ADDR
        - ARENA_ATTR_SEMANTIC_RUNTIME_ADDR
    )
    return code


def build_ted_incremental_signature_writer() -> bytes:
    """Replace the writer ending at $3127 with incremental raw checksums.

    The native triplet is ``LD A,(HL+); LD (DE),A; INC DE``; its following
    ``POP BC`` remains in fixed ROM. This helper preserves that ABI and updates
    two order-independent deltas: all
    writes, and odd-address writes.  An arbitrary pre-entry offset cancels in
    equality comparisons, so no full-plane initialization pass is required.
    """
    a = _Asm()
    a.db(
        0x2A, 0xE5, 0x67, 0x1A, 0x6F, 0x7C, 0x12,
                                                # native read/write; H=new,L=old
        0x95, 0x47,                          # B=new-old
        0xFA, TED_INCREMENTAL_SIGNATURE_SUM_ADDR & 0xFF,
        TED_INCREMENTAL_SIGNATURE_SUM_ADDR >> 8,
        0x80,
        0xEA, TED_INCREMENTAL_SIGNATURE_SUM_ADDR & 0xFF,
        TED_INCREMENTAL_SIGNATURE_SUM_ADDR >> 8,
        0xCB, 0x43,                          # odd destination address?
    )
    a.jr(0x28, "done")
    a.db(
        0xFA, TED_INCREMENTAL_SIGNATURE_ODD_ADDR & 0xFF,
        TED_INCREMENTAL_SIGNATURE_ODD_ADDR >> 8,
        0x80,
        0xEA, TED_INCREMENTAL_SIGNATURE_ODD_ADDR & 0xFF,
        TED_INCREMENTAL_SIGNATURE_ODD_ADDR >> 8,
    )
    a.label("done")
    a.db(0x7C, 0xE1, 0x13, 0xC9)
    code = a.finish()
    assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return code


def build_ted_incremental_signature_installer() -> bytes:
    """Scene-change dispatcher for Crystal rearm and Ted helper install."""
    helper = build_ted_incremental_signature_writer()
    a = _Asm()
    a.db(0xFE, CRYSTAL_DRAGON_SCENE)
    a.jr(0x28, "crystal")
    a.db(0xFE, 0x10, 0xC0)                 # preserve A outside Ted
    a.db(
        0x21, TED_INCREMENTAL_WRITER_SOURCE_ADDR & 0xFF,
        TED_INCREMENTAL_WRITER_SOURCE_ADDR >> 8,
        0x11, TED_INCREMENTAL_WRITER_RUNTIME_ADDR & 0xFF,
        TED_INCREMENTAL_WRITER_RUNTIME_ADDR >> 8,
        0x01, len(helper), 0x00,
        0xCD, 0xB3, 0x09,
        0x3E, 0x10, 0xC9,
    )
    a.label("crystal")
    a.db(0x21, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
         0x36, 0x11, 0x3E, CRYSTAL_DRAGON_SCENE, 0xC9)
    code = a.finish()
    assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return code


def build_ted_full_source_tracker() -> tuple[bytes, bytes, bytes]:
    """Delta-update Ted's exact four-class source key in volatile SVBK4.

    The private cloned writer enters once after each completed 2x2 write with
    DE restored to its top-left source cell.  D000-D23F is an exact prior
    source mirror and D240-D244 owns four additive class sums plus validity.
    ``class=(index^(index>>5))&3`` is collision-free across the archived Ted
    corpus and needs no multiplication.  The fixed-bank writer is untouched.
    """
    if _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1":
        return build_ted_direct_plane_writer()

    a = _Asm()
    a.db(0xF3, 0xF5, 0xD5, 0xE5)           # DI; preserve native AF/DE/HL
    a.db(0xFA, TED_INCREMENTAL_VALID_ADDR & 0xFF,
         TED_INCREMENTAL_VALID_ADDR >> 8, 0xB7)
    a.jr(0x28, "finish")
    a.db(0x62, 0x6B, 0x01, 0x60, 0x0E, 0x09)  # HL=DE+$0E60 mirror
    cell_calls: list[int] = []
    for index in range(4):
        cell_calls.append(len(a.code))
        a.db(0xCD, 0x00, 0x00)
        if index != 3:
            a.db(0x13, 0x23)
        if index == 1:
            # Both pointers are now top-left+2; advance to next row (+22).
            a.db(0x01, 0x16, 0x00, 0x09,
                 0x7B, 0xC6, 0x16, 0x5F)
            a.jr(0x30, "de_row_ready")
            a.db(0x14)
            a.label("de_row_ready")
    a.label("finish")
    a.db(0xE1, 0xD1, 0xF1,
         0xC3, TED_INCREMENTAL_TRACKER_EXIT_ADDR & 0xFF,
         TED_INCREMENTAL_TRACKER_EXIT_ADDR >> 8)
    a.label("cell")
    cell_addr = TED_INCREMENTAL_TRACKER_ADDR + len(a.code)
    a.db(
        0x1A, 0x47, 0x7E, 0xB8, 0xC8,     # new B; old A; RET Z
        0x4F, 0x70, 0x78, 0x91, 0x47,     # mirror=new; B=delta
        0xE5, 0x7D, 0x4F, 0xCB, 0x37, 0x0F,
        0xA9, 0xE6, 0x03, 0xC6,
        TED_INCREMENTAL_KEY_ADDR & 0xFF,
        0x6F, 0x26, TED_INCREMENTAL_KEY_ADDR >> 8,
        0x7E, 0x80, 0x77, 0xE1, 0xC9,
    )
    tracker = bytearray(a.finish())
    for offset in cell_calls:
        tracker[offset + 1:offset + 3] = bytes(
            [cell_addr & 0xFF, cell_addr >> 8]
        )
    assert (
        TED_INCREMENTAL_TRACKER_ADDR + len(tracker)
        <= TED_INCREMENTAL_TRACKER_EXIT_ADDR
    ), len(tracker)
    # The unbanked C500 caller restores SVBK1 before enabling interrupts.
    # The hook replaces stock $3136 after $3134/$3135 have already popped
    # HL/DE.  Reproduce only the displaced POP BC / INC DE / INC DE / RST /
    # RET tail; extra pops here cross the caller's banked stack.
    continuation = bytes.fromhex("C1 13 13 EF C9 00 00 00 00")
    return bytes(tracker), b"", continuation


def build_ted_direct_plane_writer() -> tuple[bytes, bytes, bytes]:
    """Maintain Ted's padded tile and attribute planes at the private tail.

    A cold-built pointer table converts the native packed C1A0 top-left DE
    directly to its padded D000 destination.  This avoids an old-value mirror,
    checksum deltas, and the post-copy 24x24 compiler: each completed native
    2x2 write performs exactly four C600 lookups and four plane stores.
    """
    a = _Asm()
    a.db(0xF3, 0xF5, 0xD5, 0xE5)          # DI; exact AF/DE/HL
    a.db(
        0x62, 0x6B,                        # HL = packed top-left DE
        0x01,
        (TED_DIRECT_PLANE_POINTER_TABLE_ADDR - 0xC1A0) & 0xFF,
        (TED_DIRECT_PLANE_POINTER_TABLE_ADDR - 0xC1A0) >> 8,
        # The table has one 16-bit pointer per even-column 2x2 top-left.
        # Its byte offset therefore equals the packed source offset here.
        0x09,                              # HL = D600 + (DE-C1A0)
        0x4E, 0x23, 0x46,                 # BC = padded destination
        0x60, 0x69, 0x7C, 0xC6, 0x09, 0x67,
                                            # HL = matching D900 tile cell
    )

    def cell(*, advance: bool) -> None:
        a.db(0x1A)
        if advance:
            a.db(0x13)
        a.db(
            0x22, 0xE5,
            0x6F, 0x26, WRAM_BG_TABLE >> 8, 0x7E,
            0x02, 0xE1,
        )
        if advance:
            a.db(0x03)

    cell(advance=True)
    cell(advance=True)
    # DE has advanced two packed cells; BC two padded cells. Move each to the
    # next row while preserving carries at C1FF/D0FF boundaries.
    a.db(0x7B, 0xC6, 0x16, 0x5F)
    a.jr(0x30, "source_row")
    a.db(0x14)
    a.label("source_row")
    a.db(0x79, 0xC6, 0x1E, 0x4F)
    a.jr(0x30, "plane_row")
    a.db(0x04)
    a.label("plane_row")
    a.db(0xC5, 0x01, 0x1E, 0x00, 0x09, 0xC1)
    cell(advance=True)
    cell(advance=False)
    a.db(
        0xE1, 0xD1, 0xF1,
        0xC3, TED_INCREMENTAL_TRACKER_EXIT_ADDR & 0xFF,
        TED_INCREMENTAL_TRACKER_EXIT_ADDR >> 8,
    )
    tracker = a.finish()
    assert len(tracker) <= (
        TED_INCREMENTAL_TRACKER_EXIT_ADDR - TED_INCREMENTAL_TRACKER_ADDR
    ), len(tracker)
    tracker += bytes(
        TED_INCREMENTAL_TRACKER_EXIT_ADDR
        - TED_INCREMENTAL_TRACKER_ADDR - len(tracker)
    )
    continuation = bytes.fromhex("C1 13 13 EF C9 00 00 00 00")
    return tracker, b"", continuation


def build_ted_full_source_initializer() -> bytes:
    """Create the exact SVBK4 mirror/key at the first Ted publication."""
    if _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1":
        a = _Asm()
        # Clear both padded planes, including all eight row-padding columns,
        # before the direct writer starts filling visible cells.
        a.db(
            0x21, 0x00, 0xD0, 0x01, 0x00, 0x03, 0xAF,
            0xCD, 0xA8, 0x09,
            # Memset returns HL=D300, BC=0, A=0. Reuse L/A and only replace
            # H/BC for the discontiguous D900 tile plane; this keeps the live
            # initializer out of the installer's historical padding chunk.
            0x26, TED_DIRECT_TILE_PLANE_ADDR >> 8,
            0x01, 0x00, 0x03, 0xCD, 0xA8, 0x09,
            0x21, TED_DIRECT_PLANE_POINTER_TABLE_ADDR & 0xFF,
            TED_DIRECT_PLANE_POINTER_TABLE_ADDR >> 8,
            0x11, 0x00, 0xD0,
            0x06, 0x18,
        )
        a.label("row")
        a.db(0x0E, 0x0C)
        a.label("cell")
        a.db(0x7B, 0x22, 0x7A, 0x22, 0x13, 0x13, 0x0D)
        a.jr(0x20, "cell")
        a.db(0x7B, 0xC6, 0x08, 0x5F)
        a.jr(0x30, "row_ready")
        a.db(0x14)
        a.label("row_ready")
        a.db(0x05)
        a.jr(0x20, "row")
        if _os.environ.get("PENTA_TED_INWINDOW_GDMA", "0") == "1":
            # The original runtime source allocation ends with eleven zero
            # bytes. Replacing RET with this single fixed-size copy installs
            # the geometry sanitizer in each selected private bank without
            # growing or perturbing the fragmented scene installer.
            a.db(
                0x21, TED_INWINDOW_SANITIZER_SOURCE_ADDR & 0xFF,
                TED_INWINDOW_SANITIZER_SOURCE_ADDR >> 8,
                0x11, TED_INWINDOW_SANITIZER_ADDR & 0xFF,
                TED_INWINDOW_SANITIZER_ADDR >> 8,
                # The pointer-table loop exits with B=C=0; only C changes.
                0x0E, TED_INWINDOW_SANITIZER_SOURCE_SIZE,
                0xCD, 0xB3, 0x09,
            )
        a.db(0xC9)
        return a.finish()

    a = _Asm()
    a.db(0xFA, TED_INCREMENTAL_VALID_ADDR & 0xFF,
         TED_INCREMENTAL_VALID_ADDR >> 8, 0xB7, 0xC0)
    a.db(0x21, TED_INCREMENTAL_KEY_ADDR & 0xFF,
         TED_INCREMENTAL_KEY_ADDR >> 8, 0xAF,
         0x22, 0x22, 0x22, 0x22)
    a.db(0x11, 0xA0, 0xC1,
         0x21, TED_INCREMENTAL_MIRROR_ADDR & 0xFF,
         TED_INCREMENTAL_MIRROR_ADDR >> 8,
         0x01, 0x40, 0x02)
    a.label("cell")
    a.db(
        0xC5, 0x1A, 0x47, 0x22,           # save count; B=value; mirror
        0x7B, 0xD6, 0xA0, 0x4F, 0xCB, 0x37, 0x0F,
        0xA9, 0xE6, 0x03, 0xC6,
        TED_INCREMENTAL_KEY_ADDR & 0xFF,
        # The key lookup temporarily borrows HL.  Preserve the incremented
        # D000-D23F mirror cursor or the second cell onward overwrites key
        # metadata instead of constructing the exact source mirror.
        0xE5, 0x6F, 0x26, TED_INCREMENTAL_KEY_ADDR >> 8,
        0x7E, 0x80, 0x77, 0xE1,
        0x13, 0xC1, 0x0B, 0x78, 0xB1,
    )
    a.jr(0x20, "cell")
    a.db(0x3E, 0x01,
         0xEA, TED_INCREMENTAL_VALID_ADDR & 0xFF,
         TED_INCREMENTAL_VALID_ADDR >> 8, 0xC9)
    return a.finish()


def build_ted_incremental_runtime_blob() -> tuple[bytes, bytes]:
    if _os.environ.get(TED_BLOCK_MAJOR_ENV, "0") == "1":
        fragments = build_ted_block_major_exact_fit_draft()
        runtime = fragments[TED_INCREMENTAL_TRACKER_ADDR]
        assert len(runtime) == sum(
            length for _address, length in TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS
        )
        return runtime, b""
    tracker, exit_code, continuation = build_ted_full_source_tracker()
    assert len(tracker) == TED_INCREMENTAL_TRACKER_EXIT_ADDR - TED_INCREMENTAL_TRACKER_ADDR
    assert not exit_code and len(continuation) == 9
    blob = tracker + continuation
    blob += bytes(
        TED_INCREMENTAL_INIT_ADDR - TED_INCREMENTAL_TRACKER_ADDR - len(blob)
    )
    blob += build_ted_full_source_initializer()
    source_capacity = sum(
        length for _address, length in TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS
    )
    assert (
        TED_INCREMENTAL_TRACKER_ADDR + len(blob) <= 0xD400
        and len(blob) <= source_capacity
    ), len(blob)
    blob += bytes(source_capacity - len(blob))
    return blob, b""


def build_ted_incremental_runtime_sources() -> dict[int, bytes]:
    """Split the volatile tracker across Ted-architecture-only ROM caves."""
    blob, continuation = build_ted_incremental_runtime_blob()
    sources: dict[int, bytes] = {}
    cursor = 0
    for address, length in TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS:
        sources[address] = blob[cursor:cursor + length]
        cursor += length
    assert cursor == len(blob), (cursor, len(blob))
    assert not continuation
    sources[TED_INCREMENTAL_FIXED_RUNTIME_SOURCE_ADDR] = (
        build_ted_incremental_fixed_runtime()
    )
    if _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1":
        helper = build_ted_direct_single_writer_helpers()
        cursor = 0
        for address, capacity in TED_DIRECT_FIXED_HELPER_SOURCE_CHUNKS:
            payload = helper[cursor:cursor + capacity]
            sources[address] = payload
            cursor += len(payload)
        assert cursor == len(helper), (cursor, len(helper))
    if _os.environ.get("PENTA_TED_INWINDOW_GDMA", "0") == "1":
        block_major = _os.environ.get(TED_BLOCK_MAJOR_ENV, "0") == "1"
        if block_major:
            assert _os.environ.get(TED_INCREMENTAL_CELL_ENV, "0") == "1"
            exact = build_ted_block_major_exact_fit_draft()
            for address, payload in exact.items():
                if address < 0x8000:
                    assert address not in sources, hex(address)
                    sources[address] = payload
            return sources
        assert (
            TED_INWINDOW_SANITIZER_SOURCE_ADDR == TED_TABLE_ADDR + 0x87
            and TED_INWINDOW_SANITIZER_SOURCE_ADDR
            + TED_INWINDOW_SANITIZER_SOURCE_SIZE == TED_TABLE_ADDR + 0x100
        ), "private sanitizer source must stay inside Ted's neutral LUT tail"
        assert all(
            ARENA_TILE_PAL["ted"].get(tile, 0) == 0
            for tile in range(0x87, 0x100)
        ), "Ted sanitizer source overlaps an editable/publishable material"
        incremental_cell = _os.environ.get(
            TED_INCREMENTAL_CELL_ENV, "0"
        ) == "1"
        if incremental_cell:
            assert tuple(
                ARENA_TILE_PAL["ted"].get(tile, 0)
                for tile in range(0x77, 0x87)
            ) == (6, 7, 7, 6, 5, 0, 1, 0, 0, 2, 0, 5, 1, 2, 5, 1), (
                "Ted $77-$86 sparse/floor LUT contract changed"
            )
            sanitizer, helper_fragments = (
                build_ted_incremental_cell_classifier_draft()
            )
            validate_ted_incremental_cell_layout(
                sanitizer, helper_fragments
            )
            assert False, (
                "PENTA_TED_INCREMENTAL_CELL is wired but blocked: the "
                "D863-D8AA body mask has no receipt-qualified SVBK4/5 "
                "ownership record"
            )
        else:
            sanitizer, helper_fragments = build_ted_inwindow_plane_sanitizer()
        sources[TED_INWINDOW_SANITIZER_SOURCE_ADDR] = sanitizer
        sources.update(helper_fragments)
    return sources


def build_ted_incremental_fixed_runtime() -> bytes:
    """Run the SVBK4 clone atomically from unbanked WRAM, then restore."""
    if _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1":
        # The physical selector is normalized by its preceding publication.
        # Mask defensively, then map pre-toggle odd->$9800/SVBK4 and
        # even->$9C00/SVBK5. Balanced AF saves keep this dual-bank dispatcher
        # inside the source cave's 24 contiguous bytes.
        code = bytes([
            0xF3, 0xF5,
            0xFA, 0x0B, 0xDC, 0xE6, 0x01, 0xEE, 0x05, 0xE0, 0x70,
            0xF1,
            0xCD, TED_INCREMENTAL_CLONE_ADDR & 0xFF,
            TED_INCREMENTAL_CLONE_ADDR >> 8,
            0xF5, 0x3E, 0x01, 0xE0, 0x70, 0xF1, 0xFB, 0xC9,
        ])
        assert len(code) == 23
        return code
    code = bytearray([
        0xF3,
        # FFA9 is retired by this incremental compiler. LD/LDH preserve F,
        # so this carries exact AF across SVBK without crossing banked stacks.
        0xE0, TED_SANITIZER_EXPECTED_HRAM,
    ])
    code.extend([0x3E, 0x04, 0xE0, 0x70])
    code.extend([
        0xF0, TED_SANITIZER_EXPECTED_HRAM,
        0xCD, TED_INCREMENTAL_CLONE_ADDR & 0xFF,
        TED_INCREMENTAL_CLONE_ADDR >> 8,
        0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0x3E, 0x01, 0xE0, 0x70,
        0xF0, TED_SANITIZER_EXPECTED_HRAM,
        0xFB, 0xC9,
    ])
    assert len(code) == 22
    return bytes(code)


def build_ted_direct_single_writer_helpers() -> bytes:
    """Mirror Ted's two late single-cell writers into the direct plane.

    Both bank-2 hooks replace their complete displaced tails with JP, so no
    synthetic return address is introduced.  The shared leaf preserves every
    live register and AF, restores SVBK1, and maps all 576 native source cells
    through the cold-built 16-bit pointer table.
    """
    helper_a_addr = TED_DIRECT_FIXED_HELPER_ADDR
    helper_b_addr = helper_a_addr + 10
    common_addr = helper_b_addr + 7

    helper_a = bytes([
        0xF3,
        0xCD, common_addr & 0xFF, common_addr >> 8,
        0xE1, 0xC1,                       # displaced POP HL / POP BC
        0xFB,
        0xC3, 0xE2, 0x61,                 # resume at DEC B
    ])
    helper_b = bytes([
        0xF1,                              # displaced POP AF
        0xF3,
        0xCD, common_addr & 0xFF, common_addr >> 8,
        0xFB, 0xC9,
    ])
    # The writers occur both inside IE=$00 map phases and in IE=$07 steady
    # gameplay. Keep the selected private-bank interval atomic; EI takes
    # effect only after the following JP/RET returns to the displaced native
    # continuation.  DC0B is still the pre-publication selector here, exactly
    # matching the C500 clone dispatcher (odd -> SVBK4, even -> SVBK5).
    common = bytes([
        0x77,                              # displaced LD [HL],A
        0xF5, 0xC5, 0xD5, 0xE5,
        0x57,                              # D = raw tile
        # The table has one pointer per even-column 2x2 top-left. Retain the
        # arbitrary single writer's column parity and align its table index;
        # an odd source cell advances the decoded destination once.
        0x7D, 0xE6, 0x01, 0x5F, 0xCB, 0x85,
        0xFA, 0x0B, 0xDC,
        # The in-window entry stores ``(DC0B + 1) & 1`` before any selected
        # plane writer can run. Block-major can spend that proven normalized
        # bit directly and reclaim the two-byte defensive mask for its
        # private-LUT lookup below.
        *([] if _os.environ.get(TED_BLOCK_MAJOR_ENV, "0") == "1"
          else [0xE6, 0x01]),
        0xEE, 0x05, 0xE0, 0x70,
        0x01, 0x60, 0x14, 0x09,           # aligned top-left table entry
        0x4E, 0x23, 0x46,                 # BC = padded plane pointer
        0x7B, 0xB7, 0x28, 0x01, 0x03,     # odd source -> next plane cell
        *(
            # Block-major owns the former $7600 Ted LUT page, so scene
            # detection can no longer seed C600 with a valid 256-byte table.
            # Its cold installer already expands tile $00 at D5FF through
            # tile $86 at D579; use that private reverse LUT for the two late
            # single-cell/tentacle writers as well as the 2x2 writer.
            [0x7A, 0x2F, 0x6F, 0x26, 0xD5, 0x7E]
            if _os.environ.get(TED_BLOCK_MAJOR_ENV, "0") == "1"
            else [0x6A, 0x26, WRAM_BG_TABLE >> 8, 0x7E]
        ),
        0x02,                              # selected plane write
        0x3E, 0x01, 0xE0, 0x70,
        0xE1, 0xD1, 0xC1, 0xF1, 0xC9,
    ])
    assert len(helper_a) == 10 and len(helper_b) == 7
    code = helper_a + helper_b + common
    if _os.environ.get(TED_BLOCK_MAJOR_ENV, "0") == "1":
        # $5E48 begins the adjacent installer. Growing this helper even one
        # byte drops its POP AF/RET tail and corrupts the native writer stack.
        assert len(code) == 64, len(code)
    assert len(code) <= sum(
        capacity for _address, capacity
        in TED_DIRECT_FIXED_HELPER_SOURCE_CHUNKS
    ), len(code)
    if _os.environ.get(TED_BLOCK_MAJOR_ENV, "0") == "1":
        # Block-major's installer begins at $5E48.  The second helper source
        # fragment begins at $5E2C, leaving only 28 bytes there (64 total),
        # even though the historical cave has a 36-byte nominal capacity.
        # Crossing this boundary overwrites the helper's POP AF / RET and
        # converts every late single-cell write into stack corruption.
        assert len(code) <= 64, (
            "block-major single-writer helper overlaps installer $5E48",
            len(code),
        )
    assert TED_DIRECT_FIXED_HELPER_ADDR + len(code) < TED_INCREMENTAL_READY_ADDR
    return code


def build_ted_incremental_bank2_gate() -> dict[int, bytes]:
    """Select stock $064D or the private $309B clone at Ted's bank-2 call."""
    entry = bytes([
        0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
        TED_INCREMENTAL_READY_ADDR >> 8, 0x3C,
        0xC2, TED_INCREMENTAL_BANK2_FALLBACK_ADDR & 0xFF,
        TED_INCREMENTAL_BANK2_FALLBACK_ADDR >> 8,
        0xC3, TED_INCREMENTAL_BANK2_READY_ADDR & 0xFF,
        TED_INCREMENTAL_BANK2_READY_ADDR >> 8,
    ])
    fallback = bytes([0xCD, 0x4D, 0x06, 0xC9])
    ready = bytes([
        0xCD, TED_INCREMENTAL_UNUSED_THUNK_ADDR & 0xFF,
        TED_INCREMENTAL_UNUSED_THUNK_ADDR >> 8, 0xC9,
    ])
    fragments = {
        TED_INCREMENTAL_BANK2_ENTRY_ADDR: entry,
        TED_INCREMENTAL_BANK2_FALLBACK_ADDR: fallback,
        TED_INCREMENTAL_BANK2_READY_ADDR: ready,
    }
    capacities = {
        TED_INCREMENTAL_BANK2_ENTRY_ADDR: 12,
        TED_INCREMENTAL_BANK2_FALLBACK_ADDR: 11,
        TED_INCREMENTAL_BANK2_READY_ADDR: 13,
    }
    for address, payload in fragments.items():
        assert len(payload) <= capacities[address]
    return fragments


def build_ted_incremental_clone_patch_records() -> tuple[tuple[int, bytes], ...]:
    """Runtime patches applied after copying stock $30AF-$313A to SVBK4."""
    clone_source = 0x309B
    delta = TED_INCREMENTAL_CLONE_ADDR - clone_source
    records = (
        (TED_INCREMENTAL_CLONE_ADDR + (0x30B9 - clone_source),
         bytes([0xCD, (0x30D8 + delta) & 0xFF, (0x30D8 + delta) >> 8])),
        (TED_INCREMENTAL_CLONE_ADDR + (0x30EB - clone_source),
         bytes([0xCD, (0x3111 + delta) & 0xFF, (0x3111 + delta) >> 8])),
        (TED_INCREMENTAL_CLONE_ADDR + (0x3103 - clone_source),
         bytes([0xCD, (0x3111 + delta) & 0xFF, (0x3111 + delta) >> 8])),
        (TED_INCREMENTAL_CLONE_ADDR + (0x3136 - clone_source),
         bytes([0xC3, TED_INCREMENTAL_TRACKER_ADDR & 0xFF,
                TED_INCREMENTAL_TRACKER_ADDR >> 8])),
    )
    stock = Path("rom/Penta Dragon (J).gb").read_bytes()
    for call_addr in (0x30B9, 0x30EB, 0x3103):
        assert stock[call_addr] == 0xCD, hex(call_addr)
    assert stock[0x3136:0x3139] == bytes.fromhex("C1 13 13")
    return records


def build_ted_postcopy_attr_compiler() -> dict[int, bytes]:
    """Compile changed Ted attrs after native copy; reuse two exact planes."""
    cache_mode = _os.environ.get("PENTA_TED_POSTCOPY_CACHE", "1")
    cache_enabled = cache_mode != "0"
    cache_reuse = cache_mode == "1"
    front = _Asm()
    front.db(0xF3, 0xC5, 0xD5, 0xE5)       # DI; preserve caller
    # HL ended three physical pages beyond the target map ($9B/$9F). Recover
    # its $98/$9C base for HDMA after compiling the packed 24x24 source.
    front.db(0x7C, 0xE6, 0xFC)
    if cache_enabled:
        front.db(0xE0, TED_SANITIZER_TILE_MASK_HRAM)
    else:
        # Do not borrow a live HRAM gameplay byte merely to retain $98/$9C.
        # The cache-free path has no early-hit exit, so carry the target map
        # on its private stack frame until the single final publication.
        front.db(0xF5)
    # The native engine republishes exact layouts. Keep those publications for
    # stock cadence, but avoid recompiling the same 576 attributes. The
    # signature helper selects WRAM bank 2/3 and returns Z on a cache hit.
    if cache_enabled:
        front.db(0xCD, TED_POSTCOPY_DISPATCH_ADDR & 0xFF,
                 TED_POSTCOPY_DISPATCH_ADDR >> 8)
        front.db(0xCA, TED_SANITIZER_ROW_TABLE_ADDR & 0xFF,
                 TED_SANITIZER_ROW_TABLE_ADDR >> 8)
        # The dispatcher restores SVBK1 before RET so its return address is
        # read from the real stack, then returns the selected cache bank in A.
        front.db(0xE0, 0x70)
        front.db(0xDA, TED_SANITIZER_ACTIVE_ADDR & 0xFF,
                 TED_SANITIZER_ACTIVE_ADDR >> 8)
    else:
        # The shared row helper and its output plane live in WRAM bank 2.
        # Cache lookup normally selects bank 2/3 before this point; the
        # cache-disabled diagnostic path must establish that invariant itself
        # or CALL $D400 executes unrelated bank-1 data and locks at $D473.
        front.db(0x3E, 0x02, 0xE0, 0x70)
    front.db(0x11, 0xA0, 0xC1, 0x21, 0x00, 0xD0,
             0x06, WRAM_BG_TABLE >> 8)
    front.db(0x3E, 0x18, 0xE0, LAVA_ATTR_DECISION_HRAM)
    front.db(0xC3, TED_SANITIZER_CLASSIFY_ADDR & 0xFF,
             TED_SANITIZER_CLASSIFY_ADDR >> 8)

    row = _Asm()
    row.label("row")
    row.db(0xCD, STAGE1_ATTR_ROW_HELPER_WRAM_ADDR & 0xFF,
           STAGE1_ATTR_ROW_HELPER_WRAM_ADDR >> 8)
    # D400 writes 24 attributes; explicitly neutralize the eight padding
    # columns so an old staging buffer can never color the map edge.
    row.db(0xAF)
    for _ in range(8):
        row.db(0x22)
    row.db(0xF0, LAVA_ATTR_DECISION_HRAM, 0x3D,
           0xE0, LAVA_ATTR_DECISION_HRAM)
    row.jr(0x20, "row")
    row.db(0xC3, TED_SANITIZER_ACTIVE_ADDR & 0xFF,
           TED_SANITIZER_ACTIVE_ADDR >> 8)

    final = _Asm()
    # Publish all $300 bytes to the just-completed off-screen map in VBK1.
    final.db(0x3E, 0x01, 0xE0, 0x4F)
    final.db(0x3E, 0xD0, 0xE0, 0x51, 0xAF, 0xE0, 0x52)
    if cache_enabled:
        final.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM)
    else:
        final.db(0xF1)
    final.db(0xE0, 0x53)
    # One immediate 48-block GDMA is cheaper than keeping the CPU interlocked
    # across 48 HBlanks, and the native publisher already runs with IRQs off.
    final.db(0x3E, 0x2F, 0xE0, 0x55)
    final.label("hdma_wait")
    final.db(0xF0, 0x55, 0xCB, 0x7F)
    final.jr(0x28, "hdma_wait")
    final.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70)
    final.db(0xE1, 0xD1, 0xC1, 0xFB, 0xC9)
    signature = bytes([
        0xFA, 0x81, 0xDD, 0x4F,
        0xFA, 0xC0, 0xDD, 0x47,
        0xFA, 0x87, 0xDD, 0x57,
        0xFA, 0xDC, 0xDD, 0x5F,
        0xC3, TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR & 0xFF,
        TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR >> 8,
    ])

    def cache_lookup_front(bank: int, miss_address: int,
                           tail_address: int) -> bytes:
        lookup = _Asm()
        lookup.db(0x3E, bank, 0xE0, 0x70, 0x21, 0x05, 0xD3)
        for expected in (0x10, 0xA7):
            lookup.db(0x7E, 0x2B)
            lookup.db(0xFE, expected)
            lookup.jr(0x20, "miss")
        lookup.db(0xC3, tail_address & 0xFF, tail_address >> 8)
        lookup.label("miss")
        lookup.db(0xC3, miss_address & 0xFF, miss_address >> 8)
        code = lookup.finish()
        assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE, len(code)
        return code

    def cache_lookup_tail(bank: int, miss_address: int) -> bytes:
        lookup = _Asm()
        for register_compare in (0xBB, 0xBA, 0xB8, 0xB9):
            lookup.db(0x7E, 0x2B, register_compare)
            lookup.jr(0x20, "miss")
        lookup.db(0x3E, bank, 0xC3,
                  TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR & 0xFF,
                  TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR >> 8)
        lookup.label("miss")
        lookup.db(0xC3, miss_address & 0xFF, miss_address >> 8)
        return lookup.finish()

    restore_hit = bytes([
        0x47,                   # B=selected bank
        0x3E, 0x01, 0xE0, 0x70, # restore stack's SVBK1
        0x78, 0xB7, 0x37, 0xC9, # A=selected bank; NZ+C; RET
    ])

    physical_select = _Asm()
    physical_select.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xFE, 0x9C)
    physical_select.jr(0x28, "map9c")
    physical_select.db(0x21, 0xFC, 0xC4)
    physical_select.jr(0x18, "check")
    physical_select.label("map9c")
    physical_select.db(0x21, 0x00, 0xC5)
    physical_select.label("check")
    physical_select.db(0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xB7)
    physical_select.db(
        0xCA, TED_INCREMENTAL_INSTALL_CONT_ADDR & 0xFF,
        TED_INCREMENTAL_INSTALL_CONT_ADDR >> 8,
    )
    physical_select.db(
        0xC3, (TED_SANITIZER_ROW_TABLE_ADDR + 5) & 0xFF,
        (TED_SANITIZER_ROW_TABLE_ADDR + 5) >> 8,
    )

    physical_check = _Asm()
    physical_check.db(0xE5)
    for register_compare in (0xB9, 0xB8, 0xBA, 0xBB):
        physical_check.db(0x2A, register_compare)
        physical_check.jr(0x20, "changed")
    physical_check.db(0xE1, 0x3E, 0x01, 0xBF, 0xC9)  # physical hit: Z
    physical_check.label("changed")
    physical_check.db(0xE1, 0xC3, TED_INCREMENTAL_INSTALL_CONT_ADDR & 0xFF,
                      TED_INCREMENTAL_INSTALL_CONT_ADDR >> 8)
    physical_changed = bytes([
        0x79, 0x22, 0x78, 0x22, 0x7A, 0x22, 0x7B, 0x22,
        0xC3, TED_SANITIZER_SPECIAL_ADDR & 0xFF,
        TED_SANITIZER_SPECIAL_ADDR >> 8,
    ])
    physical_fragment = bytes([0xE1, 0xD1, 0xC1, 0xFB, 0xC9]) + (
        physical_check.finish()
    )
    assert len(physical_fragment) <= ARENA_SANITIZER_FRAGMENT_SIZE

    select_miss = _Asm()
    select_miss.db(0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xFE, 0x02,
                   0x3E, 0x02)
    select_miss.jr(0x20, "selected")
    select_miss.db(0x3E, 0x03)
    select_miss.label("selected")
    select_miss.db(0xE0, TED_SANITIZER_EXPECTED_HRAM, 0xE0, 0x70,
                   0x21, 0x00, 0xD3,
                   0xC3, TED_SANITIZER_GEOMETRY_CONT_ADDR & 0xFF,
                   TED_SANITIZER_GEOMETRY_CONT_ADDR >> 8)
    select_store = bytes([
                   0x79, 0x22, 0x78, 0x22, 0x7A, 0x22, 0x7B, 0x22,
                   0x3E, 0xA7, 0x22, 0x3E, 0x10, 0x77,
                   0x3E, 0x01, 0xE0, 0x70,
                   0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xB7, 0xC9])

    fragments = {
        TED_POSTCOPY_ATTR_COMPILER_ADDR: front.finish(),
        TED_SANITIZER_CLASSIFY_ADDR: row.finish(),
        TED_SANITIZER_ACTIVE_ADDR: final.finish(),
        TED_SANITIZER_SPECIAL_ADDR: cache_lookup_front(
            2, TED_SANITIZER_CLEAR_ADDR, TED_SANITIZER_ANCHOR_ADDR
        ),
        TED_SANITIZER_ANCHOR_ADDR: cache_lookup_tail(
            2, TED_SANITIZER_CLEAR_ADDR
        ),
        TED_SANITIZER_CLEAR_ADDR: cache_lookup_front(
            3, TED_SANITIZER_COMPARE_ADDR, TED_SANITIZER_ANCHOR_PACK_ADDR
        ),
        TED_SANITIZER_ANCHOR_PACK_ADDR: cache_lookup_tail(
            3, TED_SANITIZER_COMPARE_ADDR
        ),
        TED_SANITIZER_COMPARE_ADDR: select_miss.finish(),
        TED_SANITIZER_GEOMETRY_CONT_ADDR: select_store,
        TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR: restore_hit,
        TED_SANITIZER_ROW_TABLE_ADDR: physical_fragment,
        TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR: physical_select.finish(),
        TED_INCREMENTAL_INSTALL_CONT_ADDR: physical_changed,
        TED_POSTCOPY_DISPATCH_ADDR: signature,
    }
    for code in fragments.values():
        assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return fragments


def build_ted_compact_postcopy_attr_compiler() -> dict[int, bytes]:
    """Cache Ted's exact post-stock-copy attributes with a compact key.

    The stock $4295 call remains the tile publisher and therefore retains its
    alternating-map geometry and cadence.  Most calls return after a two-byte
    physical-map tag check.  A changed map reuses one of two exact WRAM
    attribute planes, compiling the 24x24 C1A0 source only on a FIFO miss.
    """
    assert _os.environ.get("PENTA_TED_POSTCOPY_CACHE", "1") == "1"
    sources = tuple(0xC1A0 + sample for sample in TED_POSTCOPY_KEY_SAMPLES)

    def jp(address: int, opcode: int = 0xC3) -> tuple[int, int, int]:
        return opcode, address & 0xFF, address >> 8

    key_loop_addr = TED_SANITIZER_CLASSIFY_ADDR
    key_table_a_addr = TED_SANITIZER_CROWN_ADDR
    key_table_b_addr = TED_SANITIZER_ACTIVE_ADDR
    key_finish_addr = TED_SANITIZER_SPECIAL_ADDR
    physical_addr = TED_SANITIZER_CLEAR_ADDR
    lookup2_addr = TED_SANITIZER_ROW_TABLE_ADDR
    lookup3_addr = TED_SANITIZER_ANCHOR_ADDR
    miss_addr = TED_SANITIZER_GEOMETRY_CONT_ADDR
    compile_row_addr = TED_SANITIZER_COMPARE_ADDR
    commit_addr = TED_SANITIZER_ANCHOR_PACK_ADDR

    # Two 16-address ROM tables feed one compact loop. B is the wrapping sum
    # and C is y=(y*3+value)&$FF. This 32-cell pair is collision-free across
    # the qualified and fresh generated-state corpora.
    key_a = _Asm()
    key_a.db(0xF3, 0xC5, 0xD5, 0xE5)       # DI; preserve BC,DE,HL
    key_a.db(0x7C, 0xE6, 0xFC, 0xE0, TED_SANITIZER_TILE_MASK_HRAM)
    key_a.db(
        0xAF, 0x47, 0x4F,                  # sum B=0, roll C=0
        0x21, key_table_a_addr & 0xFF, key_table_a_addr >> 8,
        0x3E, 0x10, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0xCD, key_loop_addr & 0xFF, key_loop_addr >> 8,
        0x21, key_table_b_addr & 0xFF, key_table_b_addr >> 8,
        0x3E, 0x10, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0xCD, key_loop_addr & 0xFF, key_loop_addr >> 8,
        *jp(key_finish_addr),
    )

    key_loop = _Asm()
    key_loop.label("sample")
    key_loop.db(
        0x5E, 0x23, 0x56, 0x23, 0x1A, 0x5F,
        0x78, 0x83, 0x47,                  # B = sum + value
        0x79, 0x81, 0x81, 0x83, 0x4F,     # C = C*3 + value
        0xF0, TED_SANITIZER_EXPECTED_HRAM,
        0x3D, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
    )
    key_loop.jr(0x20, "sample")
    key_loop.db(0xC9)

    def address_table(items: tuple[int, ...]) -> bytes:
        return bytes(byte for address in items for byte in (
            address & 0xFF, address >> 8
        ))

    key_table_a = address_table(sources[:16])
    key_table_b = address_table(sources[16:])
    key_finish = bytes([
        0x78, 0xE0, TED_SANITIZER_COUNTER_HRAM,
        0x79, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
        *jp(physical_addr),
    ])

    # Check the selected physical map before switching WRAM. On the qualified
    # trace this fast path handles 402/485 publications.
    physical = _Asm()
    physical.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xFE, 0x9C)
    physical.db(
        0x21, TED_POSTCOPY_PHYSICAL_9800_ADDR & 0xFF,
        TED_POSTCOPY_PHYSICAL_9800_ADDR >> 8,
    )
    physical.jr(0x20, "selected")
    physical.db(
        0x21, TED_POSTCOPY_PHYSICAL_9C00_ADDR & 0xFF,
        TED_POSTCOPY_PHYSICAL_9C00_ADDR >> 8,
    )
    physical.label("selected")
    physical.db(0xF0, TED_SANITIZER_COUNTER_HRAM, 0xBE)
    physical.db(*jp(lookup2_addr, 0xC2))                   # JP NZ,lookup2
    physical.db(0x23, 0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xBE)
    physical.db(*jp(lookup2_addr, 0xC2))
    physical.db(
        0x23,
        0xFA, TED_POSTCOPY_GENERATION_ADDR & 0xFF,
        TED_POSTCOPY_GENERATION_ADDR >> 8,
        0xBE,
    )
    tag_cont_addr = commit_addr + 19
    finish_addr = tag_cont_addr + 7
    physical.db(*jp(lookup2_addr, 0xC2))
    physical.db(*jp(finish_addr))

    publish_addr = TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR
    def cache_probe(bank: int, miss: int) -> bytes:
        a = _Asm()
        if bank == 2:
            # Capture fixed-bank generation before SVBK hides DFxx.
            a.db(
                0xFA, TED_POSTCOPY_GENERATION_ADDR & 0xFF,
                TED_POSTCOPY_GENERATION_ADDR >> 8,
                0x57,
            )
        a.db(0x3E, bank, 0xE0, 0x70)
        a.db(
            0x21, TED_POSTCOPY_PLANE_GENERATION_ADDR & 0xFF,
            TED_POSTCOPY_PLANE_GENERATION_ADDR >> 8,
            0x7A, 0xBE,
        )
        a.db(*jp(miss, 0xC2))
        a.db(0x2B, 0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xBE)
        a.db(*jp(miss, 0xC2))
        a.db(0x2B, 0xF0, TED_SANITIZER_COUNTER_HRAM, 0xBE)
        a.db(*jp(miss, 0xC2))
        a.db(*jp(publish_addr))
        return a.finish()

    lookup2 = cache_probe(2, lookup3_addr)
    lookup3 = cache_probe(3, miss_addr)

    select_miss = _Asm()
    select_miss.db(
        0x3E, 0x01, 0xE0, 0x70,            # fixed DFxx metadata is bank 1
        0xFA, TED_POSTCOPY_FIFO_ADDR & 0xFF,
        TED_POSTCOPY_FIFO_ADDR >> 8,
        0x47,                               # B = selected bank
        0xEE, 0x01,
        0xEA, TED_POSTCOPY_FIFO_ADDR & 0xFF,
        TED_POSTCOPY_FIFO_ADDR >> 8,
        0x78, 0xE0, 0x70,
        0x21, (TED_POSTCOPY_PLANE_GENERATION_ADDR + 1) & 0xFF,
        (TED_POSTCOPY_PLANE_GENERATION_ADDR + 1) >> 8,
        0x72,                               # bank-local generation scratch
        0x11, 0xA0, 0xC1,
        0x21, 0x00, 0xD0,
        0x06, WRAM_BG_TABLE >> 8,
        0x3E, 0x18, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
        *jp(compile_row_addr),
    )

    compile_row = _Asm()
    compile_row.db(
        0xCD, STAGE1_ATTR_ROW_HELPER_WRAM_ADDR & 0xFF,
        STAGE1_ATTR_ROW_HELPER_WRAM_ADDR >> 8,
        0xAF,
    )
    compile_row.db(*([0x22] * 8))           # deterministic row padding
    compile_row.db(
        0xF0, TED_SANITIZER_EXPECTED_HRAM,
        0x3D,
        0xE0, TED_SANITIZER_EXPECTED_HRAM,
        *jp(compile_row_addr, 0xC2),
        *jp(commit_addr),
    )

    commit = _Asm()
    commit.db(
        0x21, TED_POSTCOPY_PLANE_KEY_ADDR & 0xFF,
        TED_POSTCOPY_PLANE_KEY_ADDR >> 8,
        0xF0, TED_SANITIZER_COUNTER_HRAM, 0x22,
        0xFA, 0x7D, 0xC2,
        0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0x22,
        0x23, 0x7E, 0x2B,
        0x77,                               # generation is the commit byte
        *jp(publish_addr),
    )
    assert len(commit.code) == tag_cont_addr - commit_addr
    # GDMA completion enters here with HL at the physical discriminator.
    commit.db(
        0xF0, TED_SANITIZER_EXPECTED_HRAM, 0x22,
        0xFA, TED_POSTCOPY_GENERATION_ADDR & 0xFF,
        TED_POSTCOPY_GENERATION_ADDR >> 8,
        0x77,                               # physical tag commits last
        0xE1, 0xD1, 0xC1, 0xFB, 0xC9,
    )

    publish = _Asm()
    publish.db(
        0x3E, 0x01, 0xE0, 0x4F,
        0x3E, 0xD0, 0xE0, 0x51,
        0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xE0, 0x53,
        0xAF, 0xE0, 0x52, 0xE0, 0x54,
        0x3E, 0x2F, 0xE0, 0x55,
        *jp(TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR),
    )

    wait_and_tag = _Asm()
    wait_and_tag.label("wait")
    wait_and_tag.db(0xF0, 0x55, 0xCB, 0x7F)
    wait_and_tag.jr(0x28, "wait")
    wait_and_tag.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70)
    wait_and_tag.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xFE, 0x9C)
    wait_and_tag.db(
        0x21, TED_POSTCOPY_PHYSICAL_9800_ADDR & 0xFF,
        TED_POSTCOPY_PHYSICAL_9800_ADDR >> 8,
    )
    wait_and_tag.jr(0x20, "selected")
    wait_and_tag.db(
        0x21, TED_POSTCOPY_PHYSICAL_9C00_ADDR & 0xFF,
        TED_POSTCOPY_PHYSICAL_9C00_ADDR >> 8,
    )
    wait_and_tag.label("selected")
    wait_and_tag.db(
        0xF0, TED_SANITIZER_COUNTER_HRAM, 0x22,
        *jp(tag_cont_addr),
    )

    fragments = {
        TED_SANITIZER_MAIN_ADDR: key_a.finish(),
        key_loop_addr: key_loop.finish(),
        key_table_a_addr: key_table_a,
        key_table_b_addr: key_table_b,
        key_finish_addr: key_finish,
        physical_addr: physical.finish(),
        lookup2_addr: lookup2,
        lookup3_addr: lookup3,
        miss_addr: select_miss.finish(),
        compile_row_addr: compile_row.finish(),
        commit_addr: commit.finish(),
        TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR: publish.finish(),
        TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR: wait_and_tag.finish(),
    }
    capacities = {
        TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR: 36,
        TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR: 31,
    }
    for address, code in fragments.items():
        assert len(code) <= capacities.get(address, ARENA_SANITIZER_FRAGMENT_SIZE), (
            hex(address), len(code)
        )
    return fragments


def build_ted_incremental_postcopy_attr_compiler() -> dict[int, bytes]:
    """Publish exact Ted attrs using the SVBK4 incremental full-source key."""
    if _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1":
        return build_ted_direct_plane_postcopy()

    entry_addr = TED_SANITIZER_MAIN_ADDR
    select_addr = TED_DIRTY_POSTCOPY_ADVANCE_ADDR
    select_cont_addr = TED_DIRTY_POSTCOPY_ADVANCE_CONT_ADDR
    compare_addr = TED_DIRTY_POSTCOPY_SETUP_ADDR
    compare_cont_addr = TED_DIRTY_POSTCOPY_BIT_ADDR
    miss_addr = TED_DIRTY_POSTCOPY_BIT_CONT_ADDR
    miss_cont_addr = TED_DIRTY_POSTCOPY_COMPILE_TAIL_ADDR
    setup_addr = TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR
    compile_addr = TED_SANITIZER_ANCHOR_ADDR
    publish_addr = TED_SANITIZER_GEOMETRY_CONT_ADDR
    wait_addr = TED_SANITIZER_COMPARE_ADDR
    finish_addr = TED_DIRTY_POSTCOPY_BIT_TAIL_ADDR

    def jp(address: int, opcode: int = 0xC3) -> tuple[int, int, int]:
        return opcode, address & 0xFF, address >> 8

    lazy_gate = bytes([
        0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
        TED_INCREMENTAL_READY_ADDR >> 8, 0x3C,
        *jp(TED_POSTCOPY_SCENE_INIT_ADDR, 0xC2),
        *jp(entry_addr),
    ])

    entry = _Asm()
    entry.db(0xF3, 0xC5, 0xD5, 0xE5,
             0x7C, 0xE6, 0xFC, 0xE0, TED_SANITIZER_TILE_MASK_HRAM,
             0x3E, 0x04, 0xE0, 0x70,
             0xCD, TED_INCREMENTAL_INIT_ADDR & 0xFF,
             TED_INCREMENTAL_INIT_ADDR >> 8,
             0x21, TED_INCREMENTAL_KEY_ADDR & 0xFF,
             TED_INCREMENTAL_KEY_ADDR >> 8,
             0x46, 0x23, 0x4E, 0x23, 0x56, 0x23, 0x5E,
             0x3E, 0x01, 0xE0, 0x70,
             *jp(select_addr))

    select = _Asm()
    select.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xFE, 0x9C,
              0x21, TED_INCREMENTAL_PHYSICAL_9800_ADDR & 0xFF,
              TED_INCREMENTAL_PHYSICAL_9800_ADDR >> 8)
    select.jr(0x20, "selected")
    select.db(0x21, TED_INCREMENTAL_PHYSICAL_9C00_ADDR & 0xFF,
              TED_INCREMENTAL_PHYSICAL_9C00_ADDR >> 8)
    select.label("selected")
    select.db(*jp(select_cont_addr))

    select_cont = _Asm()
    select_cont.db(
              0x78, 0xBE, *jp(miss_addr, 0xC2),
              0x23, 0x79, 0xBE, *jp(miss_addr, 0xC2),
              0x23, *jp(compare_addr))

    compare = _Asm()
    compare.db(0x7A, 0xBE, *jp(miss_addr, 0xC2),
               0x23, 0x7B, 0xBE, *jp(miss_addr, 0xC2),
               0x23, *jp(compare_cont_addr))

    compare_cont = _Asm()
    compare_cont.db(
               0xFA, TED_INCREMENTAL_GENERATION_ADDR & 0xFF,
               TED_INCREMENTAL_GENERATION_ADDR >> 8,
               0xBE, *jp(miss_addr, 0xC2), *jp(finish_addr))

    miss = _Asm()
    miss.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xFE, 0x9C,
            0x21, TED_INCREMENTAL_PHYSICAL_9800_ADDR & 0xFF,
            TED_INCREMENTAL_PHYSICAL_9800_ADDR >> 8)
    miss.jr(0x20, "tag_selected")
    miss.db(0x21, TED_INCREMENTAL_PHYSICAL_9C00_ADDR & 0xFF,
            TED_INCREMENTAL_PHYSICAL_9C00_ADDR >> 8)
    miss.label("tag_selected")
    miss.db(*jp(miss_cont_addr))

    miss_cont = _Asm()
    miss_cont.db(0x70, 0x23, 0x71, 0x23, 0x72, 0x23, 0x73, 0x23, 0xE5,
            0x3E, 0x18, 0xE0, TED_SANITIZER_COUNTER_HRAM,
            *jp(setup_addr))

    setup = _Asm()
    setup.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xFE, 0x9C,
             0x3E, 0x02)
    setup.jr(0x20, "bank_selected")
    setup.db(0x3C)
    setup.label("bank_selected")
    setup.db(0xE0, 0x70, 0x11, 0xA0, 0xC1, 0x21, 0x00, 0xD0,
            0x06, WRAM_BG_TABLE >> 8,
            *jp(compile_addr))

    compile_row = _Asm()
    compile_row.db(0xCD, STAGE1_ATTR_ROW_HELPER_WRAM_ADDR & 0xFF,
                   STAGE1_ATTR_ROW_HELPER_WRAM_ADDR >> 8,
                   0xAF, *([0x22] * 8),
                   0xF0, TED_SANITIZER_COUNTER_HRAM, 0x3D,
                   0xE0, TED_SANITIZER_COUNTER_HRAM,
                   *jp(compile_addr, 0xC2), *jp(publish_addr))

    publish = bytes([
        0x3E, 0x01, 0xE0, 0x4F,
        0x3E, 0xD0, 0xE0, 0x51,
        0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xE0, 0x53,
        0xAF, 0xE0, 0x52, 0xE0, 0x54,
        0x3E, 0x2F, 0xE0, 0x55,
        *jp(wait_addr),
    ])

    wait = _Asm()
    wait.label("busy")
    wait.db(0xF0, 0x55, 0xCB, 0x7F)
    wait.jr(0x28, "busy")
    wait.db(0xAF, 0xE0, 0x4F, 0x3C, 0xE0, 0x70,
            0xE1,
            0xFA, TED_INCREMENTAL_GENERATION_ADDR & 0xFF,
            TED_INCREMENTAL_GENERATION_ADDR >> 8, 0x77,
            *jp(finish_addr))

    finish = bytes([0xE1, 0xD1, 0xC1, 0xFB, 0xC9])
    fragments = {
        TED_INCREMENTAL_LAZY_GATE_ADDR: lazy_gate,
        entry_addr: entry.finish(),
        select_addr: select.finish(),
        select_cont_addr: select_cont.finish(),
        compare_addr: compare.finish(),
        compare_cont_addr: compare_cont.finish(),
        miss_addr: miss.finish(),
        miss_cont_addr: miss_cont.finish(),
        setup_addr: setup.finish(),
        compile_addr: compile_row.finish(),
        publish_addr: publish,
        wait_addr: wait.finish(),
        finish_addr: finish,
    }
    capacities = {
        select_addr: 18,
        select_cont_addr: 18,
        compare_addr: 18,
        compare_cont_addr: 18,
        miss_addr: 15,
        miss_cont_addr: 17,
        setup_addr: 24,
        finish_addr: 8,
        TED_INCREMENTAL_LAZY_GATE_ADDR: 11,
    }
    for address, code in fragments.items():
        assert len(code) <= capacities.get(
            address, ARENA_SANITIZER_FRAGMENT_SIZE
        ), (hex(address), len(code))
    return fragments


def build_ted_direct_plane_postcopy() -> dict[int, bytes]:
    """Publish the already-maintained SVBK4 D000 attribute plane."""
    entry_addr = TED_SANITIZER_MAIN_ADDR
    setup_addr = TED_DIRTY_POSTCOPY_SETUP_ADDR
    wait_addr = TED_SANITIZER_COMPARE_ADDR

    # The native postcopy wrapper enters through this cold/ready gate.  The
    # incremental compiler normally emits it, but the direct-plane branch
    # returns from build_ted_incremental_postcopy_attr_compiler() before that
    # common fragment is constructed.  Keep the same sentinel convention:
    # $00 installs the private clone/plane and $FF enters the hot publisher.
    lazy_gate = bytes([
        0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
        TED_INCREMENTAL_READY_ADDR >> 8, 0x3C,
        0xC2, TED_POSTCOPY_SCENE_INIT_ADDR & 0xFF,
        TED_POSTCOPY_SCENE_INIT_ADDR >> 8,
        0xC3, entry_addr & 0xFF, entry_addr >> 8,
    ])

    if _os.environ.get("PENTA_TED_INWINDOW_GDMA", "0") == "1":
        # $578C is the in-window one-block DMA service in this experiment,
        # not a standalone postcopy publisher.  DB91 calls this gate only to
        # install the two private planes on the cold stock-copy path; a ready
        # call is therefore a bounded cleanup/return, never a DMA entry.
        inwindow_lazy_gate = bytes([
            0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
            TED_INCREMENTAL_READY_ADDR >> 8, 0x3C,
            0xC2, TED_POSTCOPY_SCENE_INIT_ADDR & 0xFF,
            TED_POSTCOPY_SCENE_INIT_ADDR >> 8,
            0xFB, 0xC9,
        ])
        return {TED_INCREMENTAL_LAZY_GATE_ADDR: inwindow_lazy_gate}

    if (
        _os.environ.get("PENTA_TED_DIRECT_PUBLISHER_NOOP", "0") == "1"
    ):
        # Controlled diagnostic bisection: retain cold installation and the
        # stock tile publisher, but do not publish the maintained attr plane.
        return {
            TED_INCREMENTAL_LAZY_GATE_ADDR: lazy_gate,
            entry_addr: bytes([0xFB, 0xC9]),
        }

    if _os.environ.get("PENTA_TED_HDMA_PIGGYBACK", "0") == "1":
        # The paired publisher runs only after DB87 returns.  On the cold path
        # the two-bank installer also tail-jumps here, so make this a bounded
        # cleanup/return instead of launching the legacy SVBK4-only GDMA.
        # The gate's caller then publishes from the correctly selected bank.
        return {
            TED_INCREMENTAL_LAZY_GATE_ADDR: lazy_gate,
            entry_addr: bytes([0xFB, 0xC9]),
        }

    entry = bytes([
        0xF3, 0xC5, 0xD5, 0xE5,
        0x7C, 0xE6, 0xFC, 0xE0, TED_SANITIZER_TILE_MASK_HRAM,
        0x3E, 0x04, 0xE0, 0x70,            # select maintained plane
        0x3E, 0x01, 0xE0, 0x4F,            # attribute VRAM bank
        0x3E, 0xD0, 0xE0, 0x51,
        0xAF, 0xE0, 0x52,
        0xC3, setup_addr & 0xFF, setup_addr >> 8,
    ])
    setup = bytes([
        0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xE0, 0x53,
        0xAF, 0xE0, 0x54,
        0x3E, 0x2F, 0xE0, 0x55,
        0xC3, wait_addr & 0xFF, wait_addr >> 8,
    ])
    wait = _Asm()
    wait.label("busy")
    wait.db(0xF0, 0x55, 0xCB, 0x7F)
    wait.jr(0x28, "busy")
    wait.db(
        0xAF, 0xE0, 0x4F,
        0x3C, 0xE0, 0x70,
        0xE1, 0xD1, 0xC1, 0xFB, 0xC9,
    )
    fragments = {
        TED_INCREMENTAL_LAZY_GATE_ADDR: lazy_gate,
        entry_addr: entry,
        setup_addr: setup,
        wait_addr: wait.finish(),
    }
    for address, payload in fragments.items():
        assert len(payload) <= ARENA_SANITIZER_FRAGMENT_SIZE, (
            hex(address), len(payload)
        )
    return fragments


def build_ted_postcopy_scene_rearm_fragments() -> dict[int, bytes]:
    """Share the nine-byte Crystal gate with Ted's transition-only epoch."""
    dispatch = bytes([
        0xFE, CRYSTAL_DRAGON_SCENE,
        0xCA, TED_POSTCOPY_CRYSTAL_REARM_ADDR & 0xFF,
        TED_POSTCOPY_CRYSTAL_REARM_ADDR >> 8,
        0xFE, 0x10, 0xC0,
        0xC3, TED_POSTCOPY_SCENE_INIT_ADDR & 0xFF,
        TED_POSTCOPY_SCENE_INIT_ADDR >> 8,
    ])
    init = _Asm()
    init.db(
        0x21, TED_POSTCOPY_GENERATION_ADDR & 0xFF,
        TED_POSTCOPY_GENERATION_ADDR >> 8,
        0x34,
    )
    init.jr(0x20, "generation_ready")       # generation zero is invalid
    init.db(0x34)
    init.label("generation_ready")
    init.db(
        0xAF, 0x2B, 0x77,                  # DF55: invalidate $9800
        0x2E, (TED_POSTCOPY_PHYSICAL_9C00_ADDR + 2) & 0xFF,
        0x77,                               # DF59: invalidate $9C00
        0x3E, 0x02,
        0x23, 0x77,                         # DF5A: FIFO begins at bank 2
        0x78, 0xC9,                         # return the new scene in A
    )
    crystal = bytes([
        0x21, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        0x36, 0x11, 0x78, 0xC9,
    ])
    fragments = {
        TED_POSTCOPY_SCENE_DISPATCH_ADDR: dispatch,
        TED_POSTCOPY_SCENE_INIT_ADDR: init.finish(),
        TED_POSTCOPY_CRYSTAL_REARM_ADDR: crystal,
    }
    assert len(dispatch) == 11
    assert len(fragments[TED_POSTCOPY_SCENE_INIT_ADDR]) == 19
    assert len(crystal) == 7
    return fragments


def build_ted_incremental_scene_rearm_fragments() -> dict[int, bytes]:
    """Invalidate lazy Ted activation on entry; retain Crystal's rearm."""
    dispatch = bytes([
        0xFE, CRYSTAL_DRAGON_SCENE,
        0xCA, TED_POSTCOPY_CRYSTAL_REARM_ADDR & 0xFF,
        TED_POSTCOPY_CRYSTAL_REARM_ADDR >> 8,
        0xFE, 0x10, 0xC0,
        0xC3, TED_INCREMENTAL_SCENE_CLEAR_ADDR & 0xFF,
        TED_INCREMENTAL_SCENE_CLEAR_ADDR >> 8,
    ])
    clear = bytes([
        0xAF,
        0xEA, TED_INCREMENTAL_READY_ADDR & 0xFF,
        TED_INCREMENTAL_READY_ADDR >> 8,
        0x3E, 0x10, 0xC9,
    ])
    crystal = bytes([
        0x21, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        0x36, 0x11, 0x78, 0xC9,
    ])
    assert len(dispatch) == 11 and len(clear) <= 9 and len(crystal) == 7
    fragments = {
        TED_POSTCOPY_SCENE_DISPATCH_ADDR: dispatch,
        TED_INCREMENTAL_SCENE_CLEAR_ADDR: clear,
        TED_POSTCOPY_CRYSTAL_REARM_ADDR: crystal,
    }
    return fragments


def build_ted_incremental_scene_installer() -> dict[int, bytes]:
    """Install the private SVBK4 clone/runtime and invalidate its epoch."""
    blob, continuation = build_ted_incremental_runtime_blob()
    assert not continuation
    records = build_ted_incremental_clone_patch_records()
    assert len(records) == 4

    def memcpy(source: int, destination: int, length: int) -> list[int]:
        return [
            0x21, source & 0xFF, source >> 8,
            0x11, destination & 0xFF, destination >> 8,
            0x01, length & 0xFF, length >> 8,
            0xCD, 0xB3, 0x09,
        ]

    def patch_record(address: int, payload: bytes) -> list[int]:
        out = [0x21, address & 0xFF, address >> 8]
        for index, value in enumerate(payload):
            out.extend([0x36, value])
            if index + 1 < len(payload):
                out.append(0x23)
        return out

    def patch_call(address: int, payload: bytes) -> list[int]:
        assert payload[0] == 0xCD and len(payload) == 3
        # CALL opcode is already present in the copied stock body.
        return [
            0x21, (address + 1) & 0xFF, (address + 1) >> 8,
            0x36, payload[1], 0x23, 0x36, payload[2],
        ]

    entry = _Asm()
    entry.db(0xF3, 0xC5, 0xD5, 0xE5)
    direct_plane = _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1"
    direct_reentry_addr = TED_POSTCOPY_SCENE_INIT_ADDR + len(entry.code)
    if direct_plane:
        # Install and initialize the identical clone/tracker/table in both
        # private banks.  C5FF is already the fail-closed cold sentinel: zero
        # selects the first SVBK5 pass, one selects the SVBK4 pass, and the
        # common finish turns the second pass's zero into ready value $FF.
        entry.db(
            0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
            TED_INCREMENTAL_READY_ADDR >> 8,
            0xEE, 0x01,
            0xEA, TED_INCREMENTAL_READY_ADDR & 0xFF,
            TED_INCREMENTAL_READY_ADDR >> 8,
            0xF6, 0x04, 0xE0, 0x70,
            0xC3,
            TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR & 0xFF,
            TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR >> 8,
        )
    else:
        entry.db(
            0x3E, 0x04, 0xE0, 0x70,
            0xAF, 0xEA, TED_INCREMENTAL_VALID_ADDR & 0xFF,
            TED_INCREMENTAL_VALID_ADDR >> 8,
            0xC3,
            TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR & 0xFF,
            TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR >> 8,
        )
    first = _Asm()
    first.db(*memcpy(0x309B,
                     TED_INCREMENTAL_CLONE_ADDR, 0x313B - 0x309B))
    first.db(*patch_call(*records[0]), *patch_call(*records[1]))
    first.db(0xC3, TED_SANITIZER_SPECIAL_ADDR & 0xFF,
             TED_SANITIZER_SPECIAL_ADDR >> 8)

    second = _Asm()
    runtime_cursor = 0
    source, length = TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS[0]
    second.db(*memcpy(source, TED_INCREMENTAL_TRACKER_ADDR, length))
    runtime_cursor += length
    source, length = TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS[1]
    # The first memcpy leaves DE at the next contiguous runtime destination.
    second.db(0x21, source & 0xFF, source >> 8,
              0x01, length & 0xFF, length >> 8,
              0xCD, 0xB3, 0x09)
    runtime_cursor += length
    direct_helper = None
    if _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1":
        direct_helper = build_ted_direct_single_writer_helpers()
        helper_source, helper_capacity = (
            TED_DIRECT_FIXED_HELPER_SOURCE_CHUNKS[0]
        )
        helper_first_length = min(helper_capacity, len(direct_helper))
        second.db(*memcpy(helper_source, TED_DIRECT_FIXED_HELPER_ADDR,
                          helper_first_length))
    second.db(0xC3, TED_SANITIZER_CLEAR_ADDR & 0xFF,
              TED_SANITIZER_CLEAR_ADDR >> 8)

    third = _Asm()
    source, length = TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS[2]
    third.db(*memcpy(source,
                     TED_INCREMENTAL_TRACKER_ADDR + runtime_cursor, length))
    runtime_cursor += length
    source, length = TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS[3]
    third.db(0x21, source & 0xFF, source >> 8,
             0x01, length & 0xFF, length >> 8,
             0xCD, 0xB3, 0x09)
    runtime_cursor += length
    if direct_helper is not None:
        helper_source, _helper_capacity = (
            TED_DIRECT_FIXED_HELPER_SOURCE_CHUNKS[1]
        )
        helper_tail_length = len(direct_helper) - helper_first_length
        third.db(*memcpy(
            helper_source,
            TED_DIRECT_FIXED_HELPER_ADDR + helper_first_length,
            helper_tail_length,
        ))
    third.db(0xC3, TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR & 0xFF,
             TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR >> 8)

    fourth = _Asm()
    for source, length in TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS[4:]:
        # Direct-plane helper installation changes DE after the D300 runtime
        # chunks.  Materialize D390 explicitly: the old implicit carry worked
        # only while these final eleven bytes happened to be zero padding.
        fourth.db(*memcpy(
            source, TED_INCREMENTAL_TRACKER_ADDR + runtime_cursor, length
        ))
        runtime_cursor += length
    assert runtime_cursor == len(blob)
    fourth.db(
        0xCD, TED_INCREMENTAL_FIXED_COPY_LEAF_ADDR & 0xFF,
        TED_INCREMENTAL_FIXED_COPY_LEAF_ADDR >> 8,
    )
    fourth.db(0xC3, TED_SANITIZER_ANCHOR_PACK_ADDR & 0xFF,
              TED_SANITIZER_ANCHOR_PACK_ADDR >> 8)

    patch_tail = _Asm()
    patch_tail.db(*patch_call(*records[2]),
                  *patch_record(*records[3]),
                  0xCD, TED_INCREMENTAL_INIT_ADDR & 0xFF,
                  TED_INCREMENTAL_INIT_ADDR >> 8)
    if direct_plane:
        patch_tail.db(
            0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
            TED_INCREMENTAL_READY_ADDR >> 8, 0xB7,
            0xC2, direct_reentry_addr & 0xFF, direct_reentry_addr >> 8,
        )
    else:
        patch_tail.db(
            0x3E, TED_INCREMENTAL_READY_VALUE,
            0xEA, TED_INCREMENTAL_READY_ADDR & 0xFF,
            TED_INCREMENTAL_READY_ADDR >> 8,
            0x3E, 0x01, 0xE0, 0x70,
        )
    patch_tail.db(
        0xC3, TED_INCREMENTAL_INSTALL_FINAL_ADDR & 0xFF,
        TED_INCREMENTAL_INSTALL_FINAL_ADDR >> 8,
    )

    finish = _Asm()
    direct_hdma = direct_plane and (
        _os.environ.get("PENTA_TED_HDMA_PIGGYBACK", "0") == "1"
    )
    direct_inwindow = direct_plane and (
        _os.environ.get("PENTA_TED_INWINDOW_GDMA", "0") == "1"
    )
    if direct_hdma:
        # Explicit cold-first -> cold-replay state. Both maintained planes are
        # complete here. Arm replay first, then write ready C5FF last so no
        # caller can observe a ready sentinel with incomplete cold state.
        finish.db(
            0x21, TED_HDMA_COLD_REPLAY_ADDR & 0xFF,
            TED_HDMA_COLD_REPLAY_ADDR >> 8,
            0x36, 0x01, 0x23, 0x35,
            0x3E, 0x01, 0xE0, 0x70,
        )
    elif direct_plane:
        finish.db(
            0x21, TED_INCREMENTAL_READY_ADDR & 0xFF,
            TED_INCREMENTAL_READY_ADDR >> 8, 0x35,
            0x3E, 0x01, 0xE0, 0x70,
        )
    if not direct_hdma and not direct_inwindow:
        finish.db(
            0x21, TED_INCREMENTAL_GENERATION_ADDR & 0xFF,
            TED_INCREMENTAL_GENERATION_ADDR >> 8, 0x34,
        )
        finish.jr(0x20, "generation_ready")
        finish.db(0x34)
        finish.label("generation_ready")
    finish.db(0xE1, 0xD1, 0xC1)
    if direct_inwindow:
        # Cold installation was entered by CALL $6290 from DB91.  The hot
        # in-window DMA service owns $578C, so finish locally with the same
        # interrupt state its former cleanup entry provided.
        finish.db(0xFB, 0xC9)
    else:
        finish.db(
            0xC3, TED_POSTCOPY_ATTR_COMPILER_ADDR & 0xFF,
            TED_POSTCOPY_ATTR_COMPILER_ADDR >> 8,
        )
    fragments = {
        TED_POSTCOPY_SCENE_INIT_ADDR: entry.finish(),
        TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR: first.finish(),
        TED_SANITIZER_SPECIAL_ADDR: second.finish(),
        TED_SANITIZER_CLEAR_ADDR: third.finish(),
        TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR: fourth.finish(),
        TED_SANITIZER_ANCHOR_PACK_ADDR: patch_tail.finish(),
        TED_INCREMENTAL_INSTALL_FINAL_ADDR: finish.finish(),
        TED_INCREMENTAL_FIXED_COPY_LEAF_ADDR: bytes([
            0x21, TED_INCREMENTAL_FIXED_RUNTIME_SOURCE_ADDR & 0xFF,
            TED_INCREMENTAL_FIXED_RUNTIME_SOURCE_ADDR >> 8,
            0x11, TED_INCREMENTAL_FIXED_RUNTIME_ADDR & 0xFF,
            TED_INCREMENTAL_FIXED_RUNTIME_ADDR >> 8,
            0x01, len(build_ted_incremental_fixed_runtime()), 0x00,
            # Tail-call memcpy; its RET returns to fourth's CALL site.
            0xC3, 0xB3, 0x09,
        ]),
    }
    for address, code in fragments.items():
        capacity = {
            TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR: 31,
            TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR: 24,
            TED_INCREMENTAL_INSTALL_FINAL_ADDR: 21,
            TED_INCREMENTAL_FIXED_COPY_LEAF_ADDR: 12,
        }.get(address, 36)
        assert len(code) <= capacity, (hex(address), len(code))
    return fragments


def build_ted_postcopy_dispatch() -> bytes:
    """Route Ted's completed pure copy; retain other arena sanitizers."""
    a = _Asm()
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x10)
    a.jr(0x28, "ted")
    a.db(0xC3, ARENA_SANITIZER_DISPATCH_ADDR & 0xFF,
         ARENA_SANITIZER_DISPATCH_ADDR >> 8)
    a.label("ted")
    # The native map copier is fixed bank-1 code. Match the existing banked
    # hazard helper contract by returning its restore bank in A.
    a.db(0x3E, 0x01, 0xC9)
    code = a.finish()
    assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE, len(code)
    return code


def build_ted_native_postcopy_wrapper() -> bytes:
    """Run Ted's byte-exact alternating copier, then its attr compiler."""
    a = _Asm()
    a.db(0x26, 0x98)                        # DB80 diagnostic entry
    a.db(0xCD, 0xA7, 0x42)                  # DB82 direct-copy entry
    a.jr(0x18, "postcopy")                  # DB85
    a.db(0xCD, 0x95, 0x42)                  # DB87 stock alternating entry
    a.label("postcopy")
    # $028A's native caller observes AF returned by $4295.  The old wrapper
    # leaked the bank-switch helper's A=1 and flags, perturbing Ted's next
    # source/layout step even though BC/DE/HL were preserved by the compiler.
    a.db(0xF5)
    a.db(0x3E, 0x0D, 0xCD, 0x61, 0x00)      # map bank 13
    compiler_addr = (
        TED_INCREMENTAL_LAZY_GATE_ADDR
        if (
            _os.environ.get("PENTA_TED_INCREMENTAL_KEY", "0") == "1"
            or _os.environ.get("PENTA_TED_DIRECT_PLANE", "0") == "1"
        )
        else TED_POSTCOPY_ATTR_COMPILER_ADDR
    )
    a.db(0xCD, compiler_addr & 0xFF, compiler_addr >> 8)
    a.db(0x3E, 0x01, 0xCD, 0x61, 0x00)      # restore bank 1
    a.db(0xF1, 0xC9)                        # exact native AF; RET
    code = a.finish()
    assert len(code) == 26
    return code


def build_ted_hdma_piggyback_copier() -> dict[int, bytes]:
    """Publish Ted's maintained attrs after the stock inactive-map tile copy.

    The routine is split only across architecture-exclusive, asserted-zero
    bank-13 caves. C1A0 is packed 24x24 while the physical tilemaps have a
    32-byte stride, so it cannot be a direct linear HDMA source.  The gate
    first runs the stock row-aware copier into the inactive map.  This helper
    then holds the matching immutable SVBK4/5 attribute plane for one 48-block
    HBlank DMA.  IME remains disabled only for that transfer; no interrupt can
    expose another WRAM bank to the DMA engine.
    """
    select_addr = 0x5830
    setup_a_addr = 0x5860
    setup_b_addr = 0x623C
    setup_c_addr = 0x6530
    wait_addr = 0x58C0
    cold_replay_addr = TED_SANITIZER_COMPARE_ADDR

    select = _Asm()
    # DB87 has already toggled the native selector and copied the matching
    # packed tile source.  Reconstruct that just-completed physical target
    # without touching the selector a second time.
    select.db(0xFA, 0x0B, 0xDC, 0xE6, 0x01, 0x26, 0x98)
    select.jr(0x28, "selected")
    select.db(0x26, 0x9C)
    select.label("selected")
    select.db(0xF3, 0xC3, setup_a_addr & 0xFF, setup_a_addr >> 8)

    setup_a = bytes([
        0x2E, 0x00,                       # L=0; preserve post-toggle A
        # Select's A is the post-toggle map bit: $9800->SVBK4,
        # $9C00->SVBK5. Hold it throughout the attribute HBlank DMA.
        0xC6, 0x04, 0x47, 0xE0, 0x70,
        0x3E, 0xD0, 0xE0, 0x51,           # padded attribute plane
        0x7C, 0xE0, 0x53,                 # selected physical map
        0xAF,
        0xC3, setup_b_addr & 0xFF, setup_b_addr >> 8,
    ])
    setup_b = bytes([
        0xE0, 0x52, 0xE0, 0x54,
        0x3E, 0x01, 0xE0, 0x4F,           # destination VRAM attr bank
        0x3E, 0xAF, 0xE0, 0x55,
        0xC3, wait_addr & 0xFF, wait_addr >> 8,
    ])
    # Final ABI body. The fixed wrapper adds three pages to H and remaps ROM1.
    setup_c = bytes([
        0xAF, 0xE0, 0x4F,                 # restore VBK0
        0x11, 0xE0, 0xC3,
        0x01, 0x08, 0x00,
        0xBF, 0xC9,                       # native Z+N flags; RET
    ])

    wait = _Asm()
    wait.label("wait_inactive")
    wait.db(0xF0, 0x55)
    wait.db(0xCB, 0x7F)
    wait.jr(0x28, "wait_inactive")
    wait.db(
        0x3E, 0x01, 0xE0, 0x70,           # native interrupt WRAM bank
        0xAF, 0xE0, 0x4F,                 # native tile VRAM bank
        0xFB,
        0xC3, cold_replay_addr & 0xFF, cold_replay_addr >> 8,
    )

    cold_replay = _Asm()
    cold_replay.db(
        0xFA, TED_HDMA_COLD_REPLAY_ADDR & 0xFF,
        TED_HDMA_COLD_REPLAY_ADDR >> 8,
        0xB7,
    )
    cold_replay.jr(0x28, "done")
    cold_replay.db(
        0xAF,
        0xEA, TED_HDMA_COLD_REPLAY_ADDR & 0xFF,
        TED_HDMA_COLD_REPLAY_ADDR >> 8,
        0x3C,
        0xEA, 0x0B, 0xDC,                 # replay pre-toggle selector=1
    )
    cold_replay.label("done")
    cold_replay.db(0xC3, setup_c_addr & 0xFF, setup_c_addr >> 8)

    fragments = {
        select_addr: select.finish(),
        setup_a_addr: setup_a,
        setup_b_addr: setup_b,
        setup_c_addr: setup_c,
        wait_addr: wait.finish(),
        cold_replay_addr: cold_replay.finish(),
    }
    capacities = {
        select_addr: 18, setup_a_addr: 18, setup_b_addr: 17,
        setup_c_addr: 11, wait_addr: 18,
        cold_replay_addr: ARENA_SANITIZER_FRAGMENT_SIZE,
    }
    for address, payload in fragments.items():
        assert len(payload) <= capacities[address], (hex(address), len(payload))
    return fragments


def build_ted_hdma_piggyback_wrapper() -> bytes:
    """Fixed-bank Ted entry: map the private copier and restore native ABI."""
    code = bytes([
        0x3E, 0x0D, 0xCD, 0x61, 0x00,
        0xCD, 0x30, 0x58,
        0x24, 0x24, 0x24,                  # map base -> stock final HL
        0x3E, 0x01, 0xBF,
        0xC3, 0x61, 0x00,                 # mapper RET returns to $028D
    ])
    assert len(code) == 17
    return code


def build_ted_inwindow_wrapper() -> bytes:
    """Fixed-bank mapper for the Ted-only in-window tile/attr copier."""
    code = bytes([
        # Private SVBK4/5 makes the ordinary ISR stack physically wrong.
        # $61B0 restores SVBK1 and re-enables IME before transport begins.
        0xF3,
        0x3E, 0x0D, 0xCD, 0x61, 0x00,
        0xCD, TED_INWINDOW_ENTRY_ADDR & 0xFF,
        TED_INWINDOW_ENTRY_ADDR >> 8,
        0x00, 0x00,
        0x3E, 0x01, 0xBF,
        0xC3, 0x61, 0x00,
    ])
    assert len(code) == 17
    return code


def build_ted_inwindow_gate() -> bytes:
    """Use stock publication cold, then the ready in-window copier."""
    code = bytes([
        0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
        TED_INCREMENTAL_READY_ADDR >> 8,
        0x3C,
        0x28, 0x04,
        0xCD, 0x91, 0xDB,
        0xC9,
        0xC3, 0x38, 0x08,
    ])
    assert len(code) <= 17
    return code + bytes(17 - len(code))


def _build_rejected_ted_incremental_helper_classifier() -> tuple[bytes, dict[int, bytes]]:
    """Build the O(1) direct-write classifier and bounded crown repair.

    The private entry at D500 is the publication dirty gate; D50A is called
    for each native source write. D900/D000 are always publication-ready,
    while DC00 retains raw tiles for the rare old/new-envelope repair.
    """
    a = _Asm()
    a.db(0xFA, TED_INWINDOW_DIRTY_ADDR & 0xFF,
         TED_INWINDOW_DIRTY_ADDR >> 8, 0xB7)
    a.db(0xCA, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
         TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8)
    a.db(0xC3, TED_INWINDOW_ENVELOPE_FRONT_ADDR & 0xFF,
         TED_INWINDOW_ENVELOPE_FRONT_ADDR >> 8)
    assert len(a.code) == 10
    a.label("classify")
    a.db(
        0xC5,                              # preserve caller's loop counters
        0x1A, 0x13, 0x47,                 # B = raw; advance source
        0xD5,                              # save advanced source
        0x54, 0x5D, 0x7A, 0xC6, 0x0C, 0x57,
        0x78, 0x12,                       # raw DC00 cell
        # Any canonical crown member may complete a differently ordered write.
        # Reconstruct its candidate start and require all five raw cells.
        0xFE, 0x02,
    )
    a.jr(0x38, "kind")
    a.db(0xFE, 0x07)
    a.jr(0x30, "kind")
    crown_call = len(a.code)
    a.db(0xCD, 0x00, 0x00)
    a.label("kind")
    a.db(0x78, 0xFE, 0x02)
    a.jr(0x38, "plain")
    a.db(0xFE, 0x77)
    a.jr(0x38, "numbered")
    a.db(0xFE, 0x7B)
    a.jr(0x38, "neutral")
    # Every measured sparse contour ID $7B-$86, including the connector
    # halves $7C/$7E/$7F/$81, owns an explicit Ted material.
    a.db(0xFE, 0x7B)
    a.jr(0x38, "neutral")
    a.db(0xFE, 0x87)
    a.jr(0x38, "colored")
    a.jr(0x18, "neutral")
    a.label("numbered")
    geometry_call = len(a.code)
    a.db(0xCD, 0x00, 0x00)
    a.jr(0x20, "neutral")
    a.label("colored")
    a.db(0xE5, 0x68, 0x26, WRAM_BG_TABLE >> 8, 0x7E, 0xE1)
    a.jr(0x18, "attr")
    a.label("plain")
    a.db(0xAF)
    a.jr(0x18, "attr")
    a.label("neutral")
    a.db(0xAF, 0x47)
    a.label("attr")
    a.db(
        0x77,                             # selected attribute plane
        0x54, 0x5D, 0x7A, 0xC6, 0x09, 0x57,
        0x78, 0x12,                       # selected sanitized tile plane
        0x23, 0xD1, 0xC1, 0xC9,
    )

    a.label("crown")
    crown_addr = TED_INWINDOW_SANITIZER_ADDR + a.labels["crown"]
    # Candidate start is current-(tile-$02). Reject a row wrap, then require
    # the exact five-byte sequence regardless of native write order.
    a.db(0xE5, 0xD5, 0xC5,
         0x78, 0xD6, 0x02, 0x4F,
         0x7D, 0xE6, 0x1F, 0xB9)
    a.jr(0x38, "crown_out")
    a.db(0x7D, 0x91, 0x6F, 0x54, 0x5D,
         0x7A, 0xC6, 0x0C, 0x57)
    a.db(0x0E, 0x02)
    a.label("crown_cell")
    a.db(0x1A, 0xB9)
    a.jr(0x20, "crown_out")
    a.db(0x13, 0x0C, 0x79, 0xFE, 0x07)
    a.jr(0x20, "crown_cell")
    # C=row and D=column for the candidate HL.
    a.db(0x7D, 0xE6, 0x1F, 0x57,
         0x7D, 0x07, 0x07, 0x07, 0xE6, 0x07, 0x4F,
         0x7C, 0xE6, 0x03, 0x07, 0x07, 0x07, 0xB1, 0x4F,
         0x21, TED_INWINDOW_CURRENT_VALID_ADDR & 0xFF,
         TED_INWINDOW_CURRENT_VALID_ADDR >> 8, 0x7E, 0xB7)
    a.jr(0x28, "crown_set")
    a.db(0x23, 0x23, 0x7E, 0xB9)
    a.jr(0x20, "crown_changed")
    a.db(0x23, 0x7E, 0xBA)
    a.jr(0x28, "crown_out")
    a.label("crown_changed")
    a.db(
        0x21, TED_INWINDOW_CURRENT_ROW_ADDR & 0xFF,
        TED_INWINDOW_CURRENT_ROW_ADDR >> 8,
        0x11, TED_INWINDOW_OLD_ROW_ADDR & 0xFF,
        TED_INWINDOW_OLD_ROW_ADDR >> 8,
        0x2A, 0x12, 0x13, 0x7E, 0x12,
    )
    a.label("crown_set")
    a.db(
        0x21, TED_INWINDOW_CURRENT_VALID_ADDR & 0xFF,
        TED_INWINDOW_CURRENT_VALID_ADDR >> 8,
        0x36, 0x01, 0x23, 0x36, 0x01, 0x23, 0x71, 0x23, 0x72,
    )
    a.label("crown_out")
    a.db(0xC1, 0xD1, 0xE1, 0xC9)

    a.label("geometry")
    geometry_addr = TED_INWINDOW_SANITIZER_ADDR + a.labels["geometry"]
    a.db(0xC5, 0xD5, 0xE5,
         0x7D, 0xE6, 0x1F, 0x57,
         0x7D, 0x07, 0x07, 0x07, 0xE6, 0x07, 0x4F,
         0x7C, 0xE6, 0x03, 0x07, 0x07, 0x07, 0xB1, 0x4F,
         0xFA, TED_INWINDOW_CURRENT_ROW_ADDR & 0xFF,
         TED_INWINDOW_CURRENT_ROW_ADDR >> 8, 0x5F, 0x79, 0x93,
         0xE6, 0x1F, 0xFE, 0x0E)
    a.jr(0x30, "geometry_out")
    a.db(0x87, 0xC6, TED_INWINDOW_ROW_TABLE_ADDR & 0xFF, 0x6F,
         0x26, TED_INWINDOW_ROW_TABLE_ADDR >> 8,
         0xFA, TED_INWINDOW_CURRENT_COL_ADDR & 0xFF,
         TED_INWINDOW_CURRENT_COL_ADDR >> 8, 0x4F,
         0x7A, 0x91, 0xC6, 0x04, 0xE6, 0x1F,
         0xBE)
    a.jr(0x38, "geometry_out")
    a.db(0x23, 0xBE)
    a.jr(0x30, "geometry_out")
    a.db(0xE1, 0xD1, 0xC1, 0xAF, 0xC9)
    a.label("geometry_out")
    a.db(0xE1, 0xD1, 0xC1, 0xF6, 0x01, 0xC9)

    runtime = bytearray(a.finish())
    crown_offset = a.labels["crown"]
    geometry_offset = a.labels["geometry"]
    fixed_crown_addr = TED_INWINDOW_PRIVATE_CROWN_HELPER_ADDR
    fixed_geometry_addr = TED_INWINDOW_PRIVATE_GEOMETRY_HELPER_ADDR
    runtime[crown_call + 1:crown_call + 3] = fixed_crown_addr.to_bytes(
        2, "little"
    )
    runtime[geometry_call + 1:geometry_call + 3] = fixed_geometry_addr.to_bytes(
        2, "little"
    )
    assert a.labels["classify"] == 10
    classifier = runtime[:crown_offset]
    crown_helper = runtime[crown_offset:geometry_offset]
    geometry_helper = runtime[geometry_offset:]
    assert len(classifier) <= TED_INWINDOW_SANITIZER_SOURCE_SIZE, len(classifier)
    assert (
        TED_INWINDOW_SANITIZER_ADDR + TED_INWINDOW_SANITIZER_SOURCE_SIZE
        == TED_INWINDOW_PRIVATE_CROWN_HELPER_ADDR
    )
    assert TED_INWINDOW_PRIVATE_CROWN_HELPER_ADDR + len(crown_helper) <= 0xD600
    assert TED_INWINDOW_PRIVATE_GEOMETRY_HELPER_ADDR + len(
        geometry_helper
    ) <= TED_DIRECT_TILE_PLANE_ADDR
    classifier.extend(bytes(
        TED_INWINDOW_SANITIZER_SOURCE_SIZE - len(classifier)
    ))

    # Publication repair is ROM-bank-13 code. Scan only the old and current
    # 14x11 bounding rectangles, invoking the same exact classifier core.
    repair = _Asm()
    repair.db(0xAF, 0xEA, TED_INWINDOW_DIRTY_ADDR & 0xFF,
              TED_INWINDOW_DIRTY_ADDR >> 8)
    repair.db(0x21, TED_INWINDOW_OLD_ROW_ADDR & 0xFF,
              TED_INWINDOW_OLD_ROW_ADDR >> 8,
              0xCD, TED_INWINDOW_ANCHOR_FRONT_ADDR & 0xFF,
              TED_INWINDOW_ANCHOR_FRONT_ADDR >> 8)
    repair.db(0x21, TED_INWINDOW_CURRENT_ROW_ADDR & 0xFF,
              TED_INWINDOW_CURRENT_ROW_ADDR >> 8,
              0xCD, TED_INWINDOW_ANCHOR_FRONT_ADDR & 0xFF,
              TED_INWINDOW_ANCHOR_FRONT_ADDR >> 8,
              0xC3, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
              TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8)

    scan_a = _Asm()
    scan_a.db(0x2A, 0x57, 0x7E, 0xD6, 0x04, 0x5F,
              0x7A, 0x6F, 0x26, 0x00)
    for _ in range(5):
        scan_a.db(0x29)
    scan_a.db(0xC3, TED_INWINDOW_ENVELOPE_FINAL_ADDR & 0xFF,
              TED_INWINDOW_ENVELOPE_FINAL_ADDR >> 8)

    scan_b = bytes([
        0x19, 0x7C, 0xC6, 0xD0, 0x67,
        0x54, 0x5D, 0x7A, 0xC6, 0x0C, 0x57,
        0x06, 0x0E,
        0xC3, TED_INWINDOW_ANCHOR_TAIL_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_TAIL_ADDR >> 8,
    ])

    scan_c = _Asm()
    scan_c.label("row")
    scan_c.db(0x0E, 0x0B)
    scan_c.label("cell")
    scan_c.db(0xCD, TED_INWINDOW_CLASSIFIER_ADDR & 0xFF,
              TED_INWINDOW_CLASSIFIER_ADDR >> 8, 0x0D)
    scan_c.jr(0x20, "cell")
    scan_c.db(0x7D, 0xC6, 0x15, 0x6F,
              0xC3, TED_INWINDOW_PLANE_SETUP_ADDR & 0xFF,
              TED_INWINDOW_PLANE_SETUP_ADDR >> 8)

    scan_d = bytes([
        0x30, 0x01, 0x24,
        0x7B, 0xC6, 0x15, 0x5F,
        0xC3, TED_INWINDOW_ENVELOPE_TAIL_ADDR & 0xFF,
        TED_INWINDOW_ENVELOPE_TAIL_ADDR >> 8,
    ])
    scan_e = bytes([
        0x30, 0x01, 0x14,
        0x05,
        0xC2, TED_INWINDOW_ANCHOR_TAIL_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_TAIL_ADDR >> 8,
        0xC9,
    ])

    assert len(repair.finish()) <= 24, len(repair.finish())
    assert len(scan_a.finish()) <= 18, len(scan_a.finish())
    assert len(scan_b) <= 17, len(scan_b)
    assert len(scan_c.finish()) <= 15, len(scan_c.finish())
    assert len(scan_d) <= 13, len(scan_d)
    assert len(scan_e) <= 9, len(scan_e)
    return bytes(classifier), {
        TED_INWINDOW_PRIVATE_CROWN_HELPER_ADDR: bytes(crown_helper),
        TED_INWINDOW_PRIVATE_GEOMETRY_HELPER_ADDR: bytes(geometry_helper),
        TED_INWINDOW_ENVELOPE_FRONT_ADDR: repair.finish(),
        TED_INWINDOW_ANCHOR_FRONT_ADDR: scan_a.finish(),
        TED_INWINDOW_ENVELOPE_FINAL_ADDR: scan_b,
        TED_INWINDOW_ANCHOR_TAIL_ADDR: scan_c.finish(),
        TED_INWINDOW_PLANE_SETUP_ADDR: scan_d,
        TED_INWINDOW_ENVELOPE_TAIL_ADDR: scan_e,
        TED_INWINDOW_SANITIZER_FINISH_ADDR: bytes([
            0xFA, TED_INWINDOW_TARGET_H_ADDR & 0xFF,
            TED_INWINDOW_TARGET_H_ADDR >> 8, 0x67,
            0x3E, 0x01, 0xE0, 0x70, 0xFB,
            0xC3, TED_INWINDOW_SETUP_ADDR & 0xFF,
            TED_INWINDOW_SETUP_ADDR >> 8,
        ]),
    }


def build_ted_incremental_cell_classifier_draft(
    *, packed_private_lut: bool = False,
) -> tuple[bytes, dict[int, bytes]]:
    """Build the O(1) 576-bit-mask cell writer.

    D500 is a publication entry into bank-13 crown/mask maintenance. D503 is
    the per-cell hot path. Its caller supplies C=the selected mask byte and
    B=the cell's one-hot bit, so numbered body admission is one constant-time
    AND rather than a per-cell divide. BC and DE are preserved so the native
    writer and publication delta walker share this exact classifier. No helper lives in
    switchable WRAM.
    """
    a = _Asm()
    a.db(
        0xC3, TED_INWINDOW_ENVELOPE_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ENVELOPE_FRONT_ADDR >> 8,
    )
    a.label("classify")
    a.db(
        # Input: A=raw tile, C=mask byte, B=one-hot bit, HL=attribute cell.
        # The native wrappers own raw DC00 and source iteration.
        0xD5, 0x57,                       # preserve DE; D=raw
        0xFE, 0x02,
    )
    a.jr(0x38, "plain")
    a.db(0xFE, 0x77)
    a.jr(0x38, "numbered")
    a.db(0xFE, 0x7B)
    a.jr(0x38, "neutral")
    a.db(0xFE, 0x87)
    a.jr(0x30, "neutral")
    # In $7B-$86, zero/nonzero in Ted's editable LUT is the exact sparse-ID
    # whitelist. Carry remains set from CP $87 through the lookup, while the
    # numbered AND below clears it, so both paths share the material fetch.
    a.jr(0x18, "lookup")

    a.label("numbered")
    a.db(0x79, 0xA0)                     # selected mask byte AND one-hot bit
    a.jr(0x28, "neutral")

    a.label("lookup")
    if packed_private_lut:
        # The cold installer expands tile $00 at D5FF through tile $86 at
        # D579.  Reversed storage makes the lookup raw->(FF-raw) and avoids a
        # 16-bit D579+raw carry sequence in the hot classifier.
        a.db(0xE5, 0x7A, 0x2F, 0x6F, 0x26, 0xD5, 0x7E, 0xE1)
    else:
        a.db(0xE5, 0x6A, 0x26, WRAM_BG_TABLE >> 8, 0x7E, 0xE1)
    a.jr(0x30, "attr")                   # NC: numbered body material
    a.db(0xB7)                            # C: sparse LUT entry must be nonzero
    a.jr(0x28, "neutral")
    a.jr(0x18, "attr")
    a.label("plain")
    a.db(0xAF)
    a.jr(0x18, "attr")
    a.label("neutral")
    a.db(0xAF, 0x57)
    a.label("attr")
    a.db(
        0x77,                             # selected attribute plane
        # D0-D2 -> D9-DB: set bit 3, then advance one page.  The inverse is
        # exact for all three visible plane pages and saves two hot bytes.
        0xCB, 0xDC, 0x24,
        0x7A, 0x77,                       # matching sanitized tile cell
        0x25, 0xCB, 0x9C,
        0x23, 0xD1, 0xC9,
    )
    assert (
        TED_INWINDOW_SANITIZER_ADDR + a.labels["classify"]
        == TED_INWINDOW_MASK_CLASSIFIER_ADDR
    )
    classifier = a.finish()
    assert len(classifier) <= TED_INWINDOW_SANITIZER_SOURCE_SIZE, len(
        classifier
    )
    classifier += bytes(
        TED_INWINDOW_SANITIZER_SOURCE_SIZE - len(classifier)
    )

    # Publication-side crown/mask repair is intentionally the next bounded
    # task. Keep the experiment blocked until those fragments and the D863
    # ownership receipt are both present.
    return classifier, {}


def build_ted_incremental_mask_builder_draft() -> bytes:
    """Assemble the publication-only 72-byte mask rebuild core.

    The qualified corpus restricts complete crown columns to 4/8/12/16.
    The resident envelope span bounds need only a zero/four-bit shift and
    a zero/one-byte row offset. The separate corpus gate rejects any layout
    outside that contract before this experiment can be promoted.
    """
    a = _Asm()
    # Clear all 24 three-byte mask rows.
    a.db(
        0x21, TED_INWINDOW_BODY_MASK_ADDR & 0xFF,
        TED_INWINDOW_BODY_MASK_ADDR >> 8,
        0x01, TED_INWINDOW_BODY_MASK_SIZE, 0x00,
        0xAF, 0xCD, 0xA8, 0x09,
    )
    # HL = D863 + current_row*3 + ((current_col-4)>>3).
    a.db(
        0xFA, TED_INWINDOW_CURRENT_ROW_ADDR & 0xFF,
        TED_INWINDOW_CURRENT_ROW_ADDR >> 8,
        0x6F, 0x26, 0x00, 0x44, 0x4D, 0x29, 0x09,
        0x01, TED_INWINDOW_BODY_MASK_ADDR & 0xFF,
        TED_INWINDOW_BODY_MASK_ADDR >> 8, 0x09,
        0xFA, TED_INWINDOW_CURRENT_COL_ADDR & 0xFF,
        TED_INWINDOW_CURRENT_COL_ADDR >> 8,
        0xD6, 0x04, 0x57, 0xE6, 0x04,
        0xE0, TED_SANITIZER_TILE_MASK_HRAM,
        0x7A, 0x0F, 0x0F, 0x0F, 0xE6, 0x01, 0x85, 0x6F,
        0x11, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF,
        TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8,
    )
    a.label("row")
    # Convert normalized [left,right) bounds to an eleven-bit row template.
    a.db(
        0x1A, 0x13, 0x4F,                # C=left
        0x1A, 0x13, 0x91,                # A=width; DE=next row bounds
        0xD5, 0x59, 0x57,                # save table; E=left,D=width
        0x01, 0x00, 0x00,                # BC=template
    )
    a.label("ones")
    a.db(0x37, 0xCB, 0x11, 0xCB, 0x10, 0x15)
    a.jr(0x20, "ones")
    a.label("left")
    a.db(0x7B, 0xB7)
    a.jr(0x28, "align")
    a.db(0xCB, 0x21, 0xCB, 0x10, 0x1D)
    a.jr(0x18, "left")
    a.label("align")
    a.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xB7)
    a.jr(0x28, "store")
    for _ in range(4):
        a.db(0xCB, 0x21, 0xCB, 0x10)
    a.label("store")
    a.db(0x71, 0x23, 0x70, 0x23, 0xD1, 0x7B, 0xFE, 0xFC)
    a.jr(0x20, "row")
    a.db(0xC9)
    return a.finish()


def build_ted_incremental_mask_publication_gate_draft() -> bytes:
    """Validate the writer-accumulated crown and dispatch mask delta work."""
    a = _Asm()
    a.db(
        0x21, TED_INWINDOW_CANDIDATE_COUNT_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COUNT_ADDR >> 8,
        0x7E, 0x36, 0x00, 0xFE, 0x01,
    )
    a.jr(0x20, "invalid")
    a.db(
        0x23, 0x5E, 0x23, 0x56,           # DE=candidate source
        0x23, 0x46, 0x23, 0x4E,           # B=row,C=column
        0xC5, 0x06, 0x02,
    )
    a.label("crown")
    a.db(0x1A, 0x13, 0xB8)
    a.jr(0x20, "invalid_pop")
    a.db(0x04, 0x78, 0xFE, 0x07)
    a.jr(0x20, "crown")
    a.db(0xC1, 0x78, 0xFE, 0x0B)
    a.jr(0x30, "invalid")
    # Runtime bounds mirror the corpus gate: row <=10, col 4/8/12/16.
    a.db(0x79, 0xFE, 0x04)
    a.jr(0x38, "invalid")
    a.db(0xFE, 0x11)
    a.jr(0x30, "invalid")
    a.db(0xE6, 0x03)
    a.jr(0x20, "invalid")
    # Identical crowns leave the resident mask untouched.
    a.db(0x21, TED_INWINDOW_CURRENT_VALID_ADDR & 0xFF,
         TED_INWINDOW_CURRENT_VALID_ADDR >> 8, 0x7E, 0xB7)
    a.jr(0x28, "changed")
    a.db(0x23, 0x7E, 0xB8)
    a.jr(0x20, "changed")
    a.db(0x23, 0x7E, 0xB9)
    a.jr(0x28, "finish")
    a.label("changed")
    a.db(
        0x21, TED_INWINDOW_CURRENT_VALID_ADDR & 0xFF,
        TED_INWINDOW_CURRENT_VALID_ADDR >> 8,
        0x36, 0x01, 0x23, 0x70, 0x23, 0x71,
    )
    a.jr(0x18, "rebuild")
    a.label("invalid")
    a.db(
        0x21, TED_INWINDOW_CURRENT_VALID_ADDR & 0xFF,
        TED_INWINDOW_CURRENT_VALID_ADDR >> 8, 0x36, 0x00,
    )
    a.jr(0x18, "rebuild")
    a.label("invalid_pop")
    a.db(0xC1)
    a.jr(0x18, "invalid")
    a.label("rebuild")
    a.db(
        0xCD, TED_INWINDOW_ENVELOPE_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ENVELOPE_FRONT_ADDR >> 8,
        0xCD, TED_INWINDOW_ANCHOR_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_FRONT_ADDR >> 8,
    )
    a.label("finish")
    a.db(
        0xC3, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
        TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8,
    )
    return a.finish()


def build_ted_incremental_specialized_fit_draft() -> tuple[bytes, bytes, bytes]:
    """Assemble the compact crown gate, nibble builder, and fused repair.

    This is a measured fit artifact, not an installer.  The writer-side
    accumulator contract is D843=packed crown key, D844=precomputed low byte
    of the D579 row base (including the byte offset), and D845=0/1 nibble
    shift.  D85C holds the last published key; FF means no valid crown.
    """
    key_addr = TED_INWINDOW_CANDIDATE_ROW_ADDR
    base_low_addr = TED_INWINDOW_CANDIDATE_COL_ADDR
    shift_addr = base_low_addr + 1
    current_key_addr = TED_INWINDOW_CURRENT_VALID_ADDR
    diff_hram = TED_SANITIZER_COUNTER_HRAM

    gate = _Asm()
    gate.db(
        0x21, TED_INWINDOW_CANDIDATE_COUNT_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COUNT_ADDR >> 8,
        0x7E, 0x36, 0x00, 0x3D,
    )
    gate.jr(0x20, "invalid")
    gate.db(0x23, 0x5E, 0x23, 0x56, 0x06, 0x02)
    gate.label("crown")
    gate.db(0x1A, 0x13, 0xB8)
    gate.jr(0x20, "invalid")
    gate.db(0x04, 0x78, 0xFE, 0x07)
    gate.jr(0x20, "crown")
    gate.db(0xFA, key_addr & 0xFF, key_addr >> 8, 0xFE, 0xFF)
    gate.jr(0x28, "invalid")
    gate.jr(0x18, "compare")
    gate.label("invalid")
    gate.db(0x3E, 0xFF)
    gate.label("compare")
    gate.db(0x21, current_key_addr & 0xFF, current_key_addr >> 8, 0xBE)
    gate.jr(0x28, "finish")
    gate.db(
        0x77,
        0xCD, TED_INWINDOW_ENVELOPE_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ENVELOPE_FRONT_ADDR >> 8,
    )
    gate.label("finish")
    gate.db(
        0xC3, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
        TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8,
    )

    builder = _Asm()
    builder.db(
        0x21, TED_INWINDOW_NEXT_MASK_ADDR & 0xFF,
        TED_INWINDOW_NEXT_MASK_ADDR >> 8,
        0x01, TED_INWINDOW_BODY_MASK_SIZE, 0x00,
        0xAF, 0xCD, 0xA8, 0x09,
        0xFA, current_key_addr & 0xFF, current_key_addr >> 8,
        0x3C,
    )
    builder.jr(0x28, "delta")
    builder.db(
        0xFA, base_low_addr & 0xFF, base_low_addr >> 8,
        0x6F, 0x26, TED_INWINDOW_NEXT_MASK_ADDR >> 8,
        0x11, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF,
        TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8,
    )
    builder.label("row")
    builder.db(0x1A, 0x13, 0x4F, 0x1A, 0x13, 0x47)
    builder.db(0xFA, shift_addr & 0xFF, shift_addr >> 8, 0xB7)
    builder.jr(0x28, "store")
    for _ in range(4):
        builder.db(0xCB, 0x21, 0xCB, 0x10)
    builder.label("store")
    builder.db(0x71, 0x23, 0x70, 0x23, 0x23, 0x7B, 0xFE, 0xFC)
    builder.jr(0x20, "row")
    builder.label("delta")
    builder.db(
        0xC3, TED_INWINDOW_ANCHOR_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_FRONT_ADDR >> 8,
    )

    delta = _Asm()
    delta.db(
        0x21, TED_INWINDOW_NEXT_MASK_ADDR & 0xFF,
        TED_INWINDOW_NEXT_MASK_ADDR >> 8,
        0x11, TED_INWINDOW_BODY_MASK_ADDR & 0xFF,
        TED_INWINDOW_BODY_MASK_ADDR >> 8,
        0x01, 0x00, 0xD0,
    )
    calls: list[int] = []
    advance_calls: list[int] = []
    delta.label("row")
    for _ in range(3):
        calls.append(len(delta.code))
        delta.db(0xCD, 0x00, 0x00)
    # Reuse the byte worker's existing BC+=8/RET epilogue for row padding.
    advance_calls.append(len(delta.code))
    delta.db(0xCD, 0x00, 0x00)
    delta.db(0x78, 0xFE, 0xD3)
    delta.jr(0x20, "row")
    delta.db(0xC9)

    delta.label("byte")
    byte_addr = TED_INWINDOW_ANCHOR_FRONT_ADDR + len(delta.code)
    delta.db(0x1A, 0xAE, 0xE0, diff_hram, 0xB7)
    delta.jr(0x28, "same")
    delta.db(
        0x2A, 0x12, 0x13,
        0xE5, 0xD5, 0x60, 0x69, 0x4F,
        0xF0, diff_hram, 0x5F, 0x06, 0x01,
    )
    delta.label("bit")
    delta.db(0x7B, 0xA0)
    delta.jr(0x28, "unchanged")
    delta.db(
        0xE5, 0x7C, 0xC6, 0x0C, 0x67, 0x7E, 0xE1,
        0xCD, TED_INWINDOW_MASK_CLASSIFIER_ADDR & 0xFF,
        TED_INWINDOW_MASK_CLASSIFIER_ADDR >> 8,
    )
    delta.jr(0x18, "next_bit")
    delta.label("unchanged")
    delta.db(0x23)
    delta.label("next_bit")
    delta.db(0xCB, 0x20)
    delta.jr(0x20, "bit")
    delta.db(0x44, 0x4D, 0xD1, 0xE1, 0xC9)
    delta.label("same")
    delta.db(0x23, 0x13)
    delta.label("advance_attr")
    advance_addr = TED_INWINDOW_ANCHOR_FRONT_ADDR + len(delta.code)
    delta.db(0x79, 0xC6, 0x08, 0x4F)
    delta.jr(0x30, "same_ready")
    delta.db(0x04)
    delta.label("same_ready")
    delta.db(0xC9)
    delta_blob = bytearray(delta.finish())
    for operand in calls:
        delta_blob[operand + 1:operand + 3] = bytes(
            (byte_addr & 0xFF, byte_addr >> 8)
        )
    for operand in advance_calls:
        delta_blob[operand + 1:operand + 3] = bytes(
            (advance_addr & 0xFF, advance_addr >> 8)
        )
    return gate.finish(), builder.finish(), bytes(delta_blob)


def build_ted_incremental_streaming_fit_draft() -> tuple[bytes, bytes]:
    """Measure a no-next-mask streaming builder/XOR repair implementation."""
    gate, _builder, _delta = build_ted_incremental_specialized_fit_draft()
    prefix_addr = TED_INWINDOW_CANDIDATE_COL_ADDR + 2
    shift_addr = TED_INWINDOW_CANDIDATE_COL_ADDR + 1
    offset_addr = prefix_addr + 1
    diff_hram = TED_SANITIZER_COUNTER_HRAM
    rows_hram = TED_SANITIZER_EXPECTED_HRAM

    a = _Asm()
    a.db(
        0x21, TED_INWINDOW_BODY_MASK_ADDR & 0xFF,
        TED_INWINDOW_BODY_MASK_ADDR >> 8,
        0x01, 0x00, 0xD0,
        0x11, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF,
        TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8,
        0x3E, 0x18, 0xE0, rows_hram,
    )
    row_calls: list[int] = []
    zero_calls: list[int] = []
    a.label("row")
    a.db(0xFA, prefix_addr & 0xFF, prefix_addr >> 8, 0xB7)
    a.jr(0x28, "maybe_body")
    a.db(0x3D, 0xEA, prefix_addr & 0xFF, prefix_addr >> 8)
    row_calls.append(len(a.code))
    a.db(0xCD, 0x00, 0x00)
    a.jr(0x18, "row_done")
    a.label("maybe_body")
    a.db(0x7B, 0xFE, 0xFC)
    a.jr(0x28, "zero_row")
    a.db(0xC5, 0x1A, 0x13, 0x4F, 0x1A, 0x13, 0x47)
    a.db(0xFA, shift_addr & 0xFF, shift_addr >> 8, 0xB7)
    a.jr(0x28, "shifted")
    for _ in range(4):
        a.db(0xCB, 0x21, 0xCB, 0x10)
    a.label("shifted")
    a.db(0xFA, offset_addr & 0xFF, offset_addr >> 8, 0xB7)
    a.jr(0x28, "no_lead")
    a.db(0xAF)
    zero_calls.append(len(a.code))
    a.db(0xCD, 0x00, 0x00)
    a.label("no_lead")
    a.db(0x79)
    zero_calls.append(len(a.code))
    a.db(0xCD, 0x00, 0x00)
    a.db(0x78)
    zero_calls.append(len(a.code))
    a.db(0xCD, 0x00, 0x00)
    a.db(0xFA, offset_addr & 0xFF, offset_addr >> 8, 0xB7)
    a.jr(0x20, "body_done")
    a.db(0xAF)
    zero_calls.append(len(a.code))
    a.db(0xCD, 0x00, 0x00)
    a.label("body_done")
    a.db(0xC1)
    a.jr(0x18, "row_done")
    a.label("zero_row")
    row_calls.append(len(a.code))
    a.db(0xCD, 0x00, 0x00)
    a.label("row_done")
    a.db(0xF0, rows_hram, 0x3D, 0xE0, rows_hram)
    a.jr(0x20, "row")
    a.db(0xC9)

    a.label("zero_helper")
    zero_addr = TED_INWINDOW_ENVELOPE_FRONT_ADDR + len(a.code)
    for _ in range(3):
        a.db(0xAF)
        zero_calls.append(len(a.code))
        a.db(0xCD, 0x00, 0x00)
    a.db(0xC9)

    a.label("byte")
    byte_addr = TED_INWINDOW_ENVELOPE_FRONT_ADDR + len(a.code)
    a.db(0xF5, 0xAE)
    a.jr(0x28, "same")
    a.db(
        0xE0, diff_hram, 0xF1, 0x22,
        0xE5, 0xD5, 0x60, 0x69, 0x4F,
        0xF0, diff_hram, 0x5F, 0x06, 0x08,
    )
    a.label("bit")
    a.db(0xCB, 0x1B)
    a.jr(0x30, "unchanged")
    a.db(0xCB, 0x19, 0x16, 0x00, 0xCB, 0x12)
    a.db(
        0xE5, 0x7C, 0xC6, 0x0C, 0x67, 0x7E, 0xE1,
        0xCD, TED_INWINDOW_MASK_CLASSIFIER_ADDR & 0xFF,
        TED_INWINDOW_MASK_CLASSIFIER_ADDR >> 8,
    )
    a.jr(0x18, "next_bit")
    a.label("unchanged")
    a.db(0xCB, 0x19, 0x23)
    a.label("next_bit")
    a.db(0x05)
    a.jr(0x20, "bit")
    a.db(0x44, 0x4D, 0xD1, 0xE1, 0xC9)
    a.label("same")
    a.db(0xF1, 0x23, 0x79, 0xC6, 0x08, 0x4F)
    a.jr(0x30, "same_ready")
    a.db(0x04)
    a.label("same_ready")
    a.db(0xC9)

    blob = bytearray(a.finish())
    for operand in row_calls:
        blob[operand + 1:operand + 3] = bytes(
            (zero_addr & 0xFF, zero_addr >> 8)
        )
    for operand in zero_calls:
        blob[operand + 1:operand + 3] = bytes(
            (byte_addr & 0xFF, byte_addr >> 8)
        )
    return gate, bytes(blob)


def build_ted_incremental_packed_geometry_draft() -> tuple[bytes, bytes]:
    """Return packed nibble spans plus their measured bit-setting builder."""
    spans = (
        (4, 9), (2, 10), (2, 10), (2, 10), (2, 10), (2, 11),
        (1, 11), (0, 11), (0, 11), (0, 11), (1, 11), (2, 10),
        (4, 10), (5, 9),
    )
    table = bytes((left << 4) | (right - 4) for left, right in spans)
    table += bytes(1 << bit for bit in range(8))
    assert len(table) == 22
    mask_lut_addr = TED_ENVELOPE_ROW_TABLE_ROM_ADDR + 14
    shift_addr = TED_INWINDOW_CANDIDATE_COL_ADDR + 1

    a = _Asm()
    a.db(
        0x21, TED_INWINDOW_NEXT_MASK_ADDR & 0xFF,
        TED_INWINDOW_NEXT_MASK_ADDR >> 8,
        0x01, TED_INWINDOW_BODY_MASK_SIZE, 0x00,
        0xAF, 0xCD, 0xA8, 0x09,
        0xFA, TED_INWINDOW_CURRENT_VALID_ADDR & 0xFF,
        TED_INWINDOW_CURRENT_VALID_ADDR >> 8, 0x3C,
    )
    a.jr(0x28, "delta")
    a.db(
        0xFA, TED_INWINDOW_CANDIDATE_COL_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COL_ADDR >> 8,
        0x6F, 0x26, TED_INWINDOW_NEXT_MASK_ADDR >> 8,
        0x11, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF,
        TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8,
    )
    a.label("row")
    a.db(
        0x1A, 0x13, 0xD5, 0xE5, 0x47,
        0xE6, 0x0F, 0xC6, 0x04, 0x4F,
        0x78, 0xCB, 0x37, 0xE6, 0x0F, 0x47,
        0x79, 0x90, 0x4F,
        0xFA, shift_addr & 0xFF, shift_addr >> 8, 0x80,
        0xFE, 0x08,
    )
    a.jr(0x38, "byte_ready")
    a.db(0xD6, 0x08, 0x23)
    a.label("byte_ready")
    a.db(
        0xC6, mask_lut_addr & 0xFF, 0x5F,
        0x16, mask_lut_addr >> 8, 0x1A, 0x47,
    )
    a.label("bit")
    a.db(0x7E, 0xB0, 0x77, 0xCB, 0x20)
    a.jr(0x30, "same_byte")
    a.db(0x23, 0x04)
    a.label("same_byte")
    a.db(0x0D)
    a.jr(0x20, "bit")
    a.db(0xE1, 0x23, 0x23, 0x23, 0xD1, 0x7B, 0xFE, 0xEE)
    a.jr(0x20, "row")
    a.label("delta")
    a.db(
        0xC3, TED_INWINDOW_ANCHOR_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_FRONT_ADDR >> 8,
    )
    return table, a.finish()


def build_ted_incremental_rle_geometry_draft() -> tuple[bytes, bytes]:
    """Measure the seven-run precomputed-template form of Ted's 14 rows."""
    runs = (
        (1, 0x01F0), (4, 0x03FC), (1, 0x07FC), (1, 0x07FE),
        (3, 0x07FF), (1, 0x07FE), (1, 0x03FC),
        # The last two singletons cannot be merged with an adjacent template.
        (1, 0x03F0), (1, 0x01E0),
    )
    # Nine runs, not seven: repeated templates separated by other silhouettes
    # remain distinct.  The table still reclaims one byte from the 28-byte
    # span record and shifts each run only once.
    table = b"".join(
        bytes((count, mask & 0xFF, mask >> 8)) for count, mask in runs
    )
    assert len(table) == 27
    shift_addr = TED_INWINDOW_CANDIDATE_COL_ADDR + 1
    a = _Asm()
    # A is the changed crown key supplied by the 50-byte gate.  $09A8
    # preserves DE, so D carries validity across the clear without a reload.
    a.db(
        0x57,
        0x21, TED_INWINDOW_NEXT_MASK_ADDR & 0xFF,
        TED_INWINDOW_NEXT_MASK_ADDR >> 8,
        0x01, TED_INWINDOW_BODY_MASK_SIZE, 0x00,
        0xAF, 0xCD, 0xA8, 0x09,
        0x14,
    )
    a.jr(0x28, "delta")
    a.db(
        0xFA, TED_INWINDOW_CANDIDATE_COL_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COL_ADDR >> 8,
        0x6F, 0x26, TED_INWINDOW_NEXT_MASK_ADDR >> 8,
        0x11, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF,
        TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8,
    )
    a.label("run")
    a.db(0x1A, 0x13, 0xF5, 0x1A, 0x13, 0x4F, 0x1A, 0x13, 0x47)
    a.db(0xFA, shift_addr & 0xFF, shift_addr >> 8, 0xB7)
    a.jr(0x28, "store")
    for _ in range(4):
        a.db(0xCB, 0x21, 0xCB, 0x10)
    a.label("store")
    a.db(0xF1)
    a.label("repeat")
    a.db(0x71, 0x23, 0x70, 0x23, 0x23, 0x3D)
    a.jr(0x20, "repeat")
    a.db(0x7B, 0xFE, (TED_ENVELOPE_ROW_TABLE_ROM_ADDR + len(table)) & 0xFF)
    a.jr(0x20, "run")
    a.label("delta")
    a.db(
        0xC3, TED_INWINDOW_ANCHOR_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_FRONT_ADDR >> 8,
    )
    return table, a.finish()


def build_ted_incremental_packed_page_fit_draft() -> dict[str, bytes]:
    """Assemble the packed-LUT capacity candidate without installing it."""
    # D578 is the expansion pad immediately below tile-$86's D579 entry.  The
    # installer necessarily writes it as zero, so it is also the packed
    # architecture's cold-initialized current-key byte.  No classifier lookup
    # can address it.
    packed_current_key_addr = TED_INWINDOW_NEXT_MASK_ADDR - 1
    # D579-D5FF is the expanded reverse palette LUT in this architecture, so
    # its 72-byte next mask lives immediately after the resident D863-D8AA
    # mask.  D8AB-D8F2 is the ownership-receipt-gated scratch interval.
    packed_next_mask_addr = (
        TED_INWINDOW_BODY_MASK_ADDR + TED_INWINDOW_BODY_MASK_SIZE
    )
    values = bytes(
        ARENA_TILE_PAL["ted"].get(tile, 0) for tile in range(0x87)
    )
    assert all(value < 8 for value in values)
    packed = bytes(
        values[index] | (
            (values[index + 1] if index + 1 < len(values) else 0) << 4
        )
        for index in range(0, len(values), 2)
    )
    assert len(packed) == 68
    expanded = bytearray()
    for value in packed:
        expanded.extend((value & 0x0F, value >> 4))
    assert bytes(expanded[:0x87]) == values
    assert expanded[0x87] == 0

    classifier, _ = build_ted_incremental_cell_classifier_draft(
        packed_private_lut=True
    )

    gate = _Asm()
    gate.db(
        0x21, TED_INWINDOW_CANDIDATE_COUNT_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COUNT_ADDR >> 8,
        0x7E, 0x36, 0x00, 0x3D,
    )
    gate.jr(0x20, "invalid")
    gate.db(0x23, 0x5E, 0x23, 0x56, 0x06, 0x02)
    gate.label("crown")
    gate.db(0x1A, 0x13, 0xB8)
    gate.jr(0x20, "invalid")
    gate.db(0x04, 0x78, 0xFE, 0x07)
    gate.jr(0x20, "crown")
    gate.db(0xFA, TED_INWINDOW_CANDIDATE_ROW_ADDR & 0xFF,
            TED_INWINDOW_CANDIDATE_ROW_ADDR >> 8, 0xB7)
    gate.jr(0x28, "invalid")
    gate.jr(0x18, "compare")
    gate.label("invalid")
    gate.db(0xAF)
    gate.label("compare")
    gate.db(0x21, packed_current_key_addr & 0xFF,
            packed_current_key_addr >> 8, 0xBE)
    gate.jr(0x28, "finish")
    gate.db(0x77, 0xCD, 0x00, 0x00)       # packed publication address patched
    gate.label("finish")
    gate.db(0xC3, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
            TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8)
    gate_blob = gate.finish()

    # The direct-plane initializer already materializes HL=source, DE=D500,
    # and C=121 immediately before entering this helper.  Reuse that ABI:
    # copying here would repeat eight bytes of setup at the tightest part of
    # the fit.  The helper copies D500-D578, expands 68 packed bytes into
    # D5FF..D578, then tail-jumps to a ten-byte private clear leaf.
    installer = _Asm()
    installer.db(
        0xCD, 0xB3, 0x09,
        0x21, TED_TABLE_ADDR & 0xFF, TED_TABLE_ADDR >> 8,
        0x11, 0xFF, 0xD5, 0x06, 0x44,
    )
    installer.label("pair")
    installer.db(
        0x2A, 0x4F, 0xE6, 0x0F, 0x12, 0x1B,
        0x79, 0xCB, 0x37, 0xE6, 0x0F, 0x12, 0x1B, 0x05,
    )
    installer.jr(0x20, "pair")
    installer.db(0xC3, 0x00, 0x00)       # private clear leaf patched

    # The final packed nibble is an asserted-zero pad, so the expander exits
    # with A=0 and has already initialized the D578 published-key sentinel.
    # Only the candidate count requires an explicit cold write. A changed
    # first key rebuilds all 72 next-mask
    # bytes and the fused XOR visits all 72 resident bytes, making a bulk
    # D840-D8AA clear redundant.  The accumulator writer must overwrite its
    # D841-D845 record before it increments D840; that remains an integration
    # gate rather than an assumption made by this fit artifact.
    clear = bytes([
        0xEA, TED_INWINDOW_CANDIDATE_COUNT_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COUNT_ADDR >> 8,
        0xC9,
    ])

    _old_gate, builder, delta = build_ted_incremental_specialized_fit_draft()
    # The changed key is live in A on entry. $09A8 preserves DE, so D carries
    # validity across memset. The former final JP becomes natural fallthrough
    # into the contiguous fused delta.
    publication = bytearray(
        # Packed gate invalidity is key zero, not the specialized draft's FF.
        # Test D exactly; INC D would incorrectly turn invalid zero into one
        # and build a mask from stale candidate geometry on the cold path.
        bytes([0x57]) + builder[:10] + bytes([0x7A, 0xB7, 0x28, 0x2F])
        + builder[16:-3] + delta
    )
    # Rewrite the specialized draft's D579 scratch operands to D8AB. The
    # accumulator correspondingly supplies D844 as the low byte of its D8AB
    # row base; every qualified row remains inside the D8 page.
    publication[2:4] = packed_next_mask_addr.to_bytes(2, "little")
    publication[20] = packed_next_mask_addr >> 8
    publication[63:65] = packed_next_mask_addr.to_bytes(2, "little")
    publication = bytes(publication)
    assert len(gate_blob) == 48
    assert len(installer.finish()) == 30
    assert len(clear) == 4
    assert len(publication) == 145
    assert len(installer.finish()) + len(publication) == 175
    assert len(gate_blob) + len(clear) == 52
    return {
        "packed_lut": packed,
        "classifier": classifier,
        "gate": gate_blob,
        "installer": installer.finish(),
        "clear": clear,
        "publication": publication,
    }


def build_ted_incremental_packed_exact_fit_draft() -> dict[int, bytes]:
    """Place the corrected packed experiment in its audited byte caves.

    This remains a fit artifact, not a production installer.  In particular,
    the accumulator writer and two-bank ready ordering still need integration
    and receipts before these fragments may be emitted by the normal build.
    """
    fit = build_ted_incremental_packed_page_fit_draft()
    publication = fit["publication"]
    classifier = bytearray(fit["classifier"])

    gate_count_addr = 0x7027
    gate_crown_addr = 0x54F2
    gate_setup_addr = 0x5890
    gate_compare_addr = 0x53A5
    delta_row_addr = 0x5D4C
    delta_setup_addr = 0x5D7F
    gate_invalid_addr = delta_setup_addr + 11
    installer_front_addr = 0x5E48
    installer_front_cont_addr = gate_crown_addr + 15
    installer_low_mask_addr = 0x5E7B
    installer_low_store_addr = 0xD573
    installer_high_load_addr = 0x6250
    installer_high_store_addr = 0x58A1
    installer_control_addr = 0x6150
    packed_key_addr = TED_INWINDOW_NEXT_MASK_ADDR - 1
    packed_next_mask_addr = (
        TED_INWINDOW_BODY_MASK_ADDR + TED_INWINDOW_BODY_MASK_SIZE
    )
    publication_addr = TED_TABLE_ADDR + 68 + TED_INWINDOW_SANITIZER_SOURCE_SIZE

    # D500 publishes to the count gate. D503 remains the hot classifier ABI.
    classifier[:3] = bytes((
        0xC3, gate_count_addr & 0xFF, gate_count_addr >> 8,
    ))
    classifier_code_bytes = len(classifier.rstrip(b"\x00"))
    assert classifier_code_bytes == 59

    # Corrected publication is builder62 + delta-main27 + worker56.  The page
    # tail owns only the builder and an absolute transfer to the delta setup.
    builder = publication[:62]
    worker = bytearray(publication[89:])
    assert len(builder) == 62 and len(worker) == 56
    byte_worker_addr = TED_INWINDOW_SANITIZER_ADDR + classifier_code_bytes
    advance_worker_addr = byte_worker_addr + 46

    row = bytearray()
    for _ in range(3):
        row.extend((0xCD, byte_worker_addr & 0xFF, byte_worker_addr >> 8))
    row.extend((
        0xCD, advance_worker_addr & 0xFF, advance_worker_addr >> 8,
        0x78, 0xFE, 0xD3,
        0x20, ((delta_row_addr - (delta_row_addr + 17)) & 0xFF),
        0xC9,
    ))
    assert len(row) == 18 and row[-3:] == bytes((0x20, 0xEF, 0xC9))

    delta_setup = bytes((
        0x21, packed_next_mask_addr & 0xFF,
        packed_next_mask_addr >> 8,
        0x11, TED_INWINDOW_BODY_MASK_ADDR & 0xFF,
        TED_INWINDOW_BODY_MASK_ADDR >> 8,
        0x01, 0x00, 0xD0,
        0x18, (delta_row_addr - (delta_setup_addr + 11)) & 0xFF,
    ))
    assert len(delta_setup) == 11 and delta_setup[-1] == 0xC2

    gate_count = bytes((
        0x21, TED_INWINDOW_CANDIDATE_COUNT_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COUNT_ADDR >> 8,
        0x7E, 0x36, 0x00, 0x3D,
        0xC2, gate_invalid_addr & 0xFF, gate_invalid_addr >> 8,
        0xC3, gate_setup_addr & 0xFF, gate_setup_addr >> 8,
    ))
    gate_setup = bytes((
        0x23, 0x5E, 0x23, 0x56, 0x06, 0x02,
        0xC3, gate_crown_addr & 0xFF, gate_crown_addr >> 8,
    ))
    gate_crown = bytes((
        0x1A, 0x13, 0xB8,
        0xC2, gate_invalid_addr & 0xFF, gate_invalid_addr >> 8,
        0x04, 0x78, 0xFE, 0x07, 0x20, 0xF4,
        0xC3, gate_compare_addr & 0xFF, gate_compare_addr >> 8,
    ))
    gate_compare = bytes((
        0xFA, TED_INWINDOW_CANDIDATE_ROW_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_ROW_ADDR >> 8,
        0xB7,
        0x21, packed_key_addr & 0xFF, packed_key_addr >> 8,
        0xBE, 0x28, 0x04, 0x77,
        0xCD, publication_addr & 0xFF, publication_addr >> 8,
        0xC3, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
        TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8,
    ))
    gate_invalid = bytes((
        0xAF, 0xC3, (gate_compare_addr + 4) & 0xFF,
        (gate_compare_addr + 4) >> 8,
    ))
    assert tuple(map(len, (
        gate_count, gate_setup, gate_crown, gate_compare, gate_invalid,
    ))) == (13, 9, 15, 17, 4)

    # Memcpy exits at HL=76BD, DE=D579, BC=0. Reusing H/D and changing only
    # L/E saves two bytes before the reverse packed-table expansion. The
    # continuation falls directly into the packed-byte load, occupying the
    # crown fragment's otherwise unusable nine-byte tail without a transfer.
    installer_front = bytes((
        0xCD, 0xB3, 0x09, 0x2E, 0x00,
        0xC3, installer_front_cont_addr & 0xFF,
        installer_front_cont_addr >> 8,
    ))
    installer_front_cont = bytes((
        0x1E, 0xFF, 0x06, 0x44, 0x2A, 0x4F,
        0xC3, installer_low_mask_addr & 0xFF,
        installer_low_mask_addr >> 8,
    ))
    installer_low_mask = bytes((
        0xE6, 0x0F,
        0xC3, installer_low_store_addr & 0xFF,
        installer_low_store_addr >> 8,
    ))
    installer_low_store = bytes((
        0x12, 0x1B,
        0xC3, installer_high_load_addr & 0xFF,
        installer_high_load_addr >> 8,
    ))
    installer_high_load = bytes((
        0x79, 0xCB, 0x37, 0xE6, 0x0F,
        0xC3, installer_high_store_addr & 0xFF,
        installer_high_store_addr >> 8,
    ))
    installer_high_store = bytes((
        0x12, 0x1B, 0x05,
        0xC3, installer_control_addr & 0xFF,
        installer_control_addr >> 8,
    ))
    installer_control = bytes((
        0xC2, (installer_front_cont_addr + 4) & 0xFF,
        (installer_front_cont_addr + 4) >> 8,
        # The asserted-zero pad nibble leaves A=0 on loop completion.
        0xEA, TED_INWINDOW_CANDIDATE_COUNT_ADDR & 0xFF,
        TED_INWINDOW_CANDIDATE_COUNT_ADDR >> 8,
        0xC9,
    ))
    assert tuple(map(len, (
        installer_front, installer_front_cont, installer_low_mask,
        installer_low_store, installer_high_load,
        installer_high_store, installer_control,
    ))) == (8, 9, 5, 5, 8, 6, 7)

    private_source = (
        bytes(classifier[:classifier_code_bytes]) + bytes(worker)
        + installer_low_store + b"\x00"
    )
    assert len(private_source) == TED_INWINDOW_SANITIZER_SOURCE_SIZE
    assert private_source[-1] == 0  # D578 packed key/pad
    page_tail = builder + bytes((
        0xC3, delta_setup_addr & 0xFF, delta_setup_addr >> 8,
        0x00, 0x00,
    ))
    assert len(page_tail) == 67

    fragments = {
        TED_TABLE_ADDR: fit["packed_lut"],
        TED_TABLE_ADDR + 68: private_source,
        publication_addr: page_tail,
        gate_count_addr: gate_count,
        gate_crown_addr: gate_crown + installer_front_cont,
        gate_compare_addr: gate_compare,
        delta_row_addr: bytes(row),
        delta_setup_addr: delta_setup + gate_invalid,
        installer_front_addr: installer_front,
        gate_setup_addr: gate_setup,
        installer_low_mask_addr: installer_low_mask,
        installer_high_load_addr: installer_high_load,
        installer_high_store_addr: installer_high_store,
        installer_control_addr: installer_control,
        installer_low_store_addr: installer_low_store,
        TED_INWINDOW_SANITIZER_FINISH_ADDR: bytes((
            0xFA, TED_INWINDOW_TARGET_H_ADDR & 0xFF,
            TED_INWINDOW_TARGET_H_ADDR >> 8, 0x67,
            0x3E, 0x01, 0xE0, 0x70, 0xFB,
            0xC3, TED_INWINDOW_SETUP_ADDR & 0xFF,
            TED_INWINDOW_SETUP_ADDR >> 8,
        )),
    }
    capacities = {
        gate_count_addr: 13,
        gate_crown_addr: 24,
        gate_compare_addr: 17,
        delta_row_addr: 18,
        delta_setup_addr: 15,
        installer_front_addr: 8,
        gate_setup_addr: 9,
        installer_low_mask_addr: 5,
        installer_high_load_addr: 8,
        installer_high_store_addr: 6,
        installer_control_addr: 8,
        installer_low_store_addr: 5,
        TED_INWINDOW_SANITIZER_FINISH_ADDR: 12,
    }
    for address, capacity in capacities.items():
        assert len(fragments[address]) <= capacity, (
            hex(address), len(fragments[address]), capacity
        )
    return fragments


def build_ted_block_major_exact_fit_draft() -> dict[int, bytes]:
    """Emit the closed block-major Ted mask candidate and its exact caves.

    Even source rows keep the native two-byte destination pointers.  The
    following otherwise-unaddressed odd-row bands keep one resident mask
    nibble per 2x2 record.  A changed crown clears the old seven-run
    silhouette and draws the new one; the published key changes only after
    both passes return.
    """
    repair_addr = TED_INWINDOW_SANITIZER_ADDR + 59
    renderer_addr = TED_TABLE_ADDR + 68 + TED_INWINDOW_SANITIZER_SOURCE_SIZE
    repair_entry_addr = TED_ENVELOPE_COMPARE_ROM_ADDR
    draw_table_addr = TED_ENVELOPE_ROW_TABLE_ROM_ADDR
    clear_table_addr = draw_table_addr + 14
    key_addr = TED_INWINDOW_NEXT_MASK_ADDR - 1
    candidate_low_addr = TED_INWINDOW_CANDIDATE_SOURCE_ADDR
    candidate_high_addr = candidate_low_addr + 1
    private_setup_addr = 0x6140

    values = bytes(
        ARENA_TILE_PAL["ted"].get(tile, 0) for tile in range(0x87)
    )
    packed = bytes(
        values[index]
        | ((values[index + 1] if index + 1 < len(values) else 0) << 4)
        for index in range(0, len(values), 2)
    )
    assert len(packed) == 68 and all(value < 8 for value in values)

    classifier, _ = build_ted_incremental_cell_classifier_draft(
        packed_private_lut=True
    )
    classifier_code = classifier.rstrip(b"\x00")
    assert len(classifier_code) == 59

    # Called only when the resident nibble differs.  The entry leaf below
    # has already saved BC and placed desired in B / diff in A.
    repair = _Asm()
    repair.db(
        0xD5, 0xE5, 0xF5, 0x78, 0x12,
        0x21, 0xE8, 0xFF, 0x19,          # pointer = resident - 24
        0x2A, 0x66, 0x6F,                # HL = stored attr pointer
        0x48, 0xF1, 0x57, 0x06, 0x11,  # C=desired,D=diff,B=one-hot pair
    )
    repair.label("bit")
    repair.db(0xCB, 0x70)
    repair.jr(0x28, "row_ready")
    repair.db(0x7D, 0xC6, 0x1E, 0x6F)
    repair.jr(0x30, "row_ready")
    repair.db(0x24)
    repair.label("row_ready")
    repair.db(0x7A, 0xA0)
    repair.jr(0x28, "unchanged")
    repair.db(
        0xE5, 0x7C, 0xF6, 0x0C, 0x67, 0x7E, 0xE1,
        0xCD, TED_INWINDOW_MASK_CLASSIFIER_ADDR & 0xFF,
        TED_INWINDOW_MASK_CLASSIFIER_ADDR >> 8,
    )
    repair.jr(0x18, "next_bit")
    repair.label("unchanged")
    repair.db(0x23)
    repair.label("next_bit")
    repair.db(0xCB, 0x20)
    repair.jr(0x30, "bit")
    repair.db(0xE1, 0xD1, 0xC1, 0x13, 0x13, 0xC9)
    repair_blob = repair.finish()
    assert len(repair_blob) == 55

    # Common compare/advance leaf.  The unchanged path is only eleven bytes;
    # the changed path jumps into the 55-byte private worker above.
    repair_entry = bytes((
        0xE6, 0x0F,
        0xC5, 0x47, 0x1A, 0xA8,
        0xC2, repair_addr & 0xFF, repair_addr >> 8,
        0xC1, 0x13, 0x13, 0xC9,
    ))
    assert len(repair_entry) == 13

    renderer = _Asm()
    repair_calls: list[int] = []
    renderer.db(
        0xB7, 0xC8,                      # token zero has no silhouette
        0xC6, 0x1A, 0x5F,
        0x3E, 0xD6, 0xCE, 0x00, 0x57,  # DE = D61A + token
        0x06, 0x07,
    )
    renderer.label("run")
    renderer.db(
        0x2A, 0x4F, 0xCB, 0x37, 0xE6, 0x0F,
        0x87, 0x87, 0x83, 0x5F,          # skip nibble is byte delta / 4
    )
    renderer.jr(0x30, "cursor_ready")
    renderer.db(0x14)
    renderer.label("cursor_ready")
    renderer.db(
        0x79, 0xE6, 0x0F, 0x4F,
        0x2A, 0xF5, 0xCB, 0x37, 0xE6, 0x0F,
    )
    repair_calls.append(len(renderer.code))
    renderer.db(0xCD, 0x00, 0x00)
    renderer.label("middle")
    # After the edge load, draw-table L is $E2-$EE and clear-table L is
    # $F0-$FC.  Adding $10 and complementing carry materializes FF/00 in five
    # bytes; the repair entry masks FF to the resident nibble $0F.
    renderer.db(0x7D, 0xC6, 0x10, 0x3F, 0x9F)
    repair_calls.append(len(renderer.code))
    renderer.db(0xCD, 0x00, 0x00, 0x0D)
    renderer.jr(0x20, "middle")
    renderer.db(0xF1, 0xE6, 0x0F)
    repair_calls.append(len(renderer.code))
    renderer.db(0xCD, 0x00, 0x00, 0x05)
    renderer.jr(0x20, "run")
    renderer.db(0xC9)
    renderer_blob = bytearray(renderer.finish())
    for call in repair_calls:
        renderer_blob[call + 1:call + 3] = repair_entry_addr.to_bytes(
            2, "little"
        )
    renderer_blob = bytes(renderer_blob)
    assert len(renderer_blob) == 59

    # Native completed-2x2 writer.  The first raw cell is also the only
    # corpus-qualified aligned tile-$06 crown completion point.
    writer = _Asm()
    writer.db(
        0xF3, 0xF5, 0xD5, 0xE5,
        0x62, 0x6B, 0x01, 0x60, 0x14, 0x09,
        0x4E, 0x23, 0x46,
        0x7D, 0xC6, 0x17, 0x6F,
    )
    writer.jr(0x30, "resident_ready")
    writer.db(0x24)
    writer.label("resident_ready")
    writer.db(
        0x7E, 0x60, 0x69, 0x4F, 0x06, 0x01,
        0x1A, 0x13, 0xFE, 0x06,
    )
    writer.jr(0x20, "not_crown")
    writer.db(
        0xE5,
        0x21, candidate_low_addr & 0xFF, candidate_low_addr >> 8,
        0x73, 0x23, 0x72,
        0xE1,
    )
    writer.label("not_crown")
    writer.db(
        0xCD, TED_INWINDOW_MASK_CLASSIFIER_ADDR & 0xFF,
        TED_INWINDOW_MASK_CLASSIFIER_ADDR >> 8,
        0xCB, 0x39, 0x1A, 0x13,
        0xCD, TED_INWINDOW_MASK_CLASSIFIER_ADDR & 0xFF,
        TED_INWINDOW_MASK_CLASSIFIER_ADDR >> 8,
        0xCB, 0x39,
        0x7B, 0xC6, 0x16, 0x5F,
    )
    writer.jr(0x30, "source_row")
    writer.db(0x14)
    writer.label("source_row")
    writer.db(0x7D, 0xC6, 0x1E, 0x6F)
    writer.jr(0x30, "attr_row")
    writer.db(0x24)
    writer.label("attr_row")
    writer.db(
        0x1A, 0x13,
        0xCD, TED_INWINDOW_MASK_CLASSIFIER_ADDR & 0xFF,
        TED_INWINDOW_MASK_CLASSIFIER_ADDR >> 8,
        0xCB, 0x39, 0x1A,
        0xCD, TED_INWINDOW_MASK_CLASSIFIER_ADDR & 0xFF,
        TED_INWINDOW_MASK_CLASSIFIER_ADDR >> 8,
        0xE1, 0xD1, 0xF1,
        0xC3, TED_INCREMENTAL_TRACKER_EXIT_ADDR & 0xFF,
        TED_INCREMENTAL_TRACKER_EXIT_ADDR >> 8,
    )
    writer_blob = writer.finish()
    assert len(writer_blob) == 83

    initializer = _Asm()
    initializer.db(
        0x21, 0x00, 0xD0, 0x01, 0x00, 0x03, 0xAF,
        0xCD, 0xA8, 0x09,
        0x26, 0xD9, 0x06, 0x03, 0xCD, 0xA8, 0x09,
        0x26, 0xD6, 0x11, 0x00, 0xD0, 0x06, 0x0C,
    )
    initializer.label("pair")
    initializer.db(0x0E, 0x0C)
    initializer.label("pointer")
    initializer.db(0x7B, 0x22, 0x7A, 0x22, 0x13, 0x13, 0x0D)
    initializer.jr(0x20, "pointer")
    initializer.db(0xAF, 0x0E, 0x0C)
    initializer.label("resident")
    initializer.db(0x22, 0x22, 0x0D)
    initializer.jr(0x20, "resident")
    initializer.db(0x7B, 0xC6, 0x28, 0x5F)
    initializer.jr(0x30, "next_pair")
    initializer.db(0x14)
    initializer.label("next_pair")
    initializer.db(0x05)
    initializer.jr(0x20, "pair")
    initializer.db(
        0x21, (TED_TABLE_ADDR + 68) & 0xFF,
        (TED_TABLE_ADDR + 68) >> 8,
        0xC3, private_setup_addr & 0xFF, private_setup_addr >> 8,
    )
    initializer_blob = initializer.finish()
    assert len(initializer_blob) == 59

    continuation = bytes.fromhex("C1 13 13 EF C9 00 00 00 00")
    runtime = (
        writer_blob
        + bytes(TED_INCREMENTAL_TRACKER_EXIT_ADDR
                - TED_INCREMENTAL_TRACKER_ADDR - len(writer_blob))
        + continuation + initializer_blob
    )
    runtime_capacity = sum(
        length for _address, length in TED_INCREMENTAL_RUNTIME_SOURCE_CHUNKS
    )
    assert len(runtime) == 155 and runtime_capacity == 155
    runtime += bytes(runtime_capacity - len(runtime))

    draw_table = bytes.fromhex(
        "02 CD A2 FF A3 F4 94 E5 94 F5 94 21 A1 B7"
    )
    clear_table = bytes.fromhex(
        "02 00 A2 00 A3 00 94 00 94 00 94 00 A1 00"
    )
    assert len(draw_table + clear_table) == 28

    gate_front_addr = TED_INWINDOW_ENVELOPE_FRONT_ADDR
    gate_validate_addr = TED_INWINDOW_ANCHOR_FRONT_ADDR
    gate_compare_addr = TED_INWINDOW_ENVELOPE_FINAL_ADDR
    gate_invalid_addr = gate_compare_addr + 10
    wrapper_front_addr = TED_INWINDOW_PLANE_SETUP_ADDR
    wrapper_tail_addr = TED_INWINDOW_ANCHOR_TAIL_ADDR

    gate_front = bytes((
        0x21, candidate_low_addr & 0xFF, candidate_low_addr >> 8,
        0x5E, 0x23, 0x56, 0x36, 0x00,
        0x7A, 0xB7,
        0xCA, gate_invalid_addr & 0xFF, gate_invalid_addr >> 8,
        0x7B, 0xD6, 0x05, 0x5F, 0x06, 0x02,
        0xC3, gate_validate_addr & 0xFF, gate_validate_addr >> 8,
    ))
    gate_validate = _Asm()
    gate_validate.label("crown")
    gate_validate.db(0x1A, 0x13, 0xB8)
    gate_validate.db(0xC2, gate_invalid_addr & 0xFF, gate_invalid_addr >> 8)
    gate_validate.db(0x04, 0xFE, 0x06)
    gate_validate.jr(0x20, "crown")
    gate_validate.db(
        0x7B, 0xD6, 0xA9,
        0xC3, gate_compare_addr & 0xFF, gate_compare_addr >> 8,
    )
    gate_validate_blob = gate_validate.finish()
    gate_compare = bytes((
        0x21, key_addr & 0xFF, key_addr >> 8, 0xBE,
        0xCA, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
        TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8,
        0xC3, wrapper_front_addr & 0xFF, wrapper_front_addr >> 8,
        0xAF, 0xC3, gate_compare_addr & 0xFF, gate_compare_addr >> 8,
    ))
    assert (len(gate_front), len(gate_validate_blob), len(gate_compare)) == (
        22, 17, 14
    )

    wrapper_front = bytes((
        0xF5, 0x7E, 0xE5,
        0x21, clear_table_addr & 0xFF, clear_table_addr >> 8,
        0xCD, renderer_addr & 0xFF, renderer_addr >> 8,
        0xE1,
        0xC3, wrapper_tail_addr & 0xFF, wrapper_tail_addr >> 8,
    ))
    wrapper_tail = bytes((
        0xF1, 0xF5, 0xE5,
        0x21, draw_table_addr & 0xFF, draw_table_addr >> 8,
        0xCD, renderer_addr & 0xFF, renderer_addr >> 8,
        0xE1, 0xF1, 0x77,
        # $5830 tail-jumps into D500 after selecting private WRAM bank 4/5,
        # so the fixed-ROM return address at DFF5 belongs to bank 1.  A RET
        # here consumed zeroes from the private stack window and jumped to
        # $0000 on the first changed publication.  Converge with the unchanged
        # gate: $61B0 restores SVBK1, then starts the normal transport.
        0xC3, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
        TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8,
    ))
    assert len(wrapper_front) == 13 and len(wrapper_tail) == 15

    installer_cont_addr = TED_INWINDOW_ENVELOPE_TAIL_ADDR
    installer_low_mask_addr = 0x50E8
    installer_low_store_addr = 0xD573
    installer_high_load_addr = 0x6250
    installer_high_store_addr = 0x61C0
    installer_control_addr = 0x6100
    private_setup = bytes((
        0x11, TED_INWINDOW_SANITIZER_ADDR & 0xFF,
        TED_INWINDOW_SANITIZER_ADDR >> 8,
        0x0E, TED_INWINDOW_SANITIZER_SOURCE_SIZE,
        0xC3, 0x48, 0x5E,
    ))
    installer_front = bytes((
        0xCD, 0xB3, 0x09, 0x2E, 0x00,
        0xC3, installer_cont_addr & 0xFF, installer_cont_addr >> 8,
    ))
    installer_cont = bytes((
        0x1E, 0xFF, 0x06, 0x44, 0x2A, 0x4F,
        0xC3, installer_low_mask_addr & 0xFF,
        installer_low_mask_addr >> 8,
    ))
    installer_low_mask = bytes((
        0xE6, 0x0F, 0xC3,
        installer_low_store_addr & 0xFF, installer_low_store_addr >> 8,
    ))
    installer_low_store = bytes((
        0x12, 0x1B, 0xC3,
        installer_high_load_addr & 0xFF, installer_high_load_addr >> 8,
    ))
    installer_high_load = bytes((
        0x79, 0xCB, 0x37, 0xE6, 0x0F, 0xC3,
        installer_high_store_addr & 0xFF, installer_high_store_addr >> 8,
    ))
    installer_high_store = bytes((
        0x12, 0x1B, 0x05, 0xC3,
        installer_control_addr & 0xFF, installer_control_addr >> 8,
    ))
    installer_control = bytes((
        0xC2, (installer_cont_addr + 4) & 0xFF,
        (installer_cont_addr + 4) >> 8,
        0xEA, candidate_high_addr & 0xFF, candidate_high_addr >> 8,
        0xC9,
    ))

    private_source = (
        classifier_code + repair_blob + b"\x00"
        + installer_low_store + b"\x00"
    )
    assert len(private_source) == TED_INWINDOW_SANITIZER_SOURCE_SIZE
    assert private_source[0x73:0x78] == installer_low_store
    page_tail = renderer_blob + bytes(67 - len(renderer_blob))
    assert len(page_tail) == 67

    finish = bytes((
        0xFA, TED_INWINDOW_TARGET_H_ADDR & 0xFF,
        TED_INWINDOW_TARGET_H_ADDR >> 8, 0x67,
        0x3E, 0x01, 0xE0, 0x70, 0xFB,
        0xC3, TED_INWINDOW_SETUP_ADDR & 0xFF,
        TED_INWINDOW_SETUP_ADDR >> 8,
    ))
    fragments = {
        TED_INCREMENTAL_TRACKER_ADDR: runtime,
        TED_TABLE_ADDR: packed,
        TED_TABLE_ADDR + 68: private_source,
        renderer_addr: page_tail,
        repair_entry_addr: repair_entry,
        draw_table_addr: draw_table + clear_table,
        gate_front_addr: gate_front,
        gate_validate_addr: gate_validate_blob,
        gate_compare_addr: gate_compare,
        wrapper_front_addr: wrapper_front,
        wrapper_tail_addr: wrapper_tail,
        0x5E48: installer_front,
        installer_cont_addr: installer_cont,
        installer_low_mask_addr: installer_low_mask,
        installer_low_store_addr: installer_low_store,
        installer_high_load_addr: installer_high_load,
        installer_high_store_addr: installer_high_store,
        installer_control_addr: installer_control,
        private_setup_addr: private_setup,
        TED_INWINDOW_SANITIZER_FINISH_ADDR: finish,
    }
    capacities = {
        TED_INCREMENTAL_TRACKER_ADDR: 155,
        TED_TABLE_ADDR: 68,
        TED_TABLE_ADDR + 68: 121,
        renderer_addr: 67,
        repair_entry_addr: 13,
        draw_table_addr: 28,
        gate_front_addr: 24,
        gate_validate_addr: 18,
        gate_compare_addr: 17,
        wrapper_front_addr: 13,
        wrapper_tail_addr: 15,
        0x5E48: 8,
        installer_cont_addr: 9,
        installer_low_mask_addr: 5,
        installer_low_store_addr: 5,
        installer_high_load_addr: 8,
        installer_high_store_addr: 6,
        installer_control_addr: 8,
        private_setup_addr: 9,
        TED_INWINDOW_SANITIZER_FINISH_ADDR: 12,
    }
    for address, payload in fragments.items():
        assert len(payload) <= capacities[address], (
            hex(address), len(payload), capacities[address]
        )
    ordered = sorted(
        (address, address + len(payload))
        for address, payload in fragments.items()
        if address < 0x8000
    )
    for left, right in zip(ordered, ordered[1:]):
        assert left[1] <= right[0], (left, right)
    assert renderer_addr + len(page_tail) == 0x7700
    return fragments


def validate_ted_incremental_cell_layout(
    classifier: bytes,
    fragments: dict[int, bytes],
) -> None:
    """Fail closed on every provisional WRAM and bank-13 interval.

    This validates assembly geometry only.  It is intentionally not an
    ownership receipt and cannot authorize the blocked ROM installer.
    """
    expected_private: dict[int, tuple[int, int]] = {}
    private = {
        address: payload
        for address, payload in fragments.items()
        if address >= 0x8000
    }
    assert set(private) == set(expected_private), (
        "incremental private helper set changed",
        tuple(hex(address) for address in sorted(private)),
    )
    assert len(classifier) == TED_INWINDOW_SANITIZER_SOURCE_SIZE
    classifier_end = TED_INWINDOW_SANITIZER_ADDR + len(classifier)
    assert classifier_end == TED_INWINDOW_PRIVATE_CROWN_HELPER_ADDR

    wram_intervals = [
        (
            TED_INWINDOW_SANITIZER_ADDR,
            classifier_end,
            "cell classifier",
        ),
        *(
            (address, address + len(payload), f"private helper ${address:04X}")
            for address, payload in private.items()
        ),
        (
            TED_DIRECT_PLANE_POINTER_TABLE_ADDR,
            TED_INWINDOW_ROW_TABLE_ADDR,
            "direct-plane pointer table",
        ),
        (
            TED_INWINDOW_ROW_TABLE_ADDR,
            TED_INWINDOW_OLD_COL_ADDR + 1,
            "row table and crown metadata",
        ),
        (
            TED_INWINDOW_BODY_MASK_ADDR,
            TED_INWINDOW_BODY_MASK_ADDR + TED_INWINDOW_BODY_MASK_SIZE,
            "576-bit body mask",
        ),
        (
            TED_DIRECT_TILE_PLANE_ADDR,
            TED_DIRECT_TILE_PLANE_ADDR + 0x300,
            "sanitized tile plane",
        ),
        (
            TED_INWINDOW_RAW_TILE_PLANE_ADDR,
            TED_INWINDOW_RAW_TILE_PLANE_ADDR + 0x300,
            "raw tile plane",
        ),
    ]
    for address, (limit, capacity) in expected_private.items():
        payload = private[address]
        assert len(payload) <= capacity
        assert address + len(payload) <= limit
    ordered_wram = sorted(wram_intervals)
    for left, right in zip(ordered_wram, ordered_wram[1:]):
        assert left[1] <= right[0], (
            f"incremental WRAM overlap: {left[2]} / {right[2]}"
        )

    rom_fragments = {
        address: payload
        for address, payload in fragments.items()
        if address < 0x8000
    }
    capacities = {
        TED_INWINDOW_ENVELOPE_FRONT_ADDR: 24,
        TED_INWINDOW_ANCHOR_FRONT_ADDR: 18,
        TED_INWINDOW_ENVELOPE_FINAL_ADDR: 17,
        TED_INWINDOW_ANCHOR_TAIL_ADDR: 15,
        TED_INWINDOW_PLANE_SETUP_ADDR: 13,
        TED_INWINDOW_ENVELOPE_TAIL_ADDR: 9,
        TED_INWINDOW_SANITIZER_FINISH_ADDR: 12,
    }
    assert not rom_fragments or set(rom_fragments) == set(capacities), (
        "incremental ROM repair set changed",
        tuple(hex(address) for address in sorted(rom_fragments)),
    )
    rom_intervals = []
    for address, payload in rom_fragments.items():
        end = address + len(payload)
        assert 0x4000 <= address < end <= 0x8000
        assert len(payload) <= capacities[address]
        for protected_start, protected_end, owner in (
            TED_INCREMENTAL_CELL_PROTECTED_ROM_RANGES
        ):
            assert end <= protected_start or address >= protected_end, (
                f"incremental fragment ${address:04X}-${end - 1:04X} "
                f"overlaps protected {owner}"
            )
        rom_intervals.append((address, end))
    ordered_rom = sorted(rom_intervals)
    for left, right in zip(ordered_rom, ordered_rom[1:]):
        assert left[1] <= right[0], (
            f"incremental ROM overlap: ${left[0]:04X}-${left[1] - 1:04X} "
            f"/ ${right[0]:04X}-${right[1] - 1:04X}"
        )


def build_ted_inwindow_plane_sanitizer() -> tuple[bytes, dict[int, bytes]]:
    """Sanitize one selected direct plane against Ted's physical geometry.

    D900/D000 remain a private, immutable tile/attribute snapshot for the
    whole publication.  Numbered body art is retained only inside the exact
    fourteen-row crown-relative silhouette.  The four checker-floor IDs and
    every rejected numbered scratch cell become neutral tile 0 / attr 0.
    Tiles above $7A retain their native tile byte, but an explicit sparse-ID
    whitelist forces every other high tile's attribute to zero.
    """
    runtime = _Asm()
    # Fail closed until the unique five-tile crown has been found.
    runtime.db(
        0x3E, 0xFF,
        0xEA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_ROW_ADDR >> 8,
        0x21, 0x00, TED_DIRECT_TILE_PLANE_ADDR >> 8,
    )
    runtime.label("crown_scan")
    runtime.db(0x2A, 0xFE, 0x02)
    runtime.jr(0x20, "crown_next")
    runtime.db(0xE5, 0x2A, 0xFE, 0x03)
    runtime.jr(0x20, "crown_restore")
    runtime.db(0x2A, 0xFE, 0x04)
    runtime.jr(0x20, "crown_restore")
    runtime.db(0x2A, 0xFE, 0x05)
    runtime.jr(0x20, "crown_restore")
    runtime.db(0x7E, 0xFE, 0x06)
    runtime.label("crown_restore")
    runtime.db(0xE1)
    runtime.jr(0x28, "crown_found")
    runtime.label("crown_next")
    runtime.db(0x7C, 0xFE, 0xDC)
    runtime.jr(0x20, "crown_scan")
    # No crown is a fail-closed publication: the $FF anchor makes every
    # numbered body cell fail the envelope predicate below.
    runtime.jr(0x18, "plane_begin")

    runtime.label("crown_found")
    # HL is crown+1.  A split ROM leaf packs the exact physical anchor and
    # jumps back to plane_begin, keeping the private D500 source within the
    # neutral 121-byte Ted LUT tail.
    runtime.db(
        0xC3, TED_INWINDOW_ANCHOR_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_FRONT_ADDR >> 8,
    )
    runtime.label("plane_begin")
    runtime.db(0xC3, TED_INWINDOW_PLANE_SETUP_ADDR & 0xFF,
               TED_INWINDOW_PLANE_SETUP_ADDR >> 8)
    runtime.label("cell")
    runtime.db(0x1A, 0xFE, 0x02)
    runtime.jr(0x38, "neutral_attr")
    runtime.db(0xFE, 0x77)
    runtime.jr(0x38, "numbered")
    runtime.db(0xFE, 0x7B)
    runtime.jr(0x38, "reject")             # checker floor $77-$7A
    # Only the traced sparse contour IDs may retain a colored attribute.
    # This explicit whitelist makes LUT-source reuse fail closed: arbitrary
    # source bytes at IDs $87-$FF can never become published attributes.
    runtime.db(0xFE, 0x7B)
    runtime.jr(0x38, "neutral_attr")
    runtime.db(0xFE, 0x87)
    runtime.jr(0x38, "advance")
    runtime.jr(0x18, "neutral_attr")

    runtime.label("numbered")
    runtime.db(
        0xE5,
        0xCD, TED_INWINDOW_ENVELOPE_FRONT_ADDR & 0xFF,
        TED_INWINDOW_ENVELOPE_FRONT_ADDR >> 8,
        0xE1,
    )
    runtime.jr(0x20, "reject")
    runtime.jr(0x18, "advance")
    runtime.label("neutral_attr")
    runtime.db(0xAF, 0x77)
    runtime.jr(0x18, "advance")
    runtime.label("reject")
    runtime.db(0xAF, 0x77, 0x12)
    runtime.label("advance")
    runtime.db(0x23, 0x13, 0x0C, 0x79, 0xFE, 0x20)
    runtime.jr(0x20, "cell")
    runtime.db(0x0E, 0x00, 0x04, 0x78, 0xFE, 0x18)
    runtime.jr(0x20, "cell")
    # Interrupts must never observe a private bank.  Setup reloads the saved
    # physical target H and starts the unchanged 48-block transport.
    runtime.db(0xC3, TED_INWINDOW_SANITIZER_FINISH_ADDR & 0xFF,
               TED_INWINDOW_SANITIZER_FINISH_ADDR >> 8)
    runtime_blob = runtime.finish()
    assert len(runtime_blob) <= TED_INWINDOW_SANITIZER_SOURCE_SIZE, len(
        runtime_blob
    )
    runtime_blob += bytes(
        TED_INWINDOW_SANITIZER_SOURCE_SIZE - len(runtime_blob)
    )

    # Called with BC=row/column counters and DE=tile cursor.  The comparator
    # at $6500 deliberately pops the saved DE before returning to D500.
    front = _Asm()
    front.db(
        0xD5,
        0xFA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_ROW_ADDR >> 8,
        0x3C,
    )
    outside_fixups = [len(front.code)]
    front.db(0xCA, 0x00, 0x00)
    front.db(0x3D, 0x57, 0x78, 0x92, 0xE6, 0x1F, 0xFE, 0x0E)
    outside_fixups.append(len(front.code))
    front.db(0xD2, 0x00, 0x00)
    front.db(0xC3, TED_INWINDOW_ENVELOPE_TAIL_ADDR & 0xFF,
             TED_INWINDOW_ENVELOPE_TAIL_ADDR >> 8)
    # Patch absolute branches to the tail's common outside return.
    front_blob = bytearray(front.finish())
    outside_addr = TED_INWINDOW_ENVELOPE_FINAL_ADDR + 13
    for offset in outside_fixups:
        assert front_blob[offset] in (0xCA, 0xD2)
        front_blob[offset + 1:offset + 3] = outside_addr.to_bytes(2, "little")
    assert len(front_blob) <= 24, len(front_blob)

    middle = bytes([
        0x87, 0xC6, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF, 0x6F,
        0x26, TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8,
        0xC3, TED_INWINDOW_ENVELOPE_FINAL_ADDR & 0xFF,
        TED_INWINDOW_ENVELOPE_FINAL_ADDR >> 8,
    ])
    assert len(middle) <= 18, len(middle)
    final = bytes([
        0xFA, TED_SANITIZER_ANCHOR_COL_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_COL_ADDR >> 8,
        0x57, 0x79, 0x92, 0xC6, 0x04, 0xE6, 0x1F,
        0xC3, TED_ENVELOPE_COMPARE_ROM_ADDR & 0xFF,
        TED_ENVELOPE_COMPARE_ROM_ADDR >> 8,
        0xD1, 0xF6, 0x01, 0xC9,
    ])
    assert len(final) <= 17, len(final)

    anchor_front = bytes([
        0x2B,
        0x7D, 0xE6, 0x1F,
        0xEA, TED_SANITIZER_ANCHOR_COL_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_COL_ADDR >> 8,
        0x7D, 0xCB, 0x37, 0x0F, 0xE6, 0x07, 0x57,
        0xC3, TED_INWINDOW_ANCHOR_TAIL_ADDR & 0xFF,
        TED_INWINDOW_ANCHOR_TAIL_ADDR >> 8,
    ])
    assert len(anchor_front) <= 18, len(anchor_front)
    anchor_tail = bytes([
        0x7C, 0xE6, 0x03, 0x07, 0x07, 0x07, 0xB2,
        0xEA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_ROW_ADDR >> 8,
        0xC3,
        (TED_INWINDOW_SANITIZER_ADDR + runtime.labels["plane_begin"]) & 0xFF,
        (TED_INWINDOW_SANITIZER_ADDR + runtime.labels["plane_begin"]) >> 8,
    ])
    assert len(anchor_tail) <= 15, len(anchor_tail)
    plane_setup = bytes([
        0x21, 0x00, 0xD0,                 # HL = selected attr plane
        0x11, 0x00, TED_DIRECT_TILE_PLANE_ADDR >> 8,
        0x01, 0x00, 0x00,                 # B=row, C=column
        0xC3,
        (TED_INWINDOW_SANITIZER_ADDR + runtime.labels["cell"]) & 0xFF,
        (TED_INWINDOW_SANITIZER_ADDR + runtime.labels["cell"]) >> 8,
    ])
    assert len(plane_setup) <= 13, len(plane_setup)
    sanitizer_finish = bytes([
        0xFA, TED_INWINDOW_TARGET_H_ADDR & 0xFF,
        TED_INWINDOW_TARGET_H_ADDR >> 8, 0x67,
        0x3E, 0x01, 0xE0, 0x70, 0xFB,
        0xC3, TED_INWINDOW_SETUP_ADDR & 0xFF,
        TED_INWINDOW_SETUP_ADDR >> 8,
    ])
    assert len(sanitizer_finish) <= 13, len(sanitizer_finish)
    return runtime_blob, {
        TED_INWINDOW_ENVELOPE_FRONT_ADDR: bytes(front_blob),
        TED_INWINDOW_ENVELOPE_TAIL_ADDR: middle,
        TED_INWINDOW_ENVELOPE_FINAL_ADDR: final,
        TED_INWINDOW_ANCHOR_FRONT_ADDR: anchor_front,
        TED_INWINDOW_ANCHOR_TAIL_ADDR: anchor_tail,
        TED_INWINDOW_PLANE_SETUP_ADDR: plane_setup,
        TED_INWINDOW_SANITIZER_FINISH_ADDR: sanitizer_finish,
    }


def build_ted_inwindow_copier() -> dict[int, bytes]:
    """Copy native tiles and 48 attr blocks in the same HBlank windows."""
    entry = bytes([
        0xFA, 0x0B, 0xDC, 0x3C, 0xE6, 0x01, 0xEA, 0x0B, 0xDC,
        0x47,                              # retain post-toggle selector
        0x3E, 0x30,
        0xE0, TED_INWINDOW_BLOCKS_HRAM,
        0xC3, TED_INWINDOW_SELECT_ADDR & 0xFF,
        TED_INWINDOW_SELECT_ADDR >> 8,
    ])
    select = bytes([
        # B is the post-toggle selector. The direct writers use the
        # equivalent pre-toggle mapping ``(DC0B & 1) XOR 5``; therefore the
        # completed destination owns SVBK 4+B, not 5-B. Publishing the peer
        # bank exposed the preceding physical map's attributes.
        0x3E, 0x04, 0x80,                 # selected plane = 4+B
        0xE0, TED_INWINDOW_BANK_HRAM,
        0xE0, 0x70,
        0x87, 0x87, 0x2F, 0xC6, 0xAD,    # bank 4/5 -> H $9C/$98
        0xEA, TED_INWINDOW_TARGET_H_ADDR & 0xFF,
        TED_INWINDOW_TARGET_H_ADDR >> 8,
        0xC3, TED_INWINDOW_SANITIZER_ADDR & 0xFF,
        TED_INWINDOW_SANITIZER_ADDR >> 8,
    ])
    setup = bytes([
        0x3E, 0xD0, 0xE0, 0x51,
        0xAF, 0xE0, 0x52,
        0x7C, 0xE0, 0x53,
        0xAF, 0xE0, 0x54, 0x6F,           # L=0 from the same XOR A
        0xC3, TED_INWINDOW_INIT_ADDR & 0xFF,
        TED_INWINDOW_INIT_ADDR >> 8,
    ])
    init = bytes([
        0x11, 0x00, TED_DIRECT_TILE_PLANE_ADDR >> 8,
        0x0E, 0x06,
        0x06, 0x18,
        0xC3, TED_INWINDOW_WAIT_ADDR & 0xFF,
        TED_INWINDOW_WAIT_ADDR >> 8,
    ])
    wait = bytes([
        0xF3,
        0xF0, TED_INWINDOW_BANK_HRAM, 0xE0, 0x70,
        0xF0, TED_INWINDOW_BLOCKS_HRAM, 0xB7,
        0x28, 0x04,
        0x3E, 0x01, 0xE0, 0x4F,
        0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03, 0x20, 0xF8,
        0xF0, 0x41, 0xE6, 0x03, 0x20, 0xFA,
        0xC3, TED_INWINDOW_DMA_ADDR & 0xFF,
        TED_INWINDOW_DMA_ADDR >> 8,
    ])
    dma = _Asm()
    dma.db(0xF0, TED_INWINDOW_BLOCKS_HRAM, 0xB7)
    dma.jr(0x28, "done")
    dma.db(
        0x3D, 0xE0, TED_INWINDOW_BLOCKS_HRAM,
        0xAF, 0xE0, 0x55,                 # one immediate 16-byte block
        0xE0, 0x4F,
        0x3C, 0xE0, 0x70,
    )
    dma.label("done")
    dma.db(
        0x1A, 0x13, 0x22, 0x1A, 0x13, 0x22,
        0x1A, 0x13, 0x22, 0x1A, 0x13, 0x22,
        0x0D,
        0xC2, TED_INWINDOW_EPILOGUE_ADDR & 0xFF,
        TED_INWINDOW_EPILOGUE_ADDR >> 8,
        0xC3, TED_INWINDOW_ROW_ADDR & 0xFF,
        TED_INWINDOW_ROW_ADDR >> 8,
    )
    row = bytes([
        0x7D, 0xC6, 0x08, 0x6F, 0x30, 0x01, 0x24,
        0x05,
        0xCA, TED_INWINDOW_FINISH_ADDR & 0xFF,
        TED_INWINDOW_FINISH_ADDR >> 8,
        0x0E, 0x06,
        0xC3, TED_INWINDOW_EPILOGUE_ADDR & 0xFF,
        TED_INWINDOW_EPILOGUE_ADDR >> 8,
    ])
    # Row arrives with A=B=0 on the final group, which bypasses the shared
    # epilogue. Restore SVBK1 here too before exposing interrupts/returning.
    finish = bytes([0x3C, 0xE0, 0x70, 0x01, 0x08, 0x00, 0xFB, 0xC9])
    epilogue = bytes([
        0x3E, 0x01, 0xE0, 0x70,           # interrupt-safe SVBK1
        0xFB,
        0xC3, TED_INWINDOW_WAIT_ADDR & 0xFF,
        TED_INWINDOW_WAIT_ADDR >> 8,
    ])
    fragments = {
        TED_INWINDOW_ENTRY_ADDR: entry,
        TED_INWINDOW_SELECT_ADDR: select,
        TED_INWINDOW_SETUP_ADDR: setup,
        TED_INWINDOW_INIT_ADDR: init,
        TED_INWINDOW_WAIT_ADDR: wait,
        TED_INWINDOW_DMA_ADDR: dma.finish(),
        TED_INWINDOW_ROW_ADDR: row,
        TED_INWINDOW_FINISH_ADDR: finish,
        TED_INWINDOW_EPILOGUE_ADDR: epilogue,
    }
    capacities = {
        TED_INWINDOW_ENTRY_ADDR: 18,
        TED_INWINDOW_SELECT_ADDR: 18,
        TED_INWINDOW_SETUP_ADDR: 17,
        TED_INWINDOW_INIT_ADDR: 11,
        TED_INWINDOW_WAIT_ADDR: 36,
        TED_INWINDOW_DMA_ADDR: 36,
        TED_INWINDOW_ROW_ADDR: 16,
        TED_INWINDOW_FINISH_ADDR: 8,
        TED_INWINDOW_EPILOGUE_ADDR: 14,
    }
    for address, payload in fragments.items():
        assert len(payload) <= capacities[address], (hex(address), len(payload))
    return fragments


def build_ted_hdma_piggyback_gate() -> bytes:
    """Cold-safe DB80 gate for the stock copy plus paired publication.

    The gate itself is copied during ordinary boot, so unlike the lazy Ted
    clone it is guaranteed to exist before the first $028A publication.  A
    zero C5FF sentinel forces the first stock toggle toward the inactive
    $9800 map; ready calls preserve stock alternation.  DB91 owns the native
    copy/compiler wrapper, and the fixed continuation publishes attributes.
    """
    code = bytes([
        0xFA, TED_INCREMENTAL_READY_ADDR & 0xFF,
        TED_INCREMENTAL_READY_ADDR >> 8,
        0x3C,
        0x28, 0x05,                       # ready: preserve natural toggle
        0x3E, 0x01, 0xEA, 0x0B, 0xDC,    # cold: first target is $9800
        0xCD, 0x91, 0xDB,
        0xC3, 0x38, 0x08,
    ])
    assert len(code) == 17
    return code


def build_ted_hdma_piggyback_postcopy() -> bytes:
    """DB91 stock-copy/lazy-compiler half of the cold-safe WRAM helper."""
    code = bytes([
        0xCD, 0x95, 0x42,                 # stock alternating row copier
        0xF5,
        0x3E, 0x0D, 0xCD, 0x61, 0x00,
        0xCD, TED_INCREMENTAL_LAZY_GATE_ADDR & 0xFF,
        TED_INCREMENTAL_LAZY_GATE_ADDR >> 8,
        0x3E, 0x01, 0xCD, 0x61, 0x00,
        0xF1, 0xC9,
    ])
    assert len(code) == 19
    return code


def build_ted_writer_mirror_runtime() -> tuple[bytes, int, int]:
    """Record one native 2x2 write, then reproduce its exact return tail.

    The hook replaces ``POP BC / INC DE / INC DE`` at $3136, after the stock
    nested writer has already produced all four cells and restored HL/DE.
    Keeping the tile writer entirely native avoids duplicating its private
    loop ABI in WRAM.  The helper marks the completed metatile in both physical
    map records, restores AF/DE/HL, and executes the displaced return tail.
    It never selects switchable WRAM.
    """
    a = _Asm()
    # AF contains the native final DEC-C result. BC's caller value is still on
    # the stock stack; HL and DE have already been restored by $3133/$3134.
    # The hook is global, so reject every non-Ted scene before doing any index
    # arithmetic. Preserve the native AF flags across this test and reproduce
    # the displaced tail byte-for-byte; Stage 1 must not pay Ted's bitmap cost.
    a.db(0xF5, 0xFA, 0x80, 0xD8, 0xFE, 0x10)
    a.jr(0x28, "track")
    a.db(0xF1, 0xC1, 0x13, 0x13, 0xEF, 0xC9)
    a.label("track")
    # The stock five-byte tail never spans VBlank, but this bookkeeping can.
    # Ted's mainline writer runs with IME set and the interrupt handler does
    # not preserve HL, so keep this bounded O(1) section atomic. EI's delayed
    # activation occurs after RET, exactly at the native caller boundary.
    a.db(0xF3, 0xE5, 0xD5)
    # Convert DE to an unsigned offset from the exact 576-byte native map
    # buffer. Ted also uses this shared writer for unrelated destinations;
    # rejecting those before indexing prevents dirty-map writes into C500+.
    a.db(0x7B, 0xD6, 0xA0, 0x6F,
         0x7A, 0xDE, 0xC1, 0x67,
         0x7C, 0xFE, 0x02)
    a.jr(0x38, "map_destination")
    a.jr(0x20, "untracked")
    a.db(0x7D, 0xFE, 0x40)
    a.jr(0x30, "untracked")
    a.label("map_destination")
    # HL = packed byte offset, then sparse metatile bit index. Native callers
    # can start a 2x2 write on either packed row parity, so all 24 rows x 12
    # even columns need distinct bits (288 bits / 36 bytes per map).
    a.db(
         0xCB, 0x3C, 0xCB, 0x1D,           # HL = offset >> 1
         0x54, 0x5D,                       # retain bit index in DE
         0x7D, 0xE6, 0x07,
         0xC6, TED_WRITER_MASK_TABLE_ADDR & 0xFF,
         0x6F, 0x26, TED_WRITER_MASK_TABLE_ADDR >> 8, 0x4E,
         0x62, 0x6B,
         0xCB, 0x3C, 0xCB, 0x1D,
         0xCB, 0x3C, 0xCB, 0x1D,
         0xCB, 0x3C, 0xCB, 0x1D,           # HL = bit index >> 3
         0x7D,
         0xC6, TED_WRITER_DIRTY_9800_ADDR & 0xFF,
         0x6F, 0x26, TED_WRITER_DIRTY_9800_ADDR >> 8,
         0x7E, 0xB1, 0x77,
         0x7D, 0xC6, TED_WRITER_BITMAP_SIZE, 0x6F,
         0x7E, 0xB1, 0x77)
    a.db(0xD1, 0xE1, 0xF1,                 # exact DE/HL/AF
         0xC1, 0x13, 0x13, 0xEF, 0xFB, 0xC9) # native tail; delayed EI
    a.label("untracked")
    a.db(0xD1, 0xE1, 0xF1,
         0xC1, 0x13, 0x13, 0xEF, 0xFB, 0xC9)
    writer = a.finish()
    assert len(writer) <= TED_WRITER_RUNTIME_LIMIT_ADDR - TED_WRITER_RUNTIME_ADDR, len(writer)

    clear = _Asm()
    # $4422 replacement: invalidate both physical mirrors, then reproduce the
    # stock 576-byte zero fill exactly.
    clear.db(0xCD, (TED_WRITER_CLEAR_RUNTIME_ADDR + 13) & 0xFF,
             (TED_WRITER_CLEAR_RUNTIME_ADDR + 13) >> 8,
             0x21, 0xA0, 0xC1, 0x01, 0x40, 0x02, 0xAF,
             0xC3, 0xA8, 0x09)
    invalidate_offset = len(clear.code)
    clear.db(0x21, TED_WRITER_DIRTY_9800_ADDR & 0xFF,
             TED_WRITER_DIRTY_9800_ADDR >> 8,
             0x01, TED_WRITER_BITMAP_SIZE * 2, 0x00,
             0x3E, 0xFF, 0xC3, 0xA8, 0x09)
    clear_code = clear.finish()
    assert len(clear_code) <= TED_WRITER_DIRTY_9800_ADDR - TED_WRITER_CLEAR_RUNTIME_ADDR

    runtime = bytearray(
        TED_WRITER_RUNTIME_SENTINEL_ADDR - TED_WRITER_RUNTIME_ADDR + 1
    )
    writer_off = 0
    clear_off = TED_WRITER_CLEAR_RUNTIME_ADDR - TED_WRITER_RUNTIME_ADDR
    runtime[writer_off:writer_off + len(writer)] = writer
    runtime[clear_off:clear_off + len(clear_code)] = clear_code
    masks_off = TED_WRITER_MASK_TABLE_ADDR - TED_WRITER_RUNTIME_ADDR
    runtime[masks_off:masks_off + 8] = bytes(1 << bit for bit in range(8))
    runtime[-1] = TED_WRITER_RUNTIME_SENTINEL_VALUE
    return bytes(runtime), 0, clear_off + invalidate_offset


def build_ted_writer_mirror_wrapper(publisher_addr: int) -> bytes:
    """Append the dirty-metatile attribute plane to every native copy."""
    code = bytes([
        0xCD, 0x95, 0x42,                  # stock alternating tile copy
        0xF5,
        0x3E, 0x0D, 0xCD, 0x61, 0x00,
        0xCD, TED_DIRTY_POSTCOPY_MAIN_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_MAIN_ADDR >> 8,
        0x3E, 0x01, 0xCD, 0x61, 0x00,
        0xF1, 0xC9,
    ])
    assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return code


def build_ted_writer_clear_gate() -> bytes:
    """Use the mirror clear only after its C500 runtime is installed.

    The native clear runs during cold boot before the existing OAM initializer
    copies the writer runtime. This exact 13-byte bank-1 trampoline preserves
    that early path and routes later clears through the dirty-map invalidator.
    """
    code = bytes([
        0xFA, TED_WRITER_RUNTIME_SENTINEL_ADDR & 0xFF,
        TED_WRITER_RUNTIME_SENTINEL_ADDR >> 8,
        0x3D,                               # sentinel 1 -> Z
        0xCA, TED_WRITER_CLEAR_RUNTIME_ADDR & 0xFF,
        TED_WRITER_CLEAR_RUNTIME_ADDR >> 8,
        0x21, 0xA0, 0xC1,                  # displaced stock LD HL,$C1A0
        0xC3, 0x25, 0x44,                  # resume stock clear
    ])
    assert len(code) == 13
    return code


def build_ted_writer_fixed_stub() -> bytes:
    """Enter the bank-13 ROM tracker from the fixed native writer tail."""
    code = bytes([
        0xF5,                               # preserve native AF
        0xF3,                               # bounded tracker is atomic
        0x3E, 0x0D, 0xCD, 0x61, 0x00,      # map bank 13
        0xC3, TED_WRITER_ROM_RUNTIME_ADDR & 0xFF,
        TED_WRITER_ROM_RUNTIME_ADDR >> 8,
        # Bank-13 runtime pushes this fixed continuation before tail-mapping
        # bank 14 through JP $0061.
        0xF1,                               # exact native AF
        0xC1, 0x13, 0x13, 0xEF, 0xFB, 0xC9,
    ])
    assert len(code) == 17
    return code


def build_ted_writer_clear_invalidator() -> bytes:
    """Invalidate both physical Ted attribute mirrors on native source clear.

    Stock $4422 clears the complete $C1A0 source before Ted rebuilds a pose.
    The ordinary 2x2 writer subsequently marks body metatiles, but the cleared
    checker/floor cells do not traverse that writer.  Marking both bank-local
    dirty-map latch here makes the next publication of each physical map
    compile the exact cleared and rebuilt source.  The helper then resumes the
    displaced stock clear without touching the caller's WRAM bank.
    """
    code = bytes([
        0x3E, 0x03,                        # both physical maps are stale
        0xEA, TED_WRITER_START_E_ADDR & 0xFF,
        TED_WRITER_START_E_ADDR >> 8,
        0x21, 0xA0, 0xC1,                  # displaced LD HL,$C1A0
        0xC3, 0x25, 0x44,                  # resume stock clear
    ])
    assert len(code) == 11
    return code


def build_ted_writer_rom_runtime() -> bytes:
    """Mark one native 2x2 write in bank-local dirty maps.

    Code lives in ROM because Ted overwrites both candidate common-WRAM pages.
    The two 36-byte maps live at D300 in SVBK 2/3, immediately after each
    0x300-byte attribute plane. No stack access occurs while SVBK is switched.
    """
    a = _Asm()
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x10)
    a.jr(0x28, "track")
    a.jr(0x18, "finish")
    a.label("track")
    a.db(0xE5, 0xD5)
    a.db(0x7B, 0xD6, 0xA0, 0x6F,
         0x7A, 0xDE, 0xC1, 0x67,
         0x7C, 0xFE, 0x02)
    a.jr(0x38, "map_destination")
    a.jr(0x20, "untracked")
    a.db(0x7D, 0xFE, 0x40)
    a.jr(0x30, "untracked")
    a.label("map_destination")
    a.db(0xCB, 0x3C, 0xCB, 0x1D,           # metatile bit index
         0x54, 0x5D,
         0x7D, 0xE6, 0x07,
         0xC6, (TED_WRITER_ROM_RUNTIME_ADDR + 0x70) & 0xFF,
         0x6F, 0x26, TED_WRITER_ROM_RUNTIME_ADDR >> 8, 0x4E,
         0x62, 0x6B,
         0xCB, 0x3C, 0xCB, 0x1D,
         0xCB, 0x3C, 0xCB, 0x1D,
         0xCB, 0x3C, 0xCB, 0x1D,
         0x7D, 0xC6, TED_WRITER_BANKED_DIRTY_ADDR & 0xFF,
         0x6F, 0x26, TED_WRITER_BANKED_DIRTY_ADDR >> 8,
         0x3E, 0x02, 0xE0, 0x70,
         0x7E, 0xB1, 0x77,
         0x3E, 0x03, 0xE0, 0x70,
         0x7E, 0xB1, 0x77,
         0x3E, 0x01, 0xE0, 0x70)
    a.db(0xD1, 0xE1)
    a.jr(0x18, "finish")
    a.label("untracked")
    a.db(0xD1, 0xE1)
    a.label("finish")
    continuation = TED_WRITER_FIXED_STUB_ADDR + 10
    a.db(0x01, continuation & 0xFF, continuation >> 8, 0xC5,
         0x3E, 0x0E,                        # native bank 14
         0xC3, 0x61, 0x00)                 # mapper RET -> fixed continuation
    code = bytearray(a.finish())
    table_offset = 0x70
    assert len(code) <= table_offset, len(code)
    code.extend(bytes(table_offset - len(code)))
    code.extend(bytes(1 << bit for bit in range(8)))
    assert len(code) <= 0x9C, len(code)
    return bytes(code)


def build_ted_dirty_postcopy_fragments() -> dict[int, bytes]:
    """Patch only dirty 2x2 attrs, then publish the selected physical plane."""
    main = _Asm()
    main.db(0xF3, 0xC5, 0xD5, 0xE5,
            0x7C, 0xE6, 0xFC, 0xE0, TED_SANITIZER_TILE_MASK_HRAM,
            0xFE, 0x9C,
            0x01, TED_WRITER_BANKED_DIRTY_ADDR & 0xFF,
            TED_WRITER_BANKED_DIRTY_ADDR >> 8,
            0x3E, 0x02)
    main.jr(0x20, "selected")
    main.db(0x01, TED_WRITER_BANKED_DIRTY_ADDR & 0xFF,
            TED_WRITER_BANKED_DIRTY_ADDR >> 8, 0x3E, 0x03)
    main.label("selected")
    # Retain selected SVBK in E so the invalidation helper can consume the
    # corresponding one of the two source-clear bits in O(1).
    main.db(0x5F, 0xE0, 0x70, 0xC3,
            TED_WRITER_INVALIDATE_MAP_ADDR & 0xFF,
            TED_WRITER_INVALIDATE_MAP_ADDR >> 8)

    invalidate_map = _Asm()
    invalidate_map.db(0x1D)                # SVBK 2/3 -> mask 1/2
    invalidate_map.db(
        0xFA, TED_WRITER_START_E_ADDR & 0xFF,
        TED_WRITER_START_E_ADDR >> 8,
        0xA3,                               # AND E
    )
    invalidate_map.db(
        0xCA, TED_DIRTY_POSTCOPY_SCAN_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_SCAN_ADDR >> 8,
    )
    invalidate_map.db(
        0xFA, TED_WRITER_START_E_ADDR & 0xFF,
        TED_WRITER_START_E_ADDR >> 8,
        0xAB,                               # XOR E; consume this map's bit
        0xEA, TED_WRITER_START_E_ADDR & 0xFF,
        TED_WRITER_START_E_ADDR >> 8,
        0x21, TED_WRITER_BANKED_DIRTY_ADDR & 0xFF,
        TED_WRITER_BANKED_DIRTY_ADDR >> 8,
        0x01, TED_WRITER_BITMAP_SIZE, 0x00,
        0x3E, 0xFF, 0xCD, 0xA8, 0x09,
    )
    invalidate_map.db(
        0x01, TED_WRITER_BANKED_DIRTY_ADDR & 0xFF,
        TED_WRITER_BANKED_DIRTY_ADDR >> 8,
        0xC3, TED_DIRTY_POSTCOPY_SCAN_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_SCAN_ADDR >> 8,
    )

    scan = _Asm()
    scan.db(0xC5, 0x60, 0x69, 0x06, TED_WRITER_BITMAP_SIZE, 0xAF)
    scan.label("cell")
    scan.db(0xB6, 0x23, 0x05)
    scan.jr(0x20, "cell")
    scan.db(0xC3, TED_DIRTY_POSTCOPY_SCAN_TAIL_ADDR & 0xFF,
            TED_DIRTY_POSTCOPY_SCAN_TAIL_ADDR >> 8)
    scan_tail = bytes([
        0xC1, 0xB7,
        0xCA, TED_DIRTY_POSTCOPY_FINAL_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_FINAL_ADDR >> 8,
        0xC3, TED_DIRTY_POSTCOPY_SETUP_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_SETUP_ADDR >> 8,
    ])

    setup = bytes([
        0x11, 0xA0, 0xC1, 0x21, 0x00, 0xD0,
        0xAF, 0xE0, TED_SANITIZER_COUNTER_HRAM,
        0x3E, TED_WRITER_BITMAP_SIZE, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0xC3, TED_DIRTY_POSTCOPY_BYTE_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_BYTE_ADDR >> 8,
    ])

    byte_loop = bytes([
        0x0A, 0xF5, 0xAF, 0x02, 0xF1, 0x03, 0xC5, 0x06, 0x08,
        0xEA, TED_WRITER_BANKED_SCRATCH_ADDR & 0xFF,
        TED_WRITER_BANKED_SCRATCH_ADDR >> 8,
        0xC3, TED_DIRTY_POSTCOPY_BIT_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_BIT_ADDR >> 8,
    ])

    bit = bytes([
        0xFA, TED_WRITER_BANKED_SCRATCH_ADDR & 0xFF,
        TED_WRITER_BANKED_SCRATCH_ADDR >> 8, 0x0F,
        0xEA, TED_WRITER_BANKED_SCRATCH_ADDR & 0xFF,
        TED_WRITER_BANKED_SCRATCH_ADDR >> 8,
        0xD2, TED_WRITER_POINTER_ADVANCE_ADDR & 0xFF,
        TED_WRITER_POINTER_ADVANCE_ADDR >> 8,
        # Preserve CP's carry into the continuation: D<C3 means compile.
        0x7A, 0xFE, 0xC3,
        0xC3, TED_DIRTY_POSTCOPY_BIT_CONT_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_BIT_CONT_ADDR >> 8,
    ])
    bit_cont = bytes([
        0x38, 0x06,                         # JR C,compile
        0x7B, 0xFE, 0xC8,
        0xD2, TED_WRITER_POINTER_ADVANCE_ADDR & 0xFF,
        TED_WRITER_POINTER_ADVANCE_ADDR >> 8,
        0xC5, 0xCD, TED_DIRTY_POSTCOPY_COMPILE_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_COMPILE_ADDR >> 8,
        0xC3, TED_DIRTY_POSTCOPY_BIT_TAIL_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_BIT_TAIL_ADDR >> 8,
    ])
    bit_tail = bytes([
        0xC1,
        0xC3, TED_WRITER_POINTER_ADVANCE_ADDR & 0xFF,
        TED_WRITER_POINTER_ADVANCE_ADDR >> 8,
    ])

    # Every bitmap bit represents the next horizontal 2x2 metatile, whether
    # it was dirty or clean.  The original prototype omitted these increments
    # and consequently recompiled all set bits from C1A0 into D000.  Keep this
    # common step outside the already-full row-advance fragment.
    pointer_advance = bytes([
        0x13, 0x13, 0x23, 0x23,
        0xC3, TED_DIRTY_POSTCOPY_ADVANCE_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_ADVANCE_ADDR >> 8,
    ])

    advance = _Asm()
    advance.db(0xF0, TED_SANITIZER_COUNTER_HRAM, 0x3C, 0xFE, 0x0C)
    advance.db(0x20, (
        TED_DIRTY_POSTCOPY_ADVANCE_CONT_ADDR
        - (TED_DIRTY_POSTCOPY_ADVANCE_ADDR + len(advance.code) + 2)
    ) & 0xFF)
    advance.db(0xAF, 0xE0, TED_SANITIZER_COUNTER_HRAM,
               0x3E, 0x08, 0xCD, 0xDE, 0x09,
               0xC3, (TED_DIRTY_POSTCOPY_ADVANCE_CONT_ADDR + 2) & 0xFF,
               (TED_DIRTY_POSTCOPY_ADVANCE_CONT_ADDR + 2) >> 8)

    # The NZ path stores its live column before falling into the common tail.
    # Splitting at two exact 18-byte native-zero gaps avoids overwriting the
    # stock data immediately following the former $5460 pseudo-cave.
    advance_cont = bytes([
        0xE0, TED_SANITIZER_COUNTER_HRAM,
        0x05, 0xC2, TED_DIRTY_POSTCOPY_BIT_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_BIT_ADDR >> 8,
        0xC1, 0xF0, TED_SANITIZER_EXPECTED_HRAM, 0x3D,
        0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0xC2, TED_DIRTY_POSTCOPY_BYTE_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_BYTE_ADDR >> 8,
        0xC3, TED_DIRTY_POSTCOPY_FINAL_FRONT_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_FINAL_FRONT_ADDR >> 8,
    ])

    compile_meta = _Asm()
    compile_meta.db(0xD5, 0xE5, 0x06, WRAM_BG_TABLE >> 8)
    for _ in range(2):
        compile_meta.db(0x1A, 0x13, 0x4F, 0x0A, 0x22)
    compile_meta.db(0xC3, TED_DIRTY_POSTCOPY_COMPILE_TAIL_ADDR & 0xFF,
                    TED_DIRTY_POSTCOPY_COMPILE_TAIL_ADDR >> 8)
    compile_tail = _Asm()
    compile_tail.db(0x3E, 0x16, 0xCD, 0xE4, 0x09,
                    0x3E, 0x1E, 0xCD, 0xDE, 0x09,
                    0xC3, TED_DIRTY_POSTCOPY_COMPILE_BOTTOM_ADDR & 0xFF,
                    TED_DIRTY_POSTCOPY_COMPILE_BOTTOM_ADDR >> 8)
    compile_bottom = bytes([
        0x1A, 0x13, 0x4F, 0x0A, 0x22,
        0xC3, TED_DIRTY_POSTCOPY_COMPILE_FINAL_ADDR & 0xFF,
        TED_DIRTY_POSTCOPY_COMPILE_FINAL_ADDR >> 8,
    ])
    compile_final = bytes([
        0x1A, 0x13, 0x4F, 0x0A, 0x22,
        0xE1, 0xD1, 0xC9,
    ])

    final_front = _Asm()
    # The byte counter reaches zero on the dirty path, so INC A selects VBK1
    # one byte more compactly than an immediate load.
    final_front.db(0x3C, 0xE0, 0x4F,
             0x3E, 0xD0, 0xE0, 0x51,
             0xAF, 0xE0, 0x52, 0xE0, 0x54,
             0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xE0, 0x53,
             0x3E, 0x2F, 0xE0, 0x55,
             0xC3, TED_DIRTY_POSTCOPY_FINAL_ADDR & 0xFF,
             TED_DIRTY_POSTCOPY_FINAL_ADDR >> 8)
    final = bytes([
        0xAF, 0xE0, 0x4F,
        0x3C, 0xE0, 0x70,
        0xE1, 0xD1, 0xC1, 0xFB, 0xC9,
    ])

    fragments = {
        TED_DIRTY_POSTCOPY_MAIN_ADDR: main.finish(),
        TED_WRITER_INVALIDATE_MAP_ADDR: invalidate_map.finish(),
        TED_DIRTY_POSTCOPY_SCAN_ADDR: scan.finish(),
        TED_DIRTY_POSTCOPY_SCAN_TAIL_ADDR: scan_tail,
        TED_DIRTY_POSTCOPY_SETUP_ADDR: setup,
        TED_DIRTY_POSTCOPY_BYTE_ADDR: byte_loop,
        TED_DIRTY_POSTCOPY_BIT_ADDR: bit,
        TED_DIRTY_POSTCOPY_BIT_CONT_ADDR: bit_cont,
        TED_DIRTY_POSTCOPY_BIT_TAIL_ADDR: bit_tail,
        TED_WRITER_POINTER_ADVANCE_ADDR: pointer_advance,
        TED_DIRTY_POSTCOPY_ADVANCE_ADDR: advance.finish(),
        TED_DIRTY_POSTCOPY_ADVANCE_CONT_ADDR: advance_cont,
        TED_DIRTY_POSTCOPY_COMPILE_ADDR: compile_meta.finish(),
        TED_DIRTY_POSTCOPY_COMPILE_TAIL_ADDR: compile_tail.finish(),
        TED_DIRTY_POSTCOPY_COMPILE_BOTTOM_ADDR: compile_bottom,
        TED_DIRTY_POSTCOPY_COMPILE_FINAL_ADDR: compile_final,
        TED_DIRTY_POSTCOPY_FINAL_FRONT_ADDR: final_front.finish(),
        TED_DIRTY_POSTCOPY_FINAL_ADDR: final,
    }
    capacities = {
        TED_DIRTY_POSTCOPY_MAIN_ADDR: 35,
        TED_WRITER_INVALIDATE_MAP_ADDR: 36,
        TED_DIRTY_POSTCOPY_SCAN_ADDR: 14,
        TED_DIRTY_POSTCOPY_SCAN_TAIL_ADDR: 11,
        TED_DIRTY_POSTCOPY_SETUP_ADDR: 18,
        TED_DIRTY_POSTCOPY_BYTE_ADDR: 36,
        TED_DIRTY_POSTCOPY_BIT_ADDR: 18,
        TED_DIRTY_POSTCOPY_BIT_CONT_ADDR: 15,
        TED_DIRTY_POSTCOPY_BIT_TAIL_ADDR: 8,
        TED_WRITER_POINTER_ADVANCE_ADDR: 24,
        TED_DIRTY_POSTCOPY_ADVANCE_ADDR: 18,
        TED_DIRTY_POSTCOPY_ADVANCE_CONT_ADDR: 18,
        TED_DIRTY_POSTCOPY_COMPILE_ADDR: 19,
        TED_DIRTY_POSTCOPY_COMPILE_TAIL_ADDR: 17,
        TED_DIRTY_POSTCOPY_COMPILE_BOTTOM_ADDR: 9,
        TED_DIRTY_POSTCOPY_COMPILE_FINAL_ADDR: 8,
        TED_DIRTY_POSTCOPY_FINAL_FRONT_ADDR: 31,
        TED_DIRTY_POSTCOPY_FINAL_ADDR: 13,
    }
    for address, payload in fragments.items():
        assert len(payload) <= capacities[address], (hex(address), len(payload))
    return fragments


def build_ted_cached_full_plane_runtime() -> bytes:
    """Publish one clean 32x32 Ted tile+attribute plane from WRAM bank 2.

    The native 24x24 workspace deliberately contains future composite poses,
    so it is useful only for locating the unique five-tile crown.  A cache
    miss rebuilds the complete checker and canonical numbered body; a hit is
    two fixed 0x400-byte GDMA publications.  This removes stale edge cells
    without a per-frame 32x32 classifier pass.
    """
    a = _Asm()
    sparse_enabled = _os.environ.get("PENTA_TED_CACHED_SPARSE", "0") != "0"
    separate_attr_fill = (
        _os.environ.get("PENTA_TED_CACHED_CANONICAL_LIMBS", "0") == "1"
    )
    cache_bank = int(_os.environ.get("PENTA_TED_CACHE_WRAM_BANK", "2"), 0)
    assert 2 <= cache_bank <= 7
    absolute_jumps: list[tuple[int, str]] = []

    def jp(label: str, opcode: int = 0xC3) -> None:
        a.db(opcode, 0x00, 0x00)
        absolute_jumps.append((len(a.code) - 2, label))
    # The private bank-1 trampoline enters with interrupts disabled. Avoid a
    # redundant DI here; the byte is needed for the fixed-bank restore tail.
    a.db(0xC5, 0xD5, 0xE5)                # preserve caller
    a.db(0x3E, cache_bank, 0xE0, 0x70)    # private cache planes

    # Find the unique full $02-$06 crown in the completed 24x24 source.
    a.db(0x21, 0xA0, 0xC1, 0x16, 0x00, 0x06, 0x18)
    a.label("crown_row")
    a.db(0x0E, 0x14)
    a.label("crown_cell")
    a.db(0x7E, 0xFE, 0x02)
    a.jr(0x20, "crown_next")
    a.db(0xE5, 0x1E, 0x03)                 # E = next crown tile
    a.label("crown_run")
    a.db(0x23, 0x7E, 0xBB)
    a.jr(0x20, "crown_bad")
    a.db(0x1C, 0x7B, 0xFE, 0x07)
    a.jr(0x20, "crown_run")
    a.db(0xE1, 0x7A,
         0xEA, TED_CACHED_ANCHOR_ROW_ADDR & 0xFF,
         TED_CACHED_ANCHOR_ROW_ADDR >> 8)
    # The completed publication already exposes the crown at source column
    # 20-C.  Adding the copier's historical eight-column workspace bias here
    # shifted every cached attribute body left of its physical tiles; the
    # 2,800-frame full-plane receipt measured that exact (0,-8) error on every
    # publication. Store the physical crown coordinate directly.
    a.db(0x3E, 0x14, 0x91,
         0xEA, TED_CACHED_ANCHOR_COL_ADDR & 0xFF,
         TED_CACHED_ANCHOR_COL_ADDR >> 8)
    a.jr(0x18, "crown_found")
    a.label("crown_bad")
    a.db(0xE1)
    a.label("crown_next")
    a.db(0x23, 0x0D)
    a.jr(0x20, "crown_cell")
    # Skip the four packed-source columns not searched for a five-cell crown.
    a.db(0x23, 0x23, 0x23, 0x23)
    a.db(0x14, 0x05)
    a.jr(0x20, "crown_row")
    # Ted's sole caller is also used during his short native construction
    # pre-roll, before a complete $02-$06 crown exists. Rebuilding from stale
    # D806/D807 during that phase perturbs the boss state machine and can eject
    # a fast candidate from the arena before its first real publication. Skip
    # only that incomplete visual handoff; the first complete crown rebuilds
    # and publishes the cache normally.
    jp("finish")

    a.label("crown_found")
    # Preserve the physical crown column before the map-selector calculation
    # overwrites A.  The old code saved A only afterwards, so E contained
    # $98/$9C and the cache key ignored horizontal crown moves entirely.
    a.db(0x5F)
    # Only a completed Ted source owns the cached publication. Preserve the
    # native pre-roll's selector until then; once complete, reproduce stock
    # $4295's alternating-map state and retain its destination page.
    # DC0B is not continuously boolean: Ted's native handoff exposes FE/FF
    # sentinels between publications. Preserve that full toggled native byte
    # in memory, but use its low bit as the physical $98/$9C map selector.
    # Skipping FE/FF entirely left the displayed pose four rows behind for a
    # deterministic nine-frame transition; storing a normalized value instead
    # perturbed Ted's state machine. Masking only the working A register keeps
    # both contracts intact.
    a.db(0x21, 0x0B, 0xDC, 0x7E, 0xEE, 0x01, 0x77, 0xE6, 0x01)
    a.db(0x07, 0x07, 0xC6, 0x98, 0xE0, TED_SANITIZER_TILE_MASK_HRAM)
    # The seven stock anchors are four-cell aligned. Pack (row/4)*8 + col/4;
    # the former row*8|col encoding overlapped bits 3-4 and collided when Ted
    # moved horizontally by eight cells.
    # Every native crown row is four-cell aligned, so row*2 already occupies
    # disjoint eight-value bands. Combining it with col/4 is collision-free
    # for the seven stock anchors and leaves the runtime sentinel untouched.
    # A still owns the crown column returned by the scan; retain it before
    # loading D.  Omitting this transfer accidentally keyed every pose from
    # the ABI's stale E=$E0 and made an eight-column move look like a hit.
    a.db(0x7A, 0x87, 0x47,
         0x7B, 0x0F, 0x0F, 0xE6, 0x07, 0xB0, 0x3C, 0x4F)
    a.db(0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xB9)
    jp("publish", 0xCA)
    a.db(0x79, 0xE0, TED_SANITIZER_EXPECTED_HRAM)
    a.label("rebuild")
    if _os.environ.get("PENTA_TED_REBUILD_COUNTER", "0") == "1":
        a.db(0x21, 0x09, 0xD7, 0x34)      # diagnostic rebuild counter
    # A new anchor invalidates the old sparse-overlay restore list.  A cache
    # hit keeps it so the sparse helper can restore precisely what the prior
    # native pose covered before applying the next pose.
    if sparse_enabled:
        # The verified native sparse publisher owns one restore list.  A
        # short-lived canonical-pose experiment added a second per-map list,
        # but that path produced non-native geometry on every frame.  Keep the
        # proven single-list invalidation byte-for-byte in expanded payloads.
        a.db(0xAF, 0xEA, TED_CACHED_SPARSE_COUNT_ADDR & 0xFF,
             TED_CACHED_SPARSE_COUNT_ADDR >> 8)
    # Fill tile and attribute caches together. The former second 1,024-cell
    # LUT pass made a cache miss cross a display frame; emitting the known
    # checker attributes here leaves only the 117 body cells to look up.
    a.db(0x21, 0x00, 0xD0)
    if not separate_attr_fill:
        a.db(0x11, 0x00, 0xD8)
    a.db(0x0E, 0x10)
    a.label("floor_pair")
    a.db(0x06, 0x10)
    a.label("floor_even")
    a.db(0x3E, 0x77, 0x22, 0x3C, 0x22)
    if not separate_attr_fill:
        a.db(0x3E, 0x06, 0x12, 0x13, 0x3C, 0x12, 0x13)
    else:
        a.db(0x00)                         # retain proven miss-path VBlank phase
    a.db(0x05)
    a.jr(0x20, "floor_even")
    a.db(0x06, 0x10)
    a.label("floor_odd")
    a.db(0x3E, 0x79, 0x22, 0x3C, 0x22)
    if not separate_attr_fill:
        a.db(0x3E, 0x07, 0x12, 0x13, 0x3D, 0x12, 0x13)
    else:
        a.db(0x00)                         # retain proven miss-path VBlank phase
    a.db(0x05)
    a.jr(0x20, "floor_odd")
    a.db(0x0D)
    a.jr(0x20, "floor_pair")
    if separate_attr_fill:
        a.db(0xCD, TED_CACHED_ATTR_CLEAR_ADDR & 0xFF,
             TED_CACHED_ATTR_CLEAR_ADDR >> 8)
    # Overlay numbered $02-$76 art using the compact [left+4,right+4)
    # silhouette already shared with the strict classifier.
    # FFA8 is the cached publisher's private counter scratch. Using LDH here
    # saves three runtime bytes versus absolute D803 and keeps the sentinel
    # byte outside executable code.
    a.db(0x3E, 0x02, 0xE0, TED_SANITIZER_COUNTER_HRAM, # next tile ID
         0x0E, 0x00,                       # C = relative row
         0x21, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF,
         TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8)
    a.label("body_row")
    # Keep B as the left edge while A holds right-left.  The previous sequence
    # copied the width back into B before calculating the destination column,
    # so every row began at crown+width-4 instead of crown+left.  Its resulting
    # +5/+6/+8/+10 horizontal bands are exactly what the long geometry receipt
    # rejected.  Stack the width beneath the row-table cursor; this preserves
    # the exact runtime size while leaving C as the relative row coordinate.
    a.db(0x2A, 0x47, 0x2A, 0x90)           # B = left; A = right-left width
    a.db(0xE5, 0xF5)                       # save table cursor, then width
    # E = absolute column = crown column + left+4 - 4.
    a.db(0xFA, TED_CACHED_ANCHOR_COL_ADDR & 0xFF,
         TED_CACHED_ANCHOR_COL_ADDR >> 8,
         0x80, 0xD6, 0x04, 0xE6, 0x1F, 0x5F)
    # Tilemap columns wrap independently modulo 32. Without this mask, a
    # right-edge pose spills Ted's positive columns into the following row,
    # producing the characteristic split body and duplicated lower fringe.
    # B = absolute row; form HL=$D000 + row*32 + column.
    a.db(0xFA, TED_CACHED_ANCHOR_ROW_ADDR & 0xFF,
         TED_CACHED_ANCHOR_ROW_ADDR >> 8, 0x81, 0x47)
    a.db(0xE6, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x83, 0x6F)
    a.db(0x78, 0x0F, 0x0F, 0x0F, 0xE6, 0x03, 0xC6, 0xD0, 0x67)
    # DE is the matching attribute cell eight pages above HL. Bank-2 $D400
    # hosts the executable row helper and intermittently overwrote the old
    # cache. Metadata now lives at $D700, leaving $D800-$DBFF as the reserved
    # Ted attribute plane without reaching the $DFxx stack.
    a.db(0x54, 0x5D, 0x7A, 0xC6, 0x08, 0x57)
    a.db(0xF1, 0x47)                       # B = saved row width
    a.label("body_cell")
    a.db(0xF0, TED_SANITIZER_COUNTER_HRAM, 0x22,
         0x3C, 0xE0, TED_SANITIZER_COUNTER_HRAM, 0x3D, 0xE5,
         0x6F, 0x26, TED_TABLE_ADDR >> 8, 0x7E, 0xE1, 0x12, 0x13,
         0xCD, TED_CACHED_COLUMN_WRAP_ADDR & 0xFF,
         TED_CACHED_COLUMN_WRAP_ADDR >> 8,
         0x05)
    a.jr(0x20, "body_cell")
    a.db(0xE1, 0x0C, 0x79, 0xFE, 0x0E)
    a.jr(0x20, "body_row")
    if _os.environ.get("PENTA_TED_CACHE_CANARY", "0") == "1":
        # Diagnostic only: A=$0E after the row-count comparison. An impossible
        # attribute makes any later overwrite unambiguous without extra bytes.
        a.db(0xEA, 0xA5, 0xD9)

    a.label("publish")
    if sparse_enabled:
        a.db(0xCD, TED_CACHED_SPARSE_ENTRY_ADDR & 0xFF,
             TED_CACHED_SPARSE_ENTRY_ADDR >> 8)
    a.db(0xCD, TED_CACHED_PUBLISH_FRONT_ADDR & 0xFF,
         TED_CACHED_PUBLISH_FRONT_ADDR >> 8)
    # Publish only the off-screen map selected by stock $4295. Publishing the
    # peer too writes through the currently visible map; the rebuild plus four
    # 1 KiB GDMAs can cross a frame boundary and expose a partial Ted pose.
    # Stock alternation prepares each map before LCDC selects it, so one
    # complete tile+attribute pair per call is both sufficient and atomic to
    # the viewer.
    # The publisher returns with VBK0 already selected.
    # Stock $4295 returns AF=$01C0; its caller consumes those flags while
    # advancing Ted's source animation. CP A recreates Z+N without changing A.
    a.label("finish")
    a.db(0x3E, 0x01, 0xE0, 0x70,
         0xE1, 0xD1, 0xC1,
         # Return directly to fixed $028D; its stock JP $0D55 performs the
         # caller's required bank-2 cleanup. Mapping bank 1 here was redundant
         # and consumed five bytes from the C600 LUT boundary.
         0xFA, 0x0B, 0xDC, 0xE6, 0x01, 0x07, 0x07,
         0xC6, 0x9B, 0x67, 0x2E, 0x00,
         0x3E, 0x01, 0xBF, 0xFB,
         # Delay only after restoring bank/register state and scheduling IME.
         # Holding interrupts off during this same cadence compensation made
         # nine visible palette-transition frames miss their VBlank service.
         0xC3, TED_CACHED_CADENCE_DELAY_ADDR & 0xFF,
         TED_CACHED_CADENCE_DELAY_ADDR >> 8)
    code = bytearray(a.finish())
    for operand, label in absolute_jumps:
        target = TED_CACHED_RUNTIME_ADDR + a.labels[label]
        code[operand] = target & 0xFF
        code[operand + 1] = target >> 8
    runtime_capacity = WRAM_BG_TABLE - TED_CACHED_RUNTIME_ADDR
    assert len(code) <= runtime_capacity, len(code)
    return code + bytes(runtime_capacity - len(code))


def build_ted_cached_full_plane_fragments() -> dict[int, bytes]:
    """Fragmented lazy installer and banked entry for the WRAM publisher."""
    runtime = build_ted_cached_full_plane_runtime()
    sources = (
        TED_SANITIZER_MAIN_ADDR, TED_SANITIZER_CLASSIFY_ADDR,
        TED_SANITIZER_CROWN_ADDR, TED_SANITIZER_ACTIVE_ADDR,
        TED_SANITIZER_ROW_TABLE_ADDR, TED_SANITIZER_GEOMETRY_CONT_ADDR,
        TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR,
        TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR,
        TED_CACHED_RUNTIME_EXTRA_SOURCE_ADDR,
    )
    # $54F2-$5509 is a verified 24-byte zero record. Three formerly-unused
    # tail bytes hold the safe fixed-bank return required by the private
    # bank-1 entry, without taking space from any live asset.
    capacities = (36, 36, 36, 36, 36, 36, 24, 31, 13)
    fragments: dict[int, bytes] = {}
    cursor = 0
    copies = []
    for source, capacity in zip(sources, capacities):
        chunk = runtime[cursor:cursor + capacity]
        fragments[source] = chunk
        # The stock BC-counted memcpy treats BC=0 as 65,536 bytes.  Once the
        # runtime was tightened to stop before C600, its ninth fragment became
        # empty; emitting a nominal zero-byte copy corrupted the entire arena.
        copies.append(bytes([
            0x21, source & 0xFF, source >> 8,
            0x11, (TED_CACHED_RUNTIME_ADDR + cursor) & 0xFF,
            (TED_CACHED_RUNTIME_ADDR + cursor) >> 8,
            0x01, len(chunk), 0x00, 0xCD, 0xB3, 0x09,
        ]) if chunk else b"")
        cursor += len(chunk)
    assert cursor == len(runtime)
    front = bytes([0xC5, 0xD5, 0xE5]) + b"".join(copies[:2]) + bytes([
        0xC3, TED_SANITIZER_INSTALL_MIDDLE_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_MIDDLE_ADDR >> 8,
    ])
    middle = b"".join(copies[2:4]) + bytes([
        0xC3, TED_SANITIZER_INSTALL_TAIL_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_TAIL_ADDR >> 8,
    ])
    tail = b"".join(copies[4:6]) + bytes([
        0xC3, TED_SANITIZER_INSTALL_FINAL_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_FINAL_ADDR >> 8,
    ])
    final = b"".join(copies[6:8]) + bytes([
        # Stock memcpy preserves AF, so stage the sentinel here and let the
        # exact 21-byte $6FFF cave spend only its three-byte absolute store.
        0x3E, TED_SANITIZER_RUNTIME_SENTINEL_VALUE,
        0xC3, TED_CACHED_INSTALL_EXTRA_ADDR & 0xFF,
        TED_CACHED_INSTALL_EXTRA_ADDR >> 8,
        # Unreachable after the JP above. The WRAM publisher calls this exact
        # seven-byte tail to begin immediate GDMA only from VBlank.
        # Wait for the first scanline of VBlank, not merely any LY >= $90.
        # The paired tile+attribute GDMAs need the complete ten-line window;
        # entering late could expose the tile plane before its attributes.
        0xF0, 0x44, 0xFE, 0x90, 0x20, 0xFA, 0xC9,
    ])
    install_extra = copies[8] + bytes([
        0xEA, TED_SANITIZER_RUNTIME_SENTINEL_ADDR & 0xFF,
        TED_SANITIZER_RUNTIME_SENTINEL_ADDR >> 8,
        0xAF, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0xE1, 0xD1, 0xC1,
        0xC3, TED_CACHED_RUNTIME_ADDR & 0xFF,
        TED_CACHED_RUNTIME_ADDR >> 8,
        # Unreachable after the JP above; the remaining asserted-zero cave is
        # a shared post-wait GDMA commit subroutine.
        0x3E, 0x3F, 0xE0, 0x55,
        0xAF, 0xE0, 0x4F, 0xC9,
    ])
    entry = bytes([
        0xFA, TED_SANITIZER_RUNTIME_SENTINEL_ADDR & 0xFF,
        TED_SANITIZER_RUNTIME_SENTINEL_ADDR >> 8,
        0xFE, TED_SANITIZER_RUNTIME_SENTINEL_VALUE,
        0xCA, TED_CACHED_RUNTIME_ADDR & 0xFF,
        TED_CACHED_RUNTIME_ADDR >> 8,
        0xC3, TED_SANITIZER_INSTALL_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_ADDR >> 8,
    ])
    assert len(entry) == 11
    publish_front_all = bytes([
        0xAF, 0xE0, 0x4F, 0xE0, 0x52, 0xE0, 0x54,
        0x3E, 0xD0, 0xE0, 0x51,
        0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xE0, 0x53,
        0xCD, TED_CACHED_GDMA_WAIT_ADDR & 0xFF,
        TED_CACHED_GDMA_WAIT_ADDR >> 8,
        0xCD, TED_CACHED_GDMA_COMMIT_ADDR & 0xFF,
        TED_CACHED_GDMA_COMMIT_ADDR >> 8,
    ])
    publish_tail_all = publish_front_all[21:] + bytes([
        0x3E, 0x01, 0xE0, 0x4F, 0xAF, 0xE0, 0x52, 0xE0, 0x54,
        0x3E, 0xD8, 0xE0, 0x51,
        0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xE0, 0x53,
        # The tile GDMA immediately above starts at the beginning of VBlank.
        # A second 1 KiB GDMA still fits in the same CGB VBlank budget; waiting
        # for LY=$90 again exposed one full frame of new tiles with stale
        # attributes whenever Ted crossed the physical-map wrap.
        0xCD, TED_CACHED_GDMA_COMMIT_ADDR & 0xFF,
        TED_CACHED_GDMA_COMMIT_ADDR >> 8, 0xC9,
    ])
    publish_front = publish_front_all[:21] + bytes([
        0xC3, TED_CACHED_PUBLISH_TAIL_ADDR & 0xFF,
        TED_CACHED_PUBLISH_TAIL_ADDR >> 8,
    ])
    # The 55D8 cave is exactly 13 bytes. Split before the complete ``LD A,D4``
    # instruction; the former [:10] split made the jump opcode ($C3) become
    # that instruction's immediate and never executed the attribute GDMA.
    publish_tail = publish_tail_all[:9] + bytes([
        0xC3, TED_CACHED_PUBLISH_TAIL_CONT_ADDR & 0xFF,
        TED_CACHED_PUBLISH_TAIL_CONT_ADDR >> 8,
    ])
    publish_tail_cont = publish_tail_all[9:15] + bytes([
        0xC3, TED_CACHED_PUBLISH_TAIL_FINAL_ADDR & 0xFF,
        TED_CACHED_PUBLISH_TAIL_FINAL_ADDR >> 8,
    ])
    publish_tail_final = publish_tail_all[15:]
    column_wrap = bytes([
        0x7D, 0xE6, 0x1F, 0xC0,            # remain in the same map row
        0x7D, 0xD6, 0x20, 0x6F,            # subtract 32 from low byte
        0x7C, 0xDE, 0x00, 0x67,            # propagate borrow into H
        0xC6, 0x08, 0x57, 0x5D, 0xC9,      # DE = corrected HL + $0800
    ])
    assert len(publish_tail) == 12
    assert len(publish_tail_cont) == 9
    assert len(publish_tail_final) == 6
    assert len(entry + publish_front) <= ARENA_SANITIZER_FRAGMENT_SIZE
    for payload in (
        front, middle, tail, final, install_extra, entry,
        publish_tail, publish_tail_cont,
        publish_tail_final,
    ):
        assert len(payload) <= ARENA_SANITIZER_FRAGMENT_SIZE, len(payload)
    fragments.update({
        TED_SANITIZER_INSTALL_ADDR: front,
        TED_SANITIZER_INSTALL_MIDDLE_ADDR: middle,
        TED_SANITIZER_INSTALL_TAIL_ADDR: tail,
        TED_SANITIZER_INSTALL_FINAL_ADDR: final,
        TED_CACHED_INSTALL_EXTRA_ADDR: install_extra,
        TED_REGISTER_MATERIALIZER_FRONT_ADDR: entry + publish_front,
        TED_CACHED_PUBLISH_TAIL_ADDR: publish_tail,
        TED_CACHED_PUBLISH_TAIL_CONT_ADDR: publish_tail_cont,
        TED_CACHED_PUBLISH_TAIL_FINAL_ADDR: publish_tail_final,
        TED_CACHED_COLUMN_WRAP_ADDR: column_wrap,
        # This delay runs after EI so VBlank service remains live. Three loops
        # are 1.85% fast and four are 2.15% slow, so alternate them in bounded
        # 16-frame blocks from the existing VBlank counter. A 253-iteration
        # first loop
        # offsets the constant selector cost; no new state or map scan is
        # introduced, and cadence is decoupled from sparse-limb animation.
        # by bypassing the stock 576-cell CPU copier. This is deterministic,
        # independent of pose complexity, and touches no game state.
        TED_CACHED_CADENCE_DELAY_ADDR: bytes.fromhex(
            "F0 D4 E6 10 06 02 20 01 04 "
            "0E FD 0D 20 FD "
            "0E 00 0D 20 FD 05 20 F8 C9"
        ),
    })
    return fragments


def build_ted_cached_sparse_fragments() -> dict[int, bytes]:
    """Track and publish Ted's native sparse limb cells without trails.

    The 24x24 stock workspace contains 45 complete native poses plus a small
    set of future-pose staging cells.  The numbered body is reconstructed by
    the cache; this helper restores the prior sparse overlay byte-for-byte,
    scans the current source, rejects only the two measured staging families,
    and overlays each surviving limb with its YAML LUT attribute.  At most 22
    cells are live in the full native pose corpus.
    """
    canonical_limbs = (
        _os.environ.get("PENTA_TED_CACHED_CANONICAL_LIMBS", "0") == "1"
    )
    entry = _Asm()
    entry.db(0xC5, 0xD5, 0xE5)             # preserve caller BC/DE/HL
    entry.db(0xFA, TED_CACHED_SPARSE_COUNT_ADDR & 0xFF,
             TED_CACHED_SPARSE_COUNT_ADDR >> 8, 0xB7)
    entry.jr(0x28, "setup")
    entry.db(0x47,
             0x21, TED_CACHED_SPARSE_RECORDS_ADDR & 0xFF,
             TED_CACHED_SPARSE_RECORDS_ADDR >> 8)
    entry.db(0xC3, TED_CACHED_SPARSE_RESTORE_ADDR & 0xFF,
             TED_CACHED_SPARSE_RESTORE_ADDR >> 8)
    entry.label("setup")
    entry.db(0xC3, TED_CACHED_SPARSE_SETUP_ADDR & 0xFF,
             TED_CACHED_SPARSE_SETUP_ADDR >> 8)

    restore = _Asm()
    restore.label("loop")
    restore.db(
        0x5E, 0x23, 0x56, 0x23,            # DE = cached tile address
        0x2A, 0x12,                        # restore old tile
        0x7A, 0xC6, 0x08, 0x57,
        0x2A, 0x12,                        # restore old attribute
        0x05,
    )
    restore.jr(0x20, "loop")
    restore.db(0xAF, 0xEA, TED_CACHED_SPARSE_COUNT_ADDR & 0xFF,
               TED_CACHED_SPARSE_COUNT_ADDR >> 8)
    restore.db(0xC3, TED_CACHED_SPARSE_SETUP_ADDR & 0xFF,
               TED_CACHED_SPARSE_SETUP_ADDR >> 8)

    setup = bytes([
        0x21, 0xA0, 0xC1,                  # native 24x24 source
        0x06, 0x18, 0x0E, 0x18,
        0xC3, TED_CACHED_SPARSE_SCAN_ADDR & 0xFF,
        TED_CACHED_SPARSE_SCAN_ADDR >> 8,
    ])

    scan = _Asm()
    scan.label("cell")
    scan.db(0x2A, 0xFE, 0x7B,
            0xDA, TED_CACHED_SPARSE_SCAN_TAIL_ADDR & 0xFF,
            TED_CACHED_SPARSE_SCAN_TAIL_ADDR >> 8,
            0xFE, 0x87,
            0xD2, TED_CACHED_SPARSE_SCAN_TAIL_ADDR & 0xFF,
            TED_CACHED_SPARSE_SCAN_TAIL_ADDR >> 8,
            0xCD, TED_CACHED_SPARSE_FILTER_ADDR & 0xFF,
            TED_CACHED_SPARSE_FILTER_ADDR >> 8,
            0xC3, TED_CACHED_SPARSE_SCAN_TAIL_ADDR & 0xFF,
            TED_CACHED_SPARSE_SCAN_TAIL_ADDR >> 8)
    scan_tail = _Asm()
    scan_tail.db(0x0D, 0xC2,
                 TED_CACHED_SPARSE_SCAN_ADDR & 0xFF,
                 TED_CACHED_SPARSE_SCAN_ADDR >> 8,
                 0x0E, 0x18, 0x05, 0xC2,
                 TED_CACHED_SPARSE_SCAN_ADDR & 0xFF,
                 TED_CACHED_SPARSE_SCAN_ADDR >> 8)
    scan_tail.db(0xE1, 0xD1, 0xC1, 0xC9)

    filt = _Asm()
    filt.db(0xEA, TED_CACHED_SPARSE_TILE_ADDR & 0xFF,
            TED_CACHED_SPARSE_TILE_ADDR >> 8)
    # The scan front admits only $7B-$86. Reject the four holes here; ordinary
    # numbered/checker cells never pay a CALL into this classifier.
    for tile in (0x7C, 0x7E, 0x7F, 0x81):
        filt.db(0xFE, tile, 0xC8)
    # D/E = signed-five crown-relative row/column.
    # B/C count down 24..1; convert them to forward 0..23 coordinates while
    # subtracting the cached crown in one expression.
    filt.db(0xFA, TED_CACHED_ANCHOR_ROW_ADDR & 0xFF,
            TED_CACHED_ANCHOR_ROW_ADDR >> 8,
            0x80, 0x2F, 0x3C, 0xC6, 0x18,
            0xE6, 0x1F, 0x57)
    filt.db(0xFA, TED_CACHED_ANCHOR_COL_ADDR & 0xFF,
            TED_CACHED_ANCHOR_COL_ADDR >> 8,
            0x81, 0x2F, 0x3C, 0xC6, 0x18,
            0xE6, 0x1F, 0x5F)
    # All observed left-side staging cells occupy relative columns -3..0 on
    # row zero or a negative row.  The sole native exception is tile $83 at
    # (-16,0), part of the long vertical extension.
    filt.db(0x7B, 0xC6, 0x03, 0xE6, 0x1F, 0xFE, 0x04)
    filt.jr(0x30, "edge_ok")
    filt.db(0x7A, 0x3D, 0xFE, 0x0F)
    filt.jr(0x38, "edge_ok")
    filt.db(0xFA, TED_CACHED_SPARSE_TILE_ADDR & 0xFF,
            TED_CACHED_SPARSE_TILE_ADDR >> 8, 0xFE, 0x83)
    filt.jr(0x20, "reject")
    filt.db(0x7A, 0xFE, 0x10)
    filt.jr(0x20, "reject")
    filt.db(0x7B, 0xB7)
    filt.jr(0x20, "reject")
    filt.label("edge_ok")
    # Two late right-edge staging cells are otherwise geometrically valid.
    filt.db(0x7B, 0xFE, 0x09)
    filt.jr(0x20, "overlay")
    filt.db(0x7A, 0xFE, 0x0E)
    filt.jr(0x38, "overlay")
    filt.db(0xFA, TED_CACHED_SPARSE_TILE_ADDR & 0xFF,
            TED_CACHED_SPARSE_TILE_ADDR >> 8, 0xFE, 0x82)
    filt.jr(0x28, "reject")
    filt.db(0xFE, 0x85)
    filt.jr(0x20, "overlay")
    filt.label("reject")
    filt.db(0xC9)
    filt.label("overlay")
    filt.db(0xFA, TED_CACHED_SPARSE_COUNT_ADDR & 0xFF,
            TED_CACHED_SPARSE_COUNT_ADDR >> 8, 0xFE, 0x16, 0xD0)
    filt.db(0xC3, TED_CACHED_SPARSE_OVERLAY_A_ADDR & 0xFF,
            TED_CACHED_SPARSE_OVERLAY_A_ADDR >> 8)

    overlay_a = bytes([
        0xE5,
        0xFA, TED_CACHED_ANCHOR_COL_ADDR & 0xFF,
        TED_CACHED_ANCHOR_COL_ADDR >> 8, 0x83, 0xE6, 0x1F, 0x5F,
        0xFA, TED_CACHED_ANCHOR_ROW_ADDR & 0xFF,
        TED_CACHED_ANCHOR_ROW_ADDR >> 8, 0x82, 0xE6, 0x1F,
        0xC3, TED_CACHED_SPARSE_OVERLAY_B_ADDR & 0xFF,
        TED_CACHED_SPARSE_OVERLAY_B_ADDR >> 8,
    ])
    overlay_b = bytes([
        0x57, 0x7A, 0xE6, 0x07,
        0x07, 0x07, 0x07, 0x07, 0x07,
        0x83, 0x6F,
        0xC3, TED_CACHED_SPARSE_OVERLAY_C_ADDR & 0xFF,
        TED_CACHED_SPARSE_OVERLAY_C_ADDR >> 8,
    ])
    overlay_c = bytes([
        0x7A, 0x0F, 0x0F, 0x0F, 0xE6, 0x03, 0xC6, 0xD0, 0x67,
        0x54, 0x5D,
        0xC3, TED_CACHED_SPARSE_OVERLAY_D_ADDR & 0xFF,
        TED_CACHED_SPARSE_OVERLAY_D_ADDR >> 8,
    ])
    overlay_d = bytes([
        0xFA, TED_CACHED_SPARSE_COUNT_ADDR & 0xFF,
        TED_CACHED_SPARSE_COUNT_ADDR >> 8, 0x87, 0x87, 0xC6, 0x20,
        0x6F, 0x26, TED_CACHED_SPARSE_RECORDS_ADDR >> 8,
        0xC3, TED_CACHED_SPARSE_OVERLAY_E_ADDR & 0xFF,
        TED_CACHED_SPARSE_OVERLAY_E_ADDR >> 8,
    ])
    overlay_e = bytes([
        0x73, 0x23, 0x72, 0x23, 0x1A, 0x22,
        0x7A, 0xC6, 0x08, 0x57, 0x1A, 0x22,
        0xC3, TED_CACHED_SPARSE_OVERLAY_F_ADDR & 0xFF,
        TED_CACHED_SPARSE_OVERLAY_F_ADDR >> 8,
    ])
    overlay_f = bytes([
        0x7A, 0xD6, 0x08, 0x57,
        0xFA, TED_CACHED_SPARSE_TILE_ADDR & 0xFF,
        TED_CACHED_SPARSE_TILE_ADDR >> 8, 0x12,
        0x6F, 0x26, TED_TABLE_ADDR >> 8, 0x7E,
        0xE1,
        0xC3, TED_CACHED_SPARSE_OVERLAY_G_ADDR & 0xFF,
        TED_CACHED_SPARSE_OVERLAY_G_ADDR >> 8,
    ])
    overlay_g = bytes([
        # A is the LUT attribute. Preserve it while moving DE from the tile
        # plane to the matching attribute plane; the former LD A,D sequence
        # wrote literal $D4/$D5/$D6 bytes as attributes.
        0xF5, 0x7A, 0xC6, 0x08, 0x57, 0xF1, 0x12,
        0xC3, TED_CACHED_SPARSE_OVERLAY_H_ADDR & 0xFF,
        TED_CACHED_SPARSE_OVERLAY_H_ADDR >> 8,
    ])
    overlay_h = bytes([
        0xFA, TED_CACHED_SPARSE_COUNT_ADDR & 0xFF,
        TED_CACHED_SPARSE_COUNT_ADDR >> 8, 0x3C,
        0xEA, TED_CACHED_SPARSE_COUNT_ADDR & 0xFF,
        TED_CACHED_SPARSE_COUNT_ADDR >> 8,
        0xC9,
    ])

    fragments = {
        TED_CACHED_SPARSE_ENTRY_ADDR: entry.finish(),
        TED_CACHED_SPARSE_RESTORE_ADDR: restore.finish(),
        TED_CACHED_SPARSE_SETUP_ADDR: setup,
        TED_CACHED_SPARSE_SCAN_ADDR: scan.finish(),
        TED_CACHED_SPARSE_SCAN_TAIL_ADDR: scan_tail.finish(),
        TED_CACHED_SPARSE_FILTER_ADDR: filt.finish(),
        TED_CACHED_SPARSE_OVERLAY_A_ADDR: overlay_a,
        TED_CACHED_SPARSE_OVERLAY_B_ADDR: overlay_b,
        TED_CACHED_SPARSE_OVERLAY_C_ADDR: overlay_c,
        TED_CACHED_SPARSE_OVERLAY_D_ADDR: overlay_d,
        TED_CACHED_SPARSE_OVERLAY_E_ADDR: overlay_e,
        TED_CACHED_SPARSE_OVERLAY_F_ADDR: overlay_f,
        TED_CACHED_SPARSE_OVERLAY_G_ADDR: overlay_g,
        TED_CACHED_SPARSE_OVERLAY_H_ADDR: overlay_h,
    }
    if canonical_limbs:
        # The raw 24x24 workspace includes future-pose staging cells. Scanning
        # and heuristically filtering it can combine individually-valid limb
        # cells into a layout that never exists natively. Alternate instead
        # between two receipt-proven native poses: the numbered body alone and
        # its compact three-cell tendril extension. This preserves visible
        # animation while making every publication deterministic and O(1).
        finish_addr = TED_CACHED_SPARSE_SCAN_TAIL_ADDR
        pose_addr = TED_CACHED_SPARSE_FILTER_ADDR
        fragments[TED_CACHED_SPARSE_SETUP_ADDR] = bytes([
            0xC3, TED_CACHED_SPARSE_SCAN_ADDR & 0xFF,
            TED_CACHED_SPARSE_SCAN_ADDR >> 8,
        ])
        # Use a bounded, state-independent 16-frame phase: eight frames with
        # the compact native tendril pose, then eight body-only frames.  This
        # is the receipt-proven v73 sequence and avoids scanning future-pose
        # staging cells in the native 24x24 workspace.
        fragments[TED_CACHED_SPARSE_SCAN_ADDR] = bytes([
            0x21, TED_CACHED_LIMB_PHASE_ADDR & 0xFF,
            TED_CACHED_LIMB_PHASE_ADDR >> 8,
            0x34, 0xCB, 0x66,
            0xCA, finish_addr & 0xFF, finish_addr >> 8,
            0xC3, pose_addr & 0xFF, pose_addr >> 8,
        ])
        fragments[TED_CACHED_SPARSE_SCAN_TAIL_ADDR] = bytes([
            0xE1, 0xD1, 0xC1, 0xC9,
        ])
        pose = bytearray()
        for tile, row, column in (
            (0x84, 5, -3),
            (0x86, 5, 6),
            (0x83, 10, -3),
        ):
            pose.extend((
                0x3E, tile,
                0xEA, TED_CACHED_SPARSE_TILE_ADDR & 0xFF,
                TED_CACHED_SPARSE_TILE_ADDR >> 8,
                0x11, column & 0x1F, row & 0x1F,
                0xCD, TED_CACHED_SPARSE_OVERLAY_A_ADDR & 0xFF,
                TED_CACHED_SPARSE_OVERLAY_A_ADDR >> 8,
            ))
        pose.extend((0xC3, finish_addr & 0xFF, finish_addr >> 8))
        fragments[TED_CACHED_SPARSE_FILTER_ADDR] = bytes(pose)
        # Use the ordinary byte-for-byte restore record even for this compact
        # pose.  Skipping it removes numbered body cells permanently and was
        # caught as non-native geometry on all 2,800 verification frames.
        # Sixteen pairs of 32-cell rows form one complete checker attribute
        # plane: even rows repeat 6,7 and odd rows repeat 7,6. Keeping this
        # independent from the tile fill prevents DE/HL phase drift while
        # retaining a fixed O(1) cache-miss cost.
        fragments[TED_CACHED_ATTR_CLEAR_ADDR] = bytes([
            0x21, 0x00, 0xD8, 0x0E, 0x10,
            0x06, 0x10, 0x3E, 0x06,
            0x22, 0x3C, 0x22, 0x3D, 0x05, 0x20, 0xF9,
            0x06, 0x10, 0x3E, 0x07,
            0x22, 0x3D, 0x22, 0x3C, 0x05, 0x20, 0xF9,
            0x0D, 0x20, 0xE7, 0xC9,
        ])
    capacities = {
        TED_CACHED_SPARSE_ENTRY_ADDR: 24,
        TED_CACHED_SPARSE_RESTORE_ADDR: 24,
        TED_CACHED_SPARSE_SETUP_ADDR: 11,
        TED_CACHED_SPARSE_SCAN_ADDR: 17,
        TED_CACHED_SPARSE_SCAN_TAIL_ADDR: 14,
        TED_CACHED_SPARSE_FILTER_ADDR: 121,
        TED_CACHED_ATTR_CLEAR_ADDR: 31,
        TED_CACHED_SPARSE_OVERLAY_A_ADDR: 18,
        TED_CACHED_SPARSE_OVERLAY_B_ADDR: 18,
        TED_CACHED_SPARSE_OVERLAY_C_ADDR: 18,
        TED_CACHED_SPARSE_OVERLAY_D_ADDR: 15,
        TED_CACHED_SPARSE_OVERLAY_E_ADDR: 18,
        TED_CACHED_SPARSE_OVERLAY_F_ADDR: 19,
        TED_CACHED_SPARSE_OVERLAY_G_ADDR: 11,
        TED_CACHED_SPARSE_OVERLAY_H_ADDR: 9,
    }
    for address, payload in fragments.items():
        assert len(payload) <= capacities[address], (hex(address), len(payload))
    return fragments


def build_ted_cached_full_plane_wrapper() -> tuple[bytes, bytes, bytes]:
    """Enter the cached publisher from Ted's receipt-proven sole caller.

    The 2,800-frame native publication census identifies fixed ``$028A`` as
    Ted's only alternating-map caller. Owning shared entry ``$4295`` or the
    shared ``$DB80`` arena helper broke the cold title/Stage-1 route before Ted
    existed. This trampoline lives in bank 1's asserted-zero ``$6FE4`` cave,
    reaches a fixed-bank continuation which maps bank 13, establishes the
    native return ABI, and tail-enters the lazy cached publisher.  The bank
    switch cannot return into a switchable-bank continuation: after mapping
    bank 13, the bytes at that return address would no longer be bank-1 code.
    The publisher restores bank 1 before returning directly to $028D.
    """
    front = bytes([
        0xF0, TED_SANITIZER_EXPECTED_HRAM,
        0x47,
        0xFA, 0x88, 0xD8,
        0xB0,
        0xCA, 0x95, 0x42,
        0xC3, TED_CACHED_BANK1_TAIL_ADDR & 0xFF,
        TED_CACHED_BANK1_TAIL_ADDR >> 8,
    ])
    tail = bytes([
        0xC3, TED_CACHED_FIXED_CONT_ADDR & 0xFF,
        TED_CACHED_FIXED_CONT_ADDR >> 8,
    ])
    fixed = bytes([
        0xF3,
        0x01, 0x08, 0x00,
        0x11, 0xE0, 0xC3,
        0x3E, 0x0D, 0xCD, 0x61, 0x00,
        0xC3, TED_REGISTER_MATERIALIZER_FRONT_ADDR & 0xFF,
        TED_REGISTER_MATERIALIZER_FRONT_ADDR >> 8,
    ])
    assert len(front) == 13 and len(tail) == 3 and len(fixed) == 15
    return front, tail, fixed


def build_ted_cached_ready_latch() -> bytes:
    """Remember Ted's native activation until his next map publication.

    The activation phase lasts many frames but need not overlap $028A. The
    existing once-per-eight-frame palette probe calls this helper, which arms
    FFA9 only before the cached runtime is installed. The installer clears the
    latch, publishes a real anchor key, and sets C5FF so this becomes a cheap
    early return for the remainder of the arena.
    """
    code = bytes([
        0xFA, TED_SANITIZER_RUNTIME_SENTINEL_ADDR & 0xFF,
        TED_SANITIZER_RUNTIME_SENTINEL_ADDR >> 8,
        0xB7, 0xC0,                        # installed -> RET NZ
        0xFA, 0x80, 0xD8, 0xFE, 0x10, 0xC0,
        0xFA, 0x88, 0xD8, 0xB7, 0xC8,     # pre-activation -> RET Z
        0x3E, 0xFF, 0xE0, TED_SANITIZER_EXPECTED_HRAM, 0xC9,
    ])
    assert len(code) == 21
    return code


def build_ted_cached_palette_gate() -> bytes:
    """Latch native Ted readiness, then run the ordinary palette service."""
    return bytes([
        0xCD, TED_CACHED_READY_LATCH_ADDR & 0xFF,
        TED_CACHED_READY_LATCH_ADDR >> 8,
        0xC3, CONDITIONAL_PALETTE_ADDR & 0xFF,
        CONDITIONAL_PALETTE_ADDR >> 8,
    ])


def build_ted_cached_abi_fragments() -> dict[int, bytes]:
    """Materialize the exact BC/DE/HL contract returned by stock $4295."""
    front = bytes([
        0x01, 0x08, 0x00,                  # BC=$0008
        0x11, 0xE0, 0xC3,                  # DE=$C3E0
        0xC3, TED_CACHED_ABI_TAIL_ADDR & 0xFF,
        TED_CACHED_ABI_TAIL_ADDR >> 8,
    ])
    tail = bytes([
        0xFA, 0x0B, 0xDC, 0x07, 0x07,     # selected map * 4
        0xC6, 0x9B, 0x67,                  # H=$9B/$9F
        0x2E, 0x00, 0xC9,
    ])
    assert len(front) <= 11 and len(tail) <= 13
    return {TED_CACHED_ABI_FRONT_ADDR: front, TED_CACHED_ABI_TAIL_ADDR: tail}


def build_arena_attr_semantic_decider() -> tuple[bytes, bytes, bytes, bytes, bytes]:
    """Build the bank-13 cold dispatcher, WRAM sources, and installer."""
    dispatch = _Asm()
    dispatch.db(
        0xFA, 0x80, 0xD8, 0xD6, 0x03, 0xFE, 0x06,
    )
    dispatch.jr(0x38, "atomic")
    dispatch.db(0xD6, 0x09, 0xFE, 0x09)
    dispatch.jr(0x38, "arena")
    dispatch.label("neutral")
    dispatch.db(0xAF, 0xE0, LAVA_ATTR_DECISION_HRAM, 0x3C, 0xC9)
    dispatch.label("atomic")
    dispatch.db(0x3E, 0x01, 0xE0, LAVA_ATTR_DECISION_HRAM, 0xC9)
    dispatch.label("arena")
    dispatch.db(0x7C, 0xE6, 0xF8, 0xFE, 0x98)
    dispatch.jr(0x20, "neutral")
    dispatch.db(
        0xC3,
        ARENA_ATTR_SEMANTIC_CHANGED_ADDR & 0xFF,
        ARENA_ATTR_SEMANTIC_CHANGED_ADDR >> 8,
    )
    dispatch_code = dispatch.finish()

    runtime = build_arena_attr_semantic_runtime()
    source_a = runtime[:36]
    source_b = runtime[36:72]
    source_c = runtime[72:]
    installer = build_penta_visible_seam_repair()
    assert len(source_a) == 36 and 0 < len(source_b) <= 36
    assert len(source_c) <= 36
    assert len(dispatch_code) <= ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE
    return dispatch_code, source_a, source_b, source_c, installer


def build_penta_visible_seam_repair() -> bytes:
    """Repair Penta's one native staging cell after the map publisher."""
    a = _Asm()
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x14)
    a.db(0xC2, LAVA_OVERRIDE_ADDR & 0xFF, LAVA_OVERRIDE_ADDR >> 8)
    a.db(0x21, 0x2F, 0x99, 0x7E, 0x6F, 0x26, 0xC6, 0x7E, 0x47)
    a.db(0x21, 0x2F, 0x99, 0x3E, 0x01, 0xE0, 0x4F, 0x70)  # LUT attr
    a.db(0xAF, 0xE0, 0x4F)                  # restore tile bank
    a.db(0xC3, LAVA_OVERRIDE_ADDR & 0xFF, LAVA_OVERRIDE_ADDR >> 8)
    code = a.finish()
    assert len(code) <= 34
    return code


def build_lava_attr_scene_dispatcher() -> bytes:
    """Return NZ when a dungeon or animated arena needs atomic attributes.

    The caller handles Stage 1 locally. Stages 2-7 use the shared two-signature
    WRAM decider. Boss arenas $0C..$14 enter the bank-13 semantic cache: raw
    animation that requests an identical layout skips the redundant map
    publication, while every real layout change remains atomic. Other scenes
    return Z.

    The arena and neutral paths communicate directly through flags. The later
    dungeon core retains its existing FFE0 publication contract.
    """
    a = _Asm()
    a.db(
        0x06, 0x05,                        # skip Stage-1 post-copy service
        0xFA, 0x80, 0xD8,                  # A = D880
        0xD6, 0x03,                        # normalize dungeon $03..$08
        0xFE, 0x06,
    )
    a.jr(0x38, "later_dungeon")
    a.db(
        0xD6, 0x09,                        # normalize arena $0C..$14
        0xFE, 0x09,
    )
    a.jr(0x38, "arena")
    a.label("neutral")
    a.db(0xAF, 0xC9)                       # A=0/Z; pure tile copy
    a.label("arena")
    a.db(
        0xFE, CRYSTAL_DRAGON_SCENE - 0x0C,
        0xCA,
        LAVA_ATTR_STAGE7_RUNTIME_ADDR & 0xFF,
        LAVA_ATTR_STAGE7_RUNTIME_ADDR >> 8,
        0xC3,
        ARENA_ATTR_SEMANTIC_RUNTIME_ADDR & 0xFF,
        ARENA_ATTR_SEMANTIC_RUNTIME_ADDR >> 8,
    )
    a.label("later_dungeon")
    a.db(
        0xC3,
        LAVA_ATTR_STAGE7_RUNTIME_ADDR & 0xFF,
        LAVA_ATTR_STAGE7_RUNTIME_ADDR >> 8,
    )
    code = a.finish()
    assert len(code) == 30
    return code


def build_stage1_attr_runtime(always_stage1: bool = False) -> bytes:
    """Return NZ once per changed Stage-1 layout on each physical BG map.

    A room ID is too coarse: the native scroller republishes shifted packed
    layouts while FFBD remains unchanged. Caching only FFBD left attributes
    behind otherwise-correct tile IDs. SCX, the native vertical camera state
    DC02, and one receipt-proven raw cell identify every transition in the
    traced live/demo/low-health corpora without using a constantly changing
    frame counter. Rotating spike phases remain handled by the selective
    bank-14 row service.
    """
    a = _Asm()
    # Live Gargoyle combat uses D880=$0A while retaining the same Stage-1
    # scrolling tilemaps. Normalizing bit 3 keeps those map transitions on
    # the atomic attr path. The hidden splash entry is handled separately by
    # the bounded final-VBlank patch, before D880 publishes live Stage 1.
    a.db(0xFA, 0x80, 0xD8, 0xE6, 0xF7, 0xFE, 0x02)
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
        assert len(code) == 16
        return code
    a.db(
        0x16, 0xDF,                         # RST discriminator -> cache page
        0x7C,                               # A = destination H ($98/$9C)
        0xEE, 0xCB,                         # low cache = H XOR $CB
        0x5F,                               # E = $53/$57
        0xF0, 0x43, 0x4F,                  # C = native horizontal camera
        0xFA, 0x02, 0xDC, 0xA9, 0x4F,      # fold vertical camera DC02
    )
    for index, sample in enumerate(STAGE1_ATTR_TRANSITION_SAMPLES):
        source = 0xC1A0 + sample
        a.db(0xFA, source & 0xFF, source >> 8)
        a.db(0xA9)                          # fold rolling signature C
        if index + 1 < len(STAGE1_ATTR_TRANSITION_SAMPLES):
            a.db(0x4F)                      # C = rolling XOR
    a.db(0xE6, 0x7F, 0x3C, 0x4F)           # valid key range $01..$80
    a.db(
        0x1A, 0xB9, 0xC8,                  # same layout -> RET Z
        0x79, 0x12, 0xC9,                  # publish key; retain NZ
    )
    a.label("other_scene")
    a.db(
        0xC3,
        LAVA_ATTR_SCENE_DISPATCH_ADDR & 0xFF,
        LAVA_ATTR_SCENE_DISPATCH_ADDR >> 8,
    )
    code = a.finish()
    assert len(code) == 40
    assert STAGE1_ATTR_RUNTIME_ADDR + len(code) <= OAM_WRAM_END_ADDR
    return code


def build_stage1_hazard_row_helper() -> tuple[bytes, bytes]:
    """Stamp the live cylinder rows found in the completed packed source.

    The original fixed room-$02/$12 coordinates stop being valid during the
    north scroll: FFBD changes to $01 while the outgoing cylinder is still on
    screen, then the Gargoyle/miniboss cylinder appears at columns 5-14. Scan
    five discriminating cells per packed row instead. They identify the three
    reviewed layouts without a broad tile-family sweep: columns 0/1 select the
    nine-cell wall cylinder (eleven at the $03 seam), columns 4/5 select the
    shifted ceiling cylinder, and connector $6A at column 4 selects the ten-
    cell miniboss cylinder. Every matched row stays on immutable attribute
    $0F, including neutral 01-04 animation phases.

    The fixed-bank mapper supplies a synthetic return which is discarded at
    entry. DC0B identifies the just-completed physical map. The bounded bank-
    14 compiler walks 24 packed rows, writes only identified cylinder spans in
    HBlank, restores VBK0, and returns here before bank 1 is restored.
    """
    a = _Asm()
    exit_addr = STAGE1_HAZARD_ROW_HELPER_END - 5
    a.db(0xE1)                              # discard synthetic RST return
    a.db(
        0xFA, 0x80, 0xD8,
        0x47,                               # retain exact scene in B
        0xE6, 0xF7,                         # live miniboss $0A -> Stage 1 $02
        0xFE, 0x02,
    )
    a.db(0xC2, exit_addr & 0xFF, exit_addr >> 8)
    # The prerecorded route keeps DCFD clear and retains its independently
    # receipt-locked tile-ID attribute path. Only live play owns bank-1 art.
    a.db(0xFA, 0xFD, 0xDC, 0xB7)
    a.db(0xCA, exit_addr & 0xFF, exit_addr >> 8)
    # Only the two native cylinder rooms and their room-$07 transition can
    # contain one of the reviewed layouts during ordinary Stage 1. Room $01
    # is also used by the long, hazard-free opening route; rescanning it on
    # every atomic movement copy caused measurable north-travel lag. The exact
    # Gargoyle scene remains admitted regardless of room, while the outgoing
    # cylinder has already been stamped before stock publishes room $01.
    a.db(0x78, 0xFE, 0x0A)
    a.jr(0x28, "hazard_room")
    a.db(0xF0, 0xBD, 0xFE, 0x02)
    a.jr(0x28, "hazard_room")
    a.db(0xFE, 0x07)
    a.jr(0x28, "hazard_room")
    a.db(0xFE, 0x12)
    a.db(0xC2, exit_addr & 0xFF, exit_addr >> 8)
    a.label("hazard_room")
    a.db(
        0xFA,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR >> 8,
        0xE6, 0x03,                         # low bits own art-load count
        0xFE, STAGE1_HAZARD_BANK1_REFRESH_COUNT,
    )
    a.db(0xC2, exit_addr & 0xFF, exit_addr >> 8)
    # The bank-13 scene dispatcher used by the fixed mapper may clobber HL.
    # DC0B still identifies the just-completed physical map at this exact
    # post-copy point: bit 0 maps directly to destination H=$98/$9C.
    # DC0B is receipt-locked to 0/1 at every completed-map hook.
    a.db(0xFA, 0x0B, 0xDC, 0x87, 0x87, 0xEE, 0x98, 0x67)
    a.db(0x2E, 0x00)                       # completed map starts at xx00
    a.db(0xE5)                              # retain base for seam repair
    a.db(0xF3)                              # pure caller re-enables after RET
    a.db(0xAF, 0xE0, 0x4F)                 # destination classifier reads VBK0
    a.db(
        0xCD,
        STAGE1_HAZARD_SCANNER_FRONT_ADDR & 0xFF,
        STAGE1_HAZARD_SCANNER_FRONT_ADDR >> 8,
    )
    a.db(0xC3, exit_addr & 0xFF, exit_addr >> 8)
    assert (
        STAGE1_HAZARD_ROW_HELPER_ADDR + len(a.code)
        <= STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR
    )
    assert STAGE1_HAZARD_ROW_HELPER_ADDR + len(a.code) <= exit_addr
    a.db(bytes(exit_addr - STAGE1_HAZARD_ROW_HELPER_ADDR - len(a.code)))
    a.label("exit")
    a.db(0x3E, 0x01, 0xC3, 0x61, 0x00)     # restore bank 1; original RET
    main = a.finish()

    row = _Asm()
    # Fold $74-$79 onto $64-$69 and return Carry for all twelve tooth IDs.
    row.db(0xE6, 0xEF, 0xD6, 0x64, 0xFE, 0x06, 0xC9)
    assert STAGE1_HAZARD_ROW_WRITER_ADDR == (
        STAGE1_HAZARD_ROW_COMPILER_ADDR + len(row.code)
    )
    row.label("stat3")
    row.db(0x3E, 0x01, 0xE0, 0x4F)         # exact destination row -> VBK1
    row.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    row.jr(0x20, "stat3")
    row.label("stat0")
    row.db(0xF0, 0x41, 0xE6, 0x03)
    row.jr(0x20, "stat0")
    # E is the immutable attribute. The hazard scanner supplies $0F; the
    # transition-edge repair reuses the same HBlank-safe loop for a one-cell
    # YAML-LUT restoration without duplicating the LCD timing code.
    row.db(0x7B)                            # LD A,E
    row.label("cell")
    row.db(0x22, 0x0D)
    row.jr(0x20, "cell")
    row.db(0x79, 0xE0, 0x4F, 0xC9)          # C=0 -> restore VBK0; RET
    row_compiler = row.finish()
    assert (
        STAGE1_HAZARD_ROW_HELPER_ADDR + len(main)
        <= STAGE1_HAZARD_ROW_HELPER_END
    )
    assert (
        STAGE1_HAZARD_ROW_COMPILER_ADDR + len(row_compiler)
        <= STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR
    ), len(row_compiler)
    return main, row_compiler


def build_stage1_hazard_dynamic_scanner() -> tuple[bytes, bytes, bytes, bytes]:
    """Build the split packed-source scanner for the completed destination.

    VRAM tile reads are unavailable during part of the LCD scan, so using the
    destination map as the classifier made the selected span depend on LCD
    mode and left old $0F cells behind. The completed C1A0 packed source is
    stable here. Scan it while advancing the destination row in lockstep, then
    repair the three receipt-proven north-seam edge cells from the destination
    tile/LUT pair before returning.
    """
    front = _Asm()
    # Stable wall/ceiling cylinders occupy packed rows 0/3; the miniboss
    # translation moves them to rows 2/5. Their union is the six-row prefix,
    # so the remaining eighteen rows are proven classifier no-ops.
    front.db(0x11, 0xA0, 0xC1)             # DE = packed source row 0
    front.db(0x06, 0x06)                   # B = reviewed rows 0..5
    front.label("row")
    row_addr = STAGE1_HAZARD_SCANNER_FRONT_ADDR + len(front.code)
    front.db(0xC5, 0xD5, 0xE5)             # preserve row count/bases
    # Columns 0/1 identify the wall cylinder.
    front.db(0x1A, 0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
             STAGE1_HAZARD_ROW_FOLD_ADDR >> 8)
    front.db(0xDA,
             STAGE1_HAZARD_SCANNER_MIDDLE_ADDR & 0xFF,
             STAGE1_HAZARD_SCANNER_MIDDLE_ADDR >> 8)
    front.db(0x13, 0x1A, 0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
             STAGE1_HAZARD_ROW_FOLD_ADDR >> 8)
    front.db(0xDA, STAGE1_HAZARD_SCANNER_SEAM_ADDR & 0xFF,
             STAGE1_HAZARD_SCANNER_SEAM_ADDR >> 8)
    # Column 4's $6A connector identifies the miniboss row. A tooth at
    # columns 4/5 identifies the shifted ceiling cylinder.
    front.db(0x13, 0x13, 0x13, 0x1A, 0xFE, 0x6A)
    front.db(0xCA,
             (STAGE1_HAZARD_SCANNER_MIDDLE_ADDR + 13) & 0xFF,
             (STAGE1_HAZARD_SCANNER_MIDDLE_ADDR + 13) >> 8)
    front.db(0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
             STAGE1_HAZARD_ROW_FOLD_ADDR >> 8)
    front.db(0xDA,
             STAGE1_HAZARD_START4_HELPER_ADDR & 0xFF,
             STAGE1_HAZARD_START4_HELPER_ADDR >> 8)
    front.db(0x13, 0x1A, 0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
             STAGE1_HAZARD_ROW_FOLD_ADDR >> 8)
    front.db(0xDA,
             STAGE1_HAZARD_START4_COL5_ADDR & 0xFF,
             STAGE1_HAZARD_START4_COL5_ADDR >> 8)
    # A tooth at column 6 with none at 4/5 is the alternating neutral-gap
    # phase. Tail-enter its one-HBlank sparse repair with DE on source col 6
    # and HL still on the exact destination row base.
    front.db(0x13)
    front.db(0xC3, STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR & 0xFF,
             STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR >> 8)
    front_code = front.finish()
    assert len(front_code) == 50
    assert STAGE1_HAZARD_SCANNER_FRONT_ADDR + len(front_code) <= 0x61EF

    middle = _Asm()
    middle.label("start0")
    middle.db(0x0E, 0x09, 0xFA, 0x0E, 0xDC, 0xE6, 0x01)
    middle.jr(0x28, "write")
    middle.db(0x0C, 0x0C)                  # source seam reaches column 10
    middle.jr(0x18, "write")
    assert len(middle.code) == 13
    middle.label("start5")
    middle.db(0x0E, 0x0A)
    middle.label("offset")
    middle.db(0x79, 0xD6, 0x05, 0x85, 0x6F)  # L += C-5
    middle.label("write")
    middle.db(0x1E, 0x0F)                  # E = BG7 + pattern bank 1
    middle.db(0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
              STAGE1_HAZARD_ROW_WRITER_ADDR >> 8)
    middle.db(0xC3, STAGE1_HAZARD_SCANNER_TAIL_ADDR & 0xFF,
              STAGE1_HAZARD_SCANNER_TAIL_ADDR >> 8)
    middle_code = middle.finish()
    assert len(middle_code) == 28
    assert STAGE1_HAZARD_SCANNER_MIDDLE_ADDR + len(middle_code) <= 0x61AF

    tail = _Asm()
    tail.db(0xE1)                          # restore destination row-base HL
    tail.label("common")
    tail.db(0xD1, 0xC1)                   # restore source DE / row count
    tail.db(0x7D, 0xC6, 0x20, 0x6F)
    tail.jr(0x30, "dest_ready")
    tail.db(0x24)
    tail.label("dest_ready")
    tail.db(0x7B, 0xC6, 0x18, 0x5F)
    tail.jr(0x30, "source_ready")
    tail.db(0x14)
    tail.label("source_ready")
    tail.db(0x05)
    tail.db(0xC2, row_addr & 0xFF, row_addr >> 8)
    tail.db(0xC3, STAGE1_HAZARD_TRANSITION_REPAIR_ADDR & 0xFF,
            STAGE1_HAZARD_TRANSITION_REPAIR_ADDR >> 8)
    tail_code = tail.finish()
    assert len(tail_code) == 24
    assert STAGE1_HAZARD_SCANNER_TAIL_ADDR + len(tail_code) <= 0x6210

    seam = bytes([
        0x7B, 0xC6, 0x09, 0x5F,             # source col 1 -> col 10
        0x30, 0x01, 0x14,
        0x1A,
        0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_FOLD_ADDR >> 8,
        0xD2, STAGE1_HAZARD_SCANNER_MIDDLE_ADDR & 0xFF,
        STAGE1_HAZARD_SCANNER_MIDDLE_ADDR >> 8,
        0x0E, 0x0B,
        0xC3,
        (STAGE1_HAZARD_SCANNER_MIDDLE_ADDR + 20) & 0xFF,
        (STAGE1_HAZARD_SCANNER_MIDDLE_ADDR + 20) >> 8,
    ])
    assert len(seam) == 19
    assert STAGE1_HAZARD_SCANNER_SEAM_ADDR + len(seam) <= 0x6CFC
    return front_code, middle_code, tail_code, seam


def build_stage1_hazard_start4_edge_helpers() -> tuple[bytes, bytes]:
    """Publish start-4 spans, then restore their trailing cell from its tile.

    The nine-cell span ends at column 12. Column 4 tooth phases leave a neutral
    palette-0 cell at column 13; column 5 tooth phases leave the final low-bank
    palette-7 tooth there. The lower ceiling row instead ends against its
    permanent tile-$63 metal support at map column 13, so that exact $xAD cell
    must stay on YAML BG6 in both phases. Two four-byte entries encode the
    phase discriminator in D before sharing the HBlank writer; the edge tail
    applies the one reviewed support exception without an unsafe destination
    VRAM read. The saved source DE is restored by the scanner tail.
    """
    start4 = bytes([
        0x16, 0x00,                         # column-4 entry: edge BG0
        0x18, 0x02,
        0x16, 0x07,                         # column-5 entry: edge BG7
        0x0E, 0x09,
        0x7D, 0xC6, 0x04, 0x6F,
        0x1E, 0x0F,
        0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_WRITER_ADDR >> 8,
        0xC3, STAGE1_HAZARD_START4_EDGE_ADDR & 0xFF,
        STAGE1_HAZARD_START4_EDGE_ADDR >> 8,
    ])
    edge = bytes([
        0x7D, 0xFE, 0xAD,                   # lower edge is tile-$63 support
        0x20, 0x02,
        0x16, 0x06,                         # permanent YAML metallic BG6
        0x5A,                               # E = support/phase edge attr
        0x0C,                               # C=0 after row writer -> one cell
        0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_WRITER_ADDR >> 8,
        0xC3, STAGE1_HAZARD_SCANNER_TAIL_ADDR & 0xFF,
        STAGE1_HAZARD_SCANNER_TAIL_ADDR >> 8,
    ])
    assert len(start4) <= 23, len(start4)
    assert len(edge) == 15, len(edge)
    return start4, edge


def build_stage1_hazard_transition_repair() -> bytes:
    """Restore the three north-seam cells that change semantic ownership.

    The source and visible destination intentionally overlap for 21 frames as
    Stage 1 scrolls from room $12 into the Gargoyle approach. Two trailing
    cells cease to belong to the outgoing cylinder and one leading cell joins
    the translated row. Rebuild those exact cells from the destination tile
    and YAML LUT after every completed-map stamp. This is bounded to three
    HBlank writes, with no broad row repaint or LCD-mode-dependent classifier.
    """
    a = _Asm()
    # The scanner tail jumps here with its CALL return above the completed-map
    # base saved by the row helper. Recover D=$98/$9C without borrowing native
    # WRAM, then put the scanner return back for this routine's final RET.
    a.db(0xC1, 0xD1, 0xC5)                 # POP BC; POP DE; PUSH BC
    # The rotating cylinder remains visible while Stage 1 hands off from the
    # ordinary gameplay scene ($02) to the Gargoyle/miniboss music scene
    # ($0A).  The row publisher deliberately keeps running across that handoff,
    # so its three bounded seam repairs must do the same; otherwise animated
    # teeth are refreshed while their connector attributes retain the outgoing
    # map's palette/bank bits.  Reject every other scene, but admit both exact
    # Stage-1 identities.  The callee remains independently room-$12 gated.
    # $02 and $0A differ only by bit 3; folding that bit is both exact for
    # this pair and keeps the repair within its audited 65-byte cave.
    a.db(0xFA, 0x80, 0xD8, 0xE6, 0xF7, 0xFE, 0x02)
    a.db(0xC0)                              # RET NZ: unrelated scene
    a.db(
        0xCD,
        STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR & 0xFF,
        STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR >> 8,
    )
    # Rows $10/$13 map to destination offset $20B/$20C at the scroll seam.
    # Both are neutral palette-0 cells in room $01, so publish the adjacent
    # pair in one HBlank instead of waiting once per cell. The room byte leads
    # the visible scroll by one map; packed row-$10 column 1 is the exact seam
    # discriminator that prevents clearing the still-visible shifted span.
    a.db(0xFA, 0x21, 0xC3)
    a.db(0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
         STAGE1_HAZARD_ROW_FOLD_ADDR >> 8)
    a.jr(0x30, "after_pair")
    a.db(0x7A, 0xC6, 0x02, 0x67, 0x2E, 0x0B)
    a.db(0x1E, 0x00, 0x0E, 0x02)
    a.db(0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
         STAGE1_HAZARD_ROW_WRITER_ADDR >> 8)
    a.label("after_pair")
    # Offset $24A is bank 1 only while its actual destination tile is a tooth.
    # Packed row-$12 column 10 is the synchronized semantic owner: a tooth
    # requests $0F, neutral $01 requests BG0, and every other value skips the
    # repair. Never classify the destination VRAM here; it can be unreadable
    # while LCD mode 3 is active immediately before the safe writer waits.
    a.db(0xFA, 0x5A, 0xC3, 0xFE, 0x01)
    a.jr(0x28, "neutral")
    a.db(0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
         STAGE1_HAZARD_ROW_FOLD_ADDR >> 8)
    a.jr(0x30, "row0")
    a.db(0x1E, 0x0F)
    a.jr(0x18, "publish")
    a.label("neutral")
    a.db(0x1E, 0x00)
    a.label("publish")
    a.db(0x7A, 0xC6, 0x02, 0x67, 0x2E, 0x4A)
    a.db(0x0E, 0x01)
    a.db(0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
         STAGE1_HAZARD_ROW_WRITER_ADDR >> 8)
    a.label("row0")
    a.label("done")
    a.db(0xC9)
    code = a.finish()
    assert len(code) <= 65, len(code)
    return code


def build_stage1_hazard_room12_wall_repair() -> bytes:
    """Restore four fixed metallic wall cells missed by the atomic copier.

    The room-$12 fixture proves source row 8/column 16 and row 12/column 13
    reach both physical tile maps while their paired attributes remain BG0;
    its alternate packed row also reaches destination $1AD. The low-health/
    miniboss handoff adds the translated $20D occurrence. They are permanent
    wall tiles $16/$25/$35, all YAML BG6. D supplies the completed map's base
    page; reuse the reviewed HBlank writer without touching any animated
    hazard coordinate.
    """
    code = bytes([
        0xF0, 0xBD, 0xFE, 0x12, 0xC0,      # exact spike room only
        0x62, 0x24,                         # H = map base + 1
        0x2E, 0x10,
        0x1E, 0x06, 0x0E, 0x01,
        0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_WRITER_ADDR >> 8,
        0x2E, 0x8D, 0x0C,
        0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_WRITER_ADDR >> 8,
        0x2E, 0xAD, 0x0C,
        0xCD, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_WRITER_ADDR >> 8,
        0x24, 0x2E, 0x0D, 0x0C,
        0xC3, STAGE1_HAZARD_ROW_WRITER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_WRITER_ADDR >> 8,
    ])
    assert len(code) == 35
    assert STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR + len(code) <= 0x6F8B
    return code


def build_stage1_hazard_row0_transition_repair(
) -> tuple[bytes, bytes, bytes]:
    """Clear six neutral gaps in the translated alternating cylinder phase.

    The caller supplies DE on packed-source column 6 and HL on the matching
    destination row base. If column 6 is not a tooth, resume the normal tail.
    Otherwise the LUT publisher has already restored the intervening tooth
    cells to palette 7, while neutral columns 4/5/7/9/11/13 can retain the
    outgoing cylinder's bank bit. Clear those six exact cells together in one
    HBlank. Because HL is row-relative, this follows row 0 to row 2 (and future
    translations) instead of hard-coding the pre-miniboss screen coordinate.
    """
    front = bytes([
        0x1A,
        0xCD, STAGE1_HAZARD_ROW_FOLD_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_FOLD_ADDR >> 8,
        0xD2, STAGE1_HAZARD_SCANNER_TAIL_ADDR & 0xFF,
        STAGE1_HAZARD_SCANNER_TAIL_ADDR >> 8,
        0x7D, 0xC6, 0x04, 0x6F,             # destination column 4
        0x06, 0x04,                         # four tooth/gap pairs
        0xC3, STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR & 0xFF,
        STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR >> 8,
    ])
    middle = bytes([
        0x3E, 0x01, 0xE0, 0x4F,             # VBK1
        0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03,
        0x20, 0xF8,                         # wait until LCD mode 3
        0xF0, 0x41,                         # first mode-0 poll
        0xC3, STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR & 0xFF,
        STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR >> 8,
    ])
    wait0_addr = STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR + 12
    wait0_pc = STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR + 4
    wait0_delta = wait0_addr - wait0_pc
    assert -128 <= wait0_delta <= 127
    tail = bytes([
        0xE6, 0x03, 0x20, wait0_delta & 0xFF, # then enter HBlank
        0xAF,
        0x22, 0x22,                         # columns 4,5
        0x3E, 0x0F, 0x22,                   # tooth: 6/8/10/12
        0xAF, 0x22,                         # neutral: 7/9/11/13
        0x05, 0x20, 0xF8,
        0xE0, 0x4F,                         # A=0 -> VBK0
        0xC3, STAGE1_HAZARD_SCANNER_TAIL_ADDR & 0xFF,
        STAGE1_HAZARD_SCANNER_TAIL_ADDR >> 8,
    ])
    assert len(front) <= 17, len(front)
    assert len(middle) <= 22, len(middle)
    assert len(tail) <= 20, len(tail)
    return front, middle, tail


def build_stage1_hazard_bank1_loader() -> bytes:
    """Gate the immutable tooth-art load and enter its bank-14 body."""
    a = _Asm()
    a.db(
        0xFA,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR >> 8,
        0xE6, 0x03,                         # high bits cache pure map stamps
        0xFE, STAGE1_HAZARD_BANK1_REFRESH_COUNT,
        0xC8,                               # immutable art already loaded
    )
    a.db(0xFA, 0x80, 0xD8, 0xE6, 0xF7, 0xFE, 0x02, 0xC0)
    a.db(
        0x01,
        STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR >> 8,
        0xC5,                               # mapper RET -> bank-14 body
        0x3E, 0x0E,
        0xC3, 0x61, 0x00,
    )
    a.db(0xC9)                              # inactive wrapper return
    code = a.finish()
    assert (
        STAGE1_HAZARD_BANK1_LOADER_ADDR + len(code)
        <= ATTRACT_PICKUP_SWEEP_HELPER_ADDR
    )
    return code


def build_stage1_entry_patch_gate() -> bytes:
    """Arm every stage prelude and patch Stage 1 at splash handoff."""
    a = _Asm()
    a.db(
        0xF0, 0xB7,
        # Every valid stage index is nonzero. Natural level-select entry can
        # otherwise retain cold HRAM zero and never run its first scene/table
        # prelude (most visibly losing the Stage 5/7 lava attributes).
        0xE0, ATTRACT_PRELUDE_FLAG_HRAM,
        0xFE, 0x02,                         # FFB7 already owns Stage 1?
    )
    a.jr(0x20, "not_ready")
    a.db(0xC3, STAGE1_ENTRY_PATCH_BODY_ADDR & 0xFF,
         STAGE1_ENTRY_PATCH_BODY_ADDR >> 8)
    a.label("not_ready")
    a.db(0x37, 0xC9)                       # retain splash skip via Carry
    code = a.finish()
    assert STAGE1_ENTRY_PATCH_GATE_ADDR + len(code) <= STALE_WINDOW_CLEANUP_ADDR
    return code


def build_stage1_entry_attr_patch(
    stage1_lut: bytes,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Publish twenty chromatic first-room cells before D880 becomes $02.

    The final STAGE splash VBlank exposes the completed Stage-1 scene in FFB7
    one frame before the main loop mirrors it into D880. The normal atomic map
    copy consequently begins one frame after the first gameplay raster. The
    upper eleven cells cover the first visible pair; the lower nine cover the
    alternate $9800 map exposed when LCDC begins double-buffering after the
    initial $9C00-only sweep. Compiling both reviewed sets from the same YAML
    LUT makes the hidden patch deterministic without repainting a later room.
    """
    assert len(stage1_lut) == 256
    bg5_tiles = (0x6E, 0x7D, 0x6D, 0x7E)
    bg6_tiles = (0x6F, 0x45, 0x54, 0x55, 0x7F, 0x54, 0x55)
    bg5 = {stage1_lut[tile] & 0x07 for tile in bg5_tiles}
    bg6 = {stage1_lut[tile] & 0x07 for tile in bg6_tiles}
    assert bg5 == {5} and bg6 == {6}, (bg5, bg6)
    assert stage1_lut[0xCF] == stage1_lut[0xB9] == 5
    assert stage1_lut[0xA5] == 4 and stage1_lut[0x42] == 6

    body = bytes([
        0x3E, 0x01, 0xE0, 0x4F,             # VBK1 attributes
        0x21, 0x82, 0x98, 0x3E, 0x05, 0x22, 0x77,
        0x2E, 0x89, 0x77,
        0x2E, 0xA2, 0x77,
        0x3E, 0x06,
        0xC3, STAGE1_ENTRY_PATCH_TAIL_ADDR & 0xFF,
        STAGE1_ENTRY_PATCH_TAIL_ADDR >> 8,
    ])
    tail = bytes([
        0x2E, 0x8B, 0x77,
        0x2E, 0x91, 0x77,
        0x2E, 0xA4, 0x22, 0x77,
        0x2E, 0xAB, 0x77,
        0xC3, STAGE1_ENTRY_PATCH_FINISH_ADDR & 0xFF,
        STAGE1_ENTRY_PATCH_FINISH_ADDR >> 8,
    ])
    finish = bytes([
        0x2E, 0xB0, 0x22, 0x77,
        # A still holds palette 6.  Arm the normal prelude on the guaranteed
        # final Stage-1 splash VBlank, covering both live and prerecorded
        # entry without perturbing title/spotlight/Gargoyle cadence.
        0xE0, ATTRACT_PRELUDE_FLAG_HRAM,
        # The stock splash can leave the scene cache already equal to $02.
        # Force exactly one real Stage-1 scene transition so the first
        # prelude selects the active YAML table and applies the demo/live
        # flag policy below.
        0x3E, 0xFF,
        0xEA, SCENE_CACHE_ADDR & 0xFF, SCENE_CACHE_ADDR >> 8,
        0xC3, STAGE1_ENTRY_PATCH_LOWER_ADDR & 0xFF,
        STAGE1_ENTRY_PATCH_LOWER_ADDR >> 8,
    ])
    lower = bytes([
        0x3E, 0x05,
        0x21, 0x18, 0x99,
        0x22, 0x23, 0x22, 0x23, 0x22, 0x23, 0x77,
        0x2E, 0x78, 0x22, 0x23, 0x77,
        0x2E, 0x98, 0x77,
        0x2C, 0x2C, 0x3E, 0x04, 0x77,
        0x2C, 0x2C, 0x3E, 0x06, 0x77,
        0xAF, 0xE0, 0x4F,                   # restore VBK0
        0x37, 0xC9,                         # splash caller skips colorizer
    ])
    assert len(body) == 22
    assert len(tail) <= 0x6C40 - STAGE1_ENTRY_PATCH_TAIL_ADDR
    assert len(finish) <= COLORIZE_PRELUDE_ADDR - STAGE1_ENTRY_PATCH_FINISH_ADDR
    assert len(lower) == 35
    assert STAGE1_ENTRY_PATCH_LOWER_ADDR + len(lower) <= 0x562E
    return body, tail, finish, lower


def build_cold_stage1_sweep_arm() -> tuple[bytes, bytes]:
    """Promote only an art-complete cold Stage-1 attribute repair.

    Scene entry publishes dormant marker $7F after the native room rearm. The
    bank-1 GDMA chain reaches this helper after each completed upload; only
    load index 3 may promote exactly $7F to $92. The sweep finishes at $80,
    while legacy states initialize these new bytes to $FF, so neither later
    hazard/miniboss refreshes nor loaded fixtures can restart the broad sweep.
    """
    front = bytes([
        0xFA,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR >> 8,
        0xFE, STAGE1_HAZARD_BANK1_REFRESH_COUNT,
        0xC0,                               # RET NZ: upload 1/2 or legacy FF
        0x21, BG_SWEEP_COUNT_ADDR & 0xFF, BG_SWEEP_COUNT_ADDR >> 8,
        0xC3,
        COLD_STAGE1_SWEEP_ARM_TAIL_ADDR & 0xFF,
        COLD_STAGE1_SWEEP_ARM_TAIL_ADDR >> 8,
    ])
    tail = bytes([
        0x7E,                               # A = current sweep marker
        0xFE, 0x7F,                         # exact cold-entry wait marker?
        0xC0,                               # RET NZ
        0x36, 0x92,                         # arm eighteen visible rows
        0xC9,
    ])
    assert COLD_STAGE1_SWEEP_ARM_ADDR + len(front) <= CONDITIONAL_PALETTE_ADDR
    assert (
        COLD_STAGE1_SWEEP_ARM_TAIL_ADDR + len(tail)
        <= LAVA_ATTR_ROOM_MATCH_ADDR
    )
    return front, tail


def build_stage1_hazard_bank1_bank14_loader() -> bytes:
    """Load all immutable tooth art, then enter the bank-14 GDMA chain."""
    code = bytes([
        0x21,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_LOAD_INDEX_ADDR >> 8,
        0x34,                               # count this complete DI/GDMA pass
        0x3E, 0x01, 0xE0, 0x4F,             # VBK1 destination
        0x3E, STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR >> 8, 0xE0, 0x51,
        0x3E, STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR & 0xF0, 0xE0, 0x52,
        0x3E, 0x90, 0xE0, 0x53,
        0x3E, 0x10, 0xE0, 0x54,
        0xC3,
        STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR >> 8,
    ])
    assert len(code) == 27
    assert (
        STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR + len(code)
        <= STAGE1_HAZARD_ROOM_DISPATCH_ADDR
    )
    return code


def build_stage1_hazard_bank1_copy_routines(
) -> tuple[bytes, bytes, bytes, bytes]:
    """Chain neutral64 -> low-tooth96 -> high-tooth96, then restore."""
    bank14 = bytes([
        0x3E, 0x03, 0xE0, 0x55,             # neutral tiles 01-04
        0x3E, 0x56, 0xE0, 0x51,
        0x3E, 0x40, 0xE0, 0x52,
        0x3E, 0x96, 0xE0, 0x53,
        0x3E, 0x40, 0xE0, 0x54,
        0x01,
        STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR >> 8,
        0xC5, 0x3E, 0x07, 0xC3, 0x61, 0x00,
    ])
    bank7 = bytes([
        0x3E, 0x05, 0xE0, 0x55,             # tooth tiles 64-69
        0x3E, 0x57, 0xE0, 0x51,
        0x3E, 0x40, 0xE0, 0x52,
        0xC3,
        STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR >> 8,
    ])
    bank7_middle = bytes([
        0x3E, 0x97, 0xE0, 0x53,
        0x3E, 0x40, 0xE0, 0x54,
        0x3E, 0x05, 0xE0, 0x55,             # final tooth GDMA completes here
        0xC3,
        STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR >> 8,
    ])
    bank7_tail = bytes([
        0x01,
        COLD_STAGE1_SWEEP_ARM_ADDR & 0xFF,
        COLD_STAGE1_SWEEP_ARM_ADDR >> 8,
        0xC5,                               # mapper RET -> cold-arm gate
        0xAF, 0xE0, 0x4F,                   # restore native tile-map bank
        0x3E, 0x0D, 0xC3, 0x61, 0x00,       # bank13; arm RET -> wrapper
    ])
    assert (
        len(bank14), len(bank7), len(bank7_middle), len(bank7_tail)
    ) == (29, 15, 15, 12)
    return bank14, bank7, bank7_middle, bank7_tail


def build_stage1_hazard_bank1_neutral_art(rom: bytes) -> bytes:
    """Build the BG7-safe no-tooth patterns used only by immutable cells."""
    return b"".join(
        _remap_2bpp_indices(
            rom[
                STAGE1_LOW_TILE_GFX_OFFSET + tile * 16:
                STAGE1_LOW_TILE_GFX_OFFSET + (tile + 1) * 16
            ],
            (0, 1, 1, 3),
        )
        for tile in (0x01, 0x02, 0x03, 0x04)
    )


def build_stage1_hazard_room_dispatcher() -> bytes:
    """Normalize both Stage-1 completed-copy stack contracts, then scan.

    The two completed-copy routes reach this selector with different stack
    ownership. Bit 7 of B identifies the route whose synthetic return must be
    discarded by the row helper itself. The other route discards it here and
    enters immediately after the helper's POP. A later Gargoyle cache replaced
    this distinction and corrupted bank-1 art/spike semantics after miniboss
    and low-health transitions.

    The fixed-bank pure-copy gate admits only Stage 1 and its demo/miniboss
    alias into bank 14, so this banked entry no longer needs to inspect arena
    scenes or rewrite a synthetic return. Boss/arena atomic publications map
    bank 13 directly from their separate fixed stub.
    """
    code = bytes([
        0xCB, 0x78,                         # BIT 7,B: helper owns frame?
        0xC2,
        STAGE1_HAZARD_ROW_HELPER_ADDR & 0xFF,
        STAGE1_HAZARD_ROW_HELPER_ADDR >> 8,
        0xE1,                               # discard synthetic mapper return
        0xC3,
        (STAGE1_HAZARD_ROW_HELPER_ADDR + 1) & 0xFF,
        (STAGE1_HAZARD_ROW_HELPER_ADDR + 1) >> 8,
    ])
    assert len(code) == 9
    return code


def build_stage1_atomic_setup() -> bytes:
    """Retain the exact destination and admit Timer while source is live."""
    code = bytes([
        0x7C,                               # A = native destination H
        0xE0, ATOMIC_DEST_H_HRAM,           # retain across compile's H use
        0xF3,                               # DI before changing IE
        0xF0, 0xFF,                         # A = caller's IE
        0xEA, STAGE1_IE_CACHE_ADDR & 0xFF,
        STAGE1_IE_CACHE_ADDR >> 8,
        0xE6, 0x04,                         # retain Timer only
        0xE0, 0xFF,                         # publish bounded in-copy IE
        0xC9,
    ])
    assert len(code) == 14
    return code


def build_stage1_atomic_wrap() -> bytes:
    """Map later dungeons/arenas, then restore IE and Ted's AF/IME contract.

    The inline atomic completion reloads D880 immediately before this call.
    The fixed selector returns for title/Stage 1 below $03 and maps later
    dungeons plus boss arenas directly to bank 13, preventing any transient
    bank-14 entry while retaining their post-copy completion contract.
    """
    code = bytes([
        0xFA, 0x80, 0xD8,                   # exact scene, not stale A=$01
        0xCD,
        STAGE1_HAZARD_BANK0_MAP_ADDR & 0xFF,
        STAGE1_HAZARD_BANK0_MAP_ADDR >> 8,
        0xC3,
        STAGE1_ATOMIC_WRAP_TAIL_ADDR & 0xFF,
        STAGE1_ATOMIC_WRAP_TAIL_ADDR >> 8,
        0x00, 0x00, 0x00,                  # fixed-cave padding, unreachable
    ])
    assert len(code) == 12
    return code


def build_stage1_atomic_wrap_tail() -> bytes:
    """Restore the exact pre-existing interrupt/AF completion contract."""
    code = bytes([
        0xFA, STAGE1_IE_CACHE_ADDR & 0xFF,
        STAGE1_IE_CACHE_ADDR >> 8,
        0xE0, 0xFF,                         # restore caller's IE
        0x3E, 0x01,
        0xBF,                               # A=$01, F=$C0
        0xD9,                               # RETI; IME active immediately
    ])
    assert len(code) == 9
    return code


def build_stage1_atomic_attr_stack_vector() -> bytes:
    """Dispatch the shared RST to layout decision or arena geometry.

    The map-decision caller deliberately presets D=$FF. The atomic stack hook
    runs later with D=$C1-$C3 as its packed-source page. Eight vector bytes are
    therefore enough to route both callers without another fixed-bank cave.
    """
    code = bytes([
        0x7A, 0x3C,                         # A=D; INC A ($FF -> zero)
        0xCA,
        STAGE1_ATTR_RUNTIME_ADDR & 0xFF,
        STAGE1_ATTR_RUNTIME_ADDR >> 8,
        0xC3,
        ARENA_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR & 0xFF,
        ARENA_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR >> 8,
    ])
    assert len(code) == 8
    return code


def build_arena_atomic_attr_stack_helper() -> bytes:
    """Compact WRAM dispatch to Ted or Shalamar's bounded sanitizer."""
    a = _Asm()
    # Never infer an arena from FFBA alone.  Cold Stage 1 legitimately carries
    # the Ted selector value ($04) while publishing its first room, so that
    # shortcut routed the live dungeon through the Ted sanitizer and left the
    # initial map unpublished.  Ambiguous pre-scene groups now retain their
    # native three source IDs; only persistent arena scenes may sanitize.
    a.db(0xFA, 0x80, 0xD8, 0xFE, 0x10)
    a.jr(0x28, "ted")
    a.db(0xFE, 0x0C)
    a.jr(0x20, "native")
    # E=$A0 selects the three possible page-aligned Shalamar checkpoints;
    # the banked main rejects D!=$C1 before doing the whole-map sweep.
    a.db(0x7B, 0xFE, 0xA0)
    a.jr(0x20, "native")
    # Fall through to the shared bank-13 mapper.
    a.label("ted")
    # Ted needs the bounded per-group geometry classifier.  Returning here
    # neutralized only its attributes and left rejected staging tile IDs in
    # the published map, producing obvious gray boss fragments at the arena
    # edges.
    a.label("bank13")
    a.db(0x3E, 0x0D, 0xC3,
         LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR & 0xFF,
         LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR >> 8)
    a.label("native")
    # The copier normally has bank 1 selected. $61B0 is bank-13 ROM, not a
    # fixed address: the former direct JP landed in bank-1 data and stranded
    # cold Stage 1 before its first live map. This helper executes from WRAM,
    # so switch around the materializer while preserving BC/DE/HL and stack.
    a.db(0x3E, 0x0D, 0xCD, 0x61, 0x00)
    a.db(0xCD, TED_TILE_COMMIT_RUNTIME_ADDR & 0xFF,
         TED_TILE_COMMIT_RUNTIME_ADDR >> 8)
    a.db(0x3E, 0x01, 0xCD, 0x61, 0x00, 0xC9)
    code = a.finish()
    assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return code


def build_ted_source_sanitizer_fragments() -> dict[int, bytes]:
    """Neutralize only the three Ted cells being published this group.

    Ted's C1A0 workspace contains future shifted poses.  Sweeping all 24x24
    cells freezes its native state machine.  The atomic copier already visits
    every visible group, so classify those three source cells against their
    physical destination and leave every not-yet-published staging cell alone.
    """
    main = _Asm()
    main.db(
        0xC5, 0xD5, 0xE5,
        0x7A, 0xFE, 0xC1,
    )
    main.jr(0x20, "ready")
    main.db(0x7B, 0xFE, 0xA0)
    main.jr(0x20, "ready")
    main.db(0xAF, 0xE0, TED_SANITIZER_EXPECTED_HRAM)
    main.label("ready")
    main.db(0x06, 0x03)
    main.label("cell")
    main.db(0xCD, TED_SANITIZER_CLASSIFY_ADDR & 0xFF,
            TED_SANITIZER_CLASSIFY_ADDR >> 8, 0x13, 0x23, 0x05)
    main.jr(0x20, "cell")
    main.db(0xE1, 0xD1, 0xC1)
    # This is the sole post-stack visit. The first three cells were classified
    # before the whole source sweep, so neutralize their pending attrs; every
    # later group observes the already-sanitized source.
    main.db(0xF8, 0x05, 0xAF, 0x22, 0x23, 0x22, 0x23, 0x77)
    main.db(0x3E, 0x01, 0xC9)

    classify = _Asm()
    classify.db(0x1A, 0xFE, 0x02, 0xD8, 0xFE, 0x77)
    classify.jr(0x38, "body_tile")
    classify.db(0xCD, TED_SANITIZER_SPECIAL_ADDR & 0xFF,
                TED_SANITIZER_SPECIAL_ADDR >> 8, 0xC0)
    classify.label("body_tile")
    classify.db(0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xB7)
    classify.db(0xC2, TED_SANITIZER_ACTIVE_ADDR & 0xFF,
                TED_SANITIZER_ACTIVE_ADDR >> 8)
    classify.db(0xC3, TED_SANITIZER_ANCHOR_ADDR & 0xFF,
                TED_SANITIZER_ANCHOR_ADDR >> 8)

    anchor = _Asm()
    anchor.db(0x1A, 0xFE, 0x02)
    anchor.db(0xC2, TED_SANITIZER_CLEAR_ADDR & 0xFF,
              TED_SANITIZER_CLEAR_ADDR >> 8)
    anchor.db(0xCD, TED_SANITIZER_CROWN_ADDR & 0xFF,
              TED_SANITIZER_CROWN_ADDR >> 8)
    anchor.db(0xC2, TED_SANITIZER_CLEAR_ADDR & 0xFF,
              TED_SANITIZER_CLEAR_ADDR >> 8)
    anchor.db(0xC3, TED_SANITIZER_ANCHOR_PACK_ADDR & 0xFF,
              TED_SANITIZER_ANCHOR_PACK_ADDR >> 8)

    anchor_pack = _Asm()
    # Pack physical anchor row/4 and column/4 into six bits, plus one.
    anchor_pack.db(0x7C, 0xE6, 0x03, 0x07, 0x07, 0x07, 0x4F)
    anchor_pack.db(0x7D, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0xE6, 0x07, 0x81)
    anchor_pack.db(0xE6, 0x1C, 0x07, 0x4F)
    anchor_pack.db(0x7D, 0x0F, 0x0F, 0xE6, 0x07, 0xB1, 0x3C)
    anchor_pack.db(0xE0, TED_SANITIZER_EXPECTED_HRAM, 0xC9)

    crown = _Asm()
    crown.db(0xE5, 0x62, 0x6B, 0x23)
    # Every native pose retains the leading $02,$03 pair. The late wrap pose
    # deliberately replaces $04-$06 with $24,$25 and another partial crown;
    # requiring all five numbered cells loses its anchor and publishes a
    # composite map near frame 900.
    for expected in (3,):
        crown.db(0x2A, 0xFE, expected)
        crown.jr(0x20, "bad")
    crown.db(0xE1, 0xAF, 0xC9)
    crown.label("bad")
    crown.db(0xE1, 0x3E, 0x01, 0xB7, 0xC9)

    active = _Asm()
    active.db(0xC5, 0xD5, 0xE5, 0x45)
    active.db(0xF0, TED_SANITIZER_EXPECTED_HRAM, 0x3D, 0x4F)
    # D = current physical row = ((H&3)*8) | (L>>5).
    active.db(0x7C, 0xE6, 0x03, 0x07, 0x07, 0x07, 0x57)
    active.db(0x7D, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0xE6, 0x07, 0x82, 0x57)
    active.db(0xC3, TED_SANITIZER_GEOMETRY_CONT_ADDR & 0xFF,
              TED_SANITIZER_GEOMETRY_CONT_ADDR >> 8)

    geometry_cont = _Asm()
    # Relative row selects the two-byte [min+4,max+4) silhouette span.
    geometry_cont.db(0x79, 0xE6, 0x38, 0x0F, 0x5F)
    geometry_cont.db(0x7A, 0x93, 0xE6, 0x1F, 0xFE, 0x0E)
    geometry_cont.db(0xD2, (TED_SANITIZER_COMPARE_ADDR + 24) & 0xFF,
                     (TED_SANITIZER_COMPARE_ADDR + 24) >> 8)
    geometry_cont.db(0x87, 0x5F, 0x16, 0x00)
    geometry_cont.db(0x21, TED_SANITIZER_ROW_TABLE_ADDR & 0xFF,
                     TED_SANITIZER_ROW_TABLE_ADDR >> 8, 0x19)
    geometry_cont.db(0xC3, TED_SANITIZER_COMPARE_ADDR & 0xFF,
                     TED_SANITIZER_COMPARE_ADDR >> 8)

    # The crown fragment has six spare bytes after its return; continue the
    # geometry comparison in a dedicated cave instead of crossing fragments.
    compare = _Asm()
    compare.db(0x79, 0xE6, 0x07, 0x07, 0x07, 0x57)
    compare.db(0x78, 0xE6, 0x1F, 0x92, 0xC6, 0x04, 0xE6, 0x1F, 0xBE)
    compare.jr(0x38, "outside")
    compare.db(0x23, 0xBE)
    compare.jr(0x30, "outside")
    compare.db(0xE1, 0xD1, 0xC1, 0xC9)
    compare.label("outside")
    compare.db(0xE1, 0xD1, 0xC1, 0xC3,
               TED_SANITIZER_CLEAR_ADDR & 0xFF,
               TED_SANITIZER_CLEAR_ADDR >> 8)

    special = _Asm()
    special.db(0xFE, 0x7B)
    special.jr(0x38, "not_sparse")
    special.db(0xFE, 0x87)
    special.jr(0x30, "not_sparse")
    special.db(0xAF, 0xC9)  # Z: all and only $7B-$86
    special.label("not_sparse")
    special.db(0x3E, 0x01, 0xB7, 0xC9)
    special.label("outside")
    special.db(0xE1, 0xD1, 0xC1, 0xC3,
               TED_SANITIZER_CLEAR_ADDR & 0xFF,
               TED_SANITIZER_CLEAR_ADDR >> 8)

    clear = _Asm()
    clear.db(0x7D, 0x0F, 0x0F, 0x0F, 0x0F, 0x0F, 0xAD, 0xE6, 0x01, 0x12, 0xC9)

    row_table = bytes([
        4, 9, 2, 10, 2, 10, 2, 10, 2, 10, 2, 11, 1, 11,
        0, 11, 0, 11, 0, 11, 1, 11, 2, 10, 4, 10, 5, 9,
    ])

    fragments = {
        TED_SANITIZER_MAIN_ADDR: main.finish(),
        TED_SANITIZER_CLASSIFY_ADDR: classify.finish(),
        TED_SANITIZER_CROWN_ADDR: crown.finish(),
        TED_SANITIZER_ACTIVE_ADDR: active.finish(),
        TED_SANITIZER_SPECIAL_ADDR: special.finish(),
        TED_SANITIZER_CLEAR_ADDR: clear.finish(),
        TED_SANITIZER_ROW_TABLE_ADDR: row_table,
        TED_SANITIZER_ANCHOR_ADDR: anchor.finish(),
        TED_SANITIZER_GEOMETRY_CONT_ADDR: geometry_cont.finish(),
        TED_SANITIZER_COMPARE_ADDR: compare.finish(),
        TED_SANITIZER_ANCHOR_PACK_ADDR: anchor_pack.finish(),
    }
    for address, code in fragments.items():
        assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE, (hex(address), len(code))
    return fragments


def build_ted_group_sanitizer_wram() -> bytes:
    """Repair Ted's three stacked attributes without mutating source art.

    One packed byte records crown position at four-cell precision.  Every
    numbered body tile outside the 16x16 crown-relative publication envelope
    becomes the native checker before its LUT lookup.  Future C1A0 cells are
    untouched until their own three-cell group is actually published.
    """
    a = _Asm()
    call_operands: list[tuple[int, str]] = []

    def call(label: str) -> None:
        a.db(0xCD, 0x00, 0x00)
        call_operands.append((len(a.code) - 2, label))

    a.label("entry")
    # Preserve caller BC/DE.  BC becomes the physical destination while HL
    # walks the three attribute A bytes already stacked by the atomic copier.
    a.db(0x44, 0x4D, 0xD5)                 # LD B,H / LD C,L / PUSH DE
    # Keep the last complete crown until the next one is encountered. Ted's
    # alternating physical map can wrap such that valid body rows are copied
    # before the new crown group. Clearing the anchor at map column zero made
    # those rows deterministically disappear, which looked like teleporting.
    # The bank mapper's CALL return occupies two bytes above our entry SP;
    # after saving BC/DE, SP+9 is the first stacked attribute A byte. SP+7
    # would overwrite the RST return high byte and jump into $00xx on RET.
    a.db(0xF8, 0x07)
    a.db(0xAF, 0xE0, TED_SANITIZER_TILE_MASK_HRAM)
    a.db(0x3E, 0x03, 0xE0, TED_SANITIZER_COUNTER_HRAM)
    a.label("cell")
    a.db(0x1A, 0xFE, 0x02)
    a.jr(0x38, "next")
    # Native floor IDs overlap the old broad numbered-body range. Always
    # materialize them from physical destination parity; allowing a shifted
    # source-floor cell through the body envelope breaks the $77-$7A lattice.
    a.db(0xFE, 0x77)
    a.jr(0x38, "body_tile")
    a.db(0xFE, 0x7B)
    a.jr(0x38, "clear")
    # Numbered body plus the compact $7B-$86 animation-edge neighborhood.
    # The intervening neutral IDs are still boss-local staging in scene $10.
    a.db(0xFE, 0x87)
    a.jr(0x30, "next")
    a.db(0xFE, 0x7B)
    a.jr(0x28, "sparse_tile")
    a.db(0xFE, 0x7D)
    a.jr(0x28, "sparse_tile")
    a.db(0xFE, 0x80)
    a.jr(0x28, "sparse_tile")
    a.db(0xFE, 0x82)
    a.jr(0x38, "next")
    a.label("sparse_tile")
    # Sparse $7B-$86 cells are Ted's native independently animated tendrils.
    # Their measured corpus reaches rows -16..15; the former compact envelope
    # clipped valid extension phases down to zero or one cell. Numbered torso
    # containment is handled separately below, so retaining sparse cells does
    # not admit the detached numbered-body copies this sanitizer targets.
    a.jr(0x18, "next")
    a.label("body_tile")
    # A9=1 is the established active anchor and retains the exact fast-path
    # cost. A9=2 means a row-zero staging crown is active; only that short-lived
    # state scans for the later completed crown. A9=$53/$57 is a deferred map
    # token emitted by the semantic boundary.
    a.db(0xF0, TED_SANITIZER_EXPECTED_HRAM, 0x3D)
    a.jr(0x28, "classify")
    a.db(0x3C)
    a.jr(0x28, "no_anchor")
    a.db(0x3D, 0xFE, 0x40)                 # restored state-1; tokens are >=40
    a.jr(0x30, "map_token")
    a.db(0xE0, TED_SANITIZER_EXPECTED_HRAM)  # bounded crown-scan countdown
    a.jr(0x18, "scan_crown")
    a.label("map_token")
    a.db(0x3C)                              # restore $53/$57 map token
    a.db(0xCD, TED_MAP_ANCHOR_ACTIVATE_ROM_ADDR & 0xFF,
         TED_MAP_ANCHOR_ACTIVATE_ROM_ADDR >> 8)
    a.jr(0x20, "classify")
    a.label("no_anchor")
    a.db(0x1A, 0xFE, 0x02)
    a.jr(0x20, "clear")                    # only tile $02 can be a crown
    a.db(0xD5)
    a.db(0xCD, TED_CROWN_PAIR_HELPER_ADDR & 0xFF,
         TED_CROWN_PAIR_HELPER_ADDR >> 8)
    a.db(0xD1)
    a.jr(0x20, "clear")
    call("pack_anchor")
    a.jr(0x18, "classify")
    a.label("scan_crown")
    a.db(0x1A, 0xFE, 0x02)
    a.jr(0x20, "classify")                 # avoid helper cost for body bulk
    a.db(0xCD, TED_SCAN_CROWN_HELPER_ROM_ADDR & 0xFF,
         TED_SCAN_CROWN_HELPER_ROM_ADDR >> 8)
    a.jr(0x30, "classify")                # NC: no crown or first staging crown
    call("pack_anchor")
    a.db(0x3E, 0x01, 0xE0, TED_SANITIZER_EXPECTED_HRAM)
    a.label("classify")
    a.db(0xE5)
    call("inside_envelope")
    a.db(0xE1)
    a.jr(0x28, "next")                    # Z = visible body envelope
    a.label("clear")
    # Reject scratch geometry and its stacked attribute atomically. Anchor
    # correctness is essential here: a four-column error turned this intended
    # containment mask into destructive clipping of the native boss.
    a.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0xF6, 0x01,
         0xE0, TED_SANITIZER_TILE_MASK_HRAM)
    a.db(0xCD, TED_CHECKER_ATTR_HELPER_ADDR & 0xFF,
         TED_CHECKER_ATTR_HELPER_ADDR >> 8)
    a.label("next")
    # Three rotations produce bits 7/6/5 in source order for the writer.
    a.db(0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0x0F,
         0xE0, TED_SANITIZER_TILE_MASK_HRAM)
    a.db(0x13, 0x03, 0x23, 0x23)
    a.db(0xF0, TED_SANITIZER_COUNTER_HRAM, 0x3D,
         0xE0, TED_SANITIZER_COUNTER_HRAM)
    a.jr(0x20, "cell")
    a.db(0xD1, 0x0B, 0x0B, 0x0B, 0x60, 0x69)
    a.db(0xC3, TED_REGISTER_MATERIALIZER_FRONT_ADDR & 0xFF,
         TED_REGISTER_MATERIALIZER_FRONT_ADDR >> 8)

    a.label("pack_anchor")
    # BC is the physical destination of the canonical crown cell. Derive its
    # row directly; the former DCE0 phase substitution made an early row-zero
    # staging crown sticky and was the source of Ted's partial disappearance.
    a.db(0xD5, 0x79, 0xCB, 0x37, 0x0F, 0xE6, 0x07, 0x57)
    a.db(0x78, 0xE6, 0x03, 0x07, 0x07, 0x07, 0xB2)
    a.db(0x57)
    a.db(0xEA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
         TED_SANITIZER_ANCHOR_ROW_ADDR >> 8)
    # The first numbered crown cell already lands at the native physical
    # origin. The former nonzero-row +4 correction shifted a real (4,12)
    # crown to (4,16), cutting roughly half of every ordinary pose.
    a.db(0x79, 0xE6, 0x1F, 0x5F, 0x7B)
    a.db(0xEA, TED_SANITIZER_ANCHOR_COL_ADDR & 0xFF,
         TED_SANITIZER_ANCHOR_COL_ADDR >> 8)
    if _os.environ.get("PENTA_TED_CACHE_CROWN", "1") == "1":
        # Persist the completed crown in the cache owned by BC's physical map.
        # This is crown-only work; the three-cell hot path and ordinary body
        # cells retain their established timing.
        a.db(0x78, 0xE6, 0x04, 0x0F)
        a.db(0xC6, TED_SANITIZER_ANCHOR_9800_ROW_ADDR & 0xFF,
             0x5F, 0x16, TED_SANITIZER_ANCHOR_9800_ROW_ADDR >> 8)
        a.db(0xFA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
             TED_SANITIZER_ANCHOR_ROW_ADDR >> 8, 0x12, 0x13)
        a.db(0xFA, TED_SANITIZER_ANCHOR_COL_ADDR & 0xFF,
             TED_SANITIZER_ANCHOR_COL_ADDR >> 8, 0x12)
    # The first canonical crown arms a bounded scan for one later completed
    # crown in the same publication. The scan caller switches this to state 1
    # immediately after that second crown is packed.
    a.db(0xD1, 0x3E, 0x08,
         0xE0, TED_SANITIZER_EXPECTED_HRAM, 0xC9)

    a.label("inside_envelope")
    a.db(0xD5)
    # A = crown-relative physical row modulo 32.
    a.db(0x79, 0xCB, 0x37, 0x0F, 0xE6, 0x07, 0x57)
    a.db(0x78, 0xE6, 0x03, 0x07, 0x07, 0x07, 0xB2, 0x57)
    a.db(0xFA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
         TED_SANITIZER_ANCHOR_ROW_ADDR >> 8, 0x5F)
    a.db(0x7A, 0x93, 0xE6, 0x1F, 0xFE, 0x0E)
    a.jr(0x30, "outside")
    a.db(0x87, 0xC6, TED_ENVELOPE_ROW_TABLE_ROM_ADDR & 0xFF, 0x6F)
    a.db(0x26, TED_ENVELOPE_ROW_TABLE_ROM_ADDR >> 8)
    a.db(0x79, 0xE6, 0x1F, 0x57)
    a.db(0xFA, TED_SANITIZER_ANCHOR_COL_ADDR & 0xFF,
         TED_SANITIZER_ANCHOR_COL_ADDR >> 8, 0x5F)
    a.db(0x7A, 0x93, 0xC6, 0x04, 0xE6, 0x1F)
    a.db(0xC3, TED_ENVELOPE_COMPARE_ROM_ADDR & 0xFF,
         TED_ENVELOPE_COMPARE_ROM_ADDR >> 8)
    a.label("outside")
    a.db(0xD1, 0xF6, 0x01, 0xC9)

    code = bytearray(a.finish())
    for operand, label in call_operands:
        target = TED_SANITIZER_RUNTIME_ADDR + a.labels[label]
        code[operand] = target & 0xFF
        code[operand + 1] = target >> 8
    # Keep the executable payload compact.  The installer's final fragment
    # writes the readiness sentinel at C5FF separately; padding the payload
    # all the way to that byte consumed two scarce ROM resource records and
    # added pointless cold-entry copy time.
    runtime_size = 257
    assert len(code) <= runtime_size, (len(code), runtime_size)
    code.extend(bytes(runtime_size - len(code)))
    assert TED_SANITIZER_RUNTIME_ADDR + len(code) <= WRAM_BG_TABLE, (
        len(code), hex(TED_SANITIZER_RUNTIME_ADDR + len(code))
    )
    return bytes(code)


def build_ted_checker_attr_helper() -> bytes:
    """Write the BG6/BG7 material for one rejected checker destination.

    BC is the physical map address and HL points at that cell's stacked
    attribute.  The native $77-$7A checker alternates on both row and column,
    so its palette is 6 + (address bit 5 XOR address bit 0).
    """
    code = bytes([
        0x79,                               # LD A,C
        0x07, 0x07, 0x07,                  # map row parity bit 5 -> bit 0
        0xA9, 0xE6, 0x01,                  # XOR C; AND 1
        0xC6, 0x06, 0x77, 0xC9,            # ADD 6; LD [HL],A; RET
    ])
    assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return code


def build_ted_crown_pair_helper() -> tuple[bytes, bytes]:
    """Return Z only for the native leading $02,$03,$04 crown prefix."""
    front = bytes([
        0x1A, 0xFE, 0x02, 0xC0,            # current source cell is $02
        0x13, 0x1A,                         # inspect following source cell
        0xC3, TED_CROWN_PAIR_HELPER_CONT_ADDR & 0xFF,
        TED_CROWN_PAIR_HELPER_CONT_ADDR >> 8,
    ])
    continuation = bytes([
        0xFE, 0x03, 0xC0,                  # second cell is $03
        0x13, 0x1A, 0xFE, 0x04, 0xC9,      # third cell is $04
    ])
    assert len(front) <= 9 and len(continuation) <= 9
    return front, continuation


def build_ted_inside_envelope_rom() -> tuple[bytes, bytes]:
    """Return the fixed-ROM span comparator and exact row table."""
    code = bytes([
        0xBE, 0x38, 0x07,
        0x23, 0xBE, 0x30, 0x03,
        0xD1, 0xAF, 0xC9,
        0xD1, 0x3C, 0xC9,
    ])
    table = bytes([
        4, 9, 2, 10, 2, 10, 2, 10, 2, 10, 2, 11, 1, 11,
        0, 11, 0, 11, 0, 11, 1, 11, 2, 10, 4, 10, 5, 9,
    ])
    return code, table


def build_ted_map_anchor_activate_rom() -> bytes:
    """Resolve a deferred $53/$57 map token to its cached active crown."""
    a = _Asm()
    a.db(
        0xE5,
        0xE6, 0x04, 0x0F,
        0xC6, TED_SANITIZER_ANCHOR_9800_ROW_ADDR & 0xFF,
        0x6F, 0x26, TED_SANITIZER_ANCHOR_9800_ROW_ADDR >> 8,
        0x2A,
        0xEA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_ROW_ADDR >> 8,
        0x3C,
    )
    a.jr(0x28, "invalid")                 # cached row $FF has no crown yet
    a.db(
        0x7E,
        0xEA, TED_SANITIZER_ANCHOR_COL_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_COL_ADDR >> 8,
        0xCD, TED_ANCHOR_STATE_HELPER_ROM_ADDR & 0xFF,
        TED_ANCHOR_STATE_HELPER_ROM_ADDR >> 8,
        0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0xB7, 0xE1, 0xC9,
    )
    a.label("invalid")
    a.db(0xAF, 0xE0, TED_SANITIZER_EXPECTED_HRAM, 0xE1, 0xC9)
    code = a.finish()
    assert (
        TED_MAP_ANCHOR_ACTIVATE_ROM_ADDR + len(code)
        <= TED_ANCHOR_STATE_HELPER_ROM_ADDR
    )
    return code


def build_ted_map_anchor_activate_tail_rom() -> bytes:
    """Retired alias retained for diagnostics that import the builder."""
    return b""


def build_ted_anchor_state_helper_rom() -> bytes:
    """Choose first-crown refresh or row-zero skip-first refresh state."""
    a = _Asm()
    a.db(0xFA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
         TED_SANITIZER_ANCHOR_ROW_ADDR >> 8, 0xB7)
    a.jr(0x28, "row_zero")
    a.db(0x3E, 0x08, 0xC9)                 # accept first canonical crown
    a.label("row_zero")
    a.db(0x3E, 0x3F, 0xC9)                 # skip staging crown; accept second
    code = a.finish()
    assert len(code) <= 21
    return code


def build_ted_scan_crown_helper_rom() -> bytes:
    """Skip a publication's first staging crown; accept its second crown."""
    a = _Asm()
    a.db(0xD5)
    a.db(0xCD, TED_CROWN_PAIR_HELPER_ADDR & 0xFF,
         TED_CROWN_PAIR_HELPER_ADDR >> 8)
    a.db(0xD1)
    a.jr(0x20, "none")
    a.db(0xF0, TED_SANITIZER_EXPECTED_HRAM, 0xFE, 0x30)
    a.jr(0x38, "accept")                   # countdown < $30: second crown
    a.db(0x3E, 0x08, 0xE0, TED_SANITIZER_EXPECTED_HRAM)
    a.label("none")
    a.db(0xAF, 0xC9)                       # NC: ignore/no crown
    a.label("accept")
    a.db(0x37, 0xC9)                       # C: caller packs completed crown
    code = a.finish()
    assert TED_SCAN_CROWN_HELPER_ROM_ADDR + len(code) <= 0x7700
    return code


def build_ted_anchor_self_patch_init() -> bytes:
    """Initialize dual anchors, then restore the byte-exact hot entry."""
    code = bytes([
        0x3E, 0xFF,
        0xEA, TED_SANITIZER_ANCHOR_9800_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_9800_ROW_ADDR >> 8,
        0xEA, TED_SANITIZER_ANCHOR_9C00_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_9C00_ROW_ADDR >> 8,
        0xEA, TED_SANITIZER_ANCHOR_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_ROW_ADDR >> 8,
        0x3C, 0xE0, TED_SANITIZER_EXPECTED_HRAM,
        0x21, TED_SANITIZER_RUNTIME_ADDR & 0xFF,
        TED_SANITIZER_RUNTIME_ADDR >> 8,
        0x3E, 0x44, 0x22,                  # LD B,H
        0x3E, 0x4D, 0x22,                  # LD C,L
        0x3E, 0xD5, 0x77,                  # PUSH DE
        0xC3, TED_SANITIZER_RUNTIME_ADDR & 0xFF,
        TED_SANITIZER_RUNTIME_ADDR >> 8,
    ])
    assert (
        TED_SANITIZER_ANCHOR_INIT_RUNTIME_ADDR + len(code)
        <= TED_SANITIZER_RUNTIME_SENTINEL_ADDR
    )
    return code


def build_native_tile_materializer() -> bytes:
    """Return native source IDs as B/C/FFA8 from bank-13 ROM."""
    return bytes([
        0x1A, 0x13, 0x47,
        0x1A, 0x13, 0x4F,
        0x1A, 0x13, 0xE0, TED_SANITIZER_COUNTER_HRAM,
        0x3E, 0x01, 0xC9,
    ])


def build_ted_register_materializer() -> tuple[bytes, bytes, bytes]:
    """Return Ted's three final tile IDs as B/C/FFA8 outside HBlank."""
    front = bytes([
        0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0x4F,
        0x7D, 0xE6, 0x20, 0xCB, 0x37, 0xC6, 0x77, 0x47,
        0xCB, 0x45, 0x28, 0x01, 0x04,
        0xCB, 0x69, 0x1A, 0x13, 0x28, 0x01, 0x78,
        0xE0, TED_SANITIZER_TILE_MASK_HRAM,
        0xCB, 0x45, 0x28, 0x03, 0x05, 0x18, 0x01, 0x04,
        0xC3, TED_REGISTER_MATERIALIZER_TAIL_ADDR & 0xFF,
        TED_REGISTER_MATERIALIZER_TAIL_ADDR >> 8,
    ])
    tail = bytes([
        0xCB, 0x71, 0x1A, 0x13, 0x28, 0x01, 0x78,
        0xE0, TED_SANITIZER_COUNTER_HRAM,
        0xCB, 0x45, 0x28, 0x03, 0x04, 0x18, 0x01, 0x05,
        0xC3, TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR & 0xFF,
        TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR >> 8,
    ])
    tail_cont = bytes([
        0xCB, 0x79,
        0xF0, TED_SANITIZER_COUNTER_HRAM, 0x4F,
        0x1A, 0x13, 0x28, 0x01, 0x78,
        0xE0, TED_SANITIZER_COUNTER_HRAM,
        0xF0, TED_SANITIZER_TILE_MASK_HRAM, 0x47,
        0x3E, 0x01, 0xC9,
    ])
    assert len(front) <= ARENA_SANITIZER_FRAGMENT_SIZE
    assert len(tail) <= ARENA_SANITIZER_FRAGMENT_SIZE
    assert len(tail_cont) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return front, tail, tail_cont


def build_ted_group_sanitizer_installer() -> tuple[bytes, bytes, bytes, bytes]:
    """Lazily copy the fragmented runtime into C500 at Ted's first group."""
    runtime = build_ted_group_sanitizer_wram()
    sources = (
        TED_SANITIZER_MAIN_ADDR,
        TED_SANITIZER_CLASSIFY_ADDR,
        TED_SANITIZER_CROWN_ADDR,
        TED_SANITIZER_ACTIVE_ADDR,
        TED_SANITIZER_ROW_TABLE_ADDR,
        TED_SANITIZER_GEOMETRY_CONT_ADDR,
        TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR,
        TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR,
    )
    copies = []
    cursor = 0
    for source in sources:
        span = min(
            (21 if source == TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR
             else 20 if source == TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR
             else ARENA_SANITIZER_FRAGMENT_SIZE),
            len(runtime) - cursor,
        )
        chunk = runtime[cursor:cursor + span]
        if source == TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR:
            chunk = chunk.rstrip(b"\x00")
        length = len(chunk)
        live = len(chunk.rstrip(b"\x00"))
        if source == TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR and 0 < live <= 3:
            # At most three executable bytes cross this fragment boundary.
            # Direct WRAM stores are smaller than setting up memcpy and leave
            # room for deterministic dual-anchor initialization.
            target = TED_SANITIZER_RUNTIME_ADDR + cursor
            direct = bytearray([0x21, target & 0xFF, target >> 8])
            for index, value in enumerate(chunk[:live]):
                direct.extend((0x36, value))
                if index + 1 < live:
                    direct.append(0x23)
            copies.append(bytes(direct))
        else:
            copies.append(bytes([
                0x21, source & 0xFF, source >> 8,
                0x11, (TED_SANITIZER_RUNTIME_ADDR + cursor) & 0xFF,
                (TED_SANITIZER_RUNTIME_ADDR + cursor) >> 8,
                0x01, length, 0x00,
                0xCD, 0xB3, 0x09,
            ]) if any(chunk) else b"")
        cursor += span
    assert cursor == len(runtime)
    second_copy = copies[1]
    assert len(second_copy) == 12 and second_copy[3] == 0x11
    # memcpy leaves DE immediately after the first 36-byte destination chunk;
    # the second chunk is contiguous, so omit its redundant LD DE,nn setup.
    second_copy = second_copy[:3] + second_copy[6:]
    cache_init = bytes([
        0x3E, 0xFF,
        0xEA, TED_SANITIZER_ANCHOR_9800_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_9800_ROW_ADDR >> 8,
        0xEA, TED_SANITIZER_ANCHOR_9C00_ROW_ADDR & 0xFF,
        TED_SANITIZER_ANCHOR_9C00_ROW_ADDR >> 8,
    ]) if _os.environ.get("PENTA_TED_DUAL_MAP_ANCHOR", "1") == "1" else b""
    front = bytes([0xC5, 0xD5, 0xE5]) + copies[0] + second_copy + cache_init + bytes([
        0xC3, TED_SANITIZER_INSTALL_MIDDLE_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_MIDDLE_ADDR >> 8,
    ])
    middle = b"".join(copies[2:4]) + bytes([
        0xC3, TED_SANITIZER_INSTALL_TAIL_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_TAIL_ADDR >> 8,
    ])
    tail = b"".join(copies[4:6]) + bytes([
        0xC3, TED_SANITIZER_INSTALL_FINAL_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_FINAL_ADDR >> 8,
    ])
    final = b"".join(copies[6:8]) + bytes([
        0x3E, TED_SANITIZER_RUNTIME_SENTINEL_VALUE,
        0xEA, TED_SANITIZER_RUNTIME_SENTINEL_ADDR & 0xFF,
        TED_SANITIZER_RUNTIME_SENTINEL_ADDR >> 8,
        0xE1, 0xD1, 0xC1,
        0xC3, TED_SANITIZER_RUNTIME_ADDR & 0xFF,
        TED_SANITIZER_RUNTIME_ADDR >> 8,
    ])
    assert len(front) <= ARENA_SANITIZER_FRAGMENT_SIZE
    assert len(middle) <= ARENA_SANITIZER_FRAGMENT_SIZE
    assert len(tail) <= ARENA_SANITIZER_FRAGMENT_SIZE
    assert len(final) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return front, middle, tail, final


def build_ted_writer_mirror_installer(
    runtime: bytes, initializer_addr: int,
) -> tuple[bytes, bytes, bytes, bytes]:
    """Install the global writer mirror during the existing boot sequence."""
    sources = (
        TED_SANITIZER_MAIN_ADDR,
        TED_SANITIZER_CLASSIFY_ADDR,
        TED_SANITIZER_CROWN_ADDR,
        TED_SANITIZER_ACTIVE_ADDR,
        TED_SANITIZER_ROW_TABLE_ADDR,
        TED_SANITIZER_GEOMETRY_CONT_ADDR,
    )
    capacities = (36, 36, 36, 36, 36, 36)
    copies = []
    cursor = 0
    for source, capacity in zip(sources, capacities):
        if cursor == len(runtime):
            break
        length = min(capacity, len(runtime) - cursor)
        copies.append(bytes([
            0x21, source & 0xFF, source >> 8,
            0x11, (TED_WRITER_RUNTIME_ADDR + cursor) & 0xFF,
            (TED_WRITER_RUNTIME_ADDR + cursor) >> 8,
            0x01, length, 0x00, 0xCD, 0xB3, 0x09,
        ]))
        cursor += length
    assert cursor == len(runtime)
    front = bytes([0xC5, 0xD5, 0xE5]) + b"".join(copies[:2]) + bytes([
        0xC3, TED_SANITIZER_INSTALL_MIDDLE_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_MIDDLE_ADDR >> 8,
    ])
    middle = b"".join(copies[2:4]) + bytes([
        0xC3, TED_SANITIZER_INSTALL_TAIL_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_TAIL_ADDR >> 8,
    ])
    tail = b"".join(copies[4:6]) + bytes([
        # Clear both switchable-WRAM attr planes before the first dirty
        # publication.  This makes the eight GDMA padding columns per row
        # deterministic even after reinstalling over a stale savestate.
        0x3E, 0x02, 0xE0, 0x70,
        0x21, 0x00, 0xD0,
        0xC3, TED_SANITIZER_INSTALL_FINAL_ADDR & 0xFF,
        TED_SANITIZER_INSTALL_FINAL_ADDR >> 8,
    ])
    final = b"".join(copies[6:]) + bytes([
        0x01, 0x00, 0x03, 0xAF, 0xCD, 0xA8, 0x09,
        0x3E, 0x03, 0xE0, 0x70,
        0x21, 0x00, 0xD0, 0x01, 0x00, 0x03,
        0xAF, 0xCD, 0xA8, 0x09,
        # The stock fill preserves A=0, so INC A restores SVBK=1 one byte
        # cheaper than LD A,1 and leaves room for the writer sentinel.
        0x3C, 0xE0, 0x70,
        0xCD, initializer_addr & 0xFF, initializer_addr >> 8,
        0x3E, TED_WRITER_RUNTIME_SENTINEL_VALUE,
        0xEA, TED_WRITER_RUNTIME_SENTINEL_ADDR & 0xFF,
        TED_WRITER_RUNTIME_SENTINEL_ADDR >> 8,
        0xE1, 0xD1, 0xC1, 0xC9,
    ])
    for payload in (front, middle, tail, final):
        assert len(payload) <= ARENA_SANITIZER_FRAGMENT_SIZE, len(payload)
    return front, middle, tail, final


def build_shalamar_source_sanitizer_fragments() -> dict[int, bytes]:
    """Apply Shalamar's established staging mask once per publication."""
    main = _Asm()
    main.db(0xC5, 0xD5, 0xE5, 0x21, 0xA0, 0xC1, 0x06, 0x18)
    main.label("row")
    main.db(0x0E, 0x18)
    main.label("cell")
    main.db(0xCD, SHALAMAR_SANITIZER_CELL_ADDR & 0xFF,
            SHALAMAR_SANITIZER_CELL_ADDR >> 8, 0x23, 0x0D)
    main.jr(0x20, "cell")
    main.db(0x05)
    main.jr(0x20, "row")
    main.db(0xE1, 0xD1, 0xC1)
    main.db(0xCD, TED_TILE_COMMIT_RUNTIME_ADDR & 0xFF,
            TED_TILE_COMMIT_RUNTIME_ADDR >> 8, 0xC9)

    cell = _Asm()
    cell.db(0x78, 0xFE, 0x0D)
    cell.jr(0x38, "clear")              # countdown B<=12 -> rows 12+
    cell.db(0xFE, 0x11, 0xD0)            # B>=17 -> rows 0..7
    cell.db(0x79, 0xFE, 0x07, 0xD0)      # rows 8..11, columns <18
    cell.label("clear")
    cell.db(0x78, 0xA9, 0xE6, 0x01, 0x77, 0xC9)
    fragments = {
        SHALAMAR_SANITIZER_MAIN_ADDR: main.finish(),
        SHALAMAR_SANITIZER_CELL_ADDR: cell.finish(),
    }
    for address, code in fragments.items():
        assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE, (hex(address), len(code))
    return fragments


def build_arena_sanitizer_banked_dispatch(
    *, writer_mirror: bool = False,
) -> bytes:
    """Route later dungeons or Shalamar/Ted post-copy sanitizers.

    The fixed atomic selector shares this bank-13 entry between later-stage
    publications and boss arenas. Stages 2-7 already built their complete
    attribute plane in the inline copier, so they only need the mapper's A=1
    return contract. Arena scenes continue into their source sanitizer.
    """
    a = _Asm()
    production_dispatch = (
        _os.environ.get("PENTA_TED_EXPANDED_PAYLOAD", "0") != "1"
    )
    if production_dispatch:
        a.db(0xFA, 0x80, 0xD8, 0xD6, 0x03, 0xFE, 0x06)
        a.jr(0x38, "later_dungeon")
    a.db(0xFA, 0x02, 0xC6, 0xFE, 0x04)
    a.db(0xCA, SHALAMAR_SANITIZER_MAIN_ADDR & 0xFF,
         SHALAMAR_SANITIZER_MAIN_ADDR >> 8)
    if writer_mirror:
        # ROM-resident tracking has no lazy common-WRAM installation.
        a.db(0x3E, 0x01, 0xC9)
        if production_dispatch:
            a.label("later_dungeon")
            a.db(0x3E, 0x01, 0xC9)
        code = a.finish()
        assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
        return code
    sentinel_addr = (
        TED_WRITER_RUNTIME_SENTINEL_ADDR
        if writer_mirror else TED_SANITIZER_RUNTIME_SENTINEL_ADDR
    )
    sentinel_value = (
        TED_WRITER_RUNTIME_SENTINEL_VALUE
        if writer_mirror else TED_SANITIZER_RUNTIME_SENTINEL_VALUE
    )
    a.db(0xFA, sentinel_addr & 0xFF, sentinel_addr >> 8)
    a.db(0xFE, sentinel_value)
    a.jr(0x28, "ted_installed")
    a.db(0xC3, TED_SANITIZER_INSTALL_ADDR & 0xFF,
         TED_SANITIZER_INSTALL_ADDR >> 8)
    a.label("ted_installed")
    a.db(0xC3, TED_SANITIZER_RUNTIME_ADDR & 0xFF,
         TED_SANITIZER_RUNTIME_ADDR >> 8)
    if production_dispatch:
        a.label("later_dungeon")
        a.db(0x3E, 0x01, 0xC9)
    code = a.finish()
    assert len(code) <= ARENA_SANITIZER_FRAGMENT_SIZE
    return code


def build_stage1_atomic_attr_stack_helper() -> bytes:
    """Replace stacked attrs for the exact nine bank-1 tooth-row cells.

    The three-wide atomic copier has already pushed one AF pair per pending
    tile when it enters through RST $18. Preserve its BC/HL, reject every row
    except map rows $40/$A0, subtract room $02's four-cell shift, then rewrite
    only stacked A bytes whose column is in the inclusive 0..8 travel span.
    The later HBlank loop therefore commits tile ID and attribute $0F in one
    access window, including while VBlank is masked during the miniboss map
    transition. No extra VRAM write or per-cell ROM-bank switch is required.
    """
    a = _Asm()
    a.db(0xC5, 0xE5)                       # preserve BC and destination HL
    a.db(0x7C, 0xE6, 0x03)                # only base $9800/$9C00 page
    a.jr(0x20, "done")
    a.db(0x7D, 0xE6, 0xE0, 0xFE, 0x40)    # only row $40 or $A0
    a.jr(0x28, "tooth_row")
    a.db(0xFE, 0xA0)
    a.jr(0x20, "done")
    a.label("tooth_row")
    a.db(0x4D, 0x79, 0xE6, 0x1F, 0x4F)    # C = group-start column
    a.db(0xF0, 0xBD, 0xFE, 0x12)
    a.jr(0x28, "room_shifted")
    a.db(0xFE, 0x02)
    a.jr(0x20, "done")
    a.db(0x0D, 0x0D, 0x0D, 0x0D)          # room $02 starts at column 4
    a.label("room_shifted")
    a.db(0xF8, 0x07, 0x06, 0x03)          # HL -> stacked A0; B=3 cells
    a.label("cell")
    a.db(0x79, 0xFE, 0x09)
    a.jr(0x30, "next")
    a.db(0x3E, 0x0F, 0x77)                 # BG7 + VRAM pattern bank 1
    a.label("next")
    a.db(0x0C, 0x23, 0x23, 0x05)
    a.jr(0x20, "cell")
    a.label("done")
    a.db(0xE1, 0xC1, 0xC9)
    code = a.finish()
    assert len(code) == 58
    return code


def build_stage1_atomic_attr_stack_copy() -> bytes:
    """Copy the split 58-byte position helper into its DB80 runtime slot."""
    helper = build_stage1_atomic_attr_stack_helper()
    first = 56
    assert len(helper[first:]) == 2
    return bytes([
        0x21,
        STAGE1_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR & 0xFF,
        STAGE1_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR >> 8,
        0x11,
        STAGE1_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR & 0xFF,
        STAGE1_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR >> 8,
        0x01, first, 0x00,
        0xCD, 0xB3, 0x09,
        0x21,
        (STAGE1_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR + first) & 0xFF,
        (STAGE1_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR + first) >> 8,
        0x3E, helper[first], 0x22,
        0x3E, helper[first + 1], 0x77,
        0xC9,
    ])


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


def build_stage1_demo_attr_trampoline() -> bytes:
    """Run the demo key path and publish B=$05 at the exact old cadence.

    Skipping the ten-cycle live scene gate balances CALL/RET plus the final
    route-token load. INC BC supplies the remaining two neutral cycles; the
    decider overwrites C and no flags are changed.
    """
    code = bytes([
        0x03,                               # 2M register-neutral balance
        0xCD,
        (STAGE1_ATTR_RUNTIME_ADDR + 9) & 0xFF,
        (STAGE1_ATTR_RUNTIME_ADDR + 9) >> 8,
        0x06, 0x05,                         # B = no-hazard route token
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
    """Build the always-mapped cached-layout map decider.

    Seven corpus-selected source cells form two independent XOR bytes. Together
    with the room identity they distinguish semantic planes in the later-
    stage streaming trace. Crystal Dragon also uses this cache because its
    body is OBJ and its BG is structurally stable. Unchanged map copies retain
    the fast pure path while every changed layout publishes both planes.
    """
    a = _Asm()
    a.db(0xC5, 0xD5, 0xE5)                 # preserve caller BC/DE/HL
    a.db(0xAF, 0xE0, LAVA_ATTR_DECISION_HRAM)

    def emit_metadata_select(label: str) -> None:
        # $98 XOR $CB = $53; $9C XOR $CB = $57.
        a.db(0x7C, 0xEE, 0xCB, 0x5F, 0x16, 0xDF)
        a.label(label)

    emit_metadata_select("metadata_selected")
    for register_opcode, samples in (
        (0x47, LATER_ATTR_SIGNATURE_A),     # LD B,A
        (0x4F, LATER_ATTR_SIGNATURE_B),     # LD C,A
    ):
        for index, offset in enumerate(samples):
            source = 0xC1A0 + offset
            a.db(0xFA, source & 0xFF, source >> 8)
            if index:
                a.db(0xA8 if register_opcode == 0x47 else 0xA9)
            a.db(register_opcode)

    a.db(0x1A, 0xB8)                       # cached signature A CP B
    a.jr(0x20, "changed")
    a.db(0x13, 0x1A, 0xB9)                 # cached signature B CP C
    a.jr(0x20, "changed_one")
    a.db(0x13, 0x1A, 0x6F)                 # L = cached room
    a.db(0xF0, 0xBD, 0xBD)                 # current room CP L
    a.jr(0x20, "changed_two")
    a.db(0xE1, 0xD1, 0xC1, 0xC9)           # unchanged -> pure tile copy

    a.label("changed_two")
    a.db(0x1B)                             # DE base+2 -> base+1
    a.label("changed_one")
    a.db(0x1B)                             # DE base+1 -> base
    a.label("changed")
    a.db(
        0x78, 0x12, 0x13,                  # signature A
        0x79, 0x12, 0x13,                  # signature B
        0xF0, 0xBD, 0x12,                  # room
        0x3E, 0x01, 0xE0, LAVA_ATTR_DECISION_HRAM,
        0xE1, 0xD1, 0xC1, 0xC9,
    )
    code = a.finish()
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
    padding_to_end = bytes(
        OAM_WRAM_END_ADDR - (STAGE1_ATTR_RUNTIME_ADDR + len(stage1_runtime))
    )
    blob = (
        code
        + padding_before_dispatch
        + dispatcher
        + stage1_runtime
        + padding_to_end
    )
    assert LAVA_ATTR_STAGE7_RUNTIME_ADDR + len(blob) == OAM_WRAM_END_ADDR
    return blob


def build_lava_attr_decider_bank0() -> bytes:
    """Load bank 14 for exact Stage-1/demo pure-copy publications."""
    code = bytes([
        0x3E, 0x0E,
        0xC3,
        LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR & 0xFF,
        LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR >> 8,
    ])
    assert len(code) == 5
    return code


def build_lava_attr_decider_bank0_map_entry() -> bytes:
    """Map A, call the same-address banked selector, and restore bank 1.

    Stock helper 0x0061 updates both FF99 and the MBC register.  The decider
    returns A=1 while its full-vs-tile-only result remains in FFE0, allowing
    the final JP to use 0x0061's RET as this trampoline's own return.
    """
    code = bytes([
        0xCD, 0x61, 0x00,
        0xCD, STAGE1_HAZARD_BANKED_ENTRY_ADDR & 0xFF,
        STAGE1_HAZARD_BANKED_ENTRY_ADDR >> 8,
        0xC3, 0x61, 0x00,
    ])
    assert len(code) == 9
    return code


def build_stage1_hazard_banked_entries() -> tuple[bytes, bytes]:
    """Build same-address selectors for the existing fixed-bank mapper.

    The ordinary lava path maps bank 13 and lands on the decider. The live
    completed-source path enters the same fixed mapper with A=$0E, so its
    bank-14 twin lands directly on the selective hazard publisher. Both use
    the CALL return at $084F as the synthetic frame discarded by that helper.
    """
    bank13_entry = bytes([
        0xC3, LAVA_ATTR_DECIDER_ADDR & 0xFF,
        LAVA_ATTR_DECIDER_ADDR >> 8,
    ])
    bank14_entry = bytes([
        0xC3, STAGE1_HAZARD_ROOM_DISPATCH_ADDR & 0xFF,
        STAGE1_HAZARD_ROOM_DISPATCH_ADDR >> 8,
    ])
    return bank13_entry, bank14_entry


def build_inline_attr_decision_helper(atomic_row_addr: int) -> bytes:
    """Title-timed prefix plus gameplay attribute decision helper.

    Gameplay calls this readiness trampoline and enters the expanded WRAM
    helper. The title path uses the RET byte at the end of the adjacent GDMA
    helper as an exact fixed-delay target and bypasses this decision entirely.
    The WRAM payload is initialized on the title path before gameplay. Arena
    setup later clears the DF51 bookkeeping sentinel immediately before its
    first map copy without clearing the payload itself, so that sentinel must
    not suppress the arena's atomic decision. The four-byte delay slot is
    retained to preserve the proven caller phase.

    The caller presets D=$FF. The readiness path preserves B because neutral
    scenes take the pure copier without reinitializing it; the WRAM helper
    reloads D880 itself. C and E remain scratch on Stage 1 cache decisions.
    """
    a = _Asm()
    # The title entry calls three bytes before the gameplay decision. This
    # exact 28T delay preserves A=0/Z and the established title copier phase.
    a.db(0x18, 0x00, 0xC9)
    a.db(0x18, 0x00, 0x00, 0x00)
    # Demo takes the fixed cycle-equal trampoline below. Live publishes FFBD
    # in B, calls the C-keyed decider through the now-retired RST $18 vector,
    # then returns with the decider's flags intact.
    a.db(0xFA, 0xFD, 0xDC, 0xB7)
    a.jr(0x28, "demo")
    a.db(
        0xF0, 0xBD,                         # A = live room route
        0x47,                               # B = route token
        STAGE1_SOURCE_GENERATION_RST,
        0xC9,
    )
    a.label("demo")
    a.db(
        0xC3,
        STAGE1_DEMO_ATTR_TRAMPOLINE_ADDR & 0xFF,
        STAGE1_DEMO_ATTR_TRAMPOLINE_ADDR >> 8,
    )
    del atomic_row_addr                     # stock-order path needs no wrap
    code = a.finish()
    assert len(code) == 21
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
    assert OAM_BOSS_LUT_SERVICE_ADDR + len(code) <= CUTSCENE_PALETTE_CONT_ADDR, len(code)
    return code


def build_oam_boss_lut_fade_gate() -> bytes:
    """Throttle idle hash work and reject it during native fades."""
    return bytes([
        0xF0, 0xD4, 0xE6, 0x07, 0xC0,
        0xF0, 0x47, 0xFE, 0xE4, 0xC0,
        0xC3, OAM_BOSS_LUT_SERVICE_ADDR & 0xFF,
        OAM_BOSS_LUT_SERVICE_ADDR >> 8,
    ])


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
    assert (
        OAM_PALETTE_RESOLVER_ADDR + len(resolver) + len(stage1_setup)
        == OAM_CENTRAL_EMITTER_ADDR
    )
    stage7 = build_lava_attr_stage7_runtime()
    if _os.environ.get("PENTA_TED_NATIVE_POSTCOPY", "0") == "1" and (
        _os.environ.get("PENTA_TED_CACHED_FULL_PLANE", "0") != "1"
    ):
        if (
            _os.environ.get("PENTA_TED_HDMA_PIGGYBACK", "0") == "1"
            or _os.environ.get("PENTA_TED_INWINDOW_GDMA", "0") == "1"
        ):
            arena_geometry = (
                (
                    build_ted_inwindow_gate()
                    if _os.environ.get("PENTA_TED_INWINDOW_GDMA", "0") == "1"
                    else build_ted_hdma_piggyback_gate()
                )
                + build_ted_hdma_piggyback_postcopy()
            )
        else:
            arena_geometry = build_ted_native_postcopy_wrapper()
    else:
        arena_geometry = build_arena_atomic_attr_stack_helper()
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
            len(resolver) + len(stage1_setup) + len(central),
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
        (
            ARENA_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR,
            ARENA_ATOMIC_ATTR_STACK_HELPER_WRAM_ADDR,
            len(arena_geometry),
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
    # The copied Stage-7 blob already includes six zero metadata bytes at
    # DAFA-DAFF, so separate cache clears were redundant. Their reclaimed
    # bytes leave an exact seven-byte data tail for Stage 4's final material
    # fragment after this unconditional jump.
    a.db(0xC3, OAM_WRAM_COPY_TAIL_ADDR & 0xFF,
         OAM_WRAM_COPY_TAIL_ADDR >> 8)
    code = a.finish()
    assert len(code) == 54
    assert OAM_WRAM_COPY_ADDR + len(code) == STAGE4_MATERIAL_HELPER_TAIL_ADDR
    assert OAM_WRAM_COPY_ADDR + len(code) <= TITLE_TRANSITION_SERVICE_ADDR
    return code


def build_stage1_attr_row_helper() -> bytes:
    """Compile one 24-cell attribute row without per-cell HRAM counters."""
    code = bytes([
        opcode
        for _ in range(24)
        for opcode in (0x1A, 0x13, 0x4F, 0x0A, 0x22)
    ] + [0xC9])
    assert len(code) == 121
    return code


def build_stage1_attr_row_initializer() -> tuple[bytes, bytes]:
    """Generate the shared row helper in cache banks 2 and 3."""
    a = _Asm()
    a.db(
        0x3E, 0x02, 0xE0, 0x70,
        0x21,
        STAGE1_ATTR_ROW_HELPER_WRAM_ADDR & 0xFF,
        STAGE1_ATTR_ROW_HELPER_WRAM_ADDR >> 8,
        0x06, 0x18,
    )
    a.label("opcode_group")
    for opcode in (0x1A, 0x13, 0x4F, 0x0A, 0x22):
        a.db(0x3E, opcode, 0x22)
    a.db(0x05)
    a.jr(0x20, "opcode_group")
    a.db(0x3E, 0xC9, 0x77)
    a.db(
        0xC3,
        STAGE1_ATTR_ROW_INIT_TAIL_ADDR & 0xFF,
        STAGE1_ATTR_ROW_INIT_TAIL_ADDR >> 8,
    )
    front = a.finish()
    # The initializer is entered by JP, not CALL, so it can switch banked
    # WRAM without hiding a return address.  Build bank 2 first, repeat the
    # same generator in bank 3, then restore the stack's bank 1.
    opcode_group_address = STAGE1_ATTR_ROW_INIT_ADDR + 9
    tail = bytes([
        0xF0, 0x70, 0xE6, 0x07, 0xFE, 0x02, 0x20, 0x0C,
        0x3E, 0x03, 0xE0, 0x70,
        0x21,
        STAGE1_ATTR_ROW_HELPER_WRAM_ADDR & 0xFF,
        STAGE1_ATTR_ROW_HELPER_WRAM_ADDR >> 8,
        0x06, 0x18,
        0xC3, opcode_group_address & 0xFF, opcode_group_address >> 8,
        0x3E, 0xFF,
        0xEA, STAGE1_ATTR_CACHE_9800_ADDR & 0xFF,
        STAGE1_ATTR_CACHE_9800_ADDR >> 8,
        0xEA, STAGE1_ATTR_CACHE_9C00_ADDR & 0xFF,
        STAGE1_ATTR_CACHE_9C00_ADDR >> 8,
        0x3E, 0x01, 0xE0, 0x70,
        0xC3, OAM_LUT_INIT_ADDR & 0xFF, OAM_LUT_INIT_ADDR >> 8,
    ])
    assert len(front) <= 36 and len(tail) <= 36
    return front, tail


def build_oam_wram_copy_tail(
    postcomputed_attrs: bool = False,
) -> tuple[bytes, bytes]:
    """Finish the one-time WRAM/LUT initialization in bank 13.

    The common arena source helper is copied by the main stub. Two full
    semantic-cache fragments fill the tail's former padding; the first arena
    call installs only the short final fragment.
    """
    init_addr = (
        STAGE1_ATTR_ROW_INIT_ADDR if postcomputed_attrs else OAM_LUT_INIT_ADDR
    )
    semantic_runtime_length = len(build_arena_attr_semantic_runtime())
    semantic_middle_length = min(36, semantic_runtime_length - 36)
    semantic_tail_length = semantic_runtime_length - 36 - semantic_middle_length
    assert 0 < semantic_middle_length <= 36 and 0 <= semantic_tail_length <= 36
    semantic_prefix = bytes([
        0x11, ARENA_ATTR_SEMANTIC_RUNTIME_ADDR & 0xFF,
        ARENA_ATTR_SEMANTIC_RUNTIME_ADDR >> 8,
        0x21, ARENA_ATTR_SEMANTIC_SIG_A_ADDR & 0xFF,
        ARENA_ATTR_SEMANTIC_SIG_A_ADDR >> 8,
        0x0E, 36,
        0xCD, 0xB3, 0x09,
        0x21, ARENA_ATTR_SEMANTIC_SIG_B_ADDR & 0xFF,
        ARENA_ATTR_SEMANTIC_SIG_B_ADDR >> 8,
        0x0E, semantic_middle_length,
        0xCD, 0xB3, 0x09,
    ])
    if semantic_tail_length:
        semantic_prefix += bytes([
            0x11, (ARENA_ATTR_SEMANTIC_RUNTIME_ADDR + 72) & 0xFF,
            (ARENA_ATTR_SEMANTIC_RUNTIME_ADDR + 72) >> 8,
            0x21, ARENA_ATTR_SEMANTIC_COMPARE_ADDR & 0xFF,
            ARENA_ATTR_SEMANTIC_COMPARE_ADDR >> 8,
            0x0E, semantic_tail_length,
            0xCD, 0xB3, 0x09,
        ])
    final = bytes([
        0xCD, init_addr & 0xFF, init_addr >> 8,
        0x3E, OAM_WRAM_SENTINEL_VALUE,
        0xEA, OAM_WRAM_SENTINEL_ADDR & 0xFF,
        OAM_WRAM_SENTINEL_ADDR >> 8,
        0xE1, 0xD1, 0xC1,
        0xC9,
    ])
    continuation = final
    front = semantic_prefix + bytes([
        0xC3, OAM_WRAM_COPY_TED_HELPER_CONT_ADDR & 0xFF,
        OAM_WRAM_COPY_TED_HELPER_CONT_ADDR >> 8,
    ])
    assert len(front) <= 36
    assert len(continuation) <= 36
    return front, continuation


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
    a.db(
        0x47,                               # B = new D880
        0xCD,
        CRYSTAL_PALETTE_REARM_ADDR & 0xFF,
        CRYSTAL_PALETTE_REARM_ADDR >> 8,
        0xEE, 0x0A,
        0xE0, ATTRACT_PRELUDE_FLAG_HRAM,    # zero only for Gargoyle $0A
        0x1E, 0x12,                         # default bounded repair count
        0x78, 0x3D,                         # A = new scene - 1
    )
    a.jr(0x28, "title")
    a.db(0x3D)                              # gameplay $02 -> zero
    a.jr(0x28, "gameplay")
    a.db(0xFE, 0x1A)                        # banner $1C - 2
    a.db(0xCC, 0x80, 0xFF)                  # banner transition OAM clear
    a.jr(0x18, "store_count")

    a.label("title")
    a.db(
        0xAF,
        0xEA, 0x08, 0xDF,                  # rearm both-map title cleaner
        0xCD, 0x80, 0xFF,                  # one transition-only OAM clear
    )
    a.jr(0x18, "store_count")

    a.label("gameplay")
    # Arm the complete gameplay palette pass immediately on Stage 1 entry.
    # The fade-aware scheduler waits for native BGP=$E4, but no longer loses
    # up to seven idle-probe frames before beginning the bounded 17 phases.
    # Tag the cold attribute sweep here, after native FFBD rearm and at the
    # exact scene transition; the earlier splash-side tag was overwritten by
    # this service's ordinary $12 publication before it could be consumed.
    a.db(
        # DCFD is zero only for prerecorded dungeon play. Its first prelude
        # has now selected the table; keep later demo VBlanks at stock cadence.
        # Live gameplay retains its nonzero discriminator as the armed flag.
        0xFA, 0xFD, 0xDC,
        0xE0, ATTRACT_PRELUDE_FLAG_HRAM,
        0x3E, 0x11,
        0xEA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        0x1E, 0x7F,                         # third bank-1 upload marker
    )

    a.label("store_count")
    a.db(
        0x2E, BG_SWEEP_COUNT_ADDR & 0xFF,  # H remains the $DF page
        0x73,                               # LD [HL],E
        # Restore the footer's native digit before any helper below can reuse
        # B. Bit 1 includes Stage 1 while excluding both title identities;
        # later calls are harmless because the helper is signature-guarded.
        0xCB, 0x48,
        0xC4, NATIVE_GLYPH_RESTORE_ADDR & 0xFF,
        NATIVE_GLYPH_RESTORE_ADDR >> 8,
        # This service runs only on scene changes, so clearing the tiny story
        # identity cache unconditionally is safe and saves the old FFC1 guard.
        0xCD, STORY_INACTIVE_HELPER_ADDR & 0xFF,
        STORY_INACTIVE_HELPER_ADDR >> 8,
        0xE1, 0xD1, 0xC1, 0xF1, 0xC9,
    )
    code = a.finish()
    assert len(code) == LAVA_ATTR_DECIDER_CONT_ADDR - TITLE_TRANSITION_SERVICE_ADDR
    return code


def build_crystal_palette_rearm() -> bytes:
    """Arm the bounded material prepass only for Crystal Dragon.

    Crystal needs its scene-local OBJ4-7 ghost palette before the native fade
    completes.  Other bosses already have their global CRAM rows resident;
    rearming them here overlaps the first arena-map publication and can expose
    Ted's numbered staging cells at the physical edges.  A is preserved; HL
    is scratch because the transition service restores its caller's HL.
    """
    if _os.environ.get("PENTA_TED_NATIVE_POSTCOPY", "0") == "1" and (
        _os.environ.get("PENTA_TED_CACHED_FULL_PLANE", "0") != "1"
        and _os.environ.get("PENTA_TED_WRITER_MIRROR", "0") != "1"
    ):
        # Native-postcopy mode needs the same transition-only call to advance
        # Ted's LUT generation. The private dispatcher retains Crystal's
        # original behavior and preserves A for the title transition service.
        code = bytes([
            0xC3, TED_POSTCOPY_SCENE_DISPATCH_ADDR & 0xFF,
            TED_POSTCOPY_SCENE_DISPATCH_ADDR >> 8,
        ]) + bytes(6)
    else:
        code = bytes([
            0xFE, CRYSTAL_DRAGON_SCENE, 0xC0,  # RET NZ outside Crystal
            0x21, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
            0x36, 0x11,                    # Crystal OBJ prepass, then rows
            0xC9,
        ])
    assert len(code) == SPOTLIGHT_PALETTE_MAP_ADDR - CRYSTAL_PALETTE_REARM_ADDR
    return code


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
    # The unchanged-scene detector returns A=D880. Scene $0A shares the
    # preceding Stage-1 demo table and needs no transition-only menu work, but
    # it must still call scene_detect: that one-time transition owns the
    # post-miniboss hazard-hook contract.
    c.extend([0xFE, 0x0A, 0xC8])              # CP $0A; RET Z
    c.extend([0xFE, 0x0C])                    # dungeon-family upper bound
    j_preserve_high_scene = len(c) + 1
    c.extend([0x30, 0x00])                    # JR NC,preserve table
    c.extend([0xFE, 0x02])
    j_not_later_lo = len(c) + 1
    c.extend([0x38, 0x00])                    # JR C,not_later
    c.extend([0xF0, 0xBA, 0xB7])              # LDH A,[FFBA]; OR A
    j_not_later_stage1 = len(c) + 1
    c.extend([0x28, 0x00])                    # JR Z,not_later
    # Stage 1 takes the branch above with exactly its receipt-proven cadence.
    # The out-of-line helper preserves FFBA while checking the phase and then
    # compiles its YAML source from the adjacent six-byte table.
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
        0x23, 0x2B,                         # receipt-locked flag/cycle state
        0xC3,
        ARENA_ATTR_SEMANTIC_CHANGED_ADDR & 0xFF,
        ARENA_ATTR_SEMANTIC_CHANGED_ADDR >> 8,
    ])

    # The live branch is out of line so the rare menu repair can fall straight
    # into window maintenance. These three receipt-locked bytes are part of
    # the proven hazard phase; even removing only the NOP advances the rotating
    # publisher enough to leave a persistent gray body cell.
    live_cfaa = len(c)
    c[j_live_cfaa] = (live_cfaa - j_live_cfaa - 1) & 0xFF
    c.extend([0x00, 0x23, 0x2B])            # receipt-locked flag/cycle state
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
    c.extend([0x05, 0xC0])                # DEC B; returned title iff B was 1
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
        # Any nonzero value re-arms the guarded prelude after Gargoyle returns
        # to title. CGB title paths do not consume A after this point.
        0x2F,
        0xE0, ATTRACT_PRELUDE_FLAG_HRAM,
        # 20T clear + 32T balance exactly replaces the old 52T delay call.
        # PUSH/POP preserves C; wrapper teardown restores the caller's B.
        0xC5, 0xC1, 0x00,
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
        0x3E, 0xE4,                         # active play always uses DMG order
        0xE0, 0x47,                         # LDH [BGP],A
        0xC9,                               # RET
    ])
    assert len(code) == 13
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
        # Native BGP transitions own CRAM until the normal $E4 order returns.
        # Servicing under black perturbs the arena publisher's interrupt
        # schedule and can expose numbered Ted staging cells at map edges.
        0xF0, 0x47, 0xFE, 0xE4, 0xC0,
        0xFA, PALETTE_PHASE_ADDR & 0xFF,
        PALETTE_PHASE_ADDR >> 8,            # A = pending phase
        0xB7,                               # OR A
        0xC2, PALETTE_LOADER_ADDR & 0xFF,
        PALETTE_LOADER_ADDR >> 8,           # pending: service every VBlank
        0xF0, 0xD4,                         # idle: stock VBlank tick
        0xE6, 0x07,                         # probe once per eight frames
        0xC0,
        0xCD,
        OAM_BOSS_LUT_SERVICE_ADDR & 0xFF,
        OAM_BOSS_LUT_SERVICE_ADDR >> 8,
        # FFBE only selects between two already-resident Sara rows; it does
        # not own CRAM. Start with the miniboss flag instead.
        0xF0, 0xBF, 0x47,                  # B = FFBF
        0xF0, 0xC0, 0xA8, 0x47,            # B ^= FFC0
        0xF0, 0xD0, 0xA8, 0x47,            # B ^= FFD0
        # FFBA starts ordinary stage/boss passes early. Crystal's scene-local
        # material pass is armed synchronously by the scene-change service:
        # the native boss fade stops this idle probe's FFD4 clock, and D880
        # also exposes transient $FF map-handoff sentinels in live arenas.
        0xF0, 0xBA, 0xA8, 0x3C, 0x47,      # B = (B ^ FFBA) + 1
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
        <= CRYSTAL_PALETTE_REARM_ADDR
    )
    return bytes(c)


def build_phased_palette_loader(
    crystal_obj_slots: tuple[int, ...] = (4, 5, 6, 7),
    crystal_obj_source_addr: int = 0x6898,
    crystal_scene: int = CRYSTAL_DRAGON_SCENE,
) -> tuple[bytes, bytes, bytes, bytes]:
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
    main.jr(0x28, "boss_first")             # phase 17
    main.db(0xFE, 0x01)
    main.jr(0x38, "palette_done")           # phase 0/invalid
    main.db(0xFE, 0x09)
    main.jr(0x38, "obj_phase")              # phases 1..8
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
        0x7B, 0x07, 0x07, 0x07,            # A = slot * 8
        0xC6, 0x40, 0x6F, 0x26, 0x68,      # HL = $6840 + slot*8
        0x7B, 0xB7,                        # slot 0?
    )
    main.jr(0x28, "obj0_variant")
    main.db(0xFE, 0x03)
    main.jr(0x38, "obj_low_variant")        # slots 1/2 can use jet rows
    assert crystal_obj_slots == (4, 5, 6, 7)
    main.db(0xCB, 0x53)                    # Crystal material slots 4..7?
    main.jr(0x28, "obj_source_ready")       # slots 3/ordinary use base source
    # FFB7 is the true scene-context publisher behind D880. Unlike FFBA, it
    # cannot alias ordinary Stage 3 to Crystal's arena.
    main.db(0xF0, 0xB7, 0xFE, crystal_scene)
    main.jr(0x20, "obj_source_ready")
    main.db(0x2E, crystal_obj_source_addr & 0xFF)
    main.jr(0x18, "obj_source_ready")

    main.label("obj_low_variant")
    main.db(0xF0, 0xD0, 0x3D)
    main.jr(0x20, "obj_source_ready")
    main.db(0x7B, 0x3D)
    main.jr(0x20, "obj2_jet")
    main.db(0x2E, 0xD8)                    # OBJ1 dragon jet (H already $68)
    main.jr(0x18, "obj_source_ready")
    main.label("obj2_jet")
    main.db(0x2E, 0xD0)                    # OBJ2 witch jet (H already $68)
    main.jr(0x18, "obj_source_ready")

    main.label("obj0_variant")
    main.db(0xF0, 0xC0, 0xB7)
    main.jr(0x28, "obj_source_ready")
    main.db(0xFE, 0x01)
    main.jr(0x20, "obj0_check_shield")
    main.db(0x2E, 0xE0)                    # H already $68
    main.jr(0x18, "obj_source_ready")
    main.label("obj0_check_shield")
    main.db(0xFE, 0x02)
    main.jr(0x20, "obj0_turbo")
    main.db(0x2E, 0xE8)                    # H already $68
    main.jr(0x18, "obj_source_ready")
    main.label("obj0_turbo")
    main.db(0x2E, 0xF0)                    # H already $68

    main.label("obj_source_ready")
    main.db(0x7B, 0x87, 0x87, 0x87, 0xF6, 0x80)
    main.absolute(0xCD, "copy_obj")

    main.label("obj_advance")
    main.db(0x7B, 0xC6, 0x02)              # next phase = slot + 2
    main.jr(0x18, "store_phase")

    main.label("boss_first")
    main.absolute(0xCD, "load_boss")
    main.db(0x3E, 0x01)
    main.jr(0x18, "store_phase")

    main.label("load_boss")
    main.db(0xF0, 0xBF, 0xB7, 0xC8)        # no active boss -> RET Z
    main.db(
        0x3D, 0x5F, 0x4F, 0x06, 0x00,     # E/C = boss index
        0x21, BOSS_SLOT_TABLE_ADDR & 0xFF,
        BOSS_SLOT_TABLE_ADDR >> 8,
        0x09, 0x7E,
        0x87, 0x87, 0x87, 0xF6, 0x80,     # destination OBJ slot
        0xF5,
        0x7B, 0x07, 0x07, 0x07,
        0xC6, 0x80, 0x6F, 0x26, 0x68,      # boss palette source
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
        # Only Stage 1 ($02) and its Gargoyle combat overlay ($0A) own the
        # rotating-tooth BG7 row. The former FFC1/FFD0 gameplay-family test
        # also matched every main boss and made Troop inherit neon spike gold.
        # Normalize bit 3 so both Stage-1 identities select the hazard row;
        # all other gameplay/title/story scenes retain the tuneable YAML BG7.
        0xFA, 0x80, 0xD8, 0xE6, 0xF7, 0xFE, 0x02,
    )
    ext.jr(0x20, "bg_source_ready")
    ext.db(
        0x2E, STAGE1_HAZARD_BG7_SOURCE_ADDR & 0xFF,
    )
    ext.label("bg_source_ready")
    # The normalized scene test is four cycles shorter on both branches than
    # the old family test. One shared NOP preserves the proven 60T/72T paths.
    ext.db(0x00, 0x7B, 0x87, 0x87, 0x87, 0xF6, 0x80)
    ext.absolute(0xCD, "copy_bg")
    ext.db(0x7A, 0xFE, 0x07)
    ext.absolute(0xCA, "palette_done")
    ext.db(0xC6, 0x0A)                    # next phase = slot + 10
    ext.absolute(0xC3, "store_phase")

    # Preserve the receipt-proven 28-cycle non-slot padding exactly. Later
    # dungeons repair BG0 after the slot-0 loader phase in the prelude.
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
    later_stage_bg0_selector = bytes([
        # Preserve FFBA, then repair only immediately after the loader advanced
        # past BG0. The just-completed BG copy leaves C=$69 through the wrapper
        # and scene detector, saving the two-byte LD C immediate needed below.
        0x5F,
        0xFA, PALETTE_PHASE_ADDR & 0xFF, PALETTE_PHASE_ADDR >> 8,
        0xFE, 0x0C, 0xC0,
        0x7B,
        0xC6, (LATER_STAGE_BG0_SOURCE_TABLE_ADDR - 1) & 0xFF,
        0x6F,
        0x26, LATER_STAGE_BG0_SOURCE_TABLE_ADDR >> 8,
        0x5E,
        # Force the compiled YAML source row into hardware BG0.
        0x3E, 0x80, 0xE0, 0x68,
        0x6B, 0x26, 0x68,
        0xC3, PALETTE_COPY_CRAM8_ADDR & 0xFF,
        PALETTE_COPY_CRAM8_ADDR >> 8,
    ])
    assert len(later_stage_bg0_selector) == 24
    return (
        main_code,
        ext_code,
        copy_cram8_code,
        later_stage_bg0_selector,
    )


def load_later_stage_bg0_sources(path: Path) -> tuple[bytes, list[str]]:
    """Compile the Stage 2-7 YAML identities to palette-source low bytes."""
    document = yaml.safe_load(Path(path).read_text())
    bg_palettes = document.get("bg_palettes", {})
    assignments = document.get("later_stage_bg0_palettes", {})
    stage_names = [f"Stage{stage}" for stage in range(2, 8)]
    assert list(assignments) == stage_names, (
        "later_stage_bg0_palettes must define ordered Stage2..Stage7 entries"
    )
    slots = {name: index for index, name in enumerate(bg_palettes)}
    selected = [str(assignments[name]) for name in stage_names]
    assert all(name in slots for name in selected), (
        "later-stage BG0 assignments must name an existing bg_palettes row"
    )
    return bytes(slots[name] * 8 for name in selected), selected


def load_crystal_obj_palette_override(
    path: Path,
) -> tuple[int, tuple[int, ...], int, str]:
    """Compile Crystal Dragon's scene-local OBJ row reference from YAML."""
    document = yaml.safe_load(Path(path).read_text())
    overrides = document.get("arena_obj_palette_overrides", {})
    entry = overrides.get("CrystalDragonGhost", {})
    scene = int(entry.get("scene", -1))
    slots = tuple(int(slot) for slot in entry.get("slots", ()))
    source_name = str(entry.get("source_boss_palette", ""))
    boss_names = list(document.get("boss_palettes", {}))
    assert scene == CRYSTAL_DRAGON_SCENE, (
        "CrystalDragonGhost scene must remain $0E"
    )
    assert slots == (4, 5, 6, 7), (
        "Crystal Dragon's traced body spans OBJ slots 4..7"
    )
    assert source_name in boss_names, (
        "CrystalDragonGhost must reference an existing boss_palettes row"
    )
    source_addr = 0x6880 + boss_names.index(source_name) * 8
    assert source_addr >> 8 == 0x68
    return scene, slots, source_addr, source_name


def build_later_stage_bg0_arm() -> bytes:
    """Enter the later-dungeon-only BG0/LUT/pickup transition service."""
    code = bytes([
        0xC3,
        LATER_PICKUP_HELPER_TAIL_ADDR & 0xFF,
        LATER_PICKUP_HELPER_TAIL_ADDR >> 8,
    ])
    assert len(code) == 3
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
    disable_stage1_hazard_source_hook: bool = False,
    demo_pickup_writer_phase_nops: int = DEMO_PICKUP_WRITER_PHASE_NOPS,
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
    vanilla = Path("rom/Penta Dragon (J).gb").read_bytes()
    tuned_palettes = load_palettes_from_yaml(palette_yaml)
    cutscene_panels = load_cutscene_region_palettes(palette_yaml)
    later_stage_bg0_sources, later_stage_bg0_names = (
        load_later_stage_bg0_sources(palette_yaml)
    )
    (
        crystal_scene,
        crystal_obj_slots,
        crystal_obj_source_addr,
        crystal_obj_source_name,
    ) = load_crystal_obj_palette_override(palette_yaml)
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
    later_stage_source_off = (
        BANK13 + LATER_STAGE_BG0_SOURCE_TABLE_ADDR - 0x4000
    )
    assert (
        LATER_STAGE_BG0_SOURCE_TABLE_ADDR + len(later_stage_bg0_sources)
        <= LAVA_ATTR_STAGE7_SOURCE_A_ADDR
    )
    # The base build still carries six stock bytes in this range.  Qualify
    # them now; the generated-posmap reset below establishes the final owned
    # padding before the table is installed.
    assert rom[
        later_stage_source_off:
        later_stage_source_off + len(later_stage_bg0_sources)
    ] == vanilla[
        later_stage_source_off:
        later_stage_source_off + len(later_stage_bg0_sources)
    ] == bytes.fromhex("87 78 FF 00 00 FF"), (
        "later-stage BG0 source table dispatcher tail changed"
    )
    print(
        "  later-stage BG0 identities: "
        + ", ".join(
            f"Stage {stage}={name}"
            for stage, name in zip(range(2, 8), later_stage_bg0_names)
        )
    )
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
        later_stage_bg0_selector,
    ) = build_phased_palette_loader(
        crystal_obj_slots=crystal_obj_slots,
        crystal_obj_source_addr=crystal_obj_source_addr,
        crystal_scene=crystal_scene,
    )
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
    # The new palette loader retires the base build's old $69B8-$69CF tail.
    # Reuse that now-unreachable gap for the later-stage BG0 selector.
    assert (
        PALETTE_LOADER_ADDR + len(palette_loader)
        == LATER_STAGE_BG0_REPAIR_ADDR
    )
    later_stage_bg0_repair_off = (
        BANK13 + (LATER_STAGE_BG0_REPAIR_ADDR - 0x4000)
    )
    assert (
        LATER_STAGE_BG0_REPAIR_ADDR + len(later_stage_bg0_selector)
        <= DEATH_FADE_HELPER_ADDR
    )
    rom[
        later_stage_bg0_repair_off:
        later_stage_bg0_repair_off + len(later_stage_bg0_selector)
    ] = later_stage_bg0_selector
    print(
        "  Crystal Dragon ghost palette: "
        f"scene ${crystal_scene:02X} OBJ{crystal_obj_slots[0]}-"
        f"{crystal_obj_slots[-1]} <- "
        f"boss_palettes.{crystal_obj_source_name} "
        f"(${crystal_obj_source_addr:04X})"
    )

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
    crystal_palette_rearm = build_crystal_palette_rearm()
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
        "  later-stage identity: YAML rows own Stage 2/4/6 BG0 while the "
        "scene LUT remains neutral "
        f"({len(later_stage_bg0_selector)} bytes at "
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

    # 5b. Transition-only semantic pickup publisher for Stages 2-7. These
    # adjacent fixed-size records are the same native-zero resource padding
    # family as the proven level-select stub above; assert the untouched base
    # image before claiming either one.
    (
        later_pickup_front,
        later_pickup_aux,
        later_pickup_tail,
        stage4_material,
    ) = build_later_stage_pickup_helper()
    for address, code in (
        (LATER_PICKUP_HELPER_FRONT_ADDR, later_pickup_front),
        (LATER_PICKUP_HELPER_AUX_ADDR, later_pickup_aux),
        (LATER_PICKUP_HELPER_TAIL_ADDR, later_pickup_tail),
    ):
        off = BANK13 + (address - 0x4000)
        assert rom[off:off + LATER_PICKUP_HELPER_CAVE_SIZE] == bytes(
            LATER_PICKUP_HELPER_CAVE_SIZE
        ), f"later pickup helper cave at ${address:04X} is no longer free"
        rom[off:off + len(code)] = code
    native_ted_postcopy = _os.environ.get(
        "PENTA_TED_NATIVE_POSTCOPY", "0"
    ) == "1"
    cached_ted_full_plane = _os.environ.get(
        "PENTA_TED_CACHED_FULL_PLANE", "0"
    ) == "1"
    cached_ted_install_only = _os.environ.get(
        "PENTA_TED_CACHED_INSTALL_ONLY", "0"
    ) == "1"
    ted_writer_mirror = _os.environ.get(
        "PENTA_TED_WRITER_MIRROR", "0"
    ) == "1"
    ted_incremental_key = _os.environ.get(
        "PENTA_TED_INCREMENTAL_KEY", "0"
    ) == "1"
    ted_direct_plane = _os.environ.get(
        "PENTA_TED_DIRECT_PLANE", "0"
    ) == "1"
    ted_hdma_piggyback = _os.environ.get(
        "PENTA_TED_HDMA_PIGGYBACK", "0"
    ) == "1"
    ted_inwindow_gdma = _os.environ.get(
        "PENTA_TED_INWINDOW_GDMA", "0"
    ) == "1"
    ted_incremental_cell = _os.environ.get(
        TED_INCREMENTAL_CELL_ENV, "0"
    ) == "1"
    ted_block_major = _os.environ.get(TED_BLOCK_MAJOR_ENV, "0") == "1"
    expanded_ted_payload = (
        _os.environ.get("PENTA_TED_EXPANDED_PAYLOAD", "0") == "1"
    )
    expanded_ted_production = (
        _os.environ.get("PENTA_TED_EXPANDED_PRODUCTION", "0") == "1"
    )
    assert not (expanded_ted_payload and expanded_ted_production), (
        "expanded Ted payload and production roles are mutually exclusive"
    )
    assert not ted_block_major or (
        ted_direct_plane and ted_inwindow_gdma and ted_incremental_cell
    ), (
        "PENTA_TED_BLOCK_MAJOR requires PENTA_TED_DIRECT_PLANE=1, "
        "PENTA_TED_INWINDOW_GDMA=1, and PENTA_TED_INCREMENTAL_CELL=1"
    )
    assert not ted_hdma_piggyback or ted_direct_plane, (
        "Ted HBlank piggyback requires the maintained direct plane"
    )
    assert not ted_inwindow_gdma or ted_direct_plane, (
        "Ted in-window GDMA requires the maintained direct plane"
    )
    assert not ted_incremental_cell or ted_inwindow_gdma, (
        "Ted incremental cell classifier requires in-window GDMA"
    )
    assert not (ted_hdma_piggyback and ted_inwindow_gdma), (
        "choose only one Ted direct-plane publisher"
    )
    assert not (ted_incremental_key and ted_direct_plane), (
        "choose either the incremental checksum or direct-plane experiment"
    )
    ted_incremental_key = ted_incremental_key or ted_direct_plane
    ted_writer_track_only = _os.environ.get(
        "PENTA_TED_WRITER_TRACK_ONLY", "0"
    ) == "1"
    ted_writer_install_only = _os.environ.get(
        "PENTA_TED_WRITER_INSTALL_ONLY", "0"
    ) == "1"
    assert not ted_writer_track_only or ted_writer_mirror, (
        "Ted writer tracking isolation requires the writer mirror"
    )
    assert not ted_writer_install_only or ted_writer_mirror, (
        "Ted writer installer isolation requires the writer mirror"
    )
    native_ted_postcopy = (
        native_ted_postcopy or cached_ted_full_plane or ted_writer_mirror
        or ted_incremental_key
    )
    assert not ted_incremental_key or (
        native_ted_postcopy and not cached_ted_full_plane
        and not ted_writer_mirror
    ), "incremental Ted key requires the native-postcopy cache lane"
    assert (
        not native_ted_postcopy
        or cached_ted_full_plane
        or stock_tile_copy
        or compact_tile_copy
    ), (
        "Ted native postcopy requires a pure tile-copy baseline"
    )
    arena_geometry = (
        (build_arena_atomic_attr_stack_helper()
         if cached_ted_full_plane else
         bytes.fromhex("CD 95 42 C9") if ted_writer_track_only else
         build_ted_writer_mirror_wrapper(
             TED_WRITER_RUNTIME_ADDR
             + build_ted_writer_mirror_runtime()[1]
         ) if ted_writer_mirror else build_ted_native_postcopy_wrapper())
        if native_ted_postcopy else build_arena_atomic_attr_stack_helper()
    )
    if ted_hdma_piggyback:
        arena_geometry = (
            build_ted_hdma_piggyback_gate()
            + build_ted_hdma_piggyback_postcopy()
        )
        assert len(arena_geometry) == LATER_PICKUP_HELPER_CAVE_SIZE
    elif ted_inwindow_gdma:
        arena_geometry = (
            build_ted_inwindow_gate()
            + build_ted_hdma_piggyback_postcopy()
        )
        assert len(arena_geometry) <= LATER_PICKUP_HELPER_CAVE_SIZE
    arena_geometry_off = (
        BANK13 + ARENA_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR - 0x4000
    )
    assert rom[
        arena_geometry_off:
        arena_geometry_off + LATER_PICKUP_HELPER_CAVE_SIZE
    ] == bytes(LATER_PICKUP_HELPER_CAVE_SIZE), (
        "arena geometry helper source cave is no longer free"
    )
    rom[
        arena_geometry_off:arena_geometry_off + len(arena_geometry)
    ] = arena_geometry
    arena_semantic_fragments = build_arena_attr_semantic_decider()
    for address, capacity, payload in (
        (
            ARENA_ATTR_SEMANTIC_DISPATCH_ADDR,
            ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
            arena_semantic_fragments[0],
        ),
        (
            ARENA_ATTR_SEMANTIC_SIG_A_ADDR,
            ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
            arena_semantic_fragments[1],
        ),
        (
            ARENA_ATTR_SEMANTIC_SIG_B_ADDR,
            ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
            arena_semantic_fragments[2],
        ),
        (
            ARENA_ATTR_SEMANTIC_COMPARE_ADDR,
            ARENA_ATTR_SEMANTIC_FRAGMENT_SIZE,
            arena_semantic_fragments[3],
        ),
        (
            ARENA_ATTR_SEMANTIC_CHANGED_ADDR,
            34,
            arena_semantic_fragments[4],
        ),
    ):
        fragment_off = BANK13 + address - 0x4000
        assert rom[fragment_off:fragment_off + capacity] == bytes(capacity), (
            f"arena semantic fragment cave at ${address:04X} is no longer free"
        )
        rom[fragment_off:fragment_off + len(payload)] = payload
    print(
        "  later-stage semantic pickups: "
        f"stage-specific tile IDs ({len(later_pickup_front)}+"
        f"{len(later_pickup_aux)}+{len(later_pickup_tail)} bytes at bank13:"
        f"0x{LATER_PICKUP_HELPER_FRONT_ADDR:04X}/"
        f"0x{LATER_PICKUP_HELPER_AUX_ADDR:04X}/"
        f"0x{LATER_PICKUP_HELPER_TAIL_ADDR:04X}; "
        f"Stage 4 materials={len(stage4_material)} split bytes; "
        f"arena geometry={len(arena_geometry)} bytes at bank13:"
        f"0x{ARENA_ATOMIC_ATTR_STACK_HELPER_ROM_ADDR:04X}; "
        f"arena semantic cache={'/'.join(str(len(part)) for part in arena_semantic_fragments)} "
        f"bytes from bank13:0x{ARENA_ATTR_SEMANTIC_DISPATCH_ADDR:04X})"
    )

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
        later_dungeon_service_addr=LATER_STAGE_BG0_ARM_ADDR,
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
        CUTSCENE_PALETTE_BRIDGE_ADDR + len(cutscene_palette_bridge)
        <= TITLE_DELAY_ADDR
        and TITLE_DELAY_ADDR + len(title_delay)
        <= CUTSCENE_PALETTE_BRIDGE_END
    ), "title-delay helper collides with cutscene bridge tail"
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
    assert rom[off:off + 0x100] == vanilla[off:off + 0x100], \
        "reclaimed bank-13 region changed in the base build"
    rom[off:off + 0x100] = bytes(0x100)
    rom[off:off + len(story_attr)] = story_attr
    # Bank-13 $4CE4-$4CF1 contains live, pointer-referenced stock records even
    # though every byte is zero.  Preserve those records exactly and use the
    # disabled fixed serial interrupt vector for the eight-byte bank bridge.
    live_record_off = BANK13 + (0x4CE4 - 0x4000)
    live_record_size = 0x4CF2 - 0x4CE4
    assert rom[
        live_record_off:live_record_off + live_record_size
    ] == vanilla[live_record_off:live_record_off + live_record_size], (
        "live bank-13 $4CE4-$4CF1 map records changed before story install"
    )
    story_region_bridge_off = STORY_REGION_FIXED_BRIDGE_ADDR
    assert len(story_region_bridge) == 8
    assert rom[
        story_region_bridge_off:
        story_region_bridge_off + len(story_region_bridge)
    ] == vanilla[
        story_region_bridge_off:
        story_region_bridge_off + len(story_region_bridge)
    ] == bytes.fromhex("D9 7D FB 7D FD ED BF FF"), (
        "fixed serial-vector story bridge slot changed"
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
        f"fixed:0x{STORY_REGION_FIXED_BRIDGE_ADDR:04X}, "
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
        == CRYSTAL_PALETTE_REARM_ADDR
        and CRYSTAL_PALETTE_REARM_ADDR + len(crystal_palette_rearm)
        == SPOTLIGHT_PALETTE_MAP_ADDR
    )
    assert (
        TITLE_TRANSITION_SERVICE_ADDR + len(title_transition)
        <= LAVA_ATTR_DECIDER_CONT_ADDR
    ), "title transition collides with the relocated lava decider"
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
    crystal_rearm_off = (
        BANK13 + (CRYSTAL_PALETTE_REARM_ADDR - 0x4000)
    )
    rom[
        crystal_rearm_off:crystal_rearm_off + len(crystal_palette_rearm)
    ] = crystal_palette_rearm
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
        "  Crystal scene-local palette rearm: "
        f"{len(crystal_palette_rearm)} bytes at bank13:"
        f"0x{CRYSTAL_PALETTE_REARM_ADDR:04X}"
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
    assert rom[
        later_stage_source_off:
        later_stage_source_off + len(later_stage_bg0_sources)
    ] == bytes(len(later_stage_bg0_sources)), (
        "generated later-stage BG0 source-table tail is not clear"
    )
    rom[
        later_stage_source_off:
        later_stage_source_off + len(later_stage_bg0_sources)
    ] = later_stage_bg0_sources
    if ted_incremental_key:
        for source_addr, source_payload in (
            build_ted_incremental_runtime_sources().items()
        ):
            source_off = BANK13 + source_addr - 0x4000
            current_source = bytes(
                rom[source_off:source_off + len(source_payload)]
            )
            if ted_block_major and (
                TED_TABLE_ADDR <= source_addr
                and source_addr + len(source_payload) <= TED_TABLE_ADDR + 0x100
            ):
                ted_table = bytes(_bg_table_ted())
                expected_source = ted_table[
                    source_addr - TED_TABLE_ADDR:
                    source_addr - TED_TABLE_ADDR + len(source_payload)
                ]
            else:
                expected_source = bytes(len(source_payload))
            assert current_source == expected_source, (
                f"Ted incremental source cave ${source_addr:04X} is not free: "
                f"{current_source.hex()}"
            )
            rom[source_off:source_off + len(source_payload)] = source_payload
    ptr_off = BANK13 + (POSMAP_PTR_TABLE - 0x4000)
    rom[ptr_off:ptr_off + 18] = bytes(18)
    rom[
        ptr_off:ptr_off + len(palette_copy_cram8)
    ] = palette_copy_cram8
    # Later-stage entry normally happens after the palette scheduler has gone
    # idle. Arm exactly its BG0 phase before clearing the neutral scene LUT;
    # on the following VBlank the loader copies BG0 and the phase-$0C repair
    # helper replaces it with the stage's YAML-selected row.
    later_stage_bg0_arm = build_later_stage_bg0_arm()
    assert LATER_STAGE_BG0_ARM_ADDR == PALETTE_COPY_CRAM8_ADDR + len(
        palette_copy_cram8
    )
    assert len(palette_copy_cram8) + len(later_stage_bg0_arm) <= 18
    rom[
        ptr_off + len(palette_copy_cram8):
        ptr_off + len(palette_copy_cram8) + len(later_stage_bg0_arm)
    ] = later_stage_bg0_arm
    print(
        "  Stage-1 BG7 selector: inline cycle-neutral title / normal YAML / "
        "hazard YAML; shared LCD-safe copier "
        f"({len(palette_copy_cram8)}/18 bytes at "
        f"bank13:0x{PALETTE_COPY_CRAM8_ADDR:04X})"
    )
    room_bg_repair = build_room_bg_repair(
        stage1_atomic_attrs=(not stock_tile_copy or native_room_writers),
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
    stage1_hazard_banked_entry13,
        stage1_hazard_banked_entry14,
    ) = build_stage1_hazard_banked_entries()
    arena_sanitizer_dispatch = build_arena_sanitizer_banked_dispatch(
        writer_mirror=ted_writer_mirror,
    )
    if not stock_tile_copy:
        stage1_hazard_banked_entry13 = bytes([
            0xC3, LAVA_ATTR_DECIDER_ADDR & 0xFF,
            LAVA_ATTR_DECIDER_ADDR >> 8,
        ])
    ted_sanitizer_fragments = {}
    if ted_writer_mirror:
        # The tracker is ROM-resident; Ted overwrites both C400 and C500.
        # Only the sparse banked-plane publisher needs fragmented bank-13
        # resource records.
        ted_sanitizer_fragments.update(build_ted_dirty_postcopy_fragments())
    elif cached_ted_full_plane:
        ted_sanitizer_fragments.update(build_ted_cached_full_plane_fragments())
        ted_sanitizer_fragments[TED_CACHED_READY_LATCH_ADDR] = (
            build_ted_cached_ready_latch()
        )
        ted_sanitizer_fragments[TED_CACHED_PALETTE_GATE_ADDR] = (
            build_ted_cached_palette_gate()
        )
        if _os.environ.get("PENTA_TED_CACHED_SPARSE", "0") != "0":
            ted_sanitizer_fragments.update(build_ted_cached_sparse_fragments())
    elif native_ted_postcopy:
        if ted_incremental_key:
            ted_sanitizer_fragments.update(
                build_ted_incremental_postcopy_attr_compiler()
            )
            ted_sanitizer_fragments.update(
                build_ted_incremental_scene_installer()
            )
            ted_sanitizer_fragments.update(
                build_ted_incremental_scene_rearm_fragments()
            )
            if ted_hdma_piggyback:
                piggyback_fragments = build_ted_hdma_piggyback_copier()
                assert not (
                    set(piggyback_fragments) & set(ted_sanitizer_fragments)
                ), "Ted piggyback fragments overlap the direct-plane runtime"
                ted_sanitizer_fragments.update(piggyback_fragments)
            elif ted_inwindow_gdma:
                inwindow_fragments = build_ted_inwindow_copier()
                assert not (
                    set(inwindow_fragments) & set(ted_sanitizer_fragments)
                ), "Ted in-window fragments overlap direct-plane runtime"
                ted_sanitizer_fragments.update(inwindow_fragments)
        else:
            ted_sanitizer_fragments.update(
                build_ted_compact_postcopy_attr_compiler()
            )
            ted_sanitizer_fragments.update(
                build_ted_postcopy_scene_rearm_fragments()
            )
    else:
        ted_sanitizer_runtime = build_ted_group_sanitizer_wram()
        ted_runtime_sources = (
            TED_SANITIZER_MAIN_ADDR, TED_SANITIZER_CLASSIFY_ADDR,
            TED_SANITIZER_CROWN_ADDR, TED_SANITIZER_ACTIVE_ADDR,
            TED_SANITIZER_ROW_TABLE_ADDR, TED_SANITIZER_GEOMETRY_CONT_ADDR,
            TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR,
            TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR,
        )
        cursor = 0
        for source in ted_runtime_sources:
            capacity = (
                21 if source == TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR
                else 20 if source == TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR
                else ARENA_SANITIZER_FRAGMENT_SIZE
            )
            chunk = ted_sanitizer_runtime[cursor:cursor + capacity]
            if source == TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR:
                chunk = chunk.rstrip(b"\x00")
            if chunk and any(chunk):
                ted_sanitizer_fragments[source] = chunk
            cursor += capacity
        assert cursor == len(ted_sanitizer_runtime)
        materializer = build_ted_register_materializer()
        ted_sanitizer_fragments.update({
            TED_REGISTER_MATERIALIZER_FRONT_ADDR: materializer[0],
            TED_REGISTER_MATERIALIZER_TAIL_ADDR: materializer[1],
            TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR: materializer[2],
            TED_TILE_COMMIT_RUNTIME_ADDR: build_native_tile_materializer(),
            TED_CHECKER_ATTR_HELPER_ADDR: build_ted_checker_attr_helper(),
        })
        ted_crown_pair, ted_crown_pair_cont = build_ted_crown_pair_helper()
        ted_sanitizer_fragments[TED_CROWN_PAIR_HELPER_ADDR] = ted_crown_pair
        ted_sanitizer_fragments[TED_CROWN_PAIR_HELPER_CONT_ADDR] = (
            ted_crown_pair_cont
        )
        (
            ted_installer_front,
            ted_installer_middle,
            ted_installer_tail,
            ted_installer_final,
        ) = build_ted_group_sanitizer_installer()
        ted_sanitizer_fragments.update({
            TED_SANITIZER_INSTALL_ADDR: ted_installer_front,
            TED_SANITIZER_INSTALL_MIDDLE_ADDR: ted_installer_middle,
            TED_SANITIZER_INSTALL_TAIL_ADDR: ted_installer_tail,
            TED_SANITIZER_INSTALL_FINAL_ADDR: ted_installer_final,
        })
    shalamar_sanitizer_fragments = build_shalamar_source_sanitizer_fragments()
    (
        stage1_hazard_row_helper,
        stage1_hazard_row_compiler,
    ) = build_stage1_hazard_row_helper()
    stage1_hazard_bank1_neutral_art = (
        build_stage1_hazard_bank1_neutral_art(rom)
    )
    assert len(stage1_hazard_bank1_neutral_art) == 64
    (
        stage1_hazard_bank14_copy,
        stage1_hazard_bank7_copy,
        stage1_hazard_bank7_copy_middle,
        stage1_hazard_bank7_copy_tail,
    ) = build_stage1_hazard_bank1_copy_routines()
    stage1_hazard_bank1_loader = build_stage1_hazard_bank1_loader()
    stage1_entry_patch_gate = build_stage1_entry_patch_gate()
    stage1_lut_off = BANK13 + DUNGEON_TABLE_ADDR - 0x4000
    (
        stage1_entry_patch_body,
        stage1_entry_patch_tail,
        stage1_entry_patch_finish,
        stage1_entry_patch_lower,
    ) = build_stage1_entry_attr_patch(
        bytes(rom[stage1_lut_off:stage1_lut_off + 256])
    )
    cold_stage1_sweep_arm, cold_stage1_sweep_arm_tail = (
        build_cold_stage1_sweep_arm()
    )
    stage1_hazard_bank1_bank14_loader = (
        build_stage1_hazard_bank1_bank14_loader()
    )
    (
        stage1_hazard_scanner_front,
        stage1_hazard_scanner_middle,
        stage1_hazard_scanner_tail,
        stage1_hazard_scanner_seam,
    ) = build_stage1_hazard_dynamic_scanner()
    stage1_hazard_transition_repair = build_stage1_hazard_transition_repair()
    stage1_hazard_room12_wall_repair = (
        build_stage1_hazard_room12_wall_repair()
    )
    (
        stage1_hazard_start4_helper,
        stage1_hazard_start4_edge,
    ) = build_stage1_hazard_start4_edge_helpers()
    (
        stage1_hazard_row0_repair_front,
        stage1_hazard_row0_repair_middle,
        stage1_hazard_row0_repair_tail,
    ) = build_stage1_hazard_row0_transition_repair()
    stage1_hazard_room_dispatcher = build_stage1_hazard_room_dispatcher()
    oam_wram_copy_tail13, oam_wram_copy_ted_helper_cont = build_oam_wram_copy_tail(
        postcomputed_attrs=True,
    )
    if True:
        stage1_attr_row_init_front, stage1_attr_row_init_tail = (
            build_stage1_attr_row_initializer()
        )
        for address, payload in (
            (STAGE1_ATTR_ROW_INIT_ADDR, stage1_attr_row_init_front),
            (STAGE1_ATTR_ROW_INIT_TAIL_ADDR, stage1_attr_row_init_tail),
        ):
            initializer_off = BANK13 + address - 0x4000
            assert rom[
                initializer_off:initializer_off + len(payload)
            ] == bytes(len(payload)), (
                f"postcomputed row-initializer cave ${address:04X} is not free"
            )
            rom[initializer_off:initializer_off + len(payload)] = payload
    (
        demo_pickup_scanner,
        demo_pickup_appender,
        demo_pickup_table,
    ) = build_demo_pickup_scanner()
    (
        demo_pickup_writer,
        demo_pickup_writer_tail,
        demo_pickup_phase_writer,
        demo_pickup_phase_writer_tail,
    ) = build_demo_pickup_writer(demo_pickup_writer_phase_nops)
    semantic_helpers = (
        (
            OAM_PALETTE_RESOLVER_ADDR,
            build_oam_palette_resolver() + build_stage1_atomic_setup(),
        ),
        (OAM_CENTRAL_EMITTER_ADDR, build_oam_central_emitter()),
        (OAM_BOSS_LUT_SERVICE_ADDR, build_oam_boss_lut_service()),
        (OAM_FREE_EMITTER_ADDR, build_oam_free_emitter()),
        (OAM_WRAM_COPY_ADDR, build_oam_wram_copy()),
        (TITLE_TRANSITION_SERVICE_ADDR, title_transition),
        (NATIVE_GLYPH_RESTORE_ADDR, build_native_glyph_restore()),
        (OAM_LUT_INIT_ADDR, build_oam_lut_init()),
    )
    ted_envelope_compare, ted_envelope_table = build_ted_inside_envelope_rom()
    for address, payload in (
        (TED_ENVELOPE_COMPARE_ROM_ADDR,
         b"" if ted_block_major else ted_envelope_compare),
        (TED_ENVELOPE_ROW_TABLE_ROM_ADDR,
         b"" if (ted_block_major or expanded_ted_production)
         else ted_envelope_table),
        (TED_MAP_ANCHOR_ACTIVATE_ROM_ADDR,
         b"" if (cached_ted_full_plane or native_ted_postcopy)
         else build_ted_map_anchor_activate_rom()),
        (TED_ANCHOR_STATE_HELPER_ROM_ADDR,
         b"" if (cached_ted_full_plane or native_ted_postcopy)
         else build_ted_anchor_state_helper_rom()),
        (TED_SCAN_CROWN_HELPER_ROM_ADDR,
         b"" if (cached_ted_full_plane or native_ted_postcopy)
         else build_ted_scan_crown_helper_rom()),
    ):
        payload_off = BANK13 + address - 0x4000
        assert rom[payload_off:payload_off + len(payload)] == bytes(len(payload)), (
            f"Ted envelope cave at ${address:04X} is no longer free"
        )
        rom[payload_off:payload_off + len(payload)] = payload
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

    hazard_bank1_loader_off = (
        BANK13 + (STAGE1_HAZARD_BANK1_LOADER_ADDR - 0x4000)
    )
    assert rom[
        hazard_bank1_loader_off:
        hazard_bank1_loader_off + len(stage1_hazard_bank1_loader)
    ] == bytes(len(stage1_hazard_bank1_loader)), (
        "Stage-1 bank-1 hazard loader cave is no longer free"
    )
    rom[
        hazard_bank1_loader_off:
        hazard_bank1_loader_off + len(stage1_hazard_bank1_loader)
    ] = stage1_hazard_bank1_loader
    hazard_bank1_return_off = BANK13 + STAGE1_ENTRY_PATCH_GATE_ADDR - 0x4000
    assert rom[
        hazard_bank1_return_off:
        hazard_bank1_return_off + len(stage1_entry_patch_gate)
    ] == bytes(len(stage1_entry_patch_gate)), (
        "Stage-1 entry-patch gate cave is no longer free"
    )
    rom[
        hazard_bank1_return_off:
        hazard_bank1_return_off + len(stage1_entry_patch_gate)
    ] = stage1_entry_patch_gate

    for bank, payload in (
        (BANK13, stage1_hazard_banked_entry13),
        (BANK14, stage1_hazard_banked_entry14),
    ):
        entry_off = bank + (STAGE1_HAZARD_BANKED_ENTRY_ADDR - 0x4000)
        assert rom[entry_off:entry_off + len(payload)] == bytes(len(payload)), (
            "Stage-1 hazard banked-entry cave is no longer free"
        )
        rom[entry_off:entry_off + len(payload)] = payload
    arena_fragment_payloads = (
        *sorted(ted_sanitizer_fragments.items()),
        *sorted(shalamar_sanitizer_fragments.items()),
        (ARENA_SANITIZER_DISPATCH_ADDR, arena_sanitizer_dispatch),
    )
    protected_title_glyph_off = BANK13 + 0x6D50 - 0x4000
    protected_title_glyph = bytes(
        rom[protected_title_glyph_off:protected_title_glyph_off + 0x20]
    )
    for address, payload in arena_fragment_payloads:
        fragment_off = BANK13 + address - 0x4000
        capacity = (
            len(payload)
            if (ted_writer_mirror
                and address in (
                    build_ted_dirty_postcopy_fragments()
                    | build_shalamar_source_sanitizer_fragments()
                )
                or address in (
                    ARENA_SANITIZER_DISPATCH_ADDR,
                    TED_CACHED_GDMA_WAIT_ADDR,
                    TED_INWINDOW_EPILOGUE_ADDR,
                ))
            or address in (TED_SANITIZER_RUNTIME_EXTRA_SOURCE_ADDR,
                           TED_TILE_COMMIT_RUNTIME_ADDR,
                           TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR,
                           TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR,
                           TED_REGISTER_MATERIALIZER_TAIL_ADDR,
                           TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR,
                           TED_CROWN_PAIR_HELPER_ADDR,
                           TED_CROWN_PAIR_HELPER_CONT_ADDR,
                           TED_CACHED_COLUMN_WRAP_ADDR,
                           TED_CACHED_SPARSE_ENTRY_ADDR,
                           TED_CACHED_SPARSE_RESTORE_ADDR,
                           TED_CACHED_SPARSE_SETUP_ADDR,
                           TED_CACHED_SPARSE_SCAN_ADDR,
                           TED_CACHED_SPARSE_SCAN_TAIL_ADDR,
                           TED_CACHED_SPARSE_FILTER_ADDR,
                           TED_CACHED_ATTR_CLEAR_ADDR,
                           TED_CACHED_CADENCE_DELAY_ADDR,
                           TED_CACHED_READY_LATCH_ADDR,
                           TED_CACHED_PALETTE_GATE_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_A_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_B_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_C_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_D_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_E_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_F_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_G_ADDR,
                           TED_CACHED_SPARSE_OVERLAY_H_ADDR,
                           TED_CACHED_RUNTIME_EXTRA_SOURCE_ADDR,
                           TED_CACHED_INSTALL_EXTRA_ADDR,
                           TED_CACHED_ABI_FRONT_ADDR,
                           TED_CACHED_ABI_TAIL_ADDR,
                           SHALAMAR_SANITIZER_MAIN_ADDR,
                           SHALAMAR_SANITIZER_CELL_ADDR)
            else ARENA_SANITIZER_FRAGMENT_SIZE
        )
        if (
            cached_ted_full_plane
            and address == TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR
        ):
            capacity = 24
        elif ted_incremental_key:
            capacity = {
                TED_DIRTY_POSTCOPY_BIT_TAIL_ADDR: 8,
                TED_REGISTER_MATERIALIZER_TAIL_CONT_ADDR: 24,
                TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR: 31,
                TED_INCREMENTAL_INSTALL_FINAL_ADDR: 21,
                TED_INCREMENTAL_LAZY_GATE_ADDR: 11,
                TED_INCREMENTAL_SCENE_CLEAR_ADDR: 9,
                TED_DIRTY_POSTCOPY_COMPILE_FINAL_ADDR: 8,
                0x5E6D: 19,
                TED_INCREMENTAL_FIXED_COPY_LEAF_ADDR: 12,
            }.get(address, capacity)
        elif not (ted_writer_mirror or cached_ted_full_plane or native_ted_postcopy):
            if address == TED_SANITIZER_RUNTIME_TAIL_A_SOURCE_ADDR:
                capacity = 20
            elif address == TED_SANITIZER_RUNTIME_TAIL_B_SOURCE_ADDR:
                capacity = len(payload)
        expanded_payload_helper = (
            expanded_ted_payload
            # This build is copied wholesale into a private expanded ROM
            # bank.  Its Ted runtime may therefore reuse the arena LUT page;
            # production continues to own the original bank-13 bytes.
            and 0x7600 <= address < 0x7740
        )
        if not expanded_payload_helper:
            assert rom[
                fragment_off:fragment_off + capacity
            ] == bytes(capacity), (
                f"arena sanitizer cave ${address:04X} is no longer free: "
                f"{bytes(rom[fragment_off:fragment_off + capacity]).hex()} "
                f"({capacity} bytes)"
            )
        rom[fragment_off:fragment_off + len(payload)] = payload
    if not expanded_ted_payload:
        assert bytes(
            rom[protected_title_glyph_off:protected_title_glyph_off + 0x20]
        ) == protected_title_glyph, (
            "Ted arena fragments changed protected title glyph $6D50-$6D6F"
        )
    for bank, payload in ((BANK13, oam_wram_copy_tail13),):
        tail_off = bank + (OAM_WRAM_COPY_TAIL_ADDR - 0x4000)
        assert rom[tail_off:tail_off + 36] == bytes(36), (
            "cross-bank OAM WRAM-copy tail cave is no longer free"
        )
        rom[tail_off:tail_off + len(payload)] = payload
    helper_cont_off = BANK13 + OAM_WRAM_COPY_TED_HELPER_CONT_ADDR - 0x4000
    assert rom[
        helper_cont_off:helper_cont_off + len(oam_wram_copy_ted_helper_cont)
    ] == bytes(len(oam_wram_copy_ted_helper_cont)), (
        "Ted tile-helper boot continuation cave is no longer free: "
        + rom[
            helper_cont_off:
            helper_cont_off + len(oam_wram_copy_ted_helper_cont)
        ].hex()
    )
    rom[
        helper_cont_off:helper_cont_off + len(oam_wram_copy_ted_helper_cont)
    ] = oam_wram_copy_ted_helper_cont

    for address, payload in (
        (STAGE1_ENTRY_PATCH_BODY_ADDR, stage1_entry_patch_body),
        (STAGE1_ENTRY_PATCH_LOWER_ADDR, stage1_entry_patch_lower),
        (STAGE1_ENTRY_PATCH_TAIL_ADDR, stage1_entry_patch_tail),
        (STAGE1_ENTRY_PATCH_FINISH_ADDR, stage1_entry_patch_finish),
    ):
        patch_off = BANK13 + address - 0x4000
        assert rom[patch_off:patch_off + len(payload)] == bytes(len(payload)), (
            f"Stage-1 entry-patch cave at ${address:04X} is no longer free: "
            f"{rom[patch_off:patch_off + len(payload)].hex()}"
        )
        rom[patch_off:patch_off + len(payload)] = payload

    for address, payload in (
        (COLD_STAGE1_SWEEP_ARM_ADDR, cold_stage1_sweep_arm),
        (COLD_STAGE1_SWEEP_ARM_TAIL_ADDR, cold_stage1_sweep_arm_tail),
    ):
        arm_off = BANK13 + address - 0x4000
        assert rom[arm_off:arm_off + len(payload)] == bytes(len(payload)), (
            f"cold Stage-1 sweep-arm cave at ${address:04X} is no longer free"
        )
        rom[arm_off:arm_off + len(payload)] = payload

    attract_pickup_helpers = (
        (
            ATTRACT_PICKUP_SWEEP_HELPER_ADDR,
            build_attract_pickup_sweep_helper(),
        ),
        (
            ATTRACT_PICKUP_SWEEP_STUB_ADDR,
            build_attract_pickup_sweep_dispatcher(),
        ),
        (
            LATER_PICKUP_SWEEP_ORDER_ADDR,
            build_later_pickup_sweep_order(),
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
    stage4_fragments = (
        (STAGE4_MATERIAL_HELPER_ADDR, stage4_material[:10]),
        (STAGE4_MATERIAL_HELPER_CONT_ADDR, stage4_material[10:17]),
        (STAGE4_MATERIAL_HELPER_TAIL_ADDR, stage4_material[17:]),
    )
    assert [len(payload) for _, payload in stage4_fragments] == [10, 7, 7]
    for address, payload in stage4_fragments:
        material_off = BANK13 + address - 0x4000
        assert rom[material_off:material_off + len(payload)] == bytes(
            len(payload)
        ), f"Stage-4 material fragment at ${address:04X} is no longer free"
        rom[material_off:material_off + len(payload)] = payload
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
    for address, payload in (
        (STAGE1_HAZARD_SCANNER_FRONT_ADDR, stage1_hazard_scanner_front),
        (STAGE1_HAZARD_SCANNER_MIDDLE_ADDR, stage1_hazard_scanner_middle),
        (STAGE1_HAZARD_SCANNER_TAIL_ADDR, stage1_hazard_scanner_tail),
        (STAGE1_HAZARD_SCANNER_SEAM_ADDR, stage1_hazard_scanner_seam),
        (STAGE1_HAZARD_TRANSITION_REPAIR_ADDR,
         stage1_hazard_transition_repair),
        (STAGE1_HAZARD_ROOM12_WALL_REPAIR_ADDR,
         stage1_hazard_room12_wall_repair),
        (STAGE1_HAZARD_ROW0_REPAIR_FRONT_ADDR,
         stage1_hazard_row0_repair_front),
        (STAGE1_HAZARD_ROW0_REPAIR_MIDDLE_ADDR,
         stage1_hazard_row0_repair_middle),
        (STAGE1_HAZARD_ROW0_REPAIR_TAIL_ADDR,
         stage1_hazard_row0_repair_tail),
        (STAGE1_HAZARD_START4_HELPER_ADDR,
         stage1_hazard_start4_helper),
        (STAGE1_HAZARD_START4_EDGE_ADDR,
         stage1_hazard_start4_edge),
    ):
        scanner_off = BANK14 + address - 0x4000
        assert rom[scanner_off:scanner_off + len(payload)] == bytes(
            len(payload)
        ), f"Stage-1 dynamic scanner cave at ${address:04X} is no longer free"
        rom[scanner_off:scanner_off + len(payload)] = payload
    stage1_hazard_neutral_art_off = (
        BANK14 + STAGE1_HAZARD_BANK1_NEUTRAL_ART_ADDR - 0x4000
    )
    assert rom[
        stage1_hazard_neutral_art_off:
        stage1_hazard_neutral_art_off + len(stage1_hazard_bank1_neutral_art)
    ] == bytes(len(stage1_hazard_bank1_neutral_art)), (
        "Stage-1 immutable neutral-art slot is no longer free"
    )
    rom[
        stage1_hazard_neutral_art_off:
        stage1_hazard_neutral_art_off + len(stage1_hazard_bank1_neutral_art)
    ] = stage1_hazard_bank1_neutral_art
    stage1_hazard_bank14_copy_off = (
        BANK14 + STAGE1_HAZARD_BANK1_BANK14_COPY_ADDR - 0x4000
    )
    assert rom[
        stage1_hazard_bank14_copy_off:
        stage1_hazard_bank14_copy_off + len(stage1_hazard_bank14_copy)
    ] == bytes(len(stage1_hazard_bank14_copy)), (
        "Stage-1 bank-14 immutable copy-routine slot is no longer free"
    )
    rom[
        stage1_hazard_bank14_copy_off:
        stage1_hazard_bank14_copy_off + len(stage1_hazard_bank14_copy)
    ] = stage1_hazard_bank14_copy
    stage1_hazard_bank7_copy_off = (
        BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_ADDR - 0x4000
    )
    assert rom[
        stage1_hazard_bank7_copy_off:
        stage1_hazard_bank7_copy_off + len(stage1_hazard_bank7_copy)
    ] == bytes(len(stage1_hazard_bank7_copy)), (
        "Stage-1 bank-7 immutable copy-routine slot is no longer free"
    )
    rom[
        stage1_hazard_bank7_copy_off:
        stage1_hazard_bank7_copy_off + len(stage1_hazard_bank7_copy)
    ] = stage1_hazard_bank7_copy
    stage1_hazard_bank7_copy_middle_off = (
        BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_MIDDLE_ADDR - 0x4000
    )
    assert rom[
        stage1_hazard_bank7_copy_middle_off:
        stage1_hazard_bank7_copy_middle_off
        + len(stage1_hazard_bank7_copy_middle)
    ] == bytes(len(stage1_hazard_bank7_copy_middle)), (
        "Stage-1 bank-7 immutable copy-middle slot is no longer free"
    )
    rom[
        stage1_hazard_bank7_copy_middle_off:
        stage1_hazard_bank7_copy_middle_off
        + len(stage1_hazard_bank7_copy_middle)
    ] = stage1_hazard_bank7_copy_middle
    stage1_hazard_bank7_copy_tail_off = (
        BANK7 + STAGE1_HAZARD_BANK1_BANK7_COPY_TAIL_ADDR - 0x4000
    )
    assert rom[
        stage1_hazard_bank7_copy_tail_off:
        stage1_hazard_bank7_copy_tail_off + len(stage1_hazard_bank7_copy_tail)
    ] == bytes(len(stage1_hazard_bank7_copy_tail)), (
        "Stage-1 bank-7 immutable copy-tail slot is no longer free"
    )
    rom[
        stage1_hazard_bank7_copy_tail_off:
        stage1_hazard_bank7_copy_tail_off + len(stage1_hazard_bank7_copy_tail)
    ] = stage1_hazard_bank7_copy_tail
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
    stage1_hazard_bank14_loader_off = (
        BANK14 + STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR - 0x4000
    )
    assert (
        STAGE1_HAZARD_ROW_COMPILER_ADDR + len(stage1_hazard_row_compiler)
        <= STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR
        and STAGE1_HAZARD_BANK1_BANK14_LOADER_ADDR
        + len(stage1_hazard_bank1_bank14_loader)
        <= STAGE1_HAZARD_ROOM_DISPATCH_ADDR
    )
    assert rom[
        stage1_hazard_bank14_loader_off:
        stage1_hazard_bank14_loader_off
        + len(stage1_hazard_bank1_bank14_loader)
    ] == bytes(len(stage1_hazard_bank1_bank14_loader)), (
        "Stage-1 bank-14 immutable loader cave is no longer free"
    )
    rom[
        stage1_hazard_bank14_loader_off:
        stage1_hazard_bank14_loader_off
        + len(stage1_hazard_bank1_bank14_loader)
    ] = stage1_hazard_bank1_bank14_loader
    stage1_hazard_room_dispatcher_off = (
        BANK14 + (STAGE1_HAZARD_ROOM_DISPATCH_ADDR - 0x4000)
    )
    assert (
        STAGE1_HAZARD_ROOM_DISPATCH_ADDR
        >= STAGE1_HAZARD_ROW_COMPILER_ADDR + len(stage1_hazard_row_compiler)
        and STAGE1_HAZARD_ROOM_DISPATCH_ADDR
        + len(stage1_hazard_room_dispatcher)
        <= STAGE1_HAZARD_ROW_COMPILER_END
    )
    assert rom[
        stage1_hazard_room_dispatcher_off:
        stage1_hazard_room_dispatcher_off
        + len(stage1_hazard_room_dispatcher)
    ] == bytes(len(stage1_hazard_room_dispatcher)), (
        "Stage-1 hazard room-dispatch cave is no longer free"
    )
    rom[
        stage1_hazard_room_dispatcher_off:
        stage1_hazard_room_dispatcher_off
        + len(stage1_hazard_room_dispatcher)
    ] = stage1_hazard_room_dispatcher
    demo_pickup_bank14 = (
        (DEMO_PICKUP_DIRECT_WRITER_ADDR, demo_pickup_writer),
        (DEMO_PICKUP_DIRECT_WRITER_TAIL_ADDR, demo_pickup_writer_tail),
        (DEMO_PICKUP_PHASE_WRITER_ADDR, demo_pickup_phase_writer),
        (DEMO_PICKUP_PHASE_WRITER_TAIL_ADDR, demo_pickup_phase_writer_tail),
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
    if ted_incremental_key:
        for address, payload in build_ted_incremental_bank2_gate().items():
            gate_off = BANK2 + address - 0x4000
            assert rom[gate_off:gate_off + len(payload)] == bytes(
                len(payload)
            ), f"Ted bank-2 gate cave ${address:04X} is no longer free"
            rom[gate_off:gate_off + len(payload)] = payload
        direct_clone_hooks = not (
            ted_direct_plane
            and _os.environ.get("PENTA_TED_DIRECT_CLONE_HOOKS", "1") == "0"
        )
        if direct_clone_hooks:
            call_off = BANK2 + TED_INCREMENTAL_BANK2_CALL_ADDR - 0x4000
            assert rom[call_off:call_off + 3] == bytes.fromhex("CD 4D 06")
            rom[call_off:call_off + 3] = bytes([
                0xCD, TED_INCREMENTAL_BANK2_ENTRY_ADDR & 0xFF,
                TED_INCREMENTAL_BANK2_ENTRY_ADDR >> 8,
            ])
            # $064A has no callers in the stock ROM. Preserve its fixed
            # wrapper's native ROM-bank entry/restore and repoint only its
            # inner CALL to the cold-installed, unbanked runtime.
            assert rom[
                TED_INCREMENTAL_UNUSED_WRAPPER_ADDR:
                TED_INCREMENTAL_UNUSED_WRAPPER_ADDR + 7
            ] == bytes.fromhex("EF CD A5 04 C3 55 0D")
            rom[
                TED_INCREMENTAL_UNUSED_WRAPPER_ADDR + 1:
                TED_INCREMENTAL_UNUSED_WRAPPER_ADDR + 4
            ] = bytes([
                0xCD, TED_INCREMENTAL_FIXED_RUNTIME_ADDR & 0xFF,
                TED_INCREMENTAL_FIXED_RUNTIME_ADDR >> 8,
            ])
        assert rom[0x30AF:0x30B2] == bytes.fromhex("11 A0 C1")
        assert rom[0x3136:0x3139] == bytes.fromhex("C1 13 13")
        if (
            ted_direct_plane
            and _os.environ.get("PENTA_TED_DIRECT_SINGLE_HOOKS", "1") != "0"
        ):
            # Ted has two later single-cell writers outside the cloned 2x2
            # builder. Replace each complete displaced tail with a jump to
            # its exact-ABI fixed-WRAM wrapper.
            helper_a = TED_DIRECT_FIXED_HELPER_ADDR
            helper_b = helper_a + 10
            for address, stock, target in (
                (TED_DIRECT_SINGLE_WRITER_A_PATCH_ADDR,
                 bytes.fromhex("77 E1 C1"), helper_a),
                (TED_DIRECT_SINGLE_WRITER_B_PATCH_ADDR,
                 bytes.fromhex("F1 77 C9"), helper_b),
            ):
                patch_off = BANK2 + address - 0x4000
                assert rom[patch_off:patch_off + 3] == stock, (
                    f"Ted single-cell writer ABI changed at ${address:04X}"
                )
                rom[patch_off:patch_off + 3] = bytes([
                    0xC3, target & 0xFF, target >> 8,
                ])
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
        f"writer and {len(demo_pickup_phase_writer)}+"
        f"{len(demo_pickup_phase_writer_tail)}-byte cycle-exact no-write twin "
        "in bank14)"
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
    # Its free $7100-$719F range hosts the story-entry dispatcher and bounded
    # two-map death/game-over neutralizer.
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
        # Keep the stock single-wait tile writer, stage only the changed
        # attribute plane in WRAM, and publish it once after the map completes.
        # Unlike the retired two-plane prototype, this retains the production
        # scene/cache decision and never GDMA-replaces live tile IDs.
        inline_blob = create_inline_tile_copy_postcomputed_attrs(
            INLINE_ATTR_DECISION_HELPER_ADDR + 3,
            STAGE1_ATOMIC_SETUP_ADDR,
            STAGE1_ATOMIC_WRAP_ADDR,
            STAGE1_HAZARD_PURE_MAP_ADDR,
            STAGE1_SOURCE_GENERATION_RST,
        )
        atomic_row_addr = 0
        print(
            "  diagnostic isolation: stock-width tiles + buffered attribute GDMA"
        )
    else:
        inline_blob = create_inline_tile_copy_stage1_precomputed_attrs(
            INLINE_ATTR_DECISION_HELPER_ADDR + 3,
            STAGE1_ATOMIC_SETUP_ADDR,
            STAGE1_ATOMIC_WRAP_ADDR,
            external_post_copy_helper_addr=STAGE1_HAZARD_PURE_MAP_ADDR,
            external_attr_stack_helper_rst=STAGE1_SOURCE_GENERATION_RST,
            atomic_group_width=STAGE1_ATOMIC_GROUP_WIDTH,
        )
        # The shared stack helper now materializes all three outgoing tile IDs
        # before the STAT wait. The generator commits A/C/B directly, keeping
        # branches and calls out of the VRAM-critical interval.
        # INC BC / DEC BC is register-neutral but deliberately retained: the
        # 16-cycle phase pair aligns every later HBlank commit. Removing it
        # reproduced transient walls/voids in the 20,000-frame Stage-1 copy
        # receipt even though the packed source itself remained byte-stable.
        assert inline_blob[:2] == bytes.fromhex("2E 00")
        assert inline_blob[4:7] == bytes.fromhex("16 FF CD")
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
    stage1_atomic_wrap_tail = build_stage1_atomic_wrap_tail()
    available = 0x436D - 0x42A7 + 1
    assert len(inline_blob) <= available
    if buffered_stage1_attrs:
        title_tail_length = 14
        title_pure_entry = 0x42A7 + len(inline_blob) - title_tail_length
        title_prefix = bytes.fromhex("26 98 AF 6F")
        assert inline_blob[-title_tail_length:-3] == title_prefix + bytes([
            0xCD,
            INLINE_ATTR_DECISION_HELPER_ADDR & 0xFF,
            INLINE_ATTR_DECISION_HELPER_ADDR >> 8,
            0x06, 0x05, 0x18, 0x00,
        ])
    else:
        title_pure_entry = 0x42A7 + len(inline_blob) - 12
        assert inline_blob[-12:-3] == bytes.fromhex(
            "26 98 AF 6F CD 82 34 06 05"
        )
    inline_padding = bytes(available - len(inline_blob))
    rom[0x42A7:0x436E] = inline_blob + inline_padding
    restoring_native_copier = (
        stock_tile_copy
        or compact_tile_copy
        or semantic_stage1_prototype
        or semantic_stage1_vblank_prototype
    )
    if not restoring_native_copier:
        assert rom[
            STAGE1_ATOMIC_WRAP_TAIL_ADDR:0x436E
        ] == bytes(0x436E - STAGE1_ATOMIC_WRAP_TAIL_ADDR), (
            "atomic wrapper bank-1 tail is no longer free"
        )
        rom[
            STAGE1_ATOMIC_WRAP_TAIL_ADDR:0x436E
        ] = stage1_atomic_wrap_tail
    assert 0x42A7 + len(inline_blob) <= 0x436E
    assert rom[0x42A0:0x42A7] == bytearray([0x26, 0x9C, 0xC3, 0xA7, 0x42, 0x26, 0x98])
    assert rom[0x0030:0x0033] == bytes.fromhex("C3 A5 42")
    assert STAGE1_ATOMIC_WRAP_ADDR + len(stage1_atomic_wrap) <= 0x34A3
    assert rom[
        INLINE_ATTR_DECISION_HELPER_ADDR:0x34A3
    ] == bytes(0x34A3 - INLINE_ATTR_DECISION_HELPER_ADDR)
    if buffered_stage1_attrs:
        fixed_inline_helpers = (
            inline_attr_decision
            + stage1_atomic_wrap
        )
        assert len(fixed_inline_helpers) == 33
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
        if stock_tile_copy:
            # The inline decision/wrap helpers occupy the tail of the native
            # fixed-bank free-OAM emitter. Restoring only the map copier left
            # $3482-$34A2 as DX helper bytes, so the old "stock" diagnostic
            # was not actually native and produced catastrophic boss traces.
            # Keep the DX entry wrapper at $346F-$3481 (OBJ colorization), but
            # restore its now-unreachable native tail alongside the copier.
            rom[
                INLINE_ATTR_DECISION_HELPER_ADDR:0x34A3
            ] = vanilla_rom[INLINE_ATTR_DECISION_HELPER_ADDR:0x34A3]
            if native_ted_postcopy and not cached_ted_full_plane:
                # The 2,800-frame caller receipt proves every Ted publication
                # comes from this one stock alternating-map call. Hooking only
                # it avoids adding even a scene check to unrelated map copies.
                assert rom[0x028A:0x028D] == bytes.fromhex("CD 95 42")
                if not ted_writer_install_only:
                    rom[0x028A:0x028D] = bytes.fromhex(
                        "CD 80 DB" if (
                            ted_writer_mirror or ted_hdma_piggyback
                            or ted_inwindow_gdma
                        ) else
                        "CD 87 DB"
                    )
                if ted_writer_mirror and not ted_writer_install_only:
                    assert rom[0x3136:0x3139] == bytes.fromhex("C1 13 13")
                    rom[0x3136:0x3139] = bytes([
                        0xC3,
                        TED_WRITER_FIXED_STUB_ADDR & 0xFF,
                        TED_WRITER_FIXED_STUB_ADDR >> 8,
                    ])
            if cached_ted_full_plane:
                # The authoritative 2,800-frame native trace proves $028A is
                # Ted's sole physical publication caller. Keep shared $4295
                # completely stock so title and cold Stage 1 cannot enter the
                # arena cache before its scene/runtime exists. The trampoline
                # is private bank-1 zero space; DB80 retains the ordinary
                # arena helper used by earlier scenes.
                assert rom[0x028A:0x028D] == bytes.fromhex("CD 95 42")
                if not cached_ted_install_only:
                    cached_entry, cached_entry_tail, cached_fixed_cont = (
                        build_ted_cached_full_plane_wrapper()
                    )
                    assert rom[
                        TED_WRITER_CLEAR_GATE_ADDR:
                        TED_WRITER_CLEAR_GATE_ADDR + 13
                    ] == bytes(13), (
                        "Ted cached bank-1 trampoline cave is not free"
                    )
                    rom[
                        TED_WRITER_CLEAR_GATE_ADDR:
                        TED_WRITER_CLEAR_GATE_ADDR + len(cached_entry)
                    ] = cached_entry
                    cached_tail_off = 0x4000 + (
                        TED_CACHED_BANK1_TAIL_ADDR - 0x4000
                    )
                    assert rom[
                        cached_tail_off:cached_tail_off + 9
                    ] == bytes(9), "Ted cached bank-1 tail cave is not free"
                    rom[
                        cached_tail_off:
                        cached_tail_off + len(cached_entry_tail)
                    ] = cached_entry_tail
                    rom[0x028A:0x028D] = bytes([
                        0xCD,
                        TED_WRITER_CLEAR_GATE_ADDR & 0xFF,
                        TED_WRITER_CLEAR_GATE_ADDR >> 8,
                    ])
        elif compact_tile_copy and native_ted_postcopy:
            # The compact diagnostic copier retains $4295's stock toggle ABI,
            # so the same sole Ted caller can append the post-copy compiler.
            # This composition tests whether its reclaimed tile-copy time can
            # pay for complete attributes without dropping publications.
            assert not cached_ted_full_plane
            assert rom[0x028A:0x028D] == bytes.fromhex("CD 95 42")
            rom[0x028A:0x028D] = bytes.fromhex(
                "CD 80 DB" if (
                    ted_writer_mirror or ted_hdma_piggyback
                    or ted_inwindow_gdma
                ) else "CD 87 DB"
            )
            if ted_writer_mirror and not ted_writer_install_only:
                assert rom[0x3136:0x3139] == bytes.fromhex("C1 13 13")
                rom[0x3136:0x3139] = bytes([
                    0xC3,
                    TED_WRITER_FIXED_STUB_ADDR & 0xFF,
                    TED_WRITER_FIXED_STUB_ADDR >> 8,
                ])

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
        or disable_stage1_hazard_source_hook
    )
    if use_stage1_hazard_hook:
        # Keep the native source-expander return intact. The mapper is now
        # called only from the two completed-copy exits, eliminating the old
        # pre-copy tile/attribute race exposed by the Gargoyle transition.
        assert rom[0x0018:0x0020] == vanilla_rom[0x0018:0x0020]
        assert (
            rom[STAGE1_SOURCE_BUILD_RET_ADDR]
            == vanilla_rom[STAGE1_SOURCE_BUILD_RET_ADDR]
            == 0xC9
        )
        print(
            "  Stage-1 hazard publication: native $13E4 source RET retained; "
            "immutable tooth rows stamp only after completed map copies"
        )
        assert rom[0x0018:0x0020] == vanilla_rom[0x0018:0x0020]
        rom[0x0018:0x0020] = build_stage1_atomic_attr_stack_vector()

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
    lava_decider_bank0 = build_lava_attr_decider_bank0()
    stage1_demo_attr_trampoline = build_stage1_demo_attr_trampoline()
    assert (
        NATIVE_DMG_FADE_DISPATCH_ADDR + len(native_fade_service)
        == LAVA_ATTR_DECIDER_BANK0_ADDR
    )
    assert (
        LAVA_ATTR_DECIDER_BANK0_ADDR + len(lava_decider_bank0)
        == STAGE1_DEMO_ATTR_TRAMPOLINE_ADDR
    )
    fixed_services = (
        native_fade_service
        + lava_decider_bank0
        + stage1_demo_attr_trampoline
    )
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

    # 15. VBlank wrapper immediately after the prelude. Preserve the proven
    # v3.01 cold-boot timing:
    # joypad -> scene/colorizer first, then the one-shot footer helper.
    # Sound remains owned by the original game; a second call here churns it.
    conditional_palette_entry = (
        TED_CACHED_PALETTE_GATE_ADDR
        if cached_ted_full_plane else CONDITIONAL_PALETTE_ADDR
    )
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
        0xCD, conditional_palette_entry & 0xFF,
        conditional_palette_entry >> 8,   # pending: service this VBlank
        0x18, 0x07,                        # JR palette_done
        0xF0, 0xD4,                        # idle: stock VBlank tick
        0xE6, 0x07,                        # once per eight frames
        0xCC, conditional_palette_entry & 0xFF,
        conditional_palette_entry >> 8,   # CALL Z,palette state probe
        # Robust joypad sampler inherited from the proven v3.01 wrapper.
        # FF93 is consumed by the game. SELECT+START is no longer intercepted.
        0x3E, 0x20,                           # LD A, 0x20 (directions)
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00, 0xF0, 0x00,              # settle reads
        0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47,  # CPL; AND 0x0F; SWAP A; LD B,A
        0x3E, 0x10,                           # LD A, 0x10 (buttons)
        0xE0, 0x00,                           # LDH [FF00], A
        0xF0, 0x00, 0xF0, 0x00,              # seven settle reads
        0xF0, 0x00, 0xF0, 0x00,
        0xF0, 0x00, 0xF0, 0x00,
        0xF0, 0x00,
        0x2F, 0xE6, 0x0F, 0xB0,              # CPL; AND 0x0F; OR B
        0xE0, 0x93,                           # LDH [FF93], A
        0x47,                                 # LD B,A for no-prelude route
        0x3E, 0x30, 0xE0, 0x00,              # deselect
        # Steady Gargoyle frames already own their selected scene table. The
        # transition service stores zero only after scene_detect has processed
        # $0A entry; the initializer and returned title remain armed.
        0xF0, ATTRACT_PRELUDE_FLAG_HRAM,
        0xB7,
        0xC4, COLORIZE_PRELUDE_ADDR & 0xFF,
        COLORIZE_PRELUDE_ADDR >> 8,
        # Gameplay is paused while the item-menu window is visible. The
        # prelude has just cleared the active window map; do not let the
        # background sweep repaint those HUD cells later in this VBlank.
        0xF0, 0x40,                        # LDH A,[LCDC]
        0xE6, 0x20,                        # AND window-enable
        0x20, 0x0A,                        # JR NZ, skip full colorizer
        # Death ($17) owns a bounded two-map neutral pass above; STAGE XX ($18)
        # uses its all-pal0 inline path. Both skip the gameplay colorizer:
        # death must not be repainted from the stale dungeon/arena table, and
        # the splash must retain stock VBlank/ditty timing. On the final splash
        # VBlank, FFB7 already identifies Stage 1; publish the eleven first-
        # room chromatic attrs before D880 changes on the following main loop.
        0xFA, 0x80, 0xD8,                  # LD A,[D880]
        0xD6, 0x17,                        # SUB first skipped scene
        0xD6, 0x01,                        # death=Carry; splash=Zero
        0xCC,                              # CALL Z, hidden entry patch
        STAGE1_ENTRY_PATCH_GATE_ADDR & 0xFF,
        STAGE1_ENTRY_PATCH_GATE_ADDR >> 8,
        0xD4, COLORIZE_ADDR & 0xFF, (COLORIZE_ADDR >> 8) & 0xFF,
        # One-shot period + v3.01 digits + footer attributes. Keeping this
        # after colorize prevents it from delaying first-VBlank CRAM writes.
        0xCD, VRAM_GLYPH_COPY_ADDR & 0xFF,
        VRAM_GLYPH_COPY_ADDR >> 8,
        # Final live-only VRAM owner: the prerecorded route stays on its
        # independent tile-ID attributes and pays no bank-1 loader cadence.
        0xFA, 0xFD, 0xDC,                  # LD A,[DCFD]
        0xB7,                              # OR A
        0xC4,                              # CALL NZ, immutable live loader
        STAGE1_HAZARD_BANK1_LOADER_ADDR & 0xFF,
        STAGE1_HAZARD_BANK1_LOADER_ADDR >> 8,
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
                0xC4, COLORIZE_PRELUDE_ADDR & 0xFF,
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
    assert WRAPPER_ADDR == 0x6F1D
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
    if use_stage1_hazard_hook:
        if _TED_CACHED_FULL_PLANE_ENV:
            # Preserve the historical diagnostic layout; this mode requires
            # native room writers and owns $0838 with its Ted continuation.
            hazard_mapper_offset = STAGE1_HAZARD_BANK0_MAP_ADDR - 0x0824
            assert len(new_hook) <= hazard_mapper_offset
            new_hook.extend(bytes(hazard_mapper_offset - len(new_hook)))
            new_hook.extend(bytes.fromhex("FE 0C 3E 0D CE 00 00"))
            assert (
                0x0824 + len(new_hook)
                == LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR
            )
        else:
            # Atomic completion reloads exact D880 immediately before calling
            # this selector. The layered v65 lineage never reached the shared
            # banked completion because stale A=$01 returned here. Admit only
            # Penta's receipt-proven seam repair; waking every dormant arena
            # post-copy sanitizer is a materially broader behavior change.
            hazard_mapper_offset = STAGE1_HAZARD_BANK0_MAP_ADDR - 0x0824
            assert len(new_hook) <= hazard_mapper_offset
            new_hook.extend(bytes(hazard_mapper_offset - len(new_hook)))
            new_hook.extend(bytes([
                0xFE, 0x14,
                0xC0,
                0x3E, 0x0D,
            ]))
            assert (
                0x0824 + len(new_hook)
                == LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR
            )
    assert len(new_hook) <= 47
    new_hook_padded = (new_hook + bytearray(47 - len(new_hook)))[:47]
    rom[0x0824:0x0824 + 47] = new_hook_padded
    if ted_hdma_piggyback or ted_inwindow_gdma:
        assert native_room_writers, (
            "Ted direct fixed entry requires the room-rearm-free $0838 cave"
        )
        piggyback_wrapper = (
            build_ted_inwindow_wrapper()
            if ted_inwindow_gdma else build_ted_hdma_piggyback_wrapper()
        )
        assert rom[
            ROOM_BG_REARM_BANK0_ADDR:
            ROOM_BG_REARM_BANK0_ADDR + len(piggyback_wrapper)
        ] == bytes(len(piggyback_wrapper)), (
            "Ted piggyback fixed entry $0838-$0847 is not free"
        )
        rom[
            ROOM_BG_REARM_BANK0_ADDR:
            ROOM_BG_REARM_BANK0_ADDR + len(piggyback_wrapper)
        ] = piggyback_wrapper
    if use_room_rearm_hooks:
        install_room_bg_rearm_hooks(
            rom,
            target_addr=ROOM_BG_REARM_BANK0_ADDR,
        )
    if cached_ted_full_plane and not cached_ted_install_only:
        assert not use_room_rearm_hooks, (
            "Ted cached fixed continuation and room rearm cannot share $0838"
        )
        cached_fixed_cont = build_ted_cached_full_plane_wrapper()[2]
        cached_fixed_end = TED_CACHED_FIXED_CONT_ADDR + len(cached_fixed_cont)
        assert rom[
            TED_CACHED_FIXED_CONT_ADDR:cached_fixed_end
        ] == bytes(len(cached_fixed_cont)), (
            "Ted cached fixed-bank continuation cave is not free: "
            + bytes(rom[
                TED_CACHED_FIXED_CONT_ADDR:cached_fixed_end
            ]).hex()
        )
        rom[TED_CACHED_FIXED_CONT_ADDR:cached_fixed_end] = cached_fixed_cont
    lava_decider_bank0_map_entry = build_lava_attr_decider_bank0_map_entry()
    bank0_decider_end = (
        LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR
        + len(lava_decider_bank0_map_entry)
    )
    assert bank0_decider_end <= 0x0853
    assert rom[
        LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR:bank0_decider_end
    ] == bytes(len(lava_decider_bank0_map_entry))
    rom[
        LAVA_ATTR_DECIDER_BANK0_MAP_ENTRY_ADDR:bank0_decider_end
    ] = lava_decider_bank0_map_entry
    if ted_writer_mirror:
        assert native_room_writers, (
            "Ted ROM writer tracker currently owns the native-room free "
            "VBlank padding at $0838"
        )
        clear_invalidator = build_ted_writer_clear_invalidator()
        clear_invalidator_end = (
            TED_WRITER_CLEAR_GATE_ADDR + len(clear_invalidator)
        )
        assert rom[
            TED_WRITER_CLEAR_GATE_ADDR:clear_invalidator_end
        ] == bytes(len(clear_invalidator)), (
            "Ted writer invalidator cave at bank1:$6FE4 is no longer free"
        )
        assert rom[0x4422:0x4425] == bytes.fromhex("21 A0 C1")
        rom[
            TED_WRITER_CLEAR_GATE_ADDR:clear_invalidator_end
        ] = clear_invalidator
        rom[0x4422:0x4425] = bytes([
            0xC3,
            TED_WRITER_CLEAR_GATE_ADDR & 0xFF,
            TED_WRITER_CLEAR_GATE_ADDR >> 8,
        ])
        writer_stub = build_ted_writer_fixed_stub()
        assert rom[
            TED_WRITER_FIXED_STUB_ADDR:
            TED_WRITER_FIXED_STUB_ADDR + len(writer_stub)
        ] == bytes(len(writer_stub))
        rom[
            TED_WRITER_FIXED_STUB_ADDR:
            TED_WRITER_FIXED_STUB_ADDR + len(writer_stub)
        ] = writer_stub
        writer_runtime = build_ted_writer_rom_runtime()
        writer_runtime_off = (
            BANK13 + TED_WRITER_ROM_RUNTIME_ADDR - 0x4000
        )
        assert rom[
            writer_runtime_off:writer_runtime_off + len(writer_runtime)
        ] == bytes(len(writer_runtime)), (
            "Ted ROM writer runtime cave at bank13:$7687 is no longer free"
        )
        rom[
            writer_runtime_off:writer_runtime_off + len(writer_runtime)
        ] = writer_runtime
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
    # Final handoff gate: the contiguous $7200-$7AFF range is nine complete
    # boss attribute LUTs. No diagnostic/runtime payload may borrow even a
    # tail from these pages after they are installed.
    protected_arena_luts = bytearray(b"".join(
        bytes(build_fn()) for _, _, build_fn in arena_tables
    ))
    assert len(protected_arena_luts) == 0x900
    if ted_block_major:
        exact = build_ted_block_major_exact_fit_draft()
        for address, payload in exact.items():
            if TED_TABLE_ADDR <= address < TED_TABLE_ADDR + 0x100:
                start = address - ARENA_BASE_ADDR
                protected_arena_luts[start:start + len(payload)] = payload
    elif ted_inwindow_gdma:
        # The in-window path cold-copies its private D500 sanitizer from the
        # otherwise-neutral tail of Ted's own page.  No other boss page is
        # touched, and the runtime whitelist clears every non-sparse high-ID
        # attribute before publication.
        sanitizer_source, _helpers = build_ted_inwindow_plane_sanitizer()
        sanitizer_offset = (
            TED_INWINDOW_SANITIZER_SOURCE_ADDR - ARENA_BASE_ADDR
        )
        protected_arena_luts[
            sanitizer_offset:
            sanitizer_offset + len(sanitizer_source)
        ] = sanitizer_source
    if expanded_ted_payload:
        # Bank 13 from this build is copied to private Ted-only bank 16.  Its
        # Angela LUT is never selected for Angela gameplay, so the receipt-
        # proven unused $BB-$D6 interval safely carries Ted's envelope table.
        # Production bank 13 remains the exact YAML-generated Angela table.
        envelope_offset = TED_ENVELOPE_ROW_TABLE_ROM_ADDR - ARENA_BASE_ADDR
        protected_arena_luts[
            envelope_offset:envelope_offset + len(ted_envelope_table)
        ] = ted_envelope_table
    # Architecture-specific Ted helpers may intentionally occupy only the
    # asserted-neutral tail ($7687-$76FF), never editable palette entries.
    # Fold their exact generated bytes into the final identity receipt while
    # retaining the full-range comparison against every other late write.
    for address, payload in arena_fragment_payloads:
        if TED_INWINDOW_SANITIZER_SOURCE_ADDR <= address < 0x7700:
            start = address - ARENA_BASE_ADDR
            protected_arena_luts[start:start + len(payload)] = payload
    # Ted's source-qualified palette domain ends at tile $86.  Several
    # independently identity-checked Ted helpers share the native-zero
    # $7687-$76FF tail, so exclude only that asserted-neutral suffix from the
    # aggregate LUT comparison.  Editable $7600-$7686 remains byte-exact.
    ted_neutral_start = TED_INWINDOW_SANITIZER_SOURCE_ADDR - ARENA_BASE_ADDR
    assert protected_arena_luts[ted_neutral_start:0x500] == bytes(
        0x500 - ted_neutral_start
    ) or ted_block_major or ted_inwindow_gdma or (
        _os.environ.get("PENTA_TED_EXPANDED_PAYLOAD", "0") == "1"
    )
    protected_arena_luts[ted_neutral_start:0x500] = rom[
        BANK13 + ARENA_BASE_ADDR - 0x4000 + ted_neutral_start:
        BANK13 + ARENA_BASE_ADDR - 0x4000 + 0x500
    ]
    protected_arena_off = BANK13 + ARENA_BASE_ADDR - 0x4000
    protected_arena_actual = rom[
        protected_arena_off:protected_arena_off + len(protected_arena_luts)
    ]
    protected_arena_mismatches = [
        index for index, (actual, expected) in enumerate(zip(
            protected_arena_actual, protected_arena_luts
        )) if actual != expected
    ]
    assert not protected_arena_mismatches, (
        "protected boss LUT range $7200-$7AFF changed after installation",
        [
            (
                hex(ARENA_BASE_ADDR + index),
                hex(protected_arena_actual[index]),
                hex(protected_arena_luts[index]),
            )
            for index in protected_arena_mismatches[:16]
        ],
    )
    # Zero-valued stock structures are still live data.  This whole range is
    # selected by the bank-13 map pointer table and must remain byte-identical
    # through every late installation step.
    live_record_off = BANK13 + (0x4CE4 - 0x4000)
    live_record_size = 0x4CF2 - 0x4CE4
    assert rom[
        live_record_off:live_record_off + live_record_size
    ] == vanilla[live_record_off:live_record_off + live_record_size], (
        "live bank-13 $4CE4-$4CF1 map records changed after installation"
    )
    assert rom[
        later_stage_source_off:
        later_stage_source_off + len(later_stage_bg0_sources)
    ] == later_stage_bg0_sources, (
        "later-stage BG0 source table changed after installation"
    )
    if ted_block_major:
        # DB80 is the in-window ready/cold gate.  DB87 is an operand byte
        # inside its CALL $DB91 instruction; entering there executes SUB C
        # followed by the undefined $DB opcode and freezes at PC=$DB88.
        assert rom[0x028A:0x028D] == bytes.fromhex("CD 80 DB"), (
            "block-major publisher caller must enter the DB80 gate",
            rom[0x028A:0x028D].hex(),
        )
    for offset, payload, label in cutscene_regions:
        assert rom[offset:offset + len(payload)] == payload, label
    print(
        "  ✅ title/gameplay OAM dispatcher + transition service + "
        "complete spotlight roster map + cutscene CRAM loader + protected "
        "boss LUTs verified"
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
    parser.add_argument(
        "--disable-stage1-hazard-source-hook",
        action="store_true",
        help=(
            "diagnostically retain the native Stage-1 source-builder RET "
            "while keeping the completed tile-copy dispatcher"
        ),
    )
    parser.add_argument(
        "--demo-pickup-writer-phase-nops",
        type=int,
        default=DEMO_PICKUP_WRITER_PHASE_NOPS,
        choices=range(8),
        metavar="0..7",
        help=(
            "diagnostically tune the prerecorded Stage-1 pickup writer "
            "phase; the release default is receipt-locked in source"
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
        disable_stage1_hazard_source_hook=(
            arguments.disable_stage1_hazard_source_hook
        ),
        demo_pickup_writer_phase_nops=(
            arguments.demo_pickup_writer_phase_nops
        ),
    )
