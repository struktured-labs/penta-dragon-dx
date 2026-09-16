-- Sample a live boss arena's BG tile IDs and CGB attributes from an mGBA
-- state. The Python verifier owns boss-specific interpretation and terminates
-- the exact guarded emulator process after this probe publishes its marker.

local OUT = assert(os.getenv("BOSS_GEOMETRY_OUT"),
  "BOSS_GEOMETRY_OUT is required")
local STATE_FILE = assert(os.getenv("PENTA_STATE_FILE"),
  "PENTA_STATE_FILE is required")
local FRAMES = tonumber(os.getenv("BOSS_GEOMETRY_FRAMES") or "360")
local WARMUP = tonumber(os.getenv("BOSS_GEOMETRY_WARMUP") or "8")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_GEOMETRY_SCENE") or "12")
-- Optional diagnostic evidence only; never changes the geometry verdict or
-- substitutes a rendered frame for the existing strict tile/attribute trace.
local CAPTURE_FIRST = tonumber(os.getenv("BOSS_GEOMETRY_CAPTURE_FIRST") or "0")
local CAPTURE_LAST = tonumber(os.getenv("BOSS_GEOMETRY_CAPTURE_LAST") or "0")
assert(CAPTURE_FIRST >= 0 and CAPTURE_LAST >= CAPTURE_FIRST,
  "invalid geometry diagnostic capture interval")

local trace = assert(io.open(OUT .. ".tsv", "w"))
trace:write("frame\tbase\tscy\tscx\trow\tcol\tscreen_row\tscreen_col\ttile\tattr\n")
trace:close()

local frame = 0
local samples = 0
local finished = false
local state_loaded = false

local function diagnostic_register(name)
  local value = emu:readRegister(name)
  assert(value ~= nil, "missing diagnostic register: " .. name)
  return value & ((name == "pc" or name == "hl") and 0xFFFF or 0xFF)
end

local function install_diagnostics()
  if CAPTURE_FIRST == 0 then return end
  local writes = assert(io.open(OUT .. ".seam-writes.tsv", "w"))
  writes:write("frame\told\tnew\tpc\tbank\tvbk\tly\tstat\tlcdc\n")
  writes:flush()
  emu:setRangeWatchpoint(function(info)
    writes:write(string.format(
      "%d\t%02X\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
      frame, info.oldValue & 0xFF, info.newValue & 0xFF,
      diagnostic_register("pc"), emu:read8(0xFF99), emu:read8(0xFF4F),
      emu:read8(0xFF44), emu:read8(0xFF41), emu:read8(0xFF40)))
    writes:flush()
  end, 0x992F, 0x9930, C.WATCHPOINT_TYPE.WRITE)
  -- Banked VRAM/DMA writes need not trigger a CPU write watchpoint. Observe
  -- the authenticated seam helper's instruction boundaries independently.
  local helper = assert(io.open(OUT .. ".seam-helper.tsv", "w"))
  helper:write("frame\tpc\tbank\ta\tb\thl\tcell\tvbk\tly\tstat\tlcdc\n")
  helper:flush()
  for _, address in ipairs({0x5737, 0x5738, 0x573C, 0x5744, 0x5745,
                            0x6200, 0x6204, 0x6210, 0x6211,
                            0x6259, 0x625A, 0x626C, 0x626D}) do
    local pc = address
    assert(emu:setBreakpoint(function()
      local entry = (pc < 0x6200) and 0x5734 or ((pc < 0x6250) and 0x6200 or 0x6250)
      if emu:read8(entry) ~= 0x21 or emu:read8(entry + 1) ~= 0x2F
          or emu:read8(entry + 2) ~= 0x99 then return end
      helper:write(string.format(
        "%d\t%04X\t%02X\t%02X\t%02X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
        frame, pc, emu:read8(0xFF99), diagnostic_register("a"), diagnostic_register("b"),
        diagnostic_register("hl"), emu:read8(0x992F), emu:read8(0xFF4F),
        emu:read8(0xFF44), emu:read8(0xFF41), emu:read8(0xFF40)))
      helper:flush()
    end, pc), "failed to install seam diagnostic breakpoint")
  end
end

local function active_map()
  if (emu:read8(0xFF40) & 0x08) ~= 0 then return 0x9C00 end
  return 0x9800
end

local function sample()
  local base = active_map()
  local scy = emu:read8(0xFF42)
  local scx = emu:read8(0xFF43)
  local top_row = (scy >> 3) & 0x1F
  local left_col = (scx >> 3) & 0x1F
  local rows = ((scy & 7) == 0) and 18 or 19
  local cols = ((scx & 7) == 0) and 20 or 21
  local old_vbk = emu:read8(0xFF4F)
  local tiles, addresses = {}, {}
  emu:write8(0xFF4F, 0)
  for screen_row = 0, rows - 1 do
    for screen_col = 0, cols - 1 do
      local key = screen_row * cols + screen_col
      local row = (top_row + screen_row) & 0x1F
      local col = (left_col + screen_col) & 0x1F
      addresses[key] = base + row * 32 + col
      tiles[key] = emu:read8(addresses[key])
    end
  end
  emu:write8(0xFF4F, 1)
  local handle = assert(io.open(OUT .. ".tsv", "a"))
  for screen_row = 0, rows - 1 do
    for screen_col = 0, cols - 1 do
      local key = screen_row * cols + screen_col
      local address = addresses[key]
      local row = ((address - base) >> 5) & 0x1F
      local col = (address - base) & 0x1F
      local attr = emu:read8(address) & 0x07
      handle:write(string.format(
        "%d\t%04X\t%02X\t%02X\t%d\t%d\t%d\t%d\t%02X\t%d\n",
        frame, base, scy, scx, row, col, screen_row, screen_col,
        tiles[key], attr))
    end
  end
  handle:close()
  emu:write8(0xFF4F, old_vbk)
  if CAPTURE_FIRST > 0 and frame >= CAPTURE_FIRST and frame <= CAPTURE_LAST then
    local prefix = string.format("%s.f%04d", OUT, frame)
    emu:screenshot(prefix .. ".png")
    assert(emu:saveStateFile(prefix .. ".ss0") ~= false,
      "failed to save geometry diagnostic state")
  end
  samples = samples + 1
end

callbacks:add("frame", function()
  if finished then return end
  if not state_loaded then
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_FILE)
    end)
    assert(ok and result ~= false, "failed to load requested boss state")
    state_loaded = true
    install_diagnostics()
    return
  end
  frame = frame + 1

  -- Hold both combatants alive long enough to cover multiple animation
  -- phases without changing the boss state machine itself.
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCDD, 0xFF)
  emu:setKeys(0)

  -- A restored state can expose the map that was inactive when serialized.
  -- Give the production eight-group atomic publisher one complete row before
  -- collecting visible-animation evidence. Fresh continuous entry is checked
  -- separately by the state generator and does not rely on this grace period.
  if frame > WARMUP and emu:read8(0xD880) == EXPECTED_SCENE then sample() end

  if samples >= FRAMES then
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write(string.format("frames=%d samples=%d scene=%02X\n",
      frame, samples, emu:read8(0xD880)))
    done:close()
    finished = true
    emu:stop()
  end
end)
