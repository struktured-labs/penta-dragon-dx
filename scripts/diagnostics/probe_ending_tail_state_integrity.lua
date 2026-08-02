-- Validate one generated ending-tail state in a fresh mGBA process.
--
-- No input, memory, stack, ROM, or control-flow injection is performed. The
-- state must resume on the release ROM with its complete tail discriminator,
-- neutral visible attributes, and neutral active table intact.

local OUT = os.getenv("ENDING_TAIL_INTEGRITY_OUT")
    or "/tmp/penta-ending-tail-integrity"
local TARGET_NAME = os.getenv("ENDING_TAIL_TARGET") or "credits"
local TARGETS = {
    credits = {
        d880 = 0x16, d889 = 0x01, dce2 = 0x00, fff9 = 0x00, palette = 1,
    },
    end_page = {
        d880 = 0x16, d889 = 0x01, dce2 = 0x00, fff9 = 0x01, palette = 2,
    },
    epilogue_text = {
        d880 = 0x00, d889 = 0x0C, dce2 = 0x01, fff9 = 0x01, palette = 3,
    },
}
local TARGET = assert(TARGETS[TARGET_NAME], "unknown ENDING_TAIL_TARGET")
local f, stable, done = 0, 0, false

local function visible_attr_layout()
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local target, wrong = 0, 0
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
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return target, wrong
end

local function active_table_is_neutral()
    for offset = 0, 0xFF do
        if emu:read8(0xC600 + offset) ~= 0 then return false end
    end
    return true
end

local function committed()
    return (
        emu:read8(0xD880) == TARGET.d880
        and emu:read8(0xFFC1) == 0
        and emu:read8(0xFFE4) == 1
        and emu:read8(0xD889) == TARGET.d889
        and emu:read8(0xDCE2) == TARGET.dce2
        and emu:read8(0xFFF9) == TARGET.fff9
    )
end

local function finish(status, message)
    if done then return end
    done = true
    local target, wrong = visible_attr_layout()
    local table_neutral = active_table_is_neutral()
    if status == "ok" and (
        target ~= 360 or wrong ~= 0 or not table_neutral
    ) then
        status = "error"
        message = "production-layout-mismatch"
    end
    if status == "ok" then emu:screenshot(OUT .. ".png") end
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s target=%s frame=%d d880=%02X ffc1=%d ffba=%02X " ..
        "ffe4=%d d889=%02X dce2=%02X fff9=%02X stable=%d " ..
        "visible_attr_target=%d visible_attr_wrong=%d " ..
        "table_neutral=%s message=%s\n",
        status, TARGET_NAME, f, emu:read8(0xD880),
        emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFE4),
        emu:read8(0xD889), emu:read8(0xDCE2), emu:read8(0xFFF9),
        stable, target, wrong, tostring(table_neutral), message
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
    if committed() then
        stable = stable + 1
    else
        finish("error", "state-left-expected-ending-tail")
        return
    end
    if stable == 60 then finish("ok", "colored-release-rom-resume") end
end)
