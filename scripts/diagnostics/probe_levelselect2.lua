-- Find + hold the level-select / high-score screen ("STAGE 01 / STAGE LOAD /
-- TOP 3 / 9999 SEC"). PICK=0 -> press A only (top menu option); PICK=1 -> DOWN
-- then A (2nd option). Force DCFD=1. After selecting, HOLD (no input) and log
-- D880 + screenshot until a screen with score text (rows >=7 populated) appears.
local OUT = os.getenv("OUT") or "/tmp/ls2"
local PICK = tonumber(os.getenv("PICK") or "1")
local f, prevd, dumped = 0, -1, false
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("levelselect2 PICK="..PICK.."\n");h:close() end end
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end
local function rowsPopulated()
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local n=0
  for r=7,15 do for c=0,19 do if emu:read8(base+r*32+c)~=0 then n=n+1 end end end
  return n, base
end
local function dumpall(tag)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local t={}; for r=0,17 do t[r]={}; for c=0,19 do t[r][c]=emu:read8(base+r*32+c) end end
  emu:write8(0xFF4F,1); local a={}; for r=0,17 do a[r]={}; for c=0,19 do a[r][c]=emu:read8(base+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  log(tag.." D880="..string.format("%02X",emu:read8(0xD880)).." FFC1="..emu:read8(0xFFC1).." base=0x"..string.format("%04X",base))
  for r=0,17 do local s=""; local pals={}
    for c=0,19 do if t[r][c]~=0 then s=s..string.format("%02X:p%d ",t[r][c],a[r][c]); pals[a[r][c]]=true end end
    if s~="" then local pl=""; for p,_ in pairs(pals) do pl=pl..tostring(p) end log(string.format("  r%02d pals=[%s] %s",r,pl,s)) end
  end
end
callbacks:add("frame", function()
  f = f + 1
  emu:write8(0xDCFD, 0x01)
  local k = 0
  if PICK==1 then k = press(180,186,0x80) | press(210,216,0x01)   -- DOWN then A
  else            k = press(210,216,0x01) end                      -- A only
  emu:setKeys(k)
  local d = emu:read8(0xD880)
  if d ~= prevd then
    emu:screenshot(string.format("%s_d%02X_f%d.png", OUT, d, f))
    log(string.format("f%d D880=%02X FFC1=%d", f, d, emu:read8(0xFFC1)))
    prevd = d
  end
  -- when score rows populate, dump once
  if not dumped and f > 230 then
    local n = rowsPopulated()
    if n >= 10 then dumped=true; emu:screenshot(OUT.."_SCORE.png"); dumpall("SCORESCREEN@f"..f) end
  end
  if f % 60 == 0 and f <= 720 then emu:screenshot(string.format("%s_t%d.png",OUT,f)) end
  if f > 760 then if not dumped then dumpall("noscore-final@f"..f) end log("DONE"); emu:stop() end
end)
