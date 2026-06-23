-- iter 246: track FFC1 per frame — gates the DMA in combined handler
local OUT = os.getenv("OUT") or "tmp/ffc1_per_frame"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then h:write("# FFC1 per-frame (iter 246) — DMA gate\n"); h:close() end
local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

callbacks:add("frame", function()
  f = f + 1
  if f > 250 then log("DONE"); emu:stop(); return end
  if f < 60 then return end
  if f > 90 and (f % 20) ~= 0 then return end

  local ffc1 = emu:read8(0xFFC1)
  local ffc0 = emu:read8(0xFFC0)
  local hw0  = emu:read8(0xFE03)
  local hw2  = emu:read8(0xFE0B)
  log(string.format("f%d FFC1=%02X FFC0=%02X | HW0=%02X(p%d) HW2=%02X(p%d)",
    f, ffc1, ffc0, hw0, hw0&7, hw2, hw2&7))
end)
