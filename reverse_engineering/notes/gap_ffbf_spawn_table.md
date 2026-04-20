# Gap: FFBF Mini-boss Spawn/AI Table — VERIFIED + CORRECTED

## Table Location: 0x2C8F (bank 0)

256 bytes = 16 entries × 16 bytes. **Includes a valid entry 16.**

## Lookup Code (verified disassembly at 0x2A99)

```z80
2A99: F0 BF       LDH A,($FFBF)
2A9B: 3D          DEC A           ; FFBF=1..16 → A=0..15
2A9C: 87 87 87    ADD A,A x3      ; A *= 8
2A9F: 47          LD B,A
2AA0: 6F          LD L,A
2AA1: 26 00       LD H,$00
2AA3: 29          ADD HL,HL       ; *= 16 total
2AA4: 78          LD A,B
2AA5: D7          RST $10         ; pointer math via RST trampoline
2AA6: 19          ADD HL,DE
2AA7: F1          POP AF
```

Effective formula: `entry_addr = base + (FFBF - 1) * 16`. Two such call sites identified: 0x29DD and 0x2A99.

## Table Dump (256 bytes verified)

| FFBF | Bytes |
|------|-------|
| 1 | `03 01 0A 04 02 08 08 03 0A 08 02 0A 03 01 0A 04` |
| 2 | `03 08 08 02 0A 08 01 0A 02 01 0F 02 02 0F 02 04` |
| 3 | `0F 02 03 0F 02 01 0F 02 02 0F 02 04 0F 02 03 0F` |
| 4 | `02 00 0A 01 00 0A 03 00 0A 01 00 0A 02 00 0A 01` |
| 5 | `00 0A 03 00 0A 01 00 0A 02 01 14 04 02 0A 02 01` |
| 6 | `14 04 03 0A 02 01 14 02 03 14 02 01 14 02 02 14` |
| 7 | `08 01 08 08 02 08 08 01 08 04 03 10 04 01 10 08` |
| 8 | `02 08 04 04 10 04 02 10 02 01 1E 02 03 1E 02 02` |
| 9 | `1E 02 04 1E 02 01 1E 02 03 1E 02 02 1E 02 04 1E` |
| 10 | `02 01 1E 03 03 0A 06 04 03 02 03 14 02 01 1E 03` |
| 11 | `02 0A 06 04 03 02 03 14 02 01 05 03 01 03 01 01` |
| 12 | `0A 01 01 0A 02 01 05 03 01 03 01 01 0A 01 01 0A` |
| 13 | `01 02 0A 02 02 0A 02 01 0A 01 01 0A 01 03 0A 02` |
| 14 | `03 0A 02 04 0A 01 04 0A 03 01 14 02 04 14 03 02` |
| 15 | `14 02 03 14 03 01 14 04 02 14 04 01 14 04 02 14` |
| **16** | `04 00 03 03 00 05 01 00 0A 02 00 08 04 00 03 03` |

## Boss-16 OOB Hypothesis: REJECTED

Entry 16 EXISTS in the table and contains plausible AI data. Lookup uses `DEC A` then ×16 multiplier — all 16 entries (FFBF=1..16) live inside the 256-byte table.

A previous agent claimed "OOB Vulnerability CONFIRMED" — that analysis was incorrect.

## So Why Is Boss 16 Unkillable?

Possible alternate causes (now the leading suspects):

1. **Sprite/tile dispatch keyed off DC04** (not FFBF) — DC04=0x7B may not have a sprite entry, leaving entity slots unpopulated → no projectile collision
2. **Per-boss palette table** at bank 13:0x7000 (DX hack) — likely sized for 15 bosses only
3. **Entry 16's repeating 4-tuple `04 00 03 03 / 00 05 01 00 / 0A 02 00 08 / 04 00 03 03`** — the `00` bytes in 4-tuple slot 1/2 may be the entity-type or sprite-id field. Value 0 = no entity = no hitbox in OAM = no collision = no damage. Compare: entries 1-15 never have 0 in those positions.

**Most likely culprit (revised)**: entry 16's `00` bytes encoding a no-op entity type. Boss 16 is unfinished/placeholder.

## Suggested Fix

Two options:
1. Patch entry 16 fields at file 0x2D80+ to copy entry 15's pattern — may make boss 16 collidable
2. Clamp FFBF ≤ 15 at 0x0C18 — simpler, treats boss 16 as boss 15

## Cross-Reference

- Boss-detect formula: `gap_miniboss_16_unkillable.md`
- Combat damage write at 0x102F: `gap_combat_damage_disasm.md`
