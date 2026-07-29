-- Generate a clean mGBA state for one direct-written post-final tail phase.
--
-- A normal cold boot establishes the release ROM's video/interrupt state,
-- then one emulator-only register redirect enters the balanced stock ending
-- routine at 5513. Released A pulses advance its pages. The requested phase
-- must commit with its ROM-native production attributes and a neutral lookup
-- table before the untouched-ROM state is saved. The ROM file is never
-- modified.

local STATE_OUT = assert(
    os.getenv("ENDING_TAIL_STATE_OUT"),
    "ENDING_TAIL_STATE_OUT required"
)
local OUT = os.getenv("ENDING_TAIL_OUT") or "/tmp/penta-ending-tail"
local TARGET_NAME = os.getenv("ENDING_TAIL_TARGET") or "credits"
local MAX_FRAMES = tonumber(os.getenv("ENDING_TAIL_MAX_FRAMES") or "45000")

local TARGETS = {
    credits = {
        d880 = 0x16, d889 = 0x01, dce2 = 0x00, fff9 = 0x00,
        stable = 240, palette = 1,
    },
    end_page = {
        d880 = 0x16, d889 = 0x01, dce2 = 0x00, fff9 = 0x01,
        stable = 60, palette = 2,
    },
    epilogue_text = {
        d880 = 0x00, d889 = 0x0C, dce2 = 0x01, fff9 = 0x01,
        stable = 180, palette = 3,
    },
}
local TARGET = assert(TARGETS[TARGET_NAME], "unknown ENDING_TAIL_TARGET")
local f, stable, done = 0, 0, false
local injected = false
local TRACE = os.getenv("ENDING_TAIL_TRACE") == "1"
    and io.open(OUT .. ".trace", "w") or nil
local previous_phase = ""

local function trace(message)
    if TRACE then TRACE:write(message .. "\n"); TRACE:flush() end
end

local function visible_attr_layout()
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local target, wrong = 0, 0
    local wrong_by_row = {}
    emu:write8(0xFF4F, 1)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local attr = emu:read8(base + map_y * 32 + map_x)
            if attr == TARGET.palette then
                target = target + 1
            else
                wrong = wrong + 1
                wrong_by_row[row + 1] = (wrong_by_row[row + 1] or 0) + 1
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    local row_parts = {}
    for row = 0, 17 do
        table.insert(
            row_parts,
            string.format("%d:%d", row, wrong_by_row[row + 1] or 0)
        )
    end
    return target, wrong, table.concat(row_parts, ",")
end

local function active_table_is_neutral()
    for offset = 0, 0xFF do
        if emu:read8(0xCC00 + offset) ~= 0 then return false end
    end
    return true
end

local function target_committed()
    return (
        emu:read8(0xD880) == TARGET.d880
        and emu:read8(0xFFC1) == 0
        and emu:read8(0xFFE4) == 1
        and emu:read8(0xD889) == TARGET.d889
        and emu:read8(0xDCE2) == TARGET.dce2
        and emu:read8(0xFFF9) == TARGET.fff9
    )
end

local function attribute_pass_complete()
    local expected_key = (
        0x40 | TARGET.palette | (emu:read8(0xFF40) & 0x08)
    )
    return (
        emu:read8(0xDF49) == expected_key
        and emu:read8(0xDF4A) >= 0x60
    )
end

local function finish(status, message)
    if done then return end
    done = true
    emu:setKeys(0)
    local target, wrong, wrong_rows = visible_attr_layout()
    local table_neutral = active_table_is_neutral()
    local state_saved = false
    if status == "ok" and (
        target ~= 360 or wrong ~= 0 or not table_neutral
    ) then
        status = "error"
        message = "production-layout-mismatch"
    end
    if status == "ok" then
        emu:screenshot(OUT .. ".png")
        local ok, result = pcall(function()
            return emu:saveStateFile(STATE_OUT)
        end)
        state_saved = ok and result ~= false
        if not state_saved then
            status = "error"
            message = "saveStateFile-failed"
        end
    end
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s target=%s frame=%d d880=%02X ffc1=%d ffba=%02X " ..
        "ffe4=%d d889=%02X dce2=%02X fff9=%02X stable=%d " ..
        "dce5=%02X dce6=%02X dce7=%02X dce8=%02X dcea=%02X " ..
        "dcf0=%02X dd07=%02X ff93=%02X " ..
        "df08=%02X df07=%02X df49=%02X df4a=%02X pc=%04X sp=%04X " ..
        "visible_attr_target=%d visible_attr_wrong=%d " ..
        "table_neutral=%s state_saved=%s wrong_rows=%s " ..
        "message=%s\n",
        status, TARGET_NAME, f, emu:read8(0xD880),
        emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFE4),
        emu:read8(0xD889), emu:read8(0xDCE2), emu:read8(0xFFF9),
        stable, emu:read8(0xDCE5), emu:read8(0xDCE6),
        emu:read8(0xDCE7), emu:read8(0xDCE8), emu:read8(0xDCEA),
        emu:read8(0xDCF0), emu:read8(0xDD07), emu:read8(0xFF93),
        emu:read8(0xDF08), emu:read8(0xDF07),
        emu:read8(0xDF49), emu:read8(0xDF4A),
        emu:readRegister("pc"), emu:readRegister("sp"),
        target, wrong, tostring(table_neutral),
        tostring(state_saved), wrong_rows, message
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
    -- A normal cold boot establishes VRAM, CRAM, interrupts, and the DX
    -- handler. Redirect the emulated CPU once; the stock 5513 entry is
    -- balanced (PUSH/POP AF) and ultimately jumps back to the normal reset.
    if f == 600 and not injected then
        local ok, message = pcall(function()
            local saved_ie = emu:read8(0xFFFF)
            emu:write8(0xFFFF, 0)
            emu:write8(0xFFC1, 0)
            emu:write8(0xDD09, 0)
            emu:write8(0xFFBA, 0x08)
            emu:write8(0xFFE4, 0x01)
            emu:write8(0x6000, 0)
            emu:write8(0x4000, 0)
            emu:write8(0x2100, 0x01)
            emu:write8(0xFF99, 0x01)
            emu:writeRegister("sp", 0xDFFF)
            emu:writeRegister("pc", 0x5513)
            emu:write8(0xFFFF, saved_ie)
        end)
        if not ok then
            finish(
                "error",
                "register-injection-" ..
                    tostring(message):gsub("%s+", "-")
            )
            return
        end
        injected = true
    end

    local raw_committed = target_committed()
    local pass_complete = attribute_pass_complete()
    if TRACE then
        local phase = string.format(
            "%02X/%02X/%02X/%02X/%02X/%02X",
            scene, emu:read8(0xDCE5), emu:read8(0xDCE6),
            emu:read8(0xFFF9), emu:read8(0xDF49),
            emu:read8(0xDF4A)
        )
        if phase ~= previous_phase or (raw_committed and f % 10 == 0) then
            local target, wrong = visible_attr_layout()
            trace(string.format(
                "f=%d phase=%s raw=%s pass=%s target=%d wrong=%d pc=%04X",
                f, phase, tostring(raw_committed), tostring(pass_complete),
                target, wrong, emu:readRegister("pc")
            ))
            previous_phase = phase
        end
    end

    -- The ending discriminator becomes visible before the stock page writer
    -- and bounded attribute passes have produced a complete viewport. The
    -- epilogue legitimately alternates its two BG maps while scrolling, so a
    -- single cache key cannot remain at row $60 for the whole stable hold.
    -- Use the rendered production layout itself as the stable invariant.
    local layout_ready = false
    if raw_committed then
        local target, wrong = visible_attr_layout()
        layout_ready = target == 360 and wrong == 0
    end
    local committed = raw_committed and layout_ready
    if committed then
        emu:setKeys(0)
        stable = stable + 1
    elseif injected then
        -- Slowly advance the original wait-for-input pages. Short pulses with
        -- a released gap avoid skipping a newly committed page.
        emu:setKeys((f % 90) < 4 and 0x01 or 0)
        stable = 0
    else
        emu:setKeys(0)
        stable = 0
    end
    if stable == TARGET.stable then
        finish("ok", "saved-colored-release-rom-tail")
    elseif f >= MAX_FRAMES then
        finish("error", "ending-tail-target-timeout")
    end
end)
