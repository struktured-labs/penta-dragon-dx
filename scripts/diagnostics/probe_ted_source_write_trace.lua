-- Trace every mutation of Ted's packed source from a fresh boss-dispatcher
-- fixture.  This is a differential diagnostic, not a release verifier.
local OUT = assert(os.getenv("TED_SOURCE_WRITE_OUT"))
local FRAMES = tonumber(os.getenv("TED_SOURCE_WRITE_FRAMES") or "360")
local SOURCE, LAST = 0xC1A0, 0xC3DF
local frame, events, finished = 0, 0, false
local log = assert(io.open(OUT .. ".log", "w"))
local snapshots = assert(io.open(OUT .. ".bin", "wb"))

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
    events = events + 1
    local sp = reg("SP") & 0xFFFF
    log:write(string.format(
        "event=%d frame=%d address=%04X offset=%03X old=%02X new=%02X scene=%02X bank=%02X pc=%04X sp=%04X stack=%s af=%04X hl=%04X de=%04X bc=%04X\n",
        events, frame, info.address & 0xFFFF,
        (info.address - SOURCE) & 0xFFFF, info.oldValue & 0xFF,
        info.newValue & 0xFF, emu:read8(0xD880), emu:read8(0xFF99),
        reg("PC") & 0xFFFF, sp, stack_words(sp, 6), reg("AF") & 0xFFFF,
        reg("HL") & 0xFFFF, reg("DE") & 0xFFFF, reg("BC") & 0xFFFF))
end, SOURCE, LAST, C.WATCHPOINT_TYPE.WRITE)

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    emu:setKeys(0)
    if emu:read8(0xD880) == 0x10 then
        emu:write8(0xDCBB, 0xF0)
        emu:write8(0xDCDC, 0xFF)
        emu:write8(0xDCDD, 0xFF)
        emu:write8(0xD888, 0)
        emu:write8(0xDD06, 0)
    end
    snapshots:write(string.char(
        emu:read8(0xD880), emu:read8(0xFF40),
        emu:read8(0xFF42), emu:read8(0xFF43)))
    for address = SOURCE, LAST do
        snapshots:write(string.char(emu:read8(address)))
    end
    if frame >= FRAMES then
        finished = true
        log:write(string.format("status=ok frames=%d events=%d\n", frame, events))
        log:close(); snapshots:close()
        local done = assert(io.open(OUT .. ".done", "w"))
        done:write("status=ok\n"); done:close(); os.exit(0)
    end
end)
