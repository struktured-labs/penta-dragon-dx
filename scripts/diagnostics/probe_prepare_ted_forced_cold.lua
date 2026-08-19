-- Create a ROM-bound Ted fixture with every lazy-install destination clear.
-- Diagnostic only; invoke through the project single-flight wrapper.

local STATE_OUT = assert(os.getenv("TED_FORCED_COLD_STATE_OUT"))
local DONE = assert(os.getenv("TED_FORCED_COLD_DONE"))
local frame = 0
local saved = false

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  if saved then
    if frame < 4 then return end
    local marker = assert(io.open(DONE, "w"))
    marker:write(string.format(
      "status=ok frame=%d scene=%02X sentinel=%02X\n",
      frame, emu:read8(0xD880), emu:read8(0xC5FF)))
    marker:close()
    os.exit(0)
  end
  if frame ~= 1 then return end
  local saved_bank = emu:read8(0xFF70)
  for _, bank in ipairs({4, 5}) do
    emu:write8(0xFF70, bank)
    for address = 0xD300, 0xD39A do emu:write8(address, 0) end
    for address = 0xD500, 0xD8FF do emu:write8(address, 0) end
  end
  emu:write8(0xFF70, saved_bank)
  for address = 0xC4FA, 0xC4FC do emu:write8(address, 0) end
  emu:write8(0xC5FE, 0)
  emu:write8(0xC5FF, 0)
  emu:saveStateFile(STATE_OUT)
  saved = true
end)
