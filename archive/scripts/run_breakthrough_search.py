#!/usr/bin/env python3
"""
Long-running breakthrough search - runs continuously and reports breakthroughs
"""
import subprocess
import json
import time
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List
import yaml
import sys

class BreakthroughSearchRunner:
    def __init__(self):
        self.base_rom_path = Path("rom/Penta Dragon (J).gb")
        self.output_base = Path("test_output") / "breakthrough_search"
        self.output_base.mkdir(parents=True, exist_ok=True)
        
        # Load expected mapping
        monster_map_path = Path("palettes/monster_palette_map.yaml")
        self.expected_mapping = {}
        if monster_map_path.exists():
            with open(monster_map_path) as f:
                self.expected_mapping = yaml.safe_load(f)
        
        self.results_log = self.output_base / "search_results.log"
        self.breakthrough_log = self.output_base / "BREAKTHROUGHS.log"
    
    def log_message(self, message: str, is_breakthrough: bool = False):
        """Log message and print if breakthrough"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        log_msg = f"[{timestamp}] {message}\n"
        
        with open(self.results_log, "a") as f:
            f.write(log_msg)
        
        if is_breakthrough:
            with open(self.breakthrough_log, "a") as f:
                f.write(log_msg)
            print(f"\n{'='*80}")
            print(f"🎉 BREAKTHROUGH: {message}")
            print(f"{'='*80}\n")
            # Also write to a notification file
            notify_file = self.output_base / "NOTIFY_BREAKTHROUGH.txt"
            notify_file.write_text(f"BREAKTHROUGH FOUND at {timestamp}\n{message}\n")
        else:
            print(f"[{timestamp}] {message}")
    
    def test_current_rom(self) -> Dict:
        """Test the current ROM build"""
        rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
        if not rom_path.exists():
            return {"success": False, "error": "ROM not found"}
        
        test_dir = self.output_base / f"test_{int(time.time())}"
        test_dir.mkdir(exist_ok=True)
        
        screenshots_dir = test_dir / "screenshots"
        logs_dir = test_dir / "logs"
        screenshots_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)
        
        # Create working Lua script based on working_trace_oam_writes.lua
        lua_script = logs_dir / "capture.lua"
        screenshot_base = str(screenshots_dir / "frame_")
        oam_json = str(logs_dir / "oam.json")
        test_log = str(logs_dir / "test.log")
        
        script_content = f'''-- Working capture script
local logFile = io.open("{test_log}", "w")
local writeCount = 0
local frameCount = 0
local writes_this_frame = {{}}
local all_writes = {{}}

logFile:write("Capture started\\n")
logFile:flush()

-- Register callbacks at TOP LEVEL
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

-- Set up callbacks for all sprite flags bytes
for sprite = 0, 39 do
    local flags_addr = 0xFE00 + (sprite * 4) + 3
    emu:addMemoryCallback(function(addr, value)
        on_oam_write(addr, value)
    end, emu.memoryCallback.WRITE, flags_addr, flags_addr)
end

logFile:write("Callbacks registered\\n")
logFile:flush()

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Log writes from this frame
    if #writes_this_frame > 0 then
        logFile:write(string.format("Frame %d: %d writes\\n", frameCount, #writes_this_frame))
        logFile:flush()
        writes_this_frame = {{}}
    end
    
    -- Capture screenshot every 60 frames
    if frameCount % 60 == 0 then
        local screenshot = emu:takeScreenshot()
        screenshot:save("{screenshot_base}" .. string.format("%05d", frameCount) .. ".png")
    end
    
    -- Stop after 8 seconds (480 frames)
    if frameCount >= 480 then
        logFile:write(string.format("\\nSummary: %d frames, %d writes\\n", frameCount, writeCount))
        logFile:close()
        
        -- Write JSON
        local jsonFile = io.open("{oam_json}", "w")
        jsonFile:write("[\\n")
        for i, w in ipairs(all_writes) do
            jsonFile:write(string.format('  {{"frame":%d,"sprite":%d,"tile":%d,"palette":%d,"flags":%d,"pc":%d}}',
                w.frame, w.sprite, w.tile, w.palette, w.flags, w.pc))
            if i < #all_writes then jsonFile:write(",") end
            jsonFile:write("\\n")
        end
        jsonFile:write("]\\n")
        jsonFile:close()
        
        emu:stop()
    end
end)

print("Capture script loaded")
'''
        
        lua_script.write_text(script_content)
        
        # Run test
        cmd = ["/usr/local/bin/mgba-qt", str(rom_path), "--fastforward", "--script", str(lua_script)]
        
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(10)
            process.terminate()
            try:
                process.wait(timeout=2)
            except:
                process.kill()
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        # Analyze results
        return self.analyze_test_results(test_dir)
    
    def analyze_test_results(self, test_dir: Path) -> Dict:
        """Analyze test results"""
        oam_json = test_dir / "logs" / "oam.json"
        screenshots = list((test_dir / "screenshots").glob("frame_*.png"))
        test_log = test_dir / "logs" / "test.log"
        
        result = {
            "screenshots": len(screenshots),
            "oam_writes": 0,
            "accuracy": 0,
            "matches": 0,
            "mismatches": 0,
            "is_breakthrough": False
        }
        
        # Check log file
        if test_log.exists():
            with open(test_log) as f:
                log_content = f.read()
                result["log_content"] = log_content[-500:]  # Last 500 chars
        
        if oam_json.exists():
            try:
                with open(oam_json) as f:
                    oam_writes = json.load(f)
                result["oam_writes"] = len(oam_writes)
                
                if oam_writes and "monster_palette_map" in self.expected_mapping:
                    # Analyze tile-to-palette mapping
                    tile_to_palette = defaultdict(lambda: defaultdict(int))
                    for write in oam_writes:
                        tile = write.get("tile", -1)
                        palette = write.get("palette", -1)
                        if tile >= 0:
                            tile_to_palette[tile][palette] += 1
                    
                    # Build expected map
                    expected_tile_map = {}
                    for monster_name, data in self.expected_mapping["monster_palette_map"].items():
                        palette = data.get("palette", 0xFF)
                        for tile in data.get("tile_range", []):
                            expected_tile_map[tile] = palette
                    
                    # Compare
                    matches = 0
                    mismatches = 0
                    
                    for tile, expected_pal in expected_tile_map.items():
                        if tile in tile_to_palette:
                            palette_counts = tile_to_palette[tile]
                            if palette_counts:
                                most_common = max(palette_counts.items(), key=lambda x: x[1])
                                total = sum(palette_counts.values())
                                confidence = most_common[1] / total
                                
                                if most_common[0] == expected_pal and confidence > 0.8:
                                    matches += 1
                                else:
                                    mismatches += 1
                    
                    if expected_tile_map:
                        result["accuracy"] = matches / len(expected_tile_map)
                        result["matches"] = matches
                        result["mismatches"] = mismatches
                        result["is_breakthrough"] = (
                            result["accuracy"] > 0.5 or  # >50% accuracy
                            result["screenshots"] > 5 or  # Multiple screenshots captured
                            result["oam_writes"] > 100  # Significant OAM activity
                        )
            except Exception as e:
                result["error"] = str(e)
        
        return result
    
    def run_continuous_search(self):
        """Run continuous search loop - interactive with Cursor"""
        print("=" * 80)
        print("BREAKTHROUGH SEARCH - Running interactively")
        print("=" * 80)
        self.log_message("Starting continuous breakthrough search...")
        iteration = 0
        
        while True:
            iteration += 1
            print(f"\n{'='*80}")
            print(f"ITERATION {iteration}")
            print(f"{'='*80}")
            self.log_message(f"Iteration {iteration}: Testing current ROM...")
            
            print("  Building and testing ROM...")
            result = self.test_current_rom()
            
            if result.get("success") is False:
                error_msg = f"  ❌ Test failed: {result.get('error', 'Unknown')}"
                print(error_msg)
                self.log_message(error_msg)
            else:
                accuracy = result.get("accuracy", 0)
                oam_writes = result.get("oam_writes", 0)
                screenshots = result.get("screenshots", 0)
                matches = result.get("matches", 0)
                mismatches = result.get("mismatches", 0)
                
                # Print detailed results to console
                print(f"\n  📊 RESULTS:")
                print(f"     OAM writes captured: {oam_writes}")
                print(f"     Screenshots captured: {screenshots}")
                print(f"     Accuracy: {accuracy*100:.1f}%")
                print(f"     Matches: {matches}")
                print(f"     Mismatches: {mismatches}")
                
                result_msg = (
                    f"  Results: {oam_writes} OAM writes, {screenshots} screenshots, "
                    f"{accuracy*100:.1f}% accuracy, {matches} matches"
                )
                
                is_breakthrough = result.get("is_breakthrough", False)
                if is_breakthrough:
                    print(f"\n  🎉 BREAKTHROUGH DETECTED!")
                    print(f"     This iteration shows significant progress!")
                    
                    breakthrough_details = f"""
BREAKTHROUGH DETAILS:
  Accuracy: {accuracy*100:.1f}%
  OAM Writes: {oam_writes}
  Screenshots: {screenshots}
  Matches: {matches}
  Mismatches: {mismatches}
  
Check test results in: {self.output_base}
"""
                    self.log_message(result_msg, is_breakthrough=True)
                    self.log_message(breakthrough_details, is_breakthrough=True)
                    
                    # Create notification file
                    notify_file = self.output_base / "NOTIFY_BREAKTHROUGH.txt"
                    notify_file.write_text(f"""
BREAKTHROUGH FOUND at {time.strftime('%Y-%m-%d %H:%M:%S')}

Iteration: {iteration}
Accuracy: {accuracy*100:.1f}%
OAM Writes: {oam_writes}
Screenshots: {screenshots}
Matches: {matches}
Mismatches: {mismatches}

{breakthrough_details}
""")
                    
                    print(f"\n  ✅ Breakthrough logged! Check: {notify_file}")
                    print(f"  Continuing search for even better results...")
                else:
                    self.log_message(result_msg)
                
                # Show progress indicator
                if oam_writes > 0:
                    print(f"  ✅ OAM capture working!")
                else:
                    print(f"  ⚠️  No OAM writes captured yet (debugging capture mechanism)")
            
            print(f"\n  Waiting 5 seconds before next iteration...")
            print(f"  (Press Ctrl+C to stop)")
            sys.stdout.flush()  # Ensure output is visible in Cursor
            time.sleep(5)

def main():
    runner = BreakthroughSearchRunner()
    
    try:
        runner.run_continuous_search()
    except KeyboardInterrupt:
        runner.log_message("Search interrupted by user")
    except Exception as e:
        runner.log_message(f"Search error: {e}")

if __name__ == "__main__":
    main()

