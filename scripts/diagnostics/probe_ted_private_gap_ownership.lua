-- Snapshot candidate bank-private Ted helper gaps in SVBK4 and SVBK5.
-- Diagnostic only; invoke through the project single-flight wrapper.

local OUT = assert(os.getenv("TED_PRIVATE_GAP_OUT"))
local FRAMES = tonumber(os.getenv("TED_PRIVATE_GAP_FRAMES") or "600")
local report = assert(io.open(OUT, "w"))
local frame, ted_frames, changes = 0, 0, 0
local armed = false
local install_seen = os.getenv("TED_PRIVATE_GAP_POSTINSTALL") == "1"
local crown_transitions = 0
local prior_crown = {[4] = nil, [5] = nil}
local examples = {}
local ranges = {{0xD579, 0xD5FF}, {0xD863, 0xD8FF}}
local function crown_key(bank)
  emu:write8(0xFF70, bank)
  local found = {}
  for row = 0, 23 do
    for col = 0, 27 do
      local address = 0xD900 + row * 32 + col
      local complete = true
      for step = 0, 4 do
        if emu:read8(address + step) ~= 2 + step then
          complete = false; break
        end
      end
      if complete then found[#found + 1] = string.format("%d:%d", row, col) end
    end
  end
  return table.concat(found, ",")
end

for _, range in ipairs(ranges) do
  assert(emu:setRangeWatchpoint(function(info)
    if not armed then return end
    local bank = emu:read8(0xFF70) & 7
    if bank ~= 4 and bank ~= 5 then return end
    changes = changes + 1
    if #examples < 64 then
      examples[#examples + 1] = string.format(
        "write frame=%d bank=%d address=%04X old=%02X new=%02X",
        frame, bank, info.address & 0xFFFF, info.oldValue & 0xFF,
        info.newValue & 0xFF)
    end
  end, range[1], range[2], C.WATCHPOINT_TYPE.WRITE) > 0)
end

emu:setBreakpoint(function()
  if emu:read8(0xD880) == 0x10 then install_seen = true end
end, 0x6FFF)
if os.getenv("TED_PRIVATE_GAP_FORCE_COLD") == "1" then
  emu:write8(0xC5FF, 0)
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  local live_bank = emu:read8(0xFF70) & 7
  if live_bank == 0 or live_bank == 1 then
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
  end
  local ted_ready = emu:read8(0xD880) == 0x10
  if not armed then
    if install_seen and ted_ready then armed = true end
    if frame < 1200 then return end
    report:write(string.format(
      "status=fail reason=no-install-final frames=%d ted_frames=%d\n",
      frame, ted_frames))
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write("fail\n"); marker:close()
    os.exit(2)
  end
  if ted_ready then ted_frames = ted_frames + 1 end
  local saved = emu:read8(0xFF70)
  for _, bank in ipairs({4, 5}) do
    emu:write8(0xFF70, bank)
    if ted_frames % 8 == 0 then
      local current_crown = crown_key(bank)
      if prior_crown[bank] ~= nil and current_crown ~= prior_crown[bank] then
        crown_transitions = crown_transitions + 1
      end
      prior_crown[bank] = current_crown
    end
  end
  emu:write8(0xFF70, saved)
  if ted_frames < FRAMES and frame < 1200 then return end
  local status = ted_frames >= FRAMES and changes == 0
      and crown_transitions > 0 and "pass" or "fail"
  report:write(string.format(
    "status=%s frames=%d ted_frames=%d changes=%d crown_transitions=%d ranges=D579-D5FF,D863-D8FF banks=4,5\n",
    status, frame, ted_frames, changes, crown_transitions))
  for _, event in ipairs(examples) do report:write(event .. "\n") end
  report:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n"); marker:close()
  os.exit(status == "pass" and 0 or 2)
end)
