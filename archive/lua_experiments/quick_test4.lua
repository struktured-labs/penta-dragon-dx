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
        local visible = {}
        for i = 0, 5 do
            local base = 0xFE00 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            local pal = flags & 0x07

            if y > 0 and y < 160 and x > 0 and x < 168 then
                visible[#visible + 1] = "S" .. i .. ":t" .. string.format("%02X", tile) .. ",p" .. pal .. ",f" .. string.format("%02X", flags)
            end
        end

        if #visible > 0 then
            logFile:write("F" .. frameCount .. ": " .. table.concat(visible, " ") .. "\n")
            logFile:flush()
        end
    end

    if frameCount >= 10500 then
        logFile:write("Test complete\n")
        logFile:close()
        emu:stop()
    end
end)

logFile:write("Script loaded\n")
logFile:flush()
