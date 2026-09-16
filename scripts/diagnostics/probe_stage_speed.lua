-- Measure stock main-loop throughput in a selected dungeon stage.
--
-- Environment:
--   STAGE_SPEED_TARGET  FFBA value (0 = Stage 1, ... 6 = Stage 7)
--   STAGE_SPEED_OUT     JSON receipt path
--   STAGE_SPEED_DONE    completion marker path
--   STAGE_SPEED_MODE    right, left, up, down, stationary, patrol, vertical-patrol,
--                       loop-patrol, or loop-vertical-patrol
--   STAGE_SPEED_FRAMES  measured rendered frames (default 600)
--   STAGE_SPEED_DMA_COMMAND_ADDR  optional legacy single breakpoint at the
--                                 candidate's HDMA5 write
--   STAGE_SPEED_DMA_COMMAND_ADDRS optional comma-separated HDMA5 write sites;
--                                 combined with the legacy single address
--   STAGE_SPEED_SAFE_BOUNDARY_DRAIN 1 freezes measured counters at LIMIT and
--                                   drains only an already-active ABI helper
--   STAGE_SPEED_SAFE_BOUNDARY_MAX_FRAMES bounded unmeasured drain (default 120)
--   STAGE_SPEED_WINDOW_HELPER_ADDR optional exact Window-helper entry whose
--                                  FFE4 value is audited during play/drain
--   STAGE_SPEED_WINDOW_HELPER_BANK mapped ROM bank for that helper

local TARGET = tonumber(os.getenv("STAGE_SPEED_TARGET") or "0")
local OUT = assert(os.getenv("STAGE_SPEED_OUT"))
local DONE = assert(os.getenv("STAGE_SPEED_DONE"))
local copy_trace = os.getenv("STAGE_SPEED_COPY_TRACE") == "1"
  and assert(io.open(OUT .. ".copies.tsv", "w")) or nil
if copy_trace then
  copy_trace:write("frame\tloop\tevent\tbank\treturn_pc\thl\troom\tscene\tlatch\tdc0b\tx\ty\topcodes\tff01\n")
end
local TRACE = os.getenv("STAGE_SPEED_TRACE")
local LIFECYCLE = os.getenv("STAGE_SPEED_LIFECYCLE")
local pc_trace = os.getenv("STAGE_SPEED_PC_TRACE") == "1"
  and assert(io.open(OUT .. ".pc.tsv", "w")) or nil
if pc_trace then
  pc_trace:write("frame\tplay_frame\tpc\tbank\tscene\tsvbk\tlatch\topcodes\n")
end
-- Diagnostic only: independent of map-copy/publication breakpoints.
local camera_trace = os.getenv("STAGE_SPEED_CAMERA_TRACE") == "1"
  and assert(io.open(OUT .. ".camera.tsv", "w")) or nil
local loop_trace = camera_trace and assert(io.open(OUT .. ".loops.tsv", "w")) or nil
if loop_trace then
  loop_trace:write("loop\tframe\tscene\troom\tworld_x\tworld_y\tsection_cycle\tarena\tlast_polled_keys\tffc8\tffc9\tffca\tffd3\tffeb\tffe4\n")
end
if camera_trace then
  camera_trace:write("frame\tphase\tscene\tstage\troom\tscx\tscy\tworld_x\tworld_y\tpending_map\tlatched_x\tlcdc\tmode97\tmain_loop_hits\ttile_copy_hits\tsection_cycle\n")
end
local METATILE_DUMP = os.getenv("STAGE_SPEED_METATILE_DUMP")
local INPUT_MODE = os.getenv("STAGE_SPEED_MODE") or "right"
local LIMIT = tonumber(os.getenv("STAGE_SPEED_FRAMES") or "600")
-- Diagnostic phase sweep only. The normal measurement still uses 120 stable
-- loading frames and the exact $016C CPU anchor. Never average away a failure.
local SYNC_DELAY = tonumber(os.getenv("STAGE_SPEED_SYNC_DELAY") or "0")
assert(SYNC_DELAY and SYNC_DELAY >= 0 and SYNC_DELAY <= 3 and SYNC_DELAY % 1 == 0,
  "STAGE_SPEED_SYNC_DELAY must be an integer from 0 to 3")
local STAGE1_DECIDER_MODE = os.getenv("STAGE_SPEED_STAGE1_DECIDER_MODE") or "native"
local ATOMIC_ADDR = tonumber(os.getenv("STAGE_SPEED_ATOMIC_ADDR") or "0")
local DMA_COMMAND_ADDR = tonumber(
  os.getenv("STAGE_SPEED_DMA_COMMAND_ADDR") or "0")
local DMA_COMMAND_ADDRS_RAW = os.getenv("STAGE_SPEED_DMA_COMMAND_ADDRS") or ""
local COMPILER_BANK = tonumber(os.getenv("STAGE_SPEED_COMPILER_BANK") or "0")
local COMPILER_START = tonumber(os.getenv("STAGE_SPEED_COMPILER_START") or "0")
local COMPILER_END = tonumber(os.getenv("STAGE_SPEED_COMPILER_END") or "0")
local TRACE_ADDRS_RAW = os.getenv("STAGE_SPEED_TRACE_ADDRS") or ""
local ABI_ENTRY_ADDR = tonumber(os.getenv("STAGE_SPEED_ABI_ENTRY_ADDR") or "0")
local ABI_EXIT_ADDR = tonumber(os.getenv("STAGE_SPEED_ABI_EXIT_ADDR") or "0")
local ABI_FALLBACK_ADDR = tonumber(
  os.getenv("STAGE_SPEED_ABI_FALLBACK_ADDR") or "0")
local ABI_CALLER_REJECT_ADDR = tonumber(
  os.getenv("STAGE_SPEED_ABI_CALLER_REJECT_ADDR") or "0")
local ABI_ATOMIC_FALLBACK_ADDR = tonumber(
  os.getenv("STAGE_SPEED_ABI_ATOMIC_FALLBACK_ADDR") or "0")
local ABI_PHASE_ADDRS_RAW = os.getenv("STAGE_SPEED_ABI_PHASE_ADDRS") or ""
local ABI_OUTER_RETURNS_RAW = os.getenv("STAGE_SPEED_ABI_OUTER_RETURNS") or ""
local ABI_BANK = tonumber(os.getenv("STAGE_SPEED_ABI_BANK") or "0")
local ABI_EXIT_BANK = tonumber(
  os.getenv("STAGE_SPEED_ABI_EXIT_BANK") or tostring(ABI_BANK))
local ABI_ENTRY_IE = tonumber(os.getenv("STAGE_SPEED_ABI_ENTRY_IE") or "7")
local ABI_PHASE_IE = tonumber(os.getenv("STAGE_SPEED_ABI_PHASE_IE") or "4")
local ABI_EXIT_IE = tonumber(os.getenv("STAGE_SPEED_ABI_EXIT_IE") or "7")
local ABI_EXIT_AF = tonumber(os.getenv("STAGE_SPEED_ABI_EXIT_AF") or "448")
local ABI_EXIT_BC = tonumber(os.getenv("STAGE_SPEED_ABI_EXIT_BC") or "2125")
local ABI_EXIT_DE = tonumber(os.getenv("STAGE_SPEED_ABI_EXIT_DE") or "50144")
local ABI_EXIT_FFA5 = tonumber(os.getenv("STAGE_SPEED_ABI_EXIT_FFA5") or "0")
local ABI_EXIT_FFE0 = tonumber(os.getenv("STAGE_SPEED_ABI_EXIT_FFE0") or "0")
local ABI_EXIT_HLS_RAW = os.getenv("STAGE_SPEED_ABI_EXIT_HLS") or "38912,39936"
local SAFE_BOUNDARY_DRAIN =
  os.getenv("STAGE_SPEED_SAFE_BOUNDARY_DRAIN") == "1"
local SAFE_BOUNDARY_MAX_FRAMES = tonumber(
  os.getenv("STAGE_SPEED_SAFE_BOUNDARY_MAX_FRAMES") or "120")
local WINDOW_HELPER_ADDR = tonumber(
  os.getenv("STAGE_SPEED_WINDOW_HELPER_ADDR") or "0")
local WINDOW_HELPER_BANK = tonumber(
  os.getenv("STAGE_SPEED_WINDOW_HELPER_BANK") or "0")
local EXPECTED_SCENE = TARGET + 2
local KEY_A, KEY_START = 0x01, 0x08
local KEY_RIGHT, KEY_LEFT, KEY_UP, KEY_DOWN = 0x10, 0x20, 0x40, 0x80

local frame, phase, seeded, confirmed = 0, "title", false, false
local stable_frames, play_frames = 0, 0
local main_loop_hits, central_emitter_hits, free_emitter_hits = 0, 0, 0
local central_tile_counts, central_palette_counts = {}, {}
local central_attr_samples = 0
local central_xflip_changes, central_yflip_changes = 0, 0
local central_any_flip_changes = 0
local central_y_low_slot_samples, central_y_low_control_set = 0, 0
local central_x_entry_11a2, central_x_entry_11a5 = 0, 0
local pending_central_attr, pending_central_x_attr = nil, nil
local last_main_loop_frame, max_main_loop_gap = -1, 0
local tile_copy_hits, atomic_attr_passes = 0, 0
stage7_fast_copy_hits = 0
stage7_fused_copy_hits = 0
local attr_dma_commands, attr_gdma_commands, attr_hblank_commands = 0, 0, 0
local attr_invalid_dma_commands, attr_dma_scene_violations = 0, 0
local attr_dma_commands_trace = {}
local dma_command_addrs, attr_dma_site_hits = {}, {}
local dma_command_addr_seen = {}
local function add_dma_command_addr(address)
  if address and address > 0 and not dma_command_addr_seen[address] then
    dma_command_addr_seen[address] = true
    dma_command_addrs[#dma_command_addrs + 1] = address
    attr_dma_site_hits[address] = 0
  end
end
add_dma_command_addr(DMA_COMMAND_ADDR)
for raw in string.gmatch(DMA_COMMAND_ADDRS_RAW, "[^,]+") do
  add_dma_command_addr(tonumber(raw))
end
local atomic_call_indices = {}
local trace_addr_hits, trace_addr_samples, trace_readiness_samples, trace_addrs = {}, {}, {}, {}
local pc_sample_counts = {}
local ff_scan_hits, ff_scan_trace = 0, {}
local stage4_parser_trace = {}
for raw in string.gmatch(TRACE_ADDRS_RAW, "[^,]+") do
  local address = tonumber(raw)
  if address then
    trace_addrs[#trace_addrs + 1] = address
    trace_addr_hits[address] = 0
    trace_addr_samples[address] = {}
    trace_readiness_samples[address] = {}
  end
end
local postcopy_decisions, postcopy_dirty_decisions = 0, 0
local postcopy_dirty_tile_copy_indices = {}
local compiler_tile_copy_indices = {}
local previous_scx, previous_scy, scroll_changes = -1, -1, 0
-- FFC1 is a gameplay sub-mode flag, not a universal active/inactive bit.
-- Retain its high-frame count and first transition as diagnostic telemetry;
-- scene stability and main-loop throughput are the actual continuity gates.
local active_frames, first_inactive_frame = 0, -1
local first_inactive_state = ""
local expected_scene_frames, first_scene_mismatch = 0, -1
local dma_unreadable_scene_samples, non_dma_scene_mismatch_frames = 0, 0
local compiler_unreadable_scene_samples = 0
local first_scene_mismatch_value = -1
local mismatch_cpu_pc, mismatch_dma_source, mismatch_svbk = -1, -1, -1
local ffe4_zero_play_frames, ffe4_nonzero_play_frames = 0, 0
local first_ffe4_nonzero_play_frame, first_ffe4_nonzero_value = -1, -1
local window_helper_hits, window_helper_ffe4_nonzero_hits = 0, 0
local lava_copy_hits, attr_map_changes, attr_map_unchanged = 0, 0, 0
local attr_changed_cells, attr_changed_groups = 0, 0
local max_attr_changed_cells, max_attr_changed_groups = 0, 0
local previous_attr_map = nil
local attr_trace = TRACE and assert(io.open(TRACE, "w")) or nil
local lifecycle = LIFECYCLE and assert(io.open(LIFECYCLE, "w")) or nil
local previous_lifecycle = ""
local tile_copy_map_hi = -1
local breakpoints_available = false
local finished = false
local metatile_state = nil
local metatile_grids = {}
local metatile_capture_svbk = -1
local metatile_capture_source = -1
local finish
local abi_phase_addrs, abi_phase_hits = {}, {}
for raw in string.gmatch(ABI_PHASE_ADDRS_RAW, "[^,]+") do
  local address = tonumber(raw)
  if address then
    abi_phase_addrs[#abi_phase_addrs + 1] = address
    abi_phase_hits[address] = 0
  end
end
local abi_exit_hls = {}
for raw in string.gmatch(ABI_EXIT_HLS_RAW, "[^,]+") do
  local value = tonumber(raw)
  if value then abi_exit_hls[value] = true end
end
local abi_outer_returns, abi_outer_stack_hits, abi_outer_post_hits = {}, {}, {}
for raw in string.gmatch(ABI_OUTER_RETURNS_RAW, "[^,]+") do
  local address = tonumber(raw)
  if address then
    abi_outer_returns[address] = true
    abi_outer_stack_hits[address] = 0
    abi_outer_post_hits[address] = 0
  end
end
local abi_enabled = ABI_ENTRY_ADDR > 0 and ABI_EXIT_ADDR > 0
  and ABI_FALLBACK_ADDR > 0 and #abi_phase_addrs > 0 and ABI_BANK > 0
  and next(abi_outer_returns) ~= nil
local abi_entry_hits, abi_exit_hits, abi_depth = 0, 0, 0
local abi_fallback_hits, abi_caller_reject_hits = 0, 0
local abi_atomic_fallback_hits = 0
local abi_fallback_examples = {}
local abi_violations, abi_timer_inside, abi_timer_after_exit = 0, 0, 0
local abi_entry_ie_observed = -1
local abi_samples, abi_violation_examples = {}, {}
local abi_timer_snapshot = nil
local abi_timer_isr_pairs, abi_timer_source_changes = 0, 0
local abi_timer_bank_state_changes = 0
local abi_current_outer_return, abi_pending_outer_return = nil, nil
local abi_current_path = nil
local abi_fast_exit_hits, abi_native_exit_hits = 0, 0
local abi_native_exit_violations = 0
-- A fixed host-frame speed window can end in the middle of the helper's last
-- HBlank transfer.  The optional finalizer freezes every ordinary speed and
-- route counter at LIMIT, then observes only the already-entered helper until
-- its post-RETI outer return and restored hardware state.  It must never turn
-- the bounded drain into extra measured gameplay.
local safe_boundary_measurement_complete = false
local safe_boundary_drain_required = false
local safe_boundary_drain_frames = 0
local safe_boundary_status = SAFE_BOUNDARY_DRAIN and "armed" or "disabled"
local safe_boundary_post_hits = 0
local safe_boundary_last_outer_return = -1
local safe_boundary_extra_entries = 0
local safe_boundary_drain_dma_commands = 0
local safe_boundary_drain_hblank_commands = 0
local safe_boundary_drain_gdma_commands = 0
local safe_boundary_drain_scene_violations = 0
local safe_boundary_drain_fallback_hits = 0
local safe_boundary_drain_dma_trace = {}
local safe_boundary_start_depth = -1
local safe_boundary_start_pending_outer = -1
local safe_boundary_start_ff55 = -1
local safe_boundary_start_vbk = -1
local safe_boundary_start_svbk = -1
local safe_boundary_start_ie = -1
local safe_boundary_drain_ffe4_nonzero_frames = 0
local LAVA5 = {
  [0x02]=true, [0x03]=true, [0x04]=true, [0x05]=true,
  [0x12]=true, [0x13]=true, [0x14]=true, [0x15]=true,
}
local LAVA7 = {[0x19]=true, [0x1A]=true}

local function is_stage1_pickup(tile)
  return tile >= 0x80 and tile < 0xE0 and (tile & 0x08) ~= 0
end

local function entry_return()
  local ok, sp = pcall(function() return emu:readRegister("SP") end)
  if not ok or type(sp) ~= "number" then
    ok, sp = pcall(function() return emu:getRegister("SP") end)
  end
  if not ok or type(sp) ~= "number" then return -1 end
  return emu:read8(sp) + 256 * emu:read8((sp + 1) & 0xFFFF)
end

local function read_register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and type(value) == "number" then return value end
  ok, value = pcall(function() return emu:getRegister(name) end)
  if ok and type(value) == "number" then return value end
  return -1
end

local function in_fixed_bank1_cave()
  -- FF99 is a software bank shadow and can lag the mapped bank. Banked
  -- animation code also executes these addresses; authenticate the native
  -- copy entry and shared map setup before counting work at those sites.
  return emu:read8(0xFF99) == 0x01
    and emu:read8(0x4295) == 0xFA and emu:read8(0x4296) == 0x0B
    and emu:read8(0x4297) == 0xDC
    and emu:read8(0x42A7) == 0x2E and emu:read8(0x42A8) == 0x00
end

function penta_in_stage5_wide_copy()
  -- The native-gold release profile routes Stage 5 through a bank-21 clone of
  -- the complete DX copier. Authenticate its router and relocated wide loop;
  -- $6D00 is common banked address space and must never be counted from bank
  -- 13's unrelated story code.
  return emu:read8(0xFF99) == 0x15
    and emu:read8(0x6C80) == 0xF0 and emu:read8(0x6C81) == 0xBA
    and emu:read8(0x42B7) == 0xC3 and emu:read8(0x42B8) == 0x00
    and emu:read8(0x42B9) == 0x6D
    and emu:read8(0x6D00) == 0x11 and emu:read8(0x6D01) == 0xA0
    and emu:read8(0x6D02) == 0xC1 and emu:read8(0x6D03) == 0x0E
    and emu:read8(0x6D04) == 0x41
end

penta_has_stage5_wide_copy = TARGET == 4
  and emu:read8(0x0AB5) == 0xCD and emu:read8(0x0AB6) == 0x13
  and emu:read8(0x0AB7) == 0x00
  and emu:read8(0x12DD) == 0xCD and emu:read8(0x12DE) == 0x13
  and emu:read8(0x12DF) == 0x00
  and emu:read8(0x0013) == 0xF0 and emu:read8(0x0014) == 0xBA
  and emu:read8(0x0024) == 0xE6
  and (emu:read8(0x0025) == 0xFB or emu:read8(0x0025) == 0x01)
  and emu:read8(0x002B) == 0xC2 and emu:read8(0x002C) == 0x95
  and emu:read8(0x002D) == 0x42
  and emu:read8(0x003C) == 0x3E and emu:read8(0x003D) == 0x15
  and emu:read8(0x000D) == 0xC3 and emu:read8(0x000E) == 0x47
  and emu:read8(0x000F) == 0x08
  and emu:read8(0x4295) == 0xFA and emu:read8(0x4296) == 0x0B
  and emu:read8(0x4297) == 0xDC

function penta_in_stage1_native_copy()
  return TARGET == 0 and emu:read8(0xFF99) == 0x16
    and emu:read8(0x4295) == 0xFA and emu:read8(0x4296) == 0x0B
    and emu:read8(0x4297) == 0xDC
    and emu:read8(0x42A7) == 0x2E and emu:read8(0x42A8) == 0x00
end

function penta_in_stage7_private_copy()
  -- Stage 7 can use a bank-23 canonical clone whose already-classified pure
  -- branch selects a six-tile LCD-on copier. The optional fused layout also
  -- combines each classified dirty tile/attribute publication.
  return TARGET == 6 and emu:read8(0xFF99) == 0x17
    and emu:read8(0x4295) == 0xFA and emu:read8(0x4296) == 0x0B
    and emu:read8(0x4297) == 0xDC
    and emu:read8(0x42B0) == 0xCA
    and ((emu:read8(0x42B1) == 0x80 and emu:read8(0x42B2) == 0x6C
      and emu:read8(0x6C80) == 0xF0 and emu:read8(0x6C81) == 0x40
      and emu:read8(0x6D00) == 0x11 and emu:read8(0x6D01) == 0xA0
      and emu:read8(0x6D02) == 0xC1 and emu:read8(0x6D03) == 0x0E
      and emu:read8(0x6D04) == 0x41)
    or (emu:read8(0x42B1) == 0x00 and emu:read8(0x42B2) == 0x6C
      and emu:read8(0x6C00) == 0xF0 and emu:read8(0x6C01) == 0x40
      and emu:read8(0x6C80) == 0x11 and emu:read8(0x6C81) == 0xA0
      and emu:read8(0x6C82) == 0xC1 and emu:read8(0x6C83) == 0x0E
      and emu:read8(0x6C84) == 0x41
      and emu:read8(0x6EA2) == 0xF0 and emu:read8(0x6EA3) == 0xB7
      and emu:read8(0x7093) == 0x11 and emu:read8(0x7094) == 0xA0))
end

function penta_in_stage7_fused_copy()
  return penta_in_stage7_private_copy()
    and emu:read8(0x42B1) == 0x00
end

penta_has_stage7_private_copy = TARGET == 6
  and emu:read8(0x0AB5) == 0xCD and emu:read8(0x0AB6) == 0x13
  and emu:read8(0x0AB7) == 0x00
  and emu:read8(0x0013) == 0xF0 and emu:read8(0x0014) == 0xBA
  and emu:read8(0x0024) == 0xE6 and emu:read8(0x0025) == 0x01

local function in_owned_row_helper(pc, svbk, mapped_bank)
  return pc >= 0xD400 and pc <= 0xD478
    and (svbk & 0x07) == 0x03
    and (mapped_bank == 0x01
      or (COMPILER_BANK > 0 and mapped_bank == COMPILER_BANK))
end

local function scene_sample()
  local pc = read_register("PC") & 0xFFFF
  local svbk = emu:read8(0xFF70)
  -- mGBA's raw WRAM domain maps offset $1880 to physical bank1:$D880
  -- (CGB segment1; DMG's fixed upper WRAM). Unlike bus read8($D880),
  -- it is independent of SVBK and OAM DMA bus restrictions. Never waive a
  -- scene mismatch because PC lies inside a compiler: inspect the real byte.
  local wram = assert(emu.memory and emu.memory.wram,
    "physical WRAM domain required for scene provenance")
  local value = wram:read8(0x1880)
  return value, false, pc, svbk
end

local function safe_boundary_restored()
  if not SAFE_BOUNDARY_DRAIN or not abi_enabled then return false end
  local scene, unreadable = scene_sample()
  return abi_depth == 0
    and abi_pending_outer_return == nil
    and abi_current_outer_return == nil
    and abi_current_path == nil
    and abi_timer_snapshot == nil
    and emu:read8(0xFF55) == 0xFF
    and (emu:read8(0xFF4F) & 0x01) == 0
    and (emu:read8(0xFF70) & 0x07) == 1
    and emu:read8(0xFFFF) == ABI_EXIT_IE
    and not unreadable
    and scene == EXPECTED_SCENE
end

local function profile_lava_attr_map()
  if phase ~= "play" or emu:read8(0xD880) ~= EXPECTED_SCENE then
    return
  end
  lava_copy_hits = lava_copy_hits + 1
  local previous = previous_attr_map
  local current, changed, groups, map_hash = {}, 0, {}, 2166136261
  local bitset, rawset, packed_bits = {}, {}, 0
  for offset = 0, 575 do
    local tile = emu:read8(0xC1A0 + offset)
    rawset[#rawset + 1] = string.format("%02X", tile)
    -- Stage 1 predates the shared C600 semantic LUT. Every later dungeon
    -- compiles its stage-local pickup/material/lava assignments into that
    -- page during scene entry, so sampling the LUT records the attribute
    -- plane the ROM actually requests instead of maintaining a partial list
    -- of hard-coded Stage 5/7 tile families here.
    local desired = TARGET == 0
      and (is_stage1_pickup(tile) and 1 or 0)
      or (emu:read8(0xC600 + tile) & 0x07)
    current[offset + 1] = desired
    if desired ~= 0 then
      packed_bits = packed_bits + 2 ^ (offset % 8)
    end
    if offset % 8 == 7 then
      bitset[#bitset + 1] = string.format("%02X", packed_bits)
      packed_bits = 0
    end
    map_hash = (map_hash * 16777619 + desired * (offset + 1)) % 4294967296
    if previous == nil or previous[offset + 1] ~= desired then
      changed = changed + 1
      groups[math.floor(offset / 4)] = true
    end
  end
  if attr_trace then
    local raw_signature = (
      emu:read8(0xC1A4)
      ~ emu:read8(0xFF43)
      ~ emu:read8(0xFF42)
    ) & 0xFE
    attr_trace:write(string.format(
      "%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\t%d\t%u"
        .. "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X"
        .. "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X"
        .. "\t%04X\t%s\t%s\n",
      lava_copy_hits, play_frames, tile_copy_map_hi & 0xFF,
      emu:read8(0xFFBD), emu:read8(0xFF43), emu:read8(0xFF42),
      emu:read8(0xC1A4), raw_signature, changed > 0 and 1 or 0,
      changed, map_hash, emu:read8(0xDF4F),
      emu:read8(0xDF53), emu:read8(0xDF54),
      emu:read8(0xDF55), emu:read8(0xDF56),
      emu:read8(0xDF57), emu:read8(0xDF58),
      emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC02), emu:read8(0xDC03),
      emu:read8(0xDC81), emu:read8(0xFFCF),
      emu:read8(0xFFE8), emu:read8(0xFFE9), emu:read8(0xFFEB),
      entry_return() & 0xFFFF, table.concat(bitset), table.concat(rawset)))
    attr_trace:flush()
  end
  local group_count = 0
  for _ in pairs(groups) do group_count = group_count + 1 end
  if changed == 0 then
    attr_map_unchanged = attr_map_unchanged + 1
  else
    attr_map_changes = attr_map_changes + 1
    attr_changed_cells = attr_changed_cells + changed
    attr_changed_groups = attr_changed_groups + group_count
    if changed > max_attr_changed_cells then max_attr_changed_cells = changed end
    if group_count > max_attr_changed_groups then
      max_attr_changed_groups = group_count
    end
  end
  previous_attr_map = current
end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for offset = 1, 0x1F do emu:write8(base + offset, 0x00) end
  end
end

local function capture_metatile_state()
  if not METATILE_DUMP or frame < 330 then return end
  if phase == "title" then return end
  if emu:read8(0xFFBA) ~= TARGET then return end
  local source = emu:read8(0xDC0E) + 256 * emu:read8(0xDC0F)
  local grid = {}
  for row = 0, 9 do
    for column = 0, 10 do
      local address = source + row * 16 + column
      grid[#grid + 1] = string.char(emu:read8(address & 0xFFFF))
    end
  end
  local packed_grid = table.concat(grid)
  if phase == "play" then
    metatile_grids[#metatile_grids + 1] = packed_grid
  end
  if metatile_state then return end
  local bytes = {}
  -- Capture at stock $13A4, after its $09CE setup call and source-pointer
  -- load, while the game's own metatile expander has the
  -- stage-local external-RAM definitions and WRAM source/LUT banks selected.
  -- Reading these regions at verifier shutdown is invalid because both bank
  -- selectors may have changed by then.
  for address = 0xA000, 0xA3FF do
    bytes[#bytes + 1] = string.char(emu:read8(address))
  end
  for address = 0xC600, 0xC6FF do
    bytes[#bytes + 1] = string.char(emu:read8(address))
  end
  -- Stock consumes 11 IDs, then advances five more bytes: ten rows at a
  -- 16-byte source stride. Pack only the 10x11 consumed IDs in the artifact.
  bytes[#bytes + 1] = packed_grid
  metatile_state = table.concat(bytes)
  metatile_capture_svbk = emu:read8(0xFF70)
  metatile_capture_source = source
end

breakpoints_available = pcall(function()
  if copy_trace then
    local function trace_copy(event)
      if phase ~= "play" then return end
      local w = assert(emu.memory.wram)
      local sp = read_register("SP") & 0xFFFF
      local pc=read_register("PC") & 0xFFFF
      copy_trace:write(string.format("%d\t%d\t%s\t%d\t%04X\t%04X\t%d\t%d\t%d\t%d\t%d\t%d\t%02X%02X%02X\t%d\n",
        play_frames, main_loop_hits, event, emu:read8(0xFF99),
        emu:read8(sp) + 256 * emu:read8((sp+1)&0xFFFF),
        read_register("HL") & 0xFFFF, emu:read8(0xFFBD), w:read8(0x1880),
        emu:read8(0xFFC4), w:read8(0x1C0B),
        w:read8(0x1C00) + 256*w:read8(0x1C01),
        w:read8(0x1C02) + 256*w:read8(0x1C03),
        emu:read8(pc),emu:read8((pc+1)&0xFFFF),emu:read8((pc+2)&0xFFFF),emu:read8(0xFF01)))
      copy_trace:flush()
    end
    for _, site in ipairs({{0x4295,"full-entry"},{0x435A,"partial-entry"},{0x42A7,"copy"},
                          {0x42BB,"loop-entry"},{0x42ED,"copy-done"},{0x4302,"compile"}}) do
      local address,event=site[1],site[2]
      emu:setBreakpoint(function()
        if in_fixed_bank1_cave() or penta_in_stage1_native_copy()
            or penta_in_stage5_wide_copy()
            or penta_in_stage7_private_copy() then
          trace_copy(event)
        end
      end,address)
    end
    emu:setBreakpoint(function()
      if emu:read8(0xFF99) == 24 then
        assert(emu:read8(0x6E00)==0xF0 and emu:read8(0x6E01)==0xC4
          and emu:read8(0x6E04)==0xC0, "packer trace preimage changed")
        trace_copy("packer-entry")
      end
    end,0x6E00)
    emu:setBreakpoint(function()
      if emu:read8(0xFF99) == 24 then trace_copy("packer-accepted") end
    end,0x6E05)
  end
  -- The two stock entries publish H immediately before the shared 0x42A7
  -- copy path. Track the control flow because this mGBA build does not expose
  -- CPU H reliably through Lua.
  emu:setBreakpoint(function()
    if in_fixed_bank1_cave() or penta_in_stage1_native_copy()
        or penta_in_stage5_wide_copy()
        or penta_in_stage7_private_copy() then
      tile_copy_map_hi = 0x9C
    end
  end, 0x42A0)
  emu:setBreakpoint(function()
    if in_fixed_bank1_cave() or penta_in_stage1_native_copy()
        or penta_in_stage5_wide_copy()
        or penta_in_stage7_private_copy() then
      tile_copy_map_hi = 0x98
    end
  end, 0x42A5)
  emu:setBreakpoint(function()
    -- A host frame callback can enter gameplay at any CPU position inside
    -- the stock loop. Starting the fixed-frame window there made equivalent
    -- cold boots disagree by dozens of iterations in some stages. Arm the
    -- measurement after scene stability, then open it only on this real
    -- main-loop anchor so input, telemetry, and both replay windows share an
    -- exact CPU boundary.
    if phase == "sync" then
      phase = "play"
      play_frames = 0
      previous_scx = emu:read8(0xFF43)
      previous_scy = emu:read8(0xFF42)
    end
    if phase == "play" then
      main_loop_hits = main_loop_hits + 1
      if loop_trace then
        local wram = assert(emu.memory.wram)
        loop_trace:write(string.format("%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",
          main_loop_hits, play_frames, wram:read8(0x1880), emu:read8(0xFFBD),
          wram:read8(0x1C00) + 256 * wram:read8(0x1C01),
          wram:read8(0x1C02) + 256 * wram:read8(0x1C03),
          wram:read8(0x1CB8), emu:read8(0xFFBF), emu:read8(0xFF93),
          emu:read8(0xFFC8), emu:read8(0xFFC9), emu:read8(0xFFCA),
          emu:read8(0xFFD3), emu:read8(0xFFEB), emu:read8(0xFFE4)))
      end
      -- Separate diagnostic routes: choose input at the CPU loop anchor,
      -- not at a host-frame boundary. Keep the original timed routes intact.
      -- Fifteen iterations in each direction, first iteration included.
      if INPUT_MODE == "loop-patrol" then
        emu:setKeys((main_loop_hits - 1) % 30 < 15 and KEY_RIGHT or KEY_LEFT)
      elseif INPUT_MODE == "loop-vertical-patrol" then
        emu:setKeys((main_loop_hits - 1) % 30 < 15 and KEY_UP or KEY_DOWN)
      end
      if last_main_loop_frame >= 0 then
        local gap = play_frames - last_main_loop_frame
        if gap > max_main_loop_gap then max_main_loop_gap = gap end
      end
      last_main_loop_frame = play_frames
    end
  end, 0x016C)
  if WINDOW_HELPER_ADDR > 0 and WINDOW_HELPER_BANK > 0 then
    emu:setBreakpoint(function()
      if (phase ~= "play" and phase ~= "drain")
          or emu:read8(0xFF99) ~= WINDOW_HELPER_BANK then return end
      window_helper_hits = window_helper_hits + 1
      if emu:read8(0xFFE4) ~= 0 then
        window_helper_ffe4_nonzero_hits =
          window_helper_ffe4_nonzero_hits + 1
      end
    end, WINDOW_HELPER_ADDR)
  end
  emu:setBreakpoint(function()
    if phase == "play" then
      central_emitter_hits = central_emitter_hits + 1
      pending_central_attr, pending_central_x_attr = nil, nil
      local hl = read_register("HL") & 0xFFFF
      local tile = emu:read8(hl)
      local palette = emu:read8(0xD900 + tile)
      if palette == 0xFF then
        palette = emu:read8(0xFFBE) == 0 and 2 or 1
      end
      central_tile_counts[tile] = (central_tile_counts[tile] or 0) + 1
      central_palette_counts[palette] =
        (central_palette_counts[palette] or 0) + 1
    end
  end, 0x10D1)
  -- Attribute helpers $11A2/$1188 are also used outside the central emitter.
  -- Filter by their synthetic return addresses so these counters describe
  -- only the WRAM-hot $DA21 path.  The emitter is DI-bounded, so one pending
  -- sample cannot be interleaved with another sprite emission.
  local function sample_central_x(entry)
    if phase == "play" and entry_return() == 0xDA3E then
      if entry == 0x11A2 then
        central_x_entry_11a2 = central_x_entry_11a2 + 1
      else
        central_x_entry_11a5 = central_x_entry_11a5 + 1
      end
      pending_central_attr = read_register("A") & 0xFF
      pending_central_x_attr = nil
    end
  end
  -- Production r210 enters the original helper at $11A2.  The compact,
  -- ABI-equivalent speed candidate relocates that same helper to $11A5.
  -- Observe both exact entries and keep the synthetic-return filter above;
  -- otherwise a faster candidate can silently lose all output telemetry.
  emu:setBreakpoint(function() sample_central_x(0x11A2) end, 0x11A2)
  emu:setBreakpoint(function() sample_central_x(0x11A5) end, 0x11A5)
  emu:setBreakpoint(function()
    if phase == "play" and entry_return() == 0xDA41
        and pending_central_attr ~= nil then
      pending_central_x_attr = read_register("A") & 0xFF
      local slot = emu:read8(0xFFDD)
      if slot < 4 then
        central_y_low_slot_samples = central_y_low_slot_samples + 1
        if emu:read8(0xFFC2 + slot) ~= 0 then
          central_y_low_control_set = central_y_low_control_set + 1
        end
      end
      if ((pending_central_x_attr ~ pending_central_attr) & 0x10) ~= 0 then
        central_xflip_changes = central_xflip_changes + 1
      end
    end
  end, 0x1188)
  emu:setBreakpoint(function()
    if phase == "play" and pending_central_attr ~= nil
        and pending_central_x_attr ~= nil then
      local final_attr = read_register("A") & 0xFF
      central_attr_samples = central_attr_samples + 1
      if ((final_attr ~ pending_central_x_attr) & 0x80) ~= 0 then
        central_yflip_changes = central_yflip_changes + 1
      end
      if ((final_attr ~ pending_central_attr) & 0x90) ~= 0 then
        central_any_flip_changes = central_any_flip_changes + 1
      end
      pending_central_attr, pending_central_x_attr = nil, nil
    end
  end, 0xDA41)
  emu:setBreakpoint(function()
    if phase == "play" then free_emitter_hits = free_emitter_hits + 1 end
  end, 0x346F)
  emu:setBreakpoint(function()
    if phase == "play" and (in_fixed_bank1_cave()
        or penta_in_stage1_native_copy()
        or penta_in_stage7_private_copy()) then
      tile_copy_hits = tile_copy_hits + 1
      profile_lava_attr_map()
    end
  end, 0x42A7)
  if penta_has_stage5_wide_copy then
    emu:setBreakpoint(function()
      if phase == "play" and penta_in_stage5_wide_copy() then
        -- The private selector has already updated DC0B and H before entering
        -- this address. Derive the physical page from the same native latch so
        -- this stays independent of mGBA builds that cannot expose H to Lua.
        tile_copy_map_hi = emu:read8(0xDC0B) == 0 and 0x98 or 0x9C
        tile_copy_hits = tile_copy_hits + 1
        profile_lava_attr_map()
      end
    end, 0x6D00)
  end
  if penta_has_stage7_private_copy then
    emu:setBreakpoint(function()
      if phase == "play" and penta_in_stage7_private_copy()
          and not penta_in_stage7_fused_copy() then
        stage7_fast_copy_hits = stage7_fast_copy_hits + 1
      end
    end, 0x6D00)
    emu:setBreakpoint(function()
      if phase == "play" and penta_in_stage7_fused_copy() then
        stage7_fast_copy_hits = stage7_fast_copy_hits + 1
      end
    end, 0x7093)
    emu:setBreakpoint(function()
      if phase == "play" and penta_in_stage7_fused_copy() then
        stage7_fused_copy_hits = stage7_fused_copy_hits + 1
      end
    end, 0x6EA2)
  end
  emu:setBreakpoint(capture_metatile_state, 0x13A4)
  -- The production postcomputed copier latches a dirty decision in B.7,
  -- copies the tile plane at stock width, then tests that stable bit here.
  -- FFE0 has already been reused by this point, so sampling it at $42A7
  -- cannot describe the executed attribute path.
  emu:setBreakpoint(function()
    if phase == "play" and (in_fixed_bank1_cave()
        or penta_in_stage7_private_copy()) then
      postcopy_decisions = postcopy_decisions + 1
      local b = read_register("B") & 0xFF
      if (b & 0x80) ~= 0 then
        postcopy_dirty_decisions = postcopy_dirty_decisions + 1
        postcopy_dirty_tile_copy_indices[
          #postcopy_dirty_tile_copy_indices + 1
        ] = tile_copy_hits
      end
    end
  end, 0x42F5)
  emu:setBreakpoint(function()
    if phase == "play" and (in_fixed_bank1_cave()
        or penta_in_stage7_private_copy())
        and emu:read8(0x4302) == 0xF3 then
      compiler_tile_copy_indices[#compiler_tile_copy_indices + 1] = tile_copy_hits
    end
  end, 0x4302)
  if ATOMIC_ADDR > 0 then
    emu:setBreakpoint(function()
      if phase == "play" then
        atomic_attr_passes = atomic_attr_passes + 1
        atomic_call_indices[#atomic_call_indices + 1] = lava_copy_hits
      end
    end, ATOMIC_ADDR)
  end
  for _, configured_address in ipairs(dma_command_addrs) do
    local dma_command_address = configured_address
    emu:setBreakpoint(function()
      local dma_owner = in_fixed_bank1_cave()
        or penta_in_stage7_private_copy()
        or (COMPILER_BANK > 0
          and emu:read8(0xFF99) == COMPILER_BANK
          and dma_command_address >= COMPILER_START
          and dma_command_address <= COMPILER_END)
      if (phase == "play" or phase == "drain") and dma_owner
          and emu:read8(dma_command_address) == 0xE0
          and emu:read8(dma_command_address + 1) == 0x55 then
        local command = read_register("A") & 0xFF
        local scene, unreadable = scene_sample()
        if phase == "drain" then
          -- Drain telemetry is deliberately separate: these commands belong
          -- to the helper already active at the LIMIT boundary and must not
          -- inflate fixed-window throughput/publication counts.
          safe_boundary_drain_dma_commands =
            safe_boundary_drain_dma_commands + 1
          if (command & 0x80) ~= 0 then
            safe_boundary_drain_hblank_commands =
              safe_boundary_drain_hblank_commands + 1
          else
            safe_boundary_drain_gdma_commands =
              safe_boundary_drain_gdma_commands + 1
          end
          if not unreadable and scene ~= EXPECTED_SCENE then
            safe_boundary_drain_scene_violations =
              safe_boundary_drain_scene_violations + 1
          end
          if #safe_boundary_drain_dma_trace < 128 then
            safe_boundary_drain_dma_trace[
              #safe_boundary_drain_dma_trace + 1
            ] = string.format("%d:%04X:%02X:%02X:%02X", play_frames,
              dma_command_address, command, scene & 0xFF,
              emu:read8(0xFF40))
          end
          return
        end
        attr_dma_commands = attr_dma_commands + 1
        attr_dma_site_hits[dma_command_address] =
          attr_dma_site_hits[dma_command_address] + 1
        -- HDMA5 bits 0..6 select any legal length from 1..128 blocks;
        -- bit 7 alone selects HBlank ($80..$FF) versus immediate GDMA
        -- ($00..$7F). Historical $AF/$2F receipts are the 48-block cases,
        -- not the only valid commands.
        if (command & 0x80) ~= 0 then
          attr_hblank_commands = attr_hblank_commands + 1
        else
          attr_gdma_commands = attr_gdma_commands + 1
        end
        if not unreadable and scene ~= EXPECTED_SCENE then
          attr_dma_scene_violations = attr_dma_scene_violations + 1
        end
        if #attr_dma_commands_trace < 256 then
          attr_dma_commands_trace[#attr_dma_commands_trace + 1] =
            string.format("%d:%02X:%02X:%02X", play_frames, command,
              scene & 0xFF, emu:read8(0xFF40))
        end
      end
    end, dma_command_address)
  end
  for _, configured_address in ipairs(trace_addrs) do
    local address = configured_address
    emu:setBreakpoint(function()
      if phase == "play" then
        trace_addr_hits[address] = trace_addr_hits[address] + 1
        local samples = trace_addr_samples[address]
        if #samples < 64 then
          -- FFA5 is the exact completed-map destination/dirty latch. Keeping
          -- it in generic trace samples lets carry-signal experiments prove
          -- C=0 iff FFA5=0 and C=1 iff FFA5 is $98/$9C at map_done without a
          -- second emulator run. Existing consumers treat samples as opaque.
          samples[#samples + 1] = string.format(
            "%d:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X",
            play_frames,
            read_register("A") & 0xFF,
            read_register("B") & 0xFF,
            read_register("F") & 0xFF,
            emu:read8(0xFFBA), emu:read8(0xD880), emu:read8(0xFF99),
            emu:read8(0xFFA5), emu:read8(0xFF70), emu:read8(0xFF4F),
            emu:read8(0xFF51), emu:read8(0xFF52), emu:read8(0xFF53),
            emu:read8(0xFF54), emu:read8(0xD04A), emu:read8(0xD04E),
            emu:read8(0x984A), emu:read8(0x984E), emu:read8(0x9C4A))
        end
        local readiness = trace_readiness_samples[address]
        if #readiness < 256 then
          -- Keep readiness/cache telemetry separate from the legacy opaque
          -- register sample. Several historical receipt readers consume the
          -- old positional string, so extending it would silently invalidate
          -- their field contract. This companion sample identifies whether a
          -- Stage-1 semantic scan is part of the mandatory cold BG sweep or a
          -- settled redundant publication, independently for both maps.
          readiness[#readiness + 1] = string.format(
            "%d:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X",
            play_frames,
            emu:read8(0xFFBD), emu:read8(0xDF4E),
            emu:read8(0xDF55), emu:read8(0xDF59),
            emu:read8(0xFFA5), read_register("H") & 0xFF,
            emu:read8(0xFF40), emu:read8(0xFF4F),
            emu:read8(0xD47E), emu:read8(0xD47F))
        end
      end
    end, address)
  end
  -- Stage 4 can enter stock's $0E6B FF-terminated list scan for whole
  -- rendered frames. Capture its exact RAM cursor and caller contract so a
  -- slowdown caused by malformed data is distinguishable from renderer cost.
  emu:setBreakpoint(function()
    if phase == "play" then
      ff_scan_hits = ff_scan_hits + 1
      if #ff_scan_trace < 256 then
        local hl = read_register("HL") & 0xFFFF
        ff_scan_trace[#ff_scan_trace + 1] = string.format(
          "%04X:%02X:%02X:%04X", hl, emu:read8(hl),
          read_register("B") & 0xFF, entry_return() & 0xFFFF)
      end
    end
  end, 0x0E6B)
  for _, configured_address in ipairs({0x0DF6, 0x0DFA, 0x0E3C, 0x0E5A, 0x0E65}) do
    local address = configured_address
    emu:setBreakpoint(function()
      if phase == "play" and #stage4_parser_trace < 256 then
        stage4_parser_trace[#stage4_parser_trace + 1] = string.format(
          "%d:%04X:%02X:%02X:%02X:%02X:%02X:%04X:%04X:%02X",
          play_frames, address, read_register("A") & 0xFF,
          read_register("B") & 0xFF, read_register("C") & 0xFF,
          read_register("D") & 0xFF, read_register("E") & 0xFF,
          read_register("HL") & 0xFFFF, read_register("SP") & 0xFFFF,
          emu:read8(0xFF99))
      end
    end, address)
  end

  if abi_enabled then
    local function abi_source_plane()
      local bytes = {}
      for address = 0xC1A0, 0xC3DF do
        bytes[#bytes + 1] = string.char(emu:read8(address))
      end
      return table.concat(bytes)
    end
    local function abi_owned_address(bank)
      return (phase == "play" or phase == "drain")
        and emu:read8(0xFF99) == bank
    end
    local function record_fallback(kind, address)
      if #abi_fallback_examples >= 32 then return end
      abi_fallback_examples[#abi_fallback_examples + 1] = string.format(
        "%s:%d:%04X:%04X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X",
        kind, play_frames, address, abi_current_outer_return or 0xFFFF,
        emu:read8(0xD880), emu:read8(0xFFBA), emu:read8(0xFFC1),
        emu:read8(0xFF40), emu:read8(0xFF43), emu:read8(0xFF42),
        read_register("H") & 0xFF, emu:read8(0xFF55))
    end
    local function abi_snapshot(kind, address, expected_ie)
      local ff55 = emu:read8(0xFF55)
      local vbk = emu:read8(0xFF4F) & 0x01
      local svbk = emu:read8(0xFF70) & 0x07
      local ie = emu:read8(0xFFFF)
      local scene = svbk == 1 and emu:read8(0xD880) or 0xFF
      local af = ((read_register("A") & 0xFF) << 8)
        | (read_register("F") & 0xF0)
      local bc = ((read_register("B") & 0xFF) << 8)
        | (read_register("C") & 0xFF)
      local de = ((read_register("D") & 0xFF) << 8)
        | (read_register("E") & 0xFF)
      local hl = read_register("HL") & 0xFFFF
      local ffa5 = emu:read8(0xFFA5)
      local ffe0 = emu:read8(0xFFE0)
      local sample = string.format(
        "%s:%d:%04X:%02X:%02X:%02X:%02X:%02X:%04X:%d:%04X:%04X:%04X:%04X:%02X:%02X",
        kind, play_frames, address, ff55, vbk, svbk, ie, scene,
        read_register("SP") & 0xFFFF, abi_depth, af, bc, de, hl, ffa5, ffe0)
      if #abi_samples < 256 then abi_samples[#abi_samples + 1] = sample end
      local bad = ff55 ~= 0xFF or vbk ~= 0 or svbk ~= 1
        or ie ~= expected_ie or scene ~= EXPECTED_SCENE
      if kind == "exit" then
        bad = bad or af ~= ABI_EXIT_AF or bc ~= ABI_EXIT_BC
          or de ~= ABI_EXIT_DE or not abi_exit_hls[hl]
          or ffa5 ~= ABI_EXIT_FFA5 or ffe0 ~= ABI_EXIT_FFE0
      elseif kind == "native-exit" then
        -- A guard-rejected entry rejoins the stock bank-1 copier at $42B3.
        -- That path intentionally preserves BC=$C600 rather than the fast
        -- helper's synthetic BC=$084D, but shares the exact restored
        -- AF/DE/HL/latches/banks contract at the common $436D RETI.
        bad = bad or af ~= ABI_EXIT_AF or bc ~= 0xC600
          or de ~= ABI_EXIT_DE or not abi_exit_hls[hl]
          or ffa5 ~= ABI_EXIT_FFA5 or ffe0 ~= ABI_EXIT_FFE0
      end
      if bad then
        abi_violations = abi_violations + 1
        if kind == "native-exit" then
          abi_native_exit_violations = abi_native_exit_violations + 1
        end
        if #abi_violation_examples < 32 then
          abi_violation_examples[#abi_violation_examples + 1] = sample
        end
      end
    end

    emu:setBreakpoint(function()
      if not abi_owned_address(ABI_BANK) then return end
      if safe_boundary_measurement_complete then
        safe_boundary_extra_entries = safe_boundary_extra_entries + 1
      end
      if abi_depth ~= 0 or abi_current_outer_return ~= nil
          or abi_current_path ~= nil
          or abi_pending_outer_return ~= nil then
        abi_violations = abi_violations + 1
      end
      local sp = read_register("SP") & 0xFFFF
      local synthetic_return = emu:read8(sp)
        | (emu:read8((sp + 1) & 0xFFFF) << 8)
      local outer_return = emu:read8((sp + 2) & 0xFFFF)
        | (emu:read8((sp + 3) & 0xFFFF) << 8)
      if synthetic_return ~= 0x084D or not abi_outer_returns[outer_return] then
        abi_violations = abi_violations + 1
      else
        abi_outer_stack_hits[outer_return] =
          abi_outer_stack_hits[outer_return] + 1
      end
      abi_current_outer_return = outer_return
      abi_current_path = "fast"
      abi_depth = abi_depth + 1
      abi_entry_hits = abi_entry_hits + 1
      abi_entry_ie_observed = emu:read8(0xFFFF)
      abi_snapshot("entry", ABI_ENTRY_ADDR, ABI_ENTRY_IE)
    end, ABI_ENTRY_ADDR)

    emu:setBreakpoint(function()
      if not abi_owned_address(ABI_BANK) or abi_depth ~= 1 then return end
      abi_fallback_hits = abi_fallback_hits + 1
      if abi_current_path ~= "fast" then
        abi_violations = abi_violations + 1
      end
      abi_current_path = "native"
      if safe_boundary_measurement_complete then
        safe_boundary_drain_fallback_hits =
          safe_boundary_drain_fallback_hits + 1
      end
      record_fallback("native", ABI_FALLBACK_ADDR)
    end, ABI_FALLBACK_ADDR)

    if ABI_CALLER_REJECT_ADDR > 0 then
      emu:setBreakpoint(function()
        if not abi_owned_address(ABI_BANK) or abi_depth ~= 1 then return end
        abi_caller_reject_hits = abi_caller_reject_hits + 1
        record_fallback("caller", ABI_CALLER_REJECT_ADDR)
      end, ABI_CALLER_REJECT_ADDR)
    end

    if ABI_ATOMIC_FALLBACK_ADDR > 0 then
      emu:setBreakpoint(function()
        if not abi_owned_address(ABI_BANK) or abi_depth ~= 1 then return end
        abi_atomic_fallback_hits = abi_atomic_fallback_hits + 1
        record_fallback("atomic", ABI_ATOMIC_FALLBACK_ADDR)
      end, ABI_ATOMIC_FALLBACK_ADDR)
    end

    for _, configured_address in ipairs(abi_phase_addrs) do
      local address = configured_address
      emu:setBreakpoint(function()
        if not abi_owned_address(ABI_BANK) then return end
        abi_phase_hits[address] = abi_phase_hits[address] + 1
        if abi_depth ~= 1 or abi_current_path ~= "fast" then
          abi_violations = abi_violations + 1
        end
        abi_snapshot("phase", address, ABI_PHASE_IE)
      end, address)
    end

    emu:setBreakpoint(function()
      if not abi_owned_address(ABI_EXIT_BANK) or abi_depth == 0 then return end
      abi_exit_hits = abi_exit_hits + 1
      if abi_depth ~= 1 or abi_entry_ie_observed ~= ABI_EXIT_IE
          or abi_timer_snapshot ~= nil then
        abi_violations = abi_violations + 1
      end
      if abi_current_path == "native" then
        abi_native_exit_hits = abi_native_exit_hits + 1
        abi_snapshot("native-exit", ABI_EXIT_ADDR, ABI_EXIT_IE)
      elseif abi_current_path == "fast" then
        abi_fast_exit_hits = abi_fast_exit_hits + 1
        abi_snapshot("exit", ABI_EXIT_ADDR, ABI_EXIT_IE)
      else
        abi_violations = abi_violations + 1
        abi_snapshot("unknown-exit", ABI_EXIT_ADDR, ABI_EXIT_IE)
      end
      abi_pending_outer_return = abi_current_outer_return
      abi_current_outer_return = nil
      abi_current_path = nil
      abi_depth = abi_depth - 1
    end, ABI_EXIT_ADDR)

    for address in pairs(abi_outer_returns) do
      local outer_address = address
      emu:setBreakpoint(function()
        if abi_pending_outer_return == nil then return end
        if abi_pending_outer_return ~= outer_address then
          abi_violations = abi_violations + 1
          return
        end
        abi_outer_post_hits[outer_address] =
          abi_outer_post_hits[outer_address] + 1
        abi_pending_outer_return = nil
        if safe_boundary_measurement_complete then
          safe_boundary_post_hits = safe_boundary_post_hits + 1
          safe_boundary_last_outer_return = outer_address
          if SAFE_BOUNDARY_DRAIN and safe_boundary_extra_entries == 0
              and safe_boundary_restored() then
            safe_boundary_status = "completed"
            finish()
          end
        end
      end, outer_address)
    end

    -- mGBA's Lua API does not expose IME. A Timer-vector hit while the helper
    -- is active proves its bounded EI service point is executable; a later
    -- hit after a completed helper proves interrupt service resumes outside.
    emu:setBreakpoint(function()
      if phase ~= "play" and phase ~= "drain" then return end
      if abi_depth == 1 then
        abi_timer_inside = abi_timer_inside + 1
        if abi_timer_snapshot ~= nil then
          abi_violations = abi_violations + 1
        end
        abi_timer_snapshot = {
          source = abi_source_plane(),
          ff55 = emu:read8(0xFF55),
          vbk = emu:read8(0xFF4F) & 0x01,
          svbk = emu:read8(0xFF70) & 0x07,
          ie = emu:read8(0xFFFF),
          ff99 = emu:read8(0xFF99),
          ffa5 = emu:read8(0xFFA5),
          ffe0 = emu:read8(0xFFE0),
        }
      elseif abi_exit_hits > 0 then
        abi_timer_after_exit = abi_timer_after_exit + 1
      end
    end, 0x0050)

    -- Pair each in-helper Timer vector with the ISR's RETI. This proves the
    -- sound service did not mutate the packed tile source or disturb the
    -- helper's required FF55/VBK/SVBK/IE state while interrupts were open.
    emu:setBreakpoint(function()
      if abi_depth ~= 1 or abi_timer_snapshot == nil then return end
      abi_timer_isr_pairs = abi_timer_isr_pairs + 1
      if abi_source_plane() ~= abi_timer_snapshot.source then
        abi_timer_source_changes = abi_timer_source_changes + 1
        abi_violations = abi_violations + 1
      end
      if emu:read8(0xFF55) ~= abi_timer_snapshot.ff55
          or (emu:read8(0xFF4F) & 0x01) ~= abi_timer_snapshot.vbk
          or (emu:read8(0xFF70) & 0x07) ~= abi_timer_snapshot.svbk
          or emu:read8(0xFFFF) ~= abi_timer_snapshot.ie
          or emu:read8(0xFF99) ~= abi_timer_snapshot.ff99
          or emu:read8(0xFFA5) ~= abi_timer_snapshot.ffa5
          or emu:read8(0xFFE0) ~= abi_timer_snapshot.ffe0 then
        abi_timer_bank_state_changes = abi_timer_bank_state_changes + 1
        abi_violations = abi_violations + 1
      end
      abi_timer_snapshot = nil
    end, 0x06D0)
  end
end)

finish = function()
  if finished then return end
  finished = true
  local handle = assert(io.open(OUT, "w"))
  handle:write("{\n")
  handle:write(string.format('  "target": %d,\n', TARGET))
  handle:write(string.format('  "stage": %d,\n', TARGET + 1))
  handle:write(string.format('  "expected_scene": %d,\n', EXPECTED_SCENE))
  local final_scene, final_scene_compiler_unreadable = scene_sample()
  if final_scene_compiler_unreadable then final_scene = EXPECTED_SCENE end
  handle:write(string.format('  "final_scene": %d,\n', final_scene))
  handle:write(string.format('  "frames": %d,\n', play_frames))
  handle:write(string.format('  "sync_delay_frames": %d,\n', SYNC_DELAY))
  handle:write(string.format(
    '  "safe_boundary_drain_enabled": %s,\n',
    tostring(SAFE_BOUNDARY_DRAIN)))
  handle:write(string.format(
    '  "safe_boundary_measurement_complete": %s,\n',
    tostring(safe_boundary_measurement_complete)))
  handle:write(string.format(
    '  "safe_boundary_drain_required": %s,\n',
    tostring(safe_boundary_drain_required)))
  handle:write(string.format(
    '  "safe_boundary_status": "%s",\n', safe_boundary_status))
  handle:write(string.format(
    '  "safe_boundary_max_frames": %d,\n', SAFE_BOUNDARY_MAX_FRAMES))
  handle:write(string.format(
    '  "safe_boundary_drain_frames": %d,\n', safe_boundary_drain_frames))
  handle:write(string.format(
    '  "safe_boundary_post_hits": %d,\n', safe_boundary_post_hits))
  handle:write(string.format(
    '  "safe_boundary_last_outer_return": %d,\n',
    safe_boundary_last_outer_return))
  handle:write(string.format(
    '  "safe_boundary_extra_entries": %d,\n',
    safe_boundary_extra_entries))
  handle:write(string.format(
    '  "safe_boundary_start_depth": %d,\n', safe_boundary_start_depth))
  handle:write(string.format(
    '  "safe_boundary_start_pending_outer": %d,\n',
    safe_boundary_start_pending_outer))
  handle:write(string.format(
    '  "safe_boundary_start_ff55": %d,\n', safe_boundary_start_ff55))
  handle:write(string.format(
    '  "safe_boundary_start_vbk": %d,\n', safe_boundary_start_vbk))
  handle:write(string.format(
    '  "safe_boundary_start_svbk": %d,\n', safe_boundary_start_svbk))
  handle:write(string.format(
    '  "safe_boundary_start_ie": %d,\n', safe_boundary_start_ie))
  handle:write(string.format(
    '  "safe_boundary_drain_dma_commands": %d,\n',
    safe_boundary_drain_dma_commands))
  handle:write(string.format(
    '  "safe_boundary_drain_hblank_commands": %d,\n',
    safe_boundary_drain_hblank_commands))
  handle:write(string.format(
    '  "safe_boundary_drain_gdma_commands": %d,\n',
    safe_boundary_drain_gdma_commands))
  handle:write(string.format(
    '  "safe_boundary_drain_scene_violations": %d,\n',
    safe_boundary_drain_scene_violations))
  handle:write(string.format(
    '  "safe_boundary_drain_ffe4_nonzero_frames": %d,\n',
    safe_boundary_drain_ffe4_nonzero_frames))
  handle:write(string.format(
    '  "safe_boundary_drain_fallback_hits": %d,\n',
    safe_boundary_drain_fallback_hits))
  local safe_drain_trace_parts = {}
  for _, record in ipairs(safe_boundary_drain_dma_trace) do
    safe_drain_trace_parts[#safe_drain_trace_parts + 1] =
      string.format('"%s"', record)
  end
  handle:write(string.format(
    '  "safe_boundary_drain_dma_trace": [%s],\n',
    table.concat(safe_drain_trace_parts, ",")))
  handle:write(string.format(
    '  "safe_boundary_final_restored": %s,\n',
    tostring(safe_boundary_restored())))
  handle:write(string.format(
    '  "stage1_decider_mode": "%s",\n', STAGE1_DECIDER_MODE))
  handle:write(string.format(
    '  "breakpoints_available": %s,\n', tostring(breakpoints_available)))
  handle:write(string.format('  "main_loop_hits": %d,\n', main_loop_hits))
  handle:write(string.format(
    '  "last_main_loop_frame": %d,\n', last_main_loop_frame))
  handle:write(string.format(
    '  "max_main_loop_gap": %d,\n', max_main_loop_gap))
  handle:write(string.format(
    '  "central_emitter_hits": %d,\n', central_emitter_hits))
  local central_tile_parts = {}
  for tile = 0, 255 do
    if central_tile_counts[tile] then
      central_tile_parts[#central_tile_parts + 1] = string.format(
        '"%02X":%d', tile, central_tile_counts[tile])
    end
  end
  handle:write(string.format(
    '  "central_tile_counts": {%s},\n', table.concat(central_tile_parts, ",")))
  local central_palette_parts = {}
  for palette = 0, 255 do
    if central_palette_counts[palette] then
      central_palette_parts[#central_palette_parts + 1] = string.format(
        '"%02X":%d', palette, central_palette_counts[palette])
    end
  end
  handle:write(string.format(
    '  "central_palette_counts": {%s},\n',
    table.concat(central_palette_parts, ",")))
  handle:write(string.format(
    '  "central_attr_samples": %d,\n', central_attr_samples))
  handle:write(string.format(
    '  "central_xflip_changes": %d,\n', central_xflip_changes))
  handle:write(string.format(
    '  "central_yflip_changes": %d,\n', central_yflip_changes))
  handle:write(string.format(
    '  "central_any_flip_changes": %d,\n', central_any_flip_changes))
  handle:write(string.format(
    '  "central_y_low_slot_samples": %d,\n', central_y_low_slot_samples))
  handle:write(string.format(
    '  "central_y_low_control_set": %d,\n', central_y_low_control_set))
  handle:write(string.format(
    '  "central_x_entry_11a2": %d,\n', central_x_entry_11a2))
  handle:write(string.format(
    '  "central_x_entry_11a5": %d,\n', central_x_entry_11a5))
  handle:write(string.format('  "free_emitter_hits": %d,\n', free_emitter_hits))
  handle:write(string.format('  "tile_copy_hits": %d,\n', tile_copy_hits))
  handle:write(string.format(
    '  "stage7_fast_copy_hits": %d,\n', stage7_fast_copy_hits))
  handle:write(string.format(
    '  "stage7_fused_copy_hits": %d,\n', stage7_fused_copy_hits))
  handle:write(string.format(
    '  "postcopy_decisions": %d,\n', postcopy_decisions))
  handle:write(string.format(
    '  "postcopy_dirty_decisions": %d,\n', postcopy_dirty_decisions))
  handle:write(string.format(
    '  "postcopy_dirty_tile_copy_indices": [%s],\n',
    table.concat(postcopy_dirty_tile_copy_indices, ",")))
  handle:write(string.format(
    '  "compiler_tile_copy_indices": [%s],\n',
    table.concat(compiler_tile_copy_indices, ",")))
  handle:write(string.format('  "atomic_attr_passes": %d,\n', atomic_attr_passes))
  handle:write(string.format(
    '  "atomic_call_indices": [%s],\n',
    table.concat(atomic_call_indices, ",")))
  handle:write(string.format('  "attr_dma_commands": %d,\n', attr_dma_commands))
  handle:write(string.format('  "attr_gdma_commands": %d,\n', attr_gdma_commands))
  handle:write(string.format(
    '  "attr_hblank_commands": %d,\n', attr_hblank_commands))
  handle:write(string.format(
    '  "attr_invalid_dma_commands": %d,\n', attr_invalid_dma_commands))
  handle:write(string.format(
    '  "attr_dma_scene_violations": %d,\n', attr_dma_scene_violations))
  local dma_trace_parts = {}
  for _, record in ipairs(attr_dma_commands_trace) do
    dma_trace_parts[#dma_trace_parts + 1] = string.format('"%s"', record)
  end
  handle:write(string.format(
    '  "attr_dma_commands_trace": [%s],\n',
    table.concat(dma_trace_parts, ",")))
  local dma_site_parts = {}
  for _, address in ipairs(dma_command_addrs) do
    dma_site_parts[#dma_site_parts + 1] = string.format(
      '"0x%04X":%d', address, attr_dma_site_hits[address])
  end
  handle:write(string.format(
    '  "attr_dma_site_hits": {%s},\n', table.concat(dma_site_parts, ",")))
  handle:write(string.format('  "abi_enabled": %s,\n', tostring(abi_enabled)))
  handle:write(string.format('  "abi_entry_hits": %d,\n', abi_entry_hits))
  handle:write(string.format('  "abi_fallback_hits": %d,\n', abi_fallback_hits))
  handle:write(string.format(
    '  "abi_caller_reject_hits": %d,\n', abi_caller_reject_hits))
  handle:write(string.format(
    '  "abi_atomic_fallback_hits": %d,\n', abi_atomic_fallback_hits))
  handle:write(string.format('  "abi_exit_hits": %d,\n', abi_exit_hits))
  handle:write(string.format(
    '  "abi_fast_exit_hits": %d,\n', abi_fast_exit_hits))
  handle:write(string.format(
    '  "abi_native_exit_hits": %d,\n', abi_native_exit_hits))
  handle:write(string.format(
    '  "abi_native_exit_violations": %d,\n',
    abi_native_exit_violations))
  handle:write(string.format('  "abi_final_depth": %d,\n', abi_depth))
  handle:write(string.format('  "abi_violations": %d,\n', abi_violations))
  handle:write(string.format(
    '  "abi_timer_inside": %d,\n', abi_timer_inside))
  handle:write(string.format(
    '  "abi_timer_after_exit": %d,\n', abi_timer_after_exit))
  handle:write(string.format(
    '  "abi_timer_isr_pairs": %d,\n', abi_timer_isr_pairs))
  handle:write(string.format(
    '  "abi_timer_source_changes": %d,\n', abi_timer_source_changes))
  handle:write(string.format(
    '  "abi_timer_bank_state_changes": %d,\n',
    abi_timer_bank_state_changes))
  local abi_phase_parts = {}
  for _, address in ipairs(abi_phase_addrs) do
    abi_phase_parts[#abi_phase_parts + 1] = string.format(
      '"0x%04X":%d', address, abi_phase_hits[address])
  end
  handle:write(string.format(
    '  "abi_phase_hits": {%s},\n', table.concat(abi_phase_parts, ",")))
  local abi_outer_stack_parts, abi_outer_post_parts = {}, {}
  for address in pairs(abi_outer_returns) do
    abi_outer_stack_parts[#abi_outer_stack_parts + 1] = string.format(
      '"0x%04X":%d', address, abi_outer_stack_hits[address])
    abi_outer_post_parts[#abi_outer_post_parts + 1] = string.format(
      '"0x%04X":%d', address, abi_outer_post_hits[address])
  end
  table.sort(abi_outer_stack_parts)
  table.sort(abi_outer_post_parts)
  handle:write(string.format(
    '  "abi_outer_stack_hits": {%s},\n',
    table.concat(abi_outer_stack_parts, ",")))
  handle:write(string.format(
    '  "abi_outer_post_hits": {%s},\n',
    table.concat(abi_outer_post_parts, ",")))
  handle:write(string.format(
    '  "abi_pending_outer_return": %d,\n', abi_pending_outer_return or -1))
  local abi_fallback_parts = {}
  for _, sample in ipairs(abi_fallback_examples) do
    abi_fallback_parts[#abi_fallback_parts + 1] = string.format('"%s"', sample)
  end
  handle:write(string.format(
    '  "abi_fallback_examples": [%s],\n',
    table.concat(abi_fallback_parts, ",")))
  local abi_sample_parts = {}
  for _, sample in ipairs(abi_samples) do
    abi_sample_parts[#abi_sample_parts + 1] = string.format('"%s"', sample)
  end
  handle:write(string.format(
    '  "abi_samples": [%s],\n', table.concat(abi_sample_parts, ",")))
  local abi_violation_parts = {}
  for _, sample in ipairs(abi_violation_examples) do
    abi_violation_parts[#abi_violation_parts + 1] = string.format('"%s"', sample)
  end
  handle:write(string.format(
    '  "abi_violation_examples": [%s],\n',
    table.concat(abi_violation_parts, ",")))
  local trace_parts = {}
  for _, address in ipairs(trace_addrs) do
    trace_parts[#trace_parts + 1] = string.format(
      '"0x%04X":%d', address, trace_addr_hits[address])
  end
  handle:write(string.format(
    '  "trace_addr_hits": {%s},\n', table.concat(trace_parts, ",")))
  local trace_sample_parts = {}
  for _, address in ipairs(trace_addrs) do
    local samples = trace_addr_samples[address]
    local quoted = {}
    for _, sample in ipairs(samples) do
      quoted[#quoted + 1] = string.format('"%s"', sample)
    end
    trace_sample_parts[#trace_sample_parts + 1] = string.format(
      '"0x%04X":[%s]', address, table.concat(quoted, ","))
  end
  handle:write(string.format(
    '  "trace_addr_samples": {%s},\n', table.concat(trace_sample_parts, ",")))
  local readiness_parts = {}
  for _, address in ipairs(trace_addrs) do
    local samples = trace_readiness_samples[address]
    local quoted = {}
    for _, sample in ipairs(samples) do
      quoted[#quoted + 1] = string.format('"%s"', sample)
    end
    readiness_parts[#readiness_parts + 1] = string.format(
      '"0x%04X":[%s]', address, table.concat(quoted, ","))
  end
  handle:write(string.format(
    '  "trace_readiness_fields": ["frame","room","bg_sweep","map9800_cache","map9c00_cache","destination_latch","h","lcdc","vbk","row_temp","row_ready"],\n'))
  handle:write(string.format(
    '  "trace_readiness_samples": {%s},\n', table.concat(readiness_parts, ",")))
  local pc_keys, pc_parts = {}, {}
  for address in pairs(pc_sample_counts) do pc_keys[#pc_keys + 1] = address end
  table.sort(pc_keys)
  for _, address in ipairs(pc_keys) do
    pc_parts[#pc_parts + 1] = string.format(
      '"0x%04X":%d', address, pc_sample_counts[address])
  end
  handle:write(string.format(
    '  "pc_samples": {%s},\n', table.concat(pc_parts, ",")))
  local ff_parts = {}
  for _, record in ipairs(ff_scan_trace) do
    ff_parts[#ff_parts + 1] = string.format('"%s"', record)
  end
  handle:write(string.format('  "ff_scan_hits": %d,\n', ff_scan_hits))
  handle:write(string.format(
    '  "ff_scan_trace": [%s],\n', table.concat(ff_parts, ",")))
  local parser_parts = {}
  for _, record in ipairs(stage4_parser_trace) do
    parser_parts[#parser_parts + 1] = string.format('"%s"', record)
  end
  handle:write(string.format(
    '  "stage4_parser_trace": [%s],\n', table.concat(parser_parts, ",")))
  handle:write(string.format('  "lava_copy_hits": %d,\n', lava_copy_hits))
  handle:write(string.format('  "attr_map_changes": %d,\n', attr_map_changes))
  handle:write(string.format('  "attr_map_unchanged": %d,\n', attr_map_unchanged))
  handle:write(string.format('  "attr_changed_cells": %d,\n', attr_changed_cells))
  handle:write(string.format('  "attr_changed_groups": %d,\n', attr_changed_groups))
  handle:write(string.format(
    '  "max_attr_changed_cells": %d,\n', max_attr_changed_cells))
  handle:write(string.format(
    '  "max_attr_changed_groups": %d,\n', max_attr_changed_groups))
  handle:write(string.format('  "scroll_changes": %d,\n', scroll_changes))
  handle:write(string.format('  "active_frames": %d,\n', active_frames))
  handle:write(string.format(
    '  "first_inactive_frame": %d,\n', first_inactive_frame))
  handle:write(string.format(
    '  "first_inactive_state": "%s",\n', first_inactive_state))
  handle:write(string.format(
    '  "expected_scene_frames": %d,\n', expected_scene_frames))
  handle:write(string.format(
    '  "dma_unreadable_scene_samples": %d,\n',
    dma_unreadable_scene_samples))
  handle:write(string.format(
    '  "compiler_unreadable_scene_samples": %d,\n',
    compiler_unreadable_scene_samples))
  handle:write(string.format(
    '  "non_dma_scene_mismatch_frames": %d,\n',
    non_dma_scene_mismatch_frames))
  handle:write(string.format(
    '  "first_scene_mismatch": %d,\n', first_scene_mismatch))
  handle:write(string.format(
    '  "first_scene_mismatch_value": %d,\n', first_scene_mismatch_value))
  handle:write(string.format(
    '  "ffe4_zero_play_frames": %d,\n', ffe4_zero_play_frames))
  handle:write(string.format(
    '  "ffe4_nonzero_play_frames": %d,\n', ffe4_nonzero_play_frames))
  handle:write(string.format(
    '  "first_ffe4_nonzero_play_frame": %d,\n',
    first_ffe4_nonzero_play_frame))
  handle:write(string.format(
    '  "first_ffe4_nonzero_value": %d,\n', first_ffe4_nonzero_value))
  handle:write(string.format(
    '  "window_helper_hits": %d,\n', window_helper_hits))
  handle:write(string.format(
    '  "window_helper_ffe4_nonzero_hits": %d,\n',
    window_helper_ffe4_nonzero_hits))
  handle:write(string.format('  "mismatch_cpu_pc": %d,\n', mismatch_cpu_pc))
  handle:write(string.format(
    '  "mismatch_dma_source": %d,\n', mismatch_dma_source))
  handle:write(string.format('  "mismatch_svbk": %d,\n', mismatch_svbk))
  handle:write(string.format('  "room": %d,\n', emu:read8(0xFFBD)))
  handle:write(string.format('  "ffc1": %d,\n', emu:read8(0xFFC1)))
  handle:write(string.format('  "final_cpu_pc": %d,\n', read_register("PC")))
  handle:write(string.format('  "final_lcdc": %d,\n', emu:read8(0xFF40)))
  handle:write(string.format('  "final_stat": %d,\n', emu:read8(0xFF41)))
  handle:write(string.format('  "final_hdma5": %d,\n', emu:read8(0xFF55)))
  handle:write(string.format('  "final_svbk": %d,\n', emu:read8(0xFF70)))
  handle:write(string.format('  "final_vbk": %d,\n', emu:read8(0xFF4F)))
  handle:write(string.format(
    '  "metatile_state_captured": %s,\n', tostring(metatile_state ~= nil)))
  handle:write(string.format(
    '  "metatile_capture_svbk": %d,\n', metatile_capture_svbk))
  handle:write(string.format(
    '  "metatile_capture_source": %d,\n', metatile_capture_source))
  handle:write(string.format('  "final_ie": %d\n', emu:read8(0xFFFF)))
  handle:write("}\n")
  handle:close()
  if attr_trace then attr_trace:close(); attr_trace = nil end
  if lifecycle then lifecycle:close(); lifecycle = nil end
  if camera_trace then camera_trace:close(); camera_trace = nil end
  if pc_trace then pc_trace:close(); pc_trace = nil end
  if copy_trace then copy_trace:close(); copy_trace = nil end
  if loop_trace then loop_trace:close(); loop_trace = nil end
  if METATILE_DUMP then
    assert(metatile_state, "stock metatile expander was not captured")
    local dump = assert(io.open(METATILE_DUMP, "wb"))
    dump:write(metatile_state)
    dump:close()
    local grids = assert(io.open(METATILE_DUMP .. ".grids", "wb"))
    grids:write(table.concat(metatile_grids))
    grids:close()
  end
  local marker = assert(io.open(DONE, "w"))
  marker:write("OK")
  marker:close()
  emu:quit()
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if pc_trace and phase == "play" then
    local sampled_pc = emu:readRegister("PC") & 65535
    -- FF99 is a software bank shadow and can lag the mapped ROM. Record
    -- live bytes so analysis can reject shadow aliases, not assume identity.
    pc_trace:write(string.format("%d\t%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X%02X%02X\n",
      frame, play_frames, sampled_pc,
      emu:read8(0xFF99), assert(emu.memory.wram):read8(0x1880),
      emu:read8(0xFF70), emu:read8(0xFFC4),
      emu:read8(sampled_pc), emu:read8((sampled_pc + 1) & 65535),
      emu:read8((sampled_pc + 2) & 65535)))
    pc_trace:flush()
  end
  if camera_trace then
    local wram = assert(emu.memory.wram)
    camera_trace:write(string.format("%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",
      frame, phase, wram:read8(0x1880), emu:read8(0xFFBA),
      emu:read8(0xFFBD), emu:read8(0xFF43), emu:read8(0xFF42),
      wram:read8(0x1C00), wram:read8(0x1C02), emu:read8(0xFFC4),
      wram:read8(0x1F5C), emu:read8(0xFF40), emu:read8(0xFF97),
      main_loop_hits, tile_copy_hits, wram:read8(0x1CB8)))
  end
  emu:write8(0xDCFD, 0x01)
  if not seeded and frame >= 100 then seed_sram(); seeded = true end

  if lifecycle then
    local state = string.format(
      "%s:%02X:%02X:%02X:%02X", phase, emu:read8(0xD880),
      emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFBD))
    if state ~= previous_lifecycle or frame % 60 == 0 then
      lifecycle:write(string.format(
        "%d\t%s\t%04X\t%02X\t%02X\t%02X\t%02X"
          .. "\t%02X\t%02X\t%02X\t%02X\t%02X\n",
        frame, phase, read_register("PC") & 0xFFFF,
        emu:read8(0xD880), emu:read8(0xFFC1),
        emu:read8(0xFFBA), emu:read8(0xFFBD),
        emu:read8(0xDF02), emu:read8(0xDF08),
        emu:read8(0xDF4E), emu:read8(0xDF0D), emu:read8(0xFF91)))
      lifecycle:flush()
      previous_lifecycle = state
    end
  end

  if phase == "title" then
    if frame >= 300 and frame < 306 then emu:setKeys(KEY_START)
    elseif frame >= 360 and frame < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if frame >= 330 then phase = "level_select" end
    return
  end

  if phase == "level_select" and not confirmed then
    emu:write8(0xFFBA, TARGET)
    seed_sram()
    if frame % 60 >= 10 and frame % 60 < 16 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if emu:read8(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
      confirmed = true
      phase = "loading"
    end
    if frame > 900 then finish() end
    return
  end

  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)

  if phase == "loading" then
    emu:write8(0xFFBA, TARGET)
    emu:setKeys(0)
    local loading_scene, loading_compiler_unreadable = scene_sample()
    if (loading_scene == EXPECTED_SCENE or loading_compiler_unreadable)
        and emu:read8(0xFFC1) == 1 then
      stable_frames = stable_frames + 1
      if stable_frames >= 120 + SYNC_DELAY then
        if TARGET == 0 and STAGE1_DECIDER_MODE == "pure" then
          -- Diagnostic upper bound: keep all Stage-1 copies on the native-
          -- width tile-only route. Attribute correctness is intentionally
          -- out of scope for this isolation run.
          emu:write8(0xDAD7, 0xAF)         -- XOR A
          emu:write8(0xDAD8, 0xC9)         -- RET Z
        elseif TARGET == 0 and STAGE1_DECIDER_MODE == "dirty" then
          -- Opposite bound: force every Stage-1 source copy through the
          -- changed-layout publisher.
          emu:write8(0xDAD7, 0x3E)         -- LD A,$01
          emu:write8(0xDAD8, 0x01)
          emu:write8(0xDAD9, 0xB7)         -- OR A
          emu:write8(0xDADA, 0xC9)         -- RET NZ
        end
        phase = "sync"
      end
    else
      stable_frames = 0
    end
    if frame > 30000 then finish() end
    return
  end

  if phase == "sync" then
    emu:setKeys(0)
    if frame > 30000 then finish() end
    return
  end

  if phase == "drain" then
    -- Freeze the measured route and counters.  Only completion telemetry for
    -- the one helper already active at LIMIT is allowed to change here.
    safe_boundary_drain_frames = safe_boundary_drain_frames + 1
    emu:setKeys(0)
    if emu:read8(0xFFE4) ~= 0 then
      safe_boundary_drain_ffe4_nonzero_frames =
        safe_boundary_drain_ffe4_nonzero_frames + 1
    end
    local drain_scene, drain_unreadable = scene_sample()
    if not drain_unreadable and drain_scene ~= EXPECTED_SCENE then
      safe_boundary_drain_scene_violations =
        safe_boundary_drain_scene_violations + 1
    end
    if safe_boundary_extra_entries ~= 0 then
      safe_boundary_status = "extra-entry"
      finish()
    elseif safe_boundary_restored() and safe_boundary_post_hits > 0 then
      safe_boundary_status = "completed"
      finish()
    elseif safe_boundary_drain_frames >= SAFE_BOUNDARY_MAX_FRAMES then
      safe_boundary_status = "timeout"
      finish()
    end
    return
  end

  play_frames = play_frames + 1
  local sampled_ffe4 = emu:read8(0xFFE4)
  if sampled_ffe4 == 0 then
    ffe4_zero_play_frames = ffe4_zero_play_frames + 1
  else
    ffe4_nonzero_play_frames = ffe4_nonzero_play_frames + 1
    if first_ffe4_nonzero_play_frame < 0 then
      first_ffe4_nonzero_play_frame = play_frames
      first_ffe4_nonzero_value = sampled_ffe4
    end
  end
  local sampled_scene, compiler_unreadable, sampled_pc, sampled_svbk =
    scene_sample()
  local sampled_pc_key = sampled_pc & 0xFFFF
  pc_sample_counts[sampled_pc_key] = (pc_sample_counts[sampled_pc_key] or 0) + 1
  if sampled_scene == EXPECTED_SCENE or compiler_unreadable then
    expected_scene_frames = expected_scene_frames + 1
    if compiler_unreadable then
      compiler_unreadable_scene_samples =
        compiler_unreadable_scene_samples + 1
    end
  else
    local sampled_dma_source = emu:read8(0xFF46)
    local dma_unreadable = sampled_scene == 0xFF
      and sampled_pc >= 0xFF80 and sampled_pc <= 0xFF9F
      and (sampled_dma_source == 0xC0 or sampled_dma_source == 0xC1)
    if dma_unreadable then
      dma_unreadable_scene_samples = dma_unreadable_scene_samples + 1
    else
      non_dma_scene_mismatch_frames = non_dma_scene_mismatch_frames + 1
    end
    if first_scene_mismatch < 0 then
      first_scene_mismatch = play_frames
      first_scene_mismatch_value = sampled_scene
      mismatch_cpu_pc = sampled_pc
      mismatch_dma_source = sampled_dma_source
      mismatch_svbk = sampled_svbk
    end
  end
  if emu:read8(0xFFC1) == 1 then
    active_frames = active_frames + 1
  elseif first_inactive_frame < 0 then
    first_inactive_frame = play_frames
    first_inactive_state = string.format(
      "pc:%04X room:%02X scx:%02X scy:%02X ffe4:%02X " ..
        "dc00:%02X dc01:%02X dc02:%02X dc03:%02X",
      read_register("PC") & 0xFFFF, emu:read8(0xFFBD),
      emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xFFE4),
      emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC02), emu:read8(0xDC03))
    emu:screenshot(OUT .. ".first-inactive.png")
  end
  if INPUT_MODE == "loop-patrol" or INPUT_MODE == "loop-vertical-patrol" then
    -- The loop breakpoint owns these keys; a frame callback must not replace them.
  elseif INPUT_MODE == "stationary" then
    emu:setKeys(0)
  elseif INPUT_MODE == "left" then
    emu:setKeys(KEY_LEFT)
  elseif INPUT_MODE == "up" then
    emu:setKeys(KEY_UP)
  elseif INPUT_MODE == "down" then
    emu:setKeys(KEY_DOWN)
  elseif INPUT_MODE == "patrol" then
    if play_frames % 120 < 60 then emu:setKeys(KEY_RIGHT)
    else emu:setKeys(KEY_LEFT) end
  elseif INPUT_MODE == "vertical-patrol" then
    if play_frames % 120 < 60 then emu:setKeys(KEY_UP)
    else emu:setKeys(KEY_DOWN) end
  else
    emu:setKeys(KEY_RIGHT)
  end

  local scx = emu:read8(0xFF43)
  local scy = emu:read8(0xFF42)
  if scx ~= previous_scx or scy ~= previous_scy then
    scroll_changes = scroll_changes + 1
  end
  previous_scx = scx
  previous_scy = scy

  if SAFE_BOUNDARY_DRAIN and play_frames >= LIMIT then
    safe_boundary_measurement_complete = true
    safe_boundary_start_depth = abi_depth
    safe_boundary_start_pending_outer = abi_pending_outer_return or -1
    safe_boundary_start_ff55 = emu:read8(0xFF55)
    safe_boundary_start_vbk = emu:read8(0xFF4F) & 0x01
    safe_boundary_start_svbk = emu:read8(0xFF70) & 0x07
    safe_boundary_start_ie = emu:read8(0xFFFF)
    if not abi_enabled or SAFE_BOUNDARY_MAX_FRAMES <= 0 then
      safe_boundary_status = "configuration-error"
      finish()
    elseif safe_boundary_restored() then
      safe_boundary_status = "already-safe"
      finish()
    else
      safe_boundary_drain_required = true
      safe_boundary_status = "draining"
      phase = "drain"
    end
  -- An ordinary ABI smoke must never manufacture a false unbalanced-helper
  -- failure by stopping on a host callback in the middle of a multi-HBlank
  -- pass.  Keep its historical bounded drain behavior separate from the
  -- measurement-preserving finalizer above.
  elseif play_frames >= LIMIT and (not abi_enabled
      or (abi_depth == 0 and abi_pending_outer_return == nil)) then
    finish()
  elseif abi_enabled and play_frames >= LIMIT + 120 then
    finish()
  end
end)
