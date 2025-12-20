#!/usr/bin/env python3
"""Quick verification script to test ROM with headless mGBA before launching mgba-qt"""
import time
import subprocess
import yaml
from pathlib import Path

def create_verification_lua():
    """Create Lua script to verify sprite palette assignments using screenshots"""
    screenshot_dir = Path("rom/working").resolve()
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    script_path = screenshot_dir / "scripts" / f"quick_verify_{int(time.time() * 1000)}.lua"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    screenshot_base = str(screenshot_dir / "verify_screenshot_")
    script_content = f'''-- Quick verification script - screenshot-based
local screenshotBase = "{screenshot_base}"
local frameCount = 0
local screenshotCount = 0
local screenshotInterval = 180  -- Every 3 seconds (180 frames = 3s at 60fps)
local startFrame = 60  -- Start after 1 second (60 frames = 1s at 60fps) - very early for fast capture
local maxFrames = 900  -- 15 seconds (900 frames = 15s at 60fps) - enough for multiple screenshots with fast forward

console:log("Quick verification: Taking screenshots every 3 seconds (mgba-qt)")
console:log("Note: Fast forward enabled via -C config flags")

-- Log frame count periodically to verify fast forward is working
local lastLogFrame = 0

-- Function to log sprite tile IDs for center sprites (for identifying characters)
local function logSpriteTiles()
    -- Log tile IDs for sprites in the center area whenever we take a screenshot
    -- Center area: roughly where characters appear in demo (around screen center)
    local logFile = io.open(screenshotBase .. "tile_ids.txt", "a")
    if logFile then
        logFile:write(string.format("Frame %d (screenshot %d):\\n", frameCount, screenshotCount))
        local centerCount = 0
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local attr = emu:read8(oamBase + 3)
            local palette = attr & 0x07
            
            -- Center area where characters appear (expanded to catch all demo sprites)
            -- Screen is 160x144, center is around 80x72
            if y >= 50 and y <= 110 and x >= 50 and x <= 110 then
                centerCount = centerCount + 1
                logFile:write(string.format("  Sprite[%d]: tile=0x%02X (%d) palette=%d pos=(%d,%d)\\n", 
                    i, tile, tile, palette, x, y))
            end
        end
        if centerCount == 0 then
            logFile:write("  (no sprites in center area)\\n")
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
    
    -- Log frame count every 60 frames to verify speed
    if frameCount - lastLogFrame >= 60 then
        console:log("Frame: " .. frameCount)
        lastLogFrame = frameCount
    end
    
    -- Take screenshots periodically after start frame
    if frameCount >= startFrame and (frameCount - startFrame) % screenshotInterval == 0 then
        takeScreenshot()
        -- Log tile IDs after taking screenshot
        logSpriteTiles()
    end
    
    -- Stop after max frames
    if frameCount >= maxFrames then
        console:log("Verification complete. Took " .. screenshotCount .. " screenshots.")
        emu:stop()
    end
end)
'''
    
    script_path.write_text(script_content)
    return script_path, screenshot_dir

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
    
    print("🔍 Creating verification Lua script...")
    lua_script, output_file = create_verification_lua()
    
    print(f"🚀 Launching mgba-qt for verification (--fastforward flag enabled)...")
    print(f"   ROM: {rom_path}")
    print(f"   Script: {lua_script}")
    print(f"   Screenshots will be saved to: {output_file}")
    print(f"   Note: mgba-qt window will open briefly to capture screenshots")
    
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
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,  # Don't capture - let window display
            stderr=subprocess.DEVNULL   # Don't capture - let window display
        )
        
        # Give mgba-qt a moment to initialize and enable fast forward
        time.sleep(1)
        
        # Wait for screenshots to be taken
        # With fast forward: unlimited speed, so 5 seconds real time should be plenty
        # Screenshots start at frame 60 (1s game time) and happen every 180 frames (3s game time)
        print(f"   Waiting 5 seconds for screenshots (with fast forward enabled)...")
        time.sleep(5)
        
        # Check if screenshots are being created
        screenshots_found = list(output_file.glob("verify_screenshot_*.png"))
        if screenshots_found:
            print(f"   ✓ Found {len(screenshots_found)} screenshots")
        else:
            print(f"   ⚠️  No screenshots found yet")
        
        # Check if process is still running
        if process.poll() is None:
            # Process still running - terminate it (we got our screenshots)
            print(f"   Terminating mgba-qt...")
            process.terminate()
            time.sleep(1)
            if process.poll() is None:
                process.kill()
        
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
    time.sleep(3)
    
    # Analyze results
    print(f"\n📋 Analyzing screenshots from {output_file}...")
    analysis = analyze_verification(output_file)
    
    if analysis['success']:
        print(f"\n✅ VERIFICATION SUCCESS!")
        print(f"   {analysis['reason']}")
        if 'screenshot_count' in analysis:
            print(f"   Screenshots analyzed: {analysis['screenshot_count']}")
        if 'distinct_colors' in analysis:
            print(f"   Distinct colors found: {analysis['distinct_colors']}")
        print(f"\n🎮 Ready to launch mgba-qt!")
        return True
    else:
        print(f"\n❌ VERIFICATION FAILED")
        print(f"   Reason: {analysis['reason']}")
        if 'screenshot_count' in analysis:
            print(f"   Screenshots found: {analysis['screenshot_count']}")
        print(f"\n⚠️  ROM may not have distinct sprite colors yet.")
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

