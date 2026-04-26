-- Round 2 runtime probes — clean rewrite
local OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/tmp/probes/"
local frame = 0

local probe_state = "WAIT"
local phase = 0
local phase_frame = 0  -- frames spent in current phase
local phase_init = false
local results = {}

local function r8(a) return emu:read8(a) end
local function w8(a, v) emu:write8(a, v) end

local function logf(name, txt)
    local f = io.open(OUT_DIR .. name, "a")
    if f then f:write(txt .. "\n"); f:close() end
end

local function hram_snap()
    local s = {}
    for a = 0xFF80, 0xFFFE do table.insert(s, r8(a)) end
    return s
end

local function diff_hram(before, after)
    local diffs = {}
    for i = 1, #before do
        if before[i] ~= after[i] then
            local addr = 0xFF80 + i - 1
            table.insert(diffs, {addr=string.format("FF%02X", addr-0xFF00), before=before[i], after=after[i]})
        end
    end
    return diffs
end

local function advance_phase(name)
    logf("trace2.txt", string.format("frame=%d advancing past phase %d (%s)", frame, phase, name))
    phase = phase + 1
    phase_frame = 0
    phase_init = false
end

callbacks:add("frame", function()
    frame = frame + 1
    if probe_state == "WAIT" then
        if r8(0xD880) == 0x02 or frame > 200 then
            probe_state = "RUN"
            logf("trace2.txt", string.format("frame=%d starting probes (D880=0x%02X)", frame, r8(0xD880)))
        end
        return
    end
    phase_frame = phase_frame + 1

    if phase == 0 then
        -- Probe 1: HRAM diff before/after FFC0=2
        if not phase_init then
            results.hram_powerup = {pre = hram_snap(), write_frame = frame}
            w8(0xFFC0, 2)
            phase_init = true
            logf("trace2.txt", "p0 init: snapped + wrote FFC0=2")
        end
        if phase_frame >= 30 then
            local post = hram_snap()
            results.hram_powerup.post = post
            results.hram_powerup.diffs = diff_hram(results.hram_powerup.pre, post)
            advance_phase("hram_powerup")
        end
        return
    end

    if phase == 1 then
        -- Probe 2: write FFBF=1 (gargoyle), log D880/DDA8/etc 60 frames
        if not phase_init then
            results.miniboss_force = {log={}}
            w8(0xFFBF, 1)
            phase_init = true
            logf("trace2.txt", "p1 init: wrote FFBF=1")
        end
        table.insert(results.miniboss_force.log, {
            f=phase_frame, D880=r8(0xD880), DDA8=r8(0xDDA8), FFBF=r8(0xFFBF),
            DCBB=r8(0xDCBB), DCB8=r8(0xDCB8), DC04=r8(0xDC04)
        })
        if phase_frame >= 60 then advance_phase("miniboss_force") end
        return
    end

    if phase == 2 then
        -- Probe 3: spawn DC04=0x7B via ROM patch + force section
        if not phase_init then
            results.boss16 = {snapshots={}}
            -- Patch ROM bank 13 entry 2 to spawn boss 16
            emu.memory.cart0:write8(0x3402F, 0x7B)
            w8(0xFFBF, 0)
            w8(0xDCB8, 2)
            w8(0xDCBA, 0x01)
            w8(0xFFD6, 0x1E)
            phase_init = true
            logf("trace2.txt", "p2 init: ROM patched, DCB8=2 forced")
        end
        if phase_frame % 5 == 0 then
            local snap = {f=phase_frame, FFBF=r8(0xFFBF), DC04=r8(0xDC04), DCBB=r8(0xDCBB), DCB8=r8(0xDCB8), D880=r8(0xD880)}
            local addrs = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
            for i, a in ipairs(addrs) do
                local b = {}
                for j=0, 7 do table.insert(b, r8(a+j)) end
                snap["slot_"..i] = b
            end
            table.insert(results.boss16.snapshots, snap)
        end
        if phase_frame >= 90 then advance_phase("boss16") end
        return
    end

    if phase == 3 then
        -- Probe 4: directly set FFBF=16 + DC04=0x7B; observe behavior
        if not phase_init then
            results.boss16_direct = {log={}}
            w8(0xFFBF, 16)
            w8(0xDC04, 0x7B)
            phase_init = true
            logf("trace2.txt", "p3 init: FFBF=16 direct")
        end
        table.insert(results.boss16_direct.log, {
            f=phase_frame, FFBF=r8(0xFFBF), DCBB=r8(0xDCBB), D880=r8(0xD880), DCB8=r8(0xDCB8)
        })
        if phase_frame >= 60 then advance_phase("boss16_direct") end
        return
    end

    if phase == 4 then
        -- Probe 5: extended HRAM watch — write powerup, scan ALL HRAM bytes for ANY change over 120 frames
        if not phase_init then
            -- Reset state
            w8(0xFFBF, 0)
            w8(0xDC04, 0x04)
            -- Build a per-byte history
            results.hram_full_watch = {addrs={}, snapshots={}, write_frame=frame}
            for a = 0xFF80, 0xFFFE do table.insert(results.hram_full_watch.addrs, string.format("FF%02X", a-0xFF00)) end
            w8(0xFFC0, 1)  -- spiral powerup
            phase_init = true
            logf("trace2.txt", "p4 init: FFC0=1 (spiral), watching HRAM")
        end
        if phase_frame % 10 == 0 then
            table.insert(results.hram_full_watch.snapshots, {f=phase_frame, hram=hram_snap(), FFC0=r8(0xFFC0)})
        end
        if phase_frame >= 120 then advance_phase("hram_full_watch") end
        return
    end

    if phase == 5 then
        -- Done. Dump JSON.
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
                    for k in pairs(o) do table.insert(ks, k) end
                    table.sort(ks)
                    for i, k in ipairs(ks) do
                        r = r .. pad .. "  \"" .. tostring(k) .. "\": " .. emit(o[k], ind+1) .. (i<#ks and "," or "") .. "\n"
                    end
                    r = r .. pad .. "}"
                end
            elseif type(o) == "number" then r = tostring(o)
            elseif type(o) == "string" then r = "\"" .. o:gsub('"','\\"') .. "\""
            else r = "null" end
            return r
        end
        local f = io.open(OUT_DIR .. "results2.json", "w")
        if f then f:write(emit(results, 0)); f:write("\n"); f:close() end
        logf("trace2.txt", string.format("frame=%d ALL DONE", frame))
        os.exit(0)
    end
end)

logf("trace2.txt", "probe2 v2 started")
