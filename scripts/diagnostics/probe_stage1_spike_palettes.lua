-- Prove the reviewed Stage-1 spike material split is live in both BG maps.
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
-- Global, not local: this chunk is already at Lua's 200-local limit.
native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end

local OUT = assert(os.getenv("STAGE1_SPIKE_OUT"))
-- Open the startup trace before any reviewed-ROM contract checks.  A failed
-- publisher identity must leave a deterministic breadcrumb instead of
-- looking like an emulator timeout with an empty report.
local watchdog_path = os.getenv("STAGE1_SPIKE_WATCHDOG")
local watchdog = watchdog_path
  and assert(io.open(watchdog_path, "w")) or nil
if watchdog then watchdog:write("init:script\n"); watchdog:flush() end
local STATE_FILE = assert(os.getenv("PENTA_STATE_FILE"),
  "PENTA_STATE_FILE required")
local EXPECTED_ATTR_TABLE = assert(
  os.getenv("STAGE1_SPIKE_EXPECTED_ATTR_TABLE"),
  "STAGE1_SPIKE_EXPECTED_ATTR_TABLE required")
assert(#EXPECTED_ATTR_TABLE == 512,
  "expected immutable 256-byte Stage-1 attribute table")
if watchdog then watchdog:write("init:env\n"); watchdog:flush() end
local reviewed_room_local_attrs = {}
do
  local spec = assert(os.getenv("STAGE1_SPIKE_REVIEWED_ROOM_LOCAL_ATTRS"),
    "STAGE1_SPIKE_REVIEWED_ROOM_LOCAL_ATTRS required")
  local expected_count = assert(tonumber(
    os.getenv("STAGE1_SPIKE_REVIEWED_ROOM_LOCAL_ATTR_COUNT")),
    "STAGE1_SPIKE_REVIEWED_ROOM_LOCAL_ATTR_COUNT required")
  local records = {}
  for record in spec:gmatch("[^,]+") do
    local room_text, tile_text, attr_text = record:match(
      "^(%x%x):(%x%x):(%x%x)$")
    assert(room_text and tile_text and attr_text,
      "malformed reviewed room-local attribute record")
    local room = assert(tonumber(room_text, 16))
    local tile = assert(tonumber(tile_text, 16))
    local attr = assert(tonumber(attr_text, 16))
    local key = room * 0x100 + tile
    assert(reviewed_room_local_attrs[key] == nil,
      "duplicate reviewed room-local attribute record")
    reviewed_room_local_attrs[key] = attr
    records[#records + 1] = record
  end
  assert(#records == expected_count,
    "reviewed room-local attribute record count changed")
  assert(table.concat(records, ",") == spec,
    "reviewed room-local attribute policy was not parsed exactly")
end
if watchdog then watchdog:write("init:room-attrs\n"); watchdog:flush() end
local BROAD_VISIBLE_ORACLE =
  os.getenv("STAGE1_SPIKE_BROAD_VISIBLE_ORACLE") == "1"
local INITIAL_MAP_ROOM = assert(tonumber(
  os.getenv("STAGE1_SPIKE_EXPECTED_ROOM")),
  "STAGE1_SPIKE_EXPECTED_ROOM required")
PENTA_EXPECTED_PUBLICATION_VARIANT = assert(
  os.getenv("STAGE1_SPIKE_EXPECTED_PUBLICATION_VARIANT"),
  "STAGE1_SPIKE_EXPECTED_PUBLICATION_VARIANT required")
PENTA_EXPECTED_PUBLICATION_PC = assert(tonumber(
  os.getenv("STAGE1_SPIKE_EXPECTED_PUBLICATION_PC"), 16),
  "STAGE1_SPIKE_EXPECTED_PUBLICATION_PC required")
-- The physical-page owner must promote at the instruction that actually
-- writes LCDC.  r320 intentionally moved that store from $12EC to $12FF
-- after SCX/SCY and wrapped the sequence in DI/EI.  Accept only a complete,
-- reviewed publisher body; a partial edit must stop the probe rather than
-- quietly watching the retired address.
PENTA_PRIMARY_ADDR = 0x12E0
PENTA_PRIMARY_END = 0x1303
PENTA_LEGACY_PRIMARY = string.char(
  0xFA, 0x0B, 0xDC, 0xB7, 0x28, 0x04, 0x3E, 0x8B, 0x18, 0x02,
  0x3E, 0x83, 0xE0, 0x40, 0xF0, 0x97, 0xFE, 0x02, 0x28, 0x07,
  0xFA, 0x00, 0xDC, 0xE6, 0x0F, 0xE0, 0x43, 0xFA, 0x02, 0xDC,
  0xE6, 0x0F, 0xE0, 0x42, 0xC9)
PENTA_R320_PRIMARY = string.char(
  0xF3, 0xF0, 0x97, 0xFE, 0x02, 0x28, 0x07, 0xFA, 0x00, 0xDC,
  0xE6, 0x0F, 0xE0, 0x43, 0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xE0,
  0x42, 0xFA, 0x0B, 0xDC, 0xB7, 0x3E, 0x83, 0x28, 0x02, 0xCB,
  0xDF, 0xE0, 0x40, 0xFB, 0xC9)
PENTA_R346_PRIMARY = string.char(
  0xF3, 0x00, 0xF0, 0x40, 0x87, 0x30, 0x06, 0xF0, 0x44, 0xFE,
  0x90, 0x38, 0xFA, 0xFA, 0x00, 0xDC, 0xE6, 0x0F, 0xE0, 0x43,
  0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xE0, 0x42, 0xF0, 0x40, 0xEE,
  0x08, 0xE0, 0x40, 0xFB, 0xC9)
PENTA_R347_PRIMARY = string.char(
  0xF3, 0xF0, 0x40, 0x07, 0x38, 0x16, 0xFA, 0x00, 0xDC, 0xE6,
  0x0F, 0xE0, 0x43, 0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xE0, 0x42,
  0xF0, 0x40, 0xEE, 0x08, 0xE0, 0x40, 0x18, 0x05, 0x3E, 0x01,
  0xEA, 0x5C, 0xDF, 0xFB, 0xC9)
PENTA_R348_PRIMARY = string.char(
  0xF3, 0xF0, 0x40, 0x07, 0x38, 0x16, 0xFA, 0x00, 0xDC, 0xE6,
  0x0F, 0xE0, 0x43, 0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xE0, 0x42,
  0xF0, 0x40, 0xEE, 0x08, 0xE0, 0x40, 0x18, 0x05, 0xF0, 0x53,
  0xEA, 0x5C, 0xDF, 0xFB, 0xC9)
PENTA_R349_PRIMARY = string.char(
  0xF3, 0xF0, 0x40, 0x07, 0x38, 0x16, 0xFA, 0x00, 0xDC, 0xE6,
  0x0F, 0xE0, 0x43, 0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xE0, 0x42,
  0xF0, 0x40, 0xEE, 0x08, 0xE0, 0x40, 0x18, 0x05, 0xF0, 0x40,
  0xEA, 0x5C, 0xDF, 0xFB, 0xC9)
PENTA_R350_PRIMARY = string.char(
  0xF3, 0xF0, 0x40, 0x07, 0x38, 0x16, 0xFA, 0x00, 0xDC, 0xE6,
  0x0F, 0xE0, 0x43, 0xFA, 0x02, 0xDC, 0xE6, 0x0F, 0xE0, 0x42,
  0xF0, 0x40, 0xEE, 0x08, 0xE0, 0x40, 0x18, 0x05, 0x3E, 0x01,
  0xEA, 0x5D, 0xDF, 0xFB, 0xC9)
-- Exact publisher body used by the selected r449f pre-helper d82 candidate.
PENTA_R449F_PREHELPER_PRIMARY = string.char(
  0xF3,0xF0,0x40,0x07,0x38,0x16,0xFA,0x00,0xDC,0xE6,0x0F,0xE0,0x43,
  0xFA,0x02,0xDC,0xE6,0x0F,0xE0,0x42,0xF0,0x40,0xEE,0x08,0xE0,0x40,
  0x18,0x05,0xC3,0x8B,0x11,0x00,0x00,0xFB,0xC9)
PENTA_PRIMARY_BYTES = {}
for address = PENTA_PRIMARY_ADDR, PENTA_PRIMARY_END - 1 do
  PENTA_PRIMARY_BYTES[#PENTA_PRIMARY_BYTES + 1] = string.char(emu:read8(address))
end
if watchdog then watchdog:write("init:rom-read\n"); watchdog:flush() end
PENTA_PRIMARY = table.concat(PENTA_PRIMARY_BYTES)
PENTA_LEGACY_PUBLICATION = PENTA_PRIMARY == PENTA_LEGACY_PRIMARY
PENTA_R320_PUBLICATION = PENTA_PRIMARY == PENTA_R320_PRIMARY
PENTA_R346_PUBLICATION = PENTA_PRIMARY == PENTA_R346_PRIMARY
PENTA_R347_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT == "r347-deferred-vblank-v1"
PENTA_R348_PUBLICATION = PENTA_PRIMARY == PENTA_R348_PRIMARY
PENTA_R349_PUBLICATION = PENTA_PRIMARY == PENTA_R349_PRIMARY
PENTA_R350_PUBLICATION = PENTA_PRIMARY == PENTA_R350_PRIMARY
PENTA_R449F_PREHELPER_PUBLICATION =
  PENTA_PRIMARY == PENTA_R449F_PREHELPER_PRIMARY
  and (PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r449f-prehelper-title-v6-d82f563d"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r449f-title-v6-15ab73c3"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r455-arena-storage-6e5e7a61"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r456c-attract-white-8234bd84"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r456d-attract-white-69896bb1"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r527-ending-handoff-13beaa1b"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r528-palette-atomic-e8da7fde"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r529-palette-atomic-5c49fa5d"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r530-palette-atomic-46b498d8"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r531-palette-atomic-9d44e9d1"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r532-palette-atomic-055a2754"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r533-story-neutral-guard-4fc5028a"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-stage4-cache-key-727ee496"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r535-title-tile-retire-681b4668"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r536-penta-seam-vram-b93ebc46"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r536-stage1-only-card-black-ffb6a829"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r535-stage-card-black-fe14b0e3"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r535-stage1-only-card-black-b691c96c"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-stage1-native-gold-72395c46"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-stage1-native-gold-2279fb35"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-stage1-native-gold-18d911a3"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-stage1-native-gold-59c62cfc"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-stage1-native-gold-703c7c1c"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-reserved-gold-620d8a31"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-reserved-gold-mirror-1b2def34"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r534-reserved-gold-mirror-c67cea34"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
      "r451c-lut-reload-repatch-b331c5e0")
PENTA_R351_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r351-completed-source-end-vblank-v1"
PENTA_R354_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT == "r354-postcommit-hram-vblank-v1"
PENTA_R356_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT == "r356-vblank-palette-map-atomic-v2"
PENTA_R357_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r357-vblank-palette-map-window-atomic-v3"
PENTA_R358_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r358-vblank-palette-map-stage1-window-atomic-v4"
PENTA_R359_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r359-vblank-palette-map-stage1-only-window-atomic-v5"
PENTA_R360_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r360-vblank-palette-map-window-fast-atomic-v6"
PENTA_R361_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r361-vblank-palette-map-window-robust-atomic-v7"
PENTA_R362_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r362-vblank-palette-map-window-final-atomic-v8"
PENTA_R363_PUBLICATION = PENTA_PRIMARY == PENTA_R347_PRIMARY
  and (PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r363-vblank-palette-map-window-fast-final-atomic-v9"
    or PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r363-vblank-palette-map-window-fast-final-guard-r374")
-- Python authenticates the whole r435/r436 ROM. Independently require its exact
-- primary dispatcher bytes here; its bank13 LCDC publication remains7457.
PENTA_R435_PUBLICATION = (PENTA_EXPECTED_PUBLICATION_VARIANT ==
    "r435-stage5-dead-moves-6b5d6a65"
    or PENTA_EXPECTED_PUBLICATION_VARIANT == "r436-single-recovery-art-37b4e9c8"
    or PENTA_EXPECTED_PUBLICATION_VARIANT == "r437-restore-room03-scanner-06146c7f"
    or PENTA_EXPECTED_PUBLICATION_VARIANT == "r438-compiled-tooth-bank-4913e494"
    or PENTA_EXPECTED_PUBLICATION_VARIANT == "r439-warning-source-tracking-24bbce66"
    or PENTA_EXPECTED_PUBLICATION_VARIANT == "r440-animation-envelope-dcb4f553"
    or PENTA_EXPECTED_PUBLICATION_VARIANT == "r441-stage2-seven-rows-44ac932a"
    or PENTA_EXPECTED_PUBLICATION_VARIANT == "r442-subscene-tracking-ea53ebb1")
  and PENTA_PRIMARY == PENTA_R347_PRIMARY:sub(1, -8)
    .. string.char(0xC3,0x8B,0x11,0x00,0x00,0xFB,0xC9)
PENTA_PUBLICATION_MATCHES = (PENTA_LEGACY_PUBLICATION and 1 or 0)
  + (PENTA_R435_PUBLICATION and 1 or 0)
  + (PENTA_R320_PUBLICATION and 1 or 0)
  + (PENTA_R346_PUBLICATION and 1 or 0)
  + (PENTA_R347_PUBLICATION and 1 or 0)
  + (PENTA_R348_PUBLICATION and 1 or 0)
  + (PENTA_R349_PUBLICATION and 1 or 0)
  + (PENTA_R350_PUBLICATION and 1 or 0)
  + (PENTA_R449F_PREHELPER_PUBLICATION and 1 or 0)
  + (PENTA_R351_PUBLICATION and 1 or 0)
  + (PENTA_R354_PUBLICATION and 1 or 0)
  + (PENTA_R356_PUBLICATION and 1 or 0)
  + (PENTA_R357_PUBLICATION and 1 or 0)
  + (PENTA_R358_PUBLICATION and 1 or 0)
  + (PENTA_R359_PUBLICATION and 1 or 0)
  + (PENTA_R360_PUBLICATION and 1 or 0)
  + (PENTA_R361_PUBLICATION and 1 or 0)
  + (PENTA_R362_PUBLICATION and 1 or 0)
  + (PENTA_R363_PUBLICATION and 1 or 0)
if watchdog then watchdog:write("init:publication-count\n"); watchdog:flush() end
assert(PENTA_PUBLICATION_MATCHES == 1,
  "spike physical-page oracle requires exactly one reviewed publisher")
if watchdog then watchdog:write("init:publication-match\n"); watchdog:flush() end
PENTA_PUBLICATION_VARIANT = PENTA_LEGACY_PUBLICATION and "legacy-v1"
  or (PENTA_R320_PUBLICATION and "r320-v1"
    or (PENTA_R346_PUBLICATION and "r346-vblank-v1"
      or (PENTA_R347_PUBLICATION and "r347-deferred-vblank-v1"
        or (PENTA_R348_PUBLICATION and "r348-absolute-vblank-v1"
          or (PENTA_R349_PUBLICATION and "r349-requested-peer-vblank-v1"
            or (PENTA_R350_PUBLICATION and "r350-completed-map-vblank-v1"
              or (PENTA_R351_PUBLICATION
                and "r351-completed-source-end-vblank-v1"
                or (PENTA_R354_PUBLICATION
                  and "r354-postcommit-hram-vblank-v1"
                  or (PENTA_R356_PUBLICATION
                    and "r356-vblank-palette-map-atomic-v2"
                    or "r357-vblank-palette-map-window-atomic-v3")))))))))
if PENTA_R358_PUBLICATION then
  PENTA_PUBLICATION_VARIANT =
    "r358-vblank-palette-map-stage1-window-atomic-v4"
end
if PENTA_R359_PUBLICATION then
  PENTA_PUBLICATION_VARIANT =
    "r359-vblank-palette-map-stage1-only-window-atomic-v5"
end
if PENTA_R360_PUBLICATION then
  PENTA_PUBLICATION_VARIANT =
    "r360-vblank-palette-map-window-fast-atomic-v6"
end
if PENTA_R361_PUBLICATION then
  PENTA_PUBLICATION_VARIANT =
    "r361-vblank-palette-map-window-robust-atomic-v7"
end
if PENTA_R362_PUBLICATION then
  PENTA_PUBLICATION_VARIANT =
    "r362-vblank-palette-map-window-final-atomic-v8"
end
if PENTA_R363_PUBLICATION or PENTA_R435_PUBLICATION then
  -- Both exact Python-authenticated layouts retain the same commit PCs and
  -- paired-window protocol; r374 adds the independently checked entry guard.
  PENTA_PUBLICATION_VARIANT = PENTA_EXPECTED_PUBLICATION_VARIANT
end
if PENTA_R449F_PREHELPER_PUBLICATION then
  PENTA_PUBLICATION_VARIANT = PENTA_EXPECTED_PUBLICATION_VARIANT
end
PENTA_PUBLICATION_PC = (PENTA_R347_PUBLICATION or PENTA_R348_PUBLICATION)
  and 0x741F
  or (PENTA_R349_PUBLICATION and 0x7425)
  or (PENTA_R350_PUBLICATION and 0x7427)
  or (PENTA_R449F_PREHELPER_PUBLICATION and 0x7457)
  or (PENTA_R351_PUBLICATION and 0x7427)
  or (PENTA_R354_PUBLICATION and 0x742C)
  or (PENTA_R356_PUBLICATION and 0x7452)
  or (PENTA_R357_PUBLICATION and 0x7459)
  or (PENTA_R358_PUBLICATION and 0x7460)
  or (PENTA_R359_PUBLICATION and 0x7465)
  or (PENTA_R360_PUBLICATION and 0x7456)
  or (PENTA_R361_PUBLICATION and 0x7456)
  or (PENTA_R362_PUBLICATION and 0x7457)
  or (PENTA_R363_PUBLICATION and 0x7457)
  or (PENTA_R435_PUBLICATION and 0x7457)
  or (PENTA_LEGACY_PUBLICATION and 0x12EC or 0x12FF)
PENTA_PUBLICATION_SEGMENT = (
  PENTA_R347_PUBLICATION or PENTA_R348_PUBLICATION
  or PENTA_R349_PUBLICATION or PENTA_R350_PUBLICATION
  or PENTA_R351_PUBLICATION or PENTA_R354_PUBLICATION
  or PENTA_R356_PUBLICATION or PENTA_R357_PUBLICATION
  or PENTA_R358_PUBLICATION
  or PENTA_R359_PUBLICATION
  or PENTA_R360_PUBLICATION
  or PENTA_R361_PUBLICATION
  or PENTA_R362_PUBLICATION
  or PENTA_R363_PUBLICATION
  or PENTA_R435_PUBLICATION
  or PENTA_R449F_PREHELPER_PUBLICATION
) and 0x0D or 0
assert(PENTA_PUBLICATION_VARIANT == PENTA_EXPECTED_PUBLICATION_VARIANT,
  "spike publisher variant differs from Python preflight")
assert(PENTA_PUBLICATION_PC == PENTA_EXPECTED_PUBLICATION_PC,
  "spike publisher PC differs from Python preflight")
if watchdog then watchdog:write("init:publication-contract\n"); watchdog:flush() end
local SETTLE = tonumber(os.getenv("STAGE1_SPIKE_SETTLE") or "180")
local frame = 0
local state_loaded = os.getenv("PENTA_STATE_PRELOADED") == "1"
local mismatches = {}
local cell_trace = {}
local last_cell = ""
local tracked_offsets = {}
local tracked_ids = {}
local transient_mismatch_frames = {}
local transient_mismatch_trace = {}
local first_transient_mismatch = ""
local first_transient_batch_state = ""
local inactive_preparation_mismatch_frames = {}
local inactive_preparation_mismatch_trace = {}
local map_flip_events = 0
local unsafe_map_flip_events = 0
PENTA_PRIMARY_FF97_02_EVENTS = 0
local map_flip_trace = {}
-- Room semantics belong to a completed physical BG-map publication.  FFBD can
-- commit the incoming room while the outgoing page remains on screen, so it
-- must never select the visible/map-flip oracle.  Capture FFE5 at the native
-- copy entry, promote that pending owner only at the corresponding LCDC
-- publication boundary, and retain one owner record per physical page.
local pending_map_publications = {}
local physical_map_owners = {}
local physical_map_owner_epoch = 0
local map_owner_seed_events = 0
local map_owner_publications = 0
local map_owner_reused_flips = 0
local map_owner_superseded_arms = 0
local map_owner_invalid_publications = 0
local map_owner_missing_flip_events = 0
local map_owner_missing_visible_frames = 0
local map_owner_live_room_divergence_frames = 0
local map_owner_trace = {}
local raw49_trace = {}
local last_raw49 = -1
local main_loop_hits, tile_copy_hits, pure_tail_hits, atomic_wrap_hits = 0, 0, 0, 0
local hazard_trampoline_hits, hazard_dispatcher_hits, hazard_helper_hits = 0, 0, 0
local hazard_row_hits = 0
local invalid_hazard_row_writes = 0
local hazard_event_trace = {}
local helper_bank_values = {}
local pure_setup_hits, atomic_path_hits = 0, 0
local tile_copy_states = {}
local phase_cache_trace = {}
local last_phase_cache = ""
local rendered_phase_trace = {}
local rendered_phase_seen = {}
local rendered_phase_oam_trace = {}
local rendered_phase_map_trace = {}
local periodic_render_trace = {}
local periodic_render_oam_trace = {}
PENTA_PERIODIC_RENDER_MAP_TRACE = {}
local compiler_unreadable_scene_frames = 0
local oam_dma_unreadable_scene_frames = 0
local last_readable_scene = 0x02
local memory_trace_path = os.getenv("STAGE1_SPIKE_MEMORY_TRACE")
local memory_trace = memory_trace_path
  and assert(io.open(memory_trace_path, "wb")) or nil
if watchdog then watchdog:write("init:globals\n"); watchdog:flush() end
local diag_break_address = tonumber(
  os.getenv("STAGE1_SPIKE_DIAG_BREAK_ADDR") or "-1")
local transient_check_start = tonumber(
  os.getenv("STAGE1_SPIKE_TRANSIENT_START") or "120")
local forced_phase_offset = tonumber(
  os.getenv("STAGE1_SPIKE_PHASE_OFFSET") or "-1")
local input_mask = tonumber(os.getenv("STAGE1_SPIKE_KEYS") or "0")
local post_menu_input_mask = tonumber(
  os.getenv("STAGE1_SPIKE_POST_MENU_KEYS") or "-1")
local menu_cycle = os.getenv("STAGE1_SPIKE_MENU_OPEN") == "1"
local menu_open_frame = tonumber(
  os.getenv("STAGE1_SPIKE_MENU_OPEN_FRAME") or "160")
local menu_close_frame = tonumber(
  os.getenv("STAGE1_SPIKE_MENU_CLOSE_FRAME") or "-1")
local menu_use_frame = tonumber(
  os.getenv("STAGE1_SPIKE_MENU_USE_FRAME") or "-1")
local low_health_frame = tonumber(
  os.getenv("STAGE1_SPIKE_LOW_HEALTH_FRAME") or "-1")
local menu_anchor_room = tonumber(
  os.getenv("STAGE1_SPIKE_MENU_ANCHOR_ROOM") or "-1")
local menu_anchor_delay = tonumber(
  os.getenv("STAGE1_SPIKE_MENU_ANCHOR_DELAY") or "20")
local menu_anchor_frame = -1
PENTA_MENU_ANCHOR_STARTED = menu_anchor_room < 0
PENTA_MENU_STABLE_ROOM = -1
PENTA_MENU_STABLE_FRAMES = 0
PENTA_MENU_STAGE1_SEEN = false
PENTA_INPUT_TRACE = {}
local effective_menu_open_frame = menu_open_frame
local effective_menu_close_frame = menu_close_frame
local effective_menu_use_frame = menu_use_frame
local effective_low_health_frame = low_health_frame
local low_health_forced_frames = 0
local low_health_scene_frames = 0
local menu_open_frames = 0
local menu_use_input_frames = 0
local menu_map_alias_frames = 0
local first_menu_map_alias = ""
local menu_hud_before_use = -1
local menu_hud_change_frame = -1
local menu_hp_before_use = -1
local menu_hp_change_frame = -1
local menu_hp_after_use = -1
local menu_a_handler_hits = 0
local menu_item_dispatch_hits = 0
local menu_heal_handler_hits = 0
local menu_selected_item_trace = {}
local menu_closed_frame = -1
local menu_seen = false
local post_menu_closed_frames = 0
local post_menu_input_frames = 0
local menu_close_repair_hits = 0
local menu_close_copy_hits = 0
local menu_close_native_tail_hits = 0
local menu_close_trace = {}
local stale_window_cleanup_hits = 0
local stale_window_cleanup_states = {}
local menu_state_trace = {}
local last_menu_state = ""
local screenshot_interval = tonumber(
  os.getenv("STAGE1_SPIKE_SCREENSHOT_INTERVAL") or "0")
local force_miniboss_frame = tonumber(
  os.getenv("STAGE1_SPIKE_FORCE_MINIBOSS_FRAME") or "-1")
local reinitialize_runtime = os.getenv("STAGE1_SPIKE_REINIT") ~= "0"
local expected_load_count = tonumber(
  os.getenv("STAGE1_SPIKE_EXPECTED_LOAD_COUNT") or "16")
local refresh_runtime_code = os.getenv("STAGE1_SPIKE_REFRESH_CODE") ~= "0"
local trace_writers = os.getenv("STAGE1_SPIKE_TRACE_WRITERS") == "1"
local trace_routes = os.getenv("STAGE1_SPIKE_TRACE_ROUTES") ~= "0"
local writer_trace = {}
local focus_start = tonumber(os.getenv("STAGE1_SPIKE_FOCUS_START") or "-1")
local focus_end = tonumber(os.getenv("STAGE1_SPIKE_FOCUS_END") or "-1")
local hazard_focus_trace = {}
local last_writer_pc, last_writer_bank = -1, -1
local watched_snapshot = ""
local miniboss_first_frame = -1
local miniboss_trace = {}
local last_miniboss_state = ""
local progress_trace = {}
local palette_mismatch_frames = {}
local first_palette_mismatch = ""
local post_miniboss_hazard_helper_hits = 0
local post_miniboss_hazard_row_hits = 0
local miniboss_hram = ""
local miniboss_rst18_flags = {}
local expected_bg5 = os.getenv("STAGE1_SPIKE_EXPECTED_BG5")
  or "7FFF,03FF,001F,0000"
local expected_bg7 = os.getenv("STAGE1_SPIKE_EXPECTED_BG7")
  or "7FFF,7E94,03FF,0000"
local expected_bank1_art = assert(os.getenv("STAGE1_SPIKE_EXPECTED_BANK1_ART"))
local bank1_art_trace = {}
local last_bank1_art_state = ""
local stage1_code_bank = tonumber(
  os.getenv("STAGE1_SPIKE_CODE_BANK") or "14")
local semantic_helper_bank = assert(tonumber(
  os.getenv("STAGE1_SPIKE_SEMANTIC_HELPER_BANK")),
  "STAGE1_SPIKE_SEMANTIC_HELPER_BANK required")
assert(semantic_helper_bank == 0x14,
  "expanded semantic helper bank changed")
local semantic_write_sites = {}
do
  local spec = assert(os.getenv("STAGE1_SPIKE_SEMANTIC_WRITE_SITES"),
    "STAGE1_SPIKE_SEMANTIC_WRITE_SITES required")
  local seen = {}
  for address_text in spec:gmatch("[^,]+") do
    assert(address_text:match("^%x%x%x%x$"),
      "malformed semantic write-site address")
    local address = assert(tonumber(address_text, 16))
    assert(not seen[address], "duplicate semantic write-site address")
    seen[address] = true
    semantic_write_sites[#semantic_write_sites + 1] = address
  end
  assert(#semantic_write_sites == 8,
    "expected four primary and four room01 semantic write sites")
end
local floor_mismatch_frames = {}
local floor_mismatch_trace = {}
local first_floor_mismatch = ""
local floor_lut_trace = {}
local last_floor_lut = ""
local floor_lut_mismatch_frames = {}
local endpoint_mismatch_frames = {}
local endpoint_mismatch_trace = {}
local first_endpoint_mismatch = ""
local post_menu_transient_mismatch_frames = 0
local post_menu_palette_mismatch_frames = 0
local post_menu_floor_mismatch_frames = 0
local post_menu_endpoint_mismatch_frames = 0
local visible_attr_mismatch_frames = {}
local visible_attr_mismatch_trace = {}
local first_visible_attr_mismatch = ""
local post_menu_visible_attr_mismatch_frames = 0
local atomic_source_trace = {}
local atomic_source_seen = {}
local atomic_floor_lut_mismatch_hits = 0
local hazard_attr_write_trace = {}
local visible_hazard_attr_write_trace = {}
local semantic_attr_write_counters = {
  hits = 0, hidden = 0, base9800 = 0, base9c00 = 0,
  invalid = 0, bank_mismatch = 0, trace_dropped = 0,
  active = 0, post_menu_active = 0, installed_sites = 0,
}

local function focus_event(value)
  if focus_start >= 0 and frame >= focus_start and frame <= focus_end
      and #hazard_focus_trace < 4096 then
    hazard_focus_trace[#hazard_focus_trace + 1] = value
  end
end
local floor_tiles = {
  0x2A, 0x2B, 0x2C, 0x2D, 0x2E,
  0x3A, 0x3B, 0x3C, 0x3D, 0x4C, 0x4D,
}

local function menu_hud_checksum()
  local value = 0
  for offset = 0, 119 do
    value = (value + emu:read8(0xC4E0 + offset) * (offset + 1)) & 0xFFFF
  end
  return value
end

local function read_register(name)
  local readers = {
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:getRegister(string.upper(name)) end,
    function() return emu:readRegister(string.lower(name)) end,
    function() return emu:readRegister(string.upper(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value then return value & 0xFFFF end
  end
  return -1
end

local function bg_map_base(lcdc)
  return (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
end

local function active_map_owner()
  local base = bg_map_base(emu:read8(0xFF40))
  return base, physical_map_owners[base]
end

local function seed_active_map_owner()
  local base = bg_map_base(emu:read8(0xFF40))
  physical_map_owners[base] = {
    room = INITIAL_MAP_ROOM,
    epoch = 0,
    publish_frame = frame,
    source = "fixture",
  }
  map_owner_seed_events = map_owner_seed_events + 1
  map_owner_trace[#map_owner_trace + 1] = string.format(
    "f%d:b%04X:r%02X:e0:seed", frame, base, INITIAL_MAP_ROOM)
end
if state_loaded then seed_active_map_owner() end

local function arm_physical_map_publication()
  if not state_loaded or (emu:read8(0xD880) & 0xF7) ~= 0x02 then
    return false
  end
  -- $42A7 exists in every switchable bank.  Native menu/window code reaches
  -- the same numeric PC in other banks with HL=$46E9/$46EF; those are address
  -- aliases, not malformed map publications.  The physical tile copier is
  -- bank 1, while an invalid H inside that exact bank remains a hard failure.
  if emu:read8(0xFF99) ~= 0x01 then return false end
  local destination_high = (read_register("HL") >> 8) & 0xFF
  if destination_high ~= 0x98 and destination_high ~= 0x9C then
    map_owner_invalid_publications = map_owner_invalid_publications + 1
    return false
  end
  local destination = destination_high << 8
  if pending_map_publications[destination] ~= nil then
    -- More than one hidden-page refresh before selection is legal.  Only the
    -- latest completed source epoch can become visible at the later flip.
    map_owner_superseded_arms = map_owner_superseded_arms + 1
  end
  -- Bind the source bytes to this copy epoch.  The rotating-hazard compiler
  -- may begin preparing the next C1A0 phase before the completed physical map
  -- reaches its later LCDC publication breakpoint; consulting live C1A0 at
  -- that point therefore compares two different, individually valid phases.
  local source_tiles = {}
  for offset = 0, 24 * 24 - 1 do
    source_tiles[offset + 1] = emu:read8(0xC1A0 + offset)
  end
  pending_map_publications[destination] = {
    destination = destination,
    -- FFE5 is the native prepublication room selector.  Unlike FFBD, it is
    -- sampled at the exact copy epoch whose C1A0 bytes are about to be used.
    room = emu:read8(0xFFE5),
    live_room = emu:read8(0xFFBD),
    start_frame = frame,
    tiles = source_tiles,
  }
  return true
end

if diag_break_address >= 0 and watchdog then pcall(function()
  emu:setBreakpoint(function()
    local sp = read_register("SP")
    watchdog:write(string.format(
      "break\t%04X\tpc=%04X\tsp=%04X\tbank=%02X\tlcdc=%02X\tstat=%02X" ..
      "\tstack=%02X,%02X,%02X,%02X\n", diag_break_address,
      read_register("PC"), sp, emu:read8(0xFF99), emu:read8(0xFF40),
      emu:read8(0xFF41), emu:read8(sp), emu:read8((sp + 1) & 0xFFFF),
      emu:read8((sp + 2) & 0xFFFF), emu:read8((sp + 3) & 0xFFFF)))
    watchdog:flush()
    if emu.stop then emu:stop() end
  end, diag_break_address, diag_break_address < 0x4000 and -1 or 1)
end) end

local function sampled_scene()
  local pc = read_register("PC")
  local compiler_unreadable = (emu:read8(0xFF70) & 0x07) == 0x03
    and ((emu:read8(0xFF99) == 1 and (
        (pc >= 0x42A7 and pc <= 0x436D)
        or (pc >= 0xD400 and pc <= 0xD478)))
      or (PENTA_R435_PUBLICATION and emu:read8(0xFF99) == 30
        and pc >= 0x6D00 and pc < 0x7890))
  if compiler_unreadable then
    compiler_unreadable_scene_frames = compiler_unreadable_scene_frames + 1
    return last_readable_scene, true, pc
  end
  local scene = emu:read8(0xD880)
  -- During the stock HRAM OAM-DMA loop, CPU-bus reads from WRAM return FF.
  -- Do not turn that inaccessible instant into a fake scene-$FF/floor-LUT/
  -- endpoint failure; the rendered frame still uses the completed VRAM map.
  if pc >= 0xFF80 and pc <= 0xFFFE and scene == 0xFF then
    oam_dma_unreadable_scene_frames = oam_dma_unreadable_scene_frames + 1
    return last_readable_scene, true, pc
  end
  last_readable_scene = scene
  return scene, false, pc
end

local function is_floor_tile(tile)
  return (tile >= 0x2A and tile <= 0x2E)
    or (tile >= 0x3A and tile <= 0x3D)
    or tile == 0x4C or tile == 0x4D
end

local function floor_lut_mismatches()
  local mismatches = {}
  for _, tile in ipairs(floor_tiles) do
    local palette = emu:read8(0xC600 + tile) & 0x07
    if palette ~= 0 then
      mismatches[#mismatches + 1] = string.format("%02X/%d", tile, palette)
    end
  end
  return table.concat(mismatches, ",")
end

-- Stage-1 room $05 uses 2A-2E/3A-3D for a 252-cell patterned floor; 4C/4D
-- build the lower platform in the adjacent room. They are environment art,
-- not part of the rotating 60-7F cylinder family. Inspect every tile that can
-- contribute pixels to the current LCD viewport, including partially exposed
-- edge tiles. The alternate map is checked as soon as stock makes it visible;
-- this preserves the fast off-screen preparation path while making any
-- player-visible palette leak a frame-exact failure.
local function inspect_floor_environment()
  local old_vbk = emu:read8(0xFF4F)
  local mismatches = {}
  local base = (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local columns = 20 + ((scx & 0x07) ~= 0 and 1 or 0)
  local rows = 18 + ((scy & 0x07) ~= 0 and 1 or 0)
  local tiles = {}
  emu:write8(0xFF4F, 0)
  for screen_row = 0, rows - 1 do
    local map_row = ((scy >> 3) + screen_row) & 0x1F
    for screen_column = 0, columns - 1 do
      local map_column = ((scx >> 3) + screen_column) & 0x1F
      local offset = map_row * 32 + map_column
      tiles[offset] = emu:read8(base + offset)
    end
  end
  emu:write8(0xFF4F, 1)
  for offset, tile in pairs(tiles) do
    if is_floor_tile(tile) then
      local attr = emu:read8(base + offset) & 0x07
      if attr ~= 0 and #mismatches < 24 then
        mismatches[#mismatches + 1] = string.format(
          "%04X/%03X/%02X/%d", base, offset, tile, attr)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatches
end

local function is_tooth_tile(tile)
  return (tile >= 0x64 and tile <= 0x69)
    or (tile >= 0x74 and tile <= 0x79)
end

local function is_retracted_tile(tile)
  return tile >= 0x01 and tile <= 0x04
end

local function immutable_tile_attr(tile)
  local offset = tile * 2 + 1
  return assert(tonumber(
    EXPECTED_ATTR_TABLE:sub(offset, offset + 1), 16))
end

-- Exact VRAM attribute, including the pattern-bank bit. Only real animated
-- teeth use bank-1 artwork; retracted floor cells return to their YAML role.
local function expected_semantic_attr(tile)
  if is_tooth_tile(tile) then return 0x0F end
  -- Do not derive the oracle from the mutable C600 table being tested.
  -- scene_detect copies that table over several thousand cycles, so a frame
  -- callback can observe a partially replaced page during the $02->$0A
  -- low-health/miniboss handoff. More importantly, trusting C600 here would
  -- let an implementation bug redefine the expected answer. The reviewed
  -- Stage-1 hazard schema is the independent authority.
  if tile >= 0x01 and tile <= 0x04 then return 0x00 end
  if tile == 0x60 or tile == 0x61 or tile == 0x62
      or tile == 0x6B or tile == 0x6F
      or tile == 0x6C or tile == 0x6D or tile == 0x6E
      or tile == 0x70 or tile == 0x71 or tile == 0x72
      or tile == 0x7B or tile == 0x7F
      or tile == 0x7C or tile == 0x7D or tile == 0x7E then
    return 0x05
  end
  if tile >= 0x60 and tile <= 0x7F then return 0x06 end
  return immutable_tile_attr(tile)
end

local function is_semantic_hazard_cell(tile)
  return is_retracted_tile(tile) or (tile >= 0x60 and tile <= 0x7F)
end

local function expected_cell_attr(room, offset, tile)
  -- These two translated north-seam cells are position-owned metallic wall
  -- edges. They are the sole Stage-1 exception to the immutable per-tile
  -- table outside the moving hazard family.
  if (offset == 0x18D or offset == 0x1AD)
      and (tile == 0x21 or tile == 0x31) then
    return 0x06
  end
  -- Room $01 reuses eight ordinary wall IDs. Four already have the same
  -- immutable value; $24/$27/$30/$33 deliberately diverge from the global
  -- table. This expectation comes from the independently reviewed fixture
  -- supplied by Python, never from the candidate-owned mutable C600 page.
  local reviewed = reviewed_room_local_attrs[room * 0x100 + tile]
  if reviewed ~= nil then return reviewed end
  return expected_semantic_attr(tile)
end

-- Hardware reports repeatedly exposed colored ordinary cells that were not
-- part of the historical eleven-ID floor whitelist. Inspect every tile that
-- contributes pixels to the current background viewport. The oracle is the
-- candidate-bound immutable table plus the reviewed moving-hazard and seam
-- rules above; mutable C600 can no longer redefine the expected result.
local function inspect_visible_attributes()
  local old_vbk = emu:read8(0xFF4F)
  local mismatches = {}
  local base, owner = active_map_owner()
  if owner == nil then
    map_owner_missing_visible_frames = map_owner_missing_visible_frames + 1
    return {string.format("%04X/unowned", base)}
  end
  local room = owner.room
  if room ~= emu:read8(0xFFBD) then
    map_owner_live_room_divergence_frames =
      map_owner_live_room_divergence_frames + 1
  end
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local columns = 20 + ((scx & 0x07) ~= 0 and 1 or 0)
  local rows = 18 + ((scy & 0x07) ~= 0 and 1 or 0)
  local tiles = {}
  emu:write8(0xFF4F, 0)
  for screen_row = 0, rows - 1 do
    local map_row = ((scy >> 3) + screen_row) & 0x1F
    for screen_column = 0, columns - 1 do
      local map_column = ((scx >> 3) + screen_column) & 0x1F
      local offset = map_row * 32 + map_column
      tiles[offset] = emu:read8(base + offset)
    end
  end
  emu:write8(0xFF4F, 1)
  for offset, tile in pairs(tiles) do
    local actual = emu:read8(base + offset)
    local expected = expected_cell_attr(room, offset, tile)
    if actual ~= expected and #mismatches < 48 then
      mismatches[#mismatches + 1] = string.format(
        "%04X/%03X/%02X/%02X/%02X", base, offset, tile, actual, expected)
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatches
end

-- Check the exact left/right attachment cells independently from the middle
-- span. Endpoints change between a real tooth and a retracted floor cell, so
-- validate the complete raw semantic attribute rather than forcing BG7.
local function inspect_active_endpoint_rows()
  local base, owner = active_map_owner()
  if owner == nil then
    return {string.format("%04X/unowned", base)}
  end
  local room = owner.room
  local shift = room == 0x02 and 4 or 0
  local old_vbk = emu:read8(0xFF4F)
  local mismatches = {}
  for _, row in ipairs({0x40 + shift, 0xA0 + shift}) do
    for _, column in ipairs({0, 8}) do
      emu:write8(0xFF4F, 0)
      local tile = emu:read8(base + row + column)
      emu:write8(0xFF4F, 1)
      local attr = emu:read8(base + row + column)
      local expected = expected_semantic_attr(tile)
      if attr ~= expected then
        mismatches[#mismatches + 1] = string.format(
          "%04X/%03X/%02X/%02X/%02X", base, row + column, tile,
          attr, expected)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatches
end

local function watched_bytes()
  local values = {}
  -- Watch the complete moving envelope in all four deterministic cylinder
  -- rows.  The old two-row/9-cell sample missed the lower cylinder entirely,
  -- including the exact row-8/row-11 writes that trigger after item use.
  for _, row in ipairs({2, 5, 8, 11}) do
    for column = 0, 17 do
      values[#values + 1] = string.char(
        emu:read8(0xC1A0 + row * 24 + column))
    end
  end
  return table.concat(values)
end

local function writer_breakpoint(address, segment)
  pcall(function()
    emu:setBreakpoint(function()
      if not state_loaded then return end
      if frame >= 70 then
        local current = watched_bytes()
        if watched_snapshot ~= "" and current ~= watched_snapshot then
          writer_trace[#writer_trace + 1] = string.format(
            "f%d:%02X:%04X", frame, last_writer_bank & 0xFF,
            last_writer_pc & 0xFFFF)
        end
        watched_snapshot = current
        last_writer_pc = address
        last_writer_bank = emu:read8(0xFF99)
      end
    end, address, segment)
  end)
end

pcall(function()
  -- The native publisher selects its completed physical map with the LCDC
  -- write at the reviewed publication boundary.  Hidden-map differences are legal while the map is
  -- being built; an active HDMA or a tile/attribute mismatch at this exact
  -- boundary is never legal and is the hardware-facing Pocket contract.
  emu:setBreakpoint(function()
    if not state_loaded or (emu:read8(0xD880) & 0xF7) ~= 0x02 then return end
    if PENTA_R347_PUBLICATION and emu:read8(0xFF99) ~= 0x0D then return end
    local target_lcdc = read_register("A") & 0xFF
    local target_core = target_lcdc & 0x9F
    local paired_selector =
      ((target_lcdc & 0x08) ~= 0) ~= ((target_lcdc & 0x40) ~= 0)
    if target_core ~= 0x83 and target_core ~= 0x8B then return end
    if (PENTA_PUBLICATION_VARIANT:match("^r357%-")
        or PENTA_PUBLICATION_VARIANT:match("^r358%-")
        or PENTA_PUBLICATION_VARIANT:match("^r359%-")
        or PENTA_PUBLICATION_VARIANT:match("^r360%-")
        or PENTA_PUBLICATION_VARIANT:match("^r361%-")
        or PENTA_PUBLICATION_VARIANT:match("^r362%-")
        or PENTA_PUBLICATION_VARIANT:match("^r363%-"))
        and not paired_selector then return end
    map_flip_events = map_flip_events + 1
    if emu:read8(0xFF97) == 0x02 then
      PENTA_PRIMARY_FF97_02_EVENTS = PENTA_PRIMARY_FF97_02_EVENTS + 1
    end
    local target_base = bg_map_base(target_lcdc)
    local pending = pending_map_publications[target_base]
    local expected_owner = pending or physical_map_owners[target_base]
    local room = expected_owner and expected_owner.room or nil
    local old_vbk = emu:read8(0xFF4F)
    local stat_mode = emu:read8(0xFF41) & 0x03
    local ly = emu:read8(0xFF44)
    local tile_mismatches, attr_mismatches = 0, 0
    if stat_mode ~= 3 then
      emu:write8(0xFF4F, 0)
      for row = 0, 23 do
        for column = 0, 23 do
          local source_index = row * 24 + column
          local source = expected_owner and expected_owner.tiles
            and expected_owner.tiles[source_index + 1]
            or emu:read8(0xC1A0 + source_index)
          local address = target_base + row * 32 + column
          if emu:read8(address) ~= source then
            tile_mismatches = tile_mismatches + 1
          end
        end
      end
      emu:write8(0xFF4F, 1)
      for row = 0, 23 do
        for column = 0, 23 do
          local source_index = row * 24 + column
          local source = expected_owner and expected_owner.tiles
            and expected_owner.tiles[source_index + 1]
            or emu:read8(0xC1A0 + source_index)
          local address = target_base + row * 32 + column
          local expected_attr = room ~= nil and expected_cell_attr(
            room, row * 32 + column, source) or nil
          if expected_attr == nil or emu:read8(address) ~= expected_attr then
            attr_mismatches = attr_mismatches + 1
          end
        end
      end
      emu:write8(0xFF4F, old_vbk)
    end
    local hdma5 = emu:read8(0xFF55)
    -- Mode 3 makes VRAM CPU reads unavailable but does not make the native
    -- LCDC selection illegal.  HDMA5 remains readable, and the next
    -- non-mode-3 flip must provide the byte-exact map receipt.
    -- A complete hidden page is still unsafe to publish during visible
    -- scanout. Pocket can show a sub-frame tear which a frame-end screenshot
    -- misses, so bind the publication itself to the ten VBlank lines.
    local unsafe = ly < 0x90 or ly > 0x99
      or hdma5 ~= 0xFF
      or expected_owner == nil
      or (stat_mode ~= 3
        and (tile_mismatches ~= 0 or attr_mismatches ~= 0))
    if unsafe then unsafe_map_flip_events = unsafe_map_flip_events + 1 end
    local owner_state = "reused"
    if pending ~= nil then
      pending_map_publications[target_base] = nil
      if hdma5 == 0xFF then
        physical_map_owner_epoch = physical_map_owner_epoch + 1
        pending.epoch = physical_map_owner_epoch
        pending.publish_frame = frame
        pending.source = "publication"
        physical_map_owners[target_base] = pending
        map_owner_publications = map_owner_publications + 1
        expected_owner = pending
        owner_state = "published"
        map_owner_trace[#map_owner_trace + 1] = string.format(
          "f%d:b%04X:r%02X:e%d:published:lr%02X", frame, target_base,
          pending.room, pending.epoch, pending.live_room)
      else
        map_owner_invalid_publications = map_owner_invalid_publications + 1
        owner_state = "invalid"
      end
    elseif expected_owner ~= nil then
      map_owner_reused_flips = map_owner_reused_flips + 1
    else
      map_owner_missing_flip_events = map_owner_missing_flip_events + 1
      owner_state = "unowned"
    end
    if #map_flip_trace < 128 then
      map_flip_trace[#map_flip_trace + 1] = string.format(
        "f%d:b%04X:h%02X:s%d:ly%02X:x%02X:t%d:a%d:%s:r%02X:e%d:%s", frame,
        target_base, hdma5, stat_mode, ly, emu:read8(0xFF97),
        tile_mismatches, attr_mismatches,
        unsafe and "bad" or "ok",
        expected_owner and expected_owner.room or 0xFF,
        expected_owner and expected_owner.epoch or -1, owner_state)
    end
  end, PENTA_PUBLICATION_PC, PENTA_PUBLICATION_SEGMENT)
  if watchdog then watchdog:write("init:publication-breakpoint\n"); watchdog:flush() end

  emu:setBreakpoint(function()
    if state_loaded then menu_a_handler_hits = menu_a_handler_hits + 1 end
  end, 0x1DE4, -1)
  emu:setBreakpoint(function()
    if state_loaded then
      menu_item_dispatch_hits = menu_item_dispatch_hits + 1
      menu_selected_item_trace[#menu_selected_item_trace + 1] = string.format(
        "f%d:g%02X:i%02X", frame, emu:read8(0xDCDB),
        emu:read8(0xDCBD + emu:read8(0xDCDB)))
    end
  end, 0x1E08, -1)
  emu:setBreakpoint(function()
    if state_loaded then menu_heal_handler_hits = menu_heal_handler_hits + 1 end
  end, 0x1F22, -1)
end)

-- These one-shot breakpoints are part of the menu-close proof, not
-- optional route diagnostics. They demonstrate that a stationary close
-- crosses the native handoff tail; map-flip and active-write receipts below
-- prove the ordinary renderer later publishes only to a hidden gameplay map.
pcall(function()
  emu:setBreakpoint(function()
    if state_loaded and emu:read8(0xFF99) == 13 then
      stale_window_cleanup_hits = stale_window_cleanup_hits + 1
      local key = string.format("%02X/%02X/%02X",
        emu:read8(0xFFE4), emu:read8(0xD880), emu:read8(0xFF70))
      stale_window_cleanup_states[key] =
        (stale_window_cleanup_states[key] or 0) + 1
    end
  end, 0x6A40, -1)
  emu:setBreakpoint(function()
    if state_loaded then
      menu_close_repair_hits = menu_close_repair_hits + 1
      menu_close_native_tail_hits = menu_close_native_tail_hits + 1
      menu_close_trace[#menu_close_trace + 1] = string.format(
        "f%d:tail:b%02X:l%02X:d%02X:c%02X/%02X", frame,
        emu:read8(0xFF99), emu:read8(0xFF40), emu:read8(0xDC0B),
        emu:read8(0xDF53), emu:read8(0xDF57))
    end
  end, 0x77A8, 1)
  emu:setBreakpoint(function()
    if state_loaded then
      menu_close_copy_hits = menu_close_copy_hits + 1
      if menu_seen and #menu_close_trace < 16 then
        menu_close_trace[#menu_close_trace + 1] = string.format(
          "f%d:9c:b%02X:l%02X:d%02X", frame, emu:read8(0xFF99),
          emu:read8(0xFF40), emu:read8(0xDC0B))
      end
    end
  end, 0x42A0, 1)
end)

if trace_writers then
  local write_opcodes = {
    [0x02]=true, [0x12]=true, [0x22]=true, [0x32]=true, [0x36]=true,
    [0x70]=true, [0x71]=true, [0x72]=true, [0x73]=true, [0x74]=true,
    [0x75]=true, [0x77]=true, [0xCB]=true, [0xE0]=true, [0xEA]=true,
  }
  for address = 0, 0x3FFF do
    if write_opcodes[emu:read8(address)] then writer_breakpoint(address, -1) end
  end
  for address = 0x4000, 0x7FFF do
    if write_opcodes[emu:read8(address)] then writer_breakpoint(address, 1) end
  end
end

local function expected_palette(tile)
  local tooth =
    (tile >= 0x64 and tile <= 0x69) or
    (tile >= 0x74 and tile <= 0x79)
  local fire =
    tile == 0x60 or tile == 0x61 or tile == 0x62 or
    tile == 0x6B or tile == 0x6F or
    tile == 0x6C or tile == 0x6D or tile == 0x6E or
    tile == 0x70 or tile == 0x71 or tile == 0x72 or
    tile == 0x7B or tile == 0x7F or
    tile == 0x7C or tile == 0x7D or tile == 0x7E
  return tooth and 7 or (fire and 5 or 6)
end


if trace_routes then pcall(function()
  -- Do not breakpoint the shared RST $18 vector here. The scene-$0A hazard
  -- publisher legitimately reaches it many times per copied map; observing
  -- every invocation made the diagnostic frontend spend minutes inside the
  -- callback even though a breakpoint-free liveness probe advanced normally.
  -- The route and output contracts below are stronger than the retired flag
  -- histogram, which was never consumed by the Python verifier.
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 then main_loop_hits = main_loop_hits + 1 end
  end, 0x016C)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if not arm_physical_map_publication() then return end
    if frame >= 80 then
      tile_copy_hits = tile_copy_hits + 1
      if #hazard_event_trace < 1000 then
        table.insert(hazard_event_trace, string.format(
          "f%d:copy:hl%04X:d%02X", frame,
          emu:readRegister("hl"), emu:read8(0xDC0B)))
      end
      local key = string.format("%02X/%02X",
        emu:read8(0xD880), emu:read8(0xDCFD))
      tile_copy_states[key] = (tile_copy_states[key] or 0) + 1
      focus_event(string.format("f%d:copy:hl%04X:d%02X:s%02X:r%02X",
        frame, emu:readRegister("hl"), emu:read8(0xDC0B),
        emu:read8(0xD880), emu:read8(0xFFBD)))
    end
  end, 0x42A7, 1)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 then atomic_path_hits = atomic_path_hits + 1 end
    focus_event(string.format("f%d:atomic:d%02X:s%02X:r%02X",
      frame, emu:read8(0xDC0B), emu:read8(0xD880), emu:read8(0xFFBD)))
    if frame >= 80 and #atomic_source_trace < 96 then
      local counts = {pattern=0, floor4c=0, floor4d=0, family=0}
      for address = 0xC1A0, 0xC3DF do
        local tile = emu:read8(address)
        if (tile >= 0x2A and tile <= 0x2E)
            or (tile >= 0x3A and tile <= 0x3D) then
          counts.pattern = counts.pattern + 1
        end
        if tile == 0x4C then counts.floor4c = counts.floor4c + 1 end
        if tile == 0x4D then counts.floor4d = counts.floor4d + 1 end
        if tile >= 0x60 and tile <= 0x7F then
          counts.family = counts.family + 1
        end
      end
      local floor_lut_mismatch = floor_lut_mismatches()
      local signature = string.format(
        "r%02X:p%d:c%d:d%d:h%d:l%s", emu:read8(0xFFBD),
        counts.pattern, counts.floor4c, counts.floor4d, counts.family,
        floor_lut_mismatch == "" and "ok" or floor_lut_mismatch)
      if counts.pattern + counts.floor4c + counts.floor4d > 0
          and floor_lut_mismatch ~= "" then
        atomic_floor_lut_mismatch_hits = atomic_floor_lut_mismatch_hits + 1
      end
      if not atomic_source_seen[signature] then
        atomic_source_seen[signature] = true
        atomic_source_trace[#atomic_source_trace + 1] = string.format(
          "f%d:%s", frame, signature)
      end
    end
  end, 0x42B2)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 then pure_setup_hits = pure_setup_hits + 1 end
  end, 0x432E)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 then pure_tail_hits = pure_tail_hits + 1 end
  end, 0x4358)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 then atomic_wrap_hits = atomic_wrap_hits + 1 end
  end, 0x3498)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 then hazard_trampoline_hits = hazard_trampoline_hits + 1 end
  end, 0x0847)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 and emu:read8(0xFF99) == 0x0D then
      hazard_dispatcher_hits = hazard_dispatcher_hits + 1
    end
  end, 0x7B9C)
  emu:setBreakpoint(function()
    if not state_loaded then return end
    if frame >= 80 and emu:read8(0xFF99) == stage1_code_bank then
      hazard_helper_hits = hazard_helper_hits + 1
      if emu:read8(0xD880) == 0x0A and emu:read8(0xFFBF) ~= 0 then
        post_miniboss_hazard_helper_hits =
          post_miniboss_hazard_helper_hits + 1
      end
      helper_bank_values[emu:read8(0xFF99)] = true
      focus_event(string.format("f%d:hook:d%02X:s%02X:r%02X:hl%04X",
        frame, emu:read8(0xDC0B), emu:read8(0xD880),
        emu:read8(0xFFBD), emu:readRegister("hl")))
      if #hazard_event_trace < 1000 then
        local source_rows = {}
        for _, row in ipairs({2, 5, 8, 11}) do
          local cells = {}
          for column = 4, 14 do
            cells[#cells + 1] = string.format(
              "%02X", emu:read8(0xC1A0 + row * 24 + column))
          end
          source_rows[#source_rows + 1] = table.concat(cells)
        end
        table.insert(hazard_event_trace, string.format(
          "f%d:hook:d%02X:r%02X:s%02X:q%s/%s/%s/%s", frame,
          emu:read8(0xDC0B), emu:read8(0xFFBD), emu:read8(0xDC0E),
          source_rows[1], source_rows[2], source_rows[3], source_rows[4]))
      end
    end
  end, 0x6BA7)
  -- Do not breakpoint the expanded semantic row helper. On the mGBA build
  -- used by CI, that switchable-bank breakpoint can stop the core before the
  -- next frame and turn a healthy ROM into a verifier timeout. Python binds
  -- the exact helper/trampoline/LUT bytes; rendered frames independently
  -- validate tile, raw attribute, endpoints, and both physical maps.
end) end

-- The physical-map owner is part of the broad oracle, not optional route
-- diagnostics.  Avoid registering two callbacks at the same address because
-- some mGBA scripting builds replace rather than append breakpoints.
if not trace_routes then pcall(function()
  emu:setBreakpoint(arm_physical_map_publication, 0x42A7, 1)
end) end

-- Hardware-facing release contract: the semantic helper must only touch the
-- map that is currently hidden. Keep all eight narrowly bank-gated probes
-- enabled even when verbose route tracing is off. A write can finish with
-- exact VRAM and still paint a visible scanline on Pocket/mGBA earlier in the
-- frame; that was the blind spot behind the menu-close trail regression.
pcall(function()
  for _, address in ipairs(semantic_write_sites) do
    local breakpoint_id = emu:setBreakpoint(function()
      if not state_loaded then return end
      if emu:read8(0xFF99) ~= semantic_helper_bank then
        semantic_attr_write_counters.bank_mismatch =
          semantic_attr_write_counters.bank_mismatch + 1
        return
      end
      semantic_attr_write_counters.hits =
        semantic_attr_write_counters.hits + 1
      local hl = read_register("HL") & 0xFFFF
      local destination = hl & 0xFC00
      local active = (emu:read8(0xFF40) & 0x08) ~= 0
        and 0x9C00 or 0x9800
      local valid = destination == 0x9800 or destination == 0x9C00
      local visible = valid and destination == active
      local disposition = "INVALID"
      if not valid then
        semantic_attr_write_counters.invalid =
          semantic_attr_write_counters.invalid + 1
      elseif destination == 0x9800 then
        semantic_attr_write_counters.base9800 =
          semantic_attr_write_counters.base9800 + 1
      else
        semantic_attr_write_counters.base9c00 =
          semantic_attr_write_counters.base9c00 + 1
      end
      if visible then
        disposition = "VISIBLE"
        semantic_attr_write_counters.active =
          semantic_attr_write_counters.active + 1
        if menu_closed_frame >= 0 then
          semantic_attr_write_counters.post_menu_active =
            semantic_attr_write_counters.post_menu_active + 1
        end
        if #visible_hazard_attr_write_trace < 128 then
          visible_hazard_attr_write_trace[
            #visible_hazard_attr_write_trace + 1] = string.format(
              "f%d:p%04X:h%04X:a%04X:s%d:l%02X", frame, address,
              hl, active, emu:read8(0xFF41) & 0x03, emu:read8(0xFF44))
        end
      elseif valid then
        disposition = "hidden"
        semantic_attr_write_counters.hidden =
          semantic_attr_write_counters.hidden + 1
      end
      if #hazard_attr_write_trace < 512 then
        hazard_attr_write_trace[#hazard_attr_write_trace + 1] = string.format(
          "f%d:p%04X:h%04X:a%04X:s%d:l%02X:%s", frame, address,
          hl, active, emu:read8(0xFF41) & 0x03, emu:read8(0xFF44),
          disposition)
      else
        semantic_attr_write_counters.trace_dropped =
          semantic_attr_write_counters.trace_dropped + 1
      end
    end, address, semantic_helper_bank)
    if breakpoint_id and breakpoint_id > 0 then
      semantic_attr_write_counters.installed_sites =
        semantic_attr_write_counters.installed_sites + 1
    end
  end
end)

local function cram_word(palette, color)
  local index = palette * 8 + color * 2
  emu:write8(0xFF68, index)
  local low = emu:read8(0xFF69)
  emu:write8(0xFF68, index + 1)
  local high = emu:read8(0xFF69)
  return (high << 8) | low
end

local function palette_words(palette)
  local old_index = emu:read8(0xFF68)
  local words = {}
  for color = 0, 3 do
    words[#words + 1] = cram_word(palette, color)
  end
  emu:write8(0xFF68, old_index)
  return words
end

local function obj_cram_word(palette, color)
  local index = palette * 8 + color * 2
  emu:write8(0xFF6A, index)
  local low = emu:read8(0xFF6B)
  emu:write8(0xFF6A, index + 1)
  local high = emu:read8(0xFF6B)
  return (high << 8) | low
end

local function obj_palette_words(palette)
  local old_index = emu:read8(0xFF6A)
  local words = {}
  for color = 0, 3 do
    words[#words + 1] = obj_cram_word(palette, color)
  end
  emu:write8(0xFF6A, old_index)
  return words
end

local function words_text(words)
  local values = {}
  for _, word in ipairs(words) do
    values[#values + 1] = string.format("%04X", word)
  end
  return table.concat(values, ",")
end

local function visible_oam_text()
  local entries = {}
  local sprite_height = (emu:read8(0xFF40) & 0x04) ~= 0 and 16 or 8
  for slot = 0, 39 do
    local address = 0xFE00 + slot * 4
    local y = emu:read8(address)
    local x = emu:read8(address + 1)
    if x > 0 and x < 168 and y > 0 and y < 160 + sprite_height then
      entries[#entries + 1] = string.format(
        "%d/%d/%d/%02X/%02X", slot, x, y,
        emu:read8(address + 2), emu:read8(address + 3))
    end
  end
  return table.concat(entries, ",")
end

local function phase_map_text(base, phase_offset)
  local old_vbk = emu:read8(0xFF4F)
  local center_row = phase_offset >> 5
  local entries = {}
  for row = math.max(0, center_row - 1), math.min(31, center_row + 4) do
    for column = 0, 31 do
      local offset = row * 32 + column
      emu:write8(0xFF4F, 0)
      local tile = emu:read8(base + offset)
      emu:write8(0xFF4F, 1)
      local attr = emu:read8(base + offset)
      if (tile >= 0x60 and tile <= 0x7F)
          or (tile >= 0x01 and tile <= 0x04) then
        entries[#entries + 1] = string.format(
          "%03X/%02X/%02X", offset, tile, attr)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(entries, ",")
end

function PENTA_PHASE_SIGNATURE_TEXT(base, phase_offset)
  -- The two animated tooth spans are six tile rows apart.  Serializing these
  -- exact 9-cell tile/attribute rows is sufficient to distinguish extension
  -- and retraction phases without paying the full 6x32 map scan at every
  -- screenshot.  The full map oracle still runs independently per frame.
  local old_vbk = emu:read8(0xFF4F)
  local entries = {}
  for _, row_start in ipairs({phase_offset, phase_offset + 0x60}) do
    for column = 0, 8 do
      local offset = row_start + column
      emu:write8(0xFF4F, 0)
      local tile = emu:read8(base + offset)
      emu:write8(0xFF4F, 1)
      local attr = emu:read8(base + offset)
      entries[#entries + 1] = string.format(
        "%03X/%02X/%02X", offset, tile, attr)
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(entries, ",")
end

local function inspect_map(base)
  local found, matched = 0, 0
  local tooth_found, tooth_matched = 0, 0
  local tooth_bank1 = 0
  local fire_found, fire_matched = 0, 0
  local terminal_found, terminal_matched = 0, 0
  local support_found, support_matched = 0, 0
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  local tiles = {}
  for offset = 0, 0x3FF do tiles[offset] = emu:read8(base + offset) end
  emu:write8(0xFF4F, 1)
  for offset = 0, 0x3FF do
    local tile = tiles[offset]
    if tile >= 0x60 and tile <= 0x7F then
      found = found + 1
      local tooth =
        (tile >= 0x64 and tile <= 0x69) or
        (tile >= 0x74 and tile <= 0x79)
      local fire =
        tile == 0x60 or tile == 0x61 or tile == 0x62 or
        tile == 0x6B or tile == 0x6F or
        tile == 0x6C or tile == 0x6D or tile == 0x6E or
        tile == 0x70 or tile == 0x71 or tile == 0x72 or
        tile == 0x7B or tile == 0x7F or
        tile == 0x7C or tile == 0x7D or tile == 0x7E
      local terminal =
        tile == 0x6B or tile == 0x6F or
        tile == 0x7B or tile == 0x7F
      local expected = expected_palette(tile)
      local raw_attr = emu:read8(base + offset)
      local actual = raw_attr & 0x07
      if actual == expected then matched = matched + 1 end
      if actual ~= expected then
        table.insert(mismatches, string.format(
          "%04X,%03X,%02X,%d,%d", base, offset, tile, actual, expected))
      end
      if tooth then
        tooth_found = tooth_found + 1
        if actual == expected then tooth_matched = tooth_matched + 1 end
        if raw_attr == 0x0F then tooth_bank1 = tooth_bank1 + 1 end
      elseif fire then
        fire_found = fire_found + 1
        if actual == expected then fire_matched = fire_matched + 1 end
      else
        support_found = support_found + 1
        if actual == expected then support_matched = support_matched + 1 end
      end
      if terminal then
        terminal_found = terminal_found + 1
        if actual == 5 then terminal_matched = terminal_matched + 1 end
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return found, matched, tooth_found, tooth_matched,
    fire_found, fire_matched, terminal_found, terminal_matched,
    support_found, support_matched, tooth_bank1
end

local function capture_batch_state()
  -- The experimental batched hazard publisher owns SVBK2:D600-D689.  Capture
  -- it only on the first semantic failure, then restore the exact incoming
  -- bank before the emulated CPU resumes.  Release candidates that remain
  -- clean never touch SVBK here.
  local old_svbk = emu:read8(0xFF70) & 0x07
  emu:write8(0xFF70, 0x02)
  local staged = {}
  for address = 0xD600, 0xD689 do
    staged[#staged + 1] = string.format("%02X", emu:read8(address))
  end
  emu:write8(0xFF70, old_svbk)
  local sources = {}
  for _, row in ipairs({2, 5, 8, 11}) do
    local cells = {}
    for column = 0, 23 do
      cells[#cells + 1] = string.format(
        "%02X", emu:read8(0xC1A0 + row * 24 + column))
    end
    sources[#sources + 1] = table.concat(cells)
  end
  return string.format(
    "svbk:%02X/hdma5:%02X/vbk:%02X/lcdc:%02X/staged:%s/sources:%s",
    old_svbk, emu:read8(0xFF55), emu:read8(0xFF4F) & 0x01,
    emu:read8(0xFF40), table.concat(staged), table.concat(sources, ","))
end

local function inspect_static_tooth_rows()
  local found, matched = 0, 0
  local active_found, active_matched = 0, 0
  local mismatch_trace = {}
  local active_base = bg_map_base(emu:read8(0xFF40))
  local old_vbk = emu:read8(0xFF4F)
  for _, base in ipairs({0x9800, 0x9C00}) do
    local owner = physical_map_owners[base]
    local shift = owner ~= nil and owner.room == 0x02 and 4 or 0
    for _, row in ipairs({0x40 + shift, 0xA0 + shift}) do
      for column = 0, 8 do
        found = found + 1
        emu:write8(0xFF4F, 0)
        local tile = emu:read8(base + row + column)
        emu:write8(0xFF4F, 1)
        local attr = emu:read8(base + row + column)
        -- Static rows are part of the physical-map oracle too.  Room $01 has
        -- four reviewed wall-material overrides ($24/$27/$30/$33); using the
        -- global per-tile table here incorrectly labels those legitimate 6
        -- attributes as mismatches (the dynamic visible-attribute probe
        -- already uses expected_cell_attr).  Keep this check room-aware so
        -- its 36-cell contract agrees with the reviewed fixture.
        local expected = owner ~= nil
          and expected_cell_attr(owner.room, row + column, tile)
          or expected_semantic_attr(tile)
        if owner ~= nil and attr == expected then matched = matched + 1 end
        if base == active_base then
          active_found = active_found + 1
          if owner ~= nil and attr == expected then
            active_matched = active_matched + 1
          end
        end
        if owner == nil or attr ~= expected then
          mismatch_trace[#mismatch_trace + 1] = string.format(
            "%04X/%02X/%02X/%02X/%s/%s", base + row + column, tile,
            attr, expected,
            base == active_base and "active" or "inactive",
            owner ~= nil and string.format("r%02X:e%d", owner.room,
              owner.epoch) or "unowned")
        end
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return found, matched, active_found, active_matched,
    table.concat(mismatch_trace, ",")
end

local function bank1_art_mismatches()
  local tiles = {
    0x01, 0x02, 0x03, 0x04,
    0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
  }
  local mismatched = 0
  local mismatch_trace = {}
  local actual_art = {}
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for tile_index, tile in ipairs(tiles) do
    local start = 0x1000 + tile * 16
    local tile_mismatches = 0
    for byte = 0, 15 do
      local text_offset = ((tile_index - 1) * 16 + byte) * 2 + 1
      local expected = tonumber(
        expected_bank1_art:sub(text_offset, text_offset + 1), 16)
      local actual = emu:read8(0x8000 + start + byte)
      actual_art[#actual_art + 1] = string.format("%02x", actual)
      if actual ~= expected then
        mismatched = mismatched + 1
        tile_mismatches = tile_mismatches + 1
      end
    end
    if tile_mismatches > 0 then
      mismatch_trace[#mismatch_trace + 1] = string.format(
        "%02X/%d", tile, tile_mismatches)
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatched, table.concat(mismatch_trace, ","), table.concat(actual_art)
end

local function finish()
  local terminal = io.open(OUT .. ".done", "r")
  if terminal then terminal:close(); return end
  local found9800, matched9800, tooth_found9800, tooth_matched9800,
    fire_found9800, fire_matched9800, terminal_found9800,
    terminal_matched9800, support_found9800, support_matched9800,
    tooth_bank1_9800 = inspect_map(0x9800)
  local found9c00, matched9c00, tooth_found9c00, tooth_matched9c00,
    fire_found9c00, fire_matched9c00, terminal_found9c00,
    terminal_matched9c00, support_found9c00, support_matched9c00,
    tooth_bank1_9c00 = inspect_map(0x9C00)
  local active_is_9c00 = (emu:read8(0xFF40) & 0x08) ~= 0
  local tooth_found = active_is_9c00 and tooth_found9c00 or tooth_found9800
  local tooth_matched = active_is_9c00 and tooth_matched9c00 or tooth_matched9800
  local fire_found = active_is_9c00 and fire_found9c00 or fire_found9800
  local fire_matched = active_is_9c00 and fire_matched9c00 or fire_matched9800
  local terminal_found = active_is_9c00 and terminal_found9c00 or terminal_found9800
  local terminal_matched = active_is_9c00 and terminal_matched9c00 or terminal_matched9800
  local support_found = active_is_9c00 and support_found9c00 or support_found9800
  local support_matched = active_is_9c00 and support_matched9c00 or support_matched9800
  local tooth_bank1 = active_is_9c00 and tooth_bank1_9c00 or tooth_bank1_9800
  local static_rows_found, static_rows_matched,
    active_static_rows_found, active_static_rows_matched,
    static_rows_mismatch_trace = inspect_static_tooth_rows()
  local bank1_mismatches, bank1_mismatch_trace, bank1_art =
    bank1_art_mismatches()
  local handle = assert(io.open(OUT .. ".txt", "w"))
  handle:write(string.format("frames=%d\n", frame))
  -- D880 is briefly bus-unreadable during the native OAM-DMA/WRAM window.
  -- Report the last readable scene sample, which is the same ownership value
  -- used by the live oracle, instead of turning a teardown-time FF/00 sample
  -- into replay nondeterminism.
  handle:write(string.format("scene=%02X\n", last_readable_scene))
  handle:write(string.format("room=%02X\n", emu:read8(0xFFBD)))
  handle:write(string.format("source=%02X%02X\n",
    emu:read8(0xDC0F), emu:read8(0xDC0E)))
  handle:write(string.format("lcdc=%02X\n", emu:read8(0xFF40)))
  handle:write(string.format(
    "map9800=%d,%d\nmap9c00=%d,%d\n",
    found9800, matched9800, found9c00, matched9c00))
  handle:write(string.format(
    "tooth=%d,%d\nfire=%d,%d\nterminal=%d,%d\nsupport=%d,%d\n",
    tooth_found, tooth_matched, fire_found, fire_matched,
    terminal_found, terminal_matched,
    support_found, support_matched))
  handle:write(string.format("tooth_bank1=%d\n", tooth_bank1))
  handle:write(string.format(
    "static_tooth_rows=%d,%d\n", static_rows_found, static_rows_matched))
  handle:write(string.format(
    "active_static_tooth_rows=%d,%d\n",
    active_static_rows_found, active_static_rows_matched))
  handle:write("static_tooth_rows_mismatch_trace=" ..
    static_rows_mismatch_trace .. "\n")
  handle:write(string.format(
    "bank1_load_index=%02X\n", emu:read8(0xDF5B)))
  handle:write(string.format(
    "bank1_art_mismatches=%d\n", bank1_mismatches))
  handle:write("bank1_art_mismatch_trace=" .. bank1_mismatch_trace .. "\n")
  handle:write("bank1_art_trace=" .. table.concat(bank1_art_trace, ";") .. "\n")
  handle:write("bank1_art=" .. bank1_art .. "\n")
  handle:write(string.format(
    "bg5=%04X,%04X,%04X,%04X\n",
    cram_word(5, 0), cram_word(5, 1), cram_word(5, 2), cram_word(5, 3)))
  handle:write(string.format(
    "bg7=%04X,%04X,%04X,%04X\n",
    cram_word(7, 0), cram_word(7, 1), cram_word(7, 2), cram_word(7, 3)))
  handle:write(string.format("powerup=%02X\n", emu:read8(0xFFC0)))
  handle:write("obj0=" .. words_text(obj_palette_words(0)) .. "\n")
  handle:write("visible_oam=" .. visible_oam_text() .. "\n")
  for _, mismatch in ipairs(mismatches) do
    handle:write("mismatch=" .. mismatch .. "\n")
  end
  handle:write("lut7d=" .. string.format("%02X", emu:read8(0xC67D)) .. "\n")
  handle:write("cell9c88=" .. table.concat(cell_trace, ";") .. "\n")
  handle:write(string.format(
    "transient_mismatch_frames=%d\n", #transient_mismatch_frames))
  handle:write(
    "transient_mismatch_trace=" .. table.concat(transient_mismatch_trace, ";") .. "\n")
  handle:write("first_transient_mismatch=" .. first_transient_mismatch .. "\n")
  handle:write(
    "first_transient_batch_state=" .. first_transient_batch_state .. "\n")
  handle:write(string.format(
    "inactive_preparation_mismatch_frames=%d\n",
    #inactive_preparation_mismatch_frames))
  handle:write(
    "inactive_preparation_mismatch_trace=" ..
    table.concat(inactive_preparation_mismatch_trace, ";") .. "\n")
  handle:write(string.format(
    "map_flip_events=%d\nunsafe_map_flip_events=%d\n" ..
    "primary_ff97_02_events=%d\n",
    map_flip_events, unsafe_map_flip_events, PENTA_PRIMARY_FF97_02_EVENTS))
  handle:write("map_flip_trace=" .. table.concat(map_flip_trace, ";") .. "\n")
  handle:write("map_owner_publication_variant=" .. PENTA_PUBLICATION_VARIANT .. "\n")
  handle:write(string.format(
    "map_owner_publication_pc=%04X\n", PENTA_PUBLICATION_PC))
  local pending_owner_count = 0
  for _, _ in pairs(pending_map_publications) do
    pending_owner_count = pending_owner_count + 1
  end
  handle:write(string.format(
    "map_owner_seed_events=%d\nmap_owner_publications=%d\n" ..
    "map_owner_reused_flips=%d\nmap_owner_superseded_arms=%d\n" ..
    "map_owner_invalid_publications=%d\n" ..
    "map_owner_missing_flip_events=%d\n" ..
    "map_owner_missing_visible_frames=%d\n" ..
    "map_owner_live_room_divergence_frames=%d\n" ..
    "map_owner_pending=%d\n",
    map_owner_seed_events, map_owner_publications,
    map_owner_reused_flips, map_owner_superseded_arms,
    map_owner_invalid_publications,
    map_owner_missing_flip_events, map_owner_missing_visible_frames,
    map_owner_live_room_divergence_frames, pending_owner_count))
  handle:write("map_owner_trace=" .. table.concat(map_owner_trace, ";") .. "\n")
  handle:write("raw49_trace=" .. table.concat(raw49_trace, ";") .. "\n")
  handle:write(string.format("miniboss_first_frame=%d\n", miniboss_first_frame))
  handle:write("miniboss_trace=" .. table.concat(miniboss_trace, ";") .. "\n")
  handle:write("miniboss_hram=" .. miniboss_hram .. "\n")
  local rst18_flags = {}
  for value, count in pairs(miniboss_rst18_flags) do
    rst18_flags[#rst18_flags + 1] = string.format("%02X:%d", value, count)
  end
  table.sort(rst18_flags)
  handle:write("miniboss_rst18_flags=" .. table.concat(rst18_flags, ",") .. "\n")
  handle:write("progress_trace=" .. table.concat(progress_trace, ";") .. "\n")
  handle:write(string.format(
    "palette_mismatch_frames=%d\n", #palette_mismatch_frames))
  handle:write("first_palette_mismatch=" .. first_palette_mismatch .. "\n")
  handle:write(string.format("menu_open_frames=%d\n", menu_open_frames))
  handle:write(string.format(
    "menu_anchor_room=%d\nmenu_anchor_frame=%d\n" ..
    "effective_menu_open_frame=%d\n" ..
    "effective_menu_close_frame=%d\n" ..
    "effective_menu_use_frame=%d\n" ..
    "effective_low_health_frame=%d\n",
    menu_anchor_room, menu_anchor_frame, effective_menu_open_frame,
    effective_menu_close_frame, effective_menu_use_frame,
    effective_low_health_frame))
  handle:write(string.format(
    "menu_use_input_frames=%d\n", menu_use_input_frames))
  handle:write(string.format(
    "menu_map_alias_frames=%d\n", menu_map_alias_frames))
  handle:write("first_menu_map_alias=" .. first_menu_map_alias .. "\n")
  handle:write(string.format(
    "menu_hud_before_use=%04X\n", menu_hud_before_use & 0xFFFF))
  handle:write(string.format(
    "menu_hud_change_frame=%d\n", menu_hud_change_frame))
  handle:write(string.format(
    "menu_hp_before_use=%04X\n", menu_hp_before_use & 0xFFFF))
  handle:write(string.format(
    "menu_hp_change_frame=%d\n", menu_hp_change_frame))
  handle:write(string.format(
    "menu_hp_after_use=%04X\n", menu_hp_after_use & 0xFFFF))
  handle:write(string.format(
    "menu_a_handler_hits=%d\nmenu_item_dispatch_hits=%d\n" ..
    "menu_heal_handler_hits=%d\n",
    menu_a_handler_hits, menu_item_dispatch_hits, menu_heal_handler_hits))
  handle:write("menu_selected_item_trace=" ..
    table.concat(menu_selected_item_trace, ";") .. "\n")
  handle:write(string.format("menu_closed_frame=%d\n", menu_closed_frame))
  handle:write(string.format(
    "post_menu_closed_frames=%d\n", post_menu_closed_frames))
  handle:write(string.format(
    "post_menu_input_frames=%d\n", post_menu_input_frames))
  handle:write(string.format(
    "menu_close_repair_hits=%d\nmenu_close_copy_hits=%d\n" ..
    "menu_close_native_tail_hits=%d\nstale_window_cleanup_hits=%d\n",
    menu_close_repair_hits, menu_close_copy_hits,
    menu_close_native_tail_hits,
    stale_window_cleanup_hits))
  local stale_states = {}
  for key, count in pairs(stale_window_cleanup_states) do
    stale_states[#stale_states + 1] = string.format("%s:%d", key, count)
  end
  table.sort(stale_states)
  handle:write("stale_window_cleanup_states=" ..
    table.concat(stale_states, ",") .. "\n")
  handle:write("menu_close_trace=" .. table.concat(menu_close_trace, ";") .. "\n")
  handle:write("menu_state_trace=" .. table.concat(menu_state_trace, ";") .. "\n")
  handle:write("input_trace=" .. table.concat(PENTA_INPUT_TRACE, ";") .. "\n")
  handle:write(string.format(
    "floor_mismatch_frames=%d\n", #floor_mismatch_frames))
  handle:write("floor_mismatch_trace=" .. table.concat(
    floor_mismatch_trace, ";") .. "\n")
  handle:write("first_floor_mismatch=" .. first_floor_mismatch .. "\n")
  handle:write(string.format(
    "endpoint_mismatch_frames=%d\n", #endpoint_mismatch_frames))
  handle:write("endpoint_mismatch_trace=" .. table.concat(
    endpoint_mismatch_trace, ";") .. "\n")
  handle:write("first_endpoint_mismatch=" .. first_endpoint_mismatch .. "\n")
  handle:write(string.format(
    "post_menu_transient_mismatch_frames=%d\n",
    post_menu_transient_mismatch_frames))
  handle:write(string.format(
    "post_menu_palette_mismatch_frames=%d\n",
    post_menu_palette_mismatch_frames))
  handle:write(string.format(
    "post_menu_floor_mismatch_frames=%d\n",
    post_menu_floor_mismatch_frames))
  handle:write(string.format(
    "post_menu_endpoint_mismatch_frames=%d\n",
    post_menu_endpoint_mismatch_frames))
  handle:write(string.format(
    "visible_attr_mismatch_frames=%d\n", #visible_attr_mismatch_frames))
  handle:write("visible_attr_mismatch_trace=" .. table.concat(
    visible_attr_mismatch_trace, ";") .. "\n")
  handle:write("first_visible_attr_mismatch=" ..
    first_visible_attr_mismatch .. "\n")
  handle:write(string.format(
    "post_menu_visible_attr_mismatch_frames=%d\n",
    post_menu_visible_attr_mismatch_frames))
  handle:write(string.format(
    "low_health_forced_frames=%d\nlow_health_scene_frames=%d\n",
    low_health_forced_frames, low_health_scene_frames))
  handle:write("floor_lut_trace=" .. table.concat(floor_lut_trace, ";") .. "\n")
  handle:write(string.format(
    "floor_lut_mismatch_frames=%d\n", #floor_lut_mismatch_frames))
  handle:write(string.format(
    "atomic_floor_lut_mismatch_hits=%d\n", atomic_floor_lut_mismatch_hits))
  handle:write(string.format(
    "active_hazard_attr_write_hits=%d\n",
    semantic_attr_write_counters.active))
  handle:write(string.format(
    "post_menu_active_hazard_attr_write_hits=%d\n",
    semantic_attr_write_counters.post_menu_active))
  handle:write(string.format(
    "semantic_attr_write_hits=%d\n" ..
    "hidden_semantic_attr_write_hits=%d\n" ..
    "semantic_attr_write_9800_hits=%d\n" ..
    "semantic_attr_write_9c00_hits=%d\n" ..
    "semantic_attr_write_invalid_destination_hits=%d\n" ..
    "semantic_attr_write_bank_mismatch_hits=%d\n" ..
    "semantic_attr_write_installed_sites=%d\n" ..
    "hazard_attr_write_trace_dropped=%d\n",
    semantic_attr_write_counters.hits,
    semantic_attr_write_counters.hidden,
    semantic_attr_write_counters.base9800,
    semantic_attr_write_counters.base9c00,
    semantic_attr_write_counters.invalid,
    semantic_attr_write_counters.bank_mismatch,
    semantic_attr_write_counters.installed_sites,
    semantic_attr_write_counters.trace_dropped))
  handle:write("hazard_attr_write_trace=" .. table.concat(
    hazard_attr_write_trace, ";") .. "\n")
  handle:write("visible_hazard_attr_write_trace=" .. table.concat(
    visible_hazard_attr_write_trace, ";") .. "\n")
  handle:write("atomic_source_trace=" .. table.concat(
    atomic_source_trace, ";") .. "\n")
  handle:write(string.format(
    "post_miniboss_hazard_helper_hits=%d\n", post_miniboss_hazard_helper_hits))
  handle:write(string.format(
    "post_miniboss_hazard_row_hits=%d\n", post_miniboss_hazard_row_hits))
  handle:write(string.format(
    "main_loop_hits=%d\ntile_copy_hits=%d\npure_tail_hits=%d\n" ..
    "atomic_wrap_hits=%d\nhazard_trampoline_hits=%d\n" ..
    "hazard_dispatcher_hits=%d\nhazard_helper_hits=%d\n" ..
    "hazard_row_hits=%d\ninvalid_hazard_row_writes=%d\n" ..
    "pure_setup_hits=%d\natomic_path_hits=%d\n",
    main_loop_hits, tile_copy_hits, pure_tail_hits, atomic_wrap_hits,
    hazard_trampoline_hits, hazard_dispatcher_hits, hazard_helper_hits,
    hazard_row_hits, invalid_hazard_row_writes,
    pure_setup_hits, atomic_path_hits))
  handle:write("phase_cache_trace=" .. table.concat(phase_cache_trace, ";") .. "\n")
  handle:write(
    "rendered_phase_trace=" .. table.concat(rendered_phase_trace, ";") .. "\n")
  handle:write(
    "rendered_phase_oam_trace=" ..
    table.concat(rendered_phase_oam_trace, ";") .. "\n")
  handle:write(
    "rendered_phase_map_trace=" ..
    table.concat(rendered_phase_map_trace, ";") .. "\n")
  handle:write(
    "periodic_render_trace=" ..
    table.concat(periodic_render_trace, ";") .. "\n")
  handle:write(
    "periodic_render_oam_trace=" ..
    table.concat(periodic_render_oam_trace, ";") .. "\n")
  handle:write(
    "periodic_render_map_trace=" ..
    table.concat(PENTA_PERIODIC_RENDER_MAP_TRACE, ";") .. "\n")
  handle:write(string.format(
    "compiler_unreadable_scene_frames=%d\n",
    compiler_unreadable_scene_frames))
  handle:write(string.format(
    "oam_dma_unreadable_scene_frames=%d\n",
    oam_dma_unreadable_scene_frames))
  handle:write("hazard_event_trace=" .. table.concat(hazard_event_trace, ";") .. "\n")
  local helper_banks = {}
  for bank, _ in pairs(helper_bank_values) do
    table.insert(helper_banks, string.format("%02X", bank))
  end
  table.sort(helper_banks)
  handle:write("helper_banks=" .. table.concat(helper_banks, ",") .. "\n")
  local copy_states = {}
  for state, count in pairs(tile_copy_states) do
    table.insert(copy_states, string.format("%s:%d", state, count))
  end
  table.sort(copy_states)
  handle:write("tile_copy_states=" .. table.concat(copy_states, ",") .. "\n")
  handle:write("writer_trace=" .. table.concat(writer_trace, ";") .. "\n")
  handle:write("hazard_focus_trace=" .. table.concat(
    hazard_focus_trace, ";") .. "\n")
  for _, offset in ipairs(tracked_offsets) do
    local ids = {}
    for tile = 0x60, 0x7F do
      if tracked_ids[offset][tile] then
        table.insert(ids, string.format("%02X", tile))
      end
    end
    handle:write(string.format(
      "cycle=9C00,%03X,%s\n", offset, table.concat(ids, ",")))
  end
  -- This marker is written only after the complete report has been emitted.
  -- Verifiers may accept a Qt teardown timeout only when this marker exists.
  handle:write("probe_finished=1\n")
  handle:close()
  if memory_trace then memory_trace:close() end
  emu:screenshot(OUT .. ".png")
  local done = assert(io.open(OUT .. ".done", "w"))
  done:write("probe_finished=1\n")
  done:close()
  emu:quit()
  os.exit(0)
end

if watchdog then watchdog:write("init:frame-callback\n"); watchdog:flush() end
callbacks:add("frame", function()
  local terminal = io.open(OUT .. ".done", "r")
  if terminal then terminal:close(); return end
  if not state_loaded then
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_FILE)
    end)
    assert(ok and result ~= false, "failed to load requested spike state")
    state_loaded = true
    seed_active_map_owner()
    if watchdog then
      watchdog:write(string.format(
        "loaded\tpc=%04X\tsp=%04X\tbank=%02X\tlcdc=%02X\tstat=%02X\n",
        read_register("PC"), read_register("SP"), emu:read8(0xFF99),
        emu:read8(0xFF40), emu:read8(0xFF41)))
      watchdog:flush()
    end
    return
  end
  frame = frame + 1
  if watchdog then
    watchdog:write(string.format(
      "%d\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\n", frame,
      read_register("PC"), read_register("SP"), emu:read8(0xFF99),
      emu:read8(0xD880), emu:read8(0xFF40), emu:read8(0xFF41)))
    watchdog:flush()
  end
  -- Anchor the interaction to the live fixture, not a host-frame number.
  -- Performance changes can advance these historical states out of their
  -- hazard room before frame 160. Once the exact Stage-1 scene/room appears,
  -- preserve every configured relative delay after the receipt-qualified
  -- 20-frame room stabilization window. SELECT is retried below until
  -- the native menu actually acknowledges it; a fixed one-shot pulse can
  -- land inside an in-progress room scroll on faster candidates.
  local anchor_scene, anchor_unreadable = sampled_scene()
  if menu_cycle and menu_anchor_room >= 0 and not PENTA_MENU_ANCHOR_STARTED
      and not anchor_unreadable and (anchor_scene & 0xF7) == 0x02 then
    PENTA_MENU_ANCHOR_STARTED = true
  end
  if menu_cycle and PENTA_MENU_ANCHOR_STARTED and menu_anchor_frame < 0
      and not anchor_unreadable then
    local stable_scene = (anchor_scene & 0xF7) == 0x02
    local stable_room = emu:read8(0xFFBD)
    if stable_scene then
      PENTA_MENU_STAGE1_SEEN = true
    end
    -- Scene publication can briefly report a transitional value while the
    -- room owner remains stable. Preserve the room-stability evidence across
    -- those readable samples, but never arm until Stage 1 has been observed.
    if not anchor_unreadable and PENTA_MENU_STAGE1_SEEN
        and stable_room == PENTA_MENU_STABLE_ROOM then
      PENTA_MENU_STABLE_FRAMES = PENTA_MENU_STABLE_FRAMES + 1
    elseif not anchor_unreadable then
      PENTA_MENU_STABLE_ROOM = stable_room
      PENTA_MENU_STABLE_FRAMES = 1
    elseif not PENTA_MENU_STAGE1_SEEN then
      PENTA_MENU_STABLE_ROOM = -1
      PENTA_MENU_STABLE_FRAMES = 0
    end
  end
  if menu_cycle and menu_anchor_frame < 0
      and (menu_anchor_room < 0
        or (PENTA_MENU_STABLE_FRAMES >= menu_anchor_delay
          and PENTA_MENU_STABLE_ROOM == menu_anchor_room)) then
    menu_anchor_frame = frame
    local shift = frame - menu_open_frame
    effective_menu_open_frame = menu_open_frame + shift
    if menu_close_frame >= 0 then
      effective_menu_close_frame = menu_close_frame + shift
    end
    if menu_use_frame >= 0 then
      effective_menu_use_frame = menu_use_frame + shift
    end
    if low_health_frame >= 0 then
      effective_low_health_frame = low_health_frame + shift
    end
    -- The historical hazard fixtures do not guarantee a usable selection.
    -- Seed canonical item 1 into group/slot zero so A must cross the real
    -- nonzero item dispatcher and redraw the native menu.
    emu:write8(0xDCBD, 0x01)
    emu:write8(0xDCDB, 0x00)
  end
  local menu_timeline_ready = menu_anchor_room < 0 or menu_anchor_frame >= 0
  local keys = input_mask
  if menu_closed_frame >= 0 and post_menu_input_mask >= 0 then
    keys = post_menu_input_mask
    post_menu_input_frames = post_menu_input_frames + 1
  end
  if menu_cycle and menu_timeline_ready and not menu_seen
      and frame >= effective_menu_open_frame
      and frame < effective_menu_open_frame + 180
      and ((frame - effective_menu_open_frame) % 11) < 6 then
    -- Pulse/release SELECT until the game accepts it. This remains bounded
    -- and the receipt records the exact acknowledged frame.
    keys = keys | 0x04
  end
  if menu_cycle and menu_timeline_ready and menu_seen
      and menu_closed_frame < 0 and effective_menu_close_frame >= 0
      and frame >= effective_menu_close_frame
      and ((frame - effective_menu_close_frame) % 11) < 6 then
    keys = keys | 0x04 -- Retry SELECT until close is acknowledged.
  end
  if menu_cycle and menu_timeline_ready and effective_menu_use_frame >= 0
      and frame >= effective_menu_use_frame
      and frame < effective_menu_use_frame + 6 then
    keys = keys | 0x01 -- A uses/redraws the selected item.
  end
  emu:setKeys(keys)
  if menu_cycle and menu_timeline_ready
      and frame >= effective_menu_open_frame - 2
      and frame <= effective_menu_open_frame + 180
      and #PENTA_INPUT_TRACE < 256 then
    PENTA_INPUT_TRACE[#PENTA_INPUT_TRACE + 1] = string.format(
      "f%d:k%02X:j%02X:s%02X:r%02X:p%04X", frame, keys,
      emu:read8(0xFF93), emu:read8(0xD880), emu:read8(0xFFBD),
      read_register("PC"))
  end

  local menu_state = string.format(
    "%02X/%02X", emu:read8(0xFFE4), emu:read8(0xFF40))
  if menu_state ~= last_menu_state then
    menu_state_trace[#menu_state_trace + 1] = string.format(
      "f%d:%s", frame, menu_state)
    last_menu_state = menu_state
  end
  local menu_visible = emu:read8(0xFFE4) ~= 0
    and (emu:read8(0xFF40) & 0x20) ~= 0
  if menu_visible and not menu_seen then
    -- Rebase use/close/low-health actions to the acknowledged opening, not
    -- the first attempted input. Candidate timing may defer SELECT during a
    -- room transition, but every subsequent interval remains identical.
    local acknowledged_shift = frame - effective_menu_open_frame
    effective_menu_open_frame = frame
    if effective_menu_close_frame >= 0 then
      effective_menu_close_frame = effective_menu_close_frame
        + acknowledged_shift
    end
    if effective_menu_use_frame >= 0 then
      effective_menu_use_frame = effective_menu_use_frame
        + acknowledged_shift
    end
    if effective_low_health_frame >= 0 then
      effective_low_health_frame = effective_low_health_frame
        + acknowledged_shift
    end
  end
  if effective_menu_use_frame >= 0
      and frame == effective_menu_use_frame - 1 then
    menu_hud_before_use = menu_hud_checksum()
    menu_hp_before_use = emu:read8(0xDCDC)
      | (emu:read8(0xDCDD) << 8)
  end
  if menu_visible then
    menu_open_frames = menu_open_frames + 1
    menu_seen = true
    if effective_menu_use_frame >= 0 and frame >= effective_menu_use_frame
        and frame < effective_menu_use_frame + 6 then
      menu_use_input_frames = menu_use_input_frames + 1
    end
    local lcdc = emu:read8(0xFF40)
    local window_map_9c = (lcdc & 0x40) ~= 0
    local bg_map_9c = (lcdc & 0x08) ~= 0
    if window_map_9c == bg_map_9c then
      menu_map_alias_frames = menu_map_alias_frames + 1
      if first_menu_map_alias == "" then
        first_menu_map_alias = string.format(
          "f%d:l%02X:s%02X:r%02X", frame, lcdc,
          emu:read8(0xD880), emu:read8(0xFFBD))
        emu:screenshot(OUT .. "-first-menu-map-alias.png")
      end
    end
    if menu_hud_before_use >= 0 and frame > effective_menu_use_frame + 5
        and menu_hud_change_frame < 0
        and menu_hud_checksum() ~= menu_hud_before_use then
      menu_hud_change_frame = frame
      emu:screenshot(OUT .. "-item-use-redraw.png")
    end
    local current_hp = emu:read8(0xDCDC) | (emu:read8(0xDCDD) << 8)
    if menu_hp_before_use >= 0 and frame > effective_menu_use_frame
        and menu_hp_change_frame < 0 and current_hp ~= menu_hp_before_use then
      menu_hp_change_frame = frame
      menu_hp_after_use = current_hp
      emu:screenshot(OUT .. "-item-use-hp-change.png")
    end
  elseif menu_seen and effective_menu_close_frame >= 0
      and frame >= effective_menu_close_frame
      and menu_closed_frame < 0 then
    menu_closed_frame = frame
  end
  if menu_closed_frame >= 0 and frame >= menu_closed_frame then
    post_menu_closed_frames = post_menu_closed_frames + 1
  end

  -- Deterministic palette-transition receipt. Historical active-Gargoyle
  -- save states are not execution-portable across ROM revisions, so switch
  -- only the three observed scene flags on a healthy current room-$12 state.
  if frame == force_miniboss_frame then
    emu:write8(0xD880, 0x0A)
    emu:write8(0xFFBF, 0x01)
    native_assistance.write(0xDCB8, 0x02)
  end

  if focus_start >= 0 and frame >= focus_start and frame <= focus_end then
    local old_vbk = emu:read8(0xFF4F)
    local snapshots = {}
    for _, base in ipairs({0x9800, 0x9C00}) do
      emu:write8(0xFF4F, 0)
      local tile48, tilea8 = emu:read8(base + 0x48), emu:read8(base + 0xA8)
      emu:write8(0xFF4F, 1)
      snapshots[#snapshots + 1] = string.format(
        "%04X:%02X/%02X,%02X/%02X", base, tile48,
        emu:read8(base + 0x48), tilea8, emu:read8(base + 0xA8))
    end
    emu:write8(0xFF4F, old_vbk)
    focus_event(string.format(
      "f%d:frame:l%02X:d%02X:src%02X/%02X/%02X/%02X:%s", frame,
      emu:read8(0xFF40), emu:read8(0xDC0B), emu:read8(0xC1A0),
      emu:read8(0xC1A1), emu:read8(0xC1A8), emu:read8(0xC1F0),
      table.concat(snapshots, "|")))
  end

  local floor_lut = floor_lut_mismatches()
  if floor_lut == "" then floor_lut = "ok" end
  if floor_lut ~= last_floor_lut then
    floor_lut_trace[#floor_lut_trace + 1] = string.format(
      "f%d:%s", frame, floor_lut)
    last_floor_lut = floor_lut
  end
  local sample_pc = read_register("PC")
  local oam_dma_unreadable = sample_pc >= 0xFF80 and sample_pc <= 0xFFFE
    and emu:read8(0xD880) == 0xFF
  if frame >= 80 and not oam_dma_unreadable then
    local art_mismatch_count, art_mismatch_tiles = bank1_art_mismatches()
    local art_state = string.format("%d/%s", art_mismatch_count,
      art_mismatch_tiles == "" and "ok" or art_mismatch_tiles)
    if art_state ~= last_bank1_art_state then
      bank1_art_trace[#bank1_art_trace + 1] = string.format(
        "f%d:%s", frame, art_state)
      last_bank1_art_state = art_state
    end
    if floor_lut ~= "ok" then
      floor_lut_mismatch_frames[#floor_lut_mismatch_frames + 1] = frame
    end
    local floor_mismatches = BROAD_VISIBLE_ORACLE
      and {} or inspect_floor_environment()
    if #floor_mismatches > 0 then
      floor_mismatch_frames[#floor_mismatch_frames + 1] = frame
      if menu_closed_frame >= 0 then
        post_menu_floor_mismatch_frames =
          post_menu_floor_mismatch_frames + 1
      end
      if #floor_mismatch_trace < 96 then
        floor_mismatch_trace[#floor_mismatch_trace + 1] = string.format(
          "f%d:s%02X:r%02X:y%02X:l%s:%s", frame,
          emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFF42),
          floor_lut, table.concat(floor_mismatches, ","))
      end
      if first_floor_mismatch == "" then
        first_floor_mismatch = floor_mismatch_trace[#floor_mismatch_trace]
        emu:screenshot(OUT .. "-first-floor-mismatch.png")
      end
    end
    local endpoint_mismatches = BROAD_VISIBLE_ORACLE
      and {} or inspect_active_endpoint_rows()
    if #endpoint_mismatches > 0 then
      endpoint_mismatch_frames[#endpoint_mismatch_frames + 1] = frame
      if menu_closed_frame >= 0 then
        post_menu_endpoint_mismatch_frames =
          post_menu_endpoint_mismatch_frames + 1
      end
      if #endpoint_mismatch_trace < 96 then
        endpoint_mismatch_trace[#endpoint_mismatch_trace + 1] = string.format(
          "f%d:s%02X:r%02X:%s", frame, emu:read8(0xD880),
          emu:read8(0xFFBD), table.concat(endpoint_mismatches, ","))
      end
      if first_endpoint_mismatch == "" then
        first_endpoint_mismatch = endpoint_mismatch_trace[
          #endpoint_mismatch_trace]
        emu:screenshot(OUT .. "-first-endpoint-mismatch.png")
      end
    end
    local visible_attr_mismatches = BROAD_VISIBLE_ORACLE
      and inspect_visible_attributes() or {}
    if #visible_attr_mismatches > 0 then
      visible_attr_mismatch_frames[#visible_attr_mismatch_frames + 1] = frame
      if menu_closed_frame >= 0 then
        post_menu_visible_attr_mismatch_frames =
          post_menu_visible_attr_mismatch_frames + 1
      end
      if #visible_attr_mismatch_trace < 96 then
        visible_attr_mismatch_trace[#visible_attr_mismatch_trace + 1] =
          string.format("f%d:s%02X:r%02X:%s", frame,
            emu:read8(0xD880), emu:read8(0xFFBD),
            table.concat(visible_attr_mismatches, ","))
      end
      if first_visible_attr_mismatch == "" then
        first_visible_attr_mismatch =
          visible_attr_mismatch_trace[#visible_attr_mismatch_trace]
        emu:screenshot(OUT .. "-first-visible-attr-mismatch.png")
      end
    end
  end

  local miniboss_scene = sampled_scene()
  local miniboss_state = string.format(
    "%02X/%02X/%02X", miniboss_scene, emu:read8(0xFFBF),
    emu:read8(0xDCB8))
  if miniboss_state ~= last_miniboss_state and #miniboss_trace < 128 then
    miniboss_trace[#miniboss_trace + 1] = string.format(
      "f%d:%s", frame, miniboss_state)
    last_miniboss_state = miniboss_state
  end
  if miniboss_first_frame < 0 and emu:read8(0xFFBF) ~= 0 then
    miniboss_first_frame = frame
    emu:screenshot(OUT .. "-miniboss-entry.png")
  end
  if miniboss_hram == "" and emu:read8(0xD880) == 0x0A then
    local bytes = {}
    for address = 0xFF80, 0xFFFE do
      bytes[#bytes + 1] = string.format("%02X", emu:read8(address))
    end
    miniboss_hram = table.concat(bytes)
  end
  if frame == 1 or frame % 30 == 0 then
    progress_trace[#progress_trace + 1] = string.format(
      "f%d:s%02X:r%02X:b%02X:k%02X:c%04X:p%02X%02X",
      frame, emu:read8(0xD880), emu:read8(0xFFBD),
      emu:read8(0xFFBF), emu:read8(0xDCB8),
      emu:read8(0xDC02) | (emu:read8(0xDC03) << 8),
      emu:read8(0xDCE8), emu:read8(0xDCE9))
  end
  if screenshot_interval > 0 and frame % screenshot_interval == 0 then
    local scene = sampled_scene()
    local render_path = string.format("%s-frame%04d.png", OUT, frame)
    local render_base, render_owner = active_map_owner()
    local render_room = render_owner and render_owner.room or INITIAL_MAP_ROOM
    local render_phase_offset = forced_phase_offset >= 0
      and forced_phase_offset or (render_room == 0x02 and 0x44 or 0x41)
    emu:screenshot(render_path)
    periodic_render_trace[#periodic_render_trace + 1] = string.format(
      "f%d:%02X:%02X:%02X:%02X:%02X:%s", frame,
      emu:read8(0xFF43), emu:read8(0xFF42), scene,
      emu:read8(0xFFBD), emu:read8(0xFFBF), render_path)
    periodic_render_oam_trace[#periodic_render_oam_trace + 1] = string.format(
      "f%d:h%d:%s", frame,
      (emu:read8(0xFF40) & 0x04) ~= 0 and 16 or 8,
      visible_oam_text())
    PENTA_PERIODIC_RENDER_MAP_TRACE[
      #PENTA_PERIODIC_RENDER_MAP_TRACE + 1] = string.format(
      "f%d:%04X:%02X:%02X:%s", frame, render_base,
      emu:read8(0xFF43), emu:read8(0xFF42),
      PENTA_PHASE_SIGNATURE_TEXT(render_base, render_phase_offset))
  end

  if refresh_runtime_code and frame == 1 then emu:write8(0xDF51, 0) end

  -- Historical states predate the current WRAM helpers. Re-enter the exact
  -- current-ROM initializer and invalidate both Stage 1 map signatures.
  if reinitialize_runtime and frame <= 40 then
    emu:write8(0xDF02, 0)
    emu:write8(0xDF00, 0)
    emu:write8(0xDF53, 0)
    emu:write8(0xDF55, 0)
    emu:write8(0xDF57, 0)
    emu:write8(0xDF58, 0)
    emu:write8(0xDF04, 0)
    emu:write8(0xDF05, 0)
    emu:write8(0xDF4E, 0)
  end
  if reinitialize_runtime and frame == 1 then emu:write8(0xDF0D, 0xFF) end

  -- Preserve the captured room while its current-ROM attributes settle.
  if effective_low_health_frame >= 0
      and frame >= effective_low_health_frame then
    -- Reproduce the hardware report as one uninterrupted state sequence:
    -- use an item, close the menu without moving, then enter the warning
    -- band while the same hazard rows remain visible.
    native_assistance.write(0xDCDD, 0x00)
    native_assistance.write(0xDCDC, 0x0C)
    low_health_forced_frames = low_health_forced_frames + 1
    if emu:read8(0xD880) == 0x0A then
      low_health_scene_frames = low_health_scene_frames + 1
    end
  elseif effective_menu_use_frame >= 0
      and frame < effective_menu_use_frame then
    -- Make the selected healing item usable; the historical fixture is at
    -- full health, so an A pulse otherwise exercises no redraw at all.
    native_assistance.write(0xDCDD, 0x01)
    native_assistance.write(0xDCDC, 0x20)
  elseif effective_menu_use_frame < 0 or menu_closed_frame >= 0 then
  end
  native_assistance.write(0xDCBB, 0xFF)
  if frame >= 80 then
    if frame >= transient_check_start then
      local bg5_text = words_text(palette_words(5))
      local bg7_text = words_text(palette_words(7))
      if bg5_text ~= expected_bg5 or bg7_text ~= expected_bg7 then
        palette_mismatch_frames[#palette_mismatch_frames + 1] = frame
        if menu_closed_frame >= 0 then
          post_menu_palette_mismatch_frames =
            post_menu_palette_mismatch_frames + 1
        end
        if first_palette_mismatch == "" then
          first_palette_mismatch = string.format(
            "f%d:bg5=%s:bg7=%s:s%02X:r%02X:b%02X:k%02X",
            frame, bg5_text, bg7_text, emu:read8(0xD880),
            emu:read8(0xFFBD), emu:read8(0xFFBF), emu:read8(0xDCB8))
          emu:screenshot(OUT .. "-first-palette-mismatch.png")
        end
      end
    end
    local phase_cache = string.format(
      "%02X/%02X", emu:read8(0xDF55), emu:read8(0xDF59))
    if phase_cache ~= last_phase_cache then
      table.insert(phase_cache_trace, string.format("f%d:%s", frame, phase_cache))
      last_phase_cache = phase_cache
    end
    -- Capture the four stable rendered cylinder phases, not merely the final
    -- attribute map. Admit frames only after all bank-1 art is installed; the
    -- position-owned rows then remain invariant through every phase change.
    local active_base, phase_owner = active_map_owner()
    local room = phase_owner and phase_owner.room or INITIAL_MAP_ROOM
    local phase_offset = forced_phase_offset >= 0
      and forced_phase_offset or (room == 0x02 and 0x44 or 0x41)
    local old_phase_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    local rendered_phase = emu:read8(active_base + phase_offset)
    emu:write8(0xFF4F, 1)
    local rendered_attr = emu:read8(active_base + phase_offset) & 0x07
    emu:write8(0xFF4F, old_phase_vbk)
    if (emu:read8(0xDF5B) & 0x03) == expected_load_count
        and not rendered_phase_seen[rendered_phase] then
      local phase_path = string.format(
        "%s-phase-%02X.png", OUT, rendered_phase)
      emu:screenshot(phase_path)
      rendered_phase_seen[rendered_phase] = true
      table.insert(rendered_phase_trace, string.format(
        "f%d:%02X/%d:%s", frame, rendered_phase, rendered_attr, phase_path))
      table.insert(rendered_phase_oam_trace, string.format(
        "f%d:%02X:%s", frame, rendered_phase, visible_oam_text()))
      table.insert(rendered_phase_map_trace, string.format(
        "f%d:%02X:%04X:%02X:%02X:%s", frame, rendered_phase, active_base,
        emu:read8(0xFF43), emu:read8(0xFF42),
        phase_map_text(active_base, phase_offset)))
    end
    local raw49 = emu:read8(0xC1D1)
    if raw49 ~= last_raw49 then
      table.insert(raw49_trace, string.format("f%d:%02X", frame, raw49))
      last_raw49 = raw49
    end
    if memory_trace and emu:read8(0xD880) == 0x02 then
      local bytes = {
        string.char(frame & 0xFF, (frame >> 8) & 0xFF, raw49)
      }
      for address = 0xC000, 0xDFFF do
        bytes[#bytes + 1] = string.char(emu:read8(address))
      end
      for address = 0xFF80, 0xFFFE do
        bytes[#bytes + 1] = string.char(emu:read8(address))
      end
      memory_trace:write(table.concat(bytes))
    end
    local old_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    if frame == 80 then
      for offset = 0, 0x3FF do
        local candidate = emu:read8(0x9C00 + offset)
        if candidate >= 0x60 and candidate <= 0x7F then
          table.insert(tracked_offsets, offset)
          tracked_ids[offset] = {}
        end
      end
    end
    for _, offset in ipairs(tracked_offsets) do
      local candidate = emu:read8(0x9C00 + offset)
      if candidate >= 0x60 and candidate <= 0x7F then
        tracked_ids[offset][candidate] = true
      end
    end
    -- The stock engine builds the hidden physical map, stamps its hazard
    -- rows, and only then flips LCDC. A tile/attribute difference on that
    -- hidden work plane is expected during preparation; it is a visible
    -- atomicity defect only if it survives until that map becomes active.
    -- Sample both planes so the receipt records the preparation interval but
    -- fails on the exact plane the PPU can render this frame.
    local active_base =
      (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800
    local inactive_base = active_base == 0x9C00 and 0x9800 or 0x9C00
    local live_tiles = {}
    local inactive_tiles = {}
    for _, offset in ipairs(tracked_offsets) do
      live_tiles[offset] = emu:read8(active_base + offset)
      inactive_tiles[offset] = emu:read8(inactive_base + offset)
    end
    local tile = emu:read8(0x9C88)
    emu:write8(0xFF4F, 1)
    local attr = emu:read8(0x9C88) & 0x07
    if frame >= transient_check_start then
      local frame_mismatches = {}
      local inactive_frame_mismatches = {}
      for _, offset in ipairs(tracked_offsets) do
        local candidate = live_tiles[offset]
        if is_semantic_hazard_cell(candidate) then
          local actual = emu:read8(active_base + offset)
          local expected = expected_semantic_attr(candidate)
          if actual ~= expected then
            table.insert(frame_mismatches, string.format(
              "%03X:%02X/%02X/%02X", offset, candidate, actual, expected))
          end
        end
        local inactive_candidate = inactive_tiles[offset]
        if is_semantic_hazard_cell(inactive_candidate) then
          local inactive_actual = emu:read8(inactive_base + offset)
          local inactive_expected = expected_semantic_attr(inactive_candidate)
          if inactive_actual ~= inactive_expected then
            inactive_frame_mismatches[#inactive_frame_mismatches + 1] =
              string.format("%03X:%02X/%02X/%02X", offset, inactive_candidate,
                inactive_actual, inactive_expected)
          end
        end
      end
      if #frame_mismatches > 0 then
        table.insert(transient_mismatch_frames, frame)
        if menu_closed_frame >= 0 then
          post_menu_transient_mismatch_frames =
            post_menu_transient_mismatch_frames + 1
        end
        if #transient_mismatch_trace < 64 then
          transient_mismatch_trace[#transient_mismatch_trace + 1] = string.format(
            "f%d:s%02X:b%02X:d%02X:a%02X:%s", frame, emu:read8(0xD880),
            emu:read8(0xFFBF), emu:read8(0xDC0B),
            active_base >> 8,
            table.concat(frame_mismatches, ","))
        end
        if first_transient_mismatch == "" then
          first_transient_mismatch = string.format(
            "f%d:%s:raw31=%02X:raw49=%02X:raw73=%02X:cache=%02X",
            frame, table.concat(frame_mismatches, ","),
            emu:read8(0xC1BF), emu:read8(0xC1D1), emu:read8(0xC1E9),
            emu:read8(0xDF57))
          emu:screenshot(OUT .. "-first-transient-mismatch.png")
          first_transient_batch_state = capture_batch_state()
        end
      end
      if #inactive_frame_mismatches > 0 then
        inactive_preparation_mismatch_frames[
          #inactive_preparation_mismatch_frames + 1] = frame
        if #inactive_preparation_mismatch_trace < 64 then
          inactive_preparation_mismatch_trace[
            #inactive_preparation_mismatch_trace + 1] = string.format(
              "f%d:i%02X:%s", frame, inactive_base >> 8,
              table.concat(inactive_frame_mismatches, ","))
        end
      end
    end
    emu:write8(0xFF4F, old_vbk)
    local value = string.format("%02X/%d", tile, attr)
    if value ~= last_cell then
      table.insert(cell_trace, string.format("f%d:%s", frame, value))
      last_cell = value
    end
  end
  if frame >= SETTLE then finish() end
end)
if watchdog then watchdog:write("init:registered\n"); watchdog:flush() end
