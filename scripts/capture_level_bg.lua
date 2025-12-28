-- Capture BG tiles during actual gameplay (skip intro)
-- Waits 8000 frames (~2 min) before capturing

local log = io.open("tmp/level_bg_tiles.log", "w")
log:write("Level BG Tile Capture (skipping intro)\n\n")
log:flush()

local frame = 0
local captures = 0
local max_captures = 30
local start_frame = 8000  -- Skip intro (~2 minutes at 60fps)

callbacks:add("frame", function()
    frame = frame + 1

    if frame >= start_frame and frame % 100 == 0 and captures < max_captures then
        captures = captures + 1

        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)
        local lcdc = emu:read8(0xFF40)

        log:write(string.format("=== Capture %d (frame %d) ===\n", captures, frame))
        log:write(string.format("SCX=%d, SCY=%d, LCDC=0x%02X\n", scx, scy, lcdc))

        -- Check which BG map is in use (LCDC bit 3)
        local bg_map_base = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800
        log:write(string.format("BG Map: 0x%04X\n", bg_map_base))

        -- Screenshot
        emu:screenshot("tmp/lvl_bg_" .. captures .. ".png")

        -- Calculate visible region
        local start_col = math.floor(scx / 8)
        local start_row = math.floor(scy / 8)

        -- Dump visible tiles
        log:write("Visible tiles:\n")
        local unique_tiles = {}
        for row = 0, 17 do
            local line = ""
            for col = 0, 19 do
                local map_col = (start_col + col) % 32
                local map_row = (start_row + row) % 32
                local addr = bg_map_base + map_row * 32 + map_col
                local tile = emu:read8(addr)
                line = line .. string.format("%02X ", tile)
                unique_tiles[tile] = (unique_tiles[tile] or 0) + 1
            end
            log:write(string.format("R%02d: %s\n", row, line))
        end

        -- List unique non-zero tiles
        log:write("Unique non-zero tiles: ")
        for tile, _ in pairs(unique_tiles) do
            if tile ~= 0 then
                log:write(string.format("%02X ", tile))
            end
        end
        log:write("\n\n")
        log:flush()
    end

    if captures >= max_captures then
        log:write("Done!\n")
        log:close()
        emu:stop()
    end
end)

print("Waiting for gameplay... (8000 frames)")
