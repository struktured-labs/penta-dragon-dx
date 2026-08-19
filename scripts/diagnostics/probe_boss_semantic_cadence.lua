-- Measure whether consecutive boss map publications actually change the
-- palette plane. The Python/shell owner must launch this through the project
-- single-flight wrapper and terminate only after this probe calls emu:stop().

local OUT = assert(os.getenv("BOSS_SEMANTIC_OUT"),
  "BOSS_SEMANTIC_OUT is required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_SEMANTIC_SCENE") or "15")
local FRAMES = tonumber(os.getenv("BOSS_SEMANTIC_FRAMES") or "900")
local WRAM_CORPUS = os.getenv("BOSS_SEMANTIC_WRAM_CORPUS") == "1"
local BUILDER_TRACE = os.getenv("BOSS_SEMANTIC_BUILDER_TRACE") == "1"
local LATCH_TRACE = os.getenv("BOSS_SEMANTIC_LATCH_TRACE") == "1"

local trace = assert(io.open(OUT .. ".trace", "w"))
local planes = assert(io.open(OUT .. ".planes.bin", "wb"))
local tiles = assert(io.open(OUT .. ".tiles.bin", "wb"))
local wram = WRAM_CORPUS and assert(io.open(OUT .. ".wram.bin", "wb")) or nil
local frame, copies, repeats, changes, finished = 0, 0, 0, 0, false
local scene_drift_frames = 0
local previous = {}
local previous_tiles = {}
-- Mirror scripts/arena_semantic_key.py exactly. Runtime cache layout is
-- raw,sumB,scene,sumA at base+0..3.
local sum_a_samples = {439, 395, 81, 300, 250, 267, 390}
local sum_b_samples = {279, 234, 401, 4, 173, 301, 341, 353, 276}
local raw_sum_samples = {420, 178, 396, 347, 233, 75, 418, 412}
local penta_semantic_key_sample = 62
local cache_writer_counts = {[0xDF5C] = 0, [0xDF5D] = 0,
  [0xDF5E] = 0, [0xDF5F] = 0}

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

-- Attribute every write to the relocated $9C00 cache record independently.
-- A one-byte collision inside the historical four-byte record at $DF57-$DF5A
-- disabled the whole cache, so a range-level presence check is insufficient.
-- The Python owner fails closed unless every observed writer is the bank-20
-- arena helper and all four bytes are exercised by the complete boss suite.
pcall(function()
  emu:setRangeWatchpoint(function(info)
    local address = info.address & 0xFFFF
    cache_writer_counts[address] = (cache_writer_counts[address] or 0) + 1
    trace:write(string.format(
      "cache_writer frame=%d address=%04X bank=%02X pc=%04X old=%02X new=%02X\n",
      frame, address, emu:read8(0xFF99), register("PC") & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF))
    trace:flush()
  -- mGBA's range end is exclusive; DF60 is the first pickup-workspace byte.
  end, 0xDF5C, 0xDF60, C.WATCHPOINT_TYPE.WRITE)
end)

if BUILDER_TRACE then
  pcall(function()
    emu:setBreakpoint(function()
      trace:write(string.format(
        "builder frame=%d scene=%02X source=%04X bank=%02X c349=%02X\n",
        frame, emu:read8(0xD880), register("HL"), emu:read8(0xFF99),
        emu:read8(0xC349)))
      trace:flush()
    end, 0x30AF)
  end)
end

if LATCH_TRACE then
  -- v77's optional exact-repeat cadence selector reaches $60A9 only after a
  -- Shalamar exact cache hit. D still holds the raw-key discriminator, so its
  -- low nibble is the authoritative class distribution for tuning; sampling
  -- the later $42A7 source plane can observe the next native source update.
  pcall(function()
    emu:setBreakpoint(function()
      if frame == 0 or emu:read8(0xD880) ~= 0x0C
          or emu:read8(0xFF99) ~= 0x14 then return end
      trace:write(string.format(
        "exact_class frame=%d raw=%02X class=%X\n",
        frame, register("D") & 0xFF, register("D") & 0x0F))
      trace:flush()
    end, 0x60A9)
  end)
  pcall(function()
    emu:setBreakpoint(function()
      if frame == 0 or emu:read8(0xD880) ~= 0x0C
          or emu:read8(0xFF99) ~= 0x14 then return end
      trace:write(string.format(
        "native_exact frame=%d raw=%02X class=%X\n",
        frame, register("D") & 0xFF, register("D") & 0x0F))
      trace:flush()
    end, 0x60B0)
  end)

  -- $42B0 is the ordinary return from the semantic decider. Exact cache hits
  -- unwind past this point; decisions 1/2/3 identify rebuild, raw-only, and
  -- fused-prepared work respectively.
  pcall(function()
    emu:setBreakpoint(function()
      if frame == 0 or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
      trace:write(string.format(
        "decision frame=%d value=%02X destination=%04X\n",
        frame, emu:read8(0xFFE0), register("HL") & 0xFC00))
      trace:flush()
    end, 0x42B0)
  end)

  -- The postcomputed copier reaches $42FC after its interruptible tile pass.
  -- B.6 must retain the pre-copy semantic decision even though FFE0 has been
  -- consumed as the 24-row counter and is normally zero at this boundary.
  pcall(function()
    emu:setBreakpoint(function()
      if frame == 0 or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
      local b = register("B") & 0xFF
      trace:write(string.format(
        "latch frame=%d b=%02X bit6=%d ffe0=%02X destination=%04X\n",
        frame, b, (b & 0x40) ~= 0 and 1 or 0, emu:read8(0xFFE0),
        register("HL") & 0xFC00))
      trace:flush()
    end, 0x42FC)
  end)
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

local function write_wram_snapshot()
  if not wram then return end
  local bytes = {}
  for address = 0xC000, 0xDFFF do
    bytes[#bytes + 1] = string.char(emu:read8(address))
  end
  for address = 0xFF80, 0xFFFE do
    bytes[#bytes + 1] = string.char(emu:read8(address))
  end
  wram:write(table.concat(bytes))
end

pcall(function()
  emu:setBreakpoint(function()
    -- mGBA may dispatch a restored PC breakpoint before the first frame
    -- callback on one launch but after it on another.  That frame-0 copy is
    -- pre-observation state, not an emulated-frame trajectory sample.
    if frame == 0 then return end
    if emu:read8(0xD880) ~= EXPECTED_SCENE then return end
    copies = copies + 1
    local destination = register("HL") & 0xFC00
    local plane, raw_tiles = palette_plane()
    local scene = emu:read8(0xD880)
    local key_a = 0
    for _, offset in ipairs(sum_a_samples) do
      key_a = (key_a + raw_tiles:byte(offset + 1)) & 0xFF
    end
    local key_b = 0
    for _, offset in ipairs(sum_b_samples) do
      key_b = (key_b + raw_tiles:byte(offset + 1)) & 0xFF
    end
    if scene == 0x14 then
      key_b = (key_b + raw_tiles:byte(penta_semantic_key_sample + 1)) & 0xFF
    end
    local raw_key = 0
    for _, offset in ipairs(raw_sum_samples) do
      raw_key = (raw_key + raw_tiles:byte(offset + 1)) & 0xFF
    end
    -- The $9C00 record lives above the atomic copier's DF5A IE-save byte.
    local cache = (destination == 0x9C00) and 0xDF5C or 0xDF53
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
    write_wram_snapshot()
    trace:write(string.format(
      "copy=%d frame=%d destination=%04X changed_cells=%d repeat=%d " ..
      "tile_changed_cells=%d tile_repeat=%d " ..
      "sum_a=%02X sum_b=%02X raw_sig=%02X cache_raw=%02X " ..
      "cache_sum_b=%02X cache_scene=%02X cache_sum_a=%02X hit=%d " ..
      "raw_hit=%d guarded=%d\n",
      copies, frame, destination, delta, delta == 0 and 1 or 0,
      tile_delta, tile_delta == 0 and 1 or 0,
      key_a, key_b, raw_key,
      emu:read8(cache), emu:read8(cache + 1), emu:read8(cache + 2),
      emu:read8(cache + 3),
      (emu:read8(cache) == raw_key and
       emu:read8(cache + 1) == key_b and
       emu:read8(cache + 2) == scene and
       emu:read8(cache + 3) == key_a)
        and 1 or 0,
      (emu:read8(cache) == raw_key)
        and 1 or 0,
      (destination == 0x4400 or scene == 0x10) and 1 or 0))
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
    if wram then wram:close() end
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write("wrong-scene\n")
    done:close()
    finished = true
    emu:stop()
    return
  end
  if frame >= FRAMES then
    trace:write(string.format(
      "cache_writer_counts DF5C=%d DF5D=%d DF5E=%d DF5F=%d\n",
      cache_writer_counts[0xDF5C], cache_writer_counts[0xDF5D],
      cache_writer_counts[0xDF5E], cache_writer_counts[0xDF5F]))
    trace:write(string.format(
      "complete frames=%d copies=%d changes=%d repeats=%d\n",
      frame, copies, changes, repeats))
    trace:close()
    planes:close()
    tiles:close()
    if wram then wram:close() end
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write(string.format(
      "ok frames=%d copies=%d changes=%d repeats=%d\n",
      frame, copies, changes, repeats))
    done:close()
    finished = true
    emu:stop()
  end
end)
