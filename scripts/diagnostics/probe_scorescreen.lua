-- Reproduce the FULL stage-load / high-score screen the user sees ("STAGE 01 /
-- STAGE LOAD / TOP 3 / 1ST 9999 SEC"). It's reached via GAME START when a save
-- exists (DCFD != 0 -> level-select path 0x7393). Force DCFD=1, drive the title
-- START, and log D880 + dump the big "STAGE NN" letter cells' palettes so we
-- learn which scene byte to fix.
local OUT = os.getenv("OUT") or "/tmp/ss"
local f, prevd = 0, -1
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("score screen probe\n");h:close() end end
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end
local function dumpbig(tag)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local t={}; for r=0,17 do t[r]={}; for c=0,19 do t[r][c]=emu:read8(base+r*32+c) end end
  emu:write8(0xFF4F,1); local a={}; for r=0,17 do a[r]={}; for c=0,19 do a[r][c]=emu:read8(base+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  log(tag.." D880="..string.format("%02X",emu:read8(0xD880)).." FFC1="..emu:read8(0xFFC1)
      .." base=0x"..string.format("%04X",base).." DCFD="..string.format("%02X",emu:read8(0xDCFD)))
  for r=0,17 do local s=""; local pals={}
    for c=0,19 do if t[r][c]~=0 then s=s..string.format("%02X:p%d ",t[r][c],a[r][c]); pals[a[r][c]]=true end end
    if s~="" then local pl=""; for p,_ in pairs(pals) do pl=pl..p end log(string.format("  r%02d pals=[%s] %s",r,pl,s)) end
  end
end
callbacks:add("frame", function()
  f = f + 1
  emu:write8(0xDCFD, 0x01)   -- force the level-select / high-score branch on GAME START
  local k = press(180,186,0x80)|press(193,199,0x01)|press(241,247,0x01)|press(291,297,0x01)|press(341,347,0x08)|press(391,397,0x01)
  -- extra A presses to advance any score-screen prompt
  k = k | press(470,476,0x01) | press(560,566,0x01) | press(650,656,0x01)
  emu:setKeys(k)
  local d = emu:read8(0xD880)
  if d ~= prevd then
    emu:screenshot(string.format("%s_d%02X_f%d.png", OUT, d, f))
    log(string.format("f%d D880=%02X FFC1=%d FFBA=%02X DCFD=%02X", f, d, emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xDCFD)))
    prevd = d
  end
  for _,sf in ipairs({430,500,560,620,700}) do
    if f==sf then emu:screenshot(string.format("%s_t%d.png",OUT,f)); dumpbig("snap f"..f) end
  end
  if f > 760 then log("DONE"); emu:stop() end
end)
