-- Prove the natural Stage-1 death/Continue CHR reload transaction.
--
-- The Python verifier supplies a freshly generated, candidate-bound Stage-1
-- state.  This probe performs exactly one gameplay-memory stimulus
-- (DCBB := 0), holds neutral controller input throughout, and observes the
-- native bank1:$4AF2 -> $4AFB -> fixed:$0C9C -> bank1:$4AFE route.  It never
-- repairs selectors, CHR, scene state, or any other gameplay byte.
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

local OUT = assert(os.getenv("PENTA_DEATH_RELOAD_OUT"))
local STATE_FILE = assert(os.getenv("PENTA_DEATH_RELOAD_STATE"))
local CANONICAL_FILE = assert(os.getenv("PENTA_DEATH_RELOAD_CANONICAL"))
local STARTUP_TOKEN = assert(os.getenv("PENTA_DEATH_RELOAD_STARTUP_TOKEN"))
local EXPECTED_ROM_SHA256 = assert(
  os.getenv("PENTA_DEATH_RELOAD_ROM_SHA256"))
local FRAME_LIMIT = tonumber(
  os.getenv("PENTA_DEATH_RELOAD_FRAME_LIMIT") or "1800")
local STIMULUS_FRAME = tonumber(
  os.getenv("PENTA_DEATH_RELOAD_STIMULUS_FRAME") or "30")
local POSTRETURN_FRAMES = tonumber(
  os.getenv("PENTA_DEATH_RELOAD_POSTRETURN_FRAMES") or "60")

local NATURAL_SELECTORS = "1011121314151617"
local PAGE_FIRST = 0x9000
local PAGE_LAST = 0x97FF
local PAGE_BYTES = 0x0800
local MAX_CHR_EVENTS = 8192
local CGB_ONLY_HEADER = 0xC0

local canonical_handle = assert(io.open(CANONICAL_FILE, "rb"))
local canonical = assert(canonical_handle:read("*a"))
canonical_handle:close()
assert(#canonical == PAGE_BYTES, "canonical Stage-1 CHR must be 0x800 bytes")
assert(emu:read8(0x0143) == CGB_ONLY_HEADER,
  "death/Continue reload gate requires a CGB-only candidate")

local frame = 0
local state_loaded = false
local preflight_done = false
local stimulus_written = false
local finished = false
local raw_vram = nil
local failure_reason = nil
local returned_frame = nil
local loader_active = false
local loader_entries = 0
local stimulus_writes = 0
local selector_watch_writes = 0
local selector_frame_violations = 0
local serial_sc_busy_samples = 0
local serial_ie_enabled_samples = 0
local preflight_mismatches = -1
local final_mismatches = -1
local chr_event_count = 0
local chr_event_dropped = 0
local preloader_write_count = 0
local loader_write_count = 0
local postreturn_write_count = 0
local postreturn_bad_write_count = 0
local death_scene_frames = 0
local route_events = {}
local last_sample = ""

local route_handle = assert(io.open(OUT .. "/route.tsv", "w"))
local chr_handle = assert(io.open(OUT .. "/chr-writes.tsv", "w"))
local selector_handle = assert(io.open(OUT .. "/selector-writes.tsv", "w"))
local state_handle = assert(io.open(OUT .. "/latch-serial-trace.tsv", "w"))
route_handle:write(
  "index\tframe\tkind\tpc\tbank\tsp\tret\tselectors\tffda\t" ..
  "ff01\tff72\tff73\tff74\tsc\tie\n")
chr_handle:write(
  "index\tphase\tframe\taddress\told\tnew\tpc\tbank\taf\tbc\tde\t" ..
  "hl\tsp\tcaller\tselectors\tff01\tff72\tff73\tff74\tsc\tie\tffda\n")
selector_handle:write(
  "index\tframe\taddress\told\tnew\tpc\tbank\tselectors\n")
state_handle:write(
  "frame\treason\tselectors\tff01\tff72\tff73\tff74\tsc\tie\t" ..
  "ffda\tscene\tactive\tlcdc\tvbk\tsvbk\n")

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

local function word(address)
  return emu:read8(address & 0xFFFF)
    | (emu:read8((address + 1) & 0xFFFF) << 8)
end

local function selectors_hex()
  local bytes = {}
  for address = 0xFFA4, 0xFFAB do
    bytes[#bytes + 1] = string.format("%02X", emu:read8(address))
  end
  return table.concat(bytes)
end

local function sample_fields()
  return {
    selectors = selectors_hex(),
    ff01 = emu:read8(0xFF01),
    ff72 = emu:read8(0xFF72),
    ff73 = emu:read8(0xFF73),
    ff74 = emu:read8(0xFF74),
    sc = emu:read8(0xFF02),
    ie = emu:read8(0xFFFF),
    ffda = emu:read8(0xFFDA),
  }
end

local function fail(reason)
  if failure_reason == nil then failure_reason = reason end
end

local function serial_and_selector_guard(fields)
  if fields.selectors ~= NATURAL_SELECTORS then
    selector_frame_violations = selector_frame_violations + 1
    fail("selector-invariant-violated")
  end
  if (fields.sc & 0x80) ~= 0 then
    serial_sc_busy_samples = serial_sc_busy_samples + 1
    fail("serial-transfer-active")
  end
  if (fields.ie & 0x08) ~= 0 then
    serial_ie_enabled_samples = serial_ie_enabled_samples + 1
    fail("serial-interrupt-enabled")
  end
end

local function trace_state(reason, force)
  local fields = sample_fields()
  serial_and_selector_guard(fields)
  local value = string.format(
    "%s:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X:%02X",
    fields.selectors, fields.ff01, fields.ff72, fields.ff73, fields.ff74,
    fields.sc, fields.ie, fields.ffda, emu:read8(0xD880),
    emu:read8(0xFFC1), emu:read8(0xFF40), emu:read8(0xFF4F),
    emu:read8(0xFF70), emu:read8(0xDCBB))
  if force or value ~= last_sample then
    state_handle:write(string.format(
      "%d\t%s\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
      "%02X\t%02X\t%02X\t%02X\t%02X\n",
      frame, reason, fields.selectors, fields.ff01, fields.ff72,
      fields.ff73, fields.ff74, fields.sc, fields.ie, fields.ffda,
      emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFF40),
      emu:read8(0xFF4F), emu:read8(0xFF70)))
    state_handle:flush()
    last_sample = value
  end
  return fields
end

local function canonical_byte(address)
  return canonical:byte(address - PAGE_FIRST + 1)
end

local function bank0_mismatches()
  assert(raw_vram ~= nil, "bank-zero VRAM accessor is unavailable")
  local mismatches = 0
  for address = PAGE_FIRST, PAGE_LAST do
    if raw_vram:read8(address - 0x8000) ~= canonical_byte(address) then
      mismatches = mismatches + 1
    end
  end
  return mismatches
end

local function dump_bank0(path)
  local handle = assert(io.open(path, "wb"))
  for address = PAGE_FIRST, PAGE_LAST do
    handle:write(string.char(raw_vram:read8(address - 0x8000)))
  end
  handle:close()
end

local function record_route(kind, expected_pc)
  local fields = sample_fields()
  serial_and_selector_guard(fields)
  local pc = reg("PC")
  local sp = reg("SP")
  route_events[#route_events + 1] = kind
  route_handle:write(string.format(
    "%d\t%d\t%s\t%04X\t%02X\t%04X\t%04X\t%s\t%02X\t%02X\t" ..
    "%02X\t%02X\t%02X\t%02X\t%02X\n",
    #route_events, frame, kind, pc, emu:read8(0xFF99), sp, word(sp),
    fields.selectors, fields.ffda, fields.ff01, fields.ff72, fields.ff73,
    fields.ff74, fields.sc, fields.ie))
  route_handle:flush()
  if pc ~= expected_pc then fail("route-pc-mismatch") end
  if emu:read8(0xFF99) ~= 0x01 then fail("route-bank-mismatch") end
  if fields.ffda ~= 0 then fail("route-ffda-nonzero") end
end

local function route_is(expected)
  if #route_events ~= #expected then return false end
  for index, value in ipairs(expected) do
    if route_events[index] ~= value then return false end
  end
  return true
end

local function install_route_breakpoint(address, kind)
  assert(emu:setBreakpoint(function()
    if not stimulus_written or finished then return end
    if emu:read8(0xFF99) ~= 0x01 and address >= 0x4000 then return end
    if kind == "continue-check-4AF2" then
      if #route_events ~= 0 then fail("duplicate-continue-check") end
      record_route(kind, 0x4AF2)
    elseif kind == "continue-call-4AFB" then
      if not route_is({"continue-check-4AF2"}) then
        fail("continue-call-without-check")
      end
      record_route(kind, 0x4AFB)
      if reg("SP") ~= 0xDFFF then fail("continue-call-stack-not-reset") end
    elseif kind == "selector-loader-0C9C" then
      loader_entries = loader_entries + 1
      if loader_entries ~= 1
          or not route_is({
            "continue-check-4AF2", "continue-call-4AFB"
          }) then
        fail("selector-loader-has-foreign-root")
      end
      record_route(kind, 0x0C9C)
      if reg("SP") ~= 0xDFFD or word(reg("SP")) ~= 0x4AFE then
        fail("selector-loader-return-root-mismatch")
      end
      loader_active = true
    elseif kind == "continue-return-4AFE" then
      if not loader_active
          or not route_is({
            "continue-check-4AF2", "continue-call-4AFB",
            "selector-loader-0C9C"
          }) then
        fail("continue-return-without-loader")
      end
      if loader_write_count ~= PAGE_BYTES then
        fail("continue-return-before-complete-loader")
      end
      record_route(kind, 0x4AFE)
      if reg("SP") ~= 0xDFFF then fail("continue-return-stack-mismatch") end
      loader_active = false
      returned_frame = frame
      trace_state("continue-return", true)
    end
  end, address) > 0)
end

install_route_breakpoint(0x4AF2, "continue-check-4AF2")
install_route_breakpoint(0x4AFB, "continue-call-4AFB")
install_route_breakpoint(0x0C9C, "selector-loader-0C9C")
install_route_breakpoint(0x4AFE, "continue-return-4AFE")

local function record_chr_write(info)
  if not stimulus_written or finished then return end
  if (emu:read8(0xFF4F) & 0x01) ~= 0 then return end
  chr_event_count = chr_event_count + 1
  local phase = "preloader"
  if loader_active then
    phase = "loader"
    loader_write_count = loader_write_count + 1
  elseif returned_frame ~= nil then
    phase = "postreturn"
    postreturn_write_count = postreturn_write_count + 1
    if (info.newValue & 0xFF) ~= canonical_byte(info.address & 0xFFFF) then
      postreturn_bad_write_count = postreturn_bad_write_count + 1
      fail("noncanonical-postreturn-chr-write")
    end
  else
    preloader_write_count = preloader_write_count + 1
  end
  local fields = sample_fields()
  serial_and_selector_guard(fields)
  if chr_event_count > MAX_CHR_EVENTS then
    chr_event_dropped = chr_event_dropped + 1
    fail("chr-event-buffer-overflow")
    return
  end
  local sp = reg("SP")
  chr_handle:write(string.format(
    "%d\t%s\t%d\t%04X\t%02X\t%02X\t%04X\t%02X\t%04X\t%04X\t" ..
    "%04X\t%04X\t%04X\t%04X\t%s\t%02X\t%02X\t%02X\t%02X\t" ..
    "%02X\t%02X\t%02X\n",
    chr_event_count, phase, frame, info.address & 0xFFFF,
    info.oldValue & 0xFF, info.newValue & 0xFF, reg("PC"),
    emu:read8(0xFF99), reg("AF"), reg("BC"), reg("DE"), reg("HL"),
    sp, word((sp + 4) & 0xFFFF), fields.selectors, fields.ff01,
    fields.ff72, fields.ff73, fields.ff74, fields.sc, fields.ie,
    fields.ffda))
  chr_handle:flush()
end

-- mGBA's range end is exclusive.  Keep $97FF on its own exact watchpoint.
assert(emu:setRangeWatchpoint(function(info)
  record_chr_write(info)
end, PAGE_FIRST, PAGE_LAST, C.WATCHPOINT_TYPE.WRITE) > 0)
assert(emu:setWatchpoint(function(info)
  record_chr_write(info)
end, PAGE_LAST, C.WATCHPOINT_TYPE.WRITE) > 0)

for address = 0xFFA4, 0xFFAB do
  local selector_address = address
  assert(emu:setWatchpoint(function(info)
    if not preflight_done or finished then return end
    selector_watch_writes = selector_watch_writes + 1
    selector_handle:write(string.format(
      "%d\t%d\t%04X\t%02X\t%02X\t%04X\t%02X\t%s\n",
      selector_watch_writes, frame, selector_address,
      info.oldValue & 0xFF, info.newValue & 0xFF, reg("PC"),
      emu:read8(0xFF99), selectors_hex()))
    selector_handle:flush()
    fail("native-selector-array-was-written")
  end, selector_address, C.WATCHPOINT_TYPE.WRITE) > 0)
end

local function close_traces()
  route_handle:close()
  chr_handle:close()
  selector_handle:close()
  state_handle:close()
end

local function finish(status, reason)
  if finished then return end
  finished = true
  emu:setKeys(0)
  if raw_vram ~= nil then
    final_mismatches = bank0_mismatches()
    dump_bank0(OUT .. "/final-bank0-9000-97ff.bin")
  end
  if status == "pass" then
    if failure_reason ~= nil then
      status, reason = "fail", failure_reason
    elseif not route_is({
      "continue-check-4AF2", "continue-call-4AFB",
      "selector-loader-0C9C", "continue-return-4AFE"
    }) then
      status, reason = "fail", "incomplete-continue-route"
    elseif loader_entries ~= 1 or loader_write_count ~= PAGE_BYTES then
      status, reason = "fail", "incomplete-selector-loader"
    elseif final_mismatches ~= 0 then
      status, reason = "fail", "final-chr-not-canonical"
    end
  end
  close_traces()
  local temporary = OUT .. "/report.txt.tmp"
  local report = assert(io.open(temporary, "w"))
  report:write("schema=penta-stage1-death-continue-chr-reload-probe-v1\n")
  report:write("status=" .. status .. "\n")
  report:write("reason=" .. reason .. "\n")
  report:write("startup_token=" .. STARTUP_TOKEN .. "\n")
  report:write("expected_rom_sha256=" .. EXPECTED_ROM_SHA256 .. "\n")
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format("state_loaded=%d\n", state_loaded and 1 or 0))
  report:write(string.format("preflight_done=%d\n", preflight_done and 1 or 0))
  report:write(string.format("stimulus_writes=%d\n", stimulus_writes))
  report:write(string.format("stimulus_frame=%d\n", STIMULUS_FRAME))
  report:write(string.format("loader_entries=%d\n", loader_entries))
  report:write(string.format("route_event_count=%d\n", #route_events))
  report:write("route_events=" .. table.concat(route_events, ",") .. "\n")
  report:write(string.format("chr_event_count=%d\n", chr_event_count))
  report:write(string.format("chr_event_dropped=%d\n", chr_event_dropped))
  report:write(string.format("preloader_write_count=%d\n", preloader_write_count))
  report:write(string.format("loader_write_count=%d\n", loader_write_count))
  report:write(string.format("postreturn_write_count=%d\n", postreturn_write_count))
  report:write(string.format(
    "postreturn_bad_write_count=%d\n", postreturn_bad_write_count))
  report:write(string.format("selector_watch_writes=%d\n", selector_watch_writes))
  report:write(string.format(
    "selector_frame_violations=%d\n", selector_frame_violations))
  report:write(string.format("serial_sc_busy_samples=%d\n", serial_sc_busy_samples))
  report:write(string.format(
    "serial_ie_enabled_samples=%d\n", serial_ie_enabled_samples))
  report:write(string.format("preflight_mismatches=%d\n", preflight_mismatches))
  report:write(string.format("final_mismatches=%d\n", final_mismatches))
  report:write(string.format("death_scene_frames=%d\n", death_scene_frames))
  report:write("final_selectors=" .. selectors_hex() .. "\n")
  report:write(string.format(
    "final_latches=%02X,%02X,%02X,%02X\n",
    emu:read8(0xFF01), emu:read8(0xFF72),
    emu:read8(0xFF73), emu:read8(0xFF74)))
  report:write(string.format(
    "final_serial=%02X,%02X\n", emu:read8(0xFF02), emu:read8(0xFFFF)))
  report:close()
  assert(os.rename(temporary, OUT .. "/report.txt"))
  local marker = assert(io.open(OUT .. "/complete.marker.tmp", "w"))
  marker:write(STARTUP_TOKEN .. "\n" .. status .. "\n")
  marker:close()
  assert(os.rename(
    OUT .. "/complete.marker.tmp", OUT .. "/complete.marker"))
  os.exit(status == "pass" and 0 or 2)
end

callbacks:add("frame", function()
  if finished then return end
  emu:setKeys(0)
  if not state_loaded then
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_FILE)
    end)
    if not ok or result == false then
      finish("fail", "state-load-failed")
      return
    end
    state_loaded = true
    raw_vram = assert(emu.memory and emu.memory.vram,
      "mGBA bank-zero VRAM domain is unavailable")
    return
  end

  frame = frame + 1
  if not preflight_done then
    local fields = sample_fields()
    if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFFC1) ~= 0x01 then
      finish("fail", "state-is-not-active-stage1-gameplay")
      return
    end
    if fields.ffda ~= 0 then
      finish("fail", "preflight-ffda-is-not-zero")
      return
    end
    if (emu:read8(0xFF94) & 0x01) ~= 0 then
      finish("fail", "preflight-has-latent-a-edge")
      return
    end
    if fields.selectors ~= NATURAL_SELECTORS then
      finish("fail", "preflight-selectors-are-not-natural")
      return
    end
    if (fields.sc & 0x80) ~= 0 or (fields.ie & 0x08) ~= 0 then
      finish("fail", "preflight-serial-contract-failed")
      return
    end
    preflight_mismatches = bank0_mismatches()
    dump_bank0(OUT .. "/preflight-bank0-9000-97ff.bin")
    if preflight_mismatches ~= 0 then
      finish("fail", "preflight-bank0-chr-is-not-canonical")
      return
    end
    preflight_done = true
    trace_state("preflight", true)
  else
    trace_state("frame", false)
  end

  if emu:read8(0xD880) == 0x17 then death_scene_frames = death_scene_frames + 1 end
  if failure_reason ~= nil then
    finish("fail", failure_reason)
    return
  end
  if frame == STIMULUS_FRAME then
    native_assistance.write(0xDCBB, 0)
    stimulus_writes = stimulus_writes + 1
    stimulus_written = true
    trace_state("dcbb-zero-stimulus", true)
  end
  if returned_frame ~= nil and frame - returned_frame >= POSTRETURN_FRAMES then
    finish("pass", "complete")
    return
  end
  if frame >= FRAME_LIMIT then
    finish("fail", "neutral-route-timeout-before-continue-return")
  end
end)
