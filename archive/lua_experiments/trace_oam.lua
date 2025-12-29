-- Trace OAM palette changes
local frameCount = 0
local lastPal = {}
local logFile = io.open("tmp/oam_trace.log", "w")

for i = 0, 39 do
    lastPal[i] = -1
end

logFile:write("OAM palette trace started\n")
logFile:flush()

callbacks:add("frame", function()
    frameCount = frameCount + 1

    -- Only trace during demo sequence
    if frameCount < 8500 or frameCount > 12000 then
        return
    end

    local changed = {}

    for i = 0, 39 do
        local base = 0xFE00 + (i * 4)
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local flags = emu:read8(base + 3)
        local pal = flags & 0x07

        -- Check if visible
        if y > 0 and y < 160 and x > 0 and x < 168 then
            if lastPal[i] ~= pal then
                table.insert(changed, string.format("S%d:%d→%d(t%02X)", i, lastPal[i], pal, tile))
                lastPal[i] = pal
            end
        else
            lastPal[i] = -1
        end
    end

    if #changed > 0 then
        logFile:write(string.format("F%d: %s\n", frameCount, table.concat(changed, " ")))
        logFile:flush()
    end

    if frameCount >= 12000 then
        logFile:write("Trace complete\n")
        logFile:close()
        emu:stop()
    end
end)
