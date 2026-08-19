-- Capture a long, native-animation boss receipt without changing its motion.
-- The Python owner launches this only through mgba-qt-singleflight.

local OUT = assert(os.getenv("BOSS_ANIMATION_OUT"), "BOSS_ANIMATION_OUT required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_ANIMATION_SCENE") or "15")
local FRAMES = tonumber(os.getenv("BOSS_ANIMATION_FRAMES") or "3600")
local STEP = tonumber(os.getenv("BOSS_ANIMATION_STEP") or "2")
local TRACE_STEP = tonumber(os.getenv("BOSS_ANIMATION_TRACE_STEP") or "1")
local SOURCE_TRACE = os.getenv("BOSS_ANIMATION_SOURCE_TRACE") == "1"
local STOCK_ROM = os.getenv("BOSS_ANIMATION_STOCK_ROM") == "1"
local FLUSH_FRAMES = 20
local frame, captured, finished = 0, 0, false
local wrong_scene_frames = 0
local trace = assert(io.open(OUT .. ".trace", "w"))
local sources = SOURCE_TRACE and assert(io.open(OUT .. ".sources.bin", "wb")) or nil
local publications = SOURCE_TRACE
    and assert(io.open(OUT .. ".publications.bin", "wb")) or nil

if SOURCE_TRACE then
    pcall(function()
        emu:setBreakpoint(function()
            if emu:read8(0xD880) == EXPECTED_SCENE then
                trace:write(string.format(
                    "publication frame=%d dc0b=%02X\n",
                    frame, emu:read8(0xDC0B)))
                trace:flush()
                local record = {frame & 0xFF, (frame >> 8) & 0xFF}
                for offset = 0, 24 * 24 - 1 do
                    record[#record + 1] = emu:read8(0xC1A0 + offset)
                end
                publications:write(string.char(table.unpack(record)))
                publications:flush()
            end
        end, 0x42A7)
    end)
end

-- Canonical numbered body geometry. Each pair is [left+4,right+4), matching
-- the ROM sanitizer table; IDs $02-$76 advance left-to-right, top-to-bottom.
local TED_BODY_ROWS = {
    4,9, 2,10, 2,10, 2,10, 2,10, 2,11, 1,11,
    0,11, 0,11, 0,11, 1,11, 2,10, 4,10, 5,9,
}
local TED_BODY_EXPECTED = {}
do
    local tile = 0x02
    for row = 0, 13 do
        local left = TED_BODY_ROWS[row * 2 + 1] - 4
        local right = TED_BODY_ROWS[row * 2 + 2] - 4
        for col = left, right - 1 do
            TED_BODY_EXPECTED[string.format("%d,%d", row, col)] = tile
            tile = tile + 1
        end
    end
    assert(tile == 0x77, "Ted body table must cover $02-$76")
end

local function visible_geometry()
    local old_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    local base = (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800
    local crown_row, crown_col = -1, -1
    local sparse_count, sparse_hash = 0, 0
    local sparse_cells = {}
    local bank1_count, priority_count, flipped_count = 0, 0, 0
    local body_offsets, sparse_offsets = {}, {}
    for row = 0, 31 do
        for col = 0, 31 do
            local value = emu:read8(base + row * 32 + col)
            if value == 0x02 then
                local complete = true
                for step = 1, 4 do
                    if emu:read8(base + row * 32 + ((col + step) & 31)) ~= 0x02 + step then
                        complete = false
                        break
                    end
                end
                if complete then crown_row, crown_col = row, col end
            end
            if value >= 0x02 and value <= 0x76 then
                table.insert(body_offsets, row * 32 + col)
            end
            if value >= 0x7B and value <= 0x86
                    and value ~= 0x7C and value ~= 0x7E
                    and value ~= 0x7F and value ~= 0x81 then
                sparse_count = sparse_count + 1
                table.insert(sparse_offsets, row * 32 + col)
                sparse_hash = ((sparse_hash * 131) ~ (value * 1024 + row * 32 + col)) & 0xFFFFFFFF
                if crown_row >= 0 then
                    local relative_row = (row - crown_row) & 31
                    local relative_col = (col - crown_col) & 31
                    if relative_row >= 16 then relative_row = relative_row - 32 end
                    if relative_col >= 16 then relative_col = relative_col - 32 end
                    table.insert(sparse_cells, string.format(
                        "%02X@%d,%d", value, relative_row, relative_col))
                end
            end
        end
    end
    -- Crown-relative cells need a second pass because legitimate tendrils can
    -- appear on rows preceding the five-tile crown in physical map order.
    sparse_cells = {}
    local body_mismatch_cells = {}
    if crown_row >= 0 then
        for row = 0, 31 do
            for col = 0, 31 do
                local value = emu:read8(base + row * 32 + col)
                if value >= 0x02 and value <= 0x76 then
                    local relative_row = (row - crown_row) & 31
                    local relative_col = (col - crown_col) & 31
                    if relative_row >= 16 then relative_row = relative_row - 32 end
                    if relative_col >= 16 then relative_col = relative_col - 32 end
                    local expected = TED_BODY_EXPECTED[string.format(
                        "%d,%d", relative_row, relative_col)]
                    if expected ~= value then
                        table.insert(body_mismatch_cells, string.format(
                            "%02X@%d,%d", value, relative_row, relative_col))
                    end
                end
                if value >= 0x7B and value <= 0x86
                        and value ~= 0x7C and value ~= 0x7E
                        and value ~= 0x7F and value ~= 0x81 then
                    local relative_row = (row - crown_row) & 31
                    local relative_col = (col - crown_col) & 31
                    if relative_row >= 16 then relative_row = relative_row - 32 end
                    if relative_col >= 16 then relative_col = relative_col - 32 end
                    table.insert(sparse_cells, string.format(
                        "%02X@%d,%d", value, relative_row, relative_col))
                end
            end
        end
    end
    emu:write8(0xFF4F, 1)
    local body_palettes, sparse_palettes = {}, {}
    for offset = 0, 0x3FF do
        local attr = emu:read8(base + offset)
        if (attr & 0x08) ~= 0 then bank1_count = bank1_count + 1 end
        if (attr & 0x80) ~= 0 then priority_count = priority_count + 1 end
        if (attr & 0x60) ~= 0 then flipped_count = flipped_count + 1 end
    end
    for _, offset in ipairs(body_offsets) do
        local palette = emu:read8(base + offset) & 0x07
        body_palettes[palette] = (body_palettes[palette] or 0) + 1
    end
    for _, offset in ipairs(sparse_offsets) do
        local palette = emu:read8(base + offset) & 0x07
        sparse_palettes[palette] = (sparse_palettes[palette] or 0) + 1
    end
    local function palette_histogram(counts)
        local fields = {}
        for palette = 0, 7 do
            table.insert(fields, tostring(counts[palette] or 0))
        end
        return table.concat(fields, ",")
    end
    emu:write8(0xFF4F, old_vbk)
    return crown_row, crown_col, sparse_count, sparse_hash,
        bank1_count, priority_count, flipped_count,
        table.concat(sparse_cells, ";"), palette_histogram(body_palettes),
        palette_histogram(sparse_palettes), #body_mismatch_cells,
        table.concat(body_mismatch_cells, ";")
end

local function source_geometry()
    local crown_row, crown_col = -1, -1
    for row = 0, 23 do
        for col = 0, 19 do
            local base = 0xC1A0 + row * 24 + col
            local complete = true
            for step = 0, 4 do
                if emu:read8(base + step) ~= 0x02 + step then
                    complete = false
                    break
                end
            end
            if complete then crown_row, crown_col = row, col end
        end
    end
    local sparse_count, sparse_hash = 0, 0
    local cells = {}
    for row = 0, 23 do
        for col = 0, 23 do
            local value = emu:read8(0xC1A0 + row * 24 + col)
            if value >= 0x7B and value <= 0x86
                    and value ~= 0x7C and value ~= 0x7E
                    and value ~= 0x7F and value ~= 0x81 then
                sparse_count = sparse_count + 1
                sparse_hash = ((sparse_hash * 131) ~ (value * 1024 + row * 24 + col)) & 0xFFFFFFFF
                if crown_row >= 0 then
                    table.insert(cells, string.format(
                        "%02X@%d,%d", value, row - crown_row, col - crown_col))
                end
            end
        end
    end
    return sparse_count, sparse_hash, table.concat(cells, ";")
end

local function source_nonchecker_envelope()
    -- Troop's stock checker uses only tiles $01-$04. Record the inclusive
    -- non-checker envelope per row so spatial sanitizers can be derived from
    -- the complete native animation instead of one hand-picked screenshot.
    local rows = {}
    for row = 0, 17 do
        local left, right = 24, -1
        for col = 0, 23 do
            local value = emu:read8(0xC1A0 + row * 24 + col)
            if value < 0x01 or value > 0x04 then
                if col < left then left = col end
                if col > right then right = col end
            end
        end
        table.insert(rows, string.format("%d:%d-%d", row, left, right))
    end
    return table.concat(rows, ",")
end

local function register(name)
    local accessors = {
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }
    for _, accessor in ipairs(accessors) do
        local ok, value = pcall(accessor)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

pcall(function()
    emu:setRangeWatchpoint(function(info)
        trace:write(string.format(
            "scene-write frame=%d pc=%04X old=%02X new=%02X df4c=%02X ff91=%02X\n",
            frame, register("PC"), info.oldValue & 0xFF, info.newValue & 0xFF,
            emu:read8(0xDF4C), emu:read8(0xFF91)))
        trace:flush()
    end, 0xD880, 0xD880, C.WATCHPOINT_TYPE.WRITE_CHANGE)
end)

local function finish(status)
    if finished then return end
    finished = true
    trace:write(string.format(
        "complete status=%s frames=%d captures=%d scene=%02X\n",
        status, frame, captured, emu:read8(0xD880)))
    trace:close()
    if sources then sources:close() end
    if publications then publications:close() end
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    emu:setKeys(0)

    -- D880/DCxx are switchable WRAM. During the cached DX publisher a frame
    -- callback can observe SVBK 2; reading "scene" then returns cache bytes
    -- (not game state), and writing survival values would corrupt the cache.
    -- Touch these fields only while bank 0/1 is naturally selected. DMG/OG
    -- reports $FF and has no switchable-WRAM bank, so $07 remains valid there.
    local svbk = emu:read8(0xFF70) & 0x07
    local game_wram_visible = (STOCK_ROM and svbk == 7)
        or (not STOCK_ROM and (svbk == 0 or svbk == 1))
    if game_wram_visible then
        -- Keep both contestants alive so the receipt observes animation
        -- rather than a boss-exit cut. These do not alter pose or timing.
        emu:write8(0xDCBB, 0xF0)
        emu:write8(0xDCDC, 0xFF)
        emu:write8(0xDCDD, 0xFF)
    end
    -- D888/DD06 participate in Ted's native animation/publication state.
    -- Writing them here previously forced the boss out of scene $10 after
    -- four frames and made the visual audit alter the motion it claimed to
    -- observe. Keep only the independently proven survival counters above.

    if game_wram_visible then
        if emu:read8(0xD880) ~= EXPECTED_SCENE then
            wrong_scene_frames = wrong_scene_frames + 1
            -- A frame callback can land inside the banked DB80 arena helper,
            -- where the D880 window is briefly not the gameplay bank even
            -- though the SVBK readback is transitioning. Require a sustained
            -- exit so one mapper boundary cannot reject a valid long capture.
            if wrong_scene_frames >= 8 then
                finish("wrong-scene")
                return
            end
        else
            wrong_scene_frames = 0
        end
    end
    if frame <= FRAMES and frame % STEP == 0 then
        captured = captured + 1
        emu:screenshot(OUT .. string.format(".f%04d.png", frame))
    end
    if frame % TRACE_STEP == 0 then
        local crown_row, crown_col, sparse_count, sparse_hash,
            bank1_count, priority_count, flipped_count, sparse_cells,
            body_palettes, sparse_palettes, body_mismatches,
            body_mismatch_cells =
            visible_geometry()
        local source_sparse_count, source_sparse_hash, source_sparse_cells =
            source_geometry()
        local source_envelope = source_nonchecker_envelope()
        trace:write(string.format(
            "frame=%d pc=%04X scene=%02X lcdc=%02X scx=%02X scy=%02X " ..
            "df4c=%02X ff91=%02X dcbb=%02X d888=%02X dd06=%02X " ..
            "crown=%d,%d sparse=%d sparse_hash=%08X svbk=%d " ..
            "bank1=%d priority=%d flipped=%d source_sparse=%d " ..
            "source_hash=%08X dc0b=%02X body_palettes=%s " ..
            "anchors=%02X,%02X,%02X,%02X,%02X,%02X a9=%02X dce0=%02X " ..
            "sparse_palettes=%s body_mismatches=%d mismatch_cells=%s " ..
            "visible_cells=%s source_cells=%s source_envelope=%s\n",
            frame, register("PC"), emu:read8(0xD880), emu:read8(0xFF40),
            emu:read8(0xFF43), emu:read8(0xFF42),
            emu:read8(0xDF4C), emu:read8(0xFF91), emu:read8(0xDCBB),
            emu:read8(0xD888), emu:read8(0xDD06), crown_row, crown_col,
            sparse_count, sparse_hash, svbk, bank1_count, priority_count,
            flipped_count, source_sparse_count, source_sparse_hash,
            emu:read8(0xDC0B), body_palettes,
            emu:read8(0xC4F3), emu:read8(0xC4F4),
            emu:read8(0xC4F5), emu:read8(0xC4F6),
            emu:read8(0xC4FA), emu:read8(0xC4FB),
            emu:read8(0xFFA9), emu:read8(0xDCE0), sparse_palettes,
            body_mismatches, body_mismatch_cells, sparse_cells,
            source_sparse_cells, source_envelope))
        trace:flush()
        if sources then
            local record = {
                frame & 0xFF, (frame >> 8) & 0xFF,
                emu:read8(0xD888), emu:read8(0xDD06),
                emu:read8(0xFF43), emu:read8(0xFF42),
            }
            for offset = 0, 24 * 24 - 1 do
                record[#record + 1] = emu:read8(0xC1A0 + offset)
            end
            sources:write(string.char(table.unpack(record)))
            sources:flush()
        end
    end
    if frame >= FRAMES + FLUSH_FRAMES then finish("ok") end
end)
