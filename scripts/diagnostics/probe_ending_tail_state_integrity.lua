-- Validate one generated ending-tail state in a fresh mGBA process.
--
-- No input, memory, stack, ROM, or control-flow injection is performed. The
-- state must resume on the release ROM with its complete tail discriminator
-- and exact visible production attributes intact. $C600 is diagnostic only:
-- stock reuses it as ending-script workspace on credits/END pages.

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
local EXPECTED_CRAM = assert(
    os.getenv("ENDING_TAIL_EXPECTED_CRAM"),
    "ENDING_TAIL_EXPECTED_CRAM required"
)
assert(#EXPECTED_CRAM == 16, "ENDING_TAIL_EXPECTED_CRAM must be 8 bytes")
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

local function visible_render_metrics()
    local lcdc = emu:read8(0xFF40)
    local scy = emu:read8(0xFF42)
    local scx = emu:read8(0xFF43)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local old_vbk = emu:read8(0xFF4F)
    local nonzero_cells, glyph_bytes = 0, 0
    local distinct = {}
    emu:write8(0xFF4F, 0)
    for row = 0, 17 do
        for column = 0, 19 do
            local map_y = ((scy + row * 8) >> 3) & 0x1F
            local map_x = ((scx + column * 8) >> 3) & 0x1F
            local tile = emu:read8(base + map_y * 32 + map_x)
            distinct[tile] = true
            if tile ~= 0 then nonzero_cells = nonzero_cells + 1 end
            local tile_address
            if (lcdc & 0x10) ~= 0 then
                tile_address = 0x8000 + tile * 16
            else
                local signed_tile = tile < 0x80 and tile or tile - 0x100
                tile_address = 0x9000 + signed_tile * 16
            end
            for byte = 0, 15 do
                if emu:read8(tile_address + byte) ~= 0 then
                    glyph_bytes = glyph_bytes + 1
                end
            end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    local distinct_count = 0
    for _tile, _present in pairs(distinct) do
        distinct_count = distinct_count + 1
    end

    local old_index = emu:read8(0xFF68)
    local cram = {}
    for index = 0, 7 do
        emu:write8(0xFF68, TARGET.palette * 8 + index)
        cram[#cram + 1] = string.format("%02X", emu:read8(0xFF69))
    end
    emu:write8(0xFF68, old_index)
    return nonzero_cells, distinct_count, glyph_bytes, table.concat(cram)
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
    local tile_nonzero, tile_distinct, glyph_bytes, cram =
        visible_render_metrics()
    if status == "ok" and (target ~= 360 or wrong ~= 0) then
        status = "error"
        message = "production-layout-mismatch"
    end
    if (
        status == "ok"
        and (tile_nonzero == 0 or tile_distinct < 2 or glyph_bytes == 0)
    ) then
        status = "error"
        message = "blank-visible-render"
    end
    if status == "ok" and cram ~= EXPECTED_CRAM then
        status = "error"
        message = "yaml-cram-mismatch"
    end
    if status == "ok" then emu:screenshot(OUT .. ".png") end
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s target=%s frame=%d d880=%02X ffc1=%d ffba=%02X " ..
        "ffe4=%d d889=%02X dce2=%02X fff9=%02X stable=%d " ..
        "visible_attr_target=%d visible_attr_wrong=%d " ..
        "tile_nonzero=%d tile_distinct=%d glyph_bytes=%d cram=%s " ..
        "table_neutral=%s message=%s\n",
        status, TARGET_NAME, f, emu:read8(0xD880),
        emu:read8(0xFFC1), emu:read8(0xFFBA), emu:read8(0xFFE4),
        emu:read8(0xD889), emu:read8(0xDCE2), emu:read8(0xFFF9),
        stable, target, wrong, tile_nonzero, tile_distinct, glyph_bytes, cram,
        tostring(table_neutral), message
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
