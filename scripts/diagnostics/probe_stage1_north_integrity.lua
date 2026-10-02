-- Cold-start GAME START, hold north, and capture the first completed room.
--
-- This is deliberately route-driven: it never writes gameplay WRAM, SRAM,
-- scene IDs, room IDs, HP, or scroll state.  The only game input after the
-- title/stage confirmations is UP.  The resulting C1A0 packed room buffer and
-- both physical BG maps are compared with the untouched Japanese ROM by the
-- Python verifier.

local OUT = assert(os.getenv("STAGE1_NORTH_OUT"))
local boot_trace = os.getenv("NORTH_BOOT_FLAG_TRACE") == "1"
  and assert(io.open(OUT .. "/boot-flags.tsv", "w")) or nil
if boot_trace then
  boot_trace:write("frame\tpc\tbank\tscene\tffe1\tdf5d\tdf02\tdf08\tkeys\n")
end
local movement_trace = nil
if os.getenv("STAGE1_NORTH_MOVEMENT_TRACE") == "1" then
  movement_trace = assert(io.open(OUT .. "/movement.tsv", "w"))
  movement_trace:write("frame\twram_dc00_dc3f\thram\n")
end
local function observe_movement(number)
  if not movement_trace then return end
  local wram = assert(emu.memory.wram)
  local state, hram = {}, {}
  for offset = 0x1C00, 0x1C3F do
    state[#state+1] = string.format("%02X", wram:read8(offset))
  end
  for address = 0xFF80, 0xFFFE do
    hram[#hram+1] = string.format("%02X", emu:read8(address))
  end
  movement_trace:write(string.format("%d\t%s\t%s\n", number,
    table.concat(state), table.concat(hram)))
  movement_trace:flush()
end
local LIMIT = tonumber(os.getenv("STAGE1_NORTH_FRAMES") or "3000")
local PLAY_LIMIT = tonumber(os.getenv("STAGE1_NORTH_PLAY_FRAMES") or "1800")
local TARGET_CAMERA_TEXT = os.getenv("STAGE1_NORTH_TARGET_CAMERA")
local TARGET_CAMERA = TARGET_CAMERA_TEXT and tonumber(TARGET_CAMERA_TEXT) or nil
local TARGET_ROOM = tonumber(os.getenv("STAGE1_NORTH_TARGET_ROOM") or "1")
local TARGET_SETTLE = tonumber(os.getenv("STAGE1_NORTH_TARGET_SETTLE") or "8")
local SNAP_INTERVAL = tonumber(os.getenv("STAGE1_NORTH_SNAP_INTERVAL") or "0")
local FIRE = os.getenv("STAGE1_NORTH_FIRE") == "1"
local TRACE_FILE = os.getenv("STAGE1_NORTH_TRACE_FILE")
local TRACE_WRITES = os.getenv("STAGE1_NORTH_TRACE_WRITES") == "1"
local TRACE_CHR_WRITES = os.getenv("STAGE1_NORTH_TRACE_CHR_WRITES") == "1"
local TRACE_CAMERA_MIN = tonumber(
  os.getenv("STAGE1_NORTH_TRACE_CAMERA_MIN") or "0x02B0")
local TRACE_CAMERA_MAX = tonumber(
  os.getenv("STAGE1_NORTH_TRACE_CAMERA_MAX") or "0x02D0")
local TRACE_OPENING_STATE = os.getenv("STAGE1_NORTH_TRACE_OPENING_STATE") == "1"
local VIA_OPENING = os.getenv("STAGE1_NORTH_VIA_OPENING") == "1"
local STATE_OUT = os.getenv("STAGE1_NORTH_STATE_OUT")
local CGB_ROM = (emu:read8(0x0143) & 0x80) ~= 0

local KEY_A = 0x01
local KEY_START = 0x08
local KEY_UP = 0x40
local KEY_DOWN = 0x80

local frame = 0
local gameplay_frame = 0
local first_gameplay = -1
local movement_writers = nil
if movement_trace then
  movement_writers = assert(io.open(OUT .. "/movement-writers.tsv", "w"))
  movement_writers:write("frame\taddress\told\tnew\tpc\tbank\taf\tbc\tde\thl\n")
  for _, address in ipairs({0xDC00, 0xDC01, 0xDC02, 0xDC03}) do
    local watched = address
    assert(emu:setWatchpoint(function(info)
      if (emu:read8(0xFF70) & 7) > 1 then return end
      movement_writers:write(string.format("%d\t%04X\t%02X\t%02X\t%04X\t%02X\t%04X\t%04X\t%04X\t%04X\n",
        frame, watched, info.oldValue & 255, info.newValue & 255,
        emu:readRegister("PC") & 65535, emu:read8(0xFF99),
        emu:readRegister("AF") & 65535, emu:readRegister("BC") & 65535,
        emu:readRegister("DE") & 65535, emu:readRegister("HL") & 65535))
    end, watched, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  end
end
-- Optional read-only timing of the map-copy pipeline. Counts use mGBA's
-- emulated global clock, not host wall time spent in screenshots/callbacks.
local pipeline_profile = nil
local pipeline_abi = nil
local pipeline_sources = nil
local pipeline_attributes = nil
local pipeline_source_writes = nil
local deferred_profile = nil
if os.getenv("STAGE1_NORTH_PROFILE") == "1" then
  pipeline_abi = assert(io.open(OUT .. "/pipeline-abi.tsv", "w"))
  pipeline_abi:write("phase\tframe\taf\tbc\tde\thl\tsp\tsvbk\te0\tstack\n")
  if os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r397b-deferred-pipeline-7f1dcd6e" then
    deferred_profile = assert(io.open(OUT .. "/deferred-profile.tsv", "w"))
    deferred_profile:write("phase\tcycle\tframe\tcaller\tlatch\tstate\tie\tiflags\tly\n")
    for _, point in ipairs({{"service", 0x6C80, 26}, {"isr", 0x6C80, 28},
                            {"scan_return", 0x42C6, 1}, {"guard_return", 0x12DA, 0}}) do
      local label, address, bank = point[1], point[2], point[3]
      assert(emu:setBreakpoint(function()
        if first_gameplay < 0 then return end
        local caller = 0
        if label == "service" then
          local sp = emu:readRegister("SP") & 0xFFFF
          caller = emu:read8(sp + 8) | (emu:read8(sp + 9) << 8)
        end
        local latch = emu:read8(0xFFC4)
        deferred_profile:write(string.format("%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",
          label, emu:currentCycle(), frame, caller, latch, latch & 0x60,
          emu:read8(0xFFFF), emu:read8(0xFF0F), emu:read8(0xFF44)))
      end, address, bank) > 0)
    end
  end
  pipeline_profile = assert(io.open(OUT .. "/pipeline-profile.tsv", "w"))
  -- One 576-byte source plane per tiles_begin event, in TSV event order.
  -- Read fixed WRAM; do not switch banks or touch emulated state.
  pipeline_sources = assert(io.open(OUT .. "/pipeline-sources.bin", "wb"))
  -- Per attrs_compiled record: source576 + LUT256 + plane768 + helper121.
  -- The breakpoint precedes SVBK1 restoration, so CPU D000/D400 read bank3.
  pipeline_attributes = assert(io.open(OUT .. "/pipeline-attributes.bin", "wb"))
  local source_write_count, source_writers = 0, {}
  if os.getenv("STAGE1_NORTH_SOURCE_WRITERS") == "1" then
    pipeline_source_writes = assert(io.open(OUT .. "/pipeline-source-writes.tsv", "w"))
    pipeline_source_writes:write("frame\twrites\twriters\n")
    assert(emu:setRangeWatchpoint(function(info)
      if first_gameplay < 0 then return end
      source_write_count = source_write_count + 1
      local key = string.format("%02X:%04X", emu:read8(0xFF99), emu:readRegister("PC"))
      source_writers[key] = (source_writers[key] or 0) + 1
    end, 0xC1A0, 0xC3E0, C.WATCHPOINT_TYPE.WRITE) > 0)
  end
  pipeline_profile:write("phase\tcycle\tframe\tly\tsvbk\tworld_x\tworld_y\tscx\tscy\tlcdc\tcompleted_map\tpending\tcache98\troom98\tcache9c\troom9c\tkey1\tscene_bus\n")
  local points = CGB_ROM and {
    {"tiles_begin", 0x42A7, 1}, {"tiles_end", 0x42ED, 1},
    {"attrs_begin", 0x42FC, 1}, {"attrs_compiled", 0x4324, 1},
    {"attrs_dma_done", 0x4354, 1}, {"semantic_done", 0x4357, 1},
    {"publish_request", 0x12E0, 0},
    {"scanner_begin", 0x61B7, 19}, {"scanner_tail", 0x55C0, 19},
    {"wall_writer", 0x6C8F, 19}, {"semantic_exit", 0x6C50, 19},
    {"batch_dispatch", 0x4500, 20},
    {"native_ffc4_set", 0x50C5, 1},
    {"native_ffc4_clear", 0x50CA, 1},
    {"cache_decider", 0x4100, 21},
    {"cache_palette_invalidate", 0x6FE9, 13},
    {"cache_owner_invalidate", 0x6C9C, 21},
    {"tile_copy_service", 0x6C80, 26},
    {"commit", tonumber(os.getenv("STAGE1_NORTH_PUBLICATION_PC"),16),
      tonumber(os.getenv("STAGE1_NORTH_PUBLICATION_SEGMENT"),16)},
  } or {
    -- The untouched DMG copier is unrolled through $436D. DX's $42ED is
    -- inside that native loop and must never be mistaken for its exit.
    {"tiles_begin", 0x42A7, 1}, {"tiles_end", 0x436D, 1},
    {"publish_request", 0x12E0, 0},
    {"commit", 0x12EC, 0},
  }
  if CGB_ROM and (os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r405-six-tiles-79e83ac5"
    or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r406-metatile-pointer-267395bb"
    or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r407-stage1-pointer-1438d4d8"
    or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r412-metatile-increment-c558d955"
    or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r423-native-pointer-increment-4ba37fda"
    or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r424-stage5-private-pointer-a36469fe"
    or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r425-stage1-bulk-compile-ee8b32b3"
    or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r426-stage1-bulk-context-f6d9550d") then
    points[#points + 1] = {"tile_copy_guard_passed", 0x6C9C, 26}
    points[#points + 1] = {"tile_copy_guard_fallback", 0x7BF0, 26}
  end
  -- This address belongs only to the authenticated r363/r374 publisher.
  -- Absolute commits alone miss flips which reuse an already-built page.
  if CGB_ROM and tonumber(os.getenv("STAGE1_NORTH_PUBLICATION_PC"), 16) == 0x7457
      and tonumber(os.getenv("STAGE1_NORTH_PUBLICATION_SEGMENT"), 16) == 13 then
    if os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r404-relative-consume-607dd536"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r405-six-tiles-79e83ac5"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r406-metatile-pointer-267395bb"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r407-stage1-pointer-1438d4d8"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r408-precompile-eb88d017"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r409-precompile-abi-bb2468cc"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r410-bulk-attributes-27be530d"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r411-cached-only-edfade4e"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r412-metatile-increment-c558d955"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r423-native-pointer-increment-4ba37fda"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r424-stage5-private-pointer-a36469fe"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r425-stage1-bulk-compile-ee8b32b3"
      or os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT") == "r426-stage1-bulk-context-f6d9550d" then
      points[#points + 1] = {"relative_commit", 0x7462, 13}
    else
      points[#points + 1] = {"relative_commit", 0x745F, 13}
    end
  end
  for _, point in ipairs(points) do
    local label, address, bank = point[1], point[2], point[3]
    emu:setBreakpoint(function()
      if first_gameplay < 0 then return end
      local wram = assert(emu.memory.wram)
      if label == "attrs_compiled" then
        assert((emu:read8(0xFF70) & 7) == 3)
        local snapshot = {}
        for _, region in ipairs({{0xC1A0,576},{0xC600,256},{0xD000,768},{0xD400,121}}) do
          for n = 0, region[2]-1 do
            snapshot[#snapshot+1] = string.char(emu:read8(region[1]+n))
          end
        end
        pipeline_attributes:write(table.concat(snapshot))
      end
      if label == "attrs_compiled" or label == "attrs_dma_done" or label == "semantic_done" then
        local sp = emu:readRegister("SP") & 0xFFFF
        local words = {}
        for n = 0, 7 do words[#words + 1] = string.format("%04X",
          emu:read8(sp + n * 2) + 256 * emu:read8(sp + n * 2 + 1)) end
        pipeline_abi:write(string.format("%s\t%d\t%04X\t%04X\t%04X\t%04X\t%04X\t%02X\t%02X\t%s\n",
          label, frame, emu:readRegister("AF"), emu:readRegister("BC"),
          emu:readRegister("DE"), emu:readRegister("HL"), sp,
          emu:read8(0xFF70), emu:read8(0xFFE0), table.concat(words, ",")))
      end
      if label == "tiles_begin" then
        local source = {}
        for index = 0, 575 do
          source[#source + 1] = string.char(emu:read8(0xC1A0 + index))
        end
        pipeline_sources:write(table.concat(source))
        if pipeline_source_writes then
          local writers = {}
          for key, count in pairs(source_writers) do
            writers[#writers + 1] = key .. "=" .. tostring(count)
          end
          table.sort(writers)
          pipeline_source_writes:write(string.format("%d\t%d\t%s\n",
            frame, source_write_count, table.concat(writers, ",")))
          source_write_count, source_writers = 0, {}
        end
      end
      pipeline_profile:write(string.format("%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\n",
        label, emu:currentCycle(), frame, emu:read8(0xFF44), emu:read8(0xFF70),
        wram:read8(0x1C00), wram:read8(0x1C02),
        emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xFF40),
        emu:read8(0xFFC4), wram:read8(0x1F5C),
        wram:read8(0x1F53), wram:read8(0x1F54),
        wram:read8(0x1F57), wram:read8(0x1F58), emu:read8(0xFF4D), emu:read8(0xD880)))
    end, address, bank)
  end
end
local initial_room = -1
local room_changes = 0
local previous_room = -1
local window_frames = 0
local finished = false
local target_settle_frame = nil
local transitions = {}
local cfaa_transitions = {}
local snapshots = {}
local last_state = ""
local previous_cfaa = -1
local raw_vram = assert(emu.memory.vram)
local trajectory = assert(io.open(OUT .. "/trajectory.bin", "wb"))
-- The Stage-1 card is still physically selected during the first few CGB
-- gameplay callbacks.  Keep those pixels in a distinct evidence stream for
-- the reviewed opening room-05 visual control, but never promote them into
-- the authenticated physical-page-owner trajectory below.
local prepublication_trajectory = assert(io.open(
  OUT .. "/prepublication-trajectory.bin", "wb"))
local TRAJECTORY_SCHEMA = "penta-stage1-north-trajectory-v3"
local OWNER_STATUS_DMG = 0
local OWNER_STATUS_CGB_OWNED = 1
local OWNER_STATUS_CGB_MISSING = 2
local OWNER_STATUS_CGB_INVALID = 3
-- Python authenticates the complete candidate-specific publisher, including
-- the bank-13 VBlank helper for deferred variants. Bind the Lua breakpoint
-- to that exact preflight rather than whichever ROM bank is mapped here.
local publication_variant = assert(
  os.getenv("STAGE1_NORTH_PUBLICATION_VARIANT"))
local publication_pc = assert(tonumber(
  os.getenv("STAGE1_NORTH_PUBLICATION_PC"), 16))
local publication_segment = assert(tonumber(
  os.getenv("STAGE1_NORTH_PUBLICATION_SEGMENT"), 16))
local publication_primary_sha256 = assert(
  os.getenv("STAGE1_NORTH_PUBLICATION_PRIMARY_SHA256"))
local publication_primary_hex = assert(
  os.getenv("STAGE1_NORTH_PUBLICATION_PRIMARY_HEX"))
-- A room-local attribute decision belongs to the physical BG page built at
-- the native copier entry, not to whichever logical room byte happens to be
-- live when a later frame is sampled.  Arm the destination page with FFE5 at
-- bank 1:$42A7 and publish that owner only at the exact reviewed LCDC store,
-- immediately before the native instruction selects the page.  Legacy uses
-- $12EC; r320 commits SCX/SCY first and moves the atomic LCDC store to $12FF.
local pending_map_publications = {}
local physical_map_owners = {}
local physical_map_owner_epoch = 0
local map_owner_arm_events = 0
local map_owner_publications = 0
local map_owner_reused_commits = 0
local map_owner_superseded_arms = 0
local map_owner_invalid_arms = 0
local map_owner_invalid_commits = 0
local map_owner_missing_commits = 0
local map_owner_missing_trajectory_frames = 0
local map_owner_invalid_trajectory_frames = 0
local map_owner_trace = {}
local trace_keys = {}
local trace_key = 0
local trace_first_frame = nil
local trace_offset = 0
local room_write_events = {}
local room_build_events = {}
local source_build_events = {}
local compressed_source_events = {}
local source_write_events = {}
local source_pointer_write_events = {}
local camera_axis_write_events = {}
local vram_tile_write_events = {}
local chr_write_events = {}
local chr_write_count = 0
local chr_write_dropped = 0
local CHR_WRITE_LIMIT = 32768
local selector_transitions = {}
local previous_selector_state = ""
local atomic_wrap_hits = 0
local hazard_helper_hits = 0
local stage1_cache_trace = {}
local last_stage1_cache = ""
local opening_started = false
local opening_completed = false
local opening_title_frame = -1
local route_down_frame = VIA_OPENING and -1 or 180
local opening_state_writes = {}

-- Do not install diagnostic breakpoints on the ordinary release route. The
-- deployed mGBA headless build stops execution after a breakpoint callback,
-- which turned a successful DX hook traversal into a false Stage-1 freeze.
-- Dedicated write-trace runs below remain explicitly opt-in.

local function register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and value then return value end
  ok, value = pcall(function() return emu:readRegister(string.lower(name)) end)
  if ok and value then return value end
  return 0
end

local function bg_map_base(lcdc)
  return (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
end

local function arm_physical_map_publication()
  -- The numeric PC aliases into every switchable bank.  Segment-qualified
  -- registration plus this explicit bank check makes bank 1 authoritative.
  if emu:read8(0xFF99) ~= 0x01 then
    map_owner_invalid_arms = map_owner_invalid_arms + 1
    return
  end
  local destination_high = (register("HL") >> 8) & 0xFF
  if destination_high ~= 0x98 and destination_high ~= 0x9C then
    map_owner_invalid_arms = map_owner_invalid_arms + 1
    return
  end
  local destination = destination_high << 8
  if pending_map_publications[destination] ~= nil then
    -- A hidden page may be rebuilt more than once before selection.  Only
    -- the newest native source epoch can own the eventual presentation.
    map_owner_superseded_arms = map_owner_superseded_arms + 1
  end
  local room = emu:read8(0xFFE5)
  pending_map_publications[destination] = {
    room = room,
    arm_frame = frame,
  }
  map_owner_arm_events = map_owner_arm_events + 1
  if #map_owner_trace < 512 then
    map_owner_trace[#map_owner_trace + 1] = string.format(
      "f%d:arm:b%04X:r%02X", frame, destination, room)
  end
end

local function commit_physical_map_publication()
  local target_lcdc = register("A") & 0xFF
  local target_core = target_lcdc & 0x9F
  local paired_selector =
    ((target_lcdc & 0x08) ~= 0) ~= ((target_lcdc & 0x40) ~= 0)
  if (target_core ~= 0x83 and target_core ~= 0x8B)
      or ((publication_variant:match("^r357%-")
        or publication_variant:match("^r358%-")
        or publication_variant:match("^r359%-")
        or publication_variant:match("^r360%-")
        or publication_variant:match("^r361%-")
        or publication_variant:match("^r362%-")
        or publication_variant:match("^r363%-"))
        and not paired_selector) then
    map_owner_invalid_commits = map_owner_invalid_commits + 1
    return
  end
  local target_base = bg_map_base(target_lcdc)
  local pending = pending_map_publications[target_base]
  if pending ~= nil then
    pending_map_publications[target_base] = nil
    physical_map_owner_epoch = physical_map_owner_epoch + 1
    if physical_map_owner_epoch > 0xFFFE then
      map_owner_invalid_commits = map_owner_invalid_commits + 1
      return
    end
    local owner = {
      room = pending.room,
      epoch = physical_map_owner_epoch,
      arm_frame = pending.arm_frame,
      publish_frame = frame,
    }
    physical_map_owners[target_base] = owner
    map_owner_publications = map_owner_publications + 1
    if #map_owner_trace < 512 then
      map_owner_trace[#map_owner_trace + 1] = string.format(
        "f%d:publish:b%04X:r%02X:e%d:a%d", frame, target_base,
        owner.room, owner.epoch, owner.arm_frame)
    end
  elseif physical_map_owners[target_base] ~= nil then
    map_owner_reused_commits = map_owner_reused_commits + 1
  else
    map_owner_missing_commits = map_owner_missing_commits + 1
    if #map_owner_trace < 512 then
      map_owner_trace[#map_owner_trace + 1] = string.format(
        "f%d:missing:b%04X", frame, target_base)
    end
  end
end

local function active_physical_map_owner(lcdc)
  if not CGB_ROM then
    return OWNER_STATUS_DMG, 0xFF, 0xFFFF
  end
  if map_owner_invalid_arms ~= 0 or map_owner_invalid_commits ~= 0 then
    return OWNER_STATUS_CGB_INVALID, 0xFF, 0xFFFF
  end
  local owner = physical_map_owners[bg_map_base(lcdc)]
  if owner == nil then
    return OWNER_STATUS_CGB_MISSING, 0xFF, 0xFFFF
  end
  return OWNER_STATUS_CGB_OWNED, owner.room, owner.epoch
end

if CGB_ROM then
  assert(emu:setBreakpoint(
    arm_physical_map_publication, 0x42A7, 1) > 0)
  assert(emu:setBreakpoint(
    commit_physical_map_publication, publication_pc,
    publication_segment) > 0)
end

if TRACE_CHR_WRITES then
  -- The reported wall-edge corruption is exactly one physical bank-zero
  -- pattern page.  The complete stock $FFA4-$FFAB selector array feeds all
  -- eight physical pages $9000-$97FF, and DX historically borrowed several
  -- of those bytes.  Observe the whole loader transaction.  Keep this trace
  -- independent of the tile-map writer trace so the cold route can name every
  -- owner without enabling the much broader north-transition diagnostics.
  local function trace_chr_write(info)
    if CGB_ROM and (emu:read8(0xFF4F) & 0x01) ~= 0 then return end
    chr_write_count = chr_write_count + 1
    if #chr_write_events >= CHR_WRITE_LIMIT then
      chr_write_dropped = chr_write_dropped + 1
      return
    end
    local sp = register("SP") & 0xFFFF
    local caller = emu:read8((sp + 4) & 0xFFFF)
      | (emu:read8((sp + 5) & 0xFFFF) << 8)
    chr_write_events[#chr_write_events + 1] = string.format(
      "f%d:g%d:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:sp%04X:k%04X:u%02X%02X%02X%02X%02X%02X%02X%02X:l%02X:s%02X:r%02X:i%02X",
      frame, gameplay_frame, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      register("AF") & 0xFFFF, register("BC") & 0xFFFF,
      register("DE") & 0xFFFF, register("HL") & 0xFFFF,
      sp, caller,
      emu:read8(0xFFA4), emu:read8(0xFFA5),
      emu:read8(0xFFA6), emu:read8(0xFFA7),
      emu:read8(0xFFA8), emu:read8(0xFFA9),
      emu:read8(0xFFAA), emu:read8(0xFFAB),
      emu:read8(0xFF40), emu:read8(0xD880), emu:read8(0xFFBD),
      emu:read8(0xFFC1))
  end
  assert(emu:setRangeWatchpoint(function(info)
    trace_chr_write(info)
  -- mGBA's range end is exclusive. Keep the endpoint on an exact-address
  -- watchpoint as an independent guard against silently losing byte $FF.
  end, 0x9000, 0x97FF, C.WATCHPOINT_TYPE.WRITE) > 0)
  assert(emu:setWatchpoint(function(info)
    trace_chr_write(info)
  end, 0x97FF, C.WATCHPOINT_TYPE.WRITE) > 0)
end

local function trace_camera_active()
  local svbk = emu:read8(0xFF70) & 0x07
  if CGB_ROM and svbk ~= 0 and svbk ~= 1 then return 0xFFFF, false end
  local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
  return camera, camera >= TRACE_CAMERA_MIN and camera <= TRACE_CAMERA_MAX
end

if TRACE_OPENING_STATE then
  -- The stock ROM has nine direct LDH [$C1],A sites. Range watchpoints do
  -- not consistently fire for high-memory I/O in every mGBA build, so keep
  -- executable breakpoints as the authoritative write-site receipt.
  local ffc1_sites = {
    {0x0A20, 0x00}, {0x15CC, 0x00}, {0x15EE, 0x00},
    {0x19D0, 0x00}, {0x19FD, 0x00}, {0x25C8, 0x00},
    {0x40EE, 0x01}, {0x7896, 0x01}, {0x5C51, 0x07},
  }
  for _, row in ipairs(ffc1_sites) do
    local site, bank = row[1], row[2]
    assert(emu:setBreakpoint(function()
      if bank ~= 0 and emu:read8(0xFF99) ~= bank then return end
      if #opening_state_writes >= 256 then return end
      local sp = register("SP") & 0xFFFF
      local return1 = emu:read8(sp) | (emu:read8(sp + 1) << 8)
      local return2 = emu:read8(sp + 2) | (emu:read8(sp + 3) << 8)
      opening_state_writes[#opening_state_writes + 1] = string.format(
        "f%d:aFFC1:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:sp%04X:r%04X/%04X:s%02X:i%02X",
        frame, emu:read8(0xFFC1), register("A") & 0xFF,
        site, emu:read8(0xFF99), register("AF") & 0xFFFF,
        register("BC") & 0xFFFF, register("DE") & 0xFFFF,
        register("HL") & 0xFFFF, sp, return1, return2,
        emu:read8(0xD880), emu:read8(0xFFC1))
    end, site) > 0)
  end
  assert(emu:setRangeWatchpoint(function(info)
    if #opening_state_writes >= 256 then return end
    opening_state_writes[#opening_state_writes + 1] = string.format(
      "f%d:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:s%02X:i%02X",
      frame, info.address & 0xFFFF, info.oldValue & 0xFF,
      info.newValue & 0xFF, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, emu:read8(0xD880), emu:read8(0xFFC1))
  end, 0xFFC1, 0xFFC1, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  assert(emu:setRangeWatchpoint(function(info)
    if #opening_state_writes >= 256 then return end
    opening_state_writes[#opening_state_writes + 1] = string.format(
      "f%d:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:s%02X:i%02X",
      frame, info.address & 0xFFFF, info.oldValue & 0xFF,
      info.newValue & 0xFF, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, emu:read8(0xD880), emu:read8(0xFFC1))
  end, 0xDCFD, 0xDCFD, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
end

if TRACE_WRITES then
  assert(emu:setRangeWatchpoint(function(info)
    local camera, active = trace_camera_active()
    if not active then return end
    if #vram_tile_write_events >= 8192 then return end
    -- Tile IDs live in VRAM bank 0. Attribute writes to the same CPU address
    -- are deliberately excluded so this receipt identifies the terrain
    -- publisher that first exposes a malformed north-route row.
    if CGB_ROM and (emu:read8(0xFF4F) & 0x01) ~= 0 then return end
    vram_tile_write_events[#vram_tile_write_events + 1] = string.format(
      "f%d:g%d:c%04X:a%04X:o%02X:n%02X:p%04X:b%02X:l%02X:x%02X:y%02X:m%02X:d%02X%02X%02X%02X:q%02X:r%02X",
      frame, gameplay_frame, camera, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      emu:read8(0xFF40), emu:read8(0xFF43), emu:read8(0xFF42),
      emu:read8(0xDC0B), emu:read8(0xDC0C), emu:read8(0xDC0D),
      emu:read8(0xDC0E), emu:read8(0xDC0F),
      emu:read8(0xDF4E), emu:read8(0xDF04))
  end, 0x9800, 0x9FFF, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  assert(emu:setRangeWatchpoint(function(info)
    local camera, active = trace_camera_active()
    if not active then return end
    if #camera_axis_write_events >= 1024 then return end
    camera_axis_write_events[#camera_axis_write_events + 1] = string.format(
      "f%d:g%d:c%04X:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:d%02X%02X%02X%02X:i%02X/%02X",
      frame, gameplay_frame, camera, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      register("AF") & 0xFFFF, register("BC") & 0xFFFF,
      register("DE") & 0xFFFF, register("HL") & 0xFFFF,
      emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC02), emu:read8(0xDC03),
      emu:read8(0xFFBB), emu:read8(0xFFBC))
  end, 0xDC00, 0xDC03, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  assert(emu:setRangeWatchpoint(function(info)
    local camera, active = trace_camera_active()
    if not active then return end
    if #source_pointer_write_events >= 1024 then return end
    source_pointer_write_events[#source_pointer_write_events + 1] = string.format(
      "f%d:g%d:c%04X:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:d%02X%02X%02X%02X",
      frame, gameplay_frame, camera, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      register("AF") & 0xFFFF, register("BC") & 0xFFFF,
      register("DE") & 0xFFFF, register("HL") & 0xFFFF,
      emu:read8(0xDC0C), emu:read8(0xDC0D),
      emu:read8(0xDC0E), emu:read8(0xDC0F))
  end, 0xDC0C, 0xDC0F, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  assert(emu:setRangeWatchpoint(function(info)
    local camera, active = trace_camera_active()
    if not active then return end
    if #room_write_events >= 2048 then return end
    room_write_events[#room_write_events + 1] = string.format(
      "f%d:g%d:c%04X:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X",
      frame, gameplay_frame, camera, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      register("AF") & 0xFFFF, register("BC") & 0xFFFF,
      register("DE") & 0xFFFF, register("HL") & 0xFFFF)
  end, 0xC1A0, 0xC1D0, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  assert(emu:setBreakpoint(function()
    local camera, active = trace_camera_active()
    if not active then return end
    if #room_build_events >= 32 then return end
    local source = emu:read8(0xDC0E) | (emu:read8(0xDC0F) << 8)
    local bytes = {}
    for offset = 0, 0x9F do
      bytes[#bytes + 1] = string.format("%02X", emu:read8(source + offset))
    end
    room_build_events[#room_build_events + 1] = string.format(
      "f%d:g%d:c%04X:s%04X:pc%04X:bank%02X:cfaa%02X:c297%02X:c29b%02X:data%s",
      frame, gameplay_frame, camera, source, register("PC") & 0xFFFF,
      emu:read8(0xFF99), emu:read8(0xCFAA), emu:read8(0xC297),
      emu:read8(0xC29B), table.concat(bytes))
  end, 0x1399) > 0)
  assert(emu:setBreakpoint(function()
    local camera, active = trace_camera_active()
    if not active then return end
    if #source_build_events >= 256 then return end
    source_build_events[#source_build_events + 1] = string.format(
      "entry:f%d:g%d:c%04X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:d%02X%02X%02X%02X",
      frame, gameplay_frame, camera, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC02), emu:read8(0xDC03))
  end, 0x1322) > 0)
  assert(emu:setBreakpoint(function()
    local camera, active = trace_camera_active()
    if not active then return end
    if #source_build_events >= 256 then return end
    source_build_events[#source_build_events + 1] = string.format(
      "mapped:f%d:g%d:c%04X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X",
      frame, gameplay_frame, camera, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF)
  end, 0x1329) > 0)
  assert(emu:setBreakpoint(function()
    local camera, active = trace_camera_active()
    if not active then return end
    if #source_build_events >= 256 then return end
    source_build_events[#source_build_events + 1] = string.format(
      "source:f%d:g%d:c%04X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X",
      frame, gameplay_frame, camera, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF)
  end, 0x1334) > 0)
  local previous_compressed_camera = -1
  assert(emu:setBreakpoint(function()
    local camera, active = trace_camera_active()
    if not active or camera == previous_compressed_camera then return end
    previous_compressed_camera = camera
    if #compressed_source_events >= 256 then return end
    compressed_source_events[#compressed_source_events + 1] = string.format(
      "f%d:g%d:c%04X:p%04X:b%02X:de%04X:hl%04X:first%02X",
      frame, gameplay_frame, camera, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, emu:read8(register("DE") & 0xFFFF))
  end, 0x133E) > 0)
  assert(emu:setRangeWatchpoint(function(info)
    local camera, active = trace_camera_active()
    if not active then return end
    if #source_write_events >= 4096 then return end
    source_write_events[#source_write_events + 1] = string.format(
      "f%d:g%d:c%04X:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X",
      frame, gameplay_frame, camera, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      register("AF") & 0xFFFF, register("BC") & 0xFFFF,
      register("DE") & 0xFFFF, register("HL") & 0xFFFF)
  end, 0xC400, 0xC4B0, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
end

if TRACE_FILE then
  local trace = assert(io.open(TRACE_FILE, "r"))
  for line in trace:lines() do
    local sample_frame = tonumber(line:match('"f":(%d+)'))
    local sample_keys = tonumber(line:match('"keys":(%d+)'))
    if sample_frame and sample_keys then
      trace_keys[sample_frame] = sample_keys
      if trace_first_frame == nil or sample_frame < trace_first_frame then
        trace_first_frame = sample_frame
      end
    end
  end
  trace:close()
end

local function pulse(lo, hi, mask)
  return (frame >= lo and frame < hi) and mask or 0
end

local function dump_bytes(path, reader, base, length)
  local handle = assert(io.open(path, "wb"))
  for offset = 0, length - 1 do
    handle:write(string.char(reader(base + offset)))
  end
  handle:close()
end

-- Scene/active flags become visible during stage-card initialization. The
-- native loop is the shared execution boundary for stock and DX gameplay.
local entry_loop_observed = false
local native_gameplay_start = -1
local entry_table_captured = false
for offset, byte in ipairs({0xCD, 0x5D, 0x49, 0xCD, 0x5D, 0x49}) do
  assert(emu:read8(0x016C + offset - 1) == byte, "unknown native gameplay loop")
end
assert(emu:setBreakpoint(function()
  if entry_loop_observed then return end
  if assert(emu.memory.wram):read8(0x1880) ~= 0x02 then return end
  if emu:read8(0xFFC1) ~= 1 then return end
  entry_loop_observed = true
  native_gameplay_start = frame
end, 0x016C), "native gameplay entry observation breakpoint unavailable")

-- $09CE enables SRAM; its RET at $09D5 executes with access enabled.
-- Capture only after gameplay entry, never from a disabled-RAM frame sample.
local sram_enable_bytes = {0xF5, 0x3E, 0x0A, 0xEA, 0xFF, 0x1F, 0xF1, 0xC9}
for offset, byte in ipairs(sram_enable_bytes) do
  assert(emu:read8(0x09CE + offset - 1) == byte, "unknown SRAM enable routine")
end
assert(emu:setBreakpoint(function()
  if not entry_loop_observed or first_gameplay < 0 or entry_table_captured then return end
  dump_bytes(OUT .. "/metatiles-at-entry.bin", function(address)
    return emu:read8(address)
  end, 0xA400, 0x400)
  entry_table_captured = true
end, 0x09D5), "SRAM-enabled entry capture breakpoint unavailable")

local function hash_bytes(reader, base, length)
  local value = 0xA55A
  for offset = 0, length - 1 do
    value = ((value * 257) ~ reader(base + offset)) & 0xFFFFFFFF
  end
  return value
end

local function gameplay_presentation_settled()
  local lcdc = emu:read8(0xFF40)
  if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFFC1) ~= 0x01 then
    return false
  end
  if (lcdc & 0x81) ~= 0x81 then return false end
  if CGB_ROM then
    local svbk = emu:read8(0xFF70) & 0x07
    if emu:read8(0xFF55) ~= 0xFF then return false end
    if svbk ~= 0 and svbk ~= 1 then return false end
  end
  return true
end

local function finish(status)
  if finished then return end
  finished = true
  trajectory:close()
  prepublication_trajectory:close()
  emu:setKeys(0)
  emu:screenshot(OUT .. "/final.png")
  dump_bytes(OUT .. "/c1a0.bin", function(address)
    return emu:read8(address)
  end, 0xC1A0, 0x240)
  dump_bytes(OUT .. "/vram9800.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x9800, 0x400)
  dump_bytes(OUT .. "/vram9c00.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x9C00, 0x400)
  local old_vbk = emu:read8(0xFF4F) & 0x01
  emu:write8(0xFF4F, 1)
  dump_bytes(OUT .. "/vram9800-attrs.bin", function(address)
    return emu:read8(address)
  end, 0x9800, 0x400)
  dump_bytes(OUT .. "/vram9c00-attrs.bin", function(address)
    return emu:read8(address)
  end, 0x9C00, 0x400)
  emu:write8(0xFF4F, old_vbk)
  local lcdc = emu:read8(0xFF40)
  local scx = emu:read8(0xFF43)
  local scy = emu:read8(0xFF42)
  local map_base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local visible_tiles = assert(io.open(OUT .. "/visible-tiles.bin", "wb"))
  local visible_attrs = assert(io.open(OUT .. "/visible-attrs.bin", "wb"))
  for row = 0, 17 do
    for column = 0, 19 do
      local map_y = ((scy + row * 8) >> 3) & 0x1F
      local map_x = ((scx + column * 8) >> 3) & 0x1F
      local offset = map_base - 0x8000 + map_y * 32 + map_x
      visible_tiles:write(string.char(raw_vram:read8(offset)))
      emu:write8(0xFF4F, 1)
      visible_attrs:write(string.char(emu:read8(0x8000 + offset)))
      emu:write8(0xFF4F, old_vbk)
    end
  end
  visible_tiles:close()
  visible_attrs:close()
  local old_bcps = emu:read8(0xFF68)
  local bg_cram = assert(io.open(OUT .. "/bg-cram.bin", "wb"))
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    bg_cram:write(string.char(emu:read8(0xFF69)))
  end
  bg_cram:close()
  emu:write8(0xFF68, old_bcps)
  local old_ocps = emu:read8(0xFF6A)
  local obj_cram = assert(io.open(OUT .. "/obj-cram.bin", "wb"))
  for index = 0, 63 do
    emu:write8(0xFF6A, index)
    obj_cram:write(string.char(emu:read8(0xFF6B)))
  end
  obj_cram:close()
  emu:write8(0xFF6A, old_ocps)
  dump_bytes(OUT .. "/hardware-oam.bin", function(address)
    return emu:read8(address)
  end, 0xFE00, 0xA0)
  dump_bytes(OUT .. "/shadow-oam.bin", function(address)
    return emu:read8(address)
  end, 0xDA00, 0xA0)
  dump_bytes(OUT .. "/vram-low-tiles.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x8000, 0x800)
  dump_bytes(OUT .. "/vram-high-tiles.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x8800, 0x800)
  dump_bytes(OUT .. "/vram-signed-positive-tiles.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x9000, 0x800)
  dump_bytes(OUT .. "/world-final.bin", function(address)
    return emu:read8(address)
  end, 0xC780, 0x880)
  dump_bytes(OUT .. "/metatiles-final.bin", function(address)
    return emu:read8(address)
  end, 0xA400, 0x400)

  local state_saved = false
  if status == "ok" and STATE_OUT and STATE_OUT ~= "" then
    emu:screenshot(OUT .. "/stage1-hazard.png")
    local ok, result = pcall(function() return emu:saveStateFile(STATE_OUT) end)
    state_saved = ok and result ~= false
  end

  local report = assert(io.open(OUT .. "/probe.txt", "w"))
  report:write("status=" .. status .. "\n")
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format("first_gameplay=%d\n", first_gameplay))
  report:write(string.format("native_gameplay_start=%d\n", native_gameplay_start))
  report:write(string.format("native_gameplay_frames=%d\n",
    native_gameplay_start >= 0 and (frame - native_gameplay_start) or -1))
  report:write(string.format("gameplay_frames=%d\n", gameplay_frame))
  report:write(string.format("via_opening=%d\n", VIA_OPENING and 1 or 0))
  report:write(string.format(
    "opening_started=%d\n", opening_started and 1 or 0))
  report:write(string.format(
    "opening_completed=%d\n", opening_completed and 1 or 0))
  report:write(string.format("opening_title_frame=%d\n", opening_title_frame))
  report:write(string.format("initial_room=%02X\n", initial_room & 0xFF))
  report:write(string.format("final_room=%02X\n", emu:read8(0xFFBD)))
  report:write(string.format("room_changes=%d\n", room_changes))
  report:write(string.format("target_camera=%s\n",
    TARGET_CAMERA and string.format("%04X", TARGET_CAMERA) or "none"))
  report:write(string.format("target_settle_frames=%d\n", TARGET_SETTLE))
  report:write("trajectory_schema=" .. TRAJECTORY_SCHEMA .. "\n")
  report:write(string.format("cgb_rom=%d\n", CGB_ROM and 1 or 0))
  report:write("map_owner_publication_variant=" .. publication_variant .. "\n")
  report:write(string.format(
    "map_owner_publication_pc=%04X\n", publication_pc))
  report:write(
    "map_owner_publication_primary_sha256=" ..
    publication_primary_sha256 .. "\n")
  report:write(
    "map_owner_publication_primary_hex=" ..
    publication_primary_hex .. "\n")
  report:write(string.format(
    "map_owner_arm_events=%d\n", map_owner_arm_events))
  report:write(string.format(
    "map_owner_publications=%d\n", map_owner_publications))
  report:write(string.format(
    "map_owner_reused_commits=%d\n", map_owner_reused_commits))
  report:write(string.format(
    "map_owner_superseded_arms=%d\n", map_owner_superseded_arms))
  report:write(string.format(
    "map_owner_invalid_arms=%d\n", map_owner_invalid_arms))
  report:write(string.format(
    "map_owner_invalid_commits=%d\n", map_owner_invalid_commits))
  report:write(string.format(
    "map_owner_missing_commits=%d\n", map_owner_missing_commits))
  report:write(string.format(
    "map_owner_missing_trajectory_frames=%d\n",
    map_owner_missing_trajectory_frames))
  report:write(string.format(
    "map_owner_invalid_trajectory_frames=%d\n",
    map_owner_invalid_trajectory_frames))
  report:write(
    "map_owner_trace=" .. table.concat(map_owner_trace, ";") .. "\n")
  report:write(string.format("state_saved=%d\n", state_saved and 1 or 0))
  report:write("state_path=" .. (STATE_OUT or "") .. "\n")
  report:write(string.format("window_frames=%d\n", window_frames))
  report:write(string.format("final_cfaa=%02X\n", emu:read8(0xCFAA)))
  report:write(string.format("final_dcfd=%02X\n", emu:read8(0xDCFD)))
  report:write(string.format(
    "final_state=scene:%02X room:%02X ffc1:%02X ffe4:%02X lcdc:%02X " ..
    "scx:%02X scy:%02X wx:%02X wy:%02X dc00:%02X dc01:%02X " ..
    "dc02:%02X dc03:%02X c1a4:%02X\n",
    emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFFC1),
    emu:read8(0xFFE4), emu:read8(0xFF40), emu:read8(0xFF43),
    emu:read8(0xFF42), emu:read8(0xFF4B), emu:read8(0xFF4A),
    emu:read8(0xDC00), emu:read8(0xDC01), emu:read8(0xDC02),
    emu:read8(0xDC03), emu:read8(0xC1A4)))
  report:write(string.format(
    "final_hardware=hdma5:%02X vbk:%02X svbk:%02X lcdc:%02X\n",
    emu:read8(0xFF55), emu:read8(0xFF4F) & 0x01,
    emu:read8(0xFF70) & 0x07, emu:read8(0xFF40)))
  report:write(string.format(
    "c1a0_hash=%08X\n",
    hash_bytes(function(address) return emu:read8(address) end,
      0xC1A0, 0x240)))
  report:write(string.format(
    "vram9800_hash=%08X\n",
    hash_bytes(function(address)
      return raw_vram:read8(address - 0x8000)
    end, 0x9800, 0x400)))
  report:write("transitions=" .. table.concat(transitions, ";") .. "\n")
  report:write("cfaa_transitions=" .. table.concat(cfaa_transitions, ";") .. "\n")
  report:write("snapshots=" .. table.concat(snapshots, ";") .. "\n")
  report:write("room_writes=" .. table.concat(room_write_events, ";") .. "\n")
  report:write("room_builds=" .. table.concat(room_build_events, ";") .. "\n")
  report:write("source_builds=" .. table.concat(source_build_events, ";") .. "\n")
  report:write(
    "compressed_sources=" ..
    table.concat(compressed_source_events, ";") .. "\n")
  report:write("source_writes=" .. table.concat(source_write_events, ";") .. "\n")
  report:write(
    "source_pointer_writes=" ..
    table.concat(source_pointer_write_events, ";") .. "\n")
  report:write(
    "camera_axis_writes=" ..
    table.concat(camera_axis_write_events, ";") .. "\n")
  report:write(
    "vram_tile_writes=" ..
    table.concat(vram_tile_write_events, ";") .. "\n")
  report:write(string.format("chr_write_count=%d\n", chr_write_count))
  report:write(string.format(
    "chr_write_stored_count=%d\n", #chr_write_events))
  report:write(string.format(
    "chr_write_dropped_count=%d\n", chr_write_dropped))
  report:write(
    "chr_writes=" .. table.concat(chr_write_events, ";") .. "\n")
  report:write(
    "selector_transitions=" ..
    table.concat(selector_transitions, ";") .. "\n")
  report:write(string.format("atomic_wrap_hits=%d\n", atomic_wrap_hits))
  report:write(string.format("hazard_helper_hits=%d\n", hazard_helper_hits))
  report:write("stage1_cache_trace=" .. table.concat(stage1_cache_trace, ";") .. "\n")
  report:write("opening_state_writes=" .. table.concat(opening_state_writes, ";") .. "\n")
  report:close()
  if movement_trace then movement_trace:close(); movement_trace = nil end
  if movement_writers then movement_writers:close(); movement_writers = nil end
  if pipeline_profile then pipeline_profile:close() end
  if pipeline_abi then pipeline_abi:close() end
  if deferred_profile then deferred_profile:close() end
  if pipeline_sources then pipeline_sources:close() end
  if pipeline_attributes then pipeline_attributes:close() end
  if pipeline_source_writes then pipeline_source_writes:close() end
  -- `status=ok` is deliberately the first report field for human triage, so
  -- it is not evidence that the receipt is complete.  Publish this marker
  -- only after every final-state field and artifact has been flushed; the
  -- Python owner must wait for it before it may stop its emulator child.
  local done = assert(io.open(OUT .. "/probe.done.tmp", "w"))
  done:write("penta-stage1-north-probe-complete-v1\n")
  done:close()
  assert(os.rename(OUT .. "/probe.done.tmp", OUT .. "/probe.done"))
  -- mGBA-Qt can leave its event loop alive after saveStateFile succeeds and
  -- emu:quit is called in the same frame callback. Other state generators in
  -- this suite use os.exit after their receipt is flushed; do the same only
  -- for this explicit state-producing branch.
  if state_saved then os.exit(0) else emu:quit() end
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if boot_trace and frame <= 1000 then
    local physical = assert(emu.memory.wram)
    boot_trace:write(string.format("%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
      frame, register("PC") & 65535, emu:read8(0xFF99), physical:read8(0x1880),
      emu:read8(0xFFE1), physical:read8(0x1F5D), physical:read8(0x1F02),
      physical:read8(0x1F08), emu:read8(0xFF93)))
    boot_trace:flush()
    if frame == 1000 then boot_trace:close(); boot_trace = nil end
  end
  if first_gameplay >= 0 and frame <= first_gameplay + 360 then
    local context = assert(io.open(OUT .. "/entry-context.txt", "a"))
    local sample = {}
    for address = 0xA400, 0xA40F do
      sample[#sample+1] = string.format("%02X", emu:read8(address))
    end
    context:write(string.format("followup=%d pc=%04X bank=%02X table=%s\n",
      frame-first_gameplay, register("PC") & 65535, emu:read8(0xFF99),
      table.concat(sample)))
    local sp = register("SP") & 65535
    context:write(string.format("stack=%04X return=%04X df4c=%02X ffe1=%02X ff47=%02X df4e=%02X df08=%02X ffe7=%02X ffe6=%02X ff94=%02X\n",
      sp, emu:read8(sp) | (emu:read8((sp+1) & 65535) << 8),
      assert(emu.memory.wram):read8(0x1F4C), emu:read8(0xFFE1),
      emu:read8(0xFF47), assert(emu.memory.wram):read8(0x1F4E),
      assert(emu.memory.wram):read8(0x1F08), emu:read8(0xFFE7),
      emu:read8(0xFFE6), emu:read8(0xFF94)))
    context:write(string.format("stack_plus2=%04X stack_plus4=%04X ffe4=%02X dcf7=%02X fff4=%02X fff5=%02X ffd5=%02X ffc1=%02X\n",
      emu:read8((sp+2) & 65535) | (emu:read8((sp+3) & 65535) << 8),
      emu:read8((sp+4) & 65535) | (emu:read8((sp+5) & 65535) << 8),
      emu:read8(0xFFE4), assert(emu.memory.wram):read8(0x1CF7),
      emu:read8(0xFFF4), emu:read8(0xFFF5), emu:read8(0xFFD5), emu:read8(0xFFC1)))
    context:close()
  end
  observe_movement(frame)

  local scene = emu:read8(0xD880)
  local active = emu:read8(0xFFC1)
  local room = emu:read8(0xFFBD)
  local lcdc = emu:read8(0xFF40)
  local cfaa = emu:read8(0xCFAA)
  if first_gameplay >= 0 and #stage1_cache_trace < 128 then
    local cache = string.format(
      "%02X/%02X/%02X/%02X:s%04X", emu:read8(0xDF53),
      emu:read8(0xDF57), emu:read8(0xDF55), emu:read8(0xDF58),
      emu:read8(0xDC0E) | (emu:read8(0xDC0F) << 8))
    if cache ~= last_stage1_cache then
      stage1_cache_trace[#stage1_cache_trace + 1] = string.format(
        "f%d:g%d:%s", frame, gameplay_frame, cache)
      last_stage1_cache = cache
    end
  end
  if first_gameplay >= 0 then
    local selector_state = string.format(
      "%02X/%02X/%02X/%02X:%02X%02X:%02X%02X:%02X%02X:h%02X",
      emu:read8(0xDC0C), emu:read8(0xDC0D),
      emu:read8(0xDC0E), emu:read8(0xDC0F),
      emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC18), emu:read8(0xDC19),
      emu:read8(0xDC1A), emu:read8(0xDC1B),
      emu:read8(0xDC22))
    if selector_state ~= previous_selector_state
        and #selector_transitions < 2048 then
      selector_transitions[#selector_transitions + 1] = string.format(
        "f%d:g%d:c%02X%02X:%s",
        frame, gameplay_frame, emu:read8(0xDC03), emu:read8(0xDC02),
        selector_state)
      previous_selector_state = selector_state
    end
  end
  local state = string.format("%02X/%02X/%02X/%02X", scene, active, room, lcdc)
  if state ~= last_state and #transitions < 128 then
    transitions[#transitions + 1] = string.format("f%d:%s", frame, state)
    last_state = state
  end
  if cfaa ~= previous_cfaa and #cfaa_transitions < 256 then
    cfaa_transitions[#cfaa_transitions + 1] = string.format(
      "f%d:g%d:%02X", frame, gameplay_frame, cfaa)
    previous_cfaa = cfaa
  end
  if (lcdc & 0x20) ~= 0 and emu:read8(0xFF4A) < 144 then
    window_frames = window_frames + 1
  end

  local keys = 0
  if first_gameplay < 0 then
    if VIA_OPENING and not opening_completed then
      -- The first title option is OPENING. Use only released A pulses until
      -- the complete stock story returns to a freshly drawn title; never
      -- write a scene/script byte from the probe.
      if not opening_started then
        keys = pulse(180, 186, KEY_A)
          | pulse(300, 306, KEY_A)
          | pulse(420, 426, KEY_A)
        if scene == 0x15 then opening_started = true end
      elseif scene == 0x15 then
        keys = ((frame % 90) < 4) and KEY_A or 0
      elseif active == 1 and scene ~= 0x15 then
        -- OPENING transitions directly into the ordinary Stage-intro/gameplay
        -- route. There is no second title selection after a completed story.
        opening_completed = true
        opening_title_frame = frame
        keys = 0
      end
    else
      -- DOWN selects GAME START. Repeated released confirmations cover the
      -- stock score/stage cards without memory writes. The opening route uses
      -- the identical relative schedule after its returned title settles.
      local down = route_down_frame
      if TRACE_FILE and not VIA_OPENING then
        keys = keys | pulse(down, down + 6, KEY_DOWN)
        keys = keys | pulse(down + 21, down + 27, KEY_A)
        keys = keys | pulse(down + 81, down + 87, KEY_A)
        keys = keys | pulse(down + 141, down + 147, KEY_A)
        keys = keys | pulse(down + 201, down + 207, KEY_START)
        keys = keys | pulse(down + 251, down + 257, KEY_A)
      else
        keys = keys | pulse(down, down + 6, KEY_DOWN)
        keys = keys | pulse(down + 13, down + 19, KEY_A)
        keys = keys | pulse(down + 61, down + 67, KEY_A)
        keys = keys | pulse(down + 111, down + 117, KEY_A)
        keys = keys | pulse(down + 161, down + 167, KEY_START)
        keys = keys | pulse(down + 211, down + 217, KEY_A)
      end
    end
    if scene == 0x02 and active == 1 then
      first_gameplay = frame
      local entry_context = assert(io.open(OUT .. "/entry-context.txt", "w"))
      entry_context:write(string.format("frame=%d\npc=%04X\nsvbk=%02X\nrom_bank=%02X\nphysical_scene=%02X\n",
        frame, register("PC") & 65535, emu:read8(0xFF70),
        emu:read8(0xFF99), assert(emu.memory.wram):read8(0x1880)))
      entry_context:close()
      dump_bytes(OUT .. "/world-at-entry.bin", function(address)
        return emu:read8(address)
      end, 0xC780, 0x880)
      if TRACE_FILE then trace_offset = frame - assert(trace_first_frame) end
      initial_room = room
      previous_room = room
      keys = TRACE_FILE and trace_key or (KEY_UP | (FIRE and KEY_A or 0))
    end
  else
    gameplay_frame = gameplay_frame + 1
    if TRACE_FILE then
      local source_frame = frame - trace_offset
      if trace_keys[source_frame] ~= nil then trace_key = trace_keys[source_frame] end
      keys = trace_key
    else
      keys = KEY_UP | (FIRE and KEY_A or 0)
    end
    -- Record the entire route, not just its final settled room. The previous
    -- gate missed a Pocket-visible void because the corrupted intermediate
    -- map was replaced before the endpoint snapshot. Each record is keyed by
    -- room/camera and contains the complete 21x19 tile and VBK1 attribute
    -- viewports (including partially visible edge tiles) from the currently
    -- displayed BG map.
    local trajectory_lcdc = emu:read8(0xFF40)
    local trajectory_scx = emu:read8(0xFF43)
    local trajectory_scy = emu:read8(0xFF42)
    local trajectory_camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    local trajectory_base = ((trajectory_lcdc & 0x08) ~= 0) and 0x1C00 or 0x1800
    local trajectory_vbk = emu:read8(0xFF4F) & 0x01
    local owner_status, owner_room, owner_epoch =
      active_physical_map_owner(trajectory_lcdc)
    -- The first three gameplay callbacks can precede the first native map
    -- compiler publication. They have no authenticated physical-page owner,
    -- so they are not valid viewport evidence. Start the CGB trajectory at
    -- the first observed owner; once started, every missing owner remains a
    -- hard failure below.
    local owner_ready = not CGB_ROM or map_owner_publications > 0
    if owner_ready and owner_status == OWNER_STATUS_CGB_MISSING then
      map_owner_missing_trajectory_frames =
        map_owner_missing_trajectory_frames + 1
    elseif owner_ready and owner_status == OWNER_STATUS_CGB_INVALID then
      map_owner_invalid_trajectory_frames =
        map_owner_invalid_trajectory_frames + 1
    end
    local trajectory_sink = owner_ready and trajectory or prepublication_trajectory
    trajectory_sink:write(string.char(
      gameplay_frame & 0xFF, (gameplay_frame >> 8) & 0xFF,
      room & 0xFF, trajectory_camera & 0xFF,
      (trajectory_camera >> 8) & 0xFF, trajectory_lcdc,
      trajectory_scx, trajectory_scy,
      emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC0C), emu:read8(0xDC0D),
      emu:read8(0xDC0E), emu:read8(0xDC0F),
      emu:read8(0xDC18), emu:read8(0xDC19),
      emu:read8(0xDC1A), emu:read8(0xDC1B),
      emu:read8(0xDC22), scene, active,
      emu:read8(0xFFBB), emu:read8(0xFFBC),
      emu:read8(0xDC81),
      emu:read8(0xDA00), emu:read8(0xDA01),
      emu:read8(0xFF70) & 0x07,
      owner_status, owner_room,
      owner_epoch & 0xFF, (owner_epoch >> 8) & 0xFF))
    emu:write8(0xFF4F, 0)
    for trajectory_row = 0, 18 do
      for trajectory_column = 0, 20 do
        local map_y = ((trajectory_scy + trajectory_row * 8) >> 3) & 0x1F
        local map_x = ((trajectory_scx + trajectory_column * 8) >> 3) & 0x1F
        trajectory_sink:write(string.char(emu:read8(
          0x8000 + trajectory_base + map_y * 32 + map_x)))
      end
    end
    emu:write8(0xFF4F, 1)
    for trajectory_row = 0, 18 do
      for trajectory_column = 0, 20 do
        local map_y = ((trajectory_scy + trajectory_row * 8) >> 3) & 0x1F
        local map_x = ((trajectory_scx + trajectory_column * 8) >> 3) & 0x1F
        trajectory_sink:write(string.char(emu:read8(
          0x8000 + trajectory_base + map_y * 32 + map_x)))
      end
    end
    emu:write8(0xFF4F, trajectory_vbk)
    if SNAP_INTERVAL > 0 and gameplay_frame % SNAP_INTERVAL == 0 then
      local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
      local name = string.format(
        "route-g%04d-r%02X-c%04X.png", gameplay_frame, room, camera)
      emu:screenshot(OUT .. "/" .. name)
      snapshots[#snapshots + 1] = string.format(
        "g%d:r%02X:c%04X:l%02X:y%02X:w%02X:d%02X:m98%08X:m9c%08X:c1%08X",
        gameplay_frame, room, camera, lcdc, emu:read8(0xFF4A),
        emu:read8(0xFF4B), emu:read8(0xDCFD),
        hash_bytes(function(address)
          return raw_vram:read8(address - 0x8000)
        end, 0x9800, 0x400),
        hash_bytes(function(address)
          return raw_vram:read8(address - 0x8000)
        end, 0x9C00, 0x400),
        hash_bytes(function(address) return emu:read8(address) end,
          0xC1A0, 0x240))
    end
    if room ~= previous_room then
      room_changes = room_changes + 1
      previous_room = room
    end
    local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    local reached_target = TARGET_CAMERA ~= nil
      and room == TARGET_ROOM and camera == TARGET_CAMERA
    if target_settle_frame ~= nil then
      keys = 0
      if gameplay_frame - target_settle_frame >= TARGET_SETTLE
          and gameplay_presentation_settled() then
        emu:setKeys(keys)
        finish("ok")
        return
      end
    elseif reached_target then
      target_settle_frame = gameplay_frame
      keys = 0
    elseif TARGET_CAMERA == nil and gameplay_frame >= PLAY_LIMIT then
      keys = 0
      if gameplay_presentation_settled() then
        emu:setKeys(keys)
        finish("ok")
        return
      end
    end
  end
  emu:setKeys(keys)

  if frame >= LIMIT then finish("timeout") end
end)
