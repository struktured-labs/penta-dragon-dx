-- Authoritative palette test: cold-boot the ROM (no save state, no level-select
-- hack), run the documented auto-start sequence into the real stage-1 dungeon,
-- then dump all 8 live BG palettes. This is the ground truth for what the ROM's
-- colorizer actually loads into CRAM in genuine gameplay.
local OUT = os.getenv("OUT") or "/tmp/bg5_cold"
local f, done = 0, false
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n");h:close() end end
do local h=io.open(OUT..".log","w"); if h then h:write("bg5 coldboot\n");h:close() end end
local function rdbg(p,c) local i=p*8+c*2; emu:write8(0xFF68,i); local lo=emu:read8(0xFF69)
  emu:write8(0xFF68,i+1); local hi=emu:read8(0xFF69); return (hi<<8)|lo end
-- key bitmask: A=0x01 START=0x08 DOWN=0x80 RIGHT=0x10
local function press(lo,hi,mask) return (f>=lo and f<hi) and mask or 0 end
callbacks:add("frame", function()
  if done then return end
  f = f + 1
  -- documented auto-start sequence (DX ROM): DOWN, A, A, A, START, A
  local k = 0
  k = k | press(180,186, 0x80)   -- DOWN
  k = k | press(193,199, 0x01)   -- A
  k = k | press(241,247, 0x01)   -- A
  k = k | press(291,297, 0x01)   -- A
  k = k | press(341,347, 0x08)   -- START
  k = k | press(391,397, 0x01)   -- A
  -- after start, STAND STILL (no input) so the dungeon renders stably.
  emu:setKeys(k)
  -- burst of screenshots to find a stable colored frame
  for _,sf in ipairs({480,520,560,600,640,680}) do
    if f == sf then
      emu:screenshot(string.format("%s_%d.png", OUT, sf))
      log(string.format("shot f%d D880=%02X FFC1=%d FFBA=%02X pal0c1=%04X pal5c1=%04X",
        f, emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBA), rdbg(0,1), rdbg(5,1)))
    end
  end
  if f == 720 then done = true; log("DONE"); emu:stop() end
end)
