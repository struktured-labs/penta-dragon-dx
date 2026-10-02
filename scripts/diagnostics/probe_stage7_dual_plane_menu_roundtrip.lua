-- Candidate-bound Stage-7 SELECT-menu containment probe.
--
-- This probe is launched only by verify_stage7_dual_plane_menu_roundtrip.py
-- through the project single-flight wrapper.  It loads one exact r4a
-- publication state, observes a complete optimized helper before the menu,
-- opens and closes the native SELECT menu, then observes another complete
-- optimized helper and saves the post-publication machine state at $1302.
-- Python is the authority for both physical VRAM banks in that final state.

local OUT = assert(os.getenv("STAGE7_MENU_OUT"), "STAGE7_MENU_OUT required")
local STATE_FILE = assert(
  os.getenv("STAGE7_MENU_STATE"), "STAGE7_MENU_STATE required")
local FINAL_STATE = assert(
  os.getenv("STAGE7_MENU_FINAL_STATE"), "STAGE7_MENU_FINAL_STATE required")
local LIMIT = tonumber(os.getenv("STAGE7_MENU_FRAMES") or "1800")
local MENU_HOLD = tonumber(os.getenv("STAGE7_MENU_HOLD") or "80")

local KEY_A = 0x01
local KEY_SELECT = 0x04
local KEY_RIGHT, KEY_LEFT = 0x10, 0x20
local KEY_UP, KEY_DOWN = 0x40, 0x80

local HELPER_BANK = 0x16
local HELPER_ENTRY = 0x6C80
local FASTPATH_START = 0x6CE8
local ATTR_DMA_STORE = 0x713D
local TILE_DMA_STORE = 0x7187
local EXACT_EXIT = 0x436D
local OUTER_RETURN = 0x12E0
local POST_PUBLISH = 0x1302
local FALLBACK_NATIVE = 0x71B3
local CALLER_REJECT = 0x71BD
local ATOMIC_FALLBACK = 0x71C1

local raw_vram = assert(emu.memory.vram)
local frame = 0
local state_loaded = false
local finished = false
local phase = "load"
local phase_frame = 0
local helper_depth = 0
local fastpath_active = false
local current_helper_period = "none"
local current_helper_target = 0
local current_attr_commands = 0
local current_tile_commands = 0
local pre_complete = false
local post_complete = false
local await_post_outer = false
local post_outer_seen = false
local menu_seen = false
local menu_closed = false
local menu_visible_frames = 0
local menu_owned_frames = 0
local menu_hold_frames = 0
local select_open_frames = 0
local select_close_frames = 0
local ffc1_non1_frames = 0
local window_mismatch_cells = 0
local window_mismatch_frames = 0
local worst_window_mismatches = 0
local window_geometry_mismatch_frames = 0
local map_alias_frames = 0
local ffe4_nonzero_frames = 0
local helper_active_menu_owned_frames = 0
local menu_hardware_mismatch_frames = 0
local menu_ff55_nonidle_frames = 0
local menu_vbk_nonzero_frames = 0
local menu_svbk_non1_frames = 0
local menu_ie_non07_frames = 0
local helper_entries_pre = 0
local helper_entries_post = 0
local helper_entries_menu_owned = 0
local helper_entries_window_visible = 0
local helper_exits_menu_owned = 0
local fastpath_hits_pre = 0
local fastpath_hits_post = 0
local fastpath_hits_menu_owned = 0
local fastpath_visible_target_hits = 0
local helper_exits_pre = 0
local helper_exits_post = 0
local attr_dma_pre = 0
local attr_dma_post = 0
local tile_dma_pre = 0
local tile_dma_post = 0
local dma_menu_owned = 0
local dma_window_visible = 0
local invalid_dma_commands = 0
local helper_command_shape_violations = 0
local abi_violations = 0
local scene_violations = 0
local breakpoint_failures = 0
local watchpoint_failures = 0
local fallback_native_hits = 0
local caller_reject_hits = 0
local atomic_fallback_hits = 0
local pre_snapshot_ok = false
local pre_snapshot_active_base = 0
local pre_snapshot_refreshes = 0
local pre_snapshot_semantic_mismatch_cells = 0
local pre_snapshot_semantic_checked_cells = 0
local pre_snapshot_tiles = {[0x9800] = {}, [0x9C00] = {}}
local pre_snapshot_attrs = {[0x9800] = {}, [0x9C00] = {}}
local intervening_visible_frames = 0
local intervening_base_9800_frames = 0
local intervening_base_9c00_frames = 0
local intervening_tile_mismatch_frames = 0
local intervening_tile_mismatch_cells = 0
local intervening_attr_checked_frames = 0
local intervening_attr_unchecked_helper_frames = 0
local intervening_attr_ppu_blocked_frames = 0
local intervening_attr_unjustified_frames = 0
local intervening_attr_mismatch_frames = 0
local intervening_attr_mismatch_cells = 0
local intervening_semantic_attr_mismatch_frames = 0
local intervening_semantic_attr_mismatch_cells = 0
local intervening_visible_map_write_events = 0
local intervening_visible_map_write_examples = {}
local state_save_ok = false
local state_save_request_ok = false
local state_save_pending = false
local state_save_wait_frames = 0
local state_save_stable_frames = 0
local state_save_last_size = -1
local final_hardware_snapshot = ""
local stage7_lut_write_events = 0
local first_window_mismatch = "none"
local first_alias = "none"
local transition_log = {}
local last_transition = ""

local function read_register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and type(value) == "number" then return value end
  ok, value = pcall(function() return emu:getRegister(name) end)
  if ok and type(value) == "number" then return value end
  return 0
end

local function window_visible()
  local lcdc = emu:read8(0xFF40)
  return (lcdc & 0x20) ~= 0 and emu:read8(0xFF4A) < 144
end

local function menu_owned()
  return emu:read8(0xFFE4) ~= 0 or window_visible()
end

local function window_map(lcdc)
  return (lcdc & 0x40) ~= 0 and 0x9C00 or 0x9800
end

local function bg_map(lcdc)
  return (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
end

local function vram_cpu_readable()
  return (emu:read8(0xFF40) & 0x80) == 0
    or (emu:read8(0xFF41) & 3) <= 1
end

local function exact_window_mismatches(base)
  local mismatches = 0
  for row = 0, 5 do
    for col = 0, 19 do
      local expected = emu:read8(0xC4E0 + row * 20 + col)
      local actual = raw_vram:read8(base - 0x8000 + row * 32 + col)
      if actual ~= expected then mismatches = mismatches + 1 end
    end
  end
  return mismatches
end

local function visible_map_cell(address, base)
  if address < base or address >= base + 0x400 then return false end
  local index = address - base
  local row, col = math.floor(index / 32), index & 31
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
  local cols = ((scx & 7) == 0) and 20 or 21
  local rows = ((scy & 7) == 0) and 18 or 19
  local col_visible, row_visible = false, false
  for offset = 0, cols - 1 do
    if ((first_col + offset) & 31) == col then col_visible = true end
  end
  for offset = 0, rows - 1 do
    if ((first_row + offset) & 31) == row then row_visible = true end
  end
  return col_visible and row_visible
end

local function dump_snapshot(path, values)
  local handle = assert(io.open(path, "wb"))
  for index = 0, 0x3FF do handle:write(string.char(values[index])) end
  handle:close()
end

local function capture_pre_snapshot()
  if helper_depth ~= 0 or menu_owned() or window_visible()
      or emu:read8(0xFF55) ~= 0xFF or (emu:read8(0xFF4F) & 1) ~= 0
      or (emu:read8(0xFF70) & 7) ~= 1 or emu:read8(0xFFFF) ~= 0x07
      or not vram_cpu_readable() then
    return false
  end
  pre_snapshot_active_base = bg_map(emu:read8(0xFF40))
  for _, base in ipairs({0x9800, 0x9C00}) do
    for index = 0, 0x3FF do
      pre_snapshot_tiles[base][index] = raw_vram:read8(
        base - 0x8000 + index)
    end
  end
  emu:write8(0xFF4F, 1)
  for _, base in ipairs({0x9800, 0x9C00}) do
    for index = 0, 0x3FF do
      pre_snapshot_attrs[base][index] = emu:read8(base + index)
    end
  end
  emu:write8(0xFF4F, 0)
  if (emu:read8(0xFF4F) & 1) ~= 0 then return false end
  for _, base in ipairs({0x9800, 0x9C00}) do
    for row = 0, 19 do
      for col = 0, 23 do
        local index = row * 32 + col
        pre_snapshot_semantic_checked_cells =
          pre_snapshot_semantic_checked_cells + 1
        local tile = pre_snapshot_tiles[base][index]
        if pre_snapshot_attrs[base][index] ~= emu:read8(0xC600 + tile) then
          pre_snapshot_semantic_mismatch_cells =
            pre_snapshot_semantic_mismatch_cells + 1
        end
      end
    end
  end
  dump_snapshot(OUT .. ".pre.9800.tiles.bin", pre_snapshot_tiles[0x9800])
  dump_snapshot(OUT .. ".pre.9800.attrs.bin", pre_snapshot_attrs[0x9800])
  dump_snapshot(OUT .. ".pre.9c00.tiles.bin", pre_snapshot_tiles[0x9C00])
  dump_snapshot(OUT .. ".pre.9c00.attrs.bin", pre_snapshot_attrs[0x9C00])
  pre_snapshot_ok = true
  pre_snapshot_refreshes = pre_snapshot_refreshes + 1
  return true
end

local function compare_intervening_visible_frame()
  if not pre_snapshot_ok then return end
  intervening_visible_frames = intervening_visible_frames + 1
  local current_base = bg_map(emu:read8(0xFF40))
  if current_base == 0x9800 then
    intervening_base_9800_frames = intervening_base_9800_frames + 1
  else
    intervening_base_9c00_frames = intervening_base_9c00_frames + 1
  end
  local expected_tiles = pre_snapshot_tiles[current_base]
  local expected_attrs = pre_snapshot_attrs[current_base]
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
  local cols = ((scx & 7) == 0) and 20 or 21
  local rows = ((scy & 7) == 0) and 18 or 19
  local tile_mismatches = 0
  for y = 0, rows - 1 do
    for x = 0, cols - 1 do
      local row = (first_row + y) & 31
      local col = (first_col + x) & 31
      local index = row * 32 + col
      local tile = raw_vram:read8(current_base - 0x8000 + index)
      if tile ~= expected_tiles[index] then
        tile_mismatches = tile_mismatches + 1
      end
    end
  end
  if tile_mismatches > 0 then
    intervening_tile_mismatch_frames = intervening_tile_mismatch_frames + 1
    intervening_tile_mismatch_cells =
      intervening_tile_mismatch_cells + tile_mismatches
  end
  -- Explicit CPU VBK reads are safe only at an exact idle/restored boundary.
  -- Active helper frames remain covered by the zero-visible-write watchpoint
  -- and the immutable hidden-target proof in the candidate static receipt.
  if emu:read8(0xFF55) == 0xFF and (emu:read8(0xFF4F) & 1) == 0
      and (emu:read8(0xFF70) & 7) == 1 and vram_cpu_readable() then
    intervening_attr_checked_frames = intervening_attr_checked_frames + 1
    local attr_mismatches = 0
    local semantic_mismatches = 0
    emu:write8(0xFF4F, 1)
    for y = 0, rows - 1 do
      for x = 0, cols - 1 do
        local row = (first_row + y) & 31
        local col = (first_col + x) & 31
        local index = row * 32 + col
        local actual_attr = emu:read8(current_base + index)
        local tile = raw_vram:read8(current_base - 0x8000 + index)
        if actual_attr ~= expected_attrs[index] then
          attr_mismatches = attr_mismatches + 1
        end
        if actual_attr ~= emu:read8(0xC600 + tile) then
          semantic_mismatches = semantic_mismatches + 1
        end
      end
    end
    emu:write8(0xFF4F, 0)
    if attr_mismatches > 0 then
      intervening_attr_mismatch_frames =
        intervening_attr_mismatch_frames + 1
      intervening_attr_mismatch_cells =
        intervening_attr_mismatch_cells + attr_mismatches
    end
    if semantic_mismatches > 0 then
      intervening_semantic_attr_mismatch_frames =
        intervening_semantic_attr_mismatch_frames + 1
      intervening_semantic_attr_mismatch_cells =
        intervening_semantic_attr_mismatch_cells + semantic_mismatches
    end
  elseif helper_depth == 1 and fastpath_active
      and current_helper_target ~= current_base then
    intervening_attr_unchecked_helper_frames =
      intervening_attr_unchecked_helper_frames + 1
  elseif not vram_cpu_readable() then
    intervening_attr_ppu_blocked_frames =
      intervening_attr_ppu_blocked_frames + 1
  else
    intervening_attr_unjustified_frames =
      intervening_attr_unjustified_frames + 1
  end
end

local function record_transition()
  local text = string.format(
    "f%d:%s:e%02X:c%02X:l%02X:w%02X:y%02X", frame, phase,
    emu:read8(0xFFE4), emu:read8(0xFFC1), emu:read8(0xFF40),
    emu:read8(0xFF4B), emu:read8(0xFF4A))
  local stable = string.format(
    "%s:%02X:%02X:%02X:%02X:%02X", phase, emu:read8(0xFFE4),
    emu:read8(0xFFC1), emu:read8(0xFF40), emu:read8(0xFF4B),
    emu:read8(0xFF4A))
  if stable ~= last_transition and #transition_log < 96 then
    transition_log[#transition_log + 1] = text
    last_transition = stable
  end
end

local function write_report(status, reason)
  local handle = assert(io.open(OUT, "w"))
  handle:write("status=" .. status .. "\n")
  handle:write("reason=" .. reason .. "\n")
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("state_loaded=%d\n", state_loaded and 1 or 0))
  handle:write(string.format("breakpoint_failures=%d\n", breakpoint_failures))
  handle:write(string.format("menu_seen=%d\n", menu_seen and 1 or 0))
  handle:write(string.format("menu_closed=%d\n", menu_closed and 1 or 0))
  handle:write(string.format("menu_visible_frames=%d\n", menu_visible_frames))
  handle:write(string.format("menu_owned_frames=%d\n", menu_owned_frames))
  handle:write(string.format("select_open_frames=%d\n", select_open_frames))
  handle:write(string.format("select_close_frames=%d\n", select_close_frames))
  handle:write(string.format("ffc1_non1_frames=%d\n", ffc1_non1_frames))
  handle:write(string.format("ffe4_nonzero_frames=%d\n", ffe4_nonzero_frames))
  handle:write(string.format(
    "window_mismatch_cells=%d\n", window_mismatch_cells))
  handle:write(string.format(
    "window_mismatch_frames=%d\n", window_mismatch_frames))
  handle:write(string.format(
    "worst_window_mismatches=%d\n", worst_window_mismatches))
  handle:write(string.format(
    "window_geometry_mismatch_frames=%d\n",
    window_geometry_mismatch_frames))
  handle:write(string.format("map_alias_frames=%d\n", map_alias_frames))
  handle:write(string.format(
    "helper_active_menu_owned_frames=%d\n",
    helper_active_menu_owned_frames))
  handle:write(string.format(
    "menu_hardware_mismatch_frames=%d\n", menu_hardware_mismatch_frames))
  handle:write(string.format(
    "menu_ff55_nonidle_frames=%d\n", menu_ff55_nonidle_frames))
  handle:write(string.format(
    "menu_vbk_nonzero_frames=%d\n", menu_vbk_nonzero_frames))
  handle:write(string.format(
    "menu_svbk_non1_frames=%d\n", menu_svbk_non1_frames))
  handle:write(string.format(
    "menu_ie_non07_frames=%d\n", menu_ie_non07_frames))
  handle:write("first_window_mismatch=" .. first_window_mismatch .. "\n")
  handle:write("first_alias=" .. first_alias .. "\n")
  handle:write(string.format("helper_entries_pre=%d\n", helper_entries_pre))
  handle:write(string.format("helper_entries_post=%d\n", helper_entries_post))
  handle:write(string.format(
    "helper_entries_menu_owned=%d\n", helper_entries_menu_owned))
  handle:write(string.format(
    "helper_entries_window_visible=%d\n", helper_entries_window_visible))
  handle:write(string.format(
    "helper_exits_menu_owned=%d\n", helper_exits_menu_owned))
  handle:write(string.format("fastpath_hits_pre=%d\n", fastpath_hits_pre))
  handle:write(string.format("fastpath_hits_post=%d\n", fastpath_hits_post))
  handle:write(string.format(
    "fastpath_hits_menu_owned=%d\n", fastpath_hits_menu_owned))
  handle:write(string.format(
    "fastpath_visible_target_hits=%d\n", fastpath_visible_target_hits))
  handle:write(string.format("helper_exits_pre=%d\n", helper_exits_pre))
  handle:write(string.format("helper_exits_post=%d\n", helper_exits_post))
  handle:write(string.format("attr_dma_pre=%d\n", attr_dma_pre))
  handle:write(string.format("attr_dma_post=%d\n", attr_dma_post))
  handle:write(string.format("tile_dma_pre=%d\n", tile_dma_pre))
  handle:write(string.format("tile_dma_post=%d\n", tile_dma_post))
  handle:write(string.format("dma_menu_owned=%d\n", dma_menu_owned))
  handle:write(string.format("dma_window_visible=%d\n", dma_window_visible))
  handle:write(string.format("invalid_dma_commands=%d\n", invalid_dma_commands))
  handle:write(string.format(
    "helper_command_shape_violations=%d\n", helper_command_shape_violations))
  handle:write(string.format("abi_violations=%d\n", abi_violations))
  handle:write(string.format("scene_violations=%d\n", scene_violations))
  handle:write(string.format("watchpoint_failures=%d\n", watchpoint_failures))
  handle:write(string.format("fallback_native_hits=%d\n", fallback_native_hits))
  handle:write(string.format("caller_reject_hits=%d\n", caller_reject_hits))
  handle:write(string.format("atomic_fallback_hits=%d\n", atomic_fallback_hits))
  handle:write(string.format("pre_snapshot_ok=%d\n", pre_snapshot_ok and 1 or 0))
  handle:write(string.format(
    "pre_snapshot_active_base=%04X\n", pre_snapshot_active_base))
  handle:write(string.format(
    "pre_snapshot_refreshes=%d\n", pre_snapshot_refreshes))
  handle:write(string.format(
    "pre_snapshot_semantic_mismatch_cells=%d\n",
    pre_snapshot_semantic_mismatch_cells))
  handle:write(string.format(
    "pre_snapshot_semantic_checked_cells=%d\n",
    pre_snapshot_semantic_checked_cells))
  handle:write(string.format(
    "intervening_visible_frames=%d\n", intervening_visible_frames))
  handle:write(string.format(
    "intervening_base_9800_frames=%d\n", intervening_base_9800_frames))
  handle:write(string.format(
    "intervening_base_9c00_frames=%d\n", intervening_base_9c00_frames))
  handle:write(string.format(
    "intervening_tile_mismatch_frames=%d\n",
    intervening_tile_mismatch_frames))
  handle:write(string.format(
    "intervening_tile_mismatch_cells=%d\n",
    intervening_tile_mismatch_cells))
  handle:write(string.format(
    "intervening_attr_checked_frames=%d\n",
    intervening_attr_checked_frames))
  handle:write(string.format(
    "intervening_attr_unchecked_helper_frames=%d\n",
    intervening_attr_unchecked_helper_frames))
  handle:write(string.format(
    "intervening_attr_ppu_blocked_frames=%d\n",
    intervening_attr_ppu_blocked_frames))
  handle:write(string.format(
    "intervening_attr_unjustified_frames=%d\n",
    intervening_attr_unjustified_frames))
  handle:write(string.format(
    "intervening_attr_mismatch_frames=%d\n",
    intervening_attr_mismatch_frames))
  handle:write(string.format(
    "intervening_attr_mismatch_cells=%d\n",
    intervening_attr_mismatch_cells))
  handle:write(string.format(
    "intervening_semantic_attr_mismatch_frames=%d\n",
    intervening_semantic_attr_mismatch_frames))
  handle:write(string.format(
    "intervening_semantic_attr_mismatch_cells=%d\n",
    intervening_semantic_attr_mismatch_cells))
  handle:write(string.format(
    "intervening_visible_map_write_events=%d\n",
    intervening_visible_map_write_events))
  handle:write("intervening_visible_map_write_examples=" ..
    table.concat(intervening_visible_map_write_examples, ";") .. "\n")
  handle:write(string.format(
    "stage7_lut_write_events=%d\n", stage7_lut_write_events))
  handle:write(string.format(
    "state_save_request_ok=%d\n", state_save_request_ok and 1 or 0))
  handle:write(string.format("state_save_ok=%d\n", state_save_ok and 1 or 0))
  handle:write(string.format(
    "state_save_wait_frames=%d\n", state_save_wait_frames))
  handle:write(string.format(
    "state_save_stable_frames=%d\n", state_save_stable_frames))
  local hardware = final_hardware_snapshot
  if hardware == "" then
    hardware = string.format(
      "ff55:%02X,vbk:%02X,svbk:%02X,ie:%02X,ffc1:%02X," ..
      "ffe4:%02X,lcdc:%02X,scene:%02X,stage:%02X,room:%02X",
      emu:read8(0xFF55), emu:read8(0xFF4F) & 1,
      emu:read8(0xFF70) & 7, emu:read8(0xFFFF), emu:read8(0xFFC1),
      emu:read8(0xFFE4), emu:read8(0xFF40), emu:read8(0xD880),
      emu:read8(0xFFBA), emu:read8(0xFFBD))
  end
  handle:write("final_hardware=" .. hardware .. "\n")
  handle:write("transitions=" .. table.concat(transition_log, ";") .. "\n")
  handle:close()
end

local function finish(status, reason)
  if finished then return end
  finished = true
  emu:setKeys(0)
  write_report(status, reason)
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

local function complete_final_state_size()
  local handle = io.open(FINAL_STATE, "rb")
  if not handle then return nil end
  local size = handle:seek("end")
  if not size or size < 1024 then handle:close(); return nil end
  handle:seek("set", size - 12)
  local tail = handle:read(12)
  handle:close()
  if not tail or #tail ~= 12 or tail:sub(5, 8) ~= "IEND" then return nil end
  return size
end

local function install(address, callback)
  local ok = pcall(function()
    emu:setBreakpoint(callback, address)
  end)
  if not ok then
    breakpoint_failures = breakpoint_failures + 1
  end
end

install(HELPER_ENTRY, function()
  if not state_loaded or state_save_pending
      or emu:read8(0xFF99) ~= HELPER_BANK then return end
  if helper_depth ~= 0 then abi_violations = abi_violations + 1 end
  helper_depth = helper_depth + 1
  fastpath_active = false
  current_helper_target = read_register("HL") & 0xFFFF
  current_attr_commands = 0
  current_tile_commands = 0
  -- Classify by native display ownership, not the host-frame phase.  Menu
  -- close can restore FFC1/Window and enter the helper before the next frame
  -- callback observes that transition.
  if not menu_seen then
    current_helper_period = "pre"
    helper_entries_pre = helper_entries_pre + 1
  elseif not menu_owned() then
    current_helper_period = "post"
    helper_entries_post = helper_entries_post + 1
  else
    current_helper_period = "menu"
  end
  if menu_owned() then
    helper_entries_menu_owned = helper_entries_menu_owned + 1
  end
  if window_visible() then
    helper_entries_window_visible = helper_entries_window_visible + 1
  end
  if emu:read8(0xFF70) & 7 ~= 1 or emu:read8(0xFF4F) & 1 ~= 0
      or emu:read8(0xFF55) ~= 0xFF or emu:read8(0xFFFF) ~= 0x07 then
    abi_violations = abi_violations + 1
  end
end)

install(FASTPATH_START, function()
  if not state_loaded or state_save_pending
      or emu:read8(0xFF99) ~= HELPER_BANK then return end
  if helper_depth ~= 1 or fastpath_active then
    abi_violations = abi_violations + 1
  end
  fastpath_active = true
  if current_helper_target ~= 0x9800 and current_helper_target ~= 0x9C00 then
    abi_violations = abi_violations + 1
  elseif (emu:read8(0xFF40) & 0x80) ~= 0
      and current_helper_target == bg_map(emu:read8(0xFF40)) then
    fastpath_visible_target_hits = fastpath_visible_target_hits + 1
  end
  if current_helper_period == "pre" then
    fastpath_hits_pre = fastpath_hits_pre + 1
  elseif current_helper_period == "post" then
    fastpath_hits_post = fastpath_hits_post + 1
  end
  if menu_owned() then
    fastpath_hits_menu_owned = fastpath_hits_menu_owned + 1
  end
end)

local function dma_store(kind)
  if not state_loaded or state_save_pending
      or emu:read8(0xFF99) ~= HELPER_BANK then return end
  if helper_depth ~= 1 or not fastpath_active then
    abi_violations = abi_violations + 1
  end
  local command = read_register("A") & 0xFF
  local lcd_on = (emu:read8(0xFF40) & 0x80) ~= 0
  local expected
  if kind == "attr" then
    expected = lcd_on and 0xA7 or 0x27
    current_attr_commands = current_attr_commands + 1
    if current_helper_period == "pre" then attr_dma_pre = attr_dma_pre + 1
    elseif current_helper_period == "post" then attr_dma_post = attr_dma_post + 1 end
    if (emu:read8(0xFF4F) & 1) ~= 1 or (emu:read8(0xFF70) & 7) ~= 3 then
      abi_violations = abi_violations + 1
    end
  else
    expected = lcd_on and 0x81 or 0x01
    current_tile_commands = current_tile_commands + 1
    if current_helper_period == "pre" then tile_dma_pre = tile_dma_pre + 1
    elseif current_helper_period == "post" then tile_dma_post = tile_dma_post + 1 end
    if (emu:read8(0xFF4F) & 1) ~= 0 or (emu:read8(0xFF70) & 7) ~= 2 then
      abi_violations = abi_violations + 1
    end
  end
  if command ~= expected or emu:read8(0xFF55) ~= 0xFF then
    invalid_dma_commands = invalid_dma_commands + 1
  end
  if menu_owned() then dma_menu_owned = dma_menu_owned + 1 end
  if window_visible() then dma_window_visible = dma_window_visible + 1 end
end

install(ATTR_DMA_STORE, function() dma_store("attr") end)
install(TILE_DMA_STORE, function() dma_store("tile") end)

install(EXACT_EXIT, function()
  if not state_loaded or state_save_pending or helper_depth == 0 then return end
  if menu_owned() then helper_exits_menu_owned = helper_exits_menu_owned + 1 end
  if helper_depth ~= 1 then abi_violations = abi_violations + 1 end
  if fastpath_active
      and (current_attr_commands ~= 1 or current_tile_commands ~= 20) then
    helper_command_shape_violations = helper_command_shape_violations + 1
  end
  local af = ((read_register("A") & 0xFF) << 8)
    | (read_register("F") & 0xF0)
  local bc = ((read_register("B") & 0xFF) << 8)
    | (read_register("C") & 0xFF)
  local de = ((read_register("D") & 0xFF) << 8)
    | (read_register("E") & 0xFF)
  local hl = read_register("HL") & 0xFFFF
  if emu:read8(0xFF55) ~= 0xFF or emu:read8(0xFF4F) & 1 ~= 0
      or emu:read8(0xFF70) & 7 ~= 1 or emu:read8(0xFFFF) ~= 0x07
      or af ~= 0x01C0 or bc ~= 0x084D or de ~= 0xC3E0
      or (hl ~= 0x9800 and hl ~= 0x9C00)
      or emu:read8(0xFFA5) ~= 0 or emu:read8(0xFFE0) ~= 0 then
    abi_violations = abi_violations + 1
  end
  local completed_period = current_helper_period
  if completed_period == "pre" then
    helper_exits_pre = helper_exits_pre + 1
    if fastpath_active then pre_complete = true end
  elseif completed_period == "post" then
    helper_exits_post = helper_exits_post + 1
    if fastpath_active then
      post_complete = true
      await_post_outer = true
    end
  end
  helper_depth = 0
  fastpath_active = false
  current_helper_period = "none"
  current_helper_target = 0
  -- The open phase can execute one last ordinary gameplay publication before
  -- FFE4/Window takes ownership.  Refresh both physical-map authorities at
  -- every exact pre-menu helper exit so the close audit cannot compare
  -- against a stale inactive page.
  if completed_period == "pre" and (phase == "pre" or phase == "open")
      and not menu_owned() and vram_cpu_readable()
      and not capture_pre_snapshot() then
    abi_violations = abi_violations + 1
  end
end)

install(OUTER_RETURN, function()
  if not state_loaded or state_save_pending or phase ~= "post"
      or not await_post_outer then return end
  post_outer_seen = true
end)

install(POST_PUBLISH, function()
  if not state_loaded or state_save_pending or phase ~= "post" or not post_complete
      or not post_outer_seen or helper_depth ~= 0 then return end
  final_hardware_snapshot = string.format(
    "ff55:%02X,vbk:%02X,svbk:%02X,ie:%02X,ffc1:%02X," ..
    "ffe4:%02X,lcdc:%02X,scene:%02X,stage:%02X,room:%02X",
    emu:read8(0xFF55), emu:read8(0xFF4F) & 1,
    emu:read8(0xFF70) & 7, emu:read8(0xFFFF), emu:read8(0xFFC1),
    emu:read8(0xFFE4), emu:read8(0xFF40), emu:read8(0xD880),
    emu:read8(0xFFBA), emu:read8(0xFFBD))
  local ok, result = pcall(function()
    return emu:saveStateFile(FINAL_STATE)
  end)
  state_save_request_ok = ok and result ~= false
  if not state_save_request_ok then
    finish("fail", "final-state-save-request-failed")
    return
  end
  state_save_pending = true
  phase = "save"
  emu:setKeys(0)
end)

local function fallback_hit(kind)
  if not state_loaded or state_save_pending
      or emu:read8(0xFF99) ~= HELPER_BANK then return end
  if kind == "native" then fallback_native_hits = fallback_native_hits + 1
  elseif kind == "caller" then caller_reject_hits = caller_reject_hits + 1
  else atomic_fallback_hits = atomic_fallback_hits + 1 end
end

install(FALLBACK_NATIVE, function() fallback_hit("native") end)
install(CALLER_REJECT, function() fallback_hit("caller") end)
install(ATOMIC_FALLBACK, function() fallback_hit("atomic") end)

do
  local ok, result = pcall(function()
    return emu:setRangeWatchpoint(function(info)
      if not state_loaded or state_save_pending or not menu_seen or menu_owned()
          or post_outer_seen or not pre_snapshot_ok then return end
      local address = info.address & 0xFFFF
      local base = bg_map(emu:read8(0xFF40))
      if not visible_map_cell(address, base) then
        return
      end
      intervening_visible_map_write_events =
        intervening_visible_map_write_events + 1
      if #intervening_visible_map_write_examples < 32 then
        intervening_visible_map_write_examples[
          #intervening_visible_map_write_examples + 1] = string.format(
          "f%d:%04X:%02X>%02X:v%d:p%04X", frame, address,
          (info.oldValue or 0) & 0xFF, info.value & 0xFF,
          emu:read8(0xFF4F) & 1, read_register("PC") & 0xFFFF)
      end
    end, 0x9800, 0x9FFF, C.WATCHPOINT_TYPE.WRITE_CHANGE)
  end)
  if not ok or type(result) ~= "number" or result <= 0 then
    watchpoint_failures = watchpoint_failures + 1
  end
end

do
  local ok, result = pcall(function()
    return emu:setRangeWatchpoint(function()
      if state_loaded and not state_save_pending then
        stage7_lut_write_events = stage7_lut_write_events + 1
      end
    end, 0xC600, 0xC6FF, C.WATCHPOINT_TYPE.WRITE_CHANGE)
  end)
  if not ok or type(result) ~= "number" or result <= 0 then
    watchpoint_failures = watchpoint_failures + 1
  end
end

local function patrol_keys()
  local cycle = frame % 120
  if cycle < 20 then return KEY_A | KEY_UP end
  if cycle < 40 then return KEY_A | KEY_DOWN end
  if cycle < 60 then return KEY_A | KEY_LEFT end
  return KEY_A | KEY_RIGHT
end

callbacks:add("frame", function()
  if finished then return end
  if not state_loaded then
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_FILE)
    end)
    if not ok or result == false then
      finish("fail", "state-load-failed")
      return
    end
    state_loaded = true
    phase = "pre"
    phase_frame = 0
    emu:setKeys(0)
    record_transition()
    return
  end

  -- mGBA can return from saveStateFile before the PNG stream is fully
  -- flushed.  Keep the emulator alive, with observation frozen and no input,
  -- until two consecutive frame callbacks see the same complete IEND-sized
  -- file.  Python independently parses CRCs/gbAs and checks file stability
  -- before terminating this exact launcher child.
  if state_save_pending then
    emu:setKeys(0)
    state_save_wait_frames = state_save_wait_frames + 1
    local size = complete_final_state_size()
    if size and size == state_save_last_size then
      state_save_stable_frames = state_save_stable_frames + 1
    elseif size then
      state_save_last_size = size
      state_save_stable_frames = 1
    else
      state_save_stable_frames = 0
    end
    if state_save_stable_frames >= 2 then
      state_save_ok = true
      state_save_pending = false
      finish("ok", "complete")
    elseif state_save_wait_frames > 120 then
      state_save_pending = false
      finish("fail", "final-state-save-not-stable")
    end
    return
  end

  frame = frame + 1
  phase_frame = phase_frame + 1
  if (emu:read8(0xFF70) & 7) == 1
      and (emu:read8(0xD880) ~= 0x08 or emu:read8(0xFFBA) ~= 0x06) then
    scene_violations = scene_violations + 1
  end

  local visible = window_visible()
  local owned = menu_owned()
  if emu:read8(0xFFC1) ~= 1 then
    ffc1_non1_frames = ffc1_non1_frames + 1
  end
  if emu:read8(0xFFE4) ~= 0 then
    ffe4_nonzero_frames = ffe4_nonzero_frames + 1
  end
  if owned then menu_owned_frames = menu_owned_frames + 1 end
  if owned or visible then
    if helper_depth ~= 0 or fastpath_active then
      helper_active_menu_owned_frames =
        helper_active_menu_owned_frames + 1
    end
    local ff55_bad = emu:read8(0xFF55) ~= 0xFF
    local vbk_bad = (emu:read8(0xFF4F) & 1) ~= 0
    local svbk_bad = (emu:read8(0xFF70) & 7) ~= 1
    local ie_bad = emu:read8(0xFFFF) ~= 0x07
    if ff55_bad then
      menu_ff55_nonidle_frames = menu_ff55_nonidle_frames + 1
    end
    if vbk_bad then menu_vbk_nonzero_frames = menu_vbk_nonzero_frames + 1 end
    if svbk_bad then menu_svbk_non1_frames = menu_svbk_non1_frames + 1 end
    if ie_bad then menu_ie_non07_frames = menu_ie_non07_frames + 1 end
    -- The native menu intentionally leaves VBK1 selected between its
    -- alternating attribute-row passes.  Keep that as telemetry, while the
    -- actual containment invariants remain FF55 idle, SVBK1, and IE=$07.
    if ff55_bad or svbk_bad or ie_bad then
      menu_hardware_mismatch_frames = menu_hardware_mismatch_frames + 1
    end
  end
  if visible then
    menu_visible_frames = menu_visible_frames + 1
    menu_seen = true
    local lcdc = emu:read8(0xFF40)
    if emu:read8(0xFF4B) ~= 0x07 or emu:read8(0xFF4A) ~= 0x60 then
      window_geometry_mismatch_frames = window_geometry_mismatch_frames + 1
    end
    local base = window_map(lcdc)
    local mismatches = exact_window_mismatches(base)
    window_mismatch_cells = window_mismatch_cells + mismatches
    if mismatches > 0 then
      window_mismatch_frames = window_mismatch_frames + 1
      if mismatches > worst_window_mismatches then
        worst_window_mismatches = mismatches
      end
      if first_window_mismatch == "none" then
        first_window_mismatch = string.format(
          "f%d:l%02X:b%04X:n%d", frame, lcdc, base, mismatches)
      end
    end
    if base == bg_map(lcdc) then
      map_alias_frames = map_alias_frames + 1
      if first_alias == "none" then
        first_alias = string.format("f%d:l%02X:b%04X", frame, lcdc, base)
      end
    end
  end

  local keys = 0
  if phase == "pre" then
    keys = patrol_keys()
    if pre_complete and helper_depth == 0 then
      if capture_pre_snapshot() then
        phase = "open"
        phase_frame = 0
        keys = 0
      end
    end
  elseif phase == "open" then
    -- Retry SELECT as a two-frame pulse every eight frames.  The native
    -- engine may defer input during a room-scroll boundary.
    if ((phase_frame - 1) % 8) < 2 then
      keys = KEY_SELECT
      select_open_frames = select_open_frames + 1
    end
    -- FFE4 acknowledges this native menu route before its Window becomes
    -- visible.  FFC1 deliberately remains the exact gameplay value $01.
    -- Stop pulsing immediately at ownership so a second SELECT cannot close
    -- the menu before the first auditable Window frame.
    if emu:read8(0xFFE4) ~= 0 or visible then
      phase = "menu"
      phase_frame = 0
      keys = 0
    elseif phase_frame > 180 then
      finish("fail", "select-open-not-acknowledged")
      return
    end
  elseif phase == "menu" then
    keys = 0
    if visible then menu_hold_frames = menu_hold_frames + 1 end
    if not menu_seen and phase_frame > 180 then
      finish("fail", "menu-window-not-visible")
      return
    end
    if menu_hold_frames >= MENU_HOLD then
      phase = "close"
      phase_frame = 0
    end
  elseif phase == "close" then
    if ((phase_frame - 1) % 8) < 2 then
      keys = KEY_SELECT
      select_close_frames = select_close_frames + 1
    end
    if menu_seen and not owned and not visible and emu:read8(0xFFC1) == 1 then
      menu_closed = true
      phase = "post"
      phase_frame = 0
      keys = patrol_keys()
    elseif phase_frame > 180 then
      finish("fail", "select-close-not-acknowledged")
      return
    end
  elseif phase == "post" then
    keys = patrol_keys()
  end
  if menu_seen and not owned and not post_outer_seen then
    compare_intervening_visible_frame()
  end
  emu:setKeys(keys)
  record_transition()
  if frame >= LIMIT then finish("fail", "frame-limit") end
end)

callbacks:add("shutdown", function()
  if not finished then
    write_report("fail", "unexpected-shutdown")
  end
end)
