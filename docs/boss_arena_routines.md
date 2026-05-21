# 9 Boss Arena Setup Routines

Each boss has a self-publishing arena setup routine in bank 2.
Dispatched by FFBA (level counter, 0-8) via a jump table at
bank 2:0x6EA6, called from bank 2:0x658F.

## Dispatcher

```
;; Entry: A = FFBA (level counter, 0-8)
;; bank 2:0x658F:
  87        ADD A, A         ; A *= 2 (each entry is 2 bytes)
  D7        RST 0x10         ; HL += A (pointer math)
  2A        LD A, [HL+]      ; A = lo byte
  66        LD H, [HL]       ; H = hi byte
  6F        LD L, A          ; HL = arena addr
  E9        JP [HL]          ; jump to arena
```

Jump table at bank 2:0x6EA6 (ROM file 0xAEA6):
```
6E 48 F8 48 99 49 0D 4A 76 4A ED 4A 61 4B D5 4B 46 4C ...
↓     ↓     ↓     ↓     ↓     ↓     ↓     ↓     ↓
0x486E 0x48F8 0x4999 0x4A0D 0x4A76 0x4AED 0x4B61 0x4BD5 0x4C46
```

## Location

| # | FFBA | ROM offset | CPU addr (bank 2) | D880 value | Size | Boss |
|---|---|---|---|---|---|---|
| 1 | 0 | 0x886E | 0x486E | 0x0C | 138 bytes | Shalamar (stage 1) |
| 2 | 1 | 0x88F8 | 0x48F8 | 0x0D | 161 bytes | Riff (stage 2) |
| 3 | 2 | 0x8999 | 0x4999 | 0x0E | 116 bytes | Crystal Dragon (stage 3) |
| 4 | 3 | 0x8A0D | 0x4A0D | 0x0F | 105 bytes | Cameo (stage 4) |
| 5 | 4 | 0x8A76 | 0x4A76 | 0x10 | 119 bytes | Ted (stage 5) |
| 6 | 5 | 0x8AED | 0x4AED | 0x11 | 116 bytes | Troop (stage 6) |
| 7 | 6 | 0x8B61 | 0x4B61 | 0x12 | 116 bytes | Faze (stage 7) |
| 8 | 7 | 0x8BD5 | 0x4BD5 | 0x13 | 113 bytes | Penta Dragon (final main) |
| 9 | 8 | 0x8C46 | 0x4C46 | 0x14 | ? bytes | **Hidden boss (Angela?)** |

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
| **0x13** | **Boss arena: Penta Dragon (final main)** |
| **0x14** | **Boss arena: Hidden boss (Angela?)** |
| 0x17 | Death / timeout cinematic |
| 0x18 | Boss splash (stage transition) |

## Caller of arena routines

Static analysis: arena routines are NOT called directly. They're
reached through the FFBA-indexed jump table at bank 2:0x6EA6,
dispatched from the `JP [HL]` at bank 2:0x658F.

The `JP 0x658F` happens at multiple sites in bank 2 (e.g. one
just before 0x886E at ROM 0x886B). Each call site loads HL with
the appropriate table pointer first.

## 9 arenas total

Memory entry `project_hidden_stages.md`'s "9 arena routines" claim
was right after all. The initial static-scan inventory missed the
9th routine at 0x8C46 because it sat just past the range I scanned.

The hidden SHMUP stages (top-down spaceship) likely use a different
mechanism since the structure is different from boss arena combat.
Arena #9 (FFBA=8, D880=0x14) might be the Penta Dragon's "true final"
form, or Angela (the documented hidden boss).
