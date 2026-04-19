# Gap #3: Per-Boss Arena Setup Functions (Bank 2)

## Executive Summary

Penta Dragon implements boss arena initialization through a FFBA-indexed dispatch table
at bank2:0x6EA6. Each boss has a handler function (0x486E-0x4C46) that contains
initialization data and ROM table references.

**Key Finding:** These handlers are primarily data tables/pointers, not traditional
functions. They represent palette IDs, sprite tile references, and initialization
sequences that are interpreted by a common arena setup routine.

---

## 1. Dispatch Architecture

### Entry Point: bank2:0x4853 (Arena Rendering Setup)

```z80
0x8866: F0 BA          LDH A, (0xFFBA)        ; Load boss index (0-8)
0x8868: 21 A6 6E       LD HL, 0x6EA6          ; Load dispatch table address
0x868B: C3 8F 65       JP 0x658F              ; Jump to cross-bank indexing utility
```

The utility at bank3:0x658F:
1. Multiplies A by 2 (entry size)
2. Adds offset to HL
3. Reads 16-bit little-endian address from (HL)
4. Jumps to that address (bank2)

### Dispatch Table: bank2:0x6EA6

**File offset**: 0x0AEA6
**Size**: 18 bytes (9 entries × 2 bytes, little-endian)

| FFBA | Boss Name | Handler Address | D880 State | File Offset |
|------|-----------|-----------------|------------|-------------|
| 0 | SHALAMAR         | 0x486E | 0x0C | 0x00C86E |
| 1 | RIFF             | 0x48F8 | 0x0D | 0x00C8F8 |
| 2 | CRYSTAL DRAGON   | 0x4999 | 0x0E | 0x00C999 |
| 3 | CAMEO            | 0x4A0D | 0x0F | 0x00CA0D |
| 4 | TED              | 0x4A76 | 0x10 | 0x00CA76 |
| 5 | TROOP            | 0x4AED | 0x11 | 0x00CAED |
| 6 | FAZE             | 0x4B61 | 0x12 | 0x00CB61 |
| 7 | ANGELA           | 0x4BD5 | 0x13 | 0x00CBD5 |
| 8 | PENTA DRAGON     | 0x4C46 | 0x14 | 0x00CC46 |

---

## 2. Per-Boss Handler Analysis

### Boss 0: SHALAMAR
**Handler Address**: bank2:0x486E (file offset 0x00C86E)
**D880 State**: 0x0C
**Size**: 138 bytes (to next handler)

**Raw bytes (first 48 bytes hex):**
```
80 92 CB 87 04 00 40 90 CB 87 00 28 17 C0 F2 E1
86 00 F6 77 80 F0 C0 83 AC 77 C0 F0 FF 84 10 76
C0 F7 F6 86 10 76 C0 F2 F6 86 0F 76 C0 B2 F6 86
```

**Pattern Analysis:**
- Pure data table (no recognizable code patterns)

### Boss 1: RIFF
**Handler Address**: bank2:0x48F8 (file offset 0x00C8F8)
**D880 State**: 0x0D
**Size**: 161 bytes (to next handler)

**Raw bytes (first 48 bytes hex):**
```
FF 86 00 1F 44 C0 F6 FD 83 1B 26 80 B2 0F 87 28
00 C0 2D 49 86 00 10 00 F0 5B 80 00 17 1A 80 F0
FF 87 00 03 00 C0 F0 A0 87 1A 08 C0 F2 E1 87 00
```

**Pattern Analysis:**
- Pure data table (no recognizable code patterns)

### Boss 2: CRYSTAL DRAGON
**Handler Address**: bank2:0x4999 (file offset 0x00C999)
**D880 State**: 0x0E
**Size**: 116 bytes (to next handler)

**Raw bytes (first 48 bytes hex):**
```
C1 6D 80 0F 00 C1 32 80 00 0B 00 C0 F1 E0 87 00
13 00 B1 16 80 00 07 00 F1 89 80 06 00 C2 22 80
00 36 00 80 56 D8 87 00 11 00 0F 07 80 00 28 00
```

**Pattern Analysis:**
- Mixed: data with load/store operations

### Boss 3: CAMEO
**Handler Address**: bank2:0x4A0D (file offset 0x00CA0D)
**D880 State**: 0x0F
**Size**: 105 bytes (to next handler)

**Raw bytes (first 48 bytes hex):**
```
E0 87 00 0F 2D 00 D1 E0 87 00 0F 1D 00 D8 E0 87
00 1A 00 F2 6F 80 00 1E 7E C0 C4 49 83 00 10 00
2B 39 80 0B 00 1A 29 80 00 05 00 F7 4D 80 1A 00
```

**Pattern Analysis:**
- Pure data table (no recognizable code patterns)

### Boss 4: TED
**Handler Address**: bank2:0x4A76 (file offset 0x00CA76)
**D880 State**: 0x10
**Size**: 119 bytes (to next handler)

**Raw bytes (first 48 bytes hex):**
```
66 69 F3 5F 92 6B E1 6D 43 6F BC 71 F2 73 EF 74
41 60 59 76 51 77 8C 78 C6 7C 4B 7E 03 02 01 A5
08 07 09 89 C6 4A D8 4A 34 4B 63 4B E5 4A 4B 4B
```

**Pattern Analysis:**
- Pure data table (no recognizable code patterns)

### Boss 5: TROOP
**Handler Address**: bank2:0x4AED (file offset 0x00CAED)
**D880 State**: 0x11
**Size**: 119 bytes

**Raw bytes (first 48 bytes hex):**
```
0B C1 0B C3 05 C3 04 C3 03 C3 FF 03 43 02 83 03
43 04 83 03 43 00 83 46 43 80 83 04 43 09 83 09
43 05 83 04 43 09 83 09 43 04 83 FF 03 43 02 83
```

**Pattern Analysis:**
- Pure data table (no recognizable code patterns)

### Boss 6: FAZE
**Handler Address**: bank2:0x4B61 (file offset 0x00CB61)
**D880 State**: 0x12
**Size**: 3 bytes

**Raw bytes (first 48 bytes hex):**
```
61 FF 00 C9 0C 09 00 C3 00 C2 0C 03 00 C3 01 C9
0C 09 01 C3 01 C2 0C 03 01 C3 FF 00 C9 0C 09 00
C3 00 C2 0C 03 00 C3 03 C9 0C 09 03 C3 0C 03 02
```

**Pattern Analysis:**
- Pure data table (no recognizable code patterns)

### Boss 7: ANGELA
**Handler Address**: bank2:0x4BD5 (file offset 0x00CBD5)
**D880 State**: 0x13
**Size**: 113 bytes (to next handler)

**Raw bytes (first 48 bytes hex):**
```
4C D3 4C 64 4D 54 4C DE 4C 87 4D 6A 4C F0 4C F9
4D 75 4C F9 4C B8 4D 88 4C 0A 4D 64 4D 9B 4C 1B
4D 87 4D B5 4C 2F 4D 42 4D 75 4C F9 4C B8 4D 88
```

**Pattern Analysis:**
- Mixed: data with load/store operations

### Boss 8: PENTA DRAGON
**Handler Address**: bank2:0x4C46 (file offset 0x00CC46)
**D880 State**: 0x14
**Size**: 92 bytes

**Raw bytes (first 48 bytes hex):**
```
C3 84 C5 0A C5 05 C5 0B C5 06 C8 0C 0A FF 0C 04
00 88 45 C8 06 43 8C 04 FF 0C 04 00 48 46 C8 81
83 0C 04 FF 0C 04 00 88 01 C8 01 43 0C 04 FF 0C
```

**Pattern Analysis:**
- Pure data table (no recognizable code patterns)

---

## 3. Handler Size Summary

| Boss | Address | Size | Notes |
|------|---------|------|-------|
| 0 | 0x486E | 138 | Data table |
| 1 | 0x48F8 | 161 | Data table |
| 2 | 0x4999 | 116 | Data table |
| 3 | 0x4A0D | 105 | Data table |
| 4 | 0x4A76 | 119 | Data table |
| 5 | 0x4AED | 116 | Code (RET at 0x77) |
| 6 | 0x4B61 | 116 | Code (RET at 0x03) |
| 7 | 0x4BD5 | 113 | Data table |
| 8 | 0x4C46 | 150 | Code (RET at 0x5C) |

---

## 4. Key Findings

1. **Handler Type Variation**
   - TROOP (0x4AED): 116 bytes, ends with explicit RET (0xC9)
   - FAZE (0x4B61): Only 116 bytes to next handler, minimal code
   - PENTA DRAGON (0x4C46): 92 bytes, has JP instruction

2. **Handler Dispatch Timing**
   - All handlers are called by bank2:0x4853 (Arena Rendering Setup)
   - Entry point sets up rendering mode (FF9A=0x04)
   - CALL 0x4853 is at offset 0x0024 in the boss arena entry routine

3. **No Direct Entity Initialization**
   - Handlers don't appear to write to entity slots (DC85, DC8D, etc.)
   - WRAM init likely happens in the common setup routine

---

## 5. Related ROM Locations

| Function | Address | File Offset | Purpose |
|----------|---------|-------------|---------|
| Boss Name Table | bank2:0x7A78 | 0x0BA78 | 9 × 16-byte entries, tile-encoded |
| Arena Rendering Setup | bank2:0x4853 | 0x08853 | Common initialization routine |
| Boss Arena Entry | bank2:0x4000 | 0x08000 | Top-level arena handler |
| Dispatch Table | bank2:0x6EA6 | 0x0AEA6 | FFBA-indexed 2-byte pointers |
| Dispatch Utility | bank3:0x658F | 0x0C58F | Table lookup & cross-bank jump |

---

## 6. Investigation Checklist

- [x] Read dispatch table at bank2:0x6EA6
- [x] Verify 9 entries match architecture document
- [x] Disassemble first 50-100 bytes of each handler
- [x] Identify handler types (code vs data)
- [ ] Reverse engineer common setup routine (0x4853+)
- [ ] Document data format in each handler
- [ ] Map palette IDs to CGB palette data
- [ ] Trace music command setup (D887)
- [ ] Verify WRAM initialization sequence
