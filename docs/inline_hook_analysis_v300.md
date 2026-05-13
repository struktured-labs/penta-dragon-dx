# v3.00 Inline BG-Attr Hook — Disassembly & Design Notes

## Vanilla tile-copy at bank 1:0x42A0-0x436D

### Entry points (preserved in v3.00)

```
0x42A0: 26 9C        LD H, 0x9C       ; tilemap 0x9C00 entry
0x42A2: C3 A7 42     JP 0x42A7
0x42A5: 26 98        LD H, 0x98       ; tilemap 0x9800 entry (falls through)
0x42A7: <body>                        ; main entry — assumes H pre-set
```

### Vanilla body (0x42A7-0x436D)

```
0x42A7  LD L, 0                       ; tilemap column = 0
0x42A9  LD DE, 0xC1A0                 ; source = WRAM tile buffer
0x42AC  LD C, 8                       ; (row stride after the 24 written cols)
0x42AE  LD B, 24                      ; row counter

0x42B0  group_loop:
        ; 6 unrolled groups follow. Each group:
        ;   DI
        ;   wait_mode_3 (JP NZ loop) ; wait until LCD mode 3 starts
        ;   wait_mode_0 (JP NZ loop) ; then wait for HBlank (mode 0)
        ;   LD A,[DE]; INC DE; LD [HL+],A   x 4   (4 tile writes)
        ;   EI
        ; Group 4 has 0 tile writes (only DI + 2 STAT waits + EI).
        ; Group 6 has 8 tile writes (4 + 4 around an extra STAT wait).
        ; Total tiles per row: 4*4 + 0 + 8 = 24.

0x4364  LD A, B                       ; save row counter
0x4365  LD B, 0
0x4367  ADD HL, BC                    ; HL += 8 (skip unused 8 cols of 32-wide tilemap)
0x4368  LD B, A                       ; restore row counter
0x4369  DEC B
0x436A  JP NZ, 0x42B0                 ; next row
0x436D  RET
```

### Register/state contract on entry to 0x42A7
- **Input**: H = 0x98 or 0x9C (tilemap base hi); FF99 = bank containing this code
- **Clobbered**: A, BC, DE, HL, flags
- **Preserved**: stack contents, FF99 (no bank switch within routine)

### Callers (verified in vanilla ROM)
- bank 0: 0x0030 (RST $30 vector), 0x0FEF, 0x1001, 0x1283, 0x3428, 0x3744, 0x381A, 0x3AD8 → all to 0x42A5
- bank 1: 0x42A2 (internal JP), 0x43BA, 0x43D5, 0x51E9
- 0x0FEF and 0x1001 in bank 0 call/JP to 0x42A7 (with H pre-set externally)

## v3.00 inline hook design

### Code layout (replaces 0x42A7-0x431B; 117 bytes; 199 bytes available)

```
0x42A0..0x42A6  UNCHANGED (entry points)

0x42A7  setup: LD L,0; LD DE,C1A0; LD A,24; PUSH AF (row counter on stack)
0x42AF  row_loop: LD C, 6 (group counter)
0x42B1  group_loop:

  ; --- TILE PHASE (vanilla pattern, DI window ~280T) ---
  DI
  wait_mode_3 (LDH FF41; AND 3; CP 3; JR NZ)
  wait_mode_0 (LDH FF41; AND 3; JR NZ)
  LD A,[DE]; INC DE; LD [HL+],A    x 4    ; 4 tile writes to VBK=0
  EI

  ; --- TRANSITION (interrupts CAN fire here) ---
  PUSH BC                                  ; preserve C (group counter)
  rewind L by 4 (with carry adjust → H -= 1 if borrow)
  rewind E by 4 (with carry adjust → D -= 1 if borrow)
  LD B, 0xDA                               ; bg_table_hi = WRAM 0xDA00 page
  LD A, 1; LDH [FF4F], A                   ; VBK = 1 (attr bank)

  ; --- ATTR PHASE (DI window ~280T) ---
  DI
  wait_mode_3
  wait_mode_0
  ; Per attr: LD A,[DE]; INC DE; LD C,A; LD A,[BC]; LD [HL+],A
  ;   ; reads tile_id, looks up bg_table[tile_id], writes palette index to VBK=1
  for _ in 4: 1A 13 4F 0A 22              ; 4 attr writes
  EI
  XOR A; LDH [FF4F], A                     ; VBK = 0 restored
  POP BC                                   ; restore group counter

  DEC C
  JR NZ, group_loop                        ; 6 groups per row

0x430B  row_end: HL += 8 (skip unused cols)
0x4312  POP AF (row counter); DEC A
0x4314  JR Z, done                         ; 0 rows left
0x4316  PUSH AF; JR row_loop
0x4319  done: RET
```

### Phantom-safety contract

1. **No bank switch.** The hook never touches FF99. The VBlank hook in 0x0824 sets FF99=13 for VBlank, restores to bank 1 (or whatever caller's bank) after; this is untouched.
2. **Two short DI windows per group.** Each DI window (~280T worst-case) is comparable to vanilla's per-group DI. EI gap between phases (~50T) lets the Timer ISR fire normally.
3. **No write to FF99 or D887.** The hook touches only HL/DE/BC/A registers, VRAM VBK 0&1, and FF4F (VBK select).
4. **WRAM bg_table at 0xDA00.** This range is verified unused both statically (zero `EA xx DA` writes in any bank) and at runtime (periodic snapshot over 5000 gameplay frames including multi-direction movement and forced mini-boss spawn → 0xDA00-0xDAFF stays zero-sum throughout). Earlier candidates 0xCF00 and 0xDE00 were rejected: 0xCF00 gets overwritten by game state during dungeon rooms past initial; 0xDE48-0xDE51 has 29 static write refs in bank 2 (boss state).
5. **Cold-boot init in bank 13's colorize handler.** First frame copies 256 bytes from bank13:0x7000 (bg_table) to WRAM[0xDA00..0xDAFF]. Subsequent frames skip the copy (DF02 magic byte).

### bg_table source-of-truth

256-byte minimal mapping (matches v2.99):
- pal0 (default): 157 tile IDs
- pal1 (items 0x88-0xDF): 88 tile IDs
- pal5 (hazards 0x2A-0x2E, 0x3A-0x3D, 0x47, 0x57): 11 tile IDs

### bg_sweep retained as safety net

The v2.99 `bg_sweep_viewport_gated` remains in the VBlank handler. Two reasons:
1. **Initial coverage**: The inline hook only writes attrs where the game writes tiles. Tilemap regions outside the 24-row × 24-col write window keep their stale attrs unless bg_sweep catches them.
2. **Game timing**: Empirically, removing bg_sweep changed the game's state-machine timing enough to break the mini-boss probe (mini-boss spawn never triggered). Keeping bg_sweep preserves the timing margin.

This means the inline hook is **the primary write path** for visible attrs, bg_sweep is the **slow-cycle backup**. Together: no lag on visible tiles, plus coverage for the rest.

## Verification results

All 5 verification harnesses PASS:
| Harness | Result |
|---|---|
| title color | PASS (3 distinct colors, 9.9% non-white) |
| phantom D887 | PASS (0 transitions, vs vanilla baseline 18, threshold 27) |
| gameplay palette | PASS (24 distinct pal words, 4 distinct attr indices) |
| miniboss color | PASS (mini-boss spawned, OBJ palette colorized) |
| scroll tearing | PASS (0 palette changes within room) |

**Visible-viewport tile/attr alignment at frame 1500** (custom probe, 20-col × 18-row window):
- v2.99: 360/360 mismatches (100%) — every visible cell shows wrong palette
- v3.00:  62/360 mismatches  (17.2%) — only ~1.7 rows of stale attrs remain

The 62 v3.00 mismatches are concentrated in tilemap rows the inline hook hadn't yet touched (still being slow-swept by bg_sweep). v3.00 dramatically reduces visible attr lag without regressing any verification harness.

