-- Measure boss-arena main-loop throughput, the way gameplay_speed_parity does.
-- The Python owner launches this only through mgba-qt-singleflight.
--
-- WHY THIS EXISTS: boss_publication_cadence measures the frame gap between
-- native 24x24 map publications. That is a game-logic EVENT RATE, not CPU
-- cost, and it reports physically impossible speedups (angela -24%, cameo
-- -22%, ted -14%) while changing sign with the observation window (one ROM:
-- crystal +2.156% at 1800 frames, +4.432% at 3600). The stage gate instead
-- counts executions of the main loop at $016C, which is a real throughput
-- measure -- fewer iterations in the same emulated frames means the game got
-- less work done. No boss probe had ever used it. This one does.
--
-- Scene holding is copied verbatim in intent from probe_boss_publication_
-- cadence.lua so OG and DX are pinned identically; these bytes are HP and
-- arena-exit latches, not the publication clock or pose selector.

local OUT = assert(os.getenv("BOSS_SPEED_OUT"), "BOSS_SPEED_OUT required")
local EXPECTED_SCENE = tonumber(os.getenv("BOSS_SPEED_SCENE") or "12")
local WARMUP = tonumber(os.getenv("BOSS_SPEED_WARMUP") or "60")
local FRAMES = tonumber(os.getenv("BOSS_SPEED_FRAMES") or "600")
-- Only candidate ROMs whose Ted compiler can span a frame boundary with
-- SVBK=2/3 need the banked-WRAM guard. On the stock DMG-mode ROM FF70 reads
-- $FF, so applying the guard unconditionally would skip EVERY frame and hang
-- the probe (found on the first vanilla smoke run).
local BANKED_WRITER = os.getenv("BOSS_SPEED_BANKED_WRITER") == "1"

-- The dungeon main loop at $016C never executes in boss arenas (measured:
-- 599 arena frames, zero hits). Arenas park inside `1A6F: CALL 4000` with
-- bank 2 mapped and iterate the loop whose head is bank2:$406F; $4083
-- increments the FFCD phase counter exactly once per iteration. Both
-- addresses fired identically (45/45 OG, 46/46 DX per 240 frames) with the
-- FF99 bank shadow reading $02 at every hit. Breakpoints are bank-blind, so
-- the FF99 filter keeps foreign-bank code at the same address out of the
-- count; the raw count is kept alongside so a filter mismatch is visible.
local ANCHOR = tonumber(os.getenv("BOSS_SPEED_ANCHOR") or "0x406F")
local ANCHOR_BANK = tonumber(os.getenv("BOSS_SPEED_ANCHOR_BANK") or "2")

local trace = assert(io.open(OUT .. ".trace", "w"))
local frame, scene_frames, finished = 0, 0, false
local scene_drift_frames = 0
local main_loop_hits = 0
local raw_anchor_hits = 0
local last_main_loop_frame, max_main_loop_gap = -1, 0
local in_scene = false
local parked_frames = 0

local function finish(status)
  if finished then return end
  finished = true
  trace:write(string.format(
    "complete status=%s frames=%d scene_frames=%d main_loop_hits=%d " ..
    "raw_anchor_hits=%d " ..
    "max_main_loop_gap=%d last_main_loop_frame=%d parked_frames=%d " ..
    "scene=%02X\n",
    status, frame, scene_frames, main_loop_hits, raw_anchor_hits,
    max_main_loop_gap, last_main_loop_frame, parked_frames,
    emu:read8(0xD880)))
  trace:close()
  local marker = assert(io.open(OUT .. ".done", "w"))
  marker:write(string.format(
    "%s main_loop_hits=%d scene_frames=%d max_main_loop_gap=%d\n",
    status, main_loop_hits, scene_frames, max_main_loop_gap))
  marker:close()
  emu:stop()
end

-- Count only iterations that happen while the arena is actually on screen and
-- past warmup, so a run that lands in the scene a few frames earlier than its
-- counterpart cannot bank extra iterations.
pcall(function()
  emu:setBreakpoint(function()
    if finished or not in_scene then return end
    if frame <= WARMUP then return end
    raw_anchor_hits = raw_anchor_hits + 1
    if ANCHOR_BANK >= 0 and emu:read8(0xFF99) ~= ANCHOR_BANK then return end
    main_loop_hits = main_loop_hits + 1
    if last_main_loop_frame >= 0 then
      local gap = scene_frames - last_main_loop_frame
      if gap > max_main_loop_gap then max_main_loop_gap = gap end
    end
    last_main_loop_frame = scene_frames
  end, ANCHOR)
end)

callbacks:add("frame", function()
  if finished then return end
  frame = frame + 1
  emu:setKeys(0)
  -- Termination must never depend on WRAM bank state: check it first so a
  -- candidate parked in SVBK=2/3 (or the stock ROM's constant $FF) cannot
  -- hang the run past its frame budget.
  if frame >= WARMUP + FRAMES then
    finish(scene_frames > 0 and "ok" or "wrong-scene")
    return
  end
  -- D000-DFFF is banked CGB WRAM; wait for the runtime to restore bank 0/1
  -- before trusting D880, exactly as the cadence probe does -- but only for
  -- ROMs whose writer actually crosses frames banked.
  local svbk = emu:read8(0xFF70) & 0x07
  if BANKED_WRITER and svbk ~= 0 and svbk ~= 1 then
    -- D880 is unreadable this frame (banked WRAM parked on 2/3), but the
    -- frame still elapsed. Carry the last known scene state so parked
    -- mid-scene frames stay in the scene_frames denominator: dropping them
    -- silently deleted ~20% of Ted-arena frames on v63-class candidates
    -- and inflated hits_per_scene_frame by the parked share (the
    -- "+22.46% faster" artifact). Keep-alive writes stay skipped -- they
    -- would land in the wrong WRAM bank.
    parked_frames = parked_frames + 1
    if in_scene and frame > WARMUP then
      scene_frames = scene_frames + 1
    end
    return
  end
  if emu:read8(0xD880) == EXPECTED_SCENE then
    in_scene = true
    scene_drift_frames = 0
    -- Keep the contestants alive without writing pose, animation, or timing.
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
        finish(scene_frames > 0 and "scene-exit" or "wrong-scene")
        return
      end
    end
  end
end)
