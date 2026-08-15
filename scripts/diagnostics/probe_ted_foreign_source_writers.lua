-- Identify writers placing non-native tile IDs in Ted's C1A0 packed plane.
local OUT = assert(os.getenv("TED_FOREIGN_WRITERS_OUT"))
local FRAMES = tonumber(os.getenv("TED_FOREIGN_WRITERS_FRAMES") or "600")
local SOURCE, LAST, SCENE = 0xC1A0, 0xC3E0, 0x10
local frame, events, finished = 0, 0, false
local out = assert(io.open(OUT, "w"))

local function reg(name)
    local ok, value = pcall(function() return emu:getRegister(name) end)
    return ok and value or 0xFFFF
end

assert(emu:setRangeWatchpoint(function(info)
    local value = info.newValue & 0xFF
    if value <= 0x86 or emu:read8(0xD880) ~= SCENE then return end
    events = events + 1
    if events <= 256 then
        local sp = reg("SP") & 0xFFFF
        local ret = emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8)
        out:write(string.format(
            "frame=%d address=%04X offset=%03X old=%02X new=%02X bank=%02X pc=%04X ret=%04X hl=%04X de=%04X bc=%04X\n",
            frame, info.address & 0xFFFF, (info.address - SOURCE) & 0xFFFF,
            info.oldValue & 0xFF, value, emu:read8(0xFF99), reg("PC") & 0xFFFF,
            ret, reg("HL") & 0xFFFF, reg("DE") & 0xFFFF, reg("BC") & 0xFFFF))
        out:flush()
    end
end, SOURCE, LAST, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1; emu:setKeys(0)
    emu:write8(0xDCBB, 0xF0); emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF); emu:write8(0xD888, 0); emu:write8(0xDD06, 0)
    if emu:read8(0xD880) ~= SCENE or frame >= FRAMES then
        finished = true
        out:write(string.format("status=%s frames=%d events=%d\n",
            emu:read8(0xD880) == SCENE and "ok" or "wrong-scene", frame, events))
        out:close(); local done = assert(io.open(OUT .. ".done", "w"))
        done:write("status=ok\n"); done:close(); os.exit(0)
    end
end)
