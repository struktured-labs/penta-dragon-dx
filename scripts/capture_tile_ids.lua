-- Tile ID capture script for mGBA
-- Logs which tile IDs are used by sprites over time
-- Run with: mgba-qt -l scripts/capture_tile_ids.lua rom.gb

local frame_count = 0
local tile_usage = {}  -- tile_id -> count
local sprite_tiles = {}  -- For tracking per-sprite tile patterns
local log_file = io.open("tile_capture.log", "w")

function log(msg)
    log_file:write(msg .. "\n")
    log_file:flush()
    console:log(msg)
end

log("Tile capture started")

function capture_oam()
    local oam_base = 0xFE00
    local active_sprites = {}

    for i = 0, 39 do
        local addr = oam_base + (i * 4)
        local y = emu:read8(addr)
        local x = emu:read8(addr + 1)
        local tile = emu:read8(addr + 2)
        local flags = emu:read8(addr + 3)

        -- Only count visible sprites
        if y > 0 and y < 160 and x > 0 and x < 168 then
            tile_usage[tile] = (tile_usage[tile] or 0) + 1
            table.insert(active_sprites, {y=y, x=x, tile=tile, flags=flags})
        end
    end

    return active_sprites
end

function on_frame()
    frame_count = frame_count + 1

    -- Capture every 100 frames
    if frame_count % 100 == 0 then
        local sprites = capture_oam()

        -- Log current frame sprites
        local msg = string.format("F%d: ", frame_count)
        for i, s in ipairs(sprites) do
            if i <= 8 then  -- First 8 sprites
                msg = msg .. string.format("t%02X ", s.tile)
            end
        end
        log(msg)
    end

    -- Every 2000 frames, dump tile usage summary
    if frame_count % 2000 == 0 then
        log("\n=== TILE USAGE SUMMARY (frame " .. frame_count .. ") ===")

        -- Sort tiles by usage
        local sorted = {}
        for tile, count in pairs(tile_usage) do
            table.insert(sorted, {tile=tile, count=count})
        end
        table.sort(sorted, function(a,b) return a.count > b.count end)

        -- Log top 32 most used tiles
        log("Top used tiles:")
        for i = 1, math.min(32, #sorted) do
            local t = sorted[i]
            log(string.format("  Tile 0x%02X (%3d): %d uses", t.tile, t.tile, t.count))
        end

        -- Group by ranges
        local ranges = {
            {0, 15, "0-15"},
            {16, 31, "16-31"},
            {32, 47, "32-47"},
            {48, 63, "48-63"},
            {64, 79, "64-79"},
            {80, 95, "80-95"},
            {96, 111, "96-111"},
            {112, 127, "112-127"},
        }

        log("\nUsage by 16-tile ranges:")
        for _, r in ipairs(ranges) do
            local count = 0
            for tile = r[1], r[2] do
                count = count + (tile_usage[tile] or 0)
            end
            if count > 0 then
                log(string.format("  %s: %d uses", r[3], count))
            end
        end
        log("")
    end

    -- Stop after 10000 frames
    if frame_count >= 10000 then
        log("\n=== FINAL SUMMARY ===")
        local sorted = {}
        for tile, count in pairs(tile_usage) do
            table.insert(sorted, {tile=tile, count=count})
        end
        table.sort(sorted, function(a,b) return a.tile < b.tile end)

        for _, t in ipairs(sorted) do
            log(string.format("Tile %3d (0x%02X): %d", t.tile, t.tile, t.count))
        end

        log_file:close()
        log("Capture complete - see tile_capture.log")
    end
end

callbacks:add("frame", on_frame)
log("Script loaded, capturing tile IDs...")
