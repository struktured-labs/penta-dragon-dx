# Inline Tile+Attr Copy at 0x42A7 (v3.01 production)

The colorization architecture in v3.01 hinges on a tile-copy routine at
bank 1:0x42A7 that we patch to write CGB tile-attribute bytes alongside
the original tile-ID writes. This document captures the full mechanism.

## Entry points

The 0x42A0 region has three callable entries:

```
0x42A0:  26 9C    LD H, 0x9C    ; target 0x9C tilemap path
0x42A2:  C3 A7 42 JP 0x42A7     ; jump to common code
0x42A4:  26 98    LD H, 0x98    ; target 0x98 tilemap path
0x42A6:  C9       RET           ; (vestigial — historical RET, no longer reached)
0x42A7:  ...      common entry, H pre-set by caller
```

Callers can:
- `CALL 0x42A0` → H=0x9C, then JP to 0x42A7
- `CALL 0x42A4` → H=0x98, then fall-through to 0x42A7
- `CALL 0x42A7` → H pre-set by caller's own `LD H, ...`

## Caller inventory (static analysis)

Five static callers of 0x42A7 found across the ROM:

| ROM bank | CPU addr | Op | Pre-set | Notes |
|---|---|---|---|---|
| 0 | 0x0FEF | CALL 0x42A7 | LD H,0x98 | Bank-0 room-load tile-copy path |
| 0 | 0x1001 | JP 0x42A7 | LD H,0x98 | Bank-0 alt entry (fall-through pattern) |
| 1 | 0x42A2 | JP 0x42A7 | LD H,0x9C | Internal alt-entry (0x42A0 → 0x42A7) |
| 1 | 0x43BA | CALL 0x42A7 | LD H,0x98 | Bank-1 utility |
| 1 | 0x43D5 | CALL 0x42A7 | LD HL,0x9800 | Direct HL pre-set, H derived |

No callers of 0x42A0 / 0x42A4 found in static scan — the alt-entries
appear unused (or only used from within the routine itself).

## Body structure (v3.01)

The patched body at 0x42A7..0x431B (117 bytes) implements:

```
Setup:
  LD L, 0x00          ; HL = H:00 (target tilemap row 0)
  LD DE, 0xC1A0       ; DE = WRAM tile-source buffer
  LD A, 24            ; A = row count (24 rows)
  PUSH AF             ; row counter on stack

row_loop:
  LD C, 6             ; C = 6 groups of 4 tiles each per row

group_loop:
  ;; -------- TILE PHASE: VBK=0 (default), 4 tile writes --------
  DI                  ; protect from STAT/Timer ISRs
  STAT-wait mode 3
  STAT-wait mode 0    ; safe time to write VRAM tile region
  LD A,[DE]; INC DE; LD [HL+],A       ; tile 1
  LD A,[DE]; INC DE; LD [HL+],A       ; tile 2
  LD A,[DE]; INC DE; LD [HL+],A       ; tile 3
  LD A,[DE]; INC DE; LD [HL+],A       ; tile 4
  EI

  ;; -------- TRANSITION: rewind HL,DE by 4 bytes; VBK=1 --------
  PUSH BC             ; save C (group counter)
  LD A,L; SUB 4; LD L,A     ; HL -= 4 (with carry into H)
  JR NC, +1; DEC H
  LD A,E; SUB 4; LD E,A     ; DE -= 4 (with carry into D)
  JR NC, +1; DEC D
  LD B, 0xDA          ; B = bg_table high byte (WRAM 0xDA00)
  LD A, 1; LDH [FF4F], A    ; VBK = 1 (attr bank)

  ;; -------- ATTR PHASE: VBK=1, 4 attr writes via [BC] lookup --------
  DI
  STAT-wait mode 3
  STAT-wait mode 0
  for _ in range(4):
    LD A,[DE]; INC DE     ; A = tile_id (from rewound DE)
    LD C, A               ; BC = 0xDA00 + tile_id (B already = 0xDA)
    LD A,[BC]             ; A = bg_table[tile_id] = palette index 0..7
    LD [HL+], A           ; write attr (HL advances, now in attr layer)
  EI

  ;; -------- POST-ATTR: VBK=0 --------
  XOR A; LDH [FF4F], A    ; VBK = 0 (restore tile-ID layer)
  POP BC                  ; restore group counter

  DEC C
  JR NZ, group_loop       ; 6 groups × 4 tiles = 24 tiles per row

row_end:
  LD A,L; ADD 8; LD L,A   ; HL += 8 (skip 8 unused columns)
  JR NC, +1; INC H

  POP AF; DEC A           ; row counter -= 1
  JR Z, done
  PUSH AF; JR/JP row_loop

done:
  RET
```

Result: 24 rows × 6 groups × 4 tiles = 576 tile+attr pairs written
per call. Equivalent to copying 576 bytes of tile IDs and 576 bytes
of attributes to the target tilemap.

## bg_table dependency (WRAM 0xDA00)

The attr phase reads `[BC]` where B=0xDA and C=tile_id. This indexes
into a 256-entry table in WRAM at 0xDA00. The table is initialized
on the first VBlank by the colorize handler's cold-boot path:

```
LD HL, bg_table_rom_addr   ; bank 13:0x7000
LD DE, 0xDA00              ; WRAM destination
LD B, 0                    ; 256 iterations
copy_loop: [HL+] → [DE]; INC DE; DEC B; JR NZ
```

Table contents (from `_bg_table()` in `build_v301_gdma.py`):
- `0x14, 0x16-0x1A, 0x1C, 0x1E`: pal 6 (wall edges)
- `0x25-0x26, 0x34-0x38`: pal 6 (wall interior)
- `0x41-0x46, 0x48-0x49, 0x54-0x56, 0x59`: pal 6 (corners)
- `0x2A-0x2E, 0x3A-0x3D, 0x47, 0x57`: pal 5 (spike hazards)
- `0x88-0xDF`: pal 1 (items)
- Other tile IDs: pal 0 (default — Dungeon floor/void)

## STAT-mode timing

The DI-protected STAT-mode waits in each tile/attr phase ensure VRAM
access happens during LCD mode 0 (HBlank), the only mode where VRAM
writes don't conflict with the picture processing unit.

```
LDH A, [FF41]    ; STAT register
AND 0x03         ; mask mode bits
CP 0x03          ; mode 3 = drawing
JR NZ, ...       ; wait until mode is NOT 3
                 ; (i.e., drawing finished)
LDH A, [FF41]
AND 0x03
JR NZ, ...       ; wait until mode is 0 (HBlank)
```

This pattern protects against PPU contention during the 4-tile burst.
Each tile/attr write window is small enough to fit in one HBlank
(85 dots = ~204 T-cycles on single-speed CGB).

## VBK toggling

The CGB tile-attribute layer is accessed at the same VRAM address
range (0x9800-0x9FFF) as the tile-ID layer, but selected by writing
VBK (FF4F):

- VBK = 0 → reads/writes go to VRAM bank 0 (tile IDs + tile patterns)
- VBK = 1 → reads/writes go to VRAM bank 1 (tile attrs + alt patterns)

The routine flips VBK=1 between the tile phase and attr phase, then
flips back VBK=0 before group_loop continues. CRITICAL: VBK must end
at 0 so the game's subsequent VRAM accesses see tile IDs (not attrs).

## What this routine does NOT cover

- **Title screen splashes** drawn via bank-0:0x0FEF caller path: covered
- **Stage load splash** ("STAGE 01" text): covered
- **Inventory menu (SELECT)**: covered (uses same code paths)
- **Window layer (separate 0x9C00 region)**: NOT explicitly handled —
  the window's tile writes might bypass 0x42A7. Empirically no issues
  observed but worth a future check.
- **Boss arena setup**: arena routines at bank 2:0x886E+ call other
  setup helpers; tile writes there typically still flow through one
  of the 5 callers above.

## Where v3.01 differs from v3.00

The routine bytes at ROM 0x42A7-0x431B are BYTE-FOR-BYTE IDENTICAL
between v3.00 FIXED.gb and v3.01. The patches are the same.

v3.01's contribution to the colorization pipeline is in the OBJ side
(palette_loader OCPS stride fix) and the bg_sweep deployment
(unchanged from v3.00 in current production after the 2026-05-23 fix).
