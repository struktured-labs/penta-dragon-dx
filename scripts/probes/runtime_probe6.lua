-- Round 6: Boss 16 isolated damage test — does it die when DCBB hits 0?
local OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/tmp/probes/"
local frame = 0
local probe_state = "WAIT"
local phase_init = false
local results = {events={}, transitions={}}

local function r8(a) return emu:read8(a) end
local function w8(a, v) emu:write8(a, v) end
local function rom_w8(a, v) emu.memory.cart0:write8(a, v) end

local function logf(name, txt)
    local f = io.open(OUT_DIR .. name, "a")
    if f then f:write(txt .. "\n"); f:close() end
end

-- Patch entry 2 to boss 16 BEFORE game boots
rom_w8(0x3402F, 0x7B)
logf("trace6.txt", "ROM patched at 0x3402F: 0x30 -> 0x7B (boss 16)")

local last_DCBB = 0xFF
local last_D880 = 0
local last_FFBF = 0
local probe_frame = 0

callbacks:add("frame", function()
    frame = frame + 1
    if probe_state == "WAIT" then
        if r8(0xD880) == 0x02 or frame > 200 then
            probe_state = "RUN"
            -- Force fresh section + boss 16 spawn
            w8(0xFFBF, 0)
            w8(0xDCB8, 0)
            w8(0xDCBA, 0x01)
            w8(0xFFD6, 0x1E)
            w8(0xDCBB, 0xFF)
            for _, a in ipairs({0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}) do w8(a, 0x00) end
            logf("trace6.txt", string.format("frame=%d starting", frame))
        end
        return
    end
    probe_frame = probe_frame + 1

    -- Forcing
    w8(0xDCBA, 0x01)
    w8(0xFFD6, 0x1E)

    local cur_DCBB = r8(0xDCBB)
    local cur_D880 = r8(0xD880)
    local cur_FFBF = r8(0xFFBF)

    -- Detect spawn
    if cur_FFBF ~= 0 and not results.spawn_frame then
        results.spawn_frame = probe_frame
        results.spawn_FFBF = cur_FFBF
        results.spawn_DC04 = r8(0xDC04)
        logf("trace6.txt", string.format("  SPAWNED at f=%d FFBF=0x%02X DC04=0x%02X", probe_frame, cur_FFBF, r8(0xDC04)))
    end

    -- Damage every 5 frames after spawn
    if cur_FFBF ~= 0 and probe_frame % 5 == 0 and cur_DCBB > 0 then
        local new_DCBB = math.max(0, cur_DCBB - 0x10)
        w8(0xDCBB, new_DCBB)
        table.insert(results.events, {f=probe_frame, before=cur_DCBB, after=new_DCBB, FFBF=cur_FFBF, D880=cur_D880})
    end

    -- Detect transitions
    if cur_DCBB ~= last_DCBB or cur_D880 ~= last_D880 or cur_FFBF ~= last_FFBF then
        table.insert(results.transitions, {f=probe_frame, DCBB=cur_DCBB, D880=cur_D880, FFBF=cur_FFBF, prev_DCBB=last_DCBB, prev_D880=last_D880, prev_FFBF=last_FFBF})
        last_DCBB = cur_DCBB
        last_D880 = cur_D880
        last_FFBF = cur_FFBF
    end

    -- Run for 600 probe frames
    if probe_frame >= 600 then
        local function emit(o, ind)
            local pad = string.rep("  ", ind)
            local r = ""
            if type(o) == "table" then
                local is_arr = (#o > 0)
                if is_arr then
                    r = "[\n"
                    for i, v in ipairs(o) do r = r .. pad .. "  " .. emit(v, ind+1) .. (i<#o and "," or "") .. "\n" end
                    r = r .. pad .. "]"
                else
                    r = "{\n"
                    local ks={}
                    for k in pairs(o) do table.insert(ks, k) end
                    table.sort(ks, function(a,b) return tostring(a)<tostring(b) end)
                    for i, k in ipairs(ks) do r = r .. pad .. "  \"" .. tostring(k) .. "\": " .. emit(o[k], ind+1) .. (i<#ks and "," or "") .. "\n" end
                    r = r .. pad .. "}"
                end
            elseif type(o) == "number" then r = tostring(o)
            elseif type(o) == "string" then r = "\"" .. o:gsub('"','\\"') .. "\""
            else r = "null" end
            return r
        end
        local f = io.open(OUT_DIR .. "results6.json", "w")
        if f then f:write(emit(results, 0)); f:write("\n"); f:close() end
        logf("trace6.txt", string.format("frame=%d ALL DONE", frame))
        os.exit(0)
    end
end)

logf("trace6.txt", "probe6 started")
