-- Capture mini-boss sprite tile IDs
-- Press SELECT when mini-boss is on screen to capture OAM
-- Sara uses tiles 0x00-0x3F and 0xE0-0xFF, so anything else is the mini-boss

print("=== MINI-BOSS TILE CAPTURE ===")
print("Press SELECT when mini-boss is visible")
print("Sara tiles: 0x00-0x3F, 0xE0-0xFF")
print("Mini-boss tiles: everything else")
print("")

local capture_count = 0

local function is_sara_tile(tile)
    return (tile >= 0x00 and tile <= 0x3F) or (tile >= 0xE0 and tile <= 0xFF)
end

local function capture_sprites()
    capture_count = capture_count + 1
    local filename = string.format("tmp/miniboss_tiles_%d.log", capture_count)
    local log = io.open(filename, "w")

    log:write(string.format("=== MINI-BOSS TILE CAPTURE #%d ===\n\n", capture_count))

    -- Screenshot
    local screenshot = string.format("tmp/miniboss_%d.png", capture_count)
    emu:screenshot(screenshot)
    log:write(string.format("Screenshot: %s\n\n", screenshot))

    local sara_sprites = {}
    local miniboss_sprites = {}
    local other_sprites = {}

    -- Scan OAM
    for slot = 0, 39 do
        local base = 0xFE00 + slot * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local flags = emu:read8(base + 3)

        if y > 0 and y < 160 and x > 0 then  -- Visible sprite
            local sprite = {slot=slot, y=y, x=x, tile=tile, flags=flags}
            if is_sara_tile(tile) then
                table.insert(sara_sprites, sprite)
            else
                table.insert(miniboss_sprites, sprite)
            end
        end
    end

    log:write("=== SARA SPRITES ===\n")
    for _, s in ipairs(sara_sprites) do
        log:write(string.format("  Slot %2d: Y=%3d X=%3d Tile=0x%02X Flags=0x%02X\n",
            s.slot, s.y, s.x, s.tile, s.flags))
    end

    log:write(string.format("\n=== MINI-BOSS SPRITES (%d found) ===\n", #miniboss_sprites))
    local miniboss_tiles = {}
    for _, s in ipairs(miniboss_sprites) do
        log:write(string.format("  Slot %2d: Y=%3d X=%3d Tile=0x%02X Flags=0x%02X\n",
            s.slot, s.y, s.x, s.tile, s.flags))
        miniboss_tiles[s.tile] = (miniboss_tiles[s.tile] or 0) + 1
    end

    log:write("\n=== UNIQUE MINI-BOSS TILE IDS ===\n")
    local sorted_tiles = {}
    for tile, count in pairs(miniboss_tiles) do
        table.insert(sorted_tiles, {tile=tile, count=count})
    end
    table.sort(sorted_tiles, function(a,b) return a.tile < b.tile end)

    local min_tile, max_tile = 255, 0
    for _, t in ipairs(sorted_tiles) do
        log:write(string.format("  0x%02X: %d sprites\n", t.tile, t.count))
        if t.tile < min_tile then min_tile = t.tile end
        if t.tile > max_tile then max_tile = t.tile end
    end

    if #sorted_tiles > 0 then
        log:write(string.format("\nTile range: 0x%02X - 0x%02X\n", min_tile, max_tile))
    end

    log:write("\nCapture complete!\n")
    log:close()

    print(string.format("Capture #%d saved to %s", capture_count, filename))
    if #sorted_tiles > 0 then
        print(string.format("Mini-boss tiles: 0x%02X - 0x%02X (%d unique)", min_tile, max_tile, #sorted_tiles))
    end
end

local last_select = false

callbacks:add("frame", function()
    emu:write8(0xFF00, 0x20)
    local buttons = emu:read8(0xFF00)
    local select_pressed = (buttons & 0x04) == 0

    if select_pressed and not last_select then
        capture_sprites()
    end

    last_select = select_pressed
end)
