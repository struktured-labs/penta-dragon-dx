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

local OUT = os.getenv("STATE_PATH") or "/tmp/penta_d887.txt"
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
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xFF)

    local d887 = emu:read8(0xD887)
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
            table.insert(trans_log, string.format("f=%d  D887: %02X -> %02X", f, prev_d887, d887))
        end
        prev_d887 = d887
    end
    if d887 ~= 0 then
        nonzero_run = nonzero_run + 1
        if nonzero_run > max_nonzero_run then max_nonzero_run = nonzero_run end
    else
        nonzero_run = 0
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
        fh:close()
        console:log(string.format("phantom_d887: %d transitions in %d gameplay frames",
            transitions, MEASURE_FRAMES))
        os.exit(0)
    end
end)
