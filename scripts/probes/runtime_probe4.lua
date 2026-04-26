-- Round 4: corrected boss-16 spawn + DDA8 watch during state 0x0A + D880 reset detector
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
    logf("trace4.txt", string.format("frame=%d advancing past phase %d (%s)", frame, phase, name))
    phase = phase + 1
    phase_frame = 0
    phase_init = false
end

callbacks:add("frame", function()
    frame = frame + 1
    if probe_state == "WAIT" then
        if r8(0xD880) == 0x02 or frame > 200 then
            probe_state = "RUN"
            logf("trace4.txt", string.format("frame=%d starting (D880=0x%02X)", frame, r8(0xD880)))
        end
        return
    end
    phase_frame = phase_frame + 1

    -- =================================================================
    -- PHASE 0: Boss 16 spawn — CORRECTED addresses
    -- Entry N DC04 at 0x34025 + 5*N (NOT +1)
    -- Entry 0: 0x34025
    -- Entry 1: 0x3402A
    -- Entry 2: 0x3402F (gargoyle, was 0x30)
    -- Entry 3: 0x34034
    -- Entry 4: 0x34039
    -- Entry 5: 0x3403E (spider, was 0x35)
    -- =================================================================
    if phase == 0 then
        if not phase_init then
            results.boss16_v2 = {snapshots={}, baseline={}, patches={}}
            -- Read baseline first
            for n = 0, 5 do
                local addr = 0x34025 + 5*n
                results.boss16_v2.baseline["entry_"..n] = string.format("0x%X = 0x%02X", addr, emu.memory.cart0:read8(addr))
            end
            -- Patch all 6 entries to 0x7B
            for n = 0, 5 do
                local addr = 0x34025 + 5*n
                local was = emu.memory.cart0:read8(addr)
                rom_w8(addr, 0x7B)
                table.insert(results.boss16_v2.patches, {entry=n, addr=string.format("0x%X", addr), was=was, now=0x7B})
                logf("trace4.txt", string.format("  patched entry %d at 0x%X: 0x%02X -> 0x7B", n, addr, was))
            end
            -- Force fresh section cycle
            w8(0xFFBF, 0)
            w8(0xDCB8, 0)
            w8(0xDCBA, 0x01)
            w8(0xFFD6, 0x1E)
            w8(0xDCBB, 0xFF)
            -- Zero entity slots to force clearance
            for _, a in ipairs({0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}) do w8(a, 0x00) end
            phase_init = true
        end
        -- Aggressive forcing every frame
        w8(0xDCBA, 0x01)
        w8(0xFFD6, 0x1E)
        if phase_frame % 10 == 0 then
            local snap = {f=phase_frame, FFBF=r8(0xFFBF), DC04=r8(0xDC04), DCBB=r8(0xDCBB),
                          DCB8=r8(0xDCB8), D880=r8(0xD880), DDA8=r8(0xDDA8)}
            local addrs = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
            for i, a in ipairs(addrs) do
                local b = {}
                for j=0, 7 do table.insert(b, r8(a+j)) end
                snap["slot_"..i] = b
            end
            table.insert(results.boss16_v2.snapshots, snap)
        end
        if r8(0xFFBF) ~= 0 and not results.boss16_v2.spawned_at then
            results.boss16_v2.spawned_at = {f=phase_frame, FFBF=r8(0xFFBF), DC04=r8(0xDC04), DCBB=r8(0xDCBB)}
            logf("trace4.txt", string.format("  SPAWNED f=%d FFBF=0x%02X DC04=0x%02X", phase_frame, r8(0xFFBF), r8(0xDC04)))
        end
        if phase_frame >= 240 then advance_phase("boss16_v2") end
        return
    end

    -- =================================================================
    -- PHASE 1: DDA8 + D880 watch during forced miniboss state
    -- =================================================================
    if phase == 1 then
        if not phase_init then
            results.dda8_combat = {events={}, log_freq={}}
            -- Restore normal spawn table
            local restore = {0x19, 0x05, 0x30, 0x19, 0x05, 0x35}  -- best guess at originals
            -- Actually use the captured baseline values
            -- For safety just write FFBF=1 to force state 0x0A
            w8(0xFFBF, 1)
            phase_init = true
            logf("trace4.txt", "p1 init: forcing FFBF=1, watching DDA8")
            results.dda8_last = r8(0xDDA8)
            results.d880_last_p1 = r8(0xD880)
        end
        -- Log every frame (60 frames)
        local d8 = r8(0xDDA8)
        local d880 = r8(0xD880)
        if d8 ~= results.dda8_last or d880 ~= results.d880_last_p1 then
            table.insert(results.dda8_combat.events, {f=phase_frame, DDA8=d8, D880=d880, FFBF=r8(0xFFBF), DCBB=r8(0xDCBB)})
            results.dda8_last = d8
            results.d880_last_p1 = d880
        end
        -- Frequency table
        local key = string.format("D880=0x%02X DDA8=0x%02X", d880, d8)
        results.dda8_combat.log_freq[key] = (results.dda8_combat.log_freq[key] or 0) + 1
        if phase_frame >= 120 then advance_phase("dda8_combat") end
        return
    end

    -- =================================================================
    -- PHASE 2: D880 RESET DETECTOR — write D880=0xAA every frame, check what it gets reset to
    -- =================================================================
    if phase == 2 then
        if not phase_init then
            results.d880_reset = {forces={}}
            w8(0xFFBF, 0)  -- clear miniboss
            phase_init = true
        end
        -- Each frame: write a probe value, record what comes back next frame
        if phase_frame >= 1 and phase_frame <= 30 then
            local probe_val = 0xA0 + (phase_frame % 16)  -- vary the value
            w8(0xD880, probe_val)
            -- Log immediate read (should still be probe_val)
            table.insert(results.d880_reset.forces, {f=phase_frame, wrote=probe_val, immediate=r8(0xD880)})
        end
        -- Check D880 every frame after writing once
        if phase_frame == 31 then
            -- Don't write — just observe
            results.d880_reset.observe_after_30 = {}
        end
        if phase_frame >= 31 and phase_frame <= 60 then
            table.insert(results.d880_reset.observe_after_30, {f=phase_frame, D880=r8(0xD880)})
        end
        if phase_frame >= 60 then advance_phase("d880_reset") end
        return
    end

    -- =================================================================
    -- PHASE 3: Done. Emit JSON.
    -- =================================================================
    if phase == 3 then
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
                        if type(k) ~= "string" or not k:match("^_") then
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
        local f = io.open(OUT_DIR .. "results4.json", "w")
        if f then f:write(emit(results, 0)); f:write("\n"); f:close() end
        logf("trace4.txt", string.format("frame=%d ALL DONE", frame))
        os.exit(0)
    end
end)

logf("trace4.txt", "probe4 started")
