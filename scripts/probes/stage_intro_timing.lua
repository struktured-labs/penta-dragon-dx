-- Measure the STAGE XX splash from scene entry (D880=0x18) until dungeon
-- entry (D880=0x02). This catches the repeated-intro-ditty regression where
-- the sound sequence restarts and holds the splash for roughly five seconds.

local OUT = os.getenv("STAGE_TIMING_OUT") or "/tmp/penta_stage_timing.txt"
local MAX_FRAMES = tonumber(os.getenv("STAGE_TIMING_MAX_FRAMES") or "1200")

local KEY_A = 0x01
local KEY_START = 0x08
local KEY_DOWN = 0x80

local SCHEDULE = {
    {180, 186, KEY_DOWN},
    {193, 199, KEY_A},
    {241, 247, KEY_A},
    {291, 297, KEY_A},
    {341, 347, KEY_START},
    {391, 397, KEY_A},
}

local frame = 0
local stage_enter = -1
local stage_exit = -1
local prev_d880 = -1
local prev_d881 = -1
local d880_transitions = {}
local d881_transitions = {}
local pending_init_frames = 0
local sound_pointer_rewinds = 0
local prev_sound_pointer = -1
local timer_ticks = 0
local prev_centisecond = -1
local stage_tac = -1
local stage_tma = -1
local stage_tima = -1
local stage_tempo = -1
local stage_contaminated_cells = -1

local function write_result(status)
    local out = io.open(OUT, "w")
    out:write(string.format("status=%s\n", status))
    out:write(string.format("reached=%d\n", frame))
    out:write(string.format("stage_enter=%d\n", stage_enter))
    out:write(string.format("stage_exit=%d\n", stage_exit))
    if stage_enter >= 0 and stage_exit >= 0 then
        out:write(string.format("stage_frames=%d\n", stage_exit - stage_enter))
    else
        out:write("stage_frames=-1\n")
    end
    out:write(string.format("pending_init_frames=%d\n", pending_init_frames))
    out:write(string.format("sound_pointer_rewinds=%d\n", sound_pointer_rewinds))
    out:write(string.format("timer_ticks=%d\n", timer_ticks))
    out:write(string.format("stage_tac=%02X\n", stage_tac & 0xFF))
    out:write(string.format("stage_tma=%02X\n", stage_tma & 0xFF))
    out:write(string.format("stage_tima=%02X\n", stage_tima & 0xFF))
    out:write(string.format("stage_tempo=%02X\n", stage_tempo & 0xFF))
    out:write(string.format("stage_contaminated_cells=%d\n", stage_contaminated_cells))
    out:write("d880_transitions=" .. table.concat(d880_transitions, ",") .. "\n")
    out:write("d881_transitions=" .. table.concat(d881_transitions, ",") .. "\n")
    out:close()
    os.exit(status == "ok" and 0 or 1)
end

callbacks:add("frame", function()
    frame = frame + 1

    local keys = 0
    for _, event in ipairs(SCHEDULE) do
        if frame >= event[1] and frame < event[2] then
            keys = event[3]
            break
        end
    end
    emu:setKeys(keys)

    local d880 = emu:read8(0xD880)
    local d881 = emu:read8(0xD881)
    if d880 ~= prev_d880 then
        table.insert(d880_transitions,
            string.format("%d:%02X>%02X", frame, prev_d880 & 0xFF, d880))
        prev_d880 = d880
    end
    if d881 ~= prev_d881 then
        table.insert(d881_transitions,
            string.format("%d:%02X>%02X", frame, prev_d881 & 0xFF, d881))
        prev_d881 = d881
    end

    if stage_enter < 0 and d880 == 0x18 then
        stage_enter = frame
        prev_sound_pointer = emu:read8(0xD895) | (emu:read8(0xD896) << 8)
        prev_centisecond = emu:read8(0xFFD1)
        stage_tac = emu:read8(0xFF07)
        stage_tma = emu:read8(0xFF06)
        stage_tima = emu:read8(0xFF05)
        stage_tempo = emu:read8(0xD883)
    elseif stage_enter >= 0 and stage_exit < 0 then
        if d881 ~= d880 then
            pending_init_frames = pending_init_frames + 1
        end
        local pointer = emu:read8(0xD895) | (emu:read8(0xD896) << 8)
        if d880 == 0x18 and pointer < prev_sound_pointer then
            sound_pointer_rewinds = sound_pointer_rewinds + 1
        end
        prev_sound_pointer = pointer

        local centisecond = emu:read8(0xFFD1)
        local tick_delta = centisecond - prev_centisecond
        if tick_delta < 0 then tick_delta = tick_delta + 100 end
        timer_ticks = timer_ticks + tick_delta
        prev_centisecond = centisecond

        if frame == stage_enter + 60 then
            local lcdc = emu:read8(0xFF40)
            local bg_map = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
            local old_vbk = emu:read8(0xFF4F)
            local contaminated = 0
            emu:write8(0xFF4F, 1)
            for row = 0, 17 do
                for column = 0, 19 do
                    local attr = emu:read8(bg_map + row * 32 + column)
                    if (attr & 0x07) ~= 0 then contaminated = contaminated + 1 end
                end
            end
            emu:write8(0xFF4F, old_vbk)
            stage_contaminated_cells = contaminated
        end

        if d880 == 0x02 then
            stage_exit = frame
            write_result("ok")
        end
    end

    if frame >= MAX_FRAMES then
        write_result("timeout")
    end
end)
