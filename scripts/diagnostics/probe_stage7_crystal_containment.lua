-- Candidate-bound Crystal Dragon containment probe for the Stage-7 HDMA helper.
--
-- This probe is deliberately read-only with respect to emulated game memory:
-- it loads one normalized savestate, supplies neutral input, observes exact
-- control-flow/write sites, and saves the final machine state.  The matching
-- Python verifier owns the emulator lifecycle and validates both states.

local OUT = assert(os.getenv("STAGE7_CRYSTAL_OUT"),
    "STAGE7_CRYSTAL_OUT required")
local STATE_FILE = assert(os.getenv("STAGE7_CRYSTAL_STATE_FILE"),
    "STAGE7_CRYSTAL_STATE_FILE required")
local STATE_OUT = assert(os.getenv("STAGE7_CRYSTAL_STATE_OUT"),
    "STAGE7_CRYSTAL_STATE_OUT required")
local FRAMES = tonumber(os.getenv("STAGE7_CRYSTAL_FRAMES") or "720")
local EXPECTED_SCENE = tonumber(
    os.getenv("STAGE7_CRYSTAL_EXPECTED_SCENE") or "14")
local RESUME_PC = tonumber(
    assert(os.getenv("STAGE7_CRYSTAL_RESUME_PC")), 16)
local RESUME_BANK = tonumber(
    assert(os.getenv("STAGE7_CRYSTAL_RESUME_BANK")))
local ROUTE_DIAGNOSTIC =
    os.getenv("STAGE7_CRYSTAL_ROUTE_DIAGNOSTIC") == "1"
local ROUTE_MODE = os.getenv("STAGE7_CRYSTAL_ROUTE_MODE") or "candidate"
assert(ROUTE_MODE == "candidate" or ROUTE_MODE == "control",
    "STAGE7_CRYSTAL_ROUTE_MODE must be candidate or control")

local PROBE_SCHEMA = "penta-stage7-crystal-containment-probe-v2"
local HELPER_BANK = 22
local HELPER_FIRST, HELPER_LAST = 0x6C80, 0x7232
local frame, state_loaded, armed, finished = 0, false, false, false
local drain_pending, drain_frames, safe_finish = false, 0, 0
local MAX_DRAIN_FRAMES = 120
local scene_samples, scene_unreadable = 0, 0
local wrong_scene = 0
local ff55_nonidle, boundary_bank22 = 0, 0
local ffe4_nonzero = 0
local final_saved = 0
local state_save_pending, state_save_wait_frames = false, 0
local state_save_stable_frames, state_save_last_size = 0, -1
local frame_lines, events = {}, {}
local startup = assert(io.open(OUT .. ".startup", "w"))
startup:write("source-entered\n"); startup:flush()

local hit_names = {
    "resume_state", "main_loop", "copy_decider", "runtime_entry",
    "runtime_native_restore", "runtime_nonstage_gate",
    "runtime_nonstage_ret", "rst_return", "dirty_branch",
    "atomic_entry", "copy_continue", "exact_exit", "outer_primary",
    "outer_secondary", "helper_entry", "phase1_service",
    "phase2_service", "attr_dma", "tile_dma", "fallback_native",
    "caller_reject", "fallback_atomic",
}
local hits = {}
for _, name in ipairs(hit_names) do hits[name] = 0 end
local finish

local function register(name)
    for _, accessor in ipairs({
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }) do
        local ok, value = pcall(accessor)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

local function remember(kind, detail)
    if #events < 64 then
        events[#events + 1] = string.format(
            "%s frame=%d pc=%04X rom=%02X svbk=%d %s",
            kind, frame, register("PC"), emu:read8(0xFF99),
            emu:read8(0xFF70) & 7, detail or "")
    end
end

local function stack_words()
    local sp = register("SP")
    local words = {}
    for offset = 0, 10, 2 do
        local lo = emu:read8((sp + offset) & 0xFFFF)
        local hi = emu:read8((sp + offset + 1) & 0xFFFF)
        words[#words + 1] = string.format("%04X", lo | (hi << 8))
    end
    return sp, table.concat(words, ",")
end

local function add_breakpoint(address, name, segment)
    local callback = function()
        if not armed or finished then return end
        hits[name] = hits[name] + 1
        if hits[name] <= 3 then
            local sp, stack = stack_words()
            startup:write(string.format(
                "hit %s count=%d frame=%d pc=%04X rom=%02X " ..
                "sp=%04X stack=%s\n",
                name, hits[name], frame, register("PC"), emu:read8(0xFF99),
                sp, stack))
            startup:flush()
        end
        if name == "helper_entry" or name == "phase1_service"
            or name == "phase2_service" or name == "attr_dma"
            or name == "tile_dma" or name == "fallback_native"
            or name == "caller_reject" or name == "fallback_atomic" then
            remember("forbidden-hit", name)
        end
        if name == "main_loop" and drain_pending then
            safe_finish = 1
            finish()
        end
    end
    local ok, result
    if segment ~= nil then
        ok, result = pcall(function()
            return emu:setBreakpoint(callback, address, segment)
        end)
    else
        ok, result = pcall(function()
            return emu:setBreakpoint(callback, address)
        end)
    end
    startup:write(string.format(
        "breakpoint %s %02X:%04X result=%s type=%s\n",
        name, segment or 0, address, tostring(result), type(result)))
    startup:flush()
    assert(ok and type(result) == "number" and result > 0,
        string.format("failed breakpoint %s at %02X:%04X",
            name, segment or 0, address))
end

-- The short base-vs-candidate route discriminator deliberately installs only
-- the exact shared-runtime/return sites needed to distinguish DAA3 from DAE9.
-- The full containment mode adds the Stage-7 helper census separately.  This
-- keeps the diagnostic from reproducing the large-breakpoint perturbation it
-- is intended to classify.
if ROUTE_DIAGNOSTIC then
    add_breakpoint(RESUME_PC, "resume_state", RESUME_BANK)
    add_breakpoint(0xDA60, "runtime_entry")
    add_breakpoint(0xDAA3, "runtime_native_restore")
    add_breakpoint(0xDAE9, "runtime_nonstage_gate")
    add_breakpoint(0xDAF5, "runtime_nonstage_ret")
    add_breakpoint(0x3493, "rst_return")
    add_breakpoint(0x42B1, "dirty_branch", 1)
    add_breakpoint(0xDA13, "atomic_entry")
    add_breakpoint(0x42B8, "copy_continue", 1)
    startup:write("instrumentation-armed\n"); startup:flush()
end

finish = function()
    if finished then return end
    finished = true
    local forbidden = hits.helper_entry + hits.phase1_service
        + hits.phase2_service + hits.attr_dma + hits.tile_dma
        + hits.fallback_native + hits.caller_reject + hits.fallback_atomic
    local status = "ok"
    if frame ~= FRAMES or scene_samples ~= FRAMES or scene_unreadable ~= 0
        or wrong_scene ~= 0
        or ff55_nonidle ~= 0 or boundary_bank22 ~= 0 or ffe4_nonzero ~= 0
        or forbidden ~= 0 then
        status = "violation"
    end
    if ROUTE_DIAGNOSTIC then
        if hits.resume_state == 0 or hits.runtime_entry == 0 then
            status = "violation"
        end
        if ROUTE_MODE == "candidate" then
            if hits.runtime_nonstage_gate == 0
                or hits.runtime_nonstage_ret == 0
                or hits.rst_return == 0 or hits.dirty_branch == 0 then
                status = "violation"
            end
        else
            if hits.runtime_native_restore == 0 or hits.rst_return == 0
                or hits.dirty_branch == 0
                or hits.runtime_nonstage_gate ~= 0
                or hits.runtime_nonstage_ret ~= 0 then
                status = "violation"
            end
        end
        local save_ok, result = pcall(function()
            return emu:saveStateFile(STATE_OUT)
        end)
        if save_ok and result ~= false then final_saved = 1
        else status = "state-save-failed" end
    elseif final_saved ~= 1
        or state_save_stable_frames < 2 then
        status = "violation"
    end

    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "schema=%s status=%s frames=%d scene_samples=%d " ..
        "scene_unreadable=%d wrong_scene=%d " ..
        "ff55_nonidle=%d boundary_bank22=%d ffe4_nonzero=%d " ..
        "final_saved=%d drain_frames=%d " ..
        "safe_finish=%d max_drain_frames=%d route_diagnostic=%d " ..
        "route_mode=%s production_debugger_instrumentation=%d " ..
        "state_save_wait_frames=%d " ..
        "state_save_stable_frames=%d\n",
        PROBE_SCHEMA, status, frame, scene_samples, scene_unreadable,
        wrong_scene, ff55_nonidle, boundary_bank22,
        ffe4_nonzero, final_saved, drain_frames, safe_finish, MAX_DRAIN_FRAMES,
        ROUTE_DIAGNOSTIC and 1 or 0, ROUTE_MODE,
        ROUTE_DIAGNOSTIC and 9 or 0,
        state_save_wait_frames,
        state_save_stable_frames))
    for _, name in ipairs(hit_names) do
        report:write(string.format("hit\t%s\t%d\n", name, hits[name]))
    end
    for _, line in ipairs(frame_lines) do report:write(line .. "\n") end
    for _, line in ipairs(events) do report:write("event\t" .. line .. "\n") end
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
    startup:write("finished " .. status .. "\n"); startup:close()
    emu:stop()
end

local function complete_final_state_size()
    local handle = io.open(STATE_OUT, "rb")
    if not handle then return nil end
    local size = handle:seek("end")
    if not size or size < 1024 then handle:close(); return nil end
    handle:seek("set", size - 12)
    local tail = handle:read(12)
    handle:close()
    if not tail or #tail ~= 12 or tail:sub(5, 8) ~= "IEND" then return nil end
    return size
end

callbacks:add("frame", function()
    if finished then return end
    if not state_loaded then
        startup:write("first-frame-callback\n"); startup:flush()
        local ok, result = pcall(function()
            return emu:loadStateFile(STATE_FILE)
        end)
        assert(ok and result ~= false, "failed to load normalized Crystal state")
        -- Crystal savestates demonstrably stop advancing when any debugger
        -- breakpoint/watchpoint is installed. Production containment is
        -- therefore boundary/outcome based and installs zero debugger hooks.
        -- The optional historical route diagnostic remains non-promotable.
        state_loaded, armed = true, true
        if ROUTE_DIAGNOSTIC then
            startup:write("state-loaded-route-debugger\n")
        else
            startup:write("state-loaded-zero-debugger\n")
        end
        startup:flush()
        emu:setKeys(0)
        return
    end

    if state_save_pending then
        emu:setKeys(0)
        state_save_wait_frames = state_save_wait_frames + 1
        local size = complete_final_state_size()
        if size and size == state_save_last_size then
            state_save_stable_frames = state_save_stable_frames + 1
        elseif size then
            state_save_last_size = size
            state_save_stable_frames = 1
        else
            state_save_stable_frames = 0
        end
        if state_save_stable_frames >= 2 then
            state_save_pending = false
            finish()
        elseif state_save_wait_frames > 120 then
            state_save_pending = false
            finish()
        end
        return
    end

    if drain_pending then
        drain_frames = drain_frames + 1
        emu:setKeys(0)
        if drain_frames > MAX_DRAIN_FRAMES then finish() end
        return
    end

    frame = frame + 1
    emu:setKeys(0)
    if frame == 1 or (frame % 60) == 0 then
        startup:write(string.format("frame %d\n", frame)); startup:flush()
    end
    local pc, rom = register("PC"), emu:read8(0xFF99)
    local svbk, vbk = emu:read8(0xFF70) & 7, emu:read8(0xFF4F) & 1
    local ff55 = emu:read8(0xFF55)
    local scene_text = "--"
    if svbk == 0 or svbk == 1 then
        local scene = emu:read8(0xD880)
        scene_samples = scene_samples + 1
        scene_text = string.format("%02X", scene)
        if scene ~= EXPECTED_SCENE then wrong_scene = wrong_scene + 1 end
    else
        scene_unreadable = scene_unreadable + 1
    end
    if ff55 ~= 0xFF then
        ff55_nonidle = ff55_nonidle + 1
        remember("nonidle-ff55", string.format("value=%02X", ff55))
    end
    if rom == HELPER_BANK then
        boundary_bank22 = boundary_bank22 + 1
        remember("bank22-frame-boundary", "")
    end
    if emu:read8(0xFFE4) ~= 0 then ffe4_nonzero = ffe4_nonzero + 1 end
    frame_lines[#frame_lines + 1] = string.format(
        "frame\t%d\t%s\t%04X\t%02X\t%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X",
        frame, scene_text, pc, rom, svbk, vbk, ff55,
        emu:read8(0xFFA5), emu:read8(0xFFE0), emu:read8(0xFFFF),
        emu:read8(0xFF40), emu:read8(0xFFBA), emu:read8(0xFFC1),
        emu:read8(0xFFE4))
    if frame >= FRAMES then
        if ROUTE_DIAGNOSTIC then finish()
        else
            local saved, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            if saved and result ~= false then
                final_saved = 1
                state_save_pending = true
                armed = false
            else
                finish()
            end
        end
    end
end)
