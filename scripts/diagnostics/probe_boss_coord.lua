-- Find a WRAM byte that tracks Shalamar's vertical bob. Each frame log
-- candidate coords + the boss's actual visual top row (min row of boss tiles).
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local function log(m) local h=io.open("/tmp/bosscoord.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/bosscoord.log","w"); if h then h:write("bosscoord\n");h:close() end end
-- candidate coord addresses (X/Y from arena docs + scroll + entity slots)
local CAND={0xDD85,0xDD86,0xDD87,0xDD88,0xFF42,0xFF43,0xDC00,0xDC01,0xC201,0xC200}
local function toprow()
  emu:write8(0xFF4F,0)
  for r=0,17 do for c=0,19 do if emu:read8(0x9800+r*32+c)>0x01 then return r end end end
  return 99
end
local samples=0
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
  elseif sub=="w" then pf=pf+1;emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
   if emu:read8(0xD880)==0x0C then sub="run";pf=0
   elseif pf>500 then at=at+1; if at>=8 then ph="done" else sub="pre" end end
  elseif sub=="run" then
   emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF); pf=pf+1
   if pf%10==0 then
     local tr=toprow()
     local vals={}
     for _,a in ipairs(CAND) do vals[#vals+1]=string.format("%04X=%02X",a,emu:read8(a)) end
     log(string.format("top=%d  %s", tr, table.concat(vals," ")))
     samples=samples+1
   end
   if pf>=400 then log("DONE"); ph="done" end
  end
 end
end)
