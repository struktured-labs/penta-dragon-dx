-- Validate a generated pre/post-final stream state in a fresh mGBA process.
--
-- The state is loaded by mGBA's -t option before this script runs. This probe
-- never patches ROM, stack, WRAM, control flow, or input; it only observes the
-- release ROM resuming naturally from the captured story panel. The attribute
-- audit verifies the production top-art/dialogue split and restores VBK.

local ENTRY = os.getenv("FINAL_STORY_ENTRY") or "pre-final"
local OUT = os.getenv("FINAL_STORY_OUT") or "/tmp/penta-final-story-integrity"
local EXPECTED = (ENTRY == "pre-final") and 0x19 or 0x1A
local EXPECTED_SEQUENCE = (ENTRY == "pre-final") and 0x04 or 0x05
local ART_TARGET = tonumber(os.getenv("FINAL_STORY_ART_ID") or "")
local f, stable, done = 0, 0, false

local function requested_art_is_committed()
    return (
        not ART_TARGET
        or (
            emu:read8(0xDCE8) == EXPECTED_SEQUENCE
            and emu:read8(0xDCEA) == 0x01
            and emu:read8(0xDCF0) == ART_TARGET
            and emu:read8(0xDD07) + 1 == ART_TARGET
        )
    )
end

local function visible_attr_layout()
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local target, neutral, wrong = 0, 0, 0
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local attr = emu:read8(base + map_y * 32 + map_x)
            local expected = (row <= 7) and ART_TARGET or 0
            if attr == expected then
                if row <= 7 then
                    target = target + 1
                else
                    neutral = neutral + 1
                end
            else
                wrong = wrong + 1
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return target, neutral, wrong
end

local function active_table_is_neutral()
    for offset = 0, 0xFF do
        if emu:read8(0xCC00 + offset) ~= 0 then return false end
    end
    return true
end

local function finish(status, message)
    if done then return end
    done = true
    local target, neutral, wrong = visible_attr_layout()
    local table_neutral = active_table_is_neutral()
    if (
        status == "ok"
        and (
            target ~= 160
            or neutral ~= 200
            or wrong ~= 0
            or not table_neutral
        )
    ) then
        status = "error"
        message = "production-layout-mismatch"
    end
    if status == "ok" then emu:screenshot(OUT .. ".png") end
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s entry=%s frame=%d d880=%02X ffc1=%d ffba=%02X " ..
        "ffe4=%d stable=%d visible_attr_target=%d " ..
        "visible_attr_neutral=%d visible_attr_wrong=%d table_neutral=%s " ..
        "art_target=%s dce8=%02X dcea=%02X dcf0=%02X dd07=%02X " ..
        "message=%s\n",
        status, ENTRY, f, emu:read8(0xD880), emu:read8(0xFFC1),
        emu:read8(0xFFBA), emu:read8(0xFFE4), stable,
        target, neutral, wrong, tostring(table_neutral), tostring(ART_TARGET),
        emu:read8(0xDCE8), emu:read8(0xDCEA),
        emu:read8(0xDCF0), emu:read8(0xDD07), message
    ))
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if done then return end
    f = f + 1
    emu:setKeys(0)
    local scene = emu:read8(0xD880)
    if (
        scene == EXPECTED
        and emu:read8(0xFFC1) == 0
        and requested_art_is_committed()
    ) then
        stable = stable + 1
    else
        finish("error", "state-left-expected-story-panel")
        return
    end
    if stable == 60 then finish("ok", "colored-release-rom-resume") end
end)
