-- Capture the title screen's rendered pixels, BG CRAM and BG attributes.
--
-- Deliberately named outside the probe_*.lua family so it cannot collide with
-- the release probe roster. Used by verify_title_color_mgba.py.
local OUT = assert(os.getenv("OUT"), "OUT is required")
local AT = tonumber(os.getenv("AT_FRAME") or "400")
-- WAIT_RETURN=1 captures the *returned* title instead: wait until the scene
-- has left $01 and come back, then settle before sampling.
local WAIT_RETURN = os.getenv("WAIT_RETURN") == "1"
local LIMIT = tonumber(os.getenv("FRAME_LIMIT") or "200000")
local f = 0
-- TITLE_WRITER_TRACE=1: optional, read-only.  Log every CPU write into the
-- title attribute rows ($9820..$9A5F on the CPU bus; VBK is logged so bank-0
-- tile writes can be told from bank-1 attribute writes) while scene $01 is
-- live.  Capped so a runaway writer cannot fill the disk.  Default capture
-- output is unchanged when the variable is unset.
local TRACE = os.getenv("TITLE_WRITER_TRACE") == "1"
local TRACE_CAP = tonumber(os.getenv("TITLE_WRITER_TRACE_CAP") or "600")
local TRACE_MIN_FRAME = tonumber(os.getenv("TITLE_WRITER_TRACE_MIN_FRAME") or "0")
local TRACE_ATTRS_ONLY = os.getenv("TITLE_WRITER_TRACE_ATTRS_ONLY") == "1"
local TRACE_ADDRESS = tonumber(os.getenv("TITLE_WRITER_TRACE_ADDRESS") or "")
local writers = nil
local writer_count = 0
local function physical_scene()
  return assert(emu.memory.wram):read8(0x1880)
end
if TRACE then
  writers = assert(io.open(OUT .. "-writers.tsv", "w"))
  writers:write("frame\taddress\tvbk\told\tnew\tpc\tbank\tly\tstat\td880\tdf08\tsvbk\tie\n")
  if os.getenv("TITLE_WRITER_TRACE_DMA") == "1" then
    local dma_count = 0
    assert(emu:setWatchpoint(function(info)
      if f < TRACE_MIN_FRAME or dma_count >= TRACE_CAP then return end
      if physical_scene() ~= 0x01 then return end
      dma_count = dma_count + 1
      writers:write(string.format(
        "#DMA\t%d\t%02X\t%04X\t%02X\t%d\t%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
        f, info.newValue & 255, emu:readRegister("PC") & 65535,
        emu:read8(0xFF99), emu:read8(0xFF44), emu:read8(0xFF4F) & 1,
        emu:read8(0xFF70) & 7, emu:read8(0xFF51), emu:read8(0xFF52),
        emu:read8(0xFF53), emu:read8(0xFF54), emu:read8(0xDF08), emu:read8(0xFFC4)))
      writers:flush()
    end, 0xFF55, C.WATCHPOINT_TYPE.WRITE) > 0)
  end
  local first_address = TRACE_ADDRESS or 0x9820
  local last_address = TRACE_ADDRESS or 0x9A5F
  assert(first_address >= 0x8000 and last_address <= 0x9FFF,
    "TITLE_WRITER_TRACE_ADDRESS must be a VRAM CPU address")
  for address = first_address, last_address do
    local watched = address
    assert(emu:setWatchpoint(function(info)
      if f < TRACE_MIN_FRAME then return end
      if TRACE_ATTRS_ONLY and (emu:read8(0xFF4F) & 1) ~= 1 then return end
      if writer_count >= TRACE_CAP then return end
      if physical_scene() ~= 0x01 then return end
      writer_count = writer_count + 1
      writers:write(string.format(
        "%d\t%04X\t%d\t%02X\t%02X\t%04X\t%02X\t%d\t%d\t%02X\t%02X\t%d\t%02X\n",
        f, watched, emu:read8(0xFF4F) & 1, info.oldValue & 255, info.newValue & 255,
        emu:readRegister("PC") & 65535, emu:read8(0xFF99), emu:read8(0xFF44),
        emu:read8(0xFF41) & 3, emu:read8(0xD880), emu:read8(0xDF08),
        emu:read8(0xFF70) & 7, emu:read8(0xFFFF)))
      writers:flush()
    end, watched, C.WATCHPOINT_TYPE.WRITE) > 0)
  end
end
local left_title = false
local returned_at = nil
local done = false

local function bg_cram()
  local out = {}
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    out[#out + 1] = string.format("%02X", emu:read8(0xFF69))
  end
  return table.concat(out, "")
end

local function attributes(base)
  emu:write8(0xFF4F, 1)
  local rows = {}
  for row = 1, 18 do
    local cells = {}
    for col = 0, 20 do
      cells[#cells + 1] = string.format("%02X", emu:read8(base + row * 32 + col))
    end
    rows[#rows + 1] = string.format("r%02d %s", row, table.concat(cells, " "))
  end
  emu:write8(0xFF4F, 0)
  return table.concat(rows, "\n")
end

-- Full 32x18 attribute rows 1..18 of ONE physical map (both maps are dumped so
-- the 576-cell both-map role image is measured, not assumed).
local function full_attributes(base)
  emu:write8(0xFF4F, 1)
  local cells = {}
  for row = 1, 18 do
    for col = 0, 31 do
      cells[#cells + 1] = string.format("%02X", emu:read8(base + row * 32 + col))
    end
  end
  emu:write8(0xFF4F, 0)
  return table.concat(cells, "")
end

local function tile_bytes(tile)
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  -- LCDC.4=0 on this title, so unsigned map ID $73 indexes $8730.
  local address = 0x8000 + ((tile + 0x80) & 0xFF) * 16
  local cells = {}
  for offset = 0, 15 do
    cells[#cells + 1] = string.format("%02X", emu:read8(address + offset))
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(cells, "")
end

callbacks:add("frame", function()
  if done then return end
  f = f + 1
  if WAIT_RETURN then
    local scene = emu:read8(0xD880)
    if not left_title then
      if f > 200 and scene ~= 0x01 then left_title = true end
      if f >= LIMIT then os.exit(3) end
      return
    end
    if returned_at == nil then
      if scene == 0x01 then returned_at = f end
      if f >= LIMIT then os.exit(3) end
      return
    end
    if f < returned_at + AT then return end
  elseif f < AT then
    return
  end

  local base = ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800
  emu:screenshot(OUT .. ".png")
  local handle = assert(io.open(OUT .. ".txt", "w"))
  handle:write(string.format(
    "returned_at=%s\n", tostring(returned_at)
  ))
  handle:write(string.format(
    "frame=%d d880=%02X ffc1=%d lcdc=%02X scx=%d scy=%d base=%04X\n",
    f, emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFF40),
    emu:read8(0xFF43), emu:read8(0xFF42), base
  ))
  handle:write("bgcram=" .. bg_cram() .. "\n")
  handle:write("cursor_tile73=" .. tile_bytes(0x73) .. "\n")
  handle:write(attributes(base) .. "\n")
  handle:write("attrs9800=" .. full_attributes(0x9800) .. "\n")
  handle:write("attrs9C00=" .. full_attributes(0x9C00) .. "\n")
  handle:close()
  if writers then
    writers:write(string.format("# writer_count=%d cap=%d\n", writer_count, TRACE_CAP))
    writers:close()
  end
  done = true
  os.exit(0)
end)
