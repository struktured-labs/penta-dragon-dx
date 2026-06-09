# Position-based arena colorization — working (2026-06-08)

Branch `wip-arena-position-sweep`. The "holy grail" path: **zero steady-state
alternation** in boss arenas, achieved with plain CPU VBlank writes (no HDMA,
so it coexists with the arena's HBlank-HDMA scroll-shake that killed GDMA).

## Architecture (P1)

Two changes, both gated to arenas (D880 0x0C..0x14); dungeon/title untouched:

1. **Neutralize the inline hook's attr writes in arenas.** `0x42A7` gets an
   entry branch: in an arena it runs a TILE-ONLY copy (no VBK=1 attr phase).
   The position sweep is then the sole attr writer there, so nothing fights the
   fixed map. (`create_inline_tile_copy_tileonly(arena_neutralize_d880=0x0C)`.)
2. **Position sweep** (`arena_position.create_position_sweep`, bank13:0x7100,
   reusing dead attr_comp space). Runs from the colorize handler (VBlank). In an
   arena it copies the active boss's fixed per-cell posmap to the BG attr plane,
   a few rows/frame cycling (rows_per_frame=2); in every other scene it
   tail-calls the normal tile-ID sweep. A **fixed** map cannot alternate: every
   write of a cell writes the same value, regardless of boss animation.

The colorize handler's `CALL bg_sweep (0x6CD0)` is repointed to the sweep
dispatcher. Posmaps live in bank13 ROM (0x7B00+), one 2-byte pointer per arena
(0x7F80); arenas without a posmap fall back to the tile-ID sweep gracefully.

## Posmap generation (the data)

`probe_arena_posmap_gen.lua` runs on a HOOK-ACTIVE ROM (Phase-0 build) and, per
cell over 180 animation frames, takes the **dominant non-zero palette** the hook
assigns, if the cell is boss-colored in >=25% of frames (else 0 = background).
This freezes the proven Phase-0 coloring per cell. The >=25% rule gives generous
coverage so swept limbs are colored (pure modal picks "floor" for a cell a leg
only sometimes occupies -> uncolored limb). Output reuses the
`footprint_maps.log` "ROW name r digits" format ->
`scripts/diagnostics/posmap_maps.log`, parsed by `arena_position.parse_footprint_posmaps`.

## Results (full-screen alternation probe, 360-400 collected frames)

| build                     | Shalamar flip_stable | Riff flip_stable |
|---------------------------|----------------------|------------------|
| baseline (tile-ID)        |  606 (top cell 18x)  |        —         |
| Phase-0 (unified table)   |  210 (top 8-11x)     |        —         |
| **position sweep (this)** | **139, each cell 1x**| **79, each 1x**  |

Every remaining flip is **count=1** — a one-time settle as the map fills, NOT
repeating alternation. Steady-state alternation ~= 0.

Visuals (headless screenshots):
- **Riff (full-screen banded boss): excellent** — vibrant teal boss, clean
  banded floor, no white, no alternation. This is the holy grail for
  full-screen bosses (crystal/cameo/troop are the same shape, expected same).
- **Shalamar (limb boss): stable dominant colors.** Teal crown, banded body,
  natural gray legs (gray in Phase-0 too — that's the boss's color, not
  under-coverage). Single Phase-0 frames looked more teal because they caught
  one alternation phase; the posmap shows the stable dominant. CRAM is static
  (no cycling — verified), so this is genuinely flicker-free.

## Regression gate

Dungeon screenshot is **pixel-identical** between the position build and Phase-0
(neutralize + repoint only affect arenas). Title/dungeon unaffected.

## Status / next

- Working for 2 of 9 arenas (Shalamar, Riff). Bank-13 free space fits only TWO
  576-byte posmaps (0x7B00-0x7FFF). **Storage generalization needed for all 9**:
  RLE-compress the (highly repetitive) maps and expand to WRAM on scene change,
  or use a free ROM bank. The other 7 currently fall back to the Phase-0
  tile-ID sweep (reduced, not zero, alternation).
- Re-probe the 4 missing footprints (ted/faze/angela/penta) — the unreliable
  teleport set.
- Tune Shalamar limb coverage threshold / consider per-arena CRAM for prettier
  stable colors.
- **MiSTer hardware verification** before promoting to production (timing- and
  HDMA-sensitive; mGBA-clean != hardware-clean historically).

Builds: `tmp/teleport_stepB3.gb` (this), `tmp/teleport_fixed.gb` (Phase-0).
