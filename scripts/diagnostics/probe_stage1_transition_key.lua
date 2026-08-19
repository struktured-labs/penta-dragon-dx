-- Capture exact Stage-1 packed layouts and their compiled attribute planes.
--
-- Environment:
--   STAGE1_KEY_OUT         required TSV output
--   STAGE1_KEY_REPORT      required summary output
--   STAGE1_KEY_MODE        live, attract, or state
--   STAGE1_KEY_FRAMES      measured Stage-1 frames (default 900)
--   STAGE1_KEY_MAX_FRAMES  total-frame safety limit (default 30000)

-- This probe deliberately records the live C600 LUT-derived plane instead of
-- guessing which tiles are chromatic.  Stage 1 mutates that LUT around hazard
-- and low-health transitions, and a pickup-only classifier can therefore
-- certify an unsafe map-cache key.

local OUT = assert(os.getenv("STAGE1_KEY_OUT"))
local REPORT = assert(os.getenv("STAGE1_KEY_REPORT"))
local MODE = os.getenv("STAGE1_KEY_MODE") or "state"
local LIMIT = tonumber(os.getenv("STAGE1_KEY_FRAMES") or "900")
local MAX_FRAMES = tonumber(os.getenv("STAGE1_KEY_MAX_FRAMES") or "30000")

local KEY_A, KEY_DOWN = 0x01, 0x80
local KEY_RIGHT, KEY_LEFT, KEY_UP = 0x10, 0x20, 0x40
local trace = assert(io.open(OUT, "w"))
trace:write(
  "copy\tframe\tstage_frame\tdestination\tscene\troom\tscx\tscy\tdc02" ..
  "\tdc00\tdc01\tdc03\tdc81\tffcf\tffe8\tffe9\tffeb" ..
  "\tdcfd\tffc1\traw\tplane\n")

local frame, stage_frame, copies = 0, 0, 0
local phase, stable = "bootstrap", 0
local destination = 0
local finished = false

local function is_stage1_scene()
  return (emu:read8(0xD880) & 0xF7) == 0x02
end

local function hex_bytes(address, length, transform)
  local parts = {}
  for offset = 0, length - 1 do
    local value = emu:read8(address + offset)
    if transform then value = transform(value) end
    parts[#parts + 1] = string.format("%02X", value)
  end
  return table.concat(parts)
end

local function finish(reason)
  if finished then return end
  finished = true
  trace:flush()
  trace:close()
  local report = assert(io.open(REPORT, "w"))
  report:write(string.format("mode=%s\n", MODE))
  report:write(string.format("reason=%s\n", reason))
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format("stage_frames=%d\n", stage_frame))
  report:write(string.format("copies=%d\n", copies))
  report:write(string.format("final_scene=%02X\n", emu:read8(0xD880)))
  report:write(string.format("final_dcfd=%02X\n", emu:read8(0xDCFD)))
  report:close()
  emu:stop()
end

pcall(function()
  emu:setBreakpoint(function()
    if emu:read8(0xFF99) == 1 then destination = 0x9C00 end
  end, 0x42A0, 1)
  emu:setBreakpoint(function()
    if emu:read8(0xFF99) == 1 then destination = 0x9800 end
  end, 0x42A5, 1)
  emu:setBreakpoint(function()
    if not is_stage1_scene() or emu:read8(0xFF99) ~= 1 then return end
    if destination ~= 0x9800 and destination ~= 0x9C00 then return end
    copies = copies + 1
    local raw = hex_bytes(0xC1A0, 576)
    local plane = hex_bytes(0xC1A0, 576, function(tile)
      return emu:read8(0xC600 + tile) & 0x07
    end)
    trace:write(string.format(
      "%d\t%d\t%d\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
      "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
      "\t%02X\t%02X\t%s\t%s\n",
      copies, frame, stage_frame, destination, emu:read8(0xD880),
      emu:read8(0xFFBD), emu:read8(0xFF43), emu:read8(0xFF42),
      emu:read8(0xDC02), emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC03), emu:read8(0xDC81), emu:read8(0xFFCF),
      emu:read8(0xFFE8), emu:read8(0xFFE9), emu:read8(0xFFEB),
      emu:read8(0xDCFD), emu:read8(0xFFC1),
      raw, plane))
    trace:flush()
  end, 0x42A7, 1)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if frame >= MAX_FRAMES then finish("max_frames") return end

  if phase == "bootstrap" then
    if is_stage1_scene() and emu:read8(0xFFC1) == 1 then
      if MODE ~= "attract" or emu:read8(0xDCFD) == 0 then
        stable = stable + 1
        if stable >= 30 then phase = "play" end
      end
    elseif MODE == "live" and frame >= 120 then
      phase = "autostart"
    else
      stable = 0
    end
  end

  if phase == "autostart" then
    if frame >= 180 and frame <= 185 then emu:setKeys(KEY_DOWN)
    elseif frame >= 193 and frame <= 198 then emu:setKeys(KEY_A)
    elseif frame >= 241 and frame <= 246 then emu:setKeys(KEY_A)
    elseif frame >= 291 and frame <= 296 then emu:setKeys(KEY_A)
    elseif frame >= 341 and frame <= 346 then emu:setKeys(KEY_A)
    elseif frame >= 391 and frame <= 396 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if is_stage1_scene() and emu:read8(0xDCFD) == 1
        and emu:read8(0xFFC1) == 1 then
      stable = stable + 1
      if stable >= 90 then phase = "play" end
    else
      stable = 0
    end
    return
  end

  if phase ~= "play" then
    emu:setKeys(0)
    return
  end

  stage_frame = stage_frame + 1
  if MODE == "attract" then
    emu:setKeys(0)
    if stage_frame >= LIMIT then finish("limit") return end
    if stage_frame > 120 and not is_stage1_scene() then
      finish("attract_exit")
    end
    return
  end

  -- Exercise both axes, attacks, and alternating physical BG maps without
  -- forcing room state. Loaded spike/miniboss/low-health fixtures therefore
  -- retain their natural state machines.
  local leg = math.floor((stage_frame % 480) / 120)
  local movement
  if leg == 0 then movement = KEY_UP
  elseif leg == 1 then movement = KEY_RIGHT
  elseif leg == 2 then movement = KEY_DOWN
  else movement = KEY_LEFT end
  if (stage_frame % 90) < 12 then movement = movement | KEY_A end
  emu:setKeys(movement)
  if stage_frame >= LIMIT then finish("limit") end
end)
