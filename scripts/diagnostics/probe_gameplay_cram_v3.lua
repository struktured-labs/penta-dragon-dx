-- Simple probe: wait until gameplay (FFC1=1), then dump CRAM + OAM + state.
-- Outputs plain text to PROBE_OUT.

local OUT = os.getenv("PROBE_OUT") or "/tmp/gameplay_cram_v3.txt"
local frame_count = 0

local KEY_DOWN = 0x80
local KEY_A = 0x01
local KEY_START = 0x08

local function dump()
    local lines = {}
    local n = 1

    lines[n] = "frame=" .. frame_count; n = n + 1
    lines[n] = "d880=0x" .. string.format("%02X", emu:read8(0xD880)); n = n + 1
    lines[n] = "ffc1=0x" .. string.format("%02X", emu:read8(0xFFC1)); n = n + 1
    lines[n] = "ffbe=0x" .. string.format("%02X", emu:read8(0xFFBE)); n = n + 1

    -- Read OBJ CRAM via cgbObjPalette accessor
    local accessor = emu.memory.cgbObjPalette
    if accessor then
        local raw = accessor:readRange(0, 64)
        local parts = {}
        for i = 1, 64 do
            parts[i] = string.format("%d", raw:byte(i))
        end
        lines[n] = "obj_cram=" .. table.concat(parts, ","); n = n + 1
    else
        -- Fallback: read each byte individually
        local parts = {}
        for slot = 0, 7 do
            for i = 0, 7 do
                emu:write8(0xFF6A, 0x80 | (slot << 2) | i)
                parts[slot * 8 + i + 1] = string.format("%d", emu:read8(0xFF6B))
            end
        end
        lines[n] = "obj_cram=" .. table.concat(parts, ","); n = n + 1
    end

    -- OAM dump (visible sprites only)
    local oam_parts = {}
    local oam_n = 1
    for i = 0, 39 do
        local base = 0xFE00 + i * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        local tile = emu:read8(base + 2)
        local attr = emu:read8(base + 3)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            oam_parts[oam_n] = string.format("%d:%d,%d,0x%02X,%d",
                                              i, x, y, tile, attr & 0x07)
            oam_n = oam_n + 1
        end
    end
    lines[n] = "oam=" .. table.concat(oam_parts, ";"); n = n + 1

    local f = io.open(OUT, "w")
    f:write(table.concat(lines, "\n"))
    f:write("\n")
    f:close()
end

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
    else
        emu:setKeys(0)
    end

    if frame_count == 400 or frame_count == 500 then
        dump()
    end

    if frame_count == 600 then
        emu:stop()
    end
end)
