-- Natural cold-boot receipt for pickup attributes in prerecorded Stage 1.
--
-- The title is left completely idle.  The target is the real gameplay-demo
-- segment D880=$02, FFC1=1, DCFD=0; live play has the same scene byte but
-- DCFD=1.  Every visible pickup tile is compared with the ROM-compiled LUT.

local OUT = assert(os.getenv("ATTRACT_PICKUP_OUT"))
local LUT_PATH = assert(os.getenv("ATTRACT_PICKUP_LUT"))
local PICKUP_PATH = assert(os.getenv("ATTRACT_PICKUP_IDS"))
local MAX_FRAMES = tonumber(os.getenv("ATTRACT_PICKUP_MAX_FRAMES") or "10000")
-- Native room transitions can expose D880=$FF for one or two frame callbacks
-- and then resume the same prerecorded Stage-1 scene.  Treat only a sustained
-- departure as the segment boundary so the receipt measures the same edges as
-- the title-reel inventory instead of truncating at an internal transition.
local TARGET_EXIT_STABLE_FRAMES = 8

local function read_blob(path)
  local handle = assert(io.open(path, "rb"))
  local value = assert(handle:read("*a"))
  handle:close()
  assert(#value == 256)
  return value
end

local lut = read_blob(LUT_PATH)
local pickup_ids = read_blob(PICKUP_PATH)
local frame = 0
local target_started = false
local target_start = -1
local target_frames = 0
local target_room = -1
local target_non_target_run = 0
local target_transient_frames = 0
local visible_pickup_cells = 0
local colored_pickup_cells = 0
local neutral_pickup_cells = 0
local pickup_mismatches = 0
local visible_background_cells = 0
local background_palette_mismatches = 0
local nonpickup_palette_mismatches = 0
local unsafe_attribute_cells = 0
local max_background_mismatches_per_frame = 0
local background_mismatch_frames = 0
local last_background_mismatch_frame = -1
local background_mismatch_trace = {}
local background_mismatch_cell_trace = {}
local first_pickup_frame = -1
local first_mismatch = ""
local first_background_mismatch = ""
local pickup_tiles = {}
local captures = {}
local capture_specs = {}
local pickup_frame_trace = {}
local capture_budget = 0
local finished = false
local trace_layouts =
  tonumber(os.getenv("ATTRACT_PICKUP_TRACE_LAYOUTS") or "0") ~= 0
local layout_records, layout_seen, layout_events = {}, {}, {}
local debug_destination = 0

local function snapshot_range(first, last)
  local values = {}
  for address = first, last do
    values[#values + 1] = string.char(emu:read8(address))
  end
  return table.concat(values)
end

local function layout_state_snapshot()
  -- These fixed ranges contain the native room-builder, camera, input-mode,
  -- and HRAM state.  Keep the raw packed layout in the separate deduplicated
  -- records below so cache-key investigations can correlate engine state
  -- without inflating every event by another 576 bytes.
  return snapshot_range(0xC000, 0xC19F)
    .. snapshot_range(0xDC00, 0xDDFF)
    .. snapshot_range(0xFF00, 0xFFFE)
end

local function byte(blob, index)
  return string.byte(blob, index + 1)
end

local function register_layout()
  if not trace_layouts then return 0 end
  local raw, attr = {}, {}
  for offset = 0, 0x23F do
    local tile = emu:read8(0xC1A0 + offset)
    raw[#raw + 1] = string.char(tile)
    attr[#attr + 1] = string.char(byte(lut, tile) & 0x07)
  end
  local raw_blob = table.concat(raw)
  if not layout_seen[raw_blob] then
    layout_records[#layout_records + 1] = {
      raw = raw_blob,
      attr = table.concat(attr),
    }
    layout_seen[raw_blob] = #layout_records
  end
  return layout_seen[raw_blob]
end

pcall(function()
  emu:setBreakpoint(function() debug_destination = 0x9C end, 0x42A0)
  emu:setBreakpoint(function() debug_destination = 0x98 end, 0x42A5)
  emu:setBreakpoint(function()
    if trace_layouts
        and emu:read8(0xD880) == 0x02
        and emu:read8(0xFFC1) == 1
        and emu:read8(0xDCFD) == 0
        and #layout_events < 2048 then
      layout_events[#layout_events + 1] = {
        frame = frame,
        destination = debug_destination,
        dc0e = emu:read8(0xDC0E),
        room = emu:read8(0xFFBD),
        cache9800 = emu:read8(0xDF53),
        cache9c00 = emu:read8(0xDF57),
        layout = register_layout(),
        state = layout_state_snapshot(),
      }
    end
  end, 0x3485)
end)

local function add_capture(label, cells)
  local path = string.format("%s-%s-f%05d.png", OUT, label, frame)
  emu:screenshot(path)
  captures[#captures + 1] = path
  local specs = {}
  for _, cell in ipairs(cells or {}) do
    specs[#specs + 1] = string.format(
      "%d,%d,%d,%02X",
      cell.screen_x, cell.screen_y,
      byte(lut, cell.tile) & 0x07, cell.tile)
  end
  capture_specs[#capture_specs + 1] = path .. "|" .. table.concat(specs, ";")
end

local function inspect_visible()
  local lcdc = emu:read8(0xFF40)
  local scy = emu:read8(0xFF42)
  local scx = emu:read8(0xFF43)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local old_vbk = emu:read8(0xFF4F)
  local cells = {}
  local background_cells = {}
  local sub_x = scx & 7
  local sub_y = scy & 7

  emu:write8(0xFF4F, 0)
  for row = 0, 18 do
    for column = 0, 20 do
      local screen_x = column * 8 - sub_x
      local screen_y = row * 8 - sub_y
      local map_y = ((scy + row * 8) >> 3) & 0x1F
      local map_x = ((scx + column * 8) >> 3) & 0x1F
      local offset = map_y * 32 + map_x
      local tile = emu:read8(base + offset)
      if screen_x < 160 and screen_x + 8 > 0
          and screen_y < 144 and screen_y + 8 > 0 then
        local cell = {
          offset = offset,
          tile = tile,
          screen_x = screen_x,
          screen_y = screen_y,
        }
        background_cells[#background_cells + 1] = cell
        if byte(pickup_ids, tile) ~= 0 then
          cells[#cells + 1] = cell
        end
      end
    end
  end

  local frame_colored = 0
  local frame_neutral = 0
  local frame_mismatches = 0
  local frame_background_mismatches = 0
  emu:write8(0xFF4F, 1)
  for _, cell in ipairs(background_cells) do
    local attr = emu:read8(base + cell.offset)
    local actual = attr & 0x07
    local expected = byte(lut, cell.tile) & 0x07
    visible_background_cells = visible_background_cells + 1
    if actual ~= expected then
      background_palette_mismatches = background_palette_mismatches + 1
      frame_background_mismatches = frame_background_mismatches + 1
      if byte(pickup_ids, cell.tile) == 0 then
        nonpickup_palette_mismatches = nonpickup_palette_mismatches + 1
      end
      if first_background_mismatch == "" then
        first_background_mismatch = string.format(
          "f%d:%04X+%03X:%02X:%d>%d:screen=%d,%d",
          frame, base, cell.offset, cell.tile, actual, expected,
          cell.screen_x, cell.screen_y)
      end
      if #background_mismatch_cell_trace < 256 then
        background_mismatch_cell_trace[#background_mismatch_cell_trace + 1] =
          string.format(
            "%d,%04X,%03X,%02X,%d,%d,%d,%d,%02X",
            frame, base, cell.offset, cell.tile, actual, expected,
            cell.screen_x, cell.screen_y, emu:read8(0xFFBD))
      end
    end
    if (attr & 0xF8) ~= 0 then
      unsafe_attribute_cells = unsafe_attribute_cells + 1
    end
  end
  max_background_mismatches_per_frame = math.max(
    max_background_mismatches_per_frame, frame_background_mismatches)
  if frame_background_mismatches > 0 then
    background_mismatch_frames = background_mismatch_frames + 1
    last_background_mismatch_frame = frame
    if #background_mismatch_trace < 128 then
      background_mismatch_trace[#background_mismatch_trace + 1] =
        string.format(
          "%d,%d,%02X,%04X,%02X,%02X,%02X,%02X",
          frame, frame_background_mismatches, emu:read8(0xFFBD), base,
          emu:read8(0xDF4E), emu:read8(0xDF7C), scx, scy)
    end
  end
  for _, cell in ipairs(cells) do
    local actual = emu:read8(base + cell.offset) & 0x07
    local expected = byte(lut, cell.tile) & 0x07
    visible_pickup_cells = visible_pickup_cells + 1
    pickup_tiles[cell.tile] = true
    if actual == expected and expected ~= 0 then
      colored_pickup_cells = colored_pickup_cells + 1
      frame_colored = frame_colored + 1
    end
    if actual == 0 then
      neutral_pickup_cells = neutral_pickup_cells + 1
      frame_neutral = frame_neutral + 1
    end
    if actual ~= expected then
      pickup_mismatches = pickup_mismatches + 1
      frame_mismatches = frame_mismatches + 1
      if first_mismatch == "" then
        first_mismatch = string.format(
          "f%d:%04X+%03X:%02X:%d>%d:screen=%d,%d",
          frame, base, cell.offset, cell.tile, actual, expected,
          cell.screen_x, cell.screen_y)
        add_capture("first-mismatch", cells)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)

  if frame_background_mismatches > 0
      and background_palette_mismatches == frame_background_mismatches then
    add_capture("first-background-mismatch", cells)
  end

  if #cells > 0 and first_pickup_frame < 0 then
    first_pickup_frame = frame
    capture_budget = 6
  end
  if #cells > 0 and #pickup_frame_trace < 512 then
    pickup_frame_trace[#pickup_frame_trace + 1] = string.format(
      "%d,%d,%d,%d,%d,%04X,%02X,%02X,%02X,%02X,%02X,%02X,%02X,%02X",
      frame, #cells, frame_colored, frame_neutral, frame_mismatches,
      base, emu:read8(0xDF4E), emu:read8(0xDF04), scx, scy,
      emu:read8(0xFFB7), emu:read8(0xFFBA), emu:read8(0xD880),
      emu:read8(0xFFC1))
  end
  if capture_budget > 0 then
    add_capture("pickup", cells)
    capture_budget = capture_budget - 1
  end
  if target_frames == 600 or target_frames == 1200 or target_frames == 1800 then
    add_capture("late-clean", cells)
  end
end

local function finish(status)
  if finished then return end
  finished = true
  local ids = {}
  for tile, _ in pairs(pickup_tiles) do ids[#ids + 1] = tile end
  table.sort(ids)
  local id_text = {}
  for _, tile in ipairs(ids) do id_text[#id_text + 1] = string.format("%02X", tile) end
  local report = assert(io.open(OUT .. ".txt", "w"))
  report:write("status=" .. status .. "\n")
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format("target_start=%d\n", target_start))
  report:write(string.format("target_frames=%d\n", target_frames))
  report:write(string.format(
    "target_transient_frames=%d\n", target_transient_frames))
  report:write(string.format("target_room=%02X\n", target_room & 0xFF))
  report:write(string.format("first_pickup_frame=%d\n", first_pickup_frame))
  report:write(string.format("visible_pickup_cells=%d\n", visible_pickup_cells))
  report:write(string.format("colored_pickup_cells=%d\n", colored_pickup_cells))
  report:write(string.format("neutral_pickup_cells=%d\n", neutral_pickup_cells))
  report:write(string.format("pickup_mismatches=%d\n", pickup_mismatches))
  report:write("first_mismatch=" .. first_mismatch .. "\n")
  report:write(string.format(
    "visible_background_cells=%d\n", visible_background_cells))
  report:write(string.format(
    "background_palette_mismatches=%d\n", background_palette_mismatches))
  report:write(string.format(
    "nonpickup_palette_mismatches=%d\n", nonpickup_palette_mismatches))
  report:write(string.format(
    "unsafe_attribute_cells=%d\n", unsafe_attribute_cells))
  report:write(string.format(
    "max_background_mismatches_per_frame=%d\n",
    max_background_mismatches_per_frame))
  report:write(string.format(
    "background_mismatch_frames=%d\n", background_mismatch_frames))
  report:write(string.format(
    "last_background_mismatch_frame=%d\n", last_background_mismatch_frame))
  report:write(
    "first_background_mismatch=" .. first_background_mismatch .. "\n")
  for _, value in ipairs(background_mismatch_trace) do
    report:write("background_mismatch_frame=" .. value .. "\n")
  end
  for _, value in ipairs(background_mismatch_cell_trace) do
    report:write("background_mismatch_cell=" .. value .. "\n")
  end
  report:write("pickup_tiles=" .. table.concat(id_text, ",") .. "\n")
  for _, value in ipairs(pickup_frame_trace) do
    report:write("pickup_frame=" .. value .. "\n")
  end
  for _, path in ipairs(captures) do report:write("capture=" .. path .. "\n") end
  for _, value in ipairs(capture_specs) do
    report:write("capture_spec=" .. value .. "\n")
  end
  for _, event in ipairs(layout_events) do
    report:write(string.format(
      "layout_event=%d|%d|%d|%d|%d|%d|%d\n",
      event.frame, event.destination, event.dc0e, event.room,
      event.cache9800, event.cache9c00, event.layout))
  end
  report:close()
  if trace_layouts then
    local layouts = assert(io.open(OUT .. "-layouts.bin", "wb"))
    for _, record in ipairs(layout_records) do
      layouts:write(record.raw)
      layouts:write(record.attr)
    end
    layouts:close()
    local states = assert(io.open(OUT .. "-states.bin", "wb"))
    for _, event in ipairs(layout_events) do states:write(event.state) end
    states:close()
  end
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  local target = (
    emu:read8(0xD880) == 0x02
    and emu:read8(0xFFC1) == 1
    and emu:read8(0xDCFD) == 0
  )
  if target then
    if not target_started then
      target_started = true
      target_start = frame
      target_room = emu:read8(0xFFBD)
    end
    if target_non_target_run > 0 then
      target_transient_frames = target_transient_frames + target_non_target_run
      target_non_target_run = 0
    end
    target_frames = target_frames + 1
    inspect_visible()
  elseif target_started and target_frames >= 120 then
    target_non_target_run = target_non_target_run + 1
    target_frames = target_frames + 1
    if target_non_target_run >= TARGET_EXIT_STABLE_FRAMES then
      target_frames = target_frames - target_non_target_run
      finish("ok")
      return
    end
  end
  if frame >= MAX_FRAMES then
    finish(target_started and "target-did-not-exit" or "target-timeout")
  end
end)
