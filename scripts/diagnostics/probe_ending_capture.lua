-- Reach the victory ending by hijacking the title entry (bank0 0x39C3) with a
-- stub that forces MBC1 to a clean bank 1 then JP 0x54C0 (ending):
--   XOR A; LD[0x6000],A (mode0); LD[0x4000],A (upper=0); LD A,1; LD[0x2100],A; JP 0x54C0
-- The ending sets FFE4=1 (0x54EA) and steps D880 0x19->0x1A->0x16, then renders
-- the graphic at D880=0x00 (0x3DB5) — disambiguate from the title via FFE4.
local OUT = os.getenv("OUT") or "/tmp/ecap"
local f, patched, shots = 0, false, 0
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("ending capture v2\n");h:close() end end

local function patchStub()
  local stub = {0xAF, 0xEA,0x00,0x60, 0xEA,0x00,0x40, 0x3E,0x01, 0xEA,0x00,0x21, 0xC3,0xC0,0x54}
  for i,b in ipairs(stub) do emu.memory.cart0:write8(0x39C3 + (i-1), b) end
end

local function dumpTilemap(tag)
  emu:write8(0xFF4F,0)
  local base = ((emu:read8(0xFF40)&0x08)~=0) and 0x9C00 or 0x9800
  local cnt = {}
  for r=0,17 do for c=0,19 do local t=emu:read8(base+r*32+c); cnt[t]=(cnt[t] or 0)+1 end end
  local arr={}; for k,v in pairs(cnt) do arr[#arr+1]={k,v} end
  table.sort(arr, function(a,b) return a[2]>b[2] end)
  local s=tag.." top tiles:"
  for i=1,math.min(16,#arr) do s=s..string.format(" %02X(%d)",arr[i][1],arr[i][2]) end
  log(s)
end

local prevd = -1
callbacks:add("frame", function()
  f = f + 1
  emu:setKeys(0)
  if f == 30 and not patched then patchStub(); patched = true; log("patched MBC-clean title->ending stub") end
  if not patched then return end
  local d, e4 = emu:read8(0xD880), emu:read8(0xFFE4)
  local ending = (d==0x19 or d==0x1A or d==0x16 or (d==0x00 and e4==1))
  if d ~= prevd then
    log(string.format("f%d D880=%02X FFE4=%d FFC1=%d FFBA=%02X LCDC=%02X%s",
      f, d, e4, emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFF40), ending and "  <<ENDING" or ""))
    prevd = d
  end
  if ending and f % 20 == 0 and shots < 20 then
    shots = shots + 1
    emu:screenshot(string.format("%s_e%02d.png", OUT, shots))
    if shots <= 3 then dumpTilemap("   ending") end
    log(string.format("   shot%d f%d D880=%02X FFE4=%d", shots, f, d, e4))
  end
  if f > 2800 then log("DONE shots="..shots); emu:stop() end
end)
