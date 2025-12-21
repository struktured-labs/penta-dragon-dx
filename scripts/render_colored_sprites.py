#!/usr/bin/env python3
"""Render colored sprite images from palette YAML and extracted sprites"""
import yaml
from pathlib import Path
from PIL import Image
import numpy as np
from datetime import datetime
import sys

# Color name to BGR555 mapping
COLOR_NAMES = {
    'black': 0x0000,
    'white': 0x7FFF,
    'red': 0x001F,
    'green': 0x03E0,
    'blue': 0x7C00,
    'yellow': 0x03FF,
    'cyan': 0x7FE0,
    'magenta': 0x7C1F,
    'orange': 0x021F,
    'purple': 0x6010,
    'brown': 0x0215,
    'gray': 0x4210,
    'grey': 0x4210,
    'pink': 0x5C1F,
    'lime': 0x03E7,
    'teal': 0x7CE0,
    'navy': 0x5000,
    'maroon': 0x0010,
    'olive': 0x0210,
    'transparent': 0x0000,
}

DARK_SCALE = 0.5
LIGHT_SCALE = 1.5


def parse_color(color_val) -> int:
    """Parse color value from hex string/name to BGR555 int."""
    if isinstance(color_val, int):
        return color_val & 0x7FFF
    if color_val is None:
        return 0x0000

    s = str(color_val).strip().lower()
    # Strip quotes
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        s = s[1:-1].strip()
    # Normalize 0x prefix
    if s.startswith('0x'):
        s = s[2:]

    # Named colors with optional modifiers 'light ' / 'dark '
    scale = 1.0
    if s.startswith('light '):
        s = s[6:].strip()
        scale = LIGHT_SCALE
    elif s.startswith('dark '):
        s = s[5:].strip()
        scale = DARK_SCALE

    if s in COLOR_NAMES:
        bgr = COLOR_NAMES[s] & 0x7FFF
        if scale != 1.0:
            r = bgr & 0x1F
            g = (bgr >> 5) & 0x1F
            b = (bgr >> 10) & 0x1F
            r = min(31, int(r * scale))
            g = min(31, int(g * scale))
            b = min(31, int(b * scale))
            bgr = (b << 10) | (g << 5) | r
        return bgr

    # Hex 4 digits
    if len(s) == 4 and all(ch in '0123456789abcdef' for ch in s):
        return int(s, 16) & 0x7FFF

    # Default to black if unknown
    print(f"Warning: Unknown color '{color_val}', using black")
    return 0x0000


def bgr555_to_rgb(bgr555):
    """Convert BGR555 to RGB888 tuple"""
    r = (bgr555 & 0x1F) << 3
    g = ((bgr555 >> 5) & 0x1F) << 3
    b = ((bgr555 >> 10) & 0x1F) << 3
    # Expand 5-bit to 8-bit properly
    r |= r >> 5
    g |= g >> 5
    b |= b >> 5
    return (r, g, b)


def map_grayscale_to_palette(img):
    """Map grayscale image to 2-color palette indices (0=transparent, 1=color1, 2=color2)"""
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    pixels = np.array(img)
    alpha = pixels[:, :, 3]
    rgb = pixels[:, :, :3]
    
    # Convert to grayscale
    gray = np.dot(rgb, [0.299, 0.587, 0.114])
    
    # Create palette indices
    # 0 = transparent (alpha < 128)
    # 1 = darker visible pixels
    # 2 = lighter visible pixels
    
    indices = np.zeros_like(gray, dtype=np.uint8)
    
    # Transparent pixels stay as 0
    visible_mask = alpha >= 128
    
    if np.any(visible_mask):
        visible_gray = gray[visible_mask]
        
        # Normalize visible pixels to 0-255 range
        gray_min = np.min(visible_gray)
        gray_max = np.max(visible_gray)
        
        if gray_max > gray_min:
            gray_norm = ((visible_gray - gray_min) / (gray_max - gray_min)) * 255
        else:
            # All same brightness, use all as color 1
            gray_norm = np.full_like(visible_gray, 127)
        
        # Split into 2 colors at the median
        median = np.median(gray_norm)
        indices[visible_mask] = np.where(gray_norm < median, 1, 2)
    else:
        # All transparent
        pass
    
    return indices


def apply_palette_to_sprite(sprite_img, palette_colors):
    """Apply palette colors to grayscale sprite (2 colors + transparent)"""
    # Map grayscale to palette indices (0=transparent, 1=color1, 2=color2)
    indices = map_grayscale_to_palette(sprite_img)
    
    # Use only first 3 colors from palette: transparent, color1, color2
    # (ignore color 3, or use it as color2 if only 3 colors provided)
    if len(palette_colors) < 3:
        # Pad with black if needed
        palette_colors = list(palette_colors) + ['black'] * (3 - len(palette_colors))
    
    # Convert palette colors to RGB (only need colors 0, 1, 2)
    rgb_colors = [
        bgr555_to_rgb(parse_color(palette_colors[0])),  # Transparent (will be set to 0 alpha)
        bgr555_to_rgb(parse_color(palette_colors[1])),  # Color 1
        bgr555_to_rgb(parse_color(palette_colors[2])),  # Color 2
    ]
    
    # Create colored image
    h, w = indices.shape
    colored = np.zeros((h, w, 4), dtype=np.uint8)
    
    # Map indices to colors
    for i in range(3):
        mask = indices == i
        if i == 0:
            # Transparent
            colored[mask, 3] = 0
        else:
            # Color 1 or 2
            colored[mask, 0] = rgb_colors[i][0]  # R
            colored[mask, 1] = rgb_colors[i][1]  # G
            colored[mask, 2] = rgb_colors[i][2]  # B
            colored[mask, 3] = 255  # Opaque
    
    return Image.fromarray(colored, 'RGBA')


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Render colored sprite images from palette YAML')
    parser.add_argument('--qualifier', '-q', type=str, default=None,
                        help='Optional qualifier for output directory (e.g., "v1", "test")')
    args = parser.parse_args()
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    # Paths
    palette_yaml = project_root / 'palettes' / 'monster_palettes.yaml'
    sprites_dir = project_root / 'sprites-extracted'
    output_dir = project_root / 'sprites-colored'
    
    # Create output directory with timestamp and optional qualifier
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if args.qualifier:
        output_subdir = output_dir / f'colored_{args.qualifier}_{timestamp}'
    else:
        output_subdir = output_dir / f'colored_{timestamp}'
    output_subdir.mkdir(parents=True, exist_ok=True)
    
    # Load palette YAML
    print(f"Loading palettes from {palette_yaml}...")
    with open(palette_yaml) as f:
        data = yaml.safe_load(f)
    
    monster_palettes = data.get('monster_palettes', {})
    print(f"Found {len(monster_palettes)} monster palettes\n")
    
    # Load monster names mapping
    json_path = project_root / 'monster_names_extracted.json'
    monster_names = {}
    if json_path.exists():
        import json
        with open(json_path) as f:
            monster_data = json.load(f)
        for frame_name, frame_data in monster_data.items():
            monster_name = frame_data.get('monster_name', '')
            if monster_name:
                # Convert to key format (e.g., "SARA W" -> "SARA_W")
                key = monster_name.replace(' ', '_').upper()
                monster_names[key] = monster_name
    
    # Process each sprite
    sprite_files = sorted(sprites_dir.glob('sprite_*.png'))
    print(f"Processing {len(sprite_files)} sprites...\n")
    
    success_count = 0
    for sprite_path in sprite_files:
        # Extract monster name from filename (e.g., sprite_SARA_W.png -> SARA_W)
        sprite_name = sprite_path.stem.replace('sprite_', '')
        
        # Find matching palette
        palette = monster_palettes.get(sprite_name)
        if not palette:
            print(f"⚠️  {sprite_name}: No palette found, skipping")
            continue
        
        palette_colors = palette.get('colors', [])
        if len(palette_colors) < 3:
            print(f"⚠️  {sprite_name}: Palette has {len(palette_colors)} colors (need at least 3: transparent + 2 colors), skipping")
            continue
        
        # Load sprite
        try:
            sprite_img = Image.open(sprite_path)
        except Exception as e:
            print(f"✗ {sprite_name}: Failed to load sprite: {e}")
            continue
        
        # Apply palette
        try:
            colored_img = apply_palette_to_sprite(sprite_img, palette_colors)
        except Exception as e:
            print(f"✗ {sprite_name}: Failed to apply palette: {e}")
            continue
        
        # Save colored sprite
        display_name = palette.get('name', sprite_name)
        output_filename = f"sprite_colored_{sprite_name}.png"
        output_path = output_subdir / output_filename
        
        colored_img.save(output_path, 'PNG')
        print(f"✓ {display_name:15s} -> {output_filename}")
        success_count += 1
    
    print(f"\n✅ Rendered {success_count}/{len(sprite_files)} colored sprites")
    print(f"📁 Output directory: {output_subdir}")
    
    # Also create a symlink to latest
    latest_link = output_dir / 'latest'
    if latest_link.exists() or latest_link.is_symlink():
        latest_link.unlink()
    latest_link.symlink_to(output_subdir.name)
    print(f"🔗 Latest link: {latest_link}")


if __name__ == '__main__':
    main()

