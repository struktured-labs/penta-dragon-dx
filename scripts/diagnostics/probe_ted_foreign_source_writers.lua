-- Identify writers placing non-native tile IDs in Ted's C1A0 packed plane.
local OUT = assert(os.getenv("TED_FOREIGN_WRITERS_OUT"))
local FRAMES = tonumber(os.getenv("TED_FOREIGN_WRITERS_FRAMES") or "600")
local WAIT_SCENE = os.getenv("TED_FOREIGN_WRITERS_WAIT_SCENE") == "1"
local SOURCE, LAST, SCENE = 0xC1A0, 0xC3E0, 0x10
local frame, total, events, finished, entered = 0, 0, 0, false, not WAIT_SCENE
local out = assert(io.open(OUT, "w"))

local function reg(name)
    local readers = {
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }
    for _, reader in ipairs(readers) do
        local ok, value = pcall(reader)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

local function stack_words(sp, count)
    local words = {}
    for index = 0, count - 1 do
        local address = (sp + index * 2) & 0xFFFF
        words[#words + 1] = string.format("%04X",
            emu:read8(address) | (emu:read8((address + 1) & 0xFFFF) << 8))
    end
    return table.concat(words, ",")
end

emu:setRangeWatchpoint(function(info)
    local value = info.newValue & 0xFF
    if value <= 0x86 or emu:read8(0xD880) ~= SCENE then return end
    events = events + 1
    if events <= 256 then
        local sp = reg("SP") & 0xFFFF
        local ret = emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8)
        out:write(string.format(
            "frame=%d address=%04X offset=%03X old=%02X new=%02X bank=%02X pc=%04X ret=%04X sp=%04X stack=%s af=%04X hl=%04X de=%04X bc=%04X\n",
            frame, info.address & 0xFFFF, (info.address - SOURCE) & 0xFFFF,
            info.oldValue & 0xFF, value, emu:read8(0xFF99), reg("PC") & 0xFFFF,
            ret, sp, stack_words(sp, 6), reg("AF") & 0xFFFF,
            reg("HL") & 0xFFFF, reg("DE") & 0xFFFF, reg("BC") & 0xFFFF))
        out:flush()
    end
end, SOURCE, LAST, C.WATCHPOINT_TYPE.WRITE_CHANGE)

callbacks:add("frame", function()
    if finished then return end
    total = total + 1
    if WAIT_SCENE then frame = total end
    emu:setKeys(0)
    emu:write8(0xDCBB, 0xF0); emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF); emu:write8(0xD888, 0); emu:write8(0xDD06, 0)
    if WAIT_SCENE then
        if emu:read8(0xD880) == SCENE then
            if not entered then
                entered = true
                out:write(string.format("entered_scene total_frame=%d pc=%04X\n",
                    total, reg("PC") & 0xFFFF))
                out:flush()
            end
        end
        if total >= FRAMES then
            finished = true
            out:write(string.format("status=%s frames=%d events=%d\n",
                entered and "ok" or "never-entered", total, events))
            out:close(); local done = assert(io.open(OUT .. ".done", "w"))
            done:write("status=ok\n"); done:close(); os.exit(entered and 0 or 1)
        end
        return
    end
    frame = frame + 1
    if emu:read8(0xD880) ~= SCENE or frame >= FRAMES then
        finished = true
        out:write(string.format("status=%s frames=%d events=%d\n",
            emu:read8(0xD880) == SCENE and "ok" or "wrong-scene", frame, events))
        out:close(); local done = assert(io.open(OUT .. ".done", "w"))
        done:write("status=ok\n"); done:close(); os.exit(0)
    end
end)
