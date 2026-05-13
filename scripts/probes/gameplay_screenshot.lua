-- Capture screenshot during gameplay. Auto-press start, get to dungeon, save N
-- screenshots at fixed game frames.
local PREFIX = os.getenv("STATE_PREFIX") or "/tmp/penta_gp"
local SHOTS_AT = {1500, 1800, 2100, 2400, 2700}  -- gameplay frames to snap
local MAX_FRAMES = 3000

local KEY_A     = 0x01
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
local shot_idx = 1

callbacks:add("frame", function()
    f = f + 1
    -- Title sequence
    local title_keys = 0
    for _, sched in ipairs(SCHEDULE) do
        if f >= sched[1] and f <= sched[2] then title_keys = sched[3]; break end
    end
    if f < 450 then emu:setKeys(title_keys); return end

    -- During gameplay: walk right + fire
    if emu:read8(0xFFC1) == 1 then
        emu:setKeys(KEY_RIGHT + (f % 4 == 0 and KEY_A or 0))
        emu:write8(0xDCDD, 0x17); emu:write8(0xDCDC, 0xFF); emu:write8(0xDCBB, 0xFF)
    end

    if shot_idx <= #SHOTS_AT and f >= SHOTS_AT[shot_idx] then
        local out = string.format("%s_%d.png", PREFIX, shot_idx)
        emu:screenshot(out)
        console:log(string.format("shot %d at frame %d -> %s", shot_idx, f, out))
        shot_idx = shot_idx + 1
    end

    if f >= MAX_FRAMES or shot_idx > #SHOTS_AT then
        os.exit(0)
    end
end)
