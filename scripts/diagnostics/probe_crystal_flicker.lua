-- Trace Crystal Dragon's native ghost animation without modifying game state.
-- The matching Python verifier owns the emulator lifecycle and single-flight
-- guard; this probe only emits deterministic per-frame evidence.

local OUT = assert(os.getenv("CRYSTAL_FLICKER_OUT"), "CRYSTAL_FLICKER_OUT required")
local FRAMES = tonumber(os.getenv("CRYSTAL_FLICKER_FRAMES") or "1920")
local RELOAD_MATERIAL = (
    os.getenv("CRYSTAL_FLICKER_RELOAD_MATERIAL") == "1"
    or os.getenv("CRYSTAL_FLICKER_RELOAD_OBJ5") == "1"
)
local RELOAD_PHASE = tonumber(os.getenv("CRYSTAL_FLICKER_RELOAD_PHASE") or "")
local RELOAD_WRAM_HELPERS = os.getenv("CRYSTAL_FLICKER_RELOAD_WRAM") == "1"
local SCREENSHOTS = os.getenv("CRYSTAL_FLICKER_SCREENSHOTS") == "1"
local SCREENSHOT_STEP = tonumber(os.getenv("CRYSTAL_FLICKER_SCREENSHOT_STEP") or "60")
local TRACE_STEP = tonumber(os.getenv("CRYSTAL_FLICKER_TRACE_STEP") or "1")
local STATE_OUT = os.getenv("CRYSTAL_FLICKER_STATE_OUT")
local STATE_TRACE = os.getenv("CRYSTAL_FLICKER_STATE_TRACE") == "1"
local COPY_TRACE = os.getenv("CRYSTAL_FLICKER_COPY_TRACE") == "1"
local AFTERIMAGE = os.getenv("CRYSTAL_FLICKER_AFTERIMAGE") or ""
local EXPECTED_SCENE = tonumber(os.getenv("CRYSTAL_FLICKER_EXPECTED_SCENE") or "14")
local frame = 0
local trace = assert(io.open(OUT .. ".trace", "w"))
local finished = false
local last_body = nil
local blank_publishes, afterimage_fills = 0, 0
local boss_released = false
local body_writes = {false, false}
local diagnostic_write = false
local material_reloaded, phase_reloaded, helpers_reloaded = false, false, false

local function hex_range(address, length)
    local bytes = {}
    for offset = 0, length - 1 do
        bytes[#bytes + 1] = string.format("%02X", emu:read8(address + offset))
    end
    return table.concat(bytes)
end

local function register(name)
    local accessors = {
        function() return emu:getRegister(name) end,
        function() return emu:getRegister(string.lower(name)) end,
        function() return emu:readRegister(name) end,
        function() return emu:readRegister(string.lower(name)) end,
    }
    for _, accessor in ipairs(accessors) do
        local ok, value = pcall(accessor)
        if ok and value ~= nil then return value & 0xFFFF end
    end
    return 0xFFFF
end

if COPY_TRACE then
    pcall(function()
        emu:setBreakpoint(function()
            trace:write(string.format(
                "copy frame=%d pc=%04X af=%04X bc=%04X de=%04X hl=%04X " ..
                "ff91=%02X ffba=%02X ffbd=%02X ffbf=%02X " ..
                "df0d=%02X df51=%02X df53_58=%s source=%s\n",
                frame, register("PC"), register("AF"), register("BC"),
                register("DE"), register("HL"), emu:read8(0xFF91),
                emu:read8(0xFFBA), emu:read8(0xFFBD), emu:read8(0xFFBF),
                emu:read8(0xDF0D), emu:read8(0xDF51),
                hex_range(0xDF53, 6), hex_range(0xC1A0, 0x240)
            ))
        end, 0x42A7)
    end)
end

local function palette_hex(accessor, index_register, data_register)
    if accessor then
        local raw = accessor:readRange(0, 64)
        return (raw:gsub(".", function(char)
            return string.format("%02X", string.byte(char))
        end))
    end
    local old_index = emu:read8(index_register)
    local bytes = {}
    for index = 0, 63 do
        emu:write8(index_register, index)
        bytes[#bytes + 1] = string.format("%02X", emu:read8(data_register))
    end
    emu:write8(index_register, old_index)
    return table.concat(bytes)
end

local function shadow_has_body(base)
    for slot = 4, 19 do
        local address = base + slot * 4
        local y, x, tile = emu:read8(address), emu:read8(address + 1),
            emu:read8(address + 2)
        if y >= 16 and y < 160 and x >= 8 and x < 168 and
            tile >= 0x40 and tile <= 0x66 then
            return true
        end
    end
    return false
end

local function capture_body(base)
    local body = {}
    for offset = 16, 79 do
        body[#body + 1] = emu:read8(base + offset)
    end
    return body
end

local function body_max_x(base)
    local maximum = 0
    for slot = 4, 19 do
        local address = base + slot * 4
        local y, x, tile = emu:read8(address), emu:read8(address + 1),
            emu:read8(address + 2)
        if y >= 16 and y < 160 and x >= 8 and x < 168 and
            tile >= 0x40 and tile <= 0x66 and x > maximum then
            maximum = x
        end
    end
    return maximum
end

local function restore_body(base, body)
    diagnostic_write = true
    for index, value in ipairs(body) do
        emu:write8(base + 15 + index, value)
    end
    diagnostic_write = false
end

local function clear_body(base)
    diagnostic_write = true
    for offset = 16, 79 do emu:write8(base + offset, 0) end
    diagnostic_write = false
end

if AFTERIMAGE ~= "" then
    assert(AFTERIMAGE == "half" or AFTERIMAGE == "full",
        "CRYSTAL_FLICKER_AFTERIMAGE must be half or full")
    -- Diagnostic A/B only. FF80 increments FFCB before selecting C000/C100,
    -- so inspect the exact buffer about to be published. Retain the last
    -- complete 4x4 body pose on half (or all) of native blank publishes.
    local function mark_body_write(address, value)
        if not diagnostic_write and value ~= 0 and
            emu:read8(0xD880) == EXPECTED_SCENE then
            body_writes[address < 0xC100 and 1 or 2] = true
        end
    end
    assert(emu:setRangeWatchpoint(function(info)
        mark_body_write(0xC010, info.newValue & 0xFF)
    end, 0xC010, 0xC010, C.WATCHPOINT_TYPE.WRITE) > 0)
    assert(emu:setRangeWatchpoint(function(info)
        mark_body_write(0xC110, info.newValue & 0xFF)
    end, 0xC110, 0xC110, C.WATCHPOINT_TYPE.WRITE) > 0)
    pcall(function()
        emu:setBreakpoint(function()
            if emu:read8(0xD880) ~= EXPECTED_SCENE then return end
            local next_buffer = (emu:read8(0xFFCB) + 1) & 1
            local base = 0xC000 + next_buffer * 0x100
            if body_writes[next_buffer + 1] and shadow_has_body(base) then
                last_body = capture_body(base)
                if body_max_x(base) >= 0x64 then boss_released = true end
            else
                blank_publishes = blank_publishes + 1
                clear_body(base)
                if boss_released and last_body and (
                    AFTERIMAGE == "full" or (blank_publishes & 1) == 1
                ) then
                    restore_body(base, last_body)
                    afterimage_fills = afterimage_fills + 1
                end
            end
            body_writes[next_buffer + 1] = false
        end, 0xFF80)
    end)
end

local function finish(status)
    if finished then return end
    finished = true
    trace:write(string.format("complete status=%s frames=%d\n", status, frame))
    trace:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    emu:setKeys(0)
    -- D000-DFFF is banked. Candidate arena publishers can remain on SVBK2/3
    -- across a frame callback; reading D880 or applying keep-alive writes in
    -- that window corrupts the private attribute plane and invents a scene
    -- exit. Defer every D-range diagnostic write until bank 0/1 is visible.
    local svbk = emu:read8(0xFF70) & 0x07
    local wram_accessible = svbk == 0 or svbk == 1
    local scene = EXPECTED_SCENE
    if wram_accessible then
        scene = emu:read8(0xD880)
        emu:write8(0xDCBB, 0xF0)
        emu:write8(0xDCDC, 0xFF)
        emu:write8(0xDCDD, 0xFF)
        -- Match the established boss-corpus survival policy. Without these
        -- neutralizations some synthetic arena fixtures resolve the fight
        -- before the scene-isolation control can observe a palette.
        emu:write8(0xD888, 0x00)
        emu:write8(0xDD06, 0x00)

        if RELOAD_MATERIAL and not material_reloaded then
            -- Production phases 5..8 own OBJ slots 4..7. This is a diagnostic
            -- re-arm, not a palette write: the ROM's loader does the copy.
            emu:write8(0xDF4C, 0x05)
            material_reloaded = true
        end
        if RELOAD_PHASE and not phase_reloaded then
            emu:write8(0xDF4C, RELOAD_PHASE & 0xFF)
            phase_reloaded = true
        end
        if RELOAD_WRAM_HELPERS and not helpers_reloaded then
            -- Clearing the production sentinel asks the ROM to recopy its
            -- current helper ABI.
            emu:write8(0xDF51, 0x00)
            helpers_reloaded = true
        end
    end

    if scene ~= EXPECTED_SCENE then
        trace:write(string.format("frame=%d scene=%02X\n", frame, scene))
        finish("wrong-scene")
        return
    end

    -- Capture at native 60 Hz. OAM identifies any sprite contribution while
    -- C600 and CRAM prove the BG material chosen for the same rendered frame.
    if frame == 1 or (frame % TRACE_STEP == 0) then
        trace:write(string.format(
            "frame=%d scx=%02X scy=%02X lcdc=%02X bgp=%02X obp0=%02X obp1=%02X " ..
            "ffc1=%02X ffba=%02X ffbf=%02X phase=%02X " ..
            "blank_publishes=%d afterimage_fills=%d released=%d " ..
            "oam=%s bg=%s obj=%s%s\n",
            frame, emu:read8(0xFF43), emu:read8(0xFF42), emu:read8(0xFF40),
            emu:read8(0xFF47), emu:read8(0xFF48), emu:read8(0xFF49),
            emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFBF),
            emu:read8(0xDF4C),
            blank_publishes, afterimage_fills, boss_released and 1 or 0,
            hex_range(0xFE00, 0xA0),
            palette_hex(emu.memory.cgbBgPalette, 0xFF68, 0xFF69),
            palette_hex(emu.memory.cgbObjPalette, 0xFF6A, 0xFF6B),
            STATE_TRACE and (" state=" .. hex_range(0xDC80, 0x380)) or ""
        ))
    end
    if SCREENSHOTS and (frame % SCREENSHOT_STEP == 0) then
        emu:screenshot(OUT .. string.format(".f%04d.png", frame))
    end
    if frame == FRAMES then
        if STATE_OUT then
            local saved, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            if not saved or result == false then finish("state-save-failed") return end
        end
        finish("ok")
    end
end)
