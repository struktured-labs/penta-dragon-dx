-- Dump the real arena tilemap so we can see the true boss extent.
-- Teleports to /tmp/alt_target.txt boss (default 0), settles, collects 120
-- frames. For each cell (rows 0..17, cols 0..23) tracks the count of DISTINCT
-- tile IDs seen (a proxy for "boss/animating") and the last tile. Reads the
-- ACTIVE tilemap (0x9800 or 0x9C00 per LCDC bit 3). Emits:
--   LCDC/SCX/SCY, an animation grid (0-9 distinct-tile count, capped), and a
--   last-frame tile grid (hex). Lets us tell coverage vs position-shift.
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local OUT="/tmp/arena_dump.log"
local function log(m) local h=io.open(OUT,"a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT,"w"); if h then h:write("arena dump\n");h:close() end end
local TARGET=0
do local h=io.open("/tmp/alt_target.txt","r"); if h then local s=h:read("*all"); h:close()
  local n=tonumber((s or ""):match("%d")); if n then TARGET=n end end end
local TGT=0x0C+TARGET
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local SETTLE=90;local COLLECT=120;local MAXTRY=8
local seen={};local last={};local frames=0
local function isar(d) return d>=0x0C and d<=0x14 end
local function base() local l=emu:read8(0xFF40); if (l&0x08)~=0 then return 0x9C00 else return 0x9800 end end
local function collect()
  local b=base(); emu:write8(0xFF4F,0)
  for r=0,17 do for c=0,23 do
    local k=r*24+c; local t=emu:read8(b+r*32+c)
    seen[k]=seen[k] or {}; seen[k][t]=true; last[k]=t
  end end
  frames=frames+1
end
local function emit()
  log(string.format("LCDC=0x%02X SCX=%d SCY=%d base=0x%04X frames=%d",
    emu:read8(0xFF40),emu:read8(0xFF43),emu:read8(0xFF42),base(),frames))
  log("ANIM grid (distinct tile count per cell, capped 9; '.'=1=static):")
  for r=0,17 do
    local s=""
    for c=0,23 do local k=r*24+c; local n=0; if seen[k] then for _ in pairs(seen[k]) do n=n+1 end end
      if n<=1 then s=s.."." else if n>9 then n=9 end; s=s..tostring(n) end end
    log(string.format("A%02d %s",r,s))
  end
  log("TILE grid (last frame, hex):")
  for r=0,17 do
    local s=""
    for c=0,23 do local k=r*24+c; s=s..string.format("%02X",last[k] or 0) end
    log(string.format("T%02d %s",r,s))
  end
  log("DONE")
end
callbacks:add("frame",function()
 f=f+1
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 if ph=="boot" then emu:setKeys(0)
  if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then fid=fid+1; if fid>30 then ph="t";sub="pre";pf=0 end end
  return end
 if ph=="done" then return end
 if sub=="pre" then local pre=TARGET-1; if pre<0 then pre=8 end
  emu:write8(0xFFBA,pre);emu:write8(0xDF0C,0);emu:write8(0xDF1D,0);sub="pr";pf=0
 elseif sub=="pr" then emu:setKeys(0x0C);pf=pf+1;if pf>=10 then emu:setKeys(0);sub="rl";pf=0 end
 elseif sub=="rl" then emu:setKeys(0);pf=pf+1;if pf>=10 then sub="w";pf=0 end
 elseif sub=="w" then pf=pf+1;emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
  if emu:read8(0xD880)==TGT then sub="s";pf=0
  elseif pf>400 then at=at+1; if at>=MAXTRY then log("giveup");ph="done" else sub="pre" end end
 elseif sub=="s" then pf=pf+1;emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
  if not isar(emu:read8(0xD880)) then at=at+1; if at>=MAXTRY then ph="done" else sub="pre";pf=0 end
  elseif pf>=SETTLE then sub="c";pf=0 end
 elseif sub=="c" then emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
  if isar(emu:read8(0xD880)) then collect(); if frames>=COLLECT then emit();ph="done" end
  else ph="done" end
 end
end)
