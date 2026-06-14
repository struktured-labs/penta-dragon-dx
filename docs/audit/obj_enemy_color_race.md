# OBJ enemy "black/blue/flat" color — root cause + fix (NEEDS hardware verify)

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
