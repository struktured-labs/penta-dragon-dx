-- One-frame scene/state inventory for an mGBA savestate.

local OUT = assert(os.getenv("STATE_SCENE_OUT"), "STATE_SCENE_OUT is required")
local WAIT = tonumber(os.getenv("STATE_SCENE_WAIT")) or 1
local frame = 0

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  if frame == WAIT then
    local report = assert(io.open(OUT, "w"))
    report:write(string.format(
      "D880=%02X FFC1=%02X FFBA=%02X FFBE=%02X FFBF=%02X "
      .. "FFC0=%02X FFD0=%02X FFE4=%02X DD09=%02X "
      .. "FF40=%02X FF42=%02X FF43=%02X FF4F=%02X\n",
      emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBA),
      emu:read8(0xFFBE), emu:read8(0xFFBF), emu:read8(0xFFC0),
      emu:read8(0xFFD0), emu:read8(0xFFE4), emu:read8(0xDD09),
      emu:read8(0xFF40), emu:read8(0xFF42), emu:read8(0xFF43),
      emu:read8(0xFF4F)))
    report:close()
  end
end)
