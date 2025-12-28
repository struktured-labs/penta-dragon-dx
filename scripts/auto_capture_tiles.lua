-- Auto capture tile IDs - runs for 5000 frames then exits
local frame_count = 0
local tile_usage = {}
local log_file = io.open("logs/tile_capture.log", "w")

function log(msg)
    log_file:write(msg .. "\n")
    log_file:flush()
end

log("Auto tile capture started")

function on_frame()
    frame_count = frame_count + 1

    -- Capture OAM every frame for first 5000 frames
    if frame_count <= 5000 then
        local oam_base = 0xFE00
        for i = 0, 39 do
            local addr = oam_base + (i * 4)
            local y = emu:read8(addr)
            local x = emu:read8(addr + 1)
            local tile = emu:read8(addr + 2)

            if y > 0 and y < 160 and x > 0 and x < 168 then
                tile_usage[tile] = (tile_usage[tile] or 0) + 1
            end
        end
    end

    -- Log progress every 1000 frames
    if frame_count % 1000 == 0 then
        log(string.format("Frame %d...", frame_count))
    end

    -- Final summary and exit at 5000 frames
    if frame_count == 5000 then
        log("\n=== TILE USAGE SUMMARY ===")

        -- All tiles sorted by ID
        local all_tiles = {}
        for tile, count in pairs(tile_usage) do
            table.insert(all_tiles, {tile=tile, count=count})
        end
        table.sort(all_tiles, function(a,b) return a.tile < b.tile end)

        for _, t in ipairs(all_tiles) do
            log(string.format("Tile %3d (0x%02X): %6d uses", t.tile, t.tile, t.count))
        end

        -- Group by 8-tile blocks for finer granularity
        log("\n=== 8-TILE BLOCK USAGE ===")
        for block = 0, 31 do
            local start_tile = block * 8
            local count = 0
            local tiles_used = {}
            for tile = start_tile, start_tile + 7 do
                if tile_usage[tile] then
                    count = count + tile_usage[tile]
                    table.insert(tiles_used, tile)
                end
            end
            if count > 0 then
                log(string.format("Block %2d (tiles %3d-%3d): %6d uses, tiles: %s",
                    block, start_tile, start_tile+7, count, table.concat(tiles_used, ",")))
            end
        end

        log("\nCapture complete!")
        log_file:close()

        -- Exit emulator
        emu:quit()
    end
end

callbacks:add("frame", on_frame)
