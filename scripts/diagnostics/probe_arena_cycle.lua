-- In-session re-entry test: teleport to bosses 0..8 IN ONE PROCESS (pre-set
-- FFBA + pulse combo, the proven method), returning to the dungeon between
-- each. Confirms the position sweep's lazy expand + flag logic carry NO stale
-- state across repeated arena<->dungeon transitions (each entry must re-expand
-- the correct posmap). Screenshots /tmp/cycle_<idx>.png per boss.
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local function log(m) local h=io.open("/tmp/cycle.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/cycle.log","w"); if h then h:write("cycle\n");h:close() end end
local NAMES={[0]="shalamar","riff","crystal","cameo","ted","troop","faze","angela","penta"}
local f=0;local ph="boot";local sub="pre";local pf=0;local fid=0;local idx=0;local at=0
local SETTLE=60;local MAXTRY=8
local function isar(d) return d>=0x0C and d<=0x14 end
local function holdhp() emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF) end
callbacks:add("frame",function()
 f=f+1
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 if ph=="boot" then emu:setKeys(0)
  if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then fid=fid+1; if fid>30 then ph="cyc";sub="pre";pf=0 end end
  return end
 if ph=="done" then return end
 holdhp()
 if sub=="pre" then
  local pre=idx-1; if pre<0 then pre=8 end
  emu:write8(0xFFBA,pre); emu:write8(0xDF0C,0); emu:write8(0xDF1D,0)
  sub="pr"; pf=0
 elseif sub=="pr" then emu:setKeys(0x0C);pf=pf+1;if pf>=10 then emu:setKeys(0);sub="rl";pf=0 end
 elseif sub=="rl" then emu:setKeys(0);pf=pf+1;if pf>=10 then sub="wa";pf=0 end
 elseif sub=="wa" then
  pf=pf+1
  if emu:read8(0xD880)==(0x0C+idx) then sub="settle";pf=0
  elseif pf>400 then at=at+1; if at>=MAXTRY then log(string.format("idx %d (%s) MISSED",idx,NAMES[idx])); idx=idx+1;at=0; if idx>=9 then log("DONE");ph="done" else sub="pre";pf=0 end else sub="pre";pf=0 end end
 elseif sub=="settle" then
  pf=pf+1
  if not isar(emu:read8(0xD880)) then sub="wa";pf=0
  elseif pf>=SETTLE then
    emu:screenshot("/tmp/cycle_"..idx..".png")
    log(string.format("idx %d: D880=0x%02X (%s) FFBA=%d OK", idx, emu:read8(0xD880), NAMES[idx], emu:read8(0xFFBA)))
    at=0; sub="wd"; pf=0
  end
 elseif sub=="wd" then
  pf=pf+1
  if emu:read8(0xD880)==0x02 then idx=idx+1; if idx>=9 then log("DONE");ph="done" else sub="pre";pf=0 end
  elseif pf>300 then idx=idx+1; if idx>=9 then log("DONE");ph="done" else sub="pre";pf=0 end end
 end
end)
