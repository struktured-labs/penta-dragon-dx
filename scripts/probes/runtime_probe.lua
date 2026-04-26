-- Penta Dragon DX runtime probe harness
-- Runs 5 probes in sequence, dumps JSON results
-- Probes: FFAC/FFAD per level, boss-16 entity slots, DDA8 substate counter,
-- powerup expiration timer, sound stream tracking

local OUT_DIR = "/home/struktured/projects/penta-dragon-dx-claude/tmp/probes/"
local frame = 0
local results = {}

-- Game start input sequence (verified working)
-- Frame ranges: DOWN(180-185)→A(193-198)→A(241-246)→A(291-296)→START(341-346)→A(391-396)
local KEY_A     = 0x01
local KEY_B     = 0x02
local KEY_SEL   = 0x04
local KEY_START = 0x08
local KEY_RIGHT = 0x10
local KEY_LEFT  = 0x20
local KEY_UP    = 0x40
local KEY_DOWN  = 0x80

local function get_input(f)
    if f >= 180 and f <= 185 then return KEY_DOWN end
    if f >= 193 and f <= 198 then return KEY_A end
    if f >= 241 and f <= 246 then return KEY_A end
    if f >= 291 and f <= 296 then return KEY_A end
    if f >= 341 and f <= 346 then return KEY_START end
    if f >= 391 and f <= 396 then return KEY_A end
    return 0
end

callbacks:add("keysRead", function()
    emu:setKeys(get_input(frame))
end)

-- Probe state (executed after game reaches gameplay)
local probe_state = "WAIT_BOOT"  -- WAIT_BOOT -> PROBES -> DONE
local probe_phase = 0
local phase_start_frame = 0
local phase_data = {}

-- Helper: write JSON-ish line to log
local function logf(name, txt)
    local f = io.open(OUT_DIR .. name, "a")
    if f then f:write(txt .. "\n"); f:close() end
end

local function dump_json(name, tbl)
    local f = io.open(OUT_DIR .. name, "w")
    if not f then return end
    local function emit(o, indent)
        local pad = string.rep("  ", indent)
        if type(o) == "table" then
            -- detect array vs map
            local is_array = (#o > 0)
            if is_array then
                f:write("[\n")
                for i, v in ipairs(o) do
                    f:write(pad .. "  ")
                    emit(v, indent+1)
                    if i < #o then f:write(",") end
                    f:write("\n")
                end
                f:write(pad .. "]")
            else
                f:write("{\n")
                local keys = {}
                for k in pairs(o) do table.insert(keys, k) end
                table.sort(keys)
                for i, k in ipairs(keys) do
                    f:write(pad .. "  \"" .. tostring(k) .. "\": ")
                    emit(o[k], indent+1)
                    if i < #keys then f:write(",") end
                    f:write("\n")
                end
                f:write(pad .. "}")
            end
        elseif type(o) == "number" then
            f:write(string.format("%d", o))
        elseif type(o) == "string" then
            f:write("\"" .. o:gsub('"', '\\"') .. "\"")
        elseif type(o) == "boolean" then
            f:write(o and "true" or "false")
        else
            f:write("null")
        end
    end
    emit(tbl, 0)
    f:write("\n")
    f:close()
end

-- Read helpers
local function r8(addr) return emu:read8(addr) end
local function w8(addr, v) emu:write8(addr, v) end

-- =====================================================================
-- PROBE PHASES (each runs for N frames, then advances)
-- =====================================================================

local probes_done = {}

local function probe_initial_state()
    -- Phase 0: just sample initial gameplay state
    return {
        D880    = r8(0xD880),
        FFBA    = r8(0xFFBA),
        FFBD    = r8(0xFFBD),
        FFBE    = r8(0xFFBE),
        FFBF    = r8(0xFFBF),
        FFC0    = r8(0xFFC0),
        FFAC    = r8(0xFFAC),
        FFAD    = r8(0xFFAD),
        DCB8    = r8(0xDCB8),
        DCBB    = r8(0xDCBB),
        DCDC    = r8(0xDCDC),
        DCDD    = r8(0xDCDD),
        DDA8    = r8(0xDDA8),
        FFFC    = r8(0xFFFC),
        DC85    = r8(0xDC85),
    }
end

local function run_phase(p)
    if p == 0 then
        -- PROBE A: initial state baseline (1 frame)
        probes_done.initial = probe_initial_state()
        return true
    elseif p == 1 then
        -- PROBE B: cycle FFBA 0-8, read FFAC/FFAD after each
        local rec = {}
        for ba = 0, 8 do
            w8(0xFFBA, ba)
            -- Yield not possible from synchronous loop; just sample immediately
            -- (will be stale unless game reads FFBA on demand)
            table.insert(rec, {
                FFBA = ba,
                FFAC = r8(0xFFAC),
                FFAD = r8(0xFFAD),
                FFBD = r8(0xFFBD),
                D880 = r8(0xD880),
            })
        end
        probes_done.ffba_cycle = rec
        return true
    elseif p == 2 then
        -- PROBE C: dump entity slots DC85, DC8D, DC95, DC9D, DCA5
        -- Plus read 16 bytes from each slot start
        local slots = {}
        local addrs = {0xDC85, 0xDC8D, 0xDC95, 0xDC9D, 0xDCA5}
        for i, a in ipairs(addrs) do
            local bytes = {}
            for j = 0, 15 do table.insert(bytes, r8(a + j)) end
            slots["slot_" .. i] = {addr = a, bytes = bytes}
        end
        probes_done.entity_slots_baseline = {DC04 = r8(0xDC04), slots = slots}
        return true
    elseif p == 3 then
        -- PROBE D: write FFC0=2 (shield), record HRAM 0xFC + FFC0 over 60 frames
        if phase_data.shield_log == nil then
            phase_data.shield_log = {}
            phase_data.shield_start = frame
            w8(0xFFC0, 2)
        end
        local f_off = frame - phase_data.shield_start
        if f_off <= 60 then
            table.insert(phase_data.shield_log, {
                f = f_off, FFC0 = r8(0xFFC0), FFFC = r8(0xFFFC), FFE4 = r8(0xFFE4)
            })
            return false  -- stay in this phase
        else
            probes_done.shield_timer = phase_data.shield_log
            return true
        end
    elseif p == 4 then
        -- PROBE E: write D887=5, log D894-D899 every frame for 60 frames
        if phase_data.sound_log == nil then
            phase_data.sound_log = {}
            phase_data.sound_start = frame
            w8(0xD887, 5)
        end
        local f_off = frame - phase_data.sound_start
        if f_off <= 60 then
            table.insert(phase_data.sound_log, {
                f = f_off,
                D887 = r8(0xD887),
                D894 = r8(0xD894), D895 = r8(0xD895),
                D896 = r8(0xD896), D897 = r8(0xD897),
                D898 = r8(0xD898), D899 = r8(0xD899),
            })
            return false
        else
            probes_done.sound_log = phase_data.sound_log
            return true
        end
    elseif p == 5 then
        -- PROBE F: log DDA8 + D880 every frame for 60 frames (passive observation)
        if phase_data.dda8_log == nil then
            phase_data.dda8_log = {}
            phase_data.dda8_start = frame
        end
        local f_off = frame - phase_data.dda8_start
        if f_off <= 60 then
            table.insert(phase_data.dda8_log, {
                f = f_off, D880 = r8(0xD880), DDA8 = r8(0xDDA8), FFBF = r8(0xFFBF)
            })
            return false
        else
            probes_done.dda8_log = phase_data.dda8_log
            return true
        end
    end
    return true
end

callbacks:add("frame", function()
    frame = frame + 1
    if probe_state == "WAIT_BOOT" then
        -- Wait until D880 reaches 0x02 (gameplay) OR frame > 500
        if r8(0xD880) == 0x02 or frame > 500 then
            probe_state = "PROBES"
            phase_start_frame = frame
            logf("trace.txt", string.format("frame=%d D880=0x%02X entering probes", frame, r8(0xD880)))
        end
    elseif probe_state == "PROBES" then
        local advance = run_phase(probe_phase)
        if advance then
            logf("trace.txt", string.format("frame=%d phase %d done", frame, probe_phase))
            probe_phase = probe_phase + 1
            phase_data = {}
            phase_start_frame = frame
            if probe_phase > 5 then
                probe_state = "DONE"
                dump_json("results.json", probes_done)
                logf("trace.txt", string.format("frame=%d ALL DONE", frame))
                os.exit(0)
            end
        end
    end
end)

logf("trace.txt", "probe started")
