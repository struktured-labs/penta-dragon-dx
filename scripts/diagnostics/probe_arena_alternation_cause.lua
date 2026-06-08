-- Pin the alternation cause: track specific boss cells' (tile,attr) + D880
-- over time. Distinguishes: attr-lag (tile changes, attr stale), competing
-- writers (tile stable, attr flips), scene thrash (D880 changes).
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local function log(m) local h=io.open("/tmp/alt_cause.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/alt_cause.log","w"); if h then h:write("alt cause\n");h:close() end end
-- watch cells across the boss body
local CELLS={{4,10},{6,10},{8,10},{5,7},{5,13},{10,10}}
local prev={}
local samples=0
local d880_changes=0; local last_d880=-1
local function sample()
  local d=emu:read8(0xD880)
  if d~=last_d880 then d880_changes=d880_changes+1; last_d880=d; log("  D880 -> 0x"..string.format("%02X",d)) end
  emu:write8(0xFF4F,0)
  local tiles={}
  for i,cc in ipairs(CELLS) do tiles[i]=emu:read8(0x9800+cc[1]*32+cc[2]) end
  emu:write8(0xFF4F,1)
  local attrs={}
  for i,cc in ipairs(CELLS) do attrs[i]=emu:read8(0x9800+cc[1]*32+cc[2])&7 end
  emu:write8(0xFF4F,0)
  for i=1,#CELLS do
    local key=string.format("%d,%d", CELLS[i][1], CELLS[i][2])
    local cur=string.format("t=%02X a=%d", tiles[i], attrs[i])
    if prev[key]~=cur then
      -- classify the change
      local tag=""
      if prev[key] then
        local pt,pa=prev[key]:match("t=(%x+) a=(%d)")
        if pt==string.format("%02X",tiles[i]) and tonumber(pa)~=attrs[i] then tag=" <<ATTR-FLIP(tile stable)" end
        if pt~=string.format("%02X",tiles[i]) then tag=" (tile changed)" end
      end
      log(string.format("f%d cell %s: %s%s", f, key, cur, tag))
      prev[key]=cur
    end
  end
  samples=samples+1
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
  elseif sub=="w" then pf=pf+1;emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
   if emu:read8(0xD880)==0x0C then sub="run";pf=0;log("arena reached")
   elseif pf>500 then at=at+1; if at>=8 then ph="done" else sub="pre" end end
  elseif sub=="run" then
   emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF); pf=pf+1
   if pf%2==0 then sample() end
   if pf>=400 then log("d880_changes="..d880_changes.." samples="..samples); log("DONE"); ph="done" end
  end
 end
end)
