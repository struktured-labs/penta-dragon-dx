-- Prove the Ted-only in-window GDMA route without changing game timing.
-- Run only through the project single-flight mGBA wrapper.

local OUT = assert(os.getenv("TED_INWINDOW_OUT"), "TED_INWINDOW_OUT required")
local MAX_FRAMES = tonumber(os.getenv("TED_INWINDOW_FRAMES") or "400")
local WANT_HOT = tonumber(os.getenv("TED_INWINDOW_PUBLICATIONS") or "4")
local STATE_OUT = os.getenv("TED_INWINDOW_STATE_OUT")
local FORCE_COLD = os.getenv("TED_INWINDOW_FORCE_COLD") == "1"
local report = assert(io.open(OUT, "w"))
local frame, failures, hot = 0, {}, 0
local forced_cold = false
local active, cold_active, cold_return_pending = false, false, false
local cold = {gate=false, postcopy=false, toggle=false, native=false,
              lazy=false, install=false, finish=false, returned=false}
local current = nil
local interrupt_entries = 0

local function reg(name)
  local readers = {
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function bank13()
  return (emu:read8(0xFF99) & 0xFF) == 0x0D
end

local function fail(message)
  failures[#failures + 1] = string.format("frame=%d %s", frame, message)
end

local function check_native(label, expected_sp)
  local af, bc, de, hl, sp = reg("AF"), reg("BC"), reg("DE"), reg("HL"), reg("SP")
  local good_hl = hl == 0x9B00 or hl == 0x9F00
  if af ~= 0x01C0 or bc ~= 0x0008 or de ~= 0xC3E0
      or not good_hl or sp ~= expected_sp then
    fail(string.format(
      "%s ABI af=%04X bc=%04X de=%04X hl=%04X sp=%04X expected_sp=%04X",
      label, af, bc, de, hl, sp, expected_sp))
  end
end

local function compare_plane(target, source_bank)
  local old_svbk, old_vbk = emu:read8(0xFF70), emu:read8(0xFF4F)
  local source = {}
  emu:write8(0xFF70, source_bank)
  for offset = 0, 0x2FF do source[offset] = emu:read8(0xD000 + offset) end
  emu:write8(0xFF4F, 1)
  local mismatch = 0
  for offset = 0, 0x2FF do
    if emu:read8(target + offset) ~= source[offset] then mismatch = mismatch + 1 end
  end
  emu:write8(0xFF4F, old_vbk & 1)
  emu:write8(0xFF70, old_svbk & 7)
  return mismatch
end

local function finish()
  local cold_ok = true
  for _, value in pairs(cold) do cold_ok = cold_ok and value end
  local status = #failures == 0 and cold_ok and hot >= WANT_HOT
      and interrupt_entries > 0 and "pass" or "fail"
  report:write(string.format(
    "status=%s frames=%d hot_publications=%d interrupts=%d failures=%d\n",
    status, frame, hot, interrupt_entries, #failures))
  report:write(string.format(
    "cold gate=%s postcopy=%s toggle=%s native=%s lazy=%s install=%s finish=%s returned=%s\n",
    tostring(cold.gate), tostring(cold.postcopy), tostring(cold.toggle),
    tostring(cold.native), tostring(cold.lazy), tostring(cold.install),
    tostring(cold.finish), tostring(cold.returned)))
  for _, message in ipairs(failures) do report:write("failure " .. message .. "\n") end
  report:close()
  if STATE_OUT and STATE_OUT ~= "" then emu:saveStateFile(STATE_OUT) end
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

local function bp(address, callback)
  pcall(function() emu:setBreakpoint(callback, address) end)
end

bp(0xDB80, function()
  if emu:read8(0xD880) ~= 0x10 then return end
  if emu:read8(0xC5FF) == 0 then
    cold.gate, cold_active, cold_return_pending = true, true, true
  end
end)
bp(0xDB91, function() if cold_active then cold.postcopy = true end end)
bp(0x4295, function() if cold_active then cold.toggle = true end end)
bp(0x42A7, function() if cold_active then cold.native = true end end)
bp(0x6290, function()
  if bank13() and cold_active then cold.lazy = true end
end)
bp(0x5340, function()
  if bank13() and cold_active then cold.install = true end
end)
bp(0x6FFF, function()
  if bank13() and cold_active then cold.finish = true end
end)
bp(0x028D, function()
  if cold_return_pending then
    cold.returned, cold_active, cold_return_pending = true, false, false
    check_native("cold-return", 0xDFF9)
  end
end)

bp(0x5830, function()
  if not bank13() or emu:read8(0xD880) ~= 0x10 then return end
  active = true
  current = {waits=0, groups=0, starts=0, completes=0, restored=0,
             source_bank=0, target=0, data_mismatches=0}
end)
bp(0x5E5C, function()
  if bank13() and active and current then current.waits = current.waits + 1 end
end)
bp(0x578C, function()
  if bank13() and active and current then current.groups = current.groups + 1 end
end)
bp(0x5795, function()
  if not bank13() or not active or not current then return end
  current.starts = current.starts + 1
  local mode = emu:read8(0xFF41) & 3
  if mode ~= 0 then fail(string.format("GDMA start %d mode=%d", current.starts, mode)) end
  local index = current.starts - 1
  local source = ((emu:read8(0xFF51) << 8) | (emu:read8(0xFF52) & 0xF0))
  local target = 0x8000 | ((emu:read8(0xFF53) & 0x1F) << 8)
      | (emu:read8(0xFF54) & 0xF0)
  if source ~= 0xD000 + 0x10 * index then
    fail(string.format("GDMA source %d=%04X", current.starts, source))
  end
  if index == 0 then current.target = target end
  if target ~= current.target + 0x10 * index then
    fail(string.format("GDMA target %d=%04X base=%04X", current.starts, target, current.target))
  end
  current.source_bank = emu:read8(0xFF70) & 7
  if current.source_bank ~= 4 and current.source_bank ~= 5 then
    fail(string.format("GDMA source bank=%d", current.source_bank))
  end
  if (emu:read8(0xFF4F) & 1) ~= 1 then fail("GDMA did not target VBK1") end
end)
bp(0x5797, function()
  if not bank13() or not active or not current then return end
  local index = current.completes
  current.completes = current.completes + 1
  if emu:read8(0xFF55) ~= 0xFF then fail("GDMA incomplete after FF55 write") end
  for byte = 0, 15 do
    if emu:read8(0xD000 + index * 16 + byte)
        ~= emu:read8(current.target + index * 16 + byte) then
      current.data_mismatches = current.data_mismatches + 1
    end
  end
end)
local function check_pre_ei()
  if not bank13() or not active or not current then return end
  current.restored = current.restored + 1
  if (emu:read8(0xFF70) & 7) ~= 1 or (emu:read8(0xFF4F) & 1) ~= 0
      or emu:read8(0xFF55) ~= 0xFF then
    fail(string.format("pre-EI state svbk=%02X vbk=%02X ff55=%02X",
      emu:read8(0xFF70), emu:read8(0xFF4F), emu:read8(0xFF55)))
  end
end
bp(0x65D8, check_pre_ei)
bp(0x0846, function()
  if not active or not current then return end
  check_native("hot-fixed-exit", 0xDFF7)
  if current.groups ~= 144 or current.starts ~= 48
      or current.completes ~= 48 or current.restored ~= 144 then
    fail(string.format("publication counts waits=%d groups=%d starts=%d completes=%d restored=%d",
      current.waits, current.groups, current.starts, current.completes,
      current.restored))
  end
  if current.data_mismatches ~= 0 then
    fail(string.format("attribute block mismatches=%d", current.data_mismatches))
  end
  hot, active, current = hot + 1, false, nil
  if hot >= WANT_HOT then finish() end
end)

for _, vector in ipairs({0x0040, 0x0048, 0x0050, 0x0058, 0x0060}) do
  bp(vector, function()
    if not active then return end
    interrupt_entries = interrupt_entries + 1
    if (emu:read8(0xFF70) & 7) ~= 1 or (emu:read8(0xFF4F) & 1) ~= 0
        or emu:read8(0xFF55) ~= 0xFF then
      fail(string.format("interrupt %04X svbk=%02X vbk=%02X ff55=%02X",
        vector, emu:read8(0xFF70), emu:read8(0xFF4F), emu:read8(0xFF55)))
    end
  end)
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  if FORCE_COLD and not forced_cold then
    -- A qualified Ted state may contain the preceding candidate's volatile
    -- private helpers.  Clear only the architecture readiness sentinel; the
    -- next native publication must traverse and reinstall the complete cold
    -- path in both banks before this receipt can pass.
    emu:write8(0xC5FF, 0)
    forced_cold = true
  end
  local svbk = emu:read8(0xFF70) & 7
  if (svbk == 0 or svbk == 1) and emu:read8(0xD880) == 0x10 then
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
  end
  if frame >= MAX_FRAMES then
    fail("timeout")
    finish()
  end
end)
