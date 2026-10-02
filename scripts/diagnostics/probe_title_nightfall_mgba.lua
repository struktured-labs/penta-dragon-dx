-- Capture the cold and attract-returned GAME START title in one mGBA run.
-- No input or state injection is used.  The Python verifier authenticates
-- both the CRAM/attribute payload and the renderer-visible pixels.

local OUT = assert(os.getenv("PENTA_TITLE_NIGHTFALL_OUT"),
  "PENTA_TITLE_NIGHTFALL_OUT is required")
local SETTLE = tonumber(os.getenv("PENTA_TITLE_NIGHTFALL_SETTLE") or "300")
local LIMIT = tonumber(os.getenv("PENTA_TITLE_NIGHTFALL_LIMIT") or "12000")
local TITLE_SCENE = 0x01

local frame = 0
local previous_scene = -1
local title_elapsed = 0
local cold_captured = false
local left_title = false
local returned_captured = false
local deferred_wram_frames = 0
local transitions = {}

local function bg_cram()
  local old_bcps = emu:read8(0xFF68)
  local values = {}
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    values[#values + 1] = string.format("%02X", emu:read8(0xFF69))
  end
  emu:write8(0xFF68, old_bcps)
  return table.concat(values, "")
end

local function attributes(base)
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 1)
  local rows = {}
  for row = 1, 18 do
    local cells = {}
    for column = 0, 20 do
      cells[#cells + 1] = string.format(
        "%02X", emu:read8(base + row * 32 + column)
      )
    end
    rows[#rows + 1] = string.format(
      "r%02d=%s", row, table.concat(cells, " ")
    )
  end
  emu:write8(0xFF4F, old_vbk)
  return table.concat(rows, "\n")
end

local function capture(label)
  local lcdc = emu:read8(0xFF40)
  local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
  emu:screenshot(OUT .. "." .. label .. ".png")
  local handle = assert(io.open(OUT .. "." .. label .. ".txt", "w"))
  handle:write(string.format(
    "frame=%d\nd880=%02X\nffc1=%d\nlcdc=%02X\nscx=%d\nscy=%d\nbase=%04X\n",
    frame, emu:read8(0xD880), emu:read8(0xFFC1), lcdc,
    emu:read8(0xFF43), emu:read8(0xFF42), base
  ))
  handle:write("bgcram=" .. bg_cram() .. "\n")
  handle:write(attributes(base) .. "\n")
  handle:close()
end

local function finish(status, message)
  local report = assert(io.open(OUT .. ".report", "w"))
  report:write("status=" .. status .. "\n")
  report:write("message=" .. message .. "\n")
  report:write(string.format("frames=%d\n", frame))
  report:write(string.format(
    "deferred_wram_frames=%d\n", deferred_wram_frames
  ))
  report:write("transitions=" .. table.concat(transitions, ",") .. "\n")
  report:write(string.format("cold_captured=%s\n", tostring(cold_captured)))
  report:write(string.format("left_title=%s\n", tostring(left_title)))
  report:write(string.format(
    "returned_captured=%s\n", tostring(returned_captured)
  ))
  report:close()
  os.exit(status == "ok" and 0 or 3)
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  -- D880 is banked WRAM.  Candidate helpers legitimately select another
  -- bank across frame boundaries; sampling D880 then would invent a scene
  -- transition and continually reset the returned-title settle counter.
  if (emu:read8(0xFF70) % 0x08) ~= 1 then
    deferred_wram_frames = deferred_wram_frames + 1
    if frame >= LIMIT then
      finish("failed", "title-return-timeout")
    end
    return
  end
  local scene = emu:read8(0xD880)
  if scene ~= previous_scene then
    transitions[#transitions + 1] = string.format(
      "%d:%02X>%02X", frame, previous_scene & 0xFF, scene
    )
    previous_scene = scene
    title_elapsed = scene == TITLE_SCENE and 1 or 0
  elseif scene == TITLE_SCENE then
    title_elapsed = title_elapsed + 1
  end

  if not cold_captured and scene == TITLE_SCENE and title_elapsed >= SETTLE then
    capture("cold")
    cold_captured = true
  elseif cold_captured and not left_title and scene ~= TITLE_SCENE then
    left_title = true
  elseif left_title and not returned_captured
      and scene == TITLE_SCENE and title_elapsed >= SETTLE then
    capture("returned")
    returned_captured = true
    finish("ok", "cold-and-returned-title-captured")
    return
  end

  if frame >= LIMIT then
    finish("failed", "title-return-timeout")
  end
end)
