-- Full-screen arena alternation probe.
-- Teleports to a target boss (default Shalamar; override via /tmp/alt_target.txt
-- containing a single digit 0..8), settles, then over N frames scans EVERY
-- boss-region cell (rows 0..17, cols 0..19) and classifies each change:
--   flip_stable  : attr palette changed while tile ID stayed the same
--                  => competing/disagreeing writers (the bug we are killing)
--   tile_changed : tile ID changed (boss animation; expected w/ tile-ID keying)
-- Emits a single SUMMARY line + a screenshot so before/after is comparable.
--
-- Target maps: FFBA pre = (target-1) mod 9 so the ROM's INC lands on target;
-- target D880 = 0x0C + target.
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
local OUT="/tmp/alt_fullscan.log"
local SHOT="/tmp/alt_fullscan.png"
local function log(m) local h=io.open(OUT,"a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT,"w"); if h then h:write("alt fullscan\n");h:close() end end

-- read target
local TARGET=0
do local h=io.open("/tmp/alt_target.txt","r"); if h then local s=h:read("*all"); h:close()
  local n=tonumber((s or ""):match("%d")); if n then TARGET=n end end end
local NAMES={[0]="shalamar","riff","crystal_dragon","cameo","ted","troop","faze","angela","penta_dragon"}
local TGT_D880=0x0C+TARGET
log("target="..TARGET.." ("..(NAMES[TARGET] or "?")..") d880=0x"..string.format("%02X",TGT_D880))

local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local SETTLE=90;local COLLECT=400;local MAXTRY=8
local ptile={};local pattr={}
local flip_stable=0;local tile_changed=0;local frames=0
local flipset={}

local function isar(d) return d>=0x0C and d<=0x14 end

local function scan()
  emu:write8(0xFF4F,0)
  local t={}
  for r=0,17 do for c=0,19 do t[r*20+c]=emu:read8(0x9800+r*32+c) end end
  emu:write8(0xFF4F,1)
  local a={}
  for r=0,17 do for c=0,19 do a[r*20+c]=emu:read8(0x9800+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  for k=0,359 do
    local pt=ptile[k];local pa=pattr[k]
    if pt~=nil then
      if t[k]==pt and a[k]~=pa then flip_stable=flip_stable+1; flipset[k]=(flipset[k] or 0)+1
      elseif t[k]~=pt then tile_changed=tile_changed+1 end
    end
    ptile[k]=t[k];pattr[k]=a[k]
  end
  frames=frames+1
end

local function emit()
  local ncells=0; for _ in pairs(flipset) do ncells=ncells+1 end
  emu:screenshot(SHOT)
  log(string.format("SUMMARY target=%d name=%s frames=%d flip_stable=%d tile_changed=%d distinct_flip_cells=%d",
    TARGET, NAMES[TARGET] or "?", frames, flip_stable, tile_changed, ncells))
  -- top flipping cells
  local arr={}; for k,v in pairs(flipset) do arr[#arr+1]={k,v} end
  table.sort(arr,function(x,y) return x[2]>y[2] end)
  for i=1,math.min(12,#arr) do local k=arr[i][1]; log(string.format("  flipcell r=%d c=%d count=%d",math.floor(k/20),k%20,arr[i][2])) end
  log("DONE")
end

callbacks:add("frame",function()
 f=f+1
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 if ph=="boot" then emu:setKeys(0)
  if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then fid=fid+1; if fid>30 then ph="t";sub="pre";pf=0;log("dungeon") end end
  return end
 if ph=="done" then return end
 -- teleport state machine
 if sub=="pre" then local pre=TARGET-1; if pre<0 then pre=8 end
  emu:write8(0xFFBA,pre);emu:write8(0xDF0C,0);emu:write8(0xDF1D,0);log("pre="..pre.." try="..at);sub="pr";pf=0
 elseif sub=="pr" then emu:setKeys(0x0C);pf=pf+1;if pf>=10 then emu:setKeys(0);sub="rl";pf=0 end
 elseif sub=="rl" then emu:setKeys(0);pf=pf+1;if pf>=10 then sub="w";pf=0 end
 elseif sub=="w" then pf=pf+1
  if emu:read8(0xD880)==TGT_D880 then log("arena reached");sub="s";pf=0
  elseif pf>400 then at=at+1; if at>=MAXTRY then log("giveup");emit();ph="done" else sub="pre" end end
 elseif sub=="s" then pf=pf+1
  if not isar(emu:read8(0xD880)) then at=at+1; if at>=MAXTRY then emit();ph="done" else sub="pre";pf=0 end
  elseif pf>=SETTLE then sub="c";pf=0 end
 elseif sub=="c" then 
  if isar(emu:read8(0xD880)) then scan(); if frames>=COLLECT then emit();ph="done" end
  else if frames>30 then emit() end; ph="done" end
 end
end)
