#!/usr/bin/env python3
"""
Capture centered sprites with their names
Runs mgba-qt with Lua script to capture sprites when centered
"""
import subprocess
import os
import time
from pathlib import Path

def main():
    base_dir = Path(__file__).parent.parent
    # Use ORIGINAL ROM for sprite capture
    rom_path = base_dir / "rom/Penta Dragon (J).gb"
    lua_script = base_dir / "scripts/capture_centered_sprites.lua"
    output_dir = base_dir / "sprite_captures"
    output_dir.mkdir(exist_ok=True)
    
    # Use simpler capture script
    lua_script = base_dir / "scripts/simple_sprite_capture.lua"
    temp_lua = output_dir / "simple_sprite_capture_temp.lua"
    
    # Update Lua script to use absolute output path
    lua_content = lua_script.read_text()
    lua_content = lua_content.replace('local outputDir = "sprite_captures"', 
        f'local outputDir = "{output_dir}"')
    temp_lua.write_text(lua_content)
    
    print("=" * 80)
    print("CAPTURING SPRITES FROM ORIGINAL ROM")
    print("=" * 80)
    print(f"📁 Output directory: {output_dir}")
    print(f"🎮 ROM: {rom_path} (ORIGINAL)")
    print(f"📝 Lua script: {temp_lua}")
    print()
    print("📋 What will be captured:")
    print("   - Screenshots every 1 second (60 frames)")
    print("   - Files saved as: frame_<num>.png")
    print("   - Focus on Sara W and other monsters")
    print()
    print("=" * 80)
    
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "xcb"
    env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    
    cmd = ["/usr/local/bin/mgba-qt", str(rom_path), "--fastforward", "--script", str(temp_lua)]
    
    print(f"🚀 Launching: {' '.join(cmd)}")
    print("⏳ Running for 15 seconds...")
    
    try:
        process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(15)  # Give it more time to capture
        print("🛑 Terminating...")
        process.terminate()
        try:
            process.wait(timeout=2)
        except:
            process.kill()
        
        # List captured files
        print("\n📸 Captured screenshots:")
        png_files = sorted(output_dir.glob("sprite_*.png"))
        if png_files:
            for png_file in png_files:
                print(f"   ✅ {png_file.name}")
        else:
            print("   ⚠️  No screenshots captured")
        
        # Show Sara W files specifically
        sara_w_files = [f for f in png_files if "Sara_W" in f.name]
        if sara_w_files:
            print(f"\n🎯 Sara W files ({len(sara_w_files)}):")
            for f in sara_w_files[:10]:  # Show first 10
                print(f"   📷 {f.name}")
            if len(sara_w_files) > 10:
                print(f"   ... and {len(sara_w_files) - 10} more")
        else:
            print("\n⚠️  No Sara W files captured yet")
        
        print(f"\n✅ Capture complete! Files saved to: {output_dir}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()

