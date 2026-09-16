-- Full pre/post-final production inventory in mGBA.
-- The ROM is unchanged: a diagnostic-only WRAM stub enters the stock bank-1
-- continuation after the title has initialized the real CGB runtime.

local OUT = assert(os.getenv("ENDING_INVENTORY_OUT"))
local MAX_FRAMES = tonumber(os.getenv("ENDING_INVENTORY_MAX_FRAMES") or "32000")
local SAMPLE_INTERVAL = tonumber(
  os.getenv("ENDING_INVENTORY_SAMPLE_INTERVAL") or "90")
assert(SAMPLE_INTERVAL >= 1, "ENDING_INVENTORY_SAMPLE_INTERVAL must be positive")
local ENTRY = os.getenv("ENDING_INVENTORY_ENTRY") or "post-final"
local PRE_FINAL = ENTRY == "pre-final"
local PRE_FINAL_MASK = PRE_FINAL and assert(os.getenv("ENDING_INVENTORY_PRE_FINAL_MASK")) or nil
local WRAM_STUB = 0xDF60
local TARGET = PRE_FINAL and 0x54C0 or 0x5513
local EXPECTED_SCENE = PRE_FINAL and 0x19 or 0x1A
local EXPECTED_SEQUENCE = PRE_FINAL and 0x04 or 0x05
local INITIAL_FFBA = PRE_FINAL and 0x06 or 0x08
local INITIAL_FFE4 = PRE_FINAL and 0x00 or 0x01
local KEY_A = 0x01
local TRACE_BGP = os.getenv("ENDING_INVENTORY_BGP_TRACE") == "1"
local TRACE_BGP_ALL = os.getenv("ENDING_INVENTORY_BGP_TRACE_ALL") == "1"
local TRACE_CRAM = os.getenv("ENDING_INVENTORY_CRAM_TRACE") == "1"
local CRAM_TRACE_MIN_FRAME = tonumber(
  os.getenv("ENDING_INVENTORY_CRAM_TRACE_MIN_FRAME") or "0")
local CRAM_TRACE_MAX_FRAME = tonumber(
  os.getenv("ENDING_INVENTORY_CRAM_TRACE_MAX_FRAME") or "9200")

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
  table.insert(code, 0x3E); table.insert(code, INITIAL_FFBA)
  table.insert(code, 0xE0); table.insert(code, 0xBA)
  table.insert(code, 0x3E); table.insert(code, INITIAL_FFE4)
  table.insert(code, 0xE0); table.insert(code, 0xE4)
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
local full_story = PRE_FINAL
  and {[4]=false, [7]=false}
  or {[5]=false, [6]=false, [7]=false}
local full_phase = {credits=false, ending=false, preamble=false, epilogue=false}
local pre_final_sequence = {}
local pre_final_return_complete = false
local function observe_pre_final(scene, state)
  if scene == 0x19 and state.dce8 == 4 and state.dcea == 1
      and state.dd07 + 1 == state.dcf0
      and pre_final_sequence[#pre_final_sequence] ~= state.dcf0 then
    pre_final_sequence[#pre_final_sequence + 1] = state.dcf0
  end
end
local function pre_final_complete()
  return #pre_final_sequence == 3 and pre_final_sequence[1] == 4
    and pre_final_sequence[2] == 7 and pre_final_sequence[3] == 4
end
local report = assert(io.open(OUT .. ".tsv", "w"))
report:write(
  "frame\tscene\tffc1\tffba\tffe4\tpalettes\tunsafe\ttable_bad\t" ..
  "tilemap_hex\tattribute_hex\twindow_tilemap_hex\t" ..
  "window_attribute_hex\toam_hex\tshadow_c000_hex\t" ..
  "shadow_c100_hex\tstate\timage\n")
local bgp_trace = nil
local fade_call_trace = nil
if TRACE_BGP then
  bgp_trace = assert(io.open(OUT .. ".bgp.tsv", "w"))
  bgp_trace:write(
    "frame\tscene\told\tnew\tpc\tsp\tff99\tsvbk\ta\tf\tsp0\tsp1\tsp2\tsp3\tsp4\tsp5\tsp6\tsp7" ..
    "\tbank1_callret\tbank2_callret\tbank3_callret\tbank4_callret" ..
    "\tbank5_callret\tbank6_callret\tbank7_callret\n")
  assert(emu:setWatchpoint(function(info)
    local scene = assert(emu.memory.wram):read8(0x1880)
    if not TRACE_BGP_ALL
        and scene ~= 0x00 and scene ~= 0x16
        and scene ~= 0x19 and scene ~= 0x1A then
      return
    end
    local sp = emu:readRegister("SP") & 0xFFFF
    local words = {}
    for depth = 0, 7 do
      local address = (sp + depth * 2) & 0xFFFF
      words[#words + 1] = emu:read8(address)
        | (emu:read8((address + 1) & 0xFFFF) << 8)
    end
    local physical_callers = {}
    local stack_offset = ((sp + 6) & 0xFFFF) - 0xD000
    for bank = 1, 7 do
      local offset = bank * 0x1000 + stack_offset
      physical_callers[#physical_callers + 1] =
        assert(emu.memory.wram):read8(offset)
        | (assert(emu.memory.wram):read8(offset + 1) << 8)
    end
    bgp_trace:write(string.format(
      "%d\t%02X\t%02X\t%02X\t%04X\t%04X\t%02X\t%02X" ..
      "\t%02X\t%02X\t%04X\t%04X\t%04X\t%04X\t%04X\t%04X\t%04X\t%04X" ..
      "\t%04X\t%04X\t%04X\t%04X\t%04X\t%04X\t%04X\n",
      frame, scene, info.oldValue & 0xFF, info.newValue & 0xFF,
      emu:readRegister("PC") & 0xFFFF, sp, emu:read8(0xFF99),
      emu:read8(0xFF70) & 0x07,
      emu:readRegister("A") & 0xFF, emu:readRegister("F") & 0xF0,
      words[1], words[2], words[3], words[4], words[5], words[6],
      words[7], words[8],
      physical_callers[1], physical_callers[2], physical_callers[3],
      physical_callers[4], physical_callers[5], physical_callers[6],
      physical_callers[7]))
    bgp_trace:flush()
  end, 0xFF47, C.WATCHPOINT_TYPE.WRITE) > 0)
  fade_call_trace = assert(io.open(OUT .. ".fade-call.tsv", "w"))
  fade_call_trace:write("frame\tscene\taf\tbc\tde\thl\tsp\tff99\tsvbk\n")
  for _, site in ipairs({0x3097, 0x3735, 0x73BA}) do
    local watched = site
    assert(emu:setBreakpoint(function()
      local scene = assert(emu.memory.wram):read8(0x1880)
      if scene ~= 0x16 and scene ~= 0x19 and scene ~= 0x1A then return end
      fade_call_trace:write(string.format(
        "%d:%04X\t%02X\t%04X\t%04X\t%04X\t%04X\t%04X\t%02X\t%02X\n",
        frame, watched, scene, emu:readRegister("AF") & 0xFFFF,
        emu:readRegister("BC") & 0xFFFF, emu:readRegister("DE") & 0xFFFF,
        emu:readRegister("HL") & 0xFFFF, emu:readRegister("SP") & 0xFFFF,
        emu:read8(0xFF99), emu:read8(0xFF70) & 0x07))
      fade_call_trace:flush()
    end, watched, watched < 0x4000 and 0 or 1) > 0)
  end
end

local cram_trace = nil
local cram_trace_writes = 0
if TRACE_CRAM then
  cram_trace = assert(io.open(OUT .. ".cram.tsv", "w"))
  cram_trace:write(
    "frame\tscene\tbcps\told\tnew\tpc\tsp\tff99\tsvbk\tsp0\tsp1\tsp2\tsp3\n")
  assert(emu:setWatchpoint(function(info)
    local scene = assert(emu.memory.wram):read8(0x1880)
    local bgp = emu:read8(0xFF47)
    local hidden_fade = bgp == 0x00 or bgp == 0x40 or bgp == 0x90
      or bgp == 0xF9 or bgp == 0xFE or bgp == 0xFF
    if frame < CRAM_TRACE_MIN_FRAME or frame >= CRAM_TRACE_MAX_FRAME
        or cram_trace_writes >= 4096 or not hidden_fade
        or (scene ~= 0x00 and scene ~= 0x16 and scene ~= 0x19
          and scene ~= 0x1A) then return end
    local sp = emu:readRegister("SP") & 0xFFFF
    local words = {}
    for depth = 0, 3 do
      local address = (sp + depth * 2) & 0xFFFF
      words[#words + 1] = emu:read8(address)
        | (emu:read8((address + 1) & 0xFFFF) << 8)
    end
    cram_trace_writes = cram_trace_writes + 1
    cram_trace:write(string.format(
      "%d\t%02X\t%02X\t%02X\t%02X\t%04X\t%04X\t%02X\t%02X" ..
      "\t%04X\t%04X\t%04X\t%04X\n",
      frame, scene, emu:read8(0xFF68), info.oldValue & 0xFF,
      info.newValue & 0xFF, emu:readRegister("PC") & 0xFFFF, sp,
      emu:read8(0xFF99), emu:read8(0xFF70) & 0x07,
      words[1], words[2], words[3], words[4]))
    cram_trace:flush()
  end, 0xFF69, C.WATCHPOINT_TYPE.WRITE) > 0)
end

local STATE_NAMES = {
  "df07", "df49", "df4a", "df4b", "df4c", "df50", "df63", "d889", "dce2", "dce5", "dce6",
  "dce7", "dce8", "dce9", "dcea", "dceb", "dcee", "dcef", "dcf0",
  "dd07", "bgp",
}
local STATE_ADDRS = {
  0xDF07, 0xDF49, 0xDF4A, 0xDF4B, 0xDF4C, 0xDF50, 0xDF63, 0xD889, 0xDCE2, 0xDCE5, 0xDCE6,
  0xDCE7, 0xDCE8, 0xDCE9, 0xDCEA, 0xDCEB, 0xDCEE, 0xDCEF, 0xDCF0,
  0xDD07, 0xFF47,
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

local function raw_map_layout(base)
  local old_vbk = emu:read8(0xFF4F)
  local tiles, attrs = {}, {}
  for row = 0, 17 do
    for column = 0, 19 do
      local address = base + row * 32 + column
      emu:write8(0xFF4F, 0)
      tiles[#tiles + 1] = string.format("%02X", emu:read8(address))
      emu:write8(0xFF4F, 1)
      attrs[#attrs + 1] = string.format("%02X", emu:read8(address))
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(tiles), table.concat(attrs)
end

local function oam_layout()
  local values = {}
  for address = 0xFE00, 0xFE9F do
    values[#values + 1] = string.format("%02X", emu:read8(address))
  end
  return table.concat(values)
end

local function byte_range(first, last)
  local values = {}
  for address = first, last do
    values[#values + 1] = string.format("%02X", emu:read8(address))
  end
  return table.concat(values)
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
    values.ffd4 = emu:read8(0xFFD4)
    values.ff99 = emu:read8(0xFF99)
    values.pc = emu:readRegister("PC") & 0xFFFF
    values.sp = emu:readRegister("SP") & 0xFFFF
    encoded[#encoded + 1] = string.format("lcdc:%02X", values.lcdc)
    encoded[#encoded + 1] = string.format("scy:%02X", values.scy)
    encoded[#encoded + 1] = string.format("scx:%02X", values.scx)
    encoded[#encoded + 1] = string.format("fff9:%02X", values.fff9)
    encoded[#encoded + 1] = string.format("ffd4:%02X", values.ffd4)
    encoded[#encoded + 1] = string.format("ff99:%02X", values.ff99)
    encoded[#encoded + 1] = string.format("pc:%04X", values.pc)
    encoded[#encoded + 1] = string.format("sp:%04X", values.sp)
    -- Preserve and expose the complete CGB BG palette file. Fine-grained
    -- transition traces use this to distinguish an attribute publication
    -- defect from a CRAM write that landed outside an accessible LCD mode.
    local old_bcps = emu:read8(0xFF68)
    for index = 0, 63 do
      emu:write8(0xFF68, index)
      local name = string.format("bg%02x", index)
      local value = emu:read8(0xFF69)
      values[name] = value
      encoded[#encoded + 1] = string.format("%s:%02X", name, value)
    end
    emu:write8(0xFF68, old_bcps)
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
  local lcdc = emu:read8(0xFF40)
  local window_base = (lcdc & 0x40) ~= 0 and 0x9C00 or 0x9800
  local window_tiles, window_attrs = raw_map_layout(window_base)
  local oam = oam_layout()
  local shadow_c000 = byte_range(0xC000, 0xC09F)
  local shadow_c100 = byte_range(0xC100, 0xC19F)
  local state, state_text = state_values()
  if PRE_FINAL then
    observe_pre_final(scene, state)
    pre_final_return_complete = pre_final_complete() and attrs == PRE_FINAL_MASK
  end
  -- D880 publishes the scene one handoff before its story table becomes
  -- active. Enforce neutrality only after the committed D889/DCE2 guard;
  -- the preceding exact-black frame cannot consume C600.
  local table_active = scene == EXPECTED_SCENE
    and state.d889 == 0x01 and state.dce2 == 0x00
  local table_bad = (table_active and not table_is_neutral()) and 1 or 0
  local key = string.format(
    "%02X|%02X|%02X|%02X|%02X|%02X|%02X|%02X|%02X|%s",
    scene, state.d889, state.dce2, state.fff9, state.dce8, state.dcea,
    state.dcf0, state.bgp, state.df63, attrs)
  if not PRE_FINAL and key == last_key then return end
  last_key = key
  samples, unsafe_total = samples + 1, unsafe_total + unsafe
  table_bad_samples = table_bad_samples + table_bad

  local image = string.format("%s.panel%03d_f%d.png", OUT, samples, frame)
  emu:screenshot(image)
  report:write(string.format(
    "%d\t%02X\t%02X\t%02X\t%02X\t%s\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n",
    frame, scene, emu:read8(0xFFC1), emu:read8(0xFFBA),
    emu:read8(0xFFE4), palette_text, unsafe, table_bad,
    tiles, attrs, window_tiles, window_attrs, oam, shadow_c000,
    shadow_c100, state_text, image))
  report:flush()

  if scene == EXPECTED_SCENE and state.dce8 == EXPECTED_SEQUENCE
      and state.dcea == 1 and full_story[state.dcf0] ~= nil
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
  if bgp_trace then bgp_trace:flush(); bgp_trace:close() end
  if fade_call_trace then fade_call_trace:flush(); fade_call_trace:close() end
  local out = assert(io.open(OUT .. ".txt", "w"))
  out:write(string.format(
    "status=%s\nmessage=%s\nframes=%d\nsamples=%d\n" ..
    "table_bad_samples=%d\nunsafe_total=%d\nreturned=%d\n" ..
    "final_pc=%04X\nfinal_sp=%04X\nfinal_ff99=%02X\n" ..
    "final_ffba=%02X\nfinal_ffe4=%02X\n" ..
    "final_df50=%02X\nfinal_df63=%02X\nfinal_df6d=%02X\nfinal_df6e=%02X\n",
    status, message, frame, samples, table_bad_samples, unsafe_total,
    (game8(0xD880) < 2 and emu:read8(0xFFE4) == 0) and 1 or 0,
    emu:readRegister("PC") & 0xFFFF, emu:readRegister("SP") & 0xFFFF,
    emu:read8(0xFF99), emu:read8(0xFFBA),
    emu:read8(0xFFE4), game8(0xDF50), game8(0xDF63),
    game8(0xDF6D), game8(0xDF6E)))
  out:write("transitions=" .. table.concat(transitions, ",") .. "\n")
  out:write(string.format(
    "full_story=%d,%d,%d,%d\nfull_phases=%d,%d,%d,%d\n",
    full_story[4] and 1 or 0, full_story[5] and 1 or 0,
    full_story[6] and 1 or 0, full_story[7] and 1 or 0,
    full_phase.credits and 1 or 0,
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
  if scene == EXPECTED_SCENE and not reached then
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

  local ending = PRE_FINAL
    and (scene == 0x19 or scene == 0x18)
    or (scene == 0x1A or scene == 0x16 or (
      scene == 0x00 and emu:read8(0xFFE4) == 1
      and emu:read8(0xFFC1) == 0))
  -- Match the legacy production inventory's observation cadence. This lands
  -- after the story publisher's bounded 16-row commit instead of recording
  -- multiple intermediate halves of the same page.
  if reached and ending and frame % SAMPLE_INTERVAL == 0 then sample(scene) end

  -- A sample count is not a route boundary: the old 43-sample cutoff stopped
  -- on portrait 7 and never observed the required return to portrait 4.
  if PRE_FINAL and pre_final_return_complete and full_story[4] and full_story[7] then
    local complete = restored and table_bad_samples == 0 and unsafe_total == 0
    finish(complete and "ok" or "failed", "pre-final-corpus-complete")
  elseif reached and frame > 600 and scene < 2 and emu:read8(0xFFE4) == 0 then
    local complete = restored and samples > 0 and table_bad_samples == 0
      and unsafe_total == 0 and full_story[5] and full_story[6] and full_story[7]
      and full_phase.credits and full_phase.ending and full_phase.preamble
      and full_phase.epilogue
    finish(complete and "ok" or "failed", "returned-to-title")
  elseif frame >= MAX_FRAMES then
    finish("failed", reached and "ending-frame-limit" or (ENTRY .. "-entry-not-reached"))
  end
end)
