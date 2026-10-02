-- Attribute every VRAM tilemap write during the native boss-death transition.
--
-- This is a reverse-engineering receipt, not a renderer: it loads an exact
-- ROM-bound boss state, reduces the native HP byte at a fixed frame, and
-- records the stock/DX writer PCs which touch either physical BG map. Run it
-- only through the project single-flight launcher.
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
local native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end

local OUT = assert(os.getenv("DEATH_WRITERS_OUT"),
  "DEATH_WRITERS_OUT is required")
local STATE_FILE = assert(os.getenv("PENTA_STATE_FILE"),
  "PENTA_STATE_FILE is required")
local KILL_FRAME = tonumber(os.getenv("DEATH_KILL_FRAME") or "30")
local MAX_FRAMES = tonumber(os.getenv("DEATH_MAX_FRAMES") or "700")
local HOLD_FRAMES = tonumber(os.getenv("DEATH_HOLD_FRAMES") or "20")

local frame, entered, loaded, finished = 0, -1, false, false
local events, signatures = {}, {}
local MAX_EVENTS = 4096

local function range_hex(first, last)
  local bytes = {}
  for address = first, last do
    bytes[#bytes + 1] = string.format("%02X", emu:read8(address))
  end
  return table.concat(bytes)
end

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

local function finish(status, message)
  if finished then return end
  finished = true
  local report = assert(io.open(OUT, "w"))
  report:write(string.format(
    "summary status=%s message=%s frames=%d entered=%d events=%d " ..
    "scene=%02X bank=%02X\n",
    status, message, frame, entered, #events, emu:read8(0xD880),
    emu:read8(0xFF99)))
  local ordered = {}
  for key, row in pairs(signatures) do
    row.key = key
    ordered[#ordered + 1] = row
  end
  table.sort(ordered, function(a, b)
    if a.first ~= b.first then return a.first < b.first end
    return a.key < b.key
  end)
  for _, row in ipairs(ordered) do
    report:write(string.format(
      "writer=%s count=%d first=%d last=%d min=%04X max=%04X\n",
      row.key, row.count, row.first, row.last, row.min, row.max))
  end
  report:write("source_c1a0=" .. range_hex(0xC1A0, 0xC3DF) .. "\n")
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  report:write("tiles_9800=" .. range_hex(0x9800, 0x9AFF) .. "\n")
  report:write("tiles_9c00=" .. range_hex(0x9C00, 0x9EFF) .. "\n")
  emu:write8(0xFF4F, old_vbk)
  for index, event in ipairs(events) do
    report:write(string.format("event=%04d %s\n", index, event))
  end
  report:close()
  os.exit(status == "ok" and 0 or 2)
end

assert(emu:setRangeWatchpoint(function(info)
  if not loaded or frame < KILL_FRAME or finished then return end
  local address = info.address & 0xFFFF
  local vbk = emu:read8(0xFF4F) & 1
  local pc, bank, scene = reg("PC"), emu:read8(0xFF99), emu:read8(0xD880)
  local key = string.format("bank=%02X pc=%04X vbk=%d scene=%02X",
    bank, pc, vbk, scene)
  local row = signatures[key]
  if row == nil then
    row = {count=0, first=frame, last=frame, min=address, max=address}
    signatures[key] = row
  end
  row.count = row.count + 1
  row.last = frame
  if address < row.min then row.min = address end
  if address > row.max then row.max = address end
  if #events < MAX_EVENTS then
    local sp = reg("SP")
    local ret = emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8)
    events[#events + 1] = string.format(
      "frame=%d age=%d scene=%02X bank=%02X pc=%04X vbk=%d " ..
      "address=%04X old=%02X new=%02X af=%04X bc=%04X de=%04X hl=%04X " ..
      "sp=%04X ret=%04X",
      frame, entered < 0 and -1 or frame - entered, scene, bank, pc, vbk,
      address, (info.oldValue or 0) & 0xFF, (info.newValue or 0) & 0xFF,
      reg("AF"), reg("BC"), reg("DE"), reg("HL"), sp, ret)
  end
end, 0x9800, 0xA000, C.WATCHPOINT_TYPE.WRITE) > 0)

callbacks:add("frame", function()
  if finished then return end
  if not loaded then
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_FILE)
    end)
    assert(ok and result ~= false, "failed to load requested boss state")
    loaded = true
    return
  end
  frame = frame + 1
  emu:setKeys(0)
  if frame == KILL_FRAME then native_assistance.write(0xDCBB, 0) end
  if entered < 0 and emu:read8(0xD880) == 0x17 then entered = frame end
  if entered >= 0 and frame - entered >= HOLD_FRAMES then
    finish("ok", "death-art-hold-observed")
  elseif frame >= MAX_FRAMES then
    finish("timeout", "death-scene-not-observed")
  end
end)
