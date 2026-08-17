-- Walk one dungeon stage on a deterministic scripted route and screenshot at
-- fixed play-frame indices, for OG-versus-DX visual regression review.
-- Route/boot logic mirrors probe_stage_speed.lua / probe_window_count.lua so
-- the frames sit beside the speed receipts. The driver runs this once per
-- ROM per stage; panels are labeled with room/scroll state because the ~6%
-- speed difference makes late frames position-drift between the two ROMs.
--
-- Environment:
--   SSS_OUT      output prefix (screenshots OUT.fNNNN.png, trace, done marker)
--   SSS_TARGET   FFBA value (0 = Stage 1 ... 6 = Stage 7)
--   SSS_FRAMES   play frames to cover (default 1200)
--   SSS_STEP     screenshot every N play frames (default 60)
--   SSS_MODE     right | patrol (default patrol: sweeps more of the room)

local OUT = assert(os.getenv("SSS_OUT"), "SSS_OUT required")
local TARGET = tonumber(os.getenv("SSS_TARGET") or "0")
local LIMIT = tonumber(os.getenv("SSS_FRAMES") or "1200")
local STEP = tonumber(os.getenv("SSS_STEP") or "60")
local MODE = os.getenv("SSS_MODE") or "patrol"
local EXPECTED_SCENE = TARGET + 2
local KEY_A, KEY_START = 0x01, 0x08
local KEY_RIGHT, KEY_LEFT = 0x10, 0x20

local frame, phase, seeded, confirmed = 0, "title", false, false
local stable_frames, play_frames = 0, 0
local finished = false
local shots = 0
local trace = assert(io.open(OUT .. ".trace", "w"))

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
  trace:write(string.format("complete status=%s frames=%d play_frames=%d shots=%d\n",
    status, frame, play_frames, shots))
  trace:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:write8(0xDCFD, 0x01)
  if not seeded and frame >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    if frame >= 300 and frame < 306 then emu:setKeys(KEY_START)
    elseif frame >= 360 and frame < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    -- One aligned title screenshot per side.
    if frame == 290 then emu:screenshot(OUT .. ".title.png") end
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
  if MODE == "right" then
    emu:setKeys(KEY_RIGHT)
  else
    if play_frames % 240 < 120 then emu:setKeys(KEY_RIGHT)
    else emu:setKeys(KEY_LEFT) end
  end

  if play_frames % STEP == 0 then
    shots = shots + 1
    emu:screenshot(string.format("%s.f%04d.png", OUT, play_frames))
    trace:write(string.format(
      "shot frame=%d room=%02X scx=%02X scy=%02X d880=%02X\n",
      play_frames, emu:read8(0xFFBD), emu:read8(0xFF43), emu:read8(0xFF42),
      emu:read8(0xD880)))
    trace:flush()
  end
  if play_frames >= LIMIT then finish("ok") end
end)
