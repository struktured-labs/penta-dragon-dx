-- #73: screenshot the Ted Select menu on every frame 1-300 and dump C4E0.
local out = assert(os.getenv("TED_SELECT_OUT"))
local n = 0
local function dump_c4e0(tag)
  local f = assert(io.open(string.format("%s/c4e0_%s.bin", out, tag), "wb"))
  for i=0,119 do
    f:write(string.char(emu:read8(0xC4E0 + i)))
  end
  f:close()
end
local log = assert(io.open(out .. "/events.jsonl", "w"))
callbacks:add("frame", function()
  n = n + 1
  if n >= 8 and n < 14 then emu:setKeys(0x04) else emu:setKeys(0) end
  emu:screenshot(string.format("%s/frame-%04d.png", out, n))
  if n == 70 or n == 300 then
    dump_c4e0(string.format("f%04d", n))
  end
  if n == 1 or n == 70 or n == 300 then
    local lcdc = emu:read8(0xFF40)
    log:write(string.format('{"frame":%d,"lcdc":%d}\n', n, lcdc))
    log:flush()
  end
  if n >= 300 then log:close(); os.exit(0) end
end)
