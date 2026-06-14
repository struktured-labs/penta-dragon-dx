-- cheat_max_state.lua — force max powerup + Dragon form + full HP every frame.
-- Load alongside live_palettes.lua via Tools → Scripting → File → Load.
--
-- Bytes:
--   FFBE = 1   (Sara form: Dragon)
--   FFC0 = 3   (Powerup: Turbo)  — try 1 (spiral) or 2 (shield) if Turbo
--               isn't visually a "star". User can edit this constant.
--   DCDD = 0xFF (Sara HP main; some scenes also need DCDC)
--   DCDC = 0xFF (Sara HP sub-counter)

local function force(addr, val)
    if emu:read8(addr) ~= val then
        emu:write8(addr, val)
    end
end

callbacks:add("frame", function()
    -- Only force during gameplay (FFC1 != 0). Avoids fighting with the
    -- title/menu state that may legitimately use these bytes.
    if emu:read8(0xFFC1) == 0 then return end
    force(0xFFBE, 1)        -- Dragon form
    force(0xFFC0, 3)        -- Turbo powerup
    force(0xDCDD, 0xFF)     -- HP main
    force(0xDCDC, 0xFF)     -- HP sub
end)

-- Optional log so you know it loaded
local log = io.open("/tmp/cheat_max_state.log", "w")
if log then
    log:write("cheat_max_state.lua loaded\n")
    log:close()
end
