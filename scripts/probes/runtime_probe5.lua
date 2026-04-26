-- Round 5: Boss 16 damage test — directly write DCBB to simulate damage
-- and see if the game progresses through phases / triggers death cinematic
local OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/tmp/probes/"
local frame = 0
local probe_state = "WAIT"
local phase = 0
local phase_frame = 0
local phase_init = false
local results = {}

local function r8(a) return emu:read8(a) end
local function w8(a, v) emu:write8(a, v) end
local function rom_w8(a, v) emu.memory.cart0:write8(a, v) end

local function logf(name, txt)
    local f = io.open(OUT_DIR .. name, "a")
    if f then f:write(txt .. "\n"); f:close() end
end

local function advance_phase(name)
    logf("trace5.txt", string.format("frame=%d advancing past phase %d (%s)", frame, phase, name))
    phase = phase + 1
    phase_frame = 0
    phase_init = false
end

callbacks:add("frame", function()
    frame = frame + 1
    if probe_state == "WAIT" then
        if r8(0xD880) == 0x02 or frame > 200 then
            probe_state = "RUN"
            logf("trace5.txt", string.format("frame=%d starting (D880=0x%02X)", frame, r8(0xD880)))
        end
        return
    end
    phase_frame = phase_frame + 1

    -- =================================================================
    -- PHASE 0: Spawn KNOWN-GOOD boss (gargoyle, DC04=0x30 unmodified)
    -- Then simulate damage by writing DCBB directly. Watch:
    --   - DCBB phase thresholds (0xC0, 0x80, 0x40)
    --   - Phase resets at 0xC0/0x80 boundaries
    --   - Death trigger at 0x00 → D880=0x17 (cinematic)
    -- =================================================================
    if phase == 0 then
        if not phase_init then
            results.gargoyle_damage = {events={}, transitions={}}
            -- DON'T patch ROM. Use entry 2 which is gargoyle (DC04=0x30) by default
            w8(0xFFBF, 0)
            w8(0xDCB8, 0)  -- reset section
            w8(0xDCBA, 0x01)
            w8(0xFFD6, 0x1E)
            w8(0xDCBB, 0xFF)
            for _, a in ipairs({0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}) do w8(a, 0x00) end
            phase_init = true
            results.gargoyle_damage.last_DCBB = 0xFF
            results.gargoyle_damage.last_D880 = r8(0xD880)
            results.gargoyle_damage.last_FFBF = 0
        end
        -- Force section advance until gargoyle spawns
        w8(0xDCBA, 0x01)
        w8(0xFFD6, 0x1E)
        -- Once spawned (FFBF != 0), start damaging
        local cur_FFBF = r8(0xFFBF)
        local cur_DCBB = r8(0xDCBB)
        local cur_D880 = r8(0xD880)
        if cur_FFBF ~= 0 and not results.gargoyle_damage.spawn_frame then
            results.gargoyle_damage.spawn_frame = phase_frame
            results.gargoyle_damage.spawn_FFBF = cur_FFBF
            results.gargoyle_damage.spawn_DC04 = r8(0xDC04)
            logf("trace5.txt", string.format("  GARGOYLE spawned at f=%d FFBF=0x%02X DC04=0x%02X", phase_frame, cur_FFBF, r8(0xDC04)))
        end
        -- After spawn, damage every 5 frames
        if cur_FFBF ~= 0 and phase_frame % 5 == 0 and cur_DCBB > 0 then
            local new_DCBB = math.max(0, cur_DCBB - 0x10)
            w8(0xDCBB, new_DCBB)
            table.insert(results.gargoyle_damage.events, {f=phase_frame, before=cur_DCBB, after=new_DCBB, FFBF=cur_FFBF, D880=cur_D880})
        end
        -- Detect ANY change to DCBB (game's own writes!)
        if cur_DCBB ~= results.gargoyle_damage.last_DCBB or cur_D880 ~= results.gargoyle_damage.last_D880 or cur_FFBF ~= results.gargoyle_damage.last_FFBF then
            table.insert(results.gargoyle_damage.transitions, {f=phase_frame, DCBB=cur_DCBB, D880=cur_D880, FFBF=cur_FFBF, prev_DCBB=results.gargoyle_damage.last_DCBB})
            results.gargoyle_damage.last_DCBB = cur_DCBB
            results.gargoyle_damage.last_D880 = cur_D880
            results.gargoyle_damage.last_FFBF = cur_FFBF
        end
        if phase_frame >= 300 then advance_phase("gargoyle_damage") end
        return
    end

    -- =================================================================
    -- PHASE 1: NOW BOSS 16 — same protocol, see if it dies
    -- =================================================================
    if phase == 1 then
        if not phase_init then
            results.boss16_damage = {events={}, transitions={}}
            -- Patch entry 2 to boss 16 spawn
            rom_w8(0x3402F, 0x7B)
            -- Reset state
            w8(0xFFBF, 0)
            w8(0xDCB8, 0)
            w8(0xDCBA, 0x01)
            w8(0xFFD6, 0x1E)
            w8(0xDCBB, 0xFF)
            for _, a in ipairs({0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}) do w8(a, 0x00) end
            phase_init = true
            results.boss16_damage.last_DCBB = 0xFF
            results.boss16_damage.last_D880 = r8(0xD880)
            results.boss16_damage.last_FFBF = 0
            logf("trace5.txt", "p1 init: boss 16 patch")
        end
        w8(0xDCBA, 0x01)
        w8(0xFFD6, 0x1E)
        local cur_FFBF = r8(0xFFBF)
        local cur_DCBB = r8(0xDCBB)
        local cur_D880 = r8(0xD880)
        if cur_FFBF ~= 0 and not results.boss16_damage.spawn_frame then
            results.boss16_damage.spawn_frame = phase_frame
            results.boss16_damage.spawn_FFBF = cur_FFBF
            results.boss16_damage.spawn_DC04 = r8(0xDC04)
            logf("trace5.txt", string.format("  BOSS 16 spawned at f=%d FFBF=0x%02X", phase_frame, cur_FFBF))
        end
        if cur_FFBF ~= 0 and phase_frame % 5 == 0 and cur_DCBB > 0 then
            local new_DCBB = math.max(0, cur_DCBB - 0x10)
            w8(0xDCBB, new_DCBB)
            table.insert(results.boss16_damage.events, {f=phase_frame, before=cur_DCBB, after=new_DCBB, FFBF=cur_FFBF, D880=cur_D880})
        end
        if cur_DCBB ~= results.boss16_damage.last_DCBB or cur_D880 ~= results.boss16_damage.last_D880 or cur_FFBF ~= results.boss16_damage.last_FFBF then
            table.insert(results.boss16_damage.transitions, {f=phase_frame, DCBB=cur_DCBB, D880=cur_D880, FFBF=cur_FFBF, prev_DCBB=results.boss16_damage.last_DCBB})
            results.boss16_damage.last_DCBB = cur_DCBB
            results.boss16_damage.last_D880 = cur_D880
            results.boss16_damage.last_FFBF = cur_FFBF
        end
        if phase_frame >= 300 then advance_phase("boss16_damage") end
        return
    end

    -- =================================================================
    -- PHASE 2: emit JSON
    -- =================================================================
    if phase == 2 then
        local function emit(o, ind)
            local pad = string.rep("  ", ind)
            local r = ""
            if type(o) == "table" then
                local is_arr = (#o > 0)
                if is_arr then
                    r = "[\n"
                    for i, v in ipairs(o) do
                        r = r .. pad .. "  " .. emit(v, ind+1) .. (i<#o and "," or "") .. "\n"
                    end
                    r = r .. pad .. "]"
                else
                    r = "{\n"
                    local ks={}
                    for k in pairs(o) do
                        if type(k) ~= "string" or not k:match("^last_") then
                            table.insert(ks, k)
                        end
                    end
                    table.sort(ks, function(a,b) return tostring(a)<tostring(b) end)
                    for i, k in ipairs(ks) do
                        r = r .. pad .. "  \"" .. tostring(k) .. "\": " .. emit(o[k], ind+1) .. (i<#ks and "," or "") .. "\n"
                    end
                    r = r .. pad .. "}"
                end
            elseif type(o) == "number" then r = tostring(o)
            elseif type(o) == "string" then r = "\"" .. o:gsub('"','\\"') .. "\""
            elseif type(o) == "boolean" then r = (o and "true" or "false")
            else r = "null" end
            return r
        end
        local f = io.open(OUT_DIR .. "results5.json", "w")
        if f then f:write(emit(results, 0)); f:write("\n"); f:close() end
        logf("trace5.txt", string.format("frame=%d ALL DONE", frame))
        os.exit(0)
    end
end)

logf("trace5.txt", "probe5 started")
