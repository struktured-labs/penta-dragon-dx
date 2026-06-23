-- iter 245: sample BOTH shadow OAM blocks (0xC003 + 0xC103) + HW OAM
-- at every frame for 60 frames after savestate load, to determine if
-- there's a double-buffer source race causing HW OAM to lag.
local OUT = os.getenv("OUT") or "tmp/double_buffer"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then
  h:write("# double-buffer probe (iter 245)\n")
  h:write("# col: frame HW0 SH0_A SH0_B HW2 SH2_A SH2_B\n")
  h:close()
end

local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

callbacks:add("frame", function()
  f = f + 1
  if f > 250 then log("DONE"); emu:stop(); return end
  if f < 60 then return end
  if f > 80 and (f % 10) ~= 0 then return end

  local hw0  = emu:read8(0xFE03)
  local sh0a = emu:read8(0xC003)
  local sh0b = emu:read8(0xC103)
  local hw2  = emu:read8(0xFE0B)
  local sh2a = emu:read8(0xC00B)
  local sh2b = emu:read8(0xC10B)
  log(string.format("f%d HW0=%02X(p%d) SH0_A=%02X(p%d) SH0_B=%02X(p%d) | HW2=%02X(p%d) SH2_A=%02X(p%d) SH2_B=%02X(p%d)",
    f, hw0, hw0&7, sh0a, sh0a&7, sh0b, sh0b&7,
       hw2, hw2&7, sh2a, sh2a&7, sh2b, sh2b&7))
end)
