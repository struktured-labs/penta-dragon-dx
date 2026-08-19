-- Trace Ted's first block-major publication without ambiguous banked-ROM
-- breakpoints.  Addresses in $4000-$7FFF are registered only for ROM bank 13;
-- fixed ROM and WRAM sites intentionally omit a segment.
local OUT = assert(os.getenv("TED_FIRST_READY_OUT"))
local FRAME_LIMIT = tonumber(os.getenv("TED_FIRST_READY_FRAMES") or "180")
local report = assert(io.open(OUT, "w"))
local frame, finished = 0, false
local counts = {}

local function reg(name)
  for _, reader in ipairs({
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }) do
    local ok, value = pcall(reader)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function line(kind)
  local stack = ""
  local sp = reg("SP")
  if sp ~= 0xFFFF then
    for offset = 0, 9 do
      stack = stack .. string.format("%02X", emu:read8((sp + offset) & 0xFFFF))
    end
  end
  report:write(string.format(
    "%s frame=%d pc=%04X rom=%02X svbk=%d ready=%02X selector=%02X " ..
    "af=%04X bc=%04X de=%04X hl=%04X sp=%04X ie=%02X lcdc=%02X " ..
    "ly=%02X stat=%02X hdma=%02X%02X%02X%02X%02X scene=%02X stack=%s\n",
    kind, frame, reg("PC"), emu:read8(0xFF99), emu:read8(0xFF70) & 7,
    emu:read8(0xC5FF), emu:read8(0xDC0B), reg("AF"), reg("BC"),
    reg("DE"), reg("HL"), reg("SP"), emu:read8(0xFFFF),
    emu:read8(0xFF40), emu:read8(0xFF44), emu:read8(0xFF41),
    emu:read8(0xFF51), emu:read8(0xFF52), emu:read8(0xFF53),
    emu:read8(0xFF54), emu:read8(0xFF55), emu:read8(0xD880), stack))
  report:flush()
end

local function breakpoint(address, name, segment)
  counts[name] = 0
  local callback = function()
    if finished then return end
    counts[name] = counts[name] + 1
    line(name .. "#" .. counts[name])
  end
  local ok, error_message
  if segment ~= nil then
    ok, error_message = pcall(function()
      return emu:setBreakpoint(callback, address, segment)
    end)
  else
    ok, error_message = pcall(function()
      return emu:setBreakpoint(callback, address)
    end)
  end
  assert(ok, string.format("breakpoint %s failed: %s", name, error_message))
end

-- Fixed ROM publication caller and wrapper.
breakpoint(0x028A, "caller-fixed")
breakpoint(0x0838, "fixed-wrapper")
breakpoint(0x0846, "fixed-wrapper-exit")
-- WRAM cold-ready gate and the post-native-copy continuation.
breakpoint(0xDB80, "cold-ready-wram")
breakpoint(0xDB91, "native-postcopy-wram")
-- Private classifier/byte-worker control flow.  These are WRAM addresses,
-- never bank-qualified ROM breakpoints.
breakpoint(0xD503, "private-classifier-wram")
breakpoint(0xD53B, "private-byte-worker-wram")
breakpoint(0xD56C, "private-byte-worker-unwind-wram")
breakpoint(0xD571, "private-byte-worker-ret-wram")
-- Block-major compiler/publisher sites.  The explicit segment is mandatory.
breakpoint(0x5830, "block-select", 13)
breakpoint(0x7027, "block-gate", 13)
breakpoint(0x5D7F, "block-miss", 13)
breakpoint(0x76BD, "block-private-source", 13)
breakpoint(0x6500, "block-fade-gate", 13)
breakpoint(0x76F4, "renderer-final-dec", 13)
breakpoint(0x76F7, "renderer-final-ret", 13)
breakpoint(0x5D88, "wrapper-tail-unwind", 13)
breakpoint(0x5D8B, "wrapper-tail-ret", 13)
breakpoint(0x61B0, "publication-finish", 13)
breakpoint(0x58C0, "transport-setup", 13)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  if frame == 1 or frame % 8 == 0 or emu:read8(0xC5FF) ~= 0 then
    line("frame")
  end
  -- D880 is banked WRAM.  During the cold installer SVBK intentionally points
  -- at banks 4/5, so reading D880 here does not observe the bank-1 scene byte.
  -- Stop only on the frame budget; a scene-based stop would truncate the
  -- exact first-publication interval this probe exists to diagnose.
  if frame >= FRAME_LIMIT then
    line("finish")
    finished = true
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write("done\n")
    marker:close()
    emu:stop()
  end
end)
