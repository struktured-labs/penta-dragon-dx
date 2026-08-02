-- Trace the native code that places Stage-1 pickup tile IDs into the packed
-- C1A0 room buffer.  This is a reverse-engineering probe, not a verifier: it
-- records CPU context only when a write's new value is one of the 73 pickup
-- tile IDs inventoried in palettes/bg_tile_categories.yaml.

local OUT = assert(os.getenv("STAGE1_PICKUP_WRITERS_OUT"))
local TRACE_FILE = assert(os.getenv("STAGE1_PICKUP_WRITERS_TRACE"))
local LIMIT = tonumber(os.getenv("STAGE1_PICKUP_WRITERS_FRAMES") or "7200")
local PLAY_LIMIT = tonumber(
    os.getenv("STAGE1_PICKUP_WRITERS_PLAY_FRAMES") or "1800")
local EVENT_LIMIT = tonumber(
    os.getenv("STAGE1_PICKUP_WRITERS_EVENT_LIMIT") or "4096")

local KEY_A = 0x01
local KEY_START = 0x08
local KEY_DOWN = 0x80

local pickup_tiles = {}
local function add(values)
    for _, value in ipairs(values) do pickup_tiles[value] = true end
end
add({0x88, 0x89, 0x96, 0x98, 0x99})
add({0x8A, 0x8B, 0x8C, 0x8D, 0x9A, 0x9B, 0x9C, 0x9D})
add({0x84, 0x85, 0x94, 0x95})
add({
    0x8E, 0x8F, 0x9E, 0x9F,
    0xA8, 0xA9, 0xB8, 0xB9,
    0xAA, 0xAB, 0xBA, 0xBB,
    0xC8, 0xC9, 0xD8, 0xD9,
    0xCE, 0xCF, 0xDE, 0xDF,
})
add({
    0xA0, 0xA1, 0xB0, 0xB1,
    0xA2, 0xA3, 0xB2, 0xB3,
    0xA4, 0xA5, 0xB4, 0xB5,
    0xA6, 0xA7, 0xB6, 0xB7,
    0xAC, 0xAD, 0xBC, 0xBD,
})
add({
    0xAE, 0xAF, 0xBE, 0xBF,
    0xC6, 0xC7, 0xD6, 0xD7,
    0xCA, 0xCB, 0xDA, 0xDB,
    0xCC, 0xCD, 0xDC, 0xDD,
})

local trace_keys = {}
local trace_first_frame = nil
for line in assert(io.open(TRACE_FILE, "r")):lines() do
    local sample_frame = tonumber(line:match('"f":(%d+)'))
    local sample_keys = tonumber(line:match('"keys":(%d+)'))
    if sample_frame and sample_keys then
        trace_keys[sample_frame] = sample_keys
        if trace_first_frame == nil or sample_frame < trace_first_frame then
            trace_first_frame = sample_frame
        end
    end
end
assert(trace_first_frame ~= nil, "controller trace contains no samples")

local frame = 0
local gameplay_frame = 0
local first_gameplay = nil
local trace_offset = 0
local trace_key = 0
local events = {}
local pc_counts = {}
local copy_callers = {}
local copy_events = {}
local gdma_writes = {}
local semantic_events = {}
local semantic_counts = {}
local stopped = false

local function pulse(lo, hi, mask)
    return (frame >= lo and frame < hi) and mask or 0
end

local function register(name)
    local readers = {
        function() return emu:readRegister(string.lower(name)) end,
        function() return emu:readRegister(string.upper(name)) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:getRegister(string.upper(name)) end,
    }
    for _, reader in ipairs(readers) do
        local ok, value = pcall(reader)
        if ok and value then return value end
    end
    return 0
end

local function on_write(info)
    local value = info.newValue and (info.newValue & 0xFF) or -1
    if not pickup_tiles[value] then return end
    local pc = register("PC") & 0xFFFF
    local bc = register("BC") & 0xFFFF
    pc_counts[pc] = (pc_counts[pc] or 0) + 1
    if #events >= EVENT_LIMIT then return end
    local sp = register("SP") & 0xFFFF
    events[#events + 1] = string.format(
        "f=%d g=%d pc=%04X bank=%02X bc=%04X meta=%02X " ..
        "sp=%04X ret=%02X%02X " ..
        "addr=%04X old=%02X new=%02X scene=%02X room=%02X camera=%04X",
        frame, gameplay_frame, pc, emu:read8(0xFF99), bc,
        ((bc - 0xA000) >> 2) & 0xFF, sp,
        emu:read8((sp + 1) & 0xFFFF), emu:read8(sp),
        info.address & 0xFFFF, info.oldValue & 0xFF, value,
        emu:read8(0xD880), emu:read8(0xFFBD),
        emu:read8(0xDC02) | (emu:read8(0xDC03) << 8))
end

assert(emu:setRangeWatchpoint(
    on_write, 0xC1A0, 0xC3E0, C.WATCHPOINT_TYPE.WRITE_CHANGE) > 0)
assert(emu:setRangeWatchpoint(function(info)
    local pc = register("PC") & 0xFFFF
    gdma_writes[pc] = (gdma_writes[pc] or 0) + 1
end, 0xFF55, 0xFF56, C.WATCHPOINT_TYPE.WRITE) > 0)
assert(emu:setBreakpoint(function()
    if emu:read8(0xD880) ~= 0x02 or emu:read8(0xFF99) ~= 0x01 then return end
    local sp = register("SP") & 0xFFFF
    local return_address =
        emu:read8(sp) | (emu:read8((sp + 1) & 0xFFFF) << 8)
    local h = register("H") & 0xFF
    local source = emu:read8(0xDC0E) | (emu:read8(0xDC0F) << 8)
    local content_key = ((emu:read8(0xDC0E) ~ emu:read8(0xC297) ~
        emu:read8(0xC29B)) + 1) & 0xFF
    local key = string.format("%04X/H%02X/S%04X", return_address, h, source)
    copy_callers[key] = (copy_callers[key] or 0) + 1
    if #copy_events < EVENT_LIMIT then
        copy_events[#copy_events + 1] = string.format(
            "f=%d g=%d caller=%04X h=%02X source=%04X key=%02X scene=%02X room=%02X camera=%04X",
            frame, gameplay_frame, return_address, h, source, content_key,
            emu:read8(0xD880), emu:read8(0xFFBD),
            emu:read8(0xDC02) | (emu:read8(0xDC03) << 8))
    end
end, 0x42A7) > 0)

local semantic_pcs = {}
local semantic_bank = tonumber(os.getenv("STAGE1_SEMANTIC_DEBUG_BANK") or "13")
for value in string.gmatch(os.getenv("STAGE1_SEMANTIC_DEBUG_PCS") or "", "[^,]+") do
    semantic_pcs[#semantic_pcs + 1] = tonumber(value)
end
for _, semantic_pc in ipairs(semantic_pcs) do
    assert(emu:setBreakpoint(function()
        if (emu:read8(0xFF99) & 0xFF) ~= semantic_bank then return end
        semantic_counts[semantic_pc] =
            (semantic_counts[semantic_pc] or 0) + 1
        if #semantic_events >= EVENT_LIMIT then return end
        local sp = register("SP") & 0xFFFF
        semantic_events[#semantic_events + 1] = string.format(
            "f=%d g=%d pc=%04X af=%04X bc=%04X de=%04X hl=%04X " ..
            "sp=%04X ret=%02X%02X f8=%02X fa=%02X fb=%02X fe=%02X " ..
            "svbk=%02X bank=%02X",
            frame, gameplay_frame, semantic_pc,
            register("AF") & 0xFFFF, register("BC") & 0xFFFF,
            register("DE") & 0xFFFF, register("HL") & 0xFFFF,
            sp, emu:read8((sp + 1) & 0xFFFF), emu:read8(sp),
            emu:read8(0xD3F8), emu:read8(0xD3FA),
            emu:read8(0xD3FB), emu:read8(0xD3FE),
            emu:read8(0xFF70), emu:read8(0xFF99))
    end, semantic_pc) > 0)
end

local function finish(reason)
    if stopped then return end
    stopped = true
    emu:setKeys(0)
    local handle = assert(io.open(OUT, "w"))
    handle:write("reason=" .. reason .. "\n")
    handle:write(string.format("frames=%d\n", frame))
    handle:write(string.format("gameplay_frames=%d\n", gameplay_frame))
    handle:write(string.format("event_count=%d\n", #events))
    local pcs = {}
    for pc, count in pairs(pc_counts) do
        pcs[#pcs + 1] = {pc = pc, count = count}
    end
    table.sort(pcs, function(a, b)
        if a.count ~= b.count then return a.count > b.count end
        return a.pc < b.pc
    end)
    for _, item in ipairs(pcs) do
        handle:write(string.format("pc=%04X count=%d\n", item.pc, item.count))
    end
    local callers = {}
    for key, count in pairs(copy_callers) do
        callers[#callers + 1] = {key = key, count = count}
    end
    table.sort(callers, function(a, b) return a.key < b.key end)
    for _, item in ipairs(callers) do
        handle:write(string.format(
            "copy_caller=%s count=%d\n", item.key, item.count))
    end
    for _, event in ipairs(copy_events) do
        handle:write("copy_event " .. event .. "\n")
    end
    for pc, count in pairs(gdma_writes) do
        handle:write(string.format("gdma_pc=%04X count=%d\n", pc, count))
    end
    for pc, count in pairs(semantic_counts) do
        handle:write(string.format(
            "semantic_pc=%04X count=%d\n", pc, count))
    end
    for _, event in ipairs(semantic_events) do
        handle:write("semantic_event " .. event .. "\n")
    end
    for _, event in ipairs(events) do handle:write("event " .. event .. "\n") end
    handle:close()
    local metatiles = assert(io.open(OUT .. ".a000.bin", "wb"))
    for offset = 0, 0x3FF do
        metatiles:write(string.char(emu:read8(0xA000 + offset)))
    end
    metatiles:close()
    os.exit(0)
end

callbacks:add("frame", function()
    frame = frame + 1
    local scene = emu:read8(0xD880)
    local active = emu:read8(0xFFC1)
    local keys = 0
    if first_gameplay == nil then
        keys = keys | pulse(180, 186, KEY_DOWN)
        keys = keys | pulse(201, 207, KEY_A)
        keys = keys | pulse(261, 267, KEY_A)
        keys = keys | pulse(321, 327, KEY_A)
        keys = keys | pulse(381, 387, KEY_START)
        keys = keys | pulse(431, 437, KEY_A)
        if scene == 0x02 and active == 1 then
            first_gameplay = frame
            trace_offset = frame - trace_first_frame
        end
    else
        gameplay_frame = gameplay_frame + 1
        local source_frame = frame - trace_offset
        if trace_keys[source_frame] ~= nil then
            trace_key = trace_keys[source_frame]
        end
        keys = trace_key
        if gameplay_frame >= PLAY_LIMIT then
            finish("play_limit")
            return
        end
    end
    emu:setKeys(keys)
    if frame >= LIMIT then finish("frame_limit") end
end)
