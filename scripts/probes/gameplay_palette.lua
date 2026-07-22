-- Gameplay BG colorization harness.
--   1. Auto-press start sequence to enter gameplay
--   2. Wait until FFC1=1 in a dungeon scene (D880=0x02..0x0B)
--   3. Wait a few extra seconds for colorization to settle
--   4. Dump CGB BG palette RAM + BG tile-attribute table from VBK=1
--
-- Output: <STATE_PATH> with pal/attrs in parseable form.

local OUT = os.getenv("STATE_PATH") or "/tmp/penta_gameplay_pal.txt"
local MAX_FRAMES = tonumber(os.getenv("MAX_FRAMES") or "1200")
local SETTLE_FRAMES = tonumber(os.getenv("SETTLE_FRAMES") or "120")

-- Auto-play sequence: DOWN to pick game start, then A several times to confirm
-- Mirrors automated game-start sequence from MEMORY.md.
local KEY_A     = 0x01
local KEY_DOWN  = 0x80
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
local fired = false

local function dump_state()
    local fh = io.open(OUT, "w")
    -- BG palette RAM (64 bytes)
    fh:write("# BG palette RAM (CGB BCPS index 0..63)\n")
    for p = 0, 7 do
        local line = string.format("pal%d:", p)
        for c = 0, 3 do
            local idx = (p * 8) + (c * 2)
            emu:write8(0xFF68, idx)
            local lo = emu:read8(0xFF69)
            emu:write8(0xFF68, idx + 1)
            local hi = emu:read8(0xFF69)
            line = line .. string.format(" %02X%02X", lo, hi)
        end
        fh:write(line .. "\n")
    end
    -- BG tile attribute table (VBK=1, 0x9800-0x9BFF = 1024 bytes)
    -- Count distinct palette indices (low 3 bits of attr byte).
    local attr_counts = {[0]=0,[1]=0,[2]=0,[3]=0,[4]=0,[5]=0,[6]=0,[7]=0}
    emu:write8(0xFF4F, 1)
    for addr = 0x9800, 0x9BFF do
        local a = emu:read8(addr)
        local pal_idx = a & 0x07
        attr_counts[pal_idx] = attr_counts[pal_idx] + 1
    end
    emu:write8(0xFF4F, 0)
    fh:write("# BG tile-attribute palette-index histogram (1024 tiles)\n")
    for i = 0, 7 do
        fh:write(string.format("attr_pal%d=%d\n", i, attr_counts[i]))
    end
    -- State for debug
    fh:write(string.format("FFC1=%d\n", emu:read8(0xFFC1)))
    fh:write(string.format("D880=0x%02X\n", emu:read8(0xD880)))
    fh:write(string.format("FFBA=%d\n", emu:read8(0xFFBA)))
    fh:write(string.format("frame_dump=%d gameplay_at=%d\n", f, gameplay_at))
    fh:close()
    console:log(string.format("gameplay_palette dumped at frame %d", f))
end

callbacks:add("frame", function()
    if fired then return end
    f = f + 1

    -- Run title menu auto-sequence
    local keys = 0
    for _, sched in ipairs(SCHEDULE) do
        if f >= sched[1] and f <= sched[2] then keys = sched[3]; break end
    end
    emu:setKeys(keys)

    -- FFC1 becomes 1 during the all-pal0 STAGE splash (D880=0x18), before
    -- dungeon attributes exist. Do not mistake that transition for gameplay.
    local d880 = emu:read8(0xD880)
    if gameplay_at < 0 and emu:read8(0xFFC1) == 1
        and d880 >= 0x02 and d880 < 0x0C then
        gameplay_at = f
        console:log("gameplay reached at frame " .. f)
    end

    if gameplay_at > 0 and f >= gameplay_at + SETTLE_FRAMES then
        fired = true
        dump_state()
        os.exit(0)
    end

    if f >= MAX_FRAMES then
        fired = true
        dump_state()  -- still dump for diagnosis
        console:log("gameplay never reached (timeout)")
        os.exit(0)
    end
end)
