-- Prove the reviewed Stage-1 spike material split is live in both BG maps.

local OUT = assert(os.getenv("STAGE1_SPIKE_OUT"))
local SETTLE = tonumber(os.getenv("STAGE1_SPIKE_SETTLE") or "180")
local frame = 0
local mismatches = {}
local cell_trace = {}
local last_cell = ""
local tracked_offsets = {}
local tracked_ids = {}
local transient_mismatch_frames = {}
local first_transient_mismatch = ""
local raw49_trace = {}
local last_raw49 = -1
local main_loop_hits, tile_copy_hits, pure_tail_hits, atomic_wrap_hits = 0, 0, 0, 0
local hazard_trampoline_hits, hazard_dispatcher_hits, hazard_helper_hits = 0, 0, 0
local hazard_row_hits = 0
local hazard_event_trace = {}
local helper_bank_values = {}
local pure_setup_hits, atomic_path_hits = 0, 0
local tile_copy_states = {}
local phase_cache_trace = {}
local last_phase_cache = ""
local memory_trace_path = os.getenv("STAGE1_SPIKE_MEMORY_TRACE")
local memory_trace = memory_trace_path
  and assert(io.open(memory_trace_path, "wb")) or nil
local transient_check_start = tonumber(
  os.getenv("STAGE1_SPIKE_TRANSIENT_START") or "120")
local reinitialize_runtime = os.getenv("STAGE1_SPIKE_REINIT") ~= "0"
local refresh_runtime_code = os.getenv("STAGE1_SPIKE_REFRESH_CODE") ~= "0"
local trace_writers = os.getenv("STAGE1_SPIKE_TRACE_WRITERS") == "1"
local writer_trace = {}
local last_writer_pc, last_writer_bank = -1, -1
local watched_snapshot = ""

local function watched_bytes()
  local values = {}
  for offset = 48, 56 do
    values[#values + 1] = string.char(emu:read8(0xC1A0 + offset))
  end
  for offset = 120, 128 do
    values[#values + 1] = string.char(emu:read8(0xC1A0 + offset))
  end
  return table.concat(values)
end

local function writer_breakpoint(address, segment)
  pcall(function()
    emu:setBreakpoint(function()
      if frame >= 70 then
        local current = watched_bytes()
        if watched_snapshot ~= "" and current ~= watched_snapshot then
          writer_trace[#writer_trace + 1] = string.format(
            "f%d:%02X:%04X", frame, last_writer_bank & 0xFF,
            last_writer_pc & 0xFFFF)
        end
        watched_snapshot = current
        last_writer_pc = address
        last_writer_bank = emu:read8(0xFF99)
      end
    end, address, segment)
  end)
end

if trace_writers then
  local write_opcodes = {
    [0x02]=true, [0x12]=true, [0x22]=true, [0x32]=true, [0x36]=true,
    [0x70]=true, [0x71]=true, [0x72]=true, [0x73]=true, [0x74]=true,
    [0x75]=true, [0x77]=true, [0xCB]=true, [0xE0]=true, [0xEA]=true,
  }
  for address = 0, 0x3FFF do
    if write_opcodes[emu:read8(address)] then writer_breakpoint(address, -1) end
  end
  for address = 0x4000, 0x7FFF do
    if write_opcodes[emu:read8(address)] then writer_breakpoint(address, 1) end
  end
end

local function expected_palette(tile)
  local tooth =
    (tile >= 0x64 and tile <= 0x69) or
    (tile >= 0x74 and tile <= 0x79)
  local fire =
    tile == 0x60 or tile == 0x61 or tile == 0x62 or
    tile == 0x6C or tile == 0x6D or tile == 0x6E or
    tile == 0x70 or tile == 0x71 or tile == 0x72 or
    tile == 0x7C or tile == 0x7D or tile == 0x7E
  return tooth and 7 or (fire and 5 or 6)
end

pcall(function()
  emu:setBreakpoint(function()
    if frame >= 80 then main_loop_hits = main_loop_hits + 1 end
  end, 0x016C)
  emu:setBreakpoint(function()
    if frame >= 80 then
      tile_copy_hits = tile_copy_hits + 1
      if #hazard_event_trace < 160 then
        table.insert(hazard_event_trace, string.format(
          "f%d:copy:hl%04X:d%02X", frame,
          emu:readRegister("hl"), emu:read8(0xDC0B)))
      end
      local key = string.format("%02X/%02X",
        emu:read8(0xD880), emu:read8(0xDCFD))
      tile_copy_states[key] = (tile_copy_states[key] or 0) + 1
    end
  end, 0x42A7)
  emu:setBreakpoint(function()
    if frame >= 80 then atomic_path_hits = atomic_path_hits + 1 end
  end, 0x42B2)
  emu:setBreakpoint(function()
    if frame >= 80 then pure_setup_hits = pure_setup_hits + 1 end
  end, 0x432E)
  emu:setBreakpoint(function()
    if frame >= 80 then pure_tail_hits = pure_tail_hits + 1 end
  end, 0x4358)
  emu:setBreakpoint(function()
    if frame >= 80 then atomic_wrap_hits = atomic_wrap_hits + 1 end
  end, 0x3498)
  emu:setBreakpoint(function()
    if frame >= 80 then hazard_trampoline_hits = hazard_trampoline_hits + 1 end
  end, 0x0847)
  emu:setBreakpoint(function()
    if frame >= 80 and emu:read8(0xFF99) == 0x0D then
      hazard_dispatcher_hits = hazard_dispatcher_hits + 1
    end
  end, 0x7B9C)
  emu:setBreakpoint(function()
    if frame >= 80 then
      hazard_helper_hits = hazard_helper_hits + 1
      helper_bank_values[emu:read8(0xFF99)] = true
      if #hazard_event_trace < 160 then
        table.insert(hazard_event_trace, string.format(
          "f%d:hook:d%02X:r%02X:s%02X", frame,
          emu:read8(0xDC0B), emu:read8(0xFFBD), emu:read8(0xDC0E)))
      end
    end
  end, 0x6BA7)
  emu:setBreakpoint(function()
    if frame >= 80 and emu:read8(0xFF99) == 0x0E then
      hazard_row_hits = hazard_row_hits + 1
      if #hazard_event_trace < 160 then
        table.insert(hazard_event_trace, string.format(
          "f%d:row:hl%04X:de%04X", frame,
          emu:readRegister("hl"), emu:readRegister("de")))
      end
    end
  end, 0x6C88)
end)

local function cram_word(palette, color)
  local index = palette * 8 + color * 2
  emu:write8(0xFF68, index)
  local low = emu:read8(0xFF69)
  emu:write8(0xFF68, index + 1)
  local high = emu:read8(0xFF69)
  return (high << 8) | low
end

local function inspect_map(base)
  local found, matched = 0, 0
  local tooth_found, tooth_matched = 0, 0
  local fire_found, fire_matched = 0, 0
  local support_found, support_matched = 0, 0
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  local tiles = {}
  for offset = 0, 0x3FF do tiles[offset] = emu:read8(base + offset) end
  emu:write8(0xFF4F, 1)
  for offset = 0, 0x3FF do
    local tile = tiles[offset]
    if tile >= 0x60 and tile <= 0x7F then
      found = found + 1
      local tooth =
        (tile >= 0x64 and tile <= 0x69) or
        (tile >= 0x74 and tile <= 0x79)
      local fire =
        tile == 0x60 or tile == 0x61 or tile == 0x62 or
        tile == 0x6C or tile == 0x6D or tile == 0x6E or
        tile == 0x70 or tile == 0x71 or tile == 0x72 or
        tile == 0x7C or tile == 0x7D or tile == 0x7E
      local expected = expected_palette(tile)
      local actual = emu:read8(base + offset) & 0x07
      if actual == expected then matched = matched + 1 end
      if actual ~= expected then
        table.insert(mismatches, string.format(
          "%04X,%03X,%02X,%d,%d", base, offset, tile, actual, expected))
      end
      if tooth then
        tooth_found = tooth_found + 1
        if actual == expected then tooth_matched = tooth_matched + 1 end
      elseif fire then
        fire_found = fire_found + 1
        if actual == expected then fire_matched = fire_matched + 1 end
      else
        support_found = support_found + 1
        if actual == expected then support_matched = support_matched + 1 end
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return found, matched, tooth_found, tooth_matched,
    fire_found, fire_matched, support_found, support_matched
end

local function finish()
  local found9800, matched9800 = inspect_map(0x9800)
  local found9c00, matched9c00, tooth_found, tooth_matched,
    fire_found, fire_matched, support_found, support_matched =
    inspect_map(0x9C00)
  local handle = assert(io.open(OUT .. ".txt", "w"))
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("scene=%02X\n", emu:read8(0xD880)))
  handle:write(string.format("room=%02X\n", emu:read8(0xFFBD)))
  handle:write(string.format("source=%02X%02X\n",
    emu:read8(0xDC0F), emu:read8(0xDC0E)))
  handle:write(string.format("lcdc=%02X\n", emu:read8(0xFF40)))
  handle:write(string.format(
    "map9800=%d,%d\nmap9c00=%d,%d\n",
    found9800, matched9800, found9c00, matched9c00))
  handle:write(string.format(
    "tooth=%d,%d\nfire=%d,%d\nsupport=%d,%d\n",
    tooth_found, tooth_matched, fire_found, fire_matched,
    support_found, support_matched))
  handle:write(string.format(
    "bg5=%04X,%04X,%04X,%04X\n",
    cram_word(5, 0), cram_word(5, 1), cram_word(5, 2), cram_word(5, 3)))
  handle:write(string.format(
    "bg7=%04X,%04X,%04X,%04X\n",
    cram_word(7, 0), cram_word(7, 1), cram_word(7, 2), cram_word(7, 3)))
  for _, mismatch in ipairs(mismatches) do
    handle:write("mismatch=" .. mismatch .. "\n")
  end
  handle:write("lut7d=" .. string.format("%02X", emu:read8(0xC67D)) .. "\n")
  handle:write("cell9c88=" .. table.concat(cell_trace, ";") .. "\n")
  handle:write(string.format(
    "transient_mismatch_frames=%d\n", #transient_mismatch_frames))
  handle:write("first_transient_mismatch=" .. first_transient_mismatch .. "\n")
  handle:write("raw49_trace=" .. table.concat(raw49_trace, ";") .. "\n")
  handle:write(string.format(
    "main_loop_hits=%d\ntile_copy_hits=%d\npure_tail_hits=%d\n" ..
    "atomic_wrap_hits=%d\nhazard_trampoline_hits=%d\n" ..
    "hazard_dispatcher_hits=%d\nhazard_helper_hits=%d\n" ..
    "hazard_row_hits=%d\n" ..
    "pure_setup_hits=%d\natomic_path_hits=%d\n",
    main_loop_hits, tile_copy_hits, pure_tail_hits, atomic_wrap_hits,
    hazard_trampoline_hits, hazard_dispatcher_hits, hazard_helper_hits,
    hazard_row_hits,
    pure_setup_hits, atomic_path_hits))
  handle:write("phase_cache_trace=" .. table.concat(phase_cache_trace, ";") .. "\n")
  handle:write("hazard_event_trace=" .. table.concat(hazard_event_trace, ";") .. "\n")
  local helper_banks = {}
  for bank, _ in pairs(helper_bank_values) do
    table.insert(helper_banks, string.format("%02X", bank))
  end
  table.sort(helper_banks)
  handle:write("helper_banks=" .. table.concat(helper_banks, ",") .. "\n")
  local copy_states = {}
  for state, count in pairs(tile_copy_states) do
    table.insert(copy_states, string.format("%s:%d", state, count))
  end
  table.sort(copy_states)
  handle:write("tile_copy_states=" .. table.concat(copy_states, ",") .. "\n")
  handle:write("writer_trace=" .. table.concat(writer_trace, ";") .. "\n")
  for _, offset in ipairs(tracked_offsets) do
    local ids = {}
    for tile = 0x60, 0x7F do
      if tracked_ids[offset][tile] then
        table.insert(ids, string.format("%02X", tile))
      end
    end
    handle:write(string.format(
      "cycle=9C00,%03X,%s\n", offset, table.concat(ids, ",")))
  end
  handle:close()
  if memory_trace then memory_trace:close() end
  emu:screenshot(OUT .. ".png")
  os.exit(0)
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)

  if refresh_runtime_code and frame == 1 then emu:write8(0xDF51, 0) end

  -- Historical states predate the current WRAM helpers. Re-enter the exact
  -- current-ROM initializer and invalidate both Stage 1 map signatures.
  if reinitialize_runtime and frame <= 40 then
    emu:write8(0xDF02, 0)
    emu:write8(0xDF00, 0)
    emu:write8(0xDF53, 0)
    emu:write8(0xDF57, 0)
    emu:write8(0xDF04, 0)
    emu:write8(0xDF05, 0)
    emu:write8(0xDF4E, 0)
  end
  if reinitialize_runtime and frame == 1 then emu:write8(0xDF0D, 0xFF) end

  -- Preserve the captured room while its current-ROM attributes settle.
  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)
  if frame >= 80 then
    local phase_cache = string.format(
      "%02X/%02X", emu:read8(0xDF55), emu:read8(0xDF58))
    if phase_cache ~= last_phase_cache then
      table.insert(phase_cache_trace, string.format("f%d:%s", frame, phase_cache))
      last_phase_cache = phase_cache
    end
    local raw49 = emu:read8(0xC1D1)
    if raw49 ~= last_raw49 then
      table.insert(raw49_trace, string.format("f%d:%02X", frame, raw49))
      last_raw49 = raw49
    end
    if memory_trace and emu:read8(0xD880) == 0x02 then
      local bytes = {
        string.char(frame & 0xFF, (frame >> 8) & 0xFF, raw49)
      }
      for address = 0xC000, 0xDFFF do
        bytes[#bytes + 1] = string.char(emu:read8(address))
      end
      for address = 0xFF80, 0xFFFE do
        bytes[#bytes + 1] = string.char(emu:read8(address))
      end
      memory_trace:write(table.concat(bytes))
    end
    local old_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    if frame == 80 then
      for offset = 0, 0x3FF do
        local candidate = emu:read8(0x9C00 + offset)
        if candidate >= 0x60 and candidate <= 0x7F then
          table.insert(tracked_offsets, offset)
          tracked_ids[offset] = {}
        end
      end
    end
    for _, offset in ipairs(tracked_offsets) do
      local candidate = emu:read8(0x9C00 + offset)
      if candidate >= 0x60 and candidate <= 0x7F then
        tracked_ids[offset][candidate] = true
      end
    end
    local live_tiles = {}
    for _, offset in ipairs(tracked_offsets) do
      live_tiles[offset] = emu:read8(0x9C00 + offset)
    end
    local tile = emu:read8(0x9C88)
    emu:write8(0xFF4F, 1)
    local attr = emu:read8(0x9C88) & 0x07
    if frame >= transient_check_start then
      local frame_mismatches = {}
      for _, offset in ipairs(tracked_offsets) do
        local candidate = live_tiles[offset]
        if candidate >= 0x60 and candidate <= 0x7F then
          local actual = emu:read8(0x9C00 + offset) & 0x07
          local expected = expected_palette(candidate)
          if actual ~= expected then
            table.insert(frame_mismatches, string.format(
              "%03X:%02X/%d/%d", offset, candidate, actual, expected))
          end
        end
      end
      if #frame_mismatches > 0 then
        table.insert(transient_mismatch_frames, frame)
        if first_transient_mismatch == "" then
          first_transient_mismatch = string.format(
            "f%d:%s:raw31=%02X:raw49=%02X:raw73=%02X:cache=%02X",
            frame, table.concat(frame_mismatches, ","),
            emu:read8(0xC1BF), emu:read8(0xC1D1), emu:read8(0xC1E9),
            emu:read8(0xDF57))
          emu:screenshot(OUT .. "-first-transient-mismatch.png")
        end
      end
    end
    emu:write8(0xFF4F, old_vbk)
    local value = string.format("%02X/%d", tile, attr)
    if value ~= last_cell then
      table.insert(cell_trace, string.format("f%d:%s", frame, value))
      last_cell = value
    end
  end
  if frame >= SETTLE then finish() end
end)
