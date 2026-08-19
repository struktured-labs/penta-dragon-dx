-- Dump both private Ted runtime payloads at the cold install-final boundary.
local OUT = assert(os.getenv("TED_INSTALL_OUT"), "TED_INSTALL_OUT required")
local report = assert(io.open(OUT, "w"))
local entries, tails, done, frame = 0, 0, false, 0

local function bp(address, callback)
  assert(pcall(function() emu:setBreakpoint(callback, address) end))
end

bp(0x5340, function() entries = entries + 1 end)
bp(0x5CDA, function() tails = tails + 1 end)
bp(0x6FFF, function()
  if done then return end
  done = true
  local sentinel = emu:read8(0xC5FF)
  local old = emu:read8(0xFF70) & 7
  local file = assert(io.open(OUT .. ".installed.bin", "wb"))
  for _, bank in ipairs({4, 5}) do
    emu:write8(0xFF70, bank)
    for address = 0xD300, 0xD39A do
      file:write(string.char(emu:read8(address)))
    end
    for address = 0xD500, 0xD578 do
      file:write(string.char(emu:read8(address)))
    end
  end
  emu:write8(0xFF70, old)
  file:close()
  local status = entries == 1 and tails == 2 and sentinel == 0
      and emu:read8(0xD880) == 0x10 and "pass" or "fail"
  report:write(string.format(
    "status=%s frame=%d entries=%d bank_passes=%d sentinel=%02X scene=%02X de=%04X\n",
    status, frame, entries, tails, sentinel, emu:read8(0xD880),
    (emu:getRegister("DE") or 0) & 0xFFFF))
  report:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n"); marker:close()
end)

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
end)
