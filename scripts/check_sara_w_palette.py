#!/usr/bin/env python3
"""Check what palette SARA_W is actually using in the ROM"""
import subprocess
import time
from pathlib import Path

def create_palette_check_lua():
    """Create Lua script to check OBJ Palette 1 and SARA_W sprite palette assignment"""
    script = '''-- Check SARA_W palette usage
local frameCount = 0
local logFile = io.open("sara_w_palette_check.txt", "w")

logFile:write("=== SARA_W Palette Check ===\\n")

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Check around frame 203 (when SARA_W is centered)
    if frameCount == 1800 + (203 * 60) then  -- Approximate frame 203
        logFile:write(string.format("\\n=== Frame %d (SARA_W centered) ===\\n", frameCount))
        
        -- Check OBJ Palette 1 (SARA_W should use this)
        logFile:write("\\nOBJ Palette 1 (SARA_W palette):\\n")
        for i = 0, 3 do
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (i * 2))
            local lo = emu:read8(0xFF6B)
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (i * 2) + 1)
            local hi = emu:read8(0xFF6B)
            local color = lo | (hi << 8)
            logFile:write(string.format("  Color %d: %04X\\n", i, color))
        end
        
        -- Find SARA_W sprites (tiles 4-7)
        logFile:write("\\nSARA_W sprites (tiles 4-7):\\n")
        for sprite = 0, 39 do
            local oam = 0xFE00 + (sprite * 4)
            local y = emu:read8(oam)
            local x = emu:read8(oam + 1)
            local tile = emu:read8(oam + 2)
            local flags = emu:read8(oam + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 and tile >= 4 and tile < 8 then
                logFile:write(string.format("  Sprite %d: tile=%d, palette=%d, pos=(%d,%d)\\n", 
                    sprite, tile, palette, x, y))
            end
        end
        
        -- Also check all OBJ palettes to see what's loaded
        logFile:write("\\nAll OBJ Palettes:\\n")
        for pal = 0, 7 do
            logFile:write(string.format("  Palette %d:", pal))
            for i = 0, 3 do
                emu:write8(0xFF6A, 0x80 + (pal * 8) + (i * 2))
                local lo = emu:read8(0xFF6B)
                emu:write8(0xFF6A, 0x80 + (pal * 8) + (i * 2) + 1)
                local hi = emu:read8(0xFF6B)
                local color = lo | (hi << 8)
                logFile:write(string.format(" %04X", color))
            end
            logFile:write("\\n")
        end
        
        logFile:close()
        emu:quit()
    end
end)
'''
    script_path = Path("rom/working/check_sara_w_palette.lua")
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script)
    return script_path

def main():
    project_root = Path(__file__).parent.parent
    rom_path = project_root / "rom/working/penta_dragon_cursor_dx.gb"
    
    if not rom_path.exists():
        print("❌ ROM not found. Building...")
        subprocess.run(["python3", "scripts/penta_cursor_dx_gbc_native.py"], check=True)
    
    lua_script = create_palette_check_lua()
    
    print("🔍 Checking SARA_W palette usage...")
    print("   Launching mGBA headlessly with Xvfb...")
    
    # Use Xvfb for headless operation (same as verify_palette_injection.py)
    import os
    xvfb_available = subprocess.run(['which', 'Xvfb'], capture_output=True).returncode == 0
    
    if xvfb_available:
        # Use Xvfb to provide virtual display
        display_num = 99
        xvfb_cmd = ['Xvfb', f':{display_num}', '-screen', '0', '1024x768x24', '-ac']
        xvfb_proc = subprocess.Popen(xvfb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)  # Give Xvfb time to start
        display_env = f':{display_num}'
        print(f"✓ Using Xvfb virtual display :{display_num}")
    else:
        # Try to use existing display or fail gracefully
        display_env = os.environ.get('DISPLAY', ':0')
        print(f"⚠️  Xvfb not available, using DISPLAY={display_env}")
        xvfb_proc = None
    
    env = os.environ.copy()
    env['DISPLAY'] = display_env
    env['QT_QPA_PLATFORM'] = 'xcb'
    
    proc = subprocess.Popen(
        ['/usr/local/bin/mgba-qt', str(rom_path.resolve()), '--script', str(lua_script.resolve()), '--fastforward'],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for script to complete
    time.sleep(120)  # Wait 2 minutes
    
    # Kill mGBA
    try:
        if proc.poll() is None:
            proc.terminate()
            time.sleep(1)
            if proc.poll() is None:
                proc.kill()
    except:
        pass
    
    # Clean up Xvfb if we started it
    if xvfb_available and xvfb_proc:
        try:
            xvfb_proc.terminate()
            xvfb_proc.wait(timeout=1)
        except:
            xvfb_proc.kill()
    
    # Read results
    log_path = project_root / "sara_w_palette_check.txt"
    if log_path.exists():
        print("\n📊 Results:")
        print(log_path.read_text())
    else:
        print("❌ Log file not found")

if __name__ == "__main__":
    main()

