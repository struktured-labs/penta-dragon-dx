-- Native-renderer title cursor route.  The CGB title runs with LCDC.4 clear,
-- so selector tile $73 at map cells $9924/$9964 is the authoritative owner.
-- Drive only DOWN/UP, observe the natural blink, and capture one renderer
-- frame for each selected position.

local OUT = assert(os.getenv("PENTA_TITLE_CURSOR_OUT"))
local SETTLE = tonumber(os.getenv("PENTA_TITLE_CURSOR_SETTLE") or "300")
local OBSERVE = tonumber(os.getenv("PENTA_TITLE_CURSOR_OBSERVE") or "180")
local PRESS = tonumber(os.getenv("PENTA_TITLE_CURSOR_PRESS") or "6")
local TITLE_SCENE, KEY_UP, KEY_DOWN = 0x01, 0x40, 0x80
local OPENING_CELL, GAME_CELL, CURSOR_TILE = 0x9924, 0x9964, 0x73

local frame, title_age, phase, phase_age = 0, 0, "settle", 0
local samples = {
  opening = { expected = 0, wrong = 0, context = 0, screenshot = false },
  game = { expected = 0, wrong = 0, context = 0, screenshot = false },
  restored = { expected = 0, wrong = 0, context = 0, screenshot = false },
}

local function finish(status, message)
  local report = assert(io.open(OUT .. ".report", "w"))
  report:write("status=" .. status .. "\n")
  report:write("message=" .. message .. "\n")
  report:write("frames=" .. frame .. "\n")
  for _, name in ipairs({"opening", "game", "restored"}) do
    local item = samples[name]
    report:write(string.format("%s_expected_hits=%d\n", name, item.expected))
    report:write(string.format("%s_wrong_hits=%d\n", name, item.wrong))
    report:write(string.format("%s_context_failures=%d\n", name, item.context))
    report:write(string.format("%s_screenshot=%s\n", name,
      item.screenshot and (OUT .. "." .. name .. ".png") or ""))
  end
  report:close()
  local done = assert(io.open(OUT .. ".done", "w"))
  done:write(status .. "\n")
  done:close()
  os.exit(status == "ok" and 0 or 3)
end

local function observe(name, expected_cell, wrong_cell)
  local item = samples[name]
  if emu:read8(0xD880) ~= TITLE_SCENE or emu:read8(0xFFC1) ~= 0 then
    item.context = item.context + 1
  end
  if emu:read8(expected_cell) == CURSOR_TILE then
    item.expected = item.expected + 1
    item.visible_streak = (item.visible_streak or 0) + 1
    -- The map can change during VBlank after the completed raster. Require
    -- a whole frame with the selector present before capturing that raster.
    if not item.screenshot and item.visible_streak >= 2 then
      emu:screenshot(OUT .. "." .. name .. ".png")
      item.screenshot = true
    end
  else
    item.visible_streak = 0
  end
  if emu:read8(wrong_cell) == CURSOR_TILE then item.wrong = item.wrong + 1 end
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  if emu:read8(0xD880) == TITLE_SCENE then title_age = title_age + 1 else title_age = 0 end

  if phase == "settle" then
    if title_age >= SETTLE then phase, phase_age = "opening", 0 end
    return
  end
  if phase == "opening" then
    observe("opening", OPENING_CELL, GAME_CELL)
    phase_age = phase_age + 1
    if phase_age >= OBSERVE then phase, phase_age = "press_down", 0 end
    return
  end
  if phase == "press_down" then
    emu:setKeys(KEY_DOWN)
    phase_age = phase_age + 1
    if phase_age >= PRESS then phase, phase_age = "down_release", 0 end
    return
  end
  if phase == "down_release" then
    phase_age = phase_age + 1
    if phase_age >= PRESS then phase, phase_age = "game", 0 end
    return
  end
  if phase == "game" then
    observe("game", GAME_CELL, OPENING_CELL)
    phase_age = phase_age + 1
    if phase_age >= OBSERVE then phase, phase_age = "press_up", 0 end
    return
  end
  if phase == "press_up" then
    emu:setKeys(KEY_UP)
    phase_age = phase_age + 1
    if phase_age >= PRESS then phase, phase_age = "up_release", 0 end
    return
  end
  if phase == "up_release" then
    phase_age = phase_age + 1
    if phase_age >= PRESS then phase, phase_age = "restored", 0 end
    return
  end
  observe("restored", OPENING_CELL, GAME_CELL)
  phase_age = phase_age + 1
  if phase_age >= OBSERVE then
    for _, name in ipairs({"opening", "game", "restored"}) do
      local item = samples[name]
      if item.expected == 0 or item.wrong ~= 0 or item.context ~= 0 or not item.screenshot then
        finish("failed", "cursor-route-contract")
        return
      end
    end
    finish("ok", "native-title-cursor-route")
  end
end)
