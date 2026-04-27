-- Trivial bot: spin in a circle + spam A. Should kill Gargoyle if combat works at all.
local f = 0
local lastDCBB = 0xFF
local startDCBB = 0xFF
local startFrame = 0
local seenSpawn = false
local killFrame = -1
local lastHpDrop = 0

-- Title nav copied from autoplay
local KEY_A=0x01; local KEY_B=0x02; local KEY_START=0x08
local KEY_RIGHT=0x10; local KEY_LEFT=0x20; local KEY_UP=0x40; local KEY_DOWN=0x80
local TITLE = {
    {180,185,KEY_DOWN},{193,198,KEY_A},{241,246,KEY_A},
    {291,296,KEY_A},{341,346,KEY_START},{391,396,KEY_A},
}

local logFile = io.open("/tmp/spin_shoot_test.log", "w")
local function log(s) logFile:write(s.."\n"); logFile:flush(); console:log(s) end

local DIRS = {KEY_RIGHT, KEY_RIGHT+KEY_DOWN, KEY_DOWN, KEY_LEFT+KEY_DOWN,
              KEY_LEFT, KEY_LEFT+KEY_UP, KEY_UP, KEY_RIGHT+KEY_UP}

callbacks:add("frame", function()
    f = f + 1

    -- Title menu
    if f <= 500 then
        local k = 0
        for _,e in ipairs(TITLE) do
            if f>=e[1] and f<=e[2] then k=e[3]; break end
        end
        emu:setKeys(k)
        return
    end

    if not seenSpawn then
        -- Force gargoyle spawn (DCB8=2 entry)
        emu:write8(0xFFBF, 0)
        emu:write8(0xDCB8, 0)
        emu:write8(0xDCBA, 0x01)
        emu:write8(0xFFD6, 0x1E)
        emu:write8(0xDCBB, 0xFF)
        for _, a in ipairs({0xDC85,0xDC8D,0xDC95,0xDC9D,0xDCA5}) do
            emu:write8(a, 0x00)
        end
        if emu:read8(0xFFBF) ~= 0 then
            seenSpawn = true
            startFrame = f
            startDCBB = emu:read8(0xDCBB)
            log(string.format("f=%d SPAWNED FFBF=0x%02X DCBB=0x%02X DC04=0x%02X",
                f, emu:read8(0xFFBF), startDCBB, emu:read8(0xDC04)))
        end
        return
    end

    -- Force the boss alive each frame (defensive)
    emu:write8(0xDCBA, 0x01)
    emu:write8(0xFFD6, 0x1E)

    -- Strategy: spin direction every 30 frames, spam A every other frame
    local dirIdx = math.floor(f/30) % 8 + 1
    local k = DIRS[dirIdx]
    if f % 2 == 0 then k = k + KEY_A end
    emu:setKeys(k)

    -- Detect DCBB drops
    local cur = emu:read8(0xDCBB)
    if cur < lastDCBB then
        log(string.format("f=%d DCBB drop 0x%02X -> 0x%02X (delta=%d)", f, lastDCBB, cur, lastDCBB-cur))
        lastHpDrop = f
    end
    if cur > lastDCBB and cur > 0 then
        -- HP rebound (phase change)
        log(string.format("f=%d DCBB rebound 0x%02X -> 0x%02X (phase change)", f, lastDCBB, cur))
    end
    lastDCBB = cur

    -- Detect kill: D880 transitions to 0x17 OR DCBB=0
    local d880 = emu:read8(0xD880)
    if d880 == 0x17 and killFrame < 0 then
        killFrame = f
        log(string.format("f=%d KILLED — D880=0x17 (death cinematic)  total %d frames in combat", f, f-startFrame))
    end

    -- Periodic status
    if f % 600 == 0 then
        log(string.format("f=%d combat_t=%ds DCBB=0x%02X D880=0x%02X FFBF=0x%02X last_hit_ago=%d",
            f, math.floor((f-startFrame)/60), cur, d880, emu:read8(0xFFBF), f-lastHpDrop))
    end

    -- Stop conditions
    if killFrame > 0 and f - killFrame > 300 then
        log(string.format("=== DONE: killed at f=%d (%ds combat) ===", killFrame, math.floor((killFrame-startFrame)/60)))
        logFile:close(); emu:stop()
    end
    if f - startFrame > 18000 then  -- 5 min combat timeout
        log(string.format("=== TIMEOUT: 5 min combat, never killed. final DCBB=0x%02X ===", cur))
        logFile:close(); emu:stop()
    end
end)

log("spin+shoot test started")
