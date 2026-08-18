-- Record native 24x24 map publications without changing boss animation.
-- The Python owner launches this only through mgba-qt-singleflight.

local OUT = assert(os.getenv("BOSS_CADENCE_OUT"), "BOSS_CADENCE_OUT required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_CADENCE_SCENE") or "15")
local WARMUP = tonumber(os.getenv("BOSS_CADENCE_WARMUP") or "60")
local FRAMES = tonumber(os.getenv("BOSS_CADENCE_FRAMES") or "600")
local BANKED_WRITER = os.getenv("BOSS_CADENCE_BANKED_WRITER") == "1"
local CACHED_TED = os.getenv("BOSS_CADENCE_CACHED_TED") == "1"
local COMPACT_TED = os.getenv("BOSS_CADENCE_COMPACT_TED") == "1"
local INCREMENTAL_TED = os.getenv("BOSS_CADENCE_INCREMENTAL_TED") == "1"

local trace = assert(io.open(OUT .. ".trace", "w"))
local sources = assert(io.open(OUT .. ".sources.bin", "wb"))
local state_features = assert(io.open(OUT .. ".state.bin", "wb"))
local frame, copies, scene_frames, finished = 0, 0, 0, false
local scene_drift_frames = 0
local parked_frames = 0
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
    "complete status=%s frames=%d scene_frames=%d copies=%d " ..
    "parked_frames=%d scene=%02X\n",
    status, frame, scene_frames, copies, parked_frames,
    emu:read8(0xD880)))
  trace:close()
  sources:close()
  state_features:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(string.format("%s copies=%d scene_frames=%d\n",
    status, copies, scene_frames))
  marker:close()
  emu:stop()
end

local function record_copy(destination, pc, caller)
    if frame <= WARMUP or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    if destination ~= 0x9800 and destination ~= 0x9C00 then return end
    local sp = register("SP")
    if caller == nil then
      caller = emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8)
    end
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
      "copy=%d frame=%d destination=%04X ly=%02X stat=%02X pc=%04X caller=%04X scx=%02X scy=%02X\n",
      copies, frame - WARMUP, destination, emu:read8(0xFF44),
      emu:read8(0xFF41), pc or register("PC"), caller,
      emu:read8(0xFF43), emu:read8(0xFF42)))
    if not COMPACT_TED then
      trace:write(string.format(
        "key=%02X%02X%02X%02X\n", emu:read8(0xDD81),
        emu:read8(0xDDC0), emu:read8(0xDD87), emu:read8(0xDDDC)))
    end
    trace:write(string.format(
      "meta=count:%d sum:%02X xor:%02X roll:%02X weighted:%02X\n",
      meta_count, meta_sum, meta_xor, meta_roll, meta_weighted))
    meta_count, meta_sum, meta_xor, meta_roll, meta_weighted = 0, 0, 0, 0, 0
    trace:flush()
end

pcall(function()
  emu:setBreakpoint(function()
    if CACHED_TED then return end
    record_copy(register("HL") & 0xFC00)
  end, 0x42A7)
end)

-- The native-postcopy cache computes its receipt key after $42A7 returns.
-- Sample the two actual HRAM result bytes at the key-ready physical-map gate,
-- rather than logging the retired DDxx state proxy before the helper ran.
pcall(function()
  emu:setBreakpoint(function()
    if not COMPACT_TED or INCREMENTAL_TED then return end
    if frame <= WARMUP or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    trace:write(string.format(
      "key=%02X%02X\n", emu:read8(0xFFA8), emu:read8(0xFFA9)))
    trace:flush()
  end, 0x5970)
end)

-- The incremental Ted clone keeps its exact four-byte full-source key in
-- BC/DE. $5830 is reached only after the first-publication initializer has
-- completed and SVBK1 has been restored.
pcall(function()
  emu:setBreakpoint(function()
    if not INCREMENTAL_TED then return end
    if frame <= WARMUP or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    local bc, de = register("BC"), register("DE")
    trace:write(string.format("key=%02X%02X%02X%02X\n",
      (bc >> 8) & 0xFF, bc & 0xFF, (de >> 8) & 0xFF, de & 0xFF))
    trace:flush()
  end, 0x5830)
end)

-- The cached path has no $42A7 entry. At the receipt-proven sole Ted caller,
-- DC0B still contains the pre-toggle selector, so XOR 1 and retain its low
-- bit exactly as the runtime does to recover the physical destination map.
pcall(function()
  emu:setBreakpoint(function()
    if not CACHED_TED then return end
    local selector = (emu:read8(0xDC0B) ~ 0x01) & 0x01
    record_copy(selector == 0 and 0x9800 or 0x9C00, 0x028A, 0x028D)
  end, 0x028A)
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
  -- D000-DFFF is banked CGB WRAM. Ted's bounded attribute compiler can span
  -- a frame boundary with SVBK=2/3 selected, where D880/DCBB/D888/DD06 are
  -- cache bytes rather than game state. Reading those bytes produced a false
  -- scene exit; fixture writes also damaged the cache being measured. Wait
  -- for the runtime to restore bank 1, exactly as state generation does.
  local svbk = emu:read8(0xFF70) & 0x07
  if BANKED_WRITER and svbk ~= 0 and svbk ~= 1 then
    -- D880 is unreadable this frame, but the frame still elapsed. Carry the
    -- last known scene state so parked mid-scene frames stay in the
    -- scene_frames denominator; silently dropping them deflated
    -- scene_frames by the parked share on banked candidates and inflated
    -- every per-scene-frame cadence rate (same defect fixed in the
    -- speed-parity and trajectory probes). Keep-alives stay skipped.
    parked_frames = parked_frames + 1
    if scene_drift_frames == 0 and frame > WARMUP and scene_frames > 0 then
      scene_frames = scene_frames + 1
    end
    return
  end
  if emu:read8(0xD880) == EXPECTED_SCENE then
    scene_drift_frames = 0
    -- Keep the contestants alive without writing pose, animation, or timing.
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    -- Synthetic boss-entry states can inherit the one-shot arena-exit latches
    -- used after a defeated/finished attack phase.  HP refresh alone does not
    -- clear them: Ted advances D880 to $FF shortly after reload and the probe
    -- mistakes fixture death for a dead publisher.  The animation probe uses
    -- the same neutral arena hold. Apply it symmetrically to OG and DX; these
    -- bytes are not the publication clock or pose selector.
    emu:write8(0xD888, 0x00)
    emu:write8(0xDD06, 0x00)
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
