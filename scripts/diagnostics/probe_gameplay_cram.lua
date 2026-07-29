-- Probe OBJ CRAM during gameplay — presses through title screen, enters
-- gameplay, then captures CRAM and dumps to JSON.
-- NOTE: FF6A/FF6B protocol uses bit 6 for auto-increment!
-- Bit 7=1 selects OBJ palette. Bit 6=1 enables auto-increment on read.

local OUT = os.getenv("PROBE_OUT") or "/tmp/gameplay_cram.json"
local frame_count = 0

local KEY_DOWN = 0x80
local KEY_A = 0x01
local KEY_START = 0x08

callbacks:add("frame", function()
    frame_count = frame_count + 1

    if frame_count >= 180 and frame_count <= 185 then
        emu:setKeys(KEY_DOWN)
    elseif frame_count >= 190 and frame_count <= 195 then
        emu:setKeys(KEY_A)
    elseif frame_count >= 200 and frame_count <= 205 then
        emu:setKeys(KEY_START)
    elseif frame_count >= 280 and frame_count <= 285 then
        emu:setKeys(KEY_A)
    elseif frame_count == 360 then
        -- Capture CRAM via FF6A/FF6B with auto-increment
        local pal = {}

        -- Read OBJ palettes (bit7=1, bit6=1 for auto-increment)
        for slot = 0, 7 do
            emu:write8(0xFF6A, 0xC0 | (slot << 2))  -- 0xC0 = bit7|bit6
            local base = slot * 8
            for i = 0, 7 do
                pal[base + i + 1] = emu:read8(0xFF6B)
            end
        end

        local f = io.open(OUT, "w")
        f:write('{"source":"FF6A","obj_pal":[')
        for i, v in ipairs(pal) do
            if i > 1 then f:write(",") end
            f:write(tostring(v))
        end
        f:write(']}')
        f:close()

        emu:stop()
    else
        emu:setKeys(0)
    end
end)
