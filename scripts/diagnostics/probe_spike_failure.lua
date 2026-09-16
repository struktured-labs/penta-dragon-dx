-- Read-only inspection of the operator-captured post-spike failure.
local out = assert(os.getenv("SPIKE_DEBUG_OUT"))
local state = assert(os.getenv("SPIKE_DEBUG_STATE"))
local f = assert(io.open(out .. "/trace.tsv", "w"))
local loaded, frame = false, 0
local counts = {}
for _, addr in ipairs(os.getenv("SPIKE_DEBUG_REARM") == "1"
    and {0xDF0D, 0xFF93, 0xFF69} or {0xDF0D, 0xFF91, 0xFF93, 0xFF69}) do
  counts[addr] = 0
  emu:setWatchpoint(function(info)
    if loaded then
      counts[addr] = counts[addr] + 1
      if counts[addr] <= 20 then
        f:write(string.format("write %04X pc=%04X bank=%02X value=%02X\n",
          addr, emu:readRegister("PC"), emu:read8(0xFF99), info.newValue or info.value or 0))
      end
    end
  end, addr, C.WATCHPOINT_TYPE.WRITE)
end
callbacks:add("frame", function()
  if not loaded then
    assert(emu:loadStateFile(state) ~= false)
    loaded = true
    return
  end
  frame = frame + 1
  if frame == 60 and os.getenv("SPIKE_DEBUG_REARM") == "1" then
    -- Diagnostic intervention only, never used as passing ROM evidence.
    emu:write8(0xFF91, 1)
  end
  if frame % 30 == 0 then
    f:write(string.format("frame=%d pc=%04X scene=%02X cache=%02X flag=%02X bank=%02X\n",
      frame, emu:readRegister("PC"), emu.memory.wram:read8(0x1880),
      emu.memory.wram:read8(0x1F0D), emu:read8(0xFF91), emu:read8(0xFF99)))
    f:flush()
  end
  if frame == 300 then
    emu:screenshot(out .. "/after.png")
    emu:saveStateFile(out .. "/after.ss0")
    for addr, count in pairs(counts) do f:write(string.format("count %04X %d\n", addr, count)) end
    f:close()
    os.exit(0)
  end
end)
