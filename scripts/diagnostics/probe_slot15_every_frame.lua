-- Sample slot 15 attr every frame from f=60 to f=300
local OUT = os.getenv("OUT") or "tmp/slot15_every"
local f = 0
local h = io.open(OUT .. ".log", "w"); h:close()
local function log(m) local h = io.open(OUT .. ".log", "a"); h:write(m.."\n"); h:close() end
local prev_pal = -1
local change_count = 0
callbacks:add("frame", function()
  f = f + 1
  if f < 60 then return end
  if f > 600 then
    log(string.format("DONE changes=%d", change_count))
    emu:stop(); return
  end
  local attr = emu:read8(0xFE3F)
  local pal = attr & 7
  if pal ~= prev_pal then
    log(string.format("f%d slot15 attr=%02X(pal=%d)", f, attr, pal))
    if prev_pal >= 0 then change_count = change_count + 1 end
    prev_pal = pal
  end
end)
