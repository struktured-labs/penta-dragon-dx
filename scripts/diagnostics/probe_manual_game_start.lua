-- Passive headed trace for a human-driven cold GAME START route.
--
-- This probe never calls emu:setKeys(), reset(), loadState(), or write8().
-- It records the controls and machine state produced by the player so a
-- headed-only white screen can be diagnosed without resetting the emulator.

local OUT = assert(os.getenv("MANUAL_GAME_START_OUT"))
local FLUSH_EVERY = tonumber(
  os.getenv("MANUAL_GAME_START_FLUSH_EVERY") or "10")
local RING_SIZE = tonumber(
  os.getenv("MANUAL_GAME_START_RING_SIZE") or "900")
local CAPTURE_LIMIT = tonumber(
  os.getenv("MANUAL_GAME_START_CAPTURE_LIMIT") or "80")

local frame = 0
local ring = {}
local ring_start = 1
local transition_lines = {}
local captures = {}
local capture_count = 0
local demo_delay_hits = 0
local previous_signature = ""
local previous_keys = -1
local previous_dcfd = -1
local previous_d880 = -1
local previous_ffc1 = -1

pcall(function()
  emu:setBreakpoint(function()
    demo_delay_hits = demo_delay_hits + 1
  end, 0x10E7)
end)

local function register(name)
  local ok, value = pcall(function() return emu:readRegister(name) end)
  if ok then return value end
  ok, value = pcall(function() return emu:getRegister(name) end)
  return ok and value or -1
end

local function sample()
  return string.format(
    "f=%d pc=%04X sp=%04X keys=%02X d880=%02X ffc1=%02X dcfd=%02X " ..
    "ffba=%02X ffbd=%02X lcdc=%02X bgp=%02X ly=%02X ie=%02X if=%02X " ..
    "df02=%02X df08=%02X df4c=%02X df51=%02X dd09=%02X " ..
    "ff99=%02X svbk=%02X wait_hits=%d",
    frame, register("PC") & 0xFFFF, register("SP") & 0xFFFF,
    emu:read8(0xFF93), emu:read8(0xD880), emu:read8(0xFFC1),
    emu:read8(0xDCFD), emu:read8(0xFFBA), emu:read8(0xFFBD),
    emu:read8(0xFF40), emu:read8(0xFF47), emu:read8(0xFF44),
    emu:read8(0xFFFF), emu:read8(0xFF0F), emu:read8(0xDF02),
    emu:read8(0xDF08), emu:read8(0xDF4C), emu:read8(0xDF51),
    emu:read8(0xDD09), emu:read8(0xFF99), emu:read8(0xFF70),
    demo_delay_hits)
end

local function append_ring(line)
  if #ring < RING_SIZE then
    ring[#ring + 1] = line
    return
  end
  ring[ring_start] = line
  ring_start = (ring_start % RING_SIZE) + 1
end

local function ordered_ring()
  local ordered = {}
  if #ring < RING_SIZE then
    for index = 1, #ring do ordered[#ordered + 1] = ring[index] end
    return ordered
  end
  for offset = 0, RING_SIZE - 1 do
    local index = ((ring_start + offset - 1) % RING_SIZE) + 1
    ordered[#ordered + 1] = ring[index]
  end
  return ordered
end

local function flush()
  local handle = assert(io.open(OUT .. ".txt.tmp", "w"))
  handle:write("status=running\n")
  handle:write(string.format("frame=%d\n", frame))
  handle:write(string.format("demo_delay_hits=%d\n", demo_delay_hits))
  for _, line in ipairs(transition_lines) do
    handle:write("transition=" .. line .. "\n")
  end
  for _, path in ipairs(captures) do
    handle:write("capture=" .. path .. "\n")
  end
  for _, line in ipairs(ordered_ring()) do
    handle:write("sample=" .. line .. "\n")
  end
  handle:close()
  os.rename(OUT .. ".txt.tmp", OUT .. ".txt")
end

local function capture(tag)
  if capture_count >= CAPTURE_LIMIT then return end
  capture_count = capture_count + 1
  local path = string.format(
    "%s-%03d-f%06d-%s.png", OUT, capture_count, frame, tag)
  emu:screenshot(path)
  captures[#captures + 1] = path
end

callbacks:add("frame", function()
  frame = frame + 1
  local keys = emu:read8(0xFF93)
  local d880 = emu:read8(0xD880)
  local ffc1 = emu:read8(0xFFC1)
  local dcfd = emu:read8(0xDCFD)
  local signature = string.format("%02X/%02X/%02X", d880, ffc1, dcfd)
  local line = sample()
  append_ring(line)

  if (
    signature ~= previous_signature
    or keys ~= previous_keys
    or dcfd ~= previous_dcfd
    or d880 ~= previous_d880
    or ffc1 ~= previous_ffc1
  ) then
    transition_lines[#transition_lines + 1] = line
    capture("transition")
    previous_signature = signature
    previous_keys = keys
    previous_dcfd = dcfd
    previous_d880 = d880
    previous_ffc1 = ffc1
  elseif dcfd == 1 and ffc1 == 0 and frame % 30 == 0 then
    capture("prestage")
  elseif ffc1 == 1 and d880 >= 2 and d880 <= 11 and frame % 120 == 0 then
    capture("gameplay")
  end

  if frame % FLUSH_EVERY == 0 then flush() end
end)
