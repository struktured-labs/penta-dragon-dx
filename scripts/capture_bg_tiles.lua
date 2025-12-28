-- Capture BG tile IDs at current scroll position
-- Run when hazard is on screen, press SELECT to capture

local log = io.open("tmp/bg_tiles.log", "w")
log:write("BG Tile Capture\n")
log:write("Press SELECT when hazard is visible\n\n")

callbacks:add("keysRead", function()
    local keys = emu:getKeys()
    if keys.select then
        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)
        log:write(string.format("SCX=%d, SCY=%d\n", scx, scy))

        -- Calculate visible tilemap region
        local start_col = math.floor(scx / 8)
        local start_row = math.floor(scy / 8)

        log:write(string.format("Visible starts at col=%d, row=%d\n\n", start_col, start_row))

        -- Dump visible 20x18 area of tilemap
        log:write("Visible BG tiles (20x18):\n")
        for row = 0, 17 do
            local line = ""
            for col = 0, 19 do
                local map_col = (start_col + col) % 32
                local map_row = (start_row + row) % 32
                local addr = 0x9800 + map_row * 32 + map_col
                local tile = emu:read8(addr)
                line = line .. string.format("%02X ", tile)
            end
            log:write(string.format("Row %2d: %s\n", row, line))
        end

        log:write("\nCapture complete!\n")
        log:flush()
        print("BG tiles captured to tmp/bg_tiles.log")
    end
end)

print("Press SELECT when hazard is on screen")
