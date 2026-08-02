-- Verify the ROM-native story/ending attribute sweep from one stable state.
--
-- The savestate is supplied with mGBA's -t option. This probe never patches
-- ROM, WRAM, stack, input, or control flow; it only lets the candidate resume,
-- audits its active visible attribute map, and captures the rendered frame.

local OUT = assert(os.getenv("STORY_ATTR_OUT"), "STORY_ATTR_OUT is required")
local KIND = assert(os.getenv("STORY_ATTR_KIND"), "STORY_ATTR_KIND is required")
local PALETTE = assert(
    tonumber(os.getenv("STORY_ATTR_PALETTE")),
    "STORY_ATTR_PALETTE is required"
)
local EXPECT_D880 = assert(
    tonumber(os.getenv("STORY_ATTR_D880")),
    "STORY_ATTR_D880 is required"
)
local EXPECT_SEQUENCE = tonumber(os.getenv("STORY_ATTR_SEQUENCE") or "")
local EXPECT_D889 = tonumber(os.getenv("STORY_ATTR_D889") or "")
local EXPECT_DCE2 = tonumber(os.getenv("STORY_ATTR_DCE2") or "")
local EXPECT_FFF9 = tonumber(os.getenv("STORY_ATTR_FFF9") or "")
local WAIT = tonumber(os.getenv("STORY_ATTR_WAIT")) or 90
local TRACE = os.getenv("STORY_ATTR_TRACE")
local f, done = 0, false

local function guard_holds()
    if emu:read8(0xD880) ~= EXPECT_D880 or emu:read8(0xFFC1) ~= 0 then
        return false
    end
    if KIND == "story" then
        return (
            emu:read8(0xDCE8) == EXPECT_SEQUENCE
            and emu:read8(0xDCEA) == 1
            and emu:read8(0xDCF0) == PALETTE
            and ((emu:read8(0xDD07) + 1) & 0xFF) == PALETTE
        )
    elseif KIND == "ending" then
        return (
            emu:read8(0xFFE4) == 1
            and emu:read8(0xD889) == EXPECT_D889
            and emu:read8(0xDCE2) == EXPECT_DCE2
            and emu:read8(0xFFF9) == EXPECT_FFF9
        )
    elseif KIND == "neutral" then
        return true
    end
    return false
end

local function visible_attr_counts()
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local target, neutral, wrong, unsafe = 0, 0, 0, 0
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local attr = emu:read8(base + map_y * 32 + map_x)
            local pal = attr & 0x07
            local expected = 0
            if KIND == "ending" or (KIND == "story" and row <= 7) then
                expected = PALETTE
            end
            if pal == expected then
                if expected == PALETTE and PALETTE ~= 0 then
                    target = target + 1
                else
                    neutral = neutral + 1
                end
            else
                wrong = wrong + 1
            end
            if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return target, neutral, wrong, unsafe
end

local function active_table_nonzero()
    local count = 0
    for offset = 0, 0xFF do
        if emu:read8(0xC600 + offset) ~= 0 then count = count + 1 end
    end
    return count
end

local function trace_layout()
    if not TRACE then return end
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local bad = {}
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local address = base + map_y * 32 + map_x
            local attr = emu:read8(address)
            local expected = 0
            if KIND == "ending" or (KIND == "story" and row <= 7) then
                expected = PALETTE
            end
            if (attr & 0x07) ~= expected or (attr & 0xF8) ~= 0 then
                emu:write8(0xFF4F, 0)
                local tile = emu:read8(address)
                emu:write8(0xFF4F, 1)
                bad[#bad + 1] = string.format(
                    "%d,%d:%04X=%02X/t%02X",
                    row, column, address, attr, tile
                )
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    local trace = assert(io.open(TRACE, "a"))
    trace:write(string.format(
        "frame=%d key=%02X row=%02X vbk=%02X bad=%d %s\n",
        f, emu:read8(0xDF49), emu:read8(0xDF4A),
        old_vbk, #bad, table.concat(bad, " ")
    ))
    trace:close()
end

local function finish(status, message)
    if done then return end
    done = true
    local target, neutral, wrong, unsafe = visible_attr_counts()
    local table_nonzero = active_table_nonzero()
    local expected_target = 0
    local expected_neutral = 360
    if KIND == "story" then
        expected_target, expected_neutral = 160, 200
    elseif KIND == "ending" then
        expected_target, expected_neutral = 360, 0
    end
    if (
        status == "ok"
        and (
            target ~= expected_target
            or neutral ~= expected_neutral
            or wrong ~= 0
            or unsafe ~= 0
            or table_nonzero ~= 0
        )
    ) then
        status = "error"
        message = "attribute-layout-mismatch"
    end
    if status == "ok" then emu:screenshot(OUT .. ".png") end
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s kind=%s frame=%d d880=%02X palette=%d " ..
        "target=%d neutral=%d wrong=%d unsafe=%d table_nonzero=%d " ..
        "df07=%02X key=%02X row=%02X lcdc=%02X scy=%02X scx=%02X " ..
        "message=%s\n",
        status, KIND, f, emu:read8(0xD880), PALETTE,
        target, neutral, wrong, unsafe, table_nonzero,
        emu:read8(0xDF07), emu:read8(0xDF49), emu:read8(0xDF4A),
        emu:read8(0xFF40), emu:read8(0xFF42), emu:read8(0xFF43),
        message
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
    if not guard_holds() then
        finish("error", "state-left-expected-page")
        return
    end
    trace_layout()
    if f == WAIT then finish("ok", "rom-native-attribute-sweep") end
end)
