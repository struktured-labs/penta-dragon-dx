# v2.29 Testing Guide - Projectile Colorization

## Overview

v2.29 implements projectile colorization with **educated assumptions** about tile ranges that need verification. This guide provides testing procedures to validate the implementation.

## Quick Test

```bash
# Build v2.29
uv run python scripts/create_vblank_colorizer_v229.py

# Launch with emulator
./mgba-qt.sh rom/working/penta_dragon_dx_FIXED.gb -t save_states_for_claude/level1_sara_w_alone.ss0
```

**Expected behavior**:
- Sara W's projectiles should be **pink/red** (Palette 0 - dynamic)
- Enemies' projectiles should be **blue/dark** (Palette 3)

**If projectiles are wrong color**:
- Tile ranges may be incorrect (0x00-0x07 assumption wrong)
- See "Troubleshooting" section below

## Test Scenarios

### Test 1: Sara W Projectiles (Pink/Red)

**Save state**: `level1_sara_w_alone.ss0`

**Expected**:
- Sara W sprite: Skin/pink (Palette 2) ✓
- Sara W projectiles: Bright pink/red (Palette 0 - dynamic) **← NEW**

**How to test**:
1. Load save state
2. Fire projectiles (press B repeatedly)
3. Observe projectile color

**Visual check**:
- Projectiles should be noticeably pink/red
- Distinct from Sara W's skin tone
- NOT white/gray (old Effect palette)

### Test 2: Sara D Projectiles (Green)

**Save state**: `level1_sara_d_alone.ss0`

**Expected**:
- Sara D sprite: Green (Palette 1) ✓
- Sara D projectiles: Bright green (Palette 0 - dynamic) **← NEW**

**How to test**:
1. Load save state
2. Fire projectiles (press B repeatedly)
3. Observe projectile color

**Visual check**:
- Projectiles should be bright green
- Similar to Sara D's body color
- NOT white/gray (old Effect palette)

### Test 3: Enemy Projectiles (Blue/Dark)

**Save state**: `level1_sara_w_4_hornets.ss0`

**Expected**:
- Hornet sprites: Yellow/orange (Palette 4) ✓
- Hornet projectiles: Blue/dark (Palette 3) **← NEW**

**How to test**:
1. Load save state
2. Let hornets fire projectiles
3. Observe projectile color

**Visual check**:
- Enemy projectiles should be blue/dark
- Distinct from Sara's pink/red projectiles
- Same palette as Crow enemies (Palette 3)

### Test 4: Form Switching

**Save state**: `level1_sara_w_dragon_powerup_item.ss0`

**Expected**:
1. **Before** picking up dragon powerup:
   - Sara W projectiles: Pink/red
2. **After** picking up dragon powerup:
   - Sara D projectiles: Green

**How to test**:
1. Load save state
2. Fire projectiles (observe pink/red)
3. Pick up dragon powerup item
4. Fire projectiles again (observe green)

**Visual check**:
- Projectile color changes when form changes
- Demonstrates dynamic Palette 0 loading works

### Test 5: Regression - Existing Features

**Save states**: Various

**Expected**: All v2.28 features still work:
- Boss detection (Gargoyle, Spider)
- Stage detection (Jet form colors)
- BG item colorization (gold palette)
- Tile-based monster coloring

**Critical regressions to watch for**:
- ❌ Crash on startup
- ❌ Palette flickering
- ❌ Wrong monster colors
- ❌ Boss palettes not loading

## Troubleshooting

### Issue: Projectiles are white/gray instead of colored

**Likely cause**: Tile ranges are incorrect

**Diagnosis**:
- Projectiles may be using tiles outside 0x00-0x0F range
- Or, tiles 0x10-0x1F are projectiles, not 0x00-0x0F

**Solution**:
1. Use MCP tools or Lua script to dump OAM
2. Identify actual projectile tile IDs
3. Adjust CP thresholds in `create_tile_based_colorizer()`

### Issue: Sara projectiles are wrong color (not pink for W, not green for D)

**Likely cause**: Palette 0 not loading correctly

**Diagnosis**:
- Check Sara form flag (0xFFBE) is being read
- Verify palette loader logic in `create_palette_loader()`

**Solution**:
- Add debug logging to palette loader
- Verify C register contains form state
- Check jump logic for Sara W vs Sara D

### Issue: Enemy projectiles are wrong color

**Likely cause**: Tile sub-range boundary is incorrect

**Diagnosis**:
- Enemy projectiles may use tiles 0x00-0x03 instead of 0x08-0x0F
- Or, different tile range entirely

**Solution**:
1. Dump OAM to identify enemy projectile tiles
2. Adjust `CP 0x08` threshold in colorizer
3. May need `CP 0x04`, `CP 0x06`, or other value

### Issue: All projectiles are blue/dark

**Likely cause**: Threshold comparison inverted

**Diagnosis**:
- `JR C, sara_projectile` should jump if tile < 0x08
- If inverted, all go to enemy_projectile

**Solution**:
- Check assembly logic in `check_projectile_subrange`
- Verify jump direction (C = carry = less than)

### Issue: Crash on startup or during gameplay

**Likely cause**: VBlank timing exceeded or bad opcode

**Diagnosis**:
- Added code may exceed VBlank timing budget
- Check colorizer size (106 bytes in v2.29)
- Verify no bad opcodes in generated assembly

**Solution**:
- Reduce logging/debugging code
- Optimize projectile detection logic
- Fall back to v2.28 if critical

## Adjusting Tile Ranges

If testing reveals incorrect tile ranges, adjust these values:

### In `create_tile_based_colorizer()`:

**Line ~126**: Change Sara projectile threshold
```python
code.extend([0xFE, 0x08])   # CP 0x08
# Try: 0x04, 0x06, or other based on OAM dump
```

**Options**:
- `CP 0x04`: Sara = 0x00-0x03, Enemy = 0x04-0x0F
- `CP 0x06`: Sara = 0x00-0x05, Enemy = 0x06-0x0F
- `CP 0x0A`: Sara = 0x00-0x09, Enemy = 0x0A-0x0F

### Fallback: All projectiles same color

If sub-range detection proves too complex:

```python
# Remove sub-range check
# All tiles < 0x10 get Palette 0 (dynamic)
labels['check_projectile_subrange'] = len(code)
code.extend([0x3E, 0x00])  # LD A, 0
jumps_to_fix.append((len(code), 'apply_palette'))
code.extend([0x18, 0x00])
```

This still provides form-based coloring (pink for W, green for D) but no distinction from enemy projectiles.

## Next Steps After Testing

### If tile ranges are correct:
1. Update `docs/projectile_tile_mapping.md` with "VERIFIED" status
2. Tag v2.29 as STABLE
3. Move to Phase 2: Powerup address discovery

### If tile ranges need adjustment:
1. Document actual tile ranges in `docs/projectile_tile_mapping.md`
2. Create v2.30 with corrected ranges
3. Re-test

### If projectiles can't be distinguished by tile:
1. Fall back to single Palette 0 for all projectiles
2. Focus on dynamic palette loading (form-based colors)
3. Consider powerup-based approach instead

## OAM Dumping for Tile Range Discovery

### Using Lua Script

```lua
-- Save as tmp/dump_projectiles.lua
local frame = 0
callbacks:add("frame", function()
    frame = frame + 1
    if frame == 60 then
        console:log("=== OAM Dump - Projectiles ===")
        for i = 0, 39 do
            local base = 0xFE00 + (i * 4)
            local y = emu:read8(base)
            local x = emu:read8(base + 1)
            local tile = emu:read8(base + 2)
            local flags = emu:read8(base + 3)
            if y > 0 and y <= 160 then
                console:log(string.format("Sprite %02d: Tile=0x%02X Y=%03d X=%03d Pal=%d",
                    i, tile, y, x, flags & 0x07))
            end
        end
        emu:quit()
    end
end)
```

**Run**:
```bash
./mgba-qt.sh rom/working/penta_dragon_dx_FIXED.gb \
  -t save_states_for_claude/level1_sara_w_alone.ss0 \
  --script tmp/dump_projectiles.lua
```

**Look for**:
- Sara W at tiles 0x20-0x27 (known)
- Projectiles at tiles 0x??-0x?? (discover)

## Success Criteria

### Minimum Viable (Phase 3 Complete):
- ✅ Sara W projectiles have pink/red color
- ✅ Sara D projectiles have green color
- ✅ Color changes when Sara form changes
- ✅ No crashes or flickering
- ✅ All v2.28 features still work

### Ideal (Phase 3 + Stretch Goals):
- ✅ Enemy projectiles have distinct blue/dark color
- ✅ Tile ranges verified and documented
- ✅ No regression in existing features

### Future (Phase 4 - Powerup-Based):
- ⏳ Powerup address discovered
- ⏳ Spiral powerup → Cyan projectiles
- ⏳ Shield powerup → Gold projectiles
- ⏳ Turbo powerup → Orange projectiles

## Files Reference

- **Implementation**: `scripts/create_vblank_colorizer_v229.py`
- **Palettes**: `palettes/penta_palettes_v097.yaml`
- **Tile mapping**: `docs/projectile_tile_mapping.md`
- **This guide**: `docs/v229_testing_guide.md`
