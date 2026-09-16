-- Cold boot -> Stage 1 -> death dispatch -> title -> new Stage 1.
-- Default death stimulus: HP=0 once per life; optional natural-damage uses
-- movement only. No scene, bank or rendering repairs in either route.
local out = assert(os.getenv("PENTA_RESTART_OUT"))
local limit = tonumber(os.getenv("PENTA_RESTART_FRAMES") or "24000")
local traverse = os.getenv("PENTA_RESTART_TRAVERSE") == "1"
local sequence = os.getenv("PENTA_RESTART_SEQUENCE") == "1"
local natural_damage = os.getenv("PENTA_RESTART_NATURAL_DAMAGE") == "1"
local hazard_death = os.getenv("PENTA_RESTART_HAZARD_DEATH") == "1"
local saved_game = os.getenv("PENTA_RESTART_SAVED_GAME") == "1"
local travel_targets = {0x0668, 0x05AC, 0x03A4}
local travel_index, travel_wait = 1, nil
local frame, age, phase, cycles = 0, 0, "title", 0
local entered, deaths, gameovers, window_age = false, 0, 0, 0
local captured = {}
local gameover_captured = false
local card_age, selector_age = 0, 0
local watched = false
-- A frame callback can interrupt the compiler while SVBK3 is selected.
-- Observe native bank1 state physically, without changing the game's SVBK.
local wram = assert(emu.memory.wram)
local function game(address) return wram:read8(address - 0xC000) end
local trace = assert(io.open(out .. "/trace.tsv", "w"))
trace:write("frame\tphase\tscene\tactive\tlcdc\tvbk\tsvbk\thp\n")
if natural_damage or hazard_death then
  emu:setWatchpoint(function(info)
    trace:write(string.format("prelude-flag frame=%d pc=%04X bank=%02X old=%02X new=%02X scene=%02X\n",
      frame, emu:readRegister("PC"), emu:read8(0xFF99),
      info.oldValue or 0, info.newValue or info.value or 0, game(0xD880)))
    trace:flush()
  end, 0xFF91, C.WATCHPOINT_TYPE.WRITE)
end
local function dump(name, reader, first, count)
  local f = assert(io.open(out .. "/" .. name, "wb"))
  for i = first, first + count - 1 do f:write(string.char(reader(i))) end
  f:close()
end
local function snapshot(name)
  if captured[name] then return end
  captured[name] = true
  emu:screenshot(out .. "/" .. name .. ".png")
  assert(emu:saveStateFile(out .. "/" .. name .. ".ss0") ~= false,
    "diagnostic state capture failed")
  local vram = assert(emu.memory.vram)
  dump(name .. ".chr", function(i) return vram:read8(i) end, 0x1000, 0x800)
  dump(name .. ".maps", function(i) return vram:read8(i) end, 0x1800, 0x800)
  -- Do not assume the scripting VRAM view exposes a second bank at +0x2000.
  -- Native screenshots supply colour evidence without writes to VBK/CRAM.
  dump(name .. ".room", function(i) return emu:read8(i) end, 0xC1A0, 576)
  local f = assert(io.open(out .. "/" .. name .. ".context", "w"))
  f:write(string.format("%02X:%02X:%02X:%02X:%02X\n", game(0xD880),
    emu:read8(0xFFC1), emu:read8(0xFF42), emu:read8(0xFF43), emu:read8(0xFFBD)))
  f:close()
end
local function finish(status)
  emu:setKeys(0)
  local f = assert(io.open(out .. "/route.txt", "w"))
  f:write(string.format("%s %d %d %d\n", status, cycles, deaths, gameovers))
  f:close(); trace:close(); os.exit(status == "ok" and 0 or 2)
end
local function change(next_phase)
  phase, age = next_phase, 0
  if next_phase == "start" then card_age, selector_age = 0, 0 end
  if next_phase == "stage" then travel_index, travel_wait = 1, nil end
end
callbacks:add("frame", function()
  frame, age = frame + 1, age + 1
  if not watched and frame > 120 and os.getenv("PENTA_RESTART_WATCH") == "1" then
    watched = true
    emu:setWatchpoint(function(info)
      if (emu:read8(0xFF70) & 7) <= 1 then
        if info.oldValue == 0x17 and (info.newValue or info.value) == 0 then
          local sp = emu:readRegister("SP")
          trace:write(string.format("gameover-exit sp=%04X stack=", sp))
          for i = 0, 15 do trace:write(string.format("%02X", emu:read8(sp+i))) end
          trace:write("\n")
        end
        trace:write(string.format("scene-write frame=%d pc=%04X bank=%02X old=%02X new=%02X\n",
          frame, emu:readRegister("PC"), emu:read8(0xFF99),
          (info.oldValue or 0) & 255, (info.newValue or info.value or 0) & 255))
        trace:flush()
      end
    end, 0xD880, C.WATCHPOINT_TYPE.WRITE)
    emu:setWatchpoint(function(info)
      if game(0xD880) == 1 and (emu:read8(0xFF4F) & 1) == 1 then
        trace:write(string.format("footer-write frame=%d pc=%04X bank=%02X old=%02X new=%02X\n",
          frame, emu:readRegister("PC"), emu:read8(0xFF99),
          (info.oldValue or 0) & 255, (info.newValue or info.value or 0) & 255))
        trace:flush()
      end
    end, 0x9A45, C.WATCHPOINT_TYPE.WRITE)
  end
  local scene, active = game(0xD880), emu:read8(0xFFC1)
  local lcdc = emu:read8(0xFF40)
  trace:write(string.format("%d\t%s\t%02X\t%02X\t%02X\t%02X\t%02X\t%02X\n",
    frame, phase, scene, active, lcdc, emu:read8(0xFF4F),
    emu:read8(0xFF70), game(0xDCBB)))
  trace:flush()
  local keys = 0
  if phase == "title" then
    if scene ~= 1 then age = 0 end
    if sequence and age >= 60 and age <= 300 then
      emu:screenshot(string.format("%s/sequence-title-%d-%04d.png", out, cycles, age))
    end
    if age == 300 then
      snapshot(cycles == 0 and "title-before" or "title-after-" .. cycles)
      change("start")
    end
  elseif phase == "start" then
    -- Fixture precondition only: expose native saved-game stage selection.
    -- Stop before the selector runs; never repair scene/rendering state.
    if saved_game and age <= 40 then emu:write8(0xDCFD, 1) end
    -- Issue #9 reports both the score/level selector (scene 0) and the
    -- plain Stage 01 splash (scene $18). Capture each on every restart.
    if saved_game and scene == 0 then
      selector_age = selector_age + 1
      if selector_age == 100 then
        snapshot(cycles == 0 and "stage-selector-before" or "stage-selector-after-" .. cycles)
      end
    end
    if scene == 0x18 then
      card_age = card_age + 1
      if card_age == 60 then
        snapshot(cycles == 0 and "stage-card-before" or "stage-card-after-" .. cycles)
      end
    end
    for _, p in ipairs({{1,0x80},{14,1},{62,1},{112,1},{162,8},{212,1}}) do
      if age >= p[1] and age < p[1]+6 then keys = p[2] end
    end
    if scene == 2 and active == 1 then change("stage") end
  elseif phase == "stage" then
    if scene ~= 2 or active ~= 1 then return finish("stage-left-before-checkpoint") end
    if age == 120 then
      snapshot(cycles == 0 and "stage-before" or "stage-after-" .. cycles)
    end
    if traverse and age > 120 and travel_index <= #travel_targets then
      keys = 0x41
      local camera = game(0xDC02) | (game(0xDC03) << 8)
      if camera == travel_targets[travel_index] and emu:read8(0xFFBD) == 1 then
        travel_wait = travel_wait or age
      end
      if travel_wait then
        keys = 0
        if age - travel_wait >= 16 then
          snapshot(string.format("travel-%04X", travel_targets[travel_index]) ..
            (cycles == 0 and "-before" or "-after-" .. cycles))
          travel_index, travel_wait = travel_index + 1, nil
        end
      end
    end
    if (traverse and travel_index > #travel_targets) or (not traverse and age == 120) then
      if cycles == 2 then return finish("ok") end
      entered, window_age, gameover_captured = false, 0, false
      if natural_damage or hazard_death then
        change("await-damage")
      else
        deaths = deaths + 1
        wram:write8(0x1CBB, 0)
        change("death")
      end
    end
  elseif phase == "await-damage" then
    -- Diagnostic movement only; stop in the first hazard lane rather than
    -- walking through the whole stage into a different scene.
    local approach = tonumber(os.getenv("PENTA_RESTART_SPIKE_WALK") or "1600")
    keys = age <= approach and 0x40 or 0
    if os.getenv("PENTA_RESTART_SPIKE_OSCILLATE") == "1" and age > approach then
      keys = (age - approach) % 240 < 120 and 0x40 or 0x80
    end
    if age % 120 == 0 then snapshot("spike-route-" .. cycles .. "-" .. age) end
    local wait_disarm = os.getenv("PENTA_RESTART_WAIT_DISARM") == "1"
    if hazard_death and ((not wait_disarm and age == approach + 30)
        or (wait_disarm and age > approach and emu:read8(0xFF91) == 0)) then
      snapshot("hazard-before-death-" .. cycles)
      wram:write8(0x1CBB, 0)
      deaths = deaths + 1
      change("death")
    end
    if scene == 0x17 then
      keys, entered, deaths = 0, true, deaths + 1
      change("death")
    end
  elseif phase == "death" then
    if scene == 0x17 then entered = true end
    if entered and (lcdc & 0x20) ~= 0 and emu:read8(0xFF47) == 0xE4 then
      window_age = window_age + 1
      if window_age == 10 and not gameover_captured then
        gameover_captured = true
        gameovers = gameovers + 1
        snapshot("gameover-" .. gameovers)
      end
      if sequence and window_age >= 10 and window_age <= 60 then
        emu:screenshot(string.format("%s/sequence-gameover-%d-%04d.png", out, gameovers, window_age))
      end
    else window_age = 0 end
    if gameover_captured and (not sequence or window_age >= 60)
        and age > 300 and age % 120 < 6 then keys = 8 end
    if entered and scene == 1 then
      if gameovers <= cycles then return finish("title-without-gameover") end
      cycles = cycles + 1
      change("title")
    elseif entered and scene == 2 and active == 1 then
      -- Native Continue restored gameplay. Exhaust the next life naturally.
      change("stage")
    end
  end
  emu:setKeys(keys)
  if frame >= limit then finish("timeout-" .. phase) end
end)
