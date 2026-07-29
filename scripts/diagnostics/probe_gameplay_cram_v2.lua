-- Probe OBJ CRAM + OAM during gameplay.
-- Uses emu.memory.cgbObjPalette if available (preferred).
-- Tries at multiple frame counts to catch the loaded state.

local OUT = os.getenv("PROBE_OUT") or "/tmp/gameplay_cram_v2.json"
local frame_count = 0

local KEY_DOWN = 0x80
local KEY_A = 0x01
local KEY_START = 0x08
local KEY_UP = 0x40
local KEY_LEFT = 0x20

local capture_done = false

-- Try multiple capture points
local CAPTURE_FRAMES = {360, 420, 480, 540, 600}

local function capture_cram()
    local result = {}
    result.source = "unknown"

    -- Try mGBA native accessor first
    local accessor = emu.memory.cgbObjPalette
    if accessor ~= nil then
        local raw = accessor:readRange(0, 64)
        result.source = "cgbObjPalette"
        result.obj_pal = {}
        for i = 1, 64 do
            result.obj_pal[i] = raw:byte(i)
        end
    else
        -- Fallback: read each OBJ palette slot via FF6A/FF6B
        -- On each slot write, FF6A = 0x80 | (slot << 2), auto-inc bit 6 = 0
        -- Read 8 bytes via FF6B, writing slot addr each time
        result.obj_pal = {}
        for slot = 0, 7 do
            for i = 0, 7 do
                emu:write8(0xFF6A, 0x80 | (slot << 2) | i)
                result.obj_pal[slot * 8 + i + 1] = emu:read8(0xFF6B)
            end
        end
        result.source = "FF6A"
    end

    -- Read OAM for HW palette attributes
    result.oam = {}
    for i = 0, 39 do
        local oam_base = 0xFE00 + i * 4
        local y = emu:read8(oam_base)
        local x = emu:read8(oam_base + 1)
        local tile = emu:read8(oam_base + 2)
        local attr = emu:read8(oam_base + 3)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            result.oam[#result.oam + 1] = {
                idx = i,
                y = y, x = x, tile = tile, attr = attr,
                pal = attr & 0x07,
                bank = (attr >> 3) & 0x01
            }
        end
    end

    -- Read D880 (scene state) and FFC1 (gameplay flag)
    result.d880 = emu:read8(0xD880)
    result.ffc1 = emu:read8(0xFFC1)
    result.frame = frame_count

    return result
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

    -- Capture at the specified frame
    for _, f in ipairs(CAPTURE_FRAMES) do
        if frame_count == f then
            local result = capture_cram()

            -- Append to output file (each capture gets its own key)
            local fh
            local existing = false
            local f_handle = io.open(OUT, "r")
            if f_handle then
                existing = true
                f_handle:close()
            end

            if existing then
                fh = io.open(OUT, "r")
                local content = fh:read("*all")
                fh:close()
                content = content:sub(1, -2)  -- remove trailing ]
                fh = io.open(OUT, "w")
                fh:write(content)
                fh:write(string.format(',"frame_%d":', f))
            else
                fh = io.open(OUT, "w")
                fh:write('{')
                fh:write(string.format('"frame_%d":', f))
            end

            fh:write('{"source":"' .. result.source .. '","obj_pal":[')
            for i, v in ipairs(result.obj_pal) do
                if i > 1 then fh:write(",") end
                fh:write(tostring(v))
            end
            fh:write('],"d880":' .. tostring(result.d880))
            fh:write(',"ffc1":' .. tostring(result.ffc1))
            fh:write(',"frame":' .. tostring(result.frame))
            fh:write(',"oam":[')
            for i, o in ipairs(result.oam) do
                if i > 1 then fh:write(",") end
                fh:write('{"idx":' .. tostring(o.idx) .. ',"y":' .. tostring(o.y)
                        .. ',"x":' .. tostring(o.x)
                        .. ',"tile":' .. tostring(o.tile)
                        .. ',"pal":' .. tostring(o.pal)
                        .. ',"bank":' .. tostring(o.bank) .. '}')
            end
            fh:write(']}')  -- close frame capture object
            fh:write(']}')  -- close top-level
            fh:close()

            if f == CAPTURE_FRAMES[#CAPTURE_FRAMES] then
                -- Final capture
                emu:stop()
            end
        end
    end
end)
