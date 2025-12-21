#!/usr/bin/env python3
"""
Capture sprites from original ROM using the working screenshot approach
"""
import subprocess
import time
import os
from pathlib import Path

def main():
    base_dir = Path(__file__).parent.parent
    rom_path = base_dir / "rom/Penta Dragon (J).gb"
    output_dir = base_dir / "sprite_captures"
    output_dir.mkdir(exist_ok=True)
    
    # Create Lua script for screenshot capture (similar to quick_verify_rom.py)
    lua_script_content = f'''-- Capture screenshots from original ROM
local frameCount = 0
local screenshotDir = "{output_dir}"
local screenshotCount = 0

console:log("=== Sprite Capture Script ===")
console:log("Screenshot directory: " .. screenshotDir)
console:log("Capturing every 60 frames (1 second)")

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    if frameCount % 60 == 0 then
        screenshotCount = screenshotCount + 1
        local filename = screenshotDir .. "/frame_" .. string.format("%05d", screenshotCount) .. ".png"
        
        -- Use emu:screenshot() which is the working method
        local success = emu:screenshot(filename)
        
        if success then
            -- Verify file exists
            local file = io.open(filename, "r")
            if file then
                file:close()
                console:log(string.format("✅ Captured frame %d: %s", frameCount, filename))
            else
                console:log(string.format("⚠️  Screenshot call succeeded but file not found: %s", filename))
            end
        else
            console:log(string.format("❌ Failed to capture frame %d", frameCount))
        end
    end
    
    if frameCount >= 1200 then
        console:log("Capture complete - " .. screenshotCount .. " screenshots")
        emu:stop()
    end
end)
'''
    
    lua_script = output_dir / "capture.lua"
    lua_script.write_text(lua_script_content)
    
    print("=" * 80)
    print("CAPTURING SPRITES FROM ORIGINAL ROM")
    print("=" * 80)
    print(f"📁 Output: {output_dir}")
    print(f"🎮 ROM: {rom_path}")
    print(f"📝 Lua: {lua_script}")
    print()
    print("🚀 Launching mgba-qt...")
    print("   Screenshots will be saved every 1 second")
    print("   Run for 20 seconds")
    print("=" * 80)
    
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "xcb"
    env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    
    cmd = ["/usr/local/bin/mgba-qt", str(rom_path), "--fastforward", "--script", str(lua_script)]
    
    try:
        process = subprocess.Popen(cmd, env=env)
        print(f"✅ mgba-qt launched (PID: {process.pid})")
        print("⏳ Running for 20 seconds...")
        time.sleep(20)
        print("🛑 Terminating...")
        process.terminate()
        try:
            process.wait(timeout=2)
        except:
            process.kill()
        
        # List captured files
        print("\n📸 Captured screenshots:")
        png_files = sorted(output_dir.glob("frame_*.png"))
        if png_files:
            print(f"   Found {len(png_files)} screenshots")
            for f in png_files[:10]:
                print(f"   ✅ {f.name}")
            if len(png_files) > 10:
                print(f"   ... and {len(png_files) - 10} more")
        else:
            print("   ⚠️  No screenshots found")
        
        print(f"\n✅ Complete! Files in: {output_dir}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()

