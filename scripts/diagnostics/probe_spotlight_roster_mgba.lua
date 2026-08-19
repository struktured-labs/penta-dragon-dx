-- Deterministically capture all 38 directly seeded title-spotlight actors.
-- One cold boot is saved at the sliding-banner boundary; every identity then
-- reloads that exact native state before FFF2 is seeded to target-1.

local OUT = assert(os.getenv("SPOTLIGHT_ROSTER_OUT"))
local LIMIT = tonumber(os.getenv("SPOTLIGHT_ROSTER_LIMIT") or "30000")
local ROSTER_SIZE = 0x26
local CAPTURE_COUNT = tonumber(os.getenv("SPOTLIGHT_ROSTER_COUNT") or "38")
local SNAPSHOT = OUT .. ".pre-banner.ss0"

local frame, target, saved, seeded, done = 0, 0, false, false, false
local centered_frame, centered_oam = nil, nil
local report = assert(io.open(OUT .. ".tsv", "w"))
report:write("identity\tframe\tscreenshot\thardware_oam\n")

local function game_scene()
  local old_svbk = emu:read8(0xFF70)
  emu:write8(0xFF70, 1)
  local scene = emu:read8(0xD880)
  emu:write8(0xFF70, old_svbk)
  return scene
end

local function body()
  local entries, distinct = {}, {}
  for slot = 0, 3 do
    local base = 0xFE00 + slot * 4
    local y, x = emu:read8(base), emu:read8(base + 1)
    local tile, attr = emu:read8(base + 2), emu:read8(base + 3)
    entries[#entries + 1] = {y=y, x=x, tile=tile, attr=attr}
    distinct[tile] = true
    if y <= 0 or y >= 160 or x <= 0 or x >= 168
        or tile < 0x08 or tile > 0x0F then return nil end
  end
  local count = 0
  for _ in pairs(distinct) do count = count + 1 end
  if count ~= 4 then return nil end
  return entries
end

local function centered(entries)
  local min_y, max_y, min_x, max_x = 255, 0, 255, 0
  for _, entry in ipairs(entries) do
    min_y, max_y = math.min(min_y, entry.y), math.max(max_y, entry.y)
    min_x, max_x = math.min(min_x, entry.x), math.max(max_x, entry.x)
  end
  return min_y >= 76 and max_y <= 92 and min_x >= 74 and max_x <= 92
end

local function encode(entries)
  local values = {}
  for _, entry in ipairs(entries) do
    values[#values + 1] = string.format(
      "%d:%d:%02X:%02X", entry.y, entry.x, entry.tile, entry.attr)
  end
  return table.concat(values, ",")
end

local function finish(status, message)
  if done then return end
  done = true
  report:flush()
  report:close()
  local summary = assert(io.open(OUT .. ".txt", "w"))
  summary:write(string.format(
    "status=%s\nmessage=%s\nframes=%d\ncaptured=%d\n",
    status, message, frame, target))
  summary:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

local function publish(entries)
  local path = string.format("%s.id%02d.png", OUT, target)
  emu:screenshot(path)
  report:write(string.format(
    "%d\t%d\t%s\t%s\n", target, frame, path, encode(entries)))
  report:flush()
  target = target + 1
  centered_frame, centered_oam, seeded = nil, nil, false
  if target >= CAPTURE_COUNT then
    finish("ok", "all-native-spotlight-identities-captured")
    return
  end
  local ok = pcall(function() return emu:loadStateFile(SNAPSHOT) end)
  if not ok then finish("failed", "pre-banner-loadStateFile-failed") end
end

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  emu:setKeys(0)
  local scene = game_scene()
  if not saved and scene == 0x1C then
    local ok = pcall(function() return emu:saveStateFile(SNAPSHOT) end)
    if not ok then
      finish("failed", "pre-banner-saveStateFile-failed")
      return
    end
    saved = true
  end
  if saved and not seeded and scene == 0x1C then
    emu:write8(0xFFF2, (target + ROSTER_SIZE - 1) % ROSTER_SIZE)
    seeded = true
  end
  if seeded and scene == 0x1B and emu:read8(0xFFF2) == target then
    local entries = body()
    if entries and centered(entries) then
      if not centered_frame then
        centered_frame, centered_oam = frame, entries
        -- Keep a fallback frame for the final no-label roster entry.
        emu:screenshot(string.format("%s.id%02d.png", OUT, target))
      end
      -- The native label appears about 250 frames after the actor centers.
      -- Identity 37 has no visible label and leaves sooner, so its centered
      -- body is the strongest available visual receipt (matching the legacy
      -- PyBoy gate's explicit first-sample fallback).
    end
    if centered_frame and (target == 37 or frame - centered_frame >= 250) then
      publish(entries or centered_oam)
      return
    end
  elseif centered_frame and centered_oam then
    publish(centered_oam)
    return
  end
  if frame >= LIMIT then finish("failed", "spotlight-roster-timeout") end
end)
