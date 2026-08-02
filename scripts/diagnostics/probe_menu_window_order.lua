-- Detect a hardware-window frame exposed before the native 6x20 HUD copy.
--
-- The game prepares the complete item HUD at C4E0 and copies it to the map
-- selected by LCDC.6.  A visible window whose first six rows differ from that
-- buffer renders stale dungeon tiles as walls/gaps, with the native fixed HUD
-- sprite at the lower left.  This probe checks the contract on every frame,
-- including the first frame of the SELECT transition.

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
local first_bad = nil
local first_visible = nil
local worst_mismatches = 0
local transition_log = {}
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
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xFF)
  end

  local lcdc = emu:read8(0xFF40)
  local wy = emu:read8(0xFF4A)
  local base = window_map(lcdc)
  local enabled = (lcdc & 0x20) ~= 0 and wy < 144
  local mismatches = enabled and mismatch_count(base) or 0
  local signature = string.format(
    "f%d:%02X/%02X/%04X/%d", frame, lcdc, wy, base, mismatches)
  local stable = string.format("%02X/%02X/%04X/%d", lcdc, wy, base, mismatches)
  if stable ~= last_signature and #transition_log < 64 then
    transition_log[#transition_log + 1] = signature
    last_signature = stable
  end

  if enabled then
    window_frames = window_frames + 1
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
        dump_grid(OUT .. ".hud.bin", 0, true)
        dump_grid(OUT .. ".window.bin", base, false)
      end
    end
  end

  if frame >= LIMIT then finish() end
end)
