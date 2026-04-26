-- Round 8: Patch boss 16 entry zero bytes to non-zero, see if collision works
-- (We can't actually trigger collision without input, but we can verify the
--  entity slot byte 0 (active flag) populates differently)
local OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/tmp/probes/"
local frame = 0
local probe_state = "WAIT"
local probe_frame = 0
local results = {snapshots={}, transitions={}}

local function r8(a) return emu:read8(a) end
local function w8(a, v) emu:write8(a, v) end
local function rom_w8(a, v) emu.memory.cart0:write8(a, v) end

local function logf(name, txt)
    local f = io.open(OUT_DIR .. name, "a")
    if f then f:write(txt .. "\n"); f:close() end
end

-- Patch ROM: spawn boss 16 + fix its AI entry
rom_w8(0x3402F, 0x7B)
-- Patch boss 16 entry (0x2D7F) zero bytes to copy boss 15's pattern
-- Boss 15: 14 02 03 14 03 01 14 04 02 14 04 01 14 04 02 14
-- Boss 16: 04 00 03 03 00 05 01 00 0A 02 00 08 04 00 03 03
-- Just fill the 0 bytes at offsets 1,4,7,10,13 with 0x04 (mid value)
for _, off in ipairs({1, 4, 7, 10, 13}) do
    rom_w8(0x2D7F + off, 0x04)
    logf("trace8.txt", string.format("patched 0x2D7F+%d (offset %d) = 0x04", off, off))
end

local last_DCBB = 0xFF
local last_D880 = 0
local last_FFBF = 0
local last_slot1_byte0 = 0

callbacks:add("frame", function()
    frame = frame + 1
    if probe_state == "WAIT" then
        if r8(0xD880) == 0x02 or frame > 200 then
            probe_state = "RUN"
            w8(0xFFBF, 0)
            w8(0xDCB8, 0)
            w8(0xDCBA, 0x01)
            w8(0xFFD6, 0x1E)
            w8(0xDCBB, 0xFF)
            for _, a in ipairs({0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}) do w8(a, 0x00) end
            logf("trace8.txt", string.format("frame=%d starting", frame))
        end
        return
    end
    probe_frame = probe_frame + 1

    w8(0xDCBA, 0x01)
    w8(0xFFD6, 0x1E)

    -- Snapshot every 30 frames
    if probe_frame % 30 == 0 then
        local snap = {f=probe_frame, FFBF=r8(0xFFBF), DC04=r8(0xDC04), DCBB=r8(0xDCBB), D880=r8(0xD880), DCB8=r8(0xDCB8)}
        local addrs = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
        for i, a in ipairs(addrs) do
            local b = {}
            for j=0, 7 do table.insert(b, r8(a+j)) end
            snap["slot_"..i] = b
        end
        table.insert(results.snapshots, snap)
    end

    -- Detect spawn
    local cur_FFBF = r8(0xFFBF)
    if cur_FFBF ~= 0 and not results.spawn_frame then
        results.spawn_frame = probe_frame
        results.spawn_FFBF = cur_FFBF
        results.spawn_DC04 = r8(0xDC04)
        logf("trace8.txt", string.format("  SPAWNED at f=%d FFBF=0x%02X", probe_frame, cur_FFBF))
    end

    -- Detect when slot 1 byte 0 changes from inactive (0x00) to active
    local cur_slot1_b0 = r8(0xDC85)
    if cur_slot1_b0 ~= last_slot1_byte0 then
        table.insert(results.transitions, {f=probe_frame, slot1_b0=cur_slot1_b0, FFBF=cur_FFBF, DCBB=r8(0xDCBB), D880=r8(0xD880)})
        last_slot1_byte0 = cur_slot1_b0
    end

    if probe_frame >= 300 then
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
        local f = io.open(OUT_DIR .. "results8.json", "w")
        if f then f:write(emit(results, 0)); f:write("\n"); f:close() end
        logf("trace8.txt", "ALL DONE")
        os.exit(0)
    end
end)

logf("trace8.txt", "probe8 started")
