-- Build a STATIC CELL-INDEXED footprint map for an arena (Letta plan).
-- Over the animation cycle, for each of the 18x20 visible cells, record how
-- often it's "boss" (tile>0x01) and its mean row. A cell that's boss in >=40%
-- of frames is part of the stable footprint; its palette = position band by
-- mean row of the whole footprint. Emits a per-cell PYGRID for the ROM map.
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local function log(m) local h=io.open("/tmp/footprint.log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open("/tmp/footprint.log","w"); if h then h:write("footprint\n");h:close() end end
local boss_cnt={}  -- [r*32+c] = frames-as-boss
local frames=0; local COLLECT=240
for i=0,17*32+31 do boss_cnt[i]=0 end
local function collect()
  emu:write8(0xFF4F,0)
  for r=0,17 do for c=0,19 do if emu:read8(0x9800+r*32+c)>0x01 then boss_cnt[r*32+c]=boss_cnt[r*32+c]+1 end end end
  frames=frames+1
end
local function emit()
  local thr=frames*0.40
  -- footprint rows present -> min/max for banding
  local minr,maxr=99,-1
  for r=0,17 do for c=0,19 do if boss_cnt[r*32+c]>=thr then if r<minr then minr=r end; if r>maxr then maxr=r end end end end
  if maxr<minr then log("NO FOOTPRINT"); return end
  local span=maxr-minr; if span<1 then span=1 end
  local PAL={4,6,5,3}
  log(string.format("footprint rows %d..%d frames=%d", minr, maxr, frames))
  -- emit 18 rows x 20 cols of palette digits (0=bg)
  for r=0,17 do
    local s=""
    for c=0,19 do
      local p=0
      if boss_cnt[r*32+c]>=thr then local q=math.floor((r-minr)*4/(span+1)); if q>3 then q=3 end; if q<0 then q=0 end; p=PAL[q+1] end
      s=s..p
    end
    log("ROW "..r.." "..s)
  end
  log("DONE")
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
   if emu:read8(0xD880)==0x0C then sub="run";pf=0
   elseif pf>500 then at=at+1; if at>=8 then ph="done" else sub="pre" end end
  elseif sub=="run" then
   emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF); pf=pf+1
   if emu:read8(0xD880)==0x0C then collect(); if frames>=COLLECT then emit(); ph="done" end end
  end
 end
end)
