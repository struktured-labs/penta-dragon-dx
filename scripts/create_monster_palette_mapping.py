#!/usr/bin/env python3
"""Create comprehensive monster type to palette mapping"""
import yaml
from pathlib import Path

def create_mapping():
    """Create tile range to palette mapping for different monster types"""
    
    # Based on tile analysis and gameplay observations
    # Each monster type gets a distinct palette with 2+ colors
    mapping = {
        # Main characters (most common)
        'sara_d': {
            'tiles': [8, 9, 14, 15, 32],
            'palette': 0,  # Red/black
            'name': 'Sara D'
        },
        'sara_w': {
            'tiles': [10, 11, 12, 13, 33],
            'palette': 1,  # Green/orange
            'name': 'Sara W'
        },
        'dragon_fly': {
            'tiles': [0, 1, 80, 81, 82, 83, 84, 85, 86, 87],
            'palette': 7,  # White/blue
            'name': 'Dragon Fly'
        },
        # Enemy types (grouped by tile ranges)
        'monster_type_1': {
            'tiles': list(range(16, 32)),  # Tiles 16-31
            'palette': 2,  # Fire (red/blue)
            'name': 'Fire Enemies'
        },
        'monster_type_2': {
            'tiles': list(range(34, 50)),  # Tiles 34-49
            'palette': 3,  # Ice (cyan/white)
            'name': 'Ice Enemies'
        },
        'monster_type_3': {
            'tiles': list(range(50, 80)),  # Tiles 50-79
            'palette': 4,  # Flying (green/yellow)
            'name': 'Flying Enemies'
        },
        'monster_type_4': {
            'tiles': list(range(88, 100)),  # Tiles 88-99
            'palette': 5,  # Poison (blue/purple)
            'name': 'Poison Enemies'
        },
        'monster_type_5': {
            'tiles': list(range(100, 120)),  # Tiles 100-119
            'palette': 6,  # Mini Boss (white/yellow/purple)
            'name': 'Mini Boss'
        },
    }
    
    return mapping

def generate_assembly_logic(mapping):
    """Generate assembly code to assign palettes based on tile ranges"""
    # This will be used to update penta_cursor_dx.py
    print("Tile to Palette Mapping:")
    for monster_type, data in mapping.items():
        tiles = data['tiles']
        palette = data['palette']
        name = data['name']
        print(f"  {name}: tiles {min(tiles)}-{max(tiles)} → Palette {palette}")
    
    return mapping

if __name__ == "__main__":
    mapping = create_mapping()
    generate_assembly_logic(mapping)
    
    # Save to YAML
    output_path = Path("rom/working/monster_palette_mapping.yaml")
    with open(output_path, 'w') as f:
        yaml.dump({'monster_types': mapping}, f, default_flow_style=False)
    print(f"\n✓ Saved mapping to {output_path}")

