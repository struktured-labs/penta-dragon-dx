-- Consecutive-frame receipt for the Stage 1 low-health warning state.
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

local OUT = assert(os.getenv("LOW_HEALTH_OUT"), "LOW_HEALTH_OUT is required")
local BOOT_STATE = os.getenv("LOW_HEALTH_BOOT_STATE") == "1"
local OWNER_ADDRESS = tonumber(os.getenv("LOW_HEALTH_OWNER_ADDRESS") or "65445")
local SETTLE = tonumber(os.getenv("LOW_HEALTH_SETTLE") or "120")
local SETTLE_KEYS = tonumber(os.getenv("LOW_HEALTH_SETTLE_KEYS") or "0")
local SETTLE_DRIVE_FRAMES = tonumber(os.getenv("LOW_HEALTH_SETTLE_DRIVE_FRAMES") or "0")
local SAMPLES = tonumber(os.getenv("LOW_HEALTH_SAMPLES") or "240")
-- Keep every requested sample; observe up to eight more frames to finish a
-- publication already in flight. All extra frames retain the visual audits.
local function observation_done(observed, requested, pending)
  return observed >= requested and (not pending or observed >= requested + 8)
end
local PRE_TRIGGER = tonumber(os.getenv("LOW_HEALTH_PRE_TRIGGER") or "60")
local REQUIRE_SCENE0B = os.getenv("LOW_HEALTH_REQUIRE_SCENE0B") == "1"
local SCENE0B_FRAMES = tonumber(
  os.getenv("LOW_HEALTH_SCENE0B_FRAMES") or "120")
local SCENE0B_HEALTH = 0x40
local POST_TRIGGER_KEYS = tonumber(
  os.getenv("LOW_HEALTH_POST_TRIGGER_KEYS") or "0")
local RECOVERY_DRIVE_FRAMES = tonumber(os.getenv("LOW_HEALTH_RECOVERY_DRIVE_FRAMES") or "0")
local TRACE_SCANNER = os.getenv("LOW_HEALTH_TRACE_SCANNER") == "1"
local TRACE_SCANNER_LIMIT = tonumber(
  os.getenv("LOW_HEALTH_TRACE_SCANNER_LIMIT") or "8192")
local TRACE_ATTR = os.getenv("LOW_HEALTH_TRACE_ATTR") == "1"
local TRACE_LAYOUTS = os.getenv("LOW_HEALTH_TRACE_LAYOUTS") == "1"
local STATE_OUT = os.getenv("LOW_HEALTH_STATE_OUT")
-- Optional read-only boundary evidence. Never restore or alter emulated state.
local trace_samples = {}
for value in (os.getenv("LOW_HEALTH_TRACE_SAMPLES") or ""):gmatch("%d+") do
  trace_samples[tonumber(value)] = true
end
local WATCH_BGP = os.getenv("LOW_HEALTH_WATCH_BGP") == "1"
local WATCH_COMPILER_HANG =
  os.getenv("LOW_HEALTH_WATCH_COMPILER_HANG") == "1"
local DIAGNOSTIC_LIGHT = os.getenv("LOW_HEALTH_DIAGNOSTIC_LIGHT") == "1"
local frame, sample, done = 0, 0, false
local music_transition_seen = false
local scanner_path = "entry"
local scanner_trace_count = 0
local layout_records, layout_seen, layout_events = {}, {}, {}
local debug_destination = 0
-- Expected ordinary attributes belong to a completed physical BG-map
-- publication, not to the live room register. A room commit can precede the
-- next map publication by many rendered frames; consulting live C600 during
-- that interval changes only the verifier's verdict, not the displayed map.
local published_expected_planes = {}
local pending_expected_plane = nil
local expected_plane_epoch = 0
local expected_plane_promotions, expected_plane_invalid_promotions = 0, 0
local source_ret_hits, postcopy_hits, hazard_dispatch_hits, hazard_helper_hits,
  hazard_pure_helper_hits, hazard_front_hits, hazard_write_hits =
  0, 0, 0, 0, 0, 0, 0
local route_profile = os.getenv("LOW_HEALTH_PUBLICATION_ROUTE_PROFILE") or ""
local route_pending, route_completed, route_bypass, route_invalid = false, 0, 0, 0
local dispatch_entry, dispatch_retries = nil, 0
-- Eligibility is cleared at the next instruction, not at route completion.
-- Thus a genuine second entry cannot masquerade as a breakpoint retry.
local function dispatch_interrupt_retry(previous, current)
  if not previous then return false end
  for _, key in ipairs({"frame", "af", "bc", "de", "hl", "sp",
      "scene", "room", "effective_room", "owner", "svbk", "ie"}) do
    if previous[key] ~= current[key] then return false end
  end
  local cleared = previous.flags - current.flags
  for _, bit in ipairs({1, 2, 4, 8, 16}) do
    if cleared == bit and math.floor(previous.flags / bit) % 2 == 1
        and math.floor(previous.ie / bit) % 2 == 1 then return true end
  end
  return false
end
local function finish_publication_route(bypass)
  if route_profile == "" then return end
  if not route_pending then route_invalid = route_invalid + 1 end
  route_pending = false
  route_completed = route_completed + 1
  if bypass then
    route_bypass = route_bypass + 1
    if emu:read8(0xD880) ~= 2 or emu:read8(0xFFBD) ~= 3
        or emu:read8(0xFFE5) ~= 3 or (emu:read8(0xFF70) & 7) ~= 1 then
      route_invalid = route_invalid + 1
    end
  end
end
local scene0b_source_ret_hits, scene0b_postcopy_hits,
  scene0b_hazard_dispatch_hits, scene0b_hazard_helper_hits,
  scene0b_hazard_pure_helper_hits, scene0b_hazard_front_hits,
  scene0b_hazard_write_hits = 0, 0, 0, 0, 0, 0, 0
local runtime_gateway_hits, runtime_gateway_scene0b_hits = 0, 0
local split_consumer_hits, split_consumer_scene0b_hits = 0, 0
local wall_helper_hits, scene0b_wall_helper_hits = 0, 0
local pure_copy_hits, scene0b_pure_copy_hits = 0, 0
local dirty_copy_hits, scene0b_dirty_copy_hits = 0, 0
local decider_hit_hits, scene0b_decider_hit_hits = 0, 0
local decider_dirty_hits, scene0b_decider_dirty_hits = 0, 0
local decider_sentinel_hits, scene0b_decider_sentinel_hits = 0, 0
local atomic_setup_hits, scene0b_atomic_setup_hits = 0, 0
local mapdone_odd_hits, mapdone_even_hits = 0, 0
local scene0b_mapdone_odd_hits, scene0b_mapdone_even_hits = 0, 0
local atomic_setup_invalid_h_hits, scene0b_atomic_setup_invalid_h_hits = 0, 0
local mapdone_invalid_latch_hits, scene0b_mapdone_invalid_latch_hits = 0, 0
local runtime_entry_mismatches, runtime_scene0b_entry_mismatches = 0, 0
local compiler_publications, compiler_first_rows, compiler_row_calls = 0, 0, 0
local compiler_d400_1a, compiler_d400_f0, compiler_d400_other = 0, 0, 0
local compiler_contract_mismatches, compiler_orphan_rows,
  compiler_incomplete = 0, 0, 0
local scene0b_compiler_publications, scene0b_compiler_first_rows,
  scene0b_compiler_row_calls, scene0b_compiler_contract_mismatches = 0, 0, 0, 0
local compiler_pending, compiler_pending_scene0b = false, false
local compiler_pending_rows, compiler_pending_latch = 0, 0
local bulk_completions, bulk_mismatches = 0, 0
local scene0b_bulk_completions, scene0b_bulk_mismatches = 0, 0

local EXPECTED_D400 = string.rep(string.char(0x1A, 0x13, 0x4F, 0x0A, 0x22), 24)
  .. string.char(0xC9)

local function early_register(name)
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
  return 0xFFFF
end

local function read_payload(name, expected_length, description)
  local path = assert(os.getenv(name), name .. " is required")
  local handle = assert(io.open(path, "rb"))
  local payload = assert(handle:read("*a"))
  handle:close()
  assert(#payload == expected_length,
    name .. " must be the " .. description)
  return payload
end

local runtime_a = read_payload(
  "LOW_HEALTH_RUNTIME_A", 0x29, "41-byte DAD7 runtime")
local runtime_b = read_payload(
  "LOW_HEALTH_RUNTIME_B", 0x29, "41-byte DAD7 runtime")
local canonical_stage1_lut = read_payload(
  "LOW_HEALTH_CANONICAL_LUT", 0x100, "256-byte canonical Stage-1 LUT")

local function independent_expected_palette(tile, room, ffe5)
  local effective_room = ffe5 ~= 0 and ffe5 or room
  if effective_room == 0x01
      and (tile == 0x24 or tile == 0x27
        or tile == 0x30 or tile == 0x33) then
    return 0x06
  end
  return string.byte(canonical_stage1_lut, tile + 1) & 0x07
end

local function resident_runtime_matches_candidate()
  local matches_a, matches_b = true, true
  for offset = 0, 0x28 do
    local actual = assert(emu.memory.wram):read8(0x1AD7 + offset)
    matches_a = matches_a and actual == string.byte(runtime_a, offset + 1)
    matches_b = matches_b and actual == string.byte(runtime_b, offset + 1)
  end
  return matches_a or matches_b
end

local function scene0b()
  return emu:read8(0xD880) == 0x0B
end

if os.getenv("LOW_HEALTH_TRACE_PUBLICATION_ROUTES") == "1" then
  local path=OUT .. ".publication-routes.tsv"
  local handle=assert(io.open(path,"w"))
  handle:write("frame\tevent\tscene\troom\teffective_room\towner\tbc\tsvbk\tsp\taf\tif\tie\tly\n")
  handle:close()
  for _, site in ipairs({{0x6CCE,"dispatch"},{0x6BA7,"helper-pop"},
      {0x6BA8,"pure-helper"},{0x6BAB,"helper-loaded"},
      {0x61B7,"scanner"},{0x6B81,"room03-bypass"}}) do
    local address,event=site[1],site[2]
    assert(emu:setBreakpoint(function()
      local h=assert(io.open(path,"a"))
      h:write(string.format("%d\t%s\t%02X\t%02X\t%02X\t%02X\t%04X\t%02X\t%04X\t%04X\t%02X\t%02X\t%02X\n",
        frame,event,emu:read8(0xD880),emu:read8(0xFFBD),emu:read8(0xFFE5),
        emu:read8(0xFF01),early_register("bc"),emu:read8(0xFF70),
        early_register("sp"),early_register("af"),emu:read8(0xFF0F),
        emu:read8(0xFFFF),emu:read8(0xFF44)))
      h:close()
    end,address,19)>0)
  end
end

-- Arithmetic validation is separate from semantic expectation generation.
-- Actual attrs and mutable LUT values can reject a compile, never define
-- the expected palette used to judge the displayed map.
local function bulk_output_matches_lookup()
  for row = 0, 23 do
    for column = 0, 23 do
      local tile = emu:read8(0xC1A0 + row * 24 + column)
      if emu:read8(0xD000 + row * 32 + column) ~= emu:read8(0xC600 + tile) then
        return false
      end
    end
  end
  return true
end

local function arm_resident_compiler_receipt()
  if compiler_pending then
    compiler_incomplete = compiler_incomplete + 1
  end
  if pending_expected_plane then
    expected_plane_invalid_promotions = expected_plane_invalid_promotions + 1
  end
  compiler_pending = true
  compiler_pending_rows = 0
  compiler_pending_scene0b = scene0b()
  compiler_pending_latch = emu:read8(OWNER_ADDRESS)
  local destination = compiler_pending_latch == 0x99 and 0x9800
    or (compiler_pending_latch == 0x9D and 0x9C00 or 0)
  local prior = published_expected_planes[destination]
  local expected = {}
  if prior then
    for offset, value in pairs(prior.expected) do expected[offset] = value end
  end
  pending_expected_plane = {
    destination = destination,
    expected = expected,
    rows = 0,
    compile_frame = frame,
    compile_sample = sample,
    room = emu:read8(0xFFBD),
    ffe5 = emu:read8(0xFFE5),
  }
  compiler_publications = compiler_publications + 1
  if compiler_pending_scene0b then
    scene0b_compiler_publications = scene0b_compiler_publications + 1
  end
end

local function inspect_resident_compiler_row()
  compiler_row_calls = compiler_row_calls + 1
  if not compiler_pending then
    compiler_orphan_rows = compiler_orphan_rows + 1
    return
  end
  if compiler_pending_scene0b then
    scene0b_compiler_row_calls = scene0b_compiler_row_calls + 1
  end
  local row = compiler_pending_rows
  if pending_expected_plane then
    local source = 0xC1A0 + row * 0x18
    local destination_offset = row * 0x20
    for column = 0, 0x17 do
      local tile = emu:read8(source + column)
      pending_expected_plane.expected[destination_offset + column] =
        independent_expected_palette(
          tile, pending_expected_plane.room, pending_expected_plane.ffe5)
    end
    pending_expected_plane.rows = row + 1
  end
  if row == 0 then
    compiler_first_rows = compiler_first_rows + 1
    if compiler_pending_scene0b then
      scene0b_compiler_first_rows = scene0b_compiler_first_rows + 1
    end
  end
  local d400 = emu:read8(0xD400)
  if d400 == 0x1A then
    compiler_d400_1a = compiler_d400_1a + 1
  elseif d400 == 0xF0 then
    compiler_d400_f0 = compiler_d400_f0 + 1
  else
    compiler_d400_other = compiler_d400_other + 1
  end
  local resident = {}
  for offset = 0, 120 do
    resident[#resident + 1] = string.char(emu:read8(0xD400 + offset))
  end
  local de = early_register("de")
  local hl = early_register("hl")
  local bc = early_register("bc")
  local valid = emu:read8(0xFF99) == 0x01
    and (emu:read8(0xFF70) & 0x07) == 0x03
    and emu:read8(0xFFE0) == 0x18 - row
    and de == 0xC1A0 + row * 0x18
    -- D400 emits 24 attribute bytes, then fixed:$4316 advances HL by the
    -- eight-byte tilemap padding.  Each source row is 24 bytes; each WRAM
    -- destination row is therefore the full 32-byte BG-map stride.
    and hl == 0xD000 + row * 0x20
    and ((bc >> 8) & 0xFF) == 0xC6
    and (compiler_pending_latch == 0x99
      or compiler_pending_latch == 0x9D)
    and table.concat(resident) == EXPECTED_D400
  if not valid then
    compiler_contract_mismatches = compiler_contract_mismatches + 1
    if compiler_pending_scene0b then
      scene0b_compiler_contract_mismatches =
        scene0b_compiler_contract_mismatches + 1
    end
  end
  compiler_pending_rows = row + 1
  if compiler_pending_rows == 24 then
    compiler_pending = false
  end
end

local function inspect_bulk_completion()
  if not compiler_pending or compiler_pending_rows ~= 0 then return end
  bulk_completions = bulk_completions + 1
  if compiler_pending_scene0b then
    scene0b_bulk_completions = scene0b_bulk_completions + 1
  end
  local valid = pending_expected_plane ~= nil
    and (emu:read8(0xFF70) & 7) == 3
    and emu:read8(0xFF99) == 1 and emu:read8(0xFFE0) == 0
    and early_register("de") == 0xC3E0
    and early_register("hl") == 0xD300
    and (early_register("bc") >> 8) == 0xC6
    and bulk_output_matches_lookup()
  if valid then
    for row = 0, 23 do
      for column = 0, 23 do
        local tile = emu:read8(0xC1A0 + row * 24 + column)
        local offset = row * 32 + column
        pending_expected_plane.expected[offset] = independent_expected_palette(
          tile, pending_expected_plane.room, pending_expected_plane.ffe5)
      end
    end
  end
  if valid then
    pending_expected_plane.rows = 24
    compiler_pending = false
  else
    bulk_mismatches = bulk_mismatches + 1
    if compiler_pending_scene0b then
      scene0b_bulk_mismatches = scene0b_bulk_mismatches + 1
    end
    pending_expected_plane = nil
  end
end

local function publish_expected_plane()
  local pending = pending_expected_plane
  if not pending or pending.destination == 0 or pending.rows ~= 24
      or emu:read8(0xFF55) ~= 0xFF
      or (emu:read8(0xFF4F) & 0x01) ~= 0
      or (emu:read8(0xFF70) & 0x07) ~= 0x01 then
    expected_plane_invalid_promotions = expected_plane_invalid_promotions + 1
    pending_expected_plane = nil
    return
  end
  expected_plane_epoch = expected_plane_epoch + 1
  pending.epoch = expected_plane_epoch
  pending.publish_frame = frame
  pending.publish_sample = sample
  published_expected_planes[pending.destination] = pending
  expected_plane_promotions = expected_plane_promotions + 1
  pending_expected_plane = nil
end

-- The fixture is a mid-game Stage-1 state, not a title transition. Older
-- serialized states can carry a stale DF0D=$18 cache even after the Python
-- normalizer restarts execution through the candidate's cold initializer.
-- Seed it immediately and keep it bound to the live scene during settling so
-- candidate title-card hooks cannot perturb the movement cadence under test.
if not BOOT_STATE then pcall(function() emu:write8(0xDF0D, 0x02) end) end

local function register_layout()
  if not TRACE_LAYOUTS then return 0 end
  local raw, attr = {}, {}
  for offset = 0, 0x23F do
    local tile = emu:read8(0xC1A0 + offset)
    raw[#raw + 1] = string.char(tile)
    attr[#attr + 1] = string.char(emu:read8(0xC600 + tile) & 0x07)
  end
  local raw_blob = table.concat(raw)
  if not layout_seen[raw_blob] then
    layout_records[#layout_records + 1] = {
      raw = raw_blob,
      attr = table.concat(attr),
    }
    layout_seen[raw_blob] = #layout_records
  end
  return layout_seen[raw_blob]
end

if TRACE_LAYOUTS then
  local cache_trace = assert(io.open(OUT .. ".cache-writes.tsv", "w"))
  cache_trace:write("frame\taddress\tpc\tbank\told\tnew\tscene\troom\n")
  cache_trace:close()
  local latch_trace = assert(io.open(OUT .. ".ffa5-writes.tsv", "w"))
  latch_trace:write("frame\tpc\tbank\told\tnew\tscene\troom\n")
  latch_trace:close()
  assert(emu:setRangeWatchpoint(function(info)
    local pc = 0
    pcall(function() pc = emu:getRegister("pc") end)
    local handle = assert(io.open(OUT .. ".ffa5-writes.tsv", "a"))
    handle:write(string.format(
      "%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
      frame, pc & 0xFFFF, emu:read8(0xFF99), info.oldValue & 0xFF,
      info.newValue & 0xFF, emu:read8(0xD880), emu:read8(0xFFBD)))
    handle:close()
  end, 0xFFA5, 0xFFA5, C.WATCHPOINT_TYPE.WRITE) > 0)
  pcall(function()
    emu:setBreakpoint(function() debug_destination = 0x9C end, 0x42A0)
    emu:setBreakpoint(function() debug_destination = 0x98 end, 0x42A5)
    emu:setBreakpoint(function()
      local scene = emu:read8(0xD880) & 0xF6
      if scene == 0x02 and #layout_events < 2048 then
        layout_events[#layout_events + 1] = {
          frame = frame,
          sample = sample,
          destination = debug_destination,
          lcdc = emu:read8(0xFF40),
          scx = emu:read8(0xFF43),
          scy = emu:read8(0xFF42),
          dc00 = emu:read8(0xDC00),
          dc01 = emu:read8(0xDC01),
          dc02 = emu:read8(0xDC02),
          dc03 = emu:read8(0xDC03),
          dc0b = emu:read8(0xDC0B),
          dc0c = emu:read8(0xDC0C),
          dc0d = emu:read8(0xDC0D),
          dc0e = emu:read8(0xDC0E),
          dc0f = emu:read8(0xDC0F),
          dc81 = emu:read8(0xDC81),
          ffcf = emu:read8(0xFFCF),
          room = emu:read8(0xFFBD),
          layout = register_layout(),
        }
      end
    end, 0x3485)
    emu:setBreakpoint(function()
      source_ret_hits = source_ret_hits + 1
      if scene0b() then scene0b_source_ret_hits = scene0b_source_ret_hits + 1 end
    end, 0x13E4, 0)
    emu:setBreakpoint(function()
      postcopy_hits = postcopy_hits + 1
      if scene0b() then scene0b_postcopy_hits = scene0b_postcopy_hits + 1 end
    end, 0x10E2, 0)
    emu:setBreakpoint(function()
      local latch = emu:read8(OWNER_ADDRESS)
      local odd = (latch & 0x01) ~= 0
      if odd then
        dirty_copy_hits = dirty_copy_hits + 1
        mapdone_odd_hits = mapdone_odd_hits + 1
        if scene0b() then
          scene0b_dirty_copy_hits = scene0b_dirty_copy_hits + 1
          scene0b_mapdone_odd_hits = scene0b_mapdone_odd_hits + 1
        end
      else
        pure_copy_hits = pure_copy_hits + 1
        mapdone_even_hits = mapdone_even_hits + 1
        if scene0b() then
          scene0b_pure_copy_hits = scene0b_pure_copy_hits + 1
          scene0b_mapdone_even_hits = scene0b_mapdone_even_hits + 1
        end
      end
      local valid = odd and (latch == 0x99 or latch == 0x9D)
        or (not odd and (latch == 0x98 or latch == 0x9C))
      if not valid then
        mapdone_invalid_latch_hits = mapdone_invalid_latch_hits + 1
        if scene0b() then
          scene0b_mapdone_invalid_latch_hits =
            scene0b_mapdone_invalid_latch_hits + 1
        end
      end
    -- This is the actual route decision, before either post-copy owner can
    -- clear FFA5.  A previous probe at $42F7 sampled after cleanup, while a
    -- breakpoint on a CALL operand could never execute.
    end, 0x42ED, 1)
    emu:setBreakpoint(function()
      atomic_setup_hits = atomic_setup_hits + 1
      if scene0b() then scene0b_atomic_setup_hits = scene0b_atomic_setup_hits + 1 end
      local h = (early_register("hl") >> 8) & 0xFF
      if h ~= 0x98 and h ~= 0x9C then
        atomic_setup_invalid_h_hits = atomic_setup_invalid_h_hits + 1
        if scene0b() then
          scene0b_atomic_setup_invalid_h_hits =
            scene0b_atomic_setup_invalid_h_hits + 1
        end
      end
    end, 0xDA13)
    emu:setBreakpoint(function()
      if route_profile ~= "" then
        local current = {frame=frame, flags=emu:read8(0xFF0F),
          ie=emu:read8(0xFFFF), scene=emu:read8(0xD880),
          room=emu:read8(0xFFBD), effective_room=emu:read8(0xFFE5),
          owner=emu:read8(OWNER_ADDRESS), svbk=emu:read8(0xFF70)}
        for _, name in ipairs({"af", "bc", "de", "hl", "sp"}) do
          current[name] = early_register(name)
        end
        local retry = dispatch_interrupt_retry(dispatch_entry, current)
        dispatch_entry = current
        if retry then
          dispatch_retries = dispatch_retries + 1
          return
        end
      end
      hazard_dispatch_hits = hazard_dispatch_hits + 1
      if route_profile ~= "" then
        if route_pending then route_invalid = route_invalid + 1 end
        route_pending = true
      end
      if scene0b() then
        scene0b_hazard_dispatch_hits = scene0b_hazard_dispatch_hits + 1
      end
    end, 0x6CCE, 19)
    if route_profile ~= "" then
      assert(emu:setBreakpoint(function() dispatch_entry = nil end,
        0x6CD0, 19) > 0)
    end
    emu:setBreakpoint(function()
      hazard_helper_hits = hazard_helper_hits + 1
      if scene0b() then
        scene0b_hazard_helper_hits = scene0b_hazard_helper_hits + 1
      end
    end, 0x6BA7, 19)
    emu:setBreakpoint(function()
      hazard_pure_helper_hits = hazard_pure_helper_hits + 1
      if scene0b() then
        scene0b_hazard_pure_helper_hits =
          scene0b_hazard_pure_helper_hits + 1
      end
    end, 0x6BA8, 19)
    emu:setBreakpoint(function()
      hazard_front_hits = hazard_front_hits + 1
      finish_publication_route(false)
      if scene0b() then scene0b_hazard_front_hits = scene0b_hazard_front_hits + 1 end
    end, 0x61B7, 19)
    if route_profile ~= "" then
      assert(route_profile == "r440-bounded-room03")
      assert(emu:setBreakpoint(function()
        finish_publication_route(true)
      end, 0x6B81, 19) > 0)
    end
    -- Expanded candidates tail-map bank 20 and publish each matched semantic
    -- span through the real row owner at $4300.  The retired $61A8 probe was
    -- merely padding before the bank-19 classifier and could never prove a
    -- write occurred.
    emu:setBreakpoint(function()
      hazard_write_hits = hazard_write_hits + 1
      if scene0b() then scene0b_hazard_write_hits = scene0b_hazard_write_hits + 1 end
    end, 0x4300, 20)
    -- Room $01 uses r300's byte-equivalent helper clone at $4500 and LUT
    -- page $46. Counting only $4300 mislabeled correct room-local rows as
    -- missing semantic publications.
    emu:setBreakpoint(function()
      hazard_write_hits = hazard_write_hits + 1
      if scene0b() then scene0b_hazard_write_hits = scene0b_hazard_write_hits + 1 end
    end, 0x4500, 20)
    if route_profile ~= "" then
      -- Current expanded routes keep the semantic row writer in the
      -- bank-13 scanner tail; older candidates also retain the bank-20
      -- compiler entry points above.
      assert(emu:setBreakpoint(function()
        hazard_write_hits = hazard_write_hits + 1
        if scene0b() then
          scene0b_hazard_write_hits = scene0b_hazard_write_hits + 1
        end
      end, 0x6C8F, 13) > 0)
      -- mGBA's bank-qualified callback uses the mapped bank index for this
      -- fixed-window address on some Qt builds; retain the unqualified
      -- registration as an equivalent ABI witness, not as an oracle.
      assert(emu:setBreakpoint(function()
        hazard_write_hits = hazard_write_hits + 1
        if scene0b() then
          scene0b_hazard_write_hits = scene0b_hazard_write_hits + 1
        end
      end, 0x6C8F) > 0)
    end
    for _, address in ipairs({0xDF53, 0xDF57}) do
      local watched = address
      assert(emu:setRangeWatchpoint(function(info)
        local pc = 0
        pcall(function() pc = emu:getRegister("pc") end)
        local handle = assert(io.open(OUT .. ".cache-writes.tsv", "a"))
        handle:write(string.format(
          "%d\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
          frame, watched, pc & 0xFFFF, emu:read8(0xFF99),
          info.oldValue & 0xFF, info.newValue & 0xFF,
          emu:read8(0xD880), emu:read8(0xFFBD)))
        handle:close()
      end, watched, watched, C.WATCHPOINT_TYPE.WRITE) > 0)
    end
  end)
  -- Arm while SVBK1 still exposes authoritative scene state, then inspect the
  -- exact CALL $D400 opcode after fixed:$430B has selected SVBK3. Keep these
  -- registrations strict and outside the optional layout-breakpoint group.
  assert(emu:setBreakpoint(arm_resident_compiler_receipt, 0x4302, 1) > 0)
  assert(emu:setBreakpoint(inspect_resident_compiler_row, 0x4313, 1) > 0)
  if os.getenv("LOW_HEALTH_BULK_COMPILER") == "r426-bulk-v1" then
    assert(emu:setBreakpoint(inspect_bulk_completion, 0x4324, 1) > 0)
  end
  -- Optional read-only diagnostic of the completed compiler output. This
  -- observes both row-loop and bulk implementations without fabricating
  -- row-call counters or changing any readiness checks. The offline checker
  -- validates all 576 output cells against the captured source and LUT.
  if os.getenv("LOW_HEALTH_TRACE_COMPILED") == "1" then
    local compiled = assert(io.open(OUT .. ".compiled-attributes.bin", "wb"))
    compiled:close()
    assert(emu:setBreakpoint(function()
      assert((emu:read8(0xFF70) & 7) == 3)
      local snapshot = {}
      for _, region in ipairs({{0xC1A0,576},{0xC600,256},{0xD000,768},{0xD400,121}}) do
        for n = 0, region[2]-1 do
          snapshot[#snapshot+1] = string.char(emu:read8(region[1]+n))
        end
      end
      local handle = assert(io.open(OUT .. ".compiled-attributes.bin", "ab"))
      handle:write(table.concat(snapshot))
      handle:close()
    end, 0x4324, 1) > 0)
  end
  -- Promote the modeled plane only after the 48-block GDMA has completed and
  -- the compiler has restored VBK0/SVBK1. Pure-copy publications deliberately
  -- retain the prior expected plane because they do not publish attributes.
  assert(emu:setBreakpoint(publish_expected_plane, 0x4354, 1) > 0)
  assert(emu:setBreakpoint(function()
    runtime_gateway_hits = runtime_gateway_hits + 1
    if not resident_runtime_matches_candidate() then
      runtime_entry_mismatches = runtime_entry_mismatches + 1
      if scene0b() then
        runtime_scene0b_entry_mismatches =
          runtime_scene0b_entry_mismatches + 1
      end
    end
    if scene0b() then
      runtime_gateway_scene0b_hits = runtime_gateway_scene0b_hits + 1
    end
  end, 0xDAD7) > 0)
  assert(emu:setBreakpoint(function()
    split_consumer_hits = split_consumer_hits + 1
    if scene0b() then
      split_consumer_scene0b_hits = split_consumer_scene0b_hits + 1
    end
  end, 0x4100, 21) > 0)
  local relocated_decider = os.getenv("LOW_HEALTH_BULK_COMPILER") == "r426-bulk-v1"
  for _, address in ipairs(relocated_decider and {0x4122, 0x7E28} or {0x4128}) do
  assert(emu:setBreakpoint(function()
    decider_hit_hits = decider_hit_hits + 1
    if scene0b() then scene0b_decider_hit_hits = scene0b_decider_hit_hits + 1 end
  end, address, 21) > 0)
  end
  for _, address in ipairs(relocated_decider and {0x4127, 0x7E2D} or {0x412D}) do
  assert(emu:setBreakpoint(function()
    decider_sentinel_hits = decider_sentinel_hits + 1
    if scene0b() then
      scene0b_decider_sentinel_hits = scene0b_decider_sentinel_hits + 1
    end
  end, address, 21) > 0)
  end
  for _, address in ipairs(relocated_decider and {0x412E, 0x7E39} or {0x4139}) do
  assert(emu:setBreakpoint(function()
    decider_dirty_hits = decider_dirty_hits + 1
    if scene0b() then
      scene0b_decider_dirty_hits = scene0b_decider_dirty_hits + 1
    end
  end, address, 21) > 0)
  end
  assert(emu:setBreakpoint(function()
    wall_helper_hits = wall_helper_hits + 1
    if scene0b() then
      scene0b_wall_helper_hits = scene0b_wall_helper_hits + 1
    end
  end, 0x6C80, 21) > 0)
end

local register

if TRACE_ATTR then
  local attr_trace = assert(io.open(OUT .. ".attr-writes.tsv", "w"))
  attr_trace:write("frame\taddress\tpc\tbank\tvbk\told\tnew\tlcdc\td880\troom\n")
  attr_trace:close()
  local row_trace = assert(io.open(OUT .. ".semantic-row-inputs.tsv", "w"))
  row_trace:write("frame\thl\tde\tcount\tsource_tiles\tdestination_tiles\n")
  row_trace:close()
  assert(emu:setBreakpoint(function()
    local hl, de, count = register("HL"), register("DE"), register("BC") & 255
    assert(count > 0 and count <= 32 and hl >= 0x9800 and hl < 0xA000)
    local source, destination = {}, {}
    for i=0,count-1 do
      source[#source+1]=string.format("%02X",emu:read8(de+i))
      destination[#destination+1]=string.format("%02X",emu.memory.vram:read8(hl-0x8000+i))
    end
    local handle=assert(io.open(OUT .. ".semantic-row-inputs.tsv", "a"))
    handle:write(string.format("%d\t%04X\t%04X\t%d\t%s\t%s\n",
      frame,hl,de,count,table.concat(source),table.concat(destination)))
    handle:close()
  end,0x4300,20)>0)
end

register = function(name)
  local readers = {
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:getRegister(string.upper(name)) end,
    function() return emu:readRegister(string.lower(name)) end,
    function() return emu:readRegister(string.upper(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value then return value end
  end
  return 0xFFFF
end

if WATCH_COMPILER_HANG then
  -- The postcomputed Stage-1 publisher starts HDMA5 at $4346 and polls it at
  -- $4348 until bit 7 reports completion.  A real transfer completes within
  -- a bounded number of polls.  Stop a wedged transfer ourselves so this
  -- diagnostic produces an exact machine-state receipt instead of relying on
  -- a wall-clock timeout (which loses the owning PC and hardware registers).
  local launches, completions, wait_polls = 0, 0, 0
  local watchdog = assert(io.open(OUT .. ".compiler-watchdog.tsv", "w"))
  watchdog:write(
    "event\tframe\tsample\tpc\tbank\taf\tbc\tde\thl\tsp" ..
    "\tlcdc\tstat\tly\tif\tie\tvbk\tsvbk\thdma1\thdma2\thdma3" ..
    "\thdma4\thdma5\tffa5\tffe0\td880\tffc1\troom\tpolls\n")
  watchdog:close()

  local function watchdog_record(event)
    local handle = assert(io.open(OUT .. ".compiler-watchdog.tsv", "a"))
    handle:write(string.format(
      "%s\t%d\t%d\t%04X\t%02X\t%04X\t%04X\t%04X\t%04X\t%04X" ..
      "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
      "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\n",
      event, frame, sample, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, register("SP") & 0xFFFF,
      emu:read8(0xFF40), emu:read8(0xFF41), emu:read8(0xFF44),
      emu:read8(0xFF0F), emu:read8(0xFFFF), emu:read8(0xFF4F),
      emu:read8(0xFF70), emu:read8(0xFF51), emu:read8(0xFF52),
      emu:read8(0xFF53), emu:read8(0xFF54), emu:read8(0xFF55),
      emu:read8(0xFFA5), emu:read8(0xFFE0), emu:read8(0xD880),
      emu:read8(0xFFC1), emu:read8(0xFFBD), wait_polls))
    handle:close()
  end

  assert(emu:setBreakpoint(function()
    launches = launches + 1
    wait_polls = 0
    watchdog_record("launch")
  end, 0x4346, 1) > 0)
  assert(emu:setBreakpoint(function()
    wait_polls = wait_polls + 1
    if wait_polls == 1 then watchdog_record("wait") end
    if wait_polls >= 4096 then
      watchdog_record("wedged")
      local marker = assert(io.open(OUT .. ".compiler-watchdog.wedged", "w"))
      marker:write(string.format(
        "launches=%d\ncompletions=%d\npolls=%d\n",
        launches, completions, wait_polls))
      marker:close()
      os.exit(86)
    end
  end, 0x4348, 1) > 0)
  assert(emu:setBreakpoint(function()
    completions = completions + 1
    watchdog_record("complete")
    wait_polls = 0
  end, 0x434E, 1) > 0)

  -- If HDMA completes but the next VBlank still never arrives, retain the
  -- exact post-copy route.  The row/predicate thresholds are deliberately far
  -- above the bounded 24-row scanner so an actual loop self-terminates with a
  -- receipt while normal publications only add a handful of diagnostic rows.
  local postcopy_active, scanner_rows, predicate_hits = false, 0, 0
  local writer_mode3_polls, writer_mode0_polls = 0, 0
  -- Boot-derived hazard states already have a settled publication corpus;
  -- arm route evidence at the sampled boundary.  The legacy normalized
  -- fixture retains the historical frame guard to exclude its title/boot
  -- startup churn.
  local route_min_frame = BOOT_STATE and SETTLE or 389
  local function route(event)
    if frame < route_min_frame then return end
    watchdog_record(event)
  end
  assert(emu:setBreakpoint(function()
    postcopy_active, scanner_rows, predicate_hits = true, 0, 0
    route("postcopy-call-pure")
  end, 0x42F7, 1) > 0)
  assert(emu:setBreakpoint(function()
    postcopy_active, scanner_rows, predicate_hits = true, 0, 0
    route("postcopy-call-dirty")
  end, 0x4354, 1) > 0)
  assert(emu:setBreakpoint(function() route("guard") end, 0xDBF1) > 0)
  assert(emu:setBreakpoint(function() route("fixed-owner") end,
    0x10E2, 0) > 0)
  assert(emu:setBreakpoint(function() route("mapper") end, 0x0847, 0) > 0)
  assert(emu:setBreakpoint(function() route("private-entry") end,
    0x6C80, 19) > 0)
  assert(emu:setBreakpoint(function() route("dispatch") end,
    0x6CCE, 19) > 0)
  assert(emu:setBreakpoint(function() route("helper") end,
    0x6BA7, 19) > 0)
  assert(emu:setBreakpoint(function() route("scanner") end,
    0x61B7, 19) > 0)
  assert(emu:setBreakpoint(function()
    scanner_rows = scanner_rows + 1
    if scanner_rows == 1 or scanner_rows == 2 or scanner_rows == 24
        or scanner_rows >= 64 then
      route("scanner-row-" .. scanner_rows)
    end
    if scanner_rows >= 64 then
      local marker = assert(io.open(
        OUT .. ".compiler-watchdog.wedged", "w"))
      marker:write(string.format(
        "reason=scanner-row-loop\nrows=%d\npredicates=%d\n",
        scanner_rows, predicate_hits))
      marker:close()
      os.exit(87)
    end
  end, 0x61BC, 19) > 0)
  assert(emu:setBreakpoint(function()
    predicate_hits = predicate_hits + 1
    if predicate_hits == 1 or predicate_hits == 256
        or predicate_hits == 1024 or predicate_hits >= 16384 then
      route("predicate-" .. predicate_hits)
    end
    if predicate_hits >= 16384 then
      local marker = assert(io.open(
        OUT .. ".compiler-watchdog.wedged", "w"))
      marker:write(string.format(
        "reason=predicate-loop\nrows=%d\npredicates=%d\n",
        scanner_rows, predicate_hits))
      marker:close()
      os.exit(88)
    end
  end, 0x6C88, 19) > 0)
  assert(emu:setBreakpoint(function()
    writer_mode3_polls, writer_mode0_polls = 0, 0
    route("semantic-writer")
  end, 0x4300, 20) > 0)
  assert(emu:setBreakpoint(function()
    writer_mode3_polls = writer_mode3_polls + 1
    if writer_mode3_polls == 1 or writer_mode3_polls == 256
        or writer_mode3_polls >= 4096 then
      route("writer-mode3-" .. writer_mode3_polls)
    end
    if writer_mode3_polls >= 4096 then
      local marker = assert(io.open(
        OUT .. ".compiler-watchdog.wedged", "w"))
      marker:write(string.format(
        "reason=writer-mode3-loop\nmode3_polls=%d\nmode0_polls=%d\n",
        writer_mode3_polls, writer_mode0_polls))
      marker:close()
      os.exit(89)
    end
  end, 0x431F, 20) > 0)
  assert(emu:setBreakpoint(function()
    writer_mode0_polls = writer_mode0_polls + 1
    if writer_mode0_polls == 1 or writer_mode0_polls == 256
        or writer_mode0_polls >= 4096 then
      route("writer-mode0-" .. writer_mode0_polls)
    end
    if writer_mode0_polls >= 4096 then
      local marker = assert(io.open(
        OUT .. ".compiler-watchdog.wedged", "w"))
      marker:write(string.format(
        "reason=writer-mode0-loop\nmode3_polls=%d\nmode0_polls=%d\n",
        writer_mode3_polls, writer_mode0_polls))
      marker:close()
      os.exit(90)
    end
  end, 0x4327, 20) > 0)
  assert(emu:setBreakpoint(function() route("semantic-writer-done") end,
    0x435D, 20) > 0)
  assert(emu:setBreakpoint(function() route("semantic-bridge") end,
    0x6CDF, 20) > 0)
  assert(emu:setBreakpoint(function() route("private-continuation") end,
    0x6CE4, 19) > 0)
  assert(emu:setBreakpoint(function() route("scanner-tail") end,
    0x61F6, 19) > 0)
  assert(emu:setBreakpoint(function() route("tail-after-pop-hl") end,
    0x61F7, 19) > 0)
  assert(emu:setBreakpoint(function() route("tail-after-pop-de") end,
    0x61F8, 19) > 0)
  assert(emu:setBreakpoint(function() route("tail-after-pop-bc") end,
    0x61F9, 19) > 0)
  assert(emu:setBreakpoint(function() route("tail-dec-row") end,
    0x6207, 19) > 0)
  assert(emu:setBreakpoint(function() route("tail-branch-row") end,
    0x6208, 19) > 0)
  assert(emu:setBreakpoint(function() route("tail-repair") end,
    0x620B, 19) > 0)
  assert(emu:setBreakpoint(function()
    route("private-exit")
    postcopy_active = false
  end, 0x6C50, 19) > 0)
  assert(emu:setBreakpoint(function()
    route("postcopy-return")
    postcopy_active = false
  end, 0x4357, 1) > 0)
end

local writes = assert(io.open(OUT .. ".writes.tsv", "w"))
writes:write("frame\tpc\tbank\told\tnew\tly\tstat\td880\tffc1\thp_sub\thp_main\n")
writes:close()

if TRACE_SCANNER then
  local scanner_trace = assert(io.open(OUT .. ".scanner.tsv", "w"))
  scanner_trace:write(
    "frame\tsample\tpoint\tpath\tpc\tbank\thl\tbc\tde\tsp\tstack0\tstack1" ..
    "\tscene\troom\tffe5\tdc0b\tdc0e\tvbk\tly\tstat\tlcdc\tffe0\n")
  scanner_trace:close()
end

if TRACE_ATTR then
  local dma_trace = assert(io.open(OUT .. ".attribute-dma.tsv", "w"))
  dma_trace:write("frame\tpc\tbank\tsource\tdestination\tlength_register\tvbk\tsvbk\tscene\troom\n")
  dma_trace:close()
  local store_frame_start = tonumber(os.getenv("LOW_HEALTH_STORE_FRAME_START") or "300")
  local store_frame_end = tonumber(os.getenv("LOW_HEALTH_STORE_FRAME_END") or "315")
  local store_address_start = tonumber(os.getenv("LOW_HEALTH_STORE_ADDRESS_START") or "40064")
  local store_address_end = tonumber(os.getenv("LOW_HEALTH_STORE_ADDRESS_END") or "40127")
  for bank, address, opcode in string.gmatch(os.getenv("LOW_HEALTH_STORE_SITES") or "", "(%d+):(%d+):(%d+)") do
    local destination_register = tonumber(opcode) == 0x12 and "DE" or "HL"
    assert(emu:setBreakpoint(function()
      if frame < store_frame_start or frame > store_frame_end
          or (emu:read8(0xFF4F) & 1) == 0 then return end
      local destination = register(destination_register)
      if destination < store_address_start or destination > store_address_end then return end
      local handle = assert(io.open(OUT .. ".recovery-stores.tsv", "a"))
      local source = register("DE")
      local vram = assert(emu.memory.vram)
      handle:write(string.format("%d\t%02X\t%04X\t%04X\t%02X\t%02X\t%04X\t%02X\t%02X\t%02X\n",
        frame, emu:read8(0xFF99), register("PC"), destination,
        emu:read8(destination), (register("AF") >> 8) & 255,
        source, emu:read8((source-1)&0xFFFF), emu:read8(source),
        vram:read8(destination-0x8000)))
      handle:close()
    end, tonumber(address), tonumber(bank)) > 0)
  end
  assert(emu:setBreakpoint(function()
    if frame < 280 or frame > 640 then return end
    local sp = register("SP")
    local words = {}
    for i = 0, 14, 2 do
      words[#words + 1] = string.format("%04X",
        emu:read8(sp + i) | (emu:read8(sp + i + 1) << 8))
    end
    local handle = assert(io.open(OUT .. ".wait-stack.tsv", "a"))
    handle:write(string.format("%d\t%04X\t%s\n", frame, sp, table.concat(words, ",")))
    handle:close()
  end, 0x406F, 1) > 0)
  local function trace_dma_launch(value)
    local handle = assert(io.open(OUT .. ".attribute-dma.tsv", "a"))
    handle:write(string.format("%d\t%04X\t%02X\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
      frame, register("PC"), emu:read8(0xFF99),
      (emu:read8(0xFF51) << 8) | (emu:read8(0xFF52) & 0xF0),
      0x8000 | ((emu:read8(0xFF53) & 0x1F) << 8) | (emu:read8(0xFF54) & 0xF0),
      value & 0xFF, emu:read8(0xFF4F), emu:read8(0xFF70),
      emu:read8(0xD880), emu:read8(0xFFBD)))
    handle:close()
  end
  for bank, address in string.gmatch(os.getenv("LOW_HEALTH_DMA_SITES") or "", "(%d+):(%d+)") do
    assert(emu:setBreakpoint(function()
      trace_dma_launch((register("AF") >> 8) & 0xFF)
    end, tonumber(address), tonumber(bank)) > 0)
  end
  -- Native menu/window attribute copier. Observe the actual stores because
  -- mGBA watchpoints do not report these writes in the current runner.
  for _, address in ipairs({0x4068, 0x406A}) do
    assert(emu:setBreakpoint(function()
      local destination = register("HL")
      local handle = assert(io.open(OUT .. ".attr-writes.tsv", "a"))
      handle:write(string.format("%d\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
        frame, destination, register("PC"), emu:read8(0xFF99),
        emu:read8(0xFF4F), emu:read8(destination),
        (register("AF") >> 8) & 0xFF, emu:read8(0xFF40),
        emu:read8(0xD880), emu:read8(0xFFBD)))
      handle:close()
    end, address, 20) > 0)
  end
  -- Include the two legacy wall probes plus representative floor/ceiling
  -- tooth cells.  The latter make a verifier-side or runtime broad-LUT clear
  -- visible instead of reporting only its eventual rendered symptom.
  for _, address in ipairs({
      0x9840, 0x9841, 0x98A0, 0x9C40, 0x9C41, 0x9CA0,
      0x998D, 0x9D10,
      0x9C82, 0x9C83, 0x9C89, 0x9C8B, 0x9C91, 0x9CA2,
      0x9CA4, 0x9CA5, 0x9CAB, 0x9CB0, 0x9CB1,
  }) do
    local watched = address
    assert(emu:setRangeWatchpoint(function(info)
      local handle = assert(io.open(OUT .. ".attr-writes.tsv", "a"))
      handle:write(string.format(
        "%d\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
        frame, watched, register("PC") & 0xFFFF, emu:read8(0xFF99),
        emu:read8(0xFF4F), info.oldValue & 0xFF, info.newValue & 0xFF,
        emu:read8(0xFF40), emu:read8(0xD880), emu:read8(0xFFBD)))
      handle:close()
    end, watched, watched, C.WATCHPOINT_TYPE.WRITE) > 0)
  end
end

local function trace_scanner(point, path)
  -- Every caller below is already registered with an exact ROM-bank segment.
  -- The retired global FF99==$0E filter rejected the real bank-$13 scanner
  -- and bank-$14 semantic writer, leaving the supposed route receipt empty.
  if not TRACE_SCANNER or scanner_trace_count >= TRACE_SCANNER_LIMIT then
    return
  end
  if path then scanner_path = path end
  local sp = register("SP") & 0xFFFF
  local handle = assert(io.open(OUT .. ".scanner.tsv", "a"))
  handle:write(string.format(
    "%d\t%d\t%s\t%s\t%04X\t%02X\t%04X\t%04X\t%04X\t%04X\t%04X\t%04X" ..
    "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
    frame, sample, point, scanner_path, register("PC") & 0xFFFF,
    emu:read8(0xFF99), register("HL") & 0xFFFF,
    register("BC") & 0xFFFF, register("DE") & 0xFFFF, sp,
    emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8),
    emu:read8((sp + 2) & 0xFFFF) |
      (emu:read8((sp + 3) & 0xFFFF) << 8),
    emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFFE5),
    emu:read8(0xDC0B), emu:read8(0xDC0E), emu:read8(0xFF4F),
    emu:read8(0xFF44), emu:read8(0xFF41), emu:read8(0xFF40),
    emu:read8(0xFFE0)))
  handle:close()
  scanner_trace_count = scanner_trace_count + 1
end

if TRACE_SCANNER then
  pcall(function()
    emu:setBreakpoint(function() trace_scanner("map9c", "map") end, 0x42A0, 1)
    emu:setBreakpoint(function() trace_scanner("map98", "map") end, 0x42A5, 1)
    emu:setBreakpoint(function() trace_scanner("decision", "map") end, 0x3485, 0)
    emu:setBreakpoint(function() trace_scanner("postcopy", "map") end, 0x10E2, 0)
    emu:setBreakpoint(function() trace_scanner("source-ret", "source") end, 0x13E4, 0)
    emu:setBreakpoint(function() trace_scanner("helper", "helper") end, 0x6BA7, 19)
    emu:setBreakpoint(function() trace_scanner("dispatch", "dispatch") end, 0x6CCE, 19)
    emu:setBreakpoint(function() trace_scanner("front", "entry") end, 0x61B7, 19)
    emu:setBreakpoint(function() trace_scanner("start4", "start4") end, 0x618F, 19)
    emu:setBreakpoint(function() trace_scanner("start5", "start5") end, 0x6194, 19)
    emu:setBreakpoint(function() trace_scanner("start0", "start0") end, 0x619E, 19)
    emu:setBreakpoint(function() trace_scanner("seam", "seam") end, 0x6CE9, 19)
    emu:setBreakpoint(function() trace_scanner("semantic-writer", nil) end,
      0x4300, 20)
    emu:setBreakpoint(function()
      hazard_write_hits = hazard_write_hits + 1
      if scene0b() then
        scene0b_hazard_write_hits = scene0b_hazard_write_hits + 1
      end
      trace_scanner("writer", nil)
    end, 0x6C8F, 19)
    emu:setBreakpoint(function() trace_scanner("tail", nil) end, 0x61F6, 19)
    -- This is the post-$0B7E room-commit hook.  Capture the exact LCD phase
    -- so an active-map repair may be accepted only when it can finish before
    -- another visible scanline, rather than inferring timing from frames.
    emu:setBreakpoint(function() trace_scanner("room-hook", "room") end,
      0x6C80, 21)
  end)
  pcall(function()
    emu:setRangeWatchpoint(function()
      trace_scanner("hdma5", "dma")
    end, 0xFF55)
  end)
end

if WATCH_BGP then
  assert(emu:setRangeWatchpoint(function(info)
    local handle = assert(io.open(OUT .. ".writes.tsv", "a"))
    handle:write(string.format(
      "%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
      frame, register("PC") & 0xFFFF, emu:read8(0xFF99),
      info.oldValue & 0xFF, info.newValue & 0xFF,
      emu:read8(0xFF44), emu:read8(0xFF41), emu:read8(0xD880),
      emu:read8(0xFFC1), emu:read8(0xDCDC), emu:read8(0xDCDD)))
    handle:close()
  end, 0xFF47, 0xFF48, C.WATCHPOINT_TYPE.WRITE) > 0)
end

local function palette_bytes(accessor_name, index_port, data_port)
  local accessor = emu.memory[accessor_name]
  if accessor then return accessor:readRange(0, 64) end
  local old_index = emu:read8(index_port)
  local result = {}
  for index = 0, 63 do
    emu:write8(index_port, index)
    result[#result + 1] = string.char(emu:read8(data_port))
  end
  emu:write8(index_port, old_index)
  return table.concat(result)
end

local function hex_bytes(raw)
  return (raw:gsub(".", function(char)
    return string.format("%02X", string.byte(char))
  end))
end

local function source_hazard_rows()
  local rows = {}
  for row = 0, 23 do
    local first, last, count = 24, -1, 0
    local tiles = {}
    for column = 0, 23 do
      local tile = emu:read8(0xC1A0 + row * 24 + column)
      tiles[#tiles + 1] = string.format("%02X", tile)
      local folded = tile & 0xEF
      if folded >= 0x64 and folded < 0x6A then
        first, last, count = math.min(first, column), column, count + 1
      end
    end
    if count > 0 then
      rows[#rows + 1] = string.format("%02X/%02X/%02X/%02X/%s",
        row, first, last, count, table.concat(tiles))
    end
  end
  return table.concat(rows, ",")
end

local function destination_hazard_rows()
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local old_vbk = emu:read8(0xFF4F)
  local rows = {}
  emu:write8(0xFF4F, 0)
  for row = 0, 23 do
    local first, last, count = 32, -1, 0
    local tiles = {}
    for column = 0, 31 do
      local tile = emu:read8(base + row * 32 + column)
      tiles[#tiles + 1] = string.format("%02X", tile)
      local folded = tile & 0xEF
      if folded >= 0x64 and folded < 0x6A then
        first, last, count = math.min(first, column), column, count + 1
      end
    end
    if count > 0 then
      rows[#rows + 1] = string.format("%02X/%02X/%02X/%02X/%s",
        row, first, last, count, table.concat(tiles))
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(rows, ",")
end

local function hazard_positions(read_tile)
  local positions = {}
  local function tooth(column, row)
    local tile = read_tile(column, row) & 0xEF
    return tile >= 0x64 and tile < 0x6A
  end
  for row = 0, 23 do
    local start, width
    if tooth(0, row) or tooth(1, row)
        or tooth(2, row) or tooth(3, row) then
      -- Left-shifted room03 phases include teeth at 2/3 and extend through
      -- column 13. Captured physical rows retain the same cylinder body
      -- and neutral endpoints; a 0/1-only discriminator misses that phase.
      start, width = 0, 14
    elseif read_tile(4, row) == 0x6A
        or tooth(4, row) or tooth(5, row) or tooth(6, row)
        or tooth(7, row) or tooth(9, row) or tooth(10, row) then
      -- The translated cylinder has left-4 and right-8 phases (native
      -- classifier witnesses at 4/5/6/7/9/10). Inspect their full union,
      -- including retracted endpoints, not only the current tooth positions.
      -- Membership never grants bank 1: the per-cell oracle below still
      -- requires an actual 64..69/74..79 tooth and raw attribute 0F.
      start, width = 4, 14
    end
    if start then
      for column = start, start + width - 1 do
        positions[row * 32 + column] = true
      end
    end
  end
  return positions
end

local function bind_cross_rom_fixture_hazards()
  if BOOT_STATE then
    local receipt = assert(io.open(OUT .. ".fixture-tooth-rebind.txt", "w"))
    receipt:write("9800=0\n9C00=0\n")
    receipt:close()
    return
  end
  -- The Python normalizer restarts old cross-ROM fixtures through the current
  -- cold helper installer.  That installer can republish the already-active
  -- map before the three immutable-art DMAs finish, an ordering that cannot
  -- occur on the real title -> STAGE 01 path.  Establish the intended test
  -- precondition once, on the final unobserved settle frame: only actual
  -- geometry-qualified tooth cells receive BG7/bank 1.  Every subsequent
  -- low-health, movement, map-copy, and miniboss frame remains unmodified and
  -- is checked by visible_bg_receipt below.
  local old_vbk = emu:read8(0xFF4F)
  local changed = {}
  for _, base in ipairs({0x9800, 0x9C00}) do
    emu:write8(0xFF4F, 0)
    local tiles = {}
    for offset = 0, 0x3FF do tiles[offset] = emu:read8(base + offset) end
    local positions = hazard_positions(function(column, row)
      return tiles[row * 32 + column]
    end)
    emu:write8(0xFF4F, 1)
    local count = 0
    for offset, _ in pairs(positions) do
      local tile = tiles[offset]
      local folded = tile & 0xEF
      if folded >= 0x64 and folded < 0x6A then
        if emu:read8(base + offset) ~= 0x0F then count = count + 1 end
        emu:write8(base + offset, 0x0F)
      end
    end
    changed[base] = count
  end
  emu:write8(0xFF4F, old_vbk)
  local receipt = assert(io.open(OUT .. ".fixture-tooth-rebind.txt", "w"))
  receipt:write(string.format(
    "9800=%d\n9C00=%d\n", changed[0x9800], changed[0x9C00]))
  receipt:close()
end

local function visible_bg_receipt()
  local lcdc = emu:read8(0xFF40)
  local scy, scx = emu:read8(0xFF42), emu:read8(0xFF43)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local room = emu:read8(0xFFBD)
  local publication = published_expected_planes[base]
  local old_vbk = emu:read8(0xFF4F)
  local tiles, all_tiles, tile_bytes, attr_bytes, mismatches,
    unexpected_mismatches, unsafe, approved_bank1, oracle_missing =
    {}, {}, {}, {}, 0, 0, 0, 0, 0
  local mismatch_details = {}
  local histogram = {0, 0, 0, 0, 0, 0, 0, 0}
  emu:write8(0xFF4F, 0)
  all_tiles = {}
  for offset = 0, 0x3FF do all_tiles[offset] = emu:read8(base + offset) end
  local hazard_cells = hazard_positions(function(column, row)
    return all_tiles[row * 32 + column]
  end)
  emu:write8(0xFF4F, 1)
  local visible_rows = (scy & 0x07) == 0 and 18 or 19
  local visible_columns = (scx & 0x07) == 0 and 20 or 21
  for row = 0, visible_rows - 1 do
    for column = 0, visible_columns - 1 do
      local map_y = ((scy >> 3) + row) & 0x1F
      local map_x = ((scx >> 3) + column) & 0x1F
      local offset = map_y * 32 + map_x
      tiles[offset] = all_tiles[offset]
    end
  end
  for row = 0, visible_rows - 1 do
    for column = 0, visible_columns - 1 do
      local map_y = ((scy >> 3) + row) & 0x1F
      local map_x = ((scx >> 3) + column) & 0x1F
      local offset = map_y * 32 + map_x
      local attr = emu:read8(base + offset)
      tile_bytes[#tile_bytes + 1] = string.char(tiles[offset])
      attr_bytes[#attr_bytes + 1] = string.char(attr)
      local palette = attr & 0x07
      histogram[palette + 1] = histogram[palette + 1] + 1
      local tile = tiles[offset]
      local expected_hazard = nil
      if hazard_cells[offset]
          and ((tile >= 0x64 and tile <= 0x69)
          or (tile >= 0x74 and tile <= 0x79)) then
        expected_hazard = 0x0F
      elseif hazard_cells[offset] and tile >= 0x01 and tile <= 0x04 then
        expected_hazard = 0x00
      elseif hazard_cells[offset]
          and (tile == 0x60 or tile == 0x61 or tile == 0x62
          or tile == 0x6B or tile == 0x6F
          or tile == 0x6C or tile == 0x6D or tile == 0x6E
          or tile == 0x70 or tile == 0x71 or tile == 0x72
          or tile == 0x7B or tile == 0x7F
          or tile == 0x7C or tile == 0x7D or tile == 0x7E) then
        expected_hazard = 0x05
      elseif hazard_cells[offset] and tile >= 0x60 and tile <= 0x7F then
        expected_hazard = 0x06
      end
      -- Never derive the hazard oracle from mutable C600. Scene detection
      -- copies that page over many cycles during the $02->$0A warning handoff,
      -- and the former whole-span rule actively blessed yellow neutral trails.
      if expected_hazard ~= nil then
        if attr == expected_hazard then
          if expected_hazard == 0x0F then
            approved_bank1 = approved_bank1 + 1
          end
        else
          mismatches = mismatches + 1
          unexpected_mismatches = unexpected_mismatches + 1
          if (attr & 0xF8) ~= 0 and expected_hazard ~= 0x0F then
            unsafe = unsafe + 1
          end
          if #mismatch_details < 16 then
            mismatch_details[#mismatch_details + 1] = string.format(
              "%03X:%02X/%02X/%02X", offset, tile, attr, expected_hazard)
          end
        end
      else
        -- The north seam's two translated metallic wall edges are not owned
        -- by the raw per-tile LUT. Their bounded runtime repair is the exact
        -- Stage-1 BG6 authority documented by the room-$12 wall receipt.
        local semantic_wall =
          (offset == 0x18D or offset == 0x1AD) and
          (tile == 0x21 or tile == 0x31) and attr == 0x06
        if (attr & 0xF8) ~= 0 then
          unsafe = unsafe + 1
          if #mismatch_details < 16 then
            mismatch_details[#mismatch_details + 1] = string.format(
              "%03X:%02X/%02X/unsafe", offset, tiles[offset], attr)
          end
        end
        -- Ordinary cells are compared with the independent, SHA-pinned
        -- semantic plane modeled for the last completed compiler publication
        -- of this physical map. Never consult live C600 here: FFBD/FFE5 and
        -- C600 may already describe an incoming room while the old map is
        -- still the one being displayed, and a bad LUT must not grade itself.
        local expected = publication and publication.expected[offset] or nil
        if expected == nil then
          oracle_missing = oracle_missing + 1
          mismatches = mismatches + 1
          unexpected_mismatches = unexpected_mismatches + 1
          if #mismatch_details < 16 then
            mismatch_details[#mismatch_details + 1] = string.format(
              "%03X:%02X/%02X/unowned", offset, tiles[offset], attr)
          end
        elseif palette ~= expected then
          mismatches = mismatches + 1
          local semantic_hazard =
            ((tiles[offset] >= 0x4C and tiles[offset] <= 0x4F) or
             (tiles[offset] >= 0x5C and tiles[offset] <= 0x5F)) and
            palette == 5 and expected == 0
          local legacy =
            ((tiles[offset] >= 0x2A and tiles[offset] <= 0x2E) or
             (tiles[offset] >= 0x3A and tiles[offset] <= 0x3D)) and
            palette == 0 and expected == 5
          if not semantic_hazard and not legacy and not semantic_wall then
            unexpected_mismatches = unexpected_mismatches + 1
          end
          if #mismatch_details < 16 then
            mismatch_details[#mismatch_details + 1] = string.format(
              "%03X:%02X/%d/%d", offset, tiles[offset], palette, expected)
          end
        end
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return base, publication and 1 or 0,
    publication and publication.epoch or 0,
    publication and publication.publish_frame or 0,
    publication and publication.room or 0xFF,
    publication and publication.ffe5 or 0xFF,
    oracle_missing, mismatches, unexpected_mismatches,
    table.concat(mismatch_details, ","), unsafe,
    approved_bank1, table.concat(histogram, ","),
    hex_bytes(table.concat(tile_bytes)), hex_bytes(table.concat(attr_bytes))
end

local function resident_runtime()
  -- Authenticate physical bank 1, even when the CPU bus is banked away or
  -- unavailable during DMA. This observation must not change SVBK.
  local wram = assert(emu.memory.wram)
  local bytes = {}
  for offset = 0, 0x28 do
    bytes[#bytes + 1] = string.char(wram:read8(0x1AD7 + offset))
  end
  return table.concat(bytes)
end

local runtime_checked = false
local function bind_candidate_runtime()
  local actual = resident_runtime()
  local matched = actual == runtime_a and "bank13" or
    (actual == runtime_b and "bank16" or "none")
  local mismatch_a, mismatch_b = 0, 0
  for index = 1, #actual do
    if string.byte(actual, index) ~= string.byte(runtime_a, index) then
      mismatch_a = mismatch_a + 1
    end
    if string.byte(actual, index) ~= string.byte(runtime_b, index) then
      mismatch_b = mismatch_b + 1
    end
  end
  local handle = assert(io.open(OUT .. ".runtime.txt", "w"))
  handle:write("matched_source=" .. matched .. "\n")
  handle:write(string.format("mismatch_bank13=%d\n", mismatch_a))
  handle:write(string.format("mismatch_bank16=%d\n", mismatch_b))
  handle:write("actual_hex=" .. hex_bytes(actual) .. "\n")
  handle:close()
  runtime_checked = true
end

local trace = assert(io.open(OUT .. ".frames.tsv", "w"))
trace:write(
  "sample\tframe\thealth_phase\tpc\tdma_source\tdma_unreadable\tcompiler_unreadable\td880\tffc1\troom\tffe5\tscy\tdc0b\tdc0e\tdcfd\thazard_rows\tdestination_hazard_rows\thp_sub\thp_main\td887\td885\td888\tbggate\tbgp\tfff7\tffe2\tffe3" ..
    "\tmap\tmap_owner_valid\tmap_owner_epoch\tmap_owner_frame" ..
    "\tmap_owner_room\tmap_owner_ffe5\toracle_missing" ..
    "\tmismatches\tunexpected_mismatches\tmismatch_details" ..
  "\tunsafe\tapproved_bank1\tattrs\ttile_bytes\tattr_bytes\tbg_cram" ..
  "\tstimulus_phase\tdcbb\tdd06\tffb7\tffbf\tffba" ..
  "\tc624\tc627\tc630\tc633\tdf53\tdf57\tffe0\tffa5\trom_bank\twram_bank\tscx\tcpu_a\tstack_return\n")
trace:close()

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  if TRACE_ATTR then
    local handle = assert(io.open(OUT .. ".frame-pc.tsv", "a"))
    handle:write(string.format("%d\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\n",
      frame, emu:read8(0xFF99), register("PC"), emu:read8(0xFF4F),
      emu:read8(0xFF70), emu:read8(0xFF40), emu:read8(0xDF5B)))
    handle:close()
  end
  if TRACE_SCANNER then
    local frame_pc = register("PC") & 0xFFFF
    if frame_pc >= 0x13AA and frame_pc <= 0x13E4 then
      trace_scanner("source-frame", "source")
    end
  end
  if not BOOT_STATE and frame <= SETTLE and emu:read8(0xD880) == 0x02 then
    emu:write8(0xDF0D, 0x02)
  end
  if frame == SETTLE then
    bind_cross_rom_fixture_hazards()
    bind_candidate_runtime()
  end
  local post_trigger_frame = frame - SETTLE - PRE_TRIGGER
  if emu:read8(0xD880) == 0x0A then music_transition_seen = true end
  -- Movement exists only to force a real publication. In the scene-$0B
  -- profile, release it as soon as the fixed post-copy owner runs under $0B;
  -- continuing for another ~35 frames lets this fragile fixture take damage
  -- and promotes DD06 independently of the DCBB evaluator. The legacy music
  -- profile still releases on its first native $0A frame.
  local drive_publication = not music_transition_seen
  if REQUIRE_SCENE0B then
    drive_publication = scene0b_postcopy_hits == 0 or
      (post_trigger_frame > SCENE0B_FRAMES
       and post_trigger_frame <= SCENE0B_FRAMES + RECOVERY_DRIVE_FRAMES)
  end
  local displayed_map = (emu:read8(0xFF40) & 8) ~= 0 and 0x9C00 or 0x9800
  local settling_unowned = frame <= SETTLE
    and (frame <= SETTLE_DRIVE_FRAMES or published_expected_planes[displayed_map] == nil)
  emu:setKeys(settling_unowned and SETTLE_KEYS
    or (post_trigger_frame > 0 and drive_publication and POST_TRIGGER_KEYS or 0))
  -- #37: all profiles use native health, never the inventory cursor pair.
  -- The bounded profile additionally verifies recovery; the default holds
  -- the warning tier through the rest of the requested observation window.
  local stimulus_phase = "pre"
  if REQUIRE_SCENE0B then
    if post_trigger_frame <= 0 then
      native_assistance.write(0xDCBB, 0xFF)
      stimulus_phase = "pre"
    elseif post_trigger_frame <= SCENE0B_FRAMES then
      -- DCBB is the native health pool consumed by bank1:$5050.  Do not
      -- inject DD06 or D880. $40 selects the warning tier, so the native
      -- evaluator must publish DD06=$01 and D880=$0B before the movement-
      -- driven room copy begins, then clear both after DCBB is restored.
      native_assistance.write(0xDCBB, SCENE0B_HEALTH)
      stimulus_phase = "scene0b"
    else
      native_assistance.write(0xDCBB, 0xFF)
      stimulus_phase = "recovered"
    end
  elseif frame <= SETTLE + PRE_TRIGGER then
    native_assistance.write(0xDCBB, 0xFF)
    stimulus_phase = "pre"
  elseif frame >= SETTLE + PRE_TRIGGER + 1 then
    native_assistance.write(0xDCBB, SCENE0B_HEALTH)
    stimulus_phase = "low"
  end
  if frame <= SETTLE then return end

  sample = sample + 1
  if trace_samples[sample] then
    emu:saveStateFile(string.format("%s.boundary%04d.ss0", OUT, sample))
    local boundary = assert(io.open(OUT .. ".boundaries.tsv", "a"))
    boundary:write(string.format("%d\t%04X\t%04X\t%d\t%d\t%d\t%d\n",
      sample, early_register("pc"), early_register("sp"),
      compiler_publications, bulk_completions, expected_plane_promotions,
      pending_expected_plane and 1 or 0))
    boundary:close()
  end
  local base, map_owner_valid, map_owner_epoch, map_owner_frame,
    map_owner_room, map_owner_ffe5, oracle_missing,
    mismatches, unexpected_mismatches, mismatch_details, unsafe,
    approved_bank1, attrs, tile_bytes, attr_bytes
  if DIAGNOSTIC_LIGHT then
    base = ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800
    map_owner_valid, map_owner_epoch, map_owner_frame = 0, 0, 0
    map_owner_room, map_owner_ffe5, oracle_missing = 0xFF, 0xFF, 0
    mismatches, unexpected_mismatches, mismatch_details = 0, 0, ""
    unsafe, approved_bank1, attrs, tile_bytes, attr_bytes = 0, 0, "", "", ""
  else
    base, map_owner_valid, map_owner_epoch, map_owner_frame,
      map_owner_room, map_owner_ffe5, oracle_missing,
      mismatches, unexpected_mismatches, mismatch_details, unsafe,
      approved_bank1, attrs, tile_bytes, attr_bytes = visible_bg_receipt()
  end
  local pc = register("PC") & 0xFFFF
  local cpu_a = (early_register("af") >> 8) & 0xFF
  local sp = early_register("sp")
  local stack_return = emu:read8(sp) + 256 * emu:read8((sp + 1) & 0xFFFF)
  local dma_source = emu:read8(0xFF46)
  local scene = emu:read8(0xD880)
  local hp_sub, hp_main = emu:read8(0xDCDC), emu:read8(0xDCDD)
  local dma_unreadable = scene == 0xFF
    and pc >= 0xFF80 and pc <= 0xFF9F
    and (dma_source == 0xC0 or dma_source == 0xC1)
  -- $431F also belongs to the bank-20 semantic hazard writer. Classify only
  -- the fixed bank-1 copier/compiler route; without the active-bank guard a
  -- real writer stall was mislabeled as a harmless private-WRAM sample.
  local compiler_unreadable = emu:read8(0xFF99) == 0x01
    and (emu:read8(0xFF70) & 0x07) == 0x03
    and ((pc >= 0x42A7 and pc <= 0x436D)
      or (pc >= 0xD400 and pc <= 0xD478))
  compiler_unreadable = compiler_unreadable or (
    os.getenv("LOW_HEALTH_BULK_COMPILER") == "r426-bulk-v1"
    and emu:read8(0xFF99) == 30 and (emu:read8(0xFF70) & 7) == 3
    and pc >= 0x6D00 and pc < 0x7890)
  compiler_unreadable = compiler_unreadable or (
    os.getenv("LOW_HEALTH_BULK_COMPILER") == "r426-bulk-v1"
    and pc == 0x09C0 and cpu_a == 1 and stack_return == 0x4324
    and emu:read8(0xFF99) == 1 and (emu:read8(0xFF70) & 7) == 3)
  local handle = assert(io.open(OUT .. ".frames.tsv", "a"))
  handle:write(string.format(
    "%d\t%d\t%s\t%04X\t%02X\t%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%04X\t%d\t%d\t%d\t%02X\t%02X\t%d" ..
    "\t%d\t%d\t%s\t%d\t%d\t%s\t%s\t%s\t%s" ..
    "\t%s\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%04X\n",
    sample, frame, emu.memory.wram:read8(0x1CBB) < 0x80 and "low" or "pre",
    pc, dma_source, dma_unreadable and 1 or 0,
    compiler_unreadable and 1 or 0,
    scene, emu:read8(0xFFC1),
    emu:read8(0xFFBD), emu:read8(0xFFE5), emu:read8(0xFF42),
    emu:read8(0xDC0B),
    emu:read8(0xDC0E), emu:read8(0xDCFD),
    DIAGNOSTIC_LIGHT and "" or source_hazard_rows(),
    DIAGNOSTIC_LIGHT and "" or destination_hazard_rows(),
    hp_sub, hp_main, emu:read8(0xD887), emu:read8(0xD885),
    emu:read8(0xD888), emu:read8(0xDF0D), emu:read8(0xFF47),
    emu:read8(0xFFF7), emu:read8(0xFFE2), emu:read8(0xFFE3),
    base, map_owner_valid, map_owner_epoch, map_owner_frame,
    map_owner_room, map_owner_ffe5, oracle_missing,
    mismatches, unexpected_mismatches,
    mismatch_details, unsafe, approved_bank1, attrs, tile_bytes, attr_bytes,
    hex_bytes(palette_bytes("cgbBgPalette", 0xFF68, 0xFF69)),
    stimulus_phase, emu:read8(0xDCBB), emu:read8(0xDD06),
    emu:read8(0xFFB7), emu:read8(0xFFBF), emu:read8(0xFFBA),
    emu:read8(0xC624), emu:read8(0xC627), emu:read8(0xC630),
    emu:read8(0xC633), emu:read8(0xDF53), emu:read8(0xDF57),
    emu:read8(0xFFE0), emu:read8(0xFFA5),
    emu:read8(0xFF99), emu:read8(0xFF70) & 7, emu:read8(0xFF43),
    cpu_a, stack_return))
  handle:close()
  if not DIAGNOSTIC_LIGHT then
    emu:screenshot(string.format("%s.frame%04d.png", OUT, sample))
  end

  if observation_done(sample, SAMPLES,
      pending_expected_plane ~= nil or compiler_pending or route_pending) then
    done = true
    if STATE_OUT and STATE_OUT ~= "" then
      emu:saveStateFile(STATE_OUT)
    end
    if TRACE_LAYOUTS then
      local layouts = assert(io.open(OUT .. ".layouts.bin", "wb"))
      for _, record in ipairs(layout_records) do
        layouts:write(record.raw)
        layouts:write(record.attr)
      end
      layouts:close()
      local events = assert(io.open(OUT .. ".layout-events.tsv", "w"))
      events:write(
        "frame\tsample\tdestination\tlcdc\tscx\tscy\tdc00\tdc01\tdc02\tdc03\t" ..
        "dc0b\tdc0c\tdc0d\tdc0e\tdc0f\tdc81\tffcf\troom\tlayout\n")
      for _, event in ipairs(layout_events) do
        events:write(string.format(
          "%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t" ..
          "%d\t%d\t%d\t%d\t%d\t%d\t%d\n",
          event.frame, event.sample, event.destination, event.lcdc,
          event.scx, event.scy,
          event.dc00, event.dc01, event.dc02, event.dc03,
          event.dc0b, event.dc0c, event.dc0d, event.dc0e, event.dc0f,
          event.dc81, event.ffcf, event.room, event.layout))
      end
      events:close()
      local counts = assert(io.open(OUT .. ".scanner-counts.txt", "w"))
      counts:write(string.format("route_completed=%d\nroute_bypass=%d\nroute_invalid=%d\nroute_pending=%d\n",
        route_completed,route_bypass,route_invalid,route_pending and 1 or 0))
      counts:write(string.format(
        "source_ret=%d\npostcopy=%d\ndispatch=%d\nhelper=%d\n" ..
        "pure_helper=%d\nfront=%d\nwrite=%d\n" ..
        "scene0b_source_ret=%d\nscene0b_postcopy=%d\n" ..
        "scene0b_dispatch=%d\nscene0b_helper=%d\n" ..
        "scene0b_pure_helper=%d\nscene0b_front=%d\nscene0b_write=%d\n" ..
        "runtime_gateway=%d\nruntime_gateway_scene0b=%d\n" ..
        "split_consumer=%d\nsplit_consumer_scene0b=%d\n" ..
        "wall_helper=%d\nscene0b_wall_helper=%d\n" ..
        "pure_copy=%d\nscene0b_pure_copy=%d\n" ..
        "dirty_copy=%d\nscene0b_dirty_copy=%d\n" ..
        "decider_hit=%d\nscene0b_decider_hit=%d\n" ..
        "decider_sentinel=%d\nscene0b_decider_sentinel=%d\n" ..
        "decider_dirty=%d\nscene0b_decider_dirty=%d\n" ..
        "atomic_setup=%d\nscene0b_atomic_setup=%d\n" ..
        "atomic_setup_invalid_h=%d\nscene0b_atomic_setup_invalid_h=%d\n" ..
        "mapdone_odd=%d\nscene0b_mapdone_odd=%d\n" ..
        "mapdone_even=%d\nscene0b_mapdone_even=%d\n" ..
        "mapdone_invalid_latch=%d\nscene0b_mapdone_invalid_latch=%d\n" ..
        "runtime_entry_mismatches=%d\n" ..
        "runtime_scene0b_entry_mismatches=%d\n" ..
        "compiler_publications=%d\ncompiler_first_rows=%d\n" ..
        "compiler_row_calls=%d\ncompiler_d400_1a=%d\n" ..
        "compiler_d400_f0=%d\ncompiler_d400_other=%d\n" ..
        "compiler_contract_mismatches=%d\ncompiler_orphan_rows=%d\n" ..
        "compiler_incomplete=%d\nscene0b_compiler_publications=%d\n" ..
        "scene0b_compiler_first_rows=%d\n" ..
        "scene0b_compiler_row_calls=%d\n" ..
        "scene0b_compiler_contract_mismatches=%d\n" ..
        "expected_plane_promotions=%d\n" ..
        "expected_plane_invalid_promotions=%d\n" ..
        "expected_plane_pending=%d\n",
        source_ret_hits, postcopy_hits, hazard_dispatch_hits,
        hazard_helper_hits, hazard_pure_helper_hits, hazard_front_hits,
        hazard_write_hits, scene0b_source_ret_hits, scene0b_postcopy_hits,
        scene0b_hazard_dispatch_hits, scene0b_hazard_helper_hits,
        scene0b_hazard_pure_helper_hits, scene0b_hazard_front_hits,
        scene0b_hazard_write_hits, runtime_gateway_hits,
        runtime_gateway_scene0b_hits, split_consumer_hits,
        split_consumer_scene0b_hits, wall_helper_hits,
        scene0b_wall_helper_hits, pure_copy_hits, scene0b_pure_copy_hits,
        dirty_copy_hits, scene0b_dirty_copy_hits,
        decider_hit_hits, scene0b_decider_hit_hits,
        decider_sentinel_hits, scene0b_decider_sentinel_hits,
        decider_dirty_hits, scene0b_decider_dirty_hits,
        atomic_setup_hits, scene0b_atomic_setup_hits,
        atomic_setup_invalid_h_hits, scene0b_atomic_setup_invalid_h_hits,
        mapdone_odd_hits, scene0b_mapdone_odd_hits,
        mapdone_even_hits, scene0b_mapdone_even_hits,
        mapdone_invalid_latch_hits, scene0b_mapdone_invalid_latch_hits,
        runtime_entry_mismatches,
        runtime_scene0b_entry_mismatches,
        compiler_publications, compiler_first_rows, compiler_row_calls,
        compiler_d400_1a, compiler_d400_f0, compiler_d400_other,
        compiler_contract_mismatches, compiler_orphan_rows,
        compiler_incomplete + (compiler_pending and 1 or 0),
        scene0b_compiler_publications, scene0b_compiler_first_rows,
        scene0b_compiler_row_calls,
        scene0b_compiler_contract_mismatches,
        expected_plane_promotions, expected_plane_invalid_promotions,
        pending_expected_plane and 1 or 0))
      counts:write(string.format("bulk_completions=%d\nbulk_mismatches=%d\n",
        bulk_completions, bulk_mismatches))
      counts:write(string.format("dispatch_interrupt_retries=%d\n", dispatch_retries))
      counts:write(string.format("scene0b_bulk_completions=%d\nscene0b_bulk_mismatches=%d\n",
        scene0b_bulk_completions, scene0b_bulk_mismatches))
      counts:close()
    end
    assert(runtime_checked, "candidate DAD7 runtime was never checked")
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write("ok\n")
    marker:close()
    os.exit(0)
  end
end)

-- #67 diagnostic use of the existing #43 pre-first-CPU barrier. The native
-- adapter releases execution only after exact-state restore and all observer
-- callbacks are installed. This does not edit or rewind emulated state.
if os.getenv("ENTRY_NATIVE_START_GATE") then
  local ready = assert(io.open(os.getenv("ENTRY_NATIVE_START_GATE"), "w"))
  ready:write("low-health observer initialization complete\n")
  ready:close()
end
