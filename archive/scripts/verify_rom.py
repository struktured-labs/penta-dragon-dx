#!/usr/bin/env python3
import subprocess
import time
import sys
import os
from pathlib import Path

def run_test(rom_path):
    print(f"🚀 Verifying ROM: {rom_path}")
    
    # Check if mgba (CLI) is available
    mgba_path = "/usr/local/bin/mgba"
    if not Path(mgba_path).exists():
        mgba_path = subprocess.getoutput("which mgba")
    
    if not mgba_path:
        print("❌ CLI mGBA not found! Falling back to mgba-qt.")
        mgba_path = "/usr/local/bin/mgba-qt"

    lua_script = Path("scripts/check_white_screen.lua").absolute()
    
    # Launch mGBA with Lua script
    # Note: mgba-qt -script flag might vary by version. 
    # If -script doesn't work, we'll try other methods.
    try:
        # Using a timeout and capturing output
        cmd = [mgba_path, "-p", str(lua_script), rom_path]
        print(f"Running command: {' '.join(cmd)}")
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        start_time = time.time()
        timeout = 15 # 15 seconds max
        
        success = False
        error_detected = False
        
        while time.time() - start_time < timeout:
            line = proc.stdout.readline()
            if line:
                print(f"Emulator: {line.strip()}")
                if "CONTENT_DETECTED" in line:
                    success = True
                    break
                if "WHITE_SCREEN_FREEZE_DETECTED" in line:
                    error_detected = True
                    break
            
            if proc.poll() is not None:
                break
            time.sleep(0.1)
            
        proc.terminate()
        
        if success:
            print("✅ Content detected on screen! Game is not frozen.")
            return True
        elif error_detected:
            print("❌ White screen freeze detected by Lua script.")
            return False
        else:
            print("❌ Timeout or unknown error during verification.")
            return False
            
    except Exception as e:
        print(f"❌ Verification Error: {e}")
        return False

if __name__ == "__main__":
    rom = "rom/working/penta_dragon_cursor_dx.gb"
    if len(sys.argv) > 1:
        rom = sys.argv[1]
    
    if run_test(rom):
        print("\n✨ STABILITY VERIFIED: Game is running and rendering content.")
        sys.exit(0)
    else:
        print("\n💥 VERIFICATION FAILED: Game is stuck or crashing.")
        sys.exit(1)
