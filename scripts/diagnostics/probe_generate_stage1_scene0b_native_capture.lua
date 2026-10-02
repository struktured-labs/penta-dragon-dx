-- Derive a candidate-native closed-menu scene-$0B state using SELECT only.

local STATE_IN = assert(os.getenv("PENTA_SCENE0B_DERIVE_STATE_IN"),
  "PENTA_SCENE0B_DERIVE_STATE_IN required")
local STATE_OUT = assert(os.getenv("PENTA_SCENE0B_DERIVE_STATE_OUT"),
  "PENTA_SCENE0B_DERIVE_STATE_OUT required")
local SCREENSHOT_OUT = assert(os.getenv("PENTA_SCENE0B_DERIVE_SCREENSHOT_OUT"),
  "PENTA_SCENE0B_DERIVE_SCREENSHOT_OUT required")
local PREFIX = assert(os.getenv("PENTA_SCENE0B_DERIVE_PREFIX"),
  "PENTA_SCENE0B_DERIVE_PREFIX required")
local STARTUP_TOKEN = assert(os.getenv("PENTA_SCENE0B_DERIVE_TOKEN"),
  "PENTA_SCENE0B_DERIVE_TOKEN required")
local SETTLE_FRAMES = tonumber(
  os.getenv("PENTA_SCENE0B_DERIVE_SETTLE_FRAMES") or "60")
assert(SETTLE_FRAMES >= 60, "settle frames must be at least 60")

local KEY_SELECT = 0x04
local loaded = false
local finished = false
local closed = false
local state_saved = false
local frame = 0
local select_frames = 0
local closed_frames = 0
local flush_frames = 0
local menu_open_events = 0
local menu_close_events = 0
local last_native_menu = false
local deferred_wram_frames = 0

local function write_token_marker(suffix, status)
  local path = PREFIX .. suffix
  local temporary = path .. ".partial"
  local marker = assert(io.open(temporary, "w"))
  marker:write("status=" .. status .. "\n")
  marker:write("startup_token=" .. STARTUP_TOKEN .. "\n")
  marker:close()
  assert(os.rename(temporary, path))
end

local function window_visible()
  local lcdc = emu:read8(0xFF40)
  return math.floor(lcdc / 0x20) % 2 ~= 0 and emu:read8(0xFF4A) < 144
end

local function native_menu()
  return emu:read8(0xFFE4) ~= 0
end

local function write_report(status, reason)
  local handle = assert(io.open(PREFIX .. ".report", "w"))
  handle:write("status=" .. status .. "\n")
  handle:write("reason=" .. reason .. "\n")
  handle:write("startup_token=" .. STARTUP_TOKEN .. "\n")
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("select_frames=%d\n", select_frames))
  handle:write(string.format("closed_settle_frames=%d\n", closed_frames))
  handle:write(string.format("menu_open_events=%d\n", menu_open_events))
  handle:write(string.format("menu_close_events=%d\n", menu_close_events))
  handle:write(string.format("deferred_wram_frames=%d\n", deferred_wram_frames))
  handle:write(string.format("state_saved=%d\n", state_saved and 1 or 0))
  handle:write(string.format("scene=%02X\n", emu:read8(0xD880)))
  handle:write(string.format("room=%02X\n", emu:read8(0xFFBD)))
  handle:write(string.format("active=%02X\n", emu:read8(0xFFC1)))
  handle:write(string.format("menu=%02X\n", emu:read8(0xFFE4)))
  handle:write(string.format("lcdc=%02X\n", emu:read8(0xFF40)))
  handle:write(string.format("scy=%02X\n", emu:read8(0xFF42)))
  handle:write(string.format("scx=%02X\n", emu:read8(0xFF43)))
  handle:close()
end

local function finish(status, reason)
  if finished then return end
  finished = true
  emu:setKeys(0)
  write_report(status, reason)
  write_token_marker(".done", status)
  emu:stop()
end

callbacks:add("frame", function()
  if finished then return end
  if not loaded then
    write_token_marker(".startup", "started")
    local ok, result = pcall(function()
      return emu:loadStateFile(STATE_IN)
    end)
    if not ok or result == false then
      finish("fail", "load-state-failed")
      return
    end
    loaded = true
    emu:setKeys(0)
    if emu:read8(0xD880) ~= 0x0B then
      finish("fail", "initial-scene-not-0B")
      return
    end
    if emu:read8(0xFFC1) ~= 0x01 then
      finish("fail", "initial-active-not-01")
      return
    end
    if emu:read8(0xFFE4) ~= 0x01 then
      finish("fail", "initial-menu-not-open")
      return
    end
    last_native_menu = true
    write_token_marker(".ready", "ready")
    return
  end

  frame = frame + 1
  if frame > 360 then
    finish("fail", "frame-limit")
    return
  end
  if emu:read8(0xFFC1) ~= 0x01 then
    finish("fail", "active-left-01")
    return
  end
  -- D880 is bank-1 WRAM. The candidate compiler briefly selects another
  -- SVBK during publication; reading D880 then would alias unrelated data.
  -- Release input and defer the logical route until bank 1 is observable.
  if (emu:read8(0xFF70) % 0x08) ~= 1 then
    deferred_wram_frames = deferred_wram_frames + 1
    emu:setKeys(0)
    return
  end
  if emu:read8(0xD880) ~= 0x0B then
    finish("fail", "scene-left-0B")
    return
  end

  local current_native_menu = native_menu()
  if current_native_menu and not last_native_menu then
    menu_open_events = menu_open_events + 1
  elseif last_native_menu and not current_native_menu then
    menu_close_events = menu_close_events + 1
  end
  last_native_menu = current_native_menu

  if not closed then
    emu:setKeys(KEY_SELECT)
    select_frames = select_frames + 1
    if not current_native_menu and not window_visible() then
      closed = true
      emu:setKeys(0)
    end
    return
  end

  emu:setKeys(0)
  if native_menu() or window_visible() then
    finish("fail", "menu-reappeared-after-close")
    return
  end
  if not state_saved then
    closed_frames = closed_frames + 1
    if closed_frames < SETTLE_FRAMES then return end
    local state_ok, state_result = pcall(function()
      return emu:saveStateFile(STATE_OUT)
    end)
    if not state_ok or state_result == false then
      finish("fail", "save-state-failed")
      return
    end
    emu:screenshot(SCREENSHOT_OUT)
    state_saved = true
    return
  end

  flush_frames = flush_frames + 1
  if flush_frames >= 4 then
    finish("pass", "candidate-native-select-close")
  end
end)
