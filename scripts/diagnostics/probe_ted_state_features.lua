-- Capture bank-1 WRAM state at each native Ted publication for key discovery.
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
local OUT = assert(os.getenv("TED_FEATURE_OUT"))
local FRAMES = tonumber(os.getenv("TED_FEATURE_FRAMES") or "2800")
local frame, copies, done = 0, 0, false
local state = assert(io.open(OUT .. ".bin", "wb"))

local function reg(name)
  for _, reader in ipairs({
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
  }) do
    local ok, value = pcall(reader)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

assert(emu:setBreakpoint(function()
  if emu:read8(0xD880) ~= 0x10 then return end
  local destination = reg("HL") & 0xFC00
  if destination ~= 0x9800 and destination ~= 0x9C00 then return end
  local record = {frame & 0xFF, (frame >> 8) & 0xFF}
  for address = 0xDC00, 0xDDFF do
    record[#record + 1] = emu:read8(address)
  end
  state:write(string.char(table.unpack(record)))
  state:flush(); copies = copies + 1
end, 0x42A7) > 0)

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  emu:setKeys(0)
  native_assistance.write(0xDCBB, 0xF0)
  if emu:read8(0xD880) ~= 0x10 or frame >= FRAMES then
    done = true; state:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(string.format("frames=%d copies=%d scene=%02X\n",
      frame, copies, emu:read8(0xD880)))
    marker:close(); emu:stop()
  end
end)
