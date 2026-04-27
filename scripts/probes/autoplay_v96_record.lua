-- Penta Dragon Auto-play & Game Documenter v9.6
-- Full game exploration bot with comprehensive capture of game states
--
-- NATURAL_MODE: When true, disables ROM patching and DCB8 resets.
-- Lets the game advance naturally through sections and levels.
-- Monitors FFAC/FFAD for level transitions.
local NATURAL_MODE = true  -- Set to true for natural progression
--
-- Features:
--   - Position-aware movement with entity scanning
--   - State machine: explore/combat/stuck/boss/post_boss
--   - ALL-ENTRIES ROM patching: patches all 6 spawn table entries as bosses
--   - Persistent section forcing after each boss kill (DCBA + entity zeroing + FFD6)
--   - Captures: bosses, items, forms, enemy types, stages, hazards
--   - Periodically forces powerup/form changes for coverage
--   - Priority screenshot system (bosses > items > enemies > rooms)

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

local MAX_SCREENSHOTS = 300
local MAX_RUNTIME = 108000  -- 30 min full recording
local MAX_SAVE_SLOT = 9

-- Powerup names for logging/screenshots
local POWERUP_NAMES = {"none","spiral","shield","turbo"}

-- Boss progression via ROM patching
-- Level 1 spawn table in bank 13 (ROM offset 0x34024)
-- Header byte = 0x06 (6 entries), then 5 bytes per entry
-- v9.4: Only entry 2 (0x3402F) ROM writes confirmed working.
-- Uses 1-frame entity-check NOP at $2240-$2241 to force section advance.
-- ALL 16 bosses! DC04 = 0x30 + (boss-1)*5
local BOSS_DC04 = {0x30, 0x35, 0x3A, 0x3F, 0x44, 0x49, 0x4E, 0x53,
                   0x58, 0x5D, 0x62, 0x67, 0x6C, 0x71, 0x76, 0x7B}
local BOSS_NAMES = {"Gargoyle","Spider","Crimson","Ice","Void","Poison","Knight","Angela",
                    "Boss9","Boss10","Boss11","Boss12","Boss13","Boss14","Boss15","Boss16"}
local SPAWN_ENTRY2_ROM = 0x3402F  -- ROM address of entry 2's DC04 byte (confirmed working)
-- Entity check NOP: at $2240 is "JR NZ,$2268" (bytes 0x20,0x26)
-- NOP'ing these 2 bytes makes section advance skip entity alive check for 1 frame
local ENTITY_CHECK_ADDR = 0x2240   -- ROM offset of JR NZ instruction
local ENTITY_CHECK_ORIG = {0x20, 0x26}  -- original bytes to restore
-- Entity slot first-byte addresses (5 slots × 8 byte stride, slot[0] = alive/dead type)
local ENTITY_SLOT_ADDRS = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}

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
local lastKillFrame = 0    -- frame of most recent boss kill
local bossEnterFrame = 0   -- frame when current boss fight began (persists across state resets)
local nopEntityCheck = false -- true = NOP active at $2240, need to restore next frame
local restoreEntityCheck = false -- true = restore original bytes at $2240 this frame
local sectionForceEnd = 0  -- frame until which FFD6 forcing is active
local uniqueBosses = {}    -- track which boss types we've encountered
local romPatchDone = false  -- initial ROM patch applied?
local prevFFAC = 0         -- for NATURAL_MODE level transition detection
local prevFFAD = 0
local prevFFBA = 0
local lastSaraX = -1       -- for frozen-Sara detection
local lastSaraY = -1
local saraFrozenFrames = 0 -- how long Sara has been at same position

-- Discovery tracking for comprehensive game documentation
local seenEnemyTiles = {}  -- unique OAM tile IDs from enemy sprites
local seenPowerups = {}    -- unique powerup states captured
local seenForms = {}       -- witch/dragon forms captured
local seenBossStates = {}  -- boss + form + powerup combos
local lastFormToggle = 0   -- frame of last forced form toggle
local lastPowerupCycle = 0 -- frame of last forced powerup cycle
local powerupCycleIdx = 0  -- current powerup in cycle
local roomScreenshotBudget = 30  -- limit room transition screenshots
local roomScreenshots = 0  -- count of room screenshots taken
local bossFullCycles = 0   -- how many full 8-boss cycles completed

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

-- BC trajectory recorder
local REC_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_v96.jsonl"
os.execute("mkdir -p /home/struktured/projects/penta-dragon-dx-claude/rl/bc_data")
local rec = io.open(REC_PATH, "w")
local recCount = 0

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
-- 5b. ROM PATCHING & SECTION FORCING
-- ============================================================

-- Patch entry 2 with the specified boss DC04 value
local function patchEntry2(bossIdx)
    emu.memory.cart0:write8(SPAWN_ENTRY2_ROM, BOSS_DC04[bossIdx])
    logMsg(string.format("ROM PATCH entry2 = %s(0x%02X)", BOSS_NAMES[bossIdx], BOSS_DC04[bossIdx]))
end

-- NOP the entity alive check at $2240-$2241 for exactly 1 frame
-- This makes the section advance skip entity checking, allowing DCB8 to advance
-- even when entities are alive (spawner timing issue bypass)
local function activateEntityCheckNOP()
    emu.memory.cart0:write8(ENTITY_CHECK_ADDR, 0x00)      -- NOP
    emu.memory.cart0:write8(ENTITY_CHECK_ADDR + 1, 0x00)  -- NOP
    nopEntityCheck = true
    restoreEntityCheck = false
    logMsg("  NOP entity check at $2240 (1-frame bypass)")
end

-- Restore original entity check bytes
local function restoreEntityCheckBytes()
    emu.memory.cart0:write8(ENTITY_CHECK_ADDR, ENTITY_CHECK_ORIG[1])      -- JR NZ
    emu.memory.cart0:write8(ENTITY_CHECK_ADDR + 1, ENTITY_CHECK_ORIG[2])  -- +0x26
    nopEntityCheck = false
    restoreEntityCheck = false
    logMsg("  Restored entity check at $2240")
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
        -- Only set bossEnterFrame on genuine new boss (not timeout re-entry)
        if bossEnterFrame == 0 then
            bossEnterFrame = f
        end
        return
    end
    if gameState == "boss_fight" and state.boss == 0 then
        bossEnterFrame = 0  -- reset for next boss
        setState("post_boss", "boss killed")
        return
    end
    -- Force-kill: if boss fight exceeds 5min (18000 frames total), write FFBF=0
    -- Some bosses (e.g., Boss16 DC04=0x7B) appear unkillable
    -- Uses bossEnterFrame which persists across timeout/re-enter cycles
    if state.boss > 0 and bossEnterFrame > 0 and (f - bossEnterFrame) > 18000 then
        logMsg("FORCE KILL: boss " .. state.boss .. " unkillable after 5min, writing FFBF=0")
        emu:write8(0xFFBF, 0)
        bossEnterFrame = 0  -- reset so it doesn't retrigger
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
    -- Aggressive boss strategy: high fire rate + track boss position
    local keys = 0

    -- Fire A at 83% duty cycle for maximum DPS
    if f % 6 < 5 then keys = keys + KEY_A end

    -- Toggle form every 15s during boss fight for varied damage types
    if (f - stateEntryFrame) % 900 == 0 and (f - stateEntryFrame) > 0 then
        keys = keys + KEY_B
    end

    -- If boss sprites visible, track their centroid
    if #ents.bossSprites > 0 then
        local bx, by = 0, 0
        for _, b in ipairs(ents.bossSprites) do
            bx = bx + b.x; by = by + b.y
        end
        bx = bx / #ents.bossSprites
        by = by / #ents.bossSprites
        -- Move toward boss horizontally (maintain 30-60px gap)
        local dx = bx - state.saraX
        if dx > 60 then keys = keys + KEY_RIGHT
        elseif dx < 30 and dx > 0 then keys = keys + KEY_LEFT  -- too close, back off
        elseif dx < -10 then keys = keys + KEY_LEFT
        else keys = keys + KEY_RIGHT end  -- default right
        -- Match boss Y within 16px
        local dy = by - state.saraY
        if dy > 16 then keys = keys + KEY_DOWN
        elseif dy < -16 then keys = keys + KEY_UP end
    else
        -- No boss sprites visible: oscillate LEFT/RIGHT every 90 frames
        local cy = (f - stateEntryFrame) % 180
        if cy < 90 then keys = keys + KEY_RIGHT
        else keys = keys + KEY_LEFT end
        -- Vertical sine
        local vy = f % 180
        if vy < 45 then keys = keys + KEY_UP
        elseif vy >= 90 and vy < 135 then keys = keys + KEY_DOWN end
    end

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
    logMsg("SCREENSHOT[" .. screenshotCount .. "]: " .. label)
end

local function saveState(reason)
    if saveSlot > MAX_SAVE_SLOT then saveSlot = 1 end  -- wrap around
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
        elseif tracker.oscillationScore < 30 and roomScreenshots < roomScreenshotBudget then
            roomScreenshots = roomScreenshots + 1
            takeScreenshot("r" .. string.format("%02X", state.room))
        end
    end

    -- Boss changes
    if state.boss ~= prev.boss then
        if state.boss > 0 then
            uniqueBosses[state.boss] = true
            local ubCount = 0; for _ in pairs(uniqueBosses) do ubCount = ubCount + 1 end
            local bName = BOSS_NAMES[state.boss] or ("Boss" .. state.boss)
            logMsg("BOSS: " .. bName .. " (" .. state.boss .. ") [unique:" .. ubCount .. "/16]")
            logMsg("  " .. stateStr(state))
            takeScreenshot("boss_" .. bName)
            saveState("boss_" .. bName)
            -- Also capture boss with each form+powerup combo
            local combo = state.boss .. "_" .. state.form .. "_" .. state.powerup
            if not seenBossStates[combo] then
                seenBossStates[combo] = true
            end
        else
            bossKillCount = bossKillCount + 1
            local bossName = BOSS_NAMES[prev.boss] or ("Boss" .. prev.boss)
            lastKillFrame = f
            if NATURAL_MODE then
                -- Natural: let DCB8 advance on its own, just force sections
                logMsg("KILL: " .. bossName .. " #" .. bossKillCount ..
                    " (natural, DCB8=" .. state.dcb8 .. ")")
                logMsg("  " .. stateStr(state))
                logMsg("  FFAC=" .. string.format("%02X", emu:read8(0xFFAC)) ..
                       " FFAD=" .. string.format("%02X", emu:read8(0xFFAD)) ..
                       " FFBA=" .. emu:read8(0xFFBA))
            else
                -- CRITICAL: Do all ROM/memory writes BEFORE screenshot (which corrupts IO)
                local nextBoss = (bossKillCount % 16) + 1  -- cycle through ALL 16 bosses
                patchEntry2(nextBoss)
                emu:write8(0xDCB8, 1)  -- set DCB8 to 1 so next advance → 2 (boss entry)
                activateEntityCheckNOP()
                sectionForceEnd = f + 36000  -- 10 minutes: effectively permanent forcing
                -- Now log and screenshot (IO may be corrupted after screenshot)
                logMsg("KILL: " .. bossName .. " #" .. bossKillCount ..
                    " next=" .. BOSS_NAMES[nextBoss] .. " NOP active")
                logMsg("  " .. stateStr(state))
            end
            -- Track full boss cycles (16 bosses now)
            if bossKillCount % 16 == 0 then
                bossFullCycles = bossFullCycles + 1
                logMsg("*** FULL 16-BOSS CYCLE #" .. bossFullCycles .. " COMPLETE ***")
            end
            -- Screenshot LAST (may corrupt IO)
            takeScreenshot("kill_" .. bossName .. "_" .. bossKillCount)
            saveState("kill_" .. bossName)
        end
    end

    -- Stage change (FFD0)
    if state.stage ~= prev.stage then
        logMsg(string.format("*** STAGE %02X -> %02X ***", prev.stage, state.stage))
        logMsg("  " .. stateStr(state))
        takeScreenshot("stage_" .. string.format("%02X", state.stage))
        saveState("stage_" .. string.format("%02X", state.stage))
    end

    -- Form change — capture screenshot of each unique form
    if state.form ~= prev.form then
        local formName = state.form == 0 and "Witch" or "Dragon"
        logMsg("FORM: " .. formName)
        if not seenForms[state.form] then
            seenForms[state.form] = true
            takeScreenshot("form_" .. formName)
            saveState("form_" .. formName)
        end
        -- Screenshot form+powerup combos
        local formPw = formName .. "_" .. (POWERUP_NAMES[state.powerup + 1] or "unk")
        takeScreenshot("form_" .. formPw)
    end

    -- Powerup change — capture screenshot of each unique powerup
    if state.powerup ~= prev.powerup then
        local pwName = POWERUP_NAMES[state.powerup + 1] or "unk"
        logMsg("POWERUP: " .. pwName)
        if not seenPowerups[state.powerup] then
            seenPowerups[state.powerup] = true
            local formName = state.form == 0 and "W" or "D"
            takeScreenshot("powerup_" .. pwName .. "_" .. formName)
            saveState("powerup_" .. pwName)
        end
    end

    -- Enemy tile discovery — log new tile IDs (every 120 frames, max 30 screenshots)
    if f % 120 == 0 then
        local etCount = 0; for _ in pairs(seenEnemyTiles) do etCount = etCount + 1 end
        if #ents.enemies > 0 then
            for _, e in ipairs(ents.enemies) do
                if not seenEnemyTiles[e.tile] then
                    seenEnemyTiles[e.tile] = true
                    etCount = etCount + 1
                    logMsg(string.format("NEW ENEMY TILE: 0x%02X at (%d,%d) [%d unique]",
                        e.tile, e.x, e.y, etCount))
                    if etCount <= 30 then
                        takeScreenshot(string.format("enemy_%02X_r%02X", e.tile, state.room))
                    end
                end
            end
        end
        -- Boss sprite tiles (count only — individual sprite logging caused log corruption)
        if #ents.bossSprites > 0 then
            local newCount = 0
            for _, b in ipairs(ents.bossSprites) do
                local key = "boss_" .. state.boss .. "_" .. b.tile
                if not seenEnemyTiles[key] then
                    seenEnemyTiles[key] = true
                    newCount = newCount + 1
                end
            end
            if newCount > 0 then
                logMsg(string.format("BOSS SPRITES: boss=%d +%d new tiles", state.boss, newCount))
            end
        end
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

    -- FFC1 drop (back to menu — game over or post-Angela?)
    if state.ffc1 ~= prev.ffc1 then
        logMsg(string.format("FFC1: %02X -> %02X", prev.ffc1, state.ffc1))
        if state.ffc1 == 0 then
            takeScreenshot("ffc1_drop_" .. bossKillCount)
            saveState("ffc1_drop")
            logMsg("*** RETURNED TO MENU — game over or post-Angela ***")
        end
    end

    -- Periodically force form toggle (every 90s between boss fights)
    if gameState == "playing_explore" and (f - lastFormToggle) > 5400 then
        lastFormToggle = f
        local newForm = state.form == 0 and 1 or 0
        emu:write8(0xFFBE, newForm)
        logMsg("FORCE FORM: " .. (newForm == 0 and "Witch" or "Dragon"))
    end

    -- Periodically force powerup cycling (every 45s between boss fights)
    if gameState == "playing_explore" and (f - lastPowerupCycle) > 2700 then
        lastPowerupCycle = f
        powerupCycleIdx = (powerupCycleIdx + 1) % 4
        emu:write8(0xFFC0, powerupCycleIdx)
        logMsg("FORCE POWERUP: " .. (POWERUP_NAMES[powerupCycleIdx + 1] or "?"))
        takeScreenshot("pw_" .. (POWERUP_NAMES[powerupCycleIdx + 1] or "unk") ..
            "_" .. (state.form == 0 and "W" or "D") ..
            "_r" .. string.format("%02X", state.room))
    end

    -- Periodic scenic screenshot (every 90s during explore, captures environment variety)
    if gameState == "playing_explore" and f % 5400 == 0 and f > gameStartFrame + 600 then
        takeScreenshot("scene_" .. string.format("%02X", state.room) ..
            "_" .. (state.form == 0 and "W" or "D") ..
            "_" .. (POWERUP_NAMES[state.powerup + 1] or "unk"))
    end

    -- NATURAL_MODE: detect FFAC/FFAD and FFBA changes (level transitions!)
    if NATURAL_MODE then
        local ffac = emu:read8(0xFFAC)
        local ffad = emu:read8(0xFFAD)
        local ffba = emu:read8(0xFFBA)
        if ffac ~= prevFFAC or ffad ~= prevFFAD then
            logMsg(string.format("*** LEVEL TRANSITION: FFAC/FFAD %02X/%02X -> %02X/%02X ***",
                prevFFAC, prevFFAD, ffac, ffad))
            logMsg("  " .. stateStr(state))
            takeScreenshot("level_transition")
            saveState("level_transition")
            prevFFAC = ffac
            prevFFAD = ffad
        end
        if ffba ~= prevFFBA then
            logMsg(string.format("FFBA CHANGED: %d -> %d", prevFFBA, ffba))
            prevFFBA = ffba
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
    local et = 0; for _ in pairs(seenEnemyTiles) do et = et + 1 end
    logMsg(string.format("  rooms=%d uniq=%d[%s] kills=%d bosses=%d/16[%s]",
        roomChangeCount, n, r, bossKillCount, ub, bList))
    logMsg(string.format("  enemyTiles=%d screenshots=%d/%d form=%s pw=%s cycles=%d nop=%s forceEnd=%d",
        et, screenshotCount, MAX_SCREENSHOTS,
        state.form == 0 and "W" or "D",
        POWERUP_NAMES[state.powerup + 1] or "?",
        bossFullCycles,
        tostring(nopEntityCheck),
        sectionForceEnd - f))
    if NATURAL_MODE then
        logMsg(string.format("  FFAC=%02X FFAD=%02X FFBA=%d",
            emu:read8(0xFFAC), emu:read8(0xFFAD), emu:read8(0xFFBA)))
    end
end

-- ============================================================
-- 11. MAIN FRAME CALLBACK
-- ============================================================

logMsg("=== PENTA DRAGON AUTO-PLAY v9.4 ===")
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
            -- v9.4: Patch entry 2 with Spider (next boss after natural Gargoyle)
            if not romPatchDone and not NATURAL_MODE then
                romPatchDone = true
                logMsg("=== v9.4 ENTRY2 ROM PATCH + NOP APPROACH ===")
                patchEntry2(2)  -- Spider for first entry2 encounter
                logMsg("Entry 2 = Spider. Entity check NOP will force DCB8 1→2 after kills.")
            elseif NATURAL_MODE then
                romPatchDone = true
                logMsg("=== NATURAL MODE: No ROM patches, watching for level transitions ===")
                sectionForceEnd = f + 216000  -- force for entire 60-min run
            end
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

    -- v9.4: 1-frame entity check NOP for section forcing
    -- After boss kill: NOP was written in prev frame → this frame's game loop uses NOP'd check
    -- → section advance fires → restore original bytes
    if nopEntityCheck then
        -- The NOP was active for this frame's game loop. Schedule restore for next frame.
        nopEntityCheck = false
        restoreEntityCheck = true
        -- Check if advance happened (DCB8 should have changed from 1 to 2+)
        local dcb8 = emu:read8(0xDCB8)
        local ffbf = emu:read8(0xFFBF)
        logMsg(string.format("  NOP frame done: DCB8=%d FFBF=%d dc04=%02X",
            dcb8, ffbf, emu:read8(0xDC04)))
        if ffbf > 0 then
            logMsg(string.format("  SUCCESS: Boss %s spawned!", BOSS_NAMES[ffbf] or "?"))
        elseif dcb8 ~= 1 then
            logMsg(string.format("  DCB8 advanced to %d but no boss. Entry data may be wrong.", dcb8))
        else
            logMsg("  WARNING: DCB8 still 1. Advance may not have fired. Will retry.")
        end
    end
    if restoreEntityCheck then
        restoreEntityCheckBytes()
    end

    -- Keep FFD6 >= 0x1E during force window (ensures DCBA stays armed for advance)
    if f <= sectionForceEnd and state.boss == 0 then
        if emu:read8(0xFFD6) < 0x1E then
            emu:write8(0xFFD6, 0x1E)
        end
        emu:write8(0xDCBA, 0x01)  -- keep DCBA armed
        -- Every 15 frames, zero entity slots to help section advance fire
        if f % 15 == 0 then
            for _, addr in ipairs(ENTITY_SLOT_ADDRS) do
                emu:write8(addr, 0x00)
            end
        end
    end

    -- Retry NOP every 30 frames if advance didn't fire yet
    if f > lastKillFrame + 30 and f <= sectionForceEnd and state.boss == 0 then
        local dcb8 = emu:read8(0xDCB8)
        if dcb8 == 1 and not nopEntityCheck and not restoreEntityCheck and (f - lastKillFrame) % 30 == 0 then
            logMsg(string.format("  RETRY NOP: DCB8 still 1 after %d frames", f - lastKillFrame))
            activateEntityCheckNOP()
        end
    end

    -- v9.4: Frozen-Sara detection — if Sara hasn't moved for 600 frames, try jolt
    if state.saraX == lastSaraX and state.saraY == lastSaraY then
        saraFrozenFrames = saraFrozenFrames + 1
    else
        saraFrozenFrames = 0
        lastSaraX = state.saraX
        lastSaraY = state.saraY
    end

    -- Scan entities
    local ents = scanEntities(state)

    -- Update tracker
    updateTracker(state)

    -- Update state machine
    updateStateMachine(state, ents)

    -- Get and apply input
    local keys = getInput(state, ents)
    -- If Sara has been frozen 10+ seconds, add aggressive jolt movement
    if saraFrozenFrames > 600 and gameState ~= "boss_fight" then
        local joltPhase = math.floor(saraFrozenFrames / 120) % 4
        if joltPhase == 0 then keys = KEY_LEFT + KEY_UP + KEY_A
        elseif joltPhase == 1 then keys = KEY_RIGHT + KEY_DOWN + KEY_A
        elseif joltPhase == 2 then keys = KEY_DOWN + KEY_LEFT + KEY_B
        else keys = KEY_UP + KEY_RIGHT + KEY_A end
        if saraFrozenFrames % 600 == 0 then
            logMsg(string.format("JOLT: Sara frozen at (%d,%d) for %d frames",
                state.saraX, state.saraY, saraFrozenFrames))
        end
    end
    emu:setKeys(keys)

    -- ============== BC RECORDING ==============
    if rec ~= nil and f % 4 == 0 and emu:read8(0xFFC1) == 1 then
        -- OAM features (Sara avg, boss centroid, nearest enemy, projectile count)
        local OAM_X_OFF = 8
        local OAM_Y_OFF = 16
        local sara_sx, sara_sy, sara_n = 0, 0, 0
        local boss_sx, boss_sy, boss_n = 0, 0, 0
        local near_sx, near_sy, near_d = 0, 0, 999
        local proj_n = 0
        local sprites_x = {}; local sprites_y = {}; local sprites_t = {}
        for i = 0, 39 do
            local sy = emu:read8(0xFE00 + i*4)
            local sx = emu:read8(0xFE00 + i*4 + 1)
            local tile = emu:read8(0xFE00 + i*4 + 2)
            if sy > 0 and sy < 160 then
                local px = sx - OAM_X_OFF
                local py = sy - OAM_Y_OFF
                table.insert(sprites_x, px); table.insert(sprites_y, py); table.insert(sprites_t, tile)
                if i < 4 then
                    sara_sx = sara_sx + px; sara_sy = sara_sy + py; sara_n = sara_n + 1
                elseif tile >= 0x30 and tile <= 0x7F then
                    boss_sx = boss_sx + px; boss_sy = boss_sy + py; boss_n = boss_n + 1
                elseif tile == 0x06 or tile == 0x09 or tile == 0x0A or tile == 0x0F or tile == 0x00 or tile == 0x01 then
                    proj_n = proj_n + 1
                end
            end
        end
        local sara_x_avg = sara_n > 0 and (sara_sx / sara_n) or -1
        local sara_y_avg = sara_n > 0 and (sara_sy / sara_n) or -1
        local boss_x_avg = boss_n > 0 and (boss_sx / boss_n) or -1
        local boss_y_avg = boss_n > 0 and (boss_sy / boss_n) or -1
        if sara_n > 0 then
            for i = 1, #sprites_t do
                if sprites_t[i] >= 0x30 and sprites_t[i] <= 0x7F then
                    local dx = sprites_x[i] - sara_x_avg
                    local dy = sprites_y[i] - sara_y_avg
                    local d = math.sqrt(dx*dx + dy*dy)
                    if d < near_d then near_d = d; near_sx = sprites_x[i]; near_sy = sprites_y[i] end
                end
            end
        end
        if near_d == 999 then near_d = -1 end
        local function k2a(k)
            if k == 0x01 then return 0 end
            if k == 0x02 then return 1 end
            if k == 0x04 then return 2 end
            if k == 0x08 then return 3 end
            if k == 0x10 then return 4 end
            if k == 0x20 then return 5 end
            if k == 0x40 then return 6 end
            if k == 0x80 then return 7 end
            if k == 0x41 then return 8 end
            if k == 0x81 then return 9 end
            if k == 0x22 then return 10 end
            if k == 0x12 then return 11 end
            if k % 2 == 1 then
                if k % 0x80 >= 0x40 then return 8 end
                if k >= 0x80 then return 9 end
                return 0
            end
            if (k - (k % 4)) % 4 >= 2 then
                if (k % 0x40) >= 0x20 then return 10 end
                if (k % 0x20) >= 0x10 then return 11 end
                return 1
            end
            if k % 0x80 >= 0x40 then return 6 end
            if k >= 0x80 then return 7 end
            if (k % 0x40) >= 0x20 then return 5 end
            if (k % 0x20) >= 0x10 then return 4 end
            return 0
        end
        local action_idx = k2a(keys)
        rec:write("{")
        rec:write(string.format('"f":%d,"action":%d,"keys":%d,', f, action_idx, keys))
        rec:write(string.format('"D880":%d,"FFBA":%d,"FFBD":%d,"FFBE":%d,"FFBF":%d,"FFC0":%d,"FFC1":%d,',
            emu:read8(0xD880), emu:read8(0xFFBA), emu:read8(0xFFBD), emu:read8(0xFFBE),
            emu:read8(0xFFBF), emu:read8(0xFFC0), emu:read8(0xFFC1)))
        rec:write(string.format('"DCBB":%d,"DCDC":%d,"DCDD":%d,"DCB8":%d,',
            emu:read8(0xDCBB), emu:read8(0xDCDC), emu:read8(0xDCDD), emu:read8(0xDCB8)))
        rec:write(string.format('"FFAC":%d,"FFAD":%d,"FFCF":%d,"SCY":%d,"SCX":%d,"DC04":%d,',
            emu:read8(0xFFAC), emu:read8(0xFFAD), emu:read8(0xFFCF),
            emu:read8(0xFF42), emu:read8(0xFF43), emu:read8(0xDC04)))
        rec:write('"slots":[')
        local slot_addrs = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
        for si, addr in ipairs(slot_addrs) do
            rec:write("[")
            for j = 0, 7 do
                rec:write(tostring(emu:read8(addr + j)))
                if j < 7 then rec:write(",") end
            end
            rec:write("]")
            if si < 5 then rec:write(",") end
        end
        rec:write(string.format('],"oam":{"sara_x":%d,"sara_y":%d,"boss_x":%d,"boss_y":%d,"boss_count":%d,"near_x":%d,"near_y":%d,"near_dist":%d,"proj_count":%d}}\n',
            math.floor(sara_x_avg), math.floor(sara_y_avg),
            math.floor(boss_x_avg), math.floor(boss_y_avg), boss_n,
            math.floor(near_sx), math.floor(near_sy), math.floor(near_d), proj_n))
        recCount = recCount + 1
        if recCount % 5000 == 0 then
            rec:flush()
            logMsg(string.format("[REC] %d frames", recCount))
        end
    end
    -- ============================================

    -- Detect and log events
    detectEvents(state, ents)

    -- Periodic summary every 30s
    if f % 1800 == 0 then logSummary(state, ents, "STATUS") end

    -- Runtime limit
    if f >= MAX_RUNTIME then
        logSummary(state, ents, "FINAL")
        if rec then logMsg(string.format("[REC] total %d frames", recCount)); rec:close(); rec = nil end
        log:close()
        emu:stop()
    end
end)

callbacks:add("shutdown", function()
    if log then logMsg("END"); log:close(); log = nil end
    if rec then rec:close(); rec = nil end
end)
