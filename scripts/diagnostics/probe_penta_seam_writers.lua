-- Trace the one Penta Dragon physical-map seam cell which can momentarily
-- retain palette 0 while its tile already requires palette 1. The owner must
-- launch this through the project single-flight wrapper.

local OUT = assert(os.getenv("PENTA_SEAM_OUT"), "PENTA_SEAM_OUT is required")
local FRAMES = tonumber(os.getenv("PENTA_SEAM_FRAMES") or "750")
local EXPECTED_SCENE = 0x14
local trace = assert(io.open(OUT .. ".trace", "w"))
local marker = OUT .. ".done"
local frame, boot_frames, started, in_scene, installed, finished =
  0, 0, false, false, false, false

local function register(name)
  local readers = {
    function() return emu:getRegister(name) end,
    function() return emu:getRegister(string.lower(name)) end,
    function() return emu:readRegister(name) end,
    function() return emu:readRegister(string.lower(name)) end,
  }
  for _, reader in ipairs(readers) do
    local ok, value = pcall(reader)
    if ok and value ~= nil then return value & 0xFFFF end
  end
  return 0xFFFF
end

local function cell_snapshot(tag)
  if not in_scene then return end
  local old_vbk = emu:read8(0xFF4F)
  emu:write8(0xFF4F, 0)
  local tile = emu:read8(0x992F)
  emu:write8(0xFF4F, 1)
  local attr = emu:read8(0x992F) & 7
  emu:write8(0xFF4F, old_vbk)
  trace:write(string.format(
    "%s frame=%d pc=%04X bank=%02X lcdc=%02X ly=%02X stat=%02X " ..
    "vbk=%d a=%02X f=%02X sp=%04X tile=%02X attr=%d expected=%d\n",
    tag, frame, register("PC"), emu:read8(0xFF99),
    emu:read8(0xFF40), emu:read8(0xFF44), emu:read8(0xFF41),
    emu:read8(0xFF4F) & 1, register("A") & 0xFF,
    register("F") & 0xFF, register("SP"), tile, attr,
    emu:read8(0xC600 + tile) & 7))
  trace:flush()
end

local function install_probes()
  local entries = {
    {0x0842, "atomic-completion-gate"},
    {0x0847, "banked-completion-mapper"},
    {0x3497, "atomic-wrap"},
    {0x42A7, "copy-entry"},
    {0x42B2, "atomic-copy"},
    {0x4324, "pure-copy"},
    {0x5D6A, "arena-sanitizer-dispatch"},
    {0x566A, "arena-completion-dispatch"},
    {0x572C, "legacy-seam-repair"},
    {0x6C80, "banked-completion-entry"},
    {0x7B9C, "v66-postcopy-dispatch"},
    {0x7E00, "vblank-lava-tail"},
    {0x6200, "v66-seam-helper"},
  }
  for _, entry in ipairs(entries) do
    local id = assert(emu:setBreakpoint(
      function() cell_snapshot(entry[2]) end, entry[1]))
    trace:write(string.format("installed breakpoint=%04X id=%s\n",
      entry[1], tostring(id)))
  end
  local watch_id = assert(emu:setRangeWatchpoint(function(info)
    if not in_scene then return end
    trace:write(string.format(
      "write frame=%d pc=%04X bank=%02X value=%02X vbk=%d ly=%02X stat=%02X\n",
      frame, register("PC"), emu:read8(0xFF99), info.value & 0xFF,
      emu:read8(0xFF4F) & 1, emu:read8(0xFF44), emu:read8(0xFF41)))
    trace:flush()
  end, 0x992F, 0x992F, C.WATCHPOINT_TYPE.WRITE))
  trace:write(string.format("installed watchpoint=992F id=%s boot_frames=%d\n",
    tostring(watch_id), boot_frames))
  trace:flush()
  installed = true
end

callbacks:add("frame", function()
  if finished then return end
  boot_frames = boot_frames + 1
  emu:setKeys(0)
  local scene = emu:read8(0xD880)
  -- mGBA installs a cross-ROM savestate after the script's first frame
  -- callback.  Do not mistake those pre-load frames for a scene exit.
  in_scene = scene == EXPECTED_SCENE
  if not in_scene then
    if not started and boot_frames >= 120 then
      trace:write(string.format("wrong-scene boot_frames=%d scene=%02X\n",
        boot_frames, scene))
      trace:close()
      local done = assert(io.open(marker, "w"))
      done:write("wrong-scene\n")
      done:close()
      finished = true
      os.exit(2)
    end
    return
  end
  -- The first callback can precede mGBA's cross-ROM state restore. Install
  -- debugger state only after that transient has completed, or the restore
  -- silently clears every breakpoint and watchpoint.
  if not installed then
    if boot_frames < 4 then return end
    install_probes()
  end
  started = true
  emu:write8(0xDCBB, 0xF0)
  emu:write8(0xDCDC, 0xFF)
  emu:write8(0xDCDD, 0xFF)
  frame = frame + 1
  cell_snapshot("frame")
  if frame >= FRAMES then
    trace:close()
    local done = assert(io.open(marker, "w"))
    done:write(string.format("ok frames=%d\n", frame))
    done:close()
    finished = true
    os.exit(0)
  end
end)
