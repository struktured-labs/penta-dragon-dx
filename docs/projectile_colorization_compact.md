# Projectile Colorization - Compact Summary

## Goal
Add distinct colors for projectiles based on source (Sara W/D, enemies) and powerup state (spiral, turbo, shield).

## Strategy
**Hybrid approach**: Tile-based detection + Dynamic Palette 0 loading

### Key Innovation: Dynamic Palette 0
- Sara W and Sara D are mutually exclusive (only one form active at a time)
- ALL Sara projectiles use Palette 0
- Palette 0 contents loaded dynamically based on form + powerup:
  - Sara W normal → Pink projectile colors
  - Sara W + Spiral → Cyan projectile colors
  - Sara D normal → Green projectile colors
  - Sara D + Turbo → Orange projectile colors
  - Either + Shield → Gold projectile colors
- Enemy projectiles use Palette 3 (blue/dark)

### Benefits
- **Only 1 palette slot** for unlimited Sara projectile variations
- No palette sacrifice required
- Scalable to any number of powerups
- Clear visual distinction between player and enemy projectiles

## Implementation Phases

1. **Tile Range Discovery** - Use MCP tools to map projectile tiles to sources
2. **Powerup Address Hunt** - Scan WRAM to find powerup state flag
3. **Tile Colorizer Update** - Add projectile sub-range checks to v229
4. **Dynamic Palette Loader** - Load Palette 0 based on form + powerup
5. **Test & Verify** - Validate all scenarios, ensure no regressions

## Technical Details

### Memory Addresses
- 0xFFBE: Sara form (0=Witch, non-zero=Dragon) - KNOWN
- 0xFFBF: Boss flag - KNOWN
- 0xFFD0: Stage flag - KNOWN
- 0x?????: Powerup state - TO BE DISCOVERED

### Palette Allocation
- Palette 0: Sara projectiles (dynamic) ← REPURPOSED
- Palette 1: Sara Dragon sprite
- Palette 2: Sara Witch sprite
- Palette 3: Crows + Enemy projectiles
- Palette 4: Hornets
- Palette 5: Orcs
- Palette 6: Humanoids / Gargoyle boss
- Palette 7: Catfish / Spider boss

### Tile Ranges (Hypothetical - To Be Confirmed)
- 0x00-0x03: Sara W projectiles → Palette 0 (pink)
- 0x04-0x07: Sara D projectiles → Palette 0 (green)
- 0x08-0x0F: Enemy projectiles → Palette 3 (blue)
- 0x10-0x1F: Effects → Palette 0 or 3
- 0x78+: Boss projectiles → Boss palettes

## Success Criteria
- ✅ Sara W/D projectiles have distinct colors
- ✅ Enemy projectiles visually distinct from player projectiles
- ✅ Powerup-based color changes work (spiral, turbo, shield)
- ✅ No crashes, flickering, or timing issues
- ✅ All existing features work (bosses, jet forms, BG items)

## Files Modified
**New:**
- `scripts/create_vblank_colorizer_v229.py`
- `docs/projectile_tile_mapping.md`
- `docs/powerup_detection.md`

**Updated:**
- `palettes/penta_palettes_v097.yaml` (add projectile palettes)
- `CLAUDE.md` (document v2.29 features)

## Risks
- **Low**: VBlank timing (uses proven tile-based pattern)
- **Medium**: Projectiles may share tiles with entities (fallback: powerup-only)
- **Medium**: Powerup address not found (projectile base colors still work)
