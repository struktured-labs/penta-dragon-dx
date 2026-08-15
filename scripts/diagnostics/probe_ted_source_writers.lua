-- Identify the native writers responsible for Ted's visible body and for the
-- off-silhouette staging cells that must remain neutral. This is a focused
-- reverse-engineering probe; it does not alter game state.

local OUT = assert(os.getenv("TED_WRITERS_OUT"), "TED_WRITERS_OUT required")
local FRAMES = tonumber(os.getenv("TED_WRITERS_FRAMES") or "900")
local SCENE = 0x10
local SOURCE = 0xC1A0
local SIZE = 24 * 24

local frame, copies, finished = 0, 0, false
local last_signature = {}
local body_counts, scratch_counts = {}, {}
local body_samples, scratch_samples, missing_writers = 0, 0, 0

local silhouette = {
    [0] = {0, 4}, [1] = {-2, 5}, [2] = {-2, 5}, [3] = {-2, 5},
    [4] = {-2, 5}, [5] = {-2, 6}, [6] = {-3, 6}, [7] = {-4, 6},
    [8] = {-4, 6}, [9] = {-4, 6}, [10] = {-3, 6}, [11] = {-2, 5},
    [12] = {0, 5}, [13] = {1, 4},
}

local function register(name)
    local readers = {
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }
    for _, reader in ipairs(readers) do
        local ok, value = pcall(reader)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

local function increment(counts, offset)
    local signature = last_signature[offset]
    if signature == nil then
        missing_writers = missing_writers + 1
        return
    end
    counts[signature] = (counts[signature] or 0) + 1
end

local function crown()
    local found = {}
    for row = 0, 23 do
        for col = 0, 19 do
            local offset = row * 24 + col
            local match = true
            for step = 0, 4 do
                if emu:read8(SOURCE + offset + step) ~= 0x02 + step then
                    match = false
                    break
                end
            end
            if match then found[#found + 1] = {row = row, col = col} end
        end
    end
    if #found ~= 1 then return nil end
    return found[1]
end

local function is_body(row, col, anchor)
    local relative_row = row - anchor.row
    local span = silhouette[relative_row]
    if span == nil then return false end
    local relative_col = col - anchor.col
    return relative_col >= span[1] and relative_col <= span[2]
end

assert(emu:setRangeWatchpoint(function(info)
    local offset = (info.address & 0xFFFF) - SOURCE
    local sp = register("SP")
    local stack = {}
    for depth = 0, 8 do
        local address = (sp + depth * 2) & 0xFFFF
        stack[#stack + 1] = emu:read8(address) |
            (emu:read8((address + 1) & 0xFFFF) << 8)
    end
    last_signature[offset] = string.format(
        "%02X:%04X stack=%04X/%04X/%04X/%04X/%04X/%04X/%04X/%04X/%04X " ..
        "hl=%04X de=%04X bc=%04X",
        emu:read8(0xFF99), register("PC"), stack[1], stack[2], stack[3],
        stack[4], stack[5], stack[6], stack[7], stack[8], stack[9],
        register("HL"), register("DE"), register("BC"))
end, SOURCE, SOURCE + SIZE, C.WATCHPOINT_TYPE.WRITE) > 0)

assert(emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= SCENE then return end
    local anchor = crown()
    if anchor == nil then return end
    copies = copies + 1
    for offset = 0, SIZE - 1 do
        local tile = emu:read8(SOURCE + offset)
        if tile >= 0x02 and tile <= 0x76 then
            local row, col = math.floor(offset / 24), offset % 24
            if is_body(row, col, anchor) then
                body_samples = body_samples + 1
                increment(body_counts, offset)
            else
                scratch_samples = scratch_samples + 1
                increment(scratch_counts, offset)
            end
        end
    end
end, 0x42A7) > 0)

local function sorted(counts)
    local rows = {}
    for key, count in pairs(counts) do
        rows[#rows + 1] = {key = key, count = count}
    end
    table.sort(rows, function(a, b)
        if a.count ~= b.count then return a.count > b.count end
        return a.key < b.key
    end)
    return rows
end

local function finish(status)
    if finished then return end
    finished = true
    local out = assert(io.open(OUT, "w"))
    out:write(string.format(
        "status=%s frames=%d copies=%d body_samples=%d scratch_samples=%d missing_writers=%d\n",
        status, frame, copies, body_samples, scratch_samples, missing_writers))
    for _, row in ipairs(sorted(body_counts)) do
        out:write(string.format("body_writer=%s count=%d\n", row.key, row.count))
    end
    for _, row in ipairs(sorted(scratch_counts)) do
        out:write(string.format("scratch_writer=%s count=%d\n", row.key, row.count))
    end
    out:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
    os.exit(status == "ok" and 0 or 1)
end

callbacks:add("frame", function()
    frame = frame + 1
    emu:setKeys(0)
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0x00)
    emu:write8(0xDD06, 0x00)
    if emu:read8(0xD880) ~= SCENE then
        finish("wrong-scene")
    elseif frame >= FRAMES then
        finish(copies > 0 and scratch_samples > 0 and "ok" or "no-samples")
    end
end)
