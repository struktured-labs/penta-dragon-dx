-- Trace D880/FFBA/scene-cache/active-table over time in an arena, to see if
-- D880 oscillates (sound-state) and makes scene_detect load the wrong table.
-- Target from /tmp/alt_target.txt. Logs every 10 frames for ~150 frames.
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
local function log(m) local h=io.open("/tmp/ttrace.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/ttrace.log","w"); if h then h:write("table trace\n");h:close() end end
local TARGET=0
do local h=io.open("/tmp/alt_target.txt","r"); if h then local s=h:read("*all"); h:close(); local n=tonumber((s or ""):match("%d")); if n then TARGET=n end end end
local TGT=0x0C+TARGET
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0;local cf=0;local done=false
local seen={}
local function isar(d) return d>=0x0C and d<=0x14 end
callbacks:add("frame",function()
 f=f+1
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 if ph=="boot" then emu:setKeys(0)
  if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then fid=fid+1; if fid>30 then ph="t";sub="pre";pf=0 end end
  return end
 if done then return end
 if sub=="pre" then local pre=TARGET-1; if pre<0 then pre=8 end
  emu:write8(0xFFBA,pre);emu:write8(0xDF0C,0);emu:write8(0xDF1D,0);sub="pr";pf=0
 elseif sub=="pr" then emu:setKeys(0x0C);pf=pf+1;if pf>=10 then emu:setKeys(0);sub="rl";pf=0 end
 elseif sub=="rl" then emu:setKeys(0);pf=pf+1;if pf>=10 then sub="w";pf=0 end
 elseif sub=="w" then pf=pf+1
  if emu:read8(0xD880)==TGT then sub="trace";pf=0;cf=0;log("reached arena f"..f)
  elseif pf>400 then at=at+1; if at>=8 then log("giveup");done=true else sub="pre" end end
 elseif sub=="trace" then
   cf=cf+1
  local d=emu:read8(0xD880)
  seen[d]=(seen[d] or 0)+1
  if cf<=70 then
   log(string.format("cf%d D880=0x%02X DF0D=0x%02X DF02=0x%02X DA00[A4]=%d",
     cf,d,emu:read8(0xDF0D),emu:read8(0xDF02),emu:read8(0xDAA4)))
  end
  if cf>=200 then
    local s="D880 histogram:"; for k,v in pairs(seen) do s=s..string.format(" 0x%02X=%d",k,v) end
    log(s); log("DONE"); done=true
  end
 end
end)
