#!/usr/bin/env python3
"""
Automated palette testing loop for Sara W, Sara D, and Dragon Fly.
1. Tries different palette configurations
2. Builds ROM
3. Captures quick screenshots (5 seconds)
4. Extracts sample sprites
5. Analyzes colors from sprites
6. Repeats until distinct colors are found
"""
import subprocess
import time
import sys
import signal
import atexit
from pathlib import Path
from collections import defaultdict

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pillow", "numpy"], check=True)
    from PIL import Image
    import numpy as np

try:
    import yaml
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "--break-system-packages", "pyyaml"], check=True)
    import yaml

def cleanup_mgba():
    """Kill any running mGBA instances"""
    subprocess.run(["pkill", "-9", "-f", "mgba"], timeout=5, capture_output=True)
    time.sleep(1)

def load_current_palettes():
    """Load current palette configuration from YAML"""
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
    
    # Color sets to try - distinct colors for Sara D, Sara W, and Dragon Fly
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
         'dragon_fly': ['transparent', '7FE0', '4A00', '2100']},  # Yellow/Orange gradient
        {'sara_d': ['transparent', '5000', '5000', '5000'],  # Dark Blue
         'sara_w': ['transparent', '7D00', '7D00', '7D00'],  # Light Blue
         'dragon_fly': ['transparent', '7FE0', '7FE0', '7FE0']},  # Yellow
        {'sara_d': ['transparent', '7C00', '7C00', '7C00'],  # Blue
         'sara_w': ['transparent', '001F', '001F', '001F'],  # Red
         'dragon_fly': ['transparent', '03E0', '03E0', '03E0']},  # Green
        {'sara_d': ['transparent', '7FE0', '7FE0', '7FE0'],  # Yellow
         'sara_w': ['transparent', '7C1F', '7C1F', '7C1F'],  # Magenta
         'dragon_fly': ['transparent', '03FF', '03FF', '03FF']},  # Cyan
        {'sara_d': ['transparent', '001F', '7C00', '03E0'],  # Red/Blue/Green mix
         'sara_w': ['transparent', '7FE0', '7C1F', '03FF'],  # Yellow/Magenta/Cyan mix
         'dragon_fly': ['transparent', '7FFF', '7C00', '001F']},  # White/Blue/Red mix
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

def create_quick_verify_lua():
    """Create Lua script for quick screenshot capture (5 seconds)"""
    screenshot_dir = Path("rom/working").resolve()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    script_path = screenshot_dir / "scripts" / f"quick_verify_{int(time.time() * 1000)}.lua"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    screenshot_base = str(screenshot_dir / "verify_screenshot_")
    script_content = f'''-- Quick verification script - 5 second capture
local screenshotBase = "{screenshot_base}"
local frameCount = 0
local screenshotCount = 0
local screenshotInterval = 30  -- Every 0.5 seconds (30 frames)
local startFrame = 60  -- Start after 1 second
local maxFrames = 360  -- 5 seconds total (360 frames = 6s at 60fps, but stops at 5s)

console:log("Quick verification: Capturing screenshots for 5 seconds")

-- Function to log sprite tile IDs and positions (APPEND mode to capture all frames)
local function logSpriteTiles()
    local logFile = io.open(screenshotBase .. "tile_ids.txt", "a")  -- Changed to "a" for append
    if logFile then
        logFile:write(string.format("Frame %d (screenshot %d):\\n", frameCount, screenshotCount))
        local spriteCount = 0
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local attr = emu:read8(oamBase + 3)
            local palette = attr & 0x07
            
            if y > 0 and y < 160 and x > 0 and x < 168 then
                spriteCount = spriteCount + 1
                logFile:write(string.format("  Sprite[%d]: tile=0x%02X (%d) palette=%d pos=(%d,%d)\\n", 
                    i, tile, tile, palette, x, y))
            end
        end
        if spriteCount == 0 then
            logFile:write("  No visible sprites\\n")
        end
        logFile:write("\\n")
        logFile:close()
    end
end

local function takeScreenshot()
    screenshotCount = screenshotCount + 1
    local screenshotPath = screenshotBase .. string.format("%03d", screenshotCount) .. ".png"
    local success = emu:screenshot(screenshotPath)
    local file = io.open(screenshotPath, "r")
    if file then
        file:close()
        console:log("📸 Screenshot " .. screenshotCount .. " saved")
        return true
    else
        console:log("⚠️  Screenshot " .. screenshotCount .. " failed")
        return false
    end
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    if frameCount >= startFrame and (frameCount - startFrame) % screenshotInterval == 0 then
        takeScreenshot()
        logSpriteTiles()
    end
    
    if frameCount >= maxFrames then
        console:log("Verification complete. Took " .. screenshotCount .. " screenshots.")
        emu:stop()
    end
end)
'''
    
    script_path.write_text(script_content)
    return script_path, screenshot_dir

def move_window_to_desktop(window_name="mgba-qt", desktop_num=3):
    """Move mgba-qt window to 3rd desktop/monitor using available tools"""
    import shutil
    
    # Wait for window to appear
    time.sleep(1.5)
    
    # Try wmctrl first (for desktop switching)
    wmctrl_path = shutil.which("wmctrl")
    if wmctrl_path:
        try:
            # Find window by name
            result = subprocess.run(
                ["wmctrl", "-l"],
                capture_output=True,
                text=True,
                timeout=2
            )
            for line in result.stdout.splitlines():
                if window_name.lower() in line.lower() or "mGBA" in line:
                    win_id = line.split()[0]
                    # Move to desktop 3 (0-indexed, so desktop 2)
                    subprocess.run(
                        ["wmctrl", "-i", "-r", win_id, "-t", str(desktop_num - 1)],
                        timeout=2
                    )
                    print(f"   ✓ Moved mgba-qt window to desktop {desktop_num}")
                    return True
        except Exception as e:
            pass
    
    # Try xdotool as fallback (for window positioning)
    xdotool_path = shutil.which("xdotool")
    if xdotool_path:
        try:
            # Find window by name
            result = subprocess.run(
                ["xdotool", "search", "--name", window_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            if not result.stdout.strip():
                # Try searching for "mGBA" or partial match
                result = subprocess.run(
                    ["xdotool", "search", "--class", "mgba-qt"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
            
            if result.stdout.strip():
                win_id = result.stdout.strip().split()[0]
                # Try to get monitor info and move to 3rd monitor
                # Common setup: 1920x1080 monitors side-by-side
                # Monitor 1: x=0, Monitor 2: x=1920, Monitor 3: x=3840
                subprocess.run(
                    ["xdotool", "windowmove", win_id, "3840", "0"],
                    timeout=2
                )
                print(f"   ✓ Moved mgba-qt window to 3rd monitor (x=3840)")
                return True
        except Exception as e:
            pass
    
    # Try using environment variable for DISPLAY if on X11
    # This is a fallback - user may need to manually move window
    print(f"   ⚠️  Could not automatically move window")
    print(f"   💡 Window should appear - please move it to your 3rd desktop/monitor manually")
    return False

def launch_mgba_with_lua(lua_script_path):
    """Launch mgba-qt with Lua script and move to 3rd desktop"""
    mgba_qt_path = Path("/usr/local/bin/mgba-qt")
    if not mgba_qt_path.exists():
        # Try to find it in PATH
        mgba_qt_path = subprocess.run(["which", "mgba-qt"], capture_output=True, text=True).stdout.strip()
        if not mgba_qt_path:
            print("❌ mgba-qt not found!")
            return None
        mgba_qt_path = Path(mgba_qt_path)
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb").resolve()
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return None
    
    # Launch mgba-qt with ROM first, then script (matching quick_verify_rom.py pattern)
    # Use --fastforward to speed up execution
    cmd = [
        str(mgba_qt_path),
        str(rom_path),
        "--fastforward",
        "--script", str(lua_script_path.resolve())
    ]
    
    print(f"   Command: {' '.join(cmd)}")
    
    # Don't capture stdout/stderr so window can display properly
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Give mgba-qt a moment to initialize, then move window
    time.sleep(0.5)
    move_window_to_desktop("mgba-qt", desktop_num=3)
    
    return proc

def extract_sprite_from_screenshot(img, center_x, center_y, sprite_size=32):
    """Extract sprite region from screenshot"""
    img_array = np.array(img)
    h, w = img_array.shape[:2]
    
    # Calculate bounds
    y1 = max(0, center_y - sprite_size // 2)
    y2 = min(h, center_y + sprite_size // 2)
    x1 = max(0, center_x - sprite_size // 2)
    x2 = min(w, center_x + sprite_size // 2)
    
    sprite_region = img_array[y1:y2, x1:x2]
    return Image.fromarray(sprite_region)

def parse_tile_log(log_path):
    """Parse tile log to find Sara D, Sara W, and Dragon Fly positions"""
    if not log_path.exists():
        return {}
    
    monsters = defaultdict(lambda: {'tiles': set(), 'positions': [], 'screenshots': set()})
    
    current_screenshot = None
    with open(log_path, 'r') as f:
        for line in f:
            if 'screenshot' in line.lower():
                # Extract screenshot number
                parts = line.split()
                for part in parts:
                    if 'screenshot' in part.lower():
                        try:
                            current_screenshot = int(part.split('_')[-1].split('.')[0])
                        except:
                            pass
            
            if 'Sprite[' in line and 'tile=' in line:
                try:
                    # Parse: Sprite[%d]: tile=0x%02X (%d) palette=%d pos=(%d,%d)
                    parts = line.split()
                    tile_part = [p for p in parts if 'tile=' in p][0]
                    palette_part = [p for p in parts if 'palette=' in p][0]
                    pos_part = [p for p in parts if 'pos=' in p][0]
                    
                    tile = int(tile_part.split('(')[1].split(')')[0])
                    palette = int(palette_part.split('=')[1])
                    pos_str = pos_part.split('(')[1].split(')')[0]
                    x, y = map(int, pos_str.split(','))
                    
                    # Identify monster type by palette and tile ID
                    # Sara D uses tiles 0-3 with palette 0
                    # Sara W uses tiles 4-7 with palette 1  
                    # Dragon Fly uses tiles 0-3 with palette 7 (or other tiles)
                    if palette == 0 and tile < 4:
                        monster_type = 'sara_d'  # MainCharacter
                    elif palette == 1 and (tile >= 4 and tile < 8):
                        monster_type = 'sara_w'  # EnemyBasic
                    elif palette == 7:
                        monster_type = 'dragon_fly'  # MainBoss (can use various tiles)
                    elif palette == 0 and tile >= 8:
                        # Might be Dragon Fly using palette 0, check tile range
                        monster_type = 'dragon_fly'  # Dragon Fly sometimes uses palette 0
                    else:
                        continue  # Skip other palettes/tile combinations
                    
                    monsters[monster_type]['tiles'].add(tile)
                    monsters[monster_type]['positions'].append((x, y, current_screenshot))
                    if current_screenshot:
                        monsters[monster_type]['screenshots'].add(current_screenshot)
                except Exception as e:
                    continue
    
    return monsters

def extract_sample_sprites(screenshot_dir, monsters, samples_per_type=5):
    """Extract sample sprites for color analysis"""
    screenshots = sorted(screenshot_dir.glob("verify_screenshot_*.png"))
    sprite_dir = screenshot_dir / "extracted_sprites"
    sprite_dir.mkdir(exist_ok=True)
    
    extracted_sprites = defaultdict(list)
    
    for monster_type in ['sara_d', 'sara_w', 'dragon_fly']:
        if monster_type not in monsters:
            continue
        
        # Get sample positions from different screenshots
        seen_screenshots = set()
        samples = []
        for x, y, screenshot_num in monsters[monster_type]['positions']:
            if screenshot_num not in seen_screenshots:
                samples.append((screenshot_num, x, y))
                seen_screenshots.add(screenshot_num)
                if len(samples) >= samples_per_type:
                    break
        
        for screenshot_num, x, y in samples:
            try:
                screenshot_path = screenshot_dir / f"verify_screenshot_{screenshot_num:03d}.png"
                if not screenshot_path.exists():
                    continue
                
                img = Image.open(screenshot_path)
                sprite_img = extract_sprite_from_screenshot(img, x, y)
                extracted_sprites[monster_type].append(sprite_img)
            except Exception as e:
                continue
    
    return extracted_sprites

def analyze_sprite_colors(extracted_sprites):
    """Analyze colors from extracted sprites"""
    if not extracted_sprites or len(extracted_sprites) < 3:
        return None, False, 0
    
    def get_dominant_colors(sprite_images, k=3):
        """Get dominant colors from sprite images"""
        all_colors = []
        for sprite_img in sprite_images:
            img_array = np.array(sprite_img)
            if img_array.size == 0:
                continue
            pixels = img_array.reshape(-1, img_array.shape[-1])
            if pixels.shape[1] == 4:
                pixels = pixels[:, :3]
            # Filter out black/transparent
            non_black = pixels[np.sum(pixels, axis=1) > 30]
            if len(non_black) > 0:
                all_colors.extend([tuple(p) for p in non_black])
        
        if not all_colors:
            return []
        
        from collections import Counter
        most_common = Counter(all_colors).most_common(k)
        return [np.array(c[0]) for c in most_common]
    
    sara_d_colors = get_dominant_colors(extracted_sprites.get('sara_d', []))
    sara_w_colors = get_dominant_colors(extracted_sprites.get('sara_w', []))
    dragon_fly_colors = get_dominant_colors(extracted_sprites.get('dragon_fly', []))
    
    if len(sara_d_colors) == 0 or len(sara_w_colors) == 0 or len(dragon_fly_colors) == 0:
        return None, False, 0
    
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
        return None, False, 0
    
    min_distance = min(distances)
    all_different = min_distance > 50  # Threshold for distinct colors
    
    return {
        'sara_d': sara_d_colors[0] if sara_d_colors else None,
        'sara_w': sara_w_colors[0] if sara_w_colors else None,
        'dragon_fly': dragon_fly_colors[0] if dragon_fly_colors else None,
        'min_distance': min_distance,
        'all_different': all_different
    }, all_different, min_distance

def main():
    """Main verification loop"""
    atexit.register(cleanup_mgba)
    signal.signal(signal.SIGINT, lambda s, f: (cleanup_mgba(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda s, f: (cleanup_mgba(), sys.exit(0)))
    
    print("=" * 70)
    print("AUTOMATED PALETTE TESTING LOOP")
    print("=" * 70)
    print("Testing palettes for Sara D, Sara W, and Dragon Fly")
    print("Using screenshots + sprite extraction + color analysis")
    print("=" * 70)
    print()
    
    cleanup_mgba()
    
    screenshot_dir = Path("rom/working").resolve()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    iteration = 0
    
    try:
        while True:
            iteration += 1
            print(f"\n{'='*70}")
            print(f"🔄 ITERATION {iteration}")
            print(f"{'='*70}")
            
            # 1. Generate palette configuration
            print(f"\n🎨 Generating palette configuration...")
            palettes = generate_next_palette_config(iteration)
            if palettes:
                save_palettes(palettes)
                config_num = ((iteration - 1) % 8) + 1
                print(f"✅ Saved palette config (Set {config_num} of 8)")
                print(f"   Sara D: {palettes['obj_palettes']['MainCharacter']['colors']}")
                print(f"   Sara W: {palettes['obj_palettes']['EnemyBasic']['colors']}")
                print(f"   Dragon Fly: {palettes['obj_palettes']['MainBoss']['colors']}")
            
            # 2. Build ROM
            print(f"\n🔨 Building ROM...")
            if not build_rom():
                print("❌ Build failed, skipping iteration")
                continue
            
            # 3. Clean up old screenshots and tile log
            print(f"\n🧹 Cleaning up old screenshots...")
            for old_file in screenshot_dir.glob("verify_screenshot_*.png"):
                old_file.unlink()
            # Clear tile log (will be appended to by Lua script)
            tile_log = screenshot_dir / "verify_screenshot_tile_ids.txt"
            if tile_log.exists():
                tile_log.unlink()
            for sprite_dir in screenshot_dir.glob("extracted_sprites"):
                import shutil
                shutil.rmtree(sprite_dir, ignore_errors=True)
            
            # 4. Create Lua script
            print(f"\n📝 Creating quick verification Lua script...")
            lua_script_path, _ = create_quick_verify_lua()
            
            # 5. Launch mGBA
            print(f"\n🚀 Launching mgba-qt (5 second capture - window will appear)...")
            mgba_proc = launch_mgba_with_lua(lua_script_path)
            if not mgba_proc:
                print("❌ Failed to launch mGBA")
                continue
            
            # 6. Wait for completion - give time for window to appear and capture
            print("⏳ Waiting for screenshot capture (window should appear for ~5 seconds)...")
            mgba_start_time = time.time()
            # Wait up to 8 seconds for the Lua script to complete (5s capture + buffer)
            while time.time() - mgba_start_time < 8:
                if mgba_proc.poll() is not None:
                    break
                time.sleep(0.5)
            
            # Give a moment for final screenshots to be written
            time.sleep(1)
            
            # Kill mGBA if still running
            print("🛑 Stopping mGBA...")
            try:
                if mgba_proc.poll() is None:
                    mgba_proc.terminate()  # Try graceful termination first
                    time.sleep(0.5)
                    if mgba_proc.poll() is None:
                        mgba_proc.kill()  # Force kill if needed
            except:
                pass
            cleanup_mgba()
            time.sleep(1)
            
            # 7. Parse tile log and extract sprites
            print(f"\n🔍 Analyzing screenshots and extracting sprites...")
            tile_log = screenshot_dir / "verify_screenshot_tile_ids.txt"
            monsters = parse_tile_log(tile_log)
            
            if not monsters:
                print("❌ No sprites found in tile log")
                continue
            
            print(f"   Found sprites:")
            for monster_type, data in monsters.items():
                print(f"     {monster_type}: {len(data['positions'])} positions")
            
            # 8. Extract sample sprites
            extracted_sprites = extract_sample_sprites(screenshot_dir, monsters, samples_per_type=5)
            
            print(f"   Extracted sprites:")
            for monster_type, sprites in extracted_sprites.items():
                print(f"     {monster_type}: {len(sprites)} sprites")
            
            # 9. Analyze colors
            print(f"\n🎨 Analyzing colors from extracted sprites...")
            color_result, all_different, min_distance = analyze_sprite_colors(extracted_sprites)
            
            if color_result:
                print(f"   Color distance: {min_distance:.2f}")
                print(f"   All distinct: {all_different}")
                
                if all_different:
                    print("\n" + "="*70)
                    print("🎉 SUCCESS! All three sprites have distinct colors!")
                    print("="*70)
                    print(f"   Sara D color: {color_result['sara_d']}")
                    print(f"   Sara W color: {color_result['sara_w']}")
                    print(f"   Dragon Fly color: {color_result['dragon_fly']}")
                    print(f"   Minimum distance: {min_distance:.2f}")
                    print(f"\n✅ Palette configuration is working!")
                    print(f"📋 Check extracted sprites in: {screenshot_dir / 'extracted_sprites'}")
                    cleanup_mgba()
                    return True
                else:
                    print(f"\n❌ Colors not distinct enough (distance: {min_distance:.2f})")
                    print(f"🔄 Trying next palette configuration...")
            else:
                print(f"\n❌ Could not analyze colors (insufficient sprite data)")
                print(f"🔄 Trying next palette configuration...")
            
            time.sleep(2)
            
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

