-- Verify every completed Stage 1 atomic tilemap copy byte-for-byte.
--
-- The game builds a packed 24x24 room map at C1A0-C3DF.  The DX copier
-- expands that into a 32-byte-stride VRAM tilemap.  Palette-only checks can
-- pass even when a bad tile ID creates a wall, so this probe compares the
-- actual tile IDs at the exact completion point of the atomic copy.
--
-- Environment:
--   STAGE1_TILEMAP_OUT     report path
--   STAGE1_TILEMAP_FRAMES  frames to exercise after loading (default 900)
--   STAGE1_TILEMAP_SETUP   candidate's 2..15-byte DA13 setup for savestates
--   STAGE1_TILEMAP_FORCE_PURE  make Stage 1 use the stock-width tile path
--   STAGE1_TILEMAP_TRACE_HASH  optional eight-digit packed-source hash
--   STAGE1_TILEMAP_PURE_COMPLETION  candidate's pure-copy RET address
--   STAGE1_TILEMAP_ATOMIC_WRAP  candidate's fixed atomic exit address
--   STAGE1_TILEMAP_CANONICAL_LUT  reviewed immutable 256-byte Stage-1 LUT
--   STAGE1_TILEMAP_CANONICAL_LUT_SHA256  reviewed LUT digest
--   STAGE1_TILEMAP_ROM_SHA256  exact candidate digest
--   STAGE1_TILEMAP_COPIER_SHA256  reviewed fixed-bank copier digest
--   STAGE1_TILEMAP_ORACLE_SCHEMA  expected-plane contract identifier

local OUT = assert(os.getenv("STAGE1_TILEMAP_OUT"))
local DONE = assert(os.getenv("STAGE1_TILEMAP_DONE"))
local LIMIT = tonumber(os.getenv("STAGE1_TILEMAP_FRAMES") or "900")
local WARM_RESET = os.getenv("STAGE1_TILEMAP_WARM_RESET") == "1"
local SETUP_PATH = os.getenv("STAGE1_TILEMAP_SETUP") or ""
local FORCE_PURE = os.getenv("STAGE1_TILEMAP_FORCE_PURE") == "1"
local TRACE_HASH_TEXT = os.getenv("STAGE1_TILEMAP_TRACE_HASH") or ""
local TRACE_HASH = TRACE_HASH_TEXT ~= "" and tonumber(TRACE_HASH_TEXT, 16) or nil
local CANONICAL_LUT_PATH = assert(
  os.getenv("STAGE1_TILEMAP_CANONICAL_LUT"))
local CANONICAL_LUT_SHA256 = assert(
  os.getenv("STAGE1_TILEMAP_CANONICAL_LUT_SHA256"))
local ROM_SHA256 = assert(os.getenv("STAGE1_TILEMAP_ROM_SHA256"))
local COPIER_SHA256 = assert(os.getenv("STAGE1_TILEMAP_COPIER_SHA256"))
local ORACLE_SCHEMA = assert(os.getenv("STAGE1_TILEMAP_ORACLE_SCHEMA"))
local PURE_COMPLETION = tonumber(
  assert(os.getenv("STAGE1_TILEMAP_PURE_COMPLETION")), 16)
local KEY_A = 0x01
local KEY_RIGHT, KEY_LEFT, KEY_UP, KEY_DOWN = 0x10, 0x20, 0x40, 0x80
local ATOMIC_WRAP = tonumber(assert(os.getenv("STAGE1_TILEMAP_ATOMIC_WRAP")), 16)
local ATOMIC_WRAP_MODE = os.getenv("STAGE1_TILEMAP_ATOMIC_WRAP_MODE") or
  "stock-order"
local ATOMIC_WRAP_SEGMENT = tonumber(
  assert(os.getenv("STAGE1_TILEMAP_ATOMIC_WRAP_SEGMENT")))
local ATOMIC_ROW = tonumber(
  assert(os.getenv("STAGE1_TILEMAP_ATOMIC_ROW")), 16)
local ATOMIC_FIRST_TILE_WRITE = tonumber(
  assert(os.getenv("STAGE1_TILEMAP_ATOMIC_FIRST_WRITE")), 16)
local R417_PRECOMPUTED = os.getenv("STAGE1_TILEMAP_R417_PRECOMPUTED") == "1"
local TILE_ROW = tonumber(
  assert(os.getenv("STAGE1_TILEMAP_TILE_ROW")), 16)
local wrap_opcode = emu:read8(ATOMIC_WRAP)
local STOCK_ORDER_WRAP = wrap_opcode ~= 0xB7

local frame, play_frame = 0, 0
local phase, stable_gameplay = "bootstrap", 0
local did_reset = false
local did_setup = false
local did_force_pure = false
local copy_entries, atomic_completions, pure_completions = 0, 0, 0
local wrap_hits, exact_copies = 0, 0
local unmatched_wrap_hits, wrong_destination_wrap_hits = 0, 0
local mismatch_copies, mismatch_cells = 0, 0
local attribute_mismatch_copies, attribute_mismatch_cells = 0, 0
local attribute_checked_copies, attribute_unreadable_copies = 0, 0
local deferred_attribute_checks, deferred_attribute_pending = {}, 0
local entry_mismatch_copies, entry_mismatch_cells = 0, 0
local source_changed_copies, source_changed_cells = 0, 0
local publication_model_copies, publication_model_cells = 0, 0
local ordinary_attribute_model_copies, ordinary_attribute_model_cells = 0, 0
local first_mismatch = nil
local first_attribute_mismatch = nil
local pending_source, pending_attributes, pending_base = nil, nil, nil
local pending_room, pending_ffe5 = nil, nil
local pending_wraps, selected_base = 0, nil
local pending_first_atomic_write = false
local trace_target_copy = false
local destinations = {}
local entry_h_values, wrap_a_values, wrap_h_values = {}, {}, {}
local completion_stat_values = {}
local atomic_start_vbk_values = {}
local atomic_start_h_values, atomic_start_l_values = {}, {}
local atomic_write_h_values, atomic_write_l_values = {}, {}
local source_events = {}
local target_row_events = {}
local tile_row_events = {}
local invalid_tile_row_events = 0
local raw_vram = assert(emu.memory.vram)
local finished = false

local setup_bytes = nil
if SETUP_PATH ~= "" then
  local handle = assert(io.open(SETUP_PATH, "rb"))
  local data = assert(handle:read("*a"))
  handle:close()
  assert(
    #data >= 2 and #data <= 15,
    "Stage 1 setup must be 2..15 bytes")
  setup_bytes = {string.byte(data, 1, #data)}
end

local canonical_lut_file = assert(io.open(CANONICAL_LUT_PATH, "rb"))
local canonical_lut = assert(canonical_lut_file:read("*a"))
canonical_lut_file:close()
assert(#canonical_lut == 0x100,
  "Stage-1 canonical attribute LUT must be exactly 256 bytes")

local function read_register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and value ~= nil then
    return (#name == 1) and (value & 0xFF) or value
  end
  ok, value = pcall(function() return emu:getRegister(name) end)
  if ok and value ~= nil then
    return (#name == 1) and (value & 0xFF) or value
  end
  return -1
end

local function packed_source()
  local bytes = {}
  for offset = 0, 575 do
    bytes[offset + 1] = emu:read8(0xC1A0 + offset)
  end
  return bytes
end

-- This is the independent ordinary-plane owner used by the resident compiler.
-- Never consult mutable C600 here: a corrupt live LUT copied faithfully to
-- VRAM must fail instead of grading itself. Room $01's four metallic wall
-- tiles are the one reviewed semantic override.  The approved compiled-tooth
-- LUT stores the CGB VRAM-bank bit in twelve entries, so this compares the
-- complete reviewed attribute byte—not only its palette low bits.
local function independent_expected_palette(tile, room, ffe5)
  local effective_room = ffe5 ~= 0 and ffe5 or room
  if effective_room == 0x01
      and (tile == 0x24 or tile == 0x27
        or tile == 0x30 or tile == 0x33) then
    return 0x06
  end
  return string.byte(canonical_lut, tile + 1)
end

local function expected_attribute_plane(source, room, ffe5)
  local expected = {}
  for offset, tile in ipairs(source) do
    expected[offset] = independent_expected_palette(tile, room, ffe5)
  end
  return expected
end

local function source_hash(bytes)
  local hash = 0x811C9DC5
  for _, value in ipairs(bytes) do
    hash = ((hash ~ value) * 0x01000193) & 0xFFFFFFFF
  end
  return hash
end

local function dump_bytes(path, bytes)
  local handle = assert(io.open(path, "wb"))
  for _, value in ipairs(bytes) do handle:write(string.char(value)) end
  handle:close()
end

local function dump_map(path, base)
  local handle = assert(io.open(path, "wb"))
  for offset = 0, 1023 do
    handle:write(string.char(raw_vram:read8(base - 0x8000 + offset)))
  end
  handle:close()
end

local function compare_completed_copy(
    base, expected, expected_attributes, compare_attributes)
  -- The entry snapshot owns this publication. Completion-time C1A0 is read
  -- only to reject in-flight source drift; it can never become the oracle.
  local completion_source = packed_source()
  local local_mismatches, local_entry_mismatches = 0, 0
  local local_source_changes = 0
  local local_attribute_mismatches = 0
  local attributes_readable = compare_attributes
      and (emu:read8(0xFF41) & 3) ~= 3
  local old_vbk = emu:read8(0xFF4F)
  if attributes_readable then emu:write8(0xFF4F, 1) end
  for row = 0, 23 do
    for col = 0, 23 do
      local source_offset = row * 24 + col
      local address = base + row * 32 + col
      local wanted = expected[source_offset + 1]
      local completion_tile = completion_source[source_offset + 1]
      local actual = raw_vram:read8(address - 0x8000)
      local actual_attr = attributes_readable and emu:read8(address) or 0
      local wanted_attr = expected_attributes[source_offset + 1]
      if completion_tile ~= wanted then
        local_source_changes = local_source_changes + 1
      end
      if actual ~= wanted then
        local_entry_mismatches = local_entry_mismatches + 1
      end
      if actual ~= wanted then
        local_mismatches = local_mismatches + 1
        if not first_mismatch then
          first_mismatch = {
            frame = frame,
            copy = atomic_completions,
            base = base,
            row = row,
            col = col,
            address = address,
            expected = wanted,
            completion_source = completion_tile,
            actual = actual,
            scene = emu:read8(0xD880),
            room = emu:read8(0xFFBD),
            scx = emu:read8(0xFF43),
            scy = emu:read8(0xFF42),
            stat = emu:read8(0xFF41) & 3,
            vbk = emu:read8(0xFF4F) & 1,
          }
          dump_bytes(OUT .. ".first.completion-source.bin", completion_source)
          dump_bytes(OUT .. ".first.publication-source.bin", expected)
          dump_map(OUT .. ".first.map.bin", base)
          emu:screenshot(OUT .. ".first.png")
        end
      end
      if attributes_readable and actual_attr ~= wanted_attr then
        local_attribute_mismatches = local_attribute_mismatches + 1
        if not first_attribute_mismatch then
          first_attribute_mismatch = {
            frame = frame,
            copy = atomic_completions,
            base = base,
            row = row,
            col = col,
            address = address,
            tile = wanted,
            expected = wanted_attr,
            actual = actual_attr,
            scene = emu:read8(0xD880),
            room = emu:read8(0xFFBD),
          }
        end
      end
    end
  end
  publication_model_copies = publication_model_copies + 1
  publication_model_cells = publication_model_cells + 576
  source_changed_cells = source_changed_cells + local_source_changes
  if local_source_changes > 0 then
    source_changed_copies = source_changed_copies + 1
  end
  mismatch_cells = mismatch_cells + local_mismatches
  if attributes_readable then
    emu:write8(0xFF4F, old_vbk)
    attribute_checked_copies = attribute_checked_copies + 1
    ordinary_attribute_model_copies = ordinary_attribute_model_copies + 1
    ordinary_attribute_model_cells = ordinary_attribute_model_cells + 576
  elseif compare_attributes then
    -- Preserve the immutable entry-owned expectation, then read it on the
    -- first later PPU-safe frame.  Never read bank-1 VRAM during mode 3.
    deferred_attribute_checks[#deferred_attribute_checks + 1] = {
      base = base, expected_attributes = expected_attributes,
      expected = expected, copy = atomic_completions,
      room = emu:read8(0xFFBD),
    }
    deferred_attribute_pending = deferred_attribute_pending + 1
  end
  attribute_mismatch_cells =
      attribute_mismatch_cells + local_attribute_mismatches
  entry_mismatch_cells = entry_mismatch_cells + local_entry_mismatches
  if local_entry_mismatches > 0 then
    entry_mismatch_copies = entry_mismatch_copies + 1
  end
  if local_mismatches == 0 then
    exact_copies = exact_copies + 1
  else
    mismatch_copies = mismatch_copies + 1
  end
  if local_attribute_mismatches > 0 then
    attribute_mismatch_copies = attribute_mismatch_copies + 1
  end
end

local function flush_deferred_attribute_checks()
  if #deferred_attribute_checks == 0 then return end
  if (emu:read8(0xFF41) & 3) == 3 then return end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  for _, check in ipairs(deferred_attribute_checks) do
    local local_mismatches = 0
    for row = 0, 23 do
      for col = 0, 23 do
        local source_offset = row * 24 + col
        local address = check.base + row * 32 + col
        local wanted_attr = check.expected_attributes[source_offset + 1]
        local actual_attr = emu:read8(address)
        if actual_attr ~= wanted_attr then
          local_mismatches = local_mismatches + 1
          if not first_attribute_mismatch then
            first_attribute_mismatch = {
              frame = frame, copy = check.copy, base = check.base,
              row = row, col = col, address = address,
              tile = check.expected[source_offset + 1],
              expected = wanted_attr, actual = actual_attr,
              scene = emu:read8(0xD880), room = check.room,
            }
          end
        end
      end
    end
    attribute_checked_copies = attribute_checked_copies + 1
    ordinary_attribute_model_copies = ordinary_attribute_model_copies + 1
    ordinary_attribute_model_cells = ordinary_attribute_model_cells + 576
    attribute_mismatch_cells = attribute_mismatch_cells + local_mismatches
    if local_mismatches > 0 then
      attribute_mismatch_copies = attribute_mismatch_copies + 1
    end
    deferred_attribute_pending = deferred_attribute_pending - 1
  end
  emu:write8(0xFF4F, old_vbk)
  deferred_attribute_checks = {}
end

local function write_report()
  if finished then return end
  finished = true
  local handle = assert(io.open(OUT, "w"))
  handle:write("oracle_schema=" .. ORACLE_SCHEMA .. "\n")
  handle:write("rom_sha256=" .. ROM_SHA256 .. "\n")
  handle:write("copier_sha256=" .. COPIER_SHA256 .. "\n")
  handle:write("canonical_lut_sha256=" .. CANONICAL_LUT_SHA256 .. "\n")
  handle:write("ordinary_attribute_scope=dirty-pre-semantic-overlay\n")
  handle:write(
    "semantic_overlay_owner=stage1-hazard-and-low-health-publication-gates\n")
  handle:write(string.format("frames=%d\n", play_frame))
  handle:write(string.format("total_frames=%d\n", frame))
  handle:write(string.format("final_scene=%02X\n", emu:read8(0xD880)))
  handle:write(string.format("final_active=%02X\n", emu:read8(0xFFC1)))
  handle:write(string.format("final_stage_index=%02X\n", emu:read8(0xFFBA)))
  handle:write(string.format("warm_reset=%d\n", did_reset and 1 or 0))
  handle:write(string.format("runtime_setup=%d\n", did_setup and 1 or 0))
  handle:write(string.format("force_pure=%d\n", did_force_pure and 1 or 0))
  handle:write(string.format("copy_entries=%d\n", copy_entries))
  handle:write(string.format("atomic_completions=%d\n", atomic_completions))
  handle:write(string.format("pure_completions=%d\n", pure_completions))
  handle:write(string.format("wrap_hits=%d\n", wrap_hits))
  handle:write(string.format("unmatched_wrap_hits=%d\n", unmatched_wrap_hits))
  handle:write(string.format(
    "wrong_destination_wrap_hits=%d\n", wrong_destination_wrap_hits))
  handle:write(string.format("exact_copies=%d\n", exact_copies))
  handle:write(string.format("mismatch_copies=%d\n", mismatch_copies))
  handle:write(string.format("mismatch_cells=%d\n", mismatch_cells))
  handle:write(string.format(
    "attribute_mismatch_copies=%d\n", attribute_mismatch_copies))
  handle:write(string.format(
    "attribute_mismatch_cells=%d\n", attribute_mismatch_cells))
  handle:write(string.format(
    "attribute_checked_copies=%d\n", attribute_checked_copies))
  handle:write(string.format(
    "attribute_unreadable_copies=%d\n", attribute_unreadable_copies))
  handle:write(string.format(
    "deferred_attribute_pending=%d\n", deferred_attribute_pending))
  handle:write(string.format(
    "entry_mismatch_copies=%d\n", entry_mismatch_copies))
  handle:write(string.format(
    "entry_mismatch_cells=%d\n", entry_mismatch_cells))
  handle:write(string.format(
    "source_changed_copies=%d\n", source_changed_copies))
  handle:write(string.format("source_changed_cells=%d\n", source_changed_cells))
  handle:write(string.format(
    "publication_model_copies=%d\n", publication_model_copies))
  handle:write(string.format(
    "publication_model_cells=%d\n", publication_model_cells))
  handle:write(string.format(
    "ordinary_attribute_model_copies=%d\n",
    ordinary_attribute_model_copies))
  handle:write(string.format(
    "ordinary_attribute_model_cells=%d\n",
    ordinary_attribute_model_cells))
  local destination_parts = {}
  for base in pairs(destinations) do
    destination_parts[#destination_parts + 1] = string.format("%04X", base)
  end
  table.sort(destination_parts)
  handle:write("destinations=" .. table.concat(destination_parts, ",") .. "\n")
  local function histogram_text(histogram)
    local keys, parts = {}, {}
    for value in pairs(histogram) do keys[#keys + 1] = value end
    table.sort(keys)
    for _, value in ipairs(keys) do
      parts[#parts + 1] = string.format("%d:%d", value, histogram[value])
    end
    return table.concat(parts, ",")
  end
  handle:write("entry_h_values=" .. histogram_text(entry_h_values) .. "\n")
  handle:write("wrap_a_values=" .. histogram_text(wrap_a_values) .. "\n")
  handle:write("wrap_h_values=" .. histogram_text(wrap_h_values) .. "\n")
  handle:write(
    "completion_stat_values=" .. histogram_text(completion_stat_values) .. "\n")
  handle:write(
    "atomic_start_vbk_values=" .. histogram_text(atomic_start_vbk_values) .. "\n")
  handle:write(
    "atomic_start_h_values=" .. histogram_text(atomic_start_h_values) .. "\n")
  handle:write(
    "atomic_start_l_values=" .. histogram_text(atomic_start_l_values) .. "\n")
  handle:write(
    "atomic_write_h_values=" .. histogram_text(atomic_write_h_values) .. "\n")
  handle:write(
    "atomic_write_l_values=" .. histogram_text(atomic_write_l_values) .. "\n")
  for _, event in ipairs(source_events) do
    handle:write(string.format(
      "source_event=%d|%d|%04X|%02X|%02X|%02X|%02X|%02X|%02X|%02X|%08X\n",
      event.frame, event.copy, event.base, event.room, event.scx, event.scy,
      event.dc00, event.dc01, event.dcb8, event.ffcf, event.hash))
  end
  for _, event in ipairs(target_row_events) do
    handle:write(string.format(
      "target_row_event=%d|%d|%02X|%02X|%d\n",
      event.frame, event.b, event.h, event.l, event.previous_mismatches))
  end
  handle:write(string.format(
    "invalid_tile_row_events=%d\n", invalid_tile_row_events))
  for _, event in ipairs(tile_row_events) do
    handle:write(string.format(
      "tile_row_event=%d|%d|%04X|%04X|%04X|%04X|%02X|%02X|%02X|%02X\n",
      event.frame, event.copy, event.de, event.hl,
      event.expected_de, event.expected_hl, event.b,
      event.scx, event.dc02, event.raw49))
  end
  if first_mismatch then
    handle:write(string.format(
      "first_mismatch=frame:%d copy:%d base:%04X row:%d col:%d " ..
      "address:%04X expected:%02X completion_source:%02X actual:%02X " ..
      "scene:%02X room:%02X stat:%d vbk:%d " ..
      "scx:%02X scy:%02X\n",
      first_mismatch.frame, first_mismatch.copy, first_mismatch.base,
      first_mismatch.row, first_mismatch.col, first_mismatch.address,
      first_mismatch.expected, first_mismatch.completion_source,
      first_mismatch.actual,
      first_mismatch.scene, first_mismatch.room,
      first_mismatch.stat, first_mismatch.vbk,
      first_mismatch.scx, first_mismatch.scy))
  else
    handle:write("first_mismatch=none\n")
  end
  if first_attribute_mismatch then
    handle:write(string.format(
      "first_attribute_mismatch=frame:%d copy:%d base:%04X row:%d col:%d " ..
      "address:%04X tile:%02X expected:%02X actual:%02X scene:%02X room:%02X\n",
      first_attribute_mismatch.frame, first_attribute_mismatch.copy,
      first_attribute_mismatch.base, first_attribute_mismatch.row,
      first_attribute_mismatch.col, first_attribute_mismatch.address,
      first_attribute_mismatch.tile, first_attribute_mismatch.expected,
      first_attribute_mismatch.actual, first_attribute_mismatch.scene,
      first_attribute_mismatch.room))
  else
    handle:write("first_attribute_mismatch=none\n")
  end
  handle:close()
  local done = assert(io.open(DONE, "w"))
  done:write("complete\n")
  done:close()
  emu:stop()
end

pcall(function()
  emu:setBreakpoint(function()
    if emu:read8(0xFF99) == 1 then selected_base = 0x9C00 end
  end, 0x42A0, 1)
  emu:setBreakpoint(function()
    if emu:read8(0xFF99) == 1 then selected_base = 0x9800 end
  end, 0x42A5, 1)
  emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFF99) ~= 1 then return end
    local h = read_register("H")
    entry_h_values[h] = (entry_h_values[h] or 0) + 1
    if h ~= 0x98 and h ~= 0x9C then return end
    if setup_bytes ~= nil and not did_setup then
      -- -t restores WRAM after Lua is initialized and can do so after the
      -- first frame callback. Install the candidate helper at the natural
      -- Stage 1 copy entry, before this routine can CALL DA13.
      for offset, value in ipairs(setup_bytes) do
        emu:write8(0xDA12 + offset, value)
      end
      did_setup = true
    end
    if FORCE_PURE and not did_force_pure then
      -- The fixed readiness helper jumps to DAD5 for Stage 1 decisions.
      -- XOR A / RET forces its stock-width tile-only branch without changing
      -- the candidate ROM or the surrounding copy implementation.
      emu:write8(0xDAD5, 0xAF)
      emu:write8(0xDAD6, 0xC9)
      did_force_pure = true
    end
    copy_entries = copy_entries + 1
    if h == 0x98 or h == 0x9C then
      pending_base = h * 0x100
      pending_source = packed_source()
      pending_room = emu:read8(0xFFBD)
      pending_ffe5 = emu:read8(0xFFE5)
      pending_attributes = expected_attribute_plane(
        pending_source, pending_room, pending_ffe5)
    end
    local pending_hash = source_hash(pending_source)
    trace_target_copy = TRACE_HASH ~= nil and pending_hash == TRACE_HASH
    if #source_events < 2048 then
      source_events[#source_events + 1] = {
        frame = frame,
        copy = copy_entries,
        base = pending_base,
        room = emu:read8(0xFFBD),
        scx = emu:read8(0xFF43),
        scy = emu:read8(0xFF42),
        dc00 = emu:read8(0xDC00),
        dc01 = emu:read8(0xDC01),
        dcb8 = emu:read8(0xDCB8),
        ffcf = emu:read8(0xFFCF),
        hash = pending_hash,
      }
    end
    pending_wraps = 0
  end, 0x42A7, 1)

  emu:setBreakpoint(function()
    if pending_source == nil or emu:read8(0xD880) ~= 0x02
        or emu:read8(0xFF99) ~= 1 then return end
    local de = read_register("DE")
    local hl = read_register("HL")
    local row = ((hl - pending_base) >> 5) & 0xFF
    local expected_de = 0xC1A0 + row * 24
    local expected_hl = pending_base + row * 32
    if de ~= expected_de or hl ~= expected_hl or row >= 24 then
      invalid_tile_row_events = invalid_tile_row_events + 1
    end
    if #tile_row_events < 512 then
      tile_row_events[#tile_row_events + 1] = {
        frame=frame, copy=copy_entries, de=de, hl=hl,
        expected_de=expected_de, expected_hl=expected_hl,
        b=read_register("B"), scx=emu:read8(0xFF43),
        dc02=emu:read8(0xDC02), raw49=emu:read8(0xC1D1),
      }
    end
  end, TILE_ROW, 1)

  emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFF99) ~= 1 then return end
    local b = read_register("B")
    local vbk = emu:read8(0xFF4F) & 1
    local h, l = read_register("H"), read_register("L")
    if trace_target_copy then
      local previous_mismatches = 0
      if b < 0x18 and pending_base ~= nil then
        local row = 0x17 - b
        for col = 0, 23 do
          local actual = raw_vram:read8(
            pending_base - 0x8000 + row * 32 + col)
          if actual ~= pending_source[row * 24 + col + 1] then
            previous_mismatches = previous_mismatches + 1
          end
        end
      end
      target_row_events[#target_row_events + 1] = {
        frame = frame, b = b, h = h, l = l,
        previous_mismatches = previous_mismatches,
      }
    end
    if l ~= 0 or (h ~= 0x98 and h ~= 0x9C) then return end
    atomic_start_vbk_values[vbk] = (atomic_start_vbk_values[vbk] or 0) + 1
    atomic_start_h_values[h] = (atomic_start_h_values[h] or 0) + 1
    atomic_start_l_values[l] = (atomic_start_l_values[l] or 0) + 1
    pending_first_atomic_write = true
  end, ATOMIC_ROW, 1)

  emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFF99) ~= 1 then return end
    if not pending_first_atomic_write then return end
    pending_first_atomic_write = false
    local h, l = read_register("H"), read_register("L")
    atomic_write_h_values[h] = (atomic_write_h_values[h] or 0) + 1
    atomic_write_l_values[l] = (atomic_write_l_values[l] or 0) + 1
  end, ATOMIC_FIRST_TILE_WRITE, 1)

  emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFF99) ~= 1 then return end
    local a, h = read_register("A"), read_register("H")
    -- The r417 precomputed layout visits this wrapper during partial rows.
    -- Its byte-pinned completed tails have H=$9B/$9F only.
    if R417_PRECOMPUTED and (h & 0x03) ~= 0x03 then return end
    wrap_hits = wrap_hits + 1
    wrap_a_values[a] = (wrap_a_values[a] or 0) + 1
    wrap_h_values[h] = (wrap_h_values[h] or 0) + 1
    local base
    if ATOMIC_WRAP_MODE == "direct-map" then
      -- The postcomputed compiler borrows H while staging the attribute plane,
      -- but its odd FF01 tag still names the exact physical DMA destination.
      -- Decode only the reviewed $99/$9D tags; aliases fail closed below.
      local tag = emu:read8(0xFF01)
      if tag == 0x99 then base = 0x9800
      elseif tag == 0x9D then base = 0x9C00
      else base = 0 end
    elseif STOCK_ORDER_WRAP then
      -- Stock-order candidate: one final visit with H=base+$03. The row-end
      -- discriminator may legitimately leave A=$00, $E0, or another value;
      -- the unique EI/RET completion itself proves that all rows finished.
      base = (h - 3) * 0x100
    else
      -- Rotated RC5: A=$00 is the row-23 wrap; A=$80/H=base is the
      -- second visit, after replaying rows 0..3.
      if a ~= 0x80 then return end
      base = h * 0x100
    end
    if base ~= 0x9800 and base ~= 0x9C00 then
      wrong_destination_wrap_hits = wrong_destination_wrap_hits + 1
      return
    end
    if pending_source == nil then
      unmatched_wrap_hits = unmatched_wrap_hits + 1
      return
    end
    if pending_base ~= base then
      wrong_destination_wrap_hits = wrong_destination_wrap_hits + 1
      return
    end
    destinations[base] = true
    atomic_completions = atomic_completions + 1
    completion_stat_values[emu:read8(0xFF41) & 3] =
      (completion_stat_values[emu:read8(0xFF41) & 3] or 0) + 1
    compare_completed_copy(base, pending_source, pending_attributes, true)
    if trace_target_copy then
      dump_bytes(OUT .. ".trace.source.bin", pending_source)
      dump_map(OUT .. ".trace.map.bin", base)
      emu:screenshot(OUT .. ".trace.png")
    end
    pending_source, pending_attributes, pending_base = nil, nil, nil
    pending_room, pending_ffe5 = nil, nil
    pending_wraps = 0
    trace_target_copy = false
  end, ATOMIC_WRAP, ATOMIC_WRAP_SEGMENT)

  -- Stock-width/pure path completion, immediately before its RET. H is three
  -- pages past the base here, so retain the entry-time destination instead.
  emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFF99) ~= 1
        or pending_source == nil then return end
    if pending_base ~= 0x9800 and pending_base ~= 0x9C00 then return end
    destinations[pending_base] = true
    pure_completions = pure_completions + 1
    completion_stat_values[emu:read8(0xFF41) & 3] =
      (completion_stat_values[emu:read8(0xFF41) & 3] or 0) + 1
    compare_completed_copy(
      pending_base, pending_source, pending_attributes, false)
    if trace_target_copy then
      dump_bytes(OUT .. ".trace.source.bin", pending_source)
      dump_map(OUT .. ".trace.map.bin", pending_base)
      emu:screenshot(OUT .. ".trace.png")
    end
    pending_source, pending_attributes, pending_base = nil, nil, nil
    pending_room, pending_ffe5 = nil, nil
    pending_wraps = 0
    trace_target_copy = false
  end, PURE_COMPLETION, 1)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  flush_deferred_attribute_checks()

  if WARM_RESET and not did_reset and frame == 20 then
    did_reset = true
    emu:reset()
    frame = 0
    phase, stable_gameplay = "bootstrap", 0
    return
  end

  if phase == "bootstrap" then
    if emu:read8(0xD880) == 0x02 and emu:read8(0xFFC1) == 1 then
      phase = "play"
    elseif frame >= 20 then
      phase = "autostart"
    end
  end

  if phase == "autostart" then
    -- Native title-menu route: Intro is the first option, so move down to
    -- Game Start. This sequence is shared with the established gameplay CRAM
    -- probes and avoids the FFBA level-select shortcut.
    if frame >= 180 and frame <= 185 then emu:setKeys(KEY_DOWN)
    elseif frame >= 193 and frame <= 198 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if emu:read8(0xDCFD) == 1
        and emu:read8(0xD880) == 0x02
        and emu:read8(0xFFC1) == 1 then
      stable_gameplay = stable_gameplay + 1
      if stable_gameplay >= 120 then phase = "play" end
    else
      stable_gameplay = 0
    end
    if frame > 3000 then write_report() end
    return
  end

  play_frame = play_frame + 1
  -- Preserve normal room logic but keep this diagnostic route alive.
  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xFF)
  local leg = math.floor((play_frame % 480) / 120)
  local movement
  if leg == 0 then movement = KEY_RIGHT
  elseif leg == 1 then movement = KEY_DOWN
  elseif leg == 2 then movement = KEY_LEFT
  else movement = KEY_UP end
  if (play_frame % 90) < 12 then movement = movement | KEY_A end
  emu:setKeys(movement)
  if play_frame >= LIMIT then write_report() end
end)
