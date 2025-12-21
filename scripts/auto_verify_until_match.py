#!/usr/bin/env python3
"""
Automated verification loop - runs verification until colors match references
Iteratively adjusts and verifies until accuracy is high
"""
import subprocess
import time
import json
import os
from pathlib import Path
from PIL import Image
import numpy as np
import yaml
import sys

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent))

def load_reference_sprites():
    """Load the colored sprite references"""
    project_root = Path(__file__).parent.parent
    sprites_dir = project_root / 'sprites-colored' / 'latest'
    
    references = {}
    for sprite_name in ['SARA_W', 'SARA_D', 'DRAGONFLY']:
        sprite_path = sprites_dir / f'sprite_colored_{sprite_name}.png'
        if sprite_path.exists():
            references[sprite_name] = Image.open(sprite_path).convert('RGBA')
            print(f"✓ Loaded reference: {sprite_name}")
        else:
            print(f"⚠️  Reference not found: {sprite_path}")
    
    return references


def extract_sprite_from_screenshot(img, center_x, center_y, sprite_size=24):
    """Extract sprite region from screenshot centered at given point"""
    pixels = np.array(img)
    h, w = pixels.shape[:2]
    
    half_size = sprite_size // 2
    left = max(0, center_x - half_size)
    top = max(0, center_y - half_size)
    right = min(w, center_x + half_size)
    bottom = min(h, center_y + half_size)
    
    sprite_region = pixels[top:bottom, left:right]
    return Image.fromarray(sprite_region, 'RGBA')


def color_distance(rgb1, rgb2):
    """Calculate Euclidean distance between two RGB colors"""
    return np.sqrt(sum((a - b) ** 2 for a, b in zip(rgb1, rgb2)))


def compare_sprites(reference_img, screenshot_sprite, threshold=30):
    """Compare two sprites cell-by-cell and return match statistics"""
    ref_array = np.array(reference_img)
    screen_array = np.array(screenshot_sprite)
    
    min_h = min(ref_array.shape[0], screen_array.shape[0])
    min_w = min(ref_array.shape[1], screen_array.shape[1])
    
    ref_array = ref_array[:min_h, :min_w]
    screen_array = screen_array[:min_h, :min_w]
    
    total_pixels = 0
    matching_pixels = 0
    color_distances = []
    
    for y in range(min_h):
        for x in range(min_w):
            ref_r, ref_g, ref_b, ref_a = ref_array[y, x]
            screen_r, screen_g, screen_b, screen_a = screen_array[y, x]
            
            if ref_a > 128 and screen_a > 128:
                total_pixels += 1
                ref_rgb = (ref_r, ref_g, ref_b)
                screen_rgb = (screen_r, screen_g, screen_b)
                
                dist = color_distance(ref_rgb, screen_rgb)
                color_distances.append(dist)
                
                if dist < threshold:
                    matching_pixels += 1
    
    accuracy = (matching_pixels / total_pixels * 100) if total_pixels > 0 else 0
    avg_distance = np.mean(color_distances) if color_distances else 0
    
    return {
        'total_pixels': total_pixels,
        'matching_pixels': matching_pixels,
        'accuracy': accuracy,
        'avg_color_distance': avg_distance,
        'max_distance': max(color_distances) if color_distances else 0
    }


def run_verification_cycle(rom_path: Path, output_dir: Path, cycle_num: int):
    """Run a single verification cycle"""
    from verify_palette_injection import create_verification_lua
    
    cycle_dir = output_dir / f"cycle_{cycle_num:03d}"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    
    lua_script = create_verification_lua(cycle_dir)
    
    # Use mgba-qt (works with existing DISPLAY or will use default)
    mgba_qt = '/usr/local/bin/mgba-qt'
    
    # Use absolute paths
    rom_path_abs = rom_path.resolve()
    lua_script_abs = lua_script.resolve()
    
    env = os.environ.copy()
    env['QT_QPA_PLATFORM'] = 'xcb'
    env['__GLX_VENDOR_LIBRARY_NAME'] = 'nvidia'
    # Use existing DISPLAY or default to :0
    if 'DISPLAY' not in env:
        env['DISPLAY'] = ':0'
    
    cmd = [
        mgba_qt,
        str(rom_path_abs),
        '--script', str(lua_script_abs),
        '--fastforward'
    ]
    
    print(f"\n🔄 Cycle {cycle_num}: Running verification...")
    # Launch mgba-qt
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for script to run (stops after 1200 frames)
    print("⏳ Running (script will stop after 1200 frames)...")
    time.sleep(20)
    
    # Terminate mgba-qt
    print("🛑 Terminating...")
    try:
        if proc.poll() is None:
            proc.terminate()
            time.sleep(1)
            if proc.poll() is None:
                proc.kill()
    except:
        pass
    
    # Clean up any remaining mgba processes
    subprocess.run(["pkill", "-9", "mgba-qt"], stderr=subprocess.DEVNULL, timeout=1)
    
    # Give time for screenshots to be written
    time.sleep(1)
    
    return cycle_dir


def analyze_cycle_results(cycle_dir: Path, references: dict):
    """Analyze verification cycle results"""
    screenshots = sorted(cycle_dir.glob("verify_frame_*.png"))
    
    if not screenshots:
        return None
    
    results = {}
    
    for screenshot_path in screenshots:
        try:
            screenshot_img = Image.open(screenshot_path).convert('RGBA')
            screenshot_array = np.array(screenshot_img)
            h, w = screenshot_array.shape[:2]
            center_x, center_y = w // 2, h // 2
            
            sprite_region = extract_sprite_from_screenshot(screenshot_img, center_x, center_y)
            
            for sprite_name, reference_img in references.items():
                comparison = compare_sprites(reference_img, sprite_region)
                
                if comparison['total_pixels'] > 10:
                    if sprite_name not in results:
                        results[sprite_name] = []
                    
                    results[sprite_name].append({
                        'screenshot': screenshot_path.name,
                        'accuracy': comparison['accuracy'],
                        'avg_distance': comparison['avg_color_distance'],
                        'total_pixels': comparison['total_pixels']
                    })
        
        except Exception as e:
            continue
    
    # Get best match for each sprite
    best_results = {}
    for sprite_name, matches in results.items():
        if matches:
            best_match = max(matches, key=lambda x: x['accuracy'])
            best_results[sprite_name] = best_match
    
    return best_results


def get_dominant_colors_from_screenshot(screenshot_path: Path, sprite_size=24):
    """Extract the two dominant colors from a centered sprite in screenshot"""
    try:
        img = Image.open(screenshot_path).convert('RGBA')
        pixels = np.array(img)
        h, w = pixels.shape[:2]
        center_x, center_y = w // 2, h // 2
        
        half_size = sprite_size // 2
        left = max(0, center_x - half_size)
        top = max(0, center_y - half_size)
        right = min(w, center_x + half_size)
        bottom = min(h, center_y + half_size)
        
        sprite_region = pixels[top:bottom, left:right]
        
        # Get non-transparent colors
        colors = []
        for row in sprite_region:
            for pixel in row:
                r, g, b, a = pixel
                if a > 128:  # Non-transparent
                    colors.append((r, g, b))
        
        if not colors:
            return None, None
        
        # Get two most common colors
        from collections import Counter
        color_counts = Counter(colors)
        most_common = color_counts.most_common(2)
        
        color1 = most_common[0][0] if len(most_common) > 0 else None
        color2 = most_common[1][0] if len(most_common) > 1 else None
        
        return color1, color2
    
    except Exception as e:
        return None, None


def rgb_to_bgr555_hex(r, g, b):
    """Convert RGB888 to BGR555 hex string"""
    # Convert 8-bit to 5-bit
    r5 = r >> 3
    g5 = g >> 3
    b5 = b >> 3
    
    # Pack as BGR555 (little-endian)
    bgr555 = (b5 << 10) | (g5 << 5) | r5
    return f"{bgr555:04X}"


def rebuild_rom_if_needed(project_root: Path):
    """Rebuild ROM using the GBC native patcher"""
    rom_script = project_root / 'scripts' / 'penta_cursor_dx_gbc_native.py'
    if not rom_script.exists():
        print("⚠️  ROM patching script not found, skipping rebuild")
        return False
    
    print("🔨 Rebuilding ROM with current palettes...")
    import subprocess
    result = subprocess.run(
        ['python3', str(rom_script)],
        cwd=project_root,
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✓ ROM rebuilt successfully")
        return True
    else:
        print(f"⚠️  ROM rebuild failed: {result.stderr[:200]}")
        return False


def main():
    project_root = Path(__file__).parent.parent
    # Try multiple possible ROM paths
    possible_rom_paths = [
        project_root / 'rom' / 'working' / 'Penta Dragon (J).gb',
        project_root / 'rom' / 'working' / 'penta_dragon_cursor_dx.gb',
        project_root / 'rom' / 'Penta Dragon (J).gb',
    ]
    
    rom_path = None
    for path in possible_rom_paths:
        if path.exists():
            rom_path = path
            break
    
    output_dir = project_root / 'auto_verification'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Check if ROM exists, rebuild if needed
    if not rom_path:
        print("⚠️  ROM not found, attempting to rebuild...")
        rebuild_rom_if_needed(project_root)
        
        # Check again after rebuild
        for path in possible_rom_paths:
            if path.exists():
                rom_path = path
                break
    
    if not rom_path:
        print(f"❌ ROM not found. Checked:")
        for path in possible_rom_paths:
            print(f"   - {path}")
        return
    
    print(f"✓ Using ROM: {rom_path}")
    
    # Load references
    print("📚 Loading reference sprites...")
    references = load_reference_sprites()
    
    if not references:
        print("❌ No reference sprites found")
        return
    
    # Load current palette
    palette_yaml = project_root / 'palettes' / 'monster_palettes.yaml'
    with open(palette_yaml) as f:
        palette_data = yaml.safe_load(f)
    
    max_cycles = 10
    target_accuracy = 80.0  # Target 80% accuracy
    
    print(f"\n🎯 Starting automated verification loop")
    print(f"   Target accuracy: {target_accuracy}%")
    print(f"   Max cycles: {max_cycles}")
    
    for cycle in range(1, max_cycles + 1):
        print(f"\n{'='*60}")
        print(f"CYCLE {cycle}/{max_cycles}")
        print(f"{'='*60}")
        
        # Run verification
        cycle_dir = run_verification_cycle(rom_path, output_dir, cycle)
        time.sleep(2)  # Wait for files to be written
        
        # Analyze results
        results = analyze_cycle_results(cycle_dir, references)
        
        if not results:
            print(f"⚠️  Cycle {cycle}: No results, skipping...")
            continue
        
        # Check if we've achieved target accuracy
        all_above_target = True
        worst_accuracy = 100.0
        
        print(f"\n📊 Cycle {cycle} Results:")
        for sprite_name, result in results.items():
            accuracy = result['accuracy']
            print(f"   {sprite_name}: {accuracy:.1f}% accuracy")
            
            if accuracy < target_accuracy:
                all_above_target = False
            worst_accuracy = min(worst_accuracy, accuracy)
        
        # If all above target, we're done!
        if all_above_target:
            print(f"\n✅ SUCCESS! All sprites match with >{target_accuracy}% accuracy")
            print(f"   Worst accuracy: {worst_accuracy:.1f}%")
            break
        
        # Otherwise, analyze what colors are actually being rendered
        print(f"\n🔍 Analyzing actual colors in ROM...")
        screenshots = sorted(cycle_dir.glob("verify_frame_*.png"))
        
        if screenshots:
            # Get actual colors from best screenshot
            best_screenshot = screenshots[-1]  # Use last screenshot
            color1, color2 = get_dominant_colors_from_screenshot(best_screenshot)
            
            if color1 and color2:
                print(f"   Actual colors detected:")
                print(f"     Color 1: RGB{color1} = #{color1[0]:02x}{color1[1]:02x}{color1[2]:02x}")
                print(f"     Color 2: RGB{color2} = #{color2[0]:02x}{color2[1]:02x}{color2[2]:02x}")
                
                # TODO: Compare with expected colors and adjust palette
                # For now, just report what we found
                print(f"\n   💡 Note: Palette may need adjustment to match detected colors")
        
        print(f"\n   Continuing to next cycle...")
        time.sleep(1)
    
    print(f"\n{'='*60}")
    print(f"Verification loop complete")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()

