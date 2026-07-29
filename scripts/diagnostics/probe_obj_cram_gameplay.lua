-- OBJ CRAM probe during gameplay.
-- Uses the same auto-press sequence as gameplay_palette.lua.
-- Outputs OBJ CRAM + OAM to PROBE_OUT (JSON).

local OUT = os.getenv("PROBE_OUT") or "/tmp/obj_cram_gameplay.json"
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES") or "1200")
local SETTLE_FRAMES = tonumber(os.getenv("SETTLE_FRAMES") or "120")

local KEY_A     = 0x01
local KEY_DOWN  = 0x80
local KEY_START = 0x08
local SCHEDULE = {
    {180, 185, KEY_DOWN}, {186, 200, 0},
    {201, 206, KEY_A},    {207, 260, 0},
    {261, 266, KEY_A},    {267, 320, 0},
    {321, 326, KEY_A},    {327, 380, 0},
    {381, 386, KEY_START}, {387, 430, 0},
    {431, 436, KEY_A},
}

local f = 0
local gameplay_at = -1
local fired = false

local function dump()
    local result = {}
    result.frame = f
    result.ffc1 = emu:read8(0xFFC1)
    result.d880 = emu:read8(0xD880)
    result.ffbe = emu:read8(0xFFBE)
    result.ffbf = emu:read8(0xFFBF)

    -- OBJ CRAM via cgbObjPalette (preferred) or FF6A
    local accessor = emu.memory.cgbObjPalette
    if accessor then
        local raw = accessor:readRange(0, 64)
        result.source = "cgbObjPalette"
        result.obj_cram = {}
        for i = 1, 64 do
            result.obj_cram[i] = raw:byte(i)
        end
    else
        result.source = "FF6A"
        result.obj_cram = {}
        for slot = 0, 7 do
            -- FF6A: bits 0-5 = byte index (0-63). Each OBJ palette = 8 bytes.
            -- Read each byte individually (no auto-increment) to avoid side effects.
            for byte_off = 0, 7 do
                local idx = 0x80 | (slot * 8 + byte_off)  -- bit7=1 for safe read (mGBA may require it)
                emu:write8(0xFF6A, idx)
                result.obj_cram[slot * 8 + byte_off + 1] = emu:read8(0xFF6B)
            end
        end
    end

    -- OAM visible sprites
    result.oam = {}
    for i = 0, 39 do
        local base = 0xFE00 + i * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local attr = emu:read8(base + 3)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            result.oam[#result.oam + 1] = {
                idx = i, x = x, y = y, tile = tile,
                attr = attr, pal = attr & 0x07
            }
        end
    end

    -- Write JSON
    local fh = io.open(OUT, "w")
    fh:write('{"frame":' .. tostring(result.frame))
    fh:write(',"ffc1":' .. tostring(result.ffc1))
    fh:write(',"d880":' .. tostring(result.d880))
    fh:write(',"ffbe":' .. tostring(result.ffbe))
    fh:write(',"ffbf":' .. tostring(result.ffbf))
    fh:write(',"source":"' .. result.source .. '"')
    fh:write(',"obj_cram":[')
    for i, v in ipairs(result.obj_cram) do
        if i > 1 then fh:write(",") end
        fh:write(tostring(v))
    end
    fh:write(']')
    fh:write(',"oam":[')
    for i, o in ipairs(result.oam) do
        if i > 1 then fh:write(",") end
        fh:write('{"idx":' .. tostring(o.idx) .. ',"x":' .. tostring(o.x)
                .. ',"y":' .. tostring(o.y)
                .. ',"tile":' .. tostring(o.tile)
                .. ',"pal":' .. tostring(o.pal) .. '}')
    end
    fh:write(']}')
    fh:close()
end

callbacks:add("frame", function()
    f = f + 1

    -- Auto-press sequence based on SCHEDULE
    local keys = 0
    for _, s in ipairs(SCHEDULE) do
        if f >= s[1] and f <= s[2] then
            keys = s[3]
            break
        end
    end
    emu:setKeys(keys)

    -- Detect dungeon gameplay (D880 == 0x02)
    local ffc1 = emu:read8(0xFFC1)
    local d880 = emu:read8(0xD880)
    if d880 == 0x02 and gameplay_at < 0 and f > 50 then
        gameplay_at = f
        console:log("gameplay detected at frame " .. f)
    end

    -- Dump after settle
    if gameplay_at > 0 and not fired and f >= gameplay_at + SETTLE_FRAMES then
        dump()
        fired = true
        console:log("CRAM dumped at frame " .. f)
    end

    if f >= MAX_FRAMES then
        if not fired then dump() end  -- dump even if gameplay never reached
        emu:stop()
    end
end)
