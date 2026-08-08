-- Capture the first stable room selected through the game's native level-select.
--
-- Environment:
--   STAGE_TARGET  FFBA value (0 = stage 1, 1 = stage 2, ...)
--   STAGE_OUT     output prefix; writes .log/.meta and binary VRAM/map dumps
--   STAGE_SHOT    "1" to request a PNG (avoid with mgba-headless)
--   STAGE_STATE_OUT optional mGBA state path saved after the stable capture
--
-- This intentionally keeps Sara stationary. The goal is to compare the exact
-- vanilla and DX tile graphics/map state before enemies, scrolling, or a quick
-- checkpoint transition can muddy the result.

local TARGET = tonumber(os.getenv("STAGE_TARGET") or "1")
local OUT = os.getenv("STAGE_OUT") or "/tmp/penta_stage_integrity"
local SHOT = os.getenv("STAGE_SHOT") == "1"
local STATE_OUT = os.getenv("STAGE_STATE_OUT")
local KEY_A, KEY_START = 0x01, 0x08
local f, phase, seeded, confirmed = 0, "title", false, false
local stable_frames = 0
local expected_scene = TARGET + 2

local function append(path, text)
  local fh = io.open(path, "a")
  if fh then fh:write(text); fh:close() end
end

local function log(text)
  append(OUT .. ".log", string.format("f%05d %s\n", f, text))
end

do
  local fh = io.open(OUT .. ".log", "w")
  if fh then
    fh:write(string.format("target=%d expected_scene=%02X\n", TARGET, expected_scene))
    fh:close()
  end
end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for i = 1, 0x1F do emu:write8(base + i, 0x00) end
  end
end

local function dump_range(path, first, last)
  local fh = assert(io.open(path, "wb"))
  for address = first, last do
    fh:write(string.char(emu:read8(address)))
  end
  fh:close()
end

local function capture()
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  dump_range(OUT .. ".vram0.bin", 0x8000, 0x97FF)
  dump_range(OUT .. ".map0.bin", 0x9800, 0x9FFF)
  emu:write8(0xFF4F, 1)
  dump_range(OUT .. ".vram1.bin", 0x8000, 0x97FF)
  dump_range(OUT .. ".attr.bin", 0x9800, 0x9FFF)
  dump_range(OUT .. ".bg-lut.bin", 0xC600, 0xC6FF)

  local old_bcps = emu:read8(0xFF68)
  local bgp = assert(io.open(OUT .. ".bgp.bin", "wb"))
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    bgp:write(string.char(emu:read8(0xFF69)))
  end
  bgp:close()
  emu:write8(0xFF68, old_bcps)

  local active_base = ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800
  local hist, unsafe, visible = {}, 0, 0
  for row = 0, 17 do
    for col = 0, 19 do
      local attr = emu:read8(active_base + row * 32 + col)
      hist[attr] = (hist[attr] or 0) + 1
      if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
      visible = visible + 1
    end
  end

  local keys = {}
  for attr in pairs(hist) do keys[#keys + 1] = attr end
  table.sort(keys)
  local parts = {}
  for _, attr in ipairs(keys) do
    parts[#parts + 1] = string.format("%02X:%d", attr, hist[attr])
  end

  local meta = assert(io.open(OUT .. ".meta", "w"))
  meta:write(string.format(
    "frame=%d target=%d expected_scene=%02X D880=%02X FFC1=%02X FF91=%02X DF02=%02X DF0D=%02X FFBA=%02X " ..
    "LCDC=%02X SCX=%02X SCY=%02X active_map=%04X visible=%d unsafe_attr=%d\n",
    f, TARGET, expected_scene, emu:read8(0xD880), emu:read8(0xFFC1),
    emu:read8(0xFF91), emu:read8(0xDF02), emu:read8(0xDF0D), emu:read8(0xFFBA),
    emu:read8(0xFF40), emu:read8(0xFF43),
    emu:read8(0xFF42), active_base, visible, unsafe))
  meta:write("visible_attr_hist=" .. table.concat(parts, ",") .. "\n")
  meta:close()

  emu:write8(0xFF4F, old_vbk)
  if SHOT then emu:screenshot(OUT .. ".png") end
  if STATE_OUT then
    local ok, result = pcall(function() return emu:saveStateFile(STATE_OUT) end)
    local saved = ok and result ~= false
    append(OUT .. ".meta", string.format(
      "state_saved=%s state_result=%s state_path=%s\n",
      tostring(saved), tostring(result), STATE_OUT))
    log("saved stable stream state to " .. STATE_OUT)
    if saved then os.exit(0) else os.exit(2) end
  end
  log("captured stable stage state")
  emu:stop()
end

callbacks:add("frame", function()
  f = f + 1
  emu:write8(0xDCFD, 0x01)
  if not seeded and f >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    if f >= 300 and f < 306 then emu:setKeys(KEY_START)
    elseif f >= 360 and f < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if f >= 330 then phase = "level_select" end
    return
  end

  if phase == "level_select" and not confirmed then
    emu:write8(0xFFBA, TARGET)
    seed_sram()
    if f % 60 >= 10 and f % 60 < 16 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if emu:read8(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
      confirmed = true
      phase = "loading"
      log("level selected")
    end
    if f > 700 then log("failed to enter stage"); emu:stop() end
    return
  end

  emu:setKeys(0)
  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xFFBA, TARGET)

  if emu:read8(0xD880) == expected_scene and emu:read8(0xFFC1) == 1 then
    stable_frames = stable_frames + 1
  else
    stable_frames = 0
  end

  if stable_frames == 120 then capture() end
  if f > 2200 then log("timed out before stable room"); emu:stop() end
end)
