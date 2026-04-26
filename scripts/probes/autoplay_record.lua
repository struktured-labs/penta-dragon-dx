-- Penta Dragon Auto-play v11.0 "Full Game"
-- Plays through ALL 8 levels × 16 bosses by switching pointer tables via FFAC/FFAD
-- Infinite HP + FFAC/FFAD level switching + section forcing = full game tour
--
-- Level structure (from ROM investigation):
--   Level 1: Gargoyle + Spider (6 entries)
--   Level 2: Crimson + Ice (16 entries)
--   Level 3: Void + Poison (18 entries)
--   Level 4: ALL 8 bosses cycling (25 entries) — Knight + Angela first appear here!
--   Level 5: Boss9 + Boss10 (12 entries)
--   Level 6: Boss11 + Boss12 (16 entries)
--   Level 7: Boss13 + Boss14 + all prev bosses (24 entries)
--   Level 8: Boss15 + Boss16 (6 entries)

local BASE = "/home/struktured/projects/penta-dragon-dx-claude"
local LOG_PATH = BASE .. "/tmp/game_start_test/autoplay_full_log.txt"
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

local ENEMY_PROJ_TILES = {[0x00]=true, [0x01]=true}
local SARA_PROJ_TILES = {[0x06]=true, [0x09]=true, [0x0A]=true, [0x0F]=true}
local ENEMY_BODY_MIN = 0x30
local ENEMY_BODY_MAX = 0x7F

local MAX_RUNTIME = 108000  -- 30 min real run (~27000 recorded frames at /4)
local ENTITY_SLOT_ADDRS = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}

-- ALL 16 bosses
local BOSS_NAMES = {
    "Gargoyle","Spider","Crimson","Ice","Void","Poison","Knight","Angela",
    "Boss9","Boss10","Boss11","Boss12","Boss13","Boss14","Boss15","Boss16"
}

-- Level pointer table data: FFAC, FFAD, entry count, level name
local LEVELS = {
    {ffac=0x00, ffad=0x40, count=6,  name="Level 1 (Gargoyle+Spider)"},
    {ffac=0xC8, ffad=0x43, count=16, name="Level 2 (Crimson+Ice)"},
    {ffac=0x3F, ffad=0x46, count=18, name="Level 3 (Void+Poison)"},
    {ffac=0x42, ffad=0x4C, count=25, name="Level 4 (All 8 bosses)"},
    {ffac=0xF2, ffad=0x4C, count=12, name="Level 5 (Boss9+Boss10)"},
    {ffac=0xFD, ffad=0x4D, count=16, name="Level 6 (Boss11+Boss12)"},
    {ffac=0x10, ffad=0x50, count=24, name="Level 7 (Boss13+Boss14+all)"},
    {ffac=0xEF, ffad=0x50, count=6,  name="Level 8 (Boss15+Boss16)"},
}

local TITLE_SCHEDULE = {
    {180, 185, KEY_DOWN}, {186, 200, 0}, {201, 206, KEY_A}, {207, 260, 0},
    {261, 266, KEY_A}, {267, 320, 0}, {321, 326, KEY_A}, {327, 380, 0},
    {381, 386, KEY_START}, {387, 430, 0}, {431, 436, KEY_A},
}

-- State
local f = 0
local gameStartFrame = 0
local gameState = "title_menu"
local stateEntryFrame = 0
local saveSlot = 1
local screenshotCount = 0
local bossKillCount = 0
local uniqueBosses = {}
local currentLevel = 1      -- which level we're on (1-8)
local levelBossKills = 0    -- bosses killed in current level
local sectionForceEnd = 0
local levelSwitchDone = false
local prev = { boss=0, room=0, ffc1=0 }

-- ============================================================
-- LOGGING
-- ============================================================

local log = io.open(LOG_PATH, "w")
if not log then console:log("ERROR: cannot open log"); return end

-- BC trajectory recorder (JSONL)
local REC_PATH = "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_trajectories.jsonl"
os.execute("mkdir -p /home/struktured/projects/penta-dragon-dx-claude/rl/bc_data")
local rec = io.open(REC_PATH, "w")
local recCount = 0
if rec then console:log("[REC] writing to " .. REC_PATH) end

local function logMsg(msg)
    local s = string.format("f%05d: %s", f, msg)
    log:write(s .. "\n"); log:flush()
    console:log(s)
end

-- ============================================================
-- LEVEL SWITCHING
-- ============================================================

local function switchToLevel(lvl)
    if lvl < 1 or lvl > 8 then return end
    local level = LEVELS[lvl]
    emu:write8(0xFFAC, level.ffac)
    emu:write8(0xFFAD, level.ffad)
    emu:write8(0xDCB8, 0)  -- reset section counter to start of new level
    currentLevel = lvl
    levelBossKills = 0
    logMsg(string.format("=== LEVEL SWITCH → %d: %s ===", lvl, level.name))
    logMsg(string.format("  FFAC=%02X FFAD=%02X count=%d DCB8=0", level.ffac, level.ffad, level.count))
end

-- ============================================================
-- ENTITY SCANNER
-- ============================================================

local function scanEntities()
    local bossSprites = {}
    local nearDist = 999
    local nearX, nearY = 0, 0
    local boss = emu:read8(0xFFBF)

    local sx, sy, n = 0, 0, 0
    for _, slot in ipairs(SARA_SLOTS) do
        local addr = OAM_BASE + slot * 4
        local y = emu:read8(addr)
        local x = emu:read8(addr + 1)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            sx = sx + (x - OAM_X_OFFSET); sy = sy + (y - OAM_Y_OFFSET); n = n + 1
        end
    end
    local saraX = n > 0 and math.floor(sx / n) or 80
    local saraY = n > 0 and math.floor(sy / n) or 72

    for slot = ENEMY_SLOT_START, MAX_SPRITES - 1 do
        local addr = OAM_BASE + slot * 4
        local y = emu:read8(addr)
        local x = emu:read8(addr + 1)
        local tile = emu:read8(addr + 2)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            local ex = x - OAM_X_OFFSET
            local ey = y - OAM_Y_OFFSET
            if ENEMY_PROJ_TILES[tile] then
                local d = math.sqrt((ex-saraX)^2 + (ey-saraY)^2)
                if d < nearDist then nearDist = d; nearX = ex; nearY = ey end
            elseif tile >= ENEMY_BODY_MIN and tile <= ENEMY_BODY_MAX then
                if boss > 0 then
                    table.insert(bossSprites, {x=ex, y=ey})
                else
                    local d = math.sqrt((ex-saraX)^2 + (ey-saraY)^2)
                    if d < nearDist then nearDist = d; nearX = ex; nearY = ey end
                end
            end
        end
    end

    return {saraX=saraX, saraY=saraY, bossSprites=bossSprites,
            nearDist=nearDist, nearX=nearX, nearY=nearY}
end

-- ============================================================
-- MOVEMENT
-- ============================================================

local function getKeys(ents)
    local boss = emu:read8(0xFFBF)
    local keys = 0

    if boss > 0 then
        -- Boss fight: track + fire + dodge
        if f % 3 < 2 then keys = keys + KEY_A end
        if #ents.bossSprites > 0 then
            local bx, by = 0, 0
            for _, b in ipairs(ents.bossSprites) do bx = bx + b.x; by = by + b.y end
            bx = bx / #ents.bossSprites; by = by / #ents.bossSprites
            local dx = bx - ents.saraX
            local dy = by - ents.saraY
            local dist = math.sqrt(dx*dx + dy*dy)
            if dist > 70 then keys = keys + (dx > 0 and KEY_RIGHT or KEY_LEFT)
            elseif dist < 30 then keys = keys + (dx > 0 and KEY_LEFT or KEY_RIGHT)
            else
                local cy = f % 240
                if cy < 60 then keys = keys + KEY_UP
                elseif cy < 120 then keys = keys + KEY_RIGHT
                elseif cy < 180 then keys = keys + KEY_DOWN
                else keys = keys + KEY_LEFT end
            end
            if math.abs(dy) > 16 then
                keys = keys + (dy > 0 and KEY_DOWN or KEY_UP)
            end
        else
            local cy = f % 180
            keys = keys + (cy < 90 and KEY_RIGHT or KEY_LEFT)
        end
    else
        -- Explore: RIGHT + fire + sine
        keys = KEY_RIGHT
        if f % 4 < 2 then keys = keys + KEY_A end
        local cycle = f % 180
        if cycle < 45 then keys = keys + KEY_UP
        elseif cycle >= 90 and cycle < 135 then keys = keys + KEY_DOWN end
        if ents.saraY < 30 then keys = keys + KEY_DOWN
        elseif ents.saraY > 110 then keys = keys + KEY_UP end
    end

    -- Dodge
    if ents.nearDist < 30 then
        local dx = ents.nearX - ents.saraX
        local dy = ents.nearY - ents.saraY
        if math.abs(dy) < 20 then
            keys = keys + (dy >= 0 and KEY_UP or KEY_DOWN)
        end
        if math.abs(dx) < 16 then
            keys = keys + (dx >= 0 and KEY_LEFT or KEY_RIGHT)
        end
    end

    return keys
end

-- ============================================================
-- SCREENSHOTS
-- ============================================================

local function takeScreenshot(label)
    if screenshotCount >= 300 then return end
    screenshotCount = screenshotCount + 1
    local path = string.format("%s/full_%03d_%s.png", SCREENSHOT_DIR, screenshotCount, label)
    emu:screenshot(path)
    logMsg("SCREENSHOT[" .. screenshotCount .. "]: " .. label)
end

local function saveState(reason)
    if saveSlot > 9 then saveSlot = 1 end
    emu:saveStateSlot(saveSlot)
    logMsg("SAVE[" .. saveSlot .. "]: " .. reason)
    saveSlot = saveSlot + 1
end

-- ============================================================
-- MAIN
-- ============================================================

logMsg("=== PENTA DRAGON AUTO-PLAY v11.0 FULL GAME ===")
logMsg("ALL 8 levels, 16 bosses, via FFAC/FFAD pointer table switching")
logMsg("Cheats: infinite HP + level switching + section forcing")

callbacks:add("frame", function()
    f = f + 1

    -- Title menu
    if gameState == "title_menu" then
        local keys = 0
        for _, e in ipairs(TITLE_SCHEDULE) do
            if f >= e[1] and f <= e[2] then keys = e[3]; break end
        end
        emu:setKeys(keys)

        if emu:read8(0xFFC1) == 1 then
            gameStartFrame = f
            gameState = "playing"
            prev.ffc1 = 1
            prev.room = emu:read8(0xFFBD)
            prev.boss = emu:read8(0xFFBF)
            logMsg("*** GAME STARTED ***")
            logMsg(string.format("  room=%02X boss=%02X ffac=%02X ffad=%02X dcb8=%d",
                prev.room, prev.boss, emu:read8(0xFFAC), emu:read8(0xFFAD), emu:read8(0xDCB8)))
            takeScreenshot("start")
            saveState("start")
            -- Start at Level 1 (already default)
            logMsg("Starting at Level 1 — natural Gargoyle + Spider")
        end

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

    local boss = emu:read8(0xFFBF)
    local ffc1 = emu:read8(0xFFC1)

    -- Section forcing: keep DCBA armed and entity slots clear
    if f <= sectionForceEnd and boss == 0 then
        if emu:read8(0xFFD6) < 0x1E then emu:write8(0xFFD6, 0x1E) end
        emu:write8(0xDCBA, 0x01)
        if f % 15 == 0 then
            for _, addr in ipairs(ENTITY_SLOT_ADDRS) do
                emu:write8(addr, 0x00)
            end
        end
    end

    -- FFC1 drop detection (game over / menu return)
    if ffc1 ~= prev.ffc1 then
        logMsg(string.format("FFC1: %02X -> %02X", prev.ffc1, ffc1))
        if ffc1 == 0 then
            logMsg("*** RETURNED TO MENU ***")
            takeScreenshot("menu_return_L" .. currentLevel)
            saveState("menu_return")
        end
        prev.ffc1 = ffc1
    end

    -- Boss events
    if boss ~= prev.boss then
        if boss > 0 then
            local bossNum = boss
            uniqueBosses[bossNum] = true
            local bName = BOSS_NAMES[bossNum] or ("Boss" .. bossNum)
            local ubCount = 0; for _ in pairs(uniqueBosses) do ubCount = ubCount + 1 end

            -- Log BEFORE screenshot (screenshot may corrupt IO)
            logMsg(string.format("BOSS: %s (#%d) [L%d unique:%d/16]", bName, bossNum, currentLevel, ubCount))
            logMsg(string.format("  dcb8=%d dc04=%02X ffac=%02X ffad=%02X room=%02X",
                emu:read8(0xDCB8), emu:read8(0xDC04), emu:read8(0xFFAC), emu:read8(0xFFAD), emu:read8(0xFFBD)))
            takeScreenshot("boss_" .. bName .. "_L" .. currentLevel)
            saveState("boss_" .. bName)
        else
            -- Boss killed!
            bossKillCount = bossKillCount + 1
            levelBossKills = levelBossKills + 1
            local bName = BOSS_NAMES[prev.boss] or ("Boss" .. prev.boss)
            local ubCount = 0; for _ in pairs(uniqueBosses) do ubCount = ubCount + 1 end

            logMsg(string.format("KILL: %s #%d (L%d kill#%d) [unique:%d/16]",
                bName, bossKillCount, currentLevel, levelBossKills, ubCount))

            -- After killing 2 bosses in a level, advance to next level
            -- (Each level introduces 2 new bosses)
            if levelBossKills >= 2 then
                local nextLevel = currentLevel + 1
                if nextLevel <= 8 then
                    logMsg(string.format("*** LEVEL %d COMPLETE — advancing to Level %d ***", currentLevel, nextLevel))
                    switchToLevel(nextLevel)
                else
                    logMsg("*** ALL 8 LEVELS COMPLETE! ***")
                    takeScreenshot("all_levels_complete")
                    saveState("all_complete")
                    -- Restart from level 1 for victory lap
                    switchToLevel(1)
                end
            end

            -- Activate section forcing for next boss spawn
            sectionForceEnd = f + 36000
            -- Reset DCB8 to ensure we hit boss entries quickly
            emu:write8(0xDCB8, 1)

            -- Screenshot LAST
            takeScreenshot("kill_" .. bName .. "_L" .. currentLevel .. "_" .. bossKillCount)
            saveState("kill_" .. bName)
        end
        prev.boss = boss
    end

    -- Scan and move
    local ents = scanEntities()
    local keys = getKeys(ents)
    emu:setKeys(keys)

    -- ============== BC RECORDING ==============
    -- Convert key bitmask → discrete action_idx (matches PentaEnv N_ACTIONS=12)
    -- 0=A, 1=B, 2=Sel, 3=Start, 4=R, 5=L, 6=U, 7=D
    -- 8=U+A, 9=D+A, 10=L+B, 11=R+B
    local function keys_to_action(k)
        if k == 0x01 then return 0 end
        if k == 0x02 then return 1 end
        if k == 0x04 then return 2 end
        if k == 0x08 then return 3 end
        if k == 0x10 then return 4 end
        if k == 0x20 then return 5 end
        if k == 0x40 then return 6 end
        if k == 0x80 then return 7 end
        if k == (0x40 + 0x01) then return 8 end
        if k == (0x80 + 0x01) then return 9 end
        if k == (0x20 + 0x02) then return 10 end
        if k == (0x10 + 0x02) then return 11 end
        -- Approximate: if A bit set with another button → use combo if matches, else fall back
        if k % 2 == 1 then  -- A bit set
            if k % 0x80 >= 0x40 then return 8 end  -- has UP
            if k >= 0x80 then return 9 end          -- has DOWN
            return 0  -- A alone fallback
        end
        if (k - (k % 4)) % 4 >= 2 then  -- B bit set
            if (k % 0x40) >= 0x20 then return 10 end
            if (k % 0x20) >= 0x10 then return 11 end
            return 1
        end
        if k % 0x80 >= 0x40 then return 6 end  -- UP only
        if k >= 0x80 then return 7 end
        if (k % 0x40) >= 0x20 then return 5 end
        if (k % 0x20) >= 0x10 then return 4 end
        return 0  -- default: A
    end
    local action_idx = keys_to_action(keys)

    -- Record state every 4 frames (matches PentaEnv frame_skip)
    if rec ~= nil and f % 4 == 0 then
        -- Build state dict matching PentaEnv schema
        local s = {
            f = f,
            action = action_idx,
            keys = keys,
            -- Scalars
            D880 = emu:read8(0xD880), FFBA = emu:read8(0xFFBA),
            FFBD = emu:read8(0xFFBD), FFBE = emu:read8(0xFFBE),
            FFBF = emu:read8(0xFFBF), FFC0 = emu:read8(0xFFC0),
            FFC1 = emu:read8(0xFFC1),
            DCBB = emu:read8(0xDCBB), DCDC = emu:read8(0xDCDC),
            DCDD = emu:read8(0xDCDD),
            DCB8 = emu:read8(0xDCB8),
            FFAC = emu:read8(0xFFAC), FFAD = emu:read8(0xFFAD),
            FFCF = emu:read8(0xFFCF),
            SCY = emu:read8(0xFF42), SCX = emu:read8(0xFF43),
            DC04 = emu:read8(0xDC04),
            slots = {},
        }
        -- Entity slots (5 × 8)
        local slot_addrs = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
        for _, addr in ipairs(slot_addrs) do
            local row = {}
            for j = 0, 7 do row[#row+1] = emu:read8(addr + j) end
            s.slots[#s.slots+1] = row
        end
        -- Emit JSONL
        rec:write("{")
        rec:write(string.format('"f":%d,"action":%d,"keys":%d,', s.f, s.action, s.keys))
        rec:write(string.format('"D880":%d,"FFBA":%d,"FFBD":%d,"FFBE":%d,"FFBF":%d,"FFC0":%d,"FFC1":%d,',
                                s.D880, s.FFBA, s.FFBD, s.FFBE, s.FFBF, s.FFC0, s.FFC1))
        rec:write(string.format('"DCBB":%d,"DCDC":%d,"DCDD":%d,"DCB8":%d,', s.DCBB, s.DCDC, s.DCDD, s.DCB8))
        rec:write(string.format('"FFAC":%d,"FFAD":%d,"FFCF":%d,"SCY":%d,"SCX":%d,"DC04":%d,',
                                s.FFAC, s.FFAD, s.FFCF, s.SCY, s.SCX, s.DC04))
        rec:write('"slots":[')
        for i, row in ipairs(s.slots) do
            rec:write("[")
            for j, b in ipairs(row) do
                rec:write(tostring(b))
                if j < #row then rec:write(",") end
            end
            rec:write("]")
            if i < #s.slots then rec:write(",") end
        end
        rec:write("]}\n")
        recCount = recCount + 1
        if recCount % 5000 == 0 then
            rec:flush()
            logMsg(string.format("[REC] %d frames logged", recCount))
        end
    end
    -- ============================================

    -- Periodic summary every 30s
    if f % 1800 == 0 then
        local t = (f - gameStartFrame) / 60.0
        local ubCount = 0; local bList = ""
        for k in pairs(uniqueBosses) do ubCount = ubCount + 1; bList = bList .. (BOSS_NAMES[k] or "?") .. " " end
        logMsg(string.format("[STATUS %.0fs] L%d kills=%d(%d) unique=%d/16 dcb8=%d boss=%02X room=%02X",
            t, currentLevel, bossKillCount, levelBossKills,
            ubCount, emu:read8(0xDCB8), boss, emu:read8(0xFFBD)))
        logMsg(string.format("  ffac=%02X ffad=%02X dc04=%02X [%s]",
            emu:read8(0xFFAC), emu:read8(0xFFAD), emu:read8(0xDC04), bList))
    end

    -- Runtime limit
    if f >= MAX_RUNTIME then
        local ubCount = 0; local bList = ""
        for k in pairs(uniqueBosses) do ubCount = ubCount + 1; bList = bList .. (BOSS_NAMES[k] or "?") .. " " end
        logMsg(string.format("=== FINAL: %d kills, %d/16 unique bosses, level %d ===", bossKillCount, ubCount, currentLevel))
        logMsg("  Bosses: " .. bList)
        if rec then logMsg(string.format("[REC] total %d frames written", recCount)); rec:close(); rec = nil end
        log:close(); emu:stop()
    end
end)

callbacks:add("shutdown", function()
    if log then logMsg("END"); log:close(); log = nil end
    if rec then rec:close(); rec = nil end
end)
