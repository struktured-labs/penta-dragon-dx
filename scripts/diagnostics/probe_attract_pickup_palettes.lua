-- Natural cold-boot receipt for pickup attributes in prerecorded Stage 1.
--
-- The title is left completely idle.  The target is the real gameplay-demo
-- segment D880=$02, FFC1=1, DCFD=0; live play has the same scene byte but
-- DCFD=1.  Every visible pickup tile is compared with the ROM-compiled LUT.

local OUT = assert(os.getenv("ATTRACT_PICKUP_OUT"))
local LUT_PATH = assert(os.getenv("ATTRACT_PICKUP_LUT"))
local PICKUP_PATH = assert(os.getenv("ATTRACT_PICKUP_IDS"))
local MAX_FRAMES = tonumber(os.getenv("ATTRACT_PICKUP_MAX_FRAMES") or "10000")

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
local visible_pickup_cells = 0
local colored_pickup_cells = 0
local neutral_pickup_cells = 0
local pickup_mismatches = 0
local first_pickup_frame = -1
local first_mismatch = ""
local pickup_tiles = {}
local captures = {}
local capture_specs = {}
local pickup_frame_trace = {}
local capture_budget = 0
local finished = false

local function byte(blob, index)
  return string.byte(blob, index + 1)
end

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
          and screen_y < 144 and screen_y + 8 > 0
          and byte(pickup_ids, tile) ~= 0 then
        cells[#cells + 1] = {
          offset = offset,
          tile = tile,
          screen_x = screen_x,
          screen_y = screen_y,
        }
      end
    end
  end

  local frame_colored = 0
  local frame_neutral = 0
  local frame_mismatches = 0
  emu:write8(0xFF4F, 1)
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

  if #cells > 0 and first_pickup_frame < 0 then
    first_pickup_frame = frame
    capture_budget = 6
  end
  if #cells > 0 and #pickup_frame_trace < 512 then
    pickup_frame_trace[#pickup_frame_trace + 1] = string.format(
      "%d,%d,%d,%d,%d,%04X,%02X,%02X,%02X,%02X",
      frame, #cells, frame_colored, frame_neutral, frame_mismatches,
      base, emu:read8(0xDF4E), emu:read8(0xDF04), scx, scy)
  end
  if capture_budget > 0 then
    add_capture("pickup", cells)
    capture_budget = capture_budget - 1
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
  report:write(string.format("target_room=%02X\n", target_room & 0xFF))
  report:write(string.format("first_pickup_frame=%d\n", first_pickup_frame))
  report:write(string.format("visible_pickup_cells=%d\n", visible_pickup_cells))
  report:write(string.format("colored_pickup_cells=%d\n", colored_pickup_cells))
  report:write(string.format("neutral_pickup_cells=%d\n", neutral_pickup_cells))
  report:write(string.format("pickup_mismatches=%d\n", pickup_mismatches))
  report:write("first_mismatch=" .. first_mismatch .. "\n")
  report:write("pickup_tiles=" .. table.concat(id_text, ",") .. "\n")
  for _, value in ipairs(pickup_frame_trace) do
    report:write("pickup_frame=" .. value .. "\n")
  end
  for _, path in ipairs(captures) do report:write("capture=" .. path .. "\n") end
  for _, value in ipairs(capture_specs) do
    report:write("capture_spec=" .. value .. "\n")
  end
  report:close()
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
    target_frames = target_frames + 1
    inspect_visible()
  elseif target_started and target_frames >= 120 then
    finish("ok")
    return
  end
  if frame >= MAX_FRAMES then
    finish(target_started and "target-did-not-exit" or "target-timeout")
  end
end)
