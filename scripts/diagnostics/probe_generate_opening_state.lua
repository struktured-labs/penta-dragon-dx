-- Generate a ROM-matched mGBA state inside the default OPENING START story.
--
-- The title cursor begins on OPENING START. Short A pulses confirm that
-- highlighted option; DOWN is deliberately never pressed (DOWN selects GAME
-- START instead).

local STATE_OUT = assert(
    os.getenv("OPENING_STATE_OUT"),
    "OPENING_STATE_OUT required"
)
local OUT = os.getenv("OPENING_OUT") or "/tmp/penta-opening-state"
local ART_TARGET = tonumber(os.getenv("OPENING_ART_ID") or "")
local ATTR_MASK = os.getenv("OPENING_ATTR_MASK") or ""
if ART_TARGET then
    assert(#ATTR_MASK == 160, "OPENING_ATTR_MASK must contain 160 digits")
end
local TRACE = os.getenv("OPENING_TRACE")
local f, reached, stable, done = 0, false, 0, false
local map_dumped = false

local function visible_attr_layout()
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
            local expected = 0
            if ART_TARGET and row <= 7 then
                local index = row * 20 + column + 1
                expected = assert(tonumber(ATTR_MASK:sub(index, index)))
            end
            if attr == expected then
                if expected ~= 0 then
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

local function map_nonzero(base)
    local old_vbk = emu:read8(0xFF4F)
    local count = 0
    emu:write8(0xFF4F, 1)
    for offset = 0, 0x3FF do
        if emu:read8(base + offset) ~= 0 then count = count + 1 end
    end
    emu:write8(0xFF4F, old_vbk)
    return count
end

local function map_nonzero_cells(base)
    local old_vbk = emu:read8(0xFF4F)
    local cells = {}
    emu:write8(0xFF4F, 1)
    for offset = 0, 0x3FF do
        local value = emu:read8(base + offset)
        if value ~= 0 then
            cells[#cells + 1] = string.format("%03X:%02X", offset, value)
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return table.concat(cells, ",")
end

local function finish(status, message)
    if done then return end
    done = true
    local target, neutral, wrong, unsafe = visible_attr_layout()
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s frame=%d d880=%02X ffc1=%d ffba=%02X " ..
        "stable=%d art_target=%s dce8=%02X dcea=%02X dcf0=%02X " ..
        "dd07=%02X visible_attr_target=%d visible_attr_neutral=%d " ..
        "visible_attr_wrong=%d visible_attr_unsafe=%d message=%s\n",
        status, f, emu:read8(0xD880), emu:read8(0xFFC1),
        emu:read8(0xFFBA), stable, tostring(ART_TARGET),
        emu:read8(0xDCE8), emu:read8(0xDCEA),
        emu:read8(0xDCF0), emu:read8(0xDD07),
        target, neutral, wrong, unsafe, message
    ))
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if done then return end
    f = f + 1
    local scene = emu:read8(0xD880)
    if TRACE and scene == 0x15 and (f % 10) == 0 then
        local trace_target, trace_neutral, trace_wrong, trace_unsafe =
            visible_attr_layout()
        local trace = assert(io.open(TRACE, "a"))
        trace:write(string.format(
            "f=%d stable=%d dce8=%02X dcea=%02X dcf0=%02X dd07=%02X " ..
            "scy=%02X scx=%02X key=%02X row=%02X target=%d " ..
            "neutral=%d wrong=%d unsafe=%d lcdc=%02X nz9800=%d nz9c00=%d\n",
            f, stable, emu:read8(0xDCE8), emu:read8(0xDCEA),
            emu:read8(0xDCF0), emu:read8(0xDD07),
            emu:read8(0xFF42), emu:read8(0xFF43),
            emu:read8(0xDF49), emu:read8(0xDF4A),
            trace_target, trace_neutral, trace_wrong, trace_unsafe,
            emu:read8(0xFF40), map_nonzero(0x9800), map_nonzero(0x9C00)
        ))
        if not map_dumped
            and ART_TARGET
            and emu:read8(0xDCF0) == ART_TARGET
            and emu:read8(0xDF4A) >= 0x88
        then
            trace:write("map9800_cells=" .. map_nonzero_cells(0x9800) .. "\n")
            trace:write("map9c00_cells=" .. map_nonzero_cells(0x9C00) .. "\n")
            map_dumped = true
        end
        trace:close()
    end

    if not reached then
        -- Repeated released pulses make the route robust to title draw timing.
        -- No directional input is ever sent, preserving the default option.
        local pulse = f >= 180 and f <= 900 and (f % 120) < 4
        emu:setKeys(pulse and 0x01 or 0)
        if scene == 0x15 then
            reached = true
            emu:setKeys(0)
        elseif f > 1800 then
            finish("error", "opening-entry-timeout")
            return
        end
    else
        if scene ~= 0x15 then
            finish("error", "opening-left-before-save")
            return
        end
        if ART_TARGET then
            -- Advance the stock story slowly enough that every art phase is
            -- displayed. Once the requested art is committed, release A and
            -- hold that untouched panel steady for the state capture.
            local committed = (
                emu:read8(0xDCE8) == 0x02
                and emu:read8(0xDCEA) == 0x01
                and emu:read8(0xDCF0) == ART_TARGET
                and emu:read8(0xDD07) + 1 == ART_TARGET
            )
            local target, neutral, wrong, unsafe = visible_attr_layout()
            local layout_ready = (
                target == 160
                and neutral == 200
                and wrong == 0
                and unsafe == 0
            )
            local pulse = not committed and (f % 90) < 4
            emu:setKeys(pulse and 0x01 or 0)
            stable = (
                committed and layout_ready
            ) and (stable + 1) or 0
        else
            emu:setKeys(0)
            local target, neutral, wrong, unsafe = visible_attr_layout()
            stable = (
                target == 0
                and neutral == 360
                and wrong == 0
                and unsafe == 0
            ) and (stable + 1) or 0
        end
        if stable == 240 then
            emu:screenshot(OUT .. ".png")
            local ok, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            if not ok or result == false then
                finish("error", "saveStateFile-failed")
                return
            end
            finish("ok", "saved")
        end
    end
end)
