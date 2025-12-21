#!/usr/bin/env python3
"""
Identify which captured frames contain Sara W sprites
Then copy/rename them with "Sara_W" in the filename
"""
import subprocess
import time
import json
import shutil
from pathlib import Path

def main():
    base_dir = Path(__file__).parent.parent
    rom_path = base_dir / "rom/Penta Dragon (J).gb"
    screenshot_dir = base_dir / "sprite_captures"
    
    # Create Lua script to identify Sara W frames
    output_file_path = str(screenshot_dir / "sara_w_frames.json")
    lua_content = f'''-- Identify frames with Sara W sprites
local frameCount = 0
local saraWFrames = {{}}
local outputFile = "{output_file_path}"

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Check every frame for Sara W sprites (tiles 4-7)
    if frameCount % 60 == 0 then  -- Check every 60 frames (matching screenshot interval)
        local saraWSprites = []
        local hasSaraW = false
        
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local flags = emu:read8(oamBase + 3)
            local palette = flags & 0x07
            
            -- Check if this is Sara W (tiles 4-7) and visible
            if tile >= 4 and tile <= 7 and y > 0 and y < 144 and x > 0 and x < 168 then
                hasSaraW = true
                table.insert(saraWSprites, {{
                    sprite = i,
                    x = x,
                    y = y,
                    tile = tile,
                    palette = palette
                }})
            end
        end
        
        if hasSaraW then
            local screenshotNum = math.floor(frameCount / 60)
            saraWFrames[screenshotNum] = saraWSprites
            console:log(string.format("Frame %d (screenshot %d): Found %d Sara W sprites", 
                frameCount, screenshotNum, #saraWSprites))
        end
    end
    
    if frameCount >= 1200 then
        -- Write JSON (simplified)
        local jsonStr = "{{"
        local first = true
        for k, v in pairs(saraWFrames) do
            if not first then jsonStr = jsonStr .. "," end
            first = false
            jsonStr = jsonStr .. string.format('"%d":[', k)
            for i, sprite in ipairs(v) do
                if i > 1 then jsonStr = jsonStr .. "," end
                jsonStr = jsonStr .. string.format('{{"sprite":%d,"x":%d,"y":%d,"tile":%d,"palette":%d}}',
                    sprite.sprite, sprite.x, sprite.y, sprite.tile, sprite.palette)
            end
            jsonStr = jsonStr .. "]"
        end
        jsonStr = jsonStr .. "}}"
        
        local file = io.open(outputFile, "w")
        if file then
            file:write(jsonStr)
            file:close()
            console:log("Wrote Sara W frame data to: " .. outputFile)
        end
        emu:stop()
    end
end)
'''
    
    lua_script = screenshot_dir / "identify_sara_w.lua"
    lua_script.write_text(lua_content)
    
    print("=" * 80)
    print("IDENTIFYING SARA W FRAMES")
    print("=" * 80)
    print(f"🎮 ROM: {rom_path}")
    print(f"📝 Analyzing frames to find Sara W sprites...")
    print()
    
    import os
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "xcb"
    env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    
    cmd = ["/usr/local/bin/mgba-qt", str(rom_path), "--fastforward", "--script", str(lua_script)]
    
    try:
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(20)
        process.terminate()
        try:
            process.wait(timeout=2)
        except:
            process.kill()
        
        # Read JSON results
        json_file = screenshot_dir / "sara_w_frames.json"
        if json_file.exists():
            with open(json_file) as f:
                sara_w_data = json.load(f)
            
            print(f"✅ Found Sara W in {len(sara_w_data)} frames")
            
            # Copy screenshots with Sara W to named files
            sara_w_count = 0
            for frame_num_str, sprites in sara_w_data.items():
                frame_num = int(frame_num_str)
                source_file = screenshot_dir / f"frame_{frame_num:05d}.png"
                
                if source_file.exists():
                    # Create Sara W named copy
                    dest_file = screenshot_dir / f"Sara_W_frame_{frame_num:05d}.png"
                    shutil.copy2(source_file, dest_file)
                    sara_w_count += 1
                    if sara_w_count <= 10:
                        print(f"   ✅ {dest_file.name} ({len(sprites)} Sara W sprites)")
            
            if sara_w_count > 10:
                print(f"   ... and {sara_w_count - 10} more Sara W files")
            
            print(f"\n🎯 Created {sara_w_count} Sara W sprite files!")
            print(f"   Location: {screenshot_dir}")
            
        else:
            print("⚠️  JSON file not found - analysis may have failed")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()

