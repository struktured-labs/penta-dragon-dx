# iter 253-260 — Byte-lock coverage expansion

## Summary

Eight consecutive autonomous-loop iters added 88 ROM-byte verification
checks to `scripts/diagnostics/verify_colorizer_bytes.py`, taking
total coverage from **64 → 152 checks** on teleport.gb (and 64 → 142
on v3.01). Zero test breakage across the 8-iter run.

The byte verifier runs at the START of the pre-commit hook (sub-second
total), BEFORE the slower YAML / fresh-boot test phases. Any ROM-source
palette or colorizer-chain corruption now fails the commit immediately
via a byte-level check — without needing to wait for full mGBA runs.

## Iter-by-iter breakdown

### iter 253 — `ITER_217_SHARED_BG_TABLE_CHECKS` extended (8 bytes)
- 7 spike-cylinder tiles (0x2B-0x2D + 0x3A-0x3D) → pal 6 metallic
- bg_table sentinel terminator 0xFF → pal 0

### iter 254 — `ITER_254_SHARED_WALL_TILE_CHECKS` new (26 bytes)
- 8 wall edge tiles (0x14, 0x16-0x1A, 0x1C, 0x1E) → pal 6
- 7 wall interior tiles (0x25, 0x26, 0x34-0x38) → pal 6
- 11 corner/doorway tiles (0x41-0x49 except 0x47, 0x54-0x59 except 0x57) → pal 6

### iter 255 — defensive cleanup (0 new byte locks, but tighter verifier)
- Removed iter 250's accidental `spider_miniboss_sara_w` duplicate
  (already existed since iter 32 + 54)
- Extended `verify_hook_tests_exist.py` to FAIL on duplicate hook entries
  (was silently passing because each name was still findable in YAML)

### iter 256 — BG-pal idx 1 expansion (10 bytes)
- BG-pal-2 idx 1 = 0x7E1F (stage 3 purple)
- BG-pal-3 idx 1 = 0x03E0 (Crow background green)
- BG-pal-4 idx 1 = 0x7FE0 (Hornet background cyan)
- BG-pal-5 idx 1 = 0x03FF (Ground/lava yellow)
- BG-pal-6 idx 1 = 0x6F7B (Gargoyle background light-pink)

### iter 257 — OBJ-pal idx 1 expansion (12 bytes)
- OBP-0 idx 1 = 0x7C00 (EnemyProjectile blue baseline)
- OBP-3 idx 1 = 0x001F (Crow dark-blue)
- OBP-4 idx 1 = 0x03FF (Hornet yellow)
- OBP-5 idx 1 = 0x2A7C (Orc green)
- OBP-6 idx 1 = 0x6B7E (Humanoid purple)
- OBP-7 idx 1 = 0x7FE0 (Special cyan baseline)

### iter 258 — OBJ-pal idx 2 expansion (10 bytes)
- OBP-3 idx 2 = 0x0017 (Crow secondary dark-blue)
- OBP-4 idx 2 = 0x01FF (Hornet orange)
- OBP-5 idx 2 = 0x1574 (Orc mid-green)
- OBP-6 idx 2 = 0x42B5 (Humanoid dark purple)
- OBP-7 idx 2 = 0x3CC0 (Special mid-cyan baseline)

### iter 259 — BG-pal idx 2 + boss_pal[2/3] expansion (18 bytes)
- 7 BG-pal idx 2 source bytes (all 7 used BG palettes)
- boss_pal[2] idx 1 = 0x0CBF (reserved boss-mode entry)
- boss_pal[3] idx 1 = 0x7F94 (reserved boss-mode entry)

### iter 260 — OBJ colorizer CP thresholds (10 bytes)
The tile-ID-to-palette dispatch boundaries in the colorizer
(bank13:0x6A10):
- 0x6A11 = 0x0A (LD B,10 shadow-pass cap)
- 0x6A1A = 0x30 (low-tile vs boss-tile dispatch)
- 0x6A23 = 0x40 (pal_3 threshold)
- 0x6A27 = 0x50 (pal_4 threshold)
- 0x6A2B = 0x60 (pal_5 threshold)
- 0x6A2F = 0x70 (pal_6 threshold)
- 0x6A33 = 0x80 (pal_7 threshold / default fallback)
- 0x6A3B = 0x20 (sara_palette tile >= 0x20)
- 0x6A3F = 0x10 (sara_palette extended >= 0x10, iter-31 addition)
- 0x6A43 = 0x02 (low-low tile branch)

## What's now byte-locked vs not

| Category | Locked |
|---|---|
| BG-pal-0 through BG-pal-6 idx 0/1/2 | ✓ idx 1+2 (idx 0 is uniform 0x7FFF white) |
| BG-pal-7 (clone of BG-pal-0) | ✗ skipped (redundant) |
| OBP-0 through OBP-7 idx 0/1/2 | ✓ idx 1+2 (idx 0 is uniform 0x0000 transparent) |
| boss_pal[0/1/2/3] idx 1 | ✓ (Gargoyle/Spider/reserved-2/reserved-3) |
| boss_pal idx 2 | ✗ (only Spider boss_pal[1] idx 2 from iter 213) |
| bg_table walls (0x14-0x1E, 0x25-0x38) | ✓ all 15 |
| bg_table corners (0x41-0x49, 0x54-0x59) | ✓ all 13 |
| bg_table spikes (0x2A-0x2E, 0x3A-0x3D) | ✓ all 9 |
| bg_table font boundaries (0x80, 0xE0) | ✓ both |
| bg_table sentinel 0xFF | ✓ |
| bg_table font/items mid-range (0x88-0xDF) | ✗ (uniformly pal 1) |
| Arena tables (teleport-only) | ✗ (9 × 256 bytes each, complex) |
| OBJ colorizer CP thresholds | ✓ all 10 |
| Cond_pal / shadow_main / scene_detect entry signatures | ✓ |
| Lava/banner/cutscene override entries | ✓ |
| STAT IRQ vector + WRAM stub | ✓ |
| Level-select stub bytes | ✓ |
| Inline hook bank-switching code | ✓ |
| CGB flag at 0x143 | ✓ |

## What this catches

The byte-lock layer catches:
- Direct ROM-source palette corruption (someone manually edits a `palettes/*.yaml` and rebuilds without realizing the impact)
- Build script regressions (e.g., bg_table generator producing wrong values)
- Accidental bytes-from-old-ROM merges
- Build-script refactors that move/shrink critical routines

The byte-lock layer does NOT catch:
- Runtime palette corruption (DMA race, mid-frame CRAM writes, etc.) — these need the YAML / fresh-boot phases
- Logic bugs in colorize chain (correct bytes, wrong execution order)
- New code paths added without corresponding test coverage

## Cost / benefit

The byte verifier runs in well under 1 second across all 152 checks.
For comparison, the YAML test phase runs 116 mGBA invocations taking
3-6 minutes total. The byte verifier is therefore a high-leverage
fast-fail gate for the entire test pipeline.

Adding more byte locks (each is ~5 lines of Python) is cheap, but
diminishing returns past this point — the broad categories are all
covered. Future expansion should target NEW code paths added by
subsequent build script changes, not retroactive locks on already-
covered code.
