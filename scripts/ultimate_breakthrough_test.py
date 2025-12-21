#!/usr/bin/env python3
"""
ULTIMATE BREAKTHROUGH TESTING SYSTEM
Combines: mgba-headless + mgba-qt + GDB + comprehensive logging
This is THE system that will give us breakthrough insights!
"""
import subprocess
import json
import time
import shutil
import socket
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
import yaml

class UltimateBreakthroughTester:
    def __init__(self, rom_path: Path, output_dir: Path):
        self.rom_path = rom_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Subdirectories
        self.screenshots_dir = self.output_dir / "screenshots"
        self.logs_dir = self.output_dir / "logs"
        self.analysis_dir = self.output_dir / "analysis"
        self.gdb_dir = self.output_dir / "gdb"
        
        for d in [self.screenshots_dir, self.logs_dir, self.analysis_dir, self.gdb_dir]:
            d.mkdir(exist_ok=True)
    
    def create_mgba_qt_comprehensive_lua(self) -> Path:
        """Create comprehensive Lua script for mgba-qt (screenshots + OAM + palettes)"""
        lua_script = self.logs_dir / "qt_comprehensive.lua"
        
        screenshot_base = str(self.screenshots_dir / "qt_frame_")
        oam_log_path = str(self.logs_dir / "qt_oam_trace.log")
        palette_log_path = str(self.logs_dir / "qt_palette_trace.log")
        
        script_content = f'''-- Comprehensive mgba-qt logging: Screenshots + OAM + Palettes
local frameCount = 0
local screenshotCount = 0
local oamLogFile = nil
local paletteLogFile = nil
local oamWrites = {{}}
local paletteWrites = {{}}

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Initialize on first frame
    if frameCount == 1 then
        oamLogFile = io.open("{oam_log_path}", "w")
        if oamLogFile then
            oamLogFile:write("=== mgba-qt OAM Write Trace ===\\n")
        end
        
        paletteLogFile = io.open("{palette_log_path}", "w")
        if paletteLogFile then
            paletteLogFile:write("=== mgba-qt Palette Write Trace ===\\n")
        end
        
        -- Set up OAM write callbacks (flags bytes)
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
                
                if oamLogFile then
                    oamLogFile:write(string.format("Frame %d: Sprite[%d] Tile=%d Palette=%d PC=0x%04X\\n",
                        frameCount, spriteIndex, tile, value & 0x07, pc))
                    oamLogFile:flush()
                end
            end, emu.memoryCallback.WRITE, flagsAddr, flagsAddr)
        end
        
        -- Set up palette write callbacks
        emu:addMemoryCallback(function(addr, value)
            local pc = emu:getRegister("PC")
            table.insert(paletteWrites, {{
                frame = frameCount,
                register = string.format("0x%04X", addr),
                value = value,
                pc = pc
            }})
            
            if paletteLogFile then
                paletteLogFile:write(string.format("Frame %d: %s = 0x%02X PC=0x%04X\\n",
                    frameCount, string.format("0x%04X", addr), value, pc))
                paletteLogFile:flush()
            end
        end, emu.memoryCallback.WRITE, 0xFF68, 0xFF6B)
    end
    
    -- Capture screenshot every 60 frames (~1 per second)
    if frameCount % 60 == 0 then
        screenshotCount = screenshotCount + 1
        local screenshot = emu:takeScreenshot()
        screenshot:save("{screenshot_base}" .. string.format("%05d", frameCount) .. ".png")
        
        -- Log OAM state with screenshot
        if oamLogFile then
            oamLogFile:write(string.format("\\n=== Screenshot %d (Frame %d) OAM State ===\\n", screenshotCount, frameCount))
            for i = 0, 39 do
                local oamBase = 0xFE00 + (i * 4)
                local y = emu:read8(oamBase)
                local x = emu:read8(oamBase + 1)
                local tile = emu:read8(oamBase + 2)
                local flags = emu:read8(oamBase + 3)
                local palette = flags & 0x07
                
                if y > 0 and y < 144 then
                    oamLogFile:write(string.format("Sprite %2d: Tile=%3d Palette=%d Pos=(%3d,%3d)\\n",
                        i, tile, palette, x, y))
                end
            end
            oamLogFile:flush()
        end
    end
    
    -- Stop after 10 seconds (600 frames at 60fps) - give sprites time to appear
    if frameCount >= 600 then
        -- Write JSON summaries
        local oamJsonFile = io.open("{self.logs_dir / 'qt_oam_writes.json'}", "w")
        oamJsonFile:write("[\\n")
        for i, write in ipairs(oamWrites) do
            oamJsonFile:write(string.format('  {{"frame":%d,"sprite":%d,"tile":%d,"palette":%d,"flags":%d,"pc":%d}}',
                write.frame, write.sprite, write.tile, write.palette, write.flags, write.pc))
            if i < #oamWrites then oamJsonFile:write(",") end
            oamJsonFile:write("\\n")
        end
        oamJsonFile:write("]\\n")
        oamJsonFile:close()
        
        if oamLogFile then
            oamLogFile:write(string.format("\\n=== Summary ===\\n"))
            oamLogFile:write(string.format("Total OAM writes: %d\\n", #oamWrites))
            oamLogFile:close()
        end
        
        if paletteLogFile then
            paletteLogFile:write(string.format("\\n=== Summary ===\\n"))
            paletteLogFile:write(string.format("Total palette writes: %d\\n", #paletteWrites))
            paletteLogFile:close()
        end
        
        emu:stop()
    end
end)

print("mgba-qt comprehensive logging script loaded")
'''
        
        lua_script.write_text(script_content)
        return lua_script
    
    def run_mgba_qt_comprehensive(self, duration_seconds: int = 5) -> Dict:
        """Run mgba-qt with comprehensive logging"""
        lua_script = self.create_mgba_qt_comprehensive_lua()
        
        cmd = [
            "/usr/local/bin/mgba-qt",
            str(self.rom_path),
            "--fastforward",
            "--script", str(lua_script),
        ]
        
        print(f"📸 Running mgba-qt comprehensive logging (duration: {duration_seconds}s)...")
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            time.sleep(duration_seconds + 3)  # Extra time for script to finish
            
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                process.kill()
            
            elapsed = time.time() - start_time
            oam_log_exists = (self.logs_dir / "qt_oam_trace.log").exists()
            screenshots = len(list(self.screenshots_dir.glob("qt_frame_*.png")))
            
            return {
                "success": oam_log_exists or screenshots > 0,
                "elapsed": elapsed,
                "oam_log_created": oam_log_exists,
                "screenshots": screenshots
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time
            }
    
    def run_mgba_headless_basic(self, duration_seconds: int = 5) -> Dict:
        """Run mgba-headless for basic execution logging"""
        log_file = self.logs_dir / "headless_execution.log"
        
        cmd = [
            "mgba-headless",
            str(self.rom_path),
            "--frameskip", "0",
        ]
        
        print(f"🔍 Running mgba-headless basic execution (duration: {duration_seconds}s)...")
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 2,
            )
            
            elapsed = time.time() - start_time
            
            # Save output
            with open(log_file, "w") as f:
                f.write("=== mgba-headless Execution Log ===\n")
                f.write(f"Return code: {result.returncode}\n")
                f.write(f"\n--- STDOUT ---\n")
                f.write(result.stdout)
                f.write(f"\n--- STDERR ---\n")
                f.write(result.stderr)
            
            return {
                "success": True,
                "elapsed": elapsed,
                "returncode": result.returncode,
                "stdout_lines": len(result.stdout.split("\n")),
                "stderr_lines": len(result.stderr.split("\n"))
            }
        except subprocess.TimeoutExpired:
            return {
                "success": True,  # Timeout is expected
                "error": "Timeout (expected)",
                "elapsed": time.time() - start_time
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time
            }
    
    def run_gdb_session(self, duration_seconds: int = 5) -> Dict:
        """Run GDB debugging session with mgba"""
        gdb_script = self.gdb_dir / "gdb_commands.txt"
        gdb_log = self.gdb_dir / "gdb_session.log"
        
        # Create GDB commands
        gdb_commands = f'''set logging file {gdb_log}
set logging on
target remote localhost:2345
info registers
break *0x0824
continue
info registers
x/10i $pc
continue
info registers
x/10i $pc
continue
info registers
x/10i $pc
set logging off
quit
'''
        
        gdb_script.write_text(gdb_commands)
        
        # Start mgba with GDB
        print(f"🐛 Starting GDB debugging session (duration: {duration_seconds}s)...")
        
        mgba_cmd = [
            "mgba-headless",
            str(self.rom_path),
            "-g",  # Enable GDB
        ]
        
        mgba_process = None
        gdb_process = None
        
        try:
            # Start mgba with GDB
            mgba_process = subprocess.Popen(
                mgba_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            # Wait for GDB server to be ready
            time.sleep(1)
            
            # Run GDB
            gdb_cmd = [
                "gdb",
                "-batch",
                "-x", str(gdb_script),
            ]
            
            gdb_process = subprocess.run(
                gdb_cmd,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 2,
            )
            
            # Cleanup
            if mgba_process:
                mgba_process.terminate()
                try:
                    mgba_process.wait(timeout=2)
                except:
                    mgba_process.kill()
            
            gdb_log_exists = gdb_log.exists()
            
            return {
                "success": gdb_log_exists,
                "gdb_returncode": gdb_process.returncode,
                "log_created": gdb_log_exists
            }
        except Exception as e:
            if mgba_process:
                mgba_process.kill()
            return {
                "success": False,
                "error": str(e)
            }
    
    def analyze_all_data(self, expected_mapping: Dict) -> Dict:
        """Analyze ALL data sources together"""
        results = {
            "mgba_qt": {},
            "mgba_headless": {},
            "gdb": {},
            "combined_insights": {}
        }
        
        # Analyze mgba-qt OAM data
        oam_json = self.logs_dir / "qt_oam_writes.json"
        if oam_json.exists():
            try:
                with open(oam_json) as f:
                    oam_writes = json.load(f)
                    results["mgba_qt"]["total_oam_writes"] = len(oam_writes)
                    
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
                                "unique_pcs": len(set(tile_to_pc[tile])),
                                "pc_samples": list(set(tile_to_pc[tile]))[:5]  # First 5 unique PCs
                            }
                    
                    results["mgba_qt"]["tile_palette_map"] = tile_palette_map
            except Exception as e:
                results["mgba_qt"]["error"] = str(e)
        
        # Analyze mgba-qt screenshots
        screenshots = sorted(self.screenshots_dir.glob("qt_frame_*.png"))
        results["mgba_qt"]["screenshot_count"] = len(screenshots)
        
        # Analyze headless execution
        headless_log = self.logs_dir / "headless_execution.log"
        if headless_log.exists():
            with open(headless_log) as f:
                content = f.read()
                results["mgba_headless"]["log_size"] = len(content)
                results["mgba_headless"]["has_errors"] = "error" in content.lower() or "Error" in content
        
        # Analyze GDB session
        gdb_log = self.gdb_dir / "gdb_session.log"
        if gdb_log.exists():
            with open(gdb_log) as f:
                content = f.read()
                results["gdb"]["log_size"] = len(content)
                results["gdb"]["breakpoints_hit"] = content.count("Breakpoint")
                results["gdb"]["registers_logged"] = content.count("info registers")
        
        # Combined insights
        if "monster_palette_map" in expected_mapping:
            expected_tile_map = {}
            for monster_name, data in expected_mapping["monster_palette_map"].items():
                palette = data.get("palette", 0xFF)
                tile_range = data.get("tile_range", [])
                for tile in tile_range:
                    expected_tile_map[tile] = palette
            
            actual_map = results["mgba_qt"].get("tile_palette_map", {})
            
            matches = []
            mismatches = []
            missing = []
            
            for tile, expected_pal in expected_tile_map.items():
                if tile in actual_map:
                    actual_data = actual_map[tile]
                    actual_pal = actual_data.get("palette", 0xFF)
                    confidence = actual_data.get("confidence", 0)
                    
                    if actual_pal == expected_pal and confidence > 0.8:
                        matches.append({
                            "tile": tile,
                            "palette": actual_pal,
                            "confidence": confidence,
                            "pc_samples": actual_data.get("pc_samples", [])
                        })
                    else:
                        mismatches.append({
                            "tile": tile,
                            "expected": expected_pal,
                            "actual": actual_pal,
                            "confidence": confidence,
                            "pc_samples": actual_data.get("pc_samples", [])
                        })
                else:
                    missing.append({"tile": tile, "expected": expected_pal})
            
            results["combined_insights"] = {
                "matches": len(matches),
                "mismatches": len(mismatches),
                "missing": len(missing),
                "accuracy": len(matches) / len(expected_tile_map) if expected_tile_map else 0,
                "match_details": matches[:10],
                "mismatch_details": mismatches[:10],
                "missing_details": missing[:10]
            }
        
        return results
    
    def generate_ultimate_report(self, expected_mapping: Dict) -> str:
        """Generate ultimate breakthrough report"""
        analysis = self.analyze_all_data(expected_mapping)
        
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("ULTIMATE BREAKTHROUGH TEST REPORT")
        report_lines.append("Combining: mgba-headless + mgba-qt + GDB + Logs")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # mgba-qt results
        report_lines.append("📸 mgba-qt Results:")
        if analysis["mgba_qt"].get("total_oam_writes"):
            report_lines.append(f"  OAM writes logged: {analysis['mgba_qt']['total_oam_writes']}")
        if analysis["mgba_qt"].get("screenshot_count"):
            report_lines.append(f"  Screenshots captured: {analysis['mgba_qt']['screenshot_count']}")
        if analysis["mgba_qt"].get("tile_palette_map"):
            report_lines.append(f"  Unique tiles tracked: {len(analysis['mgba_qt']['tile_palette_map'])}")
        report_lines.append("")
        
        # mgba-headless results
        report_lines.append("🔍 mgba-headless Results:")
        if analysis["mgba_headless"].get("log_size"):
            report_lines.append(f"  Execution log size: {analysis['mgba_headless']['log_size']} bytes")
        if analysis["mgba_headless"].get("has_errors"):
            report_lines.append(f"  Has errors: {analysis['mgba_headless']['has_errors']}")
        report_lines.append("")
        
        # GDB results
        report_lines.append("🐛 GDB Results:")
        if analysis["gdb"].get("log_size"):
            report_lines.append(f"  Session log size: {analysis['gdb']['log_size']} bytes")
        if analysis["gdb"].get("breakpoints_hit"):
            report_lines.append(f"  Breakpoints hit: {analysis['gdb']['breakpoints_hit']}")
        report_lines.append("")
        
        # Combined insights
        if analysis["combined_insights"]:
            report_lines.append("💡 BREAKTHROUGH INSIGHTS:")
            report_lines.append(f"  ✅ Matches: {analysis['combined_insights']['matches']}")
            report_lines.append(f"  ❌ Mismatches: {analysis['combined_insights']['mismatches']}")
            report_lines.append(f"  ⚠️  Missing: {analysis['combined_insights']['missing']}")
            report_lines.append(f"  📊 Accuracy: {analysis['combined_insights']['accuracy']*100:.1f}%")
            report_lines.append("")
            
            if analysis["combined_insights"]["mismatch_details"]:
                report_lines.append("Mismatches (first 10):")
                for m in analysis["combined_insights"]["mismatch_details"]:
                    pcs = ", ".join([f"0x{pc:04X}" for pc in m.get("pc_samples", [])[:3]])
                    report_lines.append(f"  Tile {m['tile']}: expected palette {m['expected']}, got {m['actual']} (confidence: {m['confidence']:.2f}, PCs: {pcs})")
                report_lines.append("")
        
        report_lines.append("=" * 80)
        
        report_text = "\n".join(report_lines)
        
        # Save report
        report_file = self.analysis_dir / "ultimate_report.txt"
        report_file.write_text(report_text)
        
        # Save JSON
        json_file = self.analysis_dir / "ultimate_analysis.json"
        with open(json_file, "w") as f:
            json.dump(analysis, f, indent=2)
        
        return report_text

def main():
    import sys
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    output_dir = Path("test_output") / f"ultimate_{int(time.time())}"
    
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
    
    tester = UltimateBreakthroughTester(rom_path, output_dir)
    
    print("🚀 Starting ULTIMATE BREAKTHROUGH TESTING SYSTEM!")
    print(f"   ROM: {rom_path}")
    print(f"   Output: {output_dir}")
    print(f"   Tools: mgba-headless + mgba-qt + GDB + Logs")
    print()
    
    # Run mgba-qt comprehensive logging
    print("1️⃣  Running mgba-qt comprehensive logging...")
    qt_result = tester.run_mgba_qt_comprehensive(duration_seconds=10)
    if qt_result.get("success"):
        print(f"   ✅ mgba-qt completed ({qt_result.get('screenshots', 0)} screenshots, OAM log: {qt_result.get('oam_log_created', False)})")
    else:
        print(f"   ⚠️  mgba-qt: {qt_result.get('error', 'Unknown')}")
    print()
    
    # Run mgba-headless basic execution
    print("2️⃣  Running mgba-headless basic execution...")
    headless_result = tester.run_mgba_headless_basic(duration_seconds=3)
    if headless_result.get("success"):
        print(f"   ✅ mgba-headless completed")
    else:
        print(f"   ⚠️  mgba-headless: {headless_result.get('error', 'Unknown')}")
    print()
    
    # Run GDB session
    print("3️⃣  Running GDB debugging session...")
    gdb_result = tester.run_gdb_session(duration_seconds=3)
    if gdb_result.get("success"):
        print(f"   ✅ GDB session completed")
    else:
        print(f"   ⚠️  GDB: {gdb_result.get('error', 'Unknown')}")
    print()
    
    # Generate ultimate report
    print("4️⃣  Generating ultimate breakthrough report...")
    report = tester.generate_ultimate_report(expected_mapping)
    print(report)
    
    print(f"\n📊 Full results saved to: {output_dir}")
    print(f"   📄 Report: {output_dir / 'analysis' / 'ultimate_report.txt'}")
    print(f"   📊 JSON: {output_dir / 'analysis' / 'ultimate_analysis.json'}")
    print(f"   📸 Screenshots: {output_dir / 'screenshots'}")
    print(f"   📝 Logs: {output_dir / 'logs'}")

if __name__ == "__main__":
    main()

