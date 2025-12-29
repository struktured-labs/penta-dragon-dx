#!/usr/bin/env python3
"""Test script to verify Sara W colorization is working"""
import subprocess
import time
from pathlib import Path

def create_test_lua():
    """Create Lua script to test Sara W colors"""
    script = '''-- Test script for Sara W colorization
local frameCount = 0
local logFile = nil

function onFrame()
    frameCount = frameCount + 1
    
    if frameCount == 1 then
        logFile = io.open("rom/working/sara_w_test.txt", "w")
        logFile:write("=== Sara W Color Test ===\\n")
    end
    
    if not logFile then return end
    
    -- Log every 60 frames
    if frameCount % 60 == 0 then
        logFile:write(string.format("\\nFrame %d:\\n", frameCount))
        
        -- Check OBJ Palette 1 (Sara W)
        local pal1_colors = {}
        for i = 0, 3 do
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (i * 2))
            local lo = emu:read8(0xFF6B)
            emu:write8(0xFF6A, 0x80 + (1 * 8) + (i * 2) + 1)
            local hi = emu:read8(0xFF6B)
            local color = lo + (hi * 256)
            table.insert(pal1_colors, string.format("%04X", color))
        end
        logFile:write(string.format("  Palette 1 (Sara W): %s\\n", table.concat(pal1_colors, " ")))
        
        -- Find Sara W sprites (tiles 4-7)
        local sara_w_sprites = {}
        for sprite = 0, 39 do
            local oam = 0xFE00 + (sprite * 4)
            local y = emu:read8(oam)
            local x = emu:read8(oam + 1)
            local tile = emu:read8(oam + 2)
            local flags = emu:read8(oam + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 and tile >= 4 and tile < 8 then
                table.insert(sara_w_sprites, {
                    sprite = sprite,
                    tile = tile,
                    palette = palette,
                    x = x,
                    y = y
                })
            end
        end
        
        logFile:write(string.format("  Sara W sprites found: %d\\n", #sara_w_sprites))
        for i, s in ipairs(sara_w_sprites) do
            logFile:write(string.format("    Sprite %d: tile=%d, palette=%d, pos=(%d,%d)\\n", 
                s.sprite, s.tile, s.palette, s.x, s.y))
        end
        
        logFile:flush()
    end
    
    if frameCount >= 300 then
        if logFile then logFile:close() end
        emu:stop()
    end
end

callbacks:add("frame", onFrame)
console:log("Sara W test script loaded")
'''
    script_path = Path("rom/working/scripts/sara_w_test.lua")
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script)
    return script_path

def main():
    print("🧪 Testing Sara W colorization...")
    lua_script = create_test_lua()
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    if not rom_path.exists():
        print("❌ ROM not found!")
        return
    
    env = {'QT_QPA_PLATFORM': 'xcb', 'GDK_BACKEND': 'x11', 'DISPLAY': ':0'}
    proc = subprocess.Popen(
        ['/usr/local/bin/mgba-qt', str(rom_path), '--script', str(lua_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env
    )
    
    print("⏳ Running test for 5 seconds...")
    time.sleep(6)
    proc.terminate()
    proc.wait()
    
    log_path = Path("rom/working/sara_w_test.txt")
    if log_path.exists():
        print("\n📊 Test Results:")
        print("=" * 60)
        with open(log_path, 'r') as f:
            print(f.read())
        print("=" * 60)
    else:
        print("❌ Test log not found!")

if __name__ == "__main__":
    main()

