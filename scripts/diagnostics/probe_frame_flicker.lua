-- Consecutive-frame pixel/CRAM/OAM capture for palette-flicker diagnosis.
--
-- FLICKER_MODE=demo leaves the title idle until the stock D880=$0A demo.
-- FLICKER_MODE=gameplay enters Stage 1 through normal controller input.
-- The Python wrapper terminates mGBA after the .done marker is written; do not
-- call emu:stop() here because that can freeze this mGBA build.

local OUT = assert(os.getenv("FLICKER_OUT"), "FLICKER_OUT is required")
local MODE = os.getenv("FLICKER_MODE") or "demo"
local SAMPLE_FRAMES = tonumber(os.getenv("FLICKER_SAMPLE_FRAMES") or "300")
local MAX_FRAMES = tonumber(os.getenv("FLICKER_MAX_FRAMES") or "16000")

local KEY_A, KEY_START, KEY_DOWN = 0x01, 0x08, 0x80
local frame, target_frame, samples = 0, nil, 0
local done = false
local previous_scene = -1
local demo_delay_hits = 0

pcall(function()
    emu:setBreakpoint(function()
        demo_delay_hits = demo_delay_hits + 1
    end, 0x10E7)
end)

local function scheduled_keys()
    if MODE ~= "gameplay" then return 0 end
    local schedule = {
        {180, 185, KEY_DOWN},
        {201, 206, KEY_A},
        {261, 266, KEY_A},
        {321, 326, KEY_A},
        {381, 386, KEY_START},
        {431, 436, KEY_A},
    }
    for _, row in ipairs(schedule) do
        if frame >= row[1] and frame <= row[2] then return row[3] end
    end
    if target_frame and frame - target_frame > 30 then
        -- Exercise scrolling and firing so gameplay uses more than Sara's
        -- standing sprite palettes.
        return 0x10 | (((frame - target_frame) % 60 < 6) and KEY_A or 0)
    end
    return 0
end

local function target_active()
    local scene = emu:read8(0xD880)
    local gameplay = emu:read8(0xFFC1)
    if MODE == "demo" then
        return scene == 0x0A
    end
    return scene == 0x02 and gameplay == 1
end

local function palette_bytes(accessor_name, index_port, data_port)
    local accessor = emu.memory[accessor_name]
    if accessor then return accessor:readRange(0, 64) end

    local old_index = emu:read8(index_port)
    local result = {}
    for index = 0, 63 do
        emu:write8(index_port, index)
        result[#result + 1] = string.char(emu:read8(data_port))
    end
    emu:write8(index_port, old_index)
    return table.concat(result)
end

local function hex_bytes(raw)
    return (raw:gsub(".", function(char)
        return string.format("%02X", string.byte(char))
    end))
end

local function visible_oam()
    local result = {}
    for slot = 0, 39 do
        local base = 0xFE00 + slot * 4
        local y = emu:read8(base)
        local x = emu:read8(base + 1)
        if y > 0 and y < 160 and x > 0 and x < 168 then
            result[#result + 1] = string.format(
                "%d:%d:%d:%02X:%02X",
                slot, y, x, emu:read8(base + 2), emu:read8(base + 3)
            )
        end
    end
    return table.concat(result, ",")
end

local previous_bg_maps = {[0x9800] = {}, [0x9C00] = {}}

local function visible_bg_mismatches()
    local lcdc = emu:read8(0xFF40)
    local scy, scx = emu:read8(0xFF42), emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local tiles, attrs = {}, {}
    local mismatches, blank, examples = 0, 0, {}
    local attr_only, tile_only, transition_examples = 0, 0, {}
    local active_slots = {}
    local previous = previous_bg_maps[base]

    emu:write8(0xFF4F, 0)
    for row = 0, 18 do
        for column = 0, 20 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local index = map_y * 32 + map_x
            local tile = emu:read8(base + index)
            tiles[index] = tile
            if tile == 0 then blank = blank + 1 end
        end
    end
    emu:write8(0xFF4F, 1)
    for row = 0, 18 do
        for column = 0, 20 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local index = map_y * 32 + map_x
            local tile = tiles[index]
            local actual = emu:read8(base + index) & 0x07
            attrs[index] = actual
            active_slots[actual] = true
            local expected = emu:read8(0xCC00 + tile) & 0x07
            if actual ~= expected then
                mismatches = mismatches + 1
                if #examples < 12 then
                    examples[#examples + 1] = string.format(
                        "%d:%d:%02X:%d:%d",
                        column, row, tile, actual, expected
                    )
                end
            end
            local old = previous[index]
            if old then
                if old.tile == tile and old.attr ~= actual then
                    attr_only = attr_only + 1
                    if #transition_examples < 12 then
                        transition_examples[#transition_examples + 1] =
                            string.format(
                                "A:%03X:%02X:%d:%d",
                                index, tile, old.attr, actual
                            )
                    end
                elseif old.tile ~= tile and old.attr == actual then
                    tile_only = tile_only + 1
                    if #transition_examples < 12 then
                        transition_examples[#transition_examples + 1] =
                            string.format(
                                "T:%03X:%02X:%02X:%d",
                                index, old.tile, tile, actual
                            )
                    end
                end
            end
            previous[index] = {tile = tile, attr = actual}
        end
    end
    emu:write8(0xFF4F, old_vbk)
    local slot_list = {}
    for slot = 0, 7 do
        if active_slots[slot] then slot_list[#slot_list + 1] = tostring(slot) end
    end
    return mismatches, blank, attr_only, tile_only,
        table.concat(examples, ","), table.concat(transition_examples, ","),
        table.concat(slot_list, ",")
end

local function finish(status)
    if done then return end
    done = true
    local hits = assert(io.open(OUT .. ".delay_hits", "w"))
    hits:write(string.format("%d\n", demo_delay_hits))
    hits:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

local trace = assert(io.open(OUT .. ".tsv", "w"))
trace:write(
    "sample\tframe\td880\tffc1\tffba\tffbe\tffbf\tdf4c\tlcdc\tstat" ..
    "\tbgp" ..
    "\tbg_mismatch\tblank_bg\tattr_only_flips\ttile_only_changes" ..
    "\tbg_examples\tbg_transition_examples\tvisible_bg_slots" ..
    "\tobj_cram\tbg_cram\tvisible_oam\n"
)
trace:close()
local timeline = assert(io.open(OUT .. ".timeline.tsv", "w"))
timeline:write(
    "frame\td880\tffc1\tdcfd\tdd09\tsentinel\tdc00\tscx\tlcdc\tbgp\tly\n"
)
timeline:close()

callbacks:add("frame", function()
    if done then return end
    frame = frame + 1
    emu:setKeys(scheduled_keys())

    local scene = emu:read8(0xD880)
    if scene ~= previous_scene then
        local handle = assert(io.open(OUT .. ".timeline.tsv", "a"))
        handle:write(string.format(
            "%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
            frame,
            scene,
            emu:read8(0xFFC1),
            emu:read8(0xDCFD),
            emu:read8(0xDD09),
            emu:read8(0xDF51),
            emu:read8(0xDC00),
            emu:read8(0xFF43),
            emu:read8(0xFF40),
            emu:read8(0xFF47),
            emu:read8(0xFF44)
        ))
        handle:close()
        previous_scene = scene
    end

    if not target_frame and target_active() then target_frame = frame end
    if target_frame then
        samples = samples + 1
        local obj = palette_bytes("cgbObjPalette", 0xFF6A, 0xFF6B)
        local bg = palette_bytes("cgbBgPalette", 0xFF68, 0xFF69)
        local bg_mismatch, blank_bg, attr_only, tile_only,
            bg_examples, bg_transition_examples,
            visible_bg_slots = visible_bg_mismatches()
        local handle = assert(io.open(OUT .. ".tsv", "a"))
        handle:write(string.format(
            "%d\t%d\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X" ..
            "\t%02X\t%d\t%d\t%d\t%d\t%s\t%s\t%s\t%s\t%s\t%s\n",
            samples, frame,
            emu:read8(0xD880), emu:read8(0xFFC1),
            emu:read8(0xFFBA), emu:read8(0xFFBE), emu:read8(0xFFBF),
            emu:read8(0xDF4C), emu:read8(0xFF40), emu:read8(0xFF41),
            emu:read8(0xFF47),
            bg_mismatch, blank_bg, attr_only, tile_only,
            bg_examples, bg_transition_examples,
            visible_bg_slots, hex_bytes(obj), hex_bytes(bg), visible_oam()
        ))
        handle:close()
        emu:screenshot(string.format("%s.frame%04d.png", OUT, samples))
        if samples >= SAMPLE_FRAMES then finish("ok") end
    end
    if frame >= MAX_FRAMES and not target_frame then finish("target-timeout") end
end)
