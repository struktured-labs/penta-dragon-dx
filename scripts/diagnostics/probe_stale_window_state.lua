-- Verify that a real resumed stale item-menu Window is hidden immediately.

local OUT = assert(os.getenv("STALE_WINDOW_STATE_OUT"))
local LIMIT = tonumber(os.getenv("STALE_WINDOW_STATE_FRAMES") or "60")

local frame = 0
local main_loop_hits = 0
local entry_hits = 0
local entry = nil
local clear_frame = -1
local settle = 0
local finished = false

local function finish()
  if finished then return end
  finished = true
  emu:setKeys(0)
  emu:screenshot(OUT .. ".final.png")
  local handle = assert(io.open(OUT, "w"))
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("main_loop_hits=%d\n", main_loop_hits))
  handle:write(string.format("entry_hits=%d\n", entry_hits))
  if entry then
    handle:write(string.format(
      "entry=frame:%d scene:%02X active:%02X ffe4:%02X lcdc:%02X " ..
      "wy:%02X room:%02X\n",
      entry.frame, entry.scene, entry.active, entry.ffe4, entry.lcdc,
      entry.wy, entry.room))
  else
    handle:write("entry=none\n")
  end
  handle:write(string.format("clear_frame=%d\n", clear_frame))
  handle:write(string.format(
    "final=scene:%02X active:%02X ffe4:%02X lcdc:%02X wy:%02X " ..
    "room:%02X\n",
    emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFE4),
    emu:read8(0xFF40), emu:read8(0xFF4A), emu:read8(0xFFBD)))
  handle:close()
  os.exit(0)
end

pcall(function()
  emu:setBreakpoint(function()
    main_loop_hits = main_loop_hits + 1
  end, 0x016C)

  emu:setBreakpoint(function()
    if emu:read8(0xFF99) ~= 0x0D then return end
    local scene = emu:read8(0xD880)
    local lcdc = emu:read8(0xFF40)
    if scene < 0x02 or scene >= 0x0C then return end
    if emu:read8(0xFFC1) ~= 1 or emu:read8(0xFFE4) ~= 0 then return end
    if (lcdc & 0x20) == 0 or emu:read8(0xFF4A) >= 144 then return end
    entry_hits = entry_hits + 1
    if not entry then
      entry = {
        frame = frame,
        scene = scene,
        active = emu:read8(0xFFC1),
        ffe4 = emu:read8(0xFFE4),
        lcdc = lcdc,
        wy = emu:read8(0xFF4A),
        room = emu:read8(0xFFBD),
      }
      emu:screenshot(OUT .. ".entry.png")
    end
  end, 0x6A40)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  if entry and (emu:read8(0xFF40) & 0x20) == 0 then
    if clear_frame < 0 then
      clear_frame = frame
      emu:screenshot(OUT .. ".cleared.png")
    end
    settle = settle + 1
    if settle >= 2 then finish() end
  end
  if frame >= LIMIT then finish() end
end)
