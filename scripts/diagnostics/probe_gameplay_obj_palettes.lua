-- Inventory ordinary-gameplay hardware OAM against the exact YAML-compiled
-- tile-to-OBJ LUT used by the release builder.

local OUT = os.getenv("GAMEPLAY_OBJ_OUT")
    or "/tmp/penta-gameplay-obj.txt"
local SCREENSHOT = os.getenv("GAMEPLAY_OBJ_SCREENSHOT")
    or "/tmp/penta-gameplay-obj.png"
local SETTLE = tonumber(os.getenv("GAMEPLAY_OBJ_SETTLE") or "120")
local SAMPLE_FRAMES = tonumber(os.getenv("GAMEPLAY_OBJ_FRAMES") or "120")
local LUT_PATH = assert(os.getenv("GAMEPLAY_OBJ_LUT"))
local lut_file = assert(io.open(LUT_PATH, "rb"))
local lut = assert(lut_file:read("*a"))
lut_file:close()
assert(#lut == 256)

local frame = 0
local sampled_frames = 0
local checked = 0
local mismatches = 0
local max_visible = 0
local max_slot = -1
local bad_state_frames = 0
local families = {}
local mismatch_rows = {}
local initial_oam_sentinel = -1
local initial_bg_repair_count = -1

local function expected_palette(tile, ffbe)
    if tile == 0 then return nil, "empty-tile" end
    local expected = string.byte(lut, tile + 1)
    if expected == 0xFF then
        return (ffbe == 0) and 2 or 1, "sara"
    end
    return expected, string.format("yaml-%02X", math.floor(tile / 0x10))
end

local function visible(y, x)
    return y > 0 and y < 160 and x > 0 and x < 168
end

local function finish()
    emu:screenshot(SCREENSHOT)
    local handle = assert(io.open(OUT, "w"))
    handle:write(string.format("frames=%d\n", frame))
    handle:write(string.format("sampled_frames=%d\n", sampled_frames))
    handle:write(string.format("checked=%d\n", checked))
    handle:write(string.format("mismatches=%d\n", mismatches))
    handle:write(string.format("max_visible=%d\n", max_visible))
    handle:write(string.format("max_slot=%d\n", max_slot))
    handle:write(string.format("bad_state_frames=%d\n", bad_state_frames))
    handle:write(string.format("D880=%02X\n", emu:read8(0xD880)))
    handle:write(string.format("FFC1=%02X\n", emu:read8(0xFFC1)))
    handle:write(string.format("FFBF=%02X\n", emu:read8(0xFFBF)))
    handle:write(string.format(
        "initial_DF51=%02X\n", initial_oam_sentinel & 0xFF))
    handle:write(string.format(
        "initial_DF4E=%02X\n", initial_bg_repair_count & 0xFF))
    handle:write(string.format("final_DF51=%02X\n", emu:read8(0xDF51)))
    handle:write(string.format("final_DF4E=%02X\n", emu:read8(0xDF4E)))
    handle:write("families=")
    local first = true
    for name, count in pairs(families) do
        if not first then handle:write(",") end
        handle:write(string.format("%s:%d", name, count))
        first = false
    end
    handle:write("\n")
    for _, row in ipairs(mismatch_rows) do
        handle:write(row .. "\n")
    end
    handle:close()
    os.exit(0)
end

callbacks:add("frame", function()
    frame = frame + 1
    if frame == 1 then
        initial_oam_sentinel = emu:read8(0xDF51)
        initial_bg_repair_count = emu:read8(0xDF4E)
    end
    emu:setKeys(0)

    -- Keep old combat anchors alive while their original state settles.
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xFF)

    if frame <= SETTLE then return end

    local scene = emu:read8(0xD880)
    local gameplay = emu:read8(0xFFC1)
    local boss = emu:read8(0xFFBF)
    if gameplay ~= 1 or scene < 0x02 or scene >= 0x0C or boss ~= 0 then
        bad_state_frames = bad_state_frames + 1
    else
        sampled_frames = sampled_frames + 1
        local ffbe = emu:read8(0xFFBE)
        local visible_count = 0
        for slot = 0, 39 do
            local base = 0xFE00 + slot * 4
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            if visible(y, x) then
                visible_count = visible_count + 1
                if slot > max_slot then max_slot = slot end
                local tile = emu:read8(base + 2)
                local actual = emu:read8(base + 3) & 0x07
                local expected, family = expected_palette(tile, ffbe)
                -- Old anchors can preserve intentional or version-specific
                -- Sara/projectile attributes, so gate the stable enemy domain.
                if expected ~= nil and tile >= 0x30 and tile < 0x80 then
                    checked = checked + 1
                    families[family] = (families[family] or 0) + 1
                    if actual ~= expected then
                        mismatches = mismatches + 1
                        if #mismatch_rows < 24 then
                            mismatch_rows[#mismatch_rows + 1] = string.format(
                                "mismatch=frame:%d,slot:%d,tile:%02X,"
                                    .. "actual:%d,expected:%d,family:%s",
                                frame, slot, tile, actual, expected, family
                            )
                        end
                    end
                end
            end
        end
        if visible_count > max_visible then max_visible = visible_count end
    end

    if frame >= SETTLE + SAMPLE_FRAMES then finish() end
end)
