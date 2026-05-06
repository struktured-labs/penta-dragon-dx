-- Human-play recorder for Penta Dragon DX.
--
-- Usage: launch mgba-qt with this script, watch title-menu auto-nav for a few
-- seconds, then YOU control the game from your keyboard. Recording starts
-- automatically once gameplay state (FFC1=1) is reached.
--
-- mgba default keymap: arrows = D-pad, X = A (fire), Z = B, Enter = Start, Backspace = Select
--
-- Records JSONL to rl/bc_data/expert_human.jsonl in PentaEnv schema with OAM.

local f = 0
local recording = false
local recCount = 0
local lastSummary = 0

-- Auto-nav title menu (verified working sequence)
local KEY_A=0x01; local KEY_B=0x02; local KEY_SELECT=0x04; local KEY_START=0x08
local KEY_RIGHT=0x10; local KEY_LEFT=0x20; local KEY_UP=0x40; local KEY_DOWN=0x80
local TITLE = {
    {180,185,KEY_DOWN}, {193,198,KEY_A}, {241,246,KEY_A},
    {291,296,KEY_A}, {341,346,KEY_START}, {391,396,KEY_A},
}
local TITLE_END = 500   -- after this, hand control to player

local REC_PATH = os.getenv("REC_PATH") or "/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/expert_human.jsonl"
os.execute("mkdir -p /home/struktured/projects/penta-dragon-dx-claude/rl/bc_data")
local rec = io.open(REC_PATH, "w")
if not rec then console:log("FATAL: cannot open " .. REC_PATH); return end
console:log("[REC] writing to " .. REC_PATH)
console:log("[REC] auto-navigating title menu (~8s)...")
console:log("[REC] then YOU PLAY: arrows=D-pad, Z=A, X=B, Enter=Start, Backspace=Select")

callbacks:add("frame", function()
    f = f + 1

    -- Title nav: drive game to gameplay
    if f <= TITLE_END then
        local k = 0
        for _, e in ipairs(TITLE) do
            if f >= e[1] and f <= e[2] then k = e[3]; break end
        end
        emu:setKeys(k)
        return
    end

    -- Hand control to player. Do NOT call setKeys(0) — that can persistently
    -- override keyboard input in some mgba builds. Just stop calling setKeys.
    if f == TITLE_END + 1 then
        console:log("[REC] *** YOUR TURN — play now! Recording starts when in gameplay ***")
        console:log("[REC] If keys feel wonky: check mgba Settings → Tools → Input")
    end

    -- Wait for gameplay state
    local ffc1 = emu:read8(0xFFC1)
    if not recording then
        if ffc1 == 1 then
            recording = true
            console:log(string.format("[REC] gameplay reached at frame %d — recording starts", f))
        else
            return
        end
    end

    -- Only record every 4 frames (matches PentaEnv frame_skip)
    if f % 4 ~= 0 then return end

    -- Read user's keys via FF93 (raw joypad register the game stored)
    local keys = emu:read8(0xFF93)

    -- Convert key bitmask → action_idx (same as autoplay_v96_record.lua)
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

    -- OAM features
    local OAM_X_OFF = 8; local OAM_Y_OFF = 16
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
    rec:write("]")  -- close slots array
    -- Inventory region D840-D89F (96 bytes) for item state
    rec:write(',"inv":[')
    for ia = 0xD840, 0xD89F do
        rec:write(tostring(emu:read8(ia)))
        if ia < 0xD89F then rec:write(",") end
    end
    -- FULL WRAM (8KB) + HRAM + OAM as hex — future-proofs against state-vector
    -- schema changes. ~17KB per frame; recording stays manageable.
    rec:write('],"wram":"')
    for a = 0xC000, 0xDFFF do rec:write(string.format("%02X", emu:read8(a))) end
    rec:write('","hram":"')
    for a = 0xFF80, 0xFFFE do rec:write(string.format("%02X", emu:read8(a))) end
    rec:write('","oam_raw":"')
    for a = 0xFE00, 0xFE9F do rec:write(string.format("%02X", emu:read8(a))) end
    rec:write(string.format('","oam":{"sara_x":%d,"sara_y":%d,"boss_x":%d,"boss_y":%d,"boss_count":%d,"near_x":%d,"near_y":%d,"near_dist":%d,"proj_count":%d}}\n',
        math.floor(sara_x_avg), math.floor(sara_y_avg),
        math.floor(boss_x_avg), math.floor(boss_y_avg), boss_n,
        math.floor(near_sx), math.floor(near_sy), math.floor(near_d), proj_n))
    recCount = recCount + 1

    -- Periodic summary (every 30 sec)
    if f - lastSummary >= 1800 then
        lastSummary = f
        rec:flush()
        local dcbb = emu:read8(0xDCBB)
        local boss = emu:read8(0xFFBF)
        console:log(string.format("[REC] %ds played, %d frames recorded, FFBF=0x%02X DCBB=0x%02X",
            math.floor((f - TITLE_END) / 60), recCount, boss, dcbb))
    end
end)

callbacks:add("shutdown", function()
    if rec then
        console:log(string.format("[REC] FINAL: %d frames recorded", recCount))
        rec:close(); rec = nil
    end
end)
