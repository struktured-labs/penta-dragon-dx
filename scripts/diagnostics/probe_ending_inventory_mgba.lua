-- Full post-final dialogue -> credits -> END -> epilogue inventory in mGBA.
-- The ROM is unchanged: a diagnostic-only WRAM stub enters the stock bank-1
-- continuation after the title has initialized the real CGB runtime.

local OUT = assert(os.getenv("ENDING_INVENTORY_OUT"))
local MAX_FRAMES = tonumber(os.getenv("ENDING_INVENTORY_MAX_FRAMES") or "32000")
local WRAM_STUB, TARGET = 0xDF60, 0x5513
local KEY_A = 0x01

local function emit16(code, value)
  table.insert(code, value & 0xFF)
  table.insert(code, (value >> 8) & 0xFF)
end
local function emit_ld_a16_a(code, address)
  code[#code + 1] = 0xEA
  emit16(code, address)
end
local function build_stub()
  local code = {0xAF}                       -- XOR A
  emit_ld_a16_a(code, 0xFFC1)
  emit_ld_a16_a(code, 0xDD09)
  emit_ld_a16_a(code, 0x6000)
  emit_ld_a16_a(code, 0x4000)
  table.insert(code, 0x3E); table.insert(code, 0x08)
  table.insert(code, 0xE0); table.insert(code, 0xBA) -- FFBA=8
  table.insert(code, 0x3E); table.insert(code, 0x01)
  table.insert(code, 0xE0); table.insert(code, 0xE4) -- FFE4=1
  table.insert(code, 0x3E); table.insert(code, 0x01)
  table.insert(code, 0xE0); table.insert(code, 0x99) -- FF99 bank shadow=1
  emit_ld_a16_a(code, 0x2100)               -- MBC bank 1
  table.insert(code, 0xC3)                  -- JP $5513
  emit16(code, TARGET)
  return code
end

local stub = build_stub()
local original_entry = {}
local frame, reached, installed, restored, done = 0, false, false, false, false
local transitions, last_scene, last_key = {}, -1, nil
local samples, table_bad_samples, unsafe_total = 0, 0, 0
local full_story = {[5]=false, [6]=false, [7]=false}
local full_phase = {credits=false, ending=false, preamble=false, epilogue=false}
local report = assert(io.open(OUT .. ".tsv", "w"))
report:write(
  "frame\tscene\tffc1\tffba\tffe4\tpalettes\tunsafe\ttable_bad\t" ..
  "tilemap_hex\tattribute_hex\tstate\timage\n")

local STATE_NAMES = {
  "df07", "df49", "df4a", "df4b", "d889", "dce2", "dce5", "dce6",
  "dce7", "dce8", "dce9", "dcea", "dceb", "dcee", "dcef", "dcf0",
  "dd07",
}
local STATE_ADDRS = {
  0xDF07, 0xDF49, 0xDF4A, 0xDF4B, 0xD889, 0xDCE2, 0xDCE5, 0xDCE6,
  0xDCE7, 0xDCE8, 0xDCE9, 0xDCEA, 0xDCEB, 0xDCEE, 0xDCEF, 0xDCF0,
  0xDD07,
}

local function with_svbk1(callback)
  local old = emu:read8(0xFF70)
  emu:write8(0xFF70, 1)
  local values = {callback()}
  emu:write8(0xFF70, old)
  return table.unpack(values)
end
local function game8(address)
  return with_svbk1(function() return emu:read8(address) end)
end
local function game_write8(address, value)
  with_svbk1(function() emu:write8(address, value) end)
end

local function visible_layout()
  local lcdc, scy, scx = emu:read8(0xFF40), emu:read8(0xFF42), emu:read8(0xFF43)
  local base = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
  local old_vbk = emu:read8(0xFF4F)
  local tiles, attrs, palettes, unsafe = {}, {}, {}, 0
  for row = 0, 17 do
    for column = 0, 19 do
      local map_y = ((scy + row * 8) >> 3) & 0x1F
      local map_x = ((scx + column * 8) >> 3) & 0x1F
      local address = base + map_y * 32 + map_x
      emu:write8(0xFF4F, 0)
      tiles[#tiles + 1] = string.format("%02X", emu:read8(address))
      emu:write8(0xFF4F, 1)
      local attr = emu:read8(address)
      attrs[#attrs + 1] = string.format("%02X", attr)
      local palette = attr & 7
      palettes[palette] = (palettes[palette] or 0) + 1
      if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  local counts = {}
  for palette = 0, 7 do
    if palettes[palette] then
      counts[#counts + 1] = string.format("%d:%d", palette, palettes[palette])
    end
  end
  return table.concat(tiles), table.concat(attrs), table.concat(counts, ","), unsafe, palettes
end

local function state_values()
  return with_svbk1(function()
    local values, encoded = {}, {}
    for index, address in ipairs(STATE_ADDRS) do
      local value = emu:read8(address)
      values[STATE_NAMES[index]] = value
      encoded[#encoded + 1] = string.format("%s:%02X", STATE_NAMES[index], value)
    end
    values.lcdc, values.scy, values.scx = emu:read8(0xFF40), emu:read8(0xFF42), emu:read8(0xFF43)
    values.fff9 = emu:read8(0xFFF9)
    encoded[#encoded + 1] = string.format("lcdc:%02X", values.lcdc)
    encoded[#encoded + 1] = string.format("scy:%02X", values.scy)
    encoded[#encoded + 1] = string.format("scx:%02X", values.scx)
    encoded[#encoded + 1] = string.format("fff9:%02X", values.fff9)
    return values, table.concat(encoded, ",")
  end)
end

local function table_is_neutral()
  for offset = 0, 0xFF do
    if emu:read8(0xC600 + offset) ~= 0 then return false end
  end
  return true
end

local function sample(scene)
  local tiles, attrs, palette_text, unsafe, palettes = visible_layout()
  local state, state_text = state_values()
  local table_bad = (scene == 0x1A and not table_is_neutral()) and 1 or 0
  local key = string.format(
    "%02X|%02X|%02X|%02X|%02X|%02X|%02X|%s",
    scene, state.d889, state.dce2, state.fff9, state.dce8, state.dcea,
    state.dcf0, attrs)
  if key == last_key then return end
  last_key = key
  samples, unsafe_total = samples + 1, unsafe_total + unsafe
  table_bad_samples = table_bad_samples + table_bad

  local image = string.format("%s.panel%03d_f%d.png", OUT, samples, frame)
  emu:screenshot(image)
  report:write(string.format(
    "%d\t%02X\t%02X\t%02X\t%02X\t%s\t%d\t%d\t%s\t%s\t%s\t%s\n",
    frame, scene, emu:read8(0xFFC1), emu:read8(0xFFBA),
    emu:read8(0xFFE4), palette_text, unsafe, table_bad,
    tiles, attrs, state_text, image))
  report:flush()

  if scene == 0x1A and state.dce8 == 0x05 and state.dcea == 1
      and state.dcf0 >= 5 and state.dcf0 <= 7
      and ((state.dd07 + 1) & 0xFF) == state.dcf0 then
    full_story[state.dcf0] = true
  elseif scene == 0x16 and state.fff9 == 0 and palettes[1] == 360 then
    full_phase.credits = true
  elseif scene == 0x16 and state.fff9 == 1 and palettes[2] == 360 then
    full_phase.ending = true
  elseif scene == 0x00 and state.d889 == 0x0C and state.dce2 == 0
      and palettes[0] == 360 then
    full_phase.preamble = true
  elseif scene == 0x00 and state.d889 == 0x0C and state.dce2 == 1
      and palettes[3] == 360 then
    full_phase.epilogue = true
  end
end

local function finish(status, message)
  if done then return end
  done = true
  report:flush(); report:close()
  local out = assert(io.open(OUT .. ".txt", "w"))
  out:write(string.format(
    "status=%s\nmessage=%s\nframes=%d\nsamples=%d\n" ..
    "table_bad_samples=%d\nunsafe_total=%d\nreturned=%d\n",
    status, message, frame, samples, table_bad_samples, unsafe_total,
    (game8(0xD880) < 2 and emu:read8(0xFFE4) == 0) and 1 or 0))
  out:write("transitions=" .. table.concat(transitions, ",") .. "\n")
  out:write(string.format(
    "full_story=%d,%d,%d\nfull_phases=%d,%d,%d,%d\n",
    full_story[5] and 1 or 0, full_story[6] and 1 or 0,
    full_story[7] and 1 or 0, full_phase.credits and 1 or 0,
    full_phase.ending and 1 or 0, full_phase.preamble and 1 or 0,
    full_phase.epilogue and 1 or 0))
  out:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n"); marker:close()
  emu:stop()
end

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  local scene = game8(0xD880)
  if frame == 30 and not installed then
    for offset = 0, 2 do original_entry[offset + 1] = emu.memory.cart0:read8(0x39C3 + offset) end
    emu.memory.cart0:write8(0x39C3, 0xC3)
    emu.memory.cart0:write8(0x39C4, WRAM_STUB & 0xFF)
    emu.memory.cart0:write8(0x39C5, (WRAM_STUB >> 8) & 0xFF)
    installed = true
  end
  if installed and not reached then
    for index, byte in ipairs(stub) do game_write8(WRAM_STUB + index - 1, byte) end
  end
  if scene == 0x1A and not reached then
    reached = true
    game_write8(0xDF0D, 0xFF)
    emu:write8(0xFF91, 1)
    for offset = 0, 2 do emu.memory.cart0:write8(0x39C3 + offset, original_entry[offset + 1]) end
    restored = true
  end
  if scene ~= last_scene then
    transitions[#transitions + 1] = string.format("%d:%02X", frame, scene)
    last_scene = scene
  end

  if reached and frame % 90 < 4 then emu:setKeys(KEY_A) else emu:setKeys(0) end

  local ending = scene == 0x1A or scene == 0x16 or (
    scene == 0x00 and emu:read8(0xFFE4) == 1 and emu:read8(0xFFC1) == 0)
  -- Match the legacy production inventory's observation cadence. This lands
  -- after the story publisher's bounded 16-row commit instead of recording
  -- multiple intermediate halves of the same page.
  if reached and ending and frame % 90 == 0 then sample(scene) end

  if reached and frame > 600 and scene < 2 and emu:read8(0xFFE4) == 0 then
    local complete = restored and samples > 0 and table_bad_samples == 0
      and unsafe_total == 0 and full_story[5] and full_story[6] and full_story[7]
      and full_phase.credits and full_phase.ending and full_phase.preamble
      and full_phase.epilogue
    finish(complete and "ok" or "failed", "returned-to-title")
  elseif frame >= MAX_FRAMES then
    finish("failed", reached and "ending-frame-limit" or "post-final-entry-not-reached")
  end
end)
