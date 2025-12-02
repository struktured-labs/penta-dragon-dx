# Color Names Support

The palette YAML files now support **color names** in addition to hex values, making it easier to create and modify color palettes.

## Usage

Instead of using hex BGR555 values like `"7FFF"`, you can now use readable color names:

```yaml
obj_palettes:
  MainCharacter:
    name: "Main Character"
    colors: ["transparent", "yellow", "orange", "brown"]
```

## Supported Color Names

### Basic Colors

All color names are **case-insensitive**:

- `black` - Black/transparent (0x0000)
- `white` - Pure white (0x7FFF)
- `red` - Pure red (0x001F)
- `green` - Pure green (0x03E0)
- `blue` - Pure blue (0x7C00)
- `yellow` - Yellow (0x03FF)
- `cyan` - Cyan (0x7FE0)
- `magenta` - Magenta (0x7C1F)
- `orange` - Orange (0x021F)
- `purple` - Purple (0x6010)
- `brown` - Brown (0x0215)
- `gray` / `grey` - Gray (0x4210)
- `pink` - Pink (0x5C1F)
- `lime` - Lime green (0x03E7)
- `teal` - Teal (0x7CE0)
- `navy` - Navy blue (0x5000)
- `maroon` - Maroon (0x0010)
- `olive` - Olive (0x0210)
- `transparent` - Transparent (0x0000) - useful for sprite color 0

### Color Modifiers

You can add `dark` or `light` modifiers to any base color:

```yaml
colors: ["transparent", "light blue", "blue", "dark blue"]
colors: ["black", "dark red", "red", "light red"]
colors: ["transparent", "dark green", "green", "light green"]
```

The modifiers work by scaling the RGB components:
- `dark` - Reduces brightness to 50%
- `light` - Increases brightness to 150% (capped at maximum)

## Examples

### Example 1: All Color Names
```yaml
bg_palettes:
  Dungeon:
    colors: ["white", "green", "dark green", "black"]
```

### Example 2: Mix of Hex and Names
```yaml
obj_palettes:
  MainCharacter:
    colors: ["0000", "yellow", "orange", "brown"]
```

### Example 3: Water Gradient with Modifiers
```yaml
bg_palettes:
  WaterZone:
    colors: ["white", "light blue", "blue", "dark blue"]
```

### Example 4: Fire Palette
```yaml
obj_palettes:
  EnemyFire:
    colors: ["transparent", "yellow", "orange", "red"]
```

## Benefits

1. **Readability**: `"red"` is easier to understand than `"001F"`
2. **Consistency**: Use the same color name across different palettes
3. **Quick Prototyping**: Test color schemes without looking up hex values
4. **Gradients**: Use `dark`/`light` modifiers to create smooth transitions
5. **Compatibility**: Hex values still work - use whatever you prefer!

## Testing

To test your palette changes:

1. Edit `palettes/penta_palettes.yaml` using color names
2. Run: `python scripts/create_dx_rom.py`
3. Test the ROM in your emulator
4. Iterate until satisfied!

## Technical Details

- Colors are internally converted to BGR555 format (15-bit color)
- The parser accepts both 4-digit hex and color names
- Modifiers scale RGB components before packing into BGR555
- Invalid color names fall back to hex parsing with an error message
