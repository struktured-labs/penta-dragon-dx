-- Probe OBJ CRAM from a savestate that's already in gameplay.
-- Loads the savestate, advances 10 frames for settling, then dumps.

local OUT = os.getenv("PROBE_OUT") or "/tmp/savestate_cram.json"
local frame_count = 0
local capture_done = false

local function dump_cram()
    local result = {}
    result.frame = frame_count

    -- Game state
    result.d880 = emu:read8(0xD880)
    result.ffc1 = emu:read8(0xFFC1)
    result.ffbe = emu:read8(0xFFBE)

    -- OBJ CRAM
    local accessor = emu.memory.cgbObjPalette
    if accessor then
        local raw = accessor:readRange(0, 64)
        result.source = "cgbObjPalette"
        result.obj_pal = {}
        for i = 1, 64 do
            result.obj_pal[i] = raw:byte(i)
        end
    else
        result.source = "FF6A"
        result.obj_pal = {}
        for slot = 0, 7 do
            for i = 0, 7 do
                emu:write8(0xFF6A, 0x80 | (slot << 2) | i)
                result.obj_pal[slot * 8 + i + 1] = emu:read8(0xFF6B)
            end
        end
    end

    -- OAM (all sprites)
    result.oam = {}
    for i = 0, 39 do
        local base = 0xFE00 + i * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local attr = emu:read8(base + 3)
        result.oam[i + 1] = {y = y, x = x, tile = tile, attr = attr,
                             pal = attr & 0x07}
    end

    -- Save as JSON
    local f = io.open(OUT, "w")
    f:write('{"frame":' .. tostring(result.frame))
    f:write(',"d880":' .. tostring(result.d880))
    f:write(',"ffc1":' .. tostring(result.ffc1))
    f:write(',"ffbe":' .. tostring(result.ffbe))
    f:write(',"source":"' .. result.source .. '"')
    f:write(',"obj_pal":[')
    for i, v in ipairs(result.obj_pal) do
        if i > 1 then f:write(",") end
        f:write(tostring(v))
    end
    f:write(']')
    f:write(',"oam":[')
    for i, o in ipairs(result.oam) do
        if i > 1 then f:write(",") end
        f:write('{"x":' .. tostring(o.x) .. ',"y":' .. tostring(o.y)
                .. ',"tile":' .. tostring(o.tile)
                .. ',"attr":' .. tostring(o.attr)
                .. ',"pal":' .. tostring(o.pal) .. '}')
    end
    f:write(']}')
    f:close()
end

callbacks:add("frame", function()
    frame_count = frame_count + 1

    -- Just advance frames, no key presses (savestate already in gameplay)
    if frame_count == 10 then
        dump_cram()
        emu:stop()
    end
end)
