-- Injection-free scene-$0B replay of both authenticated operator captures.
--
-- The Python verifier retargets only mGBA's serialized ROM identity metadata
-- (CRC plus its saved $80->$C0 CGB flag copy) and launches this probe through
-- scripts/mgba-qt-singleflight. This probe loads that machine-exact state,
-- applies only native SELECT pulses, captures every audited phase, and verifies
-- that the captured runtime attribute table is untouched.

local OUT = assert(os.getenv("PENTA_SCENE0B_OUT"),
  "PENTA_SCENE0B_OUT required")
local STARTUP_TOKEN = assert(os.getenv("PENTA_SCENE0B_STARTUP_TOKEN"),
  "PENTA_SCENE0B_STARTUP_TOKEN required")
local function write_token_marker(suffix)
  local path = OUT .. suffix
  local temporary = path .. ".tmp"
  local handle = assert(io.open(temporary, "w"))
  handle:write(STARTUP_TOKEN .. "\n")
  handle:close()
  assert(os.rename(temporary, path))
end
write_token_marker(".startup")
PENTA_PRESENTATION_PUBLICATION_PC = assert(tonumber(
  os.getenv("PENTA_SCENE0B_PRESENTATION_PC"), 16),
  "PENTA_SCENE0B_PRESENTATION_PC required")
PENTA_PRESENTATION_FALLBACK_PC = assert(tonumber(
  os.getenv("PENTA_SCENE0B_PRESENTATION_FALLBACK_PC"), 16),
  "PENTA_SCENE0B_PRESENTATION_FALLBACK_PC required")
PENTA_PRESENTATION_SEGMENT = assert(tonumber(
  os.getenv("PENTA_SCENE0B_PRESENTATION_SEGMENT"), 16),
  "PENTA_SCENE0B_PRESENTATION_SEGMENT required")
local STATE_FILE = nil
local CAPTURE_LABEL = nil
local EXPECTED_INITIAL_MENU = nil
local FRAME_LIMIT = nil
local CAPTURE_FRAMES = nil
local REPAIR_SETTLE = nil
local MENU_HOLD = nil
local POST_CLOSE = nil
local KEY_SELECT = 0x04
local TERMINAL_LUT_TILES = {
  [0x6B] = true, [0x6F] = true, [0x7B] = true, [0x7F] = true,
}
local CACHE_ADDRESSES = {
  0xDF53, 0xDF54, 0xDF55, 0xDF57, 0xDF58, 0xDF59,
}
local raw_vram = nil
local trace = nil
local cache_audit = nil
local CACHE_AUDIT_OUT = nil
local runtime_initialized = false
local plane_dump_written = false
local plane_dump_frame = 0
local plane_dump_sample = 0

local frame = 0
local sample = 0
local state_loaded = false
local finished = false
local phase = "load"
local phase_frame = 0
local capture_samples = 0
local menu_hold_samples = 0
local post_close_samples = 0
local flush_frames = 0
local opening_completed = false
local initial_scene = 0xFF
local initial_menu = 0xFF
local last_owned = false
local menu_open_events = 0
local menu_close_events = 0
local scene_violation_frames = 0
local active_violation_frames = 0
local observation_restore_failures = 0
local deferred_wram_frames = 0
PENTA_SCENE0B_OAM_DMA_UNREADABLE_FRAMES = 0
local attr_checked_samples = 0
local attr_unreadable_samples = 0
local semantic_checked_samples = 0
local semantic_unreadable_samples = 0
local immutable_tile_checked_samples = 0
local immutable_tile_unreadable_samples = 0
local cram_checked_samples = 0
local cram_unreadable_samples = 0
local baseline_ready = false
local baseline_tiles = {}
local baseline_attrs = {}
local runtime_lut = {}
local immutable_source_packed = {}
local immutable_stage1_tables = {}
local immutable_source_tiles = {}
local canonical_bg_art = {}
local canonical_hazard_bank1_art = {}
local hazard_phase_tiles = {}
local immutable_hazard_positions = {}
local immutable_hazard_envelope = {}
local exact_hazard_owned = {}
-- Tile truth belongs to the last completed physical-map publication.  The
-- world grid can advance to the next hazard phase before LCDC selects the map
-- compiled from it, so comparing a rendered map with the *current* grid
-- invents trails.  Each owner below is instead snapshotted independently at
-- the native compiler entry and promoted only after its exact GDMA completion.
local published_tile_planes = {}
local pending_tile_plane = nil
local tile_publication_oracle_failures = 0
local tile_publication_component = 0
local tile_phase_component = 0
local tile_plane_component = 0
local tile_source_component = 0
local tile_art_component = 0
local arm_tile_publication_oracle = nil
local publish_tile_publication_oracle = nil
local expected_bg_cram = {}
local cache_audit_breakpoint_failures = 0
local cache_audit_watchpoint_failures = 0
local cache_audit_event = 0
local cache_audit_selfheal_start_seen = false
local cache_audit_selfheal_commit_seen = false
local cache_audit_hits = {
  epochGate13 = 0,
  epochGate16 = 0,
  installer13 = 0,
  installer16 = 0,
  epochPublish13 = 0,
  epochPublish16 = 0,
  runtimeDAD7 = 0,
  rst18Route001A = 0,
  selfhealEntry6CEA = 0,
  selfhealRepair6D35 = 0,
  selfhealStart6D4D = 0,
  transactionArmed6DCB = 0,
  displayFlip6E25 = 0,
  commitEffect6E2A = 0,
  menuMux6CC5 = 0,
  menuEffect6CE2 = 0,
  consumer4100 = 0,
  compiler4302 = 0,
  publication4354 = 0,
  postcopy10E2 = 0,
  hazardDispatch6CCE = 0,
  hazardHelper6BA7 = 0,
  hazardFront61B7 = 0,
  hazardWrite4300 = 0,
  hazardWrite4500 = 0,
}
local cache_audit_consumer_after_selfheal = 0
local cache_audit_publication_after_selfheal = 0
local cache_audit_repopulation_after_selfheal = 0
local cache_audit_runtime_after_selfheal_matches = 0
local cache_audit_runtime_after_selfheal_mismatches = 0
local cache_audit_write_events = 0
local cache_audit_transition_events = 0
local cache_audit_wrong_svbk_writes = 0
local presentation_event_trace = {}
PENTA_SCENE_HP_TAIL = {}

function PENTA_SCENE0B_READ_PC()
  for _, reader in ipairs({
    function() return emu:getRegister("PC") end,
    function() return emu:readRegister("PC") end,
    function() return emu:readRegister("pc") end,
  }) do
    local ok, value = pcall(reader)
    if ok and type(value) == "number" then return value % 0x10000 end
  end
  return 0xFFFF
end
local cache_audit_write_counts = {}
local cache_audit_transition_counts = {}
for _, address in ipairs(CACHE_ADDRESSES) do
  cache_audit_write_counts[address] = 0
  cache_audit_transition_counts[address] = 0
end

-- Optional diagnostic-only sidecar. It observes exact bank-qualified code
-- sites and WRAM1 cache writers without writing gameplay, fixture, or VRAM
-- state. Breakpointed evidence is diagnostic and never a visual oracle.
local function cache_audit_sample(kind, write_info)
  if not cache_audit then return end
  cache_audit_event = cache_audit_event + 1
  local write_address, old_value, new_value = 0xFFFF, 0xFF, 0xFF
  if write_info then
    write_address = write_info.address % 0x10000
    old_value = write_info.oldValue % 0x100
    new_value = write_info.newValue % 0x100
  end
  local pc = 0xFFFF
  for _, reader in ipairs({
    function() return emu:getRegister("PC") end,
    function() return emu:readRegister("PC") end,
    function() return emu:readRegister("pc") end,
  }) do
    local ok, value = pcall(reader)
    if ok and type(value) == "number" then pc = value % 0x10000; break end
  end
  cache_audit:write(string.format(
    "%d\t%s\t%d\t%d\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%02X\t%02X\t%02X\t%02X" ..
    "\t%02X\t%02X\t%02X\t%02X\t%02X\t%04X\t%02X\t%02X\t%04X\n",
    cache_audit_event, kind, sample, frame, phase,
    emu:read8(0xFF70) % 0x08, emu:read8(0xFFB7), emu:read8(0xFFBA),
    emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFFC1),
    emu:read8(0xFFE4), emu:read8(0xFF01), emu:read8(0xFF42),
    emu:read8(0xDC0B),
    emu:read8(0xDC00), emu:read8(0xDC02), emu:read8(0xC21B),
    emu:read8(0xC2B8), emu:read8(0xDF02), emu:read8(0xDF0D),
    emu:read8(0xDF4F), emu:read8(0xDF51), emu:read8(0xDF53),
    emu:read8(0xDF54),
    emu:read8(0xDF55), emu:read8(0xDF56), emu:read8(0xDF57),
    emu:read8(0xDF58), emu:read8(0xDF59), emu:read8(0xDADE),
    emu:read8(0xDADF), emu:read8(0xDAE0), emu:read8(0xC624),
    emu:read8(0xC627), emu:read8(0xC630), emu:read8(0xC633),
    emu:read8(0xFF99), emu:read8(0xFF40), write_address, old_value,
    new_value, pc))
  cache_audit:flush()
end

local function install_cache_audit_breakpoints()
  local function trace_presentation_event(kind)
    if #presentation_event_trace >= 128 then return end
    local register_a = 0xFF
    for _, reader in ipairs({
      function() return emu:getRegister("A") end,
      function() return emu:readRegister("A") end,
      function() return emu:readRegister("a") end,
    }) do
      local ok, value = pcall(reader)
      if ok and type(value) == "number" then
        register_a = value % 0x100
        break
      end
    end
    presentation_event_trace[#presentation_event_trace + 1] = string.format(
      "%s:s%d:f%d:%s:m%02X:l%02X:stat%02X:ly%02X:h%02X:c%02X:p%02X:a%02X",
      kind, sample, frame, phase, emu:read8(0xFFE4),
      emu:read8(0xFF40), emu:read8(0xFF41), emu:read8(0xFF44),
      emu:read8(0xFF53), emu:read8(0xFFC4), emu:read8(0xDF5C), register_a)
  end
  local function install(address, bank, kind)
    local callback = function()
        if kind == "request12E0" or kind == "absolutePublication"
            or kind == "fallbackPublication"
            or kind == "compiler4302" or kind == "publication4354" then
          trace_presentation_event(kind)
        end
        if kind == "compiler4302" then
          arm_tile_publication_oracle()
        elseif kind == "publication4354" then
          publish_tile_publication_oracle()
        end
        if not cache_audit then return end
        if not state_loaded then return end
        cache_audit_hits[kind] = cache_audit_hits[kind] + 1
        if kind == "selfhealStart6D4D" then
          cache_audit_selfheal_start_seen = true
        elseif kind == "commitEffect6E2A" then
          cache_audit_selfheal_commit_seen = true
        elseif kind == "runtimeDAD7" and cache_audit_selfheal_commit_seen then
          if emu:read8(0xDADE) == 0xC4
              and emu:read8(0xDADF) == 0x13
              and emu:read8(0xDAE0) == 0x00 then
            cache_audit_runtime_after_selfheal_matches =
              cache_audit_runtime_after_selfheal_matches + 1
          else
            cache_audit_runtime_after_selfheal_mismatches =
              cache_audit_runtime_after_selfheal_mismatches + 1
          end
        elseif kind == "consumer4100" and cache_audit_selfheal_start_seen then
          cache_audit_consumer_after_selfheal =
            cache_audit_consumer_after_selfheal + 1
        elseif kind == "publication4354"
            and cache_audit_selfheal_start_seen then
          cache_audit_publication_after_selfheal =
            cache_audit_publication_after_selfheal + 1
        end
        cache_audit_sample(kind)
    end
    local ok, result = pcall(function()
      local arguments = {callback, address}
      if bank ~= nil then arguments[3] = bank end
      return emu:setBreakpoint(table.unpack(arguments))
    end)
    if not ok or type(result) ~= "number" or result <= 0 then
      cache_audit_breakpoint_failures = cache_audit_breakpoint_failures + 1
    end
  end
  -- The two tile-owner callbacks are mandatory visual-oracle inputs even when
  -- the optional diagnostic cache-audit sidecar is disabled.
  if not cache_audit then
    install(0x4302, 1, "compiler4302")
    install(0x4354, 1, "publication4354")
    install(0x12E0, 0, "request12E0")
    install(PENTA_PRESENTATION_PUBLICATION_PC,
      PENTA_PRESENTATION_SEGMENT, "absolutePublication")
    install(PENTA_PRESENTATION_FALLBACK_PC,
      PENTA_PRESENTATION_SEGMENT, "fallbackPublication")
    return cache_audit_breakpoint_failures == 0
  end
  -- Observe every candidate-owned epoch gate in both physical source banks.
  -- The WRAM gateway is intentionally unbanked; every ROM site is qualified.
  for _, address in ipairs({0x6B10, 0x6B19, 0x6B80}) do
    install(address, 13, "epochGate13")
    install(address, 16, "epochGate16")
  end
  install(0x7CBF, 13, "installer13")
  install(0x7CBF, 16, "installer16")
  install(0x5559, 13, "epochPublish13")
  install(0x5559, 16, "epochPublish16")
  install(0xDAD7, nil, "runtimeDAD7")
  install(0x001A, nil, "rst18Route001A")
  install(0x6CEA, 31, "selfhealEntry6CEA")
  install(0x6D35, 31, "selfhealRepair6D35")
  install(0x6D4D, 31, "selfhealStart6D4D")
  install(0x6DCB, 31, "transactionArmed6DCB")
  install(0x6E25, 31, "displayFlip6E25")
  install(0x6E2A, 31, "commitEffect6E2A")
  install(0x6CC5, 31, "menuMux6CC5")
  install(0x6CE2, 31, "menuEffect6CE2")
  install(0x4100, 21, "consumer4100")
  install(0x4302, 1, "compiler4302")
  install(0x4354, 1, "publication4354")
  -- Ordinary publication is only the pre-semantic plane. Observe the exact
  -- fixed post-copy handoff and every stage of the Stage-1 geometry owner so
  -- a canonical C600 publication cannot falsely certify gray teeth or yellow
  -- trail cells. Both bank-20 writers are real: room $01 uses the $4500 clone.
  install(0x10E2, 0, "postcopy10E2")
  install(0x6CCE, 19, "hazardDispatch6CCE")
  install(0x6BA7, 19, "hazardHelper6BA7")
  install(0x61B7, 19, "hazardFront61B7")
  install(0x4300, 20, "hazardWrite4300")
  install(0x4500, 20, "hazardWrite4500")
  local watch_ok, watch_result = pcall(function()
    return emu:setRangeWatchpoint(function(info)
      if not state_loaded or emu:read8(0xD880) ~= 0x0B then return end
      local address = info.address % 0x10000
      if cache_audit_write_counts[address] == nil then return end
      cache_audit_write_events = cache_audit_write_events + 1
      cache_audit_write_counts[address] =
        cache_audit_write_counts[address] + 1
      if info.oldValue ~= info.newValue then
        cache_audit_transition_events = cache_audit_transition_events + 1
        cache_audit_transition_counts[address] =
          cache_audit_transition_counts[address] + 1
      end
      if (emu:read8(0xFF70) % 0x08) ~= 1 then
        cache_audit_wrong_svbk_writes = cache_audit_wrong_svbk_writes + 1
      end
      if cache_audit_selfheal_start_seen
          and (address == 0xDF53 or address == 0xDF57)
          and info.oldValue == 0xFF and info.newValue ~= 0xFF then
        cache_audit_repopulation_after_selfheal =
          cache_audit_repopulation_after_selfheal + 1
      end
      cache_audit_sample(string.format("write%04X", address), info)
    end, 0xDF53, 0xDF59, C.WATCHPOINT_TYPE.WRITE)
  end)
  if not watch_ok or type(watch_result) ~= "number" or watch_result <= 0 then
    cache_audit_watchpoint_failures = cache_audit_watchpoint_failures + 1
  end
  cache_audit_sample("observers-ready")
  return cache_audit_breakpoint_failures == 0
    and cache_audit_watchpoint_failures == 0
end

local function window_visible()
  local lcdc = emu:read8(0xFF40)
  return math.floor(lcdc / 0x20) % 2 ~= 0 and emu:read8(0xFF4A) < 144
end

local function menu_owned()
  return emu:read8(0xFFE4) ~= 0 or window_visible()
end

-- FFE4 is the native menu lifecycle marker.  Window visibility remains part
-- of menu_owned() for pixel/phase ownership, but candidate repair code may
-- legitimately use the prepared Window as a short atomic display cover.  A
-- cover is not a user menu transition and must not inflate the event count.
local function native_menu_owned()
  return emu:read8(0xFFE4) ~= 0
end

local function vram_cpu_readable()
  return math.floor(emu:read8(0xFF40) / 0x80) % 2 == 0
    or emu:read8(0xFF41) % 4 <= 1
end

-- mGBA's raw VRAM domain exposes bank zero only.  Every bank-one observation
-- therefore goes through the CGB CPU window while VRAM is readable.  Keep the
-- selector writes in this single helper so map attributes, hazard CHR, and the
-- final physical dump cannot silently alias bank zero.
local function read_vbk1(offsets)
  if not vram_cpu_readable() then return nil end
  local old_vbk = emu:read8(0xFF4F)
  local values = {}
  emu:write8(0xFF4F, 1)
  for index, offset in ipairs(offsets) do
    values[index] = emu:read8(0x8000 + offset)
  end
  emu:write8(0xFF4F, old_vbk)
  if emu:read8(0xFF4F) ~= old_vbk then
    observation_restore_failures = observation_restore_failures + 1
    return nil
  end
  return values
end

local function read_planes(offsets)
  local attrs = read_vbk1(offsets)
  if not attrs then return nil, nil end
  local tiles = {}
  for index, offset in ipairs(offsets) do
    tiles[index] = raw_vram:read8(offset)
  end
  return tiles, attrs
end

local function byte_blob(values)
  local chunks = {}
  for first = 1, #values, 128 do
    local bytes = {}
    local last = math.min(first + 127, #values)
    for index = first, last do
      bytes[#bytes + 1] = string.char(values[index])
    end
    chunks[#chunks + 1] = table.concat(bytes)
  end
  return table.concat(chunks)
end

local function dump_physical_planes()
  local offsets = {}
  for offset = 0x1800, 0x1FFF do offsets[#offsets + 1] = offset end
  local tiles, attrs = read_planes(offsets)
  if not tiles then return false end
  local chr_offsets = {}
  for offset = 0, 0x1FFF do
    chr_offsets[#chr_offsets + 1] = offset
  end
  local bank1_chr = read_vbk1(chr_offsets)
  if not bank1_chr then return false end
  local source, lut = {}, {}
  for offset = 0, 0x23F do
    source[#source + 1] = emu:read8(0xC1A0 + offset)
  end
  for offset = 0, 0xFF do
    lut[#lut + 1] = emu:read8(0xC600 + offset)
  end
  local handle = assert(io.open(OUT .. ".planes.bin", "wb"))
  handle:write(byte_blob(tiles))
  handle:write(byte_blob(attrs))
  handle:write(byte_blob(source))
  handle:write(byte_blob(lut))
  handle:close()
  -- Preserve the actual final physical CHR bytes for independent offline
  -- grading.  The per-frame checker catches transients; this artifact lets
  -- the binder verify the final patterns instead of trusting scalar claims.
  local bank0_chr = {}
  for offset = 0, 0x1FFF do
    bank0_chr[#bank0_chr + 1] = raw_vram:read8(offset)
  end
  local chr_handle = assert(io.open(OUT .. ".chr.bin", "wb"))
  chr_handle:write(byte_blob(bank0_chr))
  chr_handle:write(byte_blob(bank1_chr))
  chr_handle:close()
  local metadata = assert(io.open(OUT .. ".planes.meta", "w"))
  metadata:write(string.format(
    "frame=%d\nsample=%d\nphase=%s\nlcdc=%02X\nscx=%02X\nscy=%02X\n" ..
    "scene=%02X\nroom=%02X\nmenu=%02X\nschema=maps-v1\nbytes=4928\n",
    frame, sample, phase, emu:read8(0xFF40), emu:read8(0xFF43),
    emu:read8(0xFF42), emu:read8(0xD880), emu:read8(0xFFBD),
    emu:read8(0xFFE4)))
  metadata:close()
  plane_dump_written = true
  plane_dump_frame = frame
  plane_dump_sample = sample
  return true
end

local function capture_baseline()
  local offsets = {}
  for offset = 0x1800, 0x1FFF do
    offsets[#offsets + 1] = offset
  end
  local tiles, attrs = read_planes(offsets)
  if not tiles then return false end
  baseline_tiles, baseline_attrs = {}, {}
  for index, offset in ipairs(offsets) do
    baseline_tiles[offset] = tiles[index]
    baseline_attrs[offset] = attrs[index]
  end
  baseline_ready = true
  return true
end

local function visible_offsets()
  local lcdc = emu:read8(0xFF40)
  local map_offset = math.floor(lcdc / 8) % 2 ~= 0 and 0x1C00 or 0x1800
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local columns = 20 + ((scx % 8 ~= 0) and 1 or 0)
  local rows = 18 + ((scy % 8 ~= 0) and 1 or 0)
  if menu_owned() and rows > 12 then rows = 12 end
  local offsets = {}
  for screen_row = 0, rows - 1 do
    local map_row = (math.floor(scy / 8) + screen_row) % 32
    for screen_column = 0, columns - 1 do
      local map_column = (math.floor(scx / 8) + screen_column) % 32
      offsets[#offsets + 1] = map_offset + map_row * 32 + map_column
    end
  end
  return offsets
end

local function visible_attr_mismatches()
  if not baseline_ready then return 0, false end
  local offsets = visible_offsets()
  local tiles, attrs = read_planes(offsets)
  if not tiles then return 0, false end
  local mismatches = 0
  for index, offset in ipairs(offsets) do
    -- A changed tile may be a legitimate animation. Attribute corruption is
    -- counted only where the physical tile still matches the repaired native
    -- baseline, making this a conservative independent state oracle.
    if tiles[index] == baseline_tiles[offset]
        and attrs[index] ~= baseline_attrs[offset] then
      mismatches = mismatches + 1
    end
  end
  return mismatches, true
end

local function stage1_tooth(tile)
  local folded = tile & 0xEF
  return folded >= 0x64 and folded < 0x6A
end

local function stage1_hazard_positions(tiles)
  local positions = {}
  local function tooth(column, row)
    return stage1_tooth(tiles[row * 32 + column + 1])
  end
  for row = 0, 31 do
    local start, width
    if tooth(0, row) or tooth(1, row) then
      start, width = 0, tooth(10, row) and 11 or
        (tooth(9, row) and 10 or 9)
    elseif tiles[row * 32 + 5] == 0x6A then
      start, width = 5, 10
    elseif tooth(4, row) or tooth(5, row) then
      start, width = 4, 9
    end
    if start then
      for column = start, start + width - 1 do
        positions[row * 32 + column] = true
      end
    elseif tooth(6, row) then
      for column = 4, 13 do
        if tooth(column, row) then
          positions[row * 32 + column] = true
        end
      end
    end
  end
  return positions
end

local function exact_hazard_tile_mismatches(tiles)
  if CAPTURE_LABEL ~= "operator-low-health-menu-loaded" then return 0 end
  local mismatches = 0
  -- Four independent, non-overlapping 4x12 components. Each component must
  -- match one complete native phase; per-cell unions are never accepted.
  for object = 0, 3 do
    local exact_matches = 0
    local best = 48
    for candidate_phase = 0, 3 do
      local phase_mismatches = 0
      local phase_base = (object * 4 + candidate_phase) * 48
      for local_row = 0, 3 do
        for local_column = 0, 11 do
          local relative = (object * 4 + local_row) * 32 + local_column
          local expected = hazard_phase_tiles[
            phase_base + local_row * 12 + local_column + 1]
          if tiles[relative + 1] ~= expected then
            phase_mismatches = phase_mismatches + 1
          end
        end
      end
      if phase_mismatches == 0 then exact_matches = exact_matches + 1 end
      if phase_mismatches < best then best = phase_mismatches end
    end
    if exact_matches ~= 1 then mismatches = mismatches + math.max(1, best) end
  end
  -- Everything outside those four exact rectangles remains immutable,
  -- including all 12 cells that the old broad envelope accidentally excused.
  for row = 0, 23 do
    for column = 0, 23 do
      local relative = row * 32 + column
      if not exact_hazard_owned[relative]
          and tiles[relative + 1] ~= immutable_source_tiles[relative + 1] then
        mismatches = mismatches + 1
      end
    end
  end
  return mismatches
end

local function capture_immutable_source()
  local tiles = {}
  for offset = 0, 0x3FF do tiles[offset + 1] = 0 end
  for row = 0, 23 do
    for column = 0, 23 do
      local offset = row * 32 + column
      tiles[offset + 1] = immutable_source_packed[
        row * 24 + column + 1]
    end
  end
  immutable_source_tiles = tiles
  immutable_hazard_positions = stage1_hazard_positions(tiles)
  immutable_hazard_envelope = {}
  for position, _ in pairs(immutable_hazard_positions) do
    local hazard_row = math.floor(position / 32)
    local hazard_column = position % 32
    for row = math.max(0, hazard_row - 1), math.min(31, hazard_row + 1) do
      for column = math.max(0, hazard_column - 1),
          math.min(31, hazard_column + 1) do
        immutable_hazard_envelope[row * 32 + column] = true
      end
    end
  end
  exact_hazard_owned = {}
  for object = 0, 3 do
    for local_row = 0, 3 do
      for local_column = 0, 11 do
        exact_hazard_owned[(object * 4 + local_row) * 32 + local_column] = true
      end
    end
  end
end

local function reconstruct_current_world_source()
  -- Rebuild the native packed 24x24 source from the live world-ID grid and
  -- the authenticated, immutable SRAM metatile tables supplied by Python.
  -- This is independent of both mutable C1A0 and either physical BG map.
  local packed = {}
  for index = 1, 24 * 24 do packed[index] = 0 end
  local camera_x = (
    emu:read8(0xDC00) + emu:read8(0xDC01) * 0x100) >> 5
  local camera_y = (
    emu:read8(0xDC02) + emu:read8(0xDC03) * 0x100) >> 5
  for world_row = 0, 5 do
    for world_column = 0, 5 do
      local world_id = emu:read8(
        0xC780 + (camera_y + world_row) * 0x40
        + camera_x + world_column)
      local metatile_base = 0x400 + world_id * 4
      for metatile_row = 0, 1 do
        for metatile_column = 0, 1 do
          local metatile = immutable_stage1_tables[
            metatile_base + metatile_row * 2 + metatile_column + 1]
          local tile_base = metatile * 4
          for tile_row = 0, 1 do
            for tile_column = 0, 1 do
              local output_row =
                world_row * 4 + metatile_row * 2 + tile_row
              local output_column =
                world_column * 4 + metatile_column * 2 + tile_column
              if output_row < 20 and output_column < 22 then
                packed[output_row * 24 + output_column + 1] =
                  immutable_stage1_tables[
                    tile_base + tile_row * 2 + tile_column + 1]
              end
            end
          end
        end
      end
    end
  end
  local tiles = {}
  for offset = 0, 0x3FF do tiles[offset + 1] = 0 end
  for row = 0, 23 do
    for column = 0, 23 do
      tiles[row * 32 + column + 1] = packed[
        row * 24 + column + 1]
    end
  end
  return tiles
end

arm_tile_publication_oracle = function()
  -- The native compiler enters $4302 once per hazard component before the
  -- shared $4354 publication.  Those nested arms are one transaction, not
  -- abandoned publications; retain the latest complete source snapshot for
  -- the eventual commit instead of permanently poisoning every later frame.
  local latch = emu:read8(0xFF01)
  local destination = latch == 0x99 and 0x9800
    or (latch == 0x9D and 0x9C00 or 0)
  local expected = reconstruct_current_world_source()
  pending_tile_plane = {
    destination = destination,
    expected = expected,
  }
end

publish_tile_publication_oracle = function()
  local pending = pending_tile_plane
  local source_mismatches = 0
  if pending then
    for row = 0, 23 do
      for column = 0, 23 do
        if emu:read8(0xC1A0 + row * 24 + column)
            ~= pending.expected[row * 32 + column + 1] then
          source_mismatches = source_mismatches + 1
        end
      end
    end
  end
  if not pending or pending.destination == 0
      or source_mismatches ~= 0
      or emu:read8(0xFF55) ~= 0xFF
      or (emu:read8(0xFF4F) & 0x01) ~= 0
      or (emu:read8(0xFF70) & 0x07) ~= 0x01 then
    tile_publication_oracle_failures =
      tile_publication_oracle_failures + 1
    pending_tile_plane = nil
    return
  end
  published_tile_planes[pending.destination] = pending.expected
  pending_tile_plane = nil
end

local function semantic_attr_mismatches()
  local lcdc = emu:read8(0xFF40)
  local base = math.floor(lcdc / 8) % 2 ~= 0 and 0x1C00 or 0x1800
  local offsets = {}
  for offset = base, base + 0x3FF do offsets[#offsets + 1] = offset end
  local tiles, attrs = read_planes(offsets)
  if not tiles then return 0, false end
  local room = emu:read8(0xFFBD)
  local mismatches = 0
  local semantic_hazard_positions = immutable_hazard_positions
  if CAPTURE_LABEL == "operator-low-health-menu-loaded" then
    -- Exact whole-phase legality is enforced by immutable_tile_mismatches;
    -- after that, the native geometry scanner may derive the current phase's
    -- tooth cells without letting candidate output define a baseline.
    semantic_hazard_positions = stage1_hazard_positions(tiles)
  end
  -- The compiler owns a full 24x24 plane, including its canonical-zero
  -- padding.  Sample all of it so seams just outside the 160x144 viewport
  -- cannot evade the menu-roundtrip gate and appear one movement later.
  for row = 0, 23 do
    for column = 0, 23 do
      local relative = row * 32 + column
      local tile = tiles[relative + 1]
      local expected = runtime_lut[tile] & 0x07
      -- r342 migrates only the four reviewed pole-terminal entries in the
      -- captured working C600 LUT before the invalidated compiler runs.  Use
      -- that live value only for the exact old-BG6 -> new-BG5 transition;
      -- every other candidate-written LUT value remains a mismatch below.
      if TERMINAL_LUT_TILES[tile]
          and runtime_lut[tile] == 0x06
          and emu:read8(0xC600 + tile) == 0x05 then
        expected = 0x05
      end
      if room == 0x01
          and (tile == 0x24 or tile == 0x27
            or tile == 0x30 or tile == 0x33) then
        expected = 0x06
      end
      if semantic_hazard_positions[relative] and stage1_tooth(tile) then
        expected = 0x0F
      end
      if attrs[relative + 1] ~= expected then
        mismatches = mismatches + 1
      end
    end
  end
  return mismatches, true
end

local function immutable_tile_mismatches()
  local lcdc = emu:read8(0xFF40)
  local base = math.floor(lcdc / 8) % 2 ~= 0 and 0x1C00 or 0x1800
  local offsets = {}
  for offset = base, base + 0x3FF do offsets[#offsets + 1] = offset end
  local tiles, attrs = read_planes(offsets)
  if not tiles then return 0, false end
  local expected = published_tile_planes[0x8000 + base]
    or immutable_source_tiles
  local current_source = reconstruct_current_world_source()
  local live_source = {}
  for offset = 0, 0x3FF do live_source[offset + 1] = 0 end
  for row = 0, 23 do
    for column = 0, 23 do
      live_source[row * 32 + column + 1] =
        emu:read8(0xC1A0 + row * 24 + column)
    end
  end
  local phase_mismatches = exact_hazard_tile_mismatches(current_source)
    + exact_hazard_tile_mismatches(expected)
    + exact_hazard_tile_mismatches(tiles)
  local publication_mismatches = tile_publication_oracle_failures
  local plane_mismatches, source_mismatches, art_mismatches = 0, 0, 0
  -- Acceptance grades the displayed plane and exact whole-phase legality.
  -- Publication timing, scratch-source convergence, and hidden/menu-owned CHR
  -- remain separately reported components and are bound by their own final or
  -- rendered gates; they must not masquerade as visible tile corruption.
  local mismatches = phase_mismatches
  for row = 0, 23 do
    for column = 0, 23 do
      local relative = row * 32 + column
      local packed = row * 24 + column
      local animation_owned = immutable_hazard_envelope[relative]
      if CAPTURE_LABEL == "operator-low-health-menu-loaded" then
        animation_owned = exact_hazard_owned[relative]
      end
      -- Hazard-owned cells legitimately advance between the publication
      -- callback and this frame sample.  The three independent whole-phase
      -- checks above prove that source, publication snapshot, and displayed
      -- plane are each an exact legal phase, including immutable guards and
      -- unexpected-tooth rejection.  Comparing two legal phases byte for
      -- byte here therefore creates a false trail failure.  Keep the strict
      -- publication equality everywhere animation does not own the cell.
      if not animation_owned
          and tiles[relative + 1] ~= expected[relative + 1] then
        mismatches = mismatches + 1
        plane_mismatches = plane_mismatches + 1
      elseif not animation_owned
          and expected[relative + 1]
            ~= immutable_source_tiles[relative + 1] then
        mismatches = mismatches + 1
        plane_mismatches = plane_mismatches + 1
      end
      -- C1A0 is separately owned by the current world/SRAM expansion.  This
      -- also enforces all 136 canonical-zero padding bytes every sample.
      if not animation_owned and live_source[relative + 1]
          ~= current_source[relative + 1] then
        source_mismatches = source_mismatches + 1
      end
    end
  end
  -- Hash-pinned r292 ROM art supplies independent bank-zero patterns for both
  -- routes and the only legal bank-one tooth patterns for the hazard route.
  -- Map IDs + attrs + CRAM + these bytes determine the displayed gameplay
  -- background.  The native menu deliberately repurposes bank-zero IDs
  -- $01-$7F behind its Window; while that Window owns the lower rows, grade
  -- only gameplay cells that remain visible above it.  Closed gameplay still
  -- grades the complete 24x24 compiler-owned plane.
  if CAPTURE_LABEL == "operator-corrupted-walls"
      or CAPTURE_LABEL == "operator-low-health-menu-loaded" then
    local checked_art = {}
    local signed = (lcdc & 0x10) == 0
    local art_offsets = {}
    if menu_owned() then
      for _, offset in ipairs(visible_offsets()) do
        art_offsets[#art_offsets + 1] = offset - base
      end
    else
      for row = 0, 23 do
        for column = 0, 23 do
          art_offsets[#art_offsets + 1] = row * 32 + column
        end
      end
    end
    for _, relative in ipairs(art_offsets) do
      local tile = tiles[relative + 1]
      local bank = (attrs[relative + 1] >> 3) & 0x01
      local key = bank * 0x100 + tile
      if not checked_art[key] then
        checked_art[key] = true
        local address = tile * 16
        if signed and tile < 0x80 then address = 0x1000 + address end
        local expected_art, expected_base
        if bank == 0 then
          expected_art, expected_base = canonical_bg_art, tile * 16
        elseif CAPTURE_LABEL == "operator-low-health-menu-loaded"
            and tile >= 0x64 and tile <= 0x69 then
          expected_art = canonical_hazard_bank1_art
          expected_base = (tile - 0x64) * 16
        elseif CAPTURE_LABEL == "operator-low-health-menu-loaded"
            and tile >= 0x74 and tile <= 0x79 then
          expected_art = canonical_hazard_bank1_art
          expected_base = 96 + (tile - 0x74) * 16
        else
          art_mismatches = art_mismatches + 1
        end
        if expected_art then
          local observed_bank1 = nil
          if bank == 1 then
            local pattern_offsets = {}
            for byte = 0, 15 do
              pattern_offsets[#pattern_offsets + 1] = address + byte
            end
            observed_bank1 = read_vbk1(pattern_offsets)
            if not observed_bank1 then return 0, false end
          end
          for byte = 0, 15 do
            local observed
            if bank == 0 then
              observed = raw_vram:read8(address + byte)
            else
              observed = observed_bank1[byte + 1]
            end
            if observed ~= expected_art[expected_base + byte + 1] then
              art_mismatches = art_mismatches + 1
            end
          end
        end
      end
    end
  end
  tile_publication_component = publication_mismatches
  tile_phase_component = phase_mismatches
  tile_plane_component = plane_mismatches
  tile_source_component = source_mismatches
  tile_art_component = art_mismatches
  return mismatches, true
end

local function bg_cram_mismatches()
  local accessor = emu.memory and emu.memory.cgbBgPalette
  local actual
  if accessor then
    actual = accessor:readRange(0, 64)
  else
    -- Some checked mGBA builds do not expose the dedicated BG-CRAM domain.
    -- Read through BCPS/BGPD without touching palette data, then restore the
    -- exact selector (including its auto-increment bit).
    local old_index = emu:read8(0xFF68)
    local values = {}
    for index = 0, 63 do
      emu:write8(0xFF68, index)
      values[#values + 1] = string.char(emu:read8(0xFF69))
    end
    emu:write8(0xFF68, old_index)
    if emu:read8(0xFF68) ~= old_index then
      observation_restore_failures = observation_restore_failures + 1
      return 0, false
    end
    actual = table.concat(values)
  end
  if not actual or #actual ~= 64 then return 0, false end
  local mismatches = 0
  for index = 1, 64 do
    if string.byte(actual, index) ~= expected_bg_cram[index] then
      mismatches = mismatches + 1
    end
  end
  return mismatches, true
end

local function lut_mismatches()
  local mismatches = 0
  for index = 0, 0xFF do
    local current = emu:read8(0xC600 + index)
    local reviewed_terminal_migration = (
      TERMINAL_LUT_TILES[index]
      and runtime_lut[index] == 0x06
      and current == 0x05
    )
    if current ~= runtime_lut[index] and not reviewed_terminal_migration then
      mismatches = mismatches + 1
    end
  end
  return mismatches
end

local function set_phase(value)
  phase = value
  phase_frame = 0
end

local function apply_keys(keys)
  emu:setKeys(keys)
end

local function sample_phase()
  sample = sample + 1
  local attr_mismatches, checked = visible_attr_mismatches()
  local semantic_mismatches, semantic_checked = semantic_attr_mismatches()
  local tile_mismatches, tile_checked = immutable_tile_mismatches()
  local cram_mismatches, cram_checked = bg_cram_mismatches()
  if checked then
    attr_checked_samples = attr_checked_samples + 1
  elseif baseline_ready then
    attr_unreadable_samples = attr_unreadable_samples + 1
  end
  if semantic_checked then
    semantic_checked_samples = semantic_checked_samples + 1
  else
    semantic_unreadable_samples = semantic_unreadable_samples + 1
  end
  if tile_checked then
    immutable_tile_checked_samples = immutable_tile_checked_samples + 1
  else
    immutable_tile_unreadable_samples = immutable_tile_unreadable_samples + 1
  end
  if cram_checked then
    cram_checked_samples = cram_checked_samples + 1
  else
    cram_unreadable_samples = cram_unreadable_samples + 1
  end
  local path = string.format("%s.frame%04d.%s.png", OUT, sample, phase)
  emu:screenshot(path)
  trace:write(string.format(
    "%d\t%d\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\n",
    sample, frame, phase, emu:read8(0xD880), emu:read8(0xFFBD),
    emu:read8(0xFFC1), emu:read8(0xFFE4), emu:read8(0xFF40),
    emu:read8(0xFF43), emu:read8(0xFF42), attr_mismatches,
    semantic_mismatches, tile_mismatches, tile_publication_component,
    tile_phase_component, tile_plane_component, tile_source_component,
    tile_art_component, cram_mismatches,
    lut_mismatches(), STARTUP_TOKEN))
  trace:flush()
  cache_audit_sample("frame")
end

local function write_report(status, reason)
  local handle = assert(io.open(OUT .. ".report", "w"))
  handle:write("status=" .. status .. "\n")
  handle:write("reason=" .. reason .. "\n")
  handle:write("startup_token=" .. STARTUP_TOKEN .. "\n")
  handle:write("capture_label=" .. CAPTURE_LABEL .. "\n")
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("samples=%d\n", sample))
  handle:write(string.format("state_loaded=%d\n", state_loaded and 1 or 0))
  handle:write(string.format("initial_menu=%d\n", initial_menu))
  handle:write(string.format("initial_scene=%02X\n", initial_scene))
  handle:write(string.format(
    "final_scene=%02X\n", emu:read8(0xD880)))
  handle:write(string.format(
    "final_room=%02X\n", emu:read8(0xFFBD)))
  handle:write(string.format(
    "final_active=%02X\n", emu:read8(0xFFC1)))
  handle:write(string.format(
    "final_hp=%02X\n", emu:read8(0xDCDC)))
  handle:write(
    "scene_hp_tail=" .. table.concat(PENTA_SCENE_HP_TAIL, ";") .. "\n")
  handle:write(string.format("menu_open_events=%d\n", menu_open_events))
  handle:write(string.format("menu_close_events=%d\n", menu_close_events))
  handle:write(string.format(
    "scene_violation_frames=%d\n", scene_violation_frames))
  handle:write(string.format(
    "active_violation_frames=%d\n", active_violation_frames))
  handle:write(string.format(
    "observation_restore_failures=%d\n", observation_restore_failures))
  handle:write(string.format(
    "cache_audit_deferred_wram_frames=%d\n", deferred_wram_frames))
  handle:write(string.format(
    "oam_dma_unreadable_frames=%d\n",
    PENTA_SCENE0B_OAM_DMA_UNREADABLE_FRAMES))
  handle:write(string.format(
    "baseline_ready=%d\n", baseline_ready and 1 or 0))
  handle:write(string.format(
    "attr_checked_samples=%d\n", attr_checked_samples))
  handle:write(string.format(
    "attr_unreadable_samples=%d\n", attr_unreadable_samples))
  handle:write(string.format(
    "semantic_checked_samples=%d\n", semantic_checked_samples))
  handle:write(string.format(
    "semantic_unreadable_samples=%d\n", semantic_unreadable_samples))
  handle:write(string.format(
    "immutable_tile_checked_samples=%d\n", immutable_tile_checked_samples))
  handle:write(string.format(
    "immutable_tile_unreadable_samples=%d\n",
    immutable_tile_unreadable_samples))
  handle:write(string.format(
    "cram_checked_samples=%d\n", cram_checked_samples))
  handle:write(string.format(
    "cram_unreadable_samples=%d\n", cram_unreadable_samples))
  handle:write(string.format(
    "plane_dump_written=%d\n", plane_dump_written and 1 or 0))
  handle:write(string.format("plane_dump_frame=%d\n", plane_dump_frame))
  handle:write(string.format("plane_dump_sample=%d\n", plane_dump_sample))
  handle:write(string.format(
    "cache_audit_breakpoint_failures=%d\n", cache_audit_breakpoint_failures))
  handle:write(string.format(
    "cache_audit_watchpoint_failures=%d\n", cache_audit_watchpoint_failures))
  handle:write(string.format(
    "cache_audit_epoch_gate13_hits=%d\n", cache_audit_hits.epochGate13))
  handle:write(string.format(
    "cache_audit_epoch_gate16_hits=%d\n", cache_audit_hits.epochGate16))
  handle:write(string.format(
    "cache_audit_installer13_hits=%d\n", cache_audit_hits.installer13))
  handle:write(string.format(
    "cache_audit_installer16_hits=%d\n", cache_audit_hits.installer16))
  handle:write(string.format(
    "cache_audit_epoch_publish13_hits=%d\n",
    cache_audit_hits.epochPublish13))
  handle:write(string.format(
    "cache_audit_epoch_publish16_hits=%d\n",
    cache_audit_hits.epochPublish16))
  handle:write(string.format(
    "cache_audit_runtime_gateway_hits=%d\n", cache_audit_hits.runtimeDAD7))
  handle:write(string.format(
    "cache_audit_rst18_route_hits=%d\n", cache_audit_hits.rst18Route001A))
  handle:write(string.format(
    "cache_audit_selfheal_entry_hits=%d\n", cache_audit_hits.selfhealEntry6CEA))
  handle:write(string.format(
    "cache_audit_selfheal_repair_hits=%d\n", cache_audit_hits.selfhealRepair6D35))
  handle:write(string.format(
    "cache_audit_selfheal_start_hits=%d\n", cache_audit_hits.selfhealStart6D4D))
  handle:write(string.format(
    "cache_audit_transaction_armed_hits=%d\n",
    cache_audit_hits.transactionArmed6DCB))
  handle:write(string.format(
    "cache_audit_display_flip_hits=%d\n", cache_audit_hits.displayFlip6E25))
  handle:write(string.format(
    "cache_audit_commit_effect_hits=%d\n", cache_audit_hits.commitEffect6E2A))
  handle:write(string.format(
    "cache_audit_menu_mux_hits=%d\n", cache_audit_hits.menuMux6CC5))
  handle:write(string.format(
    "cache_audit_menu_effect_hits=%d\n", cache_audit_hits.menuEffect6CE2))
  handle:write(string.format(
    "cache_audit_consumer_hits=%d\n", cache_audit_hits.consumer4100))
  handle:write(string.format(
    "cache_audit_compiler_hits=%d\n", cache_audit_hits.compiler4302))
  handle:write(string.format(
    "cache_audit_publication_hits=%d\n", cache_audit_hits.publication4354))
  handle:write(string.format(
    "cache_audit_postcopy_hits=%d\n", cache_audit_hits.postcopy10E2))
  handle:write(string.format(
    "cache_audit_hazard_dispatch_hits=%d\n",
    cache_audit_hits.hazardDispatch6CCE))
  handle:write(string.format(
    "cache_audit_hazard_helper_hits=%d\n",
    cache_audit_hits.hazardHelper6BA7))
  handle:write(string.format(
    "cache_audit_hazard_front_hits=%d\n",
    cache_audit_hits.hazardFront61B7))
  handle:write(string.format(
    "cache_audit_hazard_write4300_hits=%d\n",
    cache_audit_hits.hazardWrite4300))
  handle:write(string.format(
    "cache_audit_hazard_write4500_hits=%d\n",
    cache_audit_hits.hazardWrite4500))
  handle:write(string.format(
    "cache_audit_consumer_after_selfheal=%d\n",
    cache_audit_consumer_after_selfheal))
  handle:write(string.format(
    "cache_audit_publication_after_selfheal=%d\n",
    cache_audit_publication_after_selfheal))
  handle:write(string.format(
    "cache_audit_repopulation_after_selfheal=%d\n",
    cache_audit_repopulation_after_selfheal))
  handle:write(string.format(
    "cache_audit_runtime_after_selfheal_matches=%d\n",
    cache_audit_runtime_after_selfheal_matches))
  handle:write(string.format(
    "cache_audit_runtime_after_selfheal_mismatches=%d\n",
    cache_audit_runtime_after_selfheal_mismatches))
  handle:write(string.format(
    "cache_audit_write_events=%d\n", cache_audit_write_events))
  handle:write(string.format(
    "cache_audit_transition_events=%d\n", cache_audit_transition_events))
  handle:write(string.format(
    "cache_audit_wrong_svbk_writes=%d\n", cache_audit_wrong_svbk_writes))
  handle:write(string.format(
    "presentation_event_count=%d\n", #presentation_event_trace))
  for index, event in ipairs(presentation_event_trace) do
    handle:write(string.format("presentation_event_%03d=%s\n", index, event))
  end
  for _, address in ipairs(CACHE_ADDRESSES) do
    handle:write(string.format(
      "cache_audit_%04X_writes=%d\n", address,
      cache_audit_write_counts[address]))
    handle:write(string.format(
      "cache_audit_%04X_transitions=%d\n", address,
      cache_audit_transition_counts[address]))
  end
  handle:close()
end

local function write_completion_marker(status)
  local path = OUT .. ".done"
  local temporary = path .. ".tmp"
  local marker = assert(io.open(temporary, "w"))
  marker:write("status=" .. status .. "\n")
  marker:write("startup_token=" .. STARTUP_TOKEN .. "\n")
  marker:close()
  assert(os.rename(temporary, path))
end

local function boot_fail(reason, detail)
  if finished then return end
  finished = true
  if trace then pcall(function() trace:close() end) end
  if cache_audit then pcall(function() cache_audit:close() end) end
  local handle = io.open(OUT .. ".report", "w")
  if handle then
    handle:write("status=fail\n")
    handle:write("reason=" .. reason .. "\n")
    handle:write("startup_token=" .. STARTUP_TOKEN .. "\n")
    handle:write("detail=" .. tostring(detail or "none"):gsub("[\r\n]", " ")
      .. "\n")
    handle:close()
  end
  pcall(function() write_completion_marker("fail") end)
  pcall(function() emu:setKeys(0) end)
  pcall(function() emu:stop() end)
end

local function finish(status, reason)
  if finished then return end
  finished = true
  emu:setKeys(0)
  trace:close()
  if cache_audit then cache_audit:close() end
  write_report(status, reason)
  write_completion_marker(status)
  -- This mGBA build cannot safely tear Qt down from a frame callback. Stop the
  -- core after durable receipts; Python then terminates only this exact child.
  emu:stop()
end

callbacks:add("frame", function()
  if finished then return end
  if not runtime_initialized then
    -- The script is evaluated before mGBA attaches a core. Defer every core
    -- accessor, remaining environment read, and trace open until this first
    -- frame callback. Each stage has an atomic marker or explicit fail receipt.
    local domain_ok, domain = pcall(function()
      return emu.memory and emu.memory.vram
    end)
    if not domain_ok or not domain then
      boot_fail("vram-domain-unavailable", domain)
      return
    end
    raw_vram = domain
    write_token_marker(".core-ready")

    local config_ok, config_error = pcall(function()
      STATE_FILE = assert(os.getenv("PENTA_SCENE0B_STATE"),
        "PENTA_SCENE0B_STATE required")
      CAPTURE_LABEL = assert(os.getenv("PENTA_SCENE0B_CAPTURE_LABEL"),
        "PENTA_SCENE0B_CAPTURE_LABEL required")
      local initial_menu_text = assert(
        os.getenv("PENTA_SCENE0B_INITIAL_MENU"),
        "PENTA_SCENE0B_INITIAL_MENU required")
      EXPECTED_INITIAL_MENU = assert(tonumber(initial_menu_text),
        "PENTA_SCENE0B_INITIAL_MENU invalid")
      FRAME_LIMIT = assert(tonumber(
        os.getenv("PENTA_SCENE0B_FRAME_LIMIT") or "900"))
      CAPTURE_FRAMES = assert(tonumber(
        os.getenv("PENTA_SCENE0B_CAPTURE_FRAMES") or "1"))
      REPAIR_SETTLE = assert(tonumber(
        os.getenv("PENTA_SCENE0B_REPAIR_SETTLE") or "24"))
      MENU_HOLD = assert(tonumber(
        os.getenv("PENTA_SCENE0B_MENU_HOLD") or "60"))
      POST_CLOSE = assert(tonumber(
        os.getenv("PENTA_SCENE0B_POST_CLOSE") or "60"))
      CACHE_AUDIT_OUT = os.getenv("PENTA_SCENE0B_CACHE_AUDIT_OUT")
      local immutable_source_hex = assert(
        os.getenv("PENTA_SCENE0B_IMMUTABLE_SOURCE"),
        "PENTA_SCENE0B_IMMUTABLE_SOURCE required")
      assert(#immutable_source_hex == 24 * 24 * 2
        and not immutable_source_hex:find("[^0-9A-Fa-f]"),
        "PENTA_SCENE0B_IMMUTABLE_SOURCE invalid")
      immutable_source_packed = {}
      for index = 0, 24 * 24 - 1 do
        immutable_source_packed[index + 1] = assert(tonumber(
          immutable_source_hex:sub(index * 2 + 1, index * 2 + 2), 16))
      end
      local stage1_tables_hex = assert(
        os.getenv("PENTA_SCENE0B_STAGE1_TABLES"),
        "PENTA_SCENE0B_STAGE1_TABLES required")
      assert(#stage1_tables_hex == 0x800 * 2
        and not stage1_tables_hex:find("[^0-9A-Fa-f]"),
        "PENTA_SCENE0B_STAGE1_TABLES invalid")
      immutable_stage1_tables = {}
      for index = 0, 0x7FF do
        immutable_stage1_tables[index + 1] = assert(tonumber(
          stage1_tables_hex:sub(index * 2 + 1, index * 2 + 2), 16))
      end
      local canonical_bg_art_hex = assert(
        os.getenv("PENTA_SCENE0B_CANONICAL_BG_ART"),
        "PENTA_SCENE0B_CANONICAL_BG_ART required")
      assert(#canonical_bg_art_hex == 0x1000 * 2
        and not canonical_bg_art_hex:find("[^0-9A-Fa-f]"),
        "PENTA_SCENE0B_CANONICAL_BG_ART invalid")
      canonical_bg_art = {}
      for index = 0, 0xFFF do
        canonical_bg_art[index + 1] = assert(tonumber(
          canonical_bg_art_hex:sub(index * 2 + 1, index * 2 + 2), 16))
      end
      local canonical_hazard_bank1_art_hex = assert(
        os.getenv("PENTA_SCENE0B_CANONICAL_HAZARD_BANK1_ART"),
        "PENTA_SCENE0B_CANONICAL_HAZARD_BANK1_ART required")
      assert(#canonical_hazard_bank1_art_hex == 192 * 2
        and not canonical_hazard_bank1_art_hex:find("[^0-9A-Fa-f]"),
        "PENTA_SCENE0B_CANONICAL_HAZARD_BANK1_ART invalid")
      canonical_hazard_bank1_art = {}
      for index = 0, 191 do
        canonical_hazard_bank1_art[index + 1] = assert(tonumber(
          canonical_hazard_bank1_art_hex:sub(
            index * 2 + 1, index * 2 + 2), 16))
      end
      local hazard_phases_hex = assert(
        os.getenv("PENTA_SCENE0B_HAZARD_PHASES"),
        "PENTA_SCENE0B_HAZARD_PHASES required")
      assert(#hazard_phases_hex == 768 * 2
        and not hazard_phases_hex:find("[^0-9A-Fa-f]"),
        "PENTA_SCENE0B_HAZARD_PHASES invalid")
      hazard_phase_tiles = {}
      for index = 0, 767 do
        hazard_phase_tiles[index + 1] = assert(tonumber(
          hazard_phases_hex:sub(index * 2 + 1, index * 2 + 2), 16))
      end
      local expected_cram_hex = assert(
        os.getenv("PENTA_SCENE0B_EXPECTED_BG_CRAM"),
        "PENTA_SCENE0B_EXPECTED_BG_CRAM required")
      assert(#expected_cram_hex == 128
        and not expected_cram_hex:find("[^0-9A-Fa-f]"),
        "PENTA_SCENE0B_EXPECTED_BG_CRAM invalid")
      expected_bg_cram = {}
      for index = 0, 63 do
        expected_bg_cram[index + 1] = assert(tonumber(
          expected_cram_hex:sub(index * 2 + 1, index * 2 + 2), 16))
      end
      -- Echo the exact parsed oracle bytes from the child process. The
      -- offline binder independently reconstructs this artifact from the
      -- candidate, authenticated operator capture/SRAM, and pinned hazard
      -- fixture, so launch-environment drift cannot be hidden behind scalar
      -- mismatch counters.
      local oracle_path = OUT .. ".runtime-oracles.bin"
      local oracle_temporary = oracle_path .. ".tmp"
      local oracle_handle = assert(io.open(oracle_temporary, "wb"))
      for _, values in ipairs({
        immutable_source_packed, immutable_stage1_tables,
        canonical_bg_art, canonical_hazard_bank1_art, hazard_phase_tiles,
        expected_bg_cram,
      }) do
        for index = 1, #values do
          oracle_handle:write(string.char(values[index]))
        end
      end
      oracle_handle:close()
      assert(os.rename(oracle_temporary, oracle_path))
    end)
    if not config_ok then
      boot_fail("runtime-env-invalid", config_error)
      return
    end
    write_token_marker(".config-ready")

    local trace_ok, trace_value = pcall(function()
      return assert(io.open(OUT .. ".trace.tsv", "w"))
    end)
    if not trace_ok or not trace_value then
      boot_fail("trace-open-failed", trace_value)
      return
    end
    trace = trace_value
    if CACHE_AUDIT_OUT then
      local cache_ok, cache_value = pcall(function()
        return assert(io.open(CACHE_AUDIT_OUT, "w"))
      end)
      if not cache_ok or not cache_value then
        boot_fail("cache-audit-open-failed", cache_value)
        return
      end
      cache_audit = cache_value
      cache_audit:write(
        "event\tkind\tsample\tframe\tphase\tsvbk\tffb7\tffba\tscene" ..
        "\troom\tactive\tmenu\tff01\tscy\tdc0b\tdc00\tdc02\tc21b\tc2b8" ..
        "\tdf02\tdf0d\tdf4f\tdf51\tdf53\tdf54\tdf55\tdf56\tdf57" ..
        "\tdf58\tdf59\tdad7_7\tdad7_8\tdad7_9" ..
        "\tc624\tc627\tc630\tc633\tff99\tlcdc" ..
        "\twrite_address\told_value\tnew_value\tpc\n")
      cache_audit:flush()
    end
    write_token_marker(".trace-ready")
    runtime_initialized = true
  end
  if not state_loaded then
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_FILE)
    end)
    if not ok or result == false then
      finish("fail", "state-load-failed")
      return
    end
    state_loaded = true
    if not install_cache_audit_breakpoints() then
      finish("fail", "cache-audit-observer-install-failed")
      return
    end
    if cache_audit then write_token_marker(".cache-audit-ready") end
    if (emu:read8(0xFF70) % 0x08) ~= 1 then
      finish("fail", "initial-wram-bank-not-1")
      return
    end
    initial_scene = emu:read8(0xD880)
    initial_menu = emu:read8(0xFFE4)
    if initial_scene ~= 0x0B then
      finish("fail", "initial-scene-not-0B")
      return
    end
    if initial_menu ~= EXPECTED_INITIAL_MENU then
      finish("fail", "initial-menu-differs")
      return
    end
    if emu:read8(0xFFC1) ~= 0x01 then
      finish("fail", "initial-active-state-differs")
      return
    end
    for index = 0, 0xFF do
      runtime_lut[index] = emu:read8(0xC600 + index)
    end
    capture_immutable_source()
    last_owned = native_menu_owned()
    set_phase("captured")
    apply_keys(0)
    return
  end

  frame = frame + 1
  if frame > FRAME_LIMIT then
    finish("fail", "frame-limit")
    return
  end
  -- D880 plus C600 and the cache records are SVBK1-owned. A frame boundary can
  -- legitimately land inside the bank1 compiler while it has SVBK3 selected;
  -- reading those addresses then observes another bank and invents a room
  -- transition. Release input and defer this logical phase/sample until the
  -- native compiler restores SVBK1. This performs no gameplay-memory write.
  if (emu:read8(0xFF70) % 0x08) ~= 1 then
    deferred_wram_frames = deferred_wram_frames + 1
    apply_keys(0)
    return
  end
  -- During OAM DMA the CPU executes from HRAM and cannot read WRAM.  mGBA
  -- correctly returns $FF for D880/DCDC in that interval; treating that bus
  -- value as gameplay state invents a scene transition (and, on low-health
  -- captures, a death).  Defer the logical sample without advancing its phase
  -- and let the existing scene/active assertions grade the next readable
  -- callback.  Input is released so this observation cannot extend an edge.
  local current_pc = PENTA_SCENE0B_READ_PC()
  if current_pc >= 0xFF80 and current_pc <= 0xFFFE
      and emu:read8(0xD880) == 0xFF then
    PENTA_SCENE0B_OAM_DMA_UNREADABLE_FRAMES =
      PENTA_SCENE0B_OAM_DMA_UNREADABLE_FRAMES + 1
    PENTA_SCENE_HP_TAIL[#PENTA_SCENE_HP_TAIL + 1] = string.format(
      "f%d:dma:pc%04X", frame, current_pc)
    if #PENTA_SCENE_HP_TAIL > 64 then table.remove(PENTA_SCENE_HP_TAIL, 1) end
    apply_keys(0)
    return
  end
  phase_frame = phase_frame + 1
  PENTA_SCENE_HP_TAIL[#PENTA_SCENE_HP_TAIL + 1] = string.format(
    "f%d:s%02X:a%02X:hp%02X", frame, emu:read8(0xD880),
    emu:read8(0xFFC1), emu:read8(0xDCDC))
  if #PENTA_SCENE_HP_TAIL > 64 then table.remove(PENTA_SCENE_HP_TAIL, 1) end
  if emu:read8(0xD880) ~= 0x0B then
    scene_violation_frames = scene_violation_frames + 1
  end
  if emu:read8(0xFFC1) ~= 0x01 then
    active_violation_frames = active_violation_frames + 1
  end
  local owned = menu_owned()
  local native_owned = native_menu_owned()
  if native_owned and not last_owned then
    menu_open_events = menu_open_events + 1
  elseif last_owned and not native_owned then
    menu_close_events = menu_close_events + 1
  end
  last_owned = native_owned

  if scene_violation_frames > 0 then
    finish("fail", "scene-left-0B")
    return
  end
  if active_violation_frames > 0 then
    finish("fail", "active-state-left-01")
    return
  end

  local keys = 0
  if phase == "captured" then
    sample_phase()
    capture_samples = capture_samples + 1
    if capture_samples >= CAPTURE_FRAMES then
      if initial_menu ~= 0 then
        set_phase("menu_exit")
      else
        set_phase("repair_settle")
      end
    end
  elseif phase == "repair_settle" then
    -- This is candidate-rendered output immediately after the native close,
    -- including the first close of the initially menu-loaded operator seed.
    -- Sample every frame so a transient palette/tile smear cannot hide in the
    -- repair window before the menu is reopened.
    sample_phase()
    if phase_frame >= REPAIR_SETTLE then
      if initial_menu == 0 or opening_completed or capture_baseline() then
        set_phase("menu_entry")
      elseif phase_frame > REPAIR_SETTLE + 180 then
        finish("fail", "baseline-not-readable-before-reopen")
        return
      end
    end
  elseif phase == "menu_entry" then
    -- The stock edge-input poll is not guaranteed to run every host frame.
    -- Hold the sole native key until the game's own menu state acknowledges
    -- the edge, then release immediately on the next callback.
    keys = KEY_SELECT
    sample_phase()
    if owned and window_visible() then
      opening_completed = true
      set_phase("menu_hold")
      keys = 0
    elseif phase_frame > 180 then
      finish("fail", "select-open-not-acknowledged")
      return
    end
  elseif phase == "menu_hold" then
    sample_phase()
    if not owned or not window_visible() then
      finish("fail", "menu-lost-during-hold")
      return
    end
    menu_hold_samples = menu_hold_samples + 1
    if menu_hold_samples >= MENU_HOLD then
      set_phase("menu_exit")
    end
  elseif phase == "menu_exit" then
    keys = KEY_SELECT
    -- The initially open operator capture is an authenticated negative seed.
    -- Do not treat its still-loaded bad pixels as candidate output; the first
    -- close is only the native repair trigger. The later audited close after
    -- reopening supplies the required menu-exit rendered/state evidence.
    if opening_completed then sample_phase() end
    if not owned and not window_visible() then
      keys = 0
      if opening_completed then
        set_phase("post_close")
      else
        set_phase("repair_settle")
        -- Capture the exact acknowledged-close frame rather than starting on
        -- the following callback.  The still-open seed was excluded above;
        -- this closed frame is candidate responsibility.
        sample_phase()
      end
    elseif phase_frame > 180 then
      finish("fail", "select-close-not-acknowledged")
      return
    end
  elseif phase == "post_close" then
    if not baseline_ready then
      if not capture_baseline() then
        if phase_frame > 180 then
          finish("fail", "post-close-baseline-not-readable")
        end
        apply_keys(0)
        return
      end
    end
    sample_phase()
    if not dump_physical_planes() then
      finish("fail", "final-physical-planes-unreadable")
      return
    end
    post_close_samples = post_close_samples + 1
    if post_close_samples >= POST_CLOSE then
      set_phase("flush")
    end
  elseif phase == "flush" then
    -- mGBA queues PNG work; four quiet frames make the final screenshot and
    -- marker ordering deterministic before the launcher child is stopped.
    flush_frames = flush_frames + 1
    if flush_frames >= 4 then
      finish("ok", "complete")
      return
    end
  else
    finish("fail", "unknown-phase")
    return
  end
  apply_keys(keys)
end)

callbacks:add("shutdown", function()
  if finished then return end
  finished = true
  pcall(function() trace:close() end)
  pcall(function() if cache_audit then cache_audit:close() end end)
  pcall(function() write_report("fail", "unexpected-shutdown") end)
  pcall(function() write_completion_marker("fail") end)
end)

-- This is written only after both callback registrations and every top-level
-- API lookup succeeded. Python separately requires the earlier startup token,
-- so parse/load and callback-registration failures are distinguished quickly.
write_token_marker(".ready")
