-- Debug OAM writes at specific frame
local frameCount = 0
local targetFrame = 9000
local logFile = io.open("tmp/debug_oam.log", "w")
logFile:write("Debug started\n")

callbacks:add("frame", function()
    frameCount = frameCount + 1

    -- Log every 500 frames during demo
    if frameCount >= 8500 and frameCount <= 10000 and frameCount % 500 == 0 then
        logFile:write(string.format("\n=== Frame %d ===\n", frameCount))

        -- Read all 40 sprites
        for i = 0, 3 do
            local base = 0xFE00 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            logFile:write(string.format("S%d: Y=%d X=%d T=0x%02X F=0x%02X (pal=%d)\n",
                i, y, x, tile, flags, flags & 0x07))
        end

        -- Also check shadow OAM at 0xC000
        logFile:write("\nShadow OAM (0xC000):\n")
        for i = 0, 3 do
            local base = 0xC000 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            logFile:write(string.format("S%d: Y=%d X=%d T=0x%02X F=0x%02X (pal=%d)\n",
                i, y, x, tile, flags, flags & 0x07))
        end

        -- Also check 0xC100 (alternate shadow buffer)
        logFile:write("\nAlt Shadow OAM (0xC100):\n")
        for i = 0, 3 do
            local base = 0xC100 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            logFile:write(string.format("S%d: Y=%d X=%d T=0x%02X F=0x%02X (pal=%d)\n",
                i, y, x, tile, flags, flags & 0x07))
        end

        logFile:flush()
    end

    if frameCount >= 10000 then
        logFile:write("\nDebug complete\n")
        logFile:close()
        emu:stop()
    end
end)
