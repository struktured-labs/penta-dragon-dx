-- Capture every native item-menu group and both Window VRAM planes.
-- Driven by verify_menu_icon_palettes.py through the guarded single-flight
-- launcher.  The route is intentionally the same cold-start path used by the
-- release menu publication-order gate.

local OUT = assert(os.getenv("MENU_ICON_PALETTE_OUT"))
local LIMIT = tonumber(os.getenv("MENU_ICON_PALETTE_FRAMES") or "1510")
local frame = 0
local finished = false
local pages = {}

local KEY_A = 0x01
local KEY_SELECT = 0x04
local KEY_DOWN = 0x80

local SNAPSHOTS = {1245, 1300, 1355, 1410, 1465}
local INVENTORY_GROUPS = {
  {1, 2, 3, 4, 5},
  {6, 7, 8, 9, 10, 11},
  {12, 13, 14, 15, 16},
}

local function pulse(lo, hi, mask)
  return (frame >= lo and frame < hi) and mask or 0
end

local function hex_grid(map, bank)
  local rows = {}
  local incoming = emu:read8(0xFF4F)
  emu:write8(0xFF4F, bank)
  for row = 0, 5 do
    local values = {}
    for col = 0, 19 do
      values[#values + 1] = string.format(
        "%02X", emu:read8(map + row * 32 + col))
    end
    rows[#rows + 1] = table.concat(values)
  end
  emu:write8(0xFF4F, incoming)
  return rows
end

local function packed_grid()
  local rows = {}
  for row = 0, 5 do
    local values = {}
    for col = 0, 19 do
      values[#values + 1] = string.format(
        "%02X", emu:read8(0xC4E0 + row * 20 + col))
    end
    rows[#rows + 1] = table.concat(values)
  end
  return rows
end

local function capture(page)
  local lcdc = emu:read8(0xFF40)
  local map = ((lcdc & 0x40) ~= 0) and 0x9C00 or 0x9800
  pages[#pages + 1] = {
    page = page,
    frame = frame,
    scene = emu:read8(0xD880),
    menu = emu:read8(0xFFE4),
    lcdc = lcdc,
    map = map,
    packed = packed_grid(),
    tiles = hex_grid(map, 0),
    attrs = hex_grid(map, 1),
  }
  emu:screenshot(string.format("%s.page-%02d.png", OUT, page))
end

local function finish()
  if finished then return end
  finished = true
  local handle = assert(io.open(OUT, "w"))
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("pages=%d\n", #pages))
  for _, page in ipairs(pages) do
    handle:write(string.format(
      "page%d_meta=frame:%d,scene:%02X,menu:%02X,lcdc:%02X,map:%04X\n",
      page.page, page.frame, page.scene, page.menu, page.lcdc, page.map))
    for row = 1, 6 do
      handle:write(string.format(
        "page%d_packed%d=%s\n", page.page, row - 1, page.packed[row]))
      handle:write(string.format(
        "page%d_tiles%d=%s\n", page.page, row - 1, page.tiles[row]))
      handle:write(string.format(
        "page%d_attrs%d=%s\n", page.page, row - 1, page.attrs[row]))
    end
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
  keys = keys | pulse(241, 247, KEY_A)
  keys = keys | pulse(291, 297, KEY_A)
  keys = keys | pulse(341, 347, 0x08)
  keys = keys | pulse(391, 397, KEY_A)
  if frame == 1180 then
    -- Normalize all three ten-slot native inventory groups.  The game still
    -- builds C4E0 itself through $1F60 and redraws each group through its
    -- ordinary input loop; this fixture only makes every canonical icon
    -- class observable without depending on a months-old cross-ROM state.
    for group = 0, 2 do
      for slot = 0, 9 do emu:write8(0xDCBD + group * 10 + slot, 0) end
      for slot, item in ipairs(INVENTORY_GROUPS[group + 1]) do
        emu:write8(0xDCBD + group * 10 + slot - 1, item)
      end
    end
    emu:write8(0xDCDB, 0)
    emu:write8(0xDCDD, 0)
  end
  keys = keys | pulse(1200, 1206, KEY_SELECT)
  for page = 0, 3 do
    local press = 1260 + page * 55
    keys = keys | pulse(press, press + 6, KEY_DOWN)
  end
  emu:setKeys(keys)

  if emu:read8(0xFFC1) == 1 then
    -- Keep the cold route alive without changing menu or Window state.
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xFF)
  end

  for index, snapshot in ipairs(SNAPSHOTS) do
    if frame == snapshot then capture(index - 1) end
  end
  if frame >= LIMIT then finish() end
end)
