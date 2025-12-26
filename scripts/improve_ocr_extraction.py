#!/usr/bin/env python3
"""Improve OCR extraction for monster names - try multiple text regions and OCR methods"""
import yaml
from pathlib import Path
from collections import defaultdict
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np
import re

def extract_text_regions(img, sprite_y, sprite_x):
    """Extract multiple text regions around sprite - names might appear in different locations"""
    pixels = np.array(img)
    h, w = pixels.shape[:2]
    
    regions = []
    
    # Region 1: Below sprite (original)
    text_y1 = min(h, sprite_y + 20)
    text_y2 = min(h, sprite_y + 40)
    text_x1 = max(0, sprite_x - 40)
    text_x2 = min(w, sprite_x + 40)
    if text_y2 > text_y1 and text_x2 > text_x1:
        regions.append(('below', pixels[text_y1:text_y2, text_x1:text_x2]))
    
    # Region 2: Above sprite
    text_y1 = max(0, sprite_y - 40)
    text_y2 = max(0, sprite_y - 20)
    text_x1 = max(0, sprite_x - 40)
    text_x2 = min(w, sprite_x + 40)
    if text_y2 > text_y1 and text_x2 > text_x1:
        regions.append(('above', pixels[text_y1:text_y2, text_x1:text_x2]))
    
    # Region 3: To the right of sprite
    text_y1 = max(0, sprite_y - 20)
    text_y2 = min(h, sprite_y + 20)
    text_x1 = min(w, sprite_x + 20)
    text_x2 = min(w, sprite_x + 60)
    if text_y2 > text_y1 and text_x2 > text_x1:
        regions.append(('right', pixels[text_y1:text_y2, text_x1:text_x2]))
    
    # Region 4: Top of screen (HUD area)
    text_y1 = 0
    text_y2 = min(h, 20)
    text_x1 = 0
    text_x2 = w
    if text_y2 > text_y1:
        regions.append(('hud', pixels[text_y1:text_y2, text_x1:text_x2]))
    
    # Region 5: Bottom of screen
    text_y1 = max(0, h - 20)
    text_y2 = h
    text_x1 = 0
    text_x2 = w
    if text_y2 > text_y1:
        regions.append(('bottom', pixels[text_y1:text_y2, text_x1:text_x2]))
    
    return regions

def enhance_for_ocr(image):
    """Enhance image for better OCR results"""
    # Convert to grayscale if needed
    if image.mode != 'L':
        gray = image.convert('L')
    else:
        gray = image
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(gray)
    enhanced = enhancer.enhance(3.0)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(enhanced)
    sharp = enhancer.enhance(2.0)
    
    # Threshold to black/white
    threshold = sharp.point(lambda x: 0 if x < 140 else 255, '1')
    
    return threshold

def ocr_text_simple(image):
    """Simple OCR using pytesseract or easyocr if available"""
    # Try pytesseract first
    try:
        import pytesseract
        import subprocess
        
        # Check if tesseract binary is available
        try:
            subprocess.run(['tesseract', '--version'], capture_output=True, check=True, timeout=1)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            # Tesseract binary not available
            return None
        
        enhanced = enhance_for_ocr(image)
        
        # Try different PSM modes
        configs = [
            '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',  # Single line
            '--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',  # Single word
            '--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',  # Single block
        ]
        
        for config in configs:
            try:
                text = pytesseract.image_to_string(enhanced, config=config)
                text = text.strip()
                if text and len(text) > 1:  # Valid text found
                    return text
            except Exception:
                continue
    except ImportError:
        pass
    except Exception as e:
        pass
    
    # Try easyocr as fallback
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False)
        enhanced = enhance_for_ocr(image)
        # Convert PIL image to numpy array
        img_array = np.array(enhanced)
        results = reader.readtext(img_array)
        if results:
            # Get the text with highest confidence
            best_result = max(results, key=lambda x: x[2])
            text = best_result[1].strip().upper()
            if text and len(text) > 1:
                return text
    except ImportError:
        pass
    except Exception as e:
        pass
    
    return None

def extract_names_from_screenshots(screenshot_dir, monsters):
    """Re-extract names from screenshots using improved OCR"""
    screenshots = sorted(screenshot_dir.glob("verify_screenshot_*.png"))
    
    print(f"🔍 Re-extracting names from {len(screenshots)} screenshots...")
    
    # Group positions by screenshot
    screenshot_sprites = defaultdict(list)
    for monster_type, data in monsters.items():
        for x, y, screenshot_num in data['positions']:
            screenshot_sprites[screenshot_num].append((monster_type, x, y))
    
    names_found = defaultdict(set)
    text_regions_saved = 0
    
    for screenshot_path in screenshots:
        try:
            screenshot_num = int(screenshot_path.stem.split('_')[-1])
            if screenshot_num not in screenshot_sprites:
                continue
            
            img = Image.open(screenshot_path)
            
            for monster_type, x, y in screenshot_sprites[screenshot_num]:
                # Try multiple text regions
                regions = extract_text_regions(img, y, x)
                
                for region_name, region_pixels in regions:
                    if region_pixels.size == 0:
                        continue
                    
                    region_img = Image.fromarray(region_pixels)
                    
                    # Always save text region for manual inspection
                    sprite_dir = screenshot_dir / "extracted_sprites"
                    sprite_dir.mkdir(exist_ok=True)
                    text_path = sprite_dir / f"{monster_type}_text_{region_name}_{screenshot_num:03d}.png"
                    
                    # Try OCR on this region
                    name = ocr_text_simple(region_img)
                    
                    if name and len(name) > 1:
                        # Clean up the name
                        name = name.strip().upper()
                        # Remove non-alphanumeric except spaces
                        name = re.sub(r'[^A-Z0-9\s]', '', name)
                        name = ' '.join(name.split())  # Normalize spaces
                        
                        # Filter out garbage results
                        name_no_spaces = name.replace(' ', '')
                        
                        # Too short
                        if len(name) < 4:
                            continue
                        
                        # Pure numbers or mostly numbers
                        if name_no_spaces.isdigit():
                            continue
                        if len([c for c in name_no_spaces if c.isdigit()]) > len(name_no_spaces) * 0.7:
                            continue
                        
                        # Common OCR artifacts
                        if re.search(r'(.)\1{4,}', name):  # 5+ repeated chars
                            continue
                        if re.search(r'[0-9]{6,}', name):  # Long number sequences
                            continue
                        if re.search(r'[A-Z]{10,}', name):  # Very long uppercase sequences
                            continue
                        
                        # Filter patterns that look like OCR errors
                        if re.search(r'[CUO]{5,}', name):  # Common OCR confusion patterns
                            continue
                        
                        # Must have at least 2 letters (not just numbers/symbols)
                        if len([c for c in name_no_spaces if c.isalpha()]) < 2:
                            continue
                        
                        # Filter very short single words (likely fragments)
                        words = name.split()
                        if len(words) == 1 and len(words[0]) < 5:
                            continue
                        
                        # Valid name after filtering
                        names_found[monster_type].add(name)
                        # Save enhanced version for verification
                        enhanced = enhance_for_ocr(region_img)
                        enhanced_path = sprite_dir / f"{monster_type}_text_{region_name}_{screenshot_num:03d}_enhanced.png"
                        enhanced.save(enhanced_path)
                        text_regions_saved += 1
                        break  # Found a name, move to next sprite
                    else:
                        # Save original region even if OCR failed (for manual inspection)
                        region_img.save(text_path)
                        text_regions_saved += 1
        
        except Exception as e:
            print(f"  Error processing {screenshot_path}: {e}")
            continue
    
    print(f"✓ Found names for {len(names_found)} monster types")
    print(f"✓ Saved {text_regions_saved} text regions for verification")
    
    # Update monsters dict with found names
    for monster_type, names in names_found.items():
        if monster_type in monsters:
            monsters[monster_type]['names'] = names
    
    return monsters

def main():
    screenshot_dir = Path("rom/working")
    log_path = screenshot_dir / "verify_screenshot_tile_ids.txt"
    yaml_path = Path("palettes/monster_palette_map.yaml")
    
    print("🔍 Re-extracting monster names with improved OCR...")
    
    # Check if tesseract is available
    try:
        import subprocess
        subprocess.run(['tesseract', '--version'], capture_output=True, check=True, timeout=1)
        print("✓ Tesseract OCR found")
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        print("⚠️  Tesseract OCR binary not found!")
        print("   Install with: sudo apt-get install tesseract-ocr")
        print("   OCR will be skipped, but text regions will be saved for manual inspection")
    print()
    
    # Load existing YAML to get monster structure
    if yaml_path.exists():
        with open(yaml_path) as f:
            yaml_data = yaml.safe_load(f)
    else:
        print("❌ YAML file not found. Run analyze_monsters.py first.")
        return
    
    # Parse tile log to get sprite positions
    monsters = defaultdict(lambda: {
        'tiles': set(), 
        'positions': [], 
        'screenshots': set(),
        'names': set()
    })
    
    if log_path.exists():
        current_screenshot = None
        with open(log_path) as f:
            for line in f:
                match = re.match(r'Frame \d+ \(screenshot (\d+)\):', line)
                if match:
                    current_screenshot = int(match.group(1))
                    continue
                
                match = re.match(r'\s+Sprite\[(\d+)\]: tile=0x(\w+) \((\d+)\) palette=(\d+) pos=\((\d+),(\d+)\)', line)
                if match:
                    sprite_idx, tile_hex, tile_dec, palette, x, y = match.groups()
                    tile = int(tile_dec)
                    palette = int(palette)
                    x, y = int(x), int(y)
                    
                    if tile < 4:
                        monster_type = 'tiles_0_3'
                    elif tile < 8:
                        monster_type = 'tiles_4_7'
                    elif tile < 16:
                        monster_type = f'tiles_{tile // 2 * 2}_{tile // 2 * 2 + 1}'
                    else:
                        monster_type = f'tiles_{tile // 4 * 4}_{tile // 4 * 4 + 3}'
                    
                    monsters[monster_type]['tiles'].add(tile)
                    monsters[monster_type]['positions'].append((x, y, current_screenshot))
                    if current_screenshot:
                        monsters[monster_type]['screenshots'].add(current_screenshot)
    
    # Extract names with improved OCR
    monsters = extract_names_from_screenshots(screenshot_dir, monsters)
    
    # Update YAML file
    character_map = {
        'tiles_0_3': 'Sara_D_or_DragonFly',
        'tiles_4_7': 'Sara_W',
    }
    
    # Update names in YAML data
    for tile_range, char_name in character_map.items():
        if tile_range in monsters and 'names' in monsters[tile_range]:
            if char_name in yaml_data.get('monster_palette_map', {}):
                yaml_data['monster_palette_map'][char_name]['names'] = sorted(list(monsters[tile_range]['names']))
    
    # Update other monsters
    for monster_name, data in yaml_data.get('monster_palette_map', {}).items():
        # Find matching tile range
        tile_range = None
        for tr, mn in character_map.items():
            if mn == monster_name:
                tile_range = tr
                break
        
        if not tile_range:
            # Try to match by tile range
            if 'tile_range' in data:
                tiles = data['tile_range']
                if tiles:
                    if tiles[0] < 4:
                        tile_range = 'tiles_0_3'
                    elif tiles[0] < 8:
                        tile_range = 'tiles_4_7'
                    elif tiles[0] < 16:
                        tile_range = f'tiles_{tiles[0] // 2 * 2}_{tiles[0] // 2 * 2 + 1}'
                    else:
                        tile_range = f'tiles_{tiles[0] // 4 * 4}_{tiles[0] // 4 * 4 + 3}'
        
        if tile_range and tile_range in monsters and 'names' in monsters[tile_range]:
            data['names'] = sorted(list(monsters[tile_range]['names']))
    
    # Write updated YAML
    with open(yaml_path, 'w') as f:
        yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"\n✅ Updated YAML file: {yaml_path}")
    print("\n📊 Names found:")
    for monster_name, data in yaml_data.get('monster_palette_map', {}).items():
        names = data.get('names', [])
        if names:
            print(f"  {monster_name}: {', '.join(names)}")

if __name__ == "__main__":
    main()

