-- Cold-boot Stage 1, play continuously, and prove that every visible tile's
-- palette attribute matches the ROM's Stage 1 tile table or an exact semantic
-- pickup override derived from the packed room source.
--
-- Environment:
--   STAGE1_BLEED_OUT       output directory
--   STAGE1_BLEED_FRAMES    actual gameplay frames (default 1200)
--   STAGE1_BLEED_MODE      right, patrol, vertical, or box (default box)

local OUT = assert(os.getenv("STAGE1_BLEED_OUT"))
local LUT_PATH = assert(os.getenv("STAGE1_BLEED_LUT"))
local lut_file = assert(io.open(LUT_PATH, "rb"))
local lut = assert(lut_file:read("*a"))
lut_file:close()
assert(#lut == 256)
local LIMIT = tonumber(os.getenv("STAGE1_BLEED_FRAMES") or "1200")
local INPUT_MODE = os.getenv("STAGE1_BLEED_MODE") or "box"
local RESULT = OUT .. "/probe.txt"
local DONE = OUT .. "/DONE"

local KEY_A, KEY_START = 0x01, 0x08
local KEY_RIGHT, KEY_LEFT = 0x10, 0x20
local KEY_UP, KEY_DOWN = 0x40, 0x80
local EXPECTED_SCENE = 0x02
local CAPTURE_FRAMES = {
  [120] = true,
  [360] = true,
  [600] = true,
  [840] = true,
  [1080] = true,
  [1200] = true,
}

local frame, phase = 0, "title"
local seeded, confirmed, finished = false, false, false
local stable_frames, play_frames = 0, 0
local sampled_frames, checked_cells = 0, 0
local pal1_cells, unexpected_cells, unsafe_cells = 0, 0, 0
local unexpected_semantic_pickup_cells, unexpected_floor_cells = 0, 0
local runtime_lut_mismatch_frames, runtime_lut_mismatch_cells = 0, 0
local runtime_lut_mismatch_max = 0
local runtime_lut_dma_unreadable_frames = 0
local first_runtime_lut_dma_unreadable = ""
local first_runtime_lut_mismatch_frame = -1
local first_runtime_lut_mismatch_details = ""
local pal1_tiles = {}
local first_pal1_frame, first_unexpected_frame = -1, -1
local first_unexpected_floor_frame = -1
local first_unexpected_floor_details = ""
local scene_frames, active_frames = 0, 0
local compiler_unreadable_scene_frames = 0
local previous_scx, previous_scy = -1, -1
local scroll_changes, scx_changes, scy_changes = 0, 0, 0
local previous_source_signature, source_signature_changes = -1, 0
local captures = {}
local raster_captures = {}
local raster_window = 0
local helper_events = {}
local first_unexpected_path = ""
local first_unexpected_details = ""
local debug_copy_hits, debug_atomic_hits, debug_pure_hits = 0, 0, 0
local debug_main_hits, debug_last_address = 0, -1
local debug_atomic = tonumber(os.getenv("STAGE1_DEBUG_ATOMIC") or "0")
local debug_pure = tonumber(os.getenv("STAGE1_DEBUG_PURE") or "0")
local debug_decision = tonumber(os.getenv("STAGE1_DEBUG_DECISION") or "13445")
local trace_layouts = tonumber(os.getenv("STAGE1_TRACE_LAYOUTS") or "0") ~= 0
local layout_records, layout_seen = {}, {}
local debug_destination = 0
local packed_signatures
local pickup_rect_history, oam_rect_history = {}, {}
local PICKUP_METATILE_PALETTES = {
  4, 4, 4, 4, 4, 5, 5, 5,
  1, 1, 1, 3, 3, 4, 4, 4,
  0, 0, 2, 5, 2, 2, 5, 2,
}
local last_semantic_pickup_cells = {}

local function read_register(name)
  local readers = {
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:getRegister(string.upper(name)) end,
    function() return emu:readRegister(string.lower(name)) end,
    function() return emu:readRegister(string.upper(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value then return value & 0xFFFF end
  end
  return -1
end

local function compiler_scene_unreadable(pc)
  return (emu:read8(0xFF70) & 0x07) == 0x03
    and ((pc >= 0x42A7 and pc <= 0x436D)
      or (pc >= 0xD400 and pc <= 0xD478))
end

local function semantic_pickup_cells()
  local cells = {}
  local source = emu:read8(0xDC0E) | (emu:read8(0xDC0F) << 8)
  -- Lua observes the CPU bus, so WRAM reads are FF during the game's OAM-DMA
  -- HRAM routine. Reuse the preceding valid semantic map for that exact
  -- inaccessible sample instead of misclassifying pickups as floor tiles.
  if source < 0xC000 or source > 0xDFFF then
    if source == 0xFFFF then return last_semantic_pickup_cells end
    return cells
  end
  for row = 0, 9 do
    for column = 0, 10 do
      local metatile = emu:read8(source + row * 16 + column)
      if metatile >= 0xD7 then metatile = metatile - 0xB1 end
      local index = metatile - 0x26
      if index >= 0 and index < #PICKUP_METATILE_PALETTES then
        local palette = PICKUP_METATILE_PALETTES[index + 1]
        if palette ~= 0 then
          local offset = row * 64 + column * 2
          cells[offset] = palette
          cells[offset + 1] = palette
          cells[offset + 32] = palette
          cells[offset + 33] = palette
        end
      end
    end
  end
  last_semantic_pickup_cells = cells
  return cells
end

local function recent_rectangles(history, value)
  if value ~= "" then history[#history + 1] = value end
  while #history > 12 do table.remove(history, 1) end
  return table.concat(history, ";")
end

local function register_layout(raw_layout, attr_layout)
  if not trace_layouts then return 0 end
  if not layout_seen[raw_layout] then
    layout_records[#layout_records + 1] = {
      raw = raw_layout,
      attr = attr_layout,
    }
    layout_seen[raw_layout] = #layout_records
  end
  return layout_seen[raw_layout]
end

pcall(function()
  emu:setBreakpoint(function()
    debug_destination = 0x9C
  end, 0x42A0)
  emu:setBreakpoint(function()
    debug_destination = 0x98
  end, 0x42A5)
  emu:setBreakpoint(function()
    debug_copy_hits = debug_copy_hits + 1
    debug_last_address = 0x42A7
  end, 0x42A7)
  emu:setBreakpoint(function()
    debug_main_hits = debug_main_hits + 1
    debug_last_address = 0x016C
  end, 0x016C)
  if debug_atomic > 0 then
    emu:setBreakpoint(function()
      debug_atomic_hits = debug_atomic_hits + 1
      debug_last_address = debug_atomic
    end, debug_atomic)
  end
  if debug_pure > 0 then
    emu:setBreakpoint(function()
      debug_pure_hits = debug_pure_hits + 1
      debug_last_address = debug_pure
    end, debug_pure)
  end
  emu:setBreakpoint(function()
    if phase == "play" and #helper_events < 1024 then
      local h_ok, h = pcall(function() return emu:getRegister("H") end)
      local a_ok, a = pcall(function() return emu:getRegister("A") end)
      local raw_hash, attr_hash, raw_layout, attr_layout =
          packed_signatures()
      helper_events[#helper_events + 1] = {
        frame = play_frames,
        h = h_ok and h or -1,
        a = a_ok and a or -1,
        destination = debug_destination,
        lcdc = emu:read8(0xFF40),
        scx = emu:read8(0xFF43),
        scy = emu:read8(0xFF42),
        dc00 = emu:read8(0xDC00),
        dc01 = emu:read8(0xDC01),
        dc02 = emu:read8(0xDC02),
        dc03 = emu:read8(0xDC03),
        dc0b = emu:read8(0xDC0B),
        dc0c = emu:read8(0xDC0C),
        dc0d = emu:read8(0xDC0D),
        dc0e = emu:read8(0xDC0E),
        dc0f = emu:read8(0xDC0F),
        dc81 = emu:read8(0xDC81),
        ffcf = emu:read8(0xFFCF),
        cache9800 = emu:read8(0xDF53),
        cache9c00 = emu:read8(0xDF57),
        raw_hash = raw_hash,
        attr_hash = attr_hash,
        layout_id = register_layout(raw_layout, attr_layout),
        room = emu:read8(0xFFBD),
      }
    end
  end, debug_decision)
end)

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for offset = 1, 0x1F do emu:write8(base + offset, 0x00) end
  end
end

local function scan_visible()
  local old_vbk = emu:read8(0xFF4F)
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local first_col = math.floor(scx / 8)
  local first_row = math.floor(scy / 8)
  local columns = ((scx % 8) == 0) and 20 or 21
  local rows = ((scy % 8) == 0) and 18 or 19
  local hist = {0, 0, 0, 0, 0, 0, 0, 0}
  local frame_pal1, frame_unexpected, frame_unsafe = 0, 0, 0
  local frame_pal1_details = {}
  local frame_unexpected_details = {}
  local pickup_cells = semantic_pickup_cells()

  for screen_row = 0, rows - 1 do
    local row = (first_row + screen_row) % 32
    for screen_col = 0, columns - 1 do
      local col = (first_col + screen_col) % 32
      local address = base + row * 32 + col
      emu:write8(0xFF4F, 0)
      local tile = emu:read8(address)
      emu:write8(0xFF4F, 1)
      local attr = emu:read8(address)
      local palette = attr & 0x07
      local expected = pickup_cells[address - base]
          or (string.byte(lut, tile + 1) & 0x07)
      hist[palette + 1] = hist[palette + 1] + 1
      checked_cells = checked_cells + 1
      if palette == 1 then
        frame_pal1 = frame_pal1 + 1
        pal1_tiles[tile] = (pal1_tiles[tile] or 0) + 1
        frame_pal1_details[#frame_pal1_details + 1] = string.format(
          "r%d,c%d,t%02X", screen_row, screen_col, tile)
      end
      if palette ~= expected then
        frame_unexpected = frame_unexpected + 1
        if pickup_cells[address - base] then
          unexpected_semantic_pickup_cells =
              unexpected_semantic_pickup_cells + 1
        else
          unexpected_floor_cells = unexpected_floor_cells + 1
          if first_unexpected_floor_frame < 0 then
            first_unexpected_floor_frame = play_frames
            first_unexpected_floor_details = string.format(
              "r%d,c%d,t%02X,p%d,e%d,addr%04X,base%04X",
              screen_row, screen_col, tile, palette, expected,
              address, base)
          end
        end
        frame_unexpected_details[#frame_unexpected_details + 1] =
            string.format(
              "r%d,c%d,t%02X,p%d,e%d",
              screen_row, screen_col, tile, palette, expected)
      end
      if (attr & 0xF8) ~= 0 then frame_unsafe = frame_unsafe + 1 end
    end
  end

  emu:write8(0xFF4F, old_vbk)
  sampled_frames = sampled_frames + 1
  pal1_cells = pal1_cells + frame_pal1
  unexpected_cells = unexpected_cells + frame_unexpected
  unsafe_cells = unsafe_cells + frame_unsafe
  if frame_pal1 > 0 and first_pal1_frame < 0 then
    first_pal1_frame = play_frames
  end
  if (frame_unexpected > 0 or frame_unsafe > 0)
      and first_unexpected_frame < 0 then
    first_unexpected_frame = play_frames
  end
  return hist, frame_pal1, frame_unexpected, frame_unsafe,
      table.concat(frame_pal1_details, ";"),
      table.concat(frame_unexpected_details, ";")
end

local function scan_runtime_lut()
  local mismatches = 0
  local details = {}
  local ff_reads = 0
  for tile = 0, 255 do
    local raw = emu:read8(0xC600 + tile)
    if raw == 0xFF then ff_reads = ff_reads + 1 end
    local actual = raw & 0x07
    local expected = string.byte(lut, tile + 1) & 0x07
    if actual ~= expected then
      mismatches = mismatches + 1
      if #details < 32 then
        details[#details + 1] = string.format(
          "t%02X,p%d,e%d", tile, actual, expected)
      end
    end
  end
  if mismatches > 0 then
    local pc_ok, pc = pcall(function() return emu:getRegister("PC") end)
    local dma_source = emu:read8(0xFF46)
    -- mGBA deliberately makes CPU-bus reads return FF during OAM DMA and
    -- does not expose CPU registers to Lua in this callback. Require the
    -- exact all-FF signature plus the game's known C0/C1 OAM DMA page; a
    -- partially changed table can never enter this exemption.
    local dma_unreadable = ff_reads == 256
        and (dma_source == 0xC0 or dma_source == 0xC1)
    if dma_unreadable then
      runtime_lut_dma_unreadable_frames =
          runtime_lut_dma_unreadable_frames + 1
      if first_runtime_lut_dma_unreadable == "" then
        first_runtime_lut_dma_unreadable = string.format(
          "f%d:pc%s:dma%02X", play_frames,
          pc_ok and string.format("%04X", pc) or "unavailable",
          dma_source)
      end
      return
    end
    runtime_lut_mismatch_frames = runtime_lut_mismatch_frames + 1
    runtime_lut_mismatch_cells = runtime_lut_mismatch_cells + mismatches
    runtime_lut_mismatch_max = math.max(runtime_lut_mismatch_max, mismatches)
    if first_runtime_lut_mismatch_frame < 0 then
      first_runtime_lut_mismatch_frame = play_frames
      first_runtime_lut_mismatch_details = string.format(
          "pc%s:dma%02X:ff%d:%s",
          pc_ok and string.format("%04X", pc) or "unavailable",
          dma_source, ff_reads, table.concat(details, ";"))
    end
  end
end

local function hist_text(hist)
  local parts = {}
  for palette = 0, 7 do
    parts[#parts + 1] = string.format("%d:%d", palette, hist[palette + 1])
  end
  return table.concat(parts, ",")
end

local function active_oam_rects()
  local height = ((emu:read8(0xFF40) & 0x04) ~= 0) and 16 or 8
  local parts = {}
  for slot = 0, 39 do
    local base = 0xFE00 + slot * 4
    local y = emu:read8(base) - 16
    local x = emu:read8(base + 1) - 8
    if x < 160 and x + 8 > 0 and y < 144 and y + height > 0 then
      parts[#parts + 1] = string.format(
        "%d,%d,%d,%d", x, y, x + 7, y + height - 1)
    end
  end
  return table.concat(parts, ";")
end

local function active_pickup_rects()
  local old_vbk = emu:read8(0xFF4F)
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local scx, scy = emu:read8(0xFF43), emu:read8(0xFF42)
  local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
  local x_offset, y_offset = scx % 8, scy % 8
  local parts = {}
  local pickup_cells = semantic_pickup_cells()
  for screen_row = 0, 18 do
    local row = (first_row + screen_row) % 32
    local y = screen_row * 8 - y_offset
    for screen_col = 0, 20 do
      local col = (first_col + screen_col) % 32
      local x = screen_col * 8 - x_offset
      local offset = row * 32 + col
      if pickup_cells[offset] then
        parts[#parts + 1] = string.format(
          "%d,%d,%d,%d", x, y, x + 7, y + 7)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(parts, ";")
end

packed_signatures = function()
  local raw_hash, attr_hash = 0xA55A, 0x5AA5
  local raw_parts, attr_parts = {}, {}
  for offset = 0, 0x23F do
    local tile = emu:read8(0xC1A0 + offset)
    local attr = string.byte(lut, tile + 1) & 0x07
    raw_hash = ((raw_hash * 257) ~ tile) & 0xFFFF
    attr_hash = ((attr_hash * 257) ~ attr) & 0xFFFF
    if trace_layouts then
      raw_parts[#raw_parts + 1] = string.char(tile)
      attr_parts[#attr_parts + 1] = string.char(attr)
    end
  end
  if trace_layouts then
    return raw_hash, attr_hash, table.concat(raw_parts), table.concat(attr_parts)
  end
  return raw_hash, attr_hash, nil, nil
end

local function finish()
  if finished then return end
  finished = true
  local handle = assert(io.open(RESULT, "w"))
  handle:write(string.format("frames=%d\n", play_frames))
  handle:write(string.format("sampled_frames=%d\n", sampled_frames))
  handle:write(string.format("checked_cells=%d\n", checked_cells))
  handle:write(string.format("pal1_cells=%d\n", pal1_cells))
  handle:write(string.format("unexpected_cells=%d\n", unexpected_cells))
  handle:write(string.format(
    "unexpected_semantic_pickup_cells=%d\n",
    unexpected_semantic_pickup_cells))
  handle:write(string.format(
    "unexpected_floor_cells=%d\n", unexpected_floor_cells))
  handle:write(string.format("unsafe_cells=%d\n", unsafe_cells))
  handle:write(string.format(
    "runtime_lut_mismatch_frames=%d\n", runtime_lut_mismatch_frames))
  handle:write(string.format(
    "runtime_lut_mismatch_cells=%d\n", runtime_lut_mismatch_cells))
  handle:write(string.format(
    "runtime_lut_mismatch_max=%d\n", runtime_lut_mismatch_max))
  handle:write(string.format(
    "runtime_lut_dma_unreadable_frames=%d\n",
    runtime_lut_dma_unreadable_frames))
  handle:write(
    "first_runtime_lut_dma_unreadable=" ..
    first_runtime_lut_dma_unreadable .. "\n")
  handle:write(string.format(
    "first_runtime_lut_mismatch_frame=%d\n",
    first_runtime_lut_mismatch_frame))
  handle:write(
    "first_runtime_lut_mismatch_details=" ..
    first_runtime_lut_mismatch_details .. "\n")
  handle:write(string.format("first_pal1_frame=%d\n", first_pal1_frame))
  handle:write(string.format(
    "first_unexpected_frame=%d\n", first_unexpected_frame))
  handle:write(string.format(
    "first_unexpected_floor_frame=%d\n", first_unexpected_floor_frame))
  handle:write(
    "first_unexpected_floor_details=" ..
    first_unexpected_floor_details .. "\n")
  handle:write(string.format("scene_frames=%d\n", scene_frames))
  handle:write(string.format(
    "compiler_unreadable_scene_frames=%d\n",
    compiler_unreadable_scene_frames))
  handle:write(string.format("active_frames=%d\n", active_frames))
  handle:write(string.format("scroll_changes=%d\n", scroll_changes))
  handle:write(string.format("scx_changes=%d\n", scx_changes))
  handle:write(string.format("scy_changes=%d\n", scy_changes))
  handle:write(string.format(
    "source_signature_changes=%d\n", source_signature_changes))
  local final_pc = read_register("PC")
  handle:write(string.format("final_scene=%d\n", emu:read8(0xD880)))
  handle:write(string.format("final_ffc1=%d\n", emu:read8(0xFFC1)))
  handle:write(string.format("final_pc=%d\n", final_pc))
  handle:write(string.format("final_sp=%d\n", read_register("SP")))
  handle:write(string.format("final_svbk=%d\n", emu:read8(0xFF70)))
  handle:write(string.format(
    "final_compiler_unreadable=%d\n",
    compiler_scene_unreadable(final_pc) and 1 or 0))
  handle:write(string.format("debug_copy_hits=%d\n", debug_copy_hits))
  handle:write(string.format("debug_atomic_hits=%d\n", debug_atomic_hits))
  handle:write(string.format("debug_pure_hits=%d\n", debug_pure_hits))
  handle:write(string.format("debug_main_hits=%d\n", debug_main_hits))
  handle:write(string.format("debug_last_address=%d\n", debug_last_address))
  handle:write(string.format("capture_count=%d\n", #captures))
  handle:write(string.format("raster_capture_count=%d\n", #raster_captures))
  handle:write(string.format("helper_event_count=%d\n", #helper_events))
  handle:write(string.format("layout_record_count=%d\n", #layout_records))
  handle:write("first_unexpected_screenshot=" .. first_unexpected_path .. "\n")
  handle:write("first_unexpected_details=" .. first_unexpected_details .. "\n")
  local tile_parts = {}
  for tile = 0, 255 do
    if pal1_tiles[tile] then
      tile_parts[#tile_parts + 1] = string.format(
        "%02X:%d", tile, pal1_tiles[tile])
    end
  end
  handle:write("pal1_tiles=" .. table.concat(tile_parts, ",") .. "\n")
  for _, capture in ipairs(captures) do
    handle:write(string.format(
      "capture=%d|%s|%s|%d|%d|%d\n",
      capture.frame,
      capture.path,
      capture.hist,
      capture.pal1,
      capture.unexpected,
      capture.unsafe))
    handle:write(string.format(
      "pal1_capture=%d|%s\n", capture.frame, capture.pal1_details))
  end
  for _, capture in ipairs(raster_captures) do
    handle:write(string.format(
      "raster_capture=%d|%s|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%s|%s|%s\n",
      capture.frame,
      capture.path,
      capture.lcdc,
      capture.scx,
      capture.scy,
      capture.signature,
      capture.dc00,
      capture.dc01,
      capture.dc02,
      capture.dc03,
      capture.cache9800,
      capture.cache9c00,
      capture.c1a4,
      capture.raw_hash,
      capture.attr_hash,
      capture.layout_id,
      capture.source,
      capture.pickups,
      capture.oam))
  end
  for _, event in ipairs(helper_events) do
    handle:write(string.format(
      "helper_event=%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d\n",
      event.frame,
      event.h,
      event.a,
      event.destination,
      event.lcdc,
      event.scx,
      event.scy,
      event.dc00,
      event.dc01,
      event.dc02,
      event.dc03,
      event.dc0b,
      event.dc0c,
      event.dc0d,
      event.dc0e,
      event.dc0f,
      event.dc81,
      event.ffcf,
      event.cache9800,
      event.cache9c00,
      event.raw_hash,
      event.attr_hash,
      event.layout_id,
      event.room))
  end
  handle:close()
  if trace_layouts then
    local layouts = assert(io.open(OUT .. "/layouts.bin", "wb"))
    for _, record in ipairs(layout_records) do
      layouts:write(record.raw)
      layouts:write(record.attr)
    end
    layouts:close()
  end
  local marker = assert(io.open(DONE, "w"))
  marker:write("OK\n")
  marker:close()
  emu:quit()
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if not seeded and frame >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    -- Match the independently verified natural north route. INTRO is selected
    -- by default; the released pulses traverse GAME START and the stock
    -- score/stage cards without writing scene or controller state.
    local keys = 0
    if frame >= 180 and frame < 186 then keys = keys | KEY_DOWN end
    if frame >= 193 and frame < 199 then keys = keys | KEY_A end
    if frame >= 241 and frame < 247 then keys = keys | KEY_A end
    if frame >= 291 and frame < 297 then keys = keys | KEY_A end
    if frame >= 341 and frame < 347 then keys = keys | KEY_START end
    if frame >= 391 and frame < 397 then keys = keys | KEY_A end
    emu:setKeys(keys)
    if emu:read8(0xD880) == EXPECTED_SCENE
        and emu:read8(0xFFC1) == 1 then
      confirmed = true
      phase = "loading"
    end
    if frame > 900 then finish() end
    return
  end

  -- Keep the route alive while still letting the stock stage run normally.
  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)

  if phase == "loading" then
    emu:write8(0xFFBA, 0)
    emu:setKeys(0)
    if emu:read8(0xD880) == EXPECTED_SCENE
        and emu:read8(0xFFC1) == 1 then
      stable_frames = stable_frames + 1
      if stable_frames >= 120 then
        phase = "play"
        previous_scx = emu:read8(0xFF43)
        previous_scy = emu:read8(0xFF42)
      end
    else
      stable_frames = 0
    end
    if frame > 30000 then finish() end
    return
  end

  play_frames = play_frames + 1
  local scene_pc = read_register("PC")
  local scene = emu:read8(0xD880)
  local compiler_unreadable = compiler_scene_unreadable(scene_pc)
  if scene == EXPECTED_SCENE or compiler_unreadable then
    scene_frames = scene_frames + 1
  end
  if compiler_unreadable then
    compiler_unreadable_scene_frames =
      compiler_unreadable_scene_frames + 1
  end
  if emu:read8(0xFFC1) == 1 then active_frames = active_frames + 1 end

  local movement
  if INPUT_MODE == "patrol" then
    movement = ((play_frames % 240) < 120) and KEY_RIGHT or KEY_LEFT
  elseif INPUT_MODE == "vertical" then
    movement = ((play_frames % 240) < 120) and KEY_DOWN or KEY_UP
  elseif INPUT_MODE == "box" then
    local leg = math.floor((play_frames % 480) / 120)
    if leg == 0 then movement = KEY_RIGHT
    elseif leg == 1 then movement = KEY_DOWN
    elseif leg == 2 then movement = KEY_LEFT
    else movement = KEY_UP end
  else
    movement = KEY_RIGHT
  end
  -- Fire periodically so captures exercise ordinary active gameplay/OAM.
  if (play_frames % 90) < 12 then movement = movement | KEY_A end
  emu:setKeys(movement)

  local scx = emu:read8(0xFF43)
  local scx_changed = scx ~= previous_scx
  if scx_changed then
    scx_changes = scx_changes + 1
    scroll_changes = scroll_changes + 1
  end
  previous_scx = scx
  local scy = emu:read8(0xFF42)
  local scy_changed = scy ~= previous_scy
  if scy_changed then
    scy_changes = scy_changes + 1
    scroll_changes = scroll_changes + 1
  end
  previous_scy = scy
  local source_signature = (
    scx
    ~ scy
    ~ emu:read8(0xC1A4)
  ) & 0xFE
  local signature_changed = source_signature ~= previous_source_signature
  if signature_changed then
    source_signature_changes = source_signature_changes + 1
  end
  previous_source_signature = source_signature
  if scx_changed or scy_changed or signature_changed then raster_window = 12 end

  local hist, frame_pal1, frame_unexpected, frame_unsafe,
      frame_pal1_details, frame_unexpected_now = scan_visible()
  scan_runtime_lut()
  if frame_unexpected > 0 and first_unexpected_path == "" then
    first_unexpected_path = OUT .. "/first-unexpected.png"
    first_unexpected_details = frame_unexpected_now
    emu:screenshot(first_unexpected_path)
  end
  if CAPTURE_FRAMES[play_frames] or play_frames == LIMIT then
    local path = string.format("%s/play-%04d.png", OUT, play_frames)
    emu:screenshot(path)
    captures[#captures + 1] = {
      frame = play_frames,
      path = path,
      hist = hist_text(hist),
      pal1 = frame_pal1,
      unexpected = frame_unexpected,
      unsafe = frame_unsafe,
      pal1_details = frame_pal1_details,
    }
  end
  local current_pickups = active_pickup_rects()
  local current_oam = active_oam_rects()
  local past_pickups = recent_rectangles(
    pickup_rect_history, current_pickups)
  local past_oam = recent_rectangles(oam_rect_history, current_oam)
  if raster_window > 0 then
    local raw_hash, attr_hash, raw_layout, attr_layout = packed_signatures()
    local layout_id = 0
    layout_id = register_layout(raw_layout, attr_layout)
    local path = string.format("%s/raster-%04d.png", OUT, play_frames)
    emu:screenshot(path)
    raster_captures[#raster_captures + 1] = {
      frame = play_frames,
      path = path,
      lcdc = emu:read8(0xFF40),
      scx = scx,
      scy = scy,
      signature = source_signature,
      dc00 = emu:read8(0xDC00),
      dc01 = emu:read8(0xDC01),
      dc02 = emu:read8(0xDC02),
      dc03 = emu:read8(0xDC03),
      cache9800 = emu:read8(0xDF53),
      cache9c00 = emu:read8(0xDF57),
      c1a4 = emu:read8(0xC1A4),
      raw_hash = raw_hash,
      attr_hash = attr_hash,
      layout_id = layout_id,
      source = string.format(
        "%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X",
        emu:read8(0xC1A0),
        emu:read8(0xC1A1),
        emu:read8(0xC1A2),
        emu:read8(0xC1A3),
        emu:read8(0xC1A4),
        emu:read8(0xC1A5),
        emu:read8(0xC1A6),
        emu:read8(0xC1A7)),
      pickups = past_pickups,
      oam = past_oam,
    }
    raster_window = raster_window - 1
  end
  -- Leave several rendered frames after the final screenshot before exiting.
  if play_frames >= LIMIT + 6 then finish() end
end)
