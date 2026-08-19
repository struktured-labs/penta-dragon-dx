-- Capture one mGBA boss-arena state after native diagnostic entry.
--
-- generate_stream_boss_states.py starts from a real Stage 1 gameplay state.
-- Its throwaway ROM copy enters the game's original boss routine at 0x1A2B;
-- the release ROM is never patched or shipped with navigation code. This Lua
-- side observes the transition, keeps Sara alive, and captures the arena.
--
-- Environment:
--   BOSS_TARGET     0..8 (Shalamar through Penta Dragon)
--   BOSS_STATE_OUT  output .ss0 path
--   BOSS_OUT        output prefix for .report/.png
--   BOSS_STABLE_FRAMES frames to render after the arena appears (default 240)

local TARGET = tonumber(os.getenv("BOSS_TARGET") or "0")
local STATE_OUT = assert(os.getenv("BOSS_STATE_OUT"), "BOSS_STATE_OUT required")
local OUT = os.getenv("BOSS_OUT") or "tmp/penta-stream-boss"
local STABLE_TARGET = tonumber(os.getenv("BOSS_STABLE_FRAMES") or "240")
local ENTRY_TIMEOUT = tonumber(os.getenv("BOSS_ENTRY_TIMEOUT") or "1200")
local OBJ_EXPECTED = os.getenv("BOSS_OBJ_EXPECTED") or ""
local STOCK_ROM = os.getenv("BOSS_STOCK_ROM") == "1"
local WRITER_MIRROR = os.getenv("BOSS_WRITER_MIRROR") == "1"
local FORCE_TED_FALLBACK = os.getenv("BOSS_FORCE_TED_FALLBACK") == "1"
local PUBLISH_STATE_OUT = os.getenv("BOSS_PUBLISH_STATE_OUT")
local GDMA_TEST_PATTERN = os.getenv("BOSS_GDMA_TEST_PATTERN") == "1"
local GDMA_LCD_OFF = os.getenv("BOSS_GDMA_LCD_OFF") == "1"
local HDMA_PIGGY_TRACE = os.getenv("BOSS_HDMA_PIGGY_TRACE") == "1"
local TED_INWINDOW_SANITIZER = os.getenv("BOSS_TED_INWINDOW_SANITIZER") == "1"
local TROOP_BUILDER_TRACE = os.getenv("BOSS_TROOP_BUILDER_TRACE") == "1"
local NATIVE_LAYOUT_TRACE = os.getenv("BOSS_NATIVE_LAYOUT_TRACE") == "1"
local COPY_ROUTE_TRACE = os.getenv("BOSS_COPY_ROUTE_TRACE") == "1"
local EXPECTED_SCENE = 0x0C + TARGET
local f, reached, stable, palette_settled, settle_frame, done = 0, false, 0, 0, 0, false
-- Ted's scene byte becomes visible roughly a minute before the synthetic
-- dispatcher has actually armed his moving source writer. Saving during that
-- pre-roll produced static fixtures and false determinism/performance passes.
local ted_activated = TARGET ~= 4
local last_tick, stagnant_ticks = nil, 0
local incremental_install_sp = nil
local pending_publish = nil
local attr_watch_installed = false
local publish_state_saved = false
local gdma_saved_lcdc = nil
local piggy_snapshot = nil
local trace = assert(io.open(OUT .. ".trace", "w"))

-- Lua is attached after the navigation savestate is loaded but before its
-- first resumed frame. Rehydrate version-local boot WRAM here; doing it from
-- the frame callback is too late because the resumed CPU can publish a map
-- before that callback fires.
if not STOCK_ROM then
    emu:write8(0xC5FF, 0x00)
    emu:write8(0xFFA7, 0x00)
    emu:write8(0xFFA8, 0x00)
    emu:write8(0xFFA9, 0x00)
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

if (TARGET == 5 and TROOP_BUILDER_TRACE) or NATIVE_LAYOUT_TRACE then
    local trace_tag = NATIVE_LAYOUT_TRACE and "native-layout" or "troop-builder"
    pcall(function()
        emu:setRangeWatchpoint(function(info)
            trace:write(string.format(
                "%s-source-write target=%d frame=%d pc=%04X bank=%02X " ..
                "old=%02X new=%02X\n",
                trace_tag, TARGET, f, register("PC"), emu:read8(0xFF99),
                (info.oldValue or 0) & 0xFF,
                (info.newValue or info.value or 0) & 0xFF))
            trace:flush()
        end, 0xC349, 0xC349, C.WATCHPOINT_TYPE.WRITE)
    end)
    for _, site in ipairs({0x30DD, 0x3111, 0x3132}) do
        pcall(function()
            emu:setBreakpoint(function()
                trace:write(string.format(
                    "%s target=%d frame=%d pc=%04X bank=%02X af=%04X " ..
                    "bc=%04X de=%04X hl=%04X c349=%02X\n",
                    trace_tag, TARGET, f, register("PC"),
                    emu:read8(0xFF99), register("AF"),
                    register("BC"), register("DE"), register("HL"),
                    emu:read8(0xC349)))
                trace:flush()
            end, site)
        end)
    end
end

if COPY_ROUTE_TRACE then
    local sites = {
        {"vblank-vector", 0x0040}, {"timer-vector", 0x0050},
        {"timer-handler", 0x06B3}, {"vblank-handler", 0x06D1},
        {"vblank-hook", 0x0824}, {"vblank-hook-return", 0x0831},
        {"vblank-exit", 0x0818}, {"vblank-reti", 0x081D},
        {"mapper-entry", 0x0061}, {"mapper-store", 0x09BE},
        {"mapper-write", 0x09C0},
        {"wrapper-entry", 0x6F1D}, {"wrapper-exit", 0x6F8B},
        {"service-death", 0x7100}, {"service-title", 0x6A60},
        {"service-palette", 0x6C90}, {"service-prelude", 0x6E80},
        {"service-entry-patch", 0x6A33}, {"service-colorizer", 0x6E00},
        {"service-glyph", 0x6DA7}, {"service-hazard", 0x6A0E},
        {"fixed-decider", 0x0842}, {"map-call", 0x0847},
        {"banked-call", 0x084A}, {"map-restore", 0x084D},
        {"copy-entry", 0x42A7}, {"atomic-start", 0x42B2},
        {"copy-42D3", 0x42D3}, {"copy-42F1", 0x42F1},
        {"copy-42F7", 0x42F7}, {"copy-4328", 0x4328},
        {"pure-start", 0x432E}, {"pure-tail", 0x4358},
        {"copy-end", 0x436D}, {"atomic-call", 0x3497},
        {"atomic-return", 0x349A}, {"atomic-reti", 0x34A2},
        {"banked-copy-entry", 0x6C80},
    }
    for _, item in ipairs(sites) do
        pcall(function()
            emu:setBreakpoint(function()
                local sp = register("SP")
                local stack = {}
                for offset = 0, 15 do
                    stack[#stack + 1] = string.format(
                        "%02X", emu:read8((sp + offset) & 0xFFFF))
                end
                trace:write(string.format(
                    "copy-route target=%d frame=%d site=%s pc=%04X sp=%04X " ..
                    "bank=%02X svbk=%02X ie=%02X af=%04X bc=%04X de=%04X " ..
                    "hl=%04X dc0b=%02X ffe0=%02X stack=%s\n",
                    TARGET, f, item[1], register("PC"), sp,
                    emu:read8(0xFF99), emu:read8(0xFF70),
                    emu:read8(0xFFFF), register("AF"), register("BC"),
                    register("DE"), register("HL"), emu:read8(0xDC0B),
                    emu:read8(0xFFE0), table.concat(stack)))
                trace:flush()
            end, item[2])
        end)
    end
end

if TARGET == 4 and os.getenv("TED_NATIVE_POSE_TRACE") == "1" then
    local function pose_log(tag)
        if emu:read8(0xFFA7) ~= 0x11 then return end
        trace:write(string.format(
            "native-pose tag=%s frame=%d pc=%04X sp=%04X bc=%04X de=%04X hl=%04X " ..
            "svbk=%02X ff91=%02X count=%02X\n",
            tag, f, register("PC"), register("SP"), register("BC"),
            register("DE"), register("HL"), emu:read8(0xFF70),
            emu:read8(0xFF91), emu:read8(0xD71F)))
        trace:flush()
    end
    emu:setBreakpoint(function() pose_log("render") end, 0x434E)
    emu:setBreakpoint(function() pose_log("finish") end, 0x4364)
    emu:setBreakpoint(function() pose_log("overlay") end, 0x436D)
    emu:setBreakpoint(function() pose_log("root") end, 0x4004)
end

local function route_hex(address, length)
    local result = {}
    for offset = 0, length - 1 do
        result[#result + 1] = string.format("%02X", emu:read8(address + offset))
    end
    return table.concat(result)
end

local function ted_pose_marker()
    local old = emu:read8(0xFF70)
    emu:write8(0xFF70, 0x02)
    local marker = emu:read8(0xD709)
    emu:write8(0xFF70, old & 0x07)
    return marker
end

local function ted_pose_markers()
    local old = emu:read8(0xFF70)
    local values = {}
    for bank = 1, 7 do
        emu:write8(0xFF70, bank)
        values[#values + 1] = string.format("%02X", emu:read8(0xD709))
    end
    emu:write8(0xFF70, old & 0x07)
    return table.concat(values)
end

if TARGET == 4 and os.getenv("BOSS_ROUTE_TRACE") == "1" then
    emu:setRangeWatchpoint(function(info)
        local watch_pc = register("PC")
        local piggy_tile_start = watch_pc == 0x6244
            and (emu:read8(0xFF4F) & 1) == 0
        local piggy_attr_only_start = watch_pc == 0x6248
            and (emu:read8(0xFF4F) & 1) == 1
        if HDMA_PIGGY_TRACE
                and (piggy_tile_start or piggy_attr_only_start) then
            local source_bank = emu:read8(0xFF70) & 7
            local target = 0x8000 | ((emu:read8(0xFF53) & 0x1F) << 8)
            local attrs, tiles = {}, {}
            local old_svbk = emu:read8(0xFF70)
            emu:write8(0xFF70, source_bank)
            for row = 0, 23 do
                for col = 0, 23 do
                    local offset = row * 32 + col
                    attrs[#attrs + 1] = emu:read8(0xD000 + offset)
                    tiles[#tiles + 1] = piggy_attr_only_start
                        and emu:read8(0xC1A0 + row * 24 + col)
                        or emu:read8(0xD900 + offset)
                end
            end
            emu:write8(0xFF70, old_svbk & 7)
            piggy_snapshot = {
                bank = source_bank, target = target,
                attrs = attrs, tiles = tiles,
                attr_only = piggy_attr_only_start,
            }
        end
        trace:write(string.format(
            "gdma_write frame=%d pc=%04X rom=%02X value=%02X " ..
            "svbk=%02X vbk=%02X hdma=%02X%02X%02X%02X\n",
            f, watch_pc, emu:read8(0xFF99),
            (info.newValue or info.value or 0) & 0xFF,
            emu:read8(0xFF70), emu:read8(0xFF4F),
            emu:read8(0xFF51), emu:read8(0xFF52),
            emu:read8(0xFF53), emu:read8(0xFF54)))
        trace:flush()
    end, 0xFF55, 0xFF56, C.WATCHPOINT_TYPE.WRITE)
    local route_items = {
        {"caller", 0x028A}, {"toggle", 0x4295}, {"wrapper", 0xDB80},
        {"native", 0x42A7},
        {"bank2-call", 0x40EF}, {"bank2-return", 0x40F2},
        {"bank2-gate", 0x7A8C}, {"bank2-ready", 0x7ABB},
        {"single-a-site", 0x61DF}, {"single-a-helper", 0xC516},
        {"single-a-resume", 0x61E2},
        {"single-b-site", 0x6219}, {"single-b-helper", 0xC520},
        {"single-b-return", 0xC525}, {"single-common", 0xC527},
        {"clone-entry", 0xD400}, {"tracker-entry", 0xD300},
        {"tracker-tail", 0xD350},
        {"install-entry", 0x5340}, {"install-copy2", 0x5940},
        {"install-copy3", 0x5970}, {"install-copy4", 0x5460},
        {"install-tail", 0x5CDA}, {"install-final", 0x6FFF},
        {"incremental-init", 0xD360},
        {"compiler-front", 0x578C}, {"compiler-select", 0x5830},
        {"compiler-miss", 0x5D7F}, {"compiler-row", 0x5DFC},
        {"compiler-publish", 0x5E2C}, {"gdma-start", 0x5899},
        {"compiler-wait", 0x5E5C}, {"compiler-exit", 0x5E62},
        {"compiler-finish", 0x6250}, {"publish-attr", 0x55D8},
        {"publish-attr-tail", 0x61B0}, {"runtime", 0xC4FC},
        {"writer-hook", 0x3136}, {"writer-runtime", 0xC500},
        {"writer-mask-read", 0xC533},
        {"clear-hook", 0x4422}, {"clear-gate", 0x6FE4},
        {"clear-runtime", 0xC594}, {"writer-overrun", 0xC633},
    }
    if HDMA_PIGGY_TRACE then
        route_items = {
            {"caller", 0x028A}, {"cold-ready-gate", 0xDB80},
            {"native-postcopy", 0xDB91}, {"toggle", 0x4295},
            {"native-copy", 0x42A7}, {"lazy-gate", 0x6290},
            {"install-entry", 0x5340}, {"install-final", 0x6FFF},
            {"fixed-entry", 0x0838},
            {"tracker-entry", 0xD300}, {"tracker-tail", 0xD357},
            {"piggy-select", 0x5830}, {"piggy-setup-a", 0x5860},
            {"piggy-setup-b", 0x623C}, {"piggy-setup-c", 0x6530},
            -- The wrapper tail-jumps through the mapper at $0846.  Observe
            -- immediately before that jump, after CP has restored native AF.
            {"fixed-exit", 0x0846},
        }
    end
    for _, item in ipairs(route_items) do
        pcall(function() return emu:setBreakpoint(function()
            local sp = register("SP")
            if item[1] == "bank2-gate" and FORCE_TED_FALLBACK then
                emu:write8(0xC5FF, 0x00)
            end
            if item[1] == "gdma-start" and GDMA_TEST_PATTERN and f >= 190 then
                for offset = 0, 0x2FF do
                    emu:write8(0xD000 + offset, (offset // 16) & 0x07)
                end
            end
            if item[1] == "gdma-start" and GDMA_LCD_OFF and f >= 190 then
                gdma_saved_lcdc = emu:read8(0xFF40)
                emu:write8(0xFF40, gdma_saved_lcdc & 0x7F)
            end
            if item[1] == "install-entry" then incremental_install_sp = sp end
            local stack_ok = "na"
            if incremental_install_sp ~= nil then
                if item[1] == "install-final" then
                    stack_ok = sp == ((incremental_install_sp - 6) & 0xFFFF)
                        and "yes" or "no"
                elseif item[1] == "compiler-front" then
                    stack_ok = sp == incremental_install_sp and "yes" or "no"
                end
            end
            trace:write(string.format(
                "route frame=%d site=%s pc=%04X sp=%04X svbk=%02X rom=%02X " ..
                "sentinel=%02X replay=%02X selector=%02X ie=%02X " ..
                "af=%04X bc=%04X hl=%04X de=%04X " ..
                "stack_ok=%s runtime=%s mid=%s ff55=%02X ly=%02X " ..
                "stat=%02X lcdc=%02X\n",
                f, item[1], register("PC"), sp,
                emu:read8(0xFF70), emu:read8(0xFF99),
                emu:read8(0xC5FF), emu:read8(0xC5FE),
                emu:read8(0xDC0B), emu:read8(0xFFFF),
                register("AF"), register("BC"),
                register("HL"), register("DE"),
                stack_ok, route_hex(0xC500, 20), route_hex(0xD300, 48),
                emu:read8(0xFF55), emu:read8(0xFF44),
                emu:read8(0xFF41), emu:read8(0xFF40)))
            if item[1] == "fixed-exit" then
                local target = (register("HL") - 0x0300) & 0xFFFF
                local old_svbk = emu:read8(0xFF70)
                local old_vbk = emu:read8(0xFF4F)
                local source_bank = target == 0x9800 and 4 or 5
                local attr_bad, tile_bad = 0, 0
                local attr_cpu_bad = 0
                local attr_plane_bad, tile_plane_bad = 0, 0
                local source_changed, snapshot_tile_bad = 0, 0
                local snapshot_attr_cpu_bad = 0
                local first_attr, first_tile = "none", "none"
                emu:write8(0xFF70, source_bank)
                for row = 0, 23 do
                    for col = 0, 23 do
                        local offset = row * 32 + col
                        local attr_source = emu:read8(
                            0xD000 + row * 32 + col)
                        local tile_source = emu:read8(
                            0xD900 + row * 32 + col)
                        local packed_tile = emu:read8(
                            0xC1A0 + row * 24 + col)
                        local expected_attr = emu:read8(
                            0xC600 + packed_tile)
                        local packed_index = row * 24 + col + 1
                        local snapshot_attr = piggy_snapshot
                            and piggy_snapshot.attrs[packed_index]
                            or attr_source
                        local snapshot_tile = piggy_snapshot
                            and piggy_snapshot.tiles[packed_index]
                            or tile_source
                        -- mGBA's raw VRAM domain lays bank 1 after bank 0;
                        -- unlike CPU-mapped reads it remains observable in
                        -- active PPU modes.
                        local attr_actual = emu.memory.vram:read8(
                            0x2000 + target - 0x8000 + offset)
                        local tile_actual = emu.memory.vram:read8(
                            target - 0x8000 + offset)
                        emu:write8(0xFF4F, 1)
                        local attr_cpu = emu:read8(target + offset)
                        emu:write8(0xFF4F, 0)
                        if attr_source ~= expected_attr then
                            attr_plane_bad = attr_plane_bad + 1
                        end
                        if tile_source ~= packed_tile then
                            tile_plane_bad = tile_plane_bad + 1
                        end
                        if attr_source ~= attr_cpu then
                            attr_cpu_bad = attr_cpu_bad + 1
                        end
                        local current_snapshot_tile = piggy_snapshot
                            and piggy_snapshot.attr_only
                            and packed_tile or tile_source
                        if attr_source ~= snapshot_attr
                                or current_snapshot_tile ~= snapshot_tile then
                            source_changed = source_changed + 1
                        end
                        if snapshot_tile ~= tile_actual then
                            snapshot_tile_bad = snapshot_tile_bad + 1
                        end
                        if snapshot_attr ~= attr_cpu then
                            snapshot_attr_cpu_bad = snapshot_attr_cpu_bad + 1
                        end
                        if attr_source ~= attr_actual then
                            attr_bad = attr_bad + 1
                            if first_attr == "none" then
                                first_attr = string.format(
                                    "%d,%d,%02X,%02X",
                                    row, col, attr_source, attr_actual)
                            end
                        end
                        if tile_source ~= tile_actual then
                            tile_bad = tile_bad + 1
                            if first_tile == "none" then
                                first_tile = string.format(
                                    "%d,%d,%02X,%02X",
                                    row, col, tile_source, tile_actual)
                            end
                        end
                    end
                end
                emu:write8(0xFF4F, old_vbk & 1)
                emu:write8(0xFF70, old_svbk & 7)
                trace:write(string.format(
                    "piggy_exit frame=%d target=%04X source_bank=%d attr_bad=%d " ..
                    "tile_bad=%d attr_cpu_bad=%d attr_plane_bad=%d " ..
                    "tile_plane_bad=%d source_changed=%d " ..
                    "snapshot_tile_bad=%d snapshot_attr_cpu_bad=%d " ..
                    "first_attr=%s first_tile=%s " ..
                    "af=%04X bc=%04X de=%04X hl=%04X sp=%04X ie=%02X " ..
                    "svbk=%02X vbk=%02X ff55=%02X ly=%02X stat=%02X\n",
                    f, target, source_bank, attr_bad, tile_bad, attr_cpu_bad,
                    attr_plane_bad, tile_plane_bad, source_changed,
                    snapshot_tile_bad, snapshot_attr_cpu_bad,
                    first_attr, first_tile,
                    register("AF"), register("BC"),
                    register("DE"), register("HL"), register("SP"),
                    emu:read8(0xFFFF), old_svbk, old_vbk,
                    emu:read8(0xFF55), emu:read8(0xFF44),
                    emu:read8(0xFF41)))
                if PUBLISH_STATE_OUT ~= nil and not publish_state_saved then
                    local save_ok, result = pcall(function()
                        return emu:saveStateFile(PUBLISH_STATE_OUT)
                    end)
                    publish_state_saved = save_ok and result ~= false
                end
            end
            if item[1] == "compiler-exit" then
                local target = emu:read8(0xFFA7) << 8
                local peer = target == 0x9800 and 0x9C00 or 0x9800
                local bad, peer_bad, source_bad, target_expected_bad = 0, 0, 0, 0
                local first = "none"
                -- Read the raw bank-1 VRAM domain. CPU-mapped reads can be
                -- blocked by the active PPU mode even after GDMA completed.
                local old_vbk = emu:read8(0xFF4F)
                for row = 0, 23 do
                    for col = 0, 23 do
                        local plane = emu:read8(0xD000 + row * 32 + col)
                        local tile = emu:read8(0xC1A0 + row * 24 + col)
                        local expected = emu:read8(0xC600 + tile)
                        local target_value = emu.memory.vram:read8(
                            target - 0x8000 + row * 32 + col)
                        if plane ~= expected then source_bad = source_bad + 1 end
                        if target_value ~= expected then
                            target_expected_bad = target_expected_bad + 1
                        end
                        if target_value ~= plane then
                            bad = bad + 1
                            if first == "none" then
                                first = string.format(
                                    "%d,%d,%02X,%02X,%02X",
                                    row, col, tile, expected, target_value)
                            end
                        end
                        if emu.memory.vram:read8(
                                peer - 0x8000 + row * 32 + col
                            ) ~= plane then
                            peer_bad = peer_bad + 1
                        end
                    end
                end
                trace:write(string.format(
                    "publish frame=%d target=%04X bad=%d peer=%04X " ..
                    "peer_bad=%d source_bad=%d target_expected_bad=%d " ..
                    "first=%s native_h=%02X vbk=%02X hdma=%02X%02X%02X%02X%02X\n",
                    f, target, bad, peer, peer_bad, source_bad,
                    target_expected_bad, first,
                    (register("HL") >> 8) & 0xFF, old_vbk,
                    emu:read8(0xFF51), emu:read8(0xFF52),
                    emu:read8(0xFF53), emu:read8(0xFF54),
                    emu:read8(0xFF55)))
                if f >= 190 and PUBLISH_STATE_OUT ~= nil
                        and not publish_state_saved then
                    local save_ok, result = pcall(function()
                        return emu:saveStateFile(PUBLISH_STATE_OUT)
                    end)
                    publish_state_saved = save_ok and result ~= false
                    trace:write(string.format(
                        "publish_state frame=%d target=%04X path=%s saved=%s\n",
                        f, target, PUBLISH_STATE_OUT,
                        publish_state_saved and "yes" or "no"))
                end
                if f >= 190 and pending_publish == nil then
                    local plane, bank1 = {}, {}
                    for row = 0, 23 do
                        for col = 0, 23 do
                            plane[#plane + 1] = emu:read8(
                                0xD000 + row * 32 + col)
                        end
                    end
                    local old_svbk = emu:read8(0xFF70)
                    emu:write8(0xFF70, 1)
                    for row = 0, 23 do
                        for col = 0, 23 do
                            bank1[#bank1 + 1] = emu:read8(
                                0xD000 + row * 32 + col)
                        end
                    end
                    emu:write8(0xFF70, old_svbk & 7)
                    pending_publish = {
                        target=target, plane=plane, bank1=bank1,
                        lcdc=gdma_saved_lcdc or emu:read8(0xFF40),
                    }
                    emu:write8(0xFF40, pending_publish.lcdc & 0x7F)
                end
                if f >= 190 and not attr_watch_installed then
                    local watched_target = target
                    for row = 0, 23 do
                        for col = 0, 23 do
                            local address = target + row * 32 + col
                            emu:setRangeWatchpoint(function(info)
                                trace:write(string.format(
                                    "attr_write frame=%d target=%04X " ..
                                    "address=%04X value=%02X pc=%04X " ..
                                    "rom=%02X vbk=%02X\n",
                                    f, watched_target, info.address & 0xFFFF,
                                    info.value & 0xFF, register("PC"),
                                    emu:read8(0xFF99), emu:read8(0xFF4F)))
                            end, address, address, C.WATCHPOINT_TYPE.WRITE)
                        end
                    end
                    attr_watch_installed = true
                end
            end
            if item[1] == "compiler-exit" and gdma_saved_lcdc ~= nil then
                emu:write8(0xFF40, gdma_saved_lcdc)
                gdma_saved_lcdc = nil
            end
            trace:flush()
        end, item[2]) end)
    end
end

local function hex_range(address, length)
    local result = {}
    for offset = 0, length - 1 do
        result[#result + 1] = string.format(
            "%02X", emu:read8(address + offset)
        )
    end
    return table.concat(result)
end

local function palette_hex(accessor_name, index_port, data_port)
    local accessor = emu.memory[accessor_name]
    local raw
    if accessor then
        raw = accessor:readRange(0, 64)
    else
        local old_index = emu:read8(index_port)
        local bytes = {}
        for index = 0, 63 do
            emu:write8(index_port, index)
            bytes[#bytes + 1] = string.char(emu:read8(data_port))
        end
        emu:write8(index_port, old_index)
        raw = table.concat(bytes)
    end
    return (raw:gsub(".", function(char)
        return string.format("%02X", string.byte(char))
    end))
end

local function finish(status, message)
    if done then return end
    done = true
    trace:close()
    local report = assert(io.open(OUT .. ".report", "w"))
    report:write(string.format(
        "status=%s target=%d expected_scene=%02X frame=%d d880=%02X " ..
        "ffc1=%d ff91=%02X df0d=%02X ffba=%02X ffbf=%02X phase=%02X " ..
        "stable=%d palette_settled=%d settle_frame=%d message=%s " ..
        "pc=%04X sp=%04X ie=%02X lcdc=%02X " ..
        "active_table=%s bg_cram=%s obj_cram=%s\n",
        status, TARGET, EXPECTED_SCENE, f, emu:read8(0xD880),
        emu:read8(0xFFC1), emu:read8(0xFF91), emu:read8(0xDF0D),
        emu:read8(0xFFBA), emu:read8(0xFFBF), emu:read8(0xDF4C),
        stable, palette_settled, settle_frame, message, register("PC"), register("SP"),
        emu:read8(0xFFFF), emu:read8(0xFF40),
        hex_range(0xC600, 0x100),
        palette_hex("cgbBgPalette", 0xFF68, 0xFF69),
        palette_hex("cgbObjPalette", 0xFF6A, 0xFF6B)
    ))
    report:close()
    local marker = assert(io.open(OUT .. ".done", "w"))
    marker:write(status .. "\n")
    marker:close()
end

if TARGET == 4 and TED_INWINDOW_SANITIZER then
    -- The row-aware publisher intentionally spends every HBlank in bank 13;
    -- a frame callback may never observe its very short fixed-bank return.
    -- Serialize exactly at the wrapper's proven ABI exit instead of saving a
    -- bank-13 PC and manufacturing an unloadable MBC state.
    pcall(function() emu:setBreakpoint(function()
        if done or not reached or not ted_activated
                or stable < STABLE_TARGET or palette_settled < 1 then
            return
        end
        emu:screenshot(OUT .. ".png")
        local save_ok, result = pcall(function()
            return emu:saveStateFile(STATE_OUT)
        end)
        if not save_ok or result == false then
            finish("error", "fixed-exit-saveStateFile-failed")
            return
        end
        settle_frame = settle_frame == 0 and f or settle_frame
        finish("ok", "saved")
    end, 0x0846) end)
end

-- Optional exact ready-path trace. Switchable-ROM breakpoints must carry
-- bank 13 explicitly; an unqualified $4000-$7FFF breakpoint can perturb a
-- different mapped bank and invalidate the diagnosis.
local qualified = os.getenv("TED_QUALIFIED_TRACE")
if qualified then
    local q = assert(io.open(qualified, "w"))
    local function hit(name)
        if (name == "repair" or name == "worker-return") and f < 100 then
            return
        end
        q:write(string.format(
            "%s frame=%d pc=%04X rombank=%02X svbk=%02X ready=%02X " ..
            "de=%04X hl=%04X bc=%04X sp=%04X ie=%02X lcdc=%02X\n",
            name, f, register("PC"), emu:read8(0xFF99),
            emu:read8(0xFF70) & 7, emu:read8(0xC5FF), register("DE"),
            register("HL"), register("BC"), register("SP"),
            emu:read8(0xFFFF), emu:read8(0xFF40)))
        q:flush()
    end
    local function bp(address, name, segment)
        assert(pcall(function()
            local callback = function() hit(name) end
            if segment then emu:setBreakpoint(callback, address, segment)
            else emu:setBreakpoint(callback, address) end
        end))
    end
    bp(0x028A, "caller")
    bp(0xDB80, "gate")
    bp(0x0838, "fixed-wrapper")
    bp(0x0846, "fixed-wrapper-exit")
    bp(0xD500, "private-runtime")
    bp(0xD571, "worker-return")
    for _, site in ipairs({
        {0x5830, "publication-entry"}, {0x7027, "clear-wrapper"},
        {0x5D7F, "draw-wrapper"}, {0x76BD, "renderer-entry"},
        {0x76F4, "renderer-run-tail"}, {0x76F7, "renderer-return"},
        {0x6500, "repair"},
        {0x5D8B, "draw-wrapper-exit"}, {0x61B0, "svbk-restore"},
        {0x58C0, "transport-setup"}, {0x6268, "publication-finish"},
    }) do bp(site[1], site[2], 13) end
end

-- Narrow post-publication trap.  This remains separate from the verbose
-- qualified route so breakpoint overhead cannot turn a two-frame transport
-- into an artificial timeout.
local dfbd_trace = os.getenv("TED_DFBD_TRACE")
if dfbd_trace then
    local trap = assert(io.open(dfbd_trace, "w"))
    local trapped = false
    assert(pcall(function()
        emu:setBreakpoint(function()
            if trapped then return end
            trapped = true
            local bytes = ""
            for address = 0xDFAD, 0xDFCC do
                bytes = bytes .. string.format("%02X", emu:read8(address))
            end
            trap:write(string.format(
                "dfbd frame=%d pc=%04X rombank=%02X svbk=%02X " ..
                "af=%04X de=%04X hl=%04X bc=%04X sp=%04X ie=%02X " ..
                "lcdc=%02X bytes=%s\n",
                f, register("PC"), emu:read8(0xFF99),
                emu:read8(0xFF70) & 7, register("AF"), register("DE"),
                register("HL"), register("BC"), register("SP"),
                emu:read8(0xFFFF), emu:read8(0xFF40), bytes))
            trap:flush()
        end, 0xDFBD)
    end))
end

local gate_trace = os.getenv("TED_GATE_TRACE")
if gate_trace then
    local gates = assert(io.open(gate_trace, "w"))
    assert(pcall(function()
        emu:setBreakpoint(function()
            gates:write(string.format(
                "gate frame=%d ready=%02X svbk=%02X pc=%04X sp=%04X\n",
                f, emu:read8(0xC5FF), emu:read8(0xFF70) & 7,
                register("PC"), register("SP")))
            gates:flush()
        end, 0xDB80)
    end))
end

callbacks:add("frame", function()
    if done then return end
    f = f + 1
    emu:setKeys(0)

    -- The gameplay colorizer can end a VBlank by jumping through the native
    -- HRAM OAM-DMA helper at $FF80.  During that short bus-locked interval,
    -- reads from external WRAM return $FF even though the arena is intact.
    -- A frame boundary can land at $FF8E inside that helper; never interpret
    -- its inaccessible D880 as a scene transition or write fixture state
    -- until execution has returned to ordinary address space.
    local frame_pc = register("PC")
    if frame_pc >= 0xFF80 and frame_pc <= 0xFF9F then
        trace:write(string.format(
            "frame=%d pc=%04X deferred=hram-oam-dma\n", f, frame_pc))
        trace:flush()
        return
    end

    if pending_publish ~= nil then
        local old_vbk = emu:read8(0xFF4F)
        emu:write8(0xFF4F, 1)
        local bad, bank1_bad = 0, 0
        for index, plane in ipairs(pending_publish.plane) do
            local row = (index - 1) // 24
            local col = (index - 1) % 24
            local value = emu:read8(
                pending_publish.target + row * 32 + col)
            if value ~= plane then
                bad = bad + 1
            end
            if value ~= pending_publish.bank1[index] then
                bank1_bad = bank1_bad + 1
            end
        end
        trace:write(string.format(
            "publish_deferred frame=%d target=%04X bad=%d " ..
            "bank1_bad=%d vbk=%02X\n",
            f, pending_publish.target, bad, bank1_bad, emu:read8(0xFF4F)))
        trace:flush()
        emu:write8(0xFF4F, old_vbk & 1)
        emu:write8(0xFF40, pending_publish.lcdc)
        pending_publish = nil
    end

    -- D000-DFFF is banked CGB WRAM. A completed-map attribute compiler may
    -- legitimately span a frame boundary with SVBK=2/3 selected. Never read
    -- game-state fields from, or inject fixture writes into, its staging
    -- plane; wait until the runtime restores bank 1.
    local svbk = emu:read8(0xFF70) & 0x07
    local game_wram_visible = STOCK_ROM or svbk == 0 or svbk == 1
    if not game_wram_visible then
        return
    end

    -- Keep Sara alive while the arena settles.
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    -- The synthetic Stage-1 dispatcher route can inherit an attack phase that
    -- decrements DCBB before serialization (Troop arms D888/DD06; Ted and
    -- Penta can leave for the splash shortly after reload). Keep every visual
    -- fixture in its arena; boss-exit behavior has a separate death/game-over
    -- gate.
    emu:write8(0xDCBB, 0xF0)

    local scene = emu:read8(0xD880)
    if f <= ENTRY_TIMEOUT and (not reached or stable < 80) then
        trace:write(string.format(
            "frame=%d pc=%04X d880=%02X ff91=%02X df0d=%02X ffb7=%02X ffba=%02X " ..
            "ffbf=%02X ffc0=%02X ffd0=%02X ffc1=%02X tick=%02X bgp=%02X hash=%02X " ..
            "phase=%02X bg7=%s dcbb=%02X d888=%02X dd06=%02X " ..
            "ff99=%02X ie=%02X ted_ready=%02X pose_marker=%02X pose_banks=%s native_tail=%s " ..
            "de=%04X hl=%04X bc=%04X sp=%04X group=%02X c349=%02X\n",
            f, register("PC"), scene, emu:read8(0xFF91),
            emu:read8(0xDF0D), emu:read8(0xFFB7),
            emu:read8(0xFFBA), emu:read8(0xFFBF), emu:read8(0xFFC0),
            emu:read8(0xFFD0), emu:read8(0xFFC1), emu:read8(0xFFD4),
            emu:read8(0xFF47), emu:read8(0xDF00),
            emu:read8(0xDF4C),
            palette_hex("cgbBgPalette", 0xFF68, 0xFF69):sub(113, 128),
            emu:read8(0xDCBB),
            emu:read8(0xD888), emu:read8(0xDD06),
            emu:read8(0xFF99), emu:read8(0xFFFF), emu:read8(0xC5FF),
            ted_pose_marker(),
            ted_pose_markers(),
            hex_range(0xC5F3, 13), register("DE"), register("HL"),
            register("BC"), register("SP"), emu:read8(0xFFE0),
            emu:read8(0xC349)
        ))
        trace:flush()
    end
    if not reached then
        if scene == EXPECTED_SCENE then
            -- The serialized diagnostic landing waits in Stage 1 before
            -- calling the stock boss dispatcher and can consume the pending
            -- scene transition during that artificial wait. Rearm only after
            -- the dispatcher publishes the real target; the unmodified ROM
            -- then selects and renders its own arena table on the next VBlank.
            emu:write8(0xFF91, 0x01)
            emu:write8(0xDF0D, 0xFF)
            reached = true
        elseif f > ENTRY_TIMEOUT then
            finish("error", "arena-entry-timeout")
            return
        end
    end
    if reached then
        if emu:read8(0xD880) ~= EXPECTED_SCENE then
            finish("error", "arena-left-before-save")
            return
        end
        if TARGET == 4 and not ted_activated
                and (emu:read8(0xD888) ~= 0 or emu:read8(0xDD06) ~= 0) then
            ted_activated = true
            stable = 0
            palette_settled = 0
        end
        if ted_activated then
            stable = stable + 1
            local tick = emu:read8(0xFFD4)
            if tick == last_tick then
                stagnant_ticks = stagnant_ticks + 1
            else
                last_tick, stagnant_ticks = tick, 0
            end
            if stagnant_ticks >= 8 then
                finish("error", "boss-main-loop-stalled")
                return
            end
        end
        -- A scene can be visually stable while the bounded CRAM loader is
        -- still carrying Stage 1 rows into the arena. Require a separate
        -- eight-frame quiet hold after phase zero, but do not demand another
        -- full minute from short-lived synthetic boss entry fixtures.
        if emu:read8(0xDF4C) == 0 then
            palette_settled = palette_settled + 1
        else
            palette_settled = 0
        end
        local obj_cram = palette_hex("cgbObjPalette", 0xFF6A, 0xFF6B)
        local obj_expected = OBJ_EXPECTED == "" or
            obj_cram:sub(65, 128) == OBJ_EXPECTED
        -- Never serialize inside the atomic publisher's temporary IE=$04
        -- section. Such a state can look settled yet resume midway through a
        -- map and invalidate every subsequent full-plane receipt.
        local pc = register("PC")
        local bank = emu:read8(0xFF99)
        local mainline_rendezvous = TARGET ~= 4 or ted_activated
        local publisher_idle = emu:read8(0xFFFF) == 0x07
            -- Expanded Ted helpers can execute at the same $6000 address in
            -- a high MBC5 bank.  Serializing there produces a state that
            -- resumes in the wrong mapped code page.  Candidate fixtures must
            -- rendezvous in native bank 1 just like every other arena.
            and (STOCK_ROM or bank == 0x01)
            and pc >= 0x4000
            and not (pc >= 0x42A7 and pc < 0x436E)
            and not (WRITER_MIRROR and bank == 0x0D
                     and pc >= 0x7687 and pc < 0x76FF)
            and not (WRITER_MIRROR and pc >= 0x0838 and pc < 0x0849)
            and mainline_rendezvous
        local required_palette_hold = TARGET == 4 and 1 or 8
        if settle_frame == 0 and ted_activated and stable >= STABLE_TARGET
                and palette_settled >= required_palette_hold and obj_expected then
            -- Performance is proven when the scene/palettes have settled;
            -- serialization may wait longer for a safe mainline rendezvous.
            settle_frame = f
        end
        if ted_activated and stable >= STABLE_TARGET
                and palette_settled >= required_palette_hold and obj_expected
                and publisher_idle then
            emu:screenshot(OUT .. ".png")
            local save_ok, result = pcall(function()
                return emu:saveStateFile(STATE_OUT)
            end)
            local saved = save_ok and result ~= false
            if not saved then
                finish("error", "saveStateFile-failed")
                return
            end
            finish("ok", "saved")
        end
    end
end)
