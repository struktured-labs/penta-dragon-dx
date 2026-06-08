-- Diagnose Shalamar: (1) capture time-series to catch color alternation,
-- (2) flag tile IDs that appear in BOTH boss-core rows and outer/bg rows.
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local function log(m) local h=io.open("/tmp/shal_diag.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/shal_diag.log","w"); if h then h:write("shal diag\n");h:close() end end
local shots=0
local seen_attr={}  -- tile_id -> set of palette attrs observed over time (catch alternation)
local function snapshot()
  emu:write8(0xFF4F,0)
  local tg={}
  for r=0,17 do tg[r]={}; for c=0,19 do tg[r][c]=emu:read8(0x9800+r*32+c) end end
  emu:write8(0xFF4F,1)
  for r=0,17 do for c=0,19 do
    local t=tg[r][c]
    if t>0x01 then local a=emu:read8(0x9800+r*32+c)&7; seen_attr[t]=seen_attr[t] or {}; seen_attr[t][a]=true end
  end end
  emu:write8(0xFF4F,0)
end
local function dump()
  emu:write8(0xFF4F,0)
  local D880=emu:read8(0xD880); local FFBA=emu:read8(0xFFBA)
  log(string.format("D880=0x%02X FFBA=%d", D880, FFBA))
  -- tiles seen with MORE THAN ONE palette over time = alternating
  local alt=0
  for t,set in pairs(seen_attr) do
    local n=0; local ps={}; for p,_ in pairs(set) do n=n+1; ps[#ps+1]=p end
    if n>1 then alt=alt+1; table.sort(ps); log(string.format("ALT tile 0x%02X -> pals %s", t, table.concat(ps,","))) end
  end
  log("alternating tiles: "..alt)
end
callbacks:add("frame",function()
 f=f+1
 if f<=500 then local k=0;for _,e in ipairs(TITLE) do if f>=e[1] and f<=e[2] then k=e[3];break end end;emu:setKeys(k);return end
 if ph=="boot" then emu:setKeys(0)
  if emu:read8(0xD880)==0x02 and emu:read8(0xFFC1)==1 then fid=fid+1; if fid>30 then ph="t";sub="pre";pf=0 end end
  return end
 if ph=="t" then
  if sub=="pre" then emu:write8(0xFFBA,8);emu:write8(0xDF0C,0);emu:write8(0xDF1D,0);sub="pr";pf=0  -- DX Shalamar
  elseif sub=="pr" then emu:setKeys(0x0C);pf=pf+1;if pf>=10 then emu:setKeys(0);sub="rl";pf=0 end
  elseif sub=="rl" then emu:setKeys(0);pf=pf+1;if pf>=10 then sub="w";pf=0 end
  elseif sub=="w" then pf=pf+1;emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
   if emu:read8(0xD880)==0x0C then sub="run";pf=0
   elseif pf>500 then at=at+1; if at>=8 then ph="done" else sub="pre" end end
  elseif sub=="run" then
   emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF); pf=pf+1
   if emu:read8(0xD880)==0x0C then
     if pf%4==0 then snapshot() end  -- sample attrs over time
     if pf==80 then emu:screenshot("/tmp/shal_t1.png") end
     if pf==200 then emu:screenshot("/tmp/shal_t2.png") end
     if pf==340 then emu:screenshot("/tmp/shal_t3.png") end
     if pf==480 then emu:screenshot("/tmp/shal_t4.png"); dump(); log("DONE"); ph="done" end
   end
  end
 end
end)
