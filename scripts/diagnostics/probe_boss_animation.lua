-- Capture a long, native-animation boss receipt without changing its motion.
-- The Python owner launches this only through mgba-qt-singleflight.

local OUT = assert(os.getenv("BOSS_ANIMATION_OUT"), "BOSS_ANIMATION_OUT required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_ANIMATION_SCENE") or "15")
local FRAMES = tonumber(os.getenv("BOSS_ANIMATION_FRAMES") or "3600")
local STEP = tonumber(os.getenv("BOSS_ANIMATION_STEP") or "2")
local TRACE_STEP = tonumber(os.getenv("BOSS_ANIMATION_TRACE_STEP") or "1")
local FLUSH_FRAMES = 20
local frame, captured, finished = 0, 0, false
local trace = assert(io.open(OUT .. ".trace", "w"))

local function register(name)
    local accessors = {
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }
    for _, accessor in ipairs(accessors) do
        local ok, value = pcall(accessor)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

pcall(function()
    emu:setRangeWatchpoint(function(info)
        trace:write(string.format(
            "scene-write frame=%d pc=%04X old=%02X new=%02X df4c=%02X ff91=%02X\n",
            frame, register("PC"), info.oldValue & 0xFF, info.newValue & 0xFF,
            emu:read8(0xDF4C), emu:read8(0xFF91)))
        trace:flush()
    end, 0xD880, 0xD880, C.WATCHPOINT_TYPE.WRITE_CHANGE)
end)

local function finish(status)
    if finished then return end
    finished = true
    trace:write(string.format(
        "complete status=%s frames=%d captures=%d scene=%02X\n",
        status, frame, captured, emu:read8(0xD880)))
    trace:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    emu:setKeys(0)

    -- Keep both contestants alive so the receipt observes animation rather
    -- than a boss-exit cut. These writes do not alter boss pose or timing.
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)

    if emu:read8(0xD880) ~= EXPECTED_SCENE then
        finish("wrong-scene")
        return
    end
    if frame <= FRAMES and frame % STEP == 0 then
        captured = captured + 1
        emu:screenshot(OUT .. string.format(".f%04d.png", frame))
    end
    if frame % TRACE_STEP == 0 then
        trace:write(string.format(
            "frame=%d pc=%04X scene=%02X lcdc=%02X scx=%02X scy=%02X " ..
            "df4c=%02X ff91=%02X dcbb=%02X d888=%02X dd06=%02X\n",
            frame, register("PC"), emu:read8(0xD880), emu:read8(0xFF40),
            emu:read8(0xFF43), emu:read8(0xFF42),
            emu:read8(0xDF4C), emu:read8(0xFF91), emu:read8(0xDCBB),
            emu:read8(0xD888), emu:read8(0xDD06)))
        trace:flush()
    end
    if frame >= FRAMES + FLUSH_FRAMES then finish("ok") end
end)
