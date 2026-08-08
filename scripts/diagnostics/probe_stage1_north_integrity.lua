-- Cold-start GAME START, hold north, and capture the first completed room.
--
-- This is deliberately route-driven: it never writes gameplay WRAM, SRAM,
-- scene IDs, room IDs, HP, or scroll state.  The only game input after the
-- title/stage confirmations is UP.  The resulting C1A0 packed room buffer and
-- both physical BG maps are compared with the untouched Japanese ROM by the
-- Python verifier.

local OUT = assert(os.getenv("STAGE1_NORTH_OUT"))
local LIMIT = tonumber(os.getenv("STAGE1_NORTH_FRAMES") or "3000")
local PLAY_LIMIT = tonumber(os.getenv("STAGE1_NORTH_PLAY_FRAMES") or "1800")
local TARGET_CAMERA_TEXT = os.getenv("STAGE1_NORTH_TARGET_CAMERA")
local TARGET_CAMERA = TARGET_CAMERA_TEXT and tonumber(TARGET_CAMERA_TEXT) or nil
local TARGET_ROOM = tonumber(os.getenv("STAGE1_NORTH_TARGET_ROOM") or "1")
local TARGET_SETTLE = tonumber(os.getenv("STAGE1_NORTH_TARGET_SETTLE") or "8")
local SNAP_INTERVAL = tonumber(os.getenv("STAGE1_NORTH_SNAP_INTERVAL") or "0")
local FIRE = os.getenv("STAGE1_NORTH_FIRE") == "1"
local TRACE_FILE = os.getenv("STAGE1_NORTH_TRACE_FILE")
local TRACE_WRITES = os.getenv("STAGE1_NORTH_TRACE_WRITES") == "1"
local TRACE_OPENING_STATE = os.getenv("STAGE1_NORTH_TRACE_OPENING_STATE") == "1"
local VIA_OPENING = os.getenv("STAGE1_NORTH_VIA_OPENING") == "1"

local KEY_A = 0x01
local KEY_START = 0x08
local KEY_UP = 0x40
local KEY_DOWN = 0x80

local frame = 0
local gameplay_frame = 0
local first_gameplay = -1
local initial_room = -1
local room_changes = 0
local previous_room = -1
local window_frames = 0
local finished = false
local target_settle_frame = nil
local transitions = {}
local cfaa_transitions = {}
local snapshots = {}
local last_state = ""
local previous_cfaa = -1
local raw_vram = assert(emu.memory.vram)
local trace_keys = {}
local trace_key = 0
local trace_first_frame = nil
local trace_offset = 0
local room_write_events = {}
local room_build_events = {}
local source_build_events = {}
local source_write_events = {}
local atomic_wrap_hits = 0
local hazard_helper_hits = 0
local stage1_cache_trace = {}
local last_stage1_cache = ""
local opening_started = false
local opening_completed = false
local opening_title_frame = -1
local route_down_frame = VIA_OPENING and -1 or 180
local opening_state_writes = {}

pcall(function()
  emu:setBreakpoint(function()
    if first_gameplay >= 0 then atomic_wrap_hits = atomic_wrap_hits + 1 end
  end, 0x3498)
  emu:setBreakpoint(function()
    if first_gameplay >= 0 and emu:read8(0xFF99) == 0x0E then
      hazard_helper_hits = hazard_helper_hits + 1
    end
  end, 0x6BA7)
end)

local function register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and value then return value end
  ok, value = pcall(function() return emu:readRegister(string.lower(name)) end)
  if ok and value then return value end
  return 0
end

if TRACE_OPENING_STATE then
  -- The stock ROM has nine direct LDH [$C1],A sites. Range watchpoints do
  -- not consistently fire for high-memory I/O in every mGBA build, so keep
  -- executable breakpoints as the authoritative write-site receipt.
  local ffc1_sites = {
    {0x0A20, 0x00}, {0x15CC, 0x00}, {0x15EE, 0x00},
    {0x19D0, 0x00}, {0x19FD, 0x00}, {0x25C8, 0x00},
    {0x40EE, 0x01}, {0x7896, 0x01}, {0x5C51, 0x07},
  }
  for _, row in ipairs(ffc1_sites) do
    local site, bank = row[1], row[2]
    assert(emu:setBreakpoint(function()
      if bank ~= 0 and emu:read8(0xFF99) ~= bank then return end
      if #opening_state_writes >= 256 then return end
      local sp = register("SP") & 0xFFFF
      local return1 = emu:read8(sp) | (emu:read8(sp + 1) << 8)
      local return2 = emu:read8(sp + 2) | (emu:read8(sp + 3) << 8)
      opening_state_writes[#opening_state_writes + 1] = string.format(
        "f%d:aFFC1:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:sp%04X:r%04X/%04X:s%02X:i%02X",
        frame, emu:read8(0xFFC1), register("A") & 0xFF,
        site, emu:read8(0xFF99), register("AF") & 0xFFFF,
        register("BC") & 0xFFFF, register("DE") & 0xFFFF,
        register("HL") & 0xFFFF, sp, return1, return2,
        emu:read8(0xD880), emu:read8(0xFFC1))
    end, site) > 0)
  end
  assert(emu:setRangeWatchpoint(function(info)
    if #opening_state_writes >= 256 then return end
    opening_state_writes[#opening_state_writes + 1] = string.format(
      "f%d:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:s%02X:i%02X",
      frame, info.address & 0xFFFF, info.oldValue & 0xFF,
      info.newValue & 0xFF, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, emu:read8(0xD880), emu:read8(0xFFC1))
  end, 0xFFC1, 0xFFC1, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  assert(emu:setRangeWatchpoint(function(info)
    if #opening_state_writes >= 256 then return end
    opening_state_writes[#opening_state_writes + 1] = string.format(
      "f%d:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:s%02X:i%02X",
      frame, info.address & 0xFFFF, info.oldValue & 0xFF,
      info.newValue & 0xFF, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, emu:read8(0xD880), emu:read8(0xFFC1))
  end, 0xDCFD, 0xDCFD, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
end

if TRACE_WRITES then
  assert(emu:setRangeWatchpoint(function(info)
    local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    if camera < 0x02B0 or camera > 0x02D0 then return end
    if #room_write_events >= 2048 then return end
    room_write_events[#room_write_events + 1] = string.format(
      "f%d:g%d:c%04X:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X",
      frame, gameplay_frame, camera, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      register("AF") & 0xFFFF, register("BC") & 0xFFFF,
      register("DE") & 0xFFFF, register("HL") & 0xFFFF)
  end, 0xC1A0, 0xC1D0, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
  assert(emu:setBreakpoint(function()
    local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    if camera < 0x02B0 or camera > 0x02D0 then return end
    if #room_build_events >= 32 then return end
    local source = emu:read8(0xDC0E) | (emu:read8(0xDC0F) << 8)
    local bytes = {}
    for offset = 0, 0x9F do
      bytes[#bytes + 1] = string.format("%02X", emu:read8(source + offset))
    end
    room_build_events[#room_build_events + 1] = string.format(
      "f%d:g%d:c%04X:s%04X:pc%04X:bank%02X:cfaa%02X:c297%02X:c29b%02X:data%s",
      frame, gameplay_frame, camera, source, register("PC") & 0xFFFF,
      emu:read8(0xFF99), emu:read8(0xCFAA), emu:read8(0xC297),
      emu:read8(0xC29B), table.concat(bytes))
  end, 0x1399) > 0)
  assert(emu:setBreakpoint(function()
    local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    if camera < 0x02B0 or camera > 0x02D0 then return end
    if #source_build_events >= 64 then return end
    source_build_events[#source_build_events + 1] = string.format(
      "entry:f%d:g%d:c%04X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X:d%02X%02X%02X%02X",
      frame, gameplay_frame, camera, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF, emu:read8(0xDC00), emu:read8(0xDC01),
      emu:read8(0xDC02), emu:read8(0xDC03))
  end, 0x1322) > 0)
  assert(emu:setBreakpoint(function()
    local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    if camera < 0x02B0 or camera > 0x02D0 then return end
    if #source_build_events >= 64 then return end
    source_build_events[#source_build_events + 1] = string.format(
      "mapped:f%d:g%d:c%04X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X",
      frame, gameplay_frame, camera, register("PC") & 0xFFFF,
      emu:read8(0xFF99), register("AF") & 0xFFFF,
      register("BC") & 0xFFFF, register("DE") & 0xFFFF,
      register("HL") & 0xFFFF)
  end, 0x1329) > 0)
  assert(emu:setRangeWatchpoint(function(info)
    local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    if camera < 0x02B0 or camera > 0x02D0 then return end
    if #source_write_events >= 4096 then return end
    source_write_events[#source_write_events + 1] = string.format(
      "f%d:g%d:c%04X:a%04X:o%02X:n%02X:p%04X:b%02X:af%04X:bc%04X:de%04X:hl%04X",
      frame, gameplay_frame, camera, info.address & 0xFFFF,
      info.oldValue & 0xFF, info.newValue & 0xFF,
      register("PC") & 0xFFFF, emu:read8(0xFF99),
      register("AF") & 0xFFFF, register("BC") & 0xFFFF,
      register("DE") & 0xFFFF, register("HL") & 0xFFFF)
  end, 0xC400, 0xC4B0, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
end

if TRACE_FILE then
  local trace = assert(io.open(TRACE_FILE, "r"))
  for line in trace:lines() do
    local sample_frame = tonumber(line:match('"f":(%d+)'))
    local sample_keys = tonumber(line:match('"keys":(%d+)'))
    if sample_frame and sample_keys then
      trace_keys[sample_frame] = sample_keys
      if trace_first_frame == nil or sample_frame < trace_first_frame then
        trace_first_frame = sample_frame
      end
    end
  end
  trace:close()
end

local function pulse(lo, hi, mask)
  return (frame >= lo and frame < hi) and mask or 0
end

local function dump_bytes(path, reader, base, length)
  local handle = assert(io.open(path, "wb"))
  for offset = 0, length - 1 do
    handle:write(string.char(reader(base + offset)))
  end
  handle:close()
end

local function hash_bytes(reader, base, length)
  local value = 0xA55A
  for offset = 0, length - 1 do
    value = ((value * 257) ~ reader(base + offset)) & 0xFFFFFFFF
  end
  return value
end

local function finish(status)
  if finished then return end
  finished = true
  emu:setKeys(0)
  emu:screenshot(OUT .. "/final.png")
  dump_bytes(OUT .. "/c1a0.bin", function(address)
    return emu:read8(address)
  end, 0xC1A0, 0x240)
  dump_bytes(OUT .. "/vram9800.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x9800, 0x400)
  dump_bytes(OUT .. "/vram9c00.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x9C00, 0x400)
  dump_bytes(OUT .. "/vram9800-attrs.bin", function(address)
    return raw_vram:read8(0x2000 + address - 0x8000)
  end, 0x9800, 0x400)
  dump_bytes(OUT .. "/vram9c00-attrs.bin", function(address)
    return raw_vram:read8(0x2000 + address - 0x8000)
  end, 0x9C00, 0x400)
  local lcdc = emu:read8(0xFF40)
  local scx = emu:read8(0xFF43)
  local scy = emu:read8(0xFF42)
  local map_base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  local visible_tiles = assert(io.open(OUT .. "/visible-tiles.bin", "wb"))
  local visible_attrs = assert(io.open(OUT .. "/visible-attrs.bin", "wb"))
  for row = 0, 17 do
    for column = 0, 19 do
      local map_y = ((scy + row * 8) >> 3) & 0x1F
      local map_x = ((scx + column * 8) >> 3) & 0x1F
      local offset = map_base - 0x8000 + map_y * 32 + map_x
      visible_tiles:write(string.char(raw_vram:read8(offset)))
      visible_attrs:write(string.char(raw_vram:read8(0x2000 + offset)))
    end
  end
  visible_tiles:close()
  visible_attrs:close()
  local old_bcps = emu:read8(0xFF68)
  local bg_cram = assert(io.open(OUT .. "/bg-cram.bin", "wb"))
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    bg_cram:write(string.char(emu:read8(0xFF69)))
  end
  bg_cram:close()
  emu:write8(0xFF68, old_bcps)
  local old_ocps = emu:read8(0xFF6A)
  local obj_cram = assert(io.open(OUT .. "/obj-cram.bin", "wb"))
  for index = 0, 63 do
    emu:write8(0xFF6A, index)
    obj_cram:write(string.char(emu:read8(0xFF6B)))
  end
  obj_cram:close()
  emu:write8(0xFF6A, old_ocps)
  dump_bytes(OUT .. "/hardware-oam.bin", function(address)
    return emu:read8(address)
  end, 0xFE00, 0xA0)
  dump_bytes(OUT .. "/shadow-oam.bin", function(address)
    return emu:read8(address)
  end, 0xDA00, 0xA0)
  dump_bytes(OUT .. "/vram-low-tiles.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x8000, 0x800)
  dump_bytes(OUT .. "/vram-high-tiles.bin", function(address)
    return raw_vram:read8(address - 0x8000)
  end, 0x8800, 0x800)

  local report = assert(io.open(OUT .. "/probe.txt", "w"))
  report:write("status=" .. status .. "\n")
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format("first_gameplay=%d\n", first_gameplay))
  report:write(string.format("gameplay_frames=%d\n", gameplay_frame))
  report:write(string.format("via_opening=%d\n", VIA_OPENING and 1 or 0))
  report:write(string.format(
    "opening_started=%d\n", opening_started and 1 or 0))
  report:write(string.format(
    "opening_completed=%d\n", opening_completed and 1 or 0))
  report:write(string.format("opening_title_frame=%d\n", opening_title_frame))
  report:write(string.format("initial_room=%02X\n", initial_room & 0xFF))
  report:write(string.format("final_room=%02X\n", emu:read8(0xFFBD)))
  report:write(string.format("room_changes=%d\n", room_changes))
  report:write(string.format("target_camera=%s\n",
    TARGET_CAMERA and string.format("%04X", TARGET_CAMERA) or "none"))
  report:write(string.format("target_settle_frames=%d\n", TARGET_SETTLE))
  report:write(string.format("window_frames=%d\n", window_frames))
  report:write(string.format("final_cfaa=%02X\n", emu:read8(0xCFAA)))
  report:write(string.format("final_dcfd=%02X\n", emu:read8(0xDCFD)))
  report:write(string.format(
    "final_state=scene:%02X room:%02X ffc1:%02X ffe4:%02X lcdc:%02X " ..
    "scx:%02X scy:%02X wx:%02X wy:%02X dc00:%02X dc01:%02X " ..
    "dc02:%02X dc03:%02X c1a4:%02X\n",
    emu:read8(0xD880), emu:read8(0xFFBD), emu:read8(0xFFC1),
    emu:read8(0xFFE4), emu:read8(0xFF40), emu:read8(0xFF43),
    emu:read8(0xFF42), emu:read8(0xFF4B), emu:read8(0xFF4A),
    emu:read8(0xDC00), emu:read8(0xDC01), emu:read8(0xDC02),
    emu:read8(0xDC03), emu:read8(0xC1A4)))
  report:write(string.format(
    "c1a0_hash=%08X\n",
    hash_bytes(function(address) return emu:read8(address) end,
      0xC1A0, 0x240)))
  report:write(string.format(
    "vram9800_hash=%08X\n",
    hash_bytes(function(address)
      return raw_vram:read8(address - 0x8000)
    end, 0x9800, 0x400)))
  report:write("transitions=" .. table.concat(transitions, ";") .. "\n")
  report:write("cfaa_transitions=" .. table.concat(cfaa_transitions, ";") .. "\n")
  report:write("snapshots=" .. table.concat(snapshots, ";") .. "\n")
  report:write("room_writes=" .. table.concat(room_write_events, ";") .. "\n")
  report:write("room_builds=" .. table.concat(room_build_events, ";") .. "\n")
  report:write("source_builds=" .. table.concat(source_build_events, ";") .. "\n")
  report:write("source_writes=" .. table.concat(source_write_events, ";") .. "\n")
  report:write(string.format("atomic_wrap_hits=%d\n", atomic_wrap_hits))
  report:write(string.format("hazard_helper_hits=%d\n", hazard_helper_hits))
  report:write("stage1_cache_trace=" .. table.concat(stage1_cache_trace, ";") .. "\n")
  report:write("opening_state_writes=" .. table.concat(opening_state_writes, ";") .. "\n")
  report:close()
  emu:quit()
end

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1

  local scene = emu:read8(0xD880)
  local active = emu:read8(0xFFC1)
  local room = emu:read8(0xFFBD)
  local lcdc = emu:read8(0xFF40)
  local cfaa = emu:read8(0xCFAA)
  if first_gameplay >= 0 and #stage1_cache_trace < 128 then
    local cache = string.format(
      "%02X/%02X/%02X/%02X:s%04X", emu:read8(0xDF53),
      emu:read8(0xDF57), emu:read8(0xDF55), emu:read8(0xDF58),
      emu:read8(0xDC0E) | (emu:read8(0xDC0F) << 8))
    if cache ~= last_stage1_cache then
      stage1_cache_trace[#stage1_cache_trace + 1] = string.format(
        "f%d:g%d:%s", frame, gameplay_frame, cache)
      last_stage1_cache = cache
    end
  end
  local state = string.format("%02X/%02X/%02X/%02X", scene, active, room, lcdc)
  if state ~= last_state and #transitions < 128 then
    transitions[#transitions + 1] = string.format("f%d:%s", frame, state)
    last_state = state
  end
  if cfaa ~= previous_cfaa and #cfaa_transitions < 256 then
    cfaa_transitions[#cfaa_transitions + 1] = string.format(
      "f%d:g%d:%02X", frame, gameplay_frame, cfaa)
    previous_cfaa = cfaa
  end
  if (lcdc & 0x20) ~= 0 and emu:read8(0xFF4A) < 144 then
    window_frames = window_frames + 1
  end

  local keys = 0
  if first_gameplay < 0 then
    if VIA_OPENING and not opening_completed then
      -- The first title option is OPENING. Use only released A pulses until
      -- the complete stock story returns to a freshly drawn title; never
      -- write a scene/script byte from the probe.
      if not opening_started then
        keys = pulse(180, 186, KEY_A)
          | pulse(300, 306, KEY_A)
          | pulse(420, 426, KEY_A)
        if scene == 0x15 then opening_started = true end
      elseif scene == 0x15 then
        keys = ((frame % 90) < 4) and KEY_A or 0
      elseif active == 1 and scene ~= 0x15 then
        -- OPENING transitions directly into the ordinary Stage-intro/gameplay
        -- route. There is no second title selection after a completed story.
        opening_completed = true
        opening_title_frame = frame
        keys = 0
      end
    else
      -- DOWN selects GAME START. Repeated released confirmations cover the
      -- stock score/stage cards without memory writes. The opening route uses
      -- the identical relative schedule after its returned title settles.
      local down = route_down_frame
      if TRACE_FILE and not VIA_OPENING then
        keys = keys | pulse(down, down + 6, KEY_DOWN)
        keys = keys | pulse(down + 21, down + 27, KEY_A)
        keys = keys | pulse(down + 81, down + 87, KEY_A)
        keys = keys | pulse(down + 141, down + 147, KEY_A)
        keys = keys | pulse(down + 201, down + 207, KEY_START)
        keys = keys | pulse(down + 251, down + 257, KEY_A)
      else
        keys = keys | pulse(down, down + 6, KEY_DOWN)
        keys = keys | pulse(down + 13, down + 19, KEY_A)
        keys = keys | pulse(down + 61, down + 67, KEY_A)
        keys = keys | pulse(down + 111, down + 117, KEY_A)
        keys = keys | pulse(down + 161, down + 167, KEY_START)
        keys = keys | pulse(down + 211, down + 217, KEY_A)
      end
    end
    if scene == 0x02 and active == 1 then
      first_gameplay = frame
      if TRACE_FILE then trace_offset = frame - assert(trace_first_frame) end
      initial_room = room
      previous_room = room
      keys = TRACE_FILE and trace_key or (KEY_UP | (FIRE and KEY_A or 0))
    end
  else
    gameplay_frame = gameplay_frame + 1
    if TRACE_FILE then
      local source_frame = frame - trace_offset
      if trace_keys[source_frame] ~= nil then trace_key = trace_keys[source_frame] end
      keys = trace_key
    else
      keys = KEY_UP | (FIRE and KEY_A or 0)
    end
    if SNAP_INTERVAL > 0 and gameplay_frame % SNAP_INTERVAL == 0 then
      local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
      local name = string.format(
        "route-g%04d-r%02X-c%04X.png", gameplay_frame, room, camera)
      emu:screenshot(OUT .. "/" .. name)
      snapshots[#snapshots + 1] = string.format(
        "g%d:r%02X:c%04X:l%02X:y%02X:w%02X:d%02X:m98%08X:m9c%08X:c1%08X",
        gameplay_frame, room, camera, lcdc, emu:read8(0xFF4A),
        emu:read8(0xFF4B), emu:read8(0xDCFD),
        hash_bytes(function(address)
          return raw_vram:read8(address - 0x8000)
        end, 0x9800, 0x400),
        hash_bytes(function(address)
          return raw_vram:read8(address - 0x8000)
        end, 0x9C00, 0x400),
        hash_bytes(function(address) return emu:read8(address) end,
          0xC1A0, 0x240))
    end
    if room ~= previous_room then
      room_changes = room_changes + 1
      previous_room = room
    end
    local camera = emu:read8(0xDC02) | (emu:read8(0xDC03) << 8)
    local reached_target = TARGET_CAMERA ~= nil
      and room == TARGET_ROOM and camera == TARGET_CAMERA
    if target_settle_frame ~= nil then
      keys = 0
      if gameplay_frame - target_settle_frame >= TARGET_SETTLE then
        emu:setKeys(keys)
        finish("ok")
        return
      end
    elseif reached_target then
      target_settle_frame = gameplay_frame
      keys = 0
    elseif TARGET_CAMERA == nil and gameplay_frame >= PLAY_LIMIT then
      emu:setKeys(keys)
      finish("ok")
      return
    end
  end
  emu:setKeys(keys)

  if frame >= LIMIT then finish("timeout") end
end)
