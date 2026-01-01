-- find_sara_form.lua
-- Find the game state variable that tracks Sara's current form (Witch vs Dragon)
-- Press SELECT to dump memory, then compare dumps between witch and dragon forms

local dump_count = 0
local previous_dump = nil

function dump_memory_for_diff()
    dump_count = dump_count + 1

    -- Focus on likely game state regions
    local regions = {
        {start = 0xC000, size = 256, name = "C000-C0FF"},
        {start = 0xC100, size = 256, name = "C100-C1FF"},
        {start = 0xC300, size = 256, name = "C300-C3FF"},
        {start = 0xC400, size = 256, name = "C400-C4FF"},
        {start = 0xC500, size = 256, name = "C500-C5FF"},
        {start = 0xD000, size = 256, name = "D000-D0FF"},
        {start = 0xD100, size = 256, name = "D100-D1FF"},
        {start = 0xD200, size = 256, name = "D200-D2FF"},
        {start = 0xFF80, size = 64, name = "HRAM"},
    }

    local current_dump = {}

    for _, region in ipairs(regions) do
        local data = {}
        for i = 0, region.size - 1 do
            data[i] = emu:read8(region.start + i)
        end
        current_dump[region.name] = {
            start = region.start,
            data = data
        }
    end

    -- Save to file
    local filename = "tmp/sara_form_dump_" .. dump_count .. ".txt"
    local f = io.open(filename, "w")
    if f then
        f:write("=== SARA FORM DUMP #" .. dump_count .. " ===\n")
        f:write("Instructions: Take dump as Witch, transform to Dragon, take another dump\n\n")

        for _, region in ipairs(regions) do
            f:write(string.format("=== %s ===\n", region.name))
            local data = current_dump[region.name].data
            for row = 0, (region.size - 1) // 16 do
                local addr = region.start + row * 16
                f:write(string.format("%04X: ", addr))
                for col = 0, 15 do
                    local idx = row * 16 + col
                    if idx < region.size then
                        f:write(string.format("%02X ", data[idx]))
                    end
                end
                f:write("\n")
            end
            f:write("\n")
        end
        f:close()
        console:log("Saved dump #" .. dump_count .. " to " .. filename)
    end

    -- Compare with previous dump
    if previous_dump then
        console:log("")
        console:log("=== DIFFERENCES FROM PREVIOUS DUMP ===")
        console:log("(Looking for Sara form variable)")
        console:log("")

        local differences = {}

        for _, region in ipairs(regions) do
            local prev = previous_dump[region.name]
            local curr = current_dump[region.name]

            if prev and curr then
                for i = 0, #curr.data do
                    if prev.data[i] ~= curr.data[i] then
                        local addr = curr.start + i
                        table.insert(differences, {
                            addr = addr,
                            prev = prev.data[i],
                            curr = curr.data[i]
                        })
                    end
                end
            end
        end

        console:log(string.format("Found %d differences", #differences))

        -- Show likely candidates (single byte changes, not animation-related)
        console:log("")
        console:log("Likely form flag candidates:")
        for _, diff in ipairs(differences) do
            -- Look for 0->1 or 1->0 changes (likely flags)
            if (diff.prev == 0 and diff.curr ~= 0) or
               (diff.prev ~= 0 and diff.curr == 0) or
               (diff.prev == 1 and diff.curr == 0) or
               (diff.prev == 0 and diff.curr == 1) then
                console:log(string.format("  0x%04X: %02X -> %02X  ***LIKELY***",
                    diff.addr, diff.prev, diff.curr))
            end
        end

        console:log("")
        console:log("All differences:")
        for i, diff in ipairs(differences) do
            if i <= 30 then  -- Limit output
                console:log(string.format("  0x%04X: %02X -> %02X",
                    diff.addr, diff.prev, diff.curr))
            end
        end
        if #differences > 30 then
            console:log(string.format("  ... and %d more", #differences - 30))
        end
    else
        console:log("First dump saved. Transform Sara and press SELECT again to compare.")
    end

    previous_dump = current_dump
end

-- Also check for specific sprite tile changes
function analyze_sara_sprites()
    console:log("=== SARA SPRITE ANALYSIS ===")

    -- Sara uses slots 0-3
    for slot = 0, 3 do
        local base = 0xFE00 + slot * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local flags = emu:read8(base + 3)

        console:log(string.format("Slot %d: Y=%d X=%d Tile=0x%02X Flags=0x%02X",
            slot, y, x, tile, flags))
    end

    -- Witch tiles are typically different from Dragon tiles
    -- This can help confirm the form even without the flag
    local tile0 = emu:read8(0xFE02)
    if tile0 >= 0x20 and tile0 < 0x40 then
        console:log("Sara appears to be in WITCH form (tiles 0x20-0x3F)")
    elseif tile0 >= 0x40 and tile0 < 0x60 then
        console:log("Sara appears to be in DRAGON form (tiles 0x40-0x5F)")
    else
        console:log("Sara form unclear (tile " .. string.format("0x%02X", tile0) .. ")")
    end
end

-- Register callback
local select_pressed = false

callbacks:add("keysRead", function()
    local keys = emu:getKeys()
    local select_down = (keys & 0x04) ~= 0

    if select_down and not select_pressed then
        select_pressed = true
        dump_memory_for_diff()
        analyze_sara_sprites()
    elseif not select_down then
        select_pressed = false
    end
end)

console:log("Sara form finder loaded.")
console:log("  SELECT: Dump memory for comparison")
console:log("")
console:log("Instructions:")
console:log("  1. Start as Witch, press SELECT to dump")
console:log("  2. Transform to Dragon, press SELECT again")
console:log("  3. Look for addresses that changed from 0->1 or similar")
console:log("")
analyze_sara_sprites()
