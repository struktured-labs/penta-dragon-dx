-- Multi-frame capture of a boss arena to tell CRAM cycling (color animation,
-- fine) from a frozen wrong color (bug). Teleports to /tmp/alt_target.txt
-- (default 0), settles, screenshots at 4 spaced frames, and logs BG palettes
-- 3..6 color1 each shot. If colors differ across shots -> the arena cycles
-- CRAM (so a fixed posmap still shows the same animation the hook would).
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local function log(m) local h=io.open("/tmp/multishot.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/multishot.log","w"); if h then h:write("multishot\n");h:close() end end
local TARGET=0
do local h=io.open("/tmp/alt_target.txt","r"); if h then local s=h:read("*all"); h:close()
  local n=tonumber((s or ""):match("%d")); if n then TARGET=n end end end
local TGT=0x0C+TARGET
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0;local shots=0
local SETTLE=90;local MAXTRY=8
local function isar(d) return d>=0x0C and d<=0x14 end
local function rdpal(p,c) local i=p*8+c*2; emu:write8(0xFF68,i); local lo=emu:read8(0xFF69)
  emu:write8(0xFF68,i+1); local hi=emu:read8(0xFF69); return (hi<<8)|lo end
local function shot(n)
  emu:screenshot("/tmp/shot_"..n..".png")
  log(string.format("shot %d: BG3c1=%04X BG4c1=%04X BG5c1=%04X BG6c1=%04X",
    n, rdpal(3,1), rdpal(4,1), rdpal(5,1), rdpal(6,1)))
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
 elseif sub=="c" then emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF); pf=pf+1
  if not isar(emu:read8(0xD880)) then ph="done"; return end
  if pf==2 or pf==24 or pf==48 or pf==72 then shots=shots+1; shot(shots) end
  if pf>=74 then log("DONE"); ph="done" end
 end
end)
