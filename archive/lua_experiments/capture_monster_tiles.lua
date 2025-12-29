-- Monster Tile Capture v4 - writes to tmp/
local frameCount = 0
local captureCount = 0
local logFile = io.open("tmp/monster_tiles.log", "w")
logFile:write("=== MONSTER TILE CAPTURE ===\n")
logFile:flush()

callbacks:add("frame", function()
    frameCount = frameCount + 1

    -- Capture every 300 frames (~5 sec)
    if frameCount % 300 == 0 then
        captureCount = captureCount + 1

        -- Screenshot
        emu:screenshot("tmp/cap_" .. captureCount .. ".png")

        local sprites = {}
        for i = 0, 39 do
            local base = 0xC000 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)

            if y > 0 and y < 160 then
                table.insert(sprites, string.format("%02X", tile))
            end
        end

        logFile:write(string.format("CAP%d F%d: %s\n", captureCount, frameCount, table.concat(sprites, " ")))
        logFile:flush()
    end

    -- Quit after 30 captures
    if captureCount >= 30 then
        logFile:write("=== DONE ===\n")
        logFile:close()
        emu:stop()
    end
end)

logFile:write("Script started\n")
logFile:flush()
