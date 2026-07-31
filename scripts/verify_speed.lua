-- Speed Verification for Penta Dragon DX
-- Starts game, waits for the real dungeon, then measures 10 seconds.
-- Compares to original ROM's advancement rate.
-- Outputs JSON report.

local OUTPUT = os.getenv("VERIFY_OUTPUT") or "verify_speed_report.json"
local TEST_DURATION = 600  -- 10 seconds at 60fps
local ROM_LABEL = os.getenv("VERIFY_ROM_LABEL") or "dx"
local INPUT_MODE = os.getenv("VERIFY_INPUT_MODE") or "right"

local KEY_A, KEY_START = 0x01, 0x08

local frame = 0
local seeded = false
local game_entry_seen = false
local dungeon_started = false
local game_start_frame = 0
local dungeon_start_frame = 0
local test_start_frame = 0
local test_running = false

-- Tracking counters
local d880_changes = 0
local ffbd_changes = 0
local dc81_changes = 0
local scroll_ticks = 0

local prev_d880 = -1
local prev_ffbd = -1
local prev_dc81 = -1
local prev_scx = -1

-- OAM change detection
local prev_oam_hash = 0
local oam_change_count = 0
local prev_sara_oam_hash = 0
local sara_oam_change_count = 0
local prev_sara_oam_full_hash = 0
local sara_oam_full_change_count = 0
local prev_enemy_oam_hash = 0
local enemy_oam_change_count = 0
local prev_sara_x = 0
local sara_x_change_count = 0
local sara_x_distance = 0
local sara_x_first = 0
local sara_x_last = 0
local prev_sara_state = 0
local sara_state_change_count = 0
local main_loop_hits = 0
local main_loop_breakpoint_available = false
local central_emitter_hits = 0
local free_emitter_hits = 0
local emitter_breakpoints_available = false

local function seed_sram()
    emu:write8(0x0000, 0x0A)
    for _, base in ipairs({0xBF00, 0xBF28, 0xBF50, 0xBF78, 0xBFA0, 0xBFC8}) do
        emu:write8(base, 0xFF)
        for offset = 1, 0x1F do emu:write8(base + offset, 0x00) end
    end
end

-- Count entries to the stock main loop directly. The old state counters could
-- remain equal even when DX consumed enough VBlank time to run the loop only
-- about half as often.
main_loop_breakpoint_available = pcall(function()
    emu:setBreakpoint(function()
        if test_running then
            main_loop_hits = main_loop_hits + 1
        end
    end, 0x016C)
end)

-- Attribute the remaining DX/vanilla delta to the two stock sprite-emission
-- entry points. Both ROMs retain these public addresses even when DX
-- tail-jumps to a WRAM-hot implementation.
emitter_breakpoints_available = pcall(function()
    emu:setBreakpoint(function()
        if test_running then
            central_emitter_hits = central_emitter_hits + 1
        end
    end, 0x10D1)
    emu:setBreakpoint(function()
        if test_running then
            free_emitter_hits = free_emitter_hits + 1
        end
    end, 0x346F)
end)

local function hash_oam_positions(first_slot, last_slot)
    local sum = 0
    for i = first_slot, last_slot do
        local base = 0xFE00 + i * 4
        sum = (sum * 31 + emu:read8(base)) % 0xFFFFFF
        sum = (sum * 31 + emu:read8(base + 1)) % 0xFFFFFF
    end
    return sum
end

local function hash_oam_full(first_slot, last_slot)
    local sum = 0
    for i = first_slot, last_slot do
        local base = 0xFE00 + i * 4
        for offset = 0, 3 do
            sum = (sum * 31 + emu:read8(base + offset)) % 0xFFFFFF
        end
    end
    return sum
end

local function read_sara_x()
    return emu:read8(0xDC18)
end

callbacks:add("frame", function()
    frame = frame + 1
    -- Force the reproducible save-present GAME START/level-select route used
    -- by the stage-speed and stage-integrity probes. Without this, clean
    -- per-ROM save directories can wander into different new-game/title
    -- branches and compare different gameplay states.
    emu:write8(0xDCFD, 0x01)

    if not seeded and frame >= 100 then
        seed_sram()
        seeded = true
    end

    -- Record menu-to-game entry independently from the speed window.
    local ffc1 = emu:read8(0xFFC1)
    if ffc1 == 1 and not game_entry_seen then
        game_entry_seen = true
        game_start_frame = frame
    end

    -- FFC1 rises before the STAGE XX splash, which previously made most of
    -- this "gameplay" receipt measure stage loading. Start only after the real
    -- dungeon state ($02-$0E), then allow 120 frames to stabilize.
    local scene = emu:read8(0xD880)
    if game_entry_seen and not dungeon_started
            and scene >= 0x02 and scene <= 0x0E then
        dungeon_started = true
        dungeon_start_frame = frame
        test_start_frame = frame + 120
    end

    -- Before test: use state-driven navigation rather than a brittle series
    -- of frame-exact title/interstitial taps.  This is the same route used by
    -- the stage-speed matrix and works for both vanilla and the DX title
    -- cadence while applying equivalent inputs to each ROM.
    if not game_entry_seen then
        if frame >= 300 and frame < 306 then
            emu:setKeys(KEY_START)
        elseif frame >= 330 then
            emu:write8(0xFFBA, 0)
            seed_sram()
            if frame % 60 >= 10 and frame % 60 < 16 then
                emu:setKeys(KEY_A)
            else
                emu:setKeys(0)
            end
        else
            emu:setKeys(0)
        end
        return
    end

    -- Stage splash / load and dungeon stabilization period.
    if not dungeon_started or frame < test_start_frame then
        emu:setKeys(0)
        -- Keep alive
        emu:write8(0xDCDD, 0x17)
        emu:write8(0xDCDC, 0xFF)
        emu:write8(0xDCBB, 0xFF)
        return
    end

    -- Start test
    if not test_running then
        test_running = true
        prev_d880 = emu:read8(0xD880)
        prev_ffbd = emu:read8(0xFFBD)
        prev_dc81 = emu:read8(0xDC81)
        prev_scx = emu:read8(0xFF43)
        prev_oam_hash = hash_oam_positions(0, 39)
        prev_sara_oam_hash = hash_oam_positions(0, 3)
        prev_sara_oam_full_hash = hash_oam_full(0, 3)
        prev_enemy_oam_hash = hash_oam_positions(4, 39)
        prev_sara_x = read_sara_x()
        sara_x_first = prev_sara_x
        sara_x_last = prev_sara_x
        prev_sara_state = emu:read8(0xDC19)
    end

    -- During test: walk RIGHT
    local elapsed = frame - test_start_frame
    if elapsed < TEST_DURATION then
        if INPUT_MODE == "stationary" then
            emu:setKeys(0)
        else
            emu:setKeys(0x10)  -- RIGHT
        end

        -- Keep alive
        emu:write8(0xDCDD, 0x17)
        emu:write8(0xDCDC, 0xFF)
        emu:write8(0xDCBB, 0xFF)

        -- Track state changes
        local d880 = emu:read8(0xD880)
        local ffbd = emu:read8(0xFFBD)
        local dc81 = emu:read8(0xDC81)
        local scx = emu:read8(0xFF43)

        if d880 ~= prev_d880 then d880_changes = d880_changes + 1 end
        if ffbd ~= prev_ffbd then ffbd_changes = ffbd_changes + 1 end
        if dc81 ~= prev_dc81 then dc81_changes = dc81_changes + 1 end
        if scx ~= prev_scx then scroll_ticks = scroll_ticks + 1 end

        prev_d880 = d880
        prev_ffbd = ffbd
        prev_dc81 = dc81
        prev_scx = scx

        local h = hash_oam_positions(0, 39)
        if h ~= prev_oam_hash then oam_change_count = oam_change_count + 1 end
        prev_oam_hash = h

        local sara_h = hash_oam_positions(0, 3)
        if sara_h ~= prev_sara_oam_hash then
            sara_oam_change_count = sara_oam_change_count + 1
        end
        prev_sara_oam_hash = sara_h

        local sara_full_h = hash_oam_full(0, 3)
        if sara_full_h ~= prev_sara_oam_full_hash then
            sara_oam_full_change_count = sara_oam_full_change_count + 1
        end
        prev_sara_oam_full_hash = sara_full_h

        local enemy_h = hash_oam_positions(4, 39)
        if enemy_h ~= prev_enemy_oam_hash then
            enemy_oam_change_count = enemy_oam_change_count + 1
        end
        prev_enemy_oam_hash = enemy_h

        local sx = read_sara_x()
        if sx ~= prev_sara_x then
            sara_x_change_count = sara_x_change_count + 1
            local delta = math.abs(sx - prev_sara_x)
            if delta > 128 then delta = 256 - delta end
            sara_x_distance = sara_x_distance + delta
        end
        prev_sara_x = sx
        sara_x_last = sx

        local sara_state = emu:read8(0xDC19)
        if sara_state ~= prev_sara_state then
            sara_state_change_count = sara_state_change_count + 1
        end
        prev_sara_state = sara_state
    else
        -- Test complete
        emu:setKeys(0)

        local f = io.open(OUTPUT, "w")
        if f then
            f:write('{\n')
            f:write(string.format('  "rom_label": "%s",\n', ROM_LABEL))
            f:write(string.format('  "input_mode": "%s",\n', INPUT_MODE))
            f:write(string.format('  "test_frames": %d,\n', TEST_DURATION))
            f:write(string.format('  "game_start_frame": %d,\n', game_start_frame))
            f:write(string.format(
                '  "dungeon_start_frame": %d,\n', dungeon_start_frame))
            f:write(string.format(
                '  "final_scene": %d,\n', emu:read8(0xD880)))
            f:write(string.format(
                '  "main_loop_breakpoint_available": %s,\n',
                tostring(main_loop_breakpoint_available)))
            f:write(string.format('  "main_loop_hits": %d,\n',
                main_loop_hits))
            f:write(string.format(
                '  "emitter_breakpoints_available": %s,\n',
                tostring(emitter_breakpoints_available)))
            f:write(string.format('  "central_emitter_hits": %d,\n',
                central_emitter_hits))
            f:write(string.format('  "free_emitter_hits": %d,\n',
                free_emitter_hits))
            f:write(string.format('  "d880_changes": %d,\n', d880_changes))
            f:write(string.format('  "ffbd_changes": %d,\n', ffbd_changes))
            f:write(string.format('  "dc81_changes": %d,\n', dc81_changes))
            f:write(string.format('  "scroll_ticks": %d,\n', scroll_ticks))
            f:write(string.format('  "oam_changes": %d,\n', oam_change_count))
            f:write(string.format('  "sara_oam_changes": %d,\n',
                sara_oam_change_count))
            f:write(string.format('  "sara_oam_full_changes": %d,\n',
                sara_oam_full_change_count))
            f:write(string.format('  "enemy_oam_changes": %d,\n',
                enemy_oam_change_count))
            f:write(string.format('  "sara_x_changes": %d,\n',
                sara_x_change_count))
            f:write(string.format('  "sara_x_distance": %d,\n',
                sara_x_distance))
            f:write(string.format('  "sara_x_first": %d,\n',
                sara_x_first))
            f:write(string.format('  "sara_x_last": %d,\n', sara_x_last))
            f:write(string.format('  "sara_state_changes": %d\n',
                sara_state_change_count))
            f:write('}\n')
            f:close()
        end

        console:log(string.format(
            "[VERIFY_SPEED] %s: loop=%d scroll=%d dc81=%d sara_oam=%d sara_x=%d in %d frames",
            ROM_LABEL, main_loop_hits, scroll_ticks, dc81_changes,
            sara_oam_change_count, sara_x_change_count, TEST_DURATION))

        local df = io.open("DONE_VERIFY_SPEED_" .. ROM_LABEL, "w")
        if df then df:write("OK"); df:close() end

        emu:quit()
    end
end)
