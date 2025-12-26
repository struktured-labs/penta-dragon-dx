# Scalable Palette Assignment Approach for ~50 Monster Types

## Problem Statement

Current approach has limitations:
1. **Game overwrites OAM modifications** - Input handler runs too early
2. **Complex branching causes crashes** - Many if/else chains are fragile
3. **Not scalable** - Adding new monster types requires complex code changes

## Solution: Tile-to-Palette Lookup Table + VBlank Hook

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  Tile-to-Palette Lookup Table (256 bytes)              │
│  Bank 13 @ 0x6E00                                       │
│  Each byte: tile_id (0-255) → palette_id (0-7)         │
│  0xFF = don't modify (keep game's original palette)     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  VBlank Interrupt Hook (0x0040)                        │
│  - Runs AFTER game updates OAM                          │
│  - Calls palette assignment function                    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  Palette Assignment Function (~50 bytes)                │
│  - Iterate all 40 sprites                              │
│  - Read tile ID from OAM                                │
│  - Look up palette: palette = table[tile_id]            │
│  - Apply palette if != 0xFF                             │
│  - No complex branching - just table lookup             │
└─────────────────────────────────────────────────────────┘
```

### Key Benefits

1. **Scalable**: Add monster types by updating table entries
   - No code changes needed
   - Just modify bytes in lookup table

2. **Simple**: No complex if/else chains
   - Single table lookup per sprite
   - O(1) complexity

3. **Reliable**: VBlank timing ensures game finished updating
   - Runs after game's sprite update code
   - Our changes won't be overwritten

4. **Maintainable**: Easy to add/modify mappings
   - Update YAML config → regenerate table
   - No assembly code changes

5. **Fast**: Table lookup is very fast
   - Single memory read per sprite
   - Minimal CPU overhead

### Implementation Details

#### 1. Lookup Table Structure

```python
# 256-byte table at Bank 13 @ 0x6E00
table = [0xFF] * 256  # Initialize: don't modify any tiles

# Example mappings:
table[8] = 0   # Tile 8 → Palette 0 (Sara D)
table[9] = 0   # Tile 9 → Palette 0 (Sara D)
table[10] = 1  # Tile 10 → Palette 1 (Sara W)
table[11] = 1  # Tile 11 → Palette 1 (Sara W)
# ... etc for all 50 monster types
```

#### 2. VBlank Hook

```assembly
; Hook at 0x0040 (VBlank interrupt)
JP vblank_handler_addr

; VBlank handler:
vblank_handler:
    PUSH AF, BC, DE, HL
    LD A, 13
    LD [2000], A          ; Switch to bank 13
    CALL assign_palettes  ; Our function
    LD A, 1
    LD [2000], A          ; Switch back to bank 1
    POP HL, DE, BC, AF
    JP original_vblank    ; Call original handler
```

#### 3. Palette Assignment Function

```assembly
assign_palettes:
    PUSH AF, BC, DE, HL
    LD HL, 0xFE00         ; OAM base
    LD B, 40              ; 40 sprites
    LD C, 0               ; Sprite index
    
.loop:
    ; Calculate sprite address: HL + (C * 4)
    LD A, C
    ADD A, A              ; *2
    ADD A, A              ; *4
    LD E, A
    LD A, L
    ADD A, E
    LD L, A               ; HL now points to sprite Y
    
    ; Check if sprite is visible
    LD A, [HL]
    AND A
    JR Z, .skip           ; Y=0 means sprite not used
    CP 144
    JR NC, .skip          ; Y>=144 means off-screen
    
    ; Get tile ID
    INC HL                ; Point to X
    INC HL                ; Point to tile ID
    LD A, [HL]            ; Get tile ID
    PUSH HL               ; Save tile address
    
    ; Look up palette from table
    LD HL, 0x6E00         ; Table base (in bank 13)
    LD E, A               ; Tile ID
    LD D, 0
    ADD HL, DE            ; HL = table[tile_id]
    LD A, [HL]            ; Get palette from table
    
    ; Check if we should modify (A != 0xFF)
    CP 0xFF
    JR Z, .no_modify      ; Don't modify if 0xFF
    
    ; Apply palette
    POP HL                ; Restore tile address
    INC HL                ; Point to flags byte
    LD D, A               ; Save palette
    LD A, [HL]            ; Get flags
    AND 0xF8              ; Clear palette bits (0-2)
    OR D                  ; Set palette
    LD [HL], A            ; Write back
    
    JR .next
    
.no_modify:
    POP HL                ; Restore tile address
    
.skip:
    LD HL, 0xFE00         ; Reset OAM base
    INC C                 ; Next sprite
    DEC B
    JR NZ, .loop
    
    POP HL, DE, BC, AF
    RET
```

### Adding New Monster Types

To add a new monster type:

1. **Identify tile IDs** used by the monster
2. **Update lookup table**:
   ```python
   # Example: Fire enemies use tiles 16-31
   for tile in range(16, 32):
       table[tile] = 2  # Palette 2 (Fire)
   ```
3. **Rebuild ROM** - no code changes needed!

### Comparison with Current Approach

| Aspect | Current (Branching) | New (Lookup Table) |
|--------|-------------------|-------------------|
| **Scalability** | ❌ Complex branching | ✅ Simple table |
| **Adding types** | ❌ Code changes | ✅ Table update |
| **Reliability** | ❌ Timing issues | ✅ VBlank timing |
| **Code size** | ❌ Grows with types | ✅ Fixed size |
| **Maintainability** | ❌ Complex | ✅ Simple |

### Memory Layout

```
Bank 13 (free space):
  0x6C80-0x6CFF: Palette data (128 bytes)
  0x6D00-0x6DFF: Functions (256 bytes)
  0x6E00-0x6EFF: Lookup table (256 bytes) ← NEW
  0x6F00-0x6FFF: Reserved for expansion
```

### Next Steps

1. ✅ Create lookup table generator script
2. ✅ Implement VBlank hook
3. ✅ Implement palette assignment function
4. ⏳ Test with current 2 monster types
5. ⏳ Expand to all 50 monster types
6. ⏳ Create YAML → table generator

### Risk Assessment

**Low Risk:**
- Lookup table approach is standard pattern
- VBlank hook is well-understood technique
- Simple code = fewer bugs

**Mitigation:**
- Test incrementally (2 → 5 → 10 → 50 types)
- Keep original VBlank handler as fallback
- Use 0xFF flag to disable modifications per tile

