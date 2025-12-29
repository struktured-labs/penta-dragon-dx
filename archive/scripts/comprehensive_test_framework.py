#!/usr/bin/env python3
"""
Comprehensive Testing Framework for ROM Colorization
Combines screenshot analysis, mgba-headless, logging, and performance profiling
"""
import subprocess
import json
import time
import tempfile
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import yaml
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("⚠️  cv2 not available - screenshot analysis will be limited")

class ComprehensiveTester:
    def __init__(self, rom_path: Path, output_dir: Path):
        self.rom_path = rom_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories for organized output
        self.screenshots_dir = self.output_dir / "screenshots"
        self.logs_dir = self.output_dir / "logs"
        self.analysis_dir = self.output_dir / "analysis"
        self.curated_dir = self.output_dir / "curated_sprites"
        
        for d in [self.screenshots_dir, self.logs_dir, self.analysis_dir, self.curated_dir]:
            d.mkdir(exist_ok=True)
    
    def create_comprehensive_lua_script(self) -> Path:
        """Create Lua script that logs OAM, palettes, performance, and captures screenshots"""
        lua_script = self.logs_dir / "comprehensive_test.lua"
        
        script_content = f"""
-- Comprehensive testing script for ROM colorization
-- Logs OAM state, palette state, performance metrics, and captures screenshots

local logFile = io.open("{self.logs_dir}/comprehensive_test.log", "w")
local frameCount = 0
local startTime = emu:time()
local oamWrites = {{}}
local paletteWrites = {{}}
local performanceData = {{}}

-- Track OAM writes
emu:addMemoryCallback(function(addr, value)
    if addr >= 0xFE00 and addr < 0xFEA0 then
        local spriteIndex = math.floor((addr - 0xFE00) / 4)
        local offset = (addr - 0xFE00) % 4
        if offset == 3 then  -- Flags byte
            oamWrites[#oamWrites + 1] = {{
                frame = frameCount,
                sprite = spriteIndex,
                tile = memory.readbyte(addr - 1),
                palette = value & 0x07,
                flags = value,
                pc = emu:getRegister("PC")
            }}
        end
    end
end, emu.memoryCallbackType.write, 0xFE00, 0xFEA0)

-- Track palette writes
emu:addMemoryCallback(function(addr, value)
    if addr == 0xFF68 or addr == 0xFF69 or addr == 0xFF6A or addr == 0xFF6B then
        paletteWrites[#paletteWrites + 1] = {{
            frame = frameCount,
            register = string.format("0x%04X", addr),
            value = value,
            pc = emu:getRegister("PC")
        }}
    end
end, emu.memoryCallbackType.write, 0xFF68, 0xFF6B)

-- Main loop
emu:addFrameCallback(function()
    frameCount = frameCount + 1
    
    -- Capture screenshot every 60 frames
    if frameCount % 60 == 0 then
        local screenshot = emu:takeScreenshot()
        screenshot:save("{self.screenshots_dir}/frame_" .. string.format("%05d", frameCount) .. ".png")
    end
    
    -- Log performance every 10 frames
    if frameCount % 10 == 0 then
        local currentTime = emu:time()
        local elapsed = currentTime - startTime
        local fps = frameCount / elapsed
        performanceData[#performanceData + 1] = {{
            frame = frameCount,
            elapsed = elapsed,
            fps = fps
        }}
    end
    
    -- Log OAM state every 60 frames
    if frameCount % 60 == 0 then
        logFile:write(string.format("\\n=== Frame %d ===\\n", frameCount))
        
        -- Log all sprite OAM entries
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = memory.readbyte(oamBase)
            local x = memory.readbyte(oamBase + 1)
            local tile = memory.readbyte(oamBase + 2)
            local flags = memory.readbyte(oamBase + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 then  -- Visible sprite
                logFile:write(string.format("Sprite %2d: Y=%3d X=%3d Tile=%3d Palette=%d Flags=0x%02X\\n",
                    i, y, x, tile, palette, flags))
            end
        end
        
        -- Log OBJ palettes
        logFile:write("OBJ Palettes:\\n")
        for pal = 0, 7 do
            local palAddr = 0xFF6A
            memory.writebyte(0xFF6A, 0x80 | (pal * 8))
            local colors = {{}}
            for i = 0, 3 do
                local colorLow = memory.readbyte(0xFF6B)
                local colorHigh = memory.readbyte(0xFF6B)
                colors[i + 1] = colorLow | (colorHigh << 8)
            end
            logFile:write(string.format("  Palette %d: %04X %04X %04X %04X\\n",
                pal, colors[1], colors[2], colors[3], colors[4]))
        end
    end
    
    -- Stop after 5 seconds (300 frames at 60fps)
    if frameCount >= 300 then
        -- Write summary
        logFile:write(string.format("\\n=== Summary ===\\n"))
        logFile:write(string.format("Total frames: %d\\n", frameCount))
        logFile:write(string.format("OAM writes: %d\\n", #oamWrites))
        logFile:write(string.format("Palette writes: %d\\n", #paletteWrites))
        logFile:write(string.format("Average FPS: %.2f\\n", frameCount / (emu:time() - startTime)))
        
        -- Write OAM writes to JSON
        local oamFile = io.open("{self.logs_dir}/oam_writes.json", "w")
        oamFile:write(json.encode(oamWrites))
        oamFile:close()
        
        -- Write palette writes to JSON
        local palFile = io.open("{self.logs_dir}/palette_writes.json", "w")
        palFile:write(json.encode(paletteWrites))
        palFile:close()
        
        -- Write performance data to JSON
        local perfFile = io.open("{self.logs_dir}/performance.json", "w")
        perfFile:write(json.encode(performanceData))
        perfFile:close()
        
        logFile:close()
        emu:stop()
    end
end)

print("Comprehensive test script loaded")
"""
        
        lua_script.write_text(script_content)
        return lua_script
    
    def run_mgba_headless_test(self, duration_seconds: int = 5) -> Dict:
        """Run mgba-headless with comprehensive logging"""
        lua_script = self.create_comprehensive_lua_script()
        
        # mgba-headless command - check if it supports --script flag
        cmd = [
            "mgba-headless",
            str(self.rom_path),
            "--script", str(lua_script),
        ]
        
        print(f"🚀 Running mgba-headless test (duration: {duration_seconds}s)...")
        print(f"   Lua script: {lua_script}")
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
            
            # Check if log files were created (indicates success even if returncode != 0)
            log_exists = (self.logs_dir / "comprehensive_test.log").exists()
            
            return {
                "success": result.returncode == 0 or log_exists,
                "elapsed": elapsed,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "log_created": log_exists
            }
        except subprocess.TimeoutExpired:
            # Check if logs were created before timeout
            log_exists = (self.logs_dir / "comprehensive_test.log").exists()
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
    
    def analyze_screenshots(self, expected_sprites: Optional[Dict] = None) -> Dict:
        """Analyze screenshots for color correctness"""
        screenshots = sorted(self.screenshots_dir.glob("frame_*.png"))
        
        if not screenshots:
            return {"error": "No screenshots found"}
        
        results = {
            "total_screenshots": len(screenshots),
            "color_analysis": [],
            "sprite_detections": []
        }
        
        if not CV2_AVAILABLE:
            # Basic analysis without cv2
            for screenshot_path in screenshots:
                results["color_analysis"].append({
                    "screenshot": screenshot_path.name,
                    "note": "cv2 not available for detailed analysis"
                })
            return results
        
        for screenshot_path in screenshots:
            img = cv2.imread(str(screenshot_path))
            if img is None:
                continue
            
            # Convert to HSV for better color analysis
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            
            # Extract distinct colors
            img_reshaped = img.reshape(-1, 3)
            unique_colors = np.unique(img_reshaped, axis=0)
            
            # Count saturated colors (non-gray)
            saturated_mask = hsv[:, :, 1] > 50  # Saturation threshold
            saturated_colors = np.unique(img[saturated_mask].reshape(-1, 3), axis=0)
            
            results["color_analysis"].append({
                "screenshot": screenshot_path.name,
                "total_colors": len(unique_colors),
                "saturated_colors": len(saturated_colors),
                "distinct_colors": len(unique_colors)
            })
        
        return results
    
    def analyze_oam_logs(self) -> Dict:
        """Analyze OAM write logs to understand palette assignment patterns"""
        oam_file = self.logs_dir / "oam_writes.json"
        
        if not oam_file.exists():
            return {"error": "OAM writes log not found"}
        
        try:
            with open(oam_file) as f:
                oam_writes = json.load(f)
        except:
            return {"error": "Failed to parse OAM writes log"}
        
        # Group by tile ID
        tile_to_palette = defaultdict(list)
        sprite_to_palette = defaultdict(list)
        
        for write in oam_writes:
            tile = write.get("tile", -1)
            palette = write.get("palette", -1)
            sprite = write.get("sprite", -1)
            
            if tile >= 0:
                tile_to_palette[tile].append(palette)
            if sprite >= 0:
                sprite_to_palette[sprite].append(palette)
        
        # Find most common palette per tile
        tile_palette_map = {}
        for tile, palettes in tile_to_palette.items():
            if palettes:
                most_common = max(set(palettes), key=palettes.count)
                tile_palette_map[tile] = {
                    "palette": most_common,
                    "confidence": palettes.count(most_common) / len(palettes),
                    "total_writes": len(palettes)
                }
        
        return {
            "total_oam_writes": len(oam_writes),
            "tile_to_palette": tile_palette_map,
            "sprite_to_palette": dict(sprite_to_palette)
        }
    
    def analyze_performance(self) -> Dict:
        """Analyze performance metrics"""
        perf_file = self.logs_dir / "performance.json"
        
        if not perf_file.exists():
            return {"error": "Performance log not found"}
        
        try:
            with open(perf_file) as f:
                perf_data = json.load(f)
        except:
            return {"error": "Failed to parse performance log"}
        
        if not perf_data:
            return {"error": "No performance data"}
        
        fps_values = [p.get("fps", 0) for p in perf_data if p.get("fps", 0) > 0]
        
        if not fps_values:
            return {"error": "No valid FPS data"}
        
        if CV2_AVAILABLE:
            return {
                "average_fps": float(np.mean(fps_values)),
                "min_fps": float(np.min(fps_values)),
                "max_fps": float(np.max(fps_values)),
                "fps_std": float(np.std(fps_values)),
                "samples": len(fps_values)
            }
        else:
            # Basic stats without numpy
            avg = sum(fps_values) / len(fps_values)
            return {
                "average_fps": avg,
                "min_fps": min(fps_values),
                "max_fps": max(fps_values),
                "samples": len(fps_values)
            }
    
    def compare_with_expected(self, expected_mapping: Dict) -> Dict:
        """Compare actual palette assignments with expected from monster_palette_map.yaml"""
        oam_analysis = self.analyze_oam_logs()
        
        if "error" in oam_analysis:
            return {"error": oam_analysis["error"]}
        
        actual_tile_map = oam_analysis.get("tile_to_palette", {})
        expected_tile_map = {}
        
        # Load expected mapping
        if "monster_palette_map" in expected_mapping:
            for monster_name, data in expected_mapping["monster_palette_map"].items():
                palette = data.get("palette", 0xFF)
                tile_range = data.get("tile_range", [])
                for tile in tile_range:
                    expected_tile_map[tile] = palette
        
        # Compare
        matches = []
        mismatches = []
        missing = []
        
        for tile, expected_pal in expected_tile_map.items():
            if tile in actual_tile_map:
                actual_pal = actual_tile_map[tile].get("palette", 0xFF)
                confidence = actual_tile_map[tile].get("confidence", 0)
                
                if actual_pal == expected_pal and confidence > 0.8:
                    matches.append({
                        "tile": tile,
                        "palette": actual_pal,
                        "confidence": confidence
                    })
                else:
                    mismatches.append({
                        "tile": tile,
                        "expected": expected_pal,
                        "actual": actual_pal,
                        "confidence": confidence
                    })
            else:
                missing.append({"tile": tile, "expected": expected_pal})
        
        return {
            "matches": len(matches),
            "mismatches": len(mismatches),
            "missing": len(missing),
            "match_details": matches,
            "mismatch_details": mismatches,
            "missing_details": missing,
            "accuracy": len(matches) / len(expected_tile_map) if expected_tile_map else 0
        }
    
    def generate_report(self, expected_mapping: Dict) -> str:
        """Generate comprehensive test report"""
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("COMPREHENSIVE TEST REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Performance analysis
        perf = self.analyze_performance()
        if "error" not in perf:
            report_lines.append("PERFORMANCE METRICS:")
            report_lines.append(f"  Average FPS: {perf.get('average_fps', 0):.2f}")
            report_lines.append(f"  Min FPS: {perf.get('min_fps', 0):.2f}")
            report_lines.append(f"  Max FPS: {perf.get('max_fps', 0):.2f}")
            if CV2_AVAILABLE:
                report_lines.append(f"  FPS Std Dev: {perf.get('fps_std', 0):.2f}")
            report_lines.append("")
        
        # Screenshot analysis
        screenshots = self.analyze_screenshots()
        if "error" not in screenshots:
            report_lines.append("SCREENSHOT ANALYSIS:")
            report_lines.append(f"  Total screenshots: {screenshots['total_screenshots']}")
            if screenshots['color_analysis'] and CV2_AVAILABLE:
                distinct_colors = [a.get('distinct_colors', 0) for a in screenshots['color_analysis'] if 'distinct_colors' in a]
                if distinct_colors:
                    avg_colors = np.mean(distinct_colors)
                    report_lines.append(f"  Average distinct colors: {avg_colors:.1f}")
            report_lines.append("")
        
        # OAM analysis
        oam = self.analyze_oam_logs()
        if "error" not in oam:
            report_lines.append("OAM ANALYSIS:")
            report_lines.append(f"  Total OAM writes: {oam['total_oam_writes']}")
            report_lines.append(f"  Unique tiles with palette assignments: {len(oam['tile_to_palette'])}")
            report_lines.append("")
        
        # Comparison with expected
        comparison = self.compare_with_expected(expected_mapping)
        if "error" not in comparison:
            report_lines.append("EXPECTED vs ACTUAL COMPARISON:")
            report_lines.append(f"  Matches: {comparison['matches']}")
            report_lines.append(f"  Mismatches: {comparison['mismatches']}")
            report_lines.append(f"  Missing: {comparison['missing']}")
            report_lines.append(f"  Accuracy: {comparison['accuracy']*100:.1f}%")
            report_lines.append("")
            
            if comparison['mismatch_details']:
                report_lines.append("MISMATCHES:")
                for m in comparison['mismatch_details'][:10]:  # Show first 10
                    report_lines.append(f"  Tile {m['tile']}: expected palette {m['expected']}, got {m['actual']} (confidence: {m['confidence']:.2f})")
                report_lines.append("")
        
        report_lines.append("=" * 80)
        
        report_text = "\n".join(report_lines)
        
        # Save report
        report_file = self.analysis_dir / "test_report.txt"
        report_file.write_text(report_text)
        
        return report_text

def main():
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: comprehensive_test_framework.py <rom_path> [output_dir]")
        sys.exit(1)
    
    rom_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("test_output")
    
    if not rom_path.exists():
        print(f"❌ ROM not found: {rom_path}")
        sys.exit(1)
    
    # Load expected mapping
    monster_map_path = Path("palettes/monster_palette_map.yaml")
    expected_mapping = {}
    if monster_map_path.exists():
        with open(monster_map_path) as f:
            expected_mapping = yaml.safe_load(f)
    
    tester = ComprehensiveTester(rom_path, output_dir)
    
    print("🧪 Starting comprehensive test...")
    
    # Run mgba-headless test
    test_result = tester.run_mgba_headless_test(duration_seconds=5)
    
    if not test_result.get("success"):
        print(f"❌ Test failed: {test_result.get('error', 'Unknown error')}")
        return
    
    print("✅ Test completed, analyzing results...")
    
    # Generate report
    report = tester.generate_report(expected_mapping)
    print(report)
    
    print(f"\n📊 Full results saved to: {output_dir}")

if __name__ == "__main__":
    main()

