# Gap: Bank 14 Death Cinematic

## Bank 14 Contents (16 KB at file 0x38000-0x3BFFF)

- Pure 2bpp Game Boy tile graphics (8×8 tiles, 16 bytes each)
- ~1024 tiles total, ~978 non-zero
- No embedded text or audio commands
- Loaded to VRAM 0x9000 for cinematic display

## Invocation Flow (0x4A44)

Triggered when DCBB reaches 0 (combat damage underflow OR corridor death timer):

1. Set `FFE4 = 1` (cinematic flag)
2. Set `D880 = 0x17` (cinematic state)
3. Call 0x109E to copy bank 14 → VRAM 0x9000
4. Configure window layer: WX=7, WY=0
5. Disable BG (LCDC bit 5)

## Copy Routine (0x109E)

| Param | Value |
|-------|-------|
| Source | bank 14 mapped at GB 0x4000-0x7FFF |
| Destination | VRAM 0x9000 |
| Size | 0x0800 bytes (128 tiles) |
| Method | Banked copy via 0x0061 utility |

## State 0x17 Handler (0x6041 in bank 3)

- Reachable via D880 jump table at bank3:0x4A5A, entry 0x17
- Manages 9-frame death animation
- Total duration ~146 frames (~2.4s @ 60 FPS)

### Frame Timing Table (0x60A1)

| Frame | Duration |
|-------|----------|
| 0 | 0x00 (instant) |
| 1 | 0x0A |
| 2 | 0x0C |
| 3 | 0x10 |
| 4 | 0x16 |
| 5 | 0x14 |
| 6 | 0x12 |
| 7 | 0x0E |
| 8 | 0x08 |

Pattern: accelerate then decelerate — typical death-flash effect.

## Cinematic Flow

```
Game Over trigger (DCBB = 0)
  → 0x4A44 (cinematic init)
  → D880 = 0x17, FFE4 = 1
  → state handler 0x6041
  → 9-frame animation loop (146 frames)
  → A-skip path at 0x4AD4 clears FFE4 → JP 0x016C (proper cleanup)
  → Normal path leaves FFE4 set → JP 0x015F (stuck state — known DX bug?)
  → State transition to menu/idle
```

## Notes

- The "name splash" mentioned in earlier docs is the boss-name display, NOT the death cinematic
- Bank 14 is a single-purpose graphics bank: only the death sequence uses it
- Tile size 0x0800 = 128 tiles fits in one VRAM bank tile region (0x9000-0x97FF)
