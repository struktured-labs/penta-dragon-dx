-- Live palette editor — polls /tmp/live_palettes.txt and writes CGB CRAM
local f = 0
local last_hash = 0
local PAL_FILE = "/home/struktured/projects/penta-dragon-dx-claude/rom/working/live_palettes.txt"
local SENTINEL = "/home/struktured/projects/penta-dragon-dx-claude/rom/working/live_palettes_lua.log"

-- Log to sentinel file (since mGBA print may not go to stdout)
local function log(msg)
    local fh = io.open(SENTINEL, "a")
    if fh then
        fh:write(msg .. "\n")
        fh:close()
    end
end

-- Reset log on startup
local fh = io.open(SENTINEL, "w")
if fh then fh:write("live_palettes.lua loaded at start\n"); fh:close() end

local function parse_color(s)
    if #s == 6 then
        local r = tonumber(s:sub(1,2), 16) or 0
        local g = tonumber(s:sub(3,4), 16) or 0
        local b = tonumber(s:sub(5,6), 16) or 0
        local r5 = math.floor(r * 31 / 255)
        local g5 = math.floor(g * 31 / 255)
        local b5 = math.floor(b * 31 / 255)
        return (b5 << 10) | (g5 << 5) | r5
    elseif #s == 4 then
        return tonumber(s, 16) or 0
    end
    return 0
end

-- Parsed file contains:
--   writes:    list of palette overrides applied every frame
--   force:     {addr=value, ...} - HRAM/WRAM bytes to set every frame
--   dx_teleport: integer DF0A value (one-shot DX boss teleport request)
local function load_palettes(path)
    local fh = io.open(path, "r")
    if not fh then return nil end
    local txt = fh:read("*all")
    fh:close()
    local result = {writes = {}, force = {}, dx_teleport = nil}
    for line in txt:gmatch("[^\r\n]+") do
        if line:sub(1,1) == "#" then
            -- comment, skip
        elseif line:match("^DX:") then
            -- DX teleport one-shot directive: "DX:N" sets DF0A=N once
            local n = line:match("^DX:(%d+)")
            if n then result.dx_teleport = tonumber(n) end
        else
            local kind, pal_idx, colors = line:match("^(OBJ)(%d):(.+)$")
            if not kind then
                kind, pal_idx, colors = line:match("^(BG)(%d):(.+)$")
            end
            if kind and pal_idx then
                local is_obj = kind == "OBJ"
                pal_idx = tonumber(pal_idx)
                for entry in colors:gmatch("[^,]+") do
                    local ci, cv = entry:match("^%s*(%d+)=(%w+)%s*$")
                    if ci and cv then
                        ci = tonumber(ci)
                        local val15 = parse_color(cv)
                        local base = pal_idx * 8 + ci * 2
                        table.insert(result.writes, {
                            is_obj = is_obj, idx = base,
                            lo = val15 & 0xFF, hi = (val15 >> 8) & 0xFF,
                        })
                    end
                end
            else
                -- Try byte-write directives: FFBF:N, FFBA:N, D880:0xXX, FFB7:0xXX
                local reg, val = line:match("^(%w+):(%S+)$")
                if reg and val then
                    local v
                    if val:sub(1,2) == "0x" or val:sub(1,2) == "0X" then
                        v = tonumber(val:sub(3), 16)
                    else
                        v = tonumber(val)
                    end
                    if v then
                        local addr
                        if reg == "FFBF" then addr = 0xFFBF
                        elseif reg == "FFBA" then addr = 0xFFBA
                        elseif reg == "FFB7" then addr = 0xFFB7
                        elseif reg == "D880" then addr = 0xD880
                        elseif reg == "FFBE" then addr = 0xFFBE
                        elseif reg == "FFC0" then addr = 0xFFC0
                        elseif reg == "FFC1" then addr = 0xFFC1
                        elseif reg == "FFBD" then addr = 0xFFBD
                        elseif reg == "FFD0" then addr = 0xFFD0
                        elseif reg == "DF0A" then addr = 0xDF0A  -- DX teleport request
                        end
                        if addr then
                            result.force[addr] = v & 0xFF
                        end
                    end
                end
            end
        end
    end
    return result
end

local function apply_writes(writes)
    if not writes or #writes == 0 then return end
    for _, w in ipairs(writes) do
        if w.is_obj then
            emu:write8(0xFF6A, w.idx)
            emu:write8(0xFF6B, w.lo)
            emu:write8(0xFF6A, w.idx + 1)
            emu:write8(0xFF6B, w.hi)
        else
            emu:write8(0xFF68, w.idx)
            emu:write8(0xFF69, w.lo)
            emu:write8(0xFF68, w.idx + 1)
            emu:write8(0xFF69, w.hi)
        end
    end
end

-- Cached parsed data — applied EVERY frame so the game's cond_pal
-- can't override our changes when it triggers a palette reload on
-- state change (room transition, miniboss spawn, etc.)
local cached = nil

-- DX combo simulation (workaround for v17 freeze, see docs/HANDOFF_2026_06_01.md).
-- Strategy: pre-write FFBA so the ROM's INC lands on the target boss,
-- then pulse FF93=0x0C (SELECT+START) for several frames via emu:setKeys.
-- The ROM's existing combo handler at 0x6E80 reads FF93 and dispatches.
-- combo_state = {target = 0..8, phase = "pre"|"press"|"release", frames = N}
local combo_state = nil

-- One-shot title autostart. If /tmp/live_palettes_autostart sentinel exists
-- on Lua load, run the canonical DOWN→A→A→A→START→A title sequence at the
-- documented frames (180-396). Avoids manual keypresses inside mGBA.
local autostart_armed = false
do
    local fh = io.open("/home/struktured/projects/penta-dragon-dx-claude/rom/working/live_palettes_autostart", "r")
    if fh then autostart_armed = true; fh:close()
        log("autostart armed via rom/working/live_palettes_autostart")
    end
end
local AUTOSTART_KEYS = {{180,185,0x80},{193,198,0x01},{241,246,0x01},
                       {291,296,0x01},{341,346,0x08},{391,396,0x01}}

-- One-shot screenshot. Poll for /tmp/live_palettes_screenshot containing
-- a file path; when seen, save the current frame to that path and delete
-- the trigger. Lets external scripts capture frames without mgba MCP.
local last_shot_mtime = 0

callbacks:add("frame", function()
    f = f + 1
    if f == 30 then log("Lua frame=30, polling /tmp/live_palettes.txt") end

    -- Title autostart: only while armed and within the documented window.
    if autostart_armed and f <= 500 then
        local k = 0
        for _, e in ipairs(AUTOSTART_KEYS) do
            if f >= e[1] and f <= e[2] then k = e[3]; break end
        end
        if f <= 410 then emu:setKeys(k) end
        if f == 500 then
            autostart_armed = false
            os.remove("/home/struktured/projects/penta-dragon-dx-claude/rom/working/live_palettes_autostart")
            log(string.format("f%d: autostart finished, FFC1=%d D880=0x%02X",
                f, emu:read8(0xFFC1), emu:read8(0xD880)))
        end
    end

    -- Screenshot trigger: read rom/working/live_palettes_screenshot, save to that path.
    if f % 5 == 0 then
        local sfh = io.open("/home/struktured/projects/penta-dragon-dx-claude/rom/working/live_palettes_screenshot", "r")
        if sfh then
            local path = sfh:read("*all"):gsub("%s+$", "")
            sfh:close()
            if path and #path > 0 then
                emu:screenshot(path)
                log(string.format("f%d: screenshot saved to %s", f, path))
                os.remove("/home/struktured/projects/penta-dragon-dx-claude/rom/working/live_palettes_screenshot")
            end
        end
    end

    -- Check for file changes every 30 frames (~0.5s).
    if f % 30 == 0 then
        local fh = io.open(PAL_FILE, "r")
        if fh then
            local content = fh:read("*all")
            fh:close()
            local hash = 0
            for i = 1, #content do
                hash = (hash * 31 + content:byte(i)) & 0xFFFFFFFF
            end
            if hash ~= last_hash then
                last_hash = hash
                cached = load_palettes(PAL_FILE)
                local nw = cached and #cached.writes or 0
                local nf = 0
                if cached and cached.force then
                    for _ in pairs(cached.force) do nf = nf + 1 end
                end
                local nt = cached and cached.dx_teleport or 0
                log(string.format("f%d: Loaded %d writes, %d forces, dx_teleport=%d", f, nw, nf, nt))
                -- Queue combo simulation for DX teleport request
                if cached and cached.dx_teleport then
                    local target = cached.dx_teleport - 1   -- DF0A 1..9 → FFBA 0..8
                    combo_state = {target = target, phase = "pre", frames = 0}
                    cached.dx_teleport = nil  -- consume
                end
            end
        end
    end

    -- Apply palette overrides EVERY frame — EXCEPT during boss arenas.
    -- Each boss arena (D880 0x0C..0x14) loads its OWN native CRAM; the editor
    -- pushes the dungeon YAML palettes, which would clobber the arena's colors
    -- (muted Ted's cyan dome/green tendrils to gray). Skip BG/OBJ pushes in
    -- arenas so the live preview matches the real ROM. (Combo + force-writes
    -- still run, so teleport keeps working.) Dungeon palette tuning unaffected.
    local d880 = emu:read8(0xD880)
    local in_arena = d880 >= 0x0C and d880 <= 0x14
    if cached and not in_arena then apply_writes(cached.writes) end

    -- Apply force writes EVERY frame (e.g., FFBF=3 for boss preview)
    if cached and cached.force then
        for addr, val in pairs(cached.force) do
            emu:write8(addr, val)
        end
    end

    -- DX combo simulator state machine.
    -- The v16 teleport ROM (`penta_dragon_dx_teleport.gb`) checks FF93 for
    -- 0x0C (SELECT+START) in its 0x6E80 routine and cycles FFBA via INC,
    -- wrap-at-9. To land on target boss N: pre-set FFBA = (N - 1) mod 9
    -- so the ROM's INC arrives at N. Wraps cleanly for N=0 → pre=8 → INC=9
    -- → "CP 9; XOR A" → 0.
    -- Note: this overrides player joypad input for ~10 frames. Acceptable
    -- for a "click teleport in browser" feature; player likely isn't also
    -- mashing buttons.
    if combo_state then
        if combo_state.phase == "pre" then
            -- Pre-write FFBA so ROM's INC lands on target
            local pre = combo_state.target - 1
            if pre < 0 then pre = 8 end
            emu:write8(0xFFBA, pre)
            log(string.format("f%d: combo PRE target=%d, FFBA=%d", f, combo_state.target, pre))
            combo_state.phase = "press"
            combo_state.frames = 6  -- hold SELECT+START for 6 frames
        elseif combo_state.phase == "press" then
            emu:setKeys(0x0C)  -- SELECT + START
            combo_state.frames = combo_state.frames - 1
            if combo_state.frames <= 0 then
                combo_state.phase = "release"
                combo_state.frames = 6
            end
        elseif combo_state.phase == "release" then
            emu:setKeys(0)
            combo_state.frames = combo_state.frames - 1
            if combo_state.frames <= 0 then
                log(string.format("f%d: combo DONE D880=0x%02X FFBA=%d",
                    f, emu:read8(0xD880), emu:read8(0xFFBA)))
                combo_state = nil
            end
        end
    end
end)
