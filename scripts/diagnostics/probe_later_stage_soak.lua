-- Multi-room soak for later-stage background integrity.
--
-- Environment:
--   SOAK_TARGET  FFBA value (1 = Stage 2, ... 6 = Stage 7)
--   SOAK_OUT     output prefix for .report/.log and per-room VRAM captures
--   SOAK_FRAMES  gameplay frames to exercise (default 8000)
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

local TARGET = tonumber(os.getenv("SOAK_TARGET") or "1")
local OUT = os.getenv("SOAK_OUT") or "tmp/penta_later_stage_soak"
local LIMIT = tonumber(os.getenv("SOAK_FRAMES") or "8000")
local SAMPLE_INTERVAL = tonumber(os.getenv("SOAK_SAMPLE_INTERVAL") or "5")
local TRACE_ADDRS = os.getenv("SOAK_TRACE_ADDRS") or ""
local VRAM_WATCH_ADDRS = os.getenv("SOAK_VRAM_WATCH_ADDRS") or ""
local PALETTE_TRACE = tonumber(os.getenv("SOAK_PALETTE_TRACE") or "0")
local TRACE_SEGMENT = tonumber(os.getenv("SOAK_TRACE_SEGMENT") or "")
local ATTR_TRACE_PATH = os.getenv("SOAK_ATTR_TRACE")
local LAYOUT_TRACE_PATH = os.getenv("SOAK_LAYOUT_TRACE")
local STREAM_TRACE_PATH = os.getenv("SOAK_STREAM_TRACE")
local FLIP_TRACE_PATH = os.getenv("SOAK_FLIP_TRACE")
local LCDC_TRACE_PATH = os.getenv("SOAK_LCDC_TRACE")
local SEMANTIC_WRITE_TRACE_PATH = os.getenv("SOAK_SEMANTIC_WRITE_TRACE")
local CAPTURE_FLIP_STATES = os.getenv("SOAK_FLIP_STATES") == "1"
local AUDIT_WRAM = os.getenv("SOAK_WRAM_AUDIT") == "1"
local CAPTURE_SCREENSHOTS = os.getenv("SOAK_SCREENSHOTS") == "1"
local CAPTURE_STABLE = tonumber(os.getenv("SOAK_CAPTURE_STABLE") or "4")
local WINDOW_HELPER_ADDR = tonumber(
  os.getenv("SOAK_WINDOW_HELPER_ADDR") or "0")
local WINDOW_HELPER_BANK = tonumber(
  os.getenv("SOAK_WINDOW_HELPER_BANK") or "0")
local EXPECTED_SCENE = TARGET + 2
local PRIMARY_FIXED_STORE = tonumber(os.getenv("SOAK_PRIMARY_FIXED_STORE") or "4844")
local KEY_A, KEY_START = 0x01, 0x08
local KEY_RIGHT, KEY_LEFT, KEY_UP, KEY_DOWN = 0x10, 0x20, 0x40, 0x80
local raw_vram = assert(emu.memory.vram)
local game_wram = assert(emu.memory.wram)
-- Native state belongs to physical WRAM bank 1. CPU-bus reads at a frame
-- callback can instead expose a temporary compiler bank or OAM-DMA $FF.
-- Do not change SVBK or use this accessor for bank-2/3 staging planes.
local function game_read(address)
  assert(address >= 0xD000 and address <= 0xDFFF)
  return game_wram:read8(address - 0xC000)
end

local f, phase, seeded, confirmed = 0, "title", false, false
local play_frame, expected_samples = 0, 0
local unsafe_attrs, unexpected_attrs, lava_mismatches = 0, 0, 0
local max_unsafe, max_unexpected, max_lava_mismatch = 0, 0, 0
local pickup_expected, pickup_mismatches, max_pickup_mismatch = 0, 0, 0
local material_expected, material_mismatches, max_material_mismatch = 0, 0, 0
local ffe4_zero_play_frames, ffe4_nonzero_play_frames = 0, 0
local first_ffe4_nonzero_play_frame, first_ffe4_nonzero_value = -1, -1
local window_helper_hits, window_helper_ffe4_nonzero_hits = 0, 0
local last_room, room_stable = -1, 0
local rooms, scenes, captured_rooms, captured_mismatches = {}, {}, {}, {}
local done = false
-- Optional read-only buffer lifetime trace. Physical WRAM avoids confusing
-- the bank-1 gameplay state with the bank-3 DMA source during a transfer.
if os.getenv("SOAK_DMA_TRACE") == "1" then
  local trace = assert(io.open(OUT .. ".dma-buffer.tsv", "w"))
  local wram = assert(emu.memory.wram)
  local writes = {}
  for row = 0, 23 do writes[row] = 0 end
  local events = 0
  local function record(kind, address, value)
    if play_frame > 1000 or events >= 5000 then return end
    if wram:read8(0x1880) ~= EXPECTED_SCENE then return end
    events = events + 1
    local counts = {}
    for row = 0, 23 do counts[#counts+1] = tostring(writes[row]) end
    trace:write(string.format("%s\t%d\t%d\t%04X\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\n",
      kind, f, play_frame, emu:readRegister("PC") & 65535,
      emu:read8(0xFF99), address or 0, value or 0,
      emu:read8(0xFFE0), emu:read8(0xFFC4), emu:read8(0xFF70),
      wram:read8(0x3280), table.concat(counts, ",")))
    trace:flush()
  end
  trace:write("kind\tframe\tplay\tpc\tbank\taddress\tvalue\tffe0\tffc4\tsvbk\tbuffer_row20col0\trow_write_counts\n")
  for offset = 0, 0x2FF do
    local watched = offset
    assert(emu:setWatchpoint(function(info)
      if (emu:read8(0xFF70) & 7) ~= 3 then return end
      writes[watched >> 5] = writes[watched >> 5] + 1
      if watched == 0x280 or watched == 0x00A then
        record("write", 0xD000 + watched, info.newValue & 255)
      end
    end, 0xD000 + watched, C.WATCHPOINT_TYPE.WRITE) > 0)
  end
  for _, pc in ipairs({0x42FC, 0x4324}) do
    local site = pc
    assert(emu:setBreakpoint(function() record("pipeline", site, 0) end, site) > 0)
  end
  assert(emu:setWatchpoint(function(info)
    record("dma", 0xFF55, info.newValue & 255)
  end, 0xFF55, C.WATCHPOINT_TYPE.WRITE) > 0)
end
local attr_trace = ATTR_TRACE_PATH and assert(io.open(ATTR_TRACE_PATH, "w")) or nil
local layout_trace = LAYOUT_TRACE_PATH and assert(io.open(LAYOUT_TRACE_PATH, "w")) or nil
local flip_trace = FLIP_TRACE_PATH and assert(io.open(FLIP_TRACE_PATH, "w")) or nil
local lcdc_trace = LCDC_TRACE_PATH and assert(io.open(LCDC_TRACE_PATH, "w")) or nil
local tile_copy_hits = 0
local tile_copy_map = 0
local wram_baseline, wram_changed = nil, 0
local wram_change_counts, wram_change_examples = {}, {}
local stream_writer_counts, stream_writer_events = {}, {}
local STREAM_EVENT_LIMIT = 256
local semantic_write_events = {}
local SEMANTIC_WRITE_EVENT_LIMIT = 512
-- Audit only DX-owned immutable WRAM. C4xx-CBxx is ordinary game state and
-- changes more often when a faster build advances farther through a route.
-- DAFA-DAFF is deliberately excluded because it is live Stage-7 metadata.
local WRAM_AUDIT_RANGES = {{0xD900, 0xD9FF}, {0xDA00, 0xDAF9}}

if WINDOW_HELPER_ADDR > 0 and WINDOW_HELPER_BANK > 0 then
  local breakpoint_id = emu:setBreakpoint(function()
    if phase ~= "play" or game_read(0xD880) ~= EXPECTED_SCENE
        or emu:read8(0xFF99) ~= WINDOW_HELPER_BANK then return end
    window_helper_hits = window_helper_hits + 1
    if emu:read8(0xFFE4) ~= 0 then
      window_helper_ffe4_nonzero_hits =
        window_helper_ffe4_nonzero_hits + 1
    end
  end, WINDOW_HELPER_ADDR)
  assert(type(breakpoint_id) == "number" and breakpoint_id > 0,
    "failed exact Window-helper breakpoint")
end

if lcdc_trace then
  -- mGBA does not install range watchpoints on I/O registers. These are the
  -- decoded LDH [$FF40],A sites that own dungeon map selection. Recording at
  -- the store gives both the current register and A, the value about to become
  -- live. The fixed and bank-1 clear sites catch temporary map-bit clears
  -- outside the two ordinary display-flip sites.
  local lcdc_post_writes = {
    {0x12EC, -1},
  }
  for _, record in ipairs(lcdc_post_writes) do
    local site, segment = record[1], record[2]
    local callback = function()
      if phase ~= "play" or game_read(0xD880) ~= EXPECTED_SCENE then return end
      lcdc_trace:write(string.format(
        "%d\t%02X\t%04X\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
        play_frame, emu:read8(0xFF99), site, segment,
        emu:read8(0xFF40), emu:readRegister("A") & 0xFF,
        game_read(0xDC0B), emu:read8(0xFFBD),
        emu:read8(0xFF43), emu:read8(0xFF42), game_read(0xDF4E)))
      lcdc_trace:flush()
    end
    if segment < 0 then emu:setBreakpoint(callback, site)
    else emu:setBreakpoint(callback, site, segment) end
  end
end

local LAVA5 = {
  [0x02]=true, [0x03]=true, [0x04]=true, [0x05]=true,
  [0x06]=true, [0x07]=true,
  [0x12]=true, [0x13]=true, [0x14]=true, [0x15]=true,
  [0x16]=true, [0x17]=true,
}
local LAVA7 = {[0x19]=true, [0x1A]=true}
-- Collision-audited against all 24 committed Stage 2-7 room captures. Apply
-- each family only in the tilesets where the corpus proves a complete pickup;
-- Stage 4's ambiguous pickup aliases remain neutral while its collision-free
-- floor and wall families are validated separately below.
local HEALTH_PICKUPS = {
  [0x88]=1, [0x89]=1, [0x96]=1, [0x98]=1, [0x99]=1,
}
local RARE_PICKUPS = {
  [0xAE]=2, [0xAF]=2, [0xBE]=2, [0xBF]=2,
  [0xC6]=2, [0xC7]=2, [0xD6]=2, [0xD7]=2,
}
local ARROW_PICKUPS = {
  [0xA0]=4, [0xA1]=4, [0xB0]=4, [0xB1]=4,
}
local STAGE4_FLOOR = {
  [0x01]=4, [0x02]=4, [0x03]=4, [0x04]=4,
  [0x05]=4, [0x06]=4, [0x07]=4, [0x08]=4,
}

local function stage_material(tile)
  if TARGET == 3 then
    if tile == 0x2D or tile == 0x2E then return 2 end
    return STAGE4_FLOOR[tile]
  end
  return nil
end

local function semantic_pickup(tile)
  if TARGET == 1 then return RARE_PICKUPS[tile] end
  if TARGET == 2 or TARGET == 5 then return HEALTH_PICKUPS[tile] end
  if TARGET == 4 then return HEALTH_PICKUPS[tile] or RARE_PICKUPS[tile] end
  if TARGET == 6 then return ARROW_PICKUPS[tile] or RARE_PICKUPS[tile] end
  return nil
end

local function visible_active_map_cell(address)
  local lcdc = emu:read8(0xFF40)
  -- The Stage-7 gameplay contract has LCD enabled and Window disabled. A
  -- menu/window route is a separate containment gate, not a dungeon-BG write.
  if (lcdc & 0x80) == 0 or (lcdc & 0x20) ~= 0 then return false end
  local base = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
  if address < base or address >= base + 0x400 then return false end
  local index = address - base
  local row, column = math.floor(index / 32), index & 31
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
  local cols = ((scx & 7) == 0) and 20 or 21
  local rows = ((scy & 7) == 0) and 18 or 19
  local visible_col, visible_row = false, false
  for offset = 0, cols - 1 do
    if ((first_col + offset) & 31) == column then visible_col = true end
  end
  for offset = 0, rows - 1 do
    if ((first_row + offset) & 31) == row then visible_row = true end
  end
  return visible_col and visible_row
end

if SEMANTIC_WRITE_TRACE_PATH then
  assert(emu:setRangeWatchpoint(function(info)
    if phase ~= "play" or game_read(0xD880) ~= EXPECTED_SCENE
        or emu:read8(0xFF47) ~= 0xE4 or game_read(0xDF4C) ~= 0
        or #semantic_write_events >= SEMANTIC_WRITE_EVENT_LIMIT then
      return
    end
    local address = info.address & 0xFFFF
    if not visible_active_map_cell(address) then return end
    local old_vbk = emu:read8(0xFF4F)
    local tile, attr
    if (old_vbk & 1) == 0 then
      tile = info.value & 0xFF
      emu:write8(0xFF4F, 1)
      attr = emu:read8(address)
    else
      attr = info.value & 0xFF
      emu:write8(0xFF4F, 0)
      tile = emu:read8(address)
    end
    emu:write8(0xFF4F, old_vbk)
    -- C600 is the candidate's exact per-tile Stage-7 attribute LUT. Checking
    -- every visible CPU write catches both directions of a trail: a pickup or
    -- lava tile briefly retaining neutral attrs, and an ordinary replacement
    -- tile briefly retaining the old colored attr. Whole-map HDMA is checked
    -- independently at the two pre-display publisher breakpoints below.
    local expected = emu:read8(0xC600 + tile)
    if attr ~= expected then
      semantic_write_events[#semantic_write_events + 1] = string.format(
        "f=%d room=%02X addr=%04X vbk=%d old=%02X new=%02X " ..
        "tile=%02X attr=%02X expected=%d bank=%02X pc=%04X " ..
        "scx=%02X scy=%02X count=%02X",
        play_frame, emu:read8(0xFFBD), address, old_vbk & 1,
        (info.oldValue or 0) & 0xFF, info.value & 0xFF,
        tile, attr, expected, emu:read8(0xFF99),
        emu:readRegister("PC") & 0xFFFF, emu:read8(0xFF43),
        emu:read8(0xFF42), game_read(0xDF4E))
    end
  end, 0x9800, 0x9FFF, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
end

if attr_trace then
  -- The stock caller selects the destination map immediately before the
  -- shared copy entry.  mGBA's Lua register accessor is not reliable in this
  -- environment, so record the two concrete control-flow entries instead.
  emu:setBreakpoint(function() tile_copy_map = 0x9C00 end, 0x42A0)
  emu:setBreakpoint(function() tile_copy_map = 0x9800 end, 0x42A5)
  emu:setBreakpoint(function()
    if phase ~= "play" or game_read(0xD880) ~= EXPECTED_SCENE then
      return
    end
    tile_copy_hits = tile_copy_hits + 1
    local bitset, rawset, packed_bits = {}, {}, 0
    for offset = 0, 575 do
      local tile = emu:read8(0xC1A0 + offset)
      rawset[#rawset + 1] = string.format("%02X", tile)
      local desired = ((TARGET == 3 and stage_material(tile))
        or (TARGET == 4 and LAVA5[tile])
        or (TARGET == 6 and LAVA7[tile])) and 1 or 0
      if desired ~= 0 then packed_bits = packed_bits + 2 ^ (offset % 8) end
      if offset % 8 == 7 then
        bitset[#bitset + 1] = string.format("%02X", packed_bits)
        packed_bits = 0
      end
    end
    attr_trace:write(string.format(
      "%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
      "%02X%02X%02X%02X%02X%02X\t%02X%02X%02X%02X%02X%02X\t" ..
      "%02X%02X%02X%02X%02X%02X\t%s\t%s\t%04X\n",
      tile_copy_hits, play_frame, emu:read8(0xFFBD),
      emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xC1A4),
      game_read(0xDF4F), emu:read8(0xFFE0),
      game_read(0xDF53), game_read(0xDF54), game_read(0xDF55),
      game_read(0xDF56), game_read(0xDF57), game_read(0xDF58),
      game_read(0xDAFA), game_read(0xDAFB), game_read(0xDAFC),
      game_read(0xDAFD), game_read(0xDAFE), game_read(0xDAFF),
      emu:read8(0xC6AF), emu:read8(0xC6C7), emu:read8(0xC6A1),
      emu:read8(0xC607), emu:read8(0xC605), emu:read8(0xC62D),
      table.concat(bitset), table.concat(rawset), tile_copy_map))
    attr_trace:flush()
  end, 0x42A7)
end

if STREAM_TRACE_PATH then
  -- Whole-map publication is already covered at $42A7. This optional trace
  -- identifies the direct packed-map writers used by later scrolling rooms,
  -- where tile IDs can otherwise outrun their CGB attribute plane. mGBA does
  -- not expose CPU VRAM writes through range watchpoints, so C1A0-C3DF is the
  -- nearest observable publication boundary.
  assert(emu:setRangeWatchpoint(function(info)
    if phase ~= "play" or play_frame < 40 or play_frame > 1200
        or (TARGET ~= 3 and TARGET ~= 4 and TARGET ~= 6)
        or game_read(0xD880) ~= EXPECTED_SCENE then
      return
    end
    local pc = emu:readRegister("PC") & 0xFFFF
    local bank = emu:read8(0xFF99) & 0xFF
    local key = string.format("%02X:%04X", bank, pc)
    stream_writer_counts[key] = (stream_writer_counts[key] or 0) + 1
    if #stream_writer_events < STREAM_EVENT_LIMIT then
      stream_writer_events[#stream_writer_events + 1] = string.format(
        "f=%d room=%02X bank=%02X pc=%04X addr=%04X old=%02X new=%02X scx=%02X scy=%02X",
        play_frame, emu:read8(0xFFBD), bank, pc,
        info.address & 0xFFFF, info.oldValue & 0xFF,
        info.newValue & 0xFF, emu:read8(0xFF43), emu:read8(0xFF42))
    end
  end, 0xC1A0, 0xC3E0, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
end

local function log(message)
  local fh = io.open(OUT .. ".log", "a")
  if fh then fh:write(string.format("f%06d p%06d %s\n", f, play_frame, message)); fh:close() end
end

do
  local fh = io.open(OUT .. ".log", "w")
  if fh then
    fh:write(string.format("target=%d expected_scene=%02X frames=%d\n",
      TARGET, EXPECTED_SCENE, LIMIT))
    fh:close()
  end
end

if VRAM_WATCH_ADDRS ~= "" then
  local installed = 0
  for raw in string.gmatch(VRAM_WATCH_ADDRS, "[^,]+") do
    local address = tonumber(raw)
    if address then
      local id = emu:setRangeWatchpoint(function(info)
        log(string.format(
          "vram_write addr=%04X value=%02X old=%02X vbk=%02X bank=%02X " ..
          "pc=%04X hl=%04X de=%04X bc=%04X scene=%02X room=%02X",
          info.address & 0xFFFF, info.value & 0xFF,
          (info.oldValue or 0) & 0xFF, emu:read8(0xFF4F),
          emu:read8(0xFF99), emu:readRegister("PC") & 0xFFFF,
          emu:readRegister("HL") & 0xFFFF,
          emu:readRegister("DE") & 0xFFFF,
          emu:readRegister("BC") & 0xFFFF,
          game_read(0xD880), emu:read8(0xFFBD)))
      end, address, address, C.WATCHPOINT_TYPE.WRITE_CHANGE)
      if id and id > 0 then installed = installed + 1 end
    end
  end
  log(string.format("vram_watchpoints=%d", installed))
end

if TRACE_ADDRS ~= "" then
  for raw in string.gmatch(TRACE_ADDRS, "[^,]+") do
    local address_text, segment_text = string.match(raw, "^([^@]+)@([^@]+)$")
    local address = tonumber(address_text or raw)
    local segment = tonumber(segment_text or "") or TRACE_SEGMENT
    if address then
      local callback = function()
        log(string.format(
          "breakpoint=%04X segment=%s pc=%04X scene=%02X room=%02X " ..
          "dcfd=%02X dd09=%02X a=%02X f=%02X scx=%02X scy=%02X " ..
          "decision=%02X bank=%02X svbk=%02X mapped4C54=%02X " ..
          "e=%02X h=%02X l=%02X phase=%02X bcps=%02X",
          address, tostring(segment), address, game_read(0xD880),
          emu:read8(0xFFBD), game_read(0xDCFD), game_read(0xDD09),
          emu:readRegister("A"), emu:readRegister("F"),
          emu:read8(0xFF43), emu:read8(0xFF42),
          emu:read8(0xFFE0), emu:read8(0xFF99), emu:read8(0xFF70),
          emu:read8(0x4C54), emu:readRegister("E"),
          emu:readRegister("H"), emu:readRegister("L"),
          game_read(0xDF4C), emu:read8(0xFF68)))
      end
      if segment then
        emu:setBreakpoint(callback, address, segment)
      else
        emu:setBreakpoint(callback, address, -1)
      end
    end
  end
end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for i = 1, 0x1F do emu:write8(base + i, 0x00) end
  end
end

local function audit_wram()
  if not AUDIT_WRAM then return end
  -- DF51=$A8 is the production install sentinel and lives in fixed WRAM. It
  -- reads $FF while native OAM DMA owns the CPU bus, so it is also the
  -- authoritative accessibility probe for the banked pages below.
  if emu:read8(0xDF51) ~= 0xA8 then return end
  -- D900/DA00 are immutable only in their owning CGB WRAM bank 1. The game
  -- legitimately selects banks 2/3 while compiling background attributes;
  -- reading the same CPU addresses without pinning SVBK compared unrelated
  -- cache planes and produced thousands of false ownership failures. mGBA's
  -- frame callback is instruction-atomic, so select bank 1 for the bounded
  -- read and restore the interrupted program's exact bank immediately.
  local old_svbk = emu:read8(0xFF70) & 0x07
  emu:write8(0xFF70, 0x01)
  -- During the native OAM DMA window the CPU bus exposes $FF and ignores
  -- this bank select. Stage 4's cadence can place a frame callback inside
  -- that window, making every audited byte appear to change to $FF and back
  -- on the next frame. Fail closed on the bank-select readback and defer the
  -- sample; a real bank-1 mutation remains visible on the next readable frame.
  if (emu:read8(0xFF70) & 0x07) ~= 0x01 then
    emu:write8(0xFF70, old_svbk)
    return
  end
  if not wram_baseline then
    wram_baseline = {}
    for _, range in ipairs(WRAM_AUDIT_RANGES) do
      for address = range[1], range[2] do
        wram_baseline[address] = emu:read8(address)
      end
    end
    emu:write8(0xFF70, old_svbk)
    return
  end
  for _, range in ipairs(WRAM_AUDIT_RANGES) do
    for address = range[1], range[2] do
      local observed = emu:read8(address)
      if observed ~= wram_baseline[address] then
        wram_changed = wram_changed + 1
        wram_change_counts[address] = (wram_change_counts[address] or 0) + 1
        if #wram_change_examples < 64 then
          wram_change_examples[#wram_change_examples + 1] = string.format(
            "%d:%04X:%02X>%02X", play_frame, address,
            wram_baseline[address], observed)
        end
        wram_baseline[address] = observed
      end
    end
  end
  emu:write8(0xFF70, old_svbk)
end

local function dump_range(path, first, last)
  local fh = assert(io.open(path, "wb"))
  for address = first, last do fh:write(string.char(emu:read8(address))) end
  fh:close()
end

local function capture_room(room)
  local prefix = OUT .. string.format(".room%02X", room)
  if CAPTURE_SCREENSHOTS then emu:screenshot(prefix .. ".png") end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  dump_range(prefix .. ".vram0.bin", 0x8000, 0x97FF)
  dump_range(prefix .. ".map0.bin", 0x9800, 0x9FFF)
  emu:write8(0xFF4F, 1)
  dump_range(prefix .. ".vram1.bin", 0x8000, 0x97FF)
  dump_range(prefix .. ".attr.bin", 0x9800, 0x9FFF)
  dump_range(prefix .. ".bg-lut.bin", 0xC600, 0xC6FF)
  -- Preserve the exact hardware sprites that produced the screenshot.  This
  -- is essential for semantic objects (pickups and hazards) whose artwork can
  -- be emitted as OBJ in one stage but baked into the BG map in another.
  dump_range(prefix .. ".oam.bin", 0xFE00, 0xFE9F)

  local old_bcps = emu:read8(0xFF68)
  local bgp = assert(io.open(prefix .. ".bgp.bin", "wb"))
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    bgp:write(string.char(emu:read8(0xFF69)))
  end
  bgp:close()
  emu:write8(0xFF68, old_bcps)

  local active_base = ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800
  local meta = assert(io.open(prefix .. ".meta", "w"))
  meta:write(string.format(
    "frame=%d target=%d expected_scene=%02X D880=%02X FFC1=%02X FFBA=%02X " ..
    "LCDC=%02X SCX=%02X SCY=%02X phase=%02X prelude=%02X " ..
    "active_map=%04X room=%02X\n",
    f, TARGET, EXPECTED_SCENE, game_read(0xD880), emu:read8(0xFFC1),
    emu:read8(0xFFBA), emu:read8(0xFF40), emu:read8(0xFF43),
    emu:read8(0xFF42), game_read(0xDF4C), emu:read8(0xFF91),
    active_base, room))
  meta:close()
  emu:write8(0xFF4F, old_vbk)
  log(string.format("captured room=%02X", room))
end

local function sample_visible()
  local lcdc, scx, scy = emu:read8(0xFF40), emu:read8(0xFF43), emu:read8(0xFF42)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
  local cols = ((scx & 7) == 0) and 20 or 21
  local rows = ((scy & 7) == 0) and 18 or 19
  local addresses, attrs = {}, {}
  local old_vbk = emu:read8(0xFF4F)

  if layout_trace then
    local raw, signature_a, signature_b = {}, 0, 0
    for offset = 0, 575 do
      raw[#raw + 1] = string.format("%02X", emu:read8(0xC1A0 + offset))
    end
    for _, offset in ipairs({444, 149, 19, 251}) do
      signature_a = signature_a ~ emu:read8(0xC1A0 + offset)
    end
    for _, offset in ipairs({0, 59, 333, 201}) do
      signature_b = signature_b ~ emu:read8(0xC1A0 + offset)
    end
    layout_trace:write(string.format(
      "%d\t%02X\t%04X\t%02X\t%02X\t%02X%02X%02X\t%02X%02X%02X\t" ..
      "%02X\t%02X\t%02X%02X%02X%02X\t%02X\t%02X\t" ..
      "%02X%02X%02X%02X\t%s\n",
      play_frame, emu:read8(0xFFBD), base, signature_a, signature_b,
      game_read(0xDF53), game_read(0xDF54), game_read(0xDF55),
      game_read(0xDF56), game_read(0xDF57), game_read(0xDF58),
      emu:read8(0xFF43), emu:read8(0xFF42),
      game_read(0xDC00), game_read(0xDC01),
      game_read(0xDC02), game_read(0xDC03),
      game_read(0xDC0B), emu:read8(0xFFCF),
      emu:read8(0xFFE8), emu:read8(0xFFE9),
      emu:read8(0xFFEA), emu:read8(0xFFEB),
      table.concat(raw)))
  end

  emu:write8(0xFF4F, 1)
  for y = 0, rows - 1 do
    for x = 0, cols - 1 do
      local row, col = (first_row + y) & 31, (first_col + x) & 31
      local address = base + row * 32 + col
      addresses[#addresses + 1] = address
      attrs[#attrs + 1] = emu:read8(address)
    end
  end

  emu:write8(0xFF4F, 0)
  local sample_unsafe, sample_unexpected, sample_lava_mismatch = 0, 0, 0
  local sample_pickup_expected, sample_pickup_mismatch = 0, 0
  local sample_material_expected, sample_material_mismatch = 0, 0
  local lava_mismatch_xy = {}
  local pickup_mismatch_xy = {}
  for index, address in ipairs(addresses) do
    local attr, tile = attrs[index], emu:read8(address)
    local semantic = semantic_pickup(tile)
    local material = stage_material(tile)
    local expected = semantic or material
    local lava = ((TARGET == 4 and LAVA5[tile])
      or (TARGET == 6 and LAVA7[tile])) and 5 or 0
    if (attr & 0xF8) ~= 0 then sample_unsafe = sample_unsafe + 1 end
    if expected then
      if semantic then
        sample_pickup_expected = sample_pickup_expected + 1
      else
        sample_material_expected = sample_material_expected + 1
      end
      if attr ~= expected then
        if semantic then
          sample_pickup_mismatch = sample_pickup_mismatch + 1
        else
          sample_material_mismatch = sample_material_mismatch + 1
        end
        sample_unexpected = sample_unexpected + 1
        local zero = index - 1
        pickup_mismatch_xy[#pickup_mismatch_xy + 1] = string.format(
          "%d:%d:%04X:%02X:%d>%d", zero % cols,
          math.floor(zero / cols), address, tile, attr, expected)
      end
    elseif attr ~= 0 and not (lava == 5 and attr == 5) then
      sample_unexpected = sample_unexpected + 1
    end
    -- Retain the established lava contract: reject palette-5 bleed onto
    -- non-lava art. A briefly neutral lava cell during direct streaming is a
    -- separately tracked historical limitation and is not this pickup fix.
    if attr == 5 and lava ~= 5 then
      sample_lava_mismatch = sample_lava_mismatch + 1
      local zero = index - 1
      lava_mismatch_xy[#lava_mismatch_xy + 1] = string.format(
        "%d:%d:%02X", zero % cols, math.floor(zero / cols), tile)
    end
  end
  emu:write8(0xFF4F, old_vbk)

  unsafe_attrs = unsafe_attrs + sample_unsafe
  unexpected_attrs = unexpected_attrs + sample_unexpected
  lava_mismatches = lava_mismatches + sample_lava_mismatch
  pickup_expected = pickup_expected + sample_pickup_expected
  pickup_mismatches = pickup_mismatches + sample_pickup_mismatch
  material_expected = material_expected + sample_material_expected
  material_mismatches = material_mismatches + sample_material_mismatch
  if sample_unsafe > max_unsafe then max_unsafe = sample_unsafe end
  if sample_unexpected > max_unexpected then max_unexpected = sample_unexpected end
  if sample_lava_mismatch > max_lava_mismatch then max_lava_mismatch = sample_lava_mismatch end
  if sample_pickup_mismatch > max_pickup_mismatch then
    max_pickup_mismatch = sample_pickup_mismatch
  end
  if sample_material_mismatch > max_material_mismatch then
    max_material_mismatch = sample_material_mismatch
  end
  if sample_lava_mismatch > 0 or sample_pickup_mismatch > 0
      or sample_material_mismatch > 0 then
    local signature_a, signature_b = 0, 0
    for _, offset in ipairs({444, 149, 19, 251}) do
      signature_a = signature_a ~ emu:read8(0xC1A0 + offset)
    end
    for _, offset in ipairs({0, 59, 333, 201}) do
      signature_b = signature_b ~ emu:read8(0xC1A0 + offset)
    end
    local mismatch_room = emu:read8(0xFFBD)
    if not captured_mismatches[mismatch_room] then
      captured_mismatches[mismatch_room] = true
      local mismatch_prefix = OUT .. string.format(
        ".mismatch.room%02X.f%06d", mismatch_room, play_frame)
      if CAPTURE_SCREENSHOTS then
        emu:screenshot(mismatch_prefix .. ".png")
      end
      dump_range(mismatch_prefix .. ".source.bin", 0xC1A0, 0xC3DF)
      local mismatch_vbk = emu:read8(0xFF4F)
      emu:write8(0xFF4F, 0)
      dump_range(mismatch_prefix .. ".map0.bin", 0x9800, 0x9FFF)
      emu:write8(0xFF4F, 1)
      dump_range(mismatch_prefix .. ".attr.bin", 0x9800, 0x9FFF)
      emu:write8(0xFF4F, mismatch_vbk)
      local mismatch_svbk = emu:read8(0xFF70)
      emu:write8(0xFF70, 2)
      dump_range(mismatch_prefix .. ".shadow.bin", 0xD000, 0xD7FF)
      dump_range(mismatch_prefix .. ".wram2-plane.bin", 0xD000, 0xD3FF)
      emu:write8(0xFF70, 3)
      dump_range(mismatch_prefix .. ".wram3-plane.bin", 0xD000, 0xD3FF)
      emu:write8(0xFF70, mismatch_svbk)
    end
    log(string.format(
      "lava_mismatch=%d pickup_mismatch=%d material_mismatch=%d room=%02X scene=%02X scx=%02X scy=%02X count=%02X cache=%02X sig=%02X/%02X meta=%02X%02X%02X/%02X%02X%02X xy=%s pickup_xy=%s",
      sample_lava_mismatch, sample_pickup_mismatch, sample_material_mismatch,
      emu:read8(0xFFBD), game_read(0xD880),
      emu:read8(0xFF43), emu:read8(0xFF42), game_read(0xDF4E),
      game_read(0xDF4F), signature_a, signature_b,
      game_read(0xDF53), game_read(0xDF54), game_read(0xDF55),
      game_read(0xDF56), game_read(0xDF57), game_read(0xDF58),
      table.concat(lava_mismatch_xy, ","),
      table.concat(pickup_mismatch_xy, ",")))
  end
  expected_samples = expected_samples + 1
end

if flip_trace then
  local flip_index = 0
  -- $12E0 and $0AB8 are the two stock $4295 producer continuations. Their
  -- actual LCDC stores are $12EC and $3095 respectively. Inspect immediately
  -- before those stores, deriving the camera that the continuation will make
  -- live (DC00/DC02 or pending DD85/DD87), while the destination must still
  -- be physically hidden.
  -- This mGBA build's raw VRAM domain exposes physical bank 0 only.  It stays
  -- readable during mode 3, so the online half of the gate checks all 576
  -- tile IDs here.  When SOAK_FLIP_STATES is armed, the matching PNG
  -- savestate's gbAs payload is the fail-closed offline authority for both
  -- physical VRAM banks, including all 576 attributes.
  local function trace_flip(
      site, explicit_base, explicit_scx, explicit_scy,
      require_hidden, camera_contract_ok, allow_transition)
    if phase ~= "play" or game_read(0xD880) ~= EXPECTED_SCENE
        or emu:read8(0xFFC1) ~= 1 then
      return
    end
    if not allow_transition
        and (emu:read8(0xFF47) ~= 0xE4 or game_read(0xDF4C) ~= 0) then
      return
    end
    flip_index = flip_index + 1
    local selector = game_read(0xDC0B) & 0x01
    local base = explicit_base or (selector ~= 0 and 0x9C00 or 0x9800)
    local scx = explicit_scx or emu:read8(0xFF43)
    local scy = explicit_scy or emu:read8(0xFF42)
    local stat_mode = emu:read8(0xFF41) & 0x03
    local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
    local cols = ((scx & 7) == 0) and 20 or 21
    local rows = ((scy & 7) == 0) and 18 or 19
    local mismatches, mismatch_count = {}, 0
    local function mismatch(text)
      mismatch_count = mismatch_count + 1
      if #mismatches < 32 then mismatches[#mismatches + 1] = text end
    end
    local current_lcdc = emu:read8(0xFF40)
    if camera_contract_ok == false then
      mismatch("camera-source-contract")
    end
    if require_hidden and (current_lcdc & 0x80) ~= 0 then
      local displayed = (current_lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
      if displayed == base then
        mismatch(string.format("visible-target:%04X", base))
      end
      if (current_lcdc & 0x20) ~= 0 then
        mismatch("window-enabled")
      end
    end
    if (emu:read8(0xFF70) & 0x07) ~= 0x01 then
      mismatch("publisher-svbk-not-1")
    end
    local state_name = "-"
    if CAPTURE_FLIP_STATES then
      state_name = string.format("flip%06d.ss0", flip_index)
      local state_path = OUT .. string.format(".flip%06d.ss0", flip_index)
      local ok, result = pcall(function()
        return emu:saveStateFile(state_path)
      end)
      if not ok or result == false then
        mismatch("savestate-failed")
      end
    end
    for row = 0, 23 do
      for col = 0, 23 do
        local source_offset = row * 24 + col
        local address = base + row * 32 + col
        local vram_offset = address - 0x8000
        local expected_tile = emu:read8(0xC1A0 + source_offset)
        local actual_tile = raw_vram:read8(vram_offset)
        if actual_tile ~= expected_tile then
          mismatch(string.format(
            "tile:%d:%d:%04X:%02X>%02X", col, row, address,
            actual_tile, expected_tile))
        end
      end
    end
    flip_trace:write(string.format(
      "%d\t%d\t%04X\t%d\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\t%s\t%s\n",
      flip_index, play_frame, site, stat_mode, selector, base,
      emu:read8(0xFFBD), scx, scy, game_read(0xDF04),
      game_read(0xDF4E), mismatch_count, table.concat(mismatches, ","),
      state_name))
    flip_trace:flush()
  end
  emu:setBreakpoint(function()
    local selector = game_read(0xDC0B) & 0x01
    local base = (emu:readRegister("A") & 0x08) ~= 0 and 0x9C00 or 0x9800
    local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
    if emu:read8(0xFF97) ~= 0x02 then
      scx = game_read(0xDC00) & 0x0F
      scy = game_read(0xDC02) & 0x0F
    end
    trace_flip(0x12E0, base, scx, scy, true,
      base == (selector ~= 0 and 0x9C00 or 0x9800), true)
  end, PRIMARY_FIXED_STORE)
  if os.getenv("SOAK_PRIMARY_BANK13_STORES") == "1" then
    local primary_frame,primary_lcdc=nil,nil
    for _, address in ipairs({0x7457,0x7462}) do
      local site=address
      assert(emu:setBreakpoint(function()
        local next_lcdc=emu:readRegister("A") & 0xFF
        local base=(next_lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
        -- The pinned primary's JR at 7459 lands at 7461, then repeats
        -- the same LCDC store. Only this paired idempotent write may target
        -- the already-active map; both events retain the full tile audit.
        local repeat_store=site==0x7462 and primary_frame==play_frame
          and primary_lcdc==next_lcdc and emu:read8(0xFF40)==next_lcdc
        trace_flip(site,base,nil,nil,not repeat_store,nil,true)
        if site==0x7457 then primary_frame,primary_lcdc=play_frame,next_lcdc
        else primary_frame,primary_lcdc=nil,nil end
      end,site,13)>0)
    end
  end
  emu:setBreakpoint(function()
    local selector = game_read(0xDC0B) & 0x01
    local base = (emu:readRegister("A") & 0x08) ~= 0 and 0x9C00 or 0x9800
    local scx = game_read(0xDD85) & 0x1F
    local scy = game_read(0xDD87) & 0x1F
    local camera_ok = emu:read8(0xFF43) == scx and emu:read8(0xFF42) == scy
      and base == (selector ~= 0 and 0x9C00 or 0x9800)
    trace_flip(0x3095, base, scx, scy, true, camera_ok, true)
  end, 0x3095)
  -- DC0B is not the sole display authority. Native room/reset paths also
  -- write LCDC bit 3 directly; audit the map selected by A at every decoded
  -- executable site. $43D8 is the post-publication continuation inside the
  -- force-$9800 room-builder loop and therefore validates every repeated
  -- direct copy, not just the first LCDC write.
  local function trace_bank1_lcdc(site)
    emu:setBreakpoint(function()
      if emu:read8(0xFF99) ~= 0x01 then return end
      local base = (emu:readRegister("A") & 0x08) ~= 0 and 0x9C00 or 0x9800
      trace_flip(site, base)
    end, site)
  end
  for _, raw_site in ipairs({
      0x405A, 0x43C1, 0x4FF3, 0x5560,
      0x752E, 0x7584, 0x75B0, 0x75DC,
  }) do
    local site = raw_site
    trace_bank1_lcdc(site)
  end
  emu:setBreakpoint(function()
    if emu:read8(0xFF99) ~= 0x01 then return end
    local base = (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800
    trace_flip(0x43D8, base)
  end, 0x43D8)
  for _, raw_site in ipairs({0x0FDC, 0x3B7E, 0x3D8D}) do
    local site = raw_site
    emu:setBreakpoint(function()
      local base = (emu:readRegister("A") & 0x08) ~= 0 and 0x9C00 or 0x9800
      trace_flip(site, base)
    end, site)
  end
end

local function write_report()
  local room_list, scene_list = {}, {}
  for room in pairs(rooms) do room_list[#room_list + 1] = room end
  for scene in pairs(scenes) do scene_list[#scene_list + 1] = scene end
  table.sort(room_list); table.sort(scene_list)
  local room_text, scene_text = {}, {}
  for _, room in ipairs(room_list) do room_text[#room_text + 1] = string.format("%02X", room) end
  for _, scene in ipairs(scene_list) do scene_text[#scene_text + 1] = string.format("%02X", scene) end

  local fh = assert(io.open(OUT .. ".report", "w"))
  fh:write(string.format(
    "target=%d stage=%d frames=%d expected_scene=%02X samples=%d rooms=%d " ..
    "unsafe=%d unexpected=%d lava_mismatch=%d max_unsafe=%d " ..
    "max_unexpected=%d max_lava_mismatch=%d pickup_expected=%d " ..
    "pickup_mismatch=%d max_pickup_mismatch=%d material_expected=%d " ..
    "material_mismatch=%d max_material_mismatch=%d wram_changed=%d " ..
    "ffe4_zero_play_frames=%d ffe4_nonzero_play_frames=%d " ..
    "first_ffe4_nonzero_play_frame=%d first_ffe4_nonzero_value=%d " ..
    "window_helper_hits=%d window_helper_ffe4_nonzero_hits=%d\n",
    TARGET, TARGET + 1, play_frame, EXPECTED_SCENE, expected_samples,
    #room_list, unsafe_attrs, unexpected_attrs, lava_mismatches,
    max_unsafe, max_unexpected, max_lava_mismatch, pickup_expected,
    pickup_mismatches, max_pickup_mismatch, material_expected,
    material_mismatches, max_material_mismatch, wram_changed,
    ffe4_zero_play_frames, ffe4_nonzero_play_frames,
    first_ffe4_nonzero_play_frame, first_ffe4_nonzero_value,
    window_helper_hits, window_helper_ffe4_nonzero_hits))
  fh:write("room_ids=" .. table.concat(room_text, ",") .. "\n")
  fh:write("scene_ids=" .. table.concat(scene_text, ",") .. "\n")
  local changed_addresses = {}
  for address in pairs(wram_change_counts) do
    changed_addresses[#changed_addresses + 1] = address
  end
  table.sort(changed_addresses)
  local changed_address_text = {}
  for _, address in ipairs(changed_addresses) do
    changed_address_text[#changed_address_text + 1] = string.format(
      "%04X:%d", address, wram_change_counts[address])
  end
  fh:write("wram_change_addresses=" .. table.concat(
    changed_address_text, ",") .. "\n")
  fh:write("wram_change_examples=" .. table.concat(
    wram_change_examples, ",") .. "\n")
  fh:close()
  if STREAM_TRACE_PATH then
    local trace = assert(io.open(STREAM_TRACE_PATH, "w"))
    local keys = {}
    for key in pairs(stream_writer_counts) do keys[#keys + 1] = key end
    table.sort(keys)
    trace:write("writers\n")
    for _, key in ipairs(keys) do
      trace:write(string.format("%s\t%d\n", key, stream_writer_counts[key]))
    end
    trace:write("events\n")
    for _, event in ipairs(stream_writer_events) do trace:write(event .. "\n") end
    trace:close()
  end
  if SEMANTIC_WRITE_TRACE_PATH then
    local trace = assert(io.open(SEMANTIC_WRITE_TRACE_PATH, "w"))
    for _, event in ipairs(semantic_write_events) do
      trace:write(event .. "\n")
    end
    trace:close()
  end
  if attr_trace then attr_trace:close(); attr_trace = nil end
  if layout_trace then layout_trace:close(); layout_trace = nil end
  if flip_trace then flip_trace:close(); flip_trace = nil end
  if lcdc_trace then lcdc_trace:close(); lcdc_trace = nil end
  local completion = assert(io.open(OUT .. ".done", "w"))
  completion:write("DONE\n")
  completion:close()
  done = true
  log("DONE")
  emu:stop()
end

local function gameplay_input()
  local cycle = play_frame % 120
  local keys = KEY_A
  if cycle < 20 then keys = keys + KEY_UP
  elseif cycle < 40 then keys = keys + KEY_DOWN
  elseif cycle < 60 then keys = keys + KEY_LEFT
  else keys = keys + KEY_RIGHT end
  return keys
end

callbacks:add("frame", function()
  if done then return end
  f = f + 1
  native_assistance.write(0xDCFD, 0x01)
  if not seeded and f >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    if f >= 300 and f < 306 then emu:setKeys(KEY_START)
    elseif f >= 360 and f < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if f >= 330 then phase = "level_select" end
    return
  end

  if phase == "level_select" and not confirmed then
    emu:write8(0xFFBA, TARGET)
    seed_sram()
    if f % 60 >= 10 and f % 60 < 16 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if game_read(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
      confirmed = true
      phase = "loading"
      log("level selected")
    end
    if f > 700 then log("failed to select level"); write_report() end
    return
  end

  if phase == "loading" then
    emu:write8(0xFFBA, TARGET)
    emu:setKeys(0)
    if game_read(0xD880) == EXPECTED_SCENE and emu:read8(0xFFC1) == 1 then
      phase = "play"
      log("stable gameplay entered")
    end
    if f > 30000 then log("failed to reach gameplay"); write_report() end
    return
  end

  play_frame = play_frame + 1
  local sampled_ffe4 = emu:read8(0xFFE4)
  if sampled_ffe4 == 0 then
    ffe4_zero_play_frames = ffe4_zero_play_frames + 1
  else
    ffe4_nonzero_play_frames = ffe4_nonzero_play_frames + 1
    if first_ffe4_nonzero_play_frame < 0 then
      first_ffe4_nonzero_play_frame = play_frame
      first_ffe4_nonzero_value = sampled_ffe4
    end
  end
  if PALETTE_TRACE > 0 and play_frame <= PALETTE_TRACE then
    local old_bcps = emu:read8(0xFF68)
    emu:write8(0xFF68, 0)
    local bg0_0 = emu:read8(0xFF69)
    emu:write8(0xFF68, 2)
    local bg0_2 = emu:read8(0xFF69)
    emu:write8(0xFF68, old_bcps)
    log(string.format(
      "palette phase=%02X prelude=%02X scene=%02X bgp=%02X bg0=%02X,%02X",
      game_read(0xDF4C), emu:read8(0xFF91), game_read(0xD880),
      emu:read8(0xFF47), bg0_0, bg0_2))
  end
  audit_wram()
  local scene, room = game_read(0xD880), emu:read8(0xFFBD)
  scenes[scene] = true
  if scene == EXPECTED_SCENE and emu:read8(0xFFC1) == 1 then
    rooms[room] = true
    if room == last_room then room_stable = room_stable + 1
    else
      last_room, room_stable = room, 0
      log(string.format("room=%02X", room))
    end
    -- Do not freeze a room receipt while the native entry fade still owns
    -- BGP or the bounded CRAM scheduler is mid-pass. Those frames are hidden
    -- by the DMG fade and can precede the stage-specific BG0 repair by dozens
    -- of frames; a release receipt must represent the stable rendered room.
    if room_stable >= CAPTURE_STABLE and emu:read8(0xFF47) == 0xE4
        and game_read(0xDF4C) == 0 and not captured_rooms[room] then
      captured_rooms[room] = true
      capture_room(room)
    end
    -- Room-entry rows are deliberately repaired beneath the stock DMG fade.
    -- Apply the same visibility contract as capture_room(): only assert the
    -- semantic plane once normal BGP is restored and the bounded palette
    -- scheduler is idle. Sampling hidden transition frames made a correct
    -- five-row priority repair look like persistent on-screen corruption.
    if play_frame % SAMPLE_INTERVAL == 0 and emu:read8(0xFF47) == 0xE4
        and game_read(0xDF4C) == 0 then
      sample_visible()
    end
  end

  emu:setKeys(gameplay_input())
  if play_frame >= LIMIT then write_report() end
end)
