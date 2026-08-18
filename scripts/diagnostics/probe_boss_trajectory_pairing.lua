-- Record the boss-arena phase-vector trajectory, iteration-indexed, so the
-- driver can align OG and DX runs at a common semantic point and measure
-- frames-per-iteration over the matched span only.
--
-- WHY THIS EXISTS: every cross-ROM boss speed receipt to date rides OG/DX
-- state fixtures that land at different arena phases, and pairing validity
-- was an assumption, not a precondition. The receipts show the consequence:
-- physically implausible signs (ted -17.1%, cameo -17.0% at 7200 frames)
-- and magnitudes that grow with the observation window -- trajectory
-- divergence amplifying, not a fixed CPU delta. This probe makes pairing
-- checkable: it samples the boss-phase WRAM vector at every arena-loop
-- iteration (the bank2:$406F anchor, FF99==$02 filtered, exactly as
-- probe_boss_speed_parity.lua counts them), and the driver aligns the two
-- sides on matching vector TRANSITIONS.
--
-- Iteration-indexed, never frame-indexed: the builds legitimately shift
-- frame phase (~5.3 frames/iteration, different cycles per frame slice), so
-- frame-indexed comparison manufactures divergence where there is none.
-- Sampling at the loop-head breakpoint keys every sample to the same point
-- in the native control flow on both ROMs.
--
-- The keep-alive writes (DCBB/DCDC/DCDD/D888/DD06) are identical on both
-- sides and those bytes are therefore excluded from the phase vector.

local OUT = assert(os.getenv("TRAJ_OUT"), "TRAJ_OUT required")
local EXPECTED_SCENE = tonumber(os.getenv("TRAJ_SCENE") or "12")
local WARMUP = tonumber(os.getenv("TRAJ_WARMUP") or "60")
local FRAMES = tonumber(os.getenv("TRAJ_FRAMES") or "1800")
-- Same banked-writer guard contract as probe_boss_speed_parity.lua: only
-- candidates whose Ted compiler parks SVBK=2/3 across frames need it, and
-- the stock DMG ROM reads FF70=$FF so the guard must stay off there.
local BANKED_WRITER = os.getenv("TRAJ_BANKED_WRITER") == "1"
local ANCHOR = tonumber(os.getenv("TRAJ_ANCHOR") or "0x406F")
local ANCHOR_BANK = tonumber(os.getenv("TRAJ_ANCHOR_BANK") or "2")

-- Boss-phase vector: DD85-88 (boss phase block), DCB8 (section cycle),
-- DD08 (arena phase byte), FFBF (mini-boss flag, HRAM). DCBB/DCDC/DCDD/
-- D888/DD06 are force-written by the keep-alives and carry no signal.
local VEC_ADDRS = {0xDD85, 0xDD86, 0xDD87, 0xDD88, 0xDCB8, 0xDD08, 0xFFBF}

local trace = assert(io.open(OUT .. ".trace", "w"))
local frame, scene_frames, finished = 0, 0, false
local scene_drift_frames = 0
local iters = 0
local raw_anchor_hits = 0
local in_scene = false
local parked_frames = 0

local function finish(status)
  if finished then return end
  finished = true
  trace:write(string.format(
    "complete status=%s frames=%d scene_frames=%d iters=%d " ..
    "raw_anchor_hits=%d parked_frames=%d scene=%02X\n",
    status, frame, scene_frames, iters, raw_anchor_hits, parked_frames,
    emu:read8(0xD880)))
  trace:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(string.format("%s iters=%d scene_frames=%d\n",
    status, iters, scene_frames))
  marker:close()
  emu:stop()
end

-- One sample per arena-loop iteration, taken at the loop head so both ROMs
-- sample at the identical point in native control flow. The FF99 filter
-- keeps foreign-bank code at the same address out, and the raw count is
-- kept alongside so a filter mismatch cannot hide (same contract as the
-- speed-parity probe).
pcall(function()
  emu:setBreakpoint(function()
    if finished or not in_scene then return end
    if frame <= WARMUP then return end
    raw_anchor_hits = raw_anchor_hits + 1
    if ANCHOR_BANK >= 0 and emu:read8(0xFF99) ~= ANCHOR_BANK then return end
    iters = iters + 1
    local svbk = emu:read8(0xFF70) & 0x07
    local vec = {}
    for index, addr in ipairs(VEC_ADDRS) do
      vec[index] = string.format("%02X", emu:read8(addr))
    end
    trace:write(string.format(
      "iter=%d frame=%d scene_frame=%d svbk=%d vec=%s ffcd=%02X\n",
      iters, frame, scene_frames, svbk, table.concat(vec),
      emu:read8(0xFFCD)))
  end, ANCHOR)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  -- Termination must never depend on WRAM bank state (a candidate parked in
  -- SVBK=2/3, or the stock ROM's constant $FF, must not hang the run).
  if frame >= WARMUP + FRAMES then
    finish(iters > 0 and "ok" or "wrong-scene")
    return
  end
  local svbk = emu:read8(0xFF70) & 0x07
  if BANKED_WRITER and svbk ~= 0 and svbk ~= 1 then
    -- D880 is unreadable this frame (banked WRAM parked on 2/3), but the
    -- frame still elapsed. Carry the last known scene state so parked
    -- mid-scene frames stay in the denominator: dropping them silently
    -- deleted ~20% of Ted-arena frames from scene_frames and inflated
    -- every iterations-per-scene-frame rate on banked candidates by the
    -- parked share (the "+22.46% faster" artifact). Keep-alive writes stay
    -- skipped -- they would land in the wrong WRAM bank.
    parked_frames = parked_frames + 1
    if in_scene and frame > WARMUP then
      scene_frames = scene_frames + 1
    end
    return
  end
  if emu:read8(0xD880) == EXPECTED_SCENE then
    in_scene = true
    scene_drift_frames = 0
    -- Keep the contestants alive without writing pose, animation, or
    -- timing state (verbatim from the speed-parity probe).
    emu:write8(0xDCBB, 0xF0)
    emu:write8(0xDCDC, 0xFF)
    emu:write8(0xDCDD, 0xFF)
    emu:write8(0xD888, 0x00)
    emu:write8(0xDD06, 0x00)
    if frame > WARMUP then scene_frames = scene_frames + 1 end
  else
    in_scene = false
    if frame > WARMUP then
      scene_drift_frames = scene_drift_frames + 1
      if scene_drift_frames > 1 then
        finish(iters > 0 and "scene-exit" or "wrong-scene")
        return
      end
    end
  end
end)
