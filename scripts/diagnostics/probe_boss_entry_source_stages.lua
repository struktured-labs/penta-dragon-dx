-- Trace C1A0 at each major return in the stock boss dispatcher. Diagnostic
-- only: this identifies which native setup stage expects the room teardown
-- that a synthetic direct CALL bypasses.

local OUT = assert(os.getenv("BOSS_ENTRY_SOURCE_OUT"))
local out = assert(io.open(OUT, "w"))
local source = 0xC1A0
local hits, frames, done = 0, 0, false

local function snapshot(label)
    local floor, numbered, other = 0, 0, 0
    for offset = 0, 24 * 24 - 1 do
        local tile = emu:read8(source + offset)
        if tile >= 0x77 and tile <= 0x7A then floor = floor + 1
        elseif tile >= 0x02 and tile <= 0x76 then numbered = numbered + 1
        else other = other + 1 end
    end
    out:write(string.format("frame=%d label=%s floor=%d numbered=%d other=%d\n",
        frames, label, floor, numbered, other))
    out:flush()
    hits = hits + 1
end

for _, item in ipairs({
    {0x1A2B, "entry"}, {0x1A4C, "after_16fd"},
    {0x1A4F, "after_174e"}, {0x1A52, "after_759b"},
    {0x1A55, "after_1ec0"}, {0x1A6F, "before_bank2_4000"},
    {0x1A72, "after_bank2_4000"}, {0x1AA9, "before_40b7"},
    {0x1AAC, "after_40b7"}, {0x1AAF, "after_492b"},
}) do
    emu:setBreakpoint(function() snapshot(item[2]) end, item[1])
end

callbacks:add("frame", function()
    if done then return end
    frames = frames + 1
    emu:setKeys(0)
    if frames >= 180 or hits >= 10 then
        done = true
        out:close()
        local marker = assert(io.open(OUT .. ".done", "w"))
        marker:write("ok\n"); marker:close()
        os.exit(0)
    end
end)
