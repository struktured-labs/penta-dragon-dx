-- Safe CRAM probe: write each FF6A index individually, no auto-increment.
-- Read ALL 64 bytes of OBJ CRAM.
-- Then read again to check consistency.

local OUT = os.getenv("PROBE_OUT") or "/tmp/cram_safe.json"
local KEY_DOWN = 0x80
local KEY_A = 0x01
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

local function read_cram()
    local result = {}
    for i = 0, 63 do
        -- Write FF6A with NO auto-increment (bit7=0), index = i
        emu:write8(0xFF6A, i)
        result[i + 1] = emu:read8(0xFF6B)
    end
    return result
end

local function dump()
    local cram1 = read_cram()
    local cram2 = read_cram()

    local fh = io.open(OUT, "w")
    fh:write('{"frame":' .. tostring(f))
    fh:write(',"d880":' .. tostring(emu:read8(0xD880)))
    fh:write(',"ffc1":' .. tostring(emu:read8(0xFFC1)))
    fh:write(',"cram1":[')
    for i, v in ipairs(cram1) do
        if i > 1 then fh:write(",") end
        fh:write(tostring(v))
    end
    fh:write(']')
    fh:write(',"cram2":[')
    for i, v in ipairs(cram2) do
        if i > 1 then fh:write(",") end
        fh:write(tostring(v))
    end
    fh:write(']')
    fh:write('}')
    fh:close()
end

callbacks:add("frame", function()
    f = f + 1
    local keys = 0
    for _, s in ipairs(SCHEDULE) do
        if f >= s[1] and f <= s[2] then keys = s[3]; break end
    end
    emu:setKeys(keys)
    local d880 = emu:read8(0xD880)
    if d880 == 0x02 and gameplay_at < 0 and f > 50 then
        gameplay_at = f
        console:log("gameplay at " .. f)
    end
    if gameplay_at > 0 and not fired and f >= gameplay_at + 60 then
        dump()
        fired = true
        console:log("dumped at " .. f)
    end
    if f >= 2000 and not fired then
        dump()
        emu:stop()
    end
end)
