-- Record every complete Ted crown in the packed source at hot publication.
local OUT = assert(os.getenv("TED_CROWN_OUT"))
local WANT = tonumber(os.getenv("TED_CROWN_PUBLICATIONS") or "48")
local report = assert(io.open(OUT, "w"))
local frame, publications, finished = 0, 0, false

local function visible(value, start, span)
  return ((value - start) & 0x1F) < span
end

local function finish()
  if finished then return end
  finished = true
  report:write(string.format("summary frames=%d publications=%d\n",
    frame, publications))
  report:close()
  local done = assert(io.open(OUT .. ".done", "w"))
  done:write("ok\n"); done:close()
end

assert(emu:setBreakpoint(function()
  if finished or emu:read8(0xD880) ~= 0x10
      or emu:read8(0xFF99) ~= 0x0D then return end
  publications = publications + 1
  local top = (emu:read8(0xFF42) >> 3) & 0x1F
  local left = (emu:read8(0xFF43) >> 3) & 0x1F
  local all, shown = {}, {}
  for row = 0, 23 do
    for col = 0, 19 do
      local base = 0xC1A0 + row * 24 + col
      local good = true
      for offset = 0, 4 do
        if emu:read8(base + offset) ~= 2 + offset then good = false end
      end
      if good then
        local text = string.format("%d,%d", row, col)
        all[#all + 1] = text
        if visible(row, top, 18) and visible(col, left, 20) then
          shown[#shown + 1] = text
        end
      end
    end
  end
  report:write(string.format(
    "publication=%d frame=%d scy=%02X scx=%02X top=%d left=%d all=%s visible=%s\n",
    publications, frame, emu:read8(0xFF42), emu:read8(0xFF43),
    top, left, table.concat(all, ";"), table.concat(shown, ";")))
  report:flush()
  if publications >= WANT then finish() end
end, 0x5830) > 0)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  if emu:read8(0xD880) == 0x10 then
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
  end
  if frame >= 500 then finish() end
end)
