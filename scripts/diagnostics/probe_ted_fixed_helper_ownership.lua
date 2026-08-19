-- Prove the proposed C557-C5FE Ted helper range has no runtime owner.
-- Diagnostic only; invoke through the project single-flight wrapper.

local OUT = assert(os.getenv("TED_FIXED_OWNER_OUT"))
local WANT = tonumber(os.getenv("TED_FIXED_OWNER_PUBLICATIONS") or "8")
local MAX_FRAMES = tonumber(os.getenv("TED_FIXED_OWNER_FRAMES") or "600")
local MODE = os.getenv("TED_FIXED_OWNER_MODE") or "snapshot"
local report = assert(io.open(OUT, "w"))
local frame, publications, reads, writes = 0, 0, 0, 0
local finished = false
local events = {}

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

local function record(kind, info)
  if kind == "read" then reads = reads + 1 else writes = writes + 1 end
  if #events < 64 then
    events[#events + 1] = string.format(
      "%s frame=%d address=%04X pc=%04X rombank=%02X svbk=%d old=%02X new=%02X",
      kind, frame, info.address & 0xFFFF, reg("PC"), emu:read8(0xFF99),
      emu:read8(0xFF70) & 7, (info.oldValue or 0) & 0xFF,
      (info.newValue or 0) & 0xFF)
  end
end

local snapshot = {}
for address = 0xC557, 0xC5FE do snapshot[address] = emu:read8(address) end

-- Exercise a fresh Ted install from the known boss fixture, then eight
-- publications. C5FF itself is excluded from the candidate range and remains
-- the installer sentinel.
if os.getenv("TED_FIXED_OWNER_FORCE_COLD") == "1" then
  emu:write8(0xC5FF, 0)
end

emu:setBreakpoint(function()
  if emu:read8(0xD880) ~= 0x10 then return end
  if finished then return end
  publications = publications + 1
  if publications < WANT then return end
  local status = reads == 0 and writes == 0 and "pass" or "fail"
  finished = true
  report:write(string.format(
    "status=%s mode=%s frames=%d publications=%d reads=%d writes=%d\n",
    status, MODE, frame, publications, reads, writes))
  for _, event in ipairs(events) do report:write(event .. "\n") end
  report:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n"); marker:close()
  os.exit(status == "pass" and 0 or 2)
end, 0x028D)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  for address = 0xC557, 0xC5FE do
    local value = emu:read8(address)
    if value ~= snapshot[address] then
      writes = writes + 1
      if #events < 64 then
        events[#events + 1] = string.format(
          "snapshot-change frame=%d address=%04X old=%02X new=%02X",
          frame, address, snapshot[address], value)
      end
      snapshot[address] = value
    end
  end
  if frame < MAX_FRAMES then return end
  finished = true
  report:write(string.format(
    "status=timeout frames=%d publications=%d reads=%d writes=%d\n",
    frame, publications, reads, writes))
  for _, event in ipairs(events) do report:write(event .. "\n") end
  report:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write("timeout\n"); marker:close()
end)
