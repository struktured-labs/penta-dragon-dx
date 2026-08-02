-- Resume a user capture, close an open item menu, and preserve visual evidence.

local OUT = assert(os.getenv("RESUME_STAGE1_VISUAL_OUT"))
local LIMIT = tonumber(os.getenv("RESUME_STAGE1_VISUAL_FRAMES") or "120")
local MOVE = os.getenv("RESUME_STAGE1_VISUAL_MOVE") or "none"
local KEYS = {none=0, up=0x40, down=0x80, left=0x20, right=0x10}
local MOVE_KEY = assert(KEYS[MOVE])

local frame = 0
local closed_frame = -1
local main_loop_hits = 0
local raw_vram = assert(emu.memory.vram)

local function hash_bytes(reader, base, length)
  local value = 0x811C9DC5
  for offset = 0, length - 1 do
    value = ((value ~ reader(base + offset)) * 0x01000193) & 0xFFFFFFFF
  end
  return value
end

local function source_fe_count()
  local count = 0
  for offset = 0, 0x23F do
    if emu:read8(0xC1A0 + offset) == 0xFE then count = count + 1 end
  end
  return count
end

pcall(function()
  emu:setBreakpoint(function() main_loop_hits = main_loop_hits + 1 end, 0x016C)
end)

callbacks:add("frame", function()
  frame = frame + 1
  local keys = 0
  if frame >= 10 and frame < 16 and emu:read8(0xFFE4) ~= 0 then
    keys = 0x04 -- SELECT closes the native item menu.
  elseif closed_frame >= 0 then
    keys = MOVE_KEY
    if frame % 45 < 6 then keys = keys | 0x01 end
  end
  emu:setKeys(keys)

  if closed_frame < 0 and emu:read8(0xFFE4) == 0
      and (emu:read8(0xFF40) & 0x20) == 0 then
    closed_frame = frame
  end
  if frame == 30 or frame == 60 or frame == LIMIT then
    emu:screenshot(string.format("%s.f%03d.png", OUT, frame))
  end
  if frame < LIMIT then return end

  local lcdc = emu:read8(0xFF40)
  local active_base = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
  local handle = assert(io.open(OUT .. ".txt", "w"))
  handle:write(string.format("frames=%d\n", frame))
  handle:write(string.format("closed_frame=%d\n", closed_frame))
  handle:write(string.format("main_loop_hits=%d\n", main_loop_hits))
  handle:write(string.format(
    "state=scene:%02X active:%02X room:%02X ffe4:%02X lcdc:%02X " ..
    "scx:%02X scy:%02X camera:%02X%02X\n",
    emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBD),
    emu:read8(0xFFE4), lcdc, emu:read8(0xFF43), emu:read8(0xFF42),
    emu:read8(0xDC03), emu:read8(0xDC02)))
  handle:write(string.format("source_hash=%08X\n",
    hash_bytes(function(address) return emu:read8(address) end,
      0xC1A0, 0x240)))
  handle:write(string.format("source_fe=%d\n", source_fe_count()))
  handle:write(string.format("active_map=%04X\n", active_base))
  handle:write(string.format("active_map_hash=%08X\n",
    hash_bytes(function(address)
      return raw_vram:read8(address - 0x8000)
    end, active_base, 0x400)))
  handle:close()
  os.exit(0)
end)
