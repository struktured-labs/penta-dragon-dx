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

local function register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok and value then return value end
  ok, value = pcall(function() return emu:readRegister(string.lower(name)) end)
  if ok and value then return value end
  return 0
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

  local report = assert(io.open(OUT .. "/probe.txt", "w"))
  report:write("status=" .. status .. "\n")
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format("first_gameplay=%d\n", first_gameplay))
  report:write(string.format("gameplay_frames=%d\n", gameplay_frame))
  report:write(string.format("initial_room=%02X\n", initial_room & 0xFF))
  report:write(string.format("final_room=%02X\n", emu:read8(0xFFBD)))
  report:write(string.format("room_changes=%d\n", room_changes))
  report:write(string.format("target_camera=%s\n",
    TARGET_CAMERA and string.format("%04X", TARGET_CAMERA) or "none"))
  report:write(string.format("target_settle_frames=%d\n", TARGET_SETTLE))
  report:write(string.format("window_frames=%d\n", window_frames))
  report:write(string.format("final_cfaa=%02X\n", emu:read8(0xCFAA)))
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
    -- Intro is selected by default. DOWN selects GAME START. Repeated released
    -- confirmations cover the stock score/stage cards without memory writes.
    if TRACE_FILE then
      keys = keys | pulse(180, 186, KEY_DOWN)
      keys = keys | pulse(201, 207, KEY_A)
      keys = keys | pulse(261, 267, KEY_A)
      keys = keys | pulse(321, 327, KEY_A)
      keys = keys | pulse(381, 387, KEY_START)
      keys = keys | pulse(431, 437, KEY_A)
    else
      keys = keys | pulse(180, 186, KEY_DOWN)
      keys = keys | pulse(193, 199, KEY_A)
      keys = keys | pulse(241, 247, KEY_A)
      keys = keys | pulse(291, 297, KEY_A)
      keys = keys | pulse(341, 347, KEY_START)
      keys = keys | pulse(391, 397, KEY_A)
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
