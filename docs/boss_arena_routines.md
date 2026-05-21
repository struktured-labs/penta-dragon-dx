# 8 Boss Arena Setup Routines

Each named stage boss has a self-publishing arena setup routine in bank 2.
There is no central dispatcher — each arena writes its own state value to
D880 at entry.

## Location

| # | ROM offset | CPU addr (bank 2) | D880 value | Size | Likely boss |
|---|---|---|---|---|---|
| 1 | 0x886E | 0x486E | 0x0C | 138 bytes | Shalamar (stage 1) |
| 2 | 0x88F8 | 0x48F8 | 0x0D | 161 bytes | Riff (stage 2) |
| 3 | 0x8999 | 0x4999 | 0x0E | 116 bytes | Crystal Dragon (stage 3) |
| 4 | 0x8A0D | 0x4A0D | 0x0F | 105 bytes | Cameo (stage 4) |
| 5 | 0x8A76 | 0x4A76 | 0x10 | 119 bytes | Ted (stage 5) |
| 6 | 0x8AED | 0x4AED | 0x11 | 116 bytes | Troop (stage 6) |
| 7 | 0x8B61 | 0x4B61 | 0x12 | 116 bytes | Faze (stage 7) |
| 8 | 0x8BD5 | 0x4BD5 | 0x13 | 113 bytes | Penta Dragon (final) |

## Common prologue

```
3E XX     LD A, 0x0C..0x13    ; arena state ID (unique per boss)
EA 80 D8  LD [D880], A         ; publish scene state
E0 B7     LDH [FFB7], A        ; publish to FFB7 (HRAM mirror)
21 A0 00  LD HL, 0x00A0        ; initial X position?
7D / 7C / EA 85 DD / EA 86 DD    ; store to DD85/DD86 (X coord?)
21 F0 00 ... EA 87 DD / EA 88 DD ; store to DD87/DD88 (Y coord?)
CD 3E 06                       ; CALL common setup
CD A7 06                       ; CALL another setup
AF / E0 43 / E0 42             ; SCX = SCY = 0
21 F1 74 / 2A / EA 91 DD ...   ; load per-arena data from 0x74xx
```

## D880 master scene state machine

Combined with documented states:

| D880 | Meaning |
|---|---|
| 0x00 | Stuck / uninitialized |
| 0x01 | Title screen / boot |
| 0x02 | Dungeon (normal gameplay) |
| 0x0A | Mini-boss combat (Haunt Dragon / Arachnid) |
| 0x0B | Mini-boss splash / boss splash |
| **0x0C** | **Boss arena: Shalamar** |
| **0x0D** | **Boss arena: Riff** |
| **0x0E** | **Boss arena: Crystal Dragon** |
| **0x0F** | **Boss arena: Cameo** |
| **0x10** | **Boss arena: Ted** |
| **0x11** | **Boss arena: Troop** |
| **0x12** | **Boss arena: Faze** |
| **0x13** | **Boss arena: Penta Dragon (final)** |
| 0x17 | Death / timeout cinematic |
| 0x18 | Boss splash (stage transition) |

## Caller of arena routines

Static analysis found only one direct caller: `bank10:0x7DA9 → 0x88DB`.
Other entries must be reached via computed JP (e.g., JP HL) or jump
tables that don't statically resolve. The 2-byte word `BD 16`
(absolute pointer to 0x16BD) appears 50× in 0x88FF-0x8BD5 — likely
jump table entries within each arena routine.

## Earlier inventory was wrong

Memory entry `project_hidden_stages.md` previously claimed
"9 arena routines at ROM 0x886E-0x8C46". The actual count is 8.
Mapping to 8 named bosses is exact.

The hidden SHMUP stages probably use a different mechanism since
top-down spaceship gameplay is structurally different from boss arena
combat (no fixed arena, scrolling background, sprite-based enemies).
