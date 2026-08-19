-- Attribute every runtime write to the relocated arena $9C00 cache record.
-- The Python owner launches this only through the project single-flight gate.

local OUT = assert(os.getenv("ARENA_CACHE_OWNERSHIP_OUT"))
local FRAMES = tonumber(os.getenv("ARENA_CACHE_OWNERSHIP_FRAMES") or "650")
local EXPECTED_SCENE = tonumber(os.getenv("ARENA_CACHE_OWNERSHIP_SCENE") or "12")
local BASE = tonumber(os.getenv("ARENA_CACHE_OWNERSHIP_BASE") or "57180")
local SIZE = tonumber(os.getenv("ARENA_CACHE_OWNERSHIP_SIZE") or "4")
local trace = assert(io.open(OUT .. ".trace", "w"))
local frame, writes, scene_frames, finished = 0, 0, 0, false
local counts = {}
for address = BASE, BASE + SIZE - 1 do counts[address] = 0 end

local function register(name)
  local readers = {
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

assert(emu:setRangeWatchpoint(function(info)
  local address = info.address & 0xFFFF
  writes = writes + 1
  counts[address] = (counts[address] or 0) + 1
  trace:write(string.format(
    "writer index=%d frame=%d scene=%02X address=%04X bank=%02X " ..
    "pc=%04X old=%02X new=%02X\n",
    writes, frame, emu:read8(0xD880), address, emu:read8(0xFF99),
    register("PC") & 0xFFFF, info.oldValue & 0xFF, info.newValue & 0xFF))
  trace:flush()
end, BASE, BASE + SIZE, C.WATCHPOINT_TYPE.WRITE) > 0)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  -- Preserve the same non-interactive survival policy as the boss receipts.
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCDD, 0xFF)
  if emu:read8(0xD880) == EXPECTED_SCENE then
    scene_frames = scene_frames + 1
  end
  if frame < FRAMES then return end
  trace:write(string.format(
    "complete frames=%d scene_frames=%d final_scene=%02X writes=%d\n",
    frame, scene_frames, emu:read8(0xD880), writes))
  trace:close()
  local done = assert(io.open(OUT .. ".done", "w"))
  done:write("ok\n")
  done:close()
  finished = true
  emu:stop()
end)
