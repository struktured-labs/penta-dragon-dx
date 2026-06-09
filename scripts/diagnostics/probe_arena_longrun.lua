-- Long-run arena stability: after settle, collect in WINDOWS and count
-- flip_stable per window (continuous prev-state). A one-time settle shows a
-- high window 1 then ~0 afterwards; STEADY alternation shows sustained nonzero
-- across all windows. Also samples Sara's OBJ palettes each window to confirm
-- the BG-hook neutralize didn't disturb sprite colors.
-- Target from /tmp/alt_target.txt (default 0).
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local OUT="/tmp/longrun.log"
local function log(m) local h=io.open(OUT,"a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT,"w"); if h then h:write("longrun\n");h:close() end end
local TARGET=0
do local h=io.open("/tmp/alt_target.txt","r"); if h then local s=h:read("*all"); h:close()
  local n=tonumber((s or ""):match("%d")); if n then TARGET=n end end end
local TGT=0x0C+TARGET
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local SETTLE=90;local WIN=375;local NWIN=5;local MAXTRY=8
local ptile={};local pattr={};local wflip=0;local win=0;local wf=0
local function isar(d) return d>=0x0C and d<=0x14 end
local function rdobj(p,c) local i=p*8+c*2; emu:write8(0xFF6A,i); local lo=emu:read8(0xFF6B)
  emu:write8(0xFF6A,i+1); local hi=emu:read8(0xFF6B); return (hi<<8)|lo end
local function scan()
  emu:write8(0xFF4F,0); local t={}
  for r=0,17 do for c=0,19 do t[r*20+c]=emu:read8(0x9800+r*32+c) end end
  emu:write8(0xFF4F,1); local a={}
  for r=0,17 do for c=0,19 do a[r*20+c]=emu:read8(0x9800+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  for k=0,359 do
    if ptile[k]~=nil and t[k]==ptile[k] and a[k]~=pattr[k] then wflip=wflip+1 end
    ptile[k]=t[k];pattr[k]=a[k]
  end
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
  elseif pf>=SETTLE then sub="c";win=1;wf=0;wflip=0 end
 elseif sub=="c" then emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
  if not isar(emu:read8(0xD880)) then log("left arena early at win"..win); ph="done"; return end
  scan(); wf=wf+1
  if wf>=WIN then
    log(string.format("WIN %d flip_stable=%d  OBJ0c1=%04X OBJ2c1=%04X OBJ2c2=%04X",
      win, wflip, rdobj(0,1), rdobj(2,1), rdobj(2,2)))
    win=win+1; wf=0; wflip=0
    if win>NWIN then log("DONE"); ph="done" end
  end
 end
end)
