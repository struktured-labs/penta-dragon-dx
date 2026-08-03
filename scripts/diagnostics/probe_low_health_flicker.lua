-- Consecutive-frame receipt for the Stage 1 low-health warning state.

local OUT = assert(os.getenv("LOW_HEALTH_OUT"), "LOW_HEALTH_OUT is required")
local SETTLE = tonumber(os.getenv("LOW_HEALTH_SETTLE") or "120")
local SAMPLES = tonumber(os.getenv("LOW_HEALTH_SAMPLES") or "240")
local frame, sample, done = 0, 0, false

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

local function visible_bg_receipt()
  local lcdc = emu:read8(0xFF40)
  local scy, scx = emu:read8(0xFF42), emu:read8(0xFF43)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local old_vbk = emu:read8(0xFF4F)
  local tiles, attr_bytes, mismatches, unexpected_mismatches, unsafe =
    {}, {}, 0, 0, 0
  local mismatch_details = {}
  local histogram = {0, 0, 0, 0, 0, 0, 0, 0}
  emu:write8(0xFF4F, 0)
  for row = 0, 17 do
    for column = 0, 19 do
      local map_y = ((scy >> 3) + row) & 0x1F
      local map_x = ((scx >> 3) + column) & 0x1F
      local offset = map_y * 32 + map_x
      tiles[offset] = emu:read8(base + offset)
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
      if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
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
  emu:write8(0xFF4F, old_vbk)
  return base, mismatches, unexpected_mismatches,
    table.concat(mismatch_details, ","), unsafe,
    table.concat(histogram, ","), hex_bytes(table.concat(attr_bytes))
end

local trace = assert(io.open(OUT .. ".frames.tsv", "w"))
trace:write(
  "sample\tframe\tpc\tdma_source\tdma_unreadable\td880\tffc1\thp_sub\thp_main\td887\tbggate\tbgp\tffe2\tffe3" ..
  "\tmap\tmismatches\tunexpected_mismatches\tmismatch_details" ..
  "\tunsafe\tattrs\tattr_bytes\tbg_cram\n")
trace:close()

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  emu:setKeys(0)
  if frame <= SETTLE then return end

  sample = sample + 1
  local base, mismatches, unexpected_mismatches, mismatch_details, unsafe,
    attrs, attr_bytes = visible_bg_receipt()
  local pc = register("PC") & 0xFFFF
  local dma_source = emu:read8(0xFF46)
  local scene = emu:read8(0xD880)
  local dma_unreadable = scene == 0xFF
    and pc >= 0xFF80 and pc <= 0xFF9F
    and (dma_source == 0xC0 or dma_source == 0xC1)
  local handle = assert(io.open(OUT .. ".frames.tsv", "a"))
  handle:write(string.format(
    "%d\t%d\t%04X\t%02X\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%04X\t%d\t%d\t%s\t%d\t%s\t%s\t%s\n",
    sample, frame, pc, dma_source, dma_unreadable and 1 or 0,
    scene, emu:read8(0xFFC1),
    emu:read8(0xDCDC), emu:read8(0xDCDD), emu:read8(0xD887),
    emu:read8(0xDF0D), emu:read8(0xFF47), emu:read8(0xFFE2),
    emu:read8(0xFFE3), base, mismatches, unexpected_mismatches,
    mismatch_details, unsafe, attrs, attr_bytes,
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
