# Gap #4: Tile Decompression at bank0:0x1322

## Compression Format: Fixed 4:1 LUT Expansion

NOT RLE, NOT LZ, NOT bit-packed. Each compressed byte is a **direct index** into a 256-entry × 4-byte lookup table at 0xA400. Each input byte → 4 output bytes.

- LUT base: 0xA400 (1024 bytes, 256 × 4)
- Input: 64 bytes (8 rows × 8 cols)
- Output: 256 bytes at 0xC3E0 (a single 8×8 tile = 16 bytes × 16 = 256? Actually 4:1 of 64 = 256 confirms)
- Compression ratio: 4:1

## Disassembly Summary (0x1322-0x135F)

Nested 8×8 loop:
- Outer loop B=8 (rows)
- Inner loop C=8 (compressed bytes per row)
- Each byte goes through 0x136C subroutine: index LUT, copy 4 bytes to dest with 2×2 sub-pattern (±15 offset)
- Source pointer advances by 0x38 (56 bytes) per outer iteration

Key sub-routines:
- **0x1360**: address calc (multiply index × 64 + 0xC780)
- **0x136C**: per-byte LUT expansion
- **0x1388**: 2-byte memcpy from LUT entry

## Callers

| Caller | Bank | HL source |
|--------|------|-----------|
| 0x12B0 | 0 | 0xC2AE (WRAM stage tiles) |
| 0x130B | 0 | 0xC1A0 (secondary buffer) |
| 0x43A4 | 1 | computed in bank 1 |
| 0x4663 | 1 | preset HL |
| 0x5087 | 1 | 0xFF94 |

## Sample LUT Entries

```
0xA400: 01 CD 04 58
0xA404: B7 CA 12 64
0xA440: E5 CD F5 65
```

## Implications

- The "tile data" referenced at C3E0 is fully expanded already by the time bank1:0x42A7 copies it to VRAM
- Output buffer 0xC3E0 is then processed by 0x1399 (C3E0 → C1A0)
- Modding tile graphics requires editing the 1024-byte LUT at 0xA400 — not the compressed source pointers
- The 4:1 ratio explains why each "stage" can fit a full tile sheet in a small spawn-table-adjacent region of bank 13
