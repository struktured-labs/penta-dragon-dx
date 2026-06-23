-- iter 269: dump runtime CRAM OBP idx 3 at fresh boot f=1500
local OUT = os.getenv("OUT") or "tmp/obp_idx3"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then h:close() end
local function log(m) local h=io.open(OUT..".log","a"); if h then h:write(m.."\n"); h:close() end end

local KEY_A=0x01; local KEY_START=0x08; local KEY_DOWN=0x80
callbacks:add("keysRead", function()
  if (f >= 180 and f <= 185) then emu:setKeys(KEY_DOWN)
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
    for pal = 0, 7 do
      log(string.format("OBP%d.3 = 0x%04X", pal, read_cram(true, pal, 3)))
    end
    emu:stop()
  end
end)
