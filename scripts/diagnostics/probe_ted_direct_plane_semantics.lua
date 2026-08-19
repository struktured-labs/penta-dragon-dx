-- Compare Ted's maintained SVBK4/5 attribute planes with a fresh compiler
-- view of the native packed C1A0 source at every logical publication.
-- Diagnostic only; run through the project single-flight mGBA wrapper.

local OUT = assert(os.getenv("TED_PLANE_OUT"), "TED_PLANE_OUT required")
local WANT = tonumber(os.getenv("TED_PLANE_PUBLICATIONS") or "8")
local MAX_FRAMES = tonumber(os.getenv("TED_PLANE_FRAMES") or "500")
local report = assert(io.open(OUT, "w"))
local frame, publications, finished = 0, 0, false
local selected_bad_total, phase_failures = 0, 0
local plane_writers, source_writers = {[4] = {}, [5] = {}}, {}
local plane_write_count, source_write_count = 0, 0

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

local function finish(requested_status, message)
  if finished then return end
  finished = true
  local status = requested_status
  if status == "pass" and (selected_bad_total ~= 0 or phase_failures ~= 0
      or publications < WANT) then status = "fail" end
  report:write(string.format(
    "summary status=%s frames=%d publications=%d selected_bad_total=%d phase_failures=%d plane_writes=%d source_writes=%d message=%s\n",
    status, frame, publications, selected_bad_total, phase_failures,
    plane_write_count, source_write_count, message or "none"))
  report:flush(); report:close()
  local helper = assert(io.open(OUT .. ".installed-helper.bin", "wb"))
  for address = 0xC500, 0xC55F do
    helper:write(string.char(emu:read8(address)))
  end
  local old_bank = emu:read8(0xFF70) & 7
  for _, bank in ipairs({4, 5}) do
    emu:write8(0xFF70, bank)
    for address = 0xD300, 0xD35F do
      helper:write(string.char(emu:read8(address)))
    end
  end
  emu:write8(0xFF70, old_bank)
  helper:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n"); marker:close()
end

local function bp(address, callback)
  assert(emu:setBreakpoint(callback, address) > 0)
end

-- Record direct-plane writers separately for each bank. Reads performed by
-- this probe do not trigger a WRITE watchpoint.
assert(emu:setRangeWatchpoint(function(info)
  local bank = emu:read8(0xFF70) & 7
  if bank ~= 4 and bank ~= 5 then return end
  local offset = (info.address - 0xD000) & 0xFFFF
  if offset > 0x2FF then return end
  plane_write_count = plane_write_count + 1
  local prior = plane_writers[bank][offset]
  plane_writers[bank][offset] = {
    pc = reg("PC"), frame = frame, count = prior and prior.count + 1 or 1,
    old = info.oldValue & 0xFF, new = info.newValue & 0xFF,
  }
end, 0xD000, 0xD300, C.WATCHPOINT_TYPE.WRITE) > 0)

assert(emu:setRangeWatchpoint(function(info)
  local offset = (info.address - 0xC1A0) & 0xFFFF
  if offset > 0x23F then return end
  source_write_count = source_write_count + 1
  local prior = source_writers[offset]
  source_writers[offset] = {
    pc = reg("PC"), frame = frame, count = prior and prior.count + 1 or 1,
    old = info.oldValue & 0xFF, new = info.newValue & 0xFF,
    rombank = emu:read8(0xFF99), svbk = emu:read8(0xFF70) & 7,
    af = reg("AF"), bc = reg("BC"), de = reg("DE"), hl = reg("HL"),
  }
  if offset == 0x000 or offset == 0x0B1 or offset == 0x0EB then
    local writer = source_writers[offset]
    report:write(string.format(
      "source_event frame=%d logical=%03X address=%04X old=%02X new=%02X pc=%04X rombank=%02X svbk=%d af=%04X bc=%04X de=%04X hl=%04X\n",
      frame, offset, info.address & 0xFFFF, writer.old, writer.new,
      writer.pc, writer.rombank, writer.svbk, writer.af, writer.bc,
      writer.de, writer.hl))
  end
end, 0xC1A0, 0xC3E0, C.WATCHPOINT_TYPE.WRITE) > 0)

local function writer_text(writer)
  if not writer then return "never" end
  local bank = writer.rombank and string.format(",rombank=%02X,svbk=%d",
    writer.rombank, writer.svbk) or ""
  return string.format("pc=%04X,frame=%d,count=%d,old=%02X,new=%02X%s",
    writer.pc, writer.frame, writer.count, writer.old, writer.new, bank)
end

local function compare_bank(bank)
  local old_bank = emu:read8(0xFF70) & 7
  emu:write8(0xFF70, bank)
  local bad, first, details = 0, nil, {}
  for row = 0, 23 do
    for col = 0, 23 do
      local logical = row * 24 + col
      local padded = row * 32 + col
      local tile = emu:read8(0xC1A0 + logical)
      local expected = emu:read8(0xC600 + tile)
      local actual = emu:read8(0xD000 + padded)
      if actual ~= expected then
        bad = bad + 1
        local detail = {
          row=row, col=col, logical=logical, padded=padded,
          tile=tile, expected=expected, actual=actual,
          plane_writer=plane_writers[bank][padded],
          source_writer=source_writers[logical],
        }
        details[#details + 1] = detail
        if not first then first = detail end
      end
    end
  end
  emu:write8(0xFF70, old_bank)
  return bad, first, details
end

local pending = nil

-- $5830 is the first instruction of the hot publication entry. DC0B still
-- owns the pre-toggle selector here. Compile expected attrs from C1A0 and
-- compare both maintained planes before the publisher changes any selector.
bp(0x5830, function()
  if finished or (emu:read8(0xFF99) & 0xFF) ~= 0x0D
      or emu:read8(0xD880) ~= 0x10 then return end
  publications = publications + 1
  local pre = emu:read8(0xDC0B)
  local post = (pre + 1) & 1
  local selected = 4 + post
  local maintained = (pre & 1) ~ 5
  local destination = 0x9C - 4 * post
  local bad4, first4, details4 = compare_bank(4)
  local bad5, first5, details5 = compare_bank(5)
  local selected_bad = selected == 4 and bad4 or bad5
  selected_bad_total = selected_bad_total + selected_bad
  if selected ~= maintained then phase_failures = phase_failures + 1 end
  report:write(string.format(
    "publication=%d frame=%d pre_dc0b=%02X predicted_post=%02X destination_h=%02X selected_svbk=%d maintainer_svbk=%d phase_match=%s selected_bad=%d bank4_bad=%d bank5_bad=%d\n",
    publications, frame, pre, post, destination, selected, maintained,
    tostring(selected == maintained), selected_bad, bad4, bad5))
  for bank, first in pairs({[4]=first4, [5]=first5}) do
    if first then
      report:write(string.format(
        "first_mismatch publication=%d bank=%d row=%d col=%d logical=%03X padded=%03X tile=%02X expected=%02X actual=%02X plane_writer={%s} source_writer={%s}\n",
        publications, bank, first.row, first.col, first.logical,
        first.padded, first.tile, first.expected, first.actual,
        writer_text(first.plane_writer), writer_text(first.source_writer)))
    end
  end
  for bank, details in pairs({[4]=details4, [5]=details5}) do
    for _, detail in ipairs(details) do
      report:write(string.format(
        "mismatch publication=%d bank=%d row=%d col=%d logical=%03X padded=%03X tile=%02X expected=%02X actual=%02X plane_writer={%s} source_writer={%s}\n",
        publications, bank, detail.row, detail.col, detail.logical,
        detail.padded, detail.tile, detail.expected, detail.actual,
        writer_text(detail.plane_writer), writer_text(detail.source_writer)))
    end
  end
  report:flush()
  pending = {publication=publications, pre=pre, post=post,
             selected=selected, destination=destination}
end)

-- Entry $5830 has executed on arrival at $5860. Receipt-lock the actual
-- selector transition and the B register consumed by the bank/map setup.
bp(0x5860, function()
  if finished or not pending or (emu:read8(0xFF99) & 0xFF) ~= 0x0D then return end
  local actual = emu:read8(0xDC0B)
  local b = (reg("BC") >> 8) & 0xFF
  report:write(string.format(
    "selection publication=%d actual_post_dc0b=%02X b=%02X expected_post=%02X transition_ok=%s\n",
    pending.publication, actual, b, pending.post,
    tostring(actual == pending.post and b == pending.post)))
  report:flush()
  pending = nil
  if publications >= WANT then finish("pass", "publication-target") end
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  local svbk = emu:read8(0xFF70) & 7
  if (svbk == 0 or svbk == 1) and emu:read8(0xD880) == 0x10 then
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
  end
  if frame >= MAX_FRAMES then finish("timeout", "frame-limit") end
end)
