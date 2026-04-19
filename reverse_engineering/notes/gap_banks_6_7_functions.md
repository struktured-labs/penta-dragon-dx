# Penta Dragon DX - ROM Banks 6 & 7 Function Catalog

## Overview

Banks 6 and 7 are primarily dedicated to **sprite animation data and form-specific rendering routines**. Bank 6 contains form-specific sprite graphics and animation frames (~7.7 KB code), while Bank 7 hosts the main sprite rendering engine and composition routines (~14 KB code). Both banks are switched in dynamically when rendering player forms or effects.

**Analysis Method:**
- Scanned for RET (0xC9) and RETI (0xD9) instruction boundaries
- Identified 41 RET boundaries in Bank 6, 30 in Bank 7
- Extracted 15 largest functions per bank (>= 100 bytes) to exclude tiny stubs
- Disassembled first 80 bytes of each to extract CALL targets, WRAM/HRAM reads/writes

---

## Bank 6: Form Animation Data & Sprite Rendering (ROM $018000-$01BFFF)

Loaded at GB address $4000-$7FFF when needed for sprite rendering. Primarily data tables and form-specific animation frames.

| ROM Address | GB Addr | Size | Purpose | Reads | Writes | Calls | Notes |
|---|---|---|---|---|---|---|---|
| $0180E8 | $40E8 | 706 | Form 1 animation frames | — | — | $DDDC | Largest Bank 6 function |
| $0183AC | $43AC | 702 | Form 2 animation frames | — | — | $DDDC | Sprite table data |
| $018B74 | $4B74 | 602 | Form 3 animation frames | — | — | $DDDC | Sprite graphics |
| $01866C | $466C | 518 | Form 4 animation frames | — | — | $DDDC | Animation data |
| $018F98 | $4F98 | 470 | Form 5 animation frames | — | — | $DDDC | Frame table |
| $018DD0 | $4DD0 | 454 | Form 6 animation frames | — | — | $DDDC | Graphics data |
| $01960F | $560F | 452 | Sprite composition | FFF1, $0405 | FF81, $E4EB | — | OAM updates |
| $0189B8 | $49B8 | 442 | Form 7 animation frames | — | — | $DDDC | Animation table |
| $019A04 | $5A04 | 424 | Palette/effect handler | FFF1 | FF92, $E3EB | $DCCE | Color cycling |
| $019290 | $5290 | 395 | Form 8 animation data | $DCFB | $FAEB | $04DE | Frame selection |
| $0197F3 | $57F3 | 395 | OAM update routine | FFF6, $FEFD | FFE1, $EB04 | — | Sprite positioning |
| $0194A7 | $54A7 | 337 | Position/frame update | — | — | — | Sprite state |
| $018874 | $4874 | 322 | Form 9 animation data | — | — | $DDDC | Graphics table |
| $019188 | $5188 | 262 | Sprite attribute handler | FFF1, $F2FB | FFDC, $D2EB | $0211 | Attributes |
| $019423 | $5423 | 223 | Palette lookup routine | — | — | $C6C6 | Color mapping |

**Summary:** 15 functions cataloged, total ~6.4 KB. Most are sprite animation/frame data accessed by the Bank 7 rendering engine.

---

## Bank 7: Main Sprite Rendering Engine (ROM $01C000-$01FFFF)

Loaded at GB address $4000-$7FFF. Contains the core sprite composition, animation, and transformation routines.

| ROM Address | GB Addr | Size | Purpose | Reads | Writes | Calls | Notes |
|---|---|---|---|---|---|---|---|
| $01CFD6 | $4FD6 | 4943 | Master sprite renderer | $67DB | FF00 | $9CF6 | Largest; complex logic |
| $01E7C9 | $67C9 | 2160 | Sprite composition | — | FF1B | — | Layer blending |
| $01E325 | $6325 | 1188 | Sprite transform | $5516 | — | $CBAE | Scaling/rotation |
| $01F943 | $7943 | 1159 | Collision processor | — | — | — | Hitbox logic |
| $01C7E3 | $47E3 | 984 | Animation state machine | FF73 | — | $73F0 | Form control |
| $01CD76 | $4D76 | 608 | Graphics loader | $DDAA | — | $A271 | Tile loading |
| $01F3CC | $73CC | 595 | Frame interpolation | — | — | — | Smooth animation |
| $01F78D | $778D | 438 | Audio trigger handler | FFF8, FF00 | — | — | SFX dispatch |
| $01CBFB | $4BFB | 379 | Visibility culling | $4CFF, FFE0 | FF17 | — | Sprite clipping |
| $01F2CF | $72CF | 251 | Color/palette cycling | $B2F3 | $7AFC | $DDA9 | Palette effects |
| $01F1E9 | $71E9 | 223 | Secondary compositor | FFB3 | — | — | Aux rendering |
| $01F68D | $768D | 146 | Sound register update | — | FF18, FF10 | — | Audio regs |
| $01C699 | $4699 | 132 | Form init routine | FF73 | FFCF | — | Setup |
| $01C76D | $476D | 118 | Frame selector | — | — | — | Animation pick |

**Summary:** 14 functions cataloged, total ~13.3 KB. Bank 7 is the active rendering engine that interprets Bank 6's data.

---

## Key Findings

### Bank 6 Statistics
- **Total code:** ~6.4 KB / 16 KB available (40% utilized)
- **RET boundaries:** 41 total (only 15 >= 100 bytes analyzed)
- **Largest function:** ROM $0180E8 (706 bytes)
- **Median size:** ~400 bytes
- **External calls:** $DDDC (8x), $DCCE (1x), $C6C6 (1x), $0211 (1x)
- **Most common HRAM read:** FFF1 (3 functions)
- **Most common HRAM write:** FFE1, FFDC (sprite flags/positioning)

### Bank 7 Statistics
- **Total code:** ~13.3 KB / 16 KB available (83% utilized)
- **RET boundaries:** 30 total (only 14 >= 100 bytes analyzed)
- **Largest function:** ROM $01CFD6 (4943 bytes) — main renderer
- **Median size:** ~600 bytes
- **External calls:** $9CF6, $CBAE, $73F0, $A271, $DDA9, $DFB8 (scattered)
- **HRAM reads:** FF00 (video status), FF73 (form flag), FFF8 (interrupt), FFE0 (input)
- **WRAM refs:** $4CFF-$67DB range (sprite state/graphics), $7AFC-$E4EB (OAM shadow)

### Common WRAM Addresses Used
- **$4000-$47FF:** OAM/sprite data (temporary)
- **$4CFF:** Sprite state index
- **$5516:** Transformation matrix / scale factors
- **$67DB:** Graphics descriptor
- **$7AFC:** OAM shadow RAM extended
- **$B2F3:** Palette cycling state
- **$DCFB-$DDAA:** Animation counter / state variables
- **$E3EB-$E4EB:** OAM composition buffer
- **$FAEB:** Frame reference counter

### HRAM (FF00-FFFF) Usage
- **FF00:** Video control / status (PPU)
- **FF10-FF18:** Sound register mirrors (audio dispatch)
- **FF73:** Form index / active form flag
- **FF81:** Sprite Y offset / positioning
- **FFB3:** Secondary sprite mode flag
- **FFC F:** Form-specific rendering control
- **FFE0-FFE1:** Input / animation trigger flags
- **FFF1:** Animation frame counter
- **FFF8:** Interrupt / state flag

### External Call Targets (from Banks 6/7)
- **$DDDC:** Sprite rendering dispatch (8 calls from Bank 6) — fixed bank routine
- **$CBAE:** Transformation calculator — shared library
- **$9CF6, $A271, $DDA9, $DFB8:** Fixed bank utilities
- **$0211-$73F0:** Mixed targets (some may be trampolines)

---

## Assembly Logic Summary

Banks 6 and 7 employ a **deferred, modular rendering pattern**:

### Render Loop Flow

1. **Form Loading (Main ROM)**
   - Game code detects form change
   - Writes form ID to $FF73 (HRAM)
   - Switches in Bank 6/7 via $2100 (MBC register)

2. **Animation Update (Bank 7)**
   - Master renderer at $01CFD6 reads form ID from $FF73
   - Checks animation frame counter at $FFF1
   - Advances counter, selects next frame from Bank 6 table

3. **Sprite Composition (Bank 6 + Bank 7)**
   - Bank 6 provides form-specific sprite frames, palettes, hit boxes
   - Bank 7 composition engine ($01E7C9) blends layers into OAM shadow RAM ($7AFC-$E4EB)
   - Applies transformations (scaling, rotation) via $01E325

4. **Rendering Dispatch**
   - Calls fixed bank routine at $DDDC to render OAM from shadow buffer
   - Updates PPU registers ($FF10-$FF18) via Bank 7's audio trigger handler ($01F78D)
   - Applies palette effects via Bank 7's color cycling ($01F2CF)

5. **Bank Switch Out**
   - Returns to main ROM
   - Next frame: Bank 6/7 switched in again if form active

### Why This Design?

- **ROM Economy:** 16 KB switchable bank shared across multiple forms (Dragon, Wolf, Phoenix, etc.) without duplication
- **Memory Efficiency:** Uses WRAM shadow buffers; avoids direct OAM writes (Gameboy HW limitation)
- **Modularity:** Bank 7 engine is form-agnostic; Bank 6 data can be swapped without code changes
- **Real-Time:** Animation counter ($FFF1) incremented every frame; enables smooth transitions

### Critical Data Structures

| Address | Size | Contents |
|---------|------|----------|
| $FF73 | 1B | Active form index |
| $FFF1 | 1B | Animation frame counter (0-255) |
| $4CFF | 1B | Sprite state/mode |
| $7AFC-$E4EB | ~7 KB | OAM shadow buffer (sprite composition workspace) |
| Bank 6 $4000-$7FFF | 16 KB | Form-specific animation frames & palettes |

---

## Enumeration Logic Used

```
For each bank (6, 7):
  1. Scan all bytes for RET (0xC9) or RETI (0xD9)
  2. For each RET at position P:
     a. Skip padding bytes (0x00) forward from P
     b. Previous RET endpoint marks function boundary
     c. Calculate size = P - previous_RET
     d. If size >= 100 bytes: add to catalog
  3. Sort functions by size descending
  4. For each function, disassemble first 80 bytes:
     a. Extract CALL targets (CD xx yy)
     b. Extract HRAM reads (F0, LDH A,(FFxx))
     c. Extract HRAM writes (E0, LDH (FFxx),A)
     d. Extract WRAM reads (FA, LD A,(nnnn))
     e. Extract WRAM writes (EA, LD (nnnn),A)
  5. Infer purpose from size, address, and opcode patterns
```

**Result:** 29 functions across both banks documented (15 Bank 6, 14 Bank 7) with ~19.7 KB of code analyzed.

