-- (1) Full STAGE-intro splash tile dump (D880=0x18) once the whole splash is up.
-- (2) Reproduce the in-stage item menu ("MEDICAL"): get into the dungeon, then
--     press START (item/pause) and SELECT; screenshot densely and dump tile+attr
--     on CONSECUTIVE frames to catch flicker (attr alternation) + bg-tile change.
local OUT = os.getenv("OUT") or "/tmp/im"
local f, prevd = 0, -1
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("item menu probe\n");h:close() end end
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end

local function dump(tag)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local tiles={}
  for r=0,17 do tiles[r]={}; for c=0,19 do tiles[r][c]=emu:read8(base+r*32+c) end end
  emu:write8(0xFF4F,1); local at={}
  for r=0,17 do at[r]={}; for c=0,19 do at[r][c]=emu:read8(base+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  log(tag.." base=0x"..string.format("%04X",base).." LCDC=0x"..string.format("%02X",emu:read8(0xFF40)))
  for r=0,17 do
    local s=""
    for c=0,19 do if tiles[r][c]~=0 then s=s..string.format("%02X:p%d ",tiles[r][c],at[r][c]) end end
    if s~="" then log(string.format("  r%02d %s",r,s)) end
  end
end

callbacks:add("frame", function()
  f = f + 1
  local k = 0
  k = k | press(180,186, 0x80) | press(193,199, 0x01) | press(241,247, 0x01)
  k = k | press(291,297, 0x01) | press(341,347, 0x08) | press(391,397, 0x01)
  k = k | press(1000,1006, 0x08)   -- START during gameplay
  k = k | press(1200,1206, 0x04)   -- SELECT during gameplay
  emu:setKeys(k)
  local d = emu:read8(0xD880)
  if d ~= prevd then
    emu:screenshot(string.format("%s_d%02X_f%d.png", OUT, d, f))
    log(string.format("f%d D880=%02X FFC1=%d FFBA=%02X", f, d, emu:read8(0xFFC1), emu:read8(0xFFBA)))
    prevd = d
  end
  if f == 600 then dump("FULL-SPLASH@f600") end
  -- dense screenshots around the START/SELECT presses
  for _,sf in ipairs({990,1010,1020,1040,1060,1100,1190,1210,1220,1240,1300}) do
    if f == sf then emu:screenshot(string.format("%s_m%d_d%02X.png", OUT, f, d))
      log(string.format("menu-snap f%d D880=%02X FFC1=%d", f, d, emu:read8(0xFFC1))) end
  end
  -- consecutive-frame dumps to catch flicker (attr alternation) after START
  if f == 1020 then dump("MENU+START@f1020") end
  if f == 1021 then dump("MENU+START@f1021") end
  if f == 1022 then dump("MENU+START@f1022") end
  if f > 1320 then log("DONE"); emu:stop() end
end)
