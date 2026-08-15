-- Capture Ted's packed 24x24 source beside both native physical BG maps.
-- This establishes the renderer's source-to-map transform without embedding
-- or guessing any stock graphics in the Python-side contract.

local OUT = assert(os.getenv("TED_SOURCE_MAP_OUT"))
local FRAMES = tonumber(os.getenv("TED_SOURCE_MAP_FRAMES") or "600")
local SCENE, SOURCE = 0x10, 0xC1A0
local STOCK_ROM = os.getenv("TED_SOURCE_MAP_STOCK") == "1"
local CLEAR_LOWER_ONCE = os.getenv("TED_SOURCE_MAP_CLEAR_LOWER") == "1"
local frame, samples, finished = 0, 0, false
local trace = assert(io.open(OUT .. ".bin", "wb"))

local function byte(value) return string.char(value & 0xFF) end

local function finish(status)
    if finished then return end
    finished = true
    trace:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write(string.format("status=%s frames=%d samples=%d\n",
        status, frame, samples))
    done:close()
    os.exit(status == "ok" and 0 or 1)
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    emu:setKeys(0)
    if not STOCK_ROM then
        local svbk = emu:read8(0xFF70) & 0x07
        if svbk ~= 0 and svbk ~= 1 then return end
    end
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0)
    emu:write8(0xDD06, 0)
    if emu:read8(0xD880) ~= SCENE then finish("wrong-scene"); return end
    if CLEAR_LOWER_ONCE and samples == 0 then
        for row = 14, 23 do
            for column = 0, 23 do
                local floor = 0x77 + 2 * (row & 1) + (column & 1)
                emu:write8(SOURCE + row * 24 + column, floor)
                local old_vbk = emu:read8(0xFF4F)
                emu:write8(0xFF4F, 0)
                emu:write8(0x9800 + row * 32 + column, floor)
                emu:write8(0x9C00 + row * 32 + column, floor)
                emu:write8(0xFF4F, old_vbk)
            end
        end
    end

    trace:write(byte(emu:read8(0xFF40)))
    trace:write(byte(emu:read8(0xFF42)))
    trace:write(byte(emu:read8(0xFF43)))
    trace:write(byte(emu:read8(0xFF91)))
    for offset = 0, 24 * 24 - 1 do
        trace:write(byte(emu:read8(SOURCE + offset)))
    end
    local old_vbk = 0
    if not STOCK_ROM then
        old_vbk = emu:read8(0xFF4F)
        emu:write8(0xFF4F, 0)
    end
    for _, base in ipairs({0x9800, 0x9C00}) do
        for offset = 0, 0x3FF do
            trace:write(byte(emu:read8(base + offset)))
        end
    end
    if not STOCK_ROM then emu:write8(0xFF4F, old_vbk) end
    samples = samples + 1
    if samples >= FRAMES then finish("ok") end
end)
