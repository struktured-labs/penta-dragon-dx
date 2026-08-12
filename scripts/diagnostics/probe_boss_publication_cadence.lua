-- Record native 24x24 map publications without changing boss animation.
-- The Python owner launches this only through mgba-qt-singleflight.

local OUT = assert(os.getenv("BOSS_CADENCE_OUT"), "BOSS_CADENCE_OUT required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_CADENCE_SCENE") or "15")
local WARMUP = tonumber(os.getenv("BOSS_CADENCE_WARMUP") or "60")
local FRAMES = tonumber(os.getenv("BOSS_CADENCE_FRAMES") or "600")

local trace = assert(io.open(OUT .. ".trace", "w"))
local frame, copies, scene_frames, finished = 0, 0, 0, false
local scene_drift_frames = 0

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

local function finish(status)
  if finished then return end
  finished = true
  trace:write(string.format(
    "complete status=%s frames=%d scene_frames=%d copies=%d scene=%02X\n",
    status, frame, scene_frames, copies, emu:read8(0xD880)))
  trace:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(string.format("%s copies=%d scene_frames=%d\n",
    status, copies, scene_frames))
  marker:close()
  emu:stop()
end

pcall(function()
  emu:setBreakpoint(function()
    if frame <= WARMUP or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    local destination = register("HL") & 0xFC00
    if destination ~= 0x9800 and destination ~= 0x9C00 then return end
    copies = copies + 1
    trace:write(string.format("copy=%d frame=%d destination=%04X\n",
      copies, frame - WARMUP, destination))
    trace:flush()
  end, 0x42A7)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  if emu:read8(0xD880) == EXPECTED_SCENE then
    scene_drift_frames = 0
    -- Keep the contestants alive without writing pose, animation, or timing.
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    if frame > WARMUP then scene_frames = scene_frames + 1 end
  elseif frame > WARMUP then
    scene_drift_frames = scene_drift_frames + 1
    if scene_drift_frames > 1 then
      finish(scene_frames > 0 and "scene-exit" or "wrong-scene")
      return
    end
  end
  if frame >= WARMUP + FRAMES then
    finish(scene_frames > 0 and "ok" or "wrong-scene")
  end
end)
