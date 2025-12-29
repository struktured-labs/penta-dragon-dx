#!/usr/bin/env python3
"""Diagnostic script to check why Sara W isn't getting distinct colors"""
import subprocess
import time
from pathlib import Path

def create_diagnostic_lua():
    """Create Lua script to diagnose OAM and palette state"""
    script = '''-- Diagnostic script for Sara W colorization
local frameCount = 0
local logFile = nil

function onFrame()
    frameCount = frameCount + 1
    
    -- Open file on first frame
    if frameCount == 1 then
        logFile = io.open("rom/working/sara_w_diagnostic.txt", "w")
        if not logFile then
            console:log("ERROR: Could not open log file!")
            return
        end
        logFile:write("=== Sara W Diagnostic Log ===\\n")
    end
    
    if not logFile then return end
    
    -- Log every 60 frames (1 second)
    if frameCount % 60 == 0 then
        logFile:write(string.format("\\n=== Frame %d ===\\n", frameCount))
        
        -- Check OBJ palettes
        logFile:write("OBJ Palettes:\\n")
        for pal = 0, 7 do
            local colors = {}
            for i = 0, 3 do
                emu:write8(0xFF6A, 0x80 + (pal * 8) + (i * 2))
                local lo = emu:read8(0xFF6B)
                emu:write8(0xFF6A, 0x80 + (pal * 8) + (i * 2) + 1)
                local hi = emu:read8(0xFF6B)
                local color = lo + (hi * 256)
                table.insert(colors, string.format("%04X", color))
            end
            logFile:write(string.format("  Palette %d: %s\\n", pal, table.concat(colors, " ")))
        end
        
        -- Check OAM for Sara W tiles (4-7, 10-13)
        logFile:write("\\nOAM Sprites with Sara W tiles (4-7, 10-13):\\n")
        local sara_w_count = 0
        for sprite = 0, 39 do
            local oam_addr = 0xFE00 + (sprite * 4)
            local y = emu:read8(oam_addr)
            local x = emu:read8(oam_addr + 1)
            local tile = emu:read8(oam_addr + 2)
            local flags = emu:read8(oam_addr + 3)
            local palette = flags & 0x07
            
            -- Check if this is a Sara W tile
            if y > 0 and y < 144 and (tile >= 4 and tile < 8) or (tile >= 10 and tile < 14) then
                sara_w_count = sara_w_count + 1
                logFile:write(string.format("  Sprite %d: tile=%d, palette=%d, pos=(%d,%d), flags=0x%02X\\n", 
                    sprite, tile, palette, x, y, flags))
            end
        end
        logFile:write(string.format("Total Sara W sprites found: %d\\n", sara_w_count))
        
        -- Check all visible sprites
        logFile:write("\\nAll visible sprites (first 20):\\n")
        local visible_count = 0
        for sprite = 0, 39 do
            if visible_count >= 20 then break end
            local oam_addr = 0xFE00 + (sprite * 4)
            local y = emu:read8(oam_addr)
            local x = emu:read8(oam_addr + 1)
            local tile = emu:read8(oam_addr + 2)
            local flags = emu:read8(oam_addr + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 then
                visible_count = visible_count + 1
                logFile:write(string.format("  Sprite %d: tile=%d, palette=%d, pos=(%d,%d)\\n", 
                    sprite, tile, palette, x, y))
            end
        end
        
        logFile:flush()
    end
    
    -- Stop after 5 seconds
    if frameCount >= 300 then
        if logFile then
            logFile:close()
        end
        emu:stop()
    end
end

callbacks:add("frame", onFrame)
console:log("Sara W diagnostic script loaded")
'''
    script_path = Path("rom/working/scripts/sara_w_diagnostic.lua")
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script)
    return script_path

def run_diagnostic():
    """Run diagnostic test"""
    print("🔍 Creating diagnostic Lua script...")
    lua_script = create_diagnostic_lua()
    
    print("🚀 Launching mgba-qt with diagnostic script...")
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    if not rom_path.exists():
        print("❌ ROM not found!")
        return
    
    # Launch mgba-qt with script
    env = {'QT_QPA_PLATFORM': 'xcb', 'GDK_BACKEND': 'x11', 'DISPLAY': ':0'}
    proc = subprocess.Popen(
        ['/usr/local/bin/mgba-qt', str(rom_path), '--script', str(lua_script)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env
    )
    
    print("⏳ Running diagnostic for 5 seconds...")
    time.sleep(6)
    
    proc.terminate()
    proc.wait()
    
    # Analyze results
    log_path = Path("rom/working/sara_w_diagnostic.txt")
    if log_path.exists():
        print("\n📊 Diagnostic Results:")
        print("=" * 60)
        with open(log_path, 'r') as f:
            content = f.read()
            # Show last frame's data
            lines = content.split('\n')
            in_last_frame = False
            for i, line in enumerate(lines):
                if '=== Frame' in line and i > len(lines) - 50:
                    in_last_frame = True
                if in_last_frame:
                    print(line)
        print("=" * 60)
        print(f"\n📄 Full log saved to: {log_path}")
    else:
        print("❌ Diagnostic log not found!")

if __name__ == "__main__":
    run_diagnostic()

