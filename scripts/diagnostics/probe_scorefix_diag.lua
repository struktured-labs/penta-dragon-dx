-- Score-screen bleed diagnostic. Reach the level-select score screen (DCFD=1,
-- DOWN+A, hold). Log the attr-cleaner sentinels (DF08/DF07) + a known p1 letter
-- cell's attr each frame. At f290 MANUALLY clear the whole attr plane to 0 and
-- screenshot/dump — if that yields uniform p0, the bleed is stale attrs (cleaner
-- approach valid, trigger is the problem); if it stays mixed, an active writer
-- is setting p1.
local OUT = os.getenv("OUT") or "/tmp/sfd"
local f, prevd = 0, -1
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("scorefix diag\n");h:close() end end
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end
local function attrAt(base,r,c) emu:write8(0xFF4F,1); local v=emu:read8(base+r*32+c)&7; emu:write8(0xFF4F,0); return v end
local function clearAttrs()
  emu:write8(0xFF4F,1)
  for a=0x9800,0x9FFF do emu:write8(a,0) end
  emu:write8(0xFF4F,0)
end
local function dumpbig(tag)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  emu:write8(0xFF4F,0); local t={}; for r=0,13 do t[r]={}; for c=0,19 do t[r][c]=emu:read8(base+r*32+c) end end
  emu:write8(0xFF4F,1); local at={}; for r=0,13 do at[r]={}; for c=0,19 do at[r][c]=emu:read8(base+r*32+c)&7 end end
  emu:write8(0xFF4F,0)
  log(tag)
  for r=0,13 do local s=""; local pals={}
    for c=0,19 do if t[r][c]~=0 then s=s..string.format("%02X:p%d ",t[r][c],at[r][c]); pals[at[r][c]]=true end end
    if s~="" then local pl=""; for p,_ in pairs(pals) do pl=pl..tostring(p) end log(string.format("  r%02d pals=[%s] %s",r,pl,s)) end
  end
end
callbacks:add("frame", function()
  f = f + 1
  emu:write8(0xDCFD, 0x01)
  emu:setKeys(press(180,186,0x80) | press(210,216,0x01))
  local d = emu:read8(0xD880)
  if d ~= prevd then log(string.format("f%d D880=%02X DF23(prev)=?", f, d)); prevd=d end
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  if f>=214 and f<=300 and f%6==0 then
    log(string.format("f%d D880=%02X DF08=%02X DF07=%02X attr(r5c4)=%d attr(r7c4)=%d",
      f, d, emu:read8(0xDF08), emu:read8(0xDF07), attrAt(base,5,4), attrAt(base,7,4)))
  end
  if f==288 then dumpbig("BEFORE manual clear @f288") end
  if f==290 then clearAttrs(); log("MANUAL attr clear @f290") end
  if f==294 then dumpbig("AFTER manual clear @f294"); emu:screenshot(OUT.."_cleared.png") end
  if f>320 then log("DONE"); emu:stop() end
end)
