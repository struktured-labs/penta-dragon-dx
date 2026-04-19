# Gap #5: FFAC / FFAD HRAM Semantics

## Summary

FFAC and FFAD form a **16-bit little-endian pointer register** in HRAM used to pass level-specific data addresses to subsystems. FFAC = low byte, FFAD = high byte.

## Writes to FFAC

| Bank | File Offset | In-Bank | Opcode | Notes |
|------|-------------|---------|--------|-------|
| 0A | 0x02A871 | 0x2871 | E0 AC | Init/level setup |
| 0C | 0x030BA3 | 0x0BA3 | E0 AC | Level init sequence |

## Writes to FFAD

| Bank | File Offset | In-Bank | Opcode |
|------|-------------|---------|--------|
| 0B | 0x02C66F | 0x066F | E0 AD |
| 0B | 0x02CF85 | 0x0F85 | E0 AD |
| 0B | 0x02D721 | 0x1721 | E0 AD |
| 0B | 0x02D961 | 0x1961 | E0 AD |

All 4 FFAD writes live in bank 0B — suggests 4 distinct configurations (one per mini-boss class or level segment).

## Reads

### Bank 0:0x1404 — pointer-builder subroutine (PRIMARY)

```z80
1404: F0 AC       LDH A,($FFAC)    ; A = low byte
1406: 6F          LD L,A           ; L = low byte (NOTE: corrected — disasm above wrote (HL),A but operand was 6F=LD L,A)
1407: F0 AD       LDH A,($FFAD)
1409: 67          LD H,A           ; H = high byte
140A: C9          RET              ; HL = pointer
```

Returns HL = (FFAD:FFAC). Canonical pointer retrieval.

### Bank 0D:0x3A01 (file 0x37A01) — spawn-table reader

Reads FFAD inside spawn-table processing code. Confirms FFAC/FFAD feeds the bank-13 spawn system.

### Bank 07 reads (3 sites)

Located in ROM data region (sprite/animation metadata), not executed code. False positive in opcode search.

## Per-Level Semantics

- FFAC = low byte of level-specific spawn/entity table pointer
- FFAD = high byte; 4 writes in bank 0B suggest one per major game mode (dungeon / mini-boss / stage-boss / cinematic?)
- Spawn table itself lives at 0x34024 (bank 13); FFAC/FFAD likely point at the **active level's** sub-table within bank 13's level data block, OR at a WRAM mirror

## Open Questions

- Concrete (FFAC,FFAD) value per FFBA (0-8). Requires runtime probe — set FFBA=0..8, log FFAC/FFAD values during init.
- Why bank 0A AND bank 0C both write FFAC (overlap or sequence?).
