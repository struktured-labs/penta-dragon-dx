-- iter 268: dump runtime CRAM for BG-pal-0/1/2/5/6 at fresh boot f=1500
local OUT = os.getenv("OUT") or "tmp/bgp_runtime"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then h:close() end
local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

local KEY_A = 0x01; local KEY_START = 0x08; local KEY_DOWN = 0x80
callbacks:add("keysRead", function()
  if     (f >= 180 and f <= 185) then emu:setKeys(KEY_DOWN)
  elseif (f >= 193 and f <= 198) then emu:setKeys(KEY_A)
  elseif (f >= 241 and f <= 246) then emu:setKeys(KEY_A)
  elseif (f >= 291 and f <= 296) then emu:setKeys(KEY_A)
  elseif (f >= 341 and f <= 346) then emu:setKeys(KEY_START)
  elseif (f >= 391 and f <= 396) then emu:setKeys(KEY_A)
  else emu:setKeys(0) end
end)

local function read_cram(is_obj, pal, color)
  local idx_reg = is_obj and 0xFF6A or 0xFF68
  local data_reg = is_obj and 0xFF6B or 0xFF69
  local idx = pal * 8 + color * 2
  emu:write8(idx_reg, idx)
  local lo = emu:read8(data_reg)
  emu:write8(idx_reg, idx + 1)
  local hi = emu:read8(data_reg)
  return (hi << 8) | lo
end

callbacks:add("frame", function()
  f = f + 1
  if f == 1500 then
    for pal in (function() local i=-1; return function() i=i+1; if i<8 then return i end end end)() do
      for c = 0, 3 do
        log(string.format("BGP%d.%d=%04X", pal, c, read_cram(false, pal, c)))
      end
    end
    emu:stop()
  end
end)
