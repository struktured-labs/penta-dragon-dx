-- Why is Crystal still red after the bg_table fix? Teleport to crystal (t2),
-- settle, then dump: the ACTIVE WRAM table 0xDA00 for cave+orb tiles, the live
-- VRAM tile+attr for several background cells, and BG CRAM pal0/1/4 colors.
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
local function log(m) local h=io.open("/tmp/cdbg.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/cdbg.log","w"); if h then h:write("crystal dbg\n");h:close() end end
local TGT=0x0E
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0;local done=false
local function isar(d) return d>=0x0C and d<=0x14 end
local function rdbg(p,c) local i=p*8+c*2; emu:write8(0xFF68,i); local lo=emu:read8(0xFF69)
  emu:write8(0xFF68,i+1); local hi=emu:read8(0xFF69); return (hi<<8)|lo end
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
  if emu:read8(0xD880)==TGT then sub="s";pf=0
  elseif pf>400 then at=at+1; if at>=8 then log("giveup");done=true else sub="pre" end end
 elseif sub=="s" then pf=pf+1
  if pf>=100 then
   log("D880=0x"..string.format("%02X",emu:read8(0xD880)).." DF0D(cache)=0x"..string.format("%02X",emu:read8(0xDF0D)))
   log("active table 0xDA00[tile]: A4="..emu:read8(0xDAA4).." B4="..emu:read8(0xDAB4).." C4="..emu:read8(0xDAC4).." 8A="..emu:read8(0xDA8A).." C7="..emu:read8(0xDAC7))
   -- sample a red-background cell region (rows 6-12, cols 5-15) live tile+attr
   for _,rc in ipairs({{8,10},{10,12},{6,6},{12,15},{4,16}}) do
     local r,c=rc[1],rc[2]
     emu:write8(0xFF4F,0); local t=emu:read8(0x9800+r*32+c)
     emu:write8(0xFF4F,1); local a=emu:read8(0x9800+r*32+c)
     emu:write8(0xFF4F,0)
     log(string.format("  cell r%d c%d: tile=0x%02X attr=0x%02X (pal %d) DA00[tile]=%d",r,c,t,a,a&7,emu:read8(0xDA00+t)))
   end
   log(string.format("CRAM BG pal0c1=%04X pal1c1=%04X pal4c1=%04X pal0c0=%04X",rdbg(0,1),rdbg(1,1),rdbg(4,1),rdbg(0,0)))
   log("DONE"); done=true
  end
 end
end)
