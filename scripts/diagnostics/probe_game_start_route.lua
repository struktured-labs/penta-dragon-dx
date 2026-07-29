-- Exercise the title -> GAME START -> Stage 1 route without changing game
-- state behind the player's back.  In particular, this probe never writes
-- DCFD, FFBA, the PC, or SRAM.  The Python verifier controls whether mGBA
-- starts with no save or a copied save file.

local OUT = assert(os.getenv("GAME_START_OUT"))
local CONFIRM = os.getenv("GAME_START_CONFIRM") or "a"
local MAX_FRAMES = tonumber(os.getenv("GAME_START_MAX_FRAMES") or "1800")

local KEY_A = 0x01
local KEY_START = 0x08
local KEY_DOWN = 0x80
local FIRST_CONFIRM = (CONFIRM == "start") and KEY_START or KEY_A

local SCHEDULE = {
  {180, 186, KEY_DOWN},
  {193, 199, FIRST_CONFIRM},
  {241, 247, KEY_A},
  {291, 297, KEY_A},
  {341, 347, KEY_START},
  {391, 397, KEY_A},
}

local CAPTURES = {
  [170] = true,
  [220] = true,
  [280] = true,
  [340] = true,
  [400] = true,
  [480] = true,
  [600] = true,
  [900] = true,
  [1200] = true,
  [1500] = true,
  [1800] = true,
}

local frame = 0
local first_gameplay = -1
local gameplay_frames = 0
local previous_d880 = -1
local previous_ffc1 = -1
local transitions = {}
local samples = {}
local captures = {}

local function register(name)
  local ok, value = pcall(function() return emu:getRegister(name) end)
  return ok and value or -1
end

local function sample(tag)
  samples[#samples + 1] = string.format(
    "%s:f%d:pc=%04X:sp=%04X:d880=%02X:ffc1=%02X:dcfd=%02X:" ..
    "ffba=%02X:ffbd=%02X:lcdc=%02X:bgp=%02X:ly=%02X:ie=%02X:if=%02X",
    tag, frame, register("PC") & 0xFFFF, register("SP") & 0xFFFF,
    emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xDCFD),
    emu:read8(0xFFBA), emu:read8(0xFFBD), emu:read8(0xFF40),
    emu:read8(0xFF47), emu:read8(0xFF44), emu:read8(0xFFFF),
    emu:read8(0xFF0F))
end

local function finish(status)
  emu:setKeys(0)
  sample("final")
  local final_path = OUT .. "-final.png"
  emu:screenshot(final_path)
  captures[#captures + 1] = final_path
  local handle = assert(io.open(OUT .. ".txt", "w"))
  handle:write("status=" .. status .. "\n")
  handle:write("confirm=" .. CONFIRM .. "\n")
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("first_gameplay=%d\n", first_gameplay))
  handle:write(string.format("gameplay_frames=%d\n", gameplay_frames))
  handle:write(
    string.format("final_d880=%02X\n", emu:read8(0xD880)))
  handle:write(
    string.format("final_ffc1=%02X\n", emu:read8(0xFFC1)))
  handle:write(
    string.format("final_dcfd=%02X\n", emu:read8(0xDCFD)))
  handle:write("transitions=" .. table.concat(transitions, ",") .. "\n")
  for _, value in ipairs(samples) do
    handle:write("sample=" .. value .. "\n")
  end
  for _, value in ipairs(captures) do
    handle:write("capture=" .. value .. "\n")
  end
  handle:close()
  os.exit(status == "ok" and 0 or 2)
end

callbacks:add("frame", function()
  frame = frame + 1

  local keys = 0
  for _, event in ipairs(SCHEDULE) do
    if frame >= event[1] and frame < event[2] then
      keys = event[3]
      break
    end
  end
  emu:setKeys(keys)

  local d880 = emu:read8(0xD880)
  local ffc1 = emu:read8(0xFFC1)
  if d880 ~= previous_d880 or ffc1 ~= previous_ffc1 then
    transitions[#transitions + 1] = string.format(
      "%d:%02X/%02X>%02X/%02X",
      frame, previous_d880 & 0xFF, previous_ffc1 & 0xFF, d880, ffc1)
    previous_d880 = d880
    previous_ffc1 = ffc1
  end

  if ffc1 == 1 and d880 >= 0x02 and d880 <= 0x0B then
    if first_gameplay < 0 then
      first_gameplay = frame
      sample("first_gameplay")
      emu:screenshot(OUT .. "-gameplay.png")
      captures[#captures + 1] = OUT .. "-gameplay.png"
    end
    gameplay_frames = gameplay_frames + 1
    if gameplay_frames >= 120 then
      finish("ok")
      return
    end
  end

  if CAPTURES[frame] then
    local path = string.format("%s-f%04d.png", OUT, frame)
    emu:screenshot(path)
    captures[#captures + 1] = path
    sample("periodic")
  end

  if frame >= MAX_FRAMES then finish("timeout") end
end)
