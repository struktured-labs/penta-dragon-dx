-- Cold-boot Stage 1, play continuously, and prove that every visible tile's
-- palette attribute matches the ROM's Stage 1 tile-to-palette table.
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
local pal1_tiles = {}
local first_pal1_frame, first_unexpected_frame = -1, -1
local scene_frames, active_frames = 0, 0
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
local trace_layouts = tonumber(os.getenv("STAGE1_TRACE_LAYOUTS") or "0") ~= 0
local layout_records, layout_seen = {}, {}
local debug_destination = 0
local packed_signatures
local previous_pickup_rects, previous_oam_rects = "", ""

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
        cache9800 = emu:read8(0xDF53),
        cache9c00 = emu:read8(0xDF57),
        raw_hash = raw_hash,
        attr_hash = attr_hash,
        layout_id = register_layout(raw_layout, attr_layout),
        room = emu:read8(0xFFBD),
      }
    end
  end, 0x3485)
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
      local expected = string.byte(lut, tile + 1) & 0x07
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
  emu:write8(0xFF4F, 1)
  for screen_row = 0, 18 do
    local row = (first_row + screen_row) % 32
    local y = screen_row * 8 - y_offset
    for screen_col = 0, 20 do
      local col = (first_col + screen_col) % 32
      local x = screen_col * 8 - x_offset
      local attr = emu:read8(base + row * 32 + col)
      if (attr & 0x07) == 1 then
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
  handle:write(string.format("unsafe_cells=%d\n", unsafe_cells))
  handle:write(string.format("first_pal1_frame=%d\n", first_pal1_frame))
  handle:write(string.format(
    "first_unexpected_frame=%d\n", first_unexpected_frame))
  handle:write(string.format("scene_frames=%d\n", scene_frames))
  handle:write(string.format("active_frames=%d\n", active_frames))
  handle:write(string.format("scroll_changes=%d\n", scroll_changes))
  handle:write(string.format("scx_changes=%d\n", scx_changes))
  handle:write(string.format("scy_changes=%d\n", scy_changes))
  handle:write(string.format(
    "source_signature_changes=%d\n", source_signature_changes))
  handle:write(string.format("final_scene=%d\n", emu:read8(0xD880)))
  handle:write(string.format("final_ffc1=%d\n", emu:read8(0xFFC1)))
  local pc_ok, pc = pcall(function() return emu:getRegister("PC") end)
  local sp_ok, sp = pcall(function() return emu:getRegister("SP") end)
  handle:write(string.format("final_pc=%d\n", pc_ok and pc or -1))
  handle:write(string.format("final_sp=%d\n", sp_ok and sp or -1))
  handle:write(string.format("final_svbk=%d\n", emu:read8(0xFF70)))
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
      "helper_event=%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d|%d\n",
      event.frame,
      event.h,
      event.a,
      event.destination,
      event.lcdc,
      event.scx,
      event.scy,
      event.dc00,
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
  emu:write8(0xDCFD, 0x01)
  if not seeded and frame >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    if frame >= 300 and frame < 306 then emu:setKeys(KEY_START)
    elseif frame >= 360 and frame < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if frame >= 330 then phase = "level_select" end
    return
  end

  if phase == "level_select" and not confirmed then
    emu:write8(0xFFBA, 0)
    seed_sram()
    if frame % 60 >= 10 and frame % 60 < 16 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if emu:read8(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
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
  if emu:read8(0xD880) == EXPECTED_SCENE then
    scene_frames = scene_frames + 1
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
  if raster_window > 0 then
    local raw_hash, attr_hash, raw_layout, attr_layout = packed_signatures()
    local layout_id = 0
    layout_id = register_layout(raw_layout, attr_layout)
    local current_pickups = active_pickup_rects()
    local current_oam = active_oam_rects()
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
      pickups = (
        previous_pickup_rects ~= ""
        and (previous_pickup_rects .. ";" .. current_pickups)
        or current_pickups
      ),
      oam = (
        previous_oam_rects ~= ""
        and (previous_oam_rects .. ";" .. current_oam)
        or current_oam
      ),
    }
    raster_window = raster_window - 1
  end
  previous_pickup_rects = active_pickup_rects()
  previous_oam_rects = active_oam_rects()

  -- Leave several rendered frames after the final screenshot before exiting.
  if play_frames >= LIMIT + 6 then finish() end
end)
