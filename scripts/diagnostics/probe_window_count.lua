-- Count HBlank-window consumption in the bank1 tile copier during dungeon
-- gameplay. Companion to docs/speed_optimization_plan_v3.md step 0.
--
-- The driver supplies the exact STAT-poll sites and their fall-through
-- (window-body) addresses from a static scan of the ROM under test, so the
-- probe carries no hardcoded copier layout:
--   poll hit  = one busy-wait iteration (~ time spent waiting)
--   body hit  = one acquired window (the wait exited)
-- On the DX candidate the body address also identifies the path taken
-- (atomic tile+attr vs vanilla-style stock), giving the path share per stage.
--
-- Boot route, HP pins, DCFD write, and input mode replicate
-- probe_stage_speed.lua so window counts are comparable with the
-- gameplay_speed_parity receipts.
--
-- Environment:
--   WC_OUT      output prefix (writes .trace and .done)
--   WC_TARGET   FFBA value (0 = Stage 1 ... 6 = Stage 7)
--   WC_FRAMES   measured play frames (default 600)
--   WC_POLLS    comma-separated hex poll-site addresses
--   WC_BODIES   comma-separated hex window-body addresses

local OUT = assert(os.getenv("WC_OUT"), "WC_OUT required")
local TARGET = tonumber(os.getenv("WC_TARGET") or "0")
local LIMIT = tonumber(os.getenv("WC_FRAMES") or "600")
local EXPECTED_SCENE = TARGET + 2
local KEY_A, KEY_START, KEY_RIGHT = 0x01, 0x08, 0x10

local function parse_list(name)
  local raw = assert(os.getenv(name), name .. " required")
  local out = {}
  for token in raw:gmatch("[0-9A-Fa-f]+") do
    out[#out + 1] = tonumber(token, 16)
  end
  assert(#out > 0, name .. " parsed empty")
  return out
end

local POLLS = parse_list("WC_POLLS")
local BODIES = parse_list("WC_BODIES")

local frame, phase, seeded, confirmed = 0, "title", false, false
local stable_frames, play_frames = 0, 0
local finished = false
local main_loop_hits, copy_entries = 0, 0
local poll_hits, body_hits = {}, {}
for _, a in ipairs(POLLS) do poll_hits[a] = 0 end
for _, a in ipairs(BODIES) do body_hits[a] = 0 end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for offset = 1, 0x1F do emu:write8(base + offset, 0x00) end
  end
end

local function finish(status)
  if finished then return end
  finished = true
  local trace = assert(io.open(OUT .. ".trace", "w"))
  trace:write(string.format(
    "complete status=%s frames=%d play_frames=%d main_loop_hits=%d " ..
    "copy_entries=%d scene=%02X\n",
    status, frame, play_frames, main_loop_hits, copy_entries,
    emu:read8(0xD880)))
  for _, a in ipairs(POLLS) do
    trace:write(string.format("poll %04X %d\n", a, poll_hits[a]))
  end
  for _, a in ipairs(BODIES) do
    trace:write(string.format("body %04X %d\n", a, body_hits[a]))
  end
  trace:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

pcall(function()
  for _, a in ipairs(POLLS) do
    emu:setBreakpoint(function()
      if phase == "play" then poll_hits[a] = poll_hits[a] + 1 end
    end, a)
  end
  for _, a in ipairs(BODIES) do
    emu:setBreakpoint(function()
      if phase == "play" then body_hits[a] = body_hits[a] + 1 end
    end, a)
  end
  emu:setBreakpoint(function()
    if phase == "play" then copy_entries = copy_entries + 1 end
  end, 0x42A7)
  emu:setBreakpoint(function()
    if phase == "play" then main_loop_hits = main_loop_hits + 1 end
  end, 0x016C)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:write8(0xDCFD, 0x01)
  if not seeded and frame >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    if frame >= 300 and frame < 306 then emu:setKeys(KEY_START)
    elseif frame >= 360 and frame < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if frame >= 330 then phase = "level_select" end
    return
  end

  if phase == "level_select" and not confirmed then
    emu:write8(0xFFBA, TARGET)
    seed_sram()
    if frame % 60 >= 10 and frame % 60 < 16 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if emu:read8(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
      confirmed = true
      phase = "loading"
    end
    if frame > 900 then finish("no-level-entry") end
    return
  end

  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)

  if phase == "loading" then
    emu:write8(0xFFBA, TARGET)
    emu:setKeys(0)
    if emu:read8(0xD880) == EXPECTED_SCENE and emu:read8(0xFFC1) == 1 then
      stable_frames = stable_frames + 1
      if stable_frames >= 120 then phase = "play" end
    else
      stable_frames = 0
    end
    if frame > 30000 then finish("no-stage-load") end
    return
  end

  play_frames = play_frames + 1
  emu:setKeys(KEY_RIGHT)
  if play_frames >= LIMIT then finish("ok") end
end)
