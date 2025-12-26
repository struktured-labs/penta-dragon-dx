#!/usr/bin/env python3
"""Detailed color verification - checks palette RAM, OAM, and screenshots"""
import subprocess
import time
from pathlib import Path

def create_detailed_lua():
    """Create Lua script to verify palette RAM, OAM, and capture screenshots"""
    script_path = Path("rom/working/detailed_verify.lua")
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    script_content = '''-- Detailed color verification script
local frameCount = 0
local screenshotCount = 0
local logFile = io.open("rom/working/detailed_verify.txt", "w")

-- Function to read OBJ palette from palette RAM
local function readOBJPalette(palIndex)
    local colors = {}
    for colorIdx = 0, 3 do
        emu:write8(0xFF6A, 0x80 + (palIndex * 8) + (colorIdx * 2))
        local lo = emu:read8(0xFF6B)
        emu:write8(0xFF6A, 0x80 + (palIndex * 8) + (colorIdx * 2) + 1)
        local hi = emu:read8(0xFF6B)
        local color = lo + (hi * 256)
        table.insert(colors, string.format("%04X", color))
    end
    return colors
end

-- Function to log OAM sprite data
local function logOAM()
    logFile:write(string.format("\\n=== Frame %d ===\\n", frameCount))
    
    -- Read OBJ palettes
    logFile:write("OBJ Palettes:\\n")
    for pal = 0, 7 do
        local colors = readOBJPalette(pal)
        logFile:write(string.format("  Palette %d: %s\\n", pal, table.concat(colors, " ")))
    end
    
    -- Read OAM sprites
    logFile:write("\\nVisible Sprites:\\n")
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
            logFile:write(string.format("  Sprite[%d]: tile=%d palette=%d pos=(%d,%d)\\n", 
                i, tile, palette, x, y))
        end
    end
    logFile:write(string.format("Total visible sprites: %d\\n", spriteCount))
    logFile:flush()
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Log every 300 frames (~5 seconds at 60fps)
    if frameCount % 300 == 0 then
        logOAM()
    end
    
    -- Take screenshots every 600 frames (~10 seconds)
    if frameCount % 600 == 0 and frameCount >= 600 then
        screenshotCount = screenshotCount + 1
        local path = string.format("rom/working/detailed_screenshot_%03d.png", screenshotCount)
        emu:screenshot(path)
        console:log("📸 Screenshot " .. screenshotCount .. ": " .. path)
    end
    
    -- Stop after 10 screenshots
    if screenshotCount >= 10 then
        logFile:close()
        console:log("✓ Verification complete")
        emu:stop()
    end
end)

console:log("Detailed verification script loaded")
'''
    
    script_path.write_text(script_content)
    return script_path

def analyze_results():
    """Analyze the verification results"""
    log_path = Path("rom/working/detailed_verify.txt")
    screenshot_dir = Path("rom/working")
    
    if not log_path.exists():
        print("❌ Verification log not found")
        return False
    
    # Read palette data
    print("\n📊 Palette RAM Analysis:")
    with open(log_path, 'r') as f:
        content = f.read()
        
        # Extract palette data
        import re
        palette_matches = re.findall(r'Palette (\d+): ([0-9A-F\s]+)', content)
        
        palettes = {}
        for pal_idx, colors_str in palette_matches:
            colors = colors_str.strip().split()
            palettes[int(pal_idx)] = colors
            print(f"  Palette {pal_idx}: {colors_str.strip()}")
        
        # Check if palettes are loaded (not all zeros/grayscale)
        pal0_loaded = palettes.get(0, [])
        pal1_loaded = palettes.get(1, [])
        pal7_loaded = palettes.get(7, [])
        
        print(f"\n✓ Palette 0 (Sara D): {pal0_loaded}")
        print(f"✓ Palette 1 (Sara W): {pal1_loaded}")
        print(f"✓ Palette 7 (Dragon Fly): {pal7_loaded}")
        
        # Check if palettes have distinct colors
        def palette_has_color(pal_colors):
            if not pal_colors:
                return False
            # Check if any color is not grayscale (R != G != B)
            for color_hex in pal_colors:
                if color_hex == "transparent" or color_hex == "0000":
                    continue
                color_val = int(color_hex, 16)
                r = (color_val >> 0) & 0x1F
                g = (color_val >> 5) & 0x1F
                b = (color_val >> 10) & 0x1F
                if r != g or g != b:
                    return True
            return False
        
        pal0_has_color = palette_has_color(pal0_loaded)
        pal1_has_color = palette_has_color(pal1_loaded)
        pal7_has_color = palette_has_color(pal7_loaded)
        
        print(f"\n🎨 Palette Color Check:")
        print(f"  Palette 0 has color: {pal0_has_color}")
        print(f"  Palette 1 has color: {pal1_has_color}")
        print(f"  Palette 7 has color: {pal7_has_color}")
        
        # Extract sprite palette assignments
        sprite_matches = re.findall(r'Sprite\[(\d+)\]: tile=(\d+) palette=(\d+)', content)
        
        tile_to_palette = {}
        for sprite_idx, tile, palette in sprite_matches:
            tile = int(tile)
            palette = int(palette)
            if tile not in tile_to_palette:
                tile_to_palette[tile] = []
            tile_to_palette[tile].append(palette)
        
        print(f"\n📋 Tile to Palette Mapping (from OAM):")
        for tile in sorted(tile_to_palette.keys())[:20]:  # Show first 20
            palettes_used = set(tile_to_palette[tile])
            print(f"  Tile {tile:3d}: palettes {sorted(palettes_used)}")
        
        # Check if tiles 8-15 are using different palettes
        tiles_8_15_palettes = set()
        for tile in range(8, 16):
            if tile in tile_to_palette:
                tiles_8_15_palettes.update(tile_to_palette[tile])
        
        print(f"\n🎯 Tiles 8-15 palette usage: {sorted(tiles_8_15_palettes)}")
        
        # Analyze screenshots
        screenshots = sorted(screenshot_dir.glob("detailed_screenshot_*.png"))
        if screenshots:
            print(f"\n📸 Analyzing {len(screenshots)} screenshots...")
            try:
                from PIL import Image
                import numpy as np
                from colorsys import rgb_to_hsv
                
                distinct_colors = set()
                hues = []
                
                for screenshot_path in screenshots[-5:]:  # Last 5 screenshots
                    img = Image.open(screenshot_path)
                    img_array = np.array(img)
                    h, w = img_array.shape[:2]
                    
                    # Sample sprite regions
                    center_y, center_x = h // 2, w // 2
                    sprite_region = img_array[
                        center_y - 50:center_y + 50,
                        center_x - 80:center_x + 80
                    ]
                    
                    if len(sprite_region.shape) == 3:
                        unique_colors = set(tuple(c[:3]) for row in sprite_region for c in row)
                        distinct_colors.update(unique_colors)
                        
                        for color in unique_colors:
                            if len(color) >= 3:
                                r, g, b = color[0]/255.0, color[1]/255.0, color[2]/255.0
                                h_val, s, v = rgb_to_hsv(r, g, b)
                                if s > 0.3 and v > 0.3:
                                    hues.append(h_val)
                
                print(f"  Distinct colors found: {len(distinct_colors)}")
                print(f"  Distinct hues: {len(set(hues))}")
                
                if len(set(hues)) >= 3:
                    print(f"\n✅ SUCCESS: Found {len(set(hues))} distinct color hues!")
                    return True
                else:
                    print(f"\n⚠️  Only {len(set(hues))} distinct hues found")
                    return False
                    
            except ImportError:
                print("  PIL not available for screenshot analysis")
                return pal0_has_color and pal1_has_color and pal7_has_color
        
        return pal0_has_color and pal1_has_color and pal7_has_color

def main():
    print("🔍 Creating detailed verification script...")
    lua_script = create_detailed_lua()
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    
    print(f"🚀 Launching mgba-qt for detailed verification...")
    cmd = [
        "/usr/local/bin/mgba-qt",
        str(rom_path),
        "--fastforward",
        "--script", str(lua_script),
    ]
    
    # Use XWayland environment for window positioning
    import os
    sys.path.insert(0, str(Path(__file__).parent))
    from mgba_window_utils import get_mgba_env_for_xwayland
    env = get_mgba_env_for_xwayland()
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    
    # Give mgba-qt a moment to initialize, then move to Dell monitor
    time.sleep(1)
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from mgba_window_utils import move_window_to_monitor
    move_window_to_monitor()
    
    # Wait for script to complete (it stops after 10 screenshots)
    print("   Waiting for verification to complete...")
    try:
        process.wait(timeout=120)  # Max 2 minutes
    except subprocess.TimeoutExpired:
        process.kill()
        print("   ⚠️  Timeout - killing process")
    finally:
        # ALWAYS ensure mgba-qt is killed
        try:
            process.kill()
        except:
            pass
        subprocess.run(["pkill", "-9", "mgba-qt"], stderr=subprocess.DEVNULL, timeout=1)
    
    time.sleep(2)  # Let files finish writing
    
    print("\n📊 Analyzing results...")
    success = analyze_results()
    
    if success:
        print("\n✅ VERIFICATION SUCCESS - Colors are working!")
    else:
        print("\n❌ VERIFICATION FAILED - Colors not working correctly")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

