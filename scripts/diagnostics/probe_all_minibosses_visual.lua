-- Capture one complete temporary-descriptor miniboss through the real game
-- spawn path.  DC04:DC08 must be the native five-entity group; checking only
-- DC04 allowed deterministic but visually corrupt mixed-boss composites.
local OUT = assert(os.getenv("PENTA_MINIBOSS_REPORT"))
local SCREENSHOT = assert(os.getenv("PENTA_MINIBOSS_SCREENSHOT"))
local TARGET = tonumber(assert(os.getenv("PENTA_MINIBOSS_INDEX")))
local EXPECTED_SLOT = tonumber(assert(os.getenv("PENTA_MINIBOSS_PALETTE_SLOT")))
local KEY_A, KEY_DOWN, KEY_RIGHT, KEY_START = 0x01, 0x80, 0x10, 0x08
local SCHEDULE = {
  {180, 185, KEY_DOWN}, {186, 200, 0},
  {201, 206, KEY_A}, {207, 260, 0},
  {261, 266, KEY_A}, {267, 320, 0},
  {321, 326, KEY_A}, {327, 380, 0},
  {381, 386, KEY_START}, {387, 430, 0},
  {431, 436, KEY_A},
}
local ENTITY_SLOTS = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
local frame, gameplay_at, spawn_at = 0, -1, -1
local armed = false
local selected_expected_count, selected_center_distance = 0, 0
local screenshot_at, exit_at = -1, -1
local finished = false

local function keys_for_frame(value)
  for _, record in ipairs(SCHEDULE) do
    if value >= record[1] and value <= record[2] then return record[3] end
  end
  return 0
end

local function boss_oam()
  local count, rows, slots = 0, {}, {}
  -- Native miniboss bodies occupy the composed-sprite block below slot 32;
  -- the upper slots carry orbiting shots/effects that can sit at screen edges
  -- and must not masquerade as body coverage.
  for sprite = 4, 31 do
    local base = 0xFE00 + sprite * 4
    local y, x = emu:read8(base), emu:read8(base + 1)
    local tile, attr = emu:read8(base + 2), emu:read8(base + 3)
    if y > 0 and y < 160 and x > 0 and x < 168 and tile >= 0x30 then
      count = count + 1
      slots[attr & 7] = true
      rows[#rows + 1] = string.format("%d:%d:%d:%02X:%02X", sprite, x, y, tile, attr)
    end
  end
  local palette_slots = {}
  for slot, _ in pairs(slots) do palette_slots[#palette_slots + 1] = slot end
  table.sort(palette_slots)
  local slot_text = {}
  for _, slot in ipairs(palette_slots) do slot_text[#slot_text + 1] = tostring(slot) end
  return count, table.concat(rows, ","), table.concat(slot_text, ",")
end

local function boss_metrics()
  local count, rows, slots = boss_oam()
  local expected_count, center_distance = 0, 0
  local min_x, max_x, min_y, max_y = 999, -1, 999, -1
  for record in string.gmatch(rows, "[^,]+") do
    local _, x, y, _, attr = string.match(
      record, "(%d+):(%d+):(%d+):(%x+):(%x+)")
    if x then
      local palette = tonumber(attr, 16) & 7
      if EXPECTED_SLOT < 0 or palette == EXPECTED_SLOT then
        expected_count = expected_count + 1
        local numeric_x, numeric_y = tonumber(x), tonumber(y)
        center_distance = center_distance + math.abs(numeric_x - 84)
          + math.abs(numeric_y - 72)
        min_x, max_x = math.min(min_x, numeric_x), math.max(max_x, numeric_x)
        min_y, max_y = math.min(min_y, numeric_y), math.max(max_y, numeric_y)
      end
    end
  end
  local contained = expected_count >= 4 and min_x >= 8 and max_x <= 160
    and min_y >= 8 and max_y <= 152
  return count, rows, slots, expected_count, center_distance, contained
end

local function finish(status)
  local count, rows, slots = boss_oam()
  local handle = assert(io.open(OUT, "w"))
  handle:write("status=" .. status .. "\n")
  handle:write(string.format("frame=%d\n", frame))
  handle:write(string.format("screenshot_at=%d\n", screenshot_at))
  handle:write(string.format("gameplay_at=%d\n", gameplay_at))
  handle:write(string.format("spawn_at=%d\n", spawn_at))
  handle:write(string.format("D880=%02X\n", emu:read8(0xD880)))
  handle:write(string.format("FFC1=%02X\n", emu:read8(0xFFC1)))
  handle:write(string.format("FFBF=%02X\n", emu:read8(0xFFBF)))
  handle:write(string.format("DC04=%02X\n", emu:read8(0xDC04)))
  handle:write(string.format(
    "descriptor=%02X %02X %02X %02X %02X\n",
    emu:read8(0xDC04), emu:read8(0xDC05), emu:read8(0xDC06),
    emu:read8(0xDC07), emu:read8(0xDC08)))
  handle:write(string.format("visible_high_tile_sprites=%d\n", count))
  handle:write("hardware_palette_slots=" .. slots .. "\n")
  handle:write("boss_oam=" .. rows .. "\n")
  handle:write(string.format("selected_expected_count=%d\n", selected_expected_count))
  handle:write(string.format("selected_center_distance=%d\n", selected_center_distance))
  handle:close()
  finished = true
end

callbacks:add("frame", function()
  frame = frame + 1
  if finished then
    emu:setKeys(0)
    return
  end
  -- mGBA queues PNG work from emu:screenshot().  Exiting Lua in that same
  -- callback intermittently tears down the emulator while the image is still
  -- being flushed (SIGSEGV).  Four quiet frames make capture/exit ordering
  -- deterministic without accepting a non-zero emulator status.
  if exit_at > 0 then
    emu:setKeys(0)
    if frame >= exit_at then finish("pass") end
    return
  end
  if gameplay_at < 0 then
    emu:setKeys(keys_for_frame(frame))
    local scene = emu:read8(0xD880)
    if emu:read8(0xFFC1) == 1 and scene >= 0x02 and scene < 0x0C then
      gameplay_at = frame
    elseif frame >= 1500 then
      finish("no-gameplay")
    end
    return
  end

  emu:setKeys(spawn_at < 0 and (KEY_RIGHT + ((frame % 8 < 2) and KEY_A or 0)) or 0)
  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)
  local elapsed = frame - gameplay_at
  if frame >= 560 and not armed then
    emu:write8(0xDCB8, 0)
    emu:write8(0xDCBA, 1)
    emu:write8(0xFFD6, 0x1E)
    for _, address in ipairs(ENTITY_SLOTS) do emu:write8(address, 0) end
    armed = true
  end
  if armed and emu:read8(0xFFBF) == 0 then
    emu:write8(0xDCBA, 1)
    emu:write8(0xFFD6, 0x1E)
    for _, address in ipairs(ENTITY_SLOTS) do emu:write8(address, 0) end
  end
  if spawn_at < 0 and emu:read8(0xFFBF) == TARGET then spawn_at = frame end
  if spawn_at > 0 and frame >= spawn_at + 90 then
    local age = frame - spawn_at
    if age % 15 == 0 then
      local _, _, _, expected_count, center_distance, contained = boss_metrics()
      if contained then
        selected_expected_count = expected_count
        selected_center_distance = center_distance
        emu:screenshot(SCREENSHOT)
        screenshot_at = frame
        exit_at = frame + 4
      end
    end
    if frame >= spawn_at + 900 then finish("no-centered-phase") end
  end
  if elapsed >= 1800 and spawn_at < 0 then finish("no-spawn") end
end)
