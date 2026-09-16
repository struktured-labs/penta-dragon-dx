-- Deterministic live OAM/CRAM receipt for one projectile or effect fixture.
-- All output paths and selector metadata are supplied by the guarded Python
-- driver; there are deliberately no system-/tmp fallbacks.

local OUT = assert(os.getenv("PENTA_PROJECTILE_REPORT"))
local SCREENSHOT = assert(os.getenv("PENTA_PROJECTILE_SCREENSHOT"))
local TARGET_MIN = tonumber(assert(os.getenv("PENTA_PROJECTILE_TILE_MIN")))
local TARGET_MAX = tonumber(assert(os.getenv("PENTA_PROJECTILE_TILE_MAX")))
local OAM_MIN = tonumber(os.getenv("PENTA_PROJECTILE_OAM_MIN") or "0")
local OAM_MAX = tonumber(os.getenv("PENTA_PROJECTILE_OAM_MAX") or "39")
local EXPECTED_BOSS = tonumber(assert(os.getenv("PENTA_PROJECTILE_BOSS")))
local FORCE_POWERUP = tonumber(assert(os.getenv("PENTA_PROJECTILE_POWERUP")))
local FORCE_FORM = tonumber(os.getenv("PENTA_PROJECTILE_FORCE_FORM") or "-1")
local INPUT_MASK = tonumber(assert(os.getenv("PENTA_PROJECTILE_INPUT_MASK")))
local COLD_TARGET = tonumber(os.getenv("PENTA_PROJECTILE_COLD_TARGET") or "0")
local PALETTE_ONLY_SLOT = tonumber(
  os.getenv("PENTA_PROJECTILE_PALETTE_ONLY_SLOT") or "-1")
local SETTLE = tonumber(os.getenv("PENTA_PROJECTILE_SETTLE") or "180")
local MIN_MATCHES = tonumber(os.getenv("PENTA_PROJECTILE_MIN_MATCHES") or "1")
local MAX_OAM_SPAN = tonumber(os.getenv("PENTA_PROJECTILE_MAX_OAM_SPAN") or "-1")
local LIMIT = tonumber(os.getenv("PENTA_PROJECTILE_LIMIT") or "1200")

local frame = 0
local observations = 0
local bad_state_frames = 0
local observed_tiles = {}
local observed_slots = {}
local all_visible_tiles = {}
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
local gameplay_at, spawn_at, armed = -1, -1, false

local function keys_for_frame(value)
  for _, record in ipairs(SCHEDULE) do
    if value >= record[1] and value <= record[2] then return record[3] end
  end
  return 0
end

local function visible(y, x)
  return y > 0 and y < 160 and x > 0 and x < 168
end

local function sorted_keys(values)
  local keys = {}
  for value, _ in pairs(values) do keys[#keys + 1] = value end
  table.sort(keys)
  local result = {}
  for _, value in ipairs(keys) do result[#result + 1] = string.format("%02X", value) end
  return table.concat(result, ",")
end

local function obj_palette_bytes(slot)
  local old_index = emu:read8(0xFF6A)
  local bytes = {}
  for offset = 0, 7 do
    emu:write8(0xFF6A, slot * 8 + offset)
    bytes[#bytes + 1] = string.format("%02X", emu:read8(0xFF6B))
  end
  emu:write8(0xFF6A, old_index)
  return table.concat(bytes)
end

local function encode_oam(entries)
  local result = {}
  for _, entry in ipairs(entries or {}) do
    result[#result + 1] = string.format(
      "%d:%d:%d:%02X:%02X",
      entry.slot, entry.x, entry.y, entry.tile, entry.attr)
  end
  return table.concat(result, ",")
end

local function write_report(status, matches, target_oam)
  local handle = assert(io.open(OUT, "w"))
  handle:write("status=" .. status .. "\n")
  handle:write(string.format("frame=%d\n", frame))
  handle:write(string.format("matches=%d\n", matches or 0))
  handle:write(string.format("observations=%d\n", observations))
  handle:write(string.format("bad_state_frames=%d\n", bad_state_frames))
  handle:write(string.format("D880=%02X\n", emu:read8(0xD880)))
  handle:write(string.format("FFC1=%02X\n", emu:read8(0xFFC1)))
  handle:write(string.format("FFBE=%02X\n", emu:read8(0xFFBE)))
  handle:write(string.format("FFBF=%02X\n", emu:read8(0xFFBF)))
  handle:write(string.format("FFC0=%02X\n", emu:read8(0xFFC0)))
  handle:write(string.format("LCDC=%02X\n", emu:read8(0xFF40)))
  handle:write("target_oam=" .. encode_oam(target_oam) .. "\n")
  local descriptor = {}
  for address = 0xDC04, 0xDC08 do
    descriptor[#descriptor + 1] = string.format("%02X", emu:read8(address))
  end
  handle:write("descriptor=" .. table.concat(descriptor, " ") .. "\n")
  handle:write("observed_tiles=" .. sorted_keys(observed_tiles) .. "\n")
  handle:write("all_visible_tiles=" .. sorted_keys(all_visible_tiles) .. "\n")
  handle:write("palette_slots=" .. sorted_keys(observed_slots) .. "\n")
  for slot, _ in pairs(observed_slots) do
    handle:write(string.format("obj%d_cram=%s\n", slot, obj_palette_bytes(slot)))
  end
  handle:close()
end

callbacks:add("frame", function()
  frame = frame + 1
  if frame == 1 and COLD_TARGET == 0 then
    emu:write8(0xDF51, 0x00)
    emu:write8(0xDF0D, 0xFF)
    emu:write8(0xDF00, 0x00)
  end

  if COLD_TARGET > 0 and gameplay_at < 0 then
    emu:setKeys(keys_for_frame(frame))
    local scene = emu:read8(0xD880)
    if emu:read8(0xFFC1) == 1 and scene >= 0x02 and scene < 0x0C then
      gameplay_at = frame
    elseif frame >= 1500 then
      write_report("no-gameplay", 0)
      os.exit(2)
    end
    return
  end

  -- Keep cross-build combat anchors alive while the current candidate settles.
  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)
  emu:write8(0xFFC0, FORCE_POWERUP)
  if FORCE_FORM >= 0 then emu:write8(0xFFBE, FORCE_FORM) end

  if COLD_TARGET > 0 then
    emu:setKeys(spawn_at < 0 and (KEY_RIGHT
      + ((frame % 8 < 2) and KEY_A or 0)) or 0)
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
    if spawn_at < 0 and emu:read8(0xFFBF) == COLD_TARGET then
      spawn_at = frame
    end
    if spawn_at < 0 or frame < spawn_at + 90 then return end
  end

  local keys = 0
  if COLD_TARGET == 0 and INPUT_MASK ~= 0
      and frame >= 30 and (frame % 48) < 8 then
    keys = INPUT_MASK
  end
  emu:setKeys(keys)

  if COLD_TARGET == 0 and frame <= SETTLE then return end
  if PALETTE_ONLY_SLOT >= 0 then
    observed_slots[PALETTE_ONLY_SLOT] = true
    emu:screenshot(SCREENSHOT)
    write_report("pass", 0)
    os.exit(0)
  end
  local scene = emu:read8(0xD880)
  local gameplay = emu:read8(0xFFC1)
  local boss = emu:read8(0xFFBF)
  if gameplay ~= 1 or scene < 0x02 or scene >= 0x0C or boss ~= EXPECTED_BOSS then
    bad_state_frames = bad_state_frames + 1
  else
    local matches = 0
    local target_oam = {}
    for slot = OAM_MIN, OAM_MAX do
      local base = 0xFE00 + slot * 4
      local y = emu:read8(base)
      local x = emu:read8(base + 1)
      local tile = emu:read8(base + 2)
      if visible(y, x) then all_visible_tiles[tile] = true end
      if visible(y, x) and tile >= TARGET_MIN and tile <= TARGET_MAX then
        local attr = emu:read8(base + 3)
        local palette = attr & 0x07
        matches = matches + 1
        observations = observations + 1
        observed_tiles[tile] = true
        observed_slots[palette] = true
        target_oam[#target_oam + 1] = {
          slot=slot, x=x, y=y, tile=tile, attr=attr}
      end
    end
    local span_ok = true
    if MAX_OAM_SPAN >= 0 and #target_oam > 0 then
      local min_x, max_x, min_y, max_y = 255, 0, 255, 0
      for _, entry in ipairs(target_oam) do
        min_x, max_x = math.min(min_x, entry.x), math.max(max_x, entry.x)
        min_y, max_y = math.min(min_y, entry.y), math.max(max_y, entry.y)
      end
      span_ok = max_x - min_x <= MAX_OAM_SPAN
        and max_y - min_y <= MAX_OAM_SPAN
    end
    if matches >= MIN_MATCHES and span_ok then
      emu:screenshot(SCREENSHOT)
      write_report("pass", matches, target_oam)
      os.exit(0)
    end
  end

  local frame_limit = (COLD_TARGET > 0) and 2600 or LIMIT
  if frame >= frame_limit then
    write_report("missing", 0)
    os.exit(2)
  end
end)
