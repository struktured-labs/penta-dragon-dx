-- Capture CRAM very early (frame 10, 20, 40) to see when corruption starts
local OUT = os.getenv("PROBE_OUT") or "/tmp/early_cram.json"
local f = 0

local CAPTURES = {10, 20, 40, 80, 160}

local function dump_cram()
    local result = {}
    result.frame = f
    result.d880 = emu:read8(0xD880)
    result.ffc1 = emu:read8(0xFFC1)

    local accessor = emu.memory.cgbObjPalette
    if accessor then
        local raw = accessor:readRange(0, 64)
        result.obj_cram = {}
        for i = 1, 64 do
            result.obj_cram[i] = raw:byte(i)
        end
    else
        result.obj_cram = {}
        for slot = 0, 7 do
            for byte_off = 0, 7 do
                local idx = 0x80 | (slot * 8 + byte_off)
                emu:write8(0xFF6A, idx)
                result.obj_cram[slot * 8 + byte_off + 1] = emu:read8(0xFF6B)
            end
        end
    end
    return result
end

callbacks:add("frame", function()
    f = f + 1
    emu:setKeys(0)

    for _, cf in ipairs(CAPTURES) do
        if f == cf then
            local r = dump_cram()
            local fh = io.open(OUT, "w")
            fh:write('{"frame":' .. tostring(r.frame))
            fh:write(',"d880":' .. tostring(r.d880))
            fh:write(',"ffc1":' .. tostring(r.ffc1))
            fh:write(',"obj_cram":[')
            for i, v in ipairs(r.obj_cram) do
                if i > 1 then fh:write(",") end
                fh:write(tostring(v))
            end
            fh:write(']}')
            fh:close()
        end
    end

    if f >= 200 then
        emu:stop()
    end
end)
