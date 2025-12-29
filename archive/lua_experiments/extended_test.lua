-- Extended test to capture all monsters
local frameCount = 0
local logFile = io.open("tmp/mgba_test.log", "w")
logFile:write("Extended test started\n")
logFile:flush()

callbacks:add("frame", function()
    frameCount = frameCount + 1

    if frameCount == 1 then
        logFile:write("First frame\n")
        logFile:flush()
    end

    -- Extended range and more frequent logging
    if frameCount >= 7000 and frameCount <= 15000 and frameCount % 300 == 0 then
        local visible = {}
        for i = 0, 7 do  -- Check more sprites
            local base = 0xFE00 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            local pal = flags & 0x07

            if y > 0 and y < 160 and x > 0 and x < 168 then
                table.insert(visible, string.format("S%d:t%02X,p%d", i, tile, pal))
            end
        end

        if #visible > 0 then
            logFile:write(string.format("F%d: %s\n", frameCount, table.concat(visible, " ")))
            logFile:flush()
        end
    end

    if frameCount >= 15000 then
        logFile:write("Test complete at frame " .. frameCount .. "\n")
        logFile:close()
        emu:stop()
    end
end)

logFile:write("Script loaded\n")
logFile:flush()
