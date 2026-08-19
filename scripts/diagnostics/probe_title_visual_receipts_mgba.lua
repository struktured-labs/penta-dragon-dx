-- Complete cold -> attract/demo -> returned-title visual inventory.
-- All observations are natural runtime state; no memory or input injection.

local OUT = assert(os.getenv("TITLE_VISUAL_OUT"))
local LIMIT = tonumber(os.getenv("TITLE_VISUAL_MAX_FRAMES") or "26000")
local FOOTER_HEX = assert(os.getenv("TITLE_VISUAL_FOOTER_HEX"))
local PERIOD_HEX = assert(os.getenv("TITLE_VISUAL_PERIOD_HEX"))

local function from_hex(value)
  local result = {}
  for pair in value:gmatch("%x%x") do result[#result + 1] = tonumber(pair, 16) end
  return result
end

local FOOTER, PERIOD = from_hex(FOOTER_HEX), from_hex(PERIOD_HEX)
local frame, last_scene, banner_start = 0, -1, -1
local demo_seen, demo_samples, demo_sprites, demo_mismatches = false, 0, 0, 0
local live_scene1b, done = false, false
local transitions = {}
local captures = {}

local function bytes_at(base, expected)
  local actual, exact = {}, true
  for index, value in ipairs(expected) do
    local observed = emu:read8(base + index - 1)
    actual[#actual + 1] = string.format("%02X", observed)
    if observed ~= value then exact = false end
  end
  return exact, table.concat(actual)
end

local function visible_oam()
  local result = {}
  for slot = 0, 39 do
    local base = 0xFE00 + slot * 4
    local y, x = emu:read8(base), emu:read8(base + 1)
    if y > 0 and y < 160 and x > 0 and x < 168 then
      result[#result + 1] = string.format(
        "%d:%02X:%02X:%02X:%02X", slot, y, x,
        emu:read8(base + 2), emu:read8(base + 3)
      )
    end
  end
  return result
end

local function capture_footer(phase)
  local key = phase .. "_footer"
  if captures[key] then return end
  local footer_ok, footer_hex = bytes_at(0x9A41, FOOTER)
  local period_ok, period_hex = bytes_at(0x97F0, PERIOD)
  if not footer_ok or not period_ok then return end
  local path = string.format("%s/%s_f%d.png", OUT, key, frame)
  emu:screenshot(path)
  captures[key] = {
    frame=frame, footer_hex=footer_hex, period_hex=period_hex,
    visible_oam=visible_oam(), screenshot=path,
  }
end

local function capture_banner(phase, scene_age)
  local key = phase .. "_banner"
  if captures[key] or scene_age < 800 then return end
  local old_vbk = emu:read8(0xFF4F)
  local counts, unsafe = {}, 0
  emu:write8(0xFF4F, 1)
  for address = 0x9800, 0x9FFF do
    local attr = emu:read8(address)
    counts[attr & 0x07] = (counts[attr & 0x07] or 0) + 1
    if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
  end
  emu:write8(0xFF4F, old_vbk)
  local count_text = {}
  for palette = 0, 7 do
    count_text[#count_text + 1] = string.format(
      "%d:%d", palette, counts[palette] or 0
    )
  end
  local path = string.format("%s/%s_f%d.png", OUT, key, frame)
  emu:screenshot(path)
  captures[key] = {
    frame=frame, attr_counts=table.concat(count_text, ","), unsafe=unsafe,
    visible_oam=visible_oam(), screenshot=path,
  }
end

local function sample_demo()
  if frame % 10 ~= 0 or emu:read8(0xFFBF) ~= 1 then return end
  local actors = 0
  for slot = 0, 39 do
    local base = 0xFE00 + slot * 4
    local y, x = emu:read8(base), emu:read8(base + 1)
    local tile, attr = emu:read8(base + 2), emu:read8(base + 3)
    if y > 0 and y < 160 and x > 0 and x < 168
        and tile >= 0x20 and tile < 0x50 then
      actors = actors + 1
      local expected = tile < 0x30 and 2 or 6
      if (attr & 0x07) ~= expected then demo_mismatches = demo_mismatches + 1 end
    end
  end
  if actors == 0 then return end
  demo_samples = demo_samples + 1
  demo_sprites = demo_sprites + actors
  if demo_samples == 1 or demo_samples == 20 or demo_samples == 40 then
    emu:screenshot(string.format(
      "%s/demo_miniboss_sample%d_f%d.png", OUT, demo_samples, frame
    ))
  end
end

local function finish(status, message)
  if done then return end
  done = true
  local report = assert(io.open(OUT .. "/report.txt", "w"))
  report:write(string.format("status=%s\nmessage=%s\nframes=%d\n", status, message, frame))
  report:write("transitions=" .. table.concat(transitions, ",") .. "\n")
  report:write(string.format(
    "demo_samples=%d\ndemo_sprites=%d\ndemo_mismatches=%d\nlive_scene1b=%d\n",
    demo_samples, demo_sprites, demo_mismatches, live_scene1b and 1 or 0
  ))
  for _, key in ipairs({"cold_footer", "returned_footer", "cold_banner", "returned_banner"}) do
    local value = captures[key]
    report:write(string.format("%s_frame=%d\n", key, value and value.frame or -1))
    report:write(string.format("%s_screenshot=%s\n", key, value and value.screenshot or ""))
    report:write(string.format("%s_visible_oam=%s\n", key,
      value and table.concat(value.visible_oam, ",") or ""))
    if key:find("footer") then
      report:write(string.format("%s_footer_hex=%s\n", key, value and value.footer_hex or ""))
      report:write(string.format("%s_period_hex=%s\n", key, value and value.period_hex or ""))
    else
      report:write(string.format("%s_attr_counts=%s\n", key, value and value.attr_counts or ""))
      report:write(string.format("%s_unsafe=%d\n", key, value and value.unsafe or -1))
    end
  end
  report:close()
  local marker = assert(io.open(OUT .. "/DONE", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  emu:setKeys(0)
  local scene, ffc1 = emu:read8(0xD880), emu:read8(0xFFC1)
  if scene ~= last_scene then
    transitions[#transitions + 1] = string.format("%d:%02X:%02X", frame, scene, ffc1)
    last_scene, banner_start = scene, scene == 0x1C and frame or -1
  end
  if scene == 0x0A then demo_seen = true end
  if scene == 0x1B and ffc1 == 1 then live_scene1b = true end
  local phase = demo_seen and "returned" or "cold"
  capture_footer(phase)
  if scene == 0x1C and banner_start >= 0 then
    capture_banner(phase, frame - banner_start)
  end
  if scene == 0x0A then sample_demo() end
  if captures.cold_footer and captures.returned_footer
      and captures.cold_banner and captures.returned_banner
      and demo_samples >= 40 and live_scene1b then
    finish(demo_mismatches == 0 and "ok" or "failed", "complete-title-inventory")
  elseif frame >= LIMIT then
    finish("failed", "title-inventory-timeout")
  end
end)
