-- iter 245: sample DF1F + DF1D + sentinel state per frame for first 60 frames
-- to determine if the colorize gate is actually drained during the lagging window.
local OUT = os.getenv("OUT") or "tmp/df1f_per_frame"
local f = 0
local h = io.open(OUT .. ".log", "w")
if h then h:write("# DF1F per-frame (iter 245)\n"); h:close() end

local function log(msg)
  local h = io.open(OUT .. ".log", "a")
  if h then h:write(msg .. "\n"); h:close() end
end

callbacks:add("frame", function()
  f = f + 1
  if f > 250 then log("DONE"); emu:stop(); return end
  if f < 60 then return end
  if f > 90 and (f % 20) ~= 0 then return end

  local df0c = emu:read8(0xDF0C)  -- debounce
  local df1d = emu:read8(0xDF1D)  -- re-fire sit-out
  local df1f = emu:read8(0xDF1F)  -- colorize-skip
  local df02 = emu:read8(0xDF02)  -- cold-boot sentinel (0x5A = booted)
  local df00 = emu:read8(0xDF00)  -- cond_pal cache
  local hw0  = emu:read8(0xFE03)
  log(string.format("f%d DF0C=%02X DF1D=%02X DF1F=%02X DF02=%02X DF00=%02X | HW0=%02X(p%d)",
    f, df0c, df1d, df1f, df02, df00, hw0, hw0 & 7))
end)
