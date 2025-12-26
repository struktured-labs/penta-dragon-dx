-- Quick test script - shows both OAM and shadow OAM
local frameCount = 0
local logFile = io.open("tmp/mgba_test.log", "w")
logFile:write("Test started\n")
logFile:flush()

callbacks:add("frame", function()
    frameCount = frameCount + 1

    if frameCount == 1 then
        logFile:write("First frame\n")
        logFile:flush()
    end

    if frameCount >= 8500 and frameCount % 500 == 0 then
        local oam = {}
        local shadow = {}

        for i = 0, 3 do
            local base = 0xFE00 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            local pal = flags & 0x07

            if y > 0 and y < 160 and x > 0 and x < 168 then
                table.insert(oam, string.format("S%d:t%02X,p%d,f%02X", i, tile, pal, flags))
            end

            -- Shadow at 0xC000
            local sbase = 0xC000 + (i * 4)
            local sy = emu:read8(sbase)
            local sx = emu:read8(sbase + 1)
            local stile = emu:read8(sbase + 2)
            local sflags = emu:read8(sbase + 3)
            local spal = sflags & 0x07

            if sy > 0 and sy < 160 and sx > 0 and sx < 168 then
                table.insert(shadow, string.format("s%d:t%02X,p%d,f%02X", i, stile, spal, sflags))
            end
        end

        if #oam > 0 then
            logFile:write(string.format("F%d OAM: %s\n", frameCount, table.concat(oam, " ")))
            logFile:write(string.format("F%d SHD: %s\n", frameCount, table.concat(shadow, " ")))
            logFile:flush()
        end
    end

    if frameCount >= 10500 then
        logFile:write("Test complete at frame " .. frameCount .. "\n")
        logFile:close()
        emu:stop()
    end
end)

logFile:write("Script loaded\n")
logFile:flush()
