-- Multi-room soak for later-stage background integrity.
--
-- Environment:
--   SOAK_TARGET  FFBA value (1 = Stage 2, ... 6 = Stage 7)
--   SOAK_OUT     output prefix for .report/.log and per-room VRAM captures
--   SOAK_FRAMES  gameplay frames to exercise (default 8000)

local TARGET = tonumber(os.getenv("SOAK_TARGET") or "1")
local OUT = os.getenv("SOAK_OUT") or "/tmp/penta_later_stage_soak"
local LIMIT = tonumber(os.getenv("SOAK_FRAMES") or "8000")
local TRACE_ADDRS = os.getenv("SOAK_TRACE_ADDRS") or ""
local TRACE_SEGMENT = tonumber(os.getenv("SOAK_TRACE_SEGMENT") or "")
local ATTR_TRACE_PATH = os.getenv("SOAK_ATTR_TRACE")
local AUDIT_WRAM = os.getenv("SOAK_WRAM_AUDIT") == "1"
local CAPTURE_SCREENSHOTS = os.getenv("SOAK_SCREENSHOTS") == "1"
local CAPTURE_STABLE = tonumber(os.getenv("SOAK_CAPTURE_STABLE") or "4")
local EXPECTED_SCENE = TARGET + 2
local KEY_A, KEY_START = 0x01, 0x08
local KEY_RIGHT, KEY_LEFT, KEY_UP, KEY_DOWN = 0x10, 0x20, 0x40, 0x80

local f, phase, seeded, confirmed = 0, "title", false, false
local play_frame, expected_samples = 0, 0
local unsafe_attrs, unexpected_attrs, lava_mismatches = 0, 0, 0
local max_unsafe, max_unexpected, max_lava_mismatch = 0, 0, 0
local last_room, room_stable = -1, 0
local rooms, scenes, captured_rooms, captured_mismatches = {}, {}, {}, {}
local done = false
local attr_trace = ATTR_TRACE_PATH and assert(io.open(ATTR_TRACE_PATH, "w")) or nil
local tile_copy_hits = 0
local tile_copy_map = 0
local wram_baseline, wram_changed = nil, 0
-- Audit only DX-owned immutable WRAM. C4xx-CBxx is ordinary game state and
-- changes more often when a faster build advances farther through a route.
-- DAFA-DAFF is deliberately excluded because it is live Stage-7 metadata.
local WRAM_AUDIT_RANGES = {{0xD900, 0xD9FF}, {0xDA00, 0xDAF9}}

local LAVA5 = {
  [0x02]=true, [0x03]=true, [0x04]=true, [0x05]=true,
  [0x12]=true, [0x13]=true, [0x14]=true, [0x15]=true,
}
local LAVA7 = {[0x19]=true, [0x1A]=true}

if attr_trace then
  -- The stock caller selects the destination map immediately before the
  -- shared copy entry.  mGBA's Lua register accessor is not reliable in this
  -- environment, so record the two concrete control-flow entries instead.
  emu:setBreakpoint(function() tile_copy_map = 0x9C00 end, 0x42A0)
  emu:setBreakpoint(function() tile_copy_map = 0x9800 end, 0x42A5)
  emu:setBreakpoint(function()
    if phase ~= "play" or (TARGET ~= 4 and TARGET ~= 6)
        or emu:read8(0xD880) ~= EXPECTED_SCENE then
      return
    end
    tile_copy_hits = tile_copy_hits + 1
    local bitset, rawset, packed_bits = {}, {}, 0
    for offset = 0, 575 do
      local tile = emu:read8(0xC1A0 + offset)
      rawset[#rawset + 1] = string.format("%02X", tile)
      local desired = ((TARGET == 4 and LAVA5[tile])
        or (TARGET == 6 and LAVA7[tile])) and 1 or 0
      if desired ~= 0 then packed_bits = packed_bits + 2 ^ (offset % 8) end
      if offset % 8 == 7 then
        bitset[#bitset + 1] = string.format("%02X", packed_bits)
        packed_bits = 0
      end
    end
    attr_trace:write(string.format(
      "%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
      "%02X%02X%02X%02X%02X%02X\t%02X%02X%02X%02X%02X%02X\t" ..
      "%s\t%s\t%04X\n",
      tile_copy_hits, play_frame, emu:read8(0xFFBD),
      emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xC1A4),
      emu:read8(0xDF4F), emu:read8(0xFFE0),
      emu:read8(0xDF53), emu:read8(0xDF54), emu:read8(0xDF55),
      emu:read8(0xDF56), emu:read8(0xDF57), emu:read8(0xDF58),
      emu:read8(0xDAFA), emu:read8(0xDAFB), emu:read8(0xDAFC),
      emu:read8(0xDAFD), emu:read8(0xDAFE), emu:read8(0xDAFF),
      table.concat(bitset), table.concat(rawset), tile_copy_map))
    attr_trace:flush()
  end, 0x42C0)
end

local function log(message)
  local fh = io.open(OUT .. ".log", "a")
  if fh then fh:write(string.format("f%06d p%06d %s\n", f, play_frame, message)); fh:close() end
end

do
  local fh = io.open(OUT .. ".log", "w")
  if fh then
    fh:write(string.format("target=%d expected_scene=%02X frames=%d\n",
      TARGET, EXPECTED_SCENE, LIMIT))
    fh:close()
  end
end

if TRACE_ADDRS ~= "" then
  for raw in string.gmatch(TRACE_ADDRS, "[^,]+") do
    local address_text, segment_text = string.match(raw, "^([^@]+)@([^@]+)$")
    local address = tonumber(address_text or raw)
    local segment = tonumber(segment_text or "") or TRACE_SEGMENT
    if address then
      local callback = function()
        log(string.format(
          "breakpoint=%04X segment=%s pc=%04X scene=%02X room=%02X " ..
          "dcfd=%02X dd09=%02X a=%02X f=%02X scx=%02X scy=%02X " ..
          "decision=%02X bank=%02X svbk=%02X mapped4C54=%02X " ..
          "e=%02X h=%02X l=%02X phase=%02X bcps=%02X",
          address, tostring(segment), address, emu:read8(0xD880),
          emu:read8(0xFFBD), emu:read8(0xDCFD), emu:read8(0xDD09),
          emu:readRegister("A"), emu:readRegister("F"),
          emu:read8(0xFF43), emu:read8(0xFF42),
          emu:read8(0xFFE0), emu:read8(0xFF99), emu:read8(0xFF70),
          emu:read8(0x4C54), emu:readRegister("E"),
          emu:readRegister("H"), emu:readRegister("L"),
          emu:read8(0xDF4C), emu:read8(0xFF68)))
      end
      if segment then
        emu:setBreakpoint(callback, address, segment)
      else
        emu:setBreakpoint(callback, address, -1)
      end
    end
  end
end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for i = 1, 0x1F do emu:write8(base + i, 0x00) end
  end
end

local function audit_wram()
  if not AUDIT_WRAM then return end
  if not wram_baseline then
    wram_baseline = {}
    for _, range in ipairs(WRAM_AUDIT_RANGES) do
      for address = range[1], range[2] do
        wram_baseline[address] = emu:read8(address)
      end
    end
    return
  end
  for _, range in ipairs(WRAM_AUDIT_RANGES) do
    for address = range[1], range[2] do
      if emu:read8(address) ~= wram_baseline[address] then
        wram_changed = wram_changed + 1
        wram_baseline[address] = emu:read8(address)
      end
    end
  end
end

local function dump_range(path, first, last)
  local fh = assert(io.open(path, "wb"))
  for address = first, last do fh:write(string.char(emu:read8(address))) end
  fh:close()
end

local function capture_room(room)
  local prefix = OUT .. string.format(".room%02X", room)
  if CAPTURE_SCREENSHOTS then emu:screenshot(prefix .. ".png") end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  dump_range(prefix .. ".vram0.bin", 0x8000, 0x97FF)
  dump_range(prefix .. ".map0.bin", 0x9800, 0x9FFF)
  emu:write8(0xFF4F, 1)
  dump_range(prefix .. ".vram1.bin", 0x8000, 0x97FF)
  dump_range(prefix .. ".attr.bin", 0x9800, 0x9FFF)

  local old_bcps = emu:read8(0xFF68)
  local bgp = assert(io.open(prefix .. ".bgp.bin", "wb"))
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    bgp:write(string.char(emu:read8(0xFF69)))
  end
  bgp:close()
  emu:write8(0xFF68, old_bcps)

  local active_base = ((emu:read8(0xFF40) & 0x08) ~= 0) and 0x9C00 or 0x9800
  local meta = assert(io.open(prefix .. ".meta", "w"))
  meta:write(string.format(
    "frame=%d target=%d expected_scene=%02X D880=%02X FFC1=%02X FFBA=%02X " ..
    "LCDC=%02X SCX=%02X SCY=%02X active_map=%04X room=%02X\n",
    f, TARGET, EXPECTED_SCENE, emu:read8(0xD880), emu:read8(0xFFC1),
    emu:read8(0xFFBA), emu:read8(0xFF40), emu:read8(0xFF43),
    emu:read8(0xFF42), active_base, room))
  meta:close()
  emu:write8(0xFF4F, old_vbk)
  log(string.format("captured room=%02X", room))
end

local function sample_visible()
  local lcdc, scx, scy = emu:read8(0xFF40), emu:read8(0xFF43), emu:read8(0xFF42)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local first_col, first_row = math.floor(scx / 8), math.floor(scy / 8)
  local cols = ((scx & 7) == 0) and 20 or 21
  local rows = ((scy & 7) == 0) and 18 or 19
  local addresses, attrs = {}, {}
  local old_vbk = emu:read8(0xFF4F)

  emu:write8(0xFF4F, 1)
  for y = 0, rows - 1 do
    for x = 0, cols - 1 do
      local row, col = (first_row + y) & 31, (first_col + x) & 31
      local address = base + row * 32 + col
      addresses[#addresses + 1] = address
      attrs[#attrs + 1] = emu:read8(address)
    end
  end

  emu:write8(0xFF4F, 0)
  local sample_unsafe, sample_unexpected, sample_lava_mismatch = 0, 0, 0
  local lava_mismatch_xy = {}
  for index, address in ipairs(addresses) do
    local attr, tile = attrs[index], emu:read8(address)
    if (attr & 0xF8) ~= 0 then sample_unsafe = sample_unsafe + 1 end
    if TARGET == 4 or TARGET == 6 then
      if attr ~= 0 and attr ~= 5 then sample_unexpected = sample_unexpected + 1 end
      if attr == 5 then
        local valid = (TARGET == 4 and LAVA5[tile]) or (TARGET == 6 and LAVA7[tile])
        if not valid then
          sample_lava_mismatch = sample_lava_mismatch + 1
          local zero = index - 1
          lava_mismatch_xy[#lava_mismatch_xy + 1] = string.format(
            "%d:%d:%02X", zero % cols, math.floor(zero / cols), tile)
        end
      end
    elseif attr ~= 0 then
      sample_unexpected = sample_unexpected + 1
    end
  end
  emu:write8(0xFF4F, old_vbk)

  unsafe_attrs = unsafe_attrs + sample_unsafe
  unexpected_attrs = unexpected_attrs + sample_unexpected
  lava_mismatches = lava_mismatches + sample_lava_mismatch
  if sample_unsafe > max_unsafe then max_unsafe = sample_unsafe end
  if sample_unexpected > max_unexpected then max_unexpected = sample_unexpected end
  if sample_lava_mismatch > max_lava_mismatch then max_lava_mismatch = sample_lava_mismatch end
  if sample_lava_mismatch > 0 then
    local mismatch_room = emu:read8(0xFFBD)
    if CAPTURE_SCREENSHOTS and not captured_mismatches[mismatch_room] then
      captured_mismatches[mismatch_room] = true
      local mismatch_prefix = OUT .. string.format(
        ".mismatch.room%02X.f%06d", mismatch_room, play_frame)
      emu:screenshot(mismatch_prefix .. ".png")
      dump_range(mismatch_prefix .. ".source.bin", 0xC1A0, 0xC3DF)
      local mismatch_vbk = emu:read8(0xFF4F)
      emu:write8(0xFF4F, 0)
      dump_range(mismatch_prefix .. ".map0.bin", 0x9800, 0x9FFF)
      emu:write8(0xFF4F, 1)
      dump_range(mismatch_prefix .. ".attr.bin", 0x9800, 0x9FFF)
      emu:write8(0xFF4F, mismatch_vbk)
      local mismatch_svbk = emu:read8(0xFF70)
      emu:write8(0xFF70, 2)
      dump_range(mismatch_prefix .. ".shadow.bin", 0xD000, 0xD7FF)
      emu:write8(0xFF70, mismatch_svbk)
    end
    log(string.format(
      "lava_mismatch=%d room=%02X scene=%02X scx=%02X scy=%02X count=%02X cache=%02X xy=%s",
      sample_lava_mismatch, emu:read8(0xFFBD), emu:read8(0xD880),
      emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xDF4E),
      emu:read8(0xDF4F), table.concat(lava_mismatch_xy, ",")))
  end
  expected_samples = expected_samples + 1
end

local function write_report()
  local room_list, scene_list = {}, {}
  for room in pairs(rooms) do room_list[#room_list + 1] = room end
  for scene in pairs(scenes) do scene_list[#scene_list + 1] = scene end
  table.sort(room_list); table.sort(scene_list)
  local room_text, scene_text = {}, {}
  for _, room in ipairs(room_list) do room_text[#room_text + 1] = string.format("%02X", room) end
  for _, scene in ipairs(scene_list) do scene_text[#scene_text + 1] = string.format("%02X", scene) end

  local fh = assert(io.open(OUT .. ".report", "w"))
  fh:write(string.format(
    "target=%d stage=%d frames=%d expected_scene=%02X samples=%d rooms=%d " ..
    "unsafe=%d unexpected=%d lava_mismatch=%d max_unsafe=%d " ..
    "max_unexpected=%d max_lava_mismatch=%d wram_changed=%d\n",
    TARGET, TARGET + 1, play_frame, EXPECTED_SCENE, expected_samples,
    #room_list, unsafe_attrs, unexpected_attrs, lava_mismatches,
    max_unsafe, max_unexpected, max_lava_mismatch, wram_changed))
  fh:write("room_ids=" .. table.concat(room_text, ",") .. "\n")
  fh:write("scene_ids=" .. table.concat(scene_text, ",") .. "\n")
  fh:close()
  if attr_trace then attr_trace:close(); attr_trace = nil end
  done = true
  log("DONE")
  emu:stop()
end

local function gameplay_input()
  local cycle = play_frame % 120
  local keys = KEY_A
  if cycle < 20 then keys = keys + KEY_UP
  elseif cycle < 40 then keys = keys + KEY_DOWN
  elseif cycle < 60 then keys = keys + KEY_LEFT
  else keys = keys + KEY_RIGHT end
  return keys
end

callbacks:add("frame", function()
  if done then return end
  f = f + 1
  emu:write8(0xDCFD, 0x01)
  if not seeded and f >= 100 then seed_sram(); seeded = true end

  if phase == "title" then
    if f >= 300 and f < 306 then emu:setKeys(KEY_START)
    elseif f >= 360 and f < 366 then emu:setKeys(KEY_START)
    else emu:setKeys(0) end
    if f >= 330 then phase = "level_select" end
    return
  end

  if phase == "level_select" and not confirmed then
    emu:write8(0xFFBA, TARGET)
    seed_sram()
    if f % 60 >= 10 and f % 60 < 16 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if emu:read8(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
      confirmed = true
      phase = "loading"
      log("level selected")
    end
    if f > 700 then log("failed to select level"); write_report() end
    return
  end

  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  if phase == "loading" then
    emu:write8(0xFFBA, TARGET)
    emu:setKeys(0)
    if emu:read8(0xD880) == EXPECTED_SCENE and emu:read8(0xFFC1) == 1 then
      phase = "play"
      log("stable gameplay entered")
    end
    if f > 30000 then log("failed to reach gameplay"); write_report() end
    return
  end

  play_frame = play_frame + 1
  audit_wram()
  local scene, room = emu:read8(0xD880), emu:read8(0xFFBD)
  scenes[scene] = true
  if scene == EXPECTED_SCENE and emu:read8(0xFFC1) == 1 then
    rooms[room] = true
    if room == last_room then room_stable = room_stable + 1
    else
      last_room, room_stable = room, 0
      log(string.format("room=%02X", room))
    end
    if room_stable == CAPTURE_STABLE and not captured_rooms[room] then
      captured_rooms[room] = true
      capture_room(room)
    end
    if play_frame % 5 == 0 then sample_visible() end
  end

  emu:setKeys(gameplay_input())
  if play_frame >= LIMIT then write_report() end
end)
