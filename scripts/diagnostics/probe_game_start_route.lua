-- Exercise the title -> GAME START -> Stage 1 route without changing game
-- state behind the player's back.  In particular, this probe never writes
-- DCFD, FFBA, the PC, or SRAM.  The Python verifier controls whether mGBA
-- starts with no save or a copied save file.

local OUT = assert(os.getenv("GAME_START_OUT"))
local CONFIRM = os.getenv("GAME_START_CONFIRM") or "a"
local MAX_FRAMES = tonumber(os.getenv("GAME_START_MAX_FRAMES") or "1800")
local DOWN_FRAME = tonumber(os.getenv("GAME_START_DOWN_FRAME") or "180")
local CONFIRM_FRAME =
  tonumber(os.getenv("GAME_START_CONFIRM_FRAME") or tostring(DOWN_FRAME + 13))
local PRESS_FRAMES = tonumber(os.getenv("GAME_START_PRESS_FRAMES") or "6")
local FOLLOWUPS = os.getenv("GAME_START_FOLLOWUPS") == "1"
local STAGE_CONFIRM_OFFSET =
  tonumber(os.getenv("GAME_START_STAGE_CONFIRM_OFFSET") or "-1")
local AFTER_ATTRACT = os.getenv("GAME_START_AFTER_ATTRACT") == "1"
local TRACE_EVENTS = os.getenv("GAME_START_TRACE_EVENTS") == "1"
local AFTER_ATTRACT_TITLE_DELAY = tonumber(
  os.getenv("GAME_START_AFTER_ATTRACT_TITLE_DELAY") or "180")
local WARM_RESET = os.getenv("GAME_START_WARM_RESET") == "1"
local WARM_RESET_FRAME =
  tonumber(os.getenv("GAME_START_WARM_RESET_FRAME") or "20")

local KEY_A = 0x01
local KEY_START = 0x08
local KEY_DOWN = 0x80
local FIRST_CONFIRM = (CONFIRM == "start") and KEY_START or KEY_A

local SCHEDULE = {}
local CAPTURES = {}
local effective_down_frame = DOWN_FRAME
local effective_confirm_frame = CONFIRM_FRAME

local function install_schedule(down_frame, confirm_frame)
  effective_down_frame = down_frame
  effective_confirm_frame = confirm_frame
  SCHEDULE = {
    {down_frame, down_frame + PRESS_FRAMES, KEY_DOWN},
    {confirm_frame, confirm_frame + PRESS_FRAMES, FIRST_CONFIRM},
  }
  if FOLLOWUPS then
    SCHEDULE[#SCHEDULE + 1] =
      {confirm_frame + 48, confirm_frame + 48 + PRESS_FRAMES, KEY_A}
    SCHEDULE[#SCHEDULE + 1] =
      {confirm_frame + 98, confirm_frame + 98 + PRESS_FRAMES, KEY_A}
    SCHEDULE[#SCHEDULE + 1] =
      {confirm_frame + 148, confirm_frame + 148 + PRESS_FRAMES, KEY_START}
    SCHEDULE[#SCHEDULE + 1] =
      {confirm_frame + 198, confirm_frame + 198 + PRESS_FRAMES, KEY_A}
  end
  if STAGE_CONFIRM_OFFSET >= 0 then
    SCHEDULE[#SCHEDULE + 1] = {
      confirm_frame + STAGE_CONFIRM_OFFSET,
      confirm_frame + STAGE_CONFIRM_OFFSET + PRESS_FRAMES,
      KEY_A,
    }
  end
  CAPTURES[math.max(1, down_frame - 10)] = true
  for _, offset in ipairs({27, 87, 147, 207, 287, 407}) do
    CAPTURES[confirm_frame + offset] = true
  end
end

if not AFTER_ATTRACT then
  install_schedule(DOWN_FRAME, CONFIRM_FRAME)
end

local frame = 0
local first_gameplay = -1
local gameplay_frames = 0
local previous_d880 = -1
local previous_ffc1 = -1
local transitions = {}
local samples = {}
local captures = {}
local did_reset = false
local demo_delay_hits = 0
local demo_delay_hits_before_route = 0
local saw_attract = false
local route_armed = not AFTER_ATTRACT
local live_trace = nil
local event_trace = nil

if AFTER_ATTRACT then
  live_trace = assert(io.open(OUT .. ".live.tsv", "w"))
  live_trace:write(
    "frame\tpc\tsp\tkeys\td880\tffc1\tdcfd\tffba\tffbd\tlcdc\tbgp\tly" ..
    "\tie\tif\tdf02\tdf08\tdf4c\tdf51\tdd09\tff93\tff99\tsvbk" ..
    "\tsp0\tsp1\tsp2\tsp3\tdemo_delay_hits\n")
  live_trace:flush()
end

if AFTER_ATTRACT and TRACE_EVENTS then
  event_trace = assert(io.open(OUT .. ".events.tsv", "w"))
  event_trace:write(
    "frame\tsite\tpc\tsp\tsp0\tsp1\tsp2\tsp3\tsp4\tsp5" ..
    "\tcfaa0\tcfaa1\tcfaa2\tcfaa3\tcfaa4\tcfaa5\n")
  event_trace:flush()
end

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

local function trace_transition_site(site)
  if event_trace == nil then return end
  if not route_armed or emu:read8(0xD880) ~= 0 then return end
  local sp = register("SP") & 0xFFFF
  event_trace:write(string.format(
    "%d\t%s\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
    "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
    frame, site, register("PC") & 0xFFFF, sp,
    emu:read8(sp), emu:read8((sp + 1) & 0xFFFF),
    emu:read8((sp + 2) & 0xFFFF), emu:read8((sp + 3) & 0xFFFF),
    emu:read8((sp + 4) & 0xFFFF), emu:read8((sp + 5) & 0xFFFF),
    emu:read8(0xCFAA), emu:read8(0xCFAB), emu:read8(0xCFAC),
    emu:read8(0xCFAD), emu:read8(0xCFAE), emu:read8(0xCFAF)))
  event_trace:flush()
end

if AFTER_ATTRACT and TRACE_EVENTS then
  for _, entry in ipairs({
    {0x0040, "irq40"},
    {0x06D4, "vblank"},
    {0x0824, "dx_hook"},
    {0x0099, "lcd_wait"},
    {0x40B5, "clear_return"},
    {0x409D, "post_clear"},
    {0x40AE, "wait_return"},
    {0x41E4, "post_clear_jump"},
    {0x41E6, "post_clear_obp0"},
    {0x41E8, "post_clear_obp0_done"},
    {0x41EA, "post_clear_obp1"},
    {0x41EC, "post_clear_obp1_done"},
    {0x41EE, "post_clear_bgp"},
    {0x41F0, "post_clear_ret"},
    {0x3D3B, "outer_return"},
    {0xCFAA, "levelsel_stub"},
    {0x6A60, "title_palette"},
    {0x6E80, "prelude"},
    {0x6F20, "wrapper"},
    {0x6F90, "scene_detect"},
    {0x7D00, "title_transition"},
    {0xFF80, "oam_dma"},
    {0xFFDB, "invalid_hram"},
  }) do
    pcall(function()
      emu:setBreakpoint(function()
        trace_transition_site(entry[2])
      end, entry[1])
    end)
  end
end

local function sample(tag)
  samples[#samples + 1] = string.format(
    "%s:f%d:pc=%04X:sp=%04X:d880=%02X:ffc1=%02X:dcfd=%02X:" ..
    "ffba=%02X:ffbd=%02X:lcdc=%02X:bgp=%02X:ly=%02X:ie=%02X:if=%02X:" ..
    "df02=%02X:df08=%02X:df4c=%02X:df51=%02X:dd09=%02X:ff93=%02X:" ..
    "ff99=%02X:svbk=%02X",
    tag, frame, register("PC") & 0xFFFF, register("SP") & 0xFFFF,
    emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xDCFD),
    emu:read8(0xFFBA), emu:read8(0xFFBD), emu:read8(0xFF40),
    emu:read8(0xFF47), emu:read8(0xFF44), emu:read8(0xFFFF),
    emu:read8(0xFF0F), emu:read8(0xDF02), emu:read8(0xDF08),
    emu:read8(0xDF4C), emu:read8(0xDF51), emu:read8(0xDD09),
    emu:read8(0xFF93), emu:read8(0xFF99), emu:read8(0xFF70))
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
  handle:write(string.format("down_frame=%d\n", effective_down_frame))
  handle:write(string.format("confirm_frame=%d\n", effective_confirm_frame))
  handle:write(string.format("followups=%d\n", FOLLOWUPS and 1 or 0))
  handle:write(
    string.format("stage_confirm_offset=%d\n", STAGE_CONFIRM_OFFSET))
  handle:write(string.format("after_attract=%d\n", AFTER_ATTRACT and 1 or 0))
  handle:write(string.format("saw_attract=%d\n", saw_attract and 1 or 0))
  handle:write(string.format("warm_reset=%d\n", did_reset and 1 or 0))
  handle:write(string.format("demo_delay_hits=%d\n", demo_delay_hits))
  handle:write(string.format(
    "demo_delay_hits_before_route=%d\n", demo_delay_hits_before_route))
  handle:write(string.format(
    "live_demo_delay_hits=%d\n",
    demo_delay_hits - demo_delay_hits_before_route))
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

  if WARM_RESET and not did_reset and frame == WARM_RESET_FRAME then
    sample("pre_reset")
    did_reset = true
    emu:reset()
    frame = 0
    previous_d880 = -1
    previous_ffc1 = -1
    return
  end

  if frame == 1 then sample(did_reset and "post_reset" or "power_on") end

  local d880 = emu:read8(0xD880)
  local dcfd = emu:read8(0xDCFD)
  if AFTER_ATTRACT and not route_armed then
    if demo_delay_hits > 0 or (d880 == 0x0A and dcfd == 0) then
      saw_attract = true
    end
    if saw_attract and d880 == 0x01 and dcfd == 0 then
      local down_frame = frame + AFTER_ATTRACT_TITLE_DELAY
      install_schedule(down_frame, down_frame + 13)
      demo_delay_hits_before_route = demo_delay_hits
      route_armed = true
      sample("post_attract_title")
    end
  end

  local keys = 0
  for _, event in ipairs(SCHEDULE) do
    if frame >= event[1] and frame < event[2] then
      keys = event[3]
      break
    end
  end
  emu:setKeys(keys)

  local ffc1 = emu:read8(0xFFC1)
  if d880 ~= previous_d880 or ffc1 ~= previous_ffc1 then
    transitions[#transitions + 1] = string.format(
      "%d:%02X/%02X>%02X/%02X",
      frame, previous_d880 & 0xFF, previous_ffc1 & 0xFF, d880, ffc1)
    previous_d880 = d880
    previous_ffc1 = ffc1
  end

  if (
    route_armed
    and emu:read8(0xDCFD) == 1
    and ffc1 == 1
    and d880 >= 0x02
    and d880 <= 0x0B
  ) then
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

  if live_trace and route_armed then
    local sp = register("SP") & 0xFFFF
    live_trace:write(string.format(
      "%d\t%04X\t%04X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
      "%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t" ..
      "%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%d\n",
      frame, register("PC") & 0xFFFF, sp,
      emu:read8(0xFF93), emu:read8(0xD880), emu:read8(0xFFC1),
      emu:read8(0xDCFD), emu:read8(0xFFBA), emu:read8(0xFFBD),
      emu:read8(0xFF40), emu:read8(0xFF47), emu:read8(0xFF44),
      emu:read8(0xFFFF), emu:read8(0xFF0F), emu:read8(0xDF02),
      emu:read8(0xDF08), emu:read8(0xDF4C), emu:read8(0xDF51),
      emu:read8(0xDD09), emu:read8(0xFF93), emu:read8(0xFF99),
      emu:read8(0xFF70), emu:read8(sp), emu:read8((sp + 1) & 0xFFFF),
      emu:read8((sp + 2) & 0xFFFF), emu:read8((sp + 3) & 0xFFFF),
      demo_delay_hits))
    live_trace:flush()
  end

  if frame >= MAX_FRAMES then finish("timeout") end
end)
