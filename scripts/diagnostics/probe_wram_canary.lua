-- Report writes to a candidate WRAM execution range without changing it.
local OUT = assert(os.getenv("WRAM_CANARY_OUT"))
local FIRST = tonumber(os.getenv("WRAM_CANARY_FIRST") or "0xC500")
local LAST = tonumber(os.getenv("WRAM_CANARY_LAST") or "0xC5FF")
local FRAMES = tonumber(os.getenv("WRAM_CANARY_FRAMES") or "600")
local frame, writes, done = 0, 0, false
local out = assert(io.open(OUT, "w"))
pcall(function()
    emu:setRangeWatchpoint(function(info)
        writes = writes + 1
        if writes <= 64 then
            out:write(string.format("frame=%d address=%04X old=%02X new=%02X\n",
                frame, info.address & 0xFFFF, info.oldValue & 0xFF,
                info.newValue & 0xFF))
            out:flush()
        end
    end, FIRST, LAST, C.WATCHPOINT_TYPE.WRITE_CHANGE)
end)
callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    emu:setKeys(0)
    if frame >= FRAMES then
        done = true
        out:write(string.format("status=ok frames=%d writes=%d\n", frame, writes))
        out:close()
        local done = assert(io.open(OUT .. ".done", "w"))
        done:write("status=ok\n"); done:close()
        if emu.stop then emu:stop() end
    end
end)
