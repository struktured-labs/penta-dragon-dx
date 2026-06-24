-- Inspect orc savestate slot 15 + adjacent slots at multiple frames
local OUT = os.getenv("OUT") or "tmp/orc_slot15"
local f = 0
local h = io.open(OUT .. ".log", "w"); h:write("# orc slot 15 inspect\n"); h:close()
local function log(m) local h = io.open(OUT .. ".log", "a"); h:write(m.."\n"); h:close() end

callbacks:add("frame", function()
  f = f + 1
  if f == 60 or f == 68 or f == 100 or f == 200 then
    log(string.format("f%d:", f))
    for s = 10, 20 do
      local y = emu:read8(0xFE00 + s*4)
      local x = emu:read8(0xFE00 + s*4 + 1)
      local tile = emu:read8(0xFE00 + s*4 + 2)
      local attr = emu:read8(0xFE00 + s*4 + 3)
      log(string.format("  slot%d: y=%d x=%d tile=%02X attr=%02X(pal=%d)", s, y, x, tile, attr, attr & 7))
    end
  end
  if f > 220 then emu:stop() end
end)
