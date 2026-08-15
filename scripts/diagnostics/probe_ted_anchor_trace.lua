-- Trace Ted's runtime anchor across native map handoffs.
local OUT = assert(os.getenv("TED_ANCHOR_OUT"))
local FRAMES = tonumber(os.getenv("TED_ANCHOR_FRAMES") or "360")
local out = assert(io.open(OUT, "w"))
local frame, done = 0, false

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    if frame == 1 and os.getenv("TED_ANCHOR_REINSTALL") == "1" then
        emu:write8(0xC5FF, 0)
    end
    emu:setKeys(0)
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
    out:write(string.format(
        "%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
        frame, emu:read8(0xD880), emu:read8(0xFF40),
        emu:read8(0xFF42), emu:read8(0xFF43),
        emu:read8(0xC4FA), emu:read8(0xC4FB),
        emu:read8(0xFFA9), emu:read8(0xDCE0), emu:read8(0xC5F7)))
    if frame >= FRAMES or emu:read8(0xD880) ~= 0x10 then
        done = true
        out:close()
        local marker = assert(io.open(OUT .. ".done", "w"))
        marker:write("done\n")
        marker:close()
        if emu.stop then emu:stop() end
    end
end)
