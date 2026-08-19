-- Verify current-ROM BG attributes and CRAM for every pickup signature in one
-- real Stage 1 savestate. The caller supplies a tab-separated specification:
-- name<TAB>palette<TAB>tile0,tile1,tile2,tile3.

local OUT = assert(os.getenv("PICKUP_LIVE_OUT"), "PICKUP_LIVE_OUT required")
local SCREENSHOT = assert(
    os.getenv("PICKUP_LIVE_SCREENSHOT"), "PICKUP_LIVE_SCREENSHOT required")
local SPEC = assert(os.getenv("PICKUP_LIVE_SPEC"), "PICKUP_LIVE_SPEC required")
local SETTLE = tonumber(os.getenv("PICKUP_LIVE_SETTLE") or "180")
local DEMO_REARM_ROWS = tonumber(
    os.getenv("PICKUP_LIVE_DEMO_REARM_ROWS") or "18")
local SUBSTITUTE = os.getenv("PICKUP_LIVE_SUBSTITUTE")
local function read_register(name)
    for _, spelling in ipairs({string.lower(name), string.upper(name)}) do
        local ok, value = pcall(function() return emu:readRegister(spelling) end)
        if ok and value then return value & 0xFFFF end
        ok, value = pcall(function() return emu:getRegister(spelling) end)
        if ok and value then return value & 0xFFFF end
    end
    return 0xFFFF
end

local entries = {}
for line in io.lines(SPEC) do
    local name, palette_text, tiles_text =
        line:match("^([^\t]+)\t([^\t]+)\t([^\t]+)$")
    assert(name and palette_text and tiles_text, "bad pickup specification")
    local tiles = {}
    for value in tiles_text:gmatch("[^,]+") do
        tiles[#tiles + 1] = assert(tonumber(value, 16))
    end
    assert(#tiles == 4, "pickup signature must contain four tiles")
    entries[#entries + 1] = {
        name = name,
        palette = assert(tonumber(palette_text)),
        tiles = tiles,
    }
end
assert(#entries > 0, "empty pickup specification")

local frame = 0
local main_loop_hits = 0
local tile_copy_hits = 0
local sweep_trace = {}
local substitution_counts = {vram = 0, source = 0}
pcall(function()
    emu:setBreakpoint(function() main_loop_hits = main_loop_hits + 1 end, 0x016C)
    emu:setBreakpoint(function() tile_copy_hits = tile_copy_hits + 1 end, 0x42A7)
    emu:setBreakpoint(function()
        if #sweep_trace < 96 then
            sweep_trace[#sweep_trace + 1] = string.format(
                "%d,%04X,%02X,%02X,%02X",
                frame,
                (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800,
                emu:read8(0xDF04),
                emu:read8(0xDF4E),
                emu:read8(0xFF42))
        end
    end, 0x6CD0)
end)

local function vram_read(bank, address)
    emu:write8(0xFF4F, bank)
    return emu:read8(address)
end

local function cram_word(palette, color)
    local index = palette * 8 + color * 2
    emu:write8(0xFF68, index)
    local low = emu:read8(0xFF69)
    emu:write8(0xFF68, index + 1)
    local high = emu:read8(0xFF69)
    return (high << 8) | low
end

local function signature_at(base, offset, tiles)
    return vram_read(0, base + offset) == tiles[1]
        and vram_read(0, base + offset + 1) == tiles[2]
        and vram_read(0, base + offset + 32) == tiles[3]
        and vram_read(0, base + offset + 33) == tiles[4]
end

local function parse_substitution(value)
    if not value then return nil end
    local before_text, after_text = value:match("^([^:]+):([^:]+)$")
    assert(before_text and after_text, "bad pickup substitution")
    local function parse_half(text)
        local result = {}
        for byte in text:gmatch("[^,]+") do
            result[#result + 1] = assert(tonumber(byte, 16))
        end
        assert(#result == 4, "pickup substitution must contain four tiles")
        return result
    end
    return {before = parse_half(before_text), after = parse_half(after_text)}
end

local substitution = parse_substitution(SUBSTITUTE)

local function install_substitution(clear_attributes)
    if not substitution then return end
    for _, base in ipairs({0x9800, 0x9C00}) do
        for row = 0, 30 do
            for column = 0, 30 do
                local offset = row * 32 + column
                if signature_at(base, offset, substitution.before) then
                    local addresses = {
                        base + offset, base + offset + 1,
                        base + offset + 32, base + offset + 33,
                    }
                    emu:write8(0xFF4F, 0)
                    for index, address in ipairs(addresses) do
                        emu:write8(address, substitution.after[index])
                    end
                    if clear_attributes then
                        emu:write8(0xFF4F, 1)
                        for _, address in ipairs(addresses) do
                            emu:write8(address, 0)
                        end
                    end
                    substitution_counts.vram = substitution_counts.vram + 1
                end
            end
        end
    end
    emu:write8(0xFF4F, 0)
    -- The native room copier consumes 32-column tile planes in C000-C5FF.
    -- Replace exact 2x2 source signatures only; no attributes are injected.
    for base = 0xC000, 0xC5C0, 0x20 do
        for column = 0, 30 do
            local address = base + column
            if emu:read8(address) == substitution.before[1]
                and emu:read8(address + 1) == substitution.before[2]
                and emu:read8(address + 32) == substitution.before[3]
                and emu:read8(address + 33) == substitution.before[4] then
                emu:write8(address, substitution.after[1])
                emu:write8(address + 1, substitution.after[2])
                emu:write8(address + 32, substitution.after[3])
                emu:write8(address + 33, substitution.after[4])
                substitution_counts.source = substitution_counts.source + 1
            end
        end
    end
end

local function finish()
    -- If the room publisher naturally rebuilt the host signature, render the
    -- same-class target IDs over its live attributes for the final audit. The
    -- frame-1 pass above cleared both maps first, so the retained attributes
    -- here are current-ROM publication output, never fixture data.
    install_substitution(false)
    emu:screenshot(SCREENSHOT)
    local handle = assert(io.open(OUT, "w"))
    local lcdc = emu:read8(0xFF40)
    handle:write(string.format("frames=%d\n", frame))
    handle:write(string.format("D880=%02X\n", emu:read8(0xD880)))
    handle:write(string.format("FFC1=%02X\n", emu:read8(0xFFC1)))
    handle:write(string.format("FFBD=%02X\n", emu:read8(0xFFBD)))
    handle:write(string.format("LCDC=%02X\n", lcdc))
    handle:write(string.format("SCX=%02X\n", emu:read8(0xFF43)))
    handle:write(string.format("SCY=%02X\n", emu:read8(0xFF42)))
    handle:write(string.format("PC=%04X\n", read_register("PC")))
    handle:write(string.format("SP=%04X\n", read_register("SP")))
    handle:write(string.format("FF99=%02X\n", emu:read8(0xFF99)))
    handle:write(string.format("DF02=%02X\n", emu:read8(0xDF02)))
    handle:write(string.format("main_loop_hits=%d\n", main_loop_hits))
    handle:write(string.format("tile_copy_hits=%d\n", tile_copy_hits))
    handle:write(string.format("demo_rearm_rows=%d\n", DEMO_REARM_ROWS))
    handle:write(string.format("sweep_hits=%d\n", #sweep_trace))
    handle:write(string.format("substitution_vram=%d\n", substitution_counts.vram))
    handle:write(string.format("substitution_source=%d\n", substitution_counts.source))
    for _, event in ipairs(sweep_trace) do
        handle:write("sweep=" .. event .. "\n")
    end
    for palette = 0, 7 do
        handle:write(string.format(
            "cram=%d,%04X,%04X,%04X,%04X\n",
            palette,
            cram_word(palette, 0), cram_word(palette, 1),
            cram_word(palette, 2), cram_word(palette, 3)))
    end

    local map_bases = {0x9800, 0x9C00}
    for _, entry in ipairs(entries) do
        local found = 0
        local matched = 0
        local details = {}
        for _, base in ipairs(map_bases) do
            for row = 0, 30 do
                for column = 0, 30 do
                    local offset = row * 32 + column
                    if signature_at(base, offset, entry.tiles) then
                        found = found + 1
                        local attrs = {
                            vram_read(1, base + offset) & 0x07,
                            vram_read(1, base + offset + 1) & 0x07,
                            vram_read(1, base + offset + 32) & 0x07,
                            vram_read(1, base + offset + 33) & 0x07,
                        }
                        local exact = true
                        for _, value in ipairs(attrs) do
                            if value ~= entry.palette then exact = false end
                        end
                        if exact then matched = matched + 1 end
                        details[#details + 1] = string.format(
                            "%04X:%d:%d:%d/%d/%d/%d",
                            base, column, row,
                            attrs[1], attrs[2], attrs[3], attrs[4])
                    end
                end
            end
        end
        handle:write(string.format(
            "pickup\t%s\t%d\t%d\t%d\t%s\n",
            entry.name, entry.palette, found, matched,
            table.concat(details, ";")))
    end
    handle:close()
    os.exit(0)
end

callbacks:add("frame", function()
    frame = frame + 1
    emu:setKeys(0)

    -- These historical capture states carry the CRAM/cache image of the ROM
    -- that created them. Re-enter the current ROM's ordinary cold initializer
    -- so this audit measures the candidate's table and palette rows.
    if frame <= 40 then
        emu:write8(0xDF02, 0x00)
        emu:write8(0xDF00, 0x00)
        emu:write8(0xDF53, 0x00)
        emu:write8(0xDF57, 0x00)
        emu:write8(0xDF04, 0x00)
        emu:write8(0xDF05, 0x00)
        emu:write8(0xDF4E, 0x00)
    end
    if frame == 1 then
        install_substitution(true)
        -- Force a real current-ROM scene-table dispatch after loading the
        -- historical state image.
        emu:write8(0xDF0D, 0xFF)
    end
    if frame == 41 and emu:read8(0xD880) == 0x0A then
        -- A natural attract room writer rearms this counter. Historical
        -- savestates resume after that event, so reproduce the missed edge.
        emu:write8(0xDF4E, DEMO_REARM_ROWS)
    end

    -- Keep Sara alive while stationary enemy-heavy captures settle.
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xFF)

    if frame >= SETTLE then finish() end
end)
