-- Measure stock main-loop throughput in a selected dungeon stage.
--
-- Environment:
--   STAGE_SPEED_TARGET  FFBA value (0 = Stage 1, ... 6 = Stage 7)
--   STAGE_SPEED_OUT     JSON receipt path
--   STAGE_SPEED_DONE    completion marker path
--   STAGE_SPEED_MODE    right, stationary, or patrol
--   STAGE_SPEED_FRAMES  measured rendered frames (default 600)

local TARGET = tonumber(os.getenv("STAGE_SPEED_TARGET") or "0")
local OUT = assert(os.getenv("STAGE_SPEED_OUT"))
local DONE = assert(os.getenv("STAGE_SPEED_DONE"))
local TRACE = os.getenv("STAGE_SPEED_TRACE")
local INPUT_MODE = os.getenv("STAGE_SPEED_MODE") or "right"
local LIMIT = tonumber(os.getenv("STAGE_SPEED_FRAMES") or "600")
local ATOMIC_ADDR = tonumber(os.getenv("STAGE_SPEED_ATOMIC_ADDR") or "0")
local EXPECTED_SCENE = TARGET + 2
local KEY_A, KEY_START = 0x01, 0x08
local KEY_RIGHT, KEY_LEFT = 0x10, 0x20

local frame, phase, seeded, confirmed = 0, "title", false, false
local stable_frames, play_frames = 0, 0
local main_loop_hits, central_emitter_hits, free_emitter_hits = 0, 0, 0
local last_main_loop_frame, max_main_loop_gap = -1, 0
local tile_copy_hits, atomic_attr_passes = 0, 0
local atomic_call_indices = {}
local previous_scx, scroll_changes = -1, 0
-- FFC1 is a gameplay sub-mode flag, not a universal active/inactive bit.
-- Retain its high-frame count and first transition as diagnostic telemetry;
-- scene stability and main-loop throughput are the actual continuity gates.
local active_frames, first_inactive_frame = 0, -1
local first_inactive_state = ""
local expected_scene_frames, first_scene_mismatch = 0, -1
local dma_unreadable_scene_samples, non_dma_scene_mismatch_frames = 0, 0
local first_scene_mismatch_value = -1
local mismatch_cpu_pc, mismatch_dma_source, mismatch_svbk = -1, -1, -1
local lava_copy_hits, attr_map_changes, attr_map_unchanged = 0, 0, 0
local attr_changed_cells, attr_changed_groups = 0, 0
local max_attr_changed_cells, max_attr_changed_groups = 0, 0
local previous_attr_map = nil
local attr_trace = TRACE and assert(io.open(TRACE, "w")) or nil
local tile_copy_map_hi = -1
local breakpoints_available = false
local finished = false
local LAVA5 = {
  [0x02]=true, [0x03]=true, [0x04]=true, [0x05]=true,
  [0x12]=true, [0x13]=true, [0x14]=true, [0x15]=true,
}
local LAVA7 = {[0x19]=true, [0x1A]=true}

local function is_stage1_pickup(tile)
  return tile >= 0x80 and tile < 0xE0 and (tile & 0x08) ~= 0
end

local function entry_return()
  local ok, sp = pcall(function() return emu:getRegister("SP") end)
  if not ok or type(sp) ~= "number" then return -1 end
  return emu:read8(sp) + 256 * emu:read8((sp + 1) & 0xFFFF)
end

local function read_register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and type(value) == "number" then return value end
  ok, value = pcall(function() return emu:getRegister(name) end)
  if ok and type(value) == "number" then return value end
  return -1
end

local function profile_lava_attr_map()
  if phase ~= "play" or (TARGET ~= 0 and TARGET ~= 4 and TARGET ~= 6)
      or emu:read8(0xD880) ~= EXPECTED_SCENE then
    return
  end
  lava_copy_hits = lava_copy_hits + 1
  local previous = previous_attr_map
  local current, changed, groups, map_hash = {}, 0, {}, 2166136261
  local bitset, rawset, packed_bits = {}, {}, 0
  for offset = 0, 575 do
    local tile = emu:read8(0xC1A0 + offset)
    rawset[#rawset + 1] = string.format("%02X", tile)
    local desired = ((TARGET == 0 and is_stage1_pickup(tile))
      or (TARGET == 4 and LAVA5[tile])
      or (TARGET == 6 and LAVA7[tile])) and 1 or 0
    current[offset + 1] = desired
    if desired ~= 0 then
      packed_bits = packed_bits + 2 ^ (offset % 8)
    end
    if offset % 8 == 7 then
      bitset[#bitset + 1] = string.format("%02X", packed_bits)
      packed_bits = 0
    end
    map_hash = (map_hash * 16777619 + desired * (offset + 1)) % 4294967296
    if previous == nil or previous[offset + 1] ~= desired then
      changed = changed + 1
      groups[math.floor(offset / 4)] = true
    end
  end
  if attr_trace then
    local raw_signature = (
      emu:read8(0xC1A4)
      ~ emu:read8(0xFF43)
      ~ emu:read8(0xFF42)
    ) & 0xFE
    attr_trace:write(string.format(
      "%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\t%d\t%u"
        .. "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X"
        .. "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X"
        .. "\t%04X\t%s\t%s\n",
      lava_copy_hits, play_frames, tile_copy_map_hi & 0xFF,
      emu:read8(0xFFBD), emu:read8(0xFF43), emu:read8(0xFF42),
      emu:read8(0xC1A4), raw_signature, changed > 0 and 1 or 0,
      changed, map_hash, emu:read8(0xDF4F),
      emu:read8(0xDF53), emu:read8(0xDF54),
      emu:read8(0xDF55), emu:read8(0xDF56),
      emu:read8(0xDF57), emu:read8(0xDF58),
      emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC02), emu:read8(0xDC03),
      emu:read8(0xDC81), emu:read8(0xFFCF),
      emu:read8(0xFFE8), emu:read8(0xFFE9), emu:read8(0xFFEB),
      entry_return() & 0xFFFF, table.concat(bitset), table.concat(rawset)))
    attr_trace:flush()
  end
  local group_count = 0
  for _ in pairs(groups) do group_count = group_count + 1 end
  if changed == 0 then
    attr_map_unchanged = attr_map_unchanged + 1
  else
    attr_map_changes = attr_map_changes + 1
    attr_changed_cells = attr_changed_cells + changed
    attr_changed_groups = attr_changed_groups + group_count
    if changed > max_attr_changed_cells then max_attr_changed_cells = changed end
    if group_count > max_attr_changed_groups then
      max_attr_changed_groups = group_count
    end
  end
  previous_attr_map = current
end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
    emu:write8(base, 0xFF)
    for offset = 1, 0x1F do emu:write8(base + offset, 0x00) end
  end
end

breakpoints_available = pcall(function()
  -- The two stock entries publish H immediately before the shared 0x42A7
  -- copy path. Track the control flow because this mGBA build does not expose
  -- CPU H reliably through Lua.
  emu:setBreakpoint(function() tile_copy_map_hi = 0x9C end, 0x42A0)
  emu:setBreakpoint(function() tile_copy_map_hi = 0x98 end, 0x42A5)
  emu:setBreakpoint(function()
    if phase == "play" then
      main_loop_hits = main_loop_hits + 1
      if last_main_loop_frame >= 0 then
        local gap = play_frames - last_main_loop_frame
        if gap > max_main_loop_gap then max_main_loop_gap = gap end
      end
      last_main_loop_frame = play_frames
    end
  end, 0x016C)
  emu:setBreakpoint(function()
    if phase == "play" then
      central_emitter_hits = central_emitter_hits + 1
    end
  end, 0x10D1)
  emu:setBreakpoint(function()
    if phase == "play" then free_emitter_hits = free_emitter_hits + 1 end
  end, 0x346F)
  emu:setBreakpoint(function()
    if phase == "play" then
      tile_copy_hits = tile_copy_hits + 1
      profile_lava_attr_map()
    end
  end, 0x42A7)
  if ATOMIC_ADDR > 0 then
    emu:setBreakpoint(function()
      if phase == "play" then
        atomic_attr_passes = atomic_attr_passes + 1
        atomic_call_indices[#atomic_call_indices + 1] = lava_copy_hits
      end
    end, ATOMIC_ADDR)
  end
end)

local function finish()
  if finished then return end
  finished = true
  local handle = assert(io.open(OUT, "w"))
  handle:write("{\n")
  handle:write(string.format('  "target": %d,\n', TARGET))
  handle:write(string.format('  "stage": %d,\n', TARGET + 1))
  handle:write(string.format('  "expected_scene": %d,\n', EXPECTED_SCENE))
  handle:write(string.format('  "final_scene": %d,\n', emu:read8(0xD880)))
  handle:write(string.format('  "frames": %d,\n', play_frames))
  handle:write(string.format(
    '  "breakpoints_available": %s,\n', tostring(breakpoints_available)))
  handle:write(string.format('  "main_loop_hits": %d,\n', main_loop_hits))
  handle:write(string.format(
    '  "last_main_loop_frame": %d,\n', last_main_loop_frame))
  handle:write(string.format(
    '  "max_main_loop_gap": %d,\n', max_main_loop_gap))
  handle:write(string.format(
    '  "central_emitter_hits": %d,\n', central_emitter_hits))
  handle:write(string.format('  "free_emitter_hits": %d,\n', free_emitter_hits))
  handle:write(string.format('  "tile_copy_hits": %d,\n', tile_copy_hits))
  handle:write(string.format('  "atomic_attr_passes": %d,\n', atomic_attr_passes))
  handle:write(string.format(
    '  "atomic_call_indices": [%s],\n',
    table.concat(atomic_call_indices, ",")))
  handle:write(string.format('  "lava_copy_hits": %d,\n', lava_copy_hits))
  handle:write(string.format('  "attr_map_changes": %d,\n', attr_map_changes))
  handle:write(string.format('  "attr_map_unchanged": %d,\n', attr_map_unchanged))
  handle:write(string.format('  "attr_changed_cells": %d,\n', attr_changed_cells))
  handle:write(string.format('  "attr_changed_groups": %d,\n', attr_changed_groups))
  handle:write(string.format(
    '  "max_attr_changed_cells": %d,\n', max_attr_changed_cells))
  handle:write(string.format(
    '  "max_attr_changed_groups": %d,\n', max_attr_changed_groups))
  handle:write(string.format('  "scroll_changes": %d,\n', scroll_changes))
  handle:write(string.format('  "active_frames": %d,\n', active_frames))
  handle:write(string.format(
    '  "first_inactive_frame": %d,\n', first_inactive_frame))
  handle:write(string.format(
    '  "first_inactive_state": "%s",\n', first_inactive_state))
  handle:write(string.format(
    '  "expected_scene_frames": %d,\n', expected_scene_frames))
  handle:write(string.format(
    '  "dma_unreadable_scene_samples": %d,\n',
    dma_unreadable_scene_samples))
  handle:write(string.format(
    '  "non_dma_scene_mismatch_frames": %d,\n',
    non_dma_scene_mismatch_frames))
  handle:write(string.format(
    '  "first_scene_mismatch": %d,\n', first_scene_mismatch))
  handle:write(string.format(
    '  "first_scene_mismatch_value": %d,\n', first_scene_mismatch_value))
  handle:write(string.format('  "mismatch_cpu_pc": %d,\n', mismatch_cpu_pc))
  handle:write(string.format(
    '  "mismatch_dma_source": %d,\n', mismatch_dma_source))
  handle:write(string.format('  "mismatch_svbk": %d,\n', mismatch_svbk))
  handle:write(string.format('  "room": %d,\n', emu:read8(0xFFBD)))
  handle:write(string.format('  "ffc1": %d\n', emu:read8(0xFFC1)))
  handle:write("}\n")
  handle:close()
  if attr_trace then attr_trace:close(); attr_trace = nil end
  local marker = assert(io.open(DONE, "w"))
  marker:write("OK")
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
    emu:write8(0xFFBA, TARGET)
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

  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)

  if phase == "loading" then
    emu:write8(0xFFBA, TARGET)
    emu:setKeys(0)
    if emu:read8(0xD880) == EXPECTED_SCENE
        and emu:read8(0xFFC1) == 1 then
      stable_frames = stable_frames + 1
      if stable_frames >= 120 then
        phase = "play"
        previous_scx = emu:read8(0xFF43)
      end
    else
      stable_frames = 0
    end
    if frame > 30000 then finish() end
    return
  end

  play_frames = play_frames + 1
  local sampled_scene = emu:read8(0xD880)
  if sampled_scene == EXPECTED_SCENE then
    expected_scene_frames = expected_scene_frames + 1
  else
    local sampled_pc = read_register("PC")
    local sampled_dma_source = emu:read8(0xFF46)
    local dma_unreadable = sampled_scene == 0xFF
      and sampled_pc >= 0xFF80 and sampled_pc <= 0xFF9F
      and (sampled_dma_source == 0xC0 or sampled_dma_source == 0xC1)
    if dma_unreadable then
      dma_unreadable_scene_samples = dma_unreadable_scene_samples + 1
    else
      non_dma_scene_mismatch_frames = non_dma_scene_mismatch_frames + 1
    end
    if first_scene_mismatch < 0 then
      first_scene_mismatch = play_frames
      first_scene_mismatch_value = sampled_scene
      mismatch_cpu_pc = sampled_pc
      mismatch_dma_source = sampled_dma_source
      mismatch_svbk = emu:read8(0xFF70)
    end
  end
  if emu:read8(0xFFC1) == 1 then
    active_frames = active_frames + 1
  elseif first_inactive_frame < 0 then
    first_inactive_frame = play_frames
    first_inactive_state = string.format(
      "pc:%04X room:%02X scx:%02X scy:%02X ffe4:%02X " ..
        "dc00:%02X dc01:%02X dc02:%02X dc03:%02X",
      read_register("PC") & 0xFFFF, emu:read8(0xFFBD),
      emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xFFE4),
      emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC02), emu:read8(0xDC03))
    emu:screenshot(OUT .. ".first-inactive.png")
  end
  if INPUT_MODE == "stationary" then
    emu:setKeys(0)
  elseif INPUT_MODE == "patrol" then
    if play_frames % 120 < 60 then emu:setKeys(KEY_RIGHT)
    else emu:setKeys(KEY_LEFT) end
  else
    emu:setKeys(KEY_RIGHT)
  end

  local scx = emu:read8(0xFF43)
  if scx ~= previous_scx then scroll_changes = scroll_changes + 1 end
  previous_scx = scx

  if play_frames >= LIMIT then finish() end
end)
