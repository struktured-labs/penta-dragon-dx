-- Traverse the verified secret-jet state with controller input and retain
-- phase/room/miniboss screenshots. Only player survivability is assisted;
-- progression, enemy HP, room changes, and boss flags remain game-owned.

local OUT = assert(os.getenv("HIDDEN_SHMUP_OUT"), "HIDDEN_SHMUP_OUT required")
local SHOT_PREFIX = assert(os.getenv("HIDDEN_SHMUP_SHOT_PREFIX"),
    "HIDDEN_SHMUP_SHOT_PREFIX required")
local FRAMES = tonumber(os.getenv("HIDDEN_SHMUP_FRAMES") or "24000")
local PERIOD = tonumber(os.getenv("HIDDEN_SHMUP_CAPTURE_EVERY") or "1200")

local KEY_A, KEY_RIGHT, KEY_LEFT, KEY_UP, KEY_DOWN = 0x01, 0x10, 0x20, 0x40, 0x80
local frame = 0
local last_signature = ""
local transitions = {}
local screenshots = 0

local function signature()
    return string.format("%02X/%d/%02X/%02X/%02X/%02X/%02X",
        emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFBA),
        emu:read8(0xFFBF), emu:read8(0xFFD0), emu:read8(0xFFBD),
        emu:read8(0xDCB8))
end

local function capture(kind)
    screenshots = screenshots + 1
    emu:screenshot(string.format("%s-%s-f%05d-%02d.png",
        SHOT_PREFIX, kind, frame, screenshots))
end

local function finish()
    local handle = assert(io.open(OUT, "w"))
    handle:write("frame\tsignature\n")
    for _, row in ipairs(transitions) do handle:write(row .. "\n") end
    handle:write(string.format("final\t%d\t%s\n", frame, signature()))
    handle:write(string.format("screenshots\t%d\n", screenshots))
    handle:close()
    local done = assert(io.open(OUT .. ".done", "w"))
    done:write("ok\n")
    done:close()
    os.exit(0)
end

callbacks:add("frame", function()
    frame = frame + 1

    -- Reinitialize palette/cache state from the candidate ROM rather than the
    -- historical state's serialized tables.
    if frame <= 40 then
        emu:write8(0xDF02, 0)
        emu:write8(0xDF00, 0)
    end
    if frame == 1 then emu:write8(0xDF0D, 0xFF) end

    -- Keep Sara alive. DCBB is game-owned during minibosses, so only refresh
    -- its corridor-timer role while no miniboss is active.
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    if emu:read8(0xFFBF) == 0 then emu:write8(0xDCBB, 0xFF) end

    -- Sweep a wide rectangle while firing. This is controller input, not a
    -- scene/state redirect, and lets native collision/progression logic run.
    local phase = math.floor((frame - 1) / 360) % 4
    local direction = KEY_RIGHT
    if phase == 1 then direction = KEY_DOWN
    elseif phase == 2 then direction = KEY_LEFT
    elseif phase == 3 then direction = KEY_UP end
    emu:setKeys(KEY_A + direction)

    local current = signature()
    if current ~= last_signature then
        transitions[#transitions + 1] = string.format("%d\t%s", frame, current)
        last_signature = current
        if frame > 45 then capture("transition") end
    elseif frame == 120 or frame % PERIOD == 0 then
        capture("periodic")
    end

    if frame >= FRAMES then finish() end
end)
