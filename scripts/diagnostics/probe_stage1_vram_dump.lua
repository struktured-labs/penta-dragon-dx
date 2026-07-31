-- Dump the active Stage 1 character set and BG CRAM for screenshot-to-tile
-- attribution. This is diagnostic-only: it never writes game state other than
-- selecting VRAM bank 0 while reading, then restores the original VBK value.

local OUT = assert(os.getenv("STAGE1_VRAM_OUT"))
local frame = 0

local function write_range(path, first, last)
  local handle = assert(io.open(path, "wb"))
  local chunk = {}
  for address = first, last do
    chunk[#chunk + 1] = string.char(emu:read8(address))
    if #chunk == 256 then
      handle:write(table.concat(chunk))
      chunk = {}
    end
  end
  if #chunk > 0 then handle:write(table.concat(chunk)) end
  handle:close()
end

local function palette_bytes()
  local accessor = emu.memory.cgbBgPalette
  if accessor then return accessor:readRange(0, 64) end

  local old_index = emu:read8(0xFF68)
  local result = {}
  for index = 0, 63 do
    emu:write8(0xFF68, index)
    result[#result + 1] = string.char(emu:read8(0xFF69))
  end
  emu:write8(0xFF68, old_index)
  return table.concat(result)
end

callbacks:add("frame", function()
  frame = frame + 1
  emu:setKeys(0)
  if frame < 30 then return end

  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  write_range(OUT .. ".vram.bin", 0x8000, 0x97FF)
  emu:write8(0xFF4F, old_vbk)

  local cram = assert(io.open(OUT .. ".bgcram.bin", "wb"))
  cram:write(palette_bytes())
  cram:close()

  local metadata = assert(io.open(OUT .. ".txt", "w"))
  metadata:write(string.format("D880=%02X\n", emu:read8(0xD880)))
  metadata:write(string.format("FFC1=%02X\n", emu:read8(0xFFC1)))
  metadata:write(string.format("BGP=%02X\n", emu:read8(0xFF47)))
  metadata:close()
  emu:screenshot(OUT .. ".png")
  os.exit(0)
end)
