-- Dump the full 256-byte WRAM table at 0xDA00 in the crystal arena (after the
-- clobber at ~cf38) so we can identify what overwrote it. Output /tmp/da00.log
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
local function log(m) local h=io.open("/tmp/da00.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/da00.log","w"); if h then h:write("da00 dump\n");h:close() end end
local TGT=0x0E
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0;local cf=0;local done=false
callbacks:add("frame",function()
 f=f+1
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 if ph=="boot" then emu:setKeys(0)
  if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then fid=fid+1; if fid>30 then ph="t";sub="pre";pf=0 end end
  return end
 if done then return end
 if sub=="pre" then emu:write8(0xFFBA,1);emu:write8(0xDF0C,0);emu:write8(0xDF1D,0);sub="pr";pf=0
 elseif sub=="pr" then emu:setKeys(0x0C);pf=pf+1;if pf>=10 then emu:setKeys(0);sub="rl";pf=0 end
 elseif sub=="rl" then emu:setKeys(0);pf=pf+1;if pf>=10 then sub="w";pf=0 end
 elseif sub=="w" then pf=pf+1
  if emu:read8(0xD880)==TGT then sub="c";cf=0
  elseif pf>400 then at=at+1; if at>=8 then log("giveup");done=true else sub="pre" end end
 elseif sub=="c" then  cf=cf+1
  if cf>=120 then
   for r=0,15 do
     local s=string.format("DA%02X:",r*16)
     for cc=0,15 do s=s..string.format(" %02X",emu:read8(0xDA00+r*16+cc)) end
     log(s)
   end
   log("DONE"); done=true
  end
 end
end)
