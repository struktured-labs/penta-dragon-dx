-- Dump both Ted tilemaps/attribute maps at one deterministic frame.
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
local native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end
local OUT = assert(os.getenv("TED_VRAM_OUT"))
local TARGET = tonumber(os.getenv("TED_VRAM_FRAME") or "120")
local frame = 0

local function dump(path, address, length)
    local file = assert(io.open(path, "wb"))
    for offset = 0, length - 1 do
        file:write(string.char(emu:read8(address + offset)))
    end
    file:close()
end

callbacks:add("frame", function()
    frame = frame + 1
    emu:setKeys(0)
    native_assistance.write(0xDCBB, 0xF0)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
    if frame ~= TARGET then return end
    local vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    dump(OUT .. ".tiles.bin", 0x9800, 0x800)
    emu:write8(0xFF4F, 1)
    dump(OUT .. ".attrs.bin", 0x9800, 0x800)
    emu:write8(0xFF4F, vbk)
    local meta = assert(io.open(OUT .. ".meta", "w"))
    meta:write(string.format("scene=%02X lcdc=%02X scx=%02X scy=%02X\n",
        emu:read8(0xD880), emu:read8(0xFF40), emu:read8(0xFF43),
        emu:read8(0xFF42)))
    meta:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write("ok\n")
    done:close()
end)
