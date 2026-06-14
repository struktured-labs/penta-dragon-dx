-- Diagnose the SELECT item-menu flicker + "bg tiles changed". Get into the
-- dungeon, snapshot bg attrs BEFORE the menu, open the menu (SELECT), then dump
-- tile+attr on many CONSECUTIVE frames. Flag any cell whose palette changes
-- frame-to-frame while its tile ID is unchanged (= flicker / alternation).
local OUT = os.getenv("OUT") or "/tmp/mf"
local f = 0
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("menu flicker probe\n");h:close() end end
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end

local function grab()
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local t={}
  for i=0,17*32-1 do t[i]=emu:read8(base+i) end
  emu:write8(0xFF4F,1); local a={}
  for i=0,17*32-1 do a[i]=emu:read8(base+i)&7 end
  emu:write8(0xFF4F,0)
  return base,t,a
end

local prev=nil
local function dumpDiff(tag)
  local base,t,a = grab()
  if prev then
    local nflip=0; local samples={}
    for i=0,17*32-1 do
      if t[i]==prev.t[i] and t[i]~=0 and a[i]~=prev.a[i] then
        nflip=nflip+1
        if #samples<12 then samples[#samples+1]=string.format("c%d(t%02X p%d->%d)",i,t[i],prev.a[i],a[i]) end
      end
    end
    log(string.format("%s flips=%d %s", tag, nflip, table.concat(samples," ")))
  else
    log(tag.." (first frame, baseline)")
  end
  prev={t=t,a=a}
end

-- bottom rows (status bar / MEDICAL box live in lower screen) tile+attr dump
local function dumpBottom(tag)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local tiles={}
  for r=10,17 do tiles[r]={}; for c=0,19 do tiles[r][c]=emu:read8(base+r*32+c) end end
  emu:write8(0xFF4F,1); local at={}
  for r=10,17 do at[r]={}; for c=0,19 do at[r][c]=emu:read8(base+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  log(tag.." (rows 10-17):")
  for r=10,17 do local s=""; for c=0,19 do if tiles[r][c]~=0 then s=s..string.format("%02X:p%d ",tiles[r][c],at[r][c]) end end
    if s~="" then log(string.format("  r%02d %s",r,s)) end end
end

callbacks:add("frame", function()
  f = f + 1
  local k = 0
  k = k | press(180,186, 0x80) | press(193,199, 0x01) | press(241,247, 0x01)
  k = k | press(291,297, 0x01) | press(341,347, 0x08) | press(391,397, 0x01)
  k = k | press(1200,1206, 0x04)   -- SELECT: open item menu
  emu:setKeys(k)
  if f == 1180 then dumpBottom("BEFORE-MENU@f1180"); emu:screenshot(OUT.."_before.png") end
  -- consecutive-frame flicker scan once menu is open
  if f >= 1215 and f <= 1265 then dumpDiff("menu f"..f) end
  if f == 1245 then dumpBottom("DURING-MENU@f1245"); emu:screenshot(OUT.."_during.png") end
  if f >= 1206 and f <= 1230 then
    emu:screenshot(string.format("%s_t%d.png",OUT,f))
    log(string.format("  scrollshot f%d SCX=%d SCY=%d FFC1=%d", f, emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xFFC1)))
  end
  if f > 1290 then log("DONE"); emu:stop() end
end)
