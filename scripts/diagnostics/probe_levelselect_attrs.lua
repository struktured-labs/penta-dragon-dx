-- Verify the save-present GAME START level-select/high-score screen.
--
-- The title defaults to OPENING START, so this deliberately presses DOWN
-- before A. DCFD=1 forces the continue path through the WRAM attr-clear stub.
local OUT = os.getenv("OUT") or "/tmp/penta-levelselect-attrs"
local f = 0
local done = false

local function press(lo, hi, mask)
  return (f >= lo and f < hi) and mask or 0
end

local function populated_rows()
  local base = ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F, 0)
  local count = 0
  for row = 7, 15 do
    for col = 0, 19 do
      if emu:read8(base + row * 32 + col) ~= 0 then count = count + 1 end
    end
  end
  return count, base
end

local function finish(base, populated)
  emu:write8(0xFF4F, 1)
  local nonzero = 0
  for row = 0, 17 do
    for col = 0, 19 do
      if (emu:read8(base + row * 32 + col) & 0x07) ~= 0 then
        nonzero = nonzero + 1
      end
    end
  end
  emu:write8(0xFF4F, 0)

  emu:screenshot(OUT .. ".png")
  local handle = assert(io.open(OUT .. ".txt", "w"))
  handle:write(string.format(
    "frame=%d d880=%02X ffc1=%d dcfd=%02X df0e=%02X base=%04X " ..
    "populated=%d checked=360 nonzero=%d lcdc=%02X\n",
    f, emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xDCFD),
    emu:read8(0xDF0E), base, populated, nonzero, emu:read8(0xFF40)
  ))
  handle:close()
  done = true
  os.exit(0)
end

callbacks:add("frame", function()
  if done then return end
  f = f + 1

  -- A save makes GAME START branch to bank1:7393.
  emu:write8(0xDCFD, 0x01)
  emu:setKeys(
    press(180, 186, 0x80) | -- DOWN: OPENING START -> GAME START
    press(210, 216, 0x01)   -- A
  )

  if f > 230 then
    local populated, base = populated_rows()
    if populated >= 10 then finish(base, populated) end
  end

  if f >= 760 then
    local handle = assert(io.open(OUT .. ".txt", "w"))
    handle:write(string.format(
      "frame=%d status=timeout d880=%02X ffc1=%d dcfd=%02X\n",
      f, emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xDCFD)
    ))
    handle:close()
    done = true
    os.exit(2)
  end
end)
