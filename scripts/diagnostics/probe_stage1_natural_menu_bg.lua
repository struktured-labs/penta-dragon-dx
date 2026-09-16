-- Fail-closed natural-route probe for item-menu colors leaking into Stage 1.
--
-- Unlike probe_menu_window_order.lua, this checks the *displayed gameplay BG*
-- plane rather than only the six Window rows.  The route performs an ordinary
-- cold boot from SRAM, remains stationary in room $05, opens SELECT, holds it,
-- and closes it.  No savestate or WRAM/VRAM normalization is permitted.

local OUT = assert(os.getenv("STAGE1_NATURAL_MENU_BG_OUT"))
local ROM_PATH = assert(os.getenv("STAGE1_NATURAL_MENU_BG_ROM"))
local ROM_SHA256 = assert(os.getenv("STAGE1_NATURAL_MENU_BG_ROM_SHA256"))
local LUT_PATH = assert(os.getenv("STAGE1_NATURAL_MENU_BG_LUT"))
local LUT_SHA256 = assert(os.getenv("STAGE1_NATURAL_MENU_BG_LUT_SHA256"))
local ART_PATH = assert(os.getenv("STAGE1_NATURAL_MENU_BG_ART"))
local ART_SHA256 = assert(os.getenv("STAGE1_NATURAL_MENU_BG_ART_SHA256"))
local LIMIT = tonumber(os.getenv("STAGE1_NATURAL_MENU_BG_FRAMES") or "1500")
local OPEN_FRAME = tonumber(os.getenv("STAGE1_NATURAL_MENU_BG_OPEN") or "1200")
local CLOSE_FRAME = tonumber(os.getenv("STAGE1_NATURAL_MENU_BG_CLOSE") or "1380")
local MENU_KEY_NAME = os.getenv("STAGE1_NATURAL_MENU_BG_KEY") or "select"
assert(MENU_KEY_NAME == "select" or MENU_KEY_NAME == "start")
local CLOSE_KEY_NAME = os.getenv("STAGE1_NATURAL_MENU_BG_CLOSE_KEY") or MENU_KEY_NAME
assert(CLOSE_KEY_NAME == "select" or CLOSE_KEY_NAME == "start" or CLOSE_KEY_NAME == "b")
local RASTER_BASELINE_FRAMES = tonumber(
  os.getenv("STAGE1_NATURAL_MENU_BG_RASTER_BASELINE_FRAMES") or "600")
local MOVE_START = tonumber(os.getenv("STAGE1_NATURAL_MENU_BG_MOVE_START") or "-1")
local MOVE_END = tonumber(os.getenv("STAGE1_NATURAL_MENU_BG_MOVE_END") or "-1")
local MOVE_NAME = os.getenv("STAGE1_NATURAL_MENU_BG_MOVE") or "none"
local EXPECTED_ROOM = tonumber(
  os.getenv("STAGE1_NATURAL_MENU_BG_EXPECTED_ROOM") or "05", 16)
assert(EXPECTED_ROOM ~= nil and EXPECTED_ROOM >= 0 and EXPECTED_ROOM <= 0xFF)
local FAULT_FF01 = os.getenv("STAGE1_NATURAL_MENU_BG_FAULT_FF01") == "1"
local FAULT_FF01_READ =
  os.getenv("STAGE1_NATURAL_MENU_BG_FAULT_FF01_READ") == "1"
local FAULT_FF01_READ_XOR = tonumber(
  os.getenv("STAGE1_NATURAL_MENU_BG_FAULT_FF01_READ_XOR") or "04", 16)
assert(FAULT_FF01_READ_XOR ~= nil and FAULT_FF01_READ_XOR >= 1
  and FAULT_FF01_READ_XOR <= 0xFF)
local FAULT_FF01_DIRTY_READ =
  os.getenv("STAGE1_NATURAL_MENU_BG_FAULT_FF01_DIRTY_READ") == "1"
local PUBLICATION_PC = tonumber(
  assert(os.getenv("STAGE1_NATURAL_MENU_BG_PUBLICATION_PC")), 16)
local PUBLICATION_SEGMENT = tonumber(
  assert(os.getenv("STAGE1_NATURAL_MENU_BG_PUBLICATION_SEGMENT")), 16)

local lut_file = assert(io.open(LUT_PATH, "rb"))
local gameplay_lut = assert(lut_file:read("*a"))
lut_file:close()
assert(#gameplay_lut == 0x100)
local art_file = assert(io.open(ART_PATH, "rb"))
local expected_art = assert(art_file:read("*a"))
art_file:close()
assert(#expected_art == 16 * 16)
local art_tiles = {
  0x01, 0x02, 0x03, 0x04,
  0x64, 0x65, 0x66, 0x67, 0x68, 0x69,
  0x74, 0x75, 0x76, 0x77, 0x78, 0x79,
}

local KEY_A = 0x01
local KEY_SELECT = 0x04
local MENU_KEY = MENU_KEY_NAME == "start" and 0x08 or KEY_SELECT
local CLOSE_KEY = CLOSE_KEY_NAME == "b" and 0x02
  or (CLOSE_KEY_NAME == "start" and 0x08 or KEY_SELECT)
local KEY_DOWN = 0x80
local MOVE_KEYS = {none = 0, right = 0x10, left = 0x20, up = 0x40, down = 0x80}
local MOVE_KEY = assert(MOVE_KEYS[MOVE_NAME])
local raw_vram = assert(emu.memory.vram)
-- Optional physical-bank observer; never switch SVBK to inspect entities.
local entity_trace = nil
if os.getenv("STAGE1_NATURAL_ENTITY_TRACE") == "1" then
  entity_trace = assert(io.open(OUT .. ".entities.tsv", "w"))
  entity_trace:write("frame\twram_dc00_deff\toam\thram\n")
end
local function entity_trace_frame(number)
  if not entity_trace or number < OPEN_FRAME - 120 then return end
  local wram = assert(emu.memory.wram)
  local state, oam, hram = {}, {}, {}
  for offset = 0x1C00, 0x1EFF do
    state[#state + 1] = string.format("%02X", wram:read8(offset))
  end
  for address = 0xFE00, 0xFE9F do
    oam[#oam + 1] = string.format("%02X", emu:read8(address))
  end
  for address = 0xFF80, 0xFFFE do
    hram[#hram + 1] = string.format("%02X", emu:read8(address))
  end
  entity_trace:write(string.format("%d\t%s\t%s\t%s\n", number,
    table.concat(state), table.concat(oam), table.concat(hram)))
end

local frame = 0
local finished = false
local baseline_frames = 0
local baseline_bad_frames = 0
local menu_frames = 0
local menu_bad_frames = 0
local post_close_frames = 0
local post_close_bad_frames = 0
local menu_mismatch_cells = 0
local post_close_mismatch_cells = 0
local first_menu_bad = nil
local first_post_close_bad = nil
local first_baseline_bad = nil
local first_gameplay = nil
local settled_art_mismatch_bytes = -1
local settled_art_examples = "none"
local art_writer_trace = {}
local settled_art_state = nil
local settled_df5b = -1
local last_preopen = nil
local first_window = nil
local first_closed = nil
local transitions = {}
local last_signature = ""
local menu_selector_trace = {}
local first_selector_lcdc = -1
local first_selector_dc0b = -1
local first_selector_frame = -1
local publication_latch_trace = {}
local publication_latch_fault = "none"
local semantic_write_trace = {}
local semantic_visible_writes = 0
local hardware_register_trace = {}
local publication_boundary_trace = {}
local target_map_mismatch_summary
local timer_isr_hits = 0
local timer_baseline_hits = 0
local timer_menu_hits = 0
local timer_post_close_hits = 0
local timer_last_frame = nil
local timer_max_frame_gap = 0
local timer_gap_trace = {}
local timer_last_cycle = nil
local timer_max_cycle_gap = 0
local temporal_raster_trace = {}
local obj_contract_trace = {}

local function read_register(name)
  local readers = {
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:getRegister(string.upper(name)) end,
    function() return emu:readRegister(string.lower(name)) end,
    function() return emu:readRegister(string.upper(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function trace_selector(tag)
  if tag == "fixed200e" and frame >= OPEN_FRAME
      and first_selector_lcdc < 0 then
    first_selector_lcdc = emu:read8(0xFF40)
    first_selector_dc0b = emu:read8(0xDC0B)
    first_selector_frame = frame
  end
  if #menu_selector_trace >= 128 then return end
  menu_selector_trace[#menu_selector_trace + 1] = string.format(
    "%s:f%d:pc%04X:b%02X:a%02X:lcdc%02X:dc0b%02X",
    tag, frame, read_register("PC"), emu:read8(0xFF99),
    read_register("A") & 0xFF, emu:read8(0xFF40), emu:read8(0xDC0B))
end

local function trace_hardware_state(tag)
  if frame < OPEN_FRAME - 30 or #hardware_register_trace >= 512 then return end
  hardware_register_trace[#hardware_register_trace + 1] = string.format(
    "%s:f%d:pc%04X:b%02X:ly%02X:s%d:lcdc%02X:e4%02X:dc0b%02X:ff01%02X:"
      .. "vbk%02X:svbk%02X:ff51%02X:ff52%02X:ff53%02X:ff54%02X:ff55%02X:"
      .. "df53%02X:df57%02X",
    tag, frame, read_register("PC"), emu:read8(0xFF99),
    emu:read8(0xFF44), emu:read8(0xFF41) & 0x03,
    emu:read8(0xFF40), emu:read8(0xFFE4), emu:read8(0xDC0B),
    emu:read8(0xFF01), emu:read8(0xFF4F), emu:read8(0xFF70),
    emu:read8(0xFF51), emu:read8(0xFF52), emu:read8(0xFF53),
    emu:read8(0xFF54), emu:read8(0xFF55), emu:read8(0xDF53),
    emu:read8(0xDF57))
end

pcall(function()
  -- Music is serviced by the fixed-bank Timer ISR.  Count it around the
  -- exact SELECT roundtrip so a visual pass cannot conceal interrupt
  -- starvation during the menu transition.
  emu:setBreakpoint(function()
    if frame < OPEN_FRAME - 120 then return end
    timer_isr_hits = timer_isr_hits + 1
    local cycle = emu:currentCycle()
    if timer_last_cycle ~= nil then
      timer_max_cycle_gap = math.max(timer_max_cycle_gap, cycle - timer_last_cycle)
    end
    if timer_last_frame ~= nil then
      timer_max_frame_gap = math.max(timer_max_frame_gap, frame - timer_last_frame)
      if frame - timer_last_frame > 1 and #timer_gap_trace < 32 then
        timer_gap_trace[#timer_gap_trace + 1] = string.format(
          "f%d:from%d:cycles%d:ly%d:e4%02X:lcdc%02X:resume%04X:bank%02X", frame,
          timer_last_frame, cycle - timer_last_cycle, emu:read8(0xFF44),
          emu:read8(0xFFE4), emu:read8(0xFF40),
          emu:read16(read_register("SP")), emu:read8(0xFF99))
      end
    end
    timer_last_cycle = cycle
    timer_last_frame = frame
    if frame < OPEN_FRAME then
      timer_baseline_hits = timer_baseline_hits + 1
    elseif frame < CLOSE_FRAME then
      timer_menu_hits = timer_menu_hits + 1
    else
      timer_post_close_hits = timer_post_close_hits + 1
    end
  end, 0x06B3)

  if os.getenv("STAGE1_ART_WRITER_TRACE") == "1" then
    for _, address in ipairs({0x9640, 0x9783}) do
      local watched = address
      assert(emu:setWatchpoint(function(info)
        if #art_writer_trace >= 512 then return end
        art_writer_trace[#art_writer_trace + 1] = string.format(
          "f%d:a%04X:pc%04X:b%02X:ly%d:mode%d:vbk%d:o%02X:n%02X",
          frame, watched, read_register("PC"), emu:read8(0xFF99),
          emu:read8(0xFF44), emu:read8(0xFF41) & 3,
          emu:read8(0xFF4F) & 1, info.oldValue & 255, info.newValue & 255)
      end, watched, C.WATCHPOINT_TYPE.WRITE) > 0)
    end
  end
  emu:setBreakpoint(function() trace_selector("fixed200e") end, 0x200E)
  emu:setBreakpoint(function() trace_selector("fixed2012") end, 0x2012)
  for _, address in ipairs({0x4020, 0x4023, 0x4030}) do
    emu:setBreakpoint(function()
      if emu:read8(0xFF99) == 0x14 then
        trace_selector(string.format("bank20_%04x", address))
      end
    end, address, 1)
  end
  emu:setRangeWatchpoint(function(info)
    if frame >= OPEN_FRAME - 30 and #menu_selector_trace < 128 then
      menu_selector_trace[#menu_selector_trace + 1] = string.format(
        "write40:f%d:pc%04X:b%02X:o%02X:n%02X:a%02X:dc0b%02X",
        frame, read_register("PC"), emu:read8(0xFF99),
        info.oldValue & 0xFF, info.newValue & 0xFF,
        read_register("A") & 0xFF, emu:read8(0xDC0B))
    end
  end, 0xFF40, 0xFF40, C.WATCHPOINT_TYPE.WRITE_CHANGE)
  emu:setRangeWatchpoint(function(info)
    local new_value = info.newValue & 0xFF
    if FAULT_FF01 and publication_latch_fault == "none"
        and info.address == 0xFF01 and frame >= CLOSE_FRAME
        and (new_value == 0x99 or new_value == 0x9D) then
      local flipped = new_value ~ 0x04
      publication_latch_fault = string.format(
        "f%d:pc%04X:%02X>%02X", frame, read_register("PC"),
        new_value, flipped)
      emu:write8(0xFF01, flipped)
    end
    if frame >= OPEN_FRAME - 30 and #publication_latch_trace < 256 then
      publication_latch_trace[#publication_latch_trace + 1] = string.format(
        "f%d:pc%04X:b%02X:%04X:%02X>%02X:lcdc%02X:dc0b%02X",
        frame, read_register("PC"), emu:read8(0xFF99), info.address,
        info.oldValue & 0xFF, info.newValue & 0xFF,
        emu:read8(0xFF40), emu:read8(0xDC0B))
    end
  end, 0xFF01, 0xFF02, C.WATCHPOINT_TYPE.WRITE)

  emu:setRangeWatchpoint(function(info)
    trace_hardware_state(string.format(
      "writeFF55:%02X>%02X", info.oldValue & 0xFF,
      info.newValue & 0xFF))
  end, 0xFF55, 0xFF55, C.WATCHPOINT_TYPE.WRITE)

  -- The dirty-latch read starts at $42ED in the shipping layout and at $42F0
  -- in the zero-cycle map-authority diagnostic layout.  Break before both
  -- possible LDH A,($01) instructions and require the opcode pair below so a
  -- layout-specific address cannot silently turn the negative control off.
  -- The dirty Stage-1 attribute path stores HDMA5 at bank 1:$4346, polls it
  -- at $4348, and reaches $4350 only after bit 7 reports inactive.  Pin all
  -- three boundaries plus the fixed LCDC publication store.
  for _, point in ipairs({
    {0x42ED, 1, "dirty-read"},
    {0x42F0, 1, "dirty-read"},
    {0x4328, 1, "latch-read"},
    {0x4346, 1, "attr-hdma-before"},
    {0x4350, 1, "attr-hdma-complete"},
  }) do
    local address, bank, tag = point[1], point[2], point[3]
    emu:setBreakpoint(function()
      local inject_map = tag == "latch-read" and FAULT_FF01_READ
      local dirty_read_opcode = tag == "dirty-read"
        and emu:read8(address) == 0xF0 and emu:read8(address + 1) == 0x01
      local inject_dirty = dirty_read_opcode and FAULT_FF01_DIRTY_READ
      if (inject_map or inject_dirty)
          and publication_latch_fault == "none"
          and frame >= CLOSE_FRAME then
        local value = emu:read8(0xFF01)
        if value == 0x99 or value == 0x9D then
          local mask = inject_dirty and 0x01 or FAULT_FF01_READ_XOR
          local flipped = value ~ mask
          emu:write8(0xFF01, flipped)
          publication_latch_fault = string.format(
            "read:f%d:pc%04X:%02X>%02X", frame, read_register("PC"),
            value, flipped)
        end
      end
      trace_hardware_state(tag)
    end, address, bank)
  end

  emu:setBreakpoint(function()
    local target_lcdc = read_register("A") & 0xFF
    local target = ((target_lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local should_sample = frame >= CLOSE_FRAME - 4
      and frame <= CLOSE_FRAME + 40
      and #publication_boundary_trace < 32
    local mismatch = "not-sampled"
    if should_sample and target_map_mismatch_summary ~= nil then
      mismatch = target_map_mismatch_summary(target)
    end
    if should_sample then
      publication_boundary_trace[#publication_boundary_trace + 1] =
        string.format("f%d:pc%04X:b%02X:target%04X:%s",
          frame, PUBLICATION_PC, emu:read8(0xFF99), target, mismatch)
    end
    trace_hardware_state("lcdc-publication")
  end, PUBLICATION_PC, PUBLICATION_SEGMENT)
end)

local function pulse(lo, hi, mask)
  return (frame >= lo and frame < hi) and mask or 0
end

local function bg_map(lcdc)
  return ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
end

pcall(function()
  for _, address in ipairs({0x432E, 0x4330, 0x434D, 0x4359}) do
    emu:setBreakpoint(function()
      if frame < OPEN_FRAME - 30 then return end
      local hl = read_register("HL") & 0xFFFF
      local destination = hl & 0xFC00
      local active = bg_map(emu:read8(0xFF40))
      local visible = destination == active
      if visible then semantic_visible_writes = semantic_visible_writes + 1 end
      if #semantic_write_trace < 512 then
        semantic_write_trace[#semantic_write_trace + 1] = string.format(
          "f%d:p%04X:h%04X:a%04X:s%d:l%02X:%s", frame, address,
          hl, active, emu:read8(0xFF41) & 0x03, emu:read8(0xFF44),
          visible and "VISIBLE" or "hidden")
      end
    end, address, 0x14)
  end
end)

local function window_map(lcdc)
  return ((lcdc & 0x40) ~= 0) and 0x9C00 or 0x9800
end

local function visible_map_signature()
  local lcdc = emu:read8(0xFF40)
  local scx = emu:read8(0xFF43)
  local scy = emu:read8(0xFF42)
  local base = bg_map(lcdc)
  local columns = math.floor(((scx & 7) + 159) / 8) + 1
  -- Hash the entire 160x144 presentation.  The old 112-line signature left
  -- the bottom 32 scanlines outside the phase key, which is exactly where an
  -- operator saw repeated Stage tiles after closing SELECT.
  local rows = math.floor(((scy & 7) + 143) / 8) + 1
  local parts = {string.format("%02X%02X", scx & 7, scy & 7)}
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for screen_row = 0, rows - 1 do
    local map_row = (math.floor(scy / 8) + screen_row) & 31
    for screen_col = 0, columns - 1 do
      local map_col = (math.floor(scx / 8) + screen_col) & 31
      local offset = base - 0x8000 + map_row * 32 + map_col
      parts[#parts + 1] = string.format(
        "%02X%02X", raw_vram:read8(offset), emu:read8(0x8000 + offset))
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(parts)
end

local function visible_oam_text()
  local entries = {}
  local sprite_height = (emu:read8(0xFF40) & 0x04) ~= 0 and 16 or 8
  for slot = 0, 39 do
    local address = 0xFE00 + slot * 4
    local y = emu:read8(address)
    local x = emu:read8(address + 1)
    if x > 0 and x < 168 and y > 0 and y < 160 + sprite_height then
      entries[#entries + 1] = string.format(
        "%d/%d/%d/%02X/%02X", slot, x, y,
        emu:read8(address + 2), emu:read8(address + 3))
    end
  end
  return table.concat(entries, ",")
end

local function capture_obj_contract()
  -- Preserve complete preloaded OBJ patterns, not only the animation tiles
  -- that happened to be referenced during the short raster baseline.
  local path = string.format("%s.obj-f%04d.bin", OUT, frame)
  local handle = assert(io.open(path, "wb"))
  handle:write(raw_vram:readRange(0, 0x1000))
  local old_index = emu:read8(0xFF6A)
  for index = 0, 63 do
    emu:write8(0xFF6A, index)
    handle:write(string.char(emu:read8(0xFF6B)))
  end
  emu:write8(0xFF6A, old_index)
  assert(emu:read8(0xFF6A) == old_index, "OBJ palette selector not restored")
  for index = 0, 159 do
    handle:write(string.char(emu:read8(0xFE00 + index)))
  end
  for _, address in ipairs({0xFF40, 0xFFBE, 0xFFBF, 0xFFC0, 0xFFD0, 0xFF70}) do
    handle:write(string.char(emu:read8(address)))
  end
  handle:close()
  obj_contract_trace[#obj_contract_trace + 1] = string.format("f%d:p%s", frame, path)
end

local function visible_bg_mismatches()
  local lcdc = emu:read8(0xFF40)
  local scx = emu:read8(0xFF43)
  local scy = emu:read8(0xFF42)
  local wy = emu:read8(0xFF4A)
  local window_visible = (lcdc & 0x20) ~= 0 and wy < 144
  local height = window_visible and wy or 144
  local columns = math.floor(((scx & 7) + 159) / 8) + 1
  local rows = math.floor(((scy & 7) + math.max(0, height - 1)) / 8) + 1
  local base = bg_map(lcdc)
  local tiles = {}
  for screen_row = 0, rows - 1 do
    local map_row = (math.floor(scy / 8) + screen_row) & 31
    for screen_col = 0, columns - 1 do
      local map_col = (math.floor(scx / 8) + screen_col) & 31
      local address = base + map_row * 32 + map_col
      tiles[#tiles + 1] = {
        address = address,
        row = map_row,
        col = map_col,
        tile = raw_vram:read8(address - 0x8000),
      }
    end
  end

  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  local mismatches = 0
  local examples = {}
  for _, cell in ipairs(tiles) do
    local actual = emu:read8(cell.address)
    local expected = string.byte(gameplay_lut, cell.tile + 1)
    if actual ~= expected then
      mismatches = mismatches + 1
      if #examples < 16 then
        examples[#examples + 1] = string.format(
          "%04X:r%d,c%d,t%02X,a%02X,e%02X",
          cell.address, cell.row, cell.col, cell.tile, actual, expected)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return mismatches, table.concat(examples, ";"), base, window_visible
end

target_map_mismatch_summary = function(base)
  local scx = emu:read8(0xFF43)
  local scy = emu:read8(0xFF42)
  local columns = math.floor(((scx & 7) + 159) / 8) + 1
  local rows = math.floor(((scy & 7) + 143) / 8) + 1
  local cells = {}
  for screen_row = 0, rows - 1 do
    local map_row = (math.floor(scy / 8) + screen_row) & 31
    for screen_col = 0, columns - 1 do
      local map_col = (math.floor(scx / 8) + screen_col) & 31
      local address = base + map_row * 32 + map_col
      cells[#cells + 1] = {
        address = address,
        tile = raw_vram:read8(address - 0x8000),
      }
    end
  end
  local mismatches = 0
  local examples = {}
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for _, cell in ipairs(cells) do
    local actual = emu:read8(cell.address)
    local expected = string.byte(gameplay_lut, cell.tile + 1)
    if actual ~= expected then
      mismatches = mismatches + 1
      if #examples < 4 then
        examples[#examples + 1] = string.format(
          "%04X:t%02X:a%02X:e%02X", cell.address, cell.tile,
          actual, expected)
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  return string.format("m%d[%s]", mismatches, table.concat(examples, ","))
end

local function state_text()
  local lcdc = emu:read8(0xFF40)
  return string.format(
    "f%d:scene%02X:room%02X:df5b%02X:ffe4%02X:lcdc%02X:bg%04X:win%04X:scx%02X:scy%02X",
    frame, emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xDF5B),
    emu:read8(0xFFE4),
    lcdc, bg_map(lcdc), window_map(lcdc), emu:read8(0xFF43),
    emu:read8(0xFF42))
end

local function bank1_art_mismatches()
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  local mismatches = 0
  local examples = {}
  for tile_index, tile in ipairs(art_tiles) do
    for byte_index = 0, 15 do
      local expected = string.byte(
        expected_art, (tile_index - 1) * 16 + byte_index + 1)
      -- Stage 1 uses signed BG tile addressing: logical tile $01 is pattern
      -- $9010, not $8010.  The natural loader's GDMA destinations are
      -- $9010/$9640/$9740 for the three immutable batches.
      local actual = emu:read8(0x9000 + tile * 16 + byte_index)
      if actual ~= expected then
        mismatches = mismatches + 1
        if #examples < 24 then
          examples[#examples + 1] = string.format("%04X:%02X/%02X",
            0x9000 + tile * 16 + byte_index, actual, expected)
        end
      end
    end
  end
  emu:write8(0xFF4F, old_vbk)
  settled_art_examples = #examples > 0 and table.concat(examples, ",") or "none"
  return mismatches
end

local function dump_plane(path, bank, base)
  local handle = assert(io.open(path, "wb"))
  if bank == 0 then
    for offset = 0, 0x3FF do
      handle:write(string.char(raw_vram:read8(base - 0x8000 + offset)))
    end
  else
    local old_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 1)
    for offset = 0, 0x3FF do
      handle:write(string.char(emu:read8(base + offset)))
    end
    emu:write8(0xFF4F, old_vbk)
  end
  handle:close()
end

local function finish()
  if finished then return end
  finished = true
  if os.getenv("STAGE1_NATURAL_EXPORT_STATE") == "1" then
    assert(emu:saveStateFile(OUT .. ".final.ss0") ~= false,
      "final machine-state export failed")
  end
  emu:screenshot(OUT .. ".final.png")
  dump_plane(OUT .. ".9800.tiles.bin", 0, 0x9800)
  dump_plane(OUT .. ".9800.attrs.bin", 1, 0x9800)
  dump_plane(OUT .. ".9c00.tiles.bin", 0, 0x9C00)
  dump_plane(OUT .. ".9c00.attrs.bin", 1, 0x9C00)
  local handle = assert(io.open(OUT, "w"))
  handle:write("rom=" .. ROM_PATH .. "\n")
  handle:write("rom_sha256=" .. ROM_SHA256 .. "\n")
  handle:write("lut_sha256=" .. LUT_SHA256 .. "\n")
  handle:write("art_sha256=" .. ART_SHA256 .. "\n")
  handle:write(string.format("expected_room=%02X\n", EXPECTED_ROOM))
  handle:write(string.format("frames=%d\n", frame))
  handle:write("no_menu_control=" .. (os.getenv("STAGE1_NATURAL_NO_MENU_CONTROL") == "1" and "1" or "0") .. "\n")
  handle:write(string.format("open_frame=%d\n", OPEN_FRAME))
  handle:write(string.format("close_frame=%d\n", CLOSE_FRAME))
  handle:write("menu_key=" .. MENU_KEY_NAME .. "\n")
  handle:write("close_key=" .. CLOSE_KEY_NAME .. "\n")
  handle:write(string.format(
    "raster_baseline_frames=%d\n", RASTER_BASELINE_FRAMES))
  handle:write(string.format("baseline_frames=%d\n", baseline_frames))
  handle:write(string.format("baseline_bad_frames=%d\n", baseline_bad_frames))
  handle:write(string.format("menu_frames=%d\n", menu_frames))
  handle:write(string.format("menu_bad_frames=%d\n", menu_bad_frames))
  handle:write(string.format("menu_mismatch_cells=%d\n", menu_mismatch_cells))
  handle:write(string.format("post_close_frames=%d\n", post_close_frames))
  handle:write(string.format(
    "post_close_bad_frames=%d\n", post_close_bad_frames))
  handle:write(string.format(
    "post_close_mismatch_cells=%d\n", post_close_mismatch_cells))
  handle:write(string.format("timer_isr_hits=%d\n", timer_isr_hits))
  handle:write(string.format(
    "timer_baseline_hits=%d\n", timer_baseline_hits))
  handle:write(string.format("timer_menu_hits=%d\n", timer_menu_hits))
  handle:write(string.format(
    "timer_post_close_hits=%d\n", timer_post_close_hits))
  handle:write(string.format(
    "timer_max_frame_gap=%d\n", timer_max_frame_gap))
  handle:write(string.format("timer_max_cycle_gap=%d\n", timer_max_cycle_gap))
  handle:write("timer_gap_trace=" .. table.concat(timer_gap_trace, ";") .. "\n")
  handle:write("last_preopen=" .. (last_preopen or "none") .. "\n")
  handle:write("first_window=" .. (first_window or "none") .. "\n")
  handle:write("first_closed=" .. (first_closed or "none") .. "\n")
  handle:write("first_menu_bad=" .. (first_menu_bad or "none") .. "\n")
  handle:write(
    "first_baseline_bad=" .. (first_baseline_bad or "none") .. "\n")
  handle:write(
    "first_post_close_bad=" .. (first_post_close_bad or "none") .. "\n")
  handle:write("final_state=" .. state_text() .. "\n")
  handle:write("first_gameplay=" .. (first_gameplay or "none") .. "\n")
  handle:write(string.format(
    "settled_art_mismatch_bytes=%d\n", settled_art_mismatch_bytes))
  handle:write(string.format("settled_df5b=%02X\n", settled_df5b))
  handle:write("settled_art_state=" .. (settled_art_state or "none") .. "\n")
  handle:write("settled_art_examples=" .. settled_art_examples .. "\n")
  handle:write("art_writer_trace=" .. table.concat(art_writer_trace, ";") .. "\n")
  handle:write("transitions=" .. table.concat(transitions, ";") .. "\n")
  handle:write(
    "menu_selector_trace=" .. table.concat(menu_selector_trace, ";") .. "\n")
  handle:write(
    "publication_latch_trace="
      .. table.concat(publication_latch_trace, ";") .. "\n")
  handle:write("publication_latch_fault=" .. publication_latch_fault .. "\n")
  handle:write(string.format(
    "semantic_visible_writes=%d\n", semantic_visible_writes))
  handle:write(
    "semantic_write_trace=" .. table.concat(semantic_write_trace, ";") .. "\n")
  handle:write(
    "hardware_register_trace=" .. table.concat(hardware_register_trace, ";") .. "\n")
  handle:write(
    "publication_boundary_trace="
      .. table.concat(publication_boundary_trace, ";") .. "\n")
  handle:write(
    "temporal_raster_trace=" .. table.concat(temporal_raster_trace, ";") .. "\n")
  handle:write("obj_contract_trace=" .. table.concat(obj_contract_trace, ";") .. "\n")
  handle:write(string.format(
    "first_selector_frame=%d\nfirst_selector_lcdc=%02X\nfirst_selector_dc0b=%02X\n",
    first_selector_frame, first_selector_lcdc, first_selector_dc0b))
  handle:close()
  if entity_trace then entity_trace:close(); entity_trace = nil end
  os.exit(0)
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  entity_trace_frame(frame)
  local keys = 0
  keys = keys | pulse(180, 186, KEY_DOWN)
  keys = keys | pulse(193, 199, KEY_A)
  keys = keys | pulse(241, 247, KEY_A)
  keys = keys | pulse(291, 297, KEY_A)
  keys = keys | pulse(341, 347, 0x08)
  keys = keys | pulse(391, 397, KEY_A)
  if os.getenv("STAGE1_NATURAL_NO_MENU_CONTROL") ~= "1" then
    keys = keys | pulse(OPEN_FRAME, OPEN_FRAME + 6, MENU_KEY)
    keys = keys | pulse(CLOSE_FRAME, CLOSE_FRAME + 6, CLOSE_KEY)
  end
  keys = keys | pulse(MOVE_START, MOVE_END, MOVE_KEY)
  emu:setKeys(keys)

  if emu:read8(0xFFC1) == 1 then
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xFF)
  end

  local lcdc = emu:read8(0xFF40)
  local signature = string.format(
    "%02X/%04X/%04X/%02X", lcdc, bg_map(lcdc), window_map(lcdc),
    emu:read8(0xFFE4))
  if signature ~= last_signature and #transitions < 128 then
    transitions[#transitions + 1] = state_text()
    last_signature = signature
  end

  local scene = emu:read8(0xD880)
  local room = emu:read8(0xFFBD)
  if not first_gameplay and scene == 0x02 and emu:read8(0xFFC1) == 1 then
    first_gameplay = state_text()
  end
  if scene == 0x02 and frame >= OPEN_FRAME - 120 then
    settled_art_mismatch_bytes = bank1_art_mismatches()
    settled_art_state = state_text()
    settled_df5b = emu:read8(0xDF5B)
  end
  local mismatches, examples, _, window_visible = visible_bg_mismatches()
  if frame >= OPEN_FRAME - 120 and frame < OPEN_FRAME then
    baseline_frames = baseline_frames + 1
    if mismatches ~= 0 then
      baseline_bad_frames = baseline_bad_frames + 1
      if not first_baseline_bad then
        first_baseline_bad = state_text() .. ":mismatches" .. mismatches .. ":" .. examples
        emu:screenshot(OUT .. ".first_baseline_bad.png")
      end
    end
    last_preopen = state_text()
  elseif window_visible and frame >= OPEN_FRAME and frame < CLOSE_FRAME then
    menu_frames = menu_frames + 1
    if not first_window then first_window = state_text() end
    if mismatches ~= 0 then
      menu_bad_frames = menu_bad_frames + 1
      menu_mismatch_cells = menu_mismatch_cells + mismatches
      if not first_menu_bad then
        first_menu_bad = state_text() .. ":mismatches" .. mismatches .. ":" .. examples
        emu:screenshot(OUT .. ".first_menu_bad.png")
      end
    end
  elseif frame >= CLOSE_FRAME and not window_visible then
    post_close_frames = post_close_frames + 1
    if not first_closed then first_closed = state_text() end
    if mismatches ~= 0 then
      post_close_bad_frames = post_close_bad_frames + 1
      post_close_mismatch_cells = post_close_mismatch_cells + mismatches
      if not first_post_close_bad then
        first_post_close_bad = state_text() .. ":mismatches" .. mismatches .. ":" .. examples
        emu:screenshot(OUT .. ".first_post_close_bad.png")
      end
    end
  end

  if frame == OPEN_FRAME - 1 then emu:screenshot(OUT .. ".preopen.png") end
  if frame == OPEN_FRAME - 1 or (frame >= CLOSE_FRAME + 2 and frame <= CLOSE_FRAME + 100) then
    capture_obj_contract()
  end
  if frame == CLOSE_FRAME + 30 then emu:screenshot(OUT .. ".postclose30.png") end
  local raster_capture =
    (frame >= OPEN_FRAME - RASTER_BASELINE_FRAMES and frame < OPEN_FRAME)
    or (frame >= OPEN_FRAME - 4 and frame <= OPEN_FRAME + 40)
    or (frame >= CLOSE_FRAME - 4 and frame <= CLOSE_FRAME + 100)
  if raster_capture then
    local raster_path = string.format("%s.raster-f%04d.png", OUT, frame)
    emu:screenshot(raster_path)
    temporal_raster_trace[#temporal_raster_trace + 1] = string.format(
      "f%d:h%d:s%s:o%s:p%s", frame,
      (emu:read8(0xFF40) & 0x04) ~= 0 and 16 or 8,
      visible_map_signature(), visible_oam_text(), raster_path)
  end

  if frame >= LIMIT then
    -- The exact reported route is live Stage 1 room $05. Keep those facts in
    -- the report rather than mutating the machine to manufacture coverage.
    if scene ~= 0x02 or room ~= EXPECTED_ROOM then
      transitions[#transitions + 1] = "unexpected-final:" .. state_text()
    end
    finish()
  end
end)
