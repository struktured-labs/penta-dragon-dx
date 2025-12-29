-- dump_game_state.lua
-- Press SELECT to dump WRAM and HRAM to file for comparison
-- Run once with boss, kill boss, run again, then diff the files

local dump_count = 0

function dump_memory()
    dump_count = dump_count + 1
    local filename = "tmp/gamestate_" .. dump_count .. ".bin"
    local txtfile = "tmp/gamestate_" .. dump_count .. ".txt"

    -- Open binary dump
    local f = io.open(filename, "wb")
    if not f then
        console:log("Failed to open " .. filename)
        return
    end

    -- Dump WRAM (0xC000-0xDFFF = 8KB)
    for addr = 0xC000, 0xDFFF do
        f:write(string.char(emu:read8(addr)))
    end

    -- Dump HRAM (0xFF80-0xFFFE)
    for addr = 0xFF80, 0xFFFE do
        f:write(string.char(emu:read8(addr)))
    end

    f:close()

    -- Also create human-readable text dump of interesting areas
    local t = io.open(txtfile, "w")
    if t then
        t:write("=== GAME STATE DUMP #" .. dump_count .. " ===\n\n")

        -- OAM info
        t:write("=== OAM (0xFE00-0xFE9F) ===\n")
        for slot = 0, 39 do
            local base = 0xFE00 + slot * 4
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            if y ~= 0 then  -- Only show visible sprites
                t:write(string.format("Slot %2d: Y=%3d X=%3d Tile=0x%02X Flags=0x%02X\n",
                    slot, y, x, tile, flags))
            end
        end

        -- Interesting WRAM regions (game variables typically 0xC000-0xC0FF or 0xD000-0xD0FF)
        t:write("\n=== WRAM 0xC000-0xC0FF ===\n")
        for row = 0, 15 do
            local addr = 0xC000 + row * 16
            t:write(string.format("%04X: ", addr))
            for col = 0, 15 do
                t:write(string.format("%02X ", emu:read8(addr + col)))
            end
            t:write("\n")
        end

        t:write("\n=== WRAM 0xC100-0xC1FF ===\n")
        for row = 0, 15 do
            local addr = 0xC100 + row * 16
            t:write(string.format("%04X: ", addr))
            for col = 0, 15 do
                t:write(string.format("%02X ", emu:read8(addr + col)))
            end
            t:write("\n")
        end

        t:write("\n=== WRAM 0xD000-0xD0FF ===\n")
        for row = 0, 15 do
            local addr = 0xD000 + row * 16
            t:write(string.format("%04X: ", addr))
            for col = 0, 15 do
                t:write(string.format("%02X ", emu:read8(addr + col)))
            end
            t:write("\n")
        end

        -- Enemy/boss data often near 0xC200-0xC3FF
        t:write("\n=== WRAM 0xC200-0xC2FF (likely enemy data) ===\n")
        for row = 0, 15 do
            local addr = 0xC200 + row * 16
            t:write(string.format("%04X: ", addr))
            for col = 0, 15 do
                t:write(string.format("%02X ", emu:read8(addr + col)))
            end
            t:write("\n")
        end

        t:close()
    end

    console:log("Dumped game state #" .. dump_count .. " to " .. filename .. " and " .. txtfile)
end

-- Register callback for SELECT button
-- mGBA returns keys as a bitmask: SELECT = bit 2 (value 4)
callbacks:add("keysRead", function()
    local keys = emu:getKeys()
    local select_down = (keys & 0x04) ~= 0  -- SELECT is bit 2

    if select_down then
        if not select_pressed then
            select_pressed = true
            dump_memory()
        end
    else
        select_pressed = false
    end
end)

select_pressed = false
console:log("Game state dumper loaded. Press SELECT to dump memory.")
console:log("Dump with boss present, kill boss, dump again, then compare files.")
