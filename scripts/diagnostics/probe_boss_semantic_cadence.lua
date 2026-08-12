-- Measure whether consecutive boss map publications actually change the
-- palette plane. The Python/shell owner must launch this through the project
-- single-flight wrapper and terminate only after this probe calls emu:stop().

local OUT = assert(os.getenv("BOSS_SEMANTIC_OUT"),
  "BOSS_SEMANTIC_OUT is required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_SEMANTIC_SCENE") or "15")
local FRAMES = tonumber(os.getenv("BOSS_SEMANTIC_FRAMES") or "900")

local trace = assert(io.open(OUT .. ".trace", "w"))
local planes = assert(io.open(OUT .. ".planes.bin", "wb"))
local tiles = assert(io.open(OUT .. ".tiles.bin", "wb"))
local frame, copies, repeats, changes, finished = 0, 0, 0, 0, false
local scene_drift_frames = 0
local previous = {}
local previous_tiles = {}
local raw_key_samples = {124, 152, 177}
local tile_key_samples = {78, 298, 177, 152, 149}
local penta_tile_key_sample = 60

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

local function palette_plane()
  local bytes = {}
  local raw = {}
  for offset = 0, 0x23F do
    local tile = emu:read8(0xC1A0 + offset)
    raw[offset + 1] = string.char(tile)
    bytes[offset + 1] = string.char(emu:read8(0xC600 + tile) & 7)
  end
  return table.concat(bytes), table.concat(raw)
end

local function changed_cells(before, after)
  if before == nil then return 0x240 end
  local count = 0
  for index = 1, #after do
    if before:byte(index) ~= after:byte(index) then count = count + 1 end
  end
  return count
end

pcall(function()
  emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    copies = copies + 1
    local destination = register("HL") & 0xFC00
    local plane, raw_tiles = palette_plane()
    local scene = emu:read8(0xD880)
    local signature_a = 0
    for _, offset in ipairs(raw_key_samples) do
      signature_a = (signature_a + raw_tiles:byte(offset + 1)) & 0xFF
    end
    local signature_b = scene
    local tile_signature = 0
    if scene == 0x14 then
      tile_signature = raw_tiles:byte(penta_tile_key_sample + 1)
    else
      for _, offset in ipairs(tile_key_samples) do
        tile_signature = tile_signature ~ raw_tiles:byte(offset + 1)
      end
    end
    local cache = (destination == 0x9C00) and 0xDF57 or 0xDF53
    local guarded_penta = scene == 0x14 and destination == 0x9C00 and
      emu:read8(0xFF43) >= 0x14
    local delta = changed_cells(previous[destination], plane)
    local tile_delta = changed_cells(previous_tiles[destination], raw_tiles)
    if previous[destination] == plane then
      repeats = repeats + 1
    else
      changes = changes + 1
    end
    previous[destination] = plane
    previous_tiles[destination] = raw_tiles
    planes:write(plane)
    tiles:write(raw_tiles)
    trace:write(string.format(
      "copy=%d frame=%d destination=%04X changed_cells=%d repeat=%d " ..
      "tile_changed_cells=%d tile_repeat=%d " ..
      "sig_a=%02X sig_b=%02X cache_a=%02X cache_b=%02X hit=%d " ..
      "tile_sig=%02X tile_cache=%02X tile_hit=%d guarded=%d\n",
      copies, frame, destination, delta, delta == 0 and 1 or 0,
      tile_delta, tile_delta == 0 and 1 or 0,
      signature_a, signature_b, emu:read8(cache), emu:read8(cache + 1),
      (emu:read8(cache) == signature_a and
       emu:read8(cache + 1) == signature_b)
        and 1 or 0,
      tile_signature, emu:read8(cache + 2),
      ((destination == 0x9800 or destination == 0x9C00) and
       not guarded_penta and
       emu:read8(cache + 2) == tile_signature and
       emu:read8(cache + 1) == signature_b)
        and 1 or 0, guarded_penta and 1 or 0))
    trace:flush()
  end, 0x42A7)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCDD, 0xFF)
  if emu:read8(0xD880) ~= EXPECTED_SCENE then
    scene_drift_frames = scene_drift_frames + 1
  else
    scene_drift_frames = 0
  end
  if scene_drift_frames > 1 then
    trace:write(string.format("wrong-scene frame=%d scene=%02X\n",
      frame, emu:read8(0xD880)))
    trace:close()
    planes:close()
    tiles:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write("wrong-scene\n")
    done:close()
    finished = true
    emu:stop()
    return
  end
  if frame >= FRAMES then
    trace:write(string.format(
      "complete frames=%d copies=%d changes=%d repeats=%d\n",
      frame, copies, changes, repeats))
    trace:close()
    planes:close()
    tiles:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write(string.format(
      "ok frames=%d copies=%d changes=%d repeats=%d\n",
      frame, copies, changes, repeats))
    done:close()
    finished = true
    emu:stop()
  end
end)
