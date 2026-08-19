-- Attribute every Ted tilemap mutation to its exact ROM bank/PC. This probe
-- is read-only and intentionally separate from the release gate.

local OUT = assert(os.getenv("TED_VRAM_WRITERS_OUT"))
local FRAMES = tonumber(os.getenv("TED_VRAM_WRITERS_FRAMES") or "180")
local LIMIT = tonumber(os.getenv("TED_VRAM_WRITERS_LIMIT") or "4000")
local out = assert(io.open(OUT, "w"))
local frame, writes, finished, installed = 0, 0, false, false

local function reg(name)
  for _, accessor in ipairs({
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }) do
    local ok, value = pcall(accessor)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function watch(info)
  if finished or emu:read8(0xD880) ~= 0x10 or writes >= LIMIT then return end
  writes = writes + 1
  out:write(string.format(
    "frame=%d address=%04X value=%02X vbk=%02X rom=%02X pc=%04X " ..
    "sp=%04X hl=%04X de=%04X bc=%04X\n",
    frame, info.address & 0xFFFF, info.value & 0xFF,
    emu:read8(0xFF4F), emu:read8(0xFF99), reg("PC"), reg("SP"),
    reg("HL"), reg("DE"), reg("BC")))
end
local function install_watches()
  -- mGBA rejects a single watch spanning the whole VRAM tilemap. Individual
  -- cells are supported, so watch every cell occupied by Ted in either
  -- physical map at fixture entry. Native animation must clear or overwrite
  -- those cells when it moves a row/body segment, which attributes the writer
  -- without perturbing VRAM or guessing a ROM callsite.
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  local count = 0
  for _, base in ipairs({0x9800, 0x9C00}) do
    for offset = 0, 0x3FF do
      local tile = emu:read8(base + offset)
      if (tile >= 0x02 and tile <= 0x76) or
         tile == 0x7B or tile == 0x7D or
         (tile >= 0x80 and tile <= 0x86) then
        local id = emu:setRangeWatchpoint(
          watch, base + offset, base + offset, C.WATCHPOINT_TYPE.WRITE)
        if id and id > 0 then count = count + 1 end
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  if count > 0 then
    out:write(string.format("watchpoints=%d frame=%d\n", count, frame)); out:flush()
    installed = true
  end
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if frame == 1 then emu:write8(0xC5FF, 0) end
  emu:setKeys(0)
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xDCDC, 0xFF); emu:write8(0xDCDD, 0xFF)
  emu:write8(0xD888, 0); emu:write8(0xDD06, 0)
  if not installed and emu:read8(0xD880) == 0x10 then install_watches() end
  if frame >= FRAMES then
    finished = true
    out:write(string.format("status=ok frames=%d writes=%d\n", frame, writes))
    out:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write("status=ok\n"); done:close()
    if emu.stop then emu:stop() end
  end
end)
