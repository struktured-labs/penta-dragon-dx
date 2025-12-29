-- Capture hazard tile IDs
-- Run this, navigate to the hazard room, press Select to capture

local captured = false
local output_dir = "test_output/hazard_tiles"

function dump_bg_tiles()
    console:log("=== CAPTURING BG TILE MAP ===")

    -- Screenshot first
    emu:screenshot(output_dir .. "/hazard_screenshot.png")
    console:log("Screenshot saved")

    -- Read BG tile map from VRAM (0x9800-0x9BFF for BG map 0)
    -- or 0x9C00-0x9FFF for BG map 1
    -- LCDC bit 3 determines which map is used

    local lcdc = emu:read8(0xFF40)
    local bg_map_base = (lcdc & 0x08) ~= 0 and 0x9C00 or 0x9800

    console:log("LCDC: " .. string.format("0x%02X", lcdc))
    console:log("BG Map base: " .. string.format("0x%04X", bg_map_base))

    -- Get scroll positions
    local scx = emu:read8(0xFF43)
    local scy = emu:read8(0xFF42)
    console:log("Scroll: SCX=" .. scx .. " SCY=" .. scy)

    -- Dump visible 20x18 tile area (160x144 pixels / 8 = 20x18 tiles)
    local tile_x_start = math.floor(scx / 8)
    local tile_y_start = math.floor(scy / 8)

    console:log("")
    console:log("Visible tiles (20x18 starting at " .. tile_x_start .. "," .. tile_y_start .. "):")
    console:log("")

    -- Collect unique tiles
    local unique_tiles = {}

    for row = 0, 17 do
        local line = ""
        for col = 0, 19 do
            local tx = (tile_x_start + col) % 32
            local ty = (tile_y_start + row) % 32
            local addr = bg_map_base + (ty * 32) + tx
            local tile_id = emu:read8(addr)
            line = line .. string.format("%02X ", tile_id)
            unique_tiles[tile_id] = (unique_tiles[tile_id] or 0) + 1
        end
        console:log(line)
    end

    console:log("")
    console:log("=== UNIQUE TILES USED ===")

    -- Sort and display unique tiles
    local sorted = {}
    for id, count in pairs(unique_tiles) do
        table.insert(sorted, {id = id, count = count})
    end
    table.sort(sorted, function(a, b) return a.id < b.id end)

    for _, item in ipairs(sorted) do
        console:log(string.format("Tile 0x%02X (%3d): used %d times", item.id, item.id, item.count))
    end

    console:log("")
    console:log("=== CAPTURE COMPLETE ===")
    console:log("Navigate to different areas and press Select again to compare")
end

function on_keysdown(keys)
    if keys["select"] and not captured then
        dump_bg_tiles()
    end
end

-- Also capture on frame 1500 automatically (about 25 seconds at 60fps)
local frame = 0
function on_frame()
    frame = frame + 1
    if frame == 1500 and not captured then
        console:log("Auto-capturing at frame 1500...")
        dump_bg_tiles()
    end
end

callbacks:add("keysRead", on_keysdown)
callbacks:add("frame", on_frame)

console:log("=== HAZARD TILE CAPTURE ===")
console:log("Press SELECT when viewing the hazard to capture tile IDs")
console:log("Or wait ~25 seconds for auto-capture")
console:log("Output: " .. output_dir)

-- Create output directory
os.execute("mkdir -p " .. output_dir)
