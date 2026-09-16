-- Exact-r287 same-process Stage-4 lazy-departure lifecycle probe.
--
-- The matching Python verifier is the only supported launcher.  This probe
-- cold-boots the game's native level-select route into Stage 4, observes the
-- production installer and hot helper, saves that naturally armed state, and
-- uses it twice in the same emulator process.  The first replay proves the
-- Stage4->Stage5 lazy reset and subsequent native path.  The second proves the
-- Stage4->Stage7 reset while preserving and executing the exact Stage-7
-- router.  Finally, the process reloads its own pre-install cold state and
-- follows the native title/level-select route into fresh Stage 1.
--
-- Harness writes are limited to the established level-select/alive controls,
-- temporary stage identity for the two deterministic departure calls, one
-- cache-byte mismatch used to force the Stage-7 dirty route, and CPU input.

local OUT = assert(os.getenv("STAGE4_LIFECYCLE_OUT"),
  "STAGE4_LIFECYCLE_OUT required")
local DONE = assert(os.getenv("STAGE4_LIFECYCLE_DONE"),
  "STAGE4_LIFECYCLE_DONE required")
local COLD_STATE = assert(os.getenv("STAGE4_LIFECYCLE_COLD_STATE"),
  "STAGE4_LIFECYCLE_COLD_STATE required")
local ARMED_STATE = assert(os.getenv("STAGE4_LIFECYCLE_ARMED_STATE"),
  "STAGE4_LIFECYCLE_ARMED_STATE required")

local SCHEMA = "penta-stage4-lazy-lifecycle-r287-probe-v1"
local KEY_A, KEY_START, KEY_DOWN = 0x01, 0x08, 0x80
local STAGE4_TARGET, STAGE1_TARGET = 3, 0
local STAGE4_SCENE, STAGE1_SCENE = 0x05, 0x02
local LIMIT = tonumber(os.getenv("STAGE4_LIFECYCLE_FRAME_LIMIT") or "12000")

local PAYLOAD = {
  0x3E,0x60,0xEA,0xD5,0xDA,0xFA,0x80,0xD8,0xD6,0x03,0xC3,0x60,0xDA,
  0x00,0x00,0x00,0x00,0x00,0x00,0xC9,
  0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
  0xF0,0xBA,0xFE,0x03,0x20,0xDA,
  0xC5,0xD5,0xE5,0xAF,0xE0,0xE0,0x7C,0xEE,0xCB,0x5F,0x16,0xDF,
  0x21,0xF1,0xC1,0x46,0x24,0x4E,0xCD,0x0D,0xDB,0xC3,0x92,0xDA,
}
local TRAMPOLINE = {0xC3,0x20,0xDB}
local ROUTER = {
  0xE1,0xD1,0xC1,0xF5,0xFA,0x80,0xD8,0xFE,0x08,0x28,0x02,0x18,0x00,
  0xF3,0xF1,0xF1,0xF1,0x3E,0x16,0xC3,0x47,0x08,
}

local frame = 0
local phase = "boot-stage4"
local epoch = "stage4"
local route_tick, route_target, route_scene = 0, STAGE4_TARGET, STAGE4_SCENE
local route_phase, route_seeded, route_confirmed = "title", false, false
local route_stable = 0
local finished = false
local hook_generation = 0
local breakpoint_failures, watchpoint_failures = 0, 0
local suppress_watch = false
local cold_save_requested, armed_save_requested = false, false
local cold_loads, armed_loads = 0, 0
local state_last_size, state_stable_frames = -1, 0
local stage4_entry_seen, installer_committed = false, false
local installer_checkpoint_index = 0
local ownership_active = false
local stage1_steady_active, stage1_steady_db_writes = false, 0
local helper_active = false
local case_state = "none"
local case_sequence = {}
local case_deadline = 0
local stage5_db_writes_at_start, stage7_db_writes_at_start = 0, 0
local atomic_events, db_writes, events = {}, {}, {}
local metrics = {
  schema=SCHEMA, same_process="1", natural_stage4_install="0",
  title_reset_seen="0", stage1_stable="0",
}
local hits = {stage4={}, stage5={}, stage7={}, stage1={}}

local function reg(name)
  for _, reader in ipairs({
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
  }) do
    local ok, value = pcall(reader)
    if ok and type(value) == "number" then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function normalized_svbk()
  local bank = emu:read8(0xFF70) & 7
  if bank == 0 then return 1 end
  return bank
end

local function remember(kind, detail)
  if #events < 160 then
    detail = tostring(detail or ""):gsub("[\r\n=]", "_")
    events[#events + 1] = string.format(
      "%s|f%d|phase:%s|pc:%04X|rom:%02X|svbk:%d|%s",
      kind, frame, phase, reg("PC"), emu:read8(0xFF99),
      normalized_svbk(), detail)
  end
end

local function set_metric(name, value)
  metrics[name] = tostring(value)
end

local function finish(status, message)
  if finished then return end
  finished = true
  metrics.status = status
  metrics.message = tostring(message):gsub("[\r\n=]", "_")
  metrics.frames = tostring(frame)
  metrics.breakpoint_failures = tostring(breakpoint_failures)
  metrics.watchpoint_failures = tostring(watchpoint_failures)
  metrics.cold_state_save_requested = cold_save_requested and "1" or "0"
  metrics.armed_state_save_requested = armed_save_requested and "1" or "0"
  metrics.cold_state_loads = tostring(cold_loads)
  metrics.armed_state_loads = tostring(armed_loads)
  metrics.db_install_write_count = tostring(#db_writes)
  metrics.event_count = tostring(#events)
  local keys = {}
  for key in pairs(metrics) do keys[#keys + 1] = key end
  table.sort(keys)
  local report = assert(io.open(OUT, "w"))
  for _, key in ipairs(keys) do
    report:write(key .. "=" .. metrics[key] .. "\n")
  end
  for _, event in ipairs(events) do report:write("event=" .. event .. "\n") end
  report:close()
  local marker = assert(io.open(DONE, "w"))
  marker:write(status .. "\t" .. metrics.message .. "\n")
  marker:close()
  emu:setKeys(0)
  emu:stop()
end

local function require_live(condition, message)
  if condition then return true end
  remember("failure", message)
  finish("FAIL", message)
  return false
end

local function with_bank1(callback)
  local old = normalized_svbk()
  emu:write8(0xFF70, 1)
  local result = callback()
  emu:write8(0xFF70, old)
  return result
end

local function bank1_bytes(first, count)
  return with_bank1(function()
    local result = {}
    for offset = 0, count - 1 do
      result[#result + 1] = emu:read8(first + offset)
    end
    return result
  end)
end

local function bytes_equal(actual, expected)
  if #actual ~= #expected then return false end
  for index, value in ipairs(expected) do
    if actual[index] ~= value then return false end
  end
  return true
end

local function all_zero(actual)
  for _, value in ipairs(actual) do if value ~= 0 then return false end end
  return true
end

local function hex_bytes(actual)
  local parts = {}
  for _, value in ipairs(actual) do parts[#parts + 1] = string.format("%02X", value) end
  return table.concat(parts)
end

local function payload_snapshot()
  local db = bank1_bytes(0xDB00, 0x80)
  local trampoline = bank1_bytes(0xDA5D, 3)
  local router = bank1_bytes(0xDAE9, #ROUTER)
  local payload_ok = true
  for index, value in ipairs(PAYLOAD) do
    if db[index] ~= value then payload_ok = false end
  end
  for index = #PAYLOAD + 1, #db do
    if db[index] ~= 0 then payload_ok = false end
  end
  return {
    db=db, trampoline=trampoline, router=router,
    payload_ok=payload_ok,
    trampoline_ok=bytes_equal(trampoline, TRAMPOLINE),
    router_ok=bytes_equal(router, ROUTER),
    dad5=bank1_bytes(0xDAD5, 1)[1],
    dab7=bank1_bytes(0xDAB7, 1)[1],
  }
end

local function seed_sram()
  emu:write8(0x0000, 0x0A)
  for _, base in ipairs({0xBF00,0xBF28,0xBF50,0xBF78,0xBFA0,0xBFC8}) do
    emu:write8(base, 0xFF)
    for index = 1, 0x1F do emu:write8(base + index, 0x00) end
  end
end

local function complete_state_size(path)
  local handle = io.open(path, "rb")
  if not handle then return nil end
  local size = handle:seek("end")
  if not size or size < 1024 then handle:close(); return nil end
  handle:seek("set", size - 12)
  local tail = handle:read(12)
  handle:close()
  if not tail or #tail ~= 12 or tail:sub(5, 8) ~= "IEND" then return nil end
  return size
end

local function state_stable(path)
  local size = complete_state_size(path)
  if size and size == state_last_size then
    state_stable_frames = state_stable_frames + 1
  elseif size then
    state_last_size, state_stable_frames = size, 1
  else
    state_last_size, state_stable_frames = -1, 0
  end
  return state_stable_frames >= 2
end

local function reset_state_wait()
  state_last_size, state_stable_frames = -1, 0
end

local function count_hit(name)
  local bucket = hits[epoch]
  bucket[name] = (bucket[name] or 0) + 1
end

local function hit_count(which_epoch, name)
  return hits[which_epoch][name] or 0
end

local function reset_hits(which_epoch)
  hits[which_epoch] = {}
end

local function append_case(name)
  case_sequence[#case_sequence + 1] = name
end

local function sequence_is(expected)
  if #case_sequence ~= #expected then return false end
  for index, value in ipairs(expected) do
    if case_sequence[index] ~= value then return false end
  end
  return true
end

local function info_value(info)
  if info.newValue ~= nil then return info.newValue & 0xFF end
  if info.value ~= nil then return info.value & 0xFF end
  return emu:read8(info.address & 0xFFFF)
end

local function expected_atomic_install(stage)
  local expected = {}
  if stage >= 1 then expected[#expected + 1] = "DAB7:EB" end
  if stage >= 2 then expected[#expected + 1] = "DAD5:60" end
  if stage >= 3 then
    for index, value in ipairs(PAYLOAD) do
      expected[#expected + 1] = string.format("DB%02X:%02X", index - 1, value)
    end
  end
  if stage >= 4 then
    expected[#expected + 1] = "DA5D:C3"
    expected[#expected + 1] = "DA5E:20"
    expected[#expected + 1] = "DA5F:DB"
  end
  if stage >= 5 then expected[#expected + 1] = "DAD5:5D" end
  return expected
end

local function validate_atomic_install_prefix(stage)
  local expected = expected_atomic_install(stage)
  if #atomic_events ~= #expected then return false end
  for index, value in ipairs(expected) do
    if atomic_events[index] ~= value then return false end
  end
  if stage < 3 then
    if #db_writes ~= 0 then return false end
  else
    if #db_writes ~= #PAYLOAD then return false end
    for index, row in ipairs(db_writes) do
      if row.address ~= 0xDAFF + index or row.value ~= PAYLOAD[index] then
        return false
      end
    end
  end
  return true
end

local function validate_atomic_install()
  return installer_checkpoint_index == 5
    and validate_atomic_install_prefix(5)
end

local function pin_departure_identity(target, scene, prior_scene, label)
  local prior_target, observed_prior_scene =
    emu:read8(0xFFBA), emu:read8(0xD880)
  if not require_live(prior_target == target
      and observed_prior_scene == prior_scene,
      label .. "-pre-pin-identity-wrong") then return false end
  set_metric(label .. "_pre_pin_identity_at_dad4",
    string.format("%02X/%02X", prior_target, observed_prior_scene))
  emu:write8(0xFFBA, target)
  emu:write8(0xD880, scene)
  if not require_live(emu:read8(0xFFBA) == target
      and emu:read8(0xD880) == scene,
      label .. "-identity-pin-failed") then return false end
  set_metric(label .. "_identity_at_dad4",
    string.format("%02X/%02X", target, scene))
  return true
end

local function stage4_entry(name)
  if finished then return end
  if epoch ~= "stage4" then
    count_hit(name)
    return
  end
  if not stage4_entry_seen then
    local before = bank1_bytes(0xDB00, 0x80)
    if not require_live(all_zero(before), "stage4-preinstall-db-not-zero") then return end
    stage4_entry_seen = true
    installer_committed = false
    installer_checkpoint_index = 0
    ownership_active = true
    atomic_events, db_writes = {}, {}
    reset_hits("stage4")
    remember("stage4-entry", name)
  end
  count_hit(name)
end

local function on_hit(name)
  if finished then return end
  if name == "entry13" or name == "entry16" then
    stage4_entry(name)
    return
  end
  count_hit(name)

  if name == "installer" and epoch == "stage4" then
    local snap = payload_snapshot()
    if not require_live(stage4_entry_seen and ownership_active,
        "installer-before-stage4-entry") then return end
    if not require_live(installer_checkpoint_index == 0
        and validate_atomic_install_prefix(0),
        "installer-entry-order-wrong") then return end
    if not require_live(snap.dad5 == 0x60 and snap.dab7 == 0xEB
        and all_zero(snap.db) and all_zero(snap.trampoline) and snap.router_ok,
        "installer-did-not-enter-native") then return end
    remember("installer-entry", "bank22:6000")
    return
  end

  if name == "installer_pc_6005" and epoch == "stage4" then
    local snap = payload_snapshot()
    if not require_live(stage4_entry_seen and ownership_active
        and not installer_committed and installer_checkpoint_index == 0,
        "installer-pc-6005-order") then return end
    if not require_live(snap.dab7 == 0xEB and snap.dad5 == 0x60
        and all_zero(snap.db) and all_zero(snap.trampoline) and snap.router_ok
        and validate_atomic_install_prefix(0),
        "installer-pc-6005-state") then return end
    atomic_events[#atomic_events + 1] = "DAB7:EB"
    installer_checkpoint_index = 1
    if not require_live(validate_atomic_install_prefix(1),
        "installer-pc-6005-prefix") then return end
    remember("installer-checkpoint", "bank22:6005:DAB7=EB")
    return
  end

  if name == "installer_pc_600A" and epoch == "stage4" then
    local snap = payload_snapshot()
    if not require_live(stage4_entry_seen and ownership_active
        and not installer_committed and installer_checkpoint_index == 1,
        "installer-pc-600A-order") then return end
    if not require_live(snap.dab7 == 0xEB and snap.dad5 == 0x60
        and all_zero(snap.db) and all_zero(snap.trampoline) and snap.router_ok
        and validate_atomic_install_prefix(1),
        "installer-pc-600A-state") then return end
    atomic_events[#atomic_events + 1] = "DAD5:60"
    installer_checkpoint_index = 2
    if not require_live(validate_atomic_install_prefix(2),
        "installer-pc-600A-prefix") then return end
    remember("installer-checkpoint", "bank22:600A:DAD5=60")
    return
  end

  if name == "installer_pc_6018" and epoch == "stage4" then
    local snap = payload_snapshot()
    if not require_live(stage4_entry_seen and ownership_active
        and not installer_committed and installer_checkpoint_index == 2,
        "installer-pc-6018-order") then return end
    if not require_live(snap.dab7 == 0xEB and snap.dad5 == 0x60
        and snap.payload_ok and all_zero(snap.trampoline) and snap.router_ok
        and validate_atomic_install_prefix(3),
        "installer-pc-6018-state") then return end
    installer_checkpoint_index = 3
    remember("installer-checkpoint", "bank22:6018:DB00-DB3D-exact")
    return
  end

  if name == "installer_pc_6024" and epoch == "stage4" then
    local snap = payload_snapshot()
    if not require_live(stage4_entry_seen and ownership_active
        and not installer_committed and installer_checkpoint_index == 3,
        "installer-pc-6024-order") then return end
    if not require_live(snap.dab7 == 0xEB and snap.dad5 == 0x60
        and snap.payload_ok and snap.trampoline_ok and snap.router_ok
        and validate_atomic_install_prefix(3),
        "installer-pc-6024-state") then return end
    atomic_events[#atomic_events + 1] = "DA5D:C3"
    atomic_events[#atomic_events + 1] = "DA5E:20"
    atomic_events[#atomic_events + 1] = "DA5F:DB"
    installer_checkpoint_index = 4
    if not require_live(validate_atomic_install_prefix(4),
        "installer-pc-6024-prefix") then return end
    remember("installer-checkpoint", "bank22:6024:DA5D-DA5F-exact")
    return
  end

  if name == "installer_pc_6029" and epoch == "stage4" then
    local snap = payload_snapshot()
    if not require_live(stage4_entry_seen and ownership_active
        and not installer_committed and installer_checkpoint_index == 4,
        "installer-pc-6029-order") then return end
    if not require_live(snap.dab7 == 0xEB and snap.dad5 == 0x5D
        and snap.payload_ok and snap.trampoline_ok and snap.router_ok
        and validate_atomic_install_prefix(4),
        "installer-pc-6029-state") then return end
    atomic_events[#atomic_events + 1] = "DAD5:5D"
    installer_checkpoint_index = 5
    if not require_live(validate_atomic_install_prefix(5),
        "installer-pc-6029-prefix") then return end
    installer_committed = true
    remember("installer-checkpoint", "bank22:6029:DAD5=5D:committed")
    return
  end

  if epoch == "stage5" then
    if case_state == "stage5-first" then
      append_case(name)
      if name == "DAD4" then
        if not pin_departure_identity(0x04, 0x06, 0x05, "stage5") then return end
        require_live(bank1_bytes(0xDAD5, 1)[1] == 0x5D,
          "stage5-first-dad5-not-armed")
      elseif name == "DB00" then
        set_metric("stage5_guard_a", string.format("%02X", reg("A") & 0xFF))
        require_live((reg("A") & 0xFF) == 0x04
          and emu:read8(0xD880) == 0x06,
          "stage5-guard-or-scene-wrong")
      elseif name == "DA60" then
        set_metric("stage5_normalized_a", string.format("%02X", reg("A") & 0xFF))
        require_live((reg("A") & 0xFF) == 0x03
          and emu:read8(0xD880) == 0x06,
          "stage5-normalized-a-or-scene-wrong")
        require_live(bank1_bytes(0xDAD5, 1)[1] == 0x60,
          "stage5-dad5-not-restored-before-native")
        require_live(bank1_bytes(0xDAB7, 1)[1] == 0xEB,
          "stage5-dab7-not-native")
        emu:write8(0xFFBA, STAGE4_TARGET)
        emu:write8(0xD880, STAGE4_SCENE)
      elseif name == "DA92" then
        case_state = "stage5-later"
      end
    elseif case_state == "stage5-later" then
      if name == "DAD4" then
        case_sequence = {"DAD4"}
        case_state = "stage5-later-active"
        require_live(bank1_bytes(0xDAD5, 1)[1] == 0x60,
          "stage5-later-dad5-not-native")
      end
    elseif case_state == "stage5-later-active" then
      append_case(name)
      if name == "DA5D" or name == "DB20" or name == "DB00" then
        finish("FAIL", "stage5-later-reentered-lazy-path")
      elseif name == "DA92" then
        case_state = "stage5-done"
      end
    end
    return
  end

  if epoch == "stage7" and case_state == "stage7-first" then
    append_case(name)
    if name == "DAD4" then
      if not pin_departure_identity(0x06, 0x08, 0x05, "stage7") then return end
      require_live(bank1_bytes(0xDAD5, 1)[1] == 0x5D,
        "stage7-first-dad5-not-armed")
    elseif name == "DB00" then
      set_metric("stage7_guard_a", string.format("%02X", reg("A") & 0xFF))
      require_live((reg("A") & 0xFF) == 0x06
        and emu:read8(0xD880) == 0x08,
        "stage7-guard-or-scene-wrong")
    elseif name == "DA60" then
      set_metric("stage7_normalized_a", string.format("%02X", reg("A") & 0xFF))
      require_live((reg("A") & 0xFF) == 0x05
        and emu:read8(0xD880) == 0x08,
        "stage7-normalized-a-or-scene-wrong")
      require_live(bank1_bytes(0xDAD5, 1)[1] == 0x60,
        "stage7-dad5-not-restored-before-native")
      require_live(bank1_bytes(0xDAB7, 1)[1] == 0x31,
        "stage7-arm-lost-at-native-entry")
    elseif name == "DA92" then
      local pointer, key = reg("DE"), (reg("B") + 1) & 0xFF
      require_live(pointer >= 0xD000 and pointer <= 0xDFFF,
        "stage7-cache-pointer-outside-wram")
      suppress_watch = true
      emu:write8(pointer, key)
      suppress_watch = false
      set_metric("stage7_forced_dirty_address", string.format("%04X", pointer))
    elseif name == "DAE9" then
      local snap = payload_snapshot()
      require_live(snap.router_ok, "stage7-live-router-bytes-changed")
      require_live(snap.dad5 == 0x60 and snap.dab7 == 0x31,
        "stage7-router-entry-state-wrong")
      set_metric("stage7_router_exact_live", "1")
    elseif name == "stage7_helper" then
      helper_active = true
      require_live(emu:read8(0xFF99) == 0x16,
        "stage7-helper-bank-not-22")
      require_live(emu:read8(0xD880) == 0x08 and emu:read8(0xFFBA) == 0x06,
        "stage7-helper-identity-wrong")
    elseif name == "stage7_disarm" then
      finish("FAIL", "stage7-router-self-disarmed")
    elseif name == "stage7_fallback" then
      finish("FAIL", "stage7-helper-fell-back")
    elseif name == "stage7_fast" then
      require_live(helper_active, "stage7-fast-before-helper")
    elseif name == "stage7_exit" and helper_active then
      require_live(bank1_bytes(0xDAD5, 1)[1] == 0x60,
        "stage7-dad5-changed-at-exit")
      require_live(bank1_bytes(0xDAB7, 1)[1] == 0x31,
        "stage7-arm-not-preserved-at-exit")
      helper_active = false
      emu:write8(0xFFBA, STAGE4_TARGET)
      emu:write8(0xD880, STAGE4_SCENE)
      case_state = "stage7-done"
    end
  end
end

local function add_breakpoint(name, address, segment)
  local generation = hook_generation
  local callback = function()
    if generation == hook_generation and not finished then on_hit(name) end
  end
  local ok, result
  if segment ~= nil then
    ok, result = pcall(function()
      return emu:setBreakpoint(callback, address, segment)
    end)
  else
    ok, result = pcall(function() return emu:setBreakpoint(callback, address) end)
  end
  if not ok or type(result) ~= "number" or result <= 0 then
    breakpoint_failures = breakpoint_failures + 1
    remember("breakpoint-failure", string.format("%s:%04X", name, address))
  end
end

local function add_watch(first, last, callback, label)
  local generation = hook_generation
  local ok, result = pcall(function()
    return emu:setRangeWatchpoint(function(info)
      if generation == hook_generation and not finished then callback(info) end
    end, first, last, C.WATCHPOINT_TYPE.WRITE)
  end)
  if not ok or type(result) ~= "number" or result <= 0 then
    watchpoint_failures = watchpoint_failures + 1
    remember("watchpoint-failure", label)
  end
end

local function install_hooks()
  hook_generation = hook_generation + 1
  add_breakpoint("entry13", 0x7C22, 13)
  add_breakpoint("entry16", 0x7C22, 16)
  add_breakpoint("installer", 0x6000, 22)
  add_breakpoint("installer_pc_6005", 0x6005, 22)
  add_breakpoint("installer_pc_600A", 0x600A, 22)
  add_breakpoint("installer_pc_6018", 0x6018, 22)
  add_breakpoint("installer_pc_6024", 0x6024, 22)
  add_breakpoint("installer_pc_6029", 0x6029, 22)
  add_breakpoint("DAD4", 0xDAD4)
  add_breakpoint("DA5D", 0xDA5D)
  add_breakpoint("DB20", 0xDB20)
  add_breakpoint("DB00", 0xDB00)
  add_breakpoint("DB0D", 0xDB0D)
  add_breakpoint("DA60", 0xDA60)
  add_breakpoint("DA92", 0xDA92)
  add_breakpoint("DAE9", 0xDAE9)
  add_breakpoint("stage7_helper", 0x6C80, 22)
  add_breakpoint("stage7_fast", 0x6CE8, 22)
  add_breakpoint("stage7_fallback", 0x71B3, 22)
  add_breakpoint("stage7_disarm", 0x7233, 22)
  add_breakpoint("stage7_exit", 0x436D, 1)

  add_watch(0xDB00, 0xDB7F, function(info)
    if suppress_watch or normalized_svbk() ~= 1 then return end
    local address, value = info.address & 0xFFFF, info_value(info)
    if ownership_active then
      db_writes[#db_writes + 1] = {address=address, value=value}
      if not installer_committed then
        atomic_events[#atomic_events + 1] = string.format(
          "DB%02X:%02X", address - 0xDB00, value)
      end
    end
    if stage1_steady_active then stage1_steady_db_writes = stage1_steady_db_writes + 1 end
  end, "DB00-DB7F")
end

local function init_route(target, scene)
  route_tick, route_target, route_scene = 0, target, scene
  route_phase, route_seeded, route_confirmed = "title", false, false
  route_stable = 0
end

local function route_frame()
  route_tick = route_tick + 1
  if not route_seeded and route_tick >= 100 then
    seed_sram()
    route_seeded = true
  end

  if route_target == STAGE1_TARGET and route_tick == 120 then
    local title_db = bank1_bytes(0xDB00, 0x80)
    if not require_live(all_zero(title_db), "title-reset-db-not-zero") then return end
    set_metric("title_reset_seen", "1")
    set_metric("title_reset_db_zero", "1")
    remember("title-reset", "cold-state-reload")
  end

  if route_phase == "title" then
    if route_tick >= 180 and route_tick < 186 then emu:setKeys(KEY_DOWN)
    elseif route_tick >= 193 and route_tick < 199 then emu:setKeys(KEY_A)
    elseif route_tick >= 241 and route_tick < 247 then emu:setKeys(KEY_A)
    elseif route_tick >= 291 and route_tick < 297 then emu:setKeys(KEY_A)
    elseif route_tick >= 341 and route_tick < 347 then emu:setKeys(KEY_START)
    elseif route_tick >= 391 and route_tick < 397 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if route_tick >= 450 then route_phase = "level-select" end
    return
  end

  if route_phase == "level-select" and not route_confirmed then
    emu:write8(0xDCFD, 0x01)
    emu:write8(0xFFBA, route_target)
    seed_sram()
    if route_tick % 60 >= 10 and route_tick % 60 < 16 then emu:setKeys(KEY_A)
    else emu:setKeys(0) end
    if emu:read8(0xD880) == 0x18 or emu:read8(0xFFC1) == 1 then
      route_confirmed = true
      route_phase = "loading"
      remember("level-selected", string.format("target:%d", route_target))
    end
    if route_tick > 900 then finish("FAIL", "level-select-timeout") end
    return
  end

  emu:setKeys(0)
  emu:write8(0xDCDD, 0x17)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xFFBA, route_target)
  if emu:read8(0xD880) == route_scene and emu:read8(0xFFC1) == 1 then
    route_stable = route_stable + 1
  end
end

local function validate_stage4_and_save()
  local snap = payload_snapshot()
  if not require_live(stage4_entry_seen and installer_committed,
      "stage4-installer-not-committed") then return end
  if not require_live(hit_count("stage4", "installer") == 1,
      "stage4-installer-hit-count") then return end
  if not require_live(installer_checkpoint_index == 5
      and hit_count("stage4", "installer_pc_6005") == 1
      and hit_count("stage4", "installer_pc_600A") == 1
      and hit_count("stage4", "installer_pc_6018") == 1
      and hit_count("stage4", "installer_pc_6024") == 1
      and hit_count("stage4", "installer_pc_6029") == 1,
      "stage4-installer-checkpoint-cardinality") then return end
  if not require_live(hit_count("stage4", "DAD4") > 0
      and hit_count("stage4", "DA5D") > 0
      and hit_count("stage4", "DB20") > 0
      and hit_count("stage4", "DB0D") > 0
      and hit_count("stage4", "DA92") > 0,
      "stage4-hot-route-missing") then return end
  if not require_live(hit_count("stage4", "DB00") == 0
      and hit_count("stage4", "DA60") == 0
      and hit_count("stage4", "DAE9") == 0,
      "stage4-hot-route-escaped") then return end
  if not require_live(validate_atomic_install(), "stage4-atomic-install-order") then return end
  if not require_live(snap.payload_ok and snap.trampoline_ok and snap.router_ok,
      "stage4-armed-payload-mismatch") then return end
  if not require_live(snap.dad5 == 0x5D and snap.dab7 == 0xEB,
      "stage4-armed-operands-wrong") then return end
  set_metric("natural_stage4_install", "1")
  set_metric("stage4_entry_hits", hit_count("stage4", "entry13")
    + hit_count("stage4", "entry16"))
  set_metric("stage4_installer_hits", hit_count("stage4", "installer"))
  set_metric("stage4_installer_pc_6005", hit_count("stage4", "installer_pc_6005"))
  set_metric("stage4_installer_pc_600A", hit_count("stage4", "installer_pc_600A"))
  set_metric("stage4_installer_pc_6018", hit_count("stage4", "installer_pc_6018"))
  set_metric("stage4_installer_pc_6024", hit_count("stage4", "installer_pc_6024"))
  set_metric("stage4_installer_pc_6029", hit_count("stage4", "installer_pc_6029"))
  set_metric("installer_checkpoint_count", installer_checkpoint_index)
  set_metric("installer_checkpoint_order", "6005,600A,6018,6024,6029")
  set_metric("stage4_hot_dad4", hit_count("stage4", "DAD4"))
  set_metric("stage4_hot_da5d", hit_count("stage4", "DA5D"))
  set_metric("stage4_hot_db20", hit_count("stage4", "DB20"))
  set_metric("stage4_hot_delay", hit_count("stage4", "DB0D"))
  set_metric("stage4_hot_da92", hit_count("stage4", "DA92"))
  set_metric("stage4_hot_da60", hit_count("stage4", "DA60"))
  set_metric("stage4_hot_db00", hit_count("stage4", "DB00"))
  set_metric("stage4_payload_exact", "1")
  set_metric("stage4_trampoline_exact", "1")
  set_metric("stage4_router_exact", "1")
  set_metric("stage4_dad5", string.format("%02X", snap.dad5))
  set_metric("stage4_dab7", string.format("%02X", snap.dab7))
  set_metric("stage4_db00_db7f", hex_bytes(snap.db))
  set_metric("atomic_install_order", "1")
  set_metric("atomic_install_event_count", #atomic_events)
  set_metric("db_unexpected_writes", "0")
  local ok, result = pcall(function() return emu:saveStateFile(ARMED_STATE) end)
  if not require_live(ok and result ~= false, "armed-state-save-request-failed") then return end
  armed_save_requested = true
  reset_state_wait()
  phase = "wait-armed-state"
  emu:setKeys(0)
end

local function start_stage5()
  epoch = "stage5"
  reset_hits("stage5")
  case_sequence = {}
  case_state = "stage5-first"
  case_deadline = frame + 360
  stage5_db_writes_at_start = #db_writes
  emu:write8(0xFFBA, 0x04)
  emu:write8(0xD880, 0x06)
  phase = "stage5-departure"
  remember("departure-start", "stage5")
end

local function validate_stage5()
  local expected = {"DAD4","DA5D","DB20","DB00","DA60","DA92"}
  if not require_live(sequence_is({"DAD4","DA60","DA92"}),
      "stage5-later-sequence-wrong") then return end
  for _, name in ipairs(expected) do
    if not require_live(hit_count("stage5", name) >= 1,
        "stage5-first-missing-" .. name) then return end
  end
  if not require_live(hit_count("stage5", "DA5D") == 1
      and hit_count("stage5", "DB20") == 1
      and hit_count("stage5", "DB00") == 1
      and hit_count("stage5", "DA60") == 2
      and hit_count("stage5", "DA92") == 2,
      "stage5-first-later-cardinality") then return end
  local snap = payload_snapshot()
  if not require_live(snap.payload_ok and snap.trampoline_ok and snap.router_ok,
      "stage5-payload-not-retained") then return end
  if not require_live(snap.dad5 == 0x60 and snap.dab7 == 0xEB,
      "stage5-final-operands-wrong") then return end
  if not require_live(#db_writes == stage5_db_writes_at_start,
      "stage5-unexpected-db-write") then return end
  set_metric("stage5_first_dad4", "1")
  set_metric("stage5_first_da5d", "1")
  set_metric("stage5_first_db20", "1")
  set_metric("stage5_first_db00", "1")
  set_metric("stage5_first_da60", "1")
  set_metric("stage5_first_da92", "1")
  set_metric("stage5_later_dad4", "1")
  set_metric("stage5_later_da5d", "0")
  set_metric("stage5_later_db20", "0")
  set_metric("stage5_later_db00", "0")
  set_metric("stage5_later_da60", "1")
  set_metric("stage5_later_da92", "1")
  set_metric("stage5_restored_dad5", string.format("%02X", snap.dad5))
  set_metric("stage5_dab7", string.format("%02X", snap.dab7))
  set_metric("stage5_payload_retained", "1")
  phase = "load-armed-for-stage7"
end

local function load_state(path, kind)
  hook_generation = hook_generation + 1
  local ok, result = pcall(function() return emu:loadStateFile(path) end)
  if not require_live(ok and result ~= false, kind .. "-state-load-failed") then return end
  if kind == "armed" then armed_loads = armed_loads + 1
  else cold_loads = cold_loads + 1 end
  phase = "rehook-" .. kind
  emu:setKeys(0)
end

local function start_stage7_after_load()
  install_hooks()
  if not require_live(breakpoint_failures == 0 and watchpoint_failures == 0,
      "stage7-rehook-failed") then return end
  local snap = payload_snapshot()
  if not require_live(snap.payload_ok and snap.trampoline_ok and snap.router_ok
      and snap.dad5 == 0x5D and snap.dab7 == 0xEB,
      "armed-state-reload-mismatch") then return end
  epoch = "stage7"
  reset_hits("stage7")
  case_sequence = {}
  case_state = "stage7-first"
  case_deadline = frame + 480
  stage7_db_writes_at_start = #db_writes
  suppress_watch = true
  emu:write8(0xDAB7, 0x31)
  suppress_watch = false
  emu:write8(0xFFBA, 0x06)
  emu:write8(0xD880, 0x08)
  phase = "stage7-departure"
  remember("departure-start", "stage7")
end

local function validate_stage7()
  local expected = {
    "DAD4","DA5D","DB20","DB00","DA60","DA92","DAE9",
    "stage7_helper","stage7_fast","stage7_exit",
  }
  if not require_live(sequence_is(expected), "stage7-route-sequence-wrong") then return end
  local snap = payload_snapshot()
  if not require_live(snap.payload_ok and snap.trampoline_ok and snap.router_ok,
      "stage7-payload-not-retained") then return end
  if not require_live(snap.dad5 == 0x60 and snap.dab7 == 0x31,
      "stage7-final-operands-wrong") then return end
  if not require_live(#db_writes == stage7_db_writes_at_start,
      "stage7-unexpected-db-write") then return end
  if not require_live(hit_count("stage7", "stage7_disarm") == 0
      and hit_count("stage7", "stage7_fallback") == 0,
      "stage7-router-fallback-or-disarm") then return end
  set_metric("stage7_first_dad4", "1")
  set_metric("stage7_first_da5d", "1")
  set_metric("stage7_first_db20", "1")
  set_metric("stage7_first_db00", "1")
  set_metric("stage7_first_da60", "1")
  set_metric("stage7_first_da92", "1")
  set_metric("stage7_dae9", "1")
  set_metric("stage7_helper_entry", "1")
  set_metric("stage7_fastpath", "1")
  set_metric("stage7_exact_exit", "1")
  set_metric("stage7_disarm_hits", "0")
  set_metric("stage7_fallback_hits", "0")
  set_metric("stage7_restored_dad5", string.format("%02X", snap.dad5))
  set_metric("stage7_preserved_dab7", string.format("%02X", snap.dab7))
  set_metric("stage7_payload_retained", "1")
  phase = "load-cold-for-stage1"
end

local function start_stage1_after_load()
  ownership_active = false
  stage1_steady_active = false
  stage1_steady_db_writes = 0
  install_hooks()
  if not require_live(breakpoint_failures == 0 and watchpoint_failures == 0,
      "stage1-rehook-failed") then return end
  epoch = "stage1"
  reset_hits("stage1")
  init_route(STAGE1_TARGET, STAGE1_SCENE)
  phase = "route-stage1"
  remember("cold-reset", "title-to-stage1")
end

local function validate_stage1()
  local snap = payload_snapshot()
  if not require_live(all_zero(snap.db), "stage1-db-not-zero") then return end
  if not require_live(all_zero(snap.trampoline), "stage1-trampoline-persisted") then return end
  if not require_live(snap.router_ok and snap.dad5 == 0x60 and snap.dab7 == 0xEB,
      "stage1-native-runtime-wrong") then return end
  if not require_live(hit_count("stage1", "entry13") == 0
      and hit_count("stage1", "entry16") == 0
      and hit_count("stage1", "installer") == 0
      and hit_count("stage1", "DAD4") == 0
      and hit_count("stage1", "DA5D") == 0
      and hit_count("stage1", "DB20") == 0
      and hit_count("stage1", "DB00") == 0,
      "stage1-touched-stage4-route") then return end
  if not require_live(stage1_steady_db_writes == 0,
      "stage1-steady-db-write") then return end
  if not require_live(metrics.title_reset_seen == "1",
      "title-reset-snapshot-missing") then return end
  set_metric("stage1_stable", "1")
  set_metric("stage1_dad5", string.format("%02X", snap.dad5))
  set_metric("stage1_dab7", string.format("%02X", snap.dab7))
  set_metric("stage1_db_zero", "1")
  set_metric("stage1_trampoline_zero", "1")
  set_metric("stage1_router_exact", "1")
  set_metric("stage1_dad4_hits", hit_count("stage1", "DAD4"))
  set_metric("stage1_db20_hits", hit_count("stage1", "DB20"))
  set_metric("stage1_steady_db_writes", stage1_steady_db_writes)
  set_metric("stage1_db00_db7f", hex_bytes(snap.db))
  set_metric("no_unexpected_db_writes", "1")
  set_metric("payload_exact_while_armed", "1")
  set_metric("lazy_reset_stage5", "1")
  set_metric("lazy_reset_stage7", "1")
  set_metric("later_native_path", "1")
  set_metric("stage7_router_preserved", "1")
  set_metric("cold_title_stage1_reset", "1")
  finish("PASS", "same-process-stage4-lazy-lifecycle")
end

install_hooks()

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  if frame > LIMIT then finish("FAIL", "global-frame-timeout"); return end
  if breakpoint_failures ~= 0 or watchpoint_failures ~= 0 then
    finish("FAIL", "instrumentation-install-failed")
    return
  end

  if not cold_save_requested then
    local ok, result = pcall(function() return emu:saveStateFile(COLD_STATE) end)
    if not require_live(ok and result ~= false, "cold-state-save-request-failed") then return end
    cold_save_requested = true
    init_route(STAGE4_TARGET, STAGE4_SCENE)
    remember("cold-state", "save-requested")
  end

  if phase == "boot-stage4" or phase == "route-stage4" then
    phase = "route-stage4"
    route_frame()
    if route_stable >= 90 and hit_count("stage4", "DAD4") > 0 then
      validate_stage4_and_save()
    elseif route_tick > 5200 then
      finish("FAIL", "stage4-stable-timeout")
    end
    return
  end

  if phase == "wait-armed-state" then
    emu:setKeys(0)
    emu:write8(0xDCDD, 0x17)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xFFBA, STAGE4_TARGET)
    if state_stable(ARMED_STATE) then
      if not require_live(complete_state_size(COLD_STATE) ~= nil,
          "cold-state-incomplete") then return end
      start_stage5()
    end
    return
  end

  if phase == "stage5-departure" then
    emu:setKeys(0)
    if case_state == "stage5-done" then validate_stage5()
    elseif frame > case_deadline then finish("FAIL", "stage5-departure-timeout") end
    return
  end

  if phase == "load-armed-for-stage7" then
    load_state(ARMED_STATE, "armed")
    return
  end
  if phase == "rehook-armed" then
    start_stage7_after_load()
    return
  end

  if phase == "stage7-departure" then
    emu:setKeys(0)
    if case_state == "stage7-done" then validate_stage7()
    elseif frame > case_deadline then finish("FAIL", "stage7-departure-timeout") end
    return
  end

  if phase == "load-cold-for-stage1" then
    load_state(COLD_STATE, "cold")
    return
  end
  if phase == "rehook-cold" then
    start_stage1_after_load()
    return
  end

  if phase == "route-stage1" then
    route_frame()
    if route_stable == 1 then
      local snap = payload_snapshot()
      if not require_live(all_zero(snap.db), "stage1-first-stable-db-not-zero") then return end
      stage1_steady_active = true
    end
    if route_stable >= 120 then validate_stage1()
    elseif route_tick > 5200 then finish("FAIL", "stage1-stable-timeout") end
    return
  end

  finish("FAIL", "unknown-phase-" .. phase)
end)

callbacks:add("shutdown", function()
  if not finished then finish("FAIL", "unexpected-shutdown") end
end)
