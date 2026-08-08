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
local transient_mismatch_trace = {}
local first_transient_mismatch = ""
local raw49_trace = {}
local last_raw49 = -1
local main_loop_hits, tile_copy_hits, pure_tail_hits, atomic_wrap_hits = 0, 0, 0, 0
local hazard_trampoline_hits, hazard_dispatcher_hits, hazard_helper_hits = 0, 0, 0
local hazard_row_hits = 0
local invalid_hazard_row_writes = 0
local hazard_event_trace = {}
local helper_bank_values = {}
local pure_setup_hits, atomic_path_hits = 0, 0
local tile_copy_states = {}
local phase_cache_trace = {}
local last_phase_cache = ""
local rendered_phase_trace = {}
local rendered_phase_seen = {}
local rendered_phase_oam_trace = {}
local rendered_phase_map_trace = {}
local periodic_render_trace = {}
local memory_trace_path = os.getenv("STAGE1_SPIKE_MEMORY_TRACE")
local memory_trace = memory_trace_path
  and assert(io.open(memory_trace_path, "wb")) or nil
local transient_check_start = tonumber(
  os.getenv("STAGE1_SPIKE_TRANSIENT_START") or "120")
local input_mask = tonumber(os.getenv("STAGE1_SPIKE_KEYS") or "0")
local screenshot_interval = tonumber(
  os.getenv("STAGE1_SPIKE_SCREENSHOT_INTERVAL") or "0")
local force_miniboss_frame = tonumber(
  os.getenv("STAGE1_SPIKE_FORCE_MINIBOSS_FRAME") or "-1")
local reinitialize_runtime = os.getenv("STAGE1_SPIKE_REINIT") ~= "0"
local expected_load_count = tonumber(
  os.getenv("STAGE1_SPIKE_EXPECTED_LOAD_COUNT") or "16")
local refresh_runtime_code = os.getenv("STAGE1_SPIKE_REFRESH_CODE") ~= "0"
local trace_writers = os.getenv("STAGE1_SPIKE_TRACE_WRITERS") == "1"
local writer_trace = {}
local last_writer_pc, last_writer_bank = -1, -1
local watched_snapshot = ""
local miniboss_first_frame = -1
local miniboss_trace = {}
local last_miniboss_state = ""
local progress_trace = {}
local palette_mismatch_frames = {}
local first_palette_mismatch = ""
local post_miniboss_hazard_helper_hits = 0
local post_miniboss_hazard_row_hits = 0
local miniboss_hram = ""
local miniboss_rst18_flags = {}
local expected_bg5 = os.getenv("STAGE1_SPIKE_EXPECTED_BG5")
  or "7FFF,03FF,001F,0000"
local expected_bg7 = os.getenv("STAGE1_SPIKE_EXPECTED_BG7")
  or "7FFF,7E94,03FF,0000"
local expected_bank1_art = assert(os.getenv("STAGE1_SPIKE_EXPECTED_BANK1_ART"))
local floor_mismatch_frames = {}
local floor_mismatch_trace = {}
local first_floor_mismatch = ""
local floor_lut_trace = {}
local last_floor_lut = ""
local floor_lut_mismatch_frames = {}
local atomic_source_trace = {}
local atomic_source_seen = {}
local atomic_floor_lut_mismatch_hits = 0
local floor_tiles = {
  0x2A, 0x2B, 0x2C, 0x2D, 0x2E,
  0x3A, 0x3B, 0x3C, 0x3D, 0x4C, 0x4D,
}

local function is_floor_tile(tile)
  return (tile >= 0x2A and tile <= 0x2E)
    or (tile >= 0x3A and tile <= 0x3D)
    or tile == 0x4C or tile == 0x4D
end

local function floor_lut_mismatches()
  local mismatches = {}
  for _, tile in ipairs(floor_tiles) do
    local palette = emu:read8(0xC600 + tile) & 0x07
    if palette ~= 0 then
      mismatches[#mismatches + 1] = string.format("%02X/%d", tile, palette)
    end
  end
  return table.concat(mismatches, ",")
end

-- Stage-1 room $05 uses 2A-2E/3A-3D for a 252-cell patterned floor; 4C/4D
-- build the lower platform in the adjacent room. They are environment art,
-- not part of the rotating 60-7F cylinder family. Inspect every tile that can
-- contribute pixels to the current LCD viewport, including partially exposed
-- edge tiles. The alternate map is checked as soon as stock makes it visible;
-- this preserves the fast off-screen preparation path while making any
-- player-visible palette leak a frame-exact failure.
local function inspect_floor_environment()
  local old_vbk = emu:read8(0xFF4F)
  local mismatches = {}
  local base = (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local columns = 20 + ((scx & 0x07) ~= 0 and 1 or 0)
  local rows = 18 + ((scy & 0x07) ~= 0 and 1 or 0)
  local tiles = {}
  emu:write8(0xFF4F, 0)
  for screen_row = 0, rows - 1 do
    local map_row = ((scy >> 3) + screen_row) & 0x1F
    for screen_column = 0, columns - 1 do
      local map_column = ((scx >> 3) + screen_column) & 0x1F
      local offset = map_row * 32 + map_column
      tiles[offset] = emu:read8(base + offset)
    end
  end
  emu:write8(0xFF4F, 1)
  for offset, tile in pairs(tiles) do
    if is_floor_tile(tile) then
      local attr = emu:read8(base + offset) & 0x07
      if attr ~= 0 and #mismatches < 24 then
        mismatches[#mismatches + 1] = string.format(
          "%04X/%03X/%02X/%d", base, offset, tile, attr)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatches
end

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
    if emu:read8(0xD880) == 0x0A then
      local flags = emu:readRegister("f") & 0xF0
      miniboss_rst18_flags[flags] = (miniboss_rst18_flags[flags] or 0) + 1
    end
  end, 0x0018)
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
    if frame >= 80 and #atomic_source_trace < 24 then
      local counts = {pattern=0, floor4c=0, floor4d=0, family=0}
      for address = 0xC1A0, 0xC3DF do
        local tile = emu:read8(address)
        if (tile >= 0x2A and tile <= 0x2E)
            or (tile >= 0x3A and tile <= 0x3D) then
          counts.pattern = counts.pattern + 1
        end
        if tile == 0x4C then counts.floor4c = counts.floor4c + 1 end
        if tile == 0x4D then counts.floor4d = counts.floor4d + 1 end
        if tile >= 0x60 and tile <= 0x7F then
          counts.family = counts.family + 1
        end
      end
      local floor_lut_mismatch = floor_lut_mismatches()
      local signature = string.format(
        "r%02X:p%d:c%d:d%d:h%d:l%s", emu:read8(0xFFBD),
        counts.pattern, counts.floor4c, counts.floor4d, counts.family,
        floor_lut_mismatch == "" and "ok" or floor_lut_mismatch)
      if counts.pattern + counts.floor4c + counts.floor4d > 0
          and floor_lut_mismatch ~= "" then
        atomic_floor_lut_mismatch_hits = atomic_floor_lut_mismatch_hits + 1
      end
      if not atomic_source_seen[signature] then
        atomic_source_seen[signature] = true
        atomic_source_trace[#atomic_source_trace + 1] = string.format(
          "f%d:%s", frame, signature)
      end
    end
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
      if emu:read8(0xD880) == 0x0A and emu:read8(0xFFBF) ~= 0 then
        post_miniboss_hazard_helper_hits =
          post_miniboss_hazard_helper_hits + 1
      end
      helper_bank_values[emu:read8(0xFF99)] = true
      if #hazard_event_trace < 160 then
        table.insert(hazard_event_trace, string.format(
          "f%d:hook:d%02X:r%02X:s%02X", frame,
          emu:read8(0xDC0B), emu:read8(0xFFBD), emu:read8(0xDC0E)))
      end
    end
  end, 0x6BA7)
  emu:setBreakpoint(function()
    if emu:read8(0xFF99) == 0x0E then
      hazard_row_hits = hazard_row_hits + 1
      local hl = emu:readRegister("hl") & 0xFFFF
      local count = emu:readRegister("c") & 0xFF
      local attr = emu:readRegister("e") & 0xFF
      if hl < 0x9800 or hl > 0x9FFF or count < 1 or count > 11 or
          (attr ~= 0x00 and attr ~= 0x06 and attr ~= 0x07 and attr ~= 0x0F) then
        invalid_hazard_row_writes = invalid_hazard_row_writes + 1
      end
      if emu:read8(0xD880) == 0x0A and emu:read8(0xFFBF) ~= 0 then
        post_miniboss_hazard_row_hits = post_miniboss_hazard_row_hits + 1
      end
      if #hazard_event_trace < 160 then
        table.insert(hazard_event_trace, string.format(
          "f%d:row:hl%04X:c%02X:e%02X", frame, hl, count, attr))
      end
    end
  end, 0x6C8F)
end)

local function cram_word(palette, color)
  local index = palette * 8 + color * 2
  emu:write8(0xFF68, index)
  local low = emu:read8(0xFF69)
  emu:write8(0xFF68, index + 1)
  local high = emu:read8(0xFF69)
  return (high << 8) | low
end

local function palette_words(palette)
  local old_index = emu:read8(0xFF68)
  local words = {}
  for color = 0, 3 do
    words[#words + 1] = cram_word(palette, color)
  end
  emu:write8(0xFF68, old_index)
  return words
end

local function obj_cram_word(palette, color)
  local index = palette * 8 + color * 2
  emu:write8(0xFF6A, index)
  local low = emu:read8(0xFF6B)
  emu:write8(0xFF6A, index + 1)
  local high = emu:read8(0xFF6B)
  return (high << 8) | low
end

local function obj_palette_words(palette)
  local old_index = emu:read8(0xFF6A)
  local words = {}
  for color = 0, 3 do
    words[#words + 1] = obj_cram_word(palette, color)
  end
  emu:write8(0xFF6A, old_index)
  return words
end

local function words_text(words)
  local values = {}
  for _, word in ipairs(words) do
    values[#values + 1] = string.format("%04X", word)
  end
  return table.concat(values, ",")
end

local function visible_oam_text()
  local entries = {}
  local sprite_height = (emu:read8(0xFF40) & 0x04) ~= 0 and 16 or 8
  for slot = 0, 39 do
    local address = 0xFE00 + slot * 4
    local y = emu:read8(address)
    local x = emu:read8(address + 1)
    if x > 0 and x < 168 and y > 0 and y < 160 + sprite_height then
      entries[#entries + 1] = string.format(
        "%d/%d/%d/%02X/%02X", slot, x, y,
        emu:read8(address + 2), emu:read8(address + 3))
    end
  end
  return table.concat(entries, ",")
end

local function phase_map_text(base, phase_offset)
  local old_vbk = emu:read8(0xFF4F)
  local center_row = phase_offset >> 5
  local entries = {}
  for row = math.max(0, center_row - 1), math.min(31, center_row + 4) do
    for column = 0, 31 do
      local offset = row * 32 + column
      emu:write8(0xFF4F, 0)
      local tile = emu:read8(base + offset)
      emu:write8(0xFF4F, 1)
      local attr = emu:read8(base + offset)
      if (tile >= 0x60 and tile <= 0x7F)
          or (tile >= 0x01 and tile <= 0x04) then
        entries[#entries + 1] = string.format(
          "%03X/%02X/%02X", offset, tile, attr)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(entries, ",")
end

local function inspect_map(base)
  local found, matched = 0, 0
  local tooth_found, tooth_matched = 0, 0
  local tooth_bank1 = 0
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
      local raw_attr = emu:read8(base + offset)
      local actual = raw_attr & 0x07
      if actual == expected then matched = matched + 1 end
      if actual ~= expected then
        table.insert(mismatches, string.format(
          "%04X,%03X,%02X,%d,%d", base, offset, tile, actual, expected))
      end
      if tooth then
        tooth_found = tooth_found + 1
        if actual == expected then tooth_matched = tooth_matched + 1 end
        if raw_attr == 0x0F then tooth_bank1 = tooth_bank1 + 1 end
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
    fire_found, fire_matched, support_found, support_matched, tooth_bank1
end

local function inspect_static_tooth_rows()
  local room = emu:read8(0xFFBD)
  local shift = room == 0x02 and 4 or 0
  local found, matched = 0, 0
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for _, base in ipairs({0x9800, 0x9C00}) do
    for _, row in ipairs({0x40 + shift, 0xA0 + shift}) do
      for column = 0, 8 do
        found = found + 1
        local attr = emu:read8(base + row + column)
        if attr == 0x0F then matched = matched + 1 end
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return found, matched
end

local function bank1_art_mismatches()
  local tiles = {
    0x01, 0x02, 0x03, 0x04,
    0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
    0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
  }
  local mismatched = 0
  local mismatch_trace = {}
  local actual_art = {}
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for tile_index, tile in ipairs(tiles) do
    local start = 0x1000 + tile * 16
    local tile_mismatches = 0
    for byte = 0, 15 do
      local text_offset = ((tile_index - 1) * 16 + byte) * 2 + 1
      local expected = tonumber(
        expected_bank1_art:sub(text_offset, text_offset + 1), 16)
      local actual = emu:read8(0x8000 + start + byte)
      actual_art[#actual_art + 1] = string.format("%02x", actual)
      if actual ~= expected then
        mismatched = mismatched + 1
        tile_mismatches = tile_mismatches + 1
      end
    end
    if tile_mismatches > 0 then
      mismatch_trace[#mismatch_trace + 1] = string.format(
        "%02X/%d", tile, tile_mismatches)
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatched, table.concat(mismatch_trace, ","), table.concat(actual_art)
end

local function finish()
  local found9800, matched9800 = inspect_map(0x9800)
  local found9c00, matched9c00, tooth_found, tooth_matched,
    fire_found, fire_matched, support_found, support_matched, tooth_bank1 =
    inspect_map(0x9C00)
  local static_rows_found, static_rows_matched = inspect_static_tooth_rows()
  local bank1_mismatches, bank1_mismatch_trace, bank1_art =
    bank1_art_mismatches()
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
  handle:write(string.format("tooth_bank1=%d\n", tooth_bank1))
  handle:write(string.format(
    "static_tooth_rows=%d,%d\n", static_rows_found, static_rows_matched))
  handle:write(string.format(
    "bank1_load_index=%02X\n", emu:read8(0xDF5B)))
  handle:write(string.format(
    "bank1_art_mismatches=%d\n", bank1_mismatches))
  handle:write("bank1_art_mismatch_trace=" .. bank1_mismatch_trace .. "\n")
  handle:write("bank1_art=" .. bank1_art .. "\n")
  handle:write(string.format(
    "bg5=%04X,%04X,%04X,%04X\n",
    cram_word(5, 0), cram_word(5, 1), cram_word(5, 2), cram_word(5, 3)))
  handle:write(string.format(
    "bg7=%04X,%04X,%04X,%04X\n",
    cram_word(7, 0), cram_word(7, 1), cram_word(7, 2), cram_word(7, 3)))
  handle:write(string.format("powerup=%02X\n", emu:read8(0xFFC0)))
  handle:write("obj0=" .. words_text(obj_palette_words(0)) .. "\n")
  handle:write("visible_oam=" .. visible_oam_text() .. "\n")
  for _, mismatch in ipairs(mismatches) do
    handle:write("mismatch=" .. mismatch .. "\n")
  end
  handle:write("lut7d=" .. string.format("%02X", emu:read8(0xC67D)) .. "\n")
  handle:write("cell9c88=" .. table.concat(cell_trace, ";") .. "\n")
  handle:write(string.format(
    "transient_mismatch_frames=%d\n", #transient_mismatch_frames))
  handle:write(
    "transient_mismatch_trace=" .. table.concat(transient_mismatch_trace, ";") .. "\n")
  handle:write("first_transient_mismatch=" .. first_transient_mismatch .. "\n")
  handle:write("raw49_trace=" .. table.concat(raw49_trace, ";") .. "\n")
  handle:write(string.format("miniboss_first_frame=%d\n", miniboss_first_frame))
  handle:write("miniboss_trace=" .. table.concat(miniboss_trace, ";") .. "\n")
  handle:write("miniboss_hram=" .. miniboss_hram .. "\n")
  local rst18_flags = {}
  for value, count in pairs(miniboss_rst18_flags) do
    rst18_flags[#rst18_flags + 1] = string.format("%02X:%d", value, count)
  end
  table.sort(rst18_flags)
  handle:write("miniboss_rst18_flags=" .. table.concat(rst18_flags, ",") .. "\n")
  handle:write("progress_trace=" .. table.concat(progress_trace, ";") .. "\n")
  handle:write(string.format(
    "palette_mismatch_frames=%d\n", #palette_mismatch_frames))
  handle:write("first_palette_mismatch=" .. first_palette_mismatch .. "\n")
  handle:write(string.format(
    "floor_mismatch_frames=%d\n", #floor_mismatch_frames))
  handle:write("floor_mismatch_trace=" .. table.concat(
    floor_mismatch_trace, ";") .. "\n")
  handle:write("first_floor_mismatch=" .. first_floor_mismatch .. "\n")
  handle:write("floor_lut_trace=" .. table.concat(floor_lut_trace, ";") .. "\n")
  handle:write(string.format(
    "floor_lut_mismatch_frames=%d\n", #floor_lut_mismatch_frames))
  handle:write(string.format(
    "atomic_floor_lut_mismatch_hits=%d\n", atomic_floor_lut_mismatch_hits))
  handle:write("atomic_source_trace=" .. table.concat(
    atomic_source_trace, ";") .. "\n")
  handle:write(string.format(
    "post_miniboss_hazard_helper_hits=%d\n", post_miniboss_hazard_helper_hits))
  handle:write(string.format(
    "post_miniboss_hazard_row_hits=%d\n", post_miniboss_hazard_row_hits))
  handle:write(string.format(
    "main_loop_hits=%d\ntile_copy_hits=%d\npure_tail_hits=%d\n" ..
    "atomic_wrap_hits=%d\nhazard_trampoline_hits=%d\n" ..
    "hazard_dispatcher_hits=%d\nhazard_helper_hits=%d\n" ..
    "hazard_row_hits=%d\ninvalid_hazard_row_writes=%d\n" ..
    "pure_setup_hits=%d\natomic_path_hits=%d\n",
    main_loop_hits, tile_copy_hits, pure_tail_hits, atomic_wrap_hits,
    hazard_trampoline_hits, hazard_dispatcher_hits, hazard_helper_hits,
    hazard_row_hits, invalid_hazard_row_writes,
    pure_setup_hits, atomic_path_hits))
  handle:write("phase_cache_trace=" .. table.concat(phase_cache_trace, ";") .. "\n")
  handle:write(
    "rendered_phase_trace=" .. table.concat(rendered_phase_trace, ";") .. "\n")
  handle:write(
    "rendered_phase_oam_trace=" ..
    table.concat(rendered_phase_oam_trace, ";") .. "\n")
  handle:write(
    "rendered_phase_map_trace=" ..
    table.concat(rendered_phase_map_trace, ";") .. "\n")
  handle:write(
    "periodic_render_trace=" ..
    table.concat(periodic_render_trace, ";") .. "\n")
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
  emu:setKeys(input_mask)

  -- Deterministic palette-transition receipt. Historical active-Gargoyle
  -- save states are not execution-portable across ROM revisions, so switch
  -- only the three observed scene flags on a healthy current room-$12 state.
  if frame == force_miniboss_frame then
    emu:write8(0xD880, 0x0A)
    emu:write8(0xFFBF, 0x01)
    emu:write8(0xDCB8, 0x02)
  end

  local floor_lut = floor_lut_mismatches()
  if floor_lut == "" then floor_lut = "ok" end
  if floor_lut ~= last_floor_lut then
    floor_lut_trace[#floor_lut_trace + 1] = string.format(
      "f%d:%s", frame, floor_lut)
    last_floor_lut = floor_lut
  end
  if frame >= 80 then
    if floor_lut ~= "ok" then
      floor_lut_mismatch_frames[#floor_lut_mismatch_frames + 1] = frame
    end
    local floor_mismatches = inspect_floor_environment()
    if #floor_mismatches > 0 then
      floor_mismatch_frames[#floor_mismatch_frames + 1] = frame
      if #floor_mismatch_trace < 96 then
        floor_mismatch_trace[#floor_mismatch_trace + 1] = string.format(
          "f%d:s%02X:r%02X:y%02X:l%s:%s", frame,
          emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFF42),
          floor_lut, table.concat(floor_mismatches, ","))
      end
      if first_floor_mismatch == "" then
        first_floor_mismatch = floor_mismatch_trace[#floor_mismatch_trace]
        emu:screenshot(OUT .. "-first-floor-mismatch.png")
      end
    end
  end

  local miniboss_state = string.format(
    "%02X/%02X/%02X", emu:read8(0xD880), emu:read8(0xFFBF),
    emu:read8(0xDCB8))
  if miniboss_state ~= last_miniboss_state and #miniboss_trace < 128 then
    miniboss_trace[#miniboss_trace + 1] = string.format(
      "f%d:%s", frame, miniboss_state)
    last_miniboss_state = miniboss_state
  end
  if miniboss_first_frame < 0 and emu:read8(0xFFBF) ~= 0 then
    miniboss_first_frame = frame
    emu:screenshot(OUT .. "-miniboss-entry.png")
  end
  if miniboss_hram == "" and emu:read8(0xD880) == 0x0A then
    local bytes = {}
    for address = 0xFF80, 0xFFFE do
      bytes[#bytes + 1] = string.format("%02X", emu:read8(address))
    end
    miniboss_hram = table.concat(bytes)
  end
  if frame == 1 or frame % 30 == 0 then
    progress_trace[#progress_trace + 1] = string.format(
      "f%d:s%02X:r%02X:b%02X:k%02X:c%04X:p%02X%02X",
      frame, emu:read8(0xD880), emu:read8(0xFFBD),
      emu:read8(0xFFBF), emu:read8(0xDCB8),
      emu:read8(0xDC02) | (emu:read8(0xDC03) << 8),
      emu:read8(0xDCE8), emu:read8(0xDCE9))
  end
  if screenshot_interval > 0 and frame % screenshot_interval == 0 then
    local render_path = string.format("%s-frame%04d.png", OUT, frame)
    emu:screenshot(render_path)
    periodic_render_trace[#periodic_render_trace + 1] = string.format(
      "f%d:%02X:%02X:%02X:%02X:%02X:%s", frame,
      emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xD880),
      emu:read8(0xFFBD), emu:read8(0xFFBF), render_path)
  end

  if refresh_runtime_code and frame == 1 then emu:write8(0xDF51, 0) end

  -- Historical states predate the current WRAM helpers. Re-enter the exact
  -- current-ROM initializer and invalidate both Stage 1 map signatures.
  if reinitialize_runtime and frame <= 40 then
    emu:write8(0xDF02, 0)
    emu:write8(0xDF00, 0)
    emu:write8(0xDF53, 0)
    emu:write8(0xDF55, 0)
    emu:write8(0xDF57, 0)
    emu:write8(0xDF58, 0)
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
    if frame >= transient_check_start then
      local bg5_text = words_text(palette_words(5))
      local bg7_text = words_text(palette_words(7))
      if bg5_text ~= expected_bg5 or bg7_text ~= expected_bg7 then
        palette_mismatch_frames[#palette_mismatch_frames + 1] = frame
        if first_palette_mismatch == "" then
          first_palette_mismatch = string.format(
            "f%d:bg5=%s:bg7=%s:s%02X:r%02X:b%02X:k%02X",
            frame, bg5_text, bg7_text, emu:read8(0xD880),
            emu:read8(0xFFBD), emu:read8(0xFFBF), emu:read8(0xDCB8))
          emu:screenshot(OUT .. "-first-palette-mismatch.png")
        end
      end
    end
    local phase_cache = string.format(
      "%02X/%02X", emu:read8(0xDF55), emu:read8(0xDF58))
    if phase_cache ~= last_phase_cache then
      table.insert(phase_cache_trace, string.format("f%d:%s", frame, phase_cache))
      last_phase_cache = phase_cache
    end
    -- Capture the four stable rendered cylinder phases, not merely the final
    -- attribute map. Admit frames only after all bank-1 art is installed; the
    -- position-owned rows then remain invariant through every phase change.
    local room = emu:read8(0xFFBD)
    local phase_offset = room == 0x02 and 0x44 or 0x41
    local active_base = (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800
    local old_phase_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    local rendered_phase = emu:read8(active_base + phase_offset)
    emu:write8(0xFF4F, 1)
    local rendered_attr = emu:read8(active_base + phase_offset) & 0x07
    emu:write8(0xFF4F, old_phase_vbk)
    if (emu:read8(0xDF5B) & 0x03) == expected_load_count
        and not rendered_phase_seen[rendered_phase] then
      local phase_path = string.format(
        "%s-phase-%02X.png", OUT, rendered_phase)
      emu:screenshot(phase_path)
      rendered_phase_seen[rendered_phase] = true
      table.insert(rendered_phase_trace, string.format(
        "f%d:%02X/%d:%s", frame, rendered_phase, rendered_attr, phase_path))
      table.insert(rendered_phase_oam_trace, string.format(
        "f%d:%02X:%s", frame, rendered_phase, visible_oam_text()))
      table.insert(rendered_phase_map_trace, string.format(
        "f%d:%02X:%04X:%02X:%02X:%s", frame, rendered_phase, active_base,
        emu:read8(0xFF43), emu:read8(0xFF42),
        phase_map_text(active_base, phase_offset)))
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
        if #transient_mismatch_trace < 64 then
          transient_mismatch_trace[#transient_mismatch_trace + 1] = string.format(
            "f%d:s%02X:b%02X:d%02X:%s", frame, emu:read8(0xD880),
            emu:read8(0xFFBF), emu:read8(0xDC0B),
            table.concat(frame_mismatches, ","))
        end
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
