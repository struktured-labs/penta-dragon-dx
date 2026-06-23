-- iter 244 v2: add FFBE state + per-frame counter
local OUT = os.getenv("OUT") or "tmp/slot_attr_trace"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then
  h:write("# slot 0/2 attr trace + FFBE state (iter 244)\n"); h:close()
end

local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

-- Sample frequency: every frame for first 30 frames, then once per 30
callbacks:add("frame", function()
  f = f + 1
  if f > 600 then log("DONE"); emu:stop(); return end
  if f < 60 then return end
  if f > 80 and (f % 30) ~= 0 then return end

  local ffbe = emu:read8(0xFFBE)
  local ffbf = emu:read8(0xFFBF)
  local d880 = emu:read8(0xD880)
  local lcdc = emu:read8(0xFF40)
  local ly   = emu:read8(0xFF44)
  local t0 = emu:read8(0xFE02)
  local a0 = emu:read8(0xFE03)
  local t2 = emu:read8(0xFE0A)
  local a2 = emu:read8(0xFE0B)
  -- Shadow OAM attrs too
  local sh0 = emu:read8(0xC003)
  local sh2 = emu:read8(0xC00B)
  log(string.format("f%d D880=%02X FFBE=%02X FFBF=%02X LCDC=%02X LY=%d | hw_slot0 t=%02X a=%02X(p%d) | hw_slot2 t=%02X a=%02X(p%d) | sh0=%02X sh2=%02X",
    f, d880, ffbe, ffbf, lcdc, ly,
    t0, a0, a0 & 7, t2, a2, a2 & 7, sh0, sh2))
end)
