-- Natural cold GAME START followed by 600 consecutive hardware-OAM samples.

local OUT = assert(os.getenv("FLASH_ATTR_OUT"))
local LIMIT = tonumber(os.getenv("FLASH_ATTR_MAX_FRAMES") or "4000")
local KEY_A, KEY_START, KEY_RIGHT, KEY_DOWN = 0x01, 0x08, 0x10, 0x80
local frame, phase, capture_frames = 0, "boot", 0
local first_gameplay, visible_wait = -1, 0
local distributions = {{}, {}}
local orange = {0, 0}
local done = false

local function pulse(lo, hi, key)
  return frame >= lo and frame < hi and key or 0
end

local function visible(slot)
  local base = 0xFE00 + slot * 4
  local y, x = emu:read8(base), emu:read8(base + 1)
  return y > 0 and y < 160 and x > 0 and x < 168
end

local function sample(slot, index)
  local attr = emu:read8(0xFE00 + slot * 4 + 3)
  local palette = attr & 0x07
  distributions[index][palette] = (distributions[index][palette] or 0) + 1
  if palette == 4 then orange[index] = orange[index] + 1 end
end

local function finish(status, message)
  if done then return end
  done = true
  local report = assert(io.open(OUT .. ".report", "w"))
  report:write(string.format(
    "status=%s\nmessage=%s\nframes=%d\nfirst_gameplay=%d\nvisible_wait=%d\n" ..
    "capture_frames=%d\nslot0_orange=%d\nslot2_orange=%d\n",
    status, message, frame, first_gameplay, visible_wait, capture_frames,
    orange[1], orange[2]
  ))
  for index, slot in ipairs({0, 2}) do
    local parts = {}
    for palette = 0, 7 do
      parts[#parts + 1] = string.format(
        "%d:%d", palette, distributions[index][palette] or 0
      )
    end
    report:write(string.format("slot%d_distribution=%s\n", slot, table.concat(parts, ",")))
  end
  report:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(status .. "\n")
  marker:close()
  emu:stop()
end

callbacks:add("frame", function()
  if done then return end
  frame = frame + 1
  -- Preserve the established route but use the current title truth: DOWN
  -- selects GAME START; released confirmations clear the stock cards.
  local keys = 0
  if phase == "boot" then
    keys = pulse(180, 186, KEY_DOWN)
      | pulse(193, 199, KEY_A)
      | pulse(241, 247, KEY_A)
      | pulse(291, 297, KEY_A)
      | pulse(341, 347, KEY_START)
      | pulse(391, 397, KEY_A)
    if emu:read8(0xD880) == 0x02 and emu:read8(0xFFC1) == 1 then
      first_gameplay = frame
      phase = "seek"
      keys = KEY_RIGHT
    end
  elseif phase == "seek" then
    keys = KEY_RIGHT
    visible_wait = visible_wait + 1
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0x17)
    if visible(0) and visible(2) then
      phase = "capture"
      keys = 0
    end
  else
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0x17)
    sample(0, 1)
    sample(2, 2)
    capture_frames = capture_frames + 1
    if capture_frames >= 600 then
      local clean = orange[1] == 0 and orange[2] == 0
      finish(clean and "ok" or "failed", "complete-600-frame-oam-capture")
      return
    end
  end
  emu:setKeys(keys)
  if frame >= LIMIT then finish("failed", "route-timeout") end
end)
