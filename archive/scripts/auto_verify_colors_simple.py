#!/usr/bin/env python3
"""
Simplified automated color verification loop.
Builds ROM, launches mgba-headless, captures screenshots, analyzes colors.
When modifications are needed, outputs instructions for Cursor to make changes.
"""
import subprocess
import time
import sys
from pathlib import Path

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pillow", "numpy"], check=True)
    from PIL import Image
    import numpy as np

def load_current_palettes():
    """Load current palette configuration from YAML"""
    try:
        import yaml
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pyyaml"], check=True)
        import yaml
    
    palette_path = Path("palettes/penta_palettes.yaml")
    if not palette_path.exists():
        return None
    try:
        with open(palette_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"⚠️  Could not load palette YAML: {e}")
        return None

def save_palettes(palettes):
    """Save palette configuration to YAML"""
    try:
        import yaml
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pyyaml"], check=True)
        import yaml
    
    palette_path = Path("palettes/penta_palettes.yaml")
    try:
        with open(palette_path, 'w') as f:
            yaml.dump(palettes, f, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        print(f"⚠️  Could not save palette YAML: {e}")
        return False

def generate_next_palette_config(iteration):
    """Generate a new palette configuration"""
    palettes = load_current_palettes()
    if not palettes:
        return None
    
    color_sets = [
        {'sara_d': ['transparent', '001F', '001F', '001F'],  # Red
         'sara_w': ['transparent', '03E0', '03E0', '03E0'],  # Green
         'dragon_fly': ['transparent', '7C00', '7C00', '7C00']},  # Blue
        {'sara_d': ['transparent', '7C1F', '7C1F', '7C1F'],  # Magenta
         'sara_w': ['transparent', '03FF', '03FF', '03FF'],  # Cyan
         'dragon_fly': ['transparent', '7FE0', '7FE0', '7FE0']},  # Yellow
        {'sara_d': ['transparent', '021F', '021F', '021F'],  # Orange
         'sara_w': ['transparent', '6010', '6010', '6010'],  # Purple
         'dragon_fly': ['transparent', '03E7', '03E7', '03E7']},  # Lime
        {'sara_d': ['transparent', '7FFF', '7FFF', '7FFF'],  # White
         'sara_w': ['transparent', '001F', '001F', '001F'],  # Red
         'dragon_fly': ['transparent', '7FE0', '4A00', '2100']},  # Yellow/Orange
        {'sara_d': ['transparent', '5000', '5000', '5000'],  # Dark Blue
         'sara_w': ['transparent', '7D00', '7D00', '7D00'],  # Light Blue
         'dragon_fly': ['transparent', '7FE0', '7FE0', '7FE0']},  # Yellow
    ]
    
    config = color_sets[(iteration - 1) % len(color_sets)]
    palettes['obj_palettes']['MainCharacter']['colors'] = config['sara_d']
    palettes['obj_palettes']['EnemyBasic']['colors'] = config['sara_w']
    palettes['obj_palettes']['MainBoss']['colors'] = config['dragon_fly']
    
    return palettes

def build_rom():
    """Build the ROM using penta_cursor_dx.py"""
    result = subprocess.run(
        ["uv", "run", "scripts/penta_cursor_dx.py"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print(f"Build failed: {result.stderr}")
        return False
    print("✅ ROM built successfully")
    return True

def create_lua_screenshot_script():
    """Create Lua script for mGBA to take screenshots"""
    screenshot_dir = Path("rom/working").resolve()
    script_path = screenshot_dir / "scripts" / f"mgba_script_{int(time.time() * 1000)}.lua"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    script_content = f'''-- Screenshot script generated at {time.time()}
local startFrame = 1800  -- 30 seconds at 60fps
local screenshotInterval = 300  -- Every 5 seconds
local maxFrames = 7200  -- 120 seconds max
local screenshotCount = 0
local screenshotBase = "{screenshot_dir}/screenshot_"

console:log("Screenshot script loaded. Will capture every 5 seconds starting at 30 seconds")

local function takeScreenshot()
    screenshotCount = screenshotCount + 1
    local screenshotPath = screenshotBase .. screenshotCount .. ".png"
    local success = emu:screenshot(screenshotPath)
    if success then
        console:log("📸 Screenshot " .. screenshotCount .. " saved: " .. screenshotPath)
    else
        console:log("⚠️  Screenshot " .. screenshotCount .. " failed")
    end
end

local frameCount = 0
local function onFrame()
    frameCount = frameCount + 1
    if frameCount >= startFrame and (frameCount - startFrame) % screenshotInterval == 0 then
        takeScreenshot()
    end
    if frameCount >= maxFrames then
        emu:stop()
    end
end

callbacks:add("frame", onFrame)
'''
    
    script_path.write_text(script_content)
    return script_path

def launch_mgba_with_lua(lua_script_path):
    """Launch mgba-headless with Lua script"""
    mgba_headless_path = subprocess.run(["which", "mgba-headless"], capture_output=True, text=True).stdout.strip()
    if not mgba_headless_path:
        print("❌ mgba-headless not found!")
        return None
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb").resolve()
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return None
    
    cmd = [mgba_headless_path, "--script", str(lua_script_path.resolve()), str(rom_path)]
    print(f"🚀 Launching: {' '.join(cmd)}")
    
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    return proc

def cleanup_mgba():
    """Kill any running mGBA instances"""
    subprocess.run(["pkill", "-9", "-f", "mgba"], timeout=5, capture_output=True)
    time.sleep(1)

def wait_for_screenshots(max_wait=20):
    """Wait for screenshots to appear"""
    screenshot_dir = Path("rom/working")
    screenshots = []
    start = time.time()
    while time.time() - start < max_wait:
        screenshots = list(screenshot_dir.glob("screenshot_*.png"))
        if screenshots:
            valid = [s for s in screenshots if s.stat().st_size >= 2048]
            if valid:
                return valid
        time.sleep(1)
    return screenshots if screenshots else None

def analyze_sprite_colors(screenshot_path):
    """Analyze screenshot to detect distinct colors for Sara D, Sara W, and Dragon Fly"""
    try:
        img = Image.open(screenshot_path)
        img_array = np.array(img)
        height, width = img_array.shape[:2]
        
        # Define regions for the three sprites
        sara_d_region = img_array[max(0, height//4):min(height, height//2), max(0, width//8):min(width, width//3)]
        sara_w_region = img_array[max(0, height//4):min(height, height//2), max(0, width//3):min(width, 2*width//3)]
        dragon_fly_region = img_array[max(0, height//8):min(height, height//3), max(0, 2*width//3):min(width, width)]
        
        def get_dominant_colors(region, k=3):
            if region.size == 0:
                return np.array([])
            pixels = region.reshape(-1, region.shape[-1])
            if pixels.shape[1] == 4:
                pixels = pixels[:, :3]
            non_black = pixels[np.sum(pixels, axis=1) > 30]
            if len(non_black) == 0:
                return np.array([])
            from collections import Counter
            colors = [tuple(p) for p in non_black]
            most_common = Counter(colors).most_common(k)
            return np.array([c[0] for c in most_common])
        
        sara_d_colors = get_dominant_colors(sara_d_region)
        sara_w_colors = get_dominant_colors(sara_w_region)
        dragon_fly_colors = get_dominant_colors(dragon_fly_region)
        
        if len(sara_d_colors) == 0 or len(sara_w_colors) == 0 or len(dragon_fly_colors) == 0:
            return None, None, None, False, 0
        
        def color_distance(c1, c2):
            return np.sqrt(np.sum((c1.astype(float) - c2.astype(float)) ** 2))
        
        distances = []
        for sd_color in sara_d_colors[:2]:
            for sw_color in sara_w_colors[:2]:
                distances.append(color_distance(sd_color, sw_color))
            for df_color in dragon_fly_colors[:2]:
                distances.append(color_distance(sd_color, df_color))
        for sw_color in sara_w_colors[:2]:
            for df_color in dragon_fly_colors[:2]:
                distances.append(color_distance(sw_color, df_color))
        
        if len(distances) == 0:
            return None, None, None, False, 0
        
        min_distance = min(distances)
        all_different = min_distance > 50
        return sara_d_colors, sara_w_colors, dragon_fly_colors, all_different, min_distance
    except Exception as e:
        print(f"Error analyzing colors: {e}")
        return None, None, None, False, 0

def analyze_and_suggest_modifications(iteration, results, debug_output):
    """
    Analyze results and suggest ROM modifications.
    Outputs instructions for Cursor to make changes directly.
    """
    print("\n" + "="*70)
    print("🧠 ANALYSIS: Suggesting ROM modifications")
    print("="*70)
    
    screenshot_count = results.get("screenshot_count", 0)
    color_distance = results.get("color_distance", 0)
    all_different = results.get("all_different", False)
    
    suggestions = []
    
    if screenshot_count == 0:
        suggestions.append("Game may be frozen - consider trying VBlank hook instead of boot loader")
    elif color_distance < 50:
        suggestions.append(f"Colors too similar (distance {color_distance:.2f})")
        suggestions.append("Try sprite OAM palette assignment - modify sprite flags directly")
        suggestions.append("Or try VBlank hook to reload palettes every frame")
    
    # Strategy based on iteration
    if iteration <= 2:
        strategy = "Continue with boot-time palette loading"
    elif iteration <= 4:
        strategy = "Try VBlank interrupt hook (0x0040) to reload palettes every frame"
    elif iteration <= 6:
        strategy = "Try sprite OAM attribute modification - set palette bits in sprite flags"
    elif iteration <= 8:
        strategy = "Try late initialization - load palettes after game starts"
    else:
        strategy = "Try hybrid: boot loader + VBlank refresh"
    
    print(f"\n💡 Suggested modifications for next iteration:")
    print(f"   Strategy: {strategy}")
    for i, suggestion in enumerate(suggestions, 1):
        print(f"   {i}. {suggestion}")
    
    print(f"\n📝 Cursor will make these changes to scripts/penta_cursor_dx.py")
    print("="*70 + "\n")
    
    return {
        "strategy": strategy,
        "suggestions": suggestions
    }

def main():
    """Main verification loop"""
    import atexit
    import signal
    
    atexit.register(cleanup_mgba)
    signal.signal(signal.SIGINT, lambda s, f: (cleanup_mgba(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (cleanup_mgba(), sys.exit(0)))
    
    print("=" * 60)
    print("AUTOMATED COLOR VERIFICATION LOOP")
    print("=" * 60)
    print()
    
    cleanup_mgba()
    
    iteration = 0
    screenshot_dir = Path("rom/working").resolve()
    print(f"📸 Screenshots will be saved to: {screenshot_dir}/screenshot_XX.png")
    print("🔄 Starting infinite loop - will stop when distinct colors are detected...")
    print()
    
    try:
        start_time = time.time()
        last_report_time = time.time()
        report_interval = 300
        
        print(f"\n{'='*70}")
        print(f"🚀 STARTING COLOR VERIFICATION LOOP")
        print(f"{'='*70}")
        print(f"🕐 Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"🎯 Target: Sara D ≠ Sara W ≠ Dragon Fly")
        print(f"{'='*70}\n")
        
        while True:
            try:
                iteration += 1
                print(f"\n{'='*70}")
                print(f"🔄 ITERATION {iteration}")
                print(f"{'='*70}")
                
                # Generate new palette configuration
                print(f"\n🎨 Generating new palette configuration...")
                palettes = generate_next_palette_config(iteration)
                if palettes:
                    save_palettes(palettes)
                    print(f"✅ Saved palette config")
                
                # Build ROM
                print(f"\n🔨 Building ROM...")
                if not build_rom():
                    print("❌ Build failed, skipping iteration")
                    continue
                
                # Create Lua script
                print(f"\n📝 Creating Lua screenshot script...")
                lua_script_path = create_lua_screenshot_script()
                
                # Launch mGBA
                print(f"\n🚀 Launching mgba-headless...")
                mgba_proc = launch_mgba_with_lua(lua_script_path)
                if not mgba_proc:
                    print("❌ Failed to launch mGBA")
                    continue
                
                # Wait for screenshots
                print("⏳ Waiting for screenshots (30s start, every 5s)...")
                mgba_start_time = time.time()
                debug_output = {"stdout": [], "stderr": []}
                
                # Simple wait loop
                while time.time() - mgba_start_time < 140:
                    if mgba_proc.poll() is not None:
                        break
                    time.sleep(5)
                
                # Kill mGBA
                print("🛑 Stopping mGBA...")
                try:
                    if mgba_proc.poll() is None:
                        mgba_proc.kill()
                except:
                    pass
                cleanup_mgba()
                time.sleep(2)
                
                # Get screenshots
                screenshot_paths = wait_for_screenshots(max_wait=20)
                
                if not screenshot_paths:
                    print("❌ No screenshots captured")
                    continue
                
                print(f"✅ Captured {len(screenshot_paths)} screenshots")
                
                # Analyze colors
                print("\n🔍 Analyzing colors...")
                best_result = None
                best_distance = 0
                
                for screenshot_path in screenshot_paths:
                    sara_d_colors, sara_w_colors, dragon_fly_colors, all_different, min_distance = analyze_sprite_colors(screenshot_path)
                    
                    if sara_d_colors is not None and sara_w_colors is not None and dragon_fly_colors is not None:
                        print(f"  📸 {screenshot_path.name}: distance={min_distance:.2f}, distinct={all_different}")
                        if min_distance > best_distance:
                            best_distance = min_distance
                            best_result = (screenshot_path, sara_d_colors, sara_w_colors, dragon_fly_colors, all_different, min_distance)
                
                # Check success
                if best_result and best_result[4]:  # all_different
                    print("\n" + "="*70)
                    print("🎉 SUCCESS! All three sprites have distinct colors!")
                    print("="*70)
                    print(f"Best screenshot: {best_result[0].name}")
                    print(f"Color distance: {best_result[5]:.2f}")
                    cleanup_mgba()
                    return True
                else:
                    print(f"\n❌ Colors not distinct enough (distance: {best_distance:.2f})")
                    
                    # Analyze and suggest modifications
                    results_summary = {
                        "screenshot_count": len(screenshot_paths),
                        "color_distance": best_distance,
                        "all_different": False
                    }
                    analyze_and_suggest_modifications(iteration, results_summary, debug_output)
                
                # Periodic reporting
                current_time = time.time()
                if current_time - last_report_time >= report_interval:
                    elapsed_minutes = (current_time - start_time) / 60
                    print(f"\n📊 PERIODIC REPORT ({elapsed_minutes:.1f} min elapsed)")
                    print(f"   Iterations: {iteration}")
                    print(f"   Best distance: {best_distance:.2f}")
                    last_report_time = current_time
                
                time.sleep(2)
                
            except Exception as e:
                print(f"\n❌ ITERATION {iteration} CRASHED: {e}")
                import traceback
                traceback.print_exc()
                cleanup_mgba()
                time.sleep(5)
                continue
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        cleanup_mgba()
        return False
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        cleanup_mgba()
        return False

if __name__ == "__main__":
    main()

