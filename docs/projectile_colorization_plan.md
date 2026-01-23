# Projectile Colorization Plan

## Goal

Implement distinct colors for projectiles based on:
1. **Source entity** - Sara W projectiles vs Sara D projectiles vs enemy projectiles
2. **Sara's powerup state** - Different colors when spiral/turbo/shield/arrow powerups are active
3. **Enemy type** - Different projectile colors for Orcs, Hornets, Crows, etc.

## Current State

### What Works
- All projectiles use **Palette 0 (white/gray)** regardless of source
- Projectile detection via **tile range 0x00-0x1F** (mainly 0x00-0x0F)
- Boss projectiles at tile range **0x78+**
- Tile-based entity coloring works well (Hornets, Orcs, Humanoids each have distinct palettes)

### Critical Constraints Discovered

**VBlank timing limitations prevent dynamic projectile ownership tracking:**
- Cannot use `AND/OR` operations in the loop
- Cannot use `PUSH/POP` for temporary storage
- Cannot read complex entity structures (0xC200+)
- Cannot build lookup tables inside the loop
- Only simple register loads and comparisons work

**What this means:**
- We CANNOT check "which entity fired this projectile" during VBlank
- We CANNOT read entity data to determine projectile ownership
- We MUST rely on either:
  1. **Tile-based approach** - Different tile IDs for different projectile types
  2. **Pre-computed state** - Set up lookup tables BEFORE entering VBlank loop
  3. **Powerup detection** - Read powerup flag like we read boss flag (0xFFBF)

## Exploration Findings

### 1. Projectile Tile Ranges
- **0x00-0x0F**: Primary projectile range (< 0x10 check)
- **0x10-0x1F**: Extended effects/projectiles
- **0x78+**: Boss projectiles (spider web, etc.)
- **Total capacity**: ~32 tiles for projectiles and effects

### 2. Powerup Types Identified
From save state analysis:
- **Spiral** - Spinning attack mode
- **Turbo** - Speed/power boost (Sara D)
- **Dragon** - Power-up item
- **Shield** - Defense active
- **Arrow Variants** - Fat arrow, diagonal arrow, bidirectional
- **Healing** - Health potions, status cures
- **P-Item** - Generic powerup

**Problem**: No memory address found yet for powerup state storage.

### 3. Entity-Projectile Association
**Projectile ownership is NOT trackable during VBlank because:**
- No explicit owner metadata in OAM sprite data
- Owner info exists only in entity data at 0xC200+ (can't read during loop)
- VBlank hook timing prevents complex lookups

**Current OAM organization:**
- Slots 0-3: Sara (both forms)
- Slots 4-39: Mixed enemies and projectiles (no explicit mapping)

## Implementation Strategy

### Approach: Hybrid Tile-Based + Dynamic Palette 0

**Core concept:**
1. **Tile-based detection** - Classify projectiles by tile ID range
2. **Dynamic palette loading** - Load different colors into Palette 0 based on Sara form + powerup state
3. **Smart allocation** - Sara W/D share palette slot since only one form exists at a time

### Palette 0 Loading Matrix

| Sara Form | Powerup | Palette 0 Colors |
|-----------|---------|------------------|
| Witch (0xFFBE=0) | None | Pink projectile |
| Witch | Spiral | Cyan projectile |
| Witch | Shield | Gold projectile |
| Dragon (0xFFBE≠0) | None | Green projectile |
| Dragon | Turbo | Orange projectile |
| Dragon | Shield | Gold projectile |

### Palette Allocation

**Current OBJ palette usage (7 of 8):**
- Palette 0: **Sara projectiles** (dynamic colors) ← REPURPOSED
- Palette 1: Sara Dragon (green)
- Palette 2: Sara Witch (pink/skin)
- Palette 3: Crow (dark blue) + **Enemy projectiles**
- Palette 4: Hornets (yellow/orange)
- Palette 5: Orc/Ground (green/brown)
- Palette 6: Humanoid (purple) OR Gargoyle boss (magenta)
- Palette 7: Catfish (cyan) OR Spider boss (red/black)

**Benefits:**
- Only 1 palette slot needed for ALL Sara projectile variations
- Scales to unlimited powerup types
- Enemy projectiles get distinct color (blue)
- No palette sacrifice required

## Implementation Phases

### Phase 1: Tile Range Discovery (CRITICAL)

**Use MCP tools to classify projectile tiles:**

Test scenarios with save states:
- Sara W firing normal projectiles
- Sara D firing normal projectiles
- Hornets firing projectiles
- Orcs firing projectiles
- Crows firing projectiles

Dump OAM for each scenario using `mcp__mgba__mgba_dump_oam`:
```python
mcp__mgba__mgba_dump_oam(
    rom_path="rom/working/penta_dragon_dx_FIXED.gb",
    savestate_path="save_states_for_claude/[scenario].ss0",
    frames=60
)
```

Build tile classification table:
- List all projectile tiles (0x00-0x1F range)
- Map each tile to its source type (Sara W, Sara D, Hornet, etc.)
- Document in `docs/projectile_tile_mapping.md`

Determine viability:
- ✅ Viable if: Different sources use different tile IDs
- ❌ Not viable if: All projectiles use same tiles (0x00-0x03)

### Phase 2: Powerup Address Discovery (OPTIONAL)

**Only pursue if user wants powerup-based coloring.**

Scan WRAM with MCP tools:
```python
mcp__mgba__mgba_read_range(
    rom_path="...",
    savestate_path="level1_sara_w_spiral_power_active.ss0",
    start_address=0xC300,  # Unexplored WRAM
    length=256
)
```

Candidate memory ranges:
- 0xC300-0xC3FF
- 0xC400-0xC4FF
- 0xFF80-0xFFDF (HRAM, excluding known addresses)

Look for bytes that change with powerup:
- Compare spiral-active vs spiral-inactive
- Compare shield-active vs normal
- Find consistent pattern

Document findings in `docs/powerup_detection.md`:
- Memory address for powerup state
- Value mappings (e.g., 0x00=none, 0x01=spiral, 0x02=shield)

### Phase 3: Implement Tile-Based Projectile Coloring

**Modify tile colorizer to handle projectile sub-ranges in v229:**

```python
# Current: All projectiles → Palette 0
code.extend([0xFE, 0x10])  # CP 0x10
code.extend([0x38, 0x00])  # JR C, projectile_palette

# New: Sub-range checks
code.extend([0xFE, 0x10])  # CP 0x10
code.extend([0x30, 0x00])  # JR NC, not_projectile

# Sub-range checks (based on Phase 1 findings):
code.extend([0xFE, 0x04])  # CP 4 (Sara W projectiles 0x00-0x03?)
code.extend([0x38, 0x00])  # JR C, sara_w_projectile

code.extend([0xFE, 0x08])  # CP 8 (Sara D projectiles 0x04-0x07?)
code.extend([0x38, 0x00])  # JR C, sara_d_projectile

# Default: enemy projectiles
code.extend([0x3E, 0x03])  # LD A, 3 (enemy projectile palette)
code.extend([0x18, 0x00])  # JR apply_palette

# sara_w_projectile:
code.extend([0x3E, 0x00])  # LD A, 0 (Palette 0 - dynamic)
code.extend([0x18, 0x00])  # JR apply_palette

# sara_d_projectile:
code.extend([0x3E, 0x00])  # LD A, 0 (Palette 0 - dynamic)
# Fall through to apply_palette
```

### Phase 4: Implement Dynamic Palette 0 Loading

**Add powerup detection and dynamic palette loading:**

1. **Read powerup flag in shadow_colorizer_main:**
```python
# After boss flag read (0xFFBF in E register):
code.extend([0xF0, powerup_addr & 0xFF])  # LDH A, [powerup_addr]
code.append(0x4F)  # LD C, A (save powerup type)
```

2. **Modify palette_loader to load dynamic Palette 0:**
```python
# Check Sara form (0xFFBE)
sara_form = read(0xFFBE)
powerup = read(0xPOWERUP_ADDR)

if powerup == SPIRAL and sara_form == WITCH:
    load_into_palette_0(cyan_colors)
elif powerup == TURBO and sara_form == DRAGON:
    load_into_palette_0(orange_colors)
elif powerup == SHIELD:
    load_into_palette_0(gold_colors)
elif sara_form == WITCH:
    load_into_palette_0(pink_projectile_colors)
elif sara_form == DRAGON:
    load_into_palette_0(green_projectile_colors)
```

3. **Add powerup palettes to YAML:**
```yaml
obj_palettes:
  SaraProjectileWitch:
    colors: ["0000", "7C1F", "5817", "3010"]  # Pink projectile
  SaraProjectileDragon:
    colors: ["0000", "03E0", "0260", "0140"]  # Green projectile
  SaraSpiral:
    colors: ["0000", "03FF", "02BF", "017F"]  # Cyan spiral
  SaraShield:
    colors: ["0000", "7FE0", "5294", "2108"]  # Gold shield
  SaraTurbo:
    colors: ["0000", "7C1F", "5817", "3010"]  # Orange/red turbo
```

### Phase 5: Testing & Verification

**Test scenarios:**

1. **Sara W projectiles:**
   - Normal state: Pink color
   - With spiral powerup: Cyan color

2. **Sara D projectiles:**
   - Normal state: Green color
   - With turbo powerup: Orange color

3. **Enemy projectiles:**
   - Should have blue/dark color (palette 3)

4. **Regression testing:**
   - Boss fights still work (Spider, Gargoyle)
   - Jet form still works (bonus stage)
   - Normal entity colors unchanged

**Success criteria:**
- ✅ Sara W and Sara D projectiles have distinct colors from each other
- ✅ Enemy projectiles have distinct color (blue vs current white)
- ✅ Powerup-based color changes work when powerup active
- ✅ No crashes or flickering
- ✅ No VBlank timing issues
- ✅ All existing features still work (bosses, jet forms, BG items)

## Files to Modify

**Create:**
- `docs/projectile_tile_mapping.md` - Tile range classification results
- `docs/powerup_detection.md` - Powerup memory address findings (if found)
- `scripts/create_vblank_colorizer_v229.py` - New version with projectile coloring

**Modify:**
- `palettes/penta_palettes_v097.yaml` - Add projectile/powerup palettes
- `CLAUDE.md` - Update with v2.29 features

**Test with:**
- `save_states_for_claude/level1_sara_w_alone.ss0` - Sara W projectiles
- `save_states_for_claude/level1_sara_d_alone.ss0` - Sara D projectiles
- `save_states_for_claude/level1_sara_w_4_hornets.ss0` - Enemy projectiles
- `save_states_for_claude/level1_sara_w_spiral_power_active.ss0` - Powerup testing

## Risk Analysis

### Risk: Projectiles share tiles with entities
**Likelihood:** Medium
**Mitigation:** Phase 1 discovery will reveal this; fall back to powerup-only approach

### Risk: Powerup address not found
**Likelihood:** Medium
**Mitigation:** Powerup coloring is optional; tile-based approach is primary goal

### Risk: VBlank timing exceeded
**Likelihood:** Low
**Mitigation:** Tile-based checks use same pattern as existing code (proven stable)

### Risk: Not enough palette slots
**Likelihood:** Low (mitigated by dynamic palette 0 approach)
**Mitigation:** Dynamic Palette 0 approach uses only 1 slot for all Sara variations

## User Decisions

**Priority**: Both entity-based AND powerup-based coloring (Hybrid approach)

**Palette strategy**: Dynamic Palette 0 with form + powerup detection

**Scope**: Comprehensive implementation - all phases
