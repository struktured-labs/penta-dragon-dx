-- Short fail-closed trace for the bank-13/16 native BG palette far route.

local OUT = assert(os.getenv("PALETTE_TRACE_OUT"))
local KEY_A, KEY_START, KEY_DOWN = 0x01, 0x08, 0x80
local frame, events, stopped = 0, 0, false

local function reg(name)
  local readers = {
    function() return emu:readRegister(string.lower(name)) end,
    function() return emu:readRegister(string.upper(name)) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:getRegister(string.upper(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function record(label)
  if events >= 256 then return end
  events = events + 1
  local sp = reg("sp")
  local words = {}
  for offset = 0, 10, 2 do
    words[#words + 1] = string.format(
      "%04X", emu:read8((sp + offset) & 0xFFFF) |
      (emu:read8((sp + offset + 1) & 0xFFFF) << 8))
  end
  local handle = assert(io.open(OUT, "a"))
  handle:write(string.format(
    "%s\tf=%d\tpc=%04X\taf=%04X\tbc=%04X\tde=%04X\thl=%04X\tsp=%04X" ..
    "\tff99=%02X\tdc09=%02X\tlcdc=%02X\tstat=%02X\tly=%02X\tif=%02X" ..
    "\tie=%02X\tstack=%s\n",
    label, frame, reg("pc"), reg("af"), reg("bc"), reg("de"), reg("hl"),
    sp, emu:read8(0xFF99), emu:read8(0xDC09), emu:read8(0xFF40),
    emu:read8(0xFF41), emu:read8(0xFF44), emu:read8(0xFF0F),
    emu:read8(0xFFFF), table.concat(words, ",")))
  handle:close()
end

local function breakpoint(label, address, bank)
  assert(emu:setBreakpoint(function() record(label) end, address, bank) > 0)
end

local initial = assert(io.open(OUT, "w"))
initial:write("schema=penta-palette-router-trace-v1\n")
initial:close()

for _, row in ipairs({
  {"source13-hook", 0x71DB, 13},
  {"source16-hook", 0x71DB, 16},
  {"guard-native", 0x7A59, 20},
  {"router", 0x7320, 20},
  {"router-di", 0x7326, 20},
  {"router-vblank-check", 0x7327, 20},
  {"router-masked-route", 0x733D, 20},
  {"router-unmasked-route", 0x7345, 20},
  {"router-switch", 0x734B, 20},
  {"source13-masked", 0x71E3, 13},
  {"source16-masked", 0x71E3, 16},
  {"source13-unmasked", 0x71F4, 13},
  {"source16-unmasked", 0x71F4, 16},
}) do
  breakpoint(row[1], row[2], row[3])
end

local function keys()
  local schedule = {
    {180, 185, KEY_DOWN}, {201, 206, KEY_A}, {261, 266, KEY_A},
    {321, 326, KEY_A}, {381, 386, KEY_START}, {431, 436, KEY_A},
  }
  for _, row in ipairs(schedule) do
    if frame >= row[1] and frame <= row[2] then return row[3] end
  end
  return 0
end

callbacks:add("frame", function()
  if stopped then return end
  frame = frame + 1
  emu:setKeys(keys())
  if frame <= 10 or frame % 60 == 0 then record("frame") end
  if frame >= 720 then
    record("done")
    stopped = true
    os.exit(0)
  end
end)
