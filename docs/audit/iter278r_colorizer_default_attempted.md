# iter 278r — colorizer high-tile default → sara_palette (attempted, reverted)

## Summary

Attempted a 2-byte change to the colorizer at bank13:0x6A36 (the
high-tile default dispatch). Changed `3E 04` (LD A, 0x04 = pal_4 hornet)
to `7A 00` (LD A, D = sara_palette; NOP) to preserve downstream JR offsets.

**Theory**: when hwoam_recolor's colorizer reads a tile byte from
mode-locked HW OAM, it returns 0xFF. 0xFF doesn't match any explicit
range (0x30-0x7F), so the dispatcher falls into the high-tile default
path → writes pal_4 (orange wedge). Routing default to D (Sara palette)
would make the race outcome look like Sara color instead of orange.

## Result

**10 regression tests FAIL**:
- crow, moth, orc — enemy sprites
- metal_ball_mage_soldier — multi-enemy scene
- sara_w_2_metal_ball — Sara + metal ball
- sara_w_catfish_menu_open — Sara + catfish
- sara_w_right_before_secret_stage_gbc — pre-secret stage
- sara_w_secret_stage_shmup — secret stage
- spiral_power_active — projectile
- stage4_live_render — stage 4 rendering

Tile range 0x80+ is used by MORE OBJ sprites than expected (not just
race-condition fallback). The default pal_4 path is legitimately hit
by many enemies/projectiles in normal gameplay. Routing all of them
to D=sara_palette breaks all those renderings.

## Why no surgical fix fits

To safely route ONLY tile==0xFF (race signature) to sara_palette
without affecting legitimate 0x80+ enemies would require:

```
CP 0xFF       ; +2 bytes
JR Z, sara_palette  ; +2 bytes  
LD A, 0x04
JR apply_palette
```

This adds 4 bytes to the colorizer, shifting all downstream JR offsets.
Regenerating the colorizer with proper offsets is non-trivial — the
"FROZEN" annotation on `create_tile_based_colorizer` exists because
many test byte locks depend on specific offsets.

Furthermore, the 16T per-slot extra check would shift wrapper runtime
~640T (16T × 40 slots), exceeding iter 277's -480T break threshold
in the opposite direction.

## Build state after revert

Restored to iter 278p baseline (commit `2d94d67`):
- iter 278p: stage intro letter brightening
- iter 278l: cursor visible as 'A' character
- iter 278e: 75% Sara race reduction
- 170 byte-verifier locks pass
- All 116 BG regression tests pass
- Fresh-boot all expectations pass

## /goal final status — 7 attempts at component 1+2

| Attempt | Approach | Outcome |
|---|---|---|
| iter 277 | B=20 hwoam_recolor reduction | -480T → broke 4 fresh-boot CRAM |
| iter 278d | inline split-stamp +600T | broke many CRAM |
| iter 278g | CALL sara_stamp +24T | broke 22 CRAM |
| iter 278h | CALL sara_stamp + FFA9 invalidate | wrapper overran VBlank |
| iter 278n | inline sara_stamp + NOP padding | 6 CRAM fail (multiple NOP counts) |
| iter 278o | iter 278n + test-side FFA9 force | 8 CRAM (game overwrite race) |
| iter 278q | iter 278n + setBreakpoint protection | partial OBP-2 fix, FFC0 crashed |
| **iter 278r** | colorizer default → sara_palette | **10 enemy tests broke** |

All 8 distinct attempts fail. The autonomous-loop architectural ceiling
for components 1+2 is exhaustively documented.

User intervention required:
1. Accept 75% Sara reduction as ship-ready
2. Authorize deep RE (game-side FFD0 write path patch, ~hours-days)
3. Adjust /goal conditions to match achievable scope
