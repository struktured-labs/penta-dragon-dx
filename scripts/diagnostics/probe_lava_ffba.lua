-- Reach stage 5 via the level-select hack, then in the dungeon STOP forcing
-- FFBA and just READ it (plus FFBD/FFCF/DCFD) while histogramming the on-screen
-- BG tile IDs. Goal: confirm whether FFBA actually equals 4 during normal
-- stage-5 dungeon roaming (so it's a valid lava-override key) OR whether the
-- lava tileset is present while FFBA reads something else (need another key).
local TARGET = 4               -- stage 5 = FFBA 4
local KEY_A, KEY_START = 0x01, 0x08
local f, phase, seeded, started, conf = 0, "title", false, false, 0
local function log(m) local h=io.open("/tmp/lava_ffba.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/lava_ffba.log","w"); if h then h:write("lava ffba probe\n");h:close() end end

local function seedSRAM()
  emu:write8(0x0000, 0x0A)
  for _,b in ipairs({0xBF00,0xBF28,0xBF50,0xBF78,0xBFA0,0xBFC8}) do
    emu:write8(b, 0xFF); for i=1,0x1F do emu:write8(b+i, 0x00) end
  end
end

local function dumpTiles(tag)
  emu:write8(0xFF4F,0)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  local cnt = {}
  for r=0,17 do for c=0,19 do local t=emu:read8(base+r*32+c); cnt[t]=(cnt[t] or 0)+1 end end
  -- top 8 tile IDs
  local arr={}; for k,v in pairs(cnt) do arr[#arr+1]={k,v} end
  table.sort(arr, function(a,b) return a[2]>b[2] end)
  local s=tag.." top:"
  for i=1,math.min(8,#arr) do s=s..string.format(" %02X(%d)",arr[i][1],arr[i][2]) end
  -- presence of stage5 lava IDs 02-05,12-15
  local lava=0; for _,id in ipairs({0x02,0x03,0x04,0x05,0x12,0x13,0x14,0x15}) do lava=lava+(cnt[id] or 0) end
  s=s..string.format("  [lavaIDs=%d]",lava)
  log(s)
end

callbacks:add("frame", function()
  f = f + 1
  emu:write8(0xDCFD, 0x01)
  if not seeded and f >= 100 then seedSRAM(); seeded = true end
  local d880, ffc1 = emu:read8(0xD880), emu:read8(0xFFC1)

  if phase == "title" then
    if f >= 300 and f < 306 then emu:setKeys(KEY_START)
    elseif f >= 360 and f < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if f >= 330 then phase = "ls" end
    return
  end
  if phase == "ls" and not started then
    emu:write8(0xFFBA, TARGET); seedSRAM()   -- only force FFBA to PICK the stage
    if f % 60 >= 10 and f % 60 < 16 then emu:setKeys(KEY_A) else emu:setKeys(0) end
    if ffc1 == 1 or d880 == 0x18 then started = true; conf = f; phase = "play" end
    return
  end
  if phase == "play" then
    -- keep Sara alive but DO NOT touch FFBA — read it as the game maintains it
    emu:write8(0xDCDD,0x17); emu:write8(0xDCDC,0xFF); emu:write8(0xDCBB,0xF0)
    emu:setKeys(0x10 + ((f % 4 < 2) and KEY_A or 0))   -- walk right + fire
    if (f - conf) % 120 == 0 then
      log(string.format("f%d t+%d  D880=%02X FFC1=%d FFBA=%02X FFBD=%02X FFCF=%02X DCFD=%02X DCB8=%02X",
        f, f-conf, d880, ffc1, emu:read8(0xFFBA), emu:read8(0xFFBD),
        emu:read8(0xFFCF), emu:read8(0xDCFD), emu:read8(0xDCB8)))
      dumpTiles("   ")
    end
    if f > conf + 900 then emu:screenshot("/tmp/lava_ffba.png"); log("DONE"); emu:stop() end
  end
end)
