# mGBA Lua OAM read timing — known issue + investigation log

**State:** unresolved 2026-06-18. Test runner OAM dump for slots in boss-fight
save states sometimes reports the boss palette (pal 6/7) for Sara's slots
(0-3), even though the actual LCD renders her in the correct Sara palette
(verified by sampling the rendered screenshot pixels — peach/pink, not
blue-gray/red).

## What's confirmed

1. **Visual = correct.** Screenshot-pixel sampling of `gargoyle_miniboss.png`
   at game coords (72,64)-(88,80) shows (247, 173, 90) peach + (74, 8, 0)
   dark red + (16, 16, 0) near-black. Those match Sara W's OBJ palette
   (`OBP2 = 0000 2EBE 511F 0842`). They do NOT match BGP6/OBP6 (blue-gray
   ~165,165,181).

2. **Single-slot probe = correct.** A focused probe reading ONLY slot 0
   and slot 1 attr at frame 60 (via `-t` state load + same Lua "frame"
   callback timing as the test runner) reports `slot0=0x02 slot1=0x02`
   consistently across f60/62/65 (`/tmp/match_test_runner.log`).

3. **40-slot dump = WRONG.** The test runner reads ALL 40 OAM slots in a
   loop (160 sequential `emu:read8` calls per sample). At frame 60+ in
   gargoyle save, slot 1 attr comes back as `0x06` (boss palette).

## Hypothesis

`emu:read8` is not atomic relative to the emulator core's frame loop —
between iterations of the OAM dump, the core may advance scanlines, and
the game's main-loop OAM rebuild can update HW OAM mid-dump. Slot 0 gets
read at LY=144 (post-recolor), slot 1 gets read at LY=145+ where the game
has had time to overwrite slot 1's attr.

The consensus filter (5 samples in frames 58–68) does NOT fix this because
each sample suffers the same mid-dump drift in the same way — majority
vote across 5 identical-bias samples still loses.

A pre-read busy-loop also doesn't help (the drift is during the dump,
not before it).

## What we ruled out

- Lua `emu:loadStateFile` vs `-t` state-load: both produce the same OAM
  behaviour at frame 60+ in single-byte probes.
- Frame-callback timing relative to VBlank IRQ: LY=144 at callback fire,
  which is post-IRQ — single reads are clean.
- The colorizer logic: trace through `bg_experiment.py.create_tile_based_colorizer`
  for tile 0x25 goes `CP 0x30 carry → low_tiles → CP 0x20 NC → sara_palette`
  → A = D (Sara form palette) = 2 for Sara W. No path produces pal 6 for
  this tile sequence.

## Workarounds in place

- Tests that need slot-specific assertions on Sara during boss saves are
  EXCLUDED from `scripts/hooks/pre-commit` (the 12-test reliable list
  doesn't include `gargoyle_miniboss`, `spider_miniboss_*`, `mage`, `moth`,
  `metal_ball_mage_soldier`).
- BG-table tests (which read `0xDA00` once, not 40 OAM bytes) and OBJ
  tests on STABLE scenes (non-boss `sara_w_alone`/`sara_d_alone`/`crow`)
  are reliable and ARE in the hook.

## Next-step ideas to try

1. **Read OAM via memory:cart? or a single bulk-read primitive.** If
   mGBA Lua has an atomic block-read API, that would eliminate the per-
   byte drift.
2. **Disable LCD during the dump.** `emu:write8(0xFF40, current & 0x7F)`
   before reading, restore after. LCD off freezes the game's OAM writes
   (since it's running its own sprite logic on next IRQ). Risk: changes
   emulator state observable by the game.
3. **Read OAM via shadow buffer instead of HW OAM.** Slot 1 in shadow A
   (C007) at frame 60+ should reflect the colorizer's last write.
   Probe showed `shA:t=25 a=00` — but that's because game's main loop
   rewrote shadow to pal0 between colorizer and our read. Same issue.
4. **Cross-validate via screenshot pixel-sampling.** Replace OAM-attr
   assertions with "sample pixel at known Sara location, must match Sara
   palette colour-set". More robust but bigger refactor.

(Option 1 likely fastest; defer until needed to widen hook coverage.)
