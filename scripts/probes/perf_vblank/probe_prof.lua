-- Stage-7 state-keyed patrol wrapper for probe_stage_speed.lua.
--
-- The stock frame/loop patrols change direction as a function of time or loop
-- count. A ROM with different renderer cadence therefore consumes a different
-- movement sequence. This wrapper changes direction only at exact world-X
-- endpoints, while observing the native $0ABB input join. During play,
-- emu:setKeys is the sole stimulus.
--
-- Equal-world mode (STAGE7_WORLD_IMAGE): at the first play-phase input join
-- both ROMs receive the same native world image (D800-D8FF scene/player
-- state, DC00-DCFF entity tables, FFD4-FFD5 frame counters) captured from the
-- stock ROM, then the RNG cursor FFD1 is set to STAGE7_WORLD_SEED. Stock and
-- DX therefore start the measured patrol from identical game state. Every
-- run dumps the post-injection image to OUT .. '.world.bin' so the verifier
-- can prove the four traces started equal.

local base_path = assert(os.getenv("STAGE7_STATE_PATROL_BASE_PROBE"))
local file = assert(io.open(base_path, "r"))
local source = file:read("*a")
file:close()

local count
source, count = source:gsub(
  '    if phase == "sync" then\n      phase = "play"\n      play_frames = 0\n      previous_scx = emu:read8%(0xFF43%)\n      previous_scy = emu:read8%(0xFF42%)\n    end',
  '    if phase == "sync" then return end')
assert(count == 1, "checked main-loop sync anchor changed")

source, count = source:gsub(
  '  %-%- The two stock entries publish H[^\n]*',
  function()
    return [[
  local WORLD_RANGES = {{0xD800, 0x100}, {0xDC00, 0x100}, {0xFFCB, 1}, {0xFFD4, 2}}
  local coordinate = assert(io.open(OUT .. '.coordinate.tsv', 'w'))
  local prof = assert(io.open(OUT .. '.prof.tsv', 'w'))
  local active = false
  local function hit(pc)
    return function()
      if phase ~= 'play' then return end
      if pc == 0x06D1 then active = true end
      if not active then return end
      prof:write(string.format('%d\t%X\t%d\t%d\n', play_frames, pc, emu:currentCycle(), emu:read8(0xFF44)))
      if pc == 0x081D then active = false end
    end
  end
  for _, pc in ipairs({0x06D1, 0x06DC, 0x06DF, 0x081D, 0xFF80}) do emu:setBreakpoint(hit(pc), pc, -1) end
  for _, pc in ipairs({0x73FC, 0x7464, 0x76EE, 0x76FB, 0x7485, 0x6F1D, 0x6F20, 0x6F23, 0x6F26, 0x6F2B, 0x6F3D, 0x6F68, 0x6F6E, 0x6F7A, 0x6F7F, 0x6F82, 0x6F85, 0x6F8C,
                       0x7100, 0x6A0E, 0x7189, 0x718C, 0x718F, 0x6C90, 0x7CBF, 0x6B00, 0x6E00, 0x6DA7, 0x6B80, 0x6E80}) do
    emu:setBreakpoint(hit(pc), pc, 13)
  end
  coordinate:write('ordinal\tloop\tframe\tconsumed\tplanned\thalf_cycles\troom\tx\ty\n')
  local consumed_count = 0
  local planned_keys = 0
  local direction = KEY_RIGHT
  local half_cycles = 0
  local world_image = nil
  local world_seed = nil
  local image_path = os.getenv('STAGE7_WORLD_IMAGE')
  if image_path and image_path ~= '' then
    local handle = assert(io.open(image_path, 'rb'))
    world_image = handle:read('*a')
    handle:close()
    world_seed = assert(tonumber(os.getenv('STAGE7_WORLD_SEED')),
      'equal-world mode requires STAGE7_WORLD_SEED')
    assert(world_seed >= 0 and world_seed < 100 and world_seed % 1 == 0,
      'RNG cursor seed must be an integer in [0, 100)')
  end
  local last_consumed_loop = -1
  local last_consumed_keys = -1
  emu:setBreakpoint(function()
    if phase == 'sync' then
      if world_image then
        local offset = 1
        for _, range in ipairs(WORLD_RANGES) do
          for address = range[1], range[1] + range[2] - 1 do
            emu:write8(address, world_image:byte(offset))
            offset = offset + 1
          end
        end
        assert(offset == #world_image + 1, 'world image size mismatch')
        emu:write8(0xFFD1, world_seed)
      end
      local dump = assert(io.open(OUT .. '.world.bin', 'wb'))
      for _, range in ipairs(WORLD_RANGES) do
        for address = range[1], range[1] + range[2] - 1 do
          dump:write(string.char(emu:read8(address)))
        end
      end
      dump:write(string.char(emu:read8(0xFFD1)))
      dump:close()
      phase = 'play'
      play_frames = 0
      previous_scx = emu:read8(0xFF43)
      previous_scy = emu:read8(0xFF42)
      main_loop_hits = 1
      last_main_loop_frame = 0
    end
    if phase ~= 'play' then return end
    assert(INPUT_MODE == 'loop-patrol', 'state patrol requires loop-patrol mode')
    assert(emu:read8(0x0ABB) == 0xF0 and emu:read8(0x0ABC) == 0xEB,
      'native real/demo input convergence changed')
    local w = assert(emu.memory.wram)
    local sp = read_register('SP') & 0xFFFF
    assert(sp >= 0xC000 and sp < 0xDFFE, 'unexpected input stack')
    local keys = w:read8(sp + 1 - 0xC000)
    consumed_count = consumed_count + 1
    if consumed_count == 1 then
      assert(keys == 0, 'first consumed input not neutral')
    elseif main_loop_hits == last_consumed_loop then
      -- The native $0ABB frame-parity wait can re-enter the join inside one
      -- main-loop iteration without a new $00A8 sample. Such a duplicate
      -- observes the same stacked input as the first hit, which was planned
      -- before this loop's endpoint update; the verifier requires the
      -- duplicate row to equal the first one.
      assert(keys == last_consumed_keys, string.format(
        'state patrol duplicate join mismatch at loop %d: %02X/%02X',
        main_loop_hits, keys, last_consumed_keys))
    else
      assert(keys == planned_keys, string.format(
        'state patrol input mismatch at loop %d: %02X/%02X',
        main_loop_hits, keys, planned_keys))
    end
    last_consumed_loop = main_loop_hits
    last_consumed_keys = keys

    local world_x = w:read8(0x1C00) + 256 * w:read8(0x1C01)
    local world_y = w:read8(0x1C02) + 256 * w:read8(0x1C03)
    if direction == KEY_RIGHT and world_x >= 152 then
      direction = KEY_LEFT
      half_cycles = half_cycles + 1
    elseif direction == KEY_LEFT and world_x <= 92 then
      direction = KEY_RIGHT
      half_cycles = half_cycles + 1
    end
    planned_keys = direction
    emu:setKeys(planned_keys)
    coordinate:write(string.format(
      '%d\t%d\t%d\t%02X\t%02X\t%d\t%02X\t%d\t%d\n',
      consumed_count, main_loop_hits, play_frames, keys, planned_keys,
      half_cycles, emu:read8(0xFFBD), world_x, world_y))
    coordinate:flush()
  end, 0x0ABB)
  -- The two stock entries publish H
]]
  end)
assert(count == 1, "checked input-observer insertion anchor changed")

source, count = source:gsub(
  'emu:setKeys%(%(main_loop_hits %- 1%) %% 30 < 15 and KEY_RIGHT or KEY_LEFT%)',
  '-- state patrol plans physical input at the native $0ABB join')
assert(count == 1, "checked loop-patrol input anchor changed")

assert(load(source, "@checked-stage-probe+stage7-state-patrol"))()
