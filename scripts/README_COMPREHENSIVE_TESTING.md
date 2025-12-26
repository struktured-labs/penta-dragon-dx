# Comprehensive Testing Framework

Automated testing system that combines screenshot analysis, mgba-headless logging, performance profiling, and curated sprite validation.

## Features

- **mgba-headless Testing**: Headless emulation with comprehensive logging
- **OAM/Palette Logging**: Tracks all OAM writes and palette assignments
- **Performance Profiling**: FPS monitoring and frame timing analysis
- **Screenshot Analysis**: Automatic color extraction and analysis
- **Curated Sprite Validation**: Compare expected vs actual sprite colors
- **Expected vs Actual Comparison**: Validates palette assignments against `monster_palette_map.yaml`

## Usage

### Basic Test Run

```bash
python3 scripts/run_comprehensive_tests.py [rom_path] [output_dir]
```

Example:
```bash
python3 scripts/run_comprehensive_tests.py rom/working/penta_dragon_cursor_dx.gb test_output/latest
```

### With Curated Sprites

1. Place curated sprite images in `test_output/curated_sprites/`
   - Name files after monster names (e.g., `Sara_W.png`, `Monster_tiles_100_103.png`)
   - Images should be isolated sprites (transparent background)

2. Run validation:
```bash
python3 scripts/curated_sprite_validator.py test_output/curated_sprites/
```

## Output Structure

```
test_output/
├── screenshots/          # Captured screenshots (every 60 frames)
├── logs/
│   ├── comprehensive_test.log    # Detailed log
│   ├── oam_writes.json           # OAM write events
│   ├── palette_writes.json       # Palette write events
│   └── performance.json          # Performance metrics
├── analysis/
│   └── test_report.txt          # Comprehensive report
└── summary.json                  # Quick summary JSON
```

## Report Contents

- **Performance Metrics**: Average/min/max FPS, frame timing
- **Screenshot Analysis**: Color diversity, distinct colors per frame
- **OAM Analysis**: Tile-to-palette mapping, write frequency
- **Expected vs Actual**: Accuracy percentage, mismatches, missing assignments

## Integration with CI/CD

The framework can be integrated into automated workflows:

```bash
# Run tests and check accuracy threshold
python3 scripts/run_comprehensive_tests.py && \
python3 -c "
import json
with open('test_output/latest/summary.json') as f:
    data = json.load(f)
    accuracy = data['comparison']['accuracy']
    if accuracy < 0.95:
        print(f'❌ Accuracy too low: {accuracy*100:.1f}%')
        exit(1)
    print(f'✅ Accuracy acceptable: {accuracy*100:.1f}%')
"
```

## Next Steps

1. **Curate Sprites**: Extract and label sprite images from screenshots
2. **Run Tests**: Execute comprehensive test suite
3. **Analyze Results**: Review reports and identify issues
4. **Iterate**: Fix issues and re-test

