#!/usr/bin/env python3
"""
Unified Testing System - Combines mgba-headless, mgba-qt screenshots, logs, and analysis
This is the breakthrough testing system that combines all data sources
"""
import subprocess
import json
import time
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import yaml

class UnifiedTestingSystem:
    def __init__(self, rom_path: Path, output_dir: Path):
        self.rom_path = rom_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        self.screenshots_dir = self.output_dir / "screenshots"
        self.logs_dir = self.output_dir / "logs"
        self.analysis_dir = self.output_dir / "analysis"
        self.mgba_qt_dir = self.output_dir / "mgba_qt"
        self.mgba_headless_dir = self.output_dir / "mgba_headless"
        
        for d in [self.screenshots_dir, self.logs_dir, self.analysis_dir, 
                  self.mgba_qt_dir, self.mgba_headless_dir]:
            d.mkdir(exist_ok=True)
    
    def create_mgba_headless_lua(self) -> Path:
        """Create Lua script for mgba-headless OAM/palette logging"""
        lua_script = self.mgba_headless_dir / "comprehensive_log.lua"
        
        # Use relative path from script location
        log_path = str(self.mgba_headless_dir / "comprehensive.log")
        oam_json_path = str(self.mgba_headless_dir / "oam_writes.json")
        
        script_content = f'''-- Comprehensive logging for mgba-headless
-- Logs OAM writes, palette state, and performance
-- Based on working_trace_oam_writes.lua pattern

local logFile = nil
local frameCount = 0
local oamWrites = {{}}
local paletteWrites = {{}}
local performanceData = {{}}

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize on first frame
    if frameCount == 1 then
        logFile = io.open("{log_path}", "w")
        if not logFile then
            print("ERROR: Could not open log file: {log_path}")
            return
        end
        logFile:write("=== Comprehensive mgba-headless Log ===\\n")
        print("Log file opened: {log_path}")
        
        -- Set up OAM write callbacks (flags bytes only)
        for sprite = 0, 39 do
            local flagsAddr = 0xFE00 + (sprite * 4) + 3
            emu:addMemoryCallback(function(addr, value)
                local spriteIndex = math.floor((addr - 0xFE00) / 4)
                local tileAddr = addr - 1
                local tile = emu:read8(tileAddr)
                local pc = emu:getRegister("PC")
                
                table.insert(oamWrites, {{
                    frame = frameCount,
                    sprite = spriteIndex,
                    tile = tile,
                    palette = value & 0x07,
                    flags = value,
                    pc = pc
                }})
            end, emu.memoryCallback.WRITE, flagsAddr, flagsAddr)
        end
        
        -- Set up palette write callbacks
        emu:addMemoryCallback(function(addr, value)
            table.insert(paletteWrites, {{
                frame = frameCount,
                register = string.format("0x%04X", addr),
                value = value,
                pc = emu:getRegister("PC")
            }})
        end, emu.memoryCallback.WRITE, 0xFF68, 0xFF6B)
    end
    
    if not logFile then return end
    
    -- Log performance every 10 frames
    if frameCount % 10 == 0 then
        local elapsed = emu:time()
        local fps = frameCount / elapsed
        table.insert(performanceData, {{
            frame = frameCount,
            elapsed = elapsed,
            fps = fps
        }})
    end
    
    -- Log OAM state every 60 frames
    if frameCount % 60 == 0 then
        logFile:write(string.format("\\n=== Frame %d ===\\n", frameCount))
        
        -- Log visible sprites
        local visibleSprites = {{}}
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local flags = emu:read8(oamBase + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 then  -- Visible sprite
                table.insert(visibleSprites, {{
                    sprite = i,
                    y = y,
                    x = x,
                    tile = tile,
                    palette = palette,
                    flags = flags
                }})
                logFile:write(string.format("Sprite %2d: Y=%3d X=%3d Tile=%3d Palette=%d Flags=0x%02X\\n",
                    i, y, x, tile, palette, flags))
            end
        end
        
        -- Log OBJ palettes
        logFile:write("OBJ Palettes:\\n")
        for pal = 0, 7 do
            emu:write8(0xFF6A, 0x80 | (pal * 8))
            local colors = {{}}
            for i = 0, 3 do
                emu:write8(0xFF6A, 0x80 | (pal * 8) | (i * 2))
                local lo = emu:read8(0xFF6B)
                emu:write8(0xFF6A, 0x80 | (pal * 8) | (i * 2) | 1)
                local hi = emu:read8(0xFF6B)
                colors[i + 1] = lo | (hi << 8)
            end
            logFile:write(string.format("  Palette %d: %04X %04X %04X %04X\\n",
                pal, colors[1], colors[2], colors[3], colors[4]))
        end
        logFile:flush()
    end
    
    -- Stop after 5 seconds (300 frames at 60fps)
    if frameCount >= 300 then
        logFile:write(string.format("\\n=== Summary ===\\n"))
        logFile:write(string.format("Total frames: %d\\n", frameCount))
        logFile:write(string.format("OAM writes: %d\\n", #oamWrites))
        logFile:write(string.format("Palette writes: %d\\n", #paletteWrites))
        logFile:close()
        
        -- Write JSON files
        local oamFile = io.open("{oam_json_path}", "w")
        oamFile:write("[\\n")
        for i, write in ipairs(oamWrites) do
            oamFile:write(string.format('  {{"frame":%d,"sprite":%d,"tile":%d,"palette":%d,"flags":%d,"pc":%d}}',
                write.frame, write.sprite, write.tile, write.palette, write.flags, write.pc))
            if i < #oamWrites then oamFile:write(",") end
            oamFile:write("\\n")
        end
        oamFile:write("]\\n")
        oamFile:close()
        
        emu:stop()
    end
end)

print("mgba-headless comprehensive logging script loaded")
'''
        
        lua_script.write_text(script_content)
        return lua_script
    
    def run_mgba_headless(self, duration_seconds: int = 5) -> Dict:
        """Run mgba-headless with comprehensive logging"""
        lua_script = self.create_mgba_headless_lua()
        
        cmd = [
            "mgba-headless",
            str(self.rom_path),
            "--script", str(lua_script),
        ]
        
        print(f"🔍 Running mgba-headless (duration: {duration_seconds}s)...")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 10,
                cwd=str(self.output_dir)
            )
            
            elapsed = time.time() - start_time
            log_exists = (self.mgba_headless_dir / "comprehensive.log").exists()
            
            return {
                "success": log_exists or result.returncode == 0,
                "elapsed": elapsed,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "log_created": log_exists
            }
        except subprocess.TimeoutExpired:
            log_exists = (self.mgba_headless_dir / "comprehensive.log").exists()
            return {
                "success": log_exists,
                "error": "Timeout",
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
        """Create Lua script for mgba-qt screenshot capture"""
        lua_script = self.mgba_qt_dir / "screenshot_capture.lua"
        
        screenshots_per_second = 8
        total_frames = duration_seconds * 60
        screenshot_interval = 60 // screenshots_per_second
        
        script_content = f'''-- Screenshot capture for mgba-qt
-- Captures screenshots at regular intervals

local frameCount = 0
local screenshotCount = 0
local logFile = nil

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize on first frame
    if frameCount == 1 then
        logFile = io.open("{self.mgba_qt_dir.absolute()}/screenshot_log.txt", "w")
        if logFile then
            logFile:write("=== mgba-qt Screenshot Log ===\\n")
        end
    end
    
    -- Capture screenshot every {screenshot_interval} frames
    if frameCount % {screenshot_interval} == 0 then
        screenshotCount = screenshotCount + 1
        local screenshot = emu:takeScreenshot()
        local filename = "{self.screenshots_dir.absolute()}/mgba_qt_frame_" .. string.format("%05d", frameCount) .. ".png"
        screenshot:save(filename)
        
        if logFile then
            logFile:write(string.format("Frame %d: Screenshot saved to %s\\n", frameCount, filename))
            logFile:flush()
        end
    end
    
    -- Stop after {total_frames} frames ({duration_seconds} seconds)
    if frameCount >= {total_frames} then
        if logFile then
            logFile:write(string.format("\\n=== Summary ===\\n"))
            logFile:write(string.format("Total frames: %d\\n", frameCount))
            logFile:write(string.format("Screenshots captured: %d\\n", screenshotCount))
            logFile:close()
        end
        emu:stop()
    end
end)

print("mgba-qt screenshot capture script loaded")
'''
        
        lua_script.write_text(script_content)
        return lua_script
    
    def run_mgba_qt_capture(self, duration_seconds: int = 5) -> Dict:
        """Run mgba-qt with screenshot capture"""
        lua_script = self.create_mgba_qt_lua(duration_seconds)
        
        # Use simple_launch_mgba.py pattern
        cmd = [
            "/usr/local/bin/mgba-qt",
            str(self.rom_path),
            "--fastforward",
            "--script", str(lua_script),
        ]
        
        print(f"📸 Running mgba-qt screenshot capture (duration: {duration_seconds}s)...")
        start_time = time.time()
        
        try:
            # Run in background - mgba-qt is GUI app
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(self.output_dir)
            )
            
            # Wait for duration
            time.sleep(duration_seconds + 2)
            
            # Try to terminate gracefully
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                process.kill()
            
            elapsed = time.time() - start_time
            log_exists = (self.mgba_qt_dir / "screenshot_log.txt").exists()
            
            return {
                "success": log_exists,
                "elapsed": elapsed,
                "log_created": log_exists
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time
            }
    
    def analyze_combined_data(self, expected_mapping: Dict) -> Dict:
        """Analyze combined data from mgba-headless and mgba-qt"""
        results = {
            "mgba_headless": {},
            "mgba_qt": {},
            "combined_analysis": {}
        }
        
        # Analyze mgba-headless logs
        log_file = self.mgba_headless_dir / "comprehensive.log"
        if log_file.exists():
            with open(log_file) as f:
                log_content = f.read()
                results["mgba_headless"]["log_size"] = len(log_content)
                results["mgba_headless"]["log_lines"] = len(log_content.split("\n"))
        
        oam_json = self.mgba_headless_dir / "oam_writes.json"
        if oam_json.exists():
            try:
                with open(oam_json) as f:
                    oam_writes = json.load(f)
                    results["mgba_headless"]["oam_writes"] = len(oam_writes)
                    
                    # Analyze tile-to-palette mapping
                    tile_to_palette = defaultdict(list)
                    for write in oam_writes:
                        tile = write.get("tile", -1)
                        palette = write.get("palette", -1)
                        if tile >= 0:
                            tile_to_palette[tile].append(palette)
                    
                    # Find most common palette per tile
                    tile_palette_map = {}
                    for tile, palettes in tile_to_palette.items():
                        if palettes:
                            most_common = max(set(palettes), key=palettes.count)
                            confidence = palettes.count(most_common) / len(palettes)
                            tile_palette_map[tile] = {
                                "palette": most_common,
                                "confidence": confidence,
                                "total_writes": len(palettes)
                            }
                    
                    results["mgba_headless"]["tile_palette_map"] = tile_palette_map
            except Exception as e:
                results["mgba_headless"]["error"] = str(e)
        
        # Analyze mgba-qt screenshots
        screenshots = sorted(self.screenshots_dir.glob("mgba_qt_frame_*.png"))
        results["mgba_qt"]["screenshot_count"] = len(screenshots)
        
        # Compare with expected
        if "monster_palette_map" in expected_mapping:
            expected_tile_map = {}
            for monster_name, data in expected_mapping["monster_palette_map"].items():
                palette = data.get("palette", 0xFF)
                tile_range = data.get("tile_range", [])
                for tile in tile_range:
                    expected_tile_map[tile] = palette
            
            actual_map = results["mgba_headless"].get("tile_palette_map", {})
            
            matches = 0
            mismatches = 0
            missing = 0
            
            for tile, expected_pal in expected_tile_map.items():
                if tile in actual_map:
                    actual_pal = actual_map[tile].get("palette", 0xFF)
                    confidence = actual_map[tile].get("confidence", 0)
                    
                    if actual_pal == expected_pal and confidence > 0.8:
                        matches += 1
                    else:
                        mismatches += 1
                else:
                    missing += 1
            
            results["combined_analysis"] = {
                "matches": matches,
                "mismatches": mismatches,
                "missing": missing,
                "total_expected": len(expected_tile_map),
                "accuracy": matches / len(expected_tile_map) if expected_tile_map else 0
            }
        
        return results
    
    def generate_unified_report(self, expected_mapping: Dict) -> str:
        """Generate unified report combining all data sources"""
        analysis = self.analyze_combined_data(expected_mapping)
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("UNIFIED TEST REPORT - Combined Data Analysis")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # mgba-headless results
        report_lines.append("mgba-headless Results:")
        if analysis["mgba_headless"].get("oam_writes"):
            report_lines.append(f"  OAM writes logged: {analysis['mgba_headless']['oam_writes']}")
        if analysis["mgba_headless"].get("tile_palette_map"):
            report_lines.append(f"  Unique tiles with palette assignments: {len(analysis['mgba_headless']['tile_palette_map'])}")
        report_lines.append("")
        
        # mgba-qt results
        report_lines.append("mgba-qt Results:")
        report_lines.append(f"  Screenshots captured: {analysis['mgba_qt']['screenshot_count']}")
        report_lines.append("")
        
        # Combined analysis
        if analysis["combined_analysis"]:
            report_lines.append("Combined Analysis:")
            report_lines.append(f"  Matches: {analysis['combined_analysis']['matches']}")
            report_lines.append(f"  Mismatches: {analysis['combined_analysis']['mismatches']}")
            report_lines.append(f"  Missing: {analysis['combined_analysis']['missing']}")
            report_lines.append(f"  Accuracy: {analysis['combined_analysis']['accuracy']*100:.1f}%")
            report_lines.append("")
        
        report_lines.append("=" * 80)
        
        report_text = "\n".join(report_lines)
        
        # Save report
        report_file = self.analysis_dir / "unified_report.txt"
        report_file.write_text(report_text)
        
        return report_text

def main():
    import sys
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    output_dir = Path("test_output") / f"unified_{int(time.time())}"
    
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
    
    tester = UnifiedTestingSystem(rom_path, output_dir)
    
    print("🚀 Starting unified testing system...")
    print(f"   ROM: {rom_path}")
    print(f"   Output: {output_dir}")
    print()
    
    # Run mgba-headless
    print("1️⃣  Running mgba-headless...")
    headless_result = tester.run_mgba_headless(duration_seconds=5)
    if headless_result.get("success"):
        print("   ✅ mgba-headless completed")
    else:
        print(f"   ⚠️  mgba-headless: {headless_result.get('error', 'Unknown error')}")
    print()
    
    # Run mgba-qt screenshot capture
    print("2️⃣  Running mgba-qt screenshot capture...")
    qt_result = tester.run_mgba_qt_capture(duration_seconds=5)
    if qt_result.get("success"):
        print("   ✅ mgba-qt screenshots captured")
    else:
        print(f"   ⚠️  mgba-qt: {qt_result.get('error', 'Unknown error')}")
    print()
    
    # Generate unified report
    print("3️⃣  Generating unified report...")
    report = tester.generate_unified_report(expected_mapping)
    print(report)
    
    print(f"\n📊 Full results saved to: {output_dir}")

if __name__ == "__main__":
    main()

