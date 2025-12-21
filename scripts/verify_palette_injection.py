#!/usr/bin/env python3
"""
Verify palette injection by comparing colored sprite references with ROM screenshots
Does cell-by-cell color comparison when sprites are centered
"""
import subprocess
import time
import json
import os
from pathlib import Path
from PIL import Image
import numpy as np
import yaml

def load_reference_sprites():
    """Load the colored sprite references"""
    project_root = Path(__file__).parent.parent
    sprites_dir = project_root / 'sprites-colored' / 'latest'
    
    references = {}
    for sprite_name in ['SARA_W', 'SARA_D', 'DRAGONFLY']:
        sprite_path = sprites_dir / f'sprite_colored_{sprite_name}.png'
        if sprite_path.exists():
            references[sprite_name] = Image.open(sprite_path).convert('RGBA')
            print(f"✓ Loaded reference: {sprite_name} ({references[sprite_name].size})")
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


def create_verification_lua(output_dir: Path):
    """Create Lua script to capture screenshots - simplified like capture_original_sprites.py"""
    lua_script = output_dir / "palette_verify.lua"
    
    screenshot_base = str(output_dir / "verify_frame_")
    
    # Use the same approach as capture_original_sprites.py which works
    # Use absolute path for screenshot directory
    screenshot_dir_abs = str(output_dir.resolve())
    
    script_content = f'''-- Palette injection verification script
console:log("=== Palette Verification Script ===")

local frameCount = 0
local screenshotCount = 0
local screenshotDir = "{screenshot_dir_abs}"

console:log("Screenshot directory: " .. screenshotDir)
console:log("Capturing every 60 frames")

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Capture screenshot every 60 frames
    if frameCount % 60 == 0 then
        screenshotCount = screenshotCount + 1
        local filename = screenshotDir .. "/verify_frame_" .. string.format("%05d", screenshotCount) .. ".png"
        
        -- Use emu:screenshot() - wait a frame after to ensure write completes
        local success = emu:screenshot(filename)
        
        if success then
            console:log(string.format("✅ Captured frame %d: %s", frameCount, filename))
        else
            console:log(string.format("❌ Failed to capture frame %d", frameCount))
        end
    end
    
    -- Stop after 1200 frames (20 seconds at 60fps, but runs faster)
    if frameCount >= 1200 then
        console:log("Verification complete - " .. screenshotCount .. " screenshots")
        -- Wait a moment for final screenshot to be written
        callbacks:add("frame", function()
            emu:quit()
        end)
    end
end)

console:log("Palette verification script loaded")
'''
    
    with open(lua_script, 'w') as f:
        f.write(script_content)
    
    return lua_script


def run_verification(rom_path: Path, output_dir: Path):
    """Run verification using mgba-qt with Xvfb (virtual display) for headless operation"""
    lua_script = create_verification_lua(output_dir)
    
    # Use mgba-qt with Xvfb for headless operation
    mgba_qt = '/usr/local/bin/mgba-qt'
    
    # Use absolute paths
    rom_path_abs = rom_path.resolve()
    lua_script_abs = lua_script.resolve()
    
    # Check if Xvfb is available
    xvfb_available = subprocess.run(['which', 'Xvfb'], capture_output=True).returncode == 0
    
    if xvfb_available:
        # Use Xvfb to provide virtual display
        display_num = 99
        xvfb_cmd = ['Xvfb', f':{display_num}', '-screen', '0', '1024x768x24', '-ac']
        xvfb_proc = subprocess.Popen(xvfb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)  # Give Xvfb time to start
        display_env = f':{display_num}'
        print(f"✓ Using Xvfb virtual display :{display_num}")
    else:
        # Try to use existing display or fail gracefully
        display_env = os.environ.get('DISPLAY', ':0')
        print(f"⚠️  Xvfb not available, using DISPLAY={display_env}")
        xvfb_proc = None
    
    env = os.environ.copy()
    env['DISPLAY'] = display_env
    env['QT_QPA_PLATFORM'] = 'xcb'
    env['__GLX_VENDOR_LIBRARY_NAME'] = 'nvidia'
    
    cmd = [
        mgba_qt,
        str(rom_path_abs),
        '--script', str(lua_script_abs),
        '--fastforward'
    ]
    
    print(f"🚀 Launching mgba-qt with verification script...")
    print(f"   ROM: {rom_path_abs}")
    print(f"   Script: {lua_script_abs}")
    
    # Launch mgba-qt
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for script to run (stops after 1200 frames)
    print("⏳ Running (script will stop after 1200 frames)...")
    time.sleep(20)  # Give enough time for 1200 frames
    
    # Terminate mgba-qt
    print("🛑 Stopping mgba-qt...")
    try:
        if proc.poll() is None:
            proc.terminate()
            time.sleep(1)
            if proc.poll() is None:
                proc.kill()
    except:
        pass
    
    # Clean up Xvfb if we started it
    if xvfb_proc:
        try:
            xvfb_proc.terminate()
            xvfb_proc.wait(timeout=1)
        except:
            xvfb_proc.kill()
    
    # Give time for final screenshots to be written
    time.sleep(1)
    
    return output_dir


def analyze_results(output_dir: Path, references: dict):
    """Analyze screenshots and compare with references"""
    screenshots = sorted(output_dir.glob("verify_frame_*.png"))
    
    if not screenshots:
        print("❌ No screenshots found")
        return None
    
    print(f"\n📸 Analyzing {len(screenshots)} screenshots...")
    
    results = {
        'SARA_W': [],
        'SARA_D': [],
        'DRAGONFLY': []
    }
    
    for screenshot_path in screenshots:
        try:
            screenshot_img = Image.open(screenshot_path).convert('RGBA')
            screenshot_array = np.array(screenshot_img)
            h, w = screenshot_array.shape[:2]
            
            # Center of screenshot
            center_x, center_y = w // 2, h // 2
            
            # Extract sprite region
            sprite_region = extract_sprite_from_screenshot(screenshot_img, center_x, center_y)
            
            # Compare with each reference
            for sprite_name, reference_img in references.items():
                comparison = compare_sprites(reference_img, sprite_region)
                
                if comparison['total_pixels'] > 10:  # Only count if we have enough pixels
                    results[sprite_name].append({
                        'screenshot': screenshot_path.name,
                        'accuracy': float(comparison['accuracy']),
                        'avg_distance': float(comparison['avg_color_distance']),
                        'total_pixels': int(comparison['total_pixels'])
                    })
                    
                    print(f"  {screenshot_path.name} vs {sprite_name}: "
                          f"{comparison['accuracy']:.1f}% match "
                          f"(avg distance: {comparison['avg_color_distance']:.1f})")
        
        except Exception as e:
            print(f"⚠️  Error analyzing {screenshot_path}: {e}")
            continue
    
    # Calculate best matches
    best_results = {}
    for sprite_name, matches in results.items():
        if matches:
            best_match = max(matches, key=lambda x: x['accuracy'])
            best_results[sprite_name] = best_match
            print(f"\n✅ {sprite_name} best match:")
            print(f"   Screenshot: {best_match['screenshot']}")
            print(f"   Accuracy: {best_match['accuracy']:.1f}%")
            print(f"   Avg color distance: {best_match['avg_distance']:.1f}")
    
    return best_results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Verify palette injection using sprite references')
    parser.add_argument('--rom', type=str, default='rom/working/Penta Dragon (J).gb',
                        help='Path to ROM file')
    parser.add_argument('--output', type=str, default='verification_output',
                        help='Output directory for screenshots and logs')
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    rom_path = project_root / args.rom
    output_dir = project_root / args.output
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load reference sprites
    print("📚 Loading reference sprites...")
    references = load_reference_sprites()
    
    if not references:
        print("❌ No reference sprites found. Run render_colored_sprites.py first.")
        return
    
    # Run verification
    print(f"\n🔍 Running verification...")
    run_verification(rom_path, output_dir)
    
    # Analyze results
    print(f"\n📊 Analyzing results...")
    results = analyze_results(output_dir, references)
    
    # Save results
    if results:
        results_file = output_dir / 'verification_results.json'
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\n💾 Results saved to {results_file}")


if __name__ == '__main__':
    main()
