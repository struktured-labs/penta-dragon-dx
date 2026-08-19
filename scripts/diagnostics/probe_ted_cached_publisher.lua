-- Trace the experimental full-plane Ted publisher at its real boundaries.
local OUT = assert(os.getenv("TED_CACHED_TRACE_OUT"))
local out = assert(io.open(OUT, "w"))
local frames = tonumber(os.getenv("TED_CACHED_TRACE_FRAMES") or "120")
local breakpoints = os.getenv("TED_CACHED_TRACE_BREAKPOINTS") ~= "0"
local frame, entries, publishes, done = 0, 0, 0, false

local function cache_receipt()
  local old_svbk = emu:read8(0xFF70)
  emu:write8(0xFF70, 2)
  local tile_nonzero, attr_nonzero = 0, 0
  local floor_attr = {[0x77] = 6, [0x78] = 7, [0x79] = 7, [0x7A] = 6}
  local floor_total, floor_correct = 0, 0
  local lut_mismatches, mismatch_examples = 0, {}
  for offset = 0, 0x3FF do
    local tile = emu:read8(0xD000 + offset)
    local attr = emu:read8(0xD400 + offset)
    if tile ~= 0 then tile_nonzero = tile_nonzero + 1 end
    if attr ~= 0 then attr_nonzero = attr_nonzero + 1 end
    local expected = emu:read8(0xC600 + tile)
    if attr ~= expected then
      lut_mismatches = lut_mismatches + 1
      if #mismatch_examples < 8 then
        mismatch_examples[#mismatch_examples + 1] = string.format(
          "%03X:%02X:%X>%X", offset, tile, expected, attr)
      end
    end
    if floor_attr[tile] ~= nil then
      floor_total = floor_total + 1
      if attr == floor_attr[tile] then floor_correct = floor_correct + 1 end
    end
  end
  emu:write8(0xFF70, old_svbk)
  out:write(string.format(
    "cache-receipt frame=%d tile_nonzero=%d attr_nonzero=%d " ..
    "floor_total=%d floor_correct=%d lut_mismatches=%d examples=%s " ..
    "key=%02X sentinel=%02X d888=%02X dc0b=%02X bank=%02X pc=%04X\n",
    frame, tile_nonzero, attr_nonzero, floor_total, floor_correct,
    lut_mismatches, table.concat(mismatch_examples, ","), emu:read8(0xFFA9),
    emu:read8(0xC5FF), emu:read8(0xD888), emu:read8(0xDC0B),
    emu:read8(0xFF99), emu:readRegister("pc")))
  out:flush()
end

local function line(kind)
  -- Breakpoint callbacks run inside timing-sensitive fixed-bank code.  The
  -- old diagnostic changed SVBK/VBK here to inspect the experimental cache;
  -- that made the probe itself capable of corrupting the interrupted copy.
  -- Record only side-effect-free caller/source state at this boundary.
  local source = {}
  for address = 0xC1A0, 0xC1BF do
    source[#source + 1] = emu:read8(address)
  end
  out:write(string.format(
    "%s frame=%d scene=%02X dc0b=%02X svbk=%02X vbk=%02X " ..
    "pc=%04X sp=%04X af=%04X bc=%04X de=%04X hl=%04X " ..
    "hdma=%02X,%02X,%02X,%02X,%02X source=%s\n",
    kind, frame, emu:read8(0xD880), emu:read8(0xDC0B),
    emu:read8(0xFF70), emu:read8(0xFF4F), emu:readRegister("pc"),
    emu:readRegister("sp"), emu:readRegister("af"),
    emu:readRegister("bc"), emu:readRegister("de"),
    emu:readRegister("hl"), emu:read8(0xFF51), emu:read8(0xFF52),
    emu:read8(0xFF53), emu:read8(0xFF54), emu:read8(0xFF55),
    table.concat(source, ",")))
  out:flush()
end

local function publication_receipt()
  local base = emu:read8(0xFFA7) * 0x100
  local old_vbk = emu:read8(0xFF4F)
  local tile_mismatches, attr_mismatches = 0, 0
  emu:write8(0xFF4F, 0)
  for offset = 0, 0x3FF do
    if emu:read8(base + offset) ~= emu:read8(0xD000 + offset) then
      tile_mismatches = tile_mismatches + 1
    end
  end
  emu:write8(0xFF4F, 1)
  for offset = 0, 0x3FF do
    if emu:read8(base + offset) ~= emu:read8(0xD400 + offset) then
      attr_mismatches = attr_mismatches + 1
    end
  end
  emu:write8(0xFF4F, old_vbk)
  out:write(string.format(
    "publication frame=%d base=%04X tile_mismatches=%d attr_mismatches=%d\n",
    frame, base, tile_mismatches, attr_mismatches))
  out:flush()
end

if breakpoints then pcall(function() emu:setBreakpoint(function()
  entries = entries + 1; line("entry")
end, 0xC4FC) end)

pcall(function() emu:setBreakpoint(function()
  line("wrapper")
end, 0xDB87) end)

pcall(function() emu:setBreakpoint(function()
  line("call-site")
end, 0x028A) end)

pcall(function() emu:setBreakpoint(function()
  line("private-entry")
end, 0x6FE4) end)

pcall(function() emu:setBreakpoint(function()
  line("private-tail")
end, 0x7C91) end)

pcall(function() emu:setBreakpoint(function()
  line("private-map")
end, 0x7CAE) end)

pcall(function() emu:setBreakpoint(function()
  line("cache-entry")
end, 0x5CDA) end)

pcall(function() emu:setBreakpoint(function()
  line("installer")
end, 0x5940) end)

pcall(function() emu:setBreakpoint(function()
  publication_receipt()
end, 0xC5E1) end)

pcall(function() emu:setBreakpoint(function()
  line("gdma-commit")
end, 0x700B) end)

pcall(function() emu:setBreakpoint(function()
  line("bg-sweep")
end, 0x6CD0) end)

pcall(function() emu:setBreakpoint(function()
  publishes = publishes + 1; line("publish-tail")
end, 0x55D8) end) end

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  emu:setKeys(0)
  if emu:read8(0xD880) == 0x10 then
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
  end
  if not breakpoints then cache_receipt() end
  if frame >= frames then
    cache_receipt()
    done = true; out:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(string.format("status=ok entries=%d publishes=%d\n", entries, publishes))
    marker:close(); emu:stop()
  end
end)
