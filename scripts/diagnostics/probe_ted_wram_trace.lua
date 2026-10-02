-- Read-only whole-WRAM trace for locating Ted's native publication phase.
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
local OUT = assert(os.getenv("TED_WRAM_TRACE_OUT"))
local FRAMES = tonumber(os.getenv("TED_WRAM_TRACE_FRAMES") or "240")
local out = assert(io.open(OUT, "wb"))
local frame = 0
local function byte(v) return string.char(v & 0xFF) end
callbacks:add("frame", function()
    frame = frame + 1
    out:write(byte(emu:read8(0xFF40)))
    out:write(byte(emu:read8(0xFF42)))
    out:write(byte(emu:read8(0xFF43)))
    for address=0xC000,0xDFFF do out:write(byte(emu:read8(address))) end
    emu:setKeys(0)
    native_assistance.write(0xDCBB, 0xF0)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
    if frame >= FRAMES then
        out:close()
        local marker = assert(io.open(OUT .. ".done", "w"))
        marker:write("done\n")
        marker:close()
        emu:stop()
    end
end)
