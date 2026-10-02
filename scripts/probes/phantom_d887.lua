-- Phantom sound detector: counts D887 transitions during sustained gameplay.
--
-- Phantom sounds occur when Timer ISR partially updates D887, leaving
-- intermediate values that get played. Vanilla coalesces these, modded
-- builds with trampoline / VBlank bugs lose coalescence → more transitions.
--
-- Strategy: auto-press the start sequence to enter gameplay, then exercise
-- actions (move + fire) for the measurement window. Count D887 transitions
-- only during the gameplay window. Idle title-screen comparison is useless
-- because the sound engine produces nothing on the title menu.
-- #41: native assistance writes physical WRAM bank1 regardless of the SVBK
-- bank a graphics routine selected. #37: never write DCDC/DCDD (inventory /
-- ten-slot cursor) as fake health; DCBB is the health byte.
local native_assistance = {writes = 0, bank_shadow_counts = {}}
function native_assistance.write(address, value)
  local svbk = emu:read8(0xFF70) & 7
  native_assistance.writes = native_assistance.writes + 1
  native_assistance.bank_shadow_counts[svbk] =
    (native_assistance.bank_shadow_counts[svbk] or 0) + 1
  assert(emu.memory and emu.memory.wram, "physical WRAM required for assistance")
    :write8(address - 0xC000, value)
end

local OUT = os.getenv("STATE_PATH") or "tmp/penta_d887.txt"
local MEASURE_FRAMES = tonumber(os.getenv("MEASURE_FRAMES") or "600")
local MAX_BOOT_FRAMES = tonumber(os.getenv("MAX_BOOT_FRAMES") or "600")

local KEY_A     = 0x01
local KEY_B     = 0x02
local KEY_DOWN  = 0x80
local KEY_RIGHT = 0x10
local KEY_START = 0x08

local SCHEDULE = {
    {180, 185, KEY_DOWN}, {186, 200, 0},
    {201, 206, KEY_A},    {207, 260, 0},
    {261, 266, KEY_A},    {267, 320, 0},
    {321, 326, KEY_A},    {327, 380, 0},
    {381, 386, KEY_START}, {387, 430, 0},
    {431, 436, KEY_A},
}

local f = 0
local gameplay_at = -1
local measure_started = false
local prev_d887 = 0
local transitions = 0
local trans_log = {}
local command_pulses = 0
local clear_pulses = 0
local chained_commands = 0
local nonzero_run = 0
local max_nonzero_run = 0
local command_values = {}
local fired = false
local rst_log = {}
local dma_unreadable_samples = 0

local function register(name)
    local readers = {
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }
    for _, reader in ipairs(readers) do
        local ok, value = pcall(reader)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

local function read16(address)
    return emu:read8(address) | (emu:read8((address + 1) & 0xFFFF) << 8)
end

-- Issue #16 diagnostic only: frame samples can miss a command that the
-- timer-driven engine reads and clears between frames. Observe bank-3's
-- actual nonzero mailbox read and its accept/reject branches. This does not
-- alter the existing acceptance rule and is not an acoustic-fidelity test.
local ENGINE_TRACE = os.getenv("PENTA_PHANTOM_ENGINE_TRACE")
local engine_trace
if ENGINE_TRACE then
    engine_trace = assert(io.open(ENGINE_TRACE, "w"))
    engine_trace:write("event\tframe\tcommand\tactive\tpc\tsvbk\n")
    local function observe(event, command_register)
        if gameplay_at < 0 or fired then return end
        engine_trace:write(string.format("%s\t%d\t%02X\t%02X\t%04X\t%02X\n",
            event, f, register(command_register) & 0xFF,
            emu:read8(0xD888), register("PC"), emu:read8(0xFF70)))
        engine_trace:flush()
    end
    -- $45B6 follows LD A,[$D887]; OR A; RET Z.
    -- $45C2 drops a lower-priority command; $45C7 starts/restarts the effect.
    emu:setBreakpoint(function() observe("read", "A") end, 0x45B6, 3)
    emu:setBreakpoint(function() observe("reject", "C") end, 0x45C2, 3)
    emu:setBreakpoint(function() observe("accept", "C") end, 0x45C7, 3)
end

-- Attribute every sound command to the real RST $38 caller. This is receipt
-- telemetry only; it never modifies the emulated machine.
pcall(function()
    emu:setBreakpoint(function()
        if gameplay_at < 0 or #rst_log >= 200 then return end
        local sp = register("SP")
        rst_log[#rst_log + 1] = string.format(
            "rst_f=%d A=%02X caller=%04X bank=%02X scene=%02X sp=%04X",
            f, register("A") & 0xFF, read16(sp),
            emu:read8(0xFF99), emu:read8(0xD880), sp)
    end, 0x0038)
end)

callbacks:add("frame", function()
    if fired then return end
    f = f + 1

    -- Title menu auto-sequence
    if gameplay_at < 0 then
        local keys = 0
        for _, sched in ipairs(SCHEDULE) do
            if f >= sched[1] and f <= sched[2] then keys = sched[3]; break end
        end
        emu:setKeys(keys)
        if emu:read8(0xFFC1) == 1 then
            gameplay_at = f
            prev_d887 = emu:read8(0xD887)
            measure_started = true
            console:log("gameplay reached at frame " .. f)
        elseif f >= MAX_BOOT_FRAMES then
            -- never reached gameplay — bail out
            local fh = io.open(OUT, "w")
            fh:write("transitions=-1\n# gameplay never reached\n")
            fh:close()
            os.exit(0)
        end
        return
    end

    -- In gameplay: exercise the sound engine with movement+fire.
    -- A repeating ABA pattern triggers shot sounds + footsteps.
    local elapsed = f - gameplay_at
    local input = KEY_RIGHT
    if elapsed % 8 < 4 then input = input + KEY_A end
    if elapsed % 24 == 0 then input = input + KEY_B end
    emu:setKeys(input)

    -- Godmode HP so we don't die mid-test
    native_assistance.write(0xDCBB, 0xFF)

    local sampled_pc = register("PC")
    local d887 = emu:read8(0xD887)
    -- During the stock HRAM OAM-DMA routine ($FF80-$FF9F), CPU-bus reads of
    -- WRAM correctly return $FF. That is an unreadable host sample, not a
    -- sound command. Ignore it without changing the last real D887 value;
    -- every $FF observed outside this exact PC window remains fatal.
    local dma_unreadable = d887 == 0xFF
        and sampled_pc >= 0xFF80 and sampled_pc <= 0xFF9F
    if dma_unreadable then
        dma_unreadable_samples = dma_unreadable_samples + 1
    else
        if d887 ~= prev_d887 then
            transitions = transitions + 1
            if prev_d887 == 0 and d887 ~= 0 then
                command_pulses = command_pulses + 1
                command_values[d887] = (command_values[d887] or 0) + 1
            elseif prev_d887 ~= 0 and d887 == 0 then
                clear_pulses = clear_pulses + 1
            elseif prev_d887 ~= 0 and d887 ~= 0 then
                chained_commands = chained_commands + 1
                command_values[d887] = (command_values[d887] or 0) + 1
            end
            if #trans_log < 200 then
                table.insert(trans_log, string.format(
                    "f=%d pc=%04X D887: %02X -> %02X",
                    f, sampled_pc, prev_d887, d887))
            end
            prev_d887 = d887
        end
        if d887 ~= 0 then
            nonzero_run = nonzero_run + 1
            if nonzero_run > max_nonzero_run then
                max_nonzero_run = nonzero_run
            end
        else
            nonzero_run = 0
        end
    end

    if elapsed >= MEASURE_FRAMES then
        fired = true
        local fh = io.open(OUT, "w")
        fh:write(string.format("# Phantom sound D887 monitor (gameplay)\n"))
        fh:write(string.format("# Boot frames: %d, measure frames: %d\n",
            gameplay_at, MEASURE_FRAMES))
        fh:write(string.format("transitions=%d\n", transitions))
        fh:write(string.format("transitions_per_second=%.2f\n", transitions * 60 / MEASURE_FRAMES))
        fh:write(string.format("command_pulses=%d\n", command_pulses))
        fh:write(string.format("clear_pulses=%d\n", clear_pulses))
        fh:write(string.format("chained_commands=%d\n", chained_commands))
        fh:write(string.format("unpaired_commands=%d\n", command_pulses - clear_pulses))
        fh:write(string.format("max_nonzero_run=%d\n", max_nonzero_run))
        fh:write(string.format(
            "dma_unreadable_samples=%d\n", dma_unreadable_samples))
        local values = {}
        for value, count in pairs(command_values) do
            table.insert(values, {value=value, count=count})
        end
        table.sort(values, function(a, b) return a.value < b.value end)
        local value_parts = {}
        for _, entry in ipairs(values) do
            table.insert(value_parts, string.format("%02X:%d", entry.value, entry.count))
        end
        fh:write("command_values=" .. table.concat(value_parts, ",") .. "\n")
        fh:write("\n--- first 200 transitions ---\n")
        for _, l in ipairs(trans_log) do fh:write(l .. "\n") end
        fh:write("\n--- first 200 RST38 calls ---\n")
        for _, l in ipairs(rst_log) do fh:write(l .. "\n") end
        fh:close()
        if engine_trace then engine_trace:close() end
        local marker = assert(io.open(OUT .. ".done", "w"))
        marker:write("complete\n")
        marker:close()
        console:log(string.format("phantom_d887: %d transitions in %d gameplay frames",
            transitions, MEASURE_FRAMES))
        -- Ordinary verification is stopped by its owning Python launcher once
        -- the complete marker exists. os.exit from the CPU thread races Qt's
        -- GUI destructors. The native AV tap supplies its own synchronous
        -- finalizer/exit path so native captures can end at this exact frame.
        if os.getenv("PENTA_NATIVE_AV_PREFIX") then os.exit(0) end
    end
end)
