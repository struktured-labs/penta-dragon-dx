-- analyze_entity_data.lua
-- Reverse engineer entity data structure at 0xC200+
-- Press SELECT to dump entity data with analysis
-- Press START to show current entity type summary

local dump_count = 0

-- Known entity types (to be discovered)
local entity_names = {
    [0x17] = "RegularEnemy?",
    [0x1D] = "Miniboss?",
    [0x1E] = "Unknown1E",
    [0x1F] = "Unknown1F",
}

function analyze_entity_region()
    console:log("=== ENTITY DATA ANALYSIS ===")
    console:log("")

    -- Scan for FE FE FE patterns (entity markers)
    local entities = {}
    local addr = 0xC200

    while addr < 0xC300 do
        local b1 = emu:read8(addr)
        local b2 = emu:read8(addr + 1)
        local b3 = emu:read8(addr + 2)
        local b4 = emu:read8(addr + 3)

        -- Check for FE marker patterns
        if b1 == 0xFE and b2 == 0xFE and b3 == 0xFE then
            -- Found entity marker, b4 is likely entity type
            local entity_type = b4
            local name = entity_names[entity_type] or "Unknown"

            table.insert(entities, {
                addr = addr,
                type = entity_type,
                name = name,
                raw = {b1, b2, b3, b4,
                       emu:read8(addr+4), emu:read8(addr+5),
                       emu:read8(addr+6), emu:read8(addr+7)}
            })

            console:log(string.format("Entity @ 0x%04X: Type=0x%02X (%s)",
                addr, entity_type, name))
            console:log(string.format("  Raw: %02X %02X %02X [%02X] %02X %02X %02X %02X",
                b1, b2, b3, b4,
                emu:read8(addr+4), emu:read8(addr+5),
                emu:read8(addr+6), emu:read8(addr+7)))

            addr = addr + 24  -- Assume 24-byte entity structures
        else
            addr = addr + 1
        end
    end

    console:log("")
    console:log(string.format("Found %d entities with FE FE FE marker", #entities))

    return entities
end

function dump_entity_data()
    dump_count = dump_count + 1
    local filename = "tmp/entity_dump_" .. dump_count .. ".txt"

    local f = io.open(filename, "w")
    if not f then
        console:log("Failed to open " .. filename)
        return
    end

    f:write("=== ENTITY DATA DUMP #" .. dump_count .. " ===\n\n")

    -- Dump OAM for correlation
    f:write("=== OAM SLOTS (for correlation) ===\n")
    for slot = 0, 19 do  -- Focus on first 20 slots
        local base = 0xFE00 + slot * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local flags = emu:read8(base + 3)
        if y ~= 0 and y < 160 then  -- Visible sprite
            f:write(string.format("Slot %2d: Y=%3d X=%3d Tile=0x%02X Flags=0x%02X\n",
                slot, y, x, tile, flags))
        end
    end

    -- Dump raw entity region
    f:write("\n=== RAW ENTITY DATA (0xC200-0xC2FF) ===\n")
    for row = 0, 15 do
        local addr = 0xC200 + row * 16
        f:write(string.format("%04X: ", addr))
        for col = 0, 15 do
            f:write(string.format("%02X ", emu:read8(addr + col)))
        end
        f:write("\n")
    end

    -- Analyze structure
    f:write("\n=== ENTITY STRUCTURE ANALYSIS ===\n")

    local addr = 0xC200
    local entity_num = 0
    while addr < 0xC300 do
        local b1 = emu:read8(addr)
        local b2 = emu:read8(addr + 1)
        local b3 = emu:read8(addr + 2)
        local b4 = emu:read8(addr + 3)

        if b1 == 0xFE and b2 == 0xFE and b3 == 0xFE then
            entity_num = entity_num + 1
            local entity_type = b4
            local name = entity_names[entity_type] or "Unknown"

            f:write(string.format("\nEntity #%d @ 0x%04X\n", entity_num, addr))
            f:write(string.format("  Type: 0x%02X (%s)\n", entity_type, name))
            f:write("  Structure (24 bytes):\n")
            f:write("    ")
            for i = 0, 23 do
                f:write(string.format("%02X ", emu:read8(addr + i)))
                if i == 7 or i == 15 then f:write("\n    ") end
            end
            f:write("\n")

            addr = addr + 24
        else
            addr = addr + 1
        end
    end

    -- Dump boss flag
    local boss_flag = emu:read8(0xFFBF)
    f:write(string.format("\n=== GAME STATE FLAGS ===\n"))
    f:write(string.format("Boss Flag (0xFFBF): 0x%02X (%s)\n",
        boss_flag, boss_flag ~= 0 and "BOSS PRESENT" or "No boss"))

    f:close()
    console:log("Dumped entity data to " .. filename)

    -- Also show analysis in console
    analyze_entity_region()
end

function show_entity_summary()
    console:log("=== CURRENT ENTITY SUMMARY ===")

    local type_counts = {}
    local addr = 0xC200

    while addr < 0xC300 do
        local b1 = emu:read8(addr)
        local b2 = emu:read8(addr + 1)
        local b3 = emu:read8(addr + 2)
        local b4 = emu:read8(addr + 3)

        if b1 == 0xFE and b2 == 0xFE and b3 == 0xFE then
            local entity_type = b4
            type_counts[entity_type] = (type_counts[entity_type] or 0) + 1
            addr = addr + 24
        else
            addr = addr + 1
        end
    end

    for type_id, count in pairs(type_counts) do
        local name = entity_names[type_id] or "Unknown"
        console:log(string.format("  Type 0x%02X (%s): %d entities", type_id, name, count))
    end

    local boss = emu:read8(0xFFBF)
    console:log(string.format("  Boss flag: 0x%02X", boss))
end

-- Register callbacks for SELECT and START buttons
local select_pressed = false
local start_pressed = false

callbacks:add("keysRead", function()
    local keys = emu:getKeys()
    local select_down = (keys & 0x04) ~= 0  -- SELECT is bit 2
    local start_down = (keys & 0x08) ~= 0   -- START is bit 3

    if select_down and not select_pressed then
        select_pressed = true
        dump_entity_data()
    elseif not select_down then
        select_pressed = false
    end

    if start_down and not start_pressed then
        start_pressed = true
        show_entity_summary()
    elseif not start_down then
        start_pressed = false
    end
end)

console:log("Entity analyzer loaded.")
console:log("  SELECT: Dump entity data to file")
console:log("  START: Show entity type summary")
console:log("")
console:log("Initial analysis:")
analyze_entity_region()
