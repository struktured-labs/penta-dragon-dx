-- Consecutive-frame receipt for the Stage 1 low-health warning state.

local OUT = assert(os.getenv("LOW_HEALTH_OUT"), "LOW_HEALTH_OUT is required")
local SETTLE = tonumber(os.getenv("LOW_HEALTH_SETTLE") or "120")
local SAMPLES = tonumber(os.getenv("LOW_HEALTH_SAMPLES") or "240")
local PRE_TRIGGER = tonumber(os.getenv("LOW_HEALTH_PRE_TRIGGER") or "60")
local HEALTHY_MAIN = tonumber(os.getenv("LOW_HEALTH_HEALTHY_MAIN") or "1")
local LOW_SUB = tonumber(os.getenv("LOW_HEALTH_LOW_SUB") or "12")
local POST_TRIGGER_KEYS = tonumber(
  os.getenv("LOW_HEALTH_POST_TRIGGER_KEYS") or "0")
local TRACE_SCANNER = os.getenv("LOW_HEALTH_TRACE_SCANNER") == "1"
local TRACE_ATTR = os.getenv("LOW_HEALTH_TRACE_ATTR") == "1"
local frame, sample, done = 0, 0, false
local music_transition_seen = false
local scanner_path = "entry"
local scanner_trace_count = 0

if TRACE_ATTR then
  local attr_trace = assert(io.open(OUT .. ".attr-writes.tsv", "w"))
  attr_trace:write("frame\taddress\tpc\tbank\tvbk\told\tnew\tlcdc\td880\troom\n")
  attr_trace:close()
end

local function register(name)
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

local writes = assert(io.open(OUT .. ".writes.tsv", "w"))
writes:write("frame\tpc\tbank\told\tnew\tly\tstat\td880\tffc1\thp_sub\thp_main\n")
writes:close()

if TRACE_SCANNER then
  local scanner_trace = assert(io.open(OUT .. ".scanner.tsv", "w"))
  scanner_trace:write(
    "frame\tsample\tpoint\tpath\tpc\tbank\thl\tbc\tsp\tstack0\tstack1" ..
    "\tscene\troom\tdc0b\tdc0e\tvbk\n")
  scanner_trace:close()
end

if TRACE_ATTR then
  for _, address in ipairs({0x998D, 0x9D10}) do
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
  if not TRACE_SCANNER or emu:read8(0xFF99) ~= 0x0E or
      scanner_trace_count >= 4096 then return end
  if path then scanner_path = path end
  local sp = register("SP") & 0xFFFF
  local handle = assert(io.open(OUT .. ".scanner.tsv", "a"))
  handle:write(string.format(
    "%d\t%d\t%s\t%s\t%04X\t%02X\t%04X\t%04X\t%04X\t%04X\t%04X" ..
    "\t%02X\t%02X\t%02X\t%02X\t%02X\n",
    frame, sample, point, scanner_path, register("PC") & 0xFFFF,
    emu:read8(0xFF99), register("HL") & 0xFFFF,
    register("BC") & 0xFFFF, sp,
    emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8),
    emu:read8((sp + 2) & 0xFFFF) |
      (emu:read8((sp + 3) & 0xFFFF) << 8),
    emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xDC0B),
    emu:read8(0xDC0E), emu:read8(0xFF4F)))
  handle:close()
  scanner_trace_count = scanner_trace_count + 1
end

if TRACE_SCANNER then
  pcall(function()
    emu:setBreakpoint(function() trace_scanner("front", "entry") end, 0x61B7)
    emu:setBreakpoint(function() trace_scanner("start4", "start4") end, 0x618F)
    emu:setBreakpoint(function() trace_scanner("start5", "start5") end, 0x6194)
    emu:setBreakpoint(function() trace_scanner("start0", "start0") end, 0x619E)
    emu:setBreakpoint(function() trace_scanner("seam", "seam") end, 0x6CE9)
    emu:setBreakpoint(function() trace_scanner("write", nil) end, 0x61A8)
    emu:setBreakpoint(function() trace_scanner("writer", nil) end, 0x6C8F)
    emu:setBreakpoint(function() trace_scanner("tail", nil) end, 0x61F6)
  end)
end

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
    if tooth(0, row) or tooth(1, row) then
      start, width = 0, tooth(10, row) and 11 or
        (tooth(9, row) and 10 or 9)
    elseif read_tile(4, row) == 0x6A then
      start, width = 5, 10
    elseif tooth(4, row) or tooth(5, row) then
      start, width = 4, 9
    end
    if start then
      for column = start, start + width - 1 do
        positions[row * 32 + column] = true
      end
    elseif tooth(6, row) then
      -- The translated alternating phase has no tooth at the normal 4/5
      -- discriminator. Only its actual 6/8/10/12 tooth cells use immutable
      -- bank-1 art; the intervening neutral cells must remain ordinary BG0.
      for column = 4, 13 do
        if tooth(column, row) then
          positions[row * 32 + column] = true
        end
      end
    end
  end
  return positions
end

local function visible_bg_receipt()
  local lcdc = emu:read8(0xFF40)
  local scy, scx = emu:read8(0xFF42), emu:read8(0xFF43)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local room = emu:read8(0xFFBD)
  local old_vbk = emu:read8(0xFF4F)
  local tiles, all_tiles, attr_bytes, mismatches, unexpected_mismatches, unsafe,
    approved_bank1 = {}, {}, {}, 0, 0, 0, 0
  local mismatch_details = {}
  local histogram = {0, 0, 0, 0, 0, 0, 0, 0}
  emu:write8(0xFF4F, 0)
  all_tiles = {}
  for offset = 0, 0x3FF do all_tiles[offset] = emu:read8(base + offset) end
  local dynamic_tooth_positions = hazard_positions(function(column, row)
    return all_tiles[row * 32 + column]
  end)
  for row = 0, 17 do
    for column = 0, 19 do
      local map_y = ((scy >> 3) + row) & 0x1F
      local map_x = ((scx >> 3) + column) & 0x1F
      local offset = map_y * 32 + map_x
      tiles[offset] = all_tiles[offset]
    end
  end
  emu:write8(0xFF4F, 1)
  for row = 0, 17 do
    for column = 0, 19 do
      local map_y = ((scy >> 3) + row) & 0x1F
      local map_x = ((scx >> 3) + column) & 0x1F
      local offset = map_y * 32 + map_x
      local attr = emu:read8(base + offset)
      attr_bytes[#attr_bytes + 1] = string.char(attr)
      local palette = attr & 0x07
      histogram[palette + 1] = histogram[palette + 1] + 1
      local static_tooth_position = dynamic_tooth_positions[offset] or false
      -- These 18 cells per physical map deliberately use BG palette 7 and
      -- VRAM pattern bank 1. Attribute $0F is safe only at these exact,
      -- reviewed room-$02/$12 coordinates; every other high bit remains a
      -- failure so this receipt cannot hide unrelated bank/flip corruption.
      if static_tooth_position and attr == 0x0F then
        approved_bank1 = approved_bank1 + 1
      elseif static_tooth_position then
        mismatches = mismatches + 1
        unexpected_mismatches = unexpected_mismatches + 1
        if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
        if #mismatch_details < 16 then
          mismatch_details[#mismatch_details + 1] = string.format(
            "%03X:%02X/%02X/0F", offset, tiles[offset], attr)
        end
      else
        if (attr & 0xF8) ~= 0 then
          unsafe = unsafe + 1
          if #mismatch_details < 16 then
            mismatch_details[#mismatch_details + 1] = string.format(
              "%03X:%02X/%02X/unsafe", offset, tiles[offset], attr)
          end
        end
        local expected = emu:read8(0xC600 + tiles[offset]) & 0x07
        if palette ~= expected then
          mismatches = mismatches + 1
          local semantic_hazard =
            ((tiles[offset] >= 0x4C and tiles[offset] <= 0x4F) or
             (tiles[offset] >= 0x5C and tiles[offset] <= 0x5F)) and
            palette == 5 and expected == 0
          local legacy =
            ((tiles[offset] >= 0x2A and tiles[offset] <= 0x2E) or
             (tiles[offset] >= 0x3A and tiles[offset] <= 0x3D)) and
            palette == 0 and expected == 5
          if not semantic_hazard and not legacy then
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
  return base, mismatches, unexpected_mismatches,
    table.concat(mismatch_details, ","), unsafe,
    approved_bank1, table.concat(histogram, ","),
    hex_bytes(table.concat(attr_bytes))
end

local trace = assert(io.open(OUT .. ".frames.tsv", "w"))
trace:write(
  "sample\tframe\thealth_phase\tpc\tdma_source\tdma_unreadable\td880\tffc1\troom\tscy\tdc0b\tdc0e\thazard_rows\tdestination_hazard_rows\thp_sub\thp_main\td887\td885\td888\tbggate\tbgp\tfff7\tffe2\tffe3" ..
  "\tmap\tmismatches\tunexpected_mismatches\tmismatch_details" ..
  "\tunsafe\tapproved_bank1\tattrs\tattr_bytes\tbg_cram\n")
trace:close()

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  local post_trigger_frame = frame - SETTLE - PRE_TRIGGER
  if emu:read8(0xD880) == 0x0A then music_transition_seen = true end
  -- The movement input exists only to reach the real Stage-1 miniboss/music
  -- boundary. Release it on the first $0A frame so the long soak measures the
  -- reported transition instead of walking the fragile fixture into death.
  emu:setKeys(
    post_trigger_frame > 0 and not music_transition_seen
      and POST_TRIGGER_KEYS or 0)
  -- The historical receipt began inside the warning band, so it could never
  -- exercise the exact health/music transition reported by the player. Hold
  -- the checked-in fixture one unit above the threshold through settling and
  -- the requested pre-trigger sample window, then cross to its original
  -- survivable low-health value exactly once.
  if frame <= SETTLE + PRE_TRIGGER then
    emu:write8(0xDCDD, HEALTHY_MAIN)
  elseif frame >= SETTLE + PRE_TRIGGER + 1 then
    -- Keep the captured route inside the warning band. Without this refresh,
    -- incidental contact eventually consumes the fixture and turns the latter
    -- half of a 1,600-frame flicker soak into unrelated scene $0B.
    emu:write8(0xDCDC, LOW_SUB)
    emu:write8(0xDCDD, 0)
  end
  if frame <= SETTLE then return end

  sample = sample + 1
  local base, mismatches, unexpected_mismatches, mismatch_details, unsafe,
    approved_bank1, attrs, attr_bytes = visible_bg_receipt()
  local pc = register("PC") & 0xFFFF
  local dma_source = emu:read8(0xFF46)
  local scene = emu:read8(0xD880)
  local hp_sub, hp_main = emu:read8(0xDCDC), emu:read8(0xDCDD)
  local dma_unreadable = scene == 0xFF
    and pc >= 0xFF80 and pc <= 0xFF9F
    and (dma_source == 0xC0 or dma_source == 0xC1)
  local handle = assert(io.open(OUT .. ".frames.tsv", "a"))
  handle:write(string.format(
    "%d\t%d\t%s\t%04X\t%02X\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%s\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%04X\t%d\t%d\t%s\t%d\t%d\t%s\t%s\t%s\n",
    sample, frame, hp_main == 0 and "low" or "pre",
    pc, dma_source, dma_unreadable and 1 or 0,
    scene, emu:read8(0xFFC1),
    emu:read8(0xFFBD), emu:read8(0xFF42), emu:read8(0xDC0B),
    emu:read8(0xDC0E), source_hazard_rows(), destination_hazard_rows(),
    hp_sub, hp_main, emu:read8(0xD887), emu:read8(0xD885),
    emu:read8(0xD888), emu:read8(0xDF0D), emu:read8(0xFF47),
    emu:read8(0xFFF7), emu:read8(0xFFE2), emu:read8(0xFFE3),
    base, mismatches, unexpected_mismatches,
    mismatch_details, unsafe, approved_bank1, attrs, attr_bytes,
    hex_bytes(palette_bytes("cgbBgPalette", 0xFF68, 0xFF69))))
  handle:close()
  emu:screenshot(string.format("%s.frame%04d.png", OUT, sample))

  if sample >= SAMPLES then
    done = true
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write("ok\n")
    marker:close()
    os.exit(0)
  end
end)
