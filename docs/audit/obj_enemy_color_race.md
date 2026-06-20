# OBJ enemy "black/blue/flat" color — FIXED in TELEPORT ROM (iter 31, 2026-06-18); production v3.01 still pending hardware verification

## UPDATE 2026-06-18 (iter 31, commit 534179f): teleport ROM unlocks all OBJ tests
**The "DMA-ordering race" framing below turned out to be over-pessimistic.** The
race exists for the SHADOW-pass colorizer (iter 29 verified shadow[14].attr stays
at 0x00 even with B=40, because the game's main-loop OAM rebuild overwrites
shadow attrs between colorize passes). But `hwoam_recolor` (the post-DMA stamp)
lives in the VBlank wrapper AFTER the DMA — nothing the game does to shadow can
race against it.

The 2-byte + 1-line fix in the teleport ROM:
- `scripts/bg_experiment.py:141` — tile 0x10-0x1F → `sara_palette` (was `pal_4`)
- `scripts/build_v301_teleport.py:561` — `hwoam_recolor` `LD B, 10` → `LD B, 40`

Sara's secondary body sprites (tiles 0x10-0x1F, slots 10-11 adjacent to primary)
get the Sara form palette D instead of pal_4 (orange) — no "Sara half-orange"
when B=40. Enemies in slots 10+ (orc 0x52, soldier 0x61, catfish, etc.) get
their tile-range palette via the post-DMA stamp.

Unlocked tests in the pre-commit hook (50 → 59):
- orc (slot 14 tile 0x52 → pal 5 ✓)
- orc_with_items (slot 12 tile 0x55 → pal 5 ✓)
- soldier (slot 12 tile 0x61 → pal 6 ✓)
- catfish (game-side default → correct pal ✓)
- spider_miniboss_sara_d (Sara D form, savestate LIVE, → pal 1 ✓)
- dragon_powerup (Sara form-change → pal 1 ✓)
- sara_w_in_spider_miniboss_live (Sara W during spider miniboss, live save) ✓

Still excluded (one test): `spider_miniboss_sara_w` — the savestate has
DF1F=0xFF (frozen). Confirmed via `probe_spider_w_liveness.lua`: poisoning HW
OAM with 0xAB persists 15 frames unmodified. The VBlank wrapper isn't running
for that savestate; not a colorizer bug.

## STILL PENDING: production v3.01 / FIXED.gb
The teleport ROM (`penta_dragon_dx_teleport.gb`) has the iter-31 fix. The
production v3.01 ROM (`penta_dragon_dx_v301.gb`) and the MiSTer-deployed
`penta_dragon_dx_FIXED.gb` do NOT have `hwoam_recolor` installed — their bank-13
0x7F40 area contains tile graphics, not code.

### Free space update (iter 95, 2026-06-20)
The earlier "Bank 13 in v3.01 is almost full" claim is **wrong**. Audit of
`rom/working/penta_dragon_dx_v301.gb` bank 13 turned up **524 truly-free
bytes across 4 contiguous zero regions**, all verified zero in the ORIGINAL
ROM (`rom/Penta Dragon (J).gb`) as well — so they're not load-time
buffers or tile graphics:
  - `bank13:0x6A70` — 144 bytes
  - `bank13:0x6B27` — 233 bytes  ← largest single contiguous run
  - `bank13:0x6D3F` — 65 bytes
  - `bank13:0x6DAE` — 82 bytes

`hwoam_recolor` is ~43 bytes (see `build_v301_teleport.py:build_hwoam_recolor`).
Plus a 3-byte CALL hook in the v3.01 wrapper → ~46 bytes total. Fits trivially
in any of the four regions. **0x6B27 is the safest choice** — largest run,
furthest from neighboring live code.

Backport plan (future iter):
  1. Modify `scripts/build_v301_gdma.py` (NOT `build_v301_teleport.py`) to:
     - Write `hwoam_recolor` body at `bank13:0x6B27`
     - Add `CALL 0x6B27` to the v3.01 VBlank wrapper after colorize+DMA
  2. Verify mGBA: 80-test regression hook + fresh-boot guards
  3. Hardware-verify on MiSTer (B=40 adds ~900 T-states to post-DMA wrapper).
MiSTer hardware verification still required because B=40 adds ~30 cycles × 30
slots ≈ 900 T-states to the post-DMA wrapper; mGBA tolerates VBlank overruns
more than real CGB/DMG.

---

# Original investigation (2026-06-XX, pre-iter-31)

Covers user items 3, 4, 6, 11 (Sara/monsters black or flat-blue; "random red
quadrants"; regular enemies one flat color). Diagnosed by the color-sweep
investigation workflow + firsthand mGBA save-state probes.

## Symptom
In-game (and attract-demo) enemy sprites render at OBJ palette 0 (blue/black)
instead of their intended type palette. Measured stably (NOT flickering) across
consecutive frames on multiple save states:
  catfish tiles 0x7C-0x7F -> p0 (should be p7 cyan)
  soldier tiles 0x68-0x6B -> p0 (should be p6)
  moth/hornet partially p4; Sara forms get p1/p2 (work).
The colorizer's per-tile palette assignment is NOT reaching the displayed HW OAM.

## Root cause (two compounding issues)
1. OAM scan cap: the colorizer scans only the first 10 shadow-OAM entries
   (build_v301_gdma.py `colorizer[1] = 0x0A`). Sprites at index >=10 (the
   attract-demo monsters at slots 16-19, in-game mage/catfish at 16-23) are
   never assigned a CGB OBJ palette -> default OBP0. (Raising to 0x28=40 gives
   full coverage but did NOT fix the in-game enemies below, and costs ~+5400T
   VBlank.)
2. DMA-ordering race (the dominant cause): the build NOP'd the game's own OAM DMA
   (rom[0x06D5]=00 00 00) and relies on the colorize handler's double-buffered
   DMA (CALL 0xFF80, source alternating 0xC0/0xC1 via FFCB). The game rebuilds
   enemy sprite entries (at pal=0) into shadow OAM in its MAIN loop; the colorize
   handler colorizes shadow OAM once in VBlank then DMAs. For sprites whose entry
   the game writes into whichever buffer is DMA'd next, the colorizer's tile-range
   palette is overwritten by the game's pal=0 rebuild before that buffer displays
   -> enemy renders pal 0 (blue). Stable (not flicker) because the buffer index
   per enemy is consistent.

## Candidate fixes (ALL timing-critical -> verify on MiSTer hardware first;
## ~76% VBlank budget; phantom-sound/audio-dropout history on this exact path)
A. Raise the scan cap to 0x28 (full 40) AND make the colorizer win the OAM write
   ordering: have shadow_main + OAM-DMA run as the FINAL OAM writer of the frame
   (e.g. move them to the end of the VBlank wrapper after the game's OAM build),
   OR add a post-DMA HW-OAM recolor pass that reads 0xFE00 and re-stamps palette
   bits by tile range. Fixes enemies AND the miniboss segmentation (item 7) in
   one shot.
B. Stop the DMA source from alternating: patch the HRAM OAM-DMA routine
   (`F0 CB 3C E6 01 E0 CB C6 C0 E0 46`) to always DMA the buffer shadow_main
   colorized. RISK: the game may rely on the alternation for live sprite
   POSITIONS — forcing one buffer can lag/garble sprite positions. Must verify
   positions stay correct.

## Color-quality follow-up (LOW risk, only meaningful once colorization sticks)
Retune palettes/penta_palettes_v097.yaml obj_palettes for distinct enemies:
  OBJ4 Hornets amber ["0000","03FF","011F","0084"]
  OBJ5 OrcGround brown/tan ["0000","021F","015A","00A6"]
  OBJ6 Humanoid steel-purple ["0000","5C1F","3811","1808"]
  (OBJ0 blue, OBJ3 red, OBJ7 cyan keep). Split crows out of OBJ3 (shared with
  Sara's shots) by reassigning colorizer tile range 0x30-0x3F to its own pal.

## Status
NOT shipped. The shipped ROM keeps the hardware-verified safe config (cap=10,
double-buffer DMA). Implement + verify on MiSTer in a focused pass.
