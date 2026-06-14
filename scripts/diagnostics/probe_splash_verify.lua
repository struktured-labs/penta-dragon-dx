-- Verify the STAGE-intro splash (D880=0x18) now renders uniform (no color bleed)
-- and STAYS uniform through the whole splash hold (cold-boot wipe didn't return).
-- Cold-boot + auto-start, screenshot + attr-dump the big-letter rows at several
-- points while D880=0x18.
local OUT = os.getenv("OUT") or "/tmp/sv"
local f = 0
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("splash verify\n");h:close() end end
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end
local function dumprows(tag)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local t={}; for r=3,7 do t[r]={}; for c=0,19 do t[r][c]=emu:read8(base+r*32+c) end end
  emu:write8(0xFF4F,1); local a={}; for r=3,7 do a[r]={}; for c=0,19 do a[r][c]=emu:read8(base+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  log(tag.." D880="..string.format("%02X",emu:read8(0xD880)).." DF02="..string.format("%02X",emu:read8(0xDF02)))
  for r=3,7 do local s=""; local pals={}
    for c=0,19 do if t[r][c]~=0 then s=s..string.format("%02X:p%d ",t[r][c],a[r][c]); pals[a[r][c]]=true end end
    if s~="" then local pl=""; for p,_ in pairs(pals) do pl=pl..p end log(string.format("  r%02d pals=[%s] %s",r,pl,s)) end
  end
end
callbacks:add("frame", function()
  f = f + 1
  local k = press(180,186,0x80)|press(193,199,0x01)|press(241,247,0x01)|press(291,297,0x01)|press(341,347,0x08)|press(391,397,0x01)
  emu:setKeys(k)
  for _,sf in ipairs({400,460,520,600,700,820}) do
    if f==sf then emu:screenshot(string.format("%s_f%d.png",OUT,f)) end
  end
  if f==460 then dumprows("SPLASH@f460") end
  if f==700 then dumprows("SPLASH@f700 (late — wipe check)") end
  if f>880 then log("DONE"); emu:stop() end
end)
