-- Injection-free Stage-1 OBJ visual contract probe.
--
-- The Python driver retargets only serialized ROM identity metadata of the reviewed
-- scene-$0B operator capture.  This probe then applies native SELECT pulses
-- and records, on every audited frame:
--
--   * all 64 bytes of hardware OBJ CRAM;
--   * every geometrically visible hardware-OAM entry; and
--   * the physical VRAM-bank-0 patterns selected by that entry.
--
-- It never writes gameplay state, OAM, CRAM, or VRAM.  The only writes are
-- joypad input and repo-local evidence files.  Bank-one OBJ selection is
-- recorded in the OAM attribute and rejected by the offline verifier; the
-- mGBA raw-VRAM domain used below is deliberately bank zero only.

local OUT = assert(
  os.getenv("PENTA_STAGE1_OBJ_OUT"), "PENTA_STAGE1_OBJ_OUT required")
local STATE_FILE = assert(
  os.getenv("PENTA_STAGE1_OBJ_STATE"), "PENTA_STAGE1_OBJ_STATE required")
local STARTUP_TOKEN = assert(
  os.getenv("PENTA_STAGE1_OBJ_TOKEN"), "PENTA_STAGE1_OBJ_TOKEN required")
local FRAME_LIMIT = tonumber(
  os.getenv("PENTA_STAGE1_OBJ_FRAME_LIMIT") or "720")
local BASELINE_FRAMES = tonumber(
  os.getenv("PENTA_STAGE1_OBJ_BASELINE_FRAMES") or "12")
local MENU_HOLD_FRAMES = tonumber(
  os.getenv("PENTA_STAGE1_OBJ_MENU_HOLD_FRAMES") or "60")
local POST_CLOSE_FRAMES = tonumber(
  os.getenv("PENTA_STAGE1_OBJ_POST_CLOSE_FRAMES") or "60")

local KEY_SELECT = 0x04
local frame = 0
local sample = 0
local phase = "load"
local phase_frame = 0
local state_loaded = false
local finished = false
local raw_vram = nil
local obj_cram = nil
local trace = nil
local stable_frames = 0
local menu_open_events = 0
local menu_close_events = 0
local obj_cram_domain_samples = 0
local obj_cram_index_samples = 0
local obj_cram_restore_failures = 0
local last_menu_owned = false
local sampled_by_phase = {
  baseline = 0,
  menu_entry = 0,
  menu_hold = 0,
  menu_exit = 0,
  post_close = 0,
}

local function marker_path(suffix)
  return OUT .. suffix
end

local function write_token_marker(suffix, status)
  local path = marker_path(suffix)
  local temporary = path .. ".tmp"
  local handle = assert(io.open(temporary, "w"))
  if status then handle:write("status=" .. status .. "\n") end
  handle:write("startup_token=" .. STARTUP_TOKEN .. "\n")
  handle:close()
  assert(os.rename(temporary, path))
end

write_token_marker(".startup")

local function window_visible()
  local lcdc = emu:read8(0xFF40)
  return (lcdc & 0x20) ~= 0 and emu:read8(0xFF4A) < 144
end

local function menu_owned()
  return emu:read8(0xFFE4) ~= 0 or window_visible()
end

local function set_phase(value)
  phase = value
  phase_frame = 0
end

local function hex_byte(value)
  return string.format("%02X", value & 0xFF)
end

local function obj_cram_hex()
  local raw
  if obj_cram then
    raw = obj_cram:readRange(0, 64)
    obj_cram_domain_samples = obj_cram_domain_samples + 1
  else
    -- The checked blackmage mGBA build does not publish the optional
    -- cgbObjPalette memory domain.  Read through OCPS/OCPD while the frame
    -- callback has the core paused, then restore the complete selector byte.
    -- OCPD is never written, so palette data cannot be changed by the probe.
    local old_index = emu:read8(0xFF6A)
    local values = {}
    for index = 0, 63 do
      emu:write8(0xFF6A, index)
      values[#values + 1] = string.char(emu:read8(0xFF6B))
    end
    emu:write8(0xFF6A, old_index)
    if emu:read8(0xFF6A) ~= old_index then
      obj_cram_restore_failures = obj_cram_restore_failures + 1
    end
    obj_cram_index_samples = obj_cram_index_samples + 1
    raw = table.concat(values)
  end
  assert(raw and #raw == 64, "OBJ CRAM observer returned the wrong size")
  local parts = {}
  for index = 1, 64 do
    parts[index] = hex_byte(string.byte(raw, index))
  end
  return table.concat(parts)
end

local function pattern_hex(tile, sprite_8x16)
  local first = sprite_8x16 and (tile & 0xFE) or tile
  local count = sprite_8x16 and 32 or 16
  local parts = {}
  for offset = 0, count - 1 do
    -- emu.memory.vram is bank zero in the reviewed mGBA build.  Do not add
    -- $2000 or touch VBK here: attr bit 3 is preserved in the OAM evidence
    -- and the offline contract rejects every bank-one visible object.
    parts[#parts + 1] = hex_byte(
      raw_vram:read8(first * 16 + offset))
  end
  return table.concat(parts)
end

local function visible_oam_text(lcdc)
  local rows = {}
  local sprite_8x16 = (lcdc & 0x04) ~= 0
  local height = sprite_8x16 and 16 or 8
  for slot = 0, 39 do
    local base = 0xFE00 + slot * 4
    local y = emu:read8(base)
    local x = emu:read8(base + 1)
    local tile = emu:read8(base + 2)
    local attr = emu:read8(base + 3)
    local left = x - 8
    local top = y - 16
    if left < 160 and left + 8 > 0 and top < 144 and top + height > 0 then
      rows[#rows + 1] = string.format(
        "%d,%d,%d,%d,%d,%s",
        slot, y, x, tile, attr, pattern_hex(tile, sprite_8x16))
    end
  end
  return table.concat(rows, ";")
end

local function capture_sample()
  local lcdc = emu:read8(0xFF40)
  sample = sample + 1
  sampled_by_phase[phase] = sampled_by_phase[phase] + 1
  trace:write(string.format(
    "%d\t%d\t%s\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%s\t%s\n",
    sample,
    frame,
    phase,
    phase_frame,
    emu:read8(0xD880),
    emu:read8(0xFFC1),
    emu:read8(0xFFBD),
    menu_owned() and 1 or 0,
    emu:read8(0xFFE4),
    lcdc,
    emu:read8(0xFFBE),
    emu:read8(0xFFBF),
    emu:read8(0xFFC0),
    emu:read8(0xFFD0),
    emu:read8(0xDF04),
    obj_cram_hex(),
    visible_oam_text(lcdc)))
  trace:flush()
end

local function write_report(status, reason)
  local path = marker_path(".report")
  local temporary = path .. ".tmp"
  local handle = assert(io.open(temporary, "w"))
  handle:write("status=" .. status .. "\n")
  handle:write("reason=" .. reason .. "\n")
  handle:write("startup_token=" .. STARTUP_TOKEN .. "\n")
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("samples=%d\n", sample))
  handle:write(string.format("menu_open_events=%d\n", menu_open_events))
  handle:write(string.format("menu_close_events=%d\n", menu_close_events))
  handle:write(string.format(
    "obj_cram_domain_samples=%d\n", obj_cram_domain_samples))
  handle:write(string.format(
    "obj_cram_index_samples=%d\n", obj_cram_index_samples))
  handle:write(string.format(
    "obj_cram_restore_failures=%d\n", obj_cram_restore_failures))
  for _, name in ipairs({
    "baseline", "menu_entry", "menu_hold", "menu_exit", "post_close",
  }) do
    handle:write(string.format(
      "samples_%s=%d\n", name, sampled_by_phase[name]))
  end
  handle:close()
  assert(os.rename(temporary, path))
end

local function finish(status, reason)
  if finished then return end
  finished = true
  emu:setKeys(0)
  if trace then trace:close() end
  write_report(status, reason)
  write_token_marker(".done", status)
  emu:stop()
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if frame > FRAME_LIMIT then
    finish("fail", "frame-limit")
    return
  end

  if not raw_vram then
    local ok_vram, vram = pcall(function()
      return emu.memory and emu.memory.vram
    end)
    local ok_cram, cram = pcall(function()
      return emu.memory and emu.memory.cgbObjPalette
    end)
    if not ok_vram or not vram then
      finish("fail", "vram-domain-unavailable")
      return
    end
    if not ok_cram then cram = nil end
    raw_vram = vram
    obj_cram = cram
    trace = assert(io.open(marker_path(".trace.tsv"), "w"))
    trace:write(
      "sample\tframe\tphase\tphase_frame\tscene\tactive\troom" ..
      "\tmenu_owned\tffe4\tlcdc\tffbe\tffbf\tffc0\tffd0\tdf04\tobj_cram" ..
      "\tvisible_oam\n")
    trace:flush()
    write_token_marker(".core-ready")
  end

  if not state_loaded then
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_FILE)
    end)
    if not ok or result == false then
      finish("fail", "state-load-failed: " .. tostring(result))
      return
    end
    state_loaded = true
    last_menu_owned = menu_owned()
    set_phase("settle")
    emu:setKeys(0)
    return
  end

  -- D880 is in banked WRAM.  A frame can land inside the compiler with SVBK3
  -- selected; do not invent a scene transition from the wrong physical bank.
  if (emu:read8(0xFF70) & 0x07) ~= 1 then
    emu:setKeys(0)
    return
  end

  phase_frame = phase_frame + 1
  if emu:read8(0xD880) ~= 0x0B then
    finish("fail", "scene-left-0B")
    return
  end
  if emu:read8(0xFFC1) ~= 0x01 then
    finish("fail", "active-state-left-01")
    return
  end

  local owned = menu_owned()
  if owned and not last_menu_owned then
    menu_open_events = menu_open_events + 1
  elseif last_menu_owned and not owned then
    menu_close_events = menu_close_events + 1
  end
  last_menu_owned = owned

  local keys = 0
  if phase == "settle" then
    -- Begin from a completely loaded closed-menu deck.  This excludes the
    -- authenticated negative seed itself while retaining every candidate-
    -- rendered entry/exit frame below.
    if not owned and emu:read8(0xDF04) == 0 then
      stable_frames = stable_frames + 1
    else
      stable_frames = 0
    end
    if stable_frames >= 8 then set_phase("baseline") end
  elseif phase == "baseline" then
    capture_sample()
    if phase_frame >= BASELINE_FRAMES then set_phase("menu_entry") end
  elseif phase == "menu_entry" then
    if ((phase_frame - 1) % 8) < 2 then keys = KEY_SELECT end
    capture_sample()
    if owned and window_visible() then
      keys = 0
      set_phase("menu_hold")
    elseif phase_frame > 180 then
      finish("fail", "select-open-not-acknowledged")
      return
    end
  elseif phase == "menu_hold" then
    capture_sample()
    if not owned or not window_visible() then
      finish("fail", "menu-lost-during-hold")
      return
    end
    if phase_frame >= MENU_HOLD_FRAMES then set_phase("menu_exit") end
  elseif phase == "menu_exit" then
    if ((phase_frame - 1) % 8) < 2 then keys = KEY_SELECT end
    capture_sample()
    if not owned and not window_visible() then
      keys = 0
      set_phase("post_close")
    elseif phase_frame > 180 then
      finish("fail", "select-close-not-acknowledged")
      return
    end
  elseif phase == "post_close" then
    capture_sample()
    if owned then
      finish("fail", "menu-reopened-during-post-close")
      return
    end
    if phase_frame >= POST_CLOSE_FRAMES then
      finish("ok", "complete")
      return
    end
  else
    finish("fail", "unknown-phase")
    return
  end

  emu:setKeys(keys)
end)
