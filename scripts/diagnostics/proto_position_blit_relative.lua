-- PROTOTYPE v2: per-frame position blit, banded RELATIVE to the boss's live
-- top row (self-tracking). Kills alternation (per-frame) + tracks the boss
-- (relative bands) + no shared-tile bleed (floor cells gated out).
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
local native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local function log(m) local h=io.open("/tmp/posblit2.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/posblit2.log","w"); if h then h:write("posblit2\n");h:close() end end
local PAL={4,6,5,3}  -- top->bottom bands
local prev={}; local flips=0; local samples=0
local CELLS={{4,10},{6,10},{8,10},{5,13},{10,10}}
local function blit()
  emu:write8(0xFF4F,0)
  local tiles={}
  local minr,maxr=99,-1
  for r=0,17 do tiles[r]={}; for c=0,19 do local t=emu:read8(0x9800+r*32+c); tiles[r][c]=t; if t>0x01 then if r<minr then minr=r end; if r>maxr then maxr=r end end end end
  if maxr<minr then emu:write8(0xFF4F,0); return end
  local span=maxr-minr; if span<1 then span=1 end
  emu:write8(0xFF4F,1)
  for r=0,17 do
    for c=0,19 do
      local a=0
      if tiles[r][c]>0x01 then
        local q=math.floor((r-minr)*4/(span+1)); if q>3 then q=3 end; if q<0 then q=0 end
        a=PAL[q+1]
      end
      emu:write8(0x9800+r*32+c, a)
    end
  end
  emu:write8(0xFF4F,0)
end
local function check()
  emu:write8(0xFF4F,1)
  for _,cc in ipairs(CELLS) do local a=emu:read8(0x9800+cc[1]*32+cc[2])&7; local k=cc[1]..","..cc[2]
    if prev[k]~=nil and prev[k]~=a then flips=flips+1 end; prev[k]=a end
  emu:write8(0xFF4F,0); samples=samples+1
end
callbacks:add("frame",function()
 f=f+1
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 if ph=="boot" then emu:setKeys(0)
  if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then fid=fid+1; if fid>30 then ph="t";sub="pre";pf=0 end end
  return end
 if ph=="t" then
  if sub=="pre" then emu:write8(0xFFBA,8);emu:write8(0xDF0C,0);emu:write8(0xDF1D,0);sub="pr";pf=0
  elseif sub=="pr" then emu:setKeys(0x0C);pf=pf+1;if pf>=10 then emu:setKeys(0);sub="rl";pf=0 end
  elseif sub=="rl" then emu:setKeys(0);pf=pf+1;if pf>=10 then sub="w";pf=0 end
  elseif sub=="w" then pf=pf+1
   if emu:read8(0xD880)==0x0C then sub="run";pf=0
   elseif pf>500 then at=at+1; if at>=8 then ph="done" else sub="pre" end end
  elseif sub=="run" then
    pf=pf+1
   blit()
   if pf%2==0 then check() end
   if pf==120 then emu:screenshot("/tmp/posblit2_a.png") end
   if pf==260 then emu:screenshot("/tmp/posblit2_b.png") end
   if pf==400 then emu:screenshot("/tmp/posblit2_c.png"); log("flips="..flips.." samples="..samples); log("DONE"); ph="done" end
  end
 end
end)
