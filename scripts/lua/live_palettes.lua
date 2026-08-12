-- Live palette editor — polls a local override file and writes CGB CRAM.
-- Scene buttons load whitelisted mGBA states; no in-ROM teleport is used.
local f = 0
local last_hash = 0
local ROOT = "/home/struktured/projects/penta-dragon-dx-claude"
local PAL_FILE = os.getenv("LIVE_PALETTE_FILE") or
    (ROOT .. "/rom/working/live_palettes.txt")
local SENTINEL = os.getenv("LIVE_PALETTE_LOG") or
    (ROOT .. "/rom/working/live_palettes_lua.log")
local SMOKE_OUT = os.getenv("LIVE_PALETTE_SMOKE_OUT")
local VISUAL_AUDIT_OUT = os.getenv("LIVE_PALETTE_VISUAL_AUDIT_OUT")
local SCENE_AUDIT_OUT = os.getenv("LIVE_PALETTE_SCENE_AUDIT_OUT")
local SPECIAL_AUDIT_OUT = os.getenv("LIVE_PALETTE_SPECIAL_AUDIT_OUT")
local STATE_ROOT = ROOT .. "/save_states_for_claude"
local STAGE_STATE_DIR = os.getenv("LIVE_PALETTE_STAGE_STATE_DIR") or
    (ROOT .. "/tmp/palette_session/states")
local BOSS_STATE_DIR = os.getenv("LIVE_PALETTE_BOSS_STATE_DIR") or
    (ROOT .. "/tmp/palette_session/boss_states")
local STORY_STATE_DIR = os.getenv("LIVE_PALETTE_STORY_STATE_DIR") or
    (ROOT .. "/tmp/palette_session/story_states")

local SCENE_FILES = {
    title = STATE_ROOT .. "/title_screen.ss0",
    opening = STORY_STATE_DIR .. "/opening.ss0",
    opening_book = STORY_STATE_DIR .. "/opening_book.ss0",
    opening_sara = STORY_STATE_DIR .. "/opening_sara.ss0",
    opening_dragon_eye = STORY_STATE_DIR .. "/opening_dragon_eye.ss0",
    pre_final_story = STORY_STATE_DIR .. "/pre_final.ss0",
    pre_final_sara = STORY_STATE_DIR .. "/pre_final_sara.ss0",
    post_final_story = STORY_STATE_DIR .. "/post_final.ss0",
    post_final_lisa = STORY_STATE_DIR .. "/post_final_lisa.ss0",
    post_final_sara = STORY_STATE_DIR .. "/post_final_sara.ss0",
    ending_credits = STORY_STATE_DIR .. "/ending_credits.ss0",
    ending_end = STORY_STATE_DIR .. "/ending_end.ss0",
    ending_epilogue = STORY_STATE_DIR .. "/ending_epilogue.ss0",
    stage2 = STAGE_STATE_DIR .. "/stage2.ss0",
    stage3 = STAGE_STATE_DIR .. "/stage3.ss0",
    stage4 = STAGE_STATE_DIR .. "/stage4.ss0",
    stage5 = STAGE_STATE_DIR .. "/stage5.ss0",
    stage6 = STAGE_STATE_DIR .. "/stage6.ss0",
    stage7 = STAGE_STATE_DIR .. "/stage7.ss0",
    boss_shalamar = BOSS_STATE_DIR .. "/boss0_shalamar.ss0",
    boss_riff = BOSS_STATE_DIR .. "/boss1_riff.ss0",
    boss_crystal_dragon = BOSS_STATE_DIR .. "/boss2_crystal_dragon.ss0",
    boss_cameo = BOSS_STATE_DIR .. "/boss3_cameo.ss0",
    boss_ted = BOSS_STATE_DIR .. "/boss4_ted.ss0",
    boss_troop = BOSS_STATE_DIR .. "/boss5_troop.ss0",
    boss_faze = BOSS_STATE_DIR .. "/boss6_faze.ss0",
    boss_angela = BOSS_STATE_DIR .. "/boss7_angela.ss0",
    boss_penta_dragon = BOSS_STATE_DIR .. "/boss8_penta_dragon.ss0",
    witch = STATE_ROOT .. "/level1_sara_w_alone.ss0",
    dragon = STATE_ROOT .. "/level1_sara_d_alone.ss0",
    crow = STATE_ROOT .. "/level1_sara_w_crow.ss0",
    hornets = STATE_ROOT .. "/level1_sara_w_4_hornets.ss0",
    orc = STATE_ROOT .. "/level1_sara_w_orc.ss0",
    soldier = STATE_ROOT .. "/level1_sara_w_soldier.ss0",
    mage = STATE_ROOT .. "/level1_sara_w_mage_health1_items.ss0",
    mixed = STATE_ROOT .. "/level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    gargoyle = STATE_ROOT .. "/level1_sara_w_gargoyle_mini_boss.ss0",
    spider = STATE_ROOT .. "/level1_sara_w_spier_miniboss.ss0",
    spiral = STATE_ROOT ..
        "/sara_d_special_spiral_weapon_activated_level1_v_2.31.ss0",
    shield = STATE_ROOT .. "/level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    jet = STATE_ROOT .. "/level1_sara_w_in_jet_form_secret_stage.ss0",
    menu = STATE_ROOT .. "/level1_square_cat_fish_menu_open.ss0",
}
local SCENE_ORDER = {
    "title", "opening", "opening_book", "opening_sara",
    "opening_dragon_eye", "pre_final_story", "pre_final_sara",
    "post_final_story", "post_final_lisa", "post_final_sara",
    "ending_credits", "ending_end", "ending_epilogue",
    "stage2", "stage3", "stage4", "stage5", "stage6", "stage7",
    "boss_shalamar", "boss_riff", "boss_crystal_dragon", "boss_cameo",
    "boss_ted", "boss_troop", "boss_faze", "boss_angela",
    "boss_penta_dragon",
    "witch", "dragon", "crow", "hornets", "orc", "soldier", "mage",
    "mixed", "gargoyle", "spider", "spiral", "shield", "jet", "menu",
}

-- Emulator-only cutscene preview. The stock ROM leaves all story tile
-- attributes on BG0. For these ROM-matched, explicitly selected states only,
-- color the top eight artwork rows with the matching BG1..BG7 palette while
-- keeping the separator and dialogue box (rows 8-17) on BG0. The complete
-- stock story discriminator is
-- required so stale DCF0/DD07 bytes cannot color another scene.
local STORY_ART_SCENES = {
    opening_book = {
        d880 = 0x15, sequence = 0x02, art = 0x01,
    },
    opening_sara = {
        d880 = 0x15, sequence = 0x02, art = 0x02,
    },
    opening_dragon_eye = {
        d880 = 0x15, sequence = 0x02, art = 0x03,
    },
    pre_final_story = {
        d880 = 0x19, sequence = 0x04, art = 0x04,
    },
    pre_final_sara = {
        d880 = 0x19, sequence = 0x04, art = 0x07,
    },
    post_final_story = {
        d880 = 0x1A, sequence = 0x05, art = 0x05,
    },
    post_final_lisa = {
        d880 = 0x1A, sequence = 0x05, art = 0x06,
    },
    post_final_sara = {
        d880 = 0x1A, sequence = 0x05, art = 0x07,
    },
}

-- The direct-written credits/END/epilogue retain stale portrait bytes, so
-- they use the independent phase guards proved by the full ending inventory.
-- Their whole 20x18 viewport is previewed on a dedicated BG palette because
-- these are text/graphic pages without the story dialogue separator.
local ENDING_TAIL_SCENES = {
    ending_credits = {
        d880 = 0x16, d889 = 0x01, dce2 = 0x00, fff9 = 0x00,
        palette = 0x01,
    },
    ending_end = {
        d880 = 0x16, d889 = 0x01, dce2 = 0x00, fff9 = 0x01,
        palette = 0x02,
    },
    ending_epilogue = {
        d880 = 0x00, d889 = 0x0C, dce2 = 0x01, fff9 = 0x01,
        palette = 0x03,
    },
}

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
        local r5 = math.floor((r * 31 + 127) / 255)
        local g5 = math.floor((g * 31 + 127) / 255)
        local b5 = math.floor((b * 31 + 127) / 255)
        return (b5 << 10) | (g5 << 5) | r5
    elseif #s == 4 then
        return tonumber(s, 16) or 0
    end
    return 0
end

-- Parsed file contains:
--   writes: list of explicitly edited palette overrides, applied every frame
--           (BOSS/POWER/JET writes are guarded by live state flags)
--   scene:  optional whitelisted mGBA save-state key, consumed once
local function load_palettes(path)
    local fh = io.open(path, "r")
    if not fh then return nil end
    local txt = fh:read("*all")
    fh:close()
    local result = {writes = {}, scene = nil}
    for line in txt:gmatch("[^\r\n]+") do
        if line:sub(1,1) == "#" then
            -- comment, skip
        elseif line:match("^SCENE:") then
            local scene = line:match("^SCENE:([a-z0-9_]+)$")
            if scene and SCENE_FILES[scene] then result.scene = scene end
        else
            local boss_idx, boss_slot, boss_colors =
                line:match("^BOSS(%d)@(%d):(.+)$")
            local jet_slot, jet_colors = line:match("^JET(%d):(.+)$")
            local power_idx, power_colors = line:match("^POWER(%d):(.+)$")
            local kind, pal_idx, colors = line:match("^(OBJ)(%d):(.+)$")
            if not kind then
                kind, pal_idx, colors = line:match("^(BG)(%d):(.+)$")
            end
            if boss_idx then
                kind, pal_idx, colors = "BOSS", boss_slot, boss_colors
            elseif jet_slot then
                kind, pal_idx, colors = "JET", jet_slot, jet_colors
            elseif power_idx then
                kind, pal_idx, colors = "POWER", 0, power_colors
            end
            if kind and pal_idx then
                local is_obj = kind ~= "BG"
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
                            boss = boss_idx and tonumber(boss_idx) or nil,
                            jet = jet_slot and tonumber(jet_slot) or nil,
                            power = power_idx and tonumber(power_idx) or nil,
                        })
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
        local active = (
            (not w.boss or emu:read8(0xFFBF) == w.boss)
            and (not w.jet or emu:read8(0xFFD0) == 1)
            and (not w.power or emu:read8(0xFFC0) == w.power)
        )
        if active then
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
end

local function read_palette(is_obj, palette)
    local index_reg = is_obj and 0xFF6A or 0xFF68
    local data_reg = is_obj and 0xFF6B or 0xFF69
    local old_index = emu:read8(index_reg)
    local words = {}
    for color = 0, 3 do
        local offset = palette * 8 + color * 2
        emu:write8(index_reg, offset)
        local lo = emu:read8(data_reg)
        emu:write8(index_reg, offset + 1)
        local hi = emu:read8(data_reg)
        words[#words + 1] = string.format("%04X", lo | (hi << 8))
    end
    emu:write8(index_reg, old_index)
    return table.concat(words, ",")
end

local function story_art_guard(scene)
    local spec = STORY_ART_SCENES[scene]
    if not spec then return false, nil end
    local committed = (
        emu:read8(0xD880) == spec.d880
        and emu:read8(0xFFC1) == 0
        and emu:read8(0xDCE8) == spec.sequence
        and emu:read8(0xDCEA) == 0x01
        and emu:read8(0xDCF0) == spec.art
        and ((emu:read8(0xDD07) + 1) & 0xFF) == spec.art
    )
    return committed, spec
end

local function apply_story_art_preview(scene)
    local committed, spec = story_art_guard(scene)
    if not committed then return false, 0, 0 end

    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local top_target, dialogue_zero = 0, 0
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        local palette = (row <= 7) and spec.art or 0
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local address = base + map_y * 32 + map_x
            local attr = emu:read8(address)
            local updated = (attr & 0xF8) | palette
            if updated ~= attr then emu:write8(address, updated) end
            if row <= 7 and (updated & 0x07) == spec.art then
                top_target = top_target + 1
            elseif row >= 8 and (updated & 0x07) == 0 then
                dialogue_zero = dialogue_zero + 1
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return true, top_target, dialogue_zero
end

local function ending_tail_guard(scene)
    local spec = ENDING_TAIL_SCENES[scene]
    if not spec then return false, nil end
    local committed = (
        emu:read8(0xD880) == spec.d880
        and emu:read8(0xFFC1) == 0
        and emu:read8(0xFFE4) == 1
        and emu:read8(0xD889) == spec.d889
        and emu:read8(0xDCE2) == spec.dce2
        and emu:read8(0xFFF9) == spec.fff9
    )
    return committed, spec
end

local function apply_ending_tail_preview(scene)
    local committed, spec = ending_tail_guard(scene)
    if not committed then return false, 0, 0 end

    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local target = 0
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local address = base + map_y * 32 + map_x
            local attr = emu:read8(address)
            local updated = (attr & 0xF8) | spec.palette
            if updated ~= attr then emu:write8(address, updated) end
            if (updated & 0x07) == spec.palette then target = target + 1 end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return true, target, spec.palette
end

-- Cached parsed data — applied EVERY frame so the game's cond_pal
-- can't override our changes when it triggers a palette reload on
-- state change (room transition, miniboss spawn, etc.)
local cached = nil
local loaded_scene = ""
local smoke_done = false
local visual_phase, visual_wait, visual_hash = 0, 0, 0
local audit_index, audit_wait, audit_ok, audit_done = 1, 0, false, false
local special_index, special_wait, special_ok, special_done = 1, 0, false, false
local SPECIAL_AUDIT_SCENES = {
    {name = "gargoyle", scene = "gargoyle"},
    {name = "jet", scene = "jet"},
    {name = "spiral", scene = "spiral"},
    {name = "shield", scene = "shield"},
    -- No natural FFC0=3 state exists in the checked-in library. This
    -- diagnostic-only case forces the guard byte after loading Witch; the
    -- production browser never writes game state.
    {name = "turbo_guard", scene = "witch", force_power = 3},
}
if SCENE_AUDIT_OUT then
    local audit = assert(io.open(SCENE_AUDIT_OUT, "w"))
    audit:write("live palette scene deck audit\n")
    audit:close()
end
if SPECIAL_AUDIT_OUT then
    cached = load_palettes(PAL_FILE)
    local audit = assert(io.open(SPECIAL_AUDIT_OUT, "w"))
    audit:write("live palette guarded-special audit\n")
    audit:close()
end

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

    -- Test-only guarded palette audit. Production sessions never set
    -- LIVE_PALETTE_SPECIAL_AUDIT_OUT and never write FFC0.
    if SPECIAL_AUDIT_OUT then
        if special_index > #SPECIAL_AUDIT_SCENES then
            if not special_done then
                local marker = assert(
                    io.open(SPECIAL_AUDIT_OUT .. ".done", "w")
                )
                marker:write("ok\n")
                marker:close()
                special_done = true
            end
            return
        end
        local spec = SPECIAL_AUDIT_SCENES[special_index]
        if special_wait == 0 then
            special_ok = pcall(function()
                return emu:loadStateFile(SCENE_FILES[spec.scene])
            end)
            emu:setKeys(0)
            special_wait = 30
        else
            special_wait = special_wait - 1
            if spec.force_power then emu:write8(0xFFC0, spec.force_power) end
            if cached then apply_writes(cached.writes) end
            if special_wait == 0 then
                local screenshot =
                    SPECIAL_AUDIT_OUT .. "." .. spec.name .. ".png"
                emu:screenshot(screenshot)
                local audit = assert(io.open(SPECIAL_AUDIT_OUT, "a"))
                audit:write(string.format(
                    "scene=%s ok=%s ffbf=%02X ffc0=%02X ffd0=%02X " ..
                    "obj0=%s obj1=%s obj2=%s obj6=%s obj7=%s\n",
                    spec.name, tostring(special_ok), emu:read8(0xFFBF),
                    emu:read8(0xFFC0), emu:read8(0xFFD0),
                    read_palette(true, 0), read_palette(true, 1),
                    read_palette(true, 2), read_palette(true, 6),
                    read_palette(true, 7)
                ))
                audit:close()
                special_index = special_index + 1
            end
        end
        return
    end

    -- Test-only walk through every curated state. Production sessions never
    -- set LIVE_PALETTE_SCENE_AUDIT_OUT.
    if SCENE_AUDIT_OUT then
        if audit_index > #SCENE_ORDER then
            if not audit_done then
                local marker = assert(io.open(SCENE_AUDIT_OUT .. ".done", "w"))
                marker:write("ok\n")
                marker:close()
                audit_done = true
            end
            return
        end
        local scene = SCENE_ORDER[audit_index]
        if audit_wait == 0 then
            local state_path = SCENE_FILES[scene]
            audit_ok = pcall(function() return emu:loadStateFile(state_path) end)
            emu:setKeys(0)
            audit_wait = 30
        else
            audit_wait = audit_wait - 1
            local story_preview, top_target, dialogue_zero =
                apply_story_art_preview(scene)
            local tail_preview, tail_cells, tail_palette =
                apply_ending_tail_preview(scene)
            if audit_wait == 0 then
                local screenshot = SCENE_AUDIT_OUT .. "." .. scene .. ".png"
                emu:screenshot(screenshot)
                local audit = assert(io.open(SCENE_AUDIT_OUT, "a"))
                audit:write(string.format(
                    "scene=%s ok=%s d880=%02X ffc1=%d ffbf=%02X " ..
                    "ffc0=%02X ffd0=%02X ffba=%02X ffe4=%d " ..
                    "dce8=%02X dcea=%02X " ..
                    "dcf0=%02X dd07=%02X story_preview=%s " ..
                    "story_top=%d story_dialogue=%d d889=%02X " ..
                    "dce2=%02X fff9=%02X tail_preview=%s " ..
                    "tail_cells=%d tail_palette=%d\n",
                    scene, tostring(audit_ok), emu:read8(0xD880),
                    emu:read8(0xFFC1), emu:read8(0xFFBF),
                    emu:read8(0xFFC0), emu:read8(0xFFD0),
                    emu:read8(0xFFBA), emu:read8(0xFFE4),
                    emu:read8(0xDCE8), emu:read8(0xDCEA),
                    emu:read8(0xDCF0), emu:read8(0xDD07),
                    tostring(story_preview), top_target, dialogue_zero,
                    emu:read8(0xD889), emu:read8(0xDCE2),
                    emu:read8(0xFFF9), tostring(tail_preview), tail_cells,
                    tail_palette
                ))
                audit:close()
                audit_index = audit_index + 1
            end
        end
        return
    end

    if f == 30 then log("Lua frame=30, polling " .. PAL_FILE) end

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
                local scene = cached and cached.scene or nil
                log(string.format(
                    "f%d: loaded %d palette writes, scene=%s",
                    f, nw, tostring(scene)
                ))
                if scene then
                    local state_path = SCENE_FILES[scene]
                    local ok, result = pcall(function()
                        return emu:loadStateFile(state_path)
                    end)
                    if ok then loaded_scene = scene end
                    log(string.format(
                        "f%d: loadStateFile scene=%s ok=%s result=%s",
                        f, scene, tostring(ok), tostring(result)
                    ))
                    cached.scene = nil
                end
            end
        end
    end

    -- Only palettes explicitly edited by the browser are cached, so applying
    -- them in every scene is safe: unrelated arena/miniboss CRAM stays intact.
    if cached then apply_writes(cached.writes) end
    if loaded_scene ~= "" then
        apply_story_art_preview(loaded_scene)
        apply_ending_tail_preview(loaded_scene)
    end

    -- Test-only, same-process browser-to-pixels receipt. Python waits for the
    -- baseline marker, changes BG3 through the HTTP editor, and then verifies
    -- that this running emulator renders a materially different frame without
    -- a reset. The production live editor never sets VISUAL_AUDIT_OUT.
    if VISUAL_AUDIT_OUT and loaded_scene == "opening_dragon_eye" then
        if visual_phase == 0 and f >= 180 then
            emu:screenshot(VISUAL_AUDIT_OUT .. ".before.png")
            local ready = assert(io.open(VISUAL_AUDIT_OUT .. ".ready", "w"))
            ready:write(string.format("frame=%d hash=%08X\n", f, last_hash))
            ready:close()
            visual_hash = last_hash
            visual_phase = 1
        elseif visual_phase == 1 and last_hash ~= visual_hash then
            -- Wait one complete browser polling interval after observing the
            -- edit so both CRAM and the story-art attributes have rendered.
            visual_wait = 30
            visual_phase = 2
        elseif visual_phase == 2 then
            visual_wait = visual_wait - 1
            if visual_wait <= 0 then
                emu:screenshot(VISUAL_AUDIT_OUT .. ".after.png")
                local report = assert(io.open(VISUAL_AUDIT_OUT, "w"))
                report:write(string.format(
                    "frame=%d scene=%s d880=%02X ffc1=%d bg3=%s\n",
                    f, loaded_scene, emu:read8(0xD880),
                    emu:read8(0xFFC1), read_palette(false, 3)
                ))
                report:close()
                local done = assert(io.open(VISUAL_AUDIT_OUT .. ".done", "w"))
                done:write("ok\n")
                done:close()
                visual_phase = 3
            end
        end
    end

    -- Optional automated bridge gate. The production session never sets this.
    if SMOKE_OUT and not smoke_done and loaded_scene ~= "" and f >= 180 then
        -- Capture before publishing the marker. mGBA may finish encoding the
        -- PNG after this callback returns, so keep the emulator alive until
        -- the Python gate observes both files and terminates it.
        emu:screenshot(SMOKE_OUT .. ".png")
        local out = assert(io.open(SMOKE_OUT, "w"))
        out:write(string.format(
            "frame=%d scene=%s d880=%02X ffc1=%d ffbf=%02X " ..
            "bg3=%s obj4=%s obj6=%s\n",
            f, loaded_scene, emu:read8(0xD880), emu:read8(0xFFC1),
            emu:read8(0xFFBF), read_palette(false, 3),
            read_palette(true, 4), read_palette(true, 6)
        ))
        out:close()
        smoke_done = true
    end
end)
