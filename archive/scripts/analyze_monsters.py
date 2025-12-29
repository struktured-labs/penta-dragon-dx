#!/usr/bin/env python3
"""Analyze screenshots and tile logs to identify all monster types, extract sprites, use OCR for names"""
import yaml
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import re
import subprocess
import sys

def extract_sprite_from_screenshot(img, center_x, center_y, sprite_size=32):
    """Extract sprite region from screenshot"""
    pixels = np.array(img)
    h, w = pixels.shape[:2]
    
    # Extract sprite area (centered on sprite)
    x1 = max(0, center_x - sprite_size // 2)
    y1 = max(0, center_y - sprite_size // 2)
    x2 = min(w, center_x + sprite_size // 2)
    y2 = min(h, center_y + sprite_size // 2)
    
    sprite_region = pixels[y1:y2, x1:x2]
    return Image.fromarray(sprite_region)


def parse_tile_log(log_path):
    """Parse tile_ids.txt to extract sprite information"""
    monsters = defaultdict(lambda: {
        'tiles': set(), 
        'positions': [], 
        'screenshots': set(),
        'sprites': []  # Store sprite image paths
    })
    
    if not log_path.exists():
        return monsters
    
    current_screenshot = None
    with open(log_path) as f:
        for line in f:
            # Match screenshot header
            match = re.match(r'Frame \d+ \(screenshot (\d+)\):', line)
            if match:
                current_screenshot = int(match.group(1))
                continue
            
            # Match sprite data
            match = re.match(r'\s+Sprite\[(\d+)\]: tile=0x(\w+) \((\d+)\) palette=(\d+) pos=\((\d+),(\d+)\)', line)
            if match:
                sprite_idx, tile_hex, tile_dec, palette, x, y = match.groups()
                tile = int(tile_dec)
                palette = int(palette)
                x, y = int(x), int(y)
                
                # Group by tile ranges to identify monster types
                if tile < 4:
                    monster_type = 'tiles_0_3'
                elif tile < 8:
                    monster_type = 'tiles_4_7'
                elif tile < 16:
                    monster_type = f'tiles_{tile // 2 * 2}_{tile // 2 * 2 + 1}'  # Group by pairs
                else:
                    monster_type = f'tiles_{tile // 4 * 4}_{tile // 4 * 4 + 3}'  # Group by 4s
                
                monsters[monster_type]['tiles'].add(tile)
                monsters[monster_type]['positions'].append((x, y, current_screenshot))
                if current_screenshot:
                    monsters[monster_type]['screenshots'].add(current_screenshot)
    
    return monsters

def extract_sample_sprites_for_verification(screenshot_dir, monsters, samples_per_type=3):
    """Extract a few sample sprites per monster type for color/palette verification"""
    screenshots = sorted(screenshot_dir.glob("verify_screenshot_*.png"))
    sprite_dir = screenshot_dir / "extracted_sprites"
    sprite_dir.mkdir(exist_ok=True)
    
    print(f"🎨 Extracting sample sprites for color verification ({samples_per_type} per monster type)...")
    
    # Group positions by monster type
    monster_samples = defaultdict(list)
    for monster_type, data in monsters.items():
        # Get a few sample positions from different screenshots
        seen_screenshots = set()
        for x, y, screenshot_num in data['positions']:
            if screenshot_num not in seen_screenshots:
                monster_samples[monster_type].append((screenshot_num, x, y))
                seen_screenshots.add(screenshot_num)
                if len(monster_samples[monster_type]) >= samples_per_type:
                    break
    
    extracted_count = 0
    for monster_type, samples in monster_samples.items():
        for screenshot_num, x, y in samples:
            try:
                screenshot_path = screenshot_dir / f"verify_screenshot_{screenshot_num:03d}.png"
                if not screenshot_path.exists():
                    continue
                
                img = Image.open(screenshot_path)
                
                # Extract sprite
                sprite_img = extract_sprite_from_screenshot(img, x, y)
                sprite_filename = f"{monster_type}_sample_{screenshot_num:03d}_pos_{x}_{y}.png"
                sprite_path = sprite_dir / sprite_filename
                sprite_img.save(sprite_path)
                
                # Store sprite path for reference
                monsters[monster_type].setdefault('sprites', []).append(str(sprite_path))
                
                extracted_count += 1
            except Exception as e:
                print(f"  Error extracting sample for {monster_type}: {e}")
                continue
    
    print(f"✓ Extracted {extracted_count} sample sprites for verification")
    return sprite_dir

def create_monster_yaml(monsters, output_path, sprite_dir):
    """Create YAML file mapping monster types to palettes"""
    # Known character mappings
    character_map = {
        'tiles_0_3': 'Sara_D_or_DragonFly',
        'tiles_4_7': 'Sara_W',
    }
    
    # Get relative path for sprite directory
    sprite_dir_str = None
    if sprite_dir:
        try:
            sprite_dir_str = str(sprite_dir.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            # If not a subpath, just use the path as-is
            sprite_dir_str = str(sprite_dir)
    
    yaml_data = {
        'monster_palette_map': {},
        'notes': 'Auto-generated from ~100-second screenshot analysis',
        'sprite_directory': sprite_dir_str
    }
    
    # Add known characters first
    for tile_range, char_name in character_map.items():
        if tile_range in monsters:
            data = monsters[tile_range]
            yaml_data['monster_palette_map'][char_name] = {
                'tile_range': sorted(list(data['tiles'])),
                'palette': 0 if 'DragonFly' in char_name else 1,
                'screenshots': sorted(list(data['screenshots']))[:10],  # First 10
                'names': []  # Empty - will be filled manually later
            }
    
    # Add other monster types
    palette_counter = 2  # Start at palette 2 (palettes 0-1 are used)
    for tile_range, data in sorted(monsters.items()):
        if tile_range not in character_map:
            tiles = sorted(list(data['tiles']))
            if tiles:
                # Create generic name based on tile range
                monster_name = f'Monster_tiles_{tiles[0]}_{tiles[-1]}'
                
                yaml_data['monster_palette_map'][monster_name] = {
                    'tile_range': tiles,
                    'palette': palette_counter % 8,  # Cycle through palettes 0-7
                    'screenshots': sorted(list(data['screenshots']))[:10],
                    'names': [],  # Empty - will be filled manually later
                    'sprite_count': len(data.get('sprites', []))
                }
                palette_counter += 1
    
    # Write YAML file
    with open(output_path, 'w') as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"✓ Created monster palette mapping: {output_path}")
    print(f"  Found {len(yaml_data['monster_palette_map'])} monster types")
    
    # Print summary
    print("\n📊 Monster Summary:")
    for name, data in yaml_data['monster_palette_map'].items():
        print(f"  {name}:")
        print(f"    Tiles: {data['tile_range']}")
        print(f"    Palette: {data['palette']}")
        print(f"    Screenshots: {len(data['screenshots'])}")
        print(f"    Sprites extracted: {data.get('sprite_count', 0)}")

def main():
    screenshot_dir = Path("rom/working")
    log_path = screenshot_dir / "verify_screenshot_tile_ids.txt"
    output_yaml = Path("palettes/monster_palette_map.yaml")
    
    print("🔍 Analyzing monster data from screenshots and tile logs...")
    
    # Parse tile log
    monsters = parse_tile_log(log_path)
    print(f"✓ Parsed tile log: {len(monsters)} tile range groups")
    
    # Extract sample sprites for color verification only
    sprite_dir = extract_sample_sprites_for_verification(screenshot_dir, monsters, samples_per_type=3)
    
    # Create YAML mapping
    create_monster_yaml(monsters, output_yaml, sprite_dir)

if __name__ == "__main__":
    main()
