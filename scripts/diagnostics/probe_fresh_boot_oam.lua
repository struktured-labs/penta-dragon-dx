-- iter 244: cold-boot + auto-input + sample slot 0/2 attrs at f=1500
-- to verify DF1F transient drain during real boot doesn't leak into stage 1.
local OUT = os.getenv("OUT") or "tmp/fresh_boot_oam"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then h:write("# fresh-boot OAM sampling (iter 244)\n"); h:close() end

local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

-- Title-menu sequence per MEMORY.md:
-- DOWN(180-185) -> A(193-198) -> A(241-246) -> A(291-296) -> START(341-346) -> A(391-396)
local KEY_A = 0x01
local KEY_START = 0x08
local KEY_DOWN = 0x80

callbacks:add("keysRead", function()
  if     (f >= 180 and f <= 185) then emu:setKeys(KEY_DOWN)
  elseif (f >= 193 and f <= 198) then emu:setKeys(KEY_A)
  elseif (f >= 241 and f <= 246) then emu:setKeys(KEY_A)
  elseif (f >= 291 and f <= 296) then emu:setKeys(KEY_A)
  elseif (f >= 341 and f <= 346) then emu:setKeys(KEY_START)
  elseif (f >= 391 and f <= 396) then emu:setKeys(KEY_A)
  else emu:setKeys(0) end
end)

callbacks:add("frame", function()
  f = f + 1
  if f > 2000 then log("DONE"); emu:stop(); return end

  if (f == 500) or (f == 1000) or (f == 1500) or (f == 1800) or (f == 2000) then
    local d880 = emu:read8(0xD880)
    local ffbe = emu:read8(0xFFBE)
    local ffc1 = emu:read8(0xFFC1)
    local df1f = emu:read8(0xDF1F)
    local t0 = emu:read8(0xFE02); local a0 = emu:read8(0xFE03)
    local t2 = emu:read8(0xFE0A); local a2 = emu:read8(0xFE0B)
    log(string.format("f%d D880=%02X FFBE=%02X FFC1=%d DF1F=%02X | hw_slot0 t=%02X a=%02X(p%d) | hw_slot2 t=%02X a=%02X(p%d)",
      f, d880, ffbe, ffc1, df1f, t0, a0, a0 & 7, t2, a2, a2 & 7))
  end
end)
