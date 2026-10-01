-- Cold-route Stage-4 SELECT-menu invalidation probe for exact r287.
--
-- The Python verifier supplies candidate-derived immutable oracles and runs
-- this probe twice through the checked-in single-flight launcher.  This Lua
-- owns no emulator launch and writes only below the verifier's repo tmp/
-- replay directory.
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
local native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end

local TARGET = 3
local EXPECTED_SCENE = 0x05
local DECIDER_ENTRY = 0xDAD4
local HELPER_ENTRY = 0xDB20
local HELPER_JOIN = 0xDA92
local CACHE_MISS_ENTRY = 0xDAA9
local CACHE_DIRTY_RETURN = 0xDAB6
local CACHE_RETURN = 0xDAA3
local ATTR_COMPILER_ENTRY = 0x42FC
local ATTR_COMPILER_BANK = 0x01
local INVALIDATOR_ENTRY = 0x6A40
local INVALIDATOR_EFFECT = 0x6A54
local INVALIDATOR_BANK = 0x0D
local PAYLOAD_FIRST = 0xDB00
local PAYLOAD_LAST = 0xDB3D
local TRAMPOLINE_FIRST = 0xDA5D
local TRAMPOLINE_LAST = 0xDA5F

local OUT = assert(os.getenv("STAGE4_MENU_OUT"), "STAGE4_MENU_OUT required")
local PAYLOAD_PATH = assert(
  os.getenv("STAGE4_MENU_PAYLOAD"), "STAGE4_MENU_PAYLOAD required")
local STAGE_LUT_PATH = assert(
  os.getenv("STAGE4_MENU_STAGE_LUT"), "STAGE4_MENU_STAGE_LUT required")
local MENU_LUT_PATH = assert(
  os.getenv("STAGE4_MENU_WINDOW_LUT"),
  "STAGE4_MENU_WINDOW_LUT required")
local ROM_SHA256 = assert(os.getenv("STAGE4_MENU_ROM_SHA256"))
local PROBE_SHA256 = assert(os.getenv("STAGE4_MENU_PROBE_SHA256"))
local VERIFIER_SHA256 = assert(os.getenv("STAGE4_MENU_VERIFIER_SHA256"))
local FRAME_LIMIT = tonumber(os.getenv("STAGE4_MENU_FRAMES") or "3000")
local MENU_HOLD = tonumber(os.getenv("STAGE4_MENU_HOLD") or "80")

local KEY_A = 0x01
local KEY_SELECT = 0x04
local KEY_START = 0x08
local KEY_DOWN = 0x80
local raw_vram = assert(emu.memory.vram)

local function read_exact(path, size)
  local handle = assert(io.open(path, "rb"))
  local payload = assert(handle:read("*a"))
  handle:close()
  assert(#payload == size, path .. " has wrong size")
  return payload
end

local expected_payload = read_exact(
  PAYLOAD_PATH, PAYLOAD_LAST - PAYLOAD_FIRST + 1)
local expected_stage_lut = read_exact(STAGE_LUT_PATH, 0x100)
local expected_menu_lut = read_exact(MENU_LUT_PATH, 0x100)

local frame = 0
local phase = "title"
local phase_frame = 0
local seeded = false
local confirmed = false
local finished = false
local stage_seen = false
local install_seen = false
local menu_seen = false
local menu_closed = false
local stable_stage_frames = 0
local breakpoint_failures = 0
local helper_active = false
local helper_period = "none"
local semantic_armed = false
local last_helper_h = nil
local helper_h_seen = {}
local helper_compare_missed = false
local first_post_helper_pending = false
local first_post_helper_miss_seen = false
local first_post_repaint_compiler_seen = false
local invalidation_effect_seen = false
local key_snapshots = {}
local key_snapshot_seen = {}
local transitions = {}
local last_transition = ""

local counters = {
  stage_context_violations = 0,
  ffc1_non1_frames = 0,
  installed_context_frames = 0,
  payload_checked_frames = 0,
  payload_mismatch_frames = 0,
  payload_mismatch_bytes = 0,
  dad5_mismatch_frames = 0,
  dab7_mismatch_frames = 0,
  trampoline_mismatch_frames = 0,
  svbk_non1_frames = 0,
  stage_lut_checked_frames = 0,
  stage_lut_mismatch_frames = 0,
  stage_lut_mismatch_bytes = 0,
  decider_entries_pre = 0,
  decider_entries_menu = 0,
  decider_entries_post = 0,
  helper_entries_pre = 0,
  helper_entries_menu = 0,
  helper_entries_post = 0,
  helper_joins_pre = 0,
  helper_joins_menu = 0,
  helper_joins_post = 0,
  helper_wrong_context = 0,
  helper_contract_failures = 0,
  helper_cache_hits_pre = 0,
  helper_cache_hits_menu = 0,
  helper_cache_hits_post = 0,
  helper_cache_misses_pre = 0,
  helper_cache_misses_menu = 0,
  helper_cache_misses_post = 0,
  first_post_helper_forced_miss = 0,
  first_post_helper_stale_hit = 0,
  first_post_helper_dirty_signal = 0,
  helper_dirty_signal_failures = 0,
  post_repaint_compiler_entries = 0,
  post_clean_after_repaint_frames = 0,
  helper_active_menu_frames = 0,
  invalidator_entries = 0,
  invalidator_menu_entries = 0,
  invalidator_effect_hits = 0,
  invalidator_effect_wrong_context = 0,
  invalidator_effect_nonzero_df53 = 0,
  invalidator_effect_nonzero_df57 = 0,
  menu_zero_cache_frames = 0,
  menu_cache_repopulation_frames = 0,
  menu_owned_frames = 0,
  menu_visible_frames = 0,
  ffe4_nonzero_frames = 0,
  menu_stage_context_violations = 0,
  window_checked_cells = 0,
  window_tile_mismatch_frames = 0,
  window_tile_mismatch_cells = 0,
  window_attr_mismatch_frames = 0,
  window_attr_mismatch_cells = 0,
  window_unsafe_attr_cells = 0,
  window_geometry_mismatch_frames = 0,
  window_map_alias_frames = 0,
  pre_visible_frames = 0,
  pre_visible_cells = 0,
  pre_semantic_mismatch_frames = 0,
  pre_semantic_mismatch_cells = 0,
  pre_write_trail_cells = 0,
  pre_unsafe_attr_cells = 0,
  pre_material_cells = 0,
  pre_warmup_mismatch_frames = 0,
  pre_warmup_mismatch_cells = 0,
  post_visible_frames = 0,
  post_visible_cells = 0,
  post_semantic_mismatch_frames = 0,
  post_semantic_mismatch_cells = 0,
  post_write_trail_cells = 0,
  post_unsafe_attr_cells = 0,
  post_material_cells = 0,
}

local function read_register(name)
  for _, reader in ipairs({
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }) do
    local ok, value = pcall(reader)
    if ok and type(value) == "number" then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function read_wram1(address)
  local old = emu:read8(0xFF70)
  emu:write8(0xFF70, 1)
  local value = emu:read8(address)
  emu:write8(0xFF70, old)
  return value
end

local function append_transition(tag)
  local state = string.format(
    "%s:%02X:%02X:%02X:%02X:%02X", tag, read_wram1(0xD880),
    emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFE4),
    emu:read8(0xFF40))
  if state ~= last_transition and #transitions < 64 then
    transitions[#transitions + 1] = string.format("f%d:%s", frame, state)
    last_transition = state
  end
end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for offset = 1, 0x1F do emu:write8(base + offset, 0) end
  end
end

local function stage4_identity()
  return read_wram1(0xD880) == EXPECTED_SCENE
    and emu:read8(0xFFBA) == TARGET
end

local function at_stage4()
  return stage4_identity() and emu:read8(0xFFC1) == 1
end

local function window_visible()
  return (emu:read8(0xFF40) & 0x20) ~= 0
    and emu:read8(0xFF4A) < 144
end

local function menu_owned()
  return emu:read8(0xFFE4) ~= 0 or window_visible()
end

local function current_period()
  if menu_owned() then return "menu" end
  if menu_closed or phase == "post" then return "post" end
  return "pre"
end

local function add_period(prefix, period)
  local name = prefix .. "_" .. period
  counters[name] = counters[name] + 1
end

local function with_svbk1(callback)
  local old = emu:read8(0xFF70)
  emu:write8(0xFF70, 1)
  local result = {callback()}
  emu:write8(0xFF70, old)
  return table.unpack(result)
end

local function capture_key_snapshot(tag)
  if key_snapshot_seen[tag] then return end
  key_snapshot_seen[tag] = true
  local cpu_h = read_register("H") & 0xFF
  local helper_h = last_helper_h or cpu_h
  local df_address = 0xDF00 + ((helper_h ~ 0xCB) & 0xFF)
  local df0, df1, df2, cache53, cache54, cache55,
    cache57, cache58, cache59 = with_svbk1(function()
    return emu:read8(df_address), emu:read8(df_address + 1),
      emu:read8(df_address + 2), emu:read8(0xDF53), emu:read8(0xDF54),
      emu:read8(0xDF55), emu:read8(0xDF57), emu:read8(0xDF58),
      emu:read8(0xDF59)
  end)
  local known_h = {}
  for value in pairs(helper_h_seen) do known_h[#known_h + 1] = value end
  table.sort(known_h)
  local known_records = {}
  for _, value in ipairs(known_h) do
    local address = 0xDF00 + ((value ~ 0xCB) & 0xFF)
    local a, b, room = with_svbk1(function()
      return emu:read8(address), emu:read8(address + 1),
        emu:read8(address + 2)
    end)
    known_records[#known_records + 1] = string.format(
      "%02X/%04X/%02X%02X%02X", value, address, a, b, room)
  end
  key_snapshots[tag] = string.format(
    "frame:%d,cpu_h:%02X,helper_h:%02X,c1f1:%02X,c2f1:%02X," ..
    "room:%02X,df_addr:%04X,df0:%02X,df1:%02X,df2:%02X," ..
    "cache53:%02X%02X%02X,cache57:%02X%02X%02X,known:%s",
    frame, cpu_h, helper_h, emu:read8(0xC1F1), emu:read8(0xC2F1),
    emu:read8(0xFFBD), df_address, df0, df1, df2,
    cache53, cache54, cache55, cache57, cache58, cache59,
    table.concat(known_records, ";"))
end

local function runtime_contract()
  return with_svbk1(function()
    local payload_bad = 0
    for address = PAYLOAD_FIRST, PAYLOAD_LAST do
      local wanted = string.byte(
        expected_payload, address - PAYLOAD_FIRST + 1)
      if emu:read8(address) ~= wanted then payload_bad = payload_bad + 1 end
    end
    local trampoline_bad = 0
    local trampoline = {0xC3, 0x20, 0xDB}
    for address = TRAMPOLINE_FIRST, TRAMPOLINE_LAST do
      if emu:read8(address) ~= trampoline[address - TRAMPOLINE_FIRST + 1] then
        trampoline_bad = trampoline_bad + 1
      end
    end
    return payload_bad, trampoline_bad,
      emu:read8(0xDAD5), emu:read8(0xDAB7)
  end)
end

local function audit_runtime_frame()
  local svbk = emu:read8(0xFF70) & 7
  if svbk ~= 1 then counters.svbk_non1_frames = counters.svbk_non1_frames + 1 end
  local payload_bad, trampoline_bad, dad5, dab7 = runtime_contract()
  local exact = payload_bad == 0 and trampoline_bad == 0
    and dad5 == 0x5D and dab7 == 0xEB
  if not install_seen and exact and at_stage4() then install_seen = true end
  if not install_seen then return false end
  counters.installed_context_frames = counters.installed_context_frames + 1
  counters.payload_checked_frames = counters.payload_checked_frames + 1
  if payload_bad ~= 0 then
    counters.payload_mismatch_frames = counters.payload_mismatch_frames + 1
    counters.payload_mismatch_bytes = counters.payload_mismatch_bytes + payload_bad
  end
  if trampoline_bad ~= 0 then
    counters.trampoline_mismatch_frames =
      counters.trampoline_mismatch_frames + 1
  end
  if dad5 ~= 0x5D then
    counters.dad5_mismatch_frames = counters.dad5_mismatch_frames + 1
  end
  if dab7 ~= 0xEB then
    counters.dab7_mismatch_frames = counters.dab7_mismatch_frames + 1
  end
  return exact
end

local function audit_stage_lut()
  local bad = 0
  for index = 0, 0xFF do
    if emu:read8(0xC600 + index) ~= string.byte(expected_stage_lut, index + 1) then
      bad = bad + 1
    end
  end
  counters.stage_lut_checked_frames = counters.stage_lut_checked_frames + 1
  if bad ~= 0 then
    counters.stage_lut_mismatch_frames = counters.stage_lut_mismatch_frames + 1
    counters.stage_lut_mismatch_bytes = counters.stage_lut_mismatch_bytes + bad
  end
end

local function material_tile(tile)
  return (tile >= 0x01 and tile <= 0x08) or tile == 0x2D or tile == 0x2E
end

local function audit_visible_gameplay(period)
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local columns = ((scx & 7) == 0) and 20 or 21
  local rows = ((scy & 7) == 0) and 18 or 19
  local first_col, first_row = scx >> 3, scy >> 3
  local tiles = {}
  for row = 0, rows - 1 do
    for col = 0, columns - 1 do
      local address = base
        + (((first_row + row) & 31) * 32)
        + ((first_col + col) & 31)
      tiles[#tiles + 1] = raw_vram:read8(address - 0x8000)
    end
  end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  local mismatch, unsafe, trails, materials = 0, 0, 0, 0
  local cursor = 1
  for row = 0, rows - 1 do
    for col = 0, columns - 1 do
      local address = base
        + (((first_row + row) & 31) * 32)
        + ((first_col + col) & 31)
      local tile = tiles[cursor]
      local actual = emu:read8(address)
      local wanted = string.byte(expected_stage_lut, tile + 1)
      if actual ~= wanted then
        mismatch = mismatch + 1
        trails = trails + 1
      end
      if (actual & 0xF8) ~= 0 then unsafe = unsafe + 1 end
      if material_tile(tile) then materials = materials + 1 end
      cursor = cursor + 1
    end
  end
  emu:write8(0xFF4F, old_vbk)
  local cells = rows * columns
  if period == "pre" and not semantic_armed then
    if mismatch == 0 and unsafe == 0 and counters.helper_entries_pre >= 2 then
      semantic_armed = true
    else
      if mismatch ~= 0 then
        counters.pre_warmup_mismatch_frames =
          counters.pre_warmup_mismatch_frames + 1
        counters.pre_warmup_mismatch_cells =
          counters.pre_warmup_mismatch_cells + mismatch
      end
      return
    end
  end
  counters[period .. "_visible_frames"] =
    counters[period .. "_visible_frames"] + 1
  counters[period .. "_visible_cells"] =
    counters[period .. "_visible_cells"] + cells
  counters[period .. "_semantic_mismatch_cells"] =
    counters[period .. "_semantic_mismatch_cells"] + mismatch
  counters[period .. "_write_trail_cells"] =
    counters[period .. "_write_trail_cells"] + trails
  counters[period .. "_unsafe_attr_cells"] =
    counters[period .. "_unsafe_attr_cells"] + unsafe
  counters[period .. "_material_cells"] =
    counters[period .. "_material_cells"] + materials
  if mismatch ~= 0 then
    counters[period .. "_semantic_mismatch_frames"] =
      counters[period .. "_semantic_mismatch_frames"] + 1
  end
  if period == "post" and first_post_repaint_compiler_seen
      and mismatch == 0 and unsafe == 0 then
    counters.post_clean_after_repaint_frames =
      counters.post_clean_after_repaint_frames + 1
    capture_key_snapshot("first_post_repaint")
  end
end

local function dump_packed(path, values)
  local handle = assert(io.open(path, "wb"))
  for _, value in ipairs(values) do handle:write(string.char(value)) end
  handle:close()
end

local menu_snapshot_done = false
local function audit_window()
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x40) ~= 0) and 0x9C00 or 0x9800
  local bg_base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local tiles, wanted_tiles = {}, {}
  local tile_bad = 0
  for row = 0, 5 do
    for col = 0, 19 do
      local actual = raw_vram:read8(base - 0x8000 + row * 32 + col)
      local wanted = emu:read8(0xC4E0 + row * 20 + col)
      tiles[#tiles + 1] = actual
      wanted_tiles[#wanted_tiles + 1] = wanted
      if actual ~= wanted then tile_bad = tile_bad + 1 end
    end
  end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  local attrs = {}
  local attr_bad, unsafe = 0, 0
  for row = 0, 5 do
    for col = 0, 19 do
      local index = row * 20 + col + 1
      local actual = emu:read8(base + row * 32 + col)
      local wanted = string.byte(expected_menu_lut, tiles[index] + 1)
      attrs[#attrs + 1] = actual
      if actual ~= wanted then attr_bad = attr_bad + 1 end
      if (actual & 0xF8) ~= 0 then unsafe = unsafe + 1 end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  counters.window_checked_cells = counters.window_checked_cells + 120
  counters.window_tile_mismatch_cells =
    counters.window_tile_mismatch_cells + tile_bad
  counters.window_attr_mismatch_cells =
    counters.window_attr_mismatch_cells + attr_bad
  counters.window_unsafe_attr_cells =
    counters.window_unsafe_attr_cells + unsafe
  if tile_bad ~= 0 then
    counters.window_tile_mismatch_frames =
      counters.window_tile_mismatch_frames + 1
  end
  if attr_bad ~= 0 then
    counters.window_attr_mismatch_frames =
      counters.window_attr_mismatch_frames + 1
  end
  if emu:read8(0xFF4B) ~= 0x07 or emu:read8(0xFF4A) ~= 0x60 then
    counters.window_geometry_mismatch_frames =
      counters.window_geometry_mismatch_frames + 1
  end
  if base == bg_base then
    counters.window_map_alias_frames = counters.window_map_alias_frames + 1
  end
  if not menu_snapshot_done then
    menu_snapshot_done = true
    dump_packed(OUT .. ".menu.tiles.bin", tiles)
    dump_packed(OUT .. ".menu.hud.bin", wanted_tiles)
    dump_packed(OUT .. ".menu.attrs.bin", attrs)
  end
end

local function dump_range(path, first, last, bank)
  local handle = assert(io.open(path, "wb"))
  local old = nil
  if bank == "svbk1" then
    old = emu:read8(0xFF70)
    emu:write8(0xFF70, 1)
  elseif bank == "vbk0" then
    old = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
  elseif bank == "vbk1" then
    old = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 1)
  end
  for address = first, last do handle:write(string.char(emu:read8(address))) end
  if bank == "svbk1" then emu:write8(0xFF70, old) end
  if bank == "vbk0" then emu:write8(0xFF4F, old) end
  if bank == "vbk1" then emu:write8(0xFF4F, old) end
  handle:close()
end

local function finish(status, reason)
  if finished then return end
  finished = true
  capture_key_snapshot("final")
  dump_range(OUT .. ".payload.bin", PAYLOAD_FIRST, PAYLOAD_LAST, "svbk1")
  dump_range(OUT .. ".stage-lut.bin", 0xC600, 0xC6FF, nil)
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  dump_range(OUT .. ".final.tiles.bin", base, base + 0x3FF, "vbk0")
  dump_range(OUT .. ".final.attrs.bin", base, base + 0x3FF, "vbk1")
  local report = assert(io.open(OUT .. ".report", "w"))
  report:write("status=" .. status .. "\n")
  report:write("reason=" .. reason .. "\n")
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format("frame_limit=%d\n", FRAME_LIMIT))
  report:write(string.format("menu_hold=%d\n", MENU_HOLD))
  report:write(string.format("target=%d\n", TARGET))
  report:write(string.format("expected_scene=%d\n", EXPECTED_SCENE))
  report:write(string.format("stage_seen=%d\n", stage_seen and 1 or 0))
  report:write(string.format("install_seen=%d\n", install_seen and 1 or 0))
  report:write(string.format("semantic_armed=%d\n", semantic_armed and 1 or 0))
  report:write(string.format("menu_seen=%d\n", menu_seen and 1 or 0))
  report:write(string.format("menu_closed=%d\n", menu_closed and 1 or 0))
  report:write(string.format("stable_stage_frames=%d\n", stable_stage_frames))
  report:write(string.format("breakpoint_failures=%d\n", breakpoint_failures))
  for name, value in pairs(counters) do
    report:write(string.format("%s=%d\n", name, value))
  end
  for _, tag in ipairs({
    "settled_pre", "open", "invalidation_effect", "menu", "first_post",
    "first_post_helper", "first_post_repaint", "final",
  }) do
    report:write("key_" .. tag .. "=" .. (key_snapshots[tag] or "missing") .. "\n")
  end
  report:write(string.format(
    "final_state=scene:%02X,ffc1:%02X,stage:%02X,ffe4:%02X,lcdc:%02X," ..
    "wx:%02X,wy:%02X,scx:%02X,scy:%02X,vbk:%02X,svbk:%02X," ..
    "ff55:%02X,dad5:%02X,dab7:%02X,base:%04X,helper:%d\n",
    read_wram1(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBA),
    emu:read8(0xFFE4), lcdc, emu:read8(0xFF4B), emu:read8(0xFF4A),
    emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xFF4F) & 1,
    emu:read8(0xFF70) & 7, emu:read8(0xFF55),
    with_svbk1(function() return emu:read8(0xDAD5) end),
    with_svbk1(function() return emu:read8(0xDAB7) end),
    base, helper_active and 1 or 0))
  report:write("rom_sha256=" .. ROM_SHA256 .. "\n")
  report:write("probe_sha256=" .. PROBE_SHA256 .. "\n")
  report:write("verifier_sha256=" .. VERIFIER_SHA256 .. "\n")
  report:write("transitions=" .. table.concat(transitions, ";") .. "\n")
  report:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

local function install_breakpoint(address, callback)
  local ok, result = pcall(function()
    return emu:setBreakpoint(callback, address)
  end)
  if not ok or type(result) ~= "number" or result <= 0 then
    breakpoint_failures = breakpoint_failures + 1
  end
end

install_breakpoint(DECIDER_ENTRY, function()
  if not stage_seen then return end
  local period = current_period()
  add_period("decider_entries", period)
end)

install_breakpoint(HELPER_ENTRY, function()
  if not stage_seen then return end
  local period = current_period()
  last_helper_h = read_register("H") & 0xFF
  helper_h_seen[last_helper_h] = true
  add_period("helper_entries", period)
  helper_active = true
  helper_period = period
  helper_compare_missed = false
  if not at_stage4() then counters.helper_wrong_context = counters.helper_wrong_context + 1 end
  local payload_bad, trampoline_bad, dad5, dab7 = runtime_contract()
  if payload_bad ~= 0 or trampoline_bad ~= 0 or dad5 ~= 0x5D or dab7 ~= 0xEB then
    counters.helper_contract_failures = counters.helper_contract_failures + 1
  else
    install_seen = true
  end
  if period == "post" and not key_snapshot_seen.first_post_helper then
    capture_key_snapshot("first_post_helper")
    first_post_helper_pending = true
  end
end)

install_breakpoint(HELPER_JOIN, function()
  if helper_active then
    add_period("helper_joins", helper_period)
  end
end)

install_breakpoint(CACHE_MISS_ENTRY, function()
  if not helper_active or helper_compare_missed then return end
  helper_compare_missed = true
  add_period("helper_cache_misses", helper_period)
  if first_post_helper_pending then
    counters.first_post_helper_forced_miss =
      counters.first_post_helper_forced_miss + 1
    first_post_helper_miss_seen = true
  end
end)

install_breakpoint(CACHE_DIRTY_RETURN, function()
  if not helper_active or not helper_compare_missed then return end
  if emu:read8(0xFFE0) ~= 1 then
    counters.helper_dirty_signal_failures =
      counters.helper_dirty_signal_failures + 1
  elseif first_post_helper_pending then
    counters.first_post_helper_dirty_signal =
      counters.first_post_helper_dirty_signal + 1
  end
end)

install_breakpoint(CACHE_RETURN, function()
  if not helper_active then return end
  if not helper_compare_missed then
    add_period("helper_cache_hits", helper_period)
    if first_post_helper_pending then
      counters.first_post_helper_stale_hit =
        counters.first_post_helper_stale_hit + 1
    end
  end
  first_post_helper_pending = false
  helper_compare_missed = false
  helper_active = false
  helper_period = "none"
end)

install_breakpoint(ATTR_COMPILER_ENTRY, function()
  if not first_post_helper_miss_seen or phase ~= "post" then return end
  if emu:read8(0xFF99) ~= ATTR_COMPILER_BANK then return end
  counters.post_repaint_compiler_entries =
    counters.post_repaint_compiler_entries + 1
  first_post_repaint_compiler_seen = true
end)

install_breakpoint(INVALIDATOR_ENTRY, function()
  if not stage_seen or emu:read8(0xFF99) ~= INVALIDATOR_BANK then return end
  counters.invalidator_entries = counters.invalidator_entries + 1
  if stage4_identity() and emu:read8(0xFFE4) ~= 0 then
    counters.invalidator_menu_entries =
      counters.invalidator_menu_entries + 1
  end
end)

install_breakpoint(INVALIDATOR_EFFECT, function()
  if not stage_seen or emu:read8(0xFF99) ~= INVALIDATOR_BANK then return end
  counters.invalidator_effect_hits = counters.invalidator_effect_hits + 1
  invalidation_effect_seen = true
  if not stage4_identity() or emu:read8(0xFFE4) == 0 then
    counters.invalidator_effect_wrong_context =
      counters.invalidator_effect_wrong_context + 1
  end
  if read_wram1(0xDF53) ~= 0 then
    counters.invalidator_effect_nonzero_df53 =
      counters.invalidator_effect_nonzero_df53 + 1
  end
  if read_wram1(0xDF57) ~= 0 then
    counters.invalidator_effect_nonzero_df57 =
      counters.invalidator_effect_nonzero_df57 + 1
  end
  capture_key_snapshot("invalidation_effect")
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  phase_frame = phase_frame + 1
  local keys = 0

  if not seeded and frame >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    -- Receipt-proven native GAME START path shared with stage_integrity.lua.
    if frame >= 180 and frame < 186 then keys = KEY_DOWN
    elseif frame >= 193 and frame < 199 then keys = KEY_A
    elseif frame >= 241 and frame < 247 then keys = KEY_A
    elseif frame >= 291 and frame < 297 then keys = KEY_A
    elseif frame >= 341 and frame < 347 then keys = KEY_START
    elseif frame >= 391 and frame < 397 then keys = KEY_A end
    if frame >= 450 then phase = "level_select"; phase_frame = 0 end
  elseif phase == "level_select" and not confirmed then
    native_assistance.write(0xDCFD, 0x01)
    emu:write8(0xFFBA, TARGET)
    seed_sram()
    if frame % 60 >= 10 and frame % 60 < 16 then keys = KEY_A end
    if read_wram1(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
      confirmed = true
      phase = "loading"
      phase_frame = 0
      append_transition("selected")
    end
    if frame > 800 then finish("fail", "level-select-timeout") end
  elseif phase == "loading" then
    -- Keep only the selector stable until Stage 4 first owns gameplay; after
    -- that point FFBA is observed, never forced.
    emu:write8(0xFFBA, TARGET)
    if at_stage4() then
      stage_seen = true
      phase = "pre"
      phase_frame = 0
      append_transition("stage4")
    end
  elseif phase == "open" then
    if phase_frame == 1 then capture_key_snapshot("open") end
    if phase_frame <= 6 then keys = KEY_SELECT end
    if menu_owned() then
      menu_seen = true
      phase = "menu"
      phase_frame = 0
      if invalidation_effect_seen then capture_key_snapshot("menu") end
      append_transition("menu")
    elseif phase_frame > 180 then
      finish("fail", "select-open-not-acknowledged")
    end
  elseif phase == "menu" then
    if counters.menu_visible_frames >= MENU_HOLD then
      phase = "close"
      phase_frame = 0
      append_transition("close")
    end
  elseif phase == "close" then
    if phase_frame <= 6 then keys = KEY_SELECT end
    if phase_frame > 6 and not menu_owned() then
      menu_closed = true
      phase = "post"
      phase_frame = 0
      capture_key_snapshot("first_post")
      append_transition("post")
    elseif phase_frame > 180 then
      finish("fail", "select-close-not-acknowledged")
    end
  end
  emu:setKeys(keys)

  if stage_seen then
    -- Standard stationary/invincibility fixture writes used by the checked-in
    -- later-stage integrity and speed routes. They do not touch renderer state.
    native_assistance.write(0xDCBB, 0xF0)
    if not stage4_identity() then
      counters.stage_context_violations =
        counters.stage_context_violations + 1
    elseif emu:read8(0xFFC1) ~= 1 then
      counters.ffc1_non1_frames = counters.ffc1_non1_frames + 1
    else
      stable_stage_frames = stable_stage_frames + 1
    end
    local exact_runtime = audit_runtime_frame()
    if install_seen then audit_stage_lut() end

    local owned, visible = menu_owned(), window_visible()
    if emu:read8(0xFFE4) ~= 0 then
      counters.ffe4_nonzero_frames = counters.ffe4_nonzero_frames + 1
    end
    if owned then
      counters.menu_owned_frames = counters.menu_owned_frames + 1
      if phase == "menu" and invalidation_effect_seen then
        capture_key_snapshot("menu")
      end
      if not at_stage4() then
        counters.menu_stage_context_violations =
          counters.menu_stage_context_violations + 1
      end
      if helper_active then
        counters.helper_active_menu_frames =
          counters.helper_active_menu_frames + 1
      end
      if invalidation_effect_seen then
        if read_wram1(0xDF53) == 0 and read_wram1(0xDF57) == 0 then
          counters.menu_zero_cache_frames =
            counters.menu_zero_cache_frames + 1
        else
          counters.menu_cache_repopulation_frames =
            counters.menu_cache_repopulation_frames + 1
        end
      end
    end
    if visible then
      counters.menu_visible_frames = counters.menu_visible_frames + 1
      audit_window()
    end

    if exact_runtime and not owned and not helper_active and at_stage4() then
      local period = (menu_closed or phase == "post") and "post" or "pre"
      audit_visible_gameplay(period)
    end

    if phase == "pre" and install_seen and phase_frame >= 120
        and counters.helper_entries_pre >= 2
        and counters.pre_visible_frames >= 30 then
      capture_key_snapshot("settled_pre")
      phase = "open"
      phase_frame = 0
      append_transition("open")
    elseif phase == "post" and phase_frame >= 120
        and counters.helper_entries_post >= 2
        and counters.post_visible_frames >= 60 then
      finish("ok", "complete")
    end
  end

  if frame >= FRAME_LIMIT then finish("fail", "frame-limit") end
end)
