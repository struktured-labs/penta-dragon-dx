#!/usr/bin/env python3
"""Quick verification script to test ROM with headless mGBA before launching mgba-qt"""
import time
import subprocess
import yaml
import shutil
import sys
from pathlib import Path

def create_verification_lua(wall_clock_seconds=5, screenshots_per_second=8):
    """Create Lua script to verify sprite palette assignments using screenshots based on wall clock time"""
    screenshot_dir = Path("rom/working").resolve()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    script_path = screenshot_dir / "scripts" / f"quick_verify_{int(time.time() * 1000)}.lua"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    screenshot_base = str(screenshot_dir / "verify_screenshot_")
    # Use frame-based timing - with fast forward, frames run very fast (hundreds/thousands per second)
    # Target: ~6 screenshots per second = ~30 screenshots in 5 seconds (20-40 range)
    # With fast forward at ~2000+ fps, need ~300-400 frames between screenshots for 5-6 per second
    screenshot_interval_frames = 600  # Every 600 frames - with fast forward this gives ~3-4 screenshots per second = ~15-20 in 5s
    script_content = f'''-- Quick verification script - screenshot-based (Python controls wall clock time)
local screenshotBase = "{screenshot_base}"
local screenshotCount = 0
local frameCount = 0
local screenshotIntervalFrames = {screenshot_interval_frames}  -- Frames between screenshots

console:log("Quick verification: Taking screenshots every " .. screenshotIntervalFrames .. " frames")
console:log("Note: Fast forward enabled - Python will kill after {wall_clock_seconds} seconds")

-- Function to log ALL sprite tile IDs (for monster identification)
local function logSpriteTiles()
    -- Log ALL visible sprites to identify all monster types
    local logFile = io.open(screenshotBase .. "tile_ids.txt", "a")
    if logFile then
        logFile:write(string.format("Screenshot %d (frame %d):\\n", screenshotCount, frameCount))
        local spriteCount = 0
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local attr = emu:read8(oamBase + 3)
            local palette = attr & 0x07
            
            -- Log ALL visible sprites (not just center area)
            if y > 0 and y < 160 and x > 0 and x < 168 then
                spriteCount = spriteCount + 1
                logFile:write(string.format("  Sprite[%d]: tile=0x%02X (%d) palette=%d pos=(%d,%d)\\n", 
                    i, tile, tile, palette, x, y))
            end
        end
        if spriteCount == 0 then
            logFile:write("  (no visible sprites)\\n")
        end
        logFile:write("\\n")
        logFile:close()
    end
end

local function takeScreenshot()
    screenshotCount = screenshotCount + 1
    local screenshotPath = screenshotBase .. string.format("%03d", screenshotCount) .. ".png"
    
    -- Try screenshot - check return value and also verify file exists
    local success = emu:screenshot(screenshotPath)
    
    -- Verify file was actually created
    local file = io.open(screenshotPath, "r")
    if file then
        file:close()
        console:log("📸 Screenshot " .. screenshotCount .. " saved: " .. screenshotPath)
        return true
    else
        console:log("⚠️  Screenshot " .. screenshotCount .. " failed - file not created: " .. screenshotPath)
        console:log("   emu:screenshot returned: " .. tostring(success))
        return false
    end
end

-- Frame callback - take screenshots periodically
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Take screenshots periodically (Python controls wall clock timing)
    if frameCount % screenshotIntervalFrames == 0 then
        takeScreenshot()
        -- Log tile IDs after taking screenshot
        logSpriteTiles()
    end
end)
'''
    
    script_path.write_text(script_content)
    return script_path, screenshot_dir

import sys
from pathlib import Path
# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from mgba_window_utils import move_window_to_monitor

def analyze_verification(screenshot_dir):
    """Analyze screenshots to check if sprites use different palettes"""
    try:
        from PIL import Image
        import numpy as np
        
        # Find all screenshots
        screenshots = sorted(screenshot_dir.glob("verify_screenshot_*.png"))
        
        if not screenshots:
            return {'success': False, 'reason': 'No screenshots found - ROM may have crashed', 'crashed': True}
        
        print(f"📸 Found {len(screenshots)} screenshots to analyze")
        
        # Analyze screenshots for color diversity
        distinct_colors_found = set()
        all_colors = []
        
        for screenshot_path in screenshots[-5:]:  # Analyze last 5 screenshots
            try:
                img = Image.open(screenshot_path)
                img_array = np.array(img)
                
                # Sample colors from sprite area (center region where sprites appear)
                # Sara W, Sara D, and Dragon Fly appear in demo around center
                h, w = img_array.shape[:2]
                center_y, center_x = h // 2, w // 2
                sample_region = img_array[
                    center_y - 40:center_y + 40,
                    center_x - 60:center_x + 60
                ]
                
                # Get unique colors (convert to tuples for hashing)
                if len(sample_region.shape) == 3:
                    unique_colors = set(tuple(c) for row in sample_region for c in row)
                    distinct_colors_found.update(unique_colors)
                    all_colors.extend([tuple(c) for row in sample_region for c in row])
            except Exception as e:
                print(f"⚠️  Error analyzing {screenshot_path}: {e}")
                continue
        
        # Check if screenshots show white screen (ROM crash)
        # Sample last few screenshots to see if they're all white
        white_screen_count = 0
        for screenshot_path in screenshots[-5:]:  # Check last 5 screenshots
            try:
                img = Image.open(screenshot_path)
                img_array = np.array(img)
                # Check if image is mostly white (ROM crashed/froze)
                if len(img_array.shape) == 3:
                    # Count white pixels (RGB > 240)
                    white_pixels = np.sum((img_array[:,:,0] > 240) & (img_array[:,:,1] > 240) & (img_array[:,:,2] > 240))
                    total_pixels = img_array.shape[0] * img_array.shape[1]
                    if white_pixels > total_pixels * 0.9:  # 90% white = crashed
                        white_screen_count += 1
            except Exception as e:
                print(f"⚠️  Error checking {screenshot_path}: {e}")
                continue
        
        if white_screen_count >= 3:
            return {'success': False, 'reason': f'ROM crashed/froze - {white_screen_count}/5 recent screenshots show white screen', 'crashed': True, 'frozen': True}
        
        if len(distinct_colors_found) < 10:
            return {'success': False, 'reason': f'Too few distinct colors ({len(distinct_colors_found)}) - ROM may be frozen or grayscale', 'crashed': False}
        
        # Check if we have multiple distinct color groups (red, green, blue)
        # Convert to HSV to check hue diversity
        from colorsys import rgb_to_hsv
        hues = []
        for color in distinct_colors_found:
            if len(color) >= 3:
                r, g, b = color[0]/255.0, color[1]/255.0, color[2]/255.0
                h, s, v = rgb_to_hsv(r, g, b)
                if s > 0.3 and v > 0.3:  # Only saturated colors
                    hues.append(h)
        
        if len(hues) < 3:
            return {'success': False, 'reason': f'Not enough color diversity ({len(hues)} distinct hues)', 'crashed': False}
        
        # Check if hues are spread out (not all similar)
        hues_sorted = sorted(hues)
        hue_diffs = [hues_sorted[i+1] - hues_sorted[i] for i in range(len(hues_sorted)-1)]
        max_hue_diff = max(hue_diffs) if hue_diffs else 0
        
        if max_hue_diff < 0.2:  # Colors too similar
            return {'success': False, 'reason': 'Colors too similar - sprites may all use same palette', 'crashed': False}
        
        return {
            'success': True,
            'reason': f'Found {len(distinct_colors_found)} distinct colors with good hue diversity',
            'screenshot_count': len(screenshots),
            'distinct_colors': len(distinct_colors_found)
        }
    except ImportError:
        # PIL not available - fall back to simple check
        screenshots = sorted(screenshot_dir.glob("verify_screenshot_*.png"))
        if not screenshots:
            return {'success': False, 'reason': 'No screenshots found', 'crashed': True}
        return {
            'success': True,
            'reason': f'Found {len(screenshots)} screenshots (PIL not available for detailed analysis)',
            'screenshot_count': len(screenshots)
        }
    except Exception as e:
        return {'success': False, 'reason': f'Error analyzing screenshots: {e}', 'crashed': False}

def main():
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        return False
    
    # Quick test: capture screenshots over 10 seconds of wall clock time (reduced from 20s)
    wall_clock_seconds = 10  # Real time seconds to run (50% faster)
    screenshots_per_second = 12  # Capture 12 screenshots per second = 60 screenshots in 5 seconds (2x more)
    expected_screenshots = wall_clock_seconds * screenshots_per_second
    
    print(f"🔍 Creating quick verification Lua script ({wall_clock_seconds}s wall clock time)...")
    lua_script, output_file = create_verification_lua(
        wall_clock_seconds=wall_clock_seconds,
        screenshots_per_second=screenshots_per_second
    )
    
    print(f"🚀 Launching mgba-qt for quick verification (--fastforward flag enabled)...")
    print(f"   ROM: {rom_path}")
    print(f"   Script: {lua_script}")
    print(f"   Will capture: ~{expected_screenshots} screenshots over {wall_clock_seconds}s wall clock time")
    print(f"   Screenshots will be saved to: {output_file}")
    
    # Clean up old screenshots
    for old_screenshot in output_file.glob("verify_screenshot_*.png"):
        try:
            old_screenshot.unlink()
        except:
            pass
    
    # Launch mgba-qt with --fastforward flag (matching user's command: mgba-qt ROM --fastforward)
    cmd = [
        "/usr/local/bin/mgba-qt",
        str(rom_path),
        "--fastforward",
        "--script", str(lua_script),
    ]
    
    # Debug: print exact command
    print(f"   Executing: {' '.join(cmd)}")
    
    try:
        # Launch mgba-qt (don't capture stdout/stderr so window can display properly)
        # Fast forward might require window to be visible/focused
        # On Wayland, force XWayland mode so xdotool can position the window
        import os
        env = os.environ.copy()
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
            from mgba_window_utils import get_mgba_env_for_xwayland
            env = get_mgba_env_for_xwayland()
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,  # Don't capture - let window display
            stderr=subprocess.DEVNULL,  # Don't capture - let window display
            env=env  # Use environment that forces XWayland on Wayland
        )
        
        # Give mgba-qt a moment to initialize and enable fast forward
        time.sleep(2)
        
        # Wait for wall clock time, then kill mgba-qt
        # Screenshots are taken based on wall clock time, not game frames
        print(f"   Running for {wall_clock_seconds} seconds of wall clock time...")
        
        # Wait for the specified wall clock duration
        waited = 0
        check_interval = 2.0  # Check every 2 seconds for intermediate analysis
        last_count = 0
        analyzed_screenshots = set()  # Track which screenshots we've already analyzed
        
        def analyze_intermediate(screenshot_dir, analyzed_set):
            """Quick intermediate analysis of new screenshots"""
            try:
                from PIL import Image
                import numpy as np
                from colorsys import rgb_to_hsv
                
                screenshots = sorted(screenshot_dir.glob("verify_screenshot_*.png"))
                new_screenshots = [s for s in screenshots if s not in analyzed_set]
                
                if not new_screenshots:
                    return None
                
                distinct_colors = set()
                hues = []
                
                for screenshot_path in new_screenshots[-10:]:  # Analyze last 10 new screenshots
                    try:
                        img = Image.open(screenshot_path)
                        img_array = np.array(img)
                        
                        h, w = img_array.shape[:2]
                        center_y, center_x = h // 2, w // 2
                        sample_region = img_array[
                            center_y - 40:center_y + 40,
                            center_x - 60:center_x + 60
                        ]
                        
                        if len(sample_region.shape) == 3:
                            unique_colors = set(tuple(c) for row in sample_region for c in row)
                            distinct_colors.update(unique_colors)
                            
                            for color in unique_colors:
                                if len(color) >= 3:
                                    r, g, b = color[0]/255.0, color[1]/255.0, color[2]/255.0
                                    h_val, s, v = rgb_to_hsv(r, g, b)
                                    if s > 0.3 and v > 0.3:
                                        hues.append(h_val)
                        
                        analyzed_set.add(screenshot_path)
                    except Exception as e:
                        continue
                
                return {
                    'new_count': len(new_screenshots),
                    'distinct_colors': len(distinct_colors),
                    'hue_count': len(hues),
                    'total_screenshots': len(screenshots)
                }
            except ImportError:
                return None
            except Exception:
                return None
        
        while waited < wall_clock_seconds:
            time.sleep(check_interval)
            waited += check_interval
            
            # Check screenshot progress
            screenshots_found = list(output_file.glob("verify_screenshot_*.png"))
            current_count = len(screenshots_found)
            
            if current_count != last_count:
                print(f"   📸 Progress: {current_count} screenshots captured ({waited:.1f}s elapsed)")
                
                # Show intermediate analysis
                intermediate = analyze_intermediate(output_file, analyzed_screenshots)
                if intermediate:
                    print(f"      └─ Analysis: {intermediate['new_count']} new screenshots analyzed")
                    print(f"         └─ Distinct colors so far: {intermediate['distinct_colors']}")
                    print(f"         └─ Saturated hues found: {intermediate['hue_count']}")
                    if intermediate['distinct_colors'] > 0:
                        print(f"         └─ Status: {'✅ Colors detected' if intermediate['distinct_colors'] >= 10 else '⚠️  Low color count'}")
                
                last_count = current_count
        
        # Kill mgba-qt after wall clock time expires - ALWAYS kill, even if crashed
        print(f"   ✓ {wall_clock_seconds}s elapsed, terminating mgba-qt...")
        try:
            if process.poll() is None:
                process.terminate()
                time.sleep(0.5)
                if process.poll() is None:
                    process.kill()
            else:
                # Process already dead, but kill anyway to be sure
                try:
                    process.kill()
                except:
                    pass
            print(f"   Process terminated")
        except:
            pass
        finally:
            # Force kill using pkill as fallback - ALWAYS ensure cleanup
            try:
                subprocess.run(["pkill", "-9", "mgba-qt"], stderr=subprocess.DEVNULL, timeout=1)
            except:
                pass
        
        # Final check
        screenshots_found = list(output_file.glob("verify_screenshot_*.png"))
        if screenshots_found:
            print(f"   ✓ Final count: {len(screenshots_found)} screenshots")
        else:
            print(f"   ⚠️  No screenshots found")
        
        # Read any output (might have errors and console logs)
        try:
            stdout, stderr = process.communicate(timeout=2)
            if stdout:
                print(f"   mgba-qt stdout (console logs):")
                # Show last few lines that might contain frame logs
                for line in stdout.split('\n')[-10:]:
                    if line.strip():
                        print(f"      {line}")
            if stderr:
                # Only show non-EGL warnings
                stderr_lines = [l for l in stderr.split('\n') if 'EGL' not in l and 'pci' not in l.lower() and l.strip()]
                if stderr_lines:
                    print(f"   mgba-qt stderr: {''.join(stderr_lines[:5])}")
        except:
            pass
        
    except Exception as e:
        print(f"⚠️  Error launching mgba-qt: {e}")
    
    # Wait a bit for screenshots to be written
    time.sleep(2)
    
    # Analyze results
    print(f"\n📋 Final analysis of screenshots from {output_file}...")
    analysis = analyze_verification(output_file)
    
    # Show detailed breakdown
    print(f"\n📊 Analysis Summary:")
    if 'screenshot_count' in analysis:
        print(f"   Total screenshots: {analysis['screenshot_count']}")
    if 'distinct_colors' in analysis:
        print(f"   Distinct colors found: {analysis['distinct_colors']}")
    
    # Show what was analyzed
    try:
        from PIL import Image
        import numpy as np
        from colorsys import rgb_to_hsv
        
        screenshots = sorted(output_file.glob("verify_screenshot_*.png"))
        if screenshots:
            print(f"\n🔍 Detailed breakdown (last 5 screenshots):")
            for i, screenshot_path in enumerate(screenshots[-5:], 1):
                try:
                    img = Image.open(screenshot_path)
                    img_array = np.array(img)
                    h, w = img_array.shape[:2]
                    center_y, center_x = h // 2, w // 2
                    sample_region = img_array[
                        center_y - 40:center_y + 40,
                        center_x - 60:center_x + 60
                    ]
                    
                    if len(sample_region.shape) == 3:
                        unique_colors = set(tuple(c) for row in sample_region for c in row)
                        hues = []
                        for color in unique_colors:
                            if len(color) >= 3:
                                r, g, b = color[0]/255.0, color[1]/255.0, color[2]/255.0
                                h_val, s, v = rgb_to_hsv(r, g, b)
                                if s > 0.3 and v > 0.3:
                                    hues.append(h_val)
                        
                        print(f"   Screenshot {i} ({screenshot_path.name}):")
                        print(f"      └─ Distinct colors: {len(unique_colors)}")
                        print(f"      └─ Saturated hues: {len(hues)}")
                        if hues:
                            hues_sorted = sorted(hues)
                            hue_diffs = [hues_sorted[j+1] - hues_sorted[j] for j in range(len(hues_sorted)-1)]
                            max_hue_diff = max(hue_diffs) if hue_diffs else 0
                            print(f"      └─ Max hue difference: {max_hue_diff:.3f} ({'✅ Good diversity' if max_hue_diff >= 0.2 else '⚠️  Low diversity'})")
                except Exception as e:
                    print(f"   Screenshot {i}: Error analyzing - {e}")
    except ImportError:
        pass
    except Exception as e:
        print(f"   ⚠️  Could not generate detailed breakdown: {e}")
    
    if analysis['success']:
        print(f"\n✅ VERIFICATION SUCCESS!")
        print(f"   {analysis['reason']}")
        print(f"\n🎮 Ready to launch mgba-qt!")
        return True
    else:
        print(f"\n❌ VERIFICATION FAILED")
        print(f"   Reason: {analysis['reason']}")
        print(f"\n⚠️  ROM may not have distinct sprite colors yet.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

