-- Fail-closed receipt for Ted's selected prepublication tile/attribute plane.
-- Run only through scripts/mgba-headless-singleflight.

local OUT = assert(os.getenv("TED_SANITIZED_OUT"), "TED_SANITIZED_OUT required")
local WANT = tonumber(os.getenv("TED_SANITIZED_PUBLICATIONS") or "4")
local MAX_FRAMES = tonumber(os.getenv("TED_SANITIZED_FRAMES") or "300")
local report = assert(io.open(OUT, "w"))
local frame, publications, failures = 0, 0, {}
local active, selected, writes, epilogues = false, 0, 0, 0
local dumped = false

local sparse = {[0x7B]=true, [0x7D]=true, [0x80]=true,
                [0x82]=true, [0x83]=true, [0x84]=true,
                [0x85]=true, [0x86]=true}
local spans = {
  {0,5}, {-2,6}, {-2,6}, {-2,6}, {-2,6}, {-2,7}, {-3,7},
  {-4,7}, {-4,7}, {-4,7}, {-3,7}, {-2,6}, {0,6}, {1,5},
}

local function fail(message)
  failures[#failures + 1] = string.format("frame=%d %s", frame, message)
end

local function dump_installed()
  if dumped then return end
  dumped = true
  local old = emu:read8(0xFF70) & 7
  local file = assert(io.open(OUT .. ".installed.bin", "wb"))
  for _, bank in ipairs({4, 5}) do
    emu:write8(0xFF70, bank)
    for address = 0xD300, 0xD39A do
      file:write(string.char(emu:read8(address)))
    end
    for address = 0xD500, 0xD578 do
      file:write(string.char(emu:read8(address)))
    end
  end
  emu:write8(0xFF70, old)
  file:close()
end

local function signed(value)
  value = value & 0x1F
  return value >= 16 and value - 32 or value
end

local function check_plane()
  selected = emu:read8(0xFF70) & 7
  if selected ~= 4 and selected ~= 5 then
    fail(string.format("sanitizer exit selected SVBK=%d", selected)); return
  end
  local crowns = {}
  for row = 0, 23 do
    for col = 0, 27 do
      local base = 0xD900 + row * 32 + col
      local match = true
      for offset = 0, 4 do
        if emu:read8(base + offset) ~= 2 + offset then match = false end
      end
      if match then crowns[#crowns + 1] = {row, col} end
    end
  end
  if #crowns ~= 1 then
    fail(string.format("crown count=%d", #crowns)); return
  end
  local crown_row, crown_col = crowns[1][1], crowns[1][2]
  local mismatches = 0
  for row = 0, 23 do
    for col = 0, 31 do
      local offset = row * 32 + col
      local tile = emu:read8(0xD900 + offset)
      local attr = emu:read8(0xD000 + offset)
      local valid = false
      if tile >= 2 and tile <= 0x76 then
        local rr, cc = signed(row - crown_row), signed(col - crown_col)
        if rr >= 0 and rr < 14 then
          valid = cc >= spans[rr + 1][1] and cc < spans[rr + 1][2]
        end
      elseif sparse[tile] then
        valid = true
      end
      if valid then
        if attr == 0 then mismatches = mismatches + 1 end
      elseif tile >= 2 and tile <= 0x7A then
        if tile ~= 0 or attr ~= 0 then mismatches = mismatches + 1 end
      elseif attr ~= 0 then
        mismatches = mismatches + 1
      end
    end
  end
  if mismatches ~= 0 then fail(string.format("geometry mismatches=%d", mismatches)) end
  active, writes, epilogues = true, 0, 0
end

local function bp(address, callback)
  local ok = pcall(function() emu:setBreakpoint(callback, address) end)
  assert(ok, string.format("failed to set breakpoint %04X", address))
end

bp(0x61B0, check_plane)
assert(pcall(function() emu:setRangeWatchpoint(function(info)
  if active and (emu:read8(0xFF70) & 7) == selected then
    writes = writes + 1
  end
end, 0xD000, 0xD300, C.WATCHPOINT_TYPE.WRITE) end))
assert(pcall(function() emu:setRangeWatchpoint(function(info)
  if active and (emu:read8(0xFF70) & 7) == selected then
    writes = writes + 1
  end
end, 0xD900, 0xDC00, C.WATCHPOINT_TYPE.WRITE) end))
bp(0x65D4, function()
  if active then epilogues = epilogues + 1 end
end)
bp(0x0846, function()
  if not active then return end
  if writes ~= 0 then fail(string.format("selected plane mutated during copy writes=%d", writes)) end
  if epilogues ~= 144 then fail(string.format("copy groups=%d expected=144", epilogues)) end
  publications, active = publications + 1, false
  if publications >= WANT then
    local status = #failures == 0 and "pass" or "fail"
    report:write(string.format(
      "status=%s frames=%d publications=%d failures=%d scene=%02X table=%04X phase=%02X\n",
      status, frame, publications, #failures, emu:read8(0xD880),
      (emu:read8(0xDF51) << 8) | emu:read8(0xDF00), emu:read8(0xDF4C)))
    for _, message in ipairs(failures) do report:write("failure " .. message .. "\n") end
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w")); marker:write(status .. "\n"); marker:close()
    emu:stop()
  end
end)

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  dump_installed()
  if frame >= MAX_FRAMES then
    fail("timeout")
    report:write(string.format("status=fail frames=%d publications=%d failures=%d\n",
      frame, publications, #failures))
    for _, message in ipairs(failures) do report:write("failure " .. message .. "\n") end
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w")); marker:write("fail\n"); marker:close()
    emu:stop()
  end
end)
