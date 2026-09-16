-- Verify current-ROM BG attributes and CRAM for every pickup signature in one
-- real Stage 1 savestate. The caller supplies a tab-separated specification:
-- name<TAB>palette<TAB>tile0,tile1,tile2,tile3.

local OUT = assert(os.getenv("PICKUP_LIVE_OUT"), "PICKUP_LIVE_OUT required")
local SCREENSHOT = assert(
    os.getenv("PICKUP_LIVE_SCREENSHOT"), "PICKUP_LIVE_SCREENSHOT required")
local SPEC = assert(os.getenv("PICKUP_LIVE_SPEC"), "PICKUP_LIVE_SPEC required")
local SETTLE = tonumber(os.getenv("PICKUP_LIVE_SETTLE") or "180")
local CAPTURE_PUBLICATION_FRAMES = 4
local DEMO_REARM_ROWS = tonumber(
    os.getenv("PICKUP_LIVE_DEMO_REARM_ROWS") or "18")
local SUBSTITUTE = os.getenv("PICKUP_LIVE_SUBSTITUTE")
local TILE_GFX = os.getenv("PICKUP_LIVE_TILE_GFX")
local HOST_ROW = os.getenv("PICKUP_LIVE_HOST_ROW")
local HOST_COLUMN = os.getenv("PICKUP_LIVE_HOST_COLUMN")
local HOST_SOURCE = os.getenv("PICKUP_LIVE_HOST_SOURCE")
local HOST_MODE = HOST_ROW ~= nil or HOST_COLUMN ~= nil or HOST_SOURCE ~= nil
if HOST_MODE then
    HOST_ROW = assert(tonumber(HOST_ROW), "PICKUP_LIVE_HOST_ROW required")
    HOST_COLUMN = assert(
        tonumber(HOST_COLUMN), "PICKUP_LIVE_HOST_COLUMN required")
    HOST_SOURCE = assert(
        tonumber(HOST_SOURCE, 16), "PICKUP_LIVE_HOST_SOURCE required")
end
local RUNTIME_PATH = assert(
    os.getenv("PICKUP_LIVE_RUNTIME"), "PICKUP_LIVE_RUNTIME required")
local runtime_file = assert(io.open(RUNTIME_PATH, "rb"))
local runtime_image = assert(runtime_file:read("*a"))
runtime_file:close()
assert(#runtime_image == 41, "Stage-1 runtime image must be 41 bytes")
local HELPER_PATH = assert(
    os.getenv("PICKUP_LIVE_HELPER"), "PICKUP_LIVE_HELPER required")
local helper_file = assert(io.open(HELPER_PATH, "rb"))
local helper_image = assert(helper_file:read("*a"))
helper_file:close()
assert(#helper_image == 160, "Stage-1 helper image must be 160 bytes")
assert(
    helper_image:sub(0x78, 0xA0) == runtime_image,
    "Stage-1 runtime must match the DAD7-DAFF helper tail")
local LUT_PATH = assert(
    os.getenv("PICKUP_LIVE_LUT"), "PICKUP_LIVE_LUT required")
local lut_file = assert(io.open(LUT_PATH, "rb"))
local lut_image = assert(lut_file:read("*a"))
lut_file:close()
assert(#lut_image == 256, "Stage-1 LUT image must be 256 bytes")
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
if HOST_MODE then
    assert(#entries == 1, "coordinate host requires exactly one pickup")
    assert(HOST_ROW >= 0 and HOST_ROW < 23, "pickup host row out of range")
    assert(HOST_COLUMN >= 0 and HOST_COLUMN < 23,
        "pickup host column out of range")
    assert(HOST_SOURCE >= 0xC000
        and HOST_SOURCE + HOST_ROW * 24 + HOST_COLUMN + 25 <= 0xDFFF,
        "pickup host source out of range")
end

local frame = 0
local main_loop_hits = 0
local tile_copy_hits = 0
local sweep_trace = {}
local substitution_counts = {vram = 0, source = 0}
local host_decision_hits = 0
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

local function parse_tile_gfx(value)
    local result = {}
    if not value then return result end
    for record in value:gmatch("[^;]+") do
        local bank_text, tile_text, payload =
            record:match("^([^:]+):([^:]+):([^:]+)$")
        local bank = assert(tonumber(bank_text))
        local tile = assert(tonumber(tile_text, 16))
        assert(#payload == 32, "tile graphics must contain 16 bytes")
        local bytes = {}
        for index = 1, #payload, 2 do
            bytes[#bytes + 1] = assert(tonumber(payload:sub(index, index + 1), 16))
        end
        result[#result + 1] = {bank = bank, tile = tile, bytes = bytes}
    end
    return result
end

local injected_tile_gfx = parse_tile_gfx(TILE_GFX)

local function install_coordinate_source()
    if not HOST_MODE then return end
    local tiles = entries[1].tiles
    local source_offset = HOST_ROW * 24 + HOST_COLUMN
    local source_addresses = {
        source_offset, source_offset + 1,
        source_offset + 24, source_offset + 25,
    }
    for index, offset in ipairs(source_addresses) do
        emu:write8(HOST_SOURCE + offset, tiles[index])
    end
end

local function clear_coordinate_attributes()
    if not HOST_MODE then return end
    local map_offset = HOST_ROW * 32 + HOST_COLUMN
    local map_addresses = {
        map_offset, map_offset + 1, map_offset + 32, map_offset + 33,
    }
    for _, base in ipairs({0x9800, 0x9C00}) do
        emu:write8(0xFF4F, 1)
        for _, offset in ipairs(map_addresses) do
            emu:write8(base + offset, 0)
        end
    end
    emu:write8(0xFF4F, 0)
end

if HOST_MODE then
    pcall(function()
        -- The native room expander owns C1A0 and may refresh it after a frame
        -- callback. Inject at the candidate's fixed decision edge, after the
        -- packed source is complete and before its tile/attribute compile.
        emu:setBreakpoint(function()
            host_decision_hits = host_decision_hits + 1
            install_coordinate_source()
        end, 0x3485)
    end)
end

local function install_tile_gfx()
    for _, record in ipairs(injected_tile_gfx) do
        emu:write8(0xFF4F, record.bank)
        local address = 0x8000 + record.tile * 16
        for index, value in ipairs(record.bytes) do
            emu:write8(address + index - 1, value)
        end
    end
    emu:write8(0xFF4F, 0)
end

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

local function clear_entry_attributes()
    -- Historical fixtures carry attributes from the ROM that captured them.
    -- Clear only the exact audited pickup signatures before asking the current
    -- ROM to publish. This prevents stale mixed 2x2 attrs from being mistaken
    -- for candidate output without touching surrounding terrain/hazards.
    for _, base in ipairs({0x9800, 0x9C00}) do
        for _, entry in ipairs(entries) do
            for row = 0, 30 do
                for column = 0, 30 do
                    local offset = row * 32 + column
                    if signature_at(base, offset, entry.tiles) then
                        emu:write8(0xFF4F, 1)
                        emu:write8(base + offset, 0)
                        emu:write8(base + offset + 1, 0)
                        emu:write8(base + offset + 32, 0)
                        emu:write8(base + offset + 33, 0)
                    end
                end
            end
        end
    end
    emu:write8(0xFF4F, 0)
end

local function finish()
    -- If the room publisher naturally rebuilt the host signature, render the
    -- same-class target IDs over its live attributes for the final audit. The
    -- frame-1 pass above cleared both maps first, so the retained attributes
    -- here are current-ROM publication output, never fixture data.
    install_substitution(false)
    install_tile_gfx()
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
    handle:write(string.format("host_decision_hits=%d\n", host_decision_hits))
    local visible_oam = {}
    for sprite = 0, 39 do
        local address = 0xFE00 + sprite * 4
        local y, x = emu:read8(address), emu:read8(address + 1)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            visible_oam[#visible_oam + 1] = string.format(
                "%d:%d:%d:%02X:%02X", sprite, x, y,
                emu:read8(address + 2), emu:read8(address + 3))
        end
    end
    handle:write("visible_oam=" .. table.concat(visible_oam, ",") .. "\n")
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
    local reported_tiles = {}
    for _, entry in ipairs(entries) do
        for _, tile in ipairs(entry.tiles) do reported_tiles[tile] = true end
    end
    for bank = 0, 1 do
        emu:write8(0xFF4F, bank)
        for tile, _ in pairs(reported_tiles) do
            local payload = {}
            local address = 0x8000 + tile * 16
            for index = 0, 15 do
                payload[#payload + 1] = string.format(
                    "%02X", emu:read8(address + index))
            end
            handle:write(string.format(
                "tilegfx=%d:%02X:%s\n", bank, tile, table.concat(payload)))
        end
    end
    emu:write8(0xFF4F, 0)

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
                            vram_read(1, base + offset),
                            vram_read(1, base + offset + 1),
                            vram_read(1, base + offset + 32),
                            vram_read(1, base + offset + 33),
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
    if frame <= 40 and not HOST_MODE then
        emu:write8(0xDF02, 0x00)
        emu:write8(0xDF00, 0x00)
        emu:write8(0xDF04, 0x00)
        emu:write8(0xDF05, 0x00)
        emu:write8(0xDF4E, 0x00)
    end
    if frame == 1 then
        if not HOST_MODE then
            -- Historical pickup fixtures serialize an earlier DA60-DAFF
            -- helper. Install the complete candidate-owned payload atomically.
            for offset = 0, #helper_image - 1 do
                emu:write8(
                    0xDA60 + offset, string.byte(helper_image, offset + 1))
            end
            -- The helper is now current, so retain the initialized sentinel.
            emu:write8(0xDF51, 0xA8)
            -- Historical fixture states also serialize their old C600 table.
            for offset = 0, #lut_image - 1 do
                emu:write8(0xC600 + offset, string.byte(lut_image, offset + 1))
            end
            -- Install the current generated row helper in both runtime banks.
            for _, bank in ipairs({2, 3}) do
                emu:write8(0xFF70, bank)
                local address = 0xD400
                for _ = 1, 24 do
                    for _, opcode in ipairs({0x1A, 0x13, 0x4F, 0x0A, 0x22}) do
                        emu:write8(address, opcode)
                        address = address + 1
                    end
                end
                emu:write8(address, 0xC9)
            end
            emu:write8(0xFF70, 1)
        end
        install_substitution(true)
        install_coordinate_source()
        clear_coordinate_attributes()
        if not HOST_MODE then clear_entry_attributes() end
        install_tile_gfx()
        -- Both content caches use ordinary byte signatures with no separate
        -- valid bit.  Zero is therefore not a safe invalid value.  Publish a
        -- one-shot unequal value derived from the exact loaded source; the
        -- current ROM will replace it with its real key after one rebuild.
        emu:write8(0xDF53, emu:read8(0xDF53) ~ 0xFF)
        emu:write8(0xDF57, emu:read8(0xDF57) ~ 0xFF)
        emu:write8(0xDF7C, emu:read8(0xDF7C) ~ 0xFF)
        if not HOST_MODE then
            -- Legacy cross-ROM fixtures also require a scene-table dispatch.
            -- Candidate-owned host states stay in their exact live room.
            emu:write8(0xDF0D, 0xFF)
        end
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

    if frame >= SETTLE and frame < SETTLE + CAPTURE_PUBLICATION_FRAMES then
        -- screenshot() captures the framebuffer produced before this callback.
        -- Publish the synthetic semantic form for several complete frames so
        -- the captured image, tilemap report, and injected native glyphs agree.
        install_substitution(false)
        install_tile_gfx()
    end
    if frame >= SETTLE + CAPTURE_PUBLICATION_FRAMES then finish() end
end)
