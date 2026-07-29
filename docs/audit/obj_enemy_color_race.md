# OBJ enemy "black/blue/flat" color — root cause and working fix

Covers user items 3, 4, 6, 11 (Sara/monsters black or flat-blue; "random red
quadrants"; regular enemies one flat color). Diagnosed by the color-sweep
investigation workflow + firsthand mGBA save-state probes.

## Symptom

Ordinary gameplay enemies rendered with OBJ palette 0 (blue/black) or with
only some quadrants colored. Direct mGBA hardware-OAM sampling reproduced the
defect in seven of eight combat anchors: 3,816 mismatches among 6,456 checked
enemy samples.

## Root cause

Two behaviors compounded:

1. The historical helper processed ten entries in each of the two Shadow OAM
   buffers. Monsters often occupy slots 10–23, so their palette attributes were
   never assigned.
2. Processing both buffers was not ordering-safe. The main loop could rebuild
   the future DMA buffer with palette 0 after the colorizer had touched it.
   The alternating DMA then displayed those stale attributes.

## Working fix

`scripts/build_v302_title_fix.py` installs a 51-byte dispatcher at bank
13:`0x69D0`. It reproduces the native `FF80` routine's `FFCB` calculation to
select the exact `C000`/`C100` buffer that will be transferred next, then runs
the established gameplay colorizer over all 40 entries in that one buffer.
The caller's next instruction is the native DMA, so no main-loop write can
intervene. Sprite positions and buffer alternation are unchanged.

This is deliberately separate from the title-idle reel's YAML LUT. Ordinary
gameplay dynamically packs monster graphics and retains the production range
mapping (`30–3F→3`, `40–4F→4`, `50–5F→5`, `60–6F→6`, `70–7F→7`), plus dynamic
Sara and boss-specific assignments.

## Verification

- `verify_gameplay_obj_palettes.py` checks visible mGBA hardware OAM every
  frame, not just the WRAM source buffer.
- Eight combat states, 120 sampled frames per state, 6,562 checked enemy
  entries, zero mismatches.
- Actors through Shadow OAM slot 23 are covered; projectile/effect slots as
  high as 36 remain outside the ordinary-enemy assertion domain.
- Title reel, real miniboss, scroll, audio/timing, HUD, boss arenas, later
  stages, both story branches, and production stress gates all still pass.
- The pre-fix ROM is preserved as
  `penta_dragon_dx_FIXED.v303-before-gameplay-obj.backup.gb`.

## Color-quality follow-up (LOW risk, only meaningful once colorization sticks)
Retune palettes/penta_palettes_v097.yaml obj_palettes for distinct enemies:
  OBJ4 Hornets amber ["0000","03FF","011F","0084"]
  OBJ5 OrcGround brown/tan ["0000","021F","015A","00A6"]
  OBJ6 Humanoid steel-purple ["0000","5C1F","3811","1808"]
  (OBJ0 blue, OBJ3 red, OBJ7 cyan keep). Split crows out of OBJ3 (shared with
  Sara's shots) by reassigning colorizer tile range 0x30-0x3F to its own pal.

## Status

Implemented in the current untagged working candidate. Emulator verification
is complete; MiSTer FPGA timing is still required before release.
