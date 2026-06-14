-- Verify lava colorization: reach stage 5 (force FFBA only in level-select),
-- then in the dungeon read WRAM 0xDA00[molten IDs] (should be 5 = pal5),
-- dump BG pal5 CRAM, and screenshot. TARGET via env or default 4 (stage 5).
local TARGET = tonumber(os.getenv("LAVA_TARGET") or "4")
local OUT = os.getenv("LAVA_OUT") or "/tmp/lava_verify"
local KEY_A, KEY_START = 0x01, 0x08
local f, phase, seeded, started, conf, done = 0, "title", false, false, 0, false
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("lava verify TARGET="..TARGET.."\n");h:close() end end

local function seedSRAM()
  emu:write8(0x0000, 0x0A)
  for _,b in ipairs({0xBF00,0xBF28,0xBF50,0xBF78,0xBFA0,0xBFC8}) do
    emu:write8(b, 0xFF); for i=1,0x1F do emu:write8(b+i, 0x00) end
  end
end
local function rdbg(p,c) local i=p*8+c*2; emu:write8(0xFF68,i); local lo=emu:read8(0xFF69)
  emu:write8(0xFF68,i+1); local hi=emu:read8(0xFF69); return (hi<<8)|lo end

callbacks:add("frame", function()
  if done then return end
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
    emu:write8(0xFFBA, TARGET); seedSRAM()
    if f % 60 >= 10 and f % 60 < 16 then emu:setKeys(KEY_A) else emu:setKeys(0) end
    if ffc1 == 1 or d880 == 0x18 then started = true; conf = f; phase = "play" end
    return
  end
  if phase == "play" then
    emu:write8(0xDCDD,0x17); emu:write8(0xDCDC,0xFF); emu:write8(0xDCBB,0xF0)
    emu:setKeys(0x10 + ((f % 4 < 2) and KEY_A or 0))
    local dt = f - conf
    -- periodic log of palette + molten-entry state during stable gameplay
    if dt > 300 and dt % 240 == 0 and d880 >= 0x02 and d880 < 0x0C then
      local allp = "allBGpal c1:"
      for p=0,7 do allp=allp..string.format(" p%d=%04X", p, rdbg(p,1)) end
      log(string.format("dt+%d D880=%02X FFC1=%d FFBA=%02X", dt, d880, ffc1, emu:read8(0xFFBA)))
      log("   pal5="..string.format("%04X/%04X/%04X/%04X",rdbg(5,0),rdbg(5,1),rdbg(5,2),rdbg(5,3)))
      log("   "..allp)
    end
    -- screenshots at three late, stable points (only when actively rendering)
    for _,sf in ipairs({600,780,960}) do
      if dt == sf and ffc1 == 1 and d880 >= 0x02 and d880 < 0x0C then
        emu:screenshot(string.format("%s_%d.png", OUT, sf))
        log(string.format("shot dt+%d D880=%02X FFC1=%d", dt, d880, ffc1))
      end
    end
    if dt > 1080 then done=true; log("DONE"); emu:stop() end
  end
end)
