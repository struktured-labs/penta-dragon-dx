# OBJ Colorizer (shadow_main + tile_based_colorizer)

The OBJ colorizer assigns CGB palette indices to sprite (OAM) attribute
bytes each VBlank, based on each sprite's tile ID. Located in bank 13.

## Entry: shadow_main at bank 13:0x69D0

```
0x69D0:  F5 C5 D5 E5      PUSH AF, BC, DE, HL
0x69D4:  F0 BE            LDH A, [FFBE]            ; Sara form (0 or 1)
0x69D6:  B7               OR A
0x69D7:  20 04            JR NZ, +4                ; if FFBE != 0: D=1
0x69D9:  16 02            LD D, 2                  ; FFBE=0 → Sara Witch palette
0x69DB:  18 02            JR +2
0x69DD:  16 01            LD D, 1                  ; FFBE=1 → Sara Dragon palette
0x69DF:  F0 BF            LDH A, [FFBF]            ; boss flag
0x69E1:  B7               OR A
0x69E2:  28 0B            JR Z, +11                ; no boss → E=0
0x69E4:  3D               DEC A                    ; A = boss_index
0x69E5:  4F               LD C, A
0x69E6:  06 00            LD B, 0
0x69E8:  21 C0 68         LD HL, 0x68C0            ; boss_slot_table
0x69EB:  09               ADD HL, BC
0x69EC:  5E               LD E, [HL]               ; E = boss_palette_slot
0x69ED:  18 02            JR +2
0x69EF:  1E 00            LD E, 0                  ; no boss
0x69F1:  21 03 C0         LD HL, 0xC003            ; OAM block 1 (start at attr byte)
0x69F4:  CD 10 6A         CALL 0x6A10              ; tile_based_colorizer
0x69F7:  21 03 C1         LD HL, 0xC103            ; OAM block 2
0x69FA:  CD 10 6A         CALL 0x6A10              ; tile_based_colorizer
0x69FD:  E1 D1 C1 F1      POP HL, DE, BC, AF
0x6A01:  C9               RET
```

Inputs:
- **FFBE**: Sara form flag (0 = Witch, 1 = Dragon)
- **FFBF**: Boss flag (0 = none, 1+ = boss index for boss_slot_table)

Outputs (set in registers, passed to colorizer):
- **D**: Sara palette index (1 or 2)
- **E**: Boss palette index (0 if no boss, 6 or 7 if Gargoyle/Spider, etc.)

## Inner: tile_based_colorizer at bank 13:0x6A10

Per-entry logic (40 OAM entries × 4 bytes each = 160 bytes per pass):

```
LD B, 40
loop_start:
  DEC HL          ; HL was at attr byte (offset +3); now at tile_id (offset +2)
  LD A, [HL]      ; A = tile_id
  INC HL          ; HL back to attr byte
  OR A
  JR Z, skip_sprite     ; tile=0 → invisible → skip
  CP 0x30
  JR C, low_tiles       ; tile < 0x30 → low_tiles
  ;; --- tiles 0x30+ ---
  LD A, E
  OR A
  JR NZ, boss_palette   ; if boss active (E != 0) → use boss palette
  LD A, C               ; tile_id back in C
  CP 0x40; JR C, pal_3
  CP 0x50; JR C, pal_4
  CP 0x60; JR C, pal_5
  CP 0x70; JR C, pal_6
  CP 0x80; JR C, pal_7
  LD A, 4; JR apply_palette       ; default pal 4
low_tiles:                ; tile < 0x30
  CP 0x20; JR NC, sara_palette    ; tile 0x20-0x2F → sara
  CP 0x10; JR NC, pal_4           ; tile 0x10-0x1F → pal 4
  CP 0x02; JR C, pal_3            ; tile 0x00-0x01 → pal 3 (projectiles)
  XOR A; JR apply_palette         ; default pal 0
pal_3: LD A, 3; JR apply_palette
pal_4: LD A, 4; JR apply_palette
pal_5: LD A, 5; JR apply_palette
pal_6: LD A, 6; JR apply_palette
pal_7: LD A, 7; JR apply_palette
sara_palette:
  LD A, D                ; D = sara palette (1 or 2 per shadow_main setup)
  JR apply_palette
boss_palette:
  LD A, E                ; E = boss palette (6, 7, etc.)
apply_palette:
  LD C, A
  LD A, [HL]
  AND 0xF8               ; clear lower 3 bits (palette bits)
  OR C                   ; insert new palette
  LD [HL], A             ; write attr back
skip_sprite:
  INC HL, INC HL, INC HL, INC HL    ; advance to next attr byte
  DEC B
  JP NZ, loop_start
  RET
```

## Tile range → palette table

| Tile range | Palette | Sprite type |
|---|---|---|
| 0x00-0x01 | 3 | Sara projectile + Crow |
| 0x02-0x0F | 0 | Various small effects (default fallback) |
| 0x10-0x1F | 4 | (unused range, defaults pal 4) |
| 0x20-0x27 | D (1 or 2) | Sara Witch tiles |
| 0x28-0x2F | D (1 or 2) | Sara Dragon tiles |
| 0x30-0x3F | E or 3 | Crows / mini-boss attacks (boss override if active) |
| 0x40-0x4F | E or 4 | Hornets |
| 0x50-0x5F | E or 5 | Orc/Ground |
| 0x60-0x6F | E or 6 | Humanoid |
| 0x70-0x7F | E or 7 | Catfish |
| 0x80+ | E or 4 | Default fallback |

When a boss is active (E != 0), **all tile IDs ≥ 0x30 get the boss
palette** instead of their default. Sara's tiles (0x20-0x2F) are
unaffected since they use `D` not `E`.

## Cycle cost

Per OAM entry: ~80-100T (depending on which branch taken)
Per shadow_main call: 2 × (40 × ~90T) = ~7200T
This is the dominant cost in the v3.01 colorize handler's FFC1 gate.

## Why this routine cannot be made cheaper

- OAM is 160 bytes (40 entries × 4 bytes) per buffer, and the game
  uses TWO shadow OAM buffers at 0xC003 and 0xC103 for sprite layers.
- Every entry must be checked each frame since sprite tile IDs change
  frequently (animation frames, Sara position).
- Skipping entries with tile=0 saves some time but the average sprite
  count is high during arena fights.

A faster colorizer would require:
- Pre-computed tile-ID → palette LUT (256 bytes vs current branching)
- Unrolled loop with no branches

These optimizations could cut shadow_main from ~7K T to maybe ~4K T,
saving ~3K T per frame and freeing up VBlank budget for other work.
Not pursued in v3.01 due to regression risk on hardware.

## What it does NOT colorize

- BG tiles (handled by inline tile+attr at 0x42A7 + bg_sweep)
- Tiles in 0x00-0x01 range are sometimes used for things other than
  projectiles; they're always pal 3 regardless of context.
