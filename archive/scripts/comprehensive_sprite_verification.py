#!/usr/bin/env python3
"""
Comprehensive Sprite Verification - Focus on Sara W and Dragonfly
Verifies 100% color override using screenshots and OAM analysis
"""
import subprocess
import json
import time
from pathlib import Path
from collections import defaultdict
import yaml

def create_sprite_focused_lua(output_dir: Path):
    """Create Lua script that focuses on sprite verification"""
    lua_script = output_dir / "sprite_verify.lua"
    
    screenshot_base = str(output_dir / "sprite_frame_")
    oam_json = str(output_dir / "oam_analysis.json")
    sprite_log = str(output_dir / "sprite_analysis.log")
    
    script_content = f'''-- Comprehensive sprite verification - focus on Sara W and Dragonfly
print("=== Sprite Verification Script Starting ===")

local frameCount = 0
local oamWrites = {{}}
local logFile = io.open("{sprite_log}", "w")

if not logFile then
    print("ERROR: Could not open log file!")
    return
end

logFile:write("=== Sprite Verification Log ===\\n")
logFile:write("Focus: Sara W (tiles 4-7) and Dragonfly (tiles 0-3)\\n")
logFile:flush()

print("Log file opened: " .. "{sprite_log}")

-- Track OAM writes for target tiles
for sprite = 0, 39 do
    local flagsAddr = 0xFE00 + (sprite * 4) + 3
    emu:addMemoryCallback(function(addr, value)
        local tile = emu:read8(addr - 1)
        -- Focus on Sara W (4-7) and Dragonfly (0-3)
        if tile >= 0 and tile <= 7 then
            table.insert(oamWrites, {{
                frame = frameCount,
                sprite = math.floor((addr - 0xFE00) / 4),
                tile = tile,
                palette = value & 0x07,
                flags = value,
                pc = emu:getRegister("PC")
            }})
        end
    end, emu.memoryCallback.WRITE, flagsAddr, flagsAddr)
end

print("OAM callbacks registered")

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Capture screenshot every 30 frames (more frequent)
    if frameCount % 30 == 0 then
        local success, screenshot = pcall(function() return emu:takeScreenshot() end)
        if success and screenshot then
            local filename = "{screenshot_base}" .. string.format("%05d", frameCount) .. ".png"
            local saveSuccess = pcall(function() screenshot:save(filename) end)
            if saveSuccess then
                print(string.format("Screenshot saved: %s", filename))
            else
                print(string.format("ERROR: Failed to save screenshot: %s", filename))
            end
        else
            print(string.format("ERROR: Failed to take screenshot at frame %d", frameCount))
        end
        
        -- Log current OAM state for target sprites
        if logFile then
            logFile:write(string.format("\\n=== Frame %d ===\\n", frameCount))
            local sara_w_count = 0
            local dragonfly_count = 0
            
            for i = 0, 39 do
                local oamBase = 0xFE00 + (i * 4)
                local y = emu:read8(oamBase)
                local x = emu:read8(oamBase + 1)
                local tile = emu:read8(oamBase + 2)
                local flags = emu:read8(oamBase + 3)
                local palette = flags & 0x07
                
                if y > 0 and y < 144 and x > 0 and x < 168 then
                    if tile >= 4 and tile <= 7 then
                        sara_w_count = sara_w_count + 1
                        logFile:write(string.format("Sara W: Sprite %d Tile %d Palette %d\\n", i, tile, palette))
                    elseif tile >= 0 and tile <= 3 then
                        dragonfly_count = dragonfly_count + 1
                        logFile:write(string.format("Dragonfly: Sprite %d Tile %d Palette %d\\n", i, tile, palette))
                    end
                end
            end
            
            logFile:write(string.format("Sara W sprites: %d, Dragonfly sprites: %d\\n", sara_w_count, dragonfly_count))
            logFile:flush()
        end
    end
    
    -- Stop after 8 seconds (480 frames at 60fps)
    if frameCount >= 480 then
        print("Reached 480 frames, stopping...")
        if logFile then
            logFile:write(string.format("\\n=== Summary ===\\n"))
            logFile:write(string.format("Total frames: %d\\n", frameCount))
            logFile:write(string.format("OAM writes for target tiles: %d\\n", #oamWrites))
            logFile:close()
        end
        
        -- Write JSON
        local jsonFile = io.open("{oam_json}", "w")
        if jsonFile then
            jsonFile:write("[\\n")
            for i, w in ipairs(oamWrites) do
                jsonFile:write(string.format('  {{"frame":%d,"sprite":%d,"tile":%d,"palette":%d,"flags":%d,"pc":%d}}',
                    w.frame, w.sprite, w.tile, w.palette, w.flags, w.pc))
                if i < #oamWrites then jsonFile:write(",") end
                jsonFile:write("\\n")
            end
            jsonFile:write("]\\n")
            jsonFile:close()
            print("JSON file written")
        else
            print("ERROR: Could not open JSON file")
        end
        
        emu:stop()
    end
end)

print("Sprite verification script loaded - frame callback registered")
'''
    
    lua_script.write_text(script_content)
    return lua_script

def verify_sprite_colors(rom_path: Path) -> dict:
    """Verify sprite colors focusing on Sara W and Dragonfly"""
    output_dir = Path("test_output") / f"sprite_verify_{int(time.time())}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    lua_script = create_sprite_focused_lua(output_dir)
    
    cmd = ["/usr/local/bin/mgba-qt", str(rom_path), "--fastforward", "--script", str(lua_script)]
    
    # Use correct environment for better video support
    import os
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "xcb"
    env["__GLX_VENDOR_LIBRARY_NAME"] = "nvidia"
    
    print(f"🚀 Launching: {' '.join(cmd)}")
    print(f"📝 Lua script: {lua_script}")
    print(f"📁 Output directory: {output_dir}")
    print(f"   Environment: QT_QPA_PLATFORM=xcb, __GLX_VENDOR_LIBRARY_NAME=nvidia")
    
    try:
        # Launch mgba-qt with script - let it run visibly
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        print(f"✅ mgba-qt launched (PID: {process.pid})")
        print("⏳ Running for 10 seconds...")
        time.sleep(10)
        print("🛑 Terminating mgba-qt...")
        process.terminate()
        try:
            process.wait(timeout=2)
        except:
            process.kill()
        print("✅ Process terminated")
    except Exception as e:
        print(f"❌ Error launching mgba-qt: {e}")
        return {"error": str(e)}
    
    # Analyze results
    oam_json = output_dir / "oam_analysis.json"
    sprite_log = output_dir / "sprite_analysis.log"
    
    result = {
        "screenshots": len(list(output_dir.glob("sprite_frame_*.png"))),
        "sara_w_analysis": {},
        "dragonfly_analysis": {},
        "is_100_percent": False
    }
    
    if oam_json.exists():
        try:
            with open(oam_json) as f:
                oam_writes = json.load(f)
            
            # Analyze Sara W (tiles 4-7)
            sara_w_writes = [w for w in oam_writes if w.get("tile", -1) >= 4 and w.get("tile", -1) <= 7]
            if sara_w_writes:
                palette_counts = defaultdict(int)
                for w in sara_w_writes:
                    palette_counts[w.get("palette", -1)] += 1
                
                total = len(sara_w_writes)
                palette_1_count = palette_counts.get(1, 0)
                sara_w_percent = (palette_1_count / total * 100) if total > 0 else 0
                
                result["sara_w_analysis"] = {
                    "total_writes": total,
                    "palette_1_count": palette_1_count,
                    "palette_1_percent": sara_w_percent,
                    "is_100_percent": sara_w_percent >= 95  # Allow 5% margin
                }
            
            # Analyze Dragonfly (tiles 0-3)
            dragonfly_writes = [w for w in oam_writes if w.get("tile", -1) >= 0 and w.get("tile", -1) <= 3]
            if dragonfly_writes:
                palette_counts = defaultdict(int)
                for w in dragonfly_writes:
                    palette_counts[w.get("palette", -1)] += 1
                
                total = len(dragonfly_writes)
                palette_0_count = palette_counts.get(0, 0)
                dragonfly_percent = (palette_0_count / total * 100) if total > 0 else 0
                
                result["dragonfly_analysis"] = {
                    "total_writes": total,
                    "palette_0_count": palette_0_count,
                    "palette_0_percent": dragonfly_percent,
                    "is_100_percent": dragonfly_percent >= 95
                }
            
            # Overall result
            result["is_100_percent"] = (
                result["sara_w_analysis"].get("is_100_percent", False) and
                result["dragonfly_analysis"].get("is_100_percent", False)
            )
        except Exception as e:
            result["error"] = str(e)
    
    return result

def main():
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    
    print("=" * 80)
    print("COMPREHENSIVE SPRITE VERIFICATION")
    print("Focus: Sara W (tiles 4-7) and Dragonfly (tiles 0-3)")
    print("=" * 80)
    print()
    
    result = verify_sprite_colors(rom_path)
    
    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return
    
    print(f"📸 Screenshots captured: {result['screenshots']}")
    print()
    
    if result.get("sara_w_analysis"):
        sw = result["sara_w_analysis"]
        print(f"🎮 Sara W Analysis:")
        print(f"   Total OAM writes: {sw['total_writes']}")
        print(f"   Palette 1 assignments: {sw['palette_1_count']} ({sw['palette_1_percent']:.1f}%)")
        print(f"   Status: {'✅ 100% override' if sw['is_100_percent'] else '❌ Not 100%'}")
        print()
    
    if result.get("dragonfly_analysis"):
        df = result["dragonfly_analysis"]
        print(f"🐉 Dragonfly Analysis:")
        print(f"   Total OAM writes: {df['total_writes']}")
        print(f"   Palette 0 assignments: {df['palette_0_count']} ({df['palette_0_percent']:.1f}%)")
        print(f"   Status: {'✅ 100% override' if df['is_100_percent'] else '❌ Not 100%'}")
        print()
    
    if result.get("is_100_percent"):
        print("=" * 80)
        print("🎉 BREAKTHROUGH: 100% COLOR OVERRIDE ACHIEVED!")
        print("=" * 80)
    else:
        print("⚠️  Not yet at 100% - continuing research...")

if __name__ == "__main__":
    main()

