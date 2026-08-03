-- Resume the Stage-1 secret/bonus SHMUP in the current ROM and audit its
-- live jet palette, hardware OAM, visible BG attributes, and rendered frames.

local OUT = assert(os.getenv("BONUS_LIVE_OUT"), "BONUS_LIVE_OUT required")
local SHOT_PREFIX = assert(
    os.getenv("BONUS_LIVE_SHOT_PREFIX"), "BONUS_LIVE_SHOT_PREFIX required")
local FRAMES = tonumber(os.getenv("BONUS_LIVE_FRAMES") or "240")
local SETTLE = tonumber(os.getenv("BONUS_LIVE_SETTLE") or "120")

local frame = 0
local main_loop_hits = 0
local tile_copy_hits = 0
local stage_samples = 0
local bad_state_frames = 0
local unsafe_attrs = 0
local sara_oam_checked = 0
local sara_oam_matched = 0
local max_visible_sprites = 0

pcall(function()
    emu:setBreakpoint(function() main_loop_hits = main_loop_hits + 1 end, 0x016C)
    emu:setBreakpoint(function() tile_copy_hits = tile_copy_hits + 1 end, 0x42A7)
end)

local function obj_cram_word(palette, color)
    local index = palette * 8 + color * 2
    emu:write8(0xFF6A, index)
    local low = emu:read8(0xFF6B)
    emu:write8(0xFF6A, index + 1)
    local high = emu:read8(0xFF6B)
    return (high << 8) | low
end

local function bg_cram_word(palette, color)
    local index = palette * 8 + color * 2
    emu:write8(0xFF68, index)
    local low = emu:read8(0xFF69)
    emu:write8(0xFF68, index + 1)
    local high = emu:read8(0xFF69)
    return (high << 8) | low
end

local function visible(y, x)
    return y > 0 and y < 160 and x > 0 and x < 168
end

local function sample_frame()
    if emu:read8(0xFFD0) ~= 0x01 or emu:read8(0xFFC1) ~= 0x01 then
        bad_state_frames = bad_state_frames + 1
        return
    end
    stage_samples = stage_samples + 1

    local expected_sara = (emu:read8(0xFFBE) == 0) and 2 or 1
    local visible_sprites = 0
    for slot = 0, 39 do
        local base = 0xFE00 + slot * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        if visible(y, x) then
            visible_sprites = visible_sprites + 1
            if slot < 4 and emu:read8(base + 2) ~= 0 then
                sara_oam_checked = sara_oam_checked + 1
                if (emu:read8(base + 3) & 0x07) == expected_sara then
                    sara_oam_matched = sara_oam_matched + 1
                end
            end
        end
    end
    if visible_sprites > max_visible_sprites then
        max_visible_sprites = visible_sprites
    end

    local lcdc = emu:read8(0xFF40)
    local map = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local first_column = math.floor(emu:read8(0xFF43) / 8)
    local first_row = math.floor(emu:read8(0xFF42) / 8)
    emu:write8(0xFF4F, 1)
    for row = 0, 18 do
        for column = 0, 20 do
            local address = map
                + ((first_row + row) & 31) * 32
                + ((first_column + column) & 31)
            if (emu:read8(address) & 0xF8) ~= 0 then
                unsafe_attrs = unsafe_attrs + 1
            end
        end
    end
    emu:write8(0xFF4F, 0)
end

local function finish()
    local handle = assert(io.open(OUT, "w"))
    handle:write(string.format("frames=%d\n", frame))
    handle:write(string.format("D880=%02X\n", emu:read8(0xD880)))
    handle:write(string.format("FFC1=%02X\n", emu:read8(0xFFC1)))
    handle:write(string.format("FFBA=%02X\n", emu:read8(0xFFBA)))
    handle:write(string.format("FFBE=%02X\n", emu:read8(0xFFBE)))
    handle:write(string.format("FFD0=%02X\n", emu:read8(0xFFD0)))
    handle:write(string.format("main_loop_hits=%d\n", main_loop_hits))
    handle:write(string.format("tile_copy_hits=%d\n", tile_copy_hits))
    handle:write(string.format("stage_samples=%d\n", stage_samples))
    handle:write(string.format("bad_state_frames=%d\n", bad_state_frames))
    handle:write(string.format("unsafe_attrs=%d\n", unsafe_attrs))
    handle:write(string.format("sara_oam_checked=%d\n", sara_oam_checked))
    handle:write(string.format("sara_oam_matched=%d\n", sara_oam_matched))
    handle:write(string.format("max_visible_sprites=%d\n", max_visible_sprites))
    for palette = 1, 2 do
        handle:write(string.format(
            "objcram=%d,%04X,%04X,%04X,%04X\n",
            palette,
            obj_cram_word(palette, 0), obj_cram_word(palette, 1),
            obj_cram_word(palette, 2), obj_cram_word(palette, 3)))
    end
    handle:write(string.format(
        "bg7=%04X,%04X,%04X,%04X\n",
        bg_cram_word(7, 0), bg_cram_word(7, 1),
        bg_cram_word(7, 2), bg_cram_word(7, 3)))
    handle:close()
    os.exit(0)
end

callbacks:add("frame", function()
    frame = frame + 1
    emu:setKeys(0)

    -- Historical states contain the source ROM's palette/cache image. Force
    -- the current candidate through its normal cold palette initialization.
    if frame <= 40 then
        emu:write8(0xDF02, 0)
        emu:write8(0xDF00, 0)
    end
    if frame == 1 then emu:write8(0xDF0D, 0xFF) end

    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xFF)

    if frame >= SETTLE then sample_frame() end
    if frame == SETTLE or frame == math.floor((SETTLE + FRAMES) / 2)
        or frame == FRAMES then
        emu:screenshot(string.format("%s-%04d.png", SHOT_PREFIX, frame))
    end
    if frame >= FRAMES then finish() end
end)
