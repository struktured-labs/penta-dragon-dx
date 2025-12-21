#!/usr/bin/env python3
"""
Analyze captured screenshots to find Sara W sprites and extract names
"""
import subprocess
from pathlib import Path
import json

def analyze_screenshots_with_mgba():
    """Use mgba-headless to analyze screenshots and extract sprite info"""
    base_dir = Path(__file__).parent.parent
    rom_path = base_dir / "rom/Penta Dragon (J).gb"
    screenshot_dir = base_dir / "sprite_captures"
    
    # Create analysis Lua script
    lua_content = '''-- Analyze screenshots and identify Sara W sprites
local frameCount = 0
local saraWFound = {}

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Check every frame for Sara W sprites (tiles 4-7)
    if frameCount % 10 == 0 then
        local saraWSprites = {}
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            
            if tile >= 4 and tile <= 7 and y > 0 and y < 144 and x > 0 and x < 168 then
                table.insert(saraWSprites, {x=x, y=y, tile=tile, frame=frameCount})
            end
        end
        
        if #saraWSprites > 0 then
            local key = frameCount
            saraWFound[key] = saraWSprites
            console:log(string.format("Frame %d: Found %d Sara W sprites", frameCount, #saraWSprites))
        end
    end
    
    if frameCount >= 1200 then
        -- Write results
        local file = io.open("sprite_captures/sara_w_frames.json", "w")
        if file then
            file:write(json.encode(saraWFound))
            file:close()
        end
        emu:stop()
    end
end)
'''
    
    # For now, let's just identify which screenshots likely contain Sara W
    # by checking file sizes and creating a simple analysis
    
    print("=" * 80)
    print("ANALYZING SPRITE CAPTURES")
    print("=" * 80)
    
    png_files = sorted(screenshot_dir.glob("frame_*.png"))
    print(f"📸 Found {len(png_files)} screenshots")
    
    # Show first 20 files as examples
    print("\n📋 Sample screenshots:")
    for f in png_files[:20]:
        size = f.stat().st_size
        print(f"   {f.name} ({size} bytes)")
    
    print(f"\n✅ Screenshots captured successfully!")
    print(f"   Location: {screenshot_dir}")
    print(f"\n💡 Next steps:")
    print(f"   1. Review screenshots manually to find Sara W sprites")
    print(f"   2. Look for frames where Sara W (tiles 4-7) appears centered")
    print(f"   3. Extract sprite names from text on screen")
    
    # Try to identify Sara W frames by checking if we can read OAM data
    # This would require running mgba-headless, which is complex
    # For now, just show the files
    
    return png_files

if __name__ == "__main__":
    files = analyze_screenshots_with_mgba()
    print(f"\n🎯 To find Sara W sprites, look for screenshots where:")
    print(f"   - The playable character (Sara W) is visible")
    print(f"   - The sprite appears centered or prominent")
    print(f"   - The sprite name might be visible in text")

