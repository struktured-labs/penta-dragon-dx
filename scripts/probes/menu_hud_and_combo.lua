-- Regression probe for the item-menu window attributes and the retired
-- SELECT+START teleport hotkey. Driven by verify_menu_hud_and_combo.py.
local MODE = os.getenv("PROBE_MODE") or "menu"
local OUT = os.getenv("PROBE_OUT") or "/tmp/penta_menu_hud_and_combo.txt"
local SCREENSHOT = os.getenv("PROBE_SCREENSHOT") or "/tmp/penta_menu_hud_and_combo.png"

local f = 0
local ffba_before = -1
local d880_before = -1
local shadow_states = {}

local function press(lo, hi, mask)
    return (f >= lo and f < hi) and mask or 0
end

local function shadow_checksum()
    local sum = 0
    for address = 0xC000, 0xC09F do
        sum = (sum + emu:read8(address) * (address - 0xBFFF)) & 0xFFFF
    end
    return sum
end

local function write_result(values)
    local out = io.open(OUT, "w")
    for key, value in pairs(values) do
        out:write(string.format("%s=%s\n", key, tostring(value)))
    end
    out:close()
    emu:screenshot(SCREENSHOT)
    os.exit(0)
end

callbacks:add("frame", function()
    f = f + 1
    local keys = 0
    if MODE ~= "title" then
        keys = keys | press(180, 186, 0x80) -- DOWN: GAME START
        keys = keys | press(193, 199, 0x01)
        keys = keys | press(241, 247, 0x01)
        keys = keys | press(291, 297, 0x01)
        keys = keys | press(341, 347, 0x08)
        keys = keys | press(391, 397, 0x01)
    end

    if MODE == "menu" then
        keys = keys | press(1200, 1206, 0x04) -- open item menu
    elseif MODE == "combo" then
        keys = keys | press(1000, 1006, 0x0C) -- exact SELECT+START report
        if f >= 1050 and f < 1290 then
            keys = keys | 0x10                   -- RIGHT
            if f % 4 == 0 then keys = keys | 0x01 end -- animate/fire
        end
    end

    if MODE == "title" and f == 600 then
        local lcdc = emu:read8(0xFF40)
        local bg_map = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
        local contaminated = 0
        emu:write8(0xFF4F, 1)
        for row = 0, 17 do
            for col = 0, 19 do
                if (emu:read8(bg_map + row * 32 + col) & 7) ~= 0 then
                    contaminated = contaminated + 1
                end
            end
        end
        emu:write8(0xFF4F, 0)
        local palette = ""
        for byte_index = 0, 7 do
            emu:write8(0xFF68, byte_index)
            palette = palette .. string.format("%02X", emu:read8(0xFF69))
        end
        write_result({
            reached = f,
            d880 = string.format("%02X", emu:read8(0xD880)),
            lcdc = string.format("%02X", lcdc),
            bg_map = string.format("%04X", bg_map),
            contaminated_cells = contaminated,
            palette0 = palette,
        })
    end
    emu:setKeys(keys)

    if emu:read8(0xFFC1) == 1 then
        emu:write8(0xDCDD, 0x17)
        emu:write8(0xDCDC, 0xFF)
        emu:write8(0xDCBB, 0xFF)
    end

    if f == 990 then
        ffba_before = emu:read8(0xFFBA)
        d880_before = emu:read8(0xD880)
    end

    if MODE == "combo" and f >= 1050 and f <= 1290 and f % 10 == 0 then
        shadow_states[shadow_checksum()] = true
    end

    if MODE == "menu" and f == 1245 then
        local lcdc = emu:read8(0xFF40)
        local window_map = ((lcdc & 0x40) ~= 0) and 0x9C00 or 0x9800
        local contaminated = 0
        local visible_cells = 0
        emu:write8(0xFF4F, 1)
        -- Rows 0, 4, and 5 contain the separator/MEDICAL and both HP rows.
        for _, row in ipairs({0, 4, 5}) do
            for col = 0, 19 do
                visible_cells = visible_cells + 1
                if (emu:read8(window_map + row * 32 + col) & 7) ~= 0 then
                    contaminated = contaminated + 1
                end
            end
        end
        emu:write8(0xFF4F, 0)
        write_result({
            reached = f,
            lcdc = string.format("%02X", lcdc),
            window_enabled = ((lcdc & 0x20) ~= 0) and 1 or 0,
            window_map = string.format("%04X", window_map),
            checked_cells = visible_cells,
            contaminated_cells = contaminated,
        })
    end

    if MODE == "combo" and f == 1300 then
        local state_count = 0
        for _ in pairs(shadow_states) do state_count = state_count + 1 end
        write_result({
            reached = f,
            ffba_before = string.format("%02X", ffba_before),
            ffba_after = string.format("%02X", emu:read8(0xFFBA)),
            d880_before = string.format("%02X", d880_before),
            d880_after = string.format("%02X", emu:read8(0xD880)),
            ffc1 = string.format("%02X", emu:read8(0xFFC1)),
            lcdc = string.format("%02X", emu:read8(0xFF40)),
            shadow_states = state_count,
        })
    end
end)
