# Penta Dragon BG Tile Architecture

## Overview

This document describes how the original DMG Penta Dragon ROM handles background tiles, based on reverse engineering analysis.

## Memory Map

### Tile Buffer (WRAM)
```
0xC1A0 - 0xC3DF: Tile buffer (576 bytes = 24x24 tiles)
                 Built in WRAM before copying to VRAM
```

### VRAM Tilemaps
```
0x9800 - 0x9BFF: Tilemap 0 (32x32 tiles, 1024 bytes)
0x9C00 - 0x9FFF: Tilemap 1 (32x32 tiles, 1024 bytes)
```

### Camera/Scroll Variables
```
0xDC00: Camera Y position (low byte)
0xDC01: Camera Y position (high byte)
0xDC02: Camera X position (low byte)
0xDC03: Camera X position (high byte)

The low nibble (& 0x0F) = sub-tile pixel offset (0-15)
The high bits = tile position in level data
```

### Hardware Scroll Registers
```
0xFF42 (SCY): Vertical scroll - set from 0xDC00 & 0x0F
0xFF43 (SCX): Horizontal scroll - set from 0xDC02 & 0x0F
```

## Tile Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     LEVEL DATA (ROM)                        │
│              Compressed/encoded level layout                │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                  METATILE LOOKUP (0x6790)                   │
│         Converts level IDs to 2x2 tile patterns            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              TILE BUFFER (0xC1A0 - 0xC3DF)                  │
│                    576 bytes in WRAM                        │
│              Built by routines at 0x30AF, 0x3111            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼ (via 0x42A7 copy routine)
┌─────────────────────────────────────────────────────────────┐
│                 VRAM TILEMAP (0x9800)                       │
│          Copied during HBlank windows only                  │
└─────────────────────────────────────────────────────────────┘
```

## Key Routines

### 0x42A7 - Tilemap Copy (Bank 1)
Main routine that copies tile buffer to VRAM.

```asm
; Input: H = high byte of VRAM dest (0x98 or 0x9C)
; Source: Always 0xC1A0 (hardcoded)
; Method: Wait for HBlank, copy 4 tiles, repeat

LD L, 0x00           ; L = 0
LD DE, 0xC1A0        ; Source buffer
LD C, 0x08           ; Row spacing
LD B, 0x18           ; 24 rows

outer_loop:
    DI
    ; Wait for LCD mode 3 (drawing)
    wait_mode3:
        LDH A, [STAT]
        AND 0x03
        CP 0x03
        JP NZ, wait_mode3

    ; Wait for LCD mode 0 (HBlank)
    wait_hblank:
        LDH A, [STAT]
        AND 0x03
        JP NZ, wait_hblank

    ; Copy 4 tiles during HBlank window
    LD A, [DE] / INC DE / LD [HL+], A  ; tile 1
    LD A, [DE] / INC DE / LD [HL+], A  ; tile 2
    LD A, [DE] / INC DE / LD [HL+], A  ; tile 3
    LD A, [DE] / INC DE / LD [HL+], A  ; tile 4

    EI
    ; ... repeats 6 times per row (24 tiles)

    ; Add row spacing, decrement counter
    DEC B
    JP NZ, outer_loop
RET
```

**Callers:**
- 0x0FEF (bank 0)
- 0x43BA (bank 1)
- 0x43D5 (bank 1)

### 0x09A8 - Memory Fill
```asm
; Fill memory with value in A
; HL = destination, BC = count
PUSH DE
LD E, A
loop:
    LD [HL+], A
    DEC BC
    LD A, B
    OR C
    LD A, E
    JR NZ, loop
POP DE
RET
```

### 0x4422 - Clear Tile Buffer
```asm
LD HL, 0xC1A0
LD BC, 0x0240        ; 576 bytes
XOR A                ; Fill with 0
JP 0x09A8
```

### 0x30AF - Build Tilemap from Level
Builds 6x6 metatile grid into tile buffer.

### 0x3111 - Place Single Metatile
Places a 2x2 metatile at current buffer position.

### 0x0904 - Set Scroll Registers
```asm
LD A, [0xDC00]       ; Camera Y
AND 0x0F             ; Sub-tile offset
ADD A, C             ; Add offset
LDH [SCY], A         ; Set hardware scroll

LD A, [0xDC02]       ; Camera X
AND 0x0F
ADD A, C
LDH [SCX], A
RET
```

## Tile ID Ranges (Observed)

### Gameplay Tiles
```
0x00      : Empty/transparent
0x01-0x02 : Floor (checkerboard pattern)
0x03-0x06 : Floor variants
0x10-0x3F : Wall/edge tiles (0x17 = left wall edge)
0x40-0x5F : Door/window decorations
```

### Menu/Text Tiles
```
0x80-0xBF : Japanese text characters (hiragana/katakana)
0xC0-0xDF : More text/UI elements
```

**IMPORTANT:** The same tile IDs are used for DIFFERENT purposes on different screens!
- Tile 0x8A on gameplay = possibly item
- Tile 0x8A on menu = Japanese character "ペ"

## GBC Colorization Challenge

The original DMG game has no concept of tile attributes. For GBC colorization:

1. **VRAM Bank 0** (0x9800): Tile IDs (what original game writes)
2. **VRAM Bank 1** (0x9800): Tile attributes (palette, flip, priority) - **UNUSED BY ORIGINAL**

To add color, we must write attributes to bank 1 that correspond to the tiles in bank 0.

### Approaches Attempted

| Version | Approach | Result |
|---------|----------|--------|
| v1.21 | VBlank scan 4 rows/frame | Too slow, flickering |
| v1.23 | Hook tile copy routine | Bank switching conflicts |
| v1.24 | Position-based attributes | Doesn't scroll with tilemap |
| v1.25 | Uniform palette | Works but no tile distinction |
| v1.26/27 | HDMA tile lookup | Wrong mappings cause yellow on menus |

### Recommended Approach

1. **Detect game mode** (gameplay vs menu) using camera variables or state flags
2. **On menus**: Use uniform palette 0 (safe)
3. **On gameplay**: Use tile-based lookup with CORRECT mappings:
   - 0x00-0x0F: palette 0 (floor)
   - 0x10-0x3F: palette 2 (walls)
   - 0x40-0x7F: palette 0 (decorations)
   - Skip 0x80+ (not used in gameplay)

### Hook Points

Best place to add attribute writing:
1. **After 0x42A7 completes** - add a second pass for attributes
2. **Replace CALL 0x42A7** with wrapper that does both tile + attribute copy
3. **VBlank handler** - but must detect when tilemap actually changed

## Game State Detection

### 0xFFC1 - Gameplay Active Flag
```
0x00     = Menu/title/score screen (inactive)
Non-zero = Gameplay active
```

**Evidence from ROM:**
- 0x4250: `LDH A,[0xC1] / AND A / JR Z,skip` - skip gameplay code if zero
- 0x15C7: Saves 0xFFC1, clears it, does menu work, restores it
- Multiple routines check `F0 C1 A7 C8` (LDH/AND/RET Z) pattern

**Usage for colorization:**
```asm
; In BG colorizer:
LDH A, [0xC1]     ; Check gameplay flag
AND A
JR Z, use_uniform ; If zero, use safe uniform palette
; ... tile-based coloring for gameplay
use_uniform:
; ... uniform palette 0 for menus
```

This prevents yellow text corruption on menu/score screens while
enabling tile-based coloring during actual gameplay.
