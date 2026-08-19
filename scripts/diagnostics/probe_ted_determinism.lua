-- Deterministic full-plane Ted trace. Capture both 32x32 physical BG maps on
-- every consecutive frame; Python owns all interpretation and comparison.

local OUT = assert(os.getenv("TED_DETERMINISM_OUT"))
local FRAMES = tonumber(os.getenv("TED_DETERMINISM_FRAMES") or "900")
-- Serialized boss fixtures can resume just before the inactive-map rebuild.
-- Exclude that fixture-only handoff; all requested samples remain consecutive.
local WARMUP = tonumber(os.getenv("TED_DETERMINISM_WARMUP") or "36")
local SCENE = 0x10
local REINSTALL_RUNTIME = os.getenv("TED_DETERMINISM_REINSTALL") == "1"
local LUA_SANITIZE = os.getenv("TED_DETERMINISM_LUA_SANITIZE") == "1"
local DEBUG = os.getenv("TED_DETERMINISM_DEBUG") == "1"
local frame, samples, finished = 0, 0, false
local trace = assert(io.open(OUT .. ".bin", "wb"))
local debug_trace = DEBUG and assert(io.open(OUT .. ".debug.tsv", "w")) or nil
if debug_trace then
    debug_trace:write(
        "frame\tscene\tsvbk\tcount\tmarker\ttile\tsource_sparse" ..
        "\tcount98\tcount9c\tphase\tmap\tffa9\tanchor_row\tanchor_col" ..
        "\ttoken_b2\ttoken_b3\ttoken_b4\ttoken_b5\ttoken_b6\ttoken_b7" ..
        "\tcache_body\tcache_sparse\tmap98_body\tmap9c_body" ..
        "\tmap98_cache_diff\tmap9c_cache_diff\tsp\tpc\n")
end

local function byte(value) return string.char(value & 0xFF) end

local numbered = {}
local tentacle_poses = {
    {},
    {{0x84,5,-3},{0x86,5,6},{0x83,10,-3}},
    {
        {0x7B,-5,8},{0x7D,-5,9},{0x83,-4,9},{0x7B,-3,7},
        {0x82,-3,8},{0x7B,-1,6},{0x82,-1,7},{0x85,-1,11},
        {0x83,0,6},{0x85,1,-8},{0x7B,1,9},{0x82,1,11},
        {0x7B,2,7},{0x82,2,9},{0x80,3,-8},{0x7D,3,-6},
        {0x84,3,6},{0x82,3,7},{0x80,4,-6},{0x7D,4,-4},
        {0x80,5,-4},{0x86,5,-3},
    },
}
do
    local spans = {{0,5},{-2,6},{-2,6},{-2,6},{-2,6},{-2,7},
        {-3,7},{-4,7},{-4,7},{-4,7},{-3,7},{-2,6},{0,6},{1,5}}
    local tile = 2
    for row, span in ipairs(spans) do
        for col = span[1], span[2] - 1 do
            numbered[tile] = {row - 1, col}; tile = tile + 1
        end
    end
end

local function signed5(value)
    value = value & 0x1F
    return value >= 16 and value - 32 or value
end

local function sanitize_active()
    if not LUA_SANITIZE then return end
    local base = (emu:read8(0xFF40) & 0x08) ~= 0 and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    emu:write8(0xFF4F, 0)
    local crown_row, crown_col = nil, nil
    for row = 0, 31 do
        for col = 0, 31 do
            local ok = true
            for step = 0, 4 do
                if emu:read8(base + row * 32 + ((col + step) & 31)) ~= 2 + step then
                    ok = false; break
                end
            end
            if ok then crown_row, crown_col = row, col end
        end
    end
    if crown_row == nil then emu:write8(0xFF4F, old_vbk); return end
    for row = 0, 31 do
        for col = 0, 31 do
            local address = base + row * 32 + col
            local tile = 0x77 + 2 * (row & 1) + (col & 1)
            emu:write8(address, tile)
            emu:write8(0xFF4F, 1)
            emu:write8(address, 6 + ((row ~ col) & 1))
            emu:write8(0xFF4F, 0)
        end
    end
    for tile = 2, 0x76 do
        local expected = numbered[tile]
        local row = (crown_row + expected[1]) & 31
        local col = (crown_col + expected[2]) & 31
        local address = base + row * 32 + col
        emu:write8(address, tile)
        emu:write8(0xFF4F, 1)
        emu:write8(address, ({1, 5, 2})[(tile % 3) + 1])
        emu:write8(0xFF4F, 0)
    end
    local pose = tentacle_poses[(math.floor(frame / 30) % #tentacle_poses) + 1]
    for _, cell in ipairs(pose) do
        local tile, relative_row, relative_col = cell[1], cell[2], cell[3]
        local row = (crown_row + relative_row) & 31
        local col = (crown_col + relative_col) & 31
        local address = base + row * 32 + col
        emu:write8(address, tile)
        emu:write8(0xFF4F, 1)
        emu:write8(address, ({1, 5, 2})[(tile % 3) + 1])
        emu:write8(0xFF4F, 0)
    end
    emu:write8(0xFF4F, old_vbk)
end

local function sample()
    local old_vbk = emu:read8(0xFF4F)
    local old_svbk = emu:read8(0xFF70)
    -- The corrected cached publisher starts at C4FA, so those bytes are now
    -- executable code rather than the retired sanitizer's anchor scratch.
    -- Its authoritative cached crown row/column live in bank-2 D706/D707.
    emu:write8(0xFF70, 2)
    local runtime_anchor_row = emu:read8(0xD706)
    local runtime_anchor_col = emu:read8(0xD707)
    emu:write8(0xFF70, old_svbk)
    trace:write(byte(emu:read8(0xFF40)))
    trace:write(byte(emu:read8(0xFF42)))
    trace:write(byte(emu:read8(0xFF43)))
    trace:write(byte(emu:read8(0xFF91)))
    trace:write(byte(runtime_anchor_row))
    trace:write(byte(runtime_anchor_col))
    trace:write(byte(emu:read8(0xDC0B)))
    for _, base in ipairs({0x9800, 0x9C00}) do
        emu:write8(0xFF4F, 0)
        for offset=0,0x3FF do trace:write(byte(emu:read8(base+offset))) end
        emu:write8(0xFF4F, 1)
        for offset=0,0x3FF do
            trace:write(byte(emu:read8(base+offset) & 0x07))
        end
    end
    emu:write8(0xFF4F, old_vbk)
    samples = samples + 1
end

local function finish(status)
    if finished then return end
    finished = true
    trace:close()
    if debug_trace then debug_trace:close() end
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write(string.format("status=%s frames=%d samples=%d scene=%02X\n",
        status, frame, samples, emu:read8(0xD880)))
    done:close()
    emu:stop()
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    if debug_trace then
        local old_svbk = emu:read8(0xFF70)
        emu:write8(0xFF70, 2)
        local count = emu:read8(0xD81F)
        local sparse_marker = emu:read8(0xD80C)
        local sparse_candidate = emu:read8(0xD80A)
        local count98 = emu:read8(0xD71F)
        local count9c = emu:read8(0xD77F)
        local limb_phase = emu:read8(0xD708)
        local anchor_row = emu:read8(0xD706)
        local anchor_col = emu:read8(0xD707)
        local tokens = {}
        for bank = 2, 7 do
            emu:write8(0xFF70, bank)
            tokens[#tokens + 1] = emu:read8(0xD71F)
        end
        emu:write8(0xFF70, 2)
        local cache_body, cache_sparse = 0, 0
        for address = 0xD000, 0xD3FF do
            local value = emu:read8(address)
            -- $77-$7A are Ted's checkerboard floor, not boss geometry.
            -- Count the numbered body ($02-$76) plus sparse tendrils
            -- ($7B-$86), matching the Python full-plane contract.
            if (value >= 0x02 and value < 0x77) or
                    (value >= 0x7B and value < 0x87) then
                cache_body = cache_body + 1
            end
            if value >= 0x7B and value < 0x87 then cache_sparse = cache_sparse + 1 end
        end
        local source_sparse = 0
        for address = 0xC1A0, 0xC3DF do
            local value = emu:read8(address)
            if value >= 0x7B and value < 0x87 then source_sparse = source_sparse + 1 end
        end
        local old_vbk = emu:read8(0xFF4F)
        emu:write8(0xFF4F, 0)
        local map98_body, map9c_body = 0, 0
        local map98_cache_diff, map9c_cache_diff = 0, 0
        for offset = 0, 0x3FF do
            local cached = emu:read8(0xD000 + offset)
            local tile98 = emu:read8(0x9800 + offset)
            local tile9c = emu:read8(0x9C00 + offset)
            if (tile98 >= 0x02 and tile98 < 0x77) or
                    (tile98 >= 0x7B and tile98 < 0x87) then
                map98_body = map98_body + 1
            end
            if (tile9c >= 0x02 and tile9c < 0x77) or
                    (tile9c >= 0x7B and tile9c < 0x87) then
                map9c_body = map9c_body + 1
            end
            if tile98 ~= cached then map98_cache_diff = map98_cache_diff + 1 end
            if tile9c ~= cached then map9c_cache_diff = map9c_cache_diff + 1 end
        end
        emu:write8(0xFF4F, old_vbk)
        emu:write8(0xFF70, old_svbk)
        local ok_sp, sp = pcall(function() return emu:getRegister("sp") end)
        local ok_pc, pc = pcall(function() return emu:getRegister("pc") end)
        debug_trace:write(string.format(
            "%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
            "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
            "\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
            "\t%d\t%d\t%d\t%d\t%d\t%d\t%04X\t%04X\n",
            frame, emu:read8(0xD880), old_svbk, count, sparse_marker,
            sparse_candidate, source_sparse, count98, count9c, limb_phase,
            emu:read8(0xFFA7), emu:read8(0xFFA9), anchor_row, anchor_col,
            tokens[1], tokens[2], tokens[3], tokens[4], tokens[5], tokens[6],
            cache_body, cache_sparse, map98_body, map9c_body,
            map98_cache_diff, map9c_cache_diff,
            ok_sp and sp or 0xFFFF, ok_pc and pc or 0xFFFF))
        debug_trace:flush()
    end
    -- Savestates retain the lazily installed C500 helper from the ROM that
    -- created them. Force the current candidate to reinstall its own runtime
    -- before the next publication; otherwise a byte-identical old WRAM blob
    -- can make materially different ROM candidates produce identical traces.
    if frame == 1 and REINSTALL_RUNTIME then emu:write8(0xC5FF, 0) end
    emu:setKeys(0)
    local svbk = emu:read8(0xFF70) & 0x07
    if svbk ~= 0 and svbk ~= 1 then return end
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    -- D888/DD06 participate in Ted's native animation/publication state.
    -- Clearing them every frame produced a perfectly deterministic frozen
    -- pose and let stale serialized WRAM pass as if it were live coverage.
    -- Keep only the independently proven survival counters above.
    if emu:read8(0xD880) ~= SCENE then finish("wrong-scene"); return end
    if frame > WARMUP then sanitize_active(); sample() end
    if samples >= FRAMES then finish("ok") end
end)
