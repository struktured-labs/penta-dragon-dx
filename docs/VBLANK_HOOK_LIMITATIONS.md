# VBlank Hook Limitations

## Overview

This document records the severe constraints discovered when implementing VBlank-based OAM colorization for Penta Dragon DX. Future sessions should reference this before attempting modifications to the colorization loop.

## Current Working Implementation (v0.96)

The stable implementation uses a VBlank hook at ROM address `0x0824` that:
1. Reads boss flag from `0xFFBF` ONCE before the loop
2. Sets enemy palette in register E (7 for boss, 4 for regular)
3. Loops through OAM slots, setting:
   - Slots 0-3: Palette 1 (Sara - green)
   - Slots 4+: Palette E (4=blue regular, 7=orange boss)

### Working Code Pattern

```asm
; === OUTSIDE LOOP (boss detection) - WORKS ===
LDH A, [0xFFBF]   ; F0 BF - Read boss flag
LD E, 7           ; 1E 07 - Assume boss (palette 7)
OR A              ; B7    - Set flags (Z if no boss)
JR NZ, +2         ; 20 02 - Skip if boss present
LD E, 4           ; 1E 04 - No boss (palette 4)

; === INSIDE LOOP - SEVERELY CONSTRAINED ===
LD A, C           ; 79    - Get slot number
CP 4              ; FE 04 - Compare to 4
JR NC, +4         ; 30 04 - Jump if slot >= 4 (enemy)
LD A, 1           ; 3E 01 - Sara palette
JR +1             ; 18 01 - Skip enemy palette
LD A, E           ; 7B    - Enemy palette from E
LD D, A           ; 57    - Save palette to D

; Then modify OAM flags byte:
LD A, [HL]        ; 7E    - Read flags
AND 0xF8          ; E6 F8 - Clear palette bits
OR D              ; B2    - Set new palette
LD [HL], A        ; 77    - Write back
```

## Instructions That WORK Inside Loop

| Instruction | Opcode | Notes |
|-------------|--------|-------|
| `LD A, C` | 79 | Load register to A |
| `LD A, E` | 7B | Load register to A |
| `LD A, n` | 3E nn | Load immediate |
| `LD D, A` | 57 | Store A to register |
| `CP n` | FE nn | Compare immediate |
| `JR NC, n` | 30 nn | **ONE instance only** |
| `JR n` | 18 nn | Unconditional jump |
| `LD A, [HL]` | 7E | Read from HL pointer |
| `LD [HL], A` | 77 | Write to HL pointer |
| `AND 0xF8` | E6 F8 | In flags modification section only |
| `OR D` | B2 | Combine palette bits |
| `INC HL` | 23 | Loop control |
| `INC C` | 0C | Loop control |
| `DEC B` | 05 | Loop control |
| `JR NZ, n` | 20 nn | **Only at loop end** |

## Instructions That CRASH Inside Loop

| Instruction | Opcode | Crash Type | When Tested |
|-------------|--------|------------|-------------|
| `AND A` | A7 | After few seconds | Palette selection |
| `AND n` | E6 nn | After button press | Palette selection (not flags) |
| `OR A` | B7 | Immediate | Inside loop |
| `OR E` | B3 | Immediate | Inside loop |
| `JR Z, n` | 28 nn | Immediate | Any conditional zero jump |
| `JR NZ, n` | 20 nn | Immediate | Inside loop body (works at end) |
| Extra `JR NC` | 30 nn | Red screen | Multiple conditionals |
| `PUSH rr` | C5/D5/E5 | Immediate | Tile lookup attempt |
| `POP rr` | C1/D1/E1 | Immediate | Tile lookup attempt |
| `ADD n` | C6 nn | After button | Palette arithmetic |
| Memory reads | Various | Immediate | Tile lookup table |

## Failed Approaches

### 1. Tile Lookup Table (Crashed)
**Goal**: Map tile IDs to palettes for per-monster-type colors
```asm
; This crashed immediately
PUSH HL           ; Save OAM pointer
LD A, [tile_byte] ; Get tile ID
LD H, lookup_hi
LD L, A
LD A, [HL]        ; Lookup palette
POP HL            ; Restore - CRASH
```
**Problem**: PUSH/POP and memory reads inside loop cause immediate crash.

### 2. Slot-Based Variety (Crashed)
**Goal**: Different palettes for different enemy slots
```asm
; This crashed after pressing buttons
LD A, C           ; Slot number
AND 3             ; E6 03 - Low 2 bits - CRASH
ADD 4             ; C6 04 - Palette 4-7 - CRASH
```
**Problem**: `AND n` and `ADD n` in palette selection crash.

### 3. OR E Boss Override (Crashed)
**Goal**: Use OR to combine slot palette with boss override
```asm
; This crashed immediately
LD A, C           ; Slot
AND 3             ; 0-3
ADD 4             ; Palette 4-7
OR E              ; If E=7 (boss), force 7 - CRASH
```
**Problem**: `OR E` inside loop crashes immediately.

### 4. Conditional Boss Check in Loop (Crashed)
**Goal**: Check boss flag per-slot
```asm
; This crashed immediately
LDH A, [0xFFBF]
OR A
JR NZ, use_boss_palette  ; CRASH - conditional in loop
```
**Problem**: `JR NZ` inside loop body crashes immediately.

## Why These Constraints?

The exact cause is unknown but likely involves:

1. **Timing sensitivity**: VBlank has limited cycles (~1140 on DMG, ~4560 on CGB double-speed)
2. **Interrupt conflicts**: The hook point may conflict with other interrupts
3. **Stack corruption**: PUSH/POP may interfere with interrupt handling
4. **Memory bus conflicts**: Additional memory reads may conflict with DMA or other operations
5. **Undocumented game state**: The game may have specific expectations about register/flag states

## What Works vs What We Wanted

| Feature | Status | Notes |
|---------|--------|-------|
| Sara distinct color | WORKS | Palette 1 (green) |
| All enemies one color | WORKS | Palette 4 (blue) |
| Boss enemies distinct | WORKS | Palette 7 (orange) when 0xFFBF != 0 |
| Varied enemy colors | FAILED | Every approach crashed |
| Per-tile-type colors | FAILED | Lookup table crashed |
| Weapon projectile colors | NOT ATTEMPTED | Would need same constrained approach |

## Recommendations for Future Work

### Option A: Patch Game's Own Code
Instead of VBlank hook, find where the game assigns OAM palette bits and patch that code directly. This is more invasive but avoids VBlank timing issues.

**Pros**: No timing constraints, full access to game state
**Cons**: Requires extensive reverse engineering, may need multiple patches

### Option B: Multiple Smaller Hooks
Instead of one loop that processes all sprites, use multiple smaller hooks at different game functions (enemy spawn, damage handler, etc.).

**Pros**: Each hook is simpler
**Cons**: Requires finding all relevant code paths

### Option C: Different Hook Point
Find an alternative hook point with fewer constraints than VBlank.

**Pros**: Might allow more complex logic
**Cons**: VBlank is typically the safest for OAM modification

### Option D: Accept Current Limitations
The 3-color system (Sara, Regular, Boss) covers the main use cases. Additional colors for weapon projectiles and explosions would use the same constrained approach.

**Pros**: Works now, stable
**Cons**: Limited variety

## Memory Addresses Discovered

| Address | Purpose | Values |
|---------|---------|--------|
| `0xFFBF` | Boss flag | 0 = no boss, non-zero = boss present |
| `0xC000-0xC09F` | Shadow OAM buffer 1 | 40 sprites * 4 bytes |
| `0xC100-0xC19F` | Shadow OAM buffer 2 | 40 sprites * 4 bytes |
| `0xFE00-0xFE9F` | Hardware OAM | 40 sprites * 4 bytes |

## Code Location

The VBlank colorizer is generated by:
```
scripts/create_vblank_colorizer.py
```

Function: `create_tile_lookup_loop()` (line ~200)

Output ROM: `rom/working/penta_dragon_dx_FIXED.gb`

## Testing Notes

When testing modifications:
1. Black screen on startup = severe crash (wrong opcode, bad jump)
2. Red screen = crash during execution (timing issue)
3. White screen = crash during initialization
4. Crash after button press = less severe timing issue
5. Works = survives button presses and gameplay

Always test with actual gameplay, not just boot screen - some crashes only manifest during game logic execution.
