-- Map the STAGE-intro splash ("STAGE 01 / STAGE LOAD / TOP 3") and the in-stage
-- item menu ("MEDICAL / MEGA-FLASH"): cold-boot, auto-start, log every D880
-- change with a screenshot, and once in gameplay try SELECT then START to open
-- the item menu. Dump tilemap tile IDs + per-cell BG palette (VBK=1) when asked.
local OUT = os.getenv("OUT") or "/tmp/sim"
local f, shots, prevd = 0, 0, -1
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("stage-intro + menu map\n");h:close() end end
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end

local function dump(tag)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local tiles={}
  for r=0,17 do tiles[r]={}; for c=0,19 do tiles[r][c]=emu:read8(base+r*32+c) end end
  emu:write8(0xFF4F,1); local at={}
  for r=0,17 do at[r]={}; for c=0,19 do at[r][c]=emu:read8(base+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  log(tag.." base=0x"..string.format("%04X",base))
  for r=0,17 do
    local s=""
    for c=0,19 do if tiles[r][c]~=0 then s=s..string.format("%02X:p%d ",tiles[r][c],at[r][c]) end end
    if s~="" then log(string.format("  r%02d %s",r,s)) end
  end
end

callbacks:add("frame", function()
  f = f + 1
  local k = 0
  k = k | press(180,186, 0x80)   -- DOWN
  k = k | press(193,199, 0x01)   -- A
  k = k | press(241,247, 0x01)   -- A
  k = k | press(291,297, 0x01)   -- A
  k = k | press(341,347, 0x08)   -- START
  k = k | press(391,397, 0x01)   -- A
  -- in gameplay: SELECT at f700, START at f850 to find the item menu
  k = k | press(700,706, 0x04)   -- SELECT
  k = k | press(850,856, 0x08)   -- START
  emu:setKeys(k)
  local d = emu:read8(0xD880)
  if d ~= prevd then
    shots = shots + 1
    emu:screenshot(string.format("%s_d%02X_f%d.png", OUT, d, f))
    log(string.format("f%d D880=%02X FFC1=%d FFBA=%02X FFBD=%02X LCDC=%02X",
      f, d, emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFBD), emu:read8(0xFF40)))
    prevd = d
  end
  -- periodic snapshots around the menu attempts
  for _,sf in ipairs({470,520,720,760,820,880,920}) do
    if f == sf then emu:screenshot(string.format("%s_t%d_d%02X.png", OUT, f, d))
      log(string.format("snap f%d D880=%02X FFC1=%d", f, d, emu:read8(0xFFC1))) end
  end
  if f == 520 then dump("STAGE-INTRO@f520") end
  if f == 760 then dump("AFTER-SELECT@f760") end
  if f == 900 then dump("AFTER-START@f900") end
  if f > 960 then log("DONE"); emu:stop() end
end)
