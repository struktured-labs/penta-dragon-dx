-- Read-only whole-WRAM trace for locating Ted's native publication phase.
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
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
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
