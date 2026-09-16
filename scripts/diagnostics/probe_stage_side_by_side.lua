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
--   SSS_AUDIT_STEP  visible tile/attribute audit cadence (default 1)
--   SSS_PUBLICATION_TRACE  optional publication/flip TSV path

local OUT = assert(os.getenv("SSS_OUT"), "SSS_OUT required")
local TARGET = tonumber(os.getenv("SSS_TARGET") or "0")
local LIMIT = tonumber(os.getenv("SSS_FRAMES") or "1200")
local STEP = tonumber(os.getenv("SSS_STEP") or "60")
local AUDIT_STEP = tonumber(os.getenv("SSS_AUDIT_STEP") or "1")
local MODE = os.getenv("SSS_MODE") or "patrol"
local PUBLICATION_TRACE_PATH = os.getenv("SSS_PUBLICATION_TRACE")
local EXPECTED_SCENE = TARGET + 2
local KEY_A, KEY_START = 0x01, 0x08
local KEY_RIGHT, KEY_LEFT = 0x10, 0x20

local frame, phase, seeded, confirmed = 0, "title", false, false
local stable_frames, play_frames = 0, 0
local finished = false
local shots = 0
local trace = assert(io.open(OUT .. ".trace", "w"))
local publication_trace = nil
local tile_copy_map = 0x0000

if PUBLICATION_TRACE_PATH then
  publication_trace = assert(io.open(PUBLICATION_TRACE_PATH, "w"))
  publication_trace:write(
    "frame\tevent\tpc\tbank\tmap\tlcdc\tdc0b\troom\tscx\tscy\t" ..
    "dc00\tdc01\tdc02\tdc03\tffcf\t" ..
    "svbk\tffa5\tffe0\tffe4\tsignature\tmeta9800\tmeta9c00\tf\traw\n")
end

local function bank1_byte(address)
  local old_svbk = emu:read8(0xFF70)
  emu:write8(0xFF70, 0x01)
  local value = emu:read8(address)
  emu:write8(0xFF70, old_svbk)
  return value
end

local function publication_event(event, pc, map)
  if not publication_trace or phase ~= "play"
      or emu:read8(0xD880) ~= EXPECTED_SCENE then return end
  local signature = emu:read8(0xC350) ~ emu:read8(0xC221)
    ~ emu:read8(0xC269) ~ emu:read8(0xC2A3)
  local meta9800 = string.format("%02X%02X%02X",
    bank1_byte(0xDF53), bank1_byte(0xDF54), bank1_byte(0xDF55))
  local meta9c00 = string.format("%02X%02X%02X",
    bank1_byte(0xDF57), bank1_byte(0xDF58), bank1_byte(0xDF59))
  local raw = "-"
  if event == "copy-entry" then
    local cells = {}
    for offset = 0, 575 do
      cells[#cells + 1] = string.format("%02X", emu:read8(0xC1A0 + offset))
    end
    raw = table.concat(cells)
  end
  publication_trace:write(string.format(
    "%d\t%s\t%04X\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
    "%02X\t%02X\t%02X\t%02X\t%02X\t" ..
    "%02X\t%02X\t%02X\t%02X\t%02X\t%s\t%s\t%02X\t%s\n",
    play_frames, event, pc, emu:read8(0xFF99), map or tile_copy_map,
    emu:read8(0xFF40), emu:read8(0xDC0B), emu:read8(0xFFBD),
    emu:read8(0xFF43), emu:read8(0xFF42),
    emu:read8(0xDC00), emu:read8(0xDC01), emu:read8(0xDC02),
    emu:read8(0xDC03), emu:read8(0xFFCF),
    emu:read8(0xFF70),
    emu:read8(0xFFA5), emu:read8(0xFFE0), emu:read8(0xFFE4), signature,
    meta9800, meta9c00, emu:readRegister("F") & 0xFF, raw))
  publication_trace:flush()
end

if publication_trace then
  emu:setBreakpoint(function() tile_copy_map = 0x9C00 end, 0x42A0)
  emu:setBreakpoint(function() tile_copy_map = 0x9800 end, 0x42A5)
  emu:setBreakpoint(function() publication_event("copy-entry", 0x42A7) end, 0x42A7)
  emu:setBreakpoint(function() publication_event("decision", 0x42B1) end, 0x42B1)
  emu:setBreakpoint(function() publication_event("map-done", 0x42ED) end, 0x42ED)
  emu:setBreakpoint(function() publication_event("dirty", 0x42FC) end, 0x42FC)
  emu:setBreakpoint(function() publication_event("lava-front", 0x69F8) end,
    0x69F8, 0x0D)
  emu:setBreakpoint(function() publication_event("lava-core", 0x7D3D) end,
    0x7D3D, 0x0D)
  emu:setBreakpoint(function() publication_event("lava-compare", 0x7D4F) end,
    0x7D4F, 0x0D)
  emu:setBreakpoint(function() publication_event("lava-miss", 0x7D51) end,
    0x7D51, 0x0D)
  emu:setBreakpoint(function()
    publication_event("flip-12E0", 0x12E0,
      (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800)
  end, 0x12E0)
  emu:setBreakpoint(function()
    publication_event("flip-3089", 0x3089,
      (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800)
  end, 0x3089)
end

local function visible_grid()
  local lcdc = emu:read8(0xFF40)
  local base = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local old_vbk = emu:read8(0xFF4F)
  local tiles, attrs = {}, {}
  for row = 0, 17 do
    for column = 0, 19 do
      local map_y = ((scy >> 3) + row) & 0x1F
      local map_x = ((scx >> 3) + column) & 0x1F
      local address = base + map_y * 32 + map_x
      emu:write8(0xFF4F, 0)
      tiles[#tiles + 1] = string.format("%02X", emu:read8(address))
      emu:write8(0xFF4F, 1)
      attrs[#attrs + 1] = string.format("%02X", emu:read8(address))
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(tiles), table.concat(attrs)
end

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
  if status ~= "ok" then
    -- Failure evidence: what the screen and key state looked like when stuck.
    emu:screenshot(OUT .. ".stuck.png")
  end
  trace:write(string.format(
    "complete status=%s frames=%d play_frames=%d shots=%d " ..
    "d880=%02X ffc1=%02X ffba=%02X ffbd=%02X lcdc=%02X\n",
    status, frame, play_frames, shots, emu:read8(0xD880), emu:read8(0xFFC1),
    emu:read8(0xFFBA), emu:read8(0xFFBD), emu:read8(0xFF40)))
  trace:close()
  if publication_trace then publication_trace:close() end
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
    -- Adaptive title handling: fixed-frame START presses miss candidates
    -- whose title timing shifted (v11 title arrives later; the old schedule
    -- idled into ATTRACT, whose demo runs FFC1=1 and false-confirmed the
    -- route). Press DOWN then A (the release GAME START menu route) only
    -- while the title/showcase is actually displayed, retrying every cycle.
    local scene = emu:read8(0xD880)
    -- Title-land: plain title/menu (< 0x02) plus the animated banner (0x1B)
    -- and showcase (0x1C). OG's title sits at D880=0x01.
    local on_title = scene < 0x02 or scene == 0x1B or scene == 0x1C
    local cycle = frame % 90
    if on_title and cycle >= 10 and cycle < 16 then emu:setKeys(0x80)      -- DOWN
    elseif on_title and cycle >= 28 and cycle < 34 then emu:setKeys(KEY_A) -- confirm
    else emu:setKeys(0) end
    if frame == 290 then emu:screenshot(OUT .. ".title.png") end
    if emu:read8(0xFFC1) == 1 and not on_title then
      phase = "level_select"
    end
    if frame > 3600 then finish("no-title-exit") end
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

  if play_frames % AUDIT_STEP == 0 then
    local tiles, attrs = visible_grid()
    trace:write(string.format(
      "audit frame=%d tiles=%s attrs=%s\n", play_frames, tiles, attrs))
  end

  if play_frames % STEP == 0 then
    shots = shots + 1
    emu:screenshot(string.format("%s.f%04d.png", OUT, play_frames))
    trace:write(string.format(
      "shot frame=%d room=%02X scx=%02X scy=%02X d880=%02X\n",
      play_frames, emu:read8(0xFFBD), emu:read8(0xFF43), emu:read8(0xFF42),
      emu:read8(0xD880)))
    local old_signature = emu:read8(0xC1A1)
      ~ emu:read8(0xC245) ~ emu:read8(0xC269)
    local stage5_signature = emu:read8(0xC350)
      ~ emu:read8(0xC221) ~ emu:read8(0xC269)
      ~ emu:read8(0xC2A3)
    trace:write(string.format(
      "state frame=%d lcdc=%02X map=%04X dc0b=%02X dc00=%02X " ..
      "c1a4=%02X ffe0=%02X meta=%02X%02X%02X/%02X%02X%02X " ..
      "signature_old=%02X signature_stage5=%02X\n",
      play_frames, emu:read8(0xFF40),
      ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800,
      emu:read8(0xDC0B), emu:read8(0xDC00), emu:read8(0xC1A4),
      emu:read8(0xFFE0), emu:read8(0xDF53), emu:read8(0xDF54),
      emu:read8(0xDF55), emu:read8(0xDF56), emu:read8(0xDF57),
      emu:read8(0xDF58), old_signature, stage5_signature))
    trace:flush()
  end
  if play_frames >= LIMIT then finish("ok") end
end)
