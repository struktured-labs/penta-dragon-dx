-- Generate a position map by capturing the MODAL palette the (good) tile-ID
-- colorizer assigns each cell over the boss animation. Run this on a
-- HOOK-ACTIVE ROM (e.g. the Phase-0 teleport build): the inline hook writes
-- attr = arena_table[tile] every animation frame, so per cell the most common
-- attr is the color that cell "should" be. Freezing that per cell gives the
-- same look with ZERO alternation (every write of a cell writes one value).
--
-- Output (append) in footprint_maps.log format so the build's parser is reused:
--   ROW <name> <r> <20 modal-palette digits>
-- Floor/background cells resolve to 0 naturally (their modal attr is 0).
--
-- Target boss from /tmp/alt_target.txt (default 0). Reads the ACTIVE tilemap
-- (0x9800/0x9C00 per LCDC bit 3).
local TITLE={{180,185,0x80},{193,198,0x01},{241,246,0x01},{291,296,0x01},{341,346,0x08},{391,396,0x01}}
local OUT="/tmp/posmap_gen.log"
local function log(m) local h=io.open(OUT,"a"); if h then h:write(m.."\n");h:close() end end
local TARGET=0
do local h=io.open("/tmp/alt_target.txt","r"); if h then local s=h:read("*all"); h:close()
  local n=tonumber((s or ""):match("%d")); if n then TARGET=n end end end
local NAMES={[0]="shalamar","riff","crystal_dragon","cameo","ted","troop","faze","angela","penta_dragon"}
local NAME=NAMES[TARGET] or ("boss"..TARGET)
local TGT=0x0C+TARGET
local f=0;local ph="boot";local sub;local pf=0;local fid=0;local at=0
local SETTLE=90;local COLLECT=180;local MAXTRY=8
local hist={};local frames=0
local function isar(d) return d>=0x0C and d<=0x14 end
local function base() local l=emu:read8(0xFF40); if (l&0x08)~=0 then return 0x9C00 else return 0x9800 end end
local function collect()
  local b=base(); emu:write8(0xFF4F,1)
  for r=0,17 do for c=0,19 do
    local k=r*20+c; local a=emu:read8(b+r*32+c)&7
    hist[k]=hist[k] or {0,0,0,0,0,0,0,0}; hist[k][a+1]=hist[k][a+1]+1
  end end
  emu:write8(0xFF4F,0)
  frames=frames+1
end
local function emit()
  log(string.format("ARENA %s rows 0..17 frames=%d (modal-attr posmap)",NAME,frames))
  -- Generous coverage: a cell takes its dominant NON-ZERO palette if it is
  -- boss-colored in >= 25% of frames (catches limbs that sweep through), else
  -- 0 (background). Pure-modal under-covers moving limbs (a swept cell is
  -- floor most frames -> picks 0 -> uncolored limb).
  for r=0,17 do
    local s=""
    for c=0,19 do
      local k=r*20+c; local bi=0
      local h=hist[k]
      if h then
        local nz=0; for a=1,7 do nz=nz+h[a+1] end       -- frames cell was non-zero
        if nz*4 >= frames then                           -- >= 25% of frames
          local best=0; for a=1,7 do if h[a+1]>best then best=h[a+1];bi=a end end
        end
      end
      s=s..tostring(bi)
    end
    log(string.format("ROW %s %d %s",NAME,r,s))
  end
  log("DONE "..NAME)
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
  elseif pf>400 then at=at+1; if at>=MAXTRY then log("giveup "..NAME);ph="done" else sub="pre" end end
 elseif sub=="s" then pf=pf+1;emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
  if not isar(emu:read8(0xD880)) then at=at+1; if at>=MAXTRY then ph="done" else sub="pre";pf=0 end
  elseif pf>=SETTLE then sub="c";pf=0 end
 elseif sub=="c" then emu:write8(0xDCDC,0xFF);emu:write8(0xDCDD,0xFF)
  if isar(emu:read8(0xD880)) then collect(); if frames>=COLLECT then emit();ph="done" end
  else if frames>30 then emit() end; ph="done" end
 end
end)
