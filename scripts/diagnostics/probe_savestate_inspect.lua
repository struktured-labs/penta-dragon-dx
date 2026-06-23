-- iter 249: quick savestate inspector — dumps state at f=68 and f=300
local OUT = os.getenv("OUT") or "tmp/savestate_inspect"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then h:write("# savestate inspect (iter 249)\n"); h:close() end
local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

local function dump_oam_slots(target_frame)
  log(string.format("--- f%d OAM dump ---", target_frame))
  log(string.format("  D880=%02X FFBE=%02X FFBF=%02X FFBA=%02X FFC1=%02X",
      emu:read8(0xD880), emu:read8(0xFFBE), emu:read8(0xFFBF),
      emu:read8(0xFFBA), emu:read8(0xFFC1)))
  -- count tiles per palette in visible slots
  local counts = {0,0,0,0,0,0,0,0}
  for s = 0, 39 do
    local y = emu:read8(0xFE00 + s*4)
    local x = emu:read8(0xFE00 + s*4 + 1)
    local tile = emu:read8(0xFE00 + s*4 + 2)
    local attr = emu:read8(0xFE00 + s*4 + 3)
    if y > 0 and y < 160 then
      local pal = attr & 7
      counts[pal+1] = counts[pal+1] + 1
      if s < 12 then
        log(string.format("  slot%d: y=%d x=%d tile=%02X pal=%d", s, y, x, tile, pal))
      end
    end
  end
  log(string.format("  visible OAM pal distribution: p0=%d p1=%d p2=%d p3=%d p4=%d p5=%d p6=%d p7=%d",
      counts[1], counts[2], counts[3], counts[4], counts[5], counts[6], counts[7], counts[8]))
end

callbacks:add("frame", function()
  f = f + 1
  if f == 68 then dump_oam_slots(68)
  elseif f == 300 then dump_oam_slots(300)
  elseif f > 350 then
    log("DONE"); emu:stop()
  end
end)
