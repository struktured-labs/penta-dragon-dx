-- Minimal liveness receipt for the exact low-health/music transition route.
-- Keep this probe deliberately free of screenshots, VRAM scans, breakpoints,
-- and watchpoints so a missing heartbeat is evidence of a game-side stall.

local OUT = assert(os.getenv("LOW_HEALTH_LIVE_OUT"))
local SETTLE = tonumber(os.getenv("LOW_HEALTH_LIVE_SETTLE") or "120")
local PRE_TRIGGER = tonumber(os.getenv("LOW_HEALTH_LIVE_PRE_TRIGGER") or "60")
local FINISH = tonumber(os.getenv("LOW_HEALTH_LIVE_FINISH") or "1200")
local LOW_SUB = tonumber(os.getenv("LOW_HEALTH_LIVE_SUB") or "12")
local KEYS = tonumber(os.getenv("LOW_HEALTH_LIVE_KEYS") or "1")
local SCREENSHOTS = os.getenv("LOW_HEALTH_LIVE_SCREENSHOTS") == "1"
local frame = 0
local transition_frame = -1

local heartbeat = assert(io.open(OUT .. ".heartbeat", "w"))
heartbeat:write("frame\tscene\troom\thp_sub\thp_main\td885\td888\tfff7\tlcdc\n")
heartbeat:close()

callbacks:add("frame", function()
  frame = frame + 1
  local scene = emu:read8(0xD880)
  if scene == 0x0A and transition_frame < 0 then transition_frame = frame end

  emu:setKeys(
    frame > SETTLE + PRE_TRIGGER and transition_frame < 0 and KEYS or 0)
  if frame <= SETTLE + PRE_TRIGGER then
    emu:write8(0xDCDD, 1)
  else
    emu:write8(0xDCDC, LOW_SUB)
    emu:write8(0xDCDD, 0)
  end

  local handle = assert(io.open(OUT .. ".heartbeat", "a"))
  handle:write(string.format(
    "%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
    frame, emu:read8(0xD880), emu:read8(0xFFBD),
    emu:read8(0xDCDC), emu:read8(0xDCDD), emu:read8(0xD885),
    emu:read8(0xD888), emu:read8(0xFFF7), emu:read8(0xFF40)))
  handle:close()
  if SCREENSHOTS then
    emu:screenshot(string.format("%s.frame%04d.png", OUT, frame))
  end

  if frame >= FINISH then
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(string.format("ok transition_frame=%d\n", transition_frame))
    marker:close()
    os.exit(0)
  end
end)
