-- Prove ownership of the two proposed Ted attribute-cache planes.
local OUT = assert(os.getenv("TED_CACHE_PLANES_OUT"))
local FRAMES = tonumber(os.getenv("TED_CACHE_PLANES_FRAMES") or "2800")
local SCENE = 0x10
local frame, finished = 0, false
local counts, read_counts, examples = {[2] = 0, [3] = 0}, {[2] = 0, [3] = 0}, {}
local owners, readers = {}, {}

local function register(name)
  for _, accessor in ipairs({
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }) do
    local ok, value = pcall(accessor)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

assert(emu:setRangeWatchpoint(function(info)
  local bank = emu:read8(0xFF70) & 7
  if counts[bank] == nil or emu:read8(0xD880) ~= SCENE then return end
  counts[bank] = counts[bank] + 1
  local pc = register("PC")
  local key = string.format("%d:%04X", bank, pc)
  owners[key] = (owners[key] or 0) + 1
  if #examples < 32 then
    examples[#examples + 1] = string.format(
      "frame=%d bank=%d address=%04X pc=%04X old=%02X new=%02X",
      frame, bank, info.address & 0xFFFF, register("PC"),
      info.oldValue & 0xFF, info.newValue & 0xFF)
  end
end, 0xD000, 0xD305, C.WATCHPOINT_TYPE.WRITE) > 0)

assert(emu:setRangeWatchpoint(function(info)
  local bank = emu:read8(0xFF70) & 7
  if read_counts[bank] == nil or emu:read8(0xD880) ~= SCENE then return end
  read_counts[bank] = read_counts[bank] + 1
  local pc = register("PC")
  local key = string.format("%d:%04X", bank, pc)
  readers[key] = (readers[key] or 0) + 1
  if #examples < 32 then
    examples[#examples + 1] = string.format(
      "read frame=%d bank=%d address=%04X pc=%04X value=%02X",
      frame, bank, info.address & 0xFFFF, pc, info.oldValue & 0xFF)
  end
end, 0xD000, 0xD305, C.WATCHPOINT_TYPE.READ) > 0)

local function finish(status)
  if finished then return end
  finished = true
  local out = assert(io.open(OUT, "w"))
  out:write(string.format(
    "status=%s frames=%d bank2=%d bank3=%d read2=%d read3=%d\n",
    status, frame, counts[2], counts[3], read_counts[2], read_counts[3]))
  local keys = {}
  for key, _ in pairs(owners) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do
    out:write(string.format("owner=%s count=%d\n", key, owners[key]))
  end
  keys = {}
  for key, _ in pairs(readers) do keys[#keys + 1] = key end
  table.sort(keys)
  for _, key in ipairs(keys) do
    out:write(string.format("reader=%s count=%d\n", key, readers[key]))
  end
  for _, line in ipairs(examples) do out:write(line .. "\n") end
  out:close()
  local done = assert(io.open(OUT .. ".done", "w"))
  done:write(status .. "\n"); done:close()
  emu:stop()
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  if emu:read8(0xD880) ~= SCENE then finish("wrong-scene"); return end
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCDD, 0xFF)
  emu:write8(0xD888, 0)
  emu:write8(0xDD06, 0)
  if frame >= FRAMES then finish("ok") end
end)
