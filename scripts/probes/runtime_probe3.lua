-- Runtime probe round 3: definitive boss-16 + D880 micro-trace + stage boss arena
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
    logf("trace3.txt", string.format("frame=%d advancing past phase %d (%s)", frame, phase, name))
    phase = phase + 1
    phase_frame = 0
    phase_init = false
end

local function dump_slots()
    -- Returns 5 slots × 8 bytes
    local out = {}
    local addrs = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
    for i, a in ipairs(addrs) do
        local b = {}
        for j=0, 7 do table.insert(b, r8(a+j)) end
        out["slot_"..i] = b
    end
    return out
end

callbacks:add("frame", function()
    frame = frame + 1

    if probe_state == "WAIT" then
        if r8(0xD880) == 0x02 or frame > 200 then
            probe_state = "RUN"
            logf("trace3.txt", string.format("frame=%d starting probes (D880=0x%02X)", frame, r8(0xD880)))
        end
        return
    end
    phase_frame = phase_frame + 1

    -- =================================================================
    -- PHASE 0: D880 micro-trace (600 frames)
    -- =================================================================
    if phase == 0 then
        if not phase_init then
            results.d880_trace = {events={}}
            results.d880_last = r8(0xD880)
            phase_init = true
            logf("trace3.txt", "p0 init: D880 micro-trace")
            -- Initial event
            table.insert(results.d880_trace.events, {f=0, D880=results.d880_last, FFBF=r8(0xFFBF), FFBA=r8(0xFFBA)})
        end
        -- Inject events to provoke transitions
        if phase_frame == 60 then w8(0xFFBF, 1); logf("trace3.txt", "  injected FFBF=1") end
        if phase_frame == 180 then w8(0xFFBF, 0); logf("trace3.txt", "  cleared FFBF") end
        if phase_frame == 240 then w8(0xFFBF, 16); logf("trace3.txt", "  injected FFBF=16") end
        if phase_frame == 360 then w8(0xFFBF, 0); w8(0xFFBA, 2); logf("trace3.txt", "  cleared FFBF, set FFBA=2") end
        if phase_frame == 420 then w8(0xD880, 0x18); logf("trace3.txt", "  forced D880=0x18 (boss splash)") end
        if phase_frame == 480 then w8(0xD880, 0x0E); logf("trace3.txt", "  forced D880=0x0E (Crystal Dragon arena)") end
        -- Log every D880 change
        local cur = r8(0xD880)
        if cur ~= results.d880_last then
            table.insert(results.d880_trace.events, {
                f=phase_frame, D880=cur, FFBF=r8(0xFFBF), FFBA=r8(0xFFBA),
                DCBB=r8(0xDCBB), DCB8=r8(0xDCB8), prev=results.d880_last
            })
            results.d880_last = cur
        end
        if phase_frame >= 540 then advance_phase("d880_trace") end
        return
    end

    -- =================================================================
    -- PHASE 1: BOSS 16 DEFINITIVE — patch ALL 6 spawn entries to DC04=0x7B
    -- Then reset DCB8=0 and force section advances through them
    -- =================================================================
    if phase == 1 then
        if not phase_init then
            results.boss16_def = {snapshots={}, events={}}
            -- Patch level 1 spawn table: bank 13 entry header at file 0x34024
            -- Each entry is 5 bytes; DC04 is byte 1 of each entry (offset 1, 6, 11, 16, 21, 26 from header start)
            -- Header: 0x34024 = count byte
            -- Entry 0: 0x34025-0x34029 (DC04 at 0x34026)
            -- Entry 1: 0x3402A-0x3402E (DC04 at 0x3402B)
            -- Entry 2: 0x3402F-0x34033 (DC04 at 0x34030) — wait let me recount
            -- Actually: header byte at 0x34024, then 6 entries × 5 bytes
            -- Entry 0 starts at 0x34025; DC04 = byte 1 of entry = 0x34026
            -- Entry 2 (gargoyle) DC04 at 0x3402F — that's what we know
            -- So entry N: DC04 at 0x34025 + 5*N + 1 = 0x34026 + 5*N
            for n = 0, 5 do
                local addr = 0x34026 + 5*n
                local was = emu.memory.cart0:read8(addr)
                rom_w8(addr, 0x7B)
                logf("trace3.txt", string.format("  patched entry %d at 0x%X: 0x%02X -> 0x7B", n, addr, was))
            end
            -- Force fresh section
            w8(0xFFBF, 0)
            w8(0xDCB8, 0)
            w8(0xDCBA, 0x01)
            w8(0xFFD6, 0x1E)
            w8(0xDCBB, 0xFF)
            phase_init = true
        end
        -- Aggressive forcing every frame
        w8(0xDCBA, 0x01)
        w8(0xFFD6, 0x1E)
        if phase_frame % 10 == 0 then
            local snap = {
                f=phase_frame, FFBF=r8(0xFFBF), DC04=r8(0xDC04), DCBB=r8(0xDCBB),
                DCB8=r8(0xDCB8), D880=r8(0xD880), DD09=r8(0xDD09)
            }
            local slots = dump_slots()
            for k,v in pairs(slots) do snap[k] = v end
            table.insert(results.boss16_def.snapshots, snap)
        end
        -- Detect boss spawn
        if r8(0xFFBF) ~= 0 and not results.boss16_def.spawned then
            results.boss16_def.spawned = {f=phase_frame, FFBF=r8(0xFFBF), DC04=r8(0xDC04), DCBB=r8(0xDCBB)}
            logf("trace3.txt", string.format("  BOSS 16 SPAWNED at f=%d FFBF=0x%02X DC04=0x%02X", phase_frame, r8(0xFFBF), r8(0xDC04)))
        end
        if phase_frame >= 180 then advance_phase("boss16_def") end
        return
    end

    -- =================================================================
    -- PHASE 2: Once boss 16 spawned, attempt damage via DCBB direct write
    -- =================================================================
    if phase == 2 then
        if not phase_init then
            results.boss16_damage = {events={}}
            -- Force boss 16 again if needed
            if r8(0xFFBF) == 0 then
                w8(0xFFBF, 16)
                w8(0xDC04, 0x7B)
            end
            -- Reset DCBB to 0xFF
            w8(0xDCBB, 0xFF)
            phase_init = true
            logf("trace3.txt", "p2 init: damage probe")
        end
        -- Every 10 frames, decrement DCBB by 0x10 to simulate damage
        if phase_frame % 10 == 5 then
            local before = r8(0xDCBB)
            w8(0xDCBB, math.max(0, before - 0x10))
            local after = r8(0xDCBB)
            table.insert(results.boss16_damage.events, {
                f=phase_frame, write=string.format("0x%02X -> 0x%02X", before, after),
                FFBF=r8(0xFFBF), D880=r8(0xD880), DC04=r8(0xDC04)
            })
        end
        if phase_frame >= 100 then advance_phase("boss16_damage") end
        return
    end

    -- =================================================================
    -- PHASE 3: Stage boss arena trigger — write D880=0x0C..0x14 with FFBA matching
    -- =================================================================
    if phase == 3 then
        if not phase_init then
            results.stage_boss = {tests={}}
            -- Reset state
            w8(0xFFBF, 0)
            w8(0xDC04, 0x04)
            w8(0xDCB8, 0)
            phase_init = true
            results.stage_boss.test_idx = 0
            logf("trace3.txt", "p3 init: stage boss arena tests")
        end
        -- Each test: 30 frames apart, set FFBA + D880 and observe
        local test_frame = phase_frame % 30
        local test_n = math.floor(phase_frame / 30)
        if test_frame == 0 and test_n < 9 then
            local ffba = test_n
            local d880 = 0x0C + test_n
            w8(0xFFBA, ffba)
            w8(0xD880, d880)
            results.stage_boss._pending = {test_n=test_n, ffba=ffba, d880_set=d880, set_frame=phase_frame}
        end
        if test_frame == 25 and results.stage_boss._pending then
            local p = results.stage_boss._pending
            p.D880_after = r8(0xD880)
            p.FFBA_after = r8(0xFFBA)
            p.D881 = r8(0xD881)
            -- Sample some VRAM to detect arena draw — read SCY/SCX, OAM[0]
            p.SCY = r8(0xFF42)
            p.SCX = r8(0xFF43)
            p.OAM0 = {r8(0xFE00), r8(0xFE01), r8(0xFE02), r8(0xFE03)}
            table.insert(results.stage_boss.tests, p)
            results.stage_boss._pending = nil
        end
        if phase_frame >= 270 then advance_phase("stage_boss") end
        return
    end

    -- =================================================================
    -- PHASE 4: Entity slot decoder — write known patterns to slot 1, watch what bytes change
    -- =================================================================
    if phase == 4 then
        if not phase_init then
            results.slot_decoder = {trials={}}
            -- Reset boss state
            w8(0xFFBF, 0)
            w8(0xD880, 0x02)
            phase_init = true
            logf("trace3.txt", "p4 init: entity slot decoder")
        end
        -- Trial: write specific value at slot 1 byte N, see how game responds
        if phase_frame == 1 then
            -- Snapshot baseline
            results.slot_decoder.baseline = {}
            for i = 0, 15 do results.slot_decoder.baseline[i+1] = r8(0xDC85 + i) end
        end
        -- At frames 30, 60, 90... try modifying different slot bytes
        if phase_frame == 30 then
            w8(0xDC85, 0x00)  -- byte 0 = active flag?
            results.slot_decoder.trial1_pre = r8(0xDC85)
        end
        if phase_frame == 31 then
            results.slot_decoder.trial1_post = r8(0xDC85)
        end
        if phase_frame == 60 then
            w8(0xDC8D + 1, 0x99)  -- slot 2 byte 1 = type?
            results.slot_decoder.trial2_pre = r8(0xDC8D + 1)
        end
        if phase_frame == 61 then
            results.slot_decoder.trial2_post = r8(0xDC8D + 1)
        end
        if phase_frame == 90 then
            -- Sample OAM at frame 90 to see sprite layout
            local oam = {}
            for i = 0, 39 do
                table.insert(oam, {r8(0xFE00+i*4), r8(0xFE01+i*4), r8(0xFE02+i*4), r8(0xFE03+i*4)})
            end
            results.slot_decoder.oam_snapshot = oam
        end
        if phase_frame >= 120 then advance_phase("slot_decoder") end
        return
    end

    -- =================================================================
    -- PHASE 5: Done. Emit JSON.
    -- =================================================================
    if phase == 5 then
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
        local f = io.open(OUT_DIR .. "results3.json", "w")
        if f then f:write(emit(results, 0)); f:write("\n"); f:close() end
        logf("trace3.txt", string.format("frame=%d ALL DONE", frame))
        os.exit(0)
    end
end)

logf("trace3.txt", "probe3 started")
