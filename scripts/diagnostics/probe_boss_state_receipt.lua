-- Reload a generated boss state in a fresh mGBA process and emit a rendered
-- receipt plus exact production table/CRAM bytes.

local OUT = assert(os.getenv("BOSS_RECEIPT_OUT"), "BOSS_RECEIPT_OUT required")
local STATE_OUT = os.getenv("BOSS_RECEIPT_STATE_OUT")
local TARGET = tonumber(os.getenv("BOSS_TARGET") or "0")
local EXPECTED_SCENE = 0x0C + TARGET
local RECEIPT_FRAME = tonumber(os.getenv("BOSS_RECEIPT_FRAMES") or "120")
local REARM_CURRENT_ROM = os.getenv("BOSS_RECEIPT_REARM") ~= "0"
local frame, done, state_saved = 0, false, false

local function hex_range(address, length)
    local result = {}
    for offset = 0, length - 1 do
        result[#result + 1] = string.format(
            "%02X", emu:read8(address + offset)
        )
    end
    return table.concat(result)
end

local function palette_hex()
    local accessor = emu.memory.cgbBgPalette
    local raw
    if accessor then
        raw = accessor:readRange(0, 64)
    else
        local old_index = emu:read8(0xFF68)
        local bytes = {}
        for index = 0, 63 do
            emu:write8(0xFF68, index)
            bytes[#bytes + 1] = string.char(emu:read8(0xFF69))
        end
        emu:write8(0xFF68, old_index)
        raw = table.concat(bytes)
    end
    return (raw:gsub(".", function(char)
        return string.format("%02X", string.byte(char))
    end))
end

local function finish(status, message)
    if done then return end
    done = true
    local report = assert(io.open(OUT .. ".audit.report", "w"))
    report:write(string.format(
        "status=%s target=%d expected_scene=%02X frame=%d d880=%02X " ..
        "ffc1=%d lcdc=%02X bgp=%02X stat=%02X ly=%02X " ..
        "state_saved=%s message=%s " ..
        "active_table=%s bg_cram=%s\n",
        status, TARGET, EXPECTED_SCENE, frame, emu:read8(0xD880),
        emu:read8(0xFFC1), emu:read8(0xFF40), emu:read8(0xFF47),
        emu:read8(0xFF41), emu:read8(0xFF44),
        tostring(state_saved), message,
        hex_range(0xC600, 0x100),
        palette_hex()
    ))
    report:close()
    local marker = assert(io.open(OUT .. ".audit.done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    emu:setKeys(0)
    emu:write8(0xDCBB, 0xF0) -- keep the arena alive for repeatable receipts
    if frame == 1 and REARM_CURRENT_ROM then
        -- Fixture states may carry an older ROM's scene-cache identity and
        -- mutable palette table. Force one normal current-ROM scene transition so the
        -- receipt proves the candidate's own arena table and palettes.
        emu:write8(0xDF0D, 0xFF)
    end
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    if frame > 3 and emu:read8(0xD880) ~= EXPECTED_SCENE then
        finish("error", "arena-left-after-reload")
        return
    end
    if frame == RECEIPT_FRAME then
        emu:screenshot(OUT .. ".png")
        if STATE_OUT then
            local save_ok, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            state_saved = save_ok and result ~= false
            if not state_saved then
                finish("error", "saveStateFile-failed")
                return
            end
        end
        finish("ok", "rendered")
    end
end)
