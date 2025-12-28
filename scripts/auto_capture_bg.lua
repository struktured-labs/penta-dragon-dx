-- Auto capture BG tiles every 200 frames
-- Will capture tilemap data to find hazard tile IDs

local log = io.open("tmp/auto_bg_tiles.log", "w")
log:write("Auto BG Tile Capture\n\n")
log:flush()

local frame = 0
local captures = 0
local max_captures = 20

callbacks:add("frame", function()
    frame = frame + 1

    if frame % 200 == 0 and captures < max_captures then
        captures = captures + 1

        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)

        log:write(string.format("=== Capture %d (frame %d) ===\n", captures, frame))
        log:write(string.format("SCX=%d, SCY=%d\n", scx, scy))

        -- Screenshot for reference
        emu:screenshot("tmp/bg_cap_" .. captures .. ".png")

        -- Calculate visible tilemap region
        local start_col = math.floor(scx / 8)
        local start_row = math.floor(scy / 8)

        -- Dump visible area (20x18 tiles)
        log:write("Visible tiles (20 cols x 18 rows):\n")
        for row = 0, 17 do
            local line = ""
            for col = 0, 19 do
                local map_col = (start_col + col) % 32
                local map_row = (start_row + row) % 32
                local addr = 0x9800 + map_row * 32 + map_col
                local tile = emu:read8(addr)
                line = line .. string.format("%02X ", tile)
            end
            log:write(string.format("R%02d: %s\n", row, line))
        end
        log:write("\n")
        log:flush()
    end

    if captures >= max_captures then
        log:write("Done!\n")
        log:close()
        emu:stop()
    end
end)

print("Auto-capturing BG tiles...")
