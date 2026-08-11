-- Sample a live boss arena's BG tile IDs and CGB attributes from an mGBA
-- state. The Python verifier owns boss-specific interpretation and terminates
-- the exact guarded emulator process after this probe publishes its marker.

local OUT = assert(os.getenv("BOSS_GEOMETRY_OUT"),
  "BOSS_GEOMETRY_OUT is required")
local FRAMES = tonumber(os.getenv("BOSS_GEOMETRY_FRAMES") or "360")
local WARMUP = tonumber(os.getenv("BOSS_GEOMETRY_WARMUP") or "8")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_GEOMETRY_SCENE") or "12")

local trace = assert(io.open(OUT .. ".tsv", "w"))
trace:write("frame\tbase\tscy\tscx\trow\tcol\tscreen_row\tscreen_col\ttile\tattr\n")
trace:close()

local frame = 0
local samples = 0
local finished = false

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
  samples = samples + 1
end

callbacks:add("frame", function()
  if finished then return end
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
