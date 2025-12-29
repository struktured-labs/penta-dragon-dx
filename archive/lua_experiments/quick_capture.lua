-- Quick capture - every 200 frames for 60 captures
local frame = 0
local captures = 0
local log = io.open("tmp/quick_capture.log", "w")
log:write("Quick capture started\n")
log:flush()

callbacks:add("frame", function()
    frame = frame + 1
    if frame % 200 == 0 and captures < 60 then
        captures = captures + 1
        emu:screenshot("tmp/qc_" .. captures .. ".png")

        local tiles = {}
        for i = 0, 39 do
            local y = emu:read8(0xC000 + i*4)
            local tile = emu:read8(0xC000 + i*4 + 2)
            if y > 0 and y < 160 then
                table.insert(tiles, string.format("%02X", tile))
            end
        end
        log:write("C" .. captures .. ": " .. table.concat(tiles, " ") .. "\n")
        log:flush()
    end
    if captures >= 60 then
        log:write("Done\n")
        log:close()
        emu:stop()
    end
end)
