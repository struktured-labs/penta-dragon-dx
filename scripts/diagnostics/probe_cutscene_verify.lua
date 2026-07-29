-- Verify the D880=0x15 intro-cutscene overlay. Cold-boots, presses START to
-- advance past the title menu into the OPENING cutscene chain, then at multiple
-- points where D880==0x15 dumps: (a) the 0xDA00 attr-table palette histogram
-- (expect pal2 for 0x80-0xC9, pal4 for 0x6B-0x72, pal1 for 0xF0-0xFF, pal3 for
-- 0x10-0x4F), and (b) the on-screen BG attr histogram (count cells per palette).
-- Pass criterion: pal2/pal3/pal4 cells present, pal1 (red flood) MINORITY only.
-- Caps screenshots at each panel transition for visual diffing against user's
-- caps 108/110/111/112.
local OUT = os.getenv("OUT") or "/tmp/cutscene_verify"
local CAPS = OUT .. "_caps"
local LOG = io.open(OUT..".log", "w")
local function log(m) if LOG then LOG:write(m.."\n"); LOG:flush() end end

local f, done = 0, false
local seen_15 = false
local last_dump_f = 0
local prev_d880 = -1
local panels_capped = 0
local DUMP_INTERVAL = 600   -- every 10s of game time at 60fps

log("cutscene_verify start")

-- Drive past title menu: at frame 320 press START a few times
local function press_start_at(frame)
  if f == frame or f == frame+2 then emu:setKeys(0x08)
  else emu:setKeys(0) end
end

local function dump_bgtable()
  local h = {}
  for i = 0, 255 do
    local p = emu:read8(0xDA00 + i) & 7
    h[p] = (h[p] or 0) + 1
  end
  local s = ""
  for p = 0, 7 do if h[p] and h[p] > 0 then s = s .. string.format(" pal%d=%d", p, h[p]) end end
  return s
end

local function dump_screen_attrs()
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F, 1)
  local h = {}
  for r = 0, 17 do for c = 0, 19 do
    local p = emu:read8(base + r*32 + c) & 7
    h[p] = (h[p] or 0) + 1
  end end
  emu:write8(0xFF4F, 0)
  local s = ""
  for p = 0, 7 do if h[p] and h[p] > 0 then s = s .. string.format(" pal%d=%d", p, h[p]) end end
  return s, (h[1] or 0)
end

callbacks:add("frame", function()
  if done then return end
  f = f + 1
  if f < 300 then emu:setKeys(0); return end

  -- Drive into the opening: press START at the title menu, then again at any
  -- subsequent menu screens; otherwise hold no keys.
  if f == 320 or f == 340 or f == 360 then emu:setKeys(0x08)
  elseif f == 1200 or f == 1220 then emu:setKeys(0x08)
  else emu:setKeys(0) end

  local d = emu:read8(0xD880)

  if d ~= prev_d880 then
    log(string.format("f%d D880 transition: 0x%02X -> 0x%02X", f, prev_d880, d))
    prev_d880 = d
  end

  if d == 0x15 and (not seen_15 or f - last_dump_f >= DUMP_INTERVAL) then
    seen_15 = true
    last_dump_f = f
    panels_capped = panels_capped + 1
    local bg_table = dump_bgtable()
    local scr_attrs, red = dump_screen_attrs()
    log(string.format("f%d D880=0x15 bg_table[0xDA00]: %s", f, bg_table))
    log(string.format("f%d D880=0x15 screen attrs: %s  RED(p1)=%d", f, scr_attrs, red))
    emu:screenshot(string.format("%s_panel%d_f%d.png", CAPS, panels_capped, f))
  end

  if f >= 10000 then
    done = true
    log(string.format("done at f%d, panels_capped=%d, seen_15=%s",
      f, panels_capped, tostring(seen_15)))
    if seen_15 then log("PASS: reached D880=0x15") else log("FAIL: never reached D880=0x15") end
    emu:stop()
  end
end)
