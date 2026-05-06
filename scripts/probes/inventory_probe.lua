-- Inventory address discovery probe.
-- Dumps WRAM 0xC000-0xCFFF every 30 frames + logs item-pickup-likely events
-- (FFC0 changes, sprite tile patterns hinting at item collision).
--
-- Run: USER PLAYS, picks up items, varies inventory. Then we diff WRAM
-- snapshots adjacent to pickup events to find the slot addresses.
--
-- Output: rl/bc_data/inventory_wram.jsonl (each row = state + 4KB WRAM hex)

local f = 0
local recording = false
local KEY_A=0x01; local KEY_DOWN=0x80; local KEY_START=0x08
local TITLE = {
    {180,185,KEY_DOWN}, {193,198,KEY_A}, {241,246,KEY_A},
    {291,296,KEY_A}, {341,346,KEY_START}, {391,396,KEY_A},
}

local REC = io.open("/home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/inventory_wram.jsonl", "w")
console:log("[INV-PROBE] writing to /home/struktured/projects/penta-dragon-dx-claude/rl/bc_data/inventory_wram.jsonl")
console:log("[INV-PROBE] play and pick up items! Each WRAM dump = 4KB of bytes 0xC000-0xCFFF")
console:log("[INV-PROBE] CRITICAL: also press Select/Start to cycle items, USE items via Start menu")

local last_ffc0 = 0
local last_dcdc = 0xFF

callbacks:add("frame", function()
    f = f + 1

    -- Auto-nav title (skip if game already in gameplay)
    if not recording then
        if emu:read8(0xFFC1) == 1 and f > 60 then
            recording = true
            console:log(string.format("[INV-PROBE] gameplay reached at frame %d", f))
        elseif f <= 500 then
            local k = 0
            for _, e in ipairs(TITLE) do
                if f >= e[1] and f <= e[2] then k = e[3]; break end
            end
            emu:setKeys(k)
        end
        return
    end

    -- Detect interesting events for sparse logging
    local ffc0 = emu:read8(0xFFC0)
    local dcdc = emu:read8(0xDCDC)
    local event = nil
    if ffc0 ~= last_ffc0 then event = string.format("ffc0:%d->%d", last_ffc0, ffc0) end
    if dcdc > last_dcdc then event = string.format("hp_up:%d->%d", last_dcdc, dcdc) end  -- HP went up = used heal
    last_ffc0 = ffc0; last_dcdc = dcdc

    -- Log every 30 frames OR on event
    if f % 30 ~= 0 and event == nil then return end

    REC:write("{")
    REC:write(string.format('"f":%d,"FFBA":%d,"FFBD":%d,"FFBE":%d,"FFBF":%d,"FFC0":%d,"FFC1":%d,',
        f, emu:read8(0xFFBA), emu:read8(0xFFBD), emu:read8(0xFFBE),
        emu:read8(0xFFBF), ffc0, emu:read8(0xFFC1)))
    REC:write(string.format('"DCDC":%d,"DCDD":%d,"DC04":%d,', dcdc, emu:read8(0xDCDD), emu:read8(0xDC04)))
    if event then REC:write(string.format('"event":"%s",', event)) end
    -- Dump 4KB WRAM as hex
    REC:write('"wram_C000_CFFF":"')
    for a = 0xC000, 0xCFFF do
        REC:write(string.format("%02X", emu:read8(a)))
    end
    -- Also high WRAM 0xD000-0xDFFF (covers DC* and DD* areas where game state lives)
    REC:write('","wram_D000_DFFF":"')
    for a = 0xD000, 0xDFFF do
        REC:write(string.format("%02X", emu:read8(a)))
    end
    REC:write('"}\n')

    if f % 600 == 0 then
        REC:flush()
        console:log(string.format("[INV-PROBE] f=%d FFC0=%d DCDC=%d", f, ffc0, dcdc))
    end
end)

callbacks:add("shutdown", function()
    if REC then REC:close() end
end)
