-- Probe using ONLY the native cgbObjPalette accessor if available
local OUT = os.getenv("PROBE_OUT") or "/tmp/cram_accessor.json"
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

local function dump()
    local accessor = emu.memory.cgbObjPalette
    local source = "none"
    local obj_cram = {}

    if accessor then
        source = "cgbObjPalette"
        local raw = accessor:readRange(0, 64)
        for i = 1, 64 do
            obj_cram[i] = raw:byte(i)
        end
    else
        source = "unavailable"
        console:log("cgbObjPalette accessor NOT available!")
    end

    local fh = io.open(OUT, "w")
    fh:write('{"frame":' .. tostring(f))
    fh:write(',"d880":' .. tostring(emu:read8(0xD880)))
    fh:write(',"ffc1":' .. tostring(emu:read8(0xFFC1)))
    fh:write(',"source":"' .. source .. '"')
    fh:write(',"obj_cram":[')
    for i, v in ipairs(obj_cram) do
        if i > 1 then fh:write(",") end
        fh:write(tostring(v))
    end
    fh:write(']}')
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
    end
    if gameplay_at > 0 and not fired and f >= gameplay_at + 60 then
        dump()
        fired = true
    end
    if f >= 2000 and not fired then
        dump()
        emu:stop()
    end
end)
