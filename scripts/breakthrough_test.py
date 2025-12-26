#!/usr/bin/env python3
"""
Breakthrough Testing System - Combines mgba-headless logs + mgba-qt screenshots + analysis
This is the unified system that combines ALL data sources for breakthrough insights
"""
import subprocess
import json
import time
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import yaml

class BreakthroughTester:
    def __init__(self, rom_path: Path, output_dir: Path):
        self.rom_path = rom_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        self.screenshots_dir = self.output_dir / "screenshots"
        self.logs_dir = self.output_dir / "logs"
        self.analysis_dir = self.output_dir / "analysis"
        
        for d in [self.screenshots_dir, self.logs_dir, self.analysis_dir]:
            d.mkdir(exist_ok=True)
    
    def create_headless_lua(self) -> Path:
        """Create working Lua script for mgba-headless based on working_trace_oam_writes.lua"""
        lua_script = self.logs_dir / "breakthrough_trace.lua"
        
        log_path = str(self.logs_dir / "oam_trace.log")
        json_path = str(self.logs_dir / "oam_writes.json")
        
        script_content = f'''-- Breakthrough OAM tracing - based on working_trace_oam_writes.lua
local logFile = nil
local writeCount = 0
local frameCount = 0
local writes_this_frame = {{}}
local all_writes = {{}}

-- Initialize log file
logFile = io.open("{log_path}", "w")
logFile:write("=== Breakthrough OAM Write Trace ===\\n")
logFile:write("Format: Frame, SpriteIndex, Tile, Palette, Flags, PC\\n")

-- Track all OAM writes by monitoring flags bytes
local function on_oam_write(addr, value)
    local sprite_index = math.floor((addr - 0xFE00) / 4)
    local tile_addr = addr - 1
    local tile = emu:read8(tile_addr)
    local pc = emu:getRegister("PC")
    
    writeCount = writeCount + 1
    
    local write_data = {{
        frame = frameCount,
        sprite = sprite_index,
        tile = tile,
        palette = value & 0x07,
        flags = value,
        pc = pc
    }}
    
    table.insert(writes_this_frame, write_data)
    table.insert(all_writes, write_data)
end

-- Set up memory callbacks for flags bytes
-- Try both API styles for compatibility
for sprite = 0, 39 do
    local flags_addr = 0xFE00 + (sprite * 4) + 3
    local callback = function(addr, value)
        on_oam_write(addr, value)
    end
    
    -- Try new API first (emu.memoryCallback.WRITE)
    if emu.memoryCallback and emu.memoryCallback.WRITE then
        emu:addMemoryCallback(callback, emu.memoryCallback.WRITE, flags_addr, flags_addr)
    -- Fall back to old API (just "write" string)
    elseif emu.addMemoryCallback then
        emu:addMemoryCallback(callback, "write", flags_addr, flags_addr)
    else
        -- Last resort: try direct callback registration
        emu:addMemoryCallback(callback, 1, flags_addr, flags_addr)  -- 1 = write
    end
end

-- Frame callback to log writes
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Log writes from this frame
    if #writes_this_frame > 0 then
        logFile:write(string.format("\\n--- Frame %d ---\\n", frameCount))
        for _, write in ipairs(writes_this_frame) do
            logFile:write(string.format("Sprite[%d]: Tile=%d Palette=%d Flags=0x%02X PC=0x%04X\\n",
                write.sprite, write.tile, write.palette, write.flags, write.pc))
        end
        logFile:flush()
        writes_this_frame = {{}}
    end
    
    -- Log OAM state every 60 frames
    if frameCount % 60 == 0 then
        logFile:write(string.format("\\n=== Frame %d OAM State ===\\n", frameCount))
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local flags = emu:read8(oamBase + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 then
                logFile:write(string.format("Sprite %2d: Y=%3d X=%3d Tile=%3d Palette=%d\\n",
                    i, y, x, tile, palette))
            end
        end
        logFile:flush()
    end
    
    -- Stop after 5 seconds (300 frames at 60fps)
    if frameCount >= 300 then
        logFile:write(string.format("\\n=== Summary ===\\n"))
        logFile:write(string.format("Total frames: %d\\n", frameCount))
        logFile:write(string.format("Total writes: %d\\n", writeCount))
        logFile:close()
        
        -- Write JSON file
        local jsonFile = io.open("{json_path}", "w")
        jsonFile:write("[\\n")
        for i, write in ipairs(all_writes) do
            jsonFile:write(string.format('  {{"frame":%d,"sprite":%d,"tile":%d,"palette":%d,"flags":%d,"pc":%d}}',
                write.frame, write.sprite, write.tile, write.palette, write.flags, write.pc))
            if i < #all_writes then jsonFile:write(",") end
            jsonFile:write("\\n")
        end
        jsonFile:write("]\\n")
        jsonFile:close()
        
        emu:stop()
    end
end)

print("Breakthrough OAM tracing started")
'''
        
        lua_script.write_text(script_content)
        return lua_script
    
    def run_headless_trace(self, duration_seconds: int = 5) -> Dict:
        """Run mgba-headless with OAM tracing"""
        lua_script = self.create_headless_lua()
        
        cmd = [
            "mgba-headless",
            str(self.rom_path),
            "--script", str(lua_script),
        ]
        
        print(f"🔍 Running mgba-headless trace (duration: {duration_seconds}s)...")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 5,
                cwd=str(self.output_dir)
            )
            
            elapsed = time.time() - start_time
            log_exists = (self.logs_dir / "oam_trace.log").exists()
            
            return {
                "success": log_exists,
                "elapsed": elapsed,
                "stdout": result.stdout[-500:] if result.stdout else "",
                "stderr": result.stderr[-500:] if result.stderr else "",
                "returncode": result.returncode,
                "log_created": log_exists
            }
        except subprocess.TimeoutExpired:
            log_exists = (self.logs_dir / "oam_trace.log").exists()
            return {
                "success": log_exists,
                "error": "Timeout (expected)",
                "elapsed": time.time() - start_time,
                "log_created": log_exists
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time
            }
    
    def create_mgba_qt_lua(self, duration_seconds: int = 5) -> Path:
        """Create Lua script for mgba-qt screenshot + OAM logging"""
        lua_script = self.logs_dir / "mgba_qt_capture.lua"
        
        screenshot_base = str(self.screenshots_dir / "qt_frame_")
        tile_log_path = str(self.logs_dir / "qt_tile_log.txt")
        
        script_content = f'''-- mgba-qt screenshot + OAM logging
local frameCount = 0
local screenshotCount = 0
local tileLogFile = nil

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize on first frame
    if frameCount == 1 then
        tileLogFile = io.open("{tile_log_path}", "w")
        if tileLogFile then
            tileLogFile:write("=== mgba-qt Tile Log ===\\n")
        end
    end
    
    -- Capture screenshot every 60 frames (~1 per second)
    if frameCount % 60 == 0 then
        screenshotCount = screenshotCount + 1
        local screenshot = emu:takeScreenshot()
        screenshot:save("{screenshot_base}" .. string.format("%05d", frameCount) .. ".png")
        
        -- Log OAM state with screenshot
        if tileLogFile then
            tileLogFile:write(string.format("\\n=== Screenshot %d (Frame %d) ===\\n", screenshotCount, frameCount))
            for i = 0, 39 do
                local oamBase = 0xFE00 + (i * 4)
                local y = emu:read8(oamBase)
                local x = emu:read8(oamBase + 1)
                local tile = emu:read8(oamBase + 2)
                local flags = emu:read8(oamBase + 3)
                local palette = flags & 0x07
                
                if y > 0 and y < 144 then
                    tileLogFile:write(string.format("Sprite %2d: Tile=%3d Palette=%d Pos=(%3d,%3d)\\n",
                        i, tile, palette, x, y))
                end
            end
            tileLogFile:flush()
        end
    end
    
    -- Stop after {duration_seconds} seconds (300 frames at 60fps)
    if frameCount >= 300 then
        if tileLogFile then
            tileLogFile:write(string.format("\\n=== Summary ===\\n"))
            tileLogFile:write(string.format("Screenshots: %d\\n", screenshotCount))
            tileLogFile:close()
        end
        emu:stop()
    end
end)

print("mgba-qt capture script loaded")
'''
        
        lua_script.write_text(script_content)
        return lua_script
    
    def run_mgba_qt_capture(self, duration_seconds: int = 5) -> Dict:
        """Run mgba-qt with screenshot capture"""
        lua_script = self.create_mgba_qt_lua(duration_seconds)
        
        cmd = [
            "/usr/local/bin/mgba-qt",
            str(self.rom_path),
            "--fastforward",
            "--script", str(lua_script),
        ]
        
        print(f"📸 Running mgba-qt capture (duration: {duration_seconds}s)...")
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            time.sleep(duration_seconds + 2)
            
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                process.kill()
            
            elapsed = time.time() - start_time
            log_exists = (self.logs_dir / "qt_tile_log.txt").exists()
            screenshots = len(list(self.screenshots_dir.glob("qt_frame_*.png")))
            
            return {
                "success": log_exists or screenshots > 0,
                "elapsed": elapsed,
                "log_created": log_exists,
                "screenshots": screenshots
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time
            }
    
    def analyze_breakthrough(self, expected_mapping: Dict) -> Dict:
        """Analyze combined data for breakthrough insights"""
        results = {
            "headless": {},
            "mgba_qt": {},
            "insights": {}
        }
        
        # Analyze headless OAM trace
        oam_json = self.logs_dir / "oam_writes.json"
        if oam_json.exists():
            try:
                with open(oam_json) as f:
                    oam_writes = json.load(f)
                    results["headless"]["total_writes"] = len(oam_writes)
                    
                    # Group by tile
                    tile_to_palette = defaultdict(lambda: defaultdict(int))
                    tile_to_pc = defaultdict(list)
                    
                    for write in oam_writes:
                        tile = write.get("tile", -1)
                        palette = write.get("palette", -1)
                        pc = write.get("pc", 0)
                        
                        if tile >= 0:
                            tile_to_palette[tile][palette] += 1
                            tile_to_pc[tile].append(pc)
                    
                    # Find most common palette per tile
                    tile_palette_map = {}
                    for tile, palette_counts in tile_to_palette.items():
                        if palette_counts:
                            most_common = max(palette_counts.items(), key=lambda x: x[1])
                            total = sum(palette_counts.values())
                            tile_palette_map[tile] = {
                                "palette": most_common[0],
                                "confidence": most_common[1] / total,
                                "total_writes": total,
                                "unique_pcs": len(set(tile_to_pc[tile]))
                            }
                    
                    results["headless"]["tile_palette_map"] = tile_palette_map
            except Exception as e:
                results["headless"]["error"] = str(e)
        
        # Analyze mgba-qt screenshots
        screenshots = sorted(self.screenshots_dir.glob("qt_frame_*.png"))
        results["mgba_qt"]["screenshot_count"] = len(screenshots)
        
        # Compare with expected
        if "monster_palette_map" in expected_mapping:
            expected_tile_map = {}
            for monster_name, data in expected_mapping["monster_palette_map"].items():
                palette = data.get("palette", 0xFF)
                tile_range = data.get("tile_range", [])
                for tile in tile_range:
                    expected_tile_map[tile] = palette
            
            actual_map = results["headless"].get("tile_palette_map", {})
            
            matches = []
            mismatches = []
            missing = []
            
            for tile, expected_pal in expected_tile_map.items():
                if tile in actual_map:
                    actual_data = actual_map[tile]
                    actual_pal = actual_data.get("palette", 0xFF)
                    confidence = actual_data.get("confidence", 0)
                    
                    if actual_pal == expected_pal and confidence > 0.8:
                        matches.append({"tile": tile, "palette": actual_pal, "confidence": confidence})
                    else:
                        mismatches.append({
                            "tile": tile,
                            "expected": expected_pal,
                            "actual": actual_pal,
                            "confidence": confidence
                        })
                else:
                    missing.append({"tile": tile, "expected": expected_pal})
            
            results["insights"] = {
                "matches": len(matches),
                "mismatches": len(mismatches),
                "missing": len(missing),
                "accuracy": len(matches) / len(expected_tile_map) if expected_tile_map else 0,
                "match_details": matches[:10],
                "mismatch_details": mismatches[:10]
            }
        
        return results
    
    def generate_breakthrough_report(self, expected_mapping: Dict) -> str:
        """Generate breakthrough report"""
        analysis = self.analyze_breakthrough(expected_mapping)
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("BREAKTHROUGH TEST REPORT - Combined Analysis")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Headless results
        report_lines.append("mgba-headless OAM Trace:")
        if analysis["headless"].get("total_writes"):
            report_lines.append(f"  Total OAM writes: {analysis['headless']['total_writes']}")
        if analysis["headless"].get("tile_palette_map"):
            report_lines.append(f"  Unique tiles tracked: {len(analysis['headless']['tile_palette_map'])}")
        report_lines.append("")
        
        # mgba-qt results
        report_lines.append("mgba-qt Screenshots:")
        report_lines.append(f"  Screenshots captured: {analysis['mgba_qt']['screenshot_count']}")
        report_lines.append("")
        
        # Insights
        if analysis["insights"]:
            report_lines.append("BREAKTHROUGH INSIGHTS:")
            report_lines.append(f"  ✅ Matches: {analysis['insights']['matches']}")
            report_lines.append(f"  ❌ Mismatches: {analysis['insights']['mismatches']}")
            report_lines.append(f"  ⚠️  Missing: {analysis['insights']['missing']}")
            report_lines.append(f"  📊 Accuracy: {analysis['insights']['accuracy']*100:.1f}%")
            report_lines.append("")
            
            if analysis["insights"]["mismatch_details"]:
                report_lines.append("Mismatches (first 10):")
                for m in analysis["insights"]["mismatch_details"]:
                    report_lines.append(f"  Tile {m['tile']}: expected palette {m['expected']}, got {m['actual']} (confidence: {m['confidence']:.2f})")
                report_lines.append("")
        
        report_lines.append("=" * 80)
        
        report_text = "\n".join(report_lines)
        
        # Save report
        report_file = self.analysis_dir / "breakthrough_report.txt"
        report_file.write_text(report_text)
        
        # Save JSON
        json_file = self.analysis_dir / "breakthrough_analysis.json"
        with open(json_file, "w") as f:
            json.dump(analysis, f, indent=2)
        
        return report_text

def main():
    import sys
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    output_dir = Path("test_output") / f"breakthrough_{int(time.time())}"
    
    if len(sys.argv) > 1:
        rom_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        sys.exit(1)
    
    # Load expected mapping
    monster_map_path = Path("palettes/monster_palette_map.yaml")
    expected_mapping = {}
    if monster_map_path.exists():
        with open(monster_map_path) as f:
            expected_mapping = yaml.safe_load(f)
    
    tester = BreakthroughTester(rom_path, output_dir)
    
    print("🚀 Starting breakthrough testing system...")
    print(f"   ROM: {rom_path}")
    print(f"   Output: {output_dir}")
    print()
    
    # Run headless trace
    print("1️⃣  Running mgba-headless OAM trace...")
    headless_result = tester.run_headless_trace(duration_seconds=5)
    if headless_result.get("success"):
        print("   ✅ mgba-headless trace completed")
        if headless_result.get("log_created"):
            print(f"   📝 Log file created")
    else:
        print(f"   ⚠️  mgba-headless: {headless_result.get('error', 'Unknown')}")
    print()
    
    # Run mgba-qt capture
    print("2️⃣  Running mgba-qt screenshot capture...")
    qt_result = tester.run_mgba_qt_capture(duration_seconds=5)
    if qt_result.get("success"):
        print(f"   ✅ mgba-qt capture completed ({qt_result.get('screenshots', 0)} screenshots)")
    else:
        print(f"   ⚠️  mgba-qt: {qt_result.get('error', 'Unknown')}")
    print()
    
    # Generate breakthrough report
    print("3️⃣  Generating breakthrough report...")
    report = tester.generate_breakthrough_report(expected_mapping)
    print(report)
    
    print(f"\n📊 Full results saved to: {output_dir}")
    print(f"   📄 Report: {output_dir / 'analysis' / 'breakthrough_report.txt'}")
    print(f"   📊 JSON: {output_dir / 'analysis' / 'breakthrough_analysis.json'}")

if __name__ == "__main__":
    main()

