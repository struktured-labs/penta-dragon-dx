-- Inventory ordinary-gameplay hardware OAM against the exact YAML-compiled
-- tile-to-OBJ LUT used by the release builder.

local OUT = os.getenv("GAMEPLAY_OBJ_OUT")
    or "tmp/penta-gameplay-obj.txt"
local SCREENSHOT = os.getenv("GAMEPLAY_OBJ_SCREENSHOT")
    or "tmp/penta-gameplay-obj.png"
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
local finished,pcs,lut_mismatches=false,{},0
local function game_read(address)
    return emu.memory.wram:read8(address - 0xC000)
end
local function game_write(address, value)
    emu.memory.wram:write8(address - 0xC000, value)
end

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
    if finished then return end
    finished=true
    emu:screenshot(SCREENSHOT)
    local handle = assert(io.open(OUT, "w"))
    handle:write(string.format("frames=%d\n", frame))
    handle:write(string.format("sampled_frames=%d\n", sampled_frames))
    handle:write(string.format("checked=%d\n", checked))
    handle:write(string.format("mismatches=%d\n", mismatches))
    local distinct=0
    for _ in pairs(pcs) do distinct=distinct+1 end
    handle:write(string.format('distinct_pcs=%d\nlut_mismatches=%d\n',distinct,lut_mismatches))
    handle:write(string.format("max_visible=%d\n", max_visible))
    handle:write(string.format("max_slot=%d\n", max_slot))
    handle:write(string.format("bad_state_frames=%d\n", bad_state_frames))
    handle:write(string.format("D880=%02X\n", game_read(0xD880)))
    handle:write(string.format("FFC1=%02X\n", emu:read8(0xFFC1)))
    handle:write(string.format("FFBF=%02X\n", emu:read8(0xFFBF)))
    handle:write(string.format(
        "initial_DF51=%02X\n", initial_oam_sentinel & 0xFF))
    handle:write(string.format(
        "initial_DF4E=%02X\n", initial_bg_repair_count & 0xFF))
    handle:write(string.format("final_DF51=%02X\n", game_read(0xDF51)))
    handle:write(string.format("final_DF4E=%02X\n", game_read(0xDF4E)))
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
    local marker=assert(io.open(assert(os.getenv('GAMEPLAY_OBJ_DONE')),'w'))
    marker:write('complete');marker:close()
end

callbacks:add("frame", function()
    if finished then return end
    frame = frame + 1
    if frame == 1 then
        initial_oam_sentinel = game_read(0xDF51)
        initial_bg_repair_count = game_read(0xDF4E)
    end
    emu:setKeys(0)

    -- Keep old combat anchors alive while their original state settles.
    game_write(0xDCDD, 0x17)
    game_write(0xDCDC, 0xFF)
    game_write(0xDCBB, 0xFF)

    if frame <= SETTLE then return end
    pcs[emu:readRegister('PC')]=true

    local scene = game_read(0xD880)
    local gameplay = emu:read8(0xFFC1)
    local boss = emu:read8(0xFFBF)
    if gameplay ~= 1 or scene < 0x02 or scene >= 0x0C or boss ~= 0 then
        bad_state_frames = bad_state_frames + 1
    else
        for tile=0,255 do
            if game_read(0xD900+tile)~=string.byte(lut,tile+1) then
                lut_mismatches=lut_mismatches+1
            end
        end
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
                                    .. "actual:%d,expected:%d,family:%s,x:%d,y:%d,lut:%02X",
                                frame, slot, tile, actual, expected, family,
                                x, y, game_read(0xD900 + tile)
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
