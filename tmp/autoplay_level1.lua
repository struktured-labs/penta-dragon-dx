-- Penta Dragon Level 1 Auto-play Script v8.5
-- Position-aware, state-driven bot with entity scanning and progress tracking
--
-- Improvements over v7:
--   - Reads Sara's XY from OAM for position-aware movement
--   - Scans OAM slots 4-39 for enemies/projectiles/boss sprites
--   - Monitors DC81 (section scroll countdown) and FFD6 (progress) for stall detection
--   - Reactive state machine: explore/combat/stuck/boss/post_boss
--   - 6-phase oscillation breaker instead of random jitter
--   - Boss-specific combat with room boundary oscillation
-- v8.2: Corrected DD04/DD05 → DC81/FFCF (probe-verified real addresses)
-- v8.5: ROM patching to cycle through ALL 8 bosses (Gargoyle→Angela)

-- ============================================================
-- 1. CONSTANTS & CONFIGURATION
-- ============================================================

local BASE = "/home/struktured/projects/penta-dragon-dx-claude"
local LOG_PATH = BASE .. "/tmp/game_start_test/autoplay_log.txt"
local SCREENSHOT_DIR = BASE .. "/tmp/game_start_test"

local KEY_A      = 0x01
local KEY_B      = 0x02
local KEY_SELECT = 0x04
local KEY_START  = 0x08
local KEY_RIGHT  = 0x10
local KEY_LEFT   = 0x20
local KEY_UP     = 0x40
local KEY_DOWN   = 0x80

local OAM_BASE = 0xFE00
local SARA_SLOTS = {0, 1, 2, 3}
local ENEMY_SLOT_START = 4
local MAX_SPRITES = 40
local OAM_X_OFFSET = 8
local OAM_Y_OFFSET = 16

local ENTITY_BASE = 0xC200
local ENTITY_SIZE = 24
local ENTITY_MARKER = 0xFE
local MAX_ENTITIES = 10

-- Tile classification (from projectile_tile_mapping.md)
local ENEMY_PROJ_TILES = {[0x00]=true, [0x01]=true}
local SARA_PROJ_TILES = {[0x06]=true, [0x09]=true, [0x0A]=true, [0x0F]=true}
local EFFECT_TILE_MIN = 0x10
local EFFECT_TILE_MAX = 0x1F
local ENEMY_BODY_MIN = 0x30
local ENEMY_BODY_MAX = 0x7F

local MAX_SCREENSHOTS = 60
local MAX_RUNTIME = 54000  -- 15 min at 60fps
local MAX_SAVE_SLOT = 9

-- Boss progression via ROM patching
-- Level 1 spawn table in bank 13 (ROM offset 0x34024)
-- Header byte = 0x06 (6 entries), then 5 bytes per entry
-- Entries 2 and 5 are the boss slots (DCB8=2 and DCB8=5)
local BOSS_DC04 = {0x30, 0x35, 0x3A, 0x3F, 0x44, 0x49, 0x4E, 0x53}
local BOSS_NAMES = {"Gargoyle","Spider","Crimson","Ice","Void","Poison","Knight","Angela"}
local SPAWN_ENTRY2_ROM = 0x3402F  -- ROM address of entry 2's DC04 byte
local SPAWN_ENTRY5_ROM = 0x3403E  -- ROM address of entry 5's DC04 byte

-- Title menu schedule (verified working)
local TITLE_SCHEDULE = {
    {180, 185, KEY_DOWN}, {186, 200, 0}, {201, 206, KEY_A}, {207, 260, 0},
    {261, 266, KEY_A}, {267, 320, 0}, {321, 326, KEY_A}, {327, 380, 0},
    {381, 386, KEY_START}, {387, 430, 0}, {431, 436, KEY_A},
}

-- ============================================================
-- 2. STATE VARIABLES
-- ============================================================

local f = 0                -- frame counter
local gameStartFrame = 0
local gameState = "title_menu"
local stateEntryFrame = 0
local saveSlot = 1
local screenshotCount = 0
local roomChangeCount = 0
local bossKillCount = 0
local uniqueRooms = {}
local stuckPhase = 0
local lastOscBreakFrame = 0
local nextBossIndex = 1    -- tracks current pair base; advances by 2 after each entry5 kill
local lastPatchedKill = 0  -- guard: only patch ROM once per kill event
local uniqueBosses = {}    -- track which boss types we've encountered

-- Previous frame values for change detection
local prev = {
    room = 0, boss = 0, form = 0, ffc1 = 0, progress = 0,
    stage = 0, difficulty = 0, powerup = 0,
}

-- ============================================================
-- 3. LOGGING
-- ============================================================

local log = io.open(LOG_PATH, "w")
if not log then console:log("ERROR: cannot open log"); return end

local function logMsg(msg)
    local s = string.format("f%05d: %s", f, msg)
    log:write(s .. "\n"); log:flush()
    console:log(s)
end

local function stateStr(s)
    return string.format(
        "room=%02X boss=%02X form=%s prog=%02X dcb8=%d dc04=%02X dc81=%02X pw=%02X sara=(%d,%d)",
        s.room, s.boss, s.form == 0 and "W" or "D", s.progress,
        s.dcb8, s.dc04, s.dc81, s.powerup, s.saraX, s.saraY)
end

-- ============================================================
-- 4. SENSOR MODULE
-- ============================================================

local function readSensors()
    local s = {}
    s.ffc1     = emu:read8(0xFFC1)
    s.room     = emu:read8(0xFFBD)
    s.form     = emu:read8(0xFFBE)
    s.boss     = emu:read8(0xFFBF)
    s.powerup  = emu:read8(0xFFC0)
    s.stage    = emu:read8(0xFFD0)
    s.progress = emu:read8(0xFFD6)
    s.difficulty = emu:read8(0xFFBA)
    s.dc81     = emu:read8(0xDC81)  -- real section scroll counter (C8→0)
    s.ffcf     = emu:read8(0xFFCF)  -- scroll position / section index
    s.dc04     = emu:read8(0xDC04)  -- section descriptor byte 0 (boss if >= 0x30)
    s.dcb8     = emu:read8(0xDCB8) -- section cycle counter (Gargoyle=2, Spider=5 for FFBA=0)
    s.hp       = emu:read8(0xDCDD)

    -- Sara position from OAM (average visible slots)
    local sx, sy, n = 0, 0, 0
    for _, slot in ipairs(SARA_SLOTS) do
        local addr = OAM_BASE + slot * 4
        local y = emu:read8(addr)
        local x = emu:read8(addr + 1)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            sx = sx + (x - OAM_X_OFFSET)
            sy = sy + (y - OAM_Y_OFFSET)
            n = n + 1
        end
    end
    s.saraX = n > 0 and math.floor(sx / n) or 80
    s.saraY = n > 0 and math.floor(sy / n) or 72
    s.saraVisible = n > 0

    return s
end

-- ============================================================
-- 5. ENTITY SCANNER
-- ============================================================

local function scanEntities(state)
    local enemies = {}
    local projectiles = {}
    local bossSprites = {}

    for slot = ENEMY_SLOT_START, MAX_SPRITES - 1 do
        local addr = OAM_BASE + slot * 4
        local y = emu:read8(addr)
        local x = emu:read8(addr + 1)
        local tile = emu:read8(addr + 2)

        if y > 0 and y < 160 and x > 0 and x < 168 then
            local sx = x - OAM_X_OFFSET
            local sy = y - OAM_Y_OFFSET

            if ENEMY_PROJ_TILES[tile] then
                table.insert(projectiles, {x=sx, y=sy, tile=tile})
            elseif SARA_PROJ_TILES[tile] then
                -- our projectile, ignore
            elseif tile >= EFFECT_TILE_MIN and tile <= EFFECT_TILE_MAX then
                -- effects, ignore
            elseif tile >= ENEMY_BODY_MIN and tile <= ENEMY_BODY_MAX then
                if state.boss > 0 then
                    table.insert(bossSprites, {x=sx, y=sy, tile=tile})
                else
                    table.insert(enemies, {x=sx, y=sy, tile=tile})
                end
            end
        end
    end

    -- Count active entities from C200 markers
    local activeEntities = 0
    for i = 0, MAX_ENTITIES - 1 do
        local base = ENTITY_BASE + i * ENTITY_SIZE
        if emu:read8(base) == ENTITY_MARKER and
           emu:read8(base + 1) == ENTITY_MARKER and
           emu:read8(base + 2) == ENTITY_MARKER then
            activeEntities = activeEntities + 1
        end
    end

    -- Find nearest enemy and projectile to Sara
    local function dist(e)
        return math.sqrt((e.x - state.saraX)^2 + (e.y - state.saraY)^2)
    end

    local nearEnemy, nearEnemyDist = nil, 999
    local nearProj, nearProjDist = nil, 999

    for _, e in ipairs(enemies) do
        local d = dist(e)
        if d < nearEnemyDist then nearEnemyDist = d; nearEnemy = e end
    end
    for _, p in ipairs(projectiles) do
        local d = dist(p)
        if d < nearProjDist then nearProjDist = d; nearProj = p end
    end

    return {
        enemies = enemies,
        projectiles = projectiles,
        bossSprites = bossSprites,
        activeEntities = activeEntities,
        nearEnemy = nearEnemy,
        nearEnemyDist = nearEnemyDist,
        nearProj = nearProj,
        nearProjDist = nearProjDist,
    }
end

-- ============================================================
-- 6. PROGRESS TRACKER
-- ============================================================

local tracker = {
    roomHistory = {},         -- last 20 rooms
    roomVisitCount = {},      -- times each room visited
    dc81Samples = {},         -- DC81 (scroll countdown) every 30 frames
    scrollStall = 0,          -- frames DC81 hasn't changed
    maxProgress = 0,          -- highest FFD6 seen
    oscillationScore = 0,     -- 0-100
    lastRoom = 0,
    lastProgress = 0,
    lastRoomChangeFrame = 0,
    newRoomFrame = 0,         -- last time a NEW room was found
}

local function computeOscScore(history)
    if #history < 6 then return 0 end
    local score = 0

    -- Count unique rooms in last 10 transitions
    local unique = {}
    local len = math.min(10, #history)
    for i = #history - len + 1, #history do
        unique[history[i]] = true
    end
    local uCount = 0
    for _ in pairs(unique) do uCount = uCount + 1 end

    if uCount <= 2 and len >= 6 then score = score + 50
    elseif uCount <= 3 and len >= 8 then score = score + 30 end

    -- Check A-B-A-B pattern
    local abCount = 0
    for i = #history, math.max(3, #history - 5), -1 do
        if history[i] == history[i-2] and history[i] ~= history[i-1] then
            abCount = abCount + 1
        end
    end
    score = score + abCount * 15

    return math.min(100, score)
end

local function updateTracker(state)
    -- Room changes
    if state.room ~= tracker.lastRoom then
        table.insert(tracker.roomHistory, state.room)
        if #tracker.roomHistory > 20 then table.remove(tracker.roomHistory, 1) end
        tracker.roomVisitCount[state.room] = (tracker.roomVisitCount[state.room] or 0) + 1
        tracker.lastRoomChangeFrame = f
        tracker.lastRoom = state.room

        -- New room discovery?
        if not uniqueRooms[state.room] then
            tracker.newRoomFrame = f
        end
    end

    -- DC81 (scroll countdown) sampling every 30 frames
    if f % 30 == 0 then
        table.insert(tracker.dc81Samples, state.dc81)
        if #tracker.dc81Samples > 20 then table.remove(tracker.dc81Samples, 1) end

        if #tracker.dc81Samples >= 4 then
            local recent = tracker.dc81Samples[#tracker.dc81Samples]
            local older = tracker.dc81Samples[#tracker.dc81Samples - 3]
            if recent == older then
                tracker.scrollStall = tracker.scrollStall + 30
            else
                tracker.scrollStall = 0
            end
        end
    end

    -- Progress tracking
    if state.progress > tracker.maxProgress then
        tracker.maxProgress = state.progress
    end
    tracker.lastProgress = state.progress

    -- Oscillation score
    tracker.oscillationScore = computeOscScore(tracker.roomHistory)
end

-- ============================================================
-- 7. STATE MACHINE
-- ============================================================

local function setState(newState, reason)
    if newState ~= gameState then
        logMsg(string.format("STATE: %s -> %s (%s)", gameState, newState, reason))
        gameState = newState
        stateEntryFrame = f
        if newState == "playing_stuck" then stuckPhase = 0 end
    end
end

local function updateStateMachine(state, ents)
    if gameState == "title_menu" then
        if state.ffc1 == 1 then setState("playing_explore", "game started") end
        return
    end

    -- Boss transitions take priority
    if state.boss > 0 and gameState ~= "boss_fight" then
        local names = {[1]="Gargoyle",[2]="Spider",[3]="Crimson",[4]="Ice",
                       [5]="Void",[6]="Poison",[7]="Knight",[8]="Angela"}
        setState("boss_fight", names[state.boss] or ("boss" .. state.boss))
        return
    end
    if gameState == "boss_fight" and state.boss == 0 then
        setState("post_boss", "boss killed")
        return
    end
    -- Boss fight timeout: if stuck fighting for >3min, revert to explore
    -- (boss strategy now oscillates RIGHT/LEFT so timeout is rare)
    if gameState == "boss_fight" and (f - stateEntryFrame) > 10800 then
        logMsg("BOSS TIMEOUT: reverting to explore (still fighting)")
        setState("playing_explore", "boss timeout 90s")
        return
    end

    -- Post-boss sprint window (2 seconds)
    if gameState == "post_boss" and (f - stateEntryFrame) > 120 then
        setState("playing_explore", "post-boss timeout")
        return
    end

    -- Only evaluate explore/combat/stuck when in playing states
    if gameState ~= "playing_explore" and gameState ~= "playing_combat"
       and gameState ~= "playing_stuck" then
        return
    end

    -- Combat: enemies close
    if #ents.enemies > 0 and ents.nearEnemyDist < 40 then
        if gameState ~= "playing_combat" then
            setState("playing_combat", string.format("enemy@%dpx", math.floor(ents.nearEnemyDist)))
        end
        return
    end
    if gameState == "playing_combat" and (ents.nearEnemyDist > 60 or #ents.enemies == 0) then
        setState("playing_explore", "enemies cleared")
        return
    end

    -- Stuck: high oscillation score, with cooldown
    if gameState ~= "playing_stuck" and tracker.oscillationScore >= 60 then
        if (f - lastOscBreakFrame) > 600 then  -- 10s cooldown
            setState("playing_stuck", "osc=" .. tracker.oscillationScore)
            lastOscBreakFrame = f
        end
    end

    -- Unstuck: timeout or new room
    if gameState == "playing_stuck" then
        if (f - stateEntryFrame) > 1080 then  -- 18s max in stuck
            setState("playing_explore", "stuck timeout")
        elseif tracker.newRoomFrame > stateEntryFrame then
            setState("playing_explore", "new room found")
        end
    end
end

-- ============================================================
-- 8. STRATEGY ENGINE
-- ============================================================

local function dodgeProjectile(keys, ents, state)
    local p = ents.nearProj
    if p and ents.nearProjDist < 24 then
        local dy = p.y - state.saraY
        if math.abs(dy) < 16 then
            -- Dodge perpendicular to projectile
            if dy >= 0 then
                keys = keys + KEY_UP
            else
                keys = keys + KEY_DOWN
            end
        end
    end
    return keys
end

local function strategyExplore(state, ents)
    local keys = KEY_RIGHT

    -- Fire A at 66% duty cycle
    if f % 6 < 4 then keys = keys + KEY_A end

    -- Vertical positioning: keep Sara centered with gentle sine-wave
    if state.saraVisible then
        if state.saraY < 40 then
            keys = keys + KEY_DOWN  -- too high, drift down
        elseif state.saraY > 104 then
            keys = keys + KEY_UP    -- too low, drift up
        else
            -- Gentle sine-wave for coverage
            local cycle = f % 240
            if cycle < 60 then
                keys = keys + KEY_UP
            elseif cycle >= 120 and cycle < 180 then
                keys = keys + KEY_DOWN
            end
        end
    end

    -- Occasional B for form/special
    if f % 300 < 3 then keys = keys + KEY_B end

    keys = dodgeProjectile(keys, ents, state)
    return keys
end

local function strategyCombat(state, ents)
    local keys = KEY_A  -- always fire

    local enemy = ents.nearEnemy
    if enemy then
        local dx = enemy.x - state.saraX
        local dy = enemy.y - state.saraY
        if math.abs(dx) > 8 then
            keys = keys + (dx > 0 and KEY_RIGHT or KEY_LEFT)
        end
        if math.abs(dy) > 8 then
            keys = keys + (dy > 0 and KEY_DOWN or KEY_UP)
        end
    else
        keys = keys + KEY_RIGHT
    end

    keys = dodgeProjectile(keys, ents, state)
    return keys
end

-- 6-phase oscillation breaker
local STUCK_PHASES = {
    -- Phase 0: Go backward
    {dur = 180, fn = function()
        local keys = KEY_LEFT + KEY_A
        if f % 60 < 20 then keys = keys + KEY_UP end
        return keys
    end},
    -- Phase 1: UP + RIGHT heavy
    {dur = 180, fn = function()
        local keys = KEY_UP + KEY_RIGHT
        if f % 8 < 3 then keys = keys + KEY_A end
        return keys
    end},
    -- Phase 2: DOWN + RIGHT heavy
    {dur = 180, fn = function()
        local keys = KEY_DOWN + KEY_RIGHT
        if f % 8 < 3 then keys = keys + KEY_A end
        return keys
    end},
    -- Phase 3: Stationary (let DC81 tick)
    {dur = 120, fn = function()
        return KEY_A
    end},
    -- Phase 4: Pure sprint RIGHT (no fire)
    {dur = 180, fn = function()
        return KEY_RIGHT
    end},
    -- Phase 5: Diagonal UP-LEFT
    {dur = 180, fn = function()
        return KEY_LEFT + KEY_UP + KEY_A
    end},
}

local function strategyStuck(state, ents)
    local timeInPhase = f - stateEntryFrame
    local phase = STUCK_PHASES[(stuckPhase % #STUCK_PHASES) + 1]

    if timeInPhase > phase.dur then
        stuckPhase = stuckPhase + 1
        stateEntryFrame = f
        logMsg("STUCK phase=" .. stuckPhase .. " (" .. (stuckPhase % #STUCK_PHASES) .. ")")
    end

    return phase.fn()
end

local function strategyBoss(state, ents)
    -- Exact v8.4 boss strategy: RIGHT + modest A fire + dodging
    -- This killed Gargoyle in ~35s via natural room boundary oscillation.
    local keys = KEY_RIGHT

    -- Fire A at 33% duty cycle (matches proven v8.4 pattern)
    if f % 6 < 2 then keys = keys + KEY_A end

    -- Occasional B
    if f % 45 < 2 then keys = keys + KEY_B end

    -- Gentle vertical sine-wave (180-frame period)
    local cy = f % 180
    if cy < 45 then keys = keys + KEY_UP
    elseif cy >= 90 and cy < 135 then keys = keys + KEY_DOWN end

    -- Dodge enemy projectiles if very close
    keys = dodgeProjectile(keys, ents, state)

    return keys
end

local function strategyPostBoss(state, ents)
    -- Sprint RIGHT + A to exploit new room access
    local keys = KEY_RIGHT + KEY_A
    local cy = f % 120
    if cy < 30 then keys = keys + KEY_UP
    elseif cy >= 60 and cy < 90 then keys = keys + KEY_DOWN end
    return keys
end

local function getInput(state, ents)
    if gameState == "playing_explore" then return strategyExplore(state, ents)
    elseif gameState == "playing_combat" then return strategyCombat(state, ents)
    elseif gameState == "playing_stuck" then return strategyStuck(state, ents)
    elseif gameState == "boss_fight" then return strategyBoss(state, ents)
    elseif gameState == "post_boss" then return strategyPostBoss(state, ents)
    end
    return 0
end

-- ============================================================
-- 9. MILESTONES (save states, screenshots)
-- ============================================================

local function takeScreenshot(label)
    if screenshotCount >= MAX_SCREENSHOTS then return end
    screenshotCount = screenshotCount + 1
    local path = string.format("%s/autoplay_%03d_%s.png", SCREENSHOT_DIR, screenshotCount, label)
    emu:screenshot(path)
end

local function saveState(reason)
    if saveSlot > MAX_SAVE_SLOT then return end
    emu:saveStateSlot(saveSlot)
    logMsg("SAVE[" .. saveSlot .. "]: " .. reason)
    saveSlot = saveSlot + 1
end

local function detectEvents(state, ents)
    -- Room change
    if state.room ~= prev.room and prev.room ~= 0 then
        roomChangeCount = roomChangeCount + 1
        local isNew = not uniqueRooms[state.room]
        uniqueRooms[state.room] = true

        if isNew then
            logMsg(string.format("NEW ROOM %02X (from %02X) #%d", state.room, prev.room, roomChangeCount))
            logMsg("  " .. stateStr(state))
            takeScreenshot("new_r" .. string.format("%02X", state.room))
            saveState("new_room_" .. string.format("%02X", state.room))
        elseif tracker.oscillationScore < 50 then
            logMsg(string.format("ROOM %02X<-%02X #%d", state.room, prev.room, roomChangeCount))
            logMsg("  " .. stateStr(state))
            takeScreenshot("r" .. string.format("%02X", state.room))
        end
        -- else oscillating, suppress log spam
    end

    -- Boss changes
    if state.boss ~= prev.boss then
        local names = {[1]="Gargoyle",[2]="Spider",[3]="Crimson",[4]="Ice",
                       [5]="Void",[6]="Poison",[7]="Knight",[8]="Angela"}
        if state.boss > 0 then
            uniqueBosses[state.boss] = true
            local ubCount = 0; for _ in pairs(uniqueBosses) do ubCount = ubCount + 1 end
            logMsg("BOSS: " .. (names[state.boss] or "?") .. " (" .. state.boss .. ") [unique:" .. ubCount .. "/8]")
            logMsg("  " .. stateStr(state))
            takeScreenshot("boss_" .. (names[state.boss] or state.boss))
            saveState("boss_" .. (names[state.boss] or state.boss))
        else
            bossKillCount = bossKillCount + 1
            logMsg("KILL: " .. (names[prev.boss] or "?") .. " #" .. bossKillCount)
            logMsg("  " .. stateStr(state))
            takeScreenshot("kill_" .. bossKillCount)
            saveState("kill_" .. bossKillCount)
        end
    end

    -- v8.5 Boss rotation via ROM patching:
    -- The spawn table has 2 boss slots: entry2 (DCB8=2) and entry5 (DCB8=5).
    -- Bosses always appear in order: entry2 first, then entry5.
    -- After each pair is killed, patch both entries with the next pair.
    --
    -- Progression: Gargoyle→Spider (natural) → Crimson→Ice → Void→Poison → Knight→Angela
    -- Kill#  Boss     Slot   Action
    --  1     Gargoyle entry2 fast-forward DCB8→4 for Spider
    --  2     Spider   entry5 patch entry2=Crimson entry5=Ice, DCB8→1
    --  3     Crimson  entry2 fast-forward DCB8→4 for Ice
    --  4     Ice      entry5 patch entry2=Void entry5=Poison, DCB8→1
    --  5     Void     entry2 fast-forward DCB8→4 for Poison
    --  6     Poison   entry5 patch entry2=Knight entry5=Angela, DCB8→1
    --  7     Knight   entry2 fast-forward DCB8→4 for Angela
    --  8     Angela   entry5 patch entry2=Gargoyle entry5=Spider, DCB8→1 (full wrap)
    if bossKillCount >= 1 and bossKillCount ~= lastPatchedKill and state.boss == 0 then
        lastPatchedKill = bossKillCount
        local dcb8 = emu:read8(0xDCB8)
        local isEntry5Kill = (bossKillCount % 2 == 0)  -- even=entry5, odd=entry2

        if isEntry5Kill then
            -- Entry5 boss killed: patch ROM with next pair, fast-forward to entry2
            nextBossIndex = nextBossIndex + 2
            if nextBossIndex > 8 then nextBossIndex = nextBossIndex - 8 end
            local b2 = nextBossIndex + 1
            if b2 > 8 then b2 = b2 - 8 end
            emu.memory.cart0:write8(SPAWN_ENTRY2_ROM, BOSS_DC04[nextBossIndex])
            emu.memory.cart0:write8(SPAWN_ENTRY5_ROM, BOSS_DC04[b2])
            emu:write8(0xDCB8, 1)  -- fast-forward: 1→2=entry2 boss
            logMsg(string.format("ROM PATCH: entry2=%s(0x%02X) entry5=%s(0x%02X) DCB8→1",
                BOSS_NAMES[nextBossIndex], BOSS_DC04[nextBossIndex],
                BOSS_NAMES[b2], BOSS_DC04[b2]))
        else
            -- Entry2 boss killed: fast-forward to entry5 boss
            if dcb8 < 4 then
                emu:write8(0xDCB8, 4)
                logMsg(string.format("DCB8: %02X -> 04 (fast-forward to entry5 boss)", dcb8))
            end
        end
    end

    -- Stage change (FFD0)
    if state.stage ~= prev.stage then
        logMsg(string.format("*** STAGE %02X -> %02X ***", prev.stage, state.stage))
        logMsg("  " .. stateStr(state))
        takeScreenshot("stage_" .. string.format("%02X", state.stage))
        saveState("stage_" .. string.format("%02X", state.stage))
    end

    -- Form change
    if state.form ~= prev.form then
        logMsg("FORM: " .. (state.form == 0 and "Witch" or "Dragon"))
    end

    -- Powerup change
    if state.powerup ~= prev.powerup then
        local pw = {"none","spiral","shield","turbo"}
        logMsg("POWERUP: " .. (pw[state.powerup + 1] or "?"))
    end

    -- Progress milestones (every 0x20 new high)
    if state.progress > prev.progress and state.progress > 0 then
        local prevMilestone = math.floor(prev.progress / 0x20)
        local curMilestone = math.floor(state.progress / 0x20)
        if curMilestone > prevMilestone and state.progress > tracker.maxProgress - 0x20 then
            logMsg(string.format("PROG milestone: %02X", state.progress))
        end
    end

    -- Progress reset
    if state.progress == 0 and prev.progress > 0x10 then
        logMsg(string.format("PROG reset (was %02X)", prev.progress))
    end

    -- FFC1 drop (back to menu)
    if state.ffc1 ~= prev.ffc1 then
        logMsg(string.format("FFC1: %02X -> %02X", prev.ffc1, state.ffc1))
        if state.ffc1 == 0 then
            takeScreenshot("ffc1_drop")
            saveState("ffc1_drop")
        end
    end

    -- Update prev
    prev.room = state.room
    prev.boss = state.boss
    prev.form = state.form
    prev.ffc1 = state.ffc1
    prev.progress = state.progress
    prev.stage = state.stage
    prev.difficulty = state.difficulty
    prev.powerup = state.powerup
end

-- ============================================================
-- 10. PERIODIC SUMMARY
-- ============================================================

local function logSummary(state, ents, label)
    local t = (f - gameStartFrame) / 60.0
    local n = 0; local r = ""
    for k in pairs(uniqueRooms) do n = n + 1; r = r .. string.format("%02X ", k) end

    logMsg(string.format("[%s %.0fs] %s state=%s osc=%d",
        label, t, stateStr(state), gameState, tracker.oscillationScore))
    local ub = 0; local bList = ""
    for k in pairs(uniqueBosses) do ub = ub + 1; bList = bList .. (BOSS_NAMES[k] or "?") .. " " end
    logMsg(string.format("  rooms=%d uniq=%d[%s] kills=%d bosses=%d/8[%s] ents=%d maxProg=%02X scrollStall=%d",
        roomChangeCount, n, r, bossKillCount, ub, bList, ents.activeEntities,
        tracker.maxProgress, tracker.scrollStall))
end

-- ============================================================
-- 11. MAIN FRAME CALLBACK
-- ============================================================

logMsg("=== PENTA DRAGON AUTO-PLAY v8.5 ===")
logMsg("Position-aware | Entity-scanning | State-driven")

callbacks:add("frame", function()
    f = f + 1

    -- Read sensors
    local state = readSensors()

    -- Title menu
    if gameState == "title_menu" then
        local keys = 0
        for _, e in ipairs(TITLE_SCHEDULE) do
            if f >= e[1] and f <= e[2] then keys = e[3]; break end
        end
        emu:setKeys(keys)

        if state.ffc1 == 1 then
            gameStartFrame = f
            prev.room = state.room; prev.boss = state.boss; prev.form = state.form
            prev.ffc1 = state.ffc1; prev.progress = state.progress
            prev.stage = state.stage; prev.difficulty = state.difficulty
            prev.powerup = state.powerup
            tracker.lastRoom = state.room
            uniqueRooms[state.room] = true
            tracker.lastRoomChangeFrame = f
            logMsg("*** GAME STARTED ***")
            logMsg("  " .. stateStr(state))
            takeScreenshot("start")
            saveState("start")
            setState("playing_explore", "game started")
        end

        -- Failsafe: if still in title after 900 frames, spam A
        if f > 600 and gameState == "title_menu" then
            if f % 30 == 0 then emu:setKeys(KEY_A)
            elseif f % 30 == 5 then emu:setKeys(0) end
        end
        if f > 900 and gameState == "title_menu" then
            logMsg("ABORT: title timeout"); log:close(); emu:stop()
        end
        return
    end

    -- Infinite HP
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)

    -- Scan entities
    local ents = scanEntities(state)

    -- Update tracker
    updateTracker(state)

    -- Update state machine
    updateStateMachine(state, ents)

    -- Get and apply input
    emu:setKeys(getInput(state, ents))

    -- Detect and log events
    detectEvents(state, ents)

    -- Periodic summary every 30s
    if f % 1800 == 0 then logSummary(state, ents, "STATUS") end

    -- Runtime limit
    if f >= MAX_RUNTIME then
        logSummary(state, ents, "FINAL")
        log:close()
        emu:stop()
    end
end)

callbacks:add("shutdown", function()
    if log then logMsg("END"); log:close(); log = nil end
end)
