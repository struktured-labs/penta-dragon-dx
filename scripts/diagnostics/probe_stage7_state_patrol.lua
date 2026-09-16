-- Stage-7 state-keyed patrol wrapper for probe_stage_speed.lua.
--
-- The stock frame/loop patrols change direction as a function of time or loop
-- count. A ROM with different renderer cadence therefore consumes a different
-- movement sequence. This wrapper changes direction only at exact world-X
-- endpoints, while observing the native $0ABB input join. It never writes game
-- RAM; emu:setKeys is the sole stimulus.

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
  local coordinate = assert(io.open(OUT .. '.coordinate.tsv', 'w'))
  coordinate:write('ordinal\tloop\tframe\tconsumed\tplanned\thalf_cycles\troom\tx\ty\n')
  local consumed_count = 0
  local planned_keys = 0
  local direction = KEY_RIGHT
  local half_cycles = 0
  emu:setBreakpoint(function()
    if phase == 'sync' then
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
    else
      assert(keys == planned_keys, string.format(
        'state patrol input mismatch at loop %d: %02X/%02X',
        main_loop_hits, keys, planned_keys))
    end

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
