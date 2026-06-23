-- iter 246: sample FFCB per frame to confirm DMA source alternation
local OUT = os.getenv("OUT") or "tmp/ffcb_per_frame"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then h:write("# FFCB per-frame (DMA source toggle) - iter 246\n"); h:close() end
local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

callbacks:add("frame", function()
  f = f + 1
  if f > 250 then log("DONE"); emu:stop(); return end
  if f < 1 then return end
  if f > 70 and (f % 30) ~= 0 then return end

  local ffcb = emu:read8(0xFFCB)
  local ffc1 = emu:read8(0xFFC1)
  local hw0  = emu:read8(0xFE03)
  local hw2  = emu:read8(0xFE0B)
  log(string.format("f%d FFCB=%02X FFC1=%02X | HW0=%02X(p%d) HW2=%02X(p%d)",
    f, ffcb, ffc1, hw0, hw0&7, hw2, hw2&7))
end)
