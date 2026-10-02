-- Detect a hardware-window frame exposed before the native 6x20 HUD copy or
-- its candidate-bound VBK1 attributes are ready.
--
-- The game prepares the complete item HUD at C4E0 and copies it to the map
-- selected by LCDC.6.  A visible window whose first six rows differ from that
-- buffer renders stale dungeon tiles as walls/gaps, with the native fixed HUD
-- sprite at the lower left. This probe checks both planes on every visible
-- frame, including the first frame of SELECT entry and the final exit edge.
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

local OUT = assert(os.getenv("MENU_WINDOW_ORDER_OUT"))
local SCREENSHOT = assert(os.getenv("MENU_WINDOW_ORDER_SCREENSHOT"))
local LIMIT = tonumber(os.getenv("MENU_WINDOW_ORDER_FRAMES") or "1280")
local OPEN_KEY_NAME = os.getenv("MENU_WINDOW_ORDER_KEY") or "select"
local OPEN_FRAME = tonumber(os.getenv("MENU_WINDOW_ORDER_OPEN_FRAME") or "1200")
local CLOSE_FRAME = tonumber(os.getenv("MENU_WINDOW_ORDER_CLOSE_FRAME") or "-1")
local MOVE_KEY_NAME = os.getenv("MENU_WINDOW_ORDER_MOVE") or "none"
local FIRE_EVERY = tonumber(os.getenv("MENU_WINDOW_ORDER_FIRE_EVERY") or "0")
local STALE_FRAME = tonumber(os.getenv("MENU_WINDOW_ORDER_STALE_FRAME") or "-1")
local STALE_SCENE_TEXT = os.getenv("MENU_WINDOW_ORDER_STALE_SCENE") or ""
local STALE_SCENE = STALE_SCENE_TEXT ~= "" and tonumber(STALE_SCENE_TEXT) or nil
local FORCE_ALIAS_FRAME = tonumber(
  os.getenv("MENU_WINDOW_ORDER_FORCE_ALIAS_FRAME") or "-1")
local FORCE_COMMIT_FRAME = tonumber(
  os.getenv("MENU_WINDOW_ORDER_FORCE_COMMIT_FRAME") or "-1")
local ATTR_LUT_PATH = assert(os.getenv("MENU_WINDOW_ORDER_ATTR_LUT"))
local ATTR_LUT_SHA256 = assert(
  os.getenv("MENU_WINDOW_ORDER_ATTR_LUT_SHA256"))
local ATTR_MODE = assert(os.getenv("MENU_WINDOW_ORDER_ATTR_MODE"))
local ROM_PATH = assert(os.getenv("MENU_WINDOW_ORDER_ROM"))
local ROM_SHA256 = assert(os.getenv("MENU_WINDOW_ORDER_ROM_SHA256"))
local attr_lut_file = assert(io.open(ATTR_LUT_PATH, "rb"))
local attr_lut = assert(attr_lut_file:read("*a"))
attr_lut_file:close()
assert(#attr_lut == 0x100)
local CONTENT_EXPECTED_PATH = assert(
  os.getenv("MENU_WINDOW_ORDER_CONTENT_EXPECTED"))
local CONTENT_MASK_PATH = assert(
  os.getenv("MENU_WINDOW_ORDER_CONTENT_MASK"))
local CONTENT_FIXTURE_SHA256 = assert(
  os.getenv("MENU_WINDOW_ORDER_CONTENT_FIXTURE_SHA256"))
local CONTENT_SCREENSHOT_PREFIX = assert(
  os.getenv("MENU_WINDOW_ORDER_CONTENT_SCREENSHOT_PREFIX"))
local CONTENT_SAMPLE_AGES_TEXT = assert(
  os.getenv("MENU_WINDOW_ORDER_CONTENT_SAMPLE_AGES"))
local content_expected_file = assert(io.open(CONTENT_EXPECTED_PATH, "rb"))
local content_expected = assert(content_expected_file:read("*a"))
content_expected_file:close()
local content_mask_file = assert(io.open(CONTENT_MASK_PATH, "rb"))
local content_mask = assert(content_mask_file:read("*a"))
content_mask_file:close()
assert(#content_expected == 120)
assert(#content_mask == 120)
local content_sample_ages = {}
for age in string.gmatch(CONTENT_SAMPLE_AGES_TEXT, "[^,]+") do
  content_sample_ages[assert(tonumber(age))] = true
end

local KEY_A = 0x01
local KEY_SELECT = 0x04
local KEY_START = 0x08
local KEY_DOWN = 0x80
local OPEN_KEY = (OPEN_KEY_NAME == "start") and KEY_START
  or (OPEN_KEY_NAME == "combo") and (KEY_START | KEY_SELECT)
  or KEY_SELECT
local MOVE_KEYS = {
  none = 0,
  right = 0x10,
  left = 0x20,
  up = 0x40,
  down = 0x80,
}
local MOVE_KEY = assert(MOVE_KEYS[MOVE_KEY_NAME])

local frame = 0
local window_frames = 0
local bad_frames = 0
local window_frames_after_close = 0
local stale_injected = false
local stale_window_frames_after_grace = 0
local map_alias_frames = 0
local forced_commit = false
local forced_commit_consumed = false
local forced_commit_target, forced_commit_scx, forced_commit_scy = nil, nil, nil
local COMMIT_PROTOCOL = os.getenv('MENU_WINDOW_ORDER_COMMIT_PROTOCOL') or ''
local COMMIT_POST_PC = tonumber(os.getenv('MENU_WINDOW_ORDER_COMMIT_POST_PC') or '0')

local function inject_completed_map()
  assert(COMMIT_PROTOCOL == 'ffc4-absolute-ready-page-scy-df5c-scx-r443')
  assert((emu:read8(0xFFC4) & 0x60) == 0, 'cannot replace an outstanding map transaction')
  local wram = assert(emu.memory.wram)
  forced_commit_target = (emu:read8(0xFF40) & 0x40) ~= 0 and 0x08 or 0x40
  forced_commit_scx = wram:read8(0x1C00) & 0x0F
  forced_commit_scy = wram:read8(0x1C02) & 0x0F
  emu:write8(0xDF5C, forced_commit_scx)
  emu:write8(0xFFC4, 0xC0 | (forced_commit_target == 0x08 and 0x10 or 0) | forced_commit_scy)
  forced_commit = true
end

local function observe_completed_map()
  if not forced_commit or forced_commit_consumed or emu:read8(0xFF99) ~= 13 then return end
  -- Only the actual post-store CPU boundary can attest consumption. A
  -- cleared latch at an unrelated frame is not evidence of publication.
  forced_commit_consumed = emu:read8(0xFFC4) == 0
    and (emu:read8(0xFF40) & 0x48) == forced_commit_target
    and emu:read8(0xFF42) == forced_commit_scy
    and (emu:read8(0xFF97) == 2 or emu:read8(0xFF43) == forced_commit_scx)
end

if FORCE_COMMIT_FRAME >= 0 then
  assert(COMMIT_POST_PC > 0)
  emu:setBreakpoint(observe_completed_map, COMMIT_POST_PC)
end
local post_close_selector_checked_frames = 0
local post_close_selector_alias_frames = 0
local post_close_hud_leak_frames = 0
local attr_checked_frames = 0
local attr_bad_frames = 0
local attr_mismatch_cells = 0
local attr_unsafe_cells = 0
local attr_entry_frames = 0
local attr_settled_frames = 0
local attr_exit_frames = 0
local window_hidden_at_close_frames = 0
local content_checked_frames = 0
local content_bad_frames = 0
local content_source_mismatch_cells = 0
local content_window_mismatch_cells = 0
local worst_content_source_mismatches = 0
local worst_content_window_mismatches = 0
local first_bad = nil
local first_visible = nil
local first_alias = nil
local first_post_close_alias = nil
local first_attr_bad = nil
local first_content_bad = nil
local worst_mismatches = 0
local worst_attr_mismatches = 0
local transition_log = {}
local content_raster_trace = {}
local last_signature = ""
local raw_vram = assert(emu.memory.vram)
local finished = false

local function pulse(lo, hi, mask)
  return (frame >= lo and frame < hi) and mask or 0
end

local function window_map(lcdc)
  return ((lcdc & 0x40) ~= 0) and 0x9C00 or 0x9800
end

local function mismatch_count(base)
  local mismatches = 0
  for row = 0, 5 do
    for col = 0, 19 do
      local wanted = emu:read8(0xC4E0 + row * 20 + col)
      local actual = raw_vram:read8(base - 0x8000 + row * 32 + col)
      if actual ~= wanted then mismatches = mismatches + 1 end
    end
  end
  return mismatches
end

local function content_mismatch_count(base)
  local source_mismatches, window_mismatches, examples = 0, 0, {}
  for row = 0, 5 do
    for col = 0, 19 do
      local index = row * 20 + col
      if string.byte(content_mask, index + 1) ~= 0 then
        local expected = string.byte(content_expected, index + 1)
        local source = emu:read8(0xC4E0 + index)
        local actual = raw_vram:read8(
          base - 0x8000 + row * 32 + col)
        if source ~= expected then source_mismatches = source_mismatches + 1 end
        if actual ~= expected then window_mismatches = window_mismatches + 1 end
        if (source ~= expected or actual ~= expected) and #examples < 16 then
          examples[#examples + 1] = string.format(
            "r%d,c%d,s%02X,w%02X,e%02X", row, col, source, actual,
            expected)
        end
      end
    end
  end
  return source_mismatches, window_mismatches, table.concat(examples, ";")
end

local function dump_grid(path, base, packed)
  local handle = assert(io.open(path, "wb"))
  for row = 0, 5 do
    local width = packed and 20 or 32
    local row_base = packed and (0xC4E0 + row * 20) or (base + row * 32)
    for col = 0, width - 1 do
      local value
      if packed then
        value = emu:read8(row_base + col)
      else
        value = raw_vram:read8(row_base - 0x8000 + col)
      end
      handle:write(string.char(value))
    end
  end
  handle:close()
end

local function attribute_mismatch_count(base)
  local tiles = {}
  local mismatches, unsafe, examples = 0, 0, {}
  for row = 0, 5 do
    for col = 0, 19 do
      local index = row * 20 + col
      tiles[index] = raw_vram:read8(
        base - 0x8000 + row * 32 + col)
    end
  end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for row = 0, 5 do
    for col = 0, 19 do
      local index = row * 20 + col
      local tile = tiles[index]
      -- mGBA's Lua raw-VRAM view exposes bank 0 only in this build; reads at
      -- +$2000 return $FF and previously manufactured a 120-cell failure.
      -- The frame callback runs after the rendered frame, so select VBK1 and
      -- read through the normal CGB VRAM aperture just like the established
      -- Stage-1 palette oracle does.
      local actual = emu:read8(base + row * 32 + col)
      local expected = string.byte(attr_lut, tile + 1)
      if actual ~= expected then
        mismatches = mismatches + 1
        if #examples < 16 then
          examples[#examples + 1] = string.format(
            "r%d,c%d,t%02X,a%02X,e%02X", row, col, tile, actual,
            expected)
        end
      end
      if (actual & 0xF8) ~= 0 then unsafe = unsafe + 1 end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatches, unsafe, table.concat(examples, ";")
end

local function dump_window_attrs(path, base)
  local handle = assert(io.open(path, "wb"))
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for row = 0, 5 do
    for col = 0, 19 do
      handle:write(string.char(emu:read8(base + row * 32 + col)))
    end
  end
  emu:write8(0xFF4F, old_vbk)
  handle:close()
end

local function dump_expected_attrs(path, base)
  local handle = assert(io.open(path, "wb"))
  for row = 0, 5 do
    for col = 0, 19 do
      local tile = raw_vram:read8(
        base - 0x8000 + row * 32 + col)
      handle:write(string.char(string.byte(attr_lut, tile + 1)))
    end
  end
  handle:close()
end

local function dump_bytes(path, reader, base, length)
  local handle = assert(io.open(path, "wb"))
  for offset = 0, length - 1 do
    handle:write(string.char(reader(base + offset)))
  end
  handle:close()
end

local function finish()
  if finished then return end
  finished = true
  emu:screenshot(OUT .. ".final.png")
  dump_bytes(OUT .. ".c1a0.bin", function(address)
    return emu:read8(address)
  end, 0xC1A0, 0x240)
  dump_bytes(OUT .. ".vram9800.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x9800, 0x400)
  dump_bytes(OUT .. ".vram9c00.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x9C00, 0x400)
  local handle = assert(io.open(OUT, "w"))
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("window_frames=%d\n", window_frames))
  handle:write(string.format("bad_frames=%d\n", bad_frames))
  handle:write(string.format(
    "window_frames_after_close=%d\n", window_frames_after_close))
  handle:write(string.format("stale_injected=%d\n", stale_injected and 1 or 0))
  handle:write(string.format(
    "stale_scene=%s\n",
    STALE_SCENE and string.format("%02X", STALE_SCENE) or "native"))
  handle:write(string.format(
    "stale_window_frames_after_grace=%d\n",
    stale_window_frames_after_grace))
  handle:write(string.format("worst_mismatches=%d\n", worst_mismatches))
  handle:write(string.format("map_alias_frames=%d\n", map_alias_frames))
  handle:write(string.format("forced_commit=%d\n", forced_commit and 1 or 0))
  handle:write('forced_commit_protocol=' .. COMMIT_PROTOCOL .. '\n')
  handle:write(string.format(
    "forced_commit_consumed=%d\n", forced_commit_consumed and 1 or 0))
  handle:write(string.format(
    "post_close_selector_checked_frames=%d\n",
    post_close_selector_checked_frames))
  handle:write(string.format(
    "post_close_selector_alias_frames=%d\n",
    post_close_selector_alias_frames))
  handle:write(string.format(
    "post_close_hud_leak_frames=%d\n", post_close_hud_leak_frames))
  handle:write(string.format("route_frame_limit=%d\n", LIMIT))
  handle:write(string.format("route_open_frame=%d\n", OPEN_FRAME))
  handle:write(string.format("route_close_frame=%d\n", CLOSE_FRAME))
  handle:write(string.format(
    "route_force_alias_frame=%d\n", FORCE_ALIAS_FRAME))
  handle:write(string.format(
    "route_force_commit_frame=%d\n", FORCE_COMMIT_FRAME))
  handle:write(string.format("route_stale_frame=%d\n", STALE_FRAME))
  handle:write("rom=" .. ROM_PATH .. "\n")
  handle:write("rom_sha256=" .. ROM_SHA256 .. "\n")
  handle:write("attr_mode=" .. ATTR_MODE .. "\n")
  handle:write("attr_lut_sha256=" .. ATTR_LUT_SHA256 .. "\n")
  handle:write(string.format(
    "attr_checked_frames=%d\n", attr_checked_frames))
  handle:write(string.format("attr_bad_frames=%d\n", attr_bad_frames))
  handle:write(string.format(
    "attr_mismatch_cells=%d\n", attr_mismatch_cells))
  handle:write(string.format("attr_unsafe_cells=%d\n", attr_unsafe_cells))
  handle:write(string.format("attr_entry_frames=%d\n", attr_entry_frames))
  handle:write(string.format(
    "attr_settled_frames=%d\n", attr_settled_frames))
  handle:write(string.format("attr_exit_frames=%d\n", attr_exit_frames))
  handle:write(string.format(
    "window_hidden_at_close_frames=%d\n", window_hidden_at_close_frames))
  handle:write(string.format(
    "worst_attr_mismatches=%d\n", worst_attr_mismatches))
  handle:write(
    "content_mode=" .. (
      STALE_FRAME < 0 and "native-fixture" or "disabled-stale-injection"
    ) .. "\n")
  handle:write("content_fixture_sha256=" .. CONTENT_FIXTURE_SHA256 .. "\n")
  handle:write(string.format(
    "content_checked_frames=%d\n", content_checked_frames))
  handle:write(string.format(
    "content_bad_frames=%d\n", content_bad_frames))
  handle:write(string.format(
    "content_source_mismatch_cells=%d\n", content_source_mismatch_cells))
  handle:write(string.format(
    "content_window_mismatch_cells=%d\n", content_window_mismatch_cells))
  handle:write(string.format(
    "worst_content_source_mismatches=%d\n",
    worst_content_source_mismatches))
  handle:write(string.format(
    "worst_content_window_mismatches=%d\n",
    worst_content_window_mismatches))
  handle:write(
    "content_raster_trace=" .. table.concat(content_raster_trace, ";") .. "\n")
  handle:write(string.format(
    "final_state=scene:%02X room:%02X ffe4:%02X lcdc:%02X " ..
    "scx:%02X scy:%02X wx:%02X wy:%02X dc00:%02X dc01:%02X " ..
    "dc02:%02X dc03:%02X c1a4:%02X\n",
    emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFFE4),
    emu:read8(0xFF40), emu:read8(0xFF43), emu:read8(0xFF42),
    emu:read8(0xFF4B), emu:read8(0xFF4A), emu:read8(0xDC00),
    emu:read8(0xDC01), emu:read8(0xDC02), emu:read8(0xDC03),
    emu:read8(0xC1A4)))
  handle:write("transitions=" .. table.concat(transition_log, ";") .. "\n")
  if first_bad then
    handle:write(string.format(
      "first_bad=frame:%d scene:%02X room:%02X lcdc:%02X wy:%02X " ..
      "map:%04X dc0b:%02X ffda:%02X mismatches:%d\n",
      first_bad.frame, first_bad.scene, first_bad.room, first_bad.lcdc,
      first_bad.wy, first_bad.map, first_bad.dc0b, first_bad.ffda,
      first_bad.mismatches))
  else
    handle:write("first_bad=none\n")
  end
  if first_visible then
    handle:write(string.format(
      "first_visible=frame:%d scene:%02X room:%02X lcdc:%02X wy:%02X " ..
      "map:%04X mismatches:%d\n",
      first_visible.frame, first_visible.scene, first_visible.room,
      first_visible.lcdc, first_visible.wy, first_visible.map,
      first_visible.mismatches))
  else
    handle:write("first_visible=none\n")
  end
  if first_alias then
    handle:write(string.format(
      "first_alias=frame:%d lcdc:%02X map:%04X\n",
      first_alias.frame, first_alias.lcdc, first_alias.map))
  else
    handle:write("first_alias=none\n")
  end
  if first_post_close_alias then
    handle:write(string.format(
      "first_post_close_alias=frame:%d lcdc:%02X bg:%04X window:%04X " ..
      "hud_matches:%d\n",
      first_post_close_alias.frame, first_post_close_alias.lcdc,
      first_post_close_alias.bg, first_post_close_alias.window,
      first_post_close_alias.hud_matches))
  else
    handle:write("first_post_close_alias=none\n")
  end
  if first_attr_bad then
    handle:write(string.format(
      "first_attr_bad=frame:%d scene:%02X room:%02X lcdc:%02X " ..
      "map:%04X mismatches:%d unsafe:%d examples:%s\n",
      first_attr_bad.frame, first_attr_bad.scene, first_attr_bad.room,
      first_attr_bad.lcdc, first_attr_bad.map, first_attr_bad.mismatches,
      first_attr_bad.unsafe, first_attr_bad.examples))
  else
    handle:write("first_attr_bad=none\n")
  end
  if first_content_bad then
    handle:write(string.format(
      "first_content_bad=frame:%d scene:%02X room:%02X lcdc:%02X " ..
      "map:%04X source_mismatches:%d window_mismatches:%d examples:%s\n",
      first_content_bad.frame, first_content_bad.scene,
      first_content_bad.room, first_content_bad.lcdc,
      first_content_bad.map, first_content_bad.source_mismatches,
      first_content_bad.window_mismatches, first_content_bad.examples))
  else
    handle:write("first_content_bad=none\n")
  end
  handle:close()
  os.exit(0)
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  local keys = 0
  keys = keys | pulse(180, 186, KEY_DOWN) -- Intro is selected by default.
  keys = keys | pulse(193, 199, KEY_A)
  -- Retain the established cold-start route through the stage card.
  keys = keys | pulse(241, 247, KEY_A)
  keys = keys | pulse(291, 297, KEY_A)
  keys = keys | pulse(341, 347, 0x08)
  keys = keys | pulse(391, 397, KEY_A)
  if STALE_FRAME < 0 then
    keys = keys | pulse(OPEN_FRAME, OPEN_FRAME + 6, OPEN_KEY)
  end
  if STALE_FRAME < 0 and CLOSE_FRAME >= 0 then
    keys = keys | pulse(CLOSE_FRAME, CLOSE_FRAME + 6, OPEN_KEY)
  end
  if frame >= 600 then keys = keys | MOVE_KEY end
  if FIRE_EVERY > 0 and frame >= OPEN_FRAME + 50
      and frame % FIRE_EVERY == 0 then
    keys = keys | KEY_A
  end
  emu:setKeys(keys)

  if frame == FORCE_ALIAS_FRAME then
    -- Deterministic parity boundary: switch the displayed BG onto the map
    -- already owned by the visible Window, without changing Window. This is
    -- the exact failure direction captured on Pocket: the HUD remains intact
    -- while its colored icon rows leak into the gameplay plane above it.
    local lcdc = emu:read8(0xFF40)
    if (lcdc & 0x40) ~= 0 then
      lcdc = lcdc | 0x08
    else
      lcdc = lcdc & 0xF7
    end
    emu:write8(0xFF40, lcdc)
  end

  if frame == FORCE_COMMIT_FRAME then
    -- Exercise the ROM's real completed-map VBlank transaction on the menu
    -- close edge.  Request the physical page currently owned by Window. r356
    -- changed only LCDC.3 and therefore left both selectors aliased; the
    -- paired transaction must move LCDC.6 to the opposite page atomically.
    inject_completed_map()
  end

  if frame == STALE_FRAME then
    -- Recreate the exact captured failure state without altering room data:
    -- live Stage 1, stock menu flag clear, stale hardware Window enabled.
    if STALE_SCENE ~= nil then emu:write8(0xD880, STALE_SCENE) end
    emu:write8(0xFFE4, 0)
    emu:write8(0xFF4B, 7)
    emu:write8(0xFF4A, 0x60)
    emu:write8(0xFF40, emu:read8(0xFF40) | 0x20)
    stale_injected = true
  end
  if STALE_FRAME >= 0 and frame == STALE_FRAME + 2 then
    emu:screenshot(OUT .. ".recovered.png")
  end

  if emu:read8(0xFFC1) == 1 then
    -- Keep the route alive without changing room/window state.
    native_assistance.write(0xDCBB, 0xFF)
  end

  local lcdc = emu:read8(0xFF40)
  local wy = emu:read8(0xFF4A)
  local base = window_map(lcdc)
  local enabled = (lcdc & 0x20) ~= 0 and wy < 144
  local mismatches = enabled and mismatch_count(base) or 0
  local attr_mismatches, unsafe_attrs, attr_examples = 0, 0, ""
  if enabled then
    attr_mismatches, unsafe_attrs, attr_examples =
      attribute_mismatch_count(base)
  end
  local signature = string.format(
    "f%d:%02X/%02X/%04X/%d", frame, lcdc, wy, base, mismatches)
  local stable = string.format("%02X/%02X/%04X/%d", lcdc, wy, base, mismatches)
  if stable ~= last_signature and #transition_log < 256 then
    transition_log[#transition_log + 1] = signature
    last_signature = stable
  end

  if enabled then
    window_frames = window_frames + 1
    if STALE_FRAME < 0 then
      content_checked_frames = content_checked_frames + 1
      local source_mismatches, window_mismatches, content_examples =
        content_mismatch_count(base)
      content_source_mismatch_cells =
        content_source_mismatch_cells + source_mismatches
      content_window_mismatch_cells =
        content_window_mismatch_cells + window_mismatches
      worst_content_source_mismatches = math.max(
        worst_content_source_mismatches, source_mismatches)
      worst_content_window_mismatches = math.max(
        worst_content_window_mismatches, window_mismatches)
      if source_mismatches > 0 or window_mismatches > 0 then
        content_bad_frames = content_bad_frames + 1
        if not first_content_bad then
          first_content_bad = {
            frame = frame,
            scene = emu:read8(0xD880),
            room = emu:read8(0xFFBD),
            lcdc = lcdc,
            map = base,
            source_mismatches = source_mismatches,
            window_mismatches = window_mismatches,
            examples = content_examples,
          }
          emu:screenshot(OUT .. ".first_content_bad.png")
        end
      end
      if content_sample_ages[window_frames] then
        local path = string.format(
          "%s-f%04d-a%03d.png", CONTENT_SCREENSHOT_PREFIX, frame,
          window_frames)
        emu:screenshot(path)
        content_raster_trace[#content_raster_trace + 1] = string.format(
          "f%d:a%d:p%s", frame, window_frames, path)
      end
    end
    attr_checked_frames = attr_checked_frames + 1
    local visible_age = window_frames
    if visible_age <= 8 then
      attr_entry_frames = attr_entry_frames + 1
    elseif CLOSE_FRAME >= 0 and frame >= CLOSE_FRAME then
      attr_exit_frames = attr_exit_frames + 1
    else
      attr_settled_frames = attr_settled_frames + 1
    end
    attr_mismatch_cells = attr_mismatch_cells + attr_mismatches
    attr_unsafe_cells = attr_unsafe_cells + unsafe_attrs
    if attr_mismatches > 0 or unsafe_attrs > 0 then
      attr_bad_frames = attr_bad_frames + 1
      worst_attr_mismatches = math.max(
        worst_attr_mismatches, attr_mismatches)
      if not first_attr_bad then
        first_attr_bad = {
          frame = frame,
          scene = emu:read8(0xD880),
          room = emu:read8(0xFFBD),
          lcdc = lcdc,
          map = base,
          mismatches = attr_mismatches,
          unsafe = unsafe_attrs,
          examples = attr_examples,
        }
        emu:screenshot(OUT .. ".first_attr_bad.png")
        dump_window_attrs(OUT .. ".window_attrs.bin", base)
        dump_expected_attrs(OUT .. ".expected_attrs.bin", base)
      end
    end
    local bg_map = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    if base == bg_map then
      map_alias_frames = map_alias_frames + 1
      if not first_alias then
        first_alias = {frame = frame, lcdc = lcdc, map = base}
        emu:screenshot(OUT .. ".first_alias.png")
      end
    end
    if STALE_FRAME < 0 and CLOSE_FRAME >= 0 and frame >= CLOSE_FRAME + 30 then
      window_frames_after_close = window_frames_after_close + 1
    end
    if STALE_FRAME >= 0 and frame >= STALE_FRAME + 2 then
      stale_window_frames_after_grace =
        stale_window_frames_after_grace + 1
    end
    if not first_visible then
      first_visible = {
        frame = frame,
        scene = emu:read8(0xD880),
        room = emu:read8(0xFFBD),
        lcdc = lcdc,
        wy = wy,
        map = base,
        mismatches = mismatches,
      }
      emu:screenshot(SCREENSHOT)
    end
    if mismatches > 0 then
      bad_frames = bad_frames + 1
      if mismatches > worst_mismatches then worst_mismatches = mismatches end
      if not first_bad then
        first_bad = {
          frame = frame,
          scene = emu:read8(0xD880),
          room = emu:read8(0xFFBD),
          lcdc = lcdc,
          wy = wy,
          map = base,
          dc0b = emu:read8(0xDC0B),
          ffda = emu:read8(0xFFDA),
          mismatches = mismatches,
        }
        emu:screenshot(OUT .. ".first_bad.png")
        dump_grid(OUT .. ".hud.bin", 0, true)
        dump_grid(OUT .. ".window.bin", base, false)
      end
    end
  end

  if CLOSE_FRAME >= 0 and frame >= CLOSE_FRAME and not enabled then
    window_hidden_at_close_frames = window_hidden_at_close_frames + 1
    post_close_selector_checked_frames =
      post_close_selector_checked_frames + 1
    local bg_base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local window_base = window_map(lcdc)
    if bg_base == window_base then
      post_close_selector_alias_frames =
        post_close_selector_alias_frames + 1
      local hud_matches = mismatch_count(bg_base) == 0 and 1 or 0
      post_close_hud_leak_frames =
        post_close_hud_leak_frames + hud_matches
      if not first_post_close_alias then
        first_post_close_alias = {
          frame = frame,
          lcdc = lcdc,
          bg = bg_base,
          window = window_base,
          hud_matches = hud_matches,
        }
        emu:screenshot(OUT .. ".first_post_close_alias.png")
      end
    end
  end

  if frame >= LIMIT then finish() end
end)
