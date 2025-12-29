# Advanced Colorization Approaches

## Goal

Create an extensible colorization system that can assign distinct palettes to:
- Player character (Sara) - green
- Regular enemies (multiple types) - varied colors per type
- Mini-bosses - distinct color (orange/purple)
- Boss battles - special palette
- Weapon projectiles - distinct from enemies
- Death explosions / effects - appropriate effects palette
- Items / pickups - distinct visibility

## Current Limitation

The VBlank hook approach is severely constrained (see `VBLANK_HOOK_LIMITATIONS.md`). Only simple register operations work in the OAM processing loop, preventing:
- Tile-to-palette lookup tables
- Complex conditionals
- Stack operations

## Proposed Approaches

### Approach 1: Game Code Patching (Recommended)

**Concept**: Find where the game writes OAM data and patch those routines to include CGB palette bits.

**How It Works**:
1. Trace OAM write operations using mGBA Lua scripting
2. Identify the sprite upload function(s)
3. Patch each function to set palette bits based on context

**Implementation**:
```
Game's sprite routine:
  LD [HL], y_position
  INC HL
  LD [HL], x_position
  INC HL
  LD [HL], tile_id
  INC HL
  LD [HL], flags      ; <-- Patch here to include palette
```

**Advantages**:
- No timing constraints - runs as part of normal game code
- Full access to game context (knows what entity is being drawn)
- Can differentiate monster types at the source
- Extensible - patch each entity type's draw routine

**Challenges**:
- Requires reverse engineering each sprite routine
- May need patches in multiple locations
- Game may have generic sprite routines (harder to differentiate)

**Reverse Engineering Steps**:
1. Use `scripts/trace_oam_writes.lua` to log all OAM write addresses
2. Disassemble the code at those addresses
3. Trace back to find what entity is being drawn
4. Add palette logic based on entity type/ID

### Approach 2: Entity-Aware VBlank Hook

**Concept**: Read entity data from WRAM to determine sprite types, rather than trying to do tile lookup.

**How It Works**:
The game likely has entity structures in WRAM like:
```
Entity structure (hypothetical):
  +0: Entity type/ID
  +1: X position
  +2: Y position
  +3: Animation frame
  +4: State flags
  ...
  +N: OAM slot assignment
```

If we can find the entity-to-OAM-slot mapping:
1. Before the loop, read entity types into a small lookup table (slots 0-9)
2. In the loop, use slot number to index into pre-built palette array

**Advantages**:
- Works within VBlank constraints (pre-build lookup before loop)
- Can differentiate entity types

**Challenges**:
- Must reverse engineer entity data structures
- Entity structures may not have direct OAM slot mapping
- Pre-building lookup still needs memory access (may crash)

### Approach 3: Scanline-Based Colorization

**Concept**: Use STAT interrupt (mode 2/HBlank) instead of VBlank to color sprites on specific scanlines.

**How It Works**:
- Different screen regions get different sprite palettes
- Top portion: one palette set
- Middle: another
- Bottom: another

**Advantages**:
- Simpler logic - position-based, not type-based
- May have different timing characteristics

**Challenges**:
- Doesn't achieve per-type coloring
- STAT interrupt may have same constraints
- More complex setup

### Approach 4: DMA Shadow Buffer

**Concept**: Maintain our own OAM shadow buffer with palette info, sync to hardware OAM.

**How It Works**:
1. Hook the game's DMA trigger
2. Before DMA, modify our shadow buffer with palette bits
3. Let DMA transfer our modified data

**Advantages**:
- Intercepts at the right moment
- Can modify palettes with full access to game state

**Challenges**:
- Must find DMA trigger point
- Timing around DMA is critical
- May conflict with game's OAM updates

### Approach 5: ROM-Based Palette Embedding

**Concept**: Modify the ROM's tile data to embed palette hints, then use simple VBlank lookup.

**How It Works**:
- Monster tiles are in specific ID ranges
- Rearrange tiles so tile ID directly indicates palette
- E.g., tiles 0x50-0x5F = palette 4, 0x60-0x6F = palette 5

**Advantages**:
- Simple VBlank logic: `palette = (tile_id >> 4) - offset`
- Works within current constraints (shift/subtract are allowed)

**Challenges**:
- Must rearrange tile data in ROM
- May break animations if tiles are scattered
- Requires understanding full tile layout

## Recommended Path Forward

### Phase 1: Reverse Engineering (Required for Approaches 1, 2)

Use Lua tracing to understand:
1. Where OAM writes happen
2. Entity data structures in WRAM
3. Entity-to-sprite mapping

```lua
-- Enhanced trace script
callbacks:add("write", function(addr)
    if addr >= 0xFE00 and addr <= 0xFE9F then
        local slot = (addr - 0xFE00) // 4
        local pc = emu:getRegister("pc")
        console:log(string.format("OAM[%d] write from 0x%04X", slot, pc))
    end
end)
```

### Phase 2: Prototype Patches

Start with a single enemy type:
1. Find Sara's sprite upload code
2. Find one enemy type's sprite upload code
3. Patch each to set distinct palette bits
4. Verify no conflicts

### Phase 3: Generalize

Once pattern is understood:
1. Identify all sprite upload routines
2. Create a systematic patching approach
3. Extend to projectiles, effects, etc.

## Entity Types to Colorize

| Entity | Priority | Palette | Notes |
|--------|----------|---------|-------|
| Sara | High | 1 (green) | Currently working |
| Regular enemies | High | 4-6 (varied) | Per-type variety desired |
| Mini-bosses | High | 7 (orange) | Currently working via flag |
| Main bosses | Medium | Special | End-of-stage bosses |
| Sara's projectiles | Medium | 2 | Distinguish from enemies |
| Enemy projectiles | Medium | 5 | Danger indication |
| Death explosions | Low | 3 | Visual feedback |
| Items/pickups | Medium | 6 | Visibility |
| UI elements | Low | 0 | Text, borders |

## Next Steps

1. Run enhanced OAM trace during gameplay
2. Document all OAM write locations
3. Disassemble the most frequent write routines
4. Identify entity type at each location
5. Prototype patch for one non-Sara entity
6. If successful, extend to all entity types

## Files for Investigation

- `scripts/trace_oam_writes.lua` - OAM write tracer
- `scripts/dump_game_state.lua` - Memory dumper
- `scripts/disassemble_function.py` - Code disassembly
- `tmp/gamestate_*.txt` - Captured game states
