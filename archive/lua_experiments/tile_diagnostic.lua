-- Tile diagnostic: captures tilemap and highlights tiles in 0x60-0x7F range
-- Run this when hazard is visible, press START to capture

print("=== TILE DIAGNOSTIC ===")
print("Navigate to hazard, press START to capture")

local captured = false
local frame = 0
local last_start = false

callbacks:add("frame", function()
    if captured then return end
    frame = frame + 1

    -- Check START button (read joypad)
    -- P1 register at 0xFF00: write 0x20 to read buttons, 0x10 to read d-pad
    emu:write8(0xFF00, 0x20)  -- Select button keys
    local buttons = emu:read8(0xFF00)
    local start_pressed = (buttons & 0x08) == 0  -- START is bit 3, active low

    -- Detect rising edge of START
    if start_pressed and not last_start then
        captured = true

        local log = io.open("tmp/tile_diagnostic.log", "w")
        local scx = emu:read8(0xFF43)
        local scy = emu:read8(0xFF42)
        local lcdc = emu:read8(0xFF40)

        -- Determine tilemap base
        local bg_map = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800

        log:write("=== TILE DIAGNOSTIC ===\n")
        log:write(string.format("Frame: %d\n", frame))
        log:write(string.format("SCX=%d, SCY=%d, LCDC=0x%02X\n", scx, scy, lcdc))
        log:write(string.format("BG Map: 0x%04X\n\n", bg_map))

        -- Screenshot
        emu:screenshot("tmp/tile_diagnostic.png")

        -- Calculate visible region
        local start_col = math.floor(scx / 8)
        local start_row = math.floor(scy / 8)

        log:write("Visible tiles (20x18) - tiles in [0x60-0x7F] marked with *:\n\n")

        local hazard_tiles = {}
        local other_tiles = {}

        for row = 0, 17 do
            local line = string.format("R%02d: ", row)
            for col = 0, 19 do
                local map_col = (start_col + col) % 32
                local map_row = (start_row + row) % 32
                local addr = bg_map + map_row * 32 + map_col
                local tile = emu:read8(addr)

                if tile >= 0x60 and tile <= 0x7F then
                    line = line .. string.format("*%02X ", tile)
                    hazard_tiles[tile] = (hazard_tiles[tile] or 0) + 1
                else
                    line = line .. string.format(" %02X ", tile)
                    other_tiles[tile] = (other_tiles[tile] or 0) + 1
                end
            end
            log:write(line .. "\n")
        end

        log:write("\n=== TILES IN TARGET RANGE (0x60-0x7F) ===\n")
        local sorted_hazard = {}
        for tile, count in pairs(hazard_tiles) do
            table.insert(sorted_hazard, {tile=tile, count=count})
        end
        table.sort(sorted_hazard, function(a,b) return a.tile < b.tile end)
        for _, item in ipairs(sorted_hazard) do
            log:write(string.format("  0x%02X: %d occurrences\n", item.tile, item.count))
        end

        log:write("\n=== OTHER COMMON TILES ===\n")
        local sorted_other = {}
        for tile, count in pairs(other_tiles) do
            table.insert(sorted_other, {tile=tile, count=count})
        end
        table.sort(sorted_other, function(a,b) return a.count > b.count end)
        for i, item in ipairs(sorted_other) do
            if i <= 15 then
                log:write(string.format("  0x%02X: %d occurrences\n", item.tile, item.count))
            end
        end

        log:write("\nCapture complete!\n")
        log:close()

        print("")
        print("=== CAPTURED! ===")
        print("Check tmp/tile_diagnostic.log")
        print("Check tmp/tile_diagnostic.png")
    end

    last_start = start_pressed

    -- Progress every 5 seconds
    if frame % 300 == 0 then
        print("Waiting for START button... (frame " .. frame .. ")")
    end
end)
