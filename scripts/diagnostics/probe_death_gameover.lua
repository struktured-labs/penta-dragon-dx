-- Inventory the stock death/game-over path from a release-ROM boss state.
--
-- The probe loads the requested state itself after its callbacks are attached.
-- Setting the arena HP byte to zero takes the game's original transition into
-- D880=$17; no PC, stack, scene, or rendering state is patched.

local OUT = assert(os.getenv("DEATH_OUT"), "DEATH_OUT is required")
local STATE_FILE = assert(os.getenv("PENTA_STATE_FILE"),
    "PENTA_STATE_FILE is required")
local KILL_FRAME = tonumber(os.getenv("DEATH_KILL_FRAME") or "30")
local MAX_FRAMES = tonumber(os.getenv("DEATH_MAX_FRAMES") or "900")
local TRACE = os.getenv("DEATH_TRACE") == "1"
    and assert(io.open(OUT .. ".trace", "w")) or nil

local frame = 0
local entered = -1
local window_entered = -1
local art_captured = false
local gameover_captured = false
local gameover_palette_ready = -1
local fade_captured = false
local done = false
local art = nil
local window_begin = nil
local gameover = nil
local fade = nil
local fade_entered = -1
local state_loaded = false

local function bg0_hex()
    local old_bcps = emu:read8(0xFF68)
    local bytes = {}
    for index = 0, 7 do
        emu:write8(0xFF68, index)
        bytes[#bytes + 1] = string.format("%02X", emu:read8(0xFF69))
    end
    emu:write8(0xFF68, old_bcps)
    return table.concat(bytes)
end

local function bg_cram_hex()
    local old_bcps = emu:read8(0xFF68)
    local bytes = {}
    for index = 0, 63 do
        emu:write8(0xFF68, index)
        bytes[#bytes + 1] = string.format("%02X", emu:read8(0xFF69))
    end
    emu:write8(0xFF68, old_bcps)
    return table.concat(bytes)
end

local function oam_hex()
    local bytes = {}
    for address = 0xFE00, 0xFE9F do
        bytes[#bytes + 1] = string.format("%02X", emu:read8(address))
    end
    return table.concat(bytes)
end

local function source_c1a0_hex()
    local bytes = {}
    for address = 0xC1A0, 0xC3DF do
        bytes[#bytes + 1] = string.format("%02X", emu:read8(address))
    end
    return table.concat(bytes)
end

local function published_9c00_hex()
    local old_vbk = emu:read8(0xFF4F)
    local bytes = {}
    emu:write8(0xFF4F, 0)
    for row = 0, 23 do
        for column = 0, 23 do
            bytes[#bytes + 1] = string.format(
                "%02X", emu:read8(0x9C00 + row * 32 + column)
            )
        end
    end
    emu:write8(0xFF4F, old_vbk)
    return table.concat(bytes)
end

local function count_region(base, start_row, start_col, rows, columns)
    local old_vbk = emu:read8(0xFF4F)
    local hist = {}
    local nonzero = 0
    local unsafe = 0
    local nonzero_cells = {}
    local tiles = {}
    emu:write8(0xFF4F, 0)
    for row = 0, rows - 1 do
        for column = 0, columns - 1 do
            local address = base
                + (((start_row + row) & 0x1F) * 32)
                + ((start_col + column) & 0x1F)
            tiles[#tiles + 1] = string.format("%02X", emu:read8(address))
        end
    end
    emu:write8(0xFF4F, 1)
    for row = 0, rows - 1 do
        for column = 0, columns - 1 do
            local address = base
                + (((start_row + row) & 0x1F) * 32)
                + ((start_col + column) & 0x1F)
            local attr = emu:read8(address)
            local palette = attr & 0x07
            hist[palette] = (hist[palette] or 0) + 1
            if palette ~= 0 then
                nonzero = nonzero + 1
                nonzero_cells[#nonzero_cells + 1] = string.format(
                    "%02X:%02X:%02X",
                    (start_row + row) & 0x1F,
                    (start_col + column) & 0x1F,
                    attr
                )
            end
            if (attr & 0xF8) ~= 0 then unsafe = unsafe + 1 end
        end
    end
    emu:write8(0xFF4F, old_vbk)
    local parts = {}
    for palette = 0, 7 do
        if hist[palette] then
            parts[#parts + 1] = string.format("%d:%d", palette, hist[palette])
        end
    end
    return nonzero, unsafe, table.concat(parts, ","),
        table.concat(nonzero_cells, ","), table.concat(tiles)
end

local function art_layout()
    local lcdc = emu:read8(0xFF40)
    local base = ((lcdc & 0x08) ~= 0) and 0x9C00 or 0x9800
    local row = (emu:read8(0xFF42) >> 3) & 0x1F
    local column = (emu:read8(0xFF43) >> 3) & 0x1F
    local nonzero, unsafe, hist, cells, tiles =
        count_region(base, row, column, 18, 20)
    local window_base = ((lcdc & 0x40) ~= 0) and 0x9C00 or 0x9800
    local window_nonzero, window_unsafe, window_hist, window_cells,
        window_tiles =
        count_region(window_base, 0, 0, 18, 20)
    return {
        nonzero = nonzero,
        unsafe = unsafe,
        hist = hist,
        cells = cells,
        tiles = tiles,
        window_nonzero = window_nonzero,
        window_unsafe = window_unsafe,
        window_hist = window_hist,
        window_cells = window_cells,
        window_tiles = window_tiles,
        bg_cram = bg_cram_hex(),
        oam = oam_hex(),
        lcdc = lcdc,
        scy = emu:read8(0xFF42),
        scx = emu:read8(0xFF43),
        base = base,
        window_base = window_base,
        source_c1a0 = source_c1a0_hex(),
        published_9c00 = published_9c00_hex(),
    }
end

local function window_layout()
    local lcdc = emu:read8(0xFF40)
    local base = ((lcdc & 0x40) ~= 0) and 0x9C00 or 0x9800
    local nonzero, unsafe, hist, cells, tiles =
        count_region(base, 0, 0, 18, 20)
    return {
        nonzero = nonzero,
        unsafe = unsafe,
        hist = hist,
        cells = cells,
        tiles = tiles,
        lcdc = lcdc,
        base = base,
        bgp = emu:read8(0xFF47),
        bg_cram = bg_cram_hex(),
    }
end

local function finish(status, message)
    if done then return end
    done = true
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s message=%s frames=%d entered=%d window_entered=%d " ..
        "fade_entered=%d d880=%02X ffc1=%02X ffe4=%02X ffba=%02X " ..
        "dcbb=%02X\n",
        status, message, frame, entered, window_entered, fade_entered,
        emu:read8(0xD880), emu:read8(0xFFC1), emu:read8(0xFFE4),
        emu:read8(0xFFBA), emu:read8(0xDCBB)
    ))
    if art then
        report:write(string.format(
            "art_nonzero=%d art_unsafe=%d art_hist=%s " ..
            "art_future_window_nonzero=%d art_future_window_unsafe=%d " ..
            "art_future_window_hist=%s art_lcdc=%02X art_scy=%02X " ..
            "art_scx=%02X art_base=%04X art_window_base=%04X " ..
            "art_cells=%s art_future_window_cells=%s art_tiles=%s " ..
            "art_future_window_tiles=%s art_bg_cram=%s " ..
            "art_oam=%s source_c1a0=%s published_9c00=%s\n",
            art.nonzero, art.unsafe, art.hist,
            art.window_nonzero, art.window_unsafe, art.window_hist,
            art.lcdc, art.scy, art.scx, art.base, art.window_base,
            art.cells, art.window_cells, art.tiles, art.window_tiles,
            art.bg_cram, art.oam, art.source_c1a0, art.published_9c00
        ))
    end
    if gameover then
        report:write(string.format(
            "gameover_nonzero=%d gameover_unsafe=%d gameover_hist=%s " ..
            "gameover_lcdc=%02X gameover_base=%04X gameover_bgp=%02X " ..
            "gameover_cells=%s gameover_tiles=%s gameover_bg_cram=%s\n",
            gameover.nonzero, gameover.unsafe, gameover.hist,
            gameover.lcdc, gameover.base, gameover.bgp,
            gameover.cells, gameover.tiles, gameover.bg_cram
        ))
    end
    if window_begin then
        report:write(string.format(
            "window_begin_nonzero=%d window_begin_unsafe=%d " ..
            "window_begin_hist=%s window_begin_lcdc=%02X " ..
            "window_begin_base=%04X window_begin_bgp=%02X " ..
            "window_begin_cells=%s window_begin_tiles=%s " ..
            "window_begin_bg_cram=%s\n",
            window_begin.nonzero, window_begin.unsafe,
            window_begin.hist, window_begin.lcdc, window_begin.base,
            window_begin.bgp, window_begin.cells, window_begin.tiles,
            window_begin.bg_cram
        ))
    end
    if fade then
        report:write(string.format(
            "fade_bgp=%02X fade_bg_cram=%s\n",
            fade.bgp, fade.bg_cram
        ))
    end
    report:close()
    os.exit(status == "ok" and 0 or 2)
end

callbacks:add("frame", function()
    if done then return end
    if not state_loaded then
        local ok, result = pcall(function()
            return emu:loadStateFile(STATE_FILE)
        end)
        assert(ok and result ~= false, "failed to load requested boss state")
        state_loaded = true
        return
    end
    frame = frame + 1
    emu:setKeys(0)

    if frame == KILL_FRAME then
        emu:write8(0xDCBB, 0)
    end

    local scene = emu:read8(0xD880)
    if scene == 0x17 and entered < 0 then
        entered = frame
    end
    if entered >= 0 then
        local age = frame - entered
        if TRACE then
            local layout = art_layout()
            TRACE:write(string.format(
                "f=%d age=%d cache=%02X phase=%02X palette_phase=%02X " ..
                "sweep=%02X " ..
                "bgp=%02X bg0=%s cram=%s scy=%02X scx=%02X " ..
                "nonzero=%d cells=%s\n",
                frame, age, emu:read8(0xDF0D), emu:read8(0xDF40),
                emu:read8(0xDF4C), emu:read8(0xDF4E),
                emu:read8(0xFF47), bg0_hex(),
                layout.bg_cram,
                layout.scy, layout.scx, layout.nonzero, layout.cells
            ))
            TRACE:flush()
        end
        -- Capture the last fully rendered illustration frame before the
        -- native white fade begins at age 16. Earlier ages can precede the
        -- bounded three-row attribute publisher on legitimate entry cadences.
        if age == 15 and not art_captured then
            art = art_layout()
            emu:screenshot(OUT .. ".art.png")
            art_captured = true
        end
        if emu:read8(0xFF47) == 0 and fade_entered < 0 then
            fade_entered = frame
        end
        if (
            fade_entered >= 0
            and frame - fade_entered >= 9
            and emu:read8(0xFF47) == 0
            and not fade_captured
        ) then
            fade = window_layout()
            emu:screenshot(OUT .. ".fade-white.png")
            fade_captured = true
        end
        if (emu:read8(0xFF40) & 0x20) ~= 0 and window_entered < 0 then
            window_entered = frame
            window_begin = window_layout()
            emu:screenshot(OUT .. ".window-begin.png")
        end
        if (
            window_entered >= 0
            and emu:read8(0xFF47) == 0xE4
            and gameover_palette_ready < 0
        ) then
            gameover_palette_ready = frame
        end
        if (
            gameover_palette_ready >= 0
            and frame - gameover_palette_ready >= 10
            and not gameover_captured
        ) then
            gameover = window_layout()
            emu:screenshot(OUT .. ".gameover.png")
            gameover_captured = true
            finish("ok", "stock-death-gameover-complete")
            return
        end
    end

    if frame >= MAX_FRAMES then
        finish("error", "timeout")
    end
end)
