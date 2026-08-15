-- Record native 24x24 map publications without changing boss animation.
-- The Python owner launches this only through mgba-qt-singleflight.

local OUT = assert(os.getenv("BOSS_CADENCE_OUT"), "BOSS_CADENCE_OUT required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_CADENCE_SCENE") or "15")
local WARMUP = tonumber(os.getenv("BOSS_CADENCE_WARMUP") or "60")
local FRAMES = tonumber(os.getenv("BOSS_CADENCE_FRAMES") or "600")

local trace = assert(io.open(OUT .. ".trace", "w"))
local sources = assert(io.open(OUT .. ".sources.bin", "wb"))
local state_features = assert(io.open(OUT .. ".state.bin", "wb"))
local frame, copies, scene_frames, finished = 0, 0, 0, false
local scene_drift_frames = 0
-- Native $3111 expands one logical metatile into a 2x2 tile block.  These
-- diagnostics let the cache contract evaluate cheap per-metatile signatures
-- without changing the ROM under test.
local meta_count, meta_sum, meta_xor, meta_roll, meta_weighted = 0, 0, 0, 0, 0

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
  sources:close()
  state_features:close()
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
    local sp = register("SP")
    local caller = emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8)
    copies = copies + 1
    local record = {
      (frame - WARMUP) & 0xFF, ((frame - WARMUP) >> 8) & 0xFF,
      destination & 0xFF, (destination >> 8) & 0xFF,
    }
    for offset = 0, 24 * 24 - 1 do
      record[#record + 1] = emu:read8(0xC1A0 + offset)
    end
    sources:write(string.char(table.unpack(record)))
    sources:flush()
    local state_record = {}
    for address = 0xDC00, 0xDDFF do
      state_record[#state_record + 1] = emu:read8(address)
    end
    state_features:write(string.char(table.unpack(state_record)))
    trace:write(string.format(
      "copy=%d frame=%d destination=%04X ly=%02X stat=%02X pc=%04X caller=%04X\n",
      copies, frame - WARMUP, destination, emu:read8(0xFF44),
      emu:read8(0xFF41), register("PC"), caller))
    trace:write(string.format(
      "key=%02X%02X%02X%02X\n", emu:read8(0xDD81),
      emu:read8(0xDDC0), emu:read8(0xDD87), emu:read8(0xDDDC)))
    trace:write(string.format(
      "meta=count:%d sum:%02X xor:%02X roll:%02X weighted:%02X\n",
      meta_count, meta_sum, meta_xor, meta_roll, meta_weighted))
    meta_count, meta_sum, meta_xor, meta_roll, meta_weighted = 0, 0, 0, 0, 0
    trace:flush()
  end, 0x42A7)
end)

pcall(function()
  emu:setBreakpoint(function()
    if frame <= WARMUP or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    local value = emu:read8(register("HL"))
    meta_count = meta_count + 1
    meta_sum = (meta_sum + value) & 0xFF
    meta_xor = meta_xor ~ value
    meta_roll = ((meta_roll * 33) + value) & 0xFF
    meta_weighted = (meta_weighted + meta_count * value) & 0xFF
  end, 0x3111)
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
