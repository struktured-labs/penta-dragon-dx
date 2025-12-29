#!/usr/bin/env python3
"""
Deep Search Automation - Brute force different injection strategies
Only reports back when breakthrough is found
"""
import subprocess
import json
import time
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

class DeepSearchAutomation:
    def __init__(self, rom_path: Path, output_dir: Path):
        self.rom_path = rom_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.screenshots_dir = self.output_dir / "screenshots"
        self.logs_dir = self.output_dir / "logs"
        self.results_dir = self.output_dir / "results"
        
        for d in [self.screenshots_dir, self.logs_dir, self.results_dir]:
            d.mkdir(exist_ok=True)
    
    def create_working_sprite_capture_lua(self) -> Path:
        """Create working Lua script that actually captures OAM writes"""
        lua_script = self.logs_dir / "sprite_capture.lua"
        
        screenshot_base = str(self.screenshots_dir / "sprite_frame_")
        oam_log = str(self.logs_dir / "oam_capture.log")
        oam_json = str(self.logs_dir / "oam_capture.json")
        
        script_content = f'''-- Working sprite capture - based on working_trace_oam_writes.lua
-- CRITICAL: Register callbacks at TOP LEVEL, not inside frame callback!

local logFile = nil
local writeCount = 0
local frameCount = 0
local writes_this_frame = {{}}
local all_writes = {{}}

-- Initialize log file immediately
logFile = io.open("{oam_log}", "w")
logFile:write("=== Sprite OAM Capture ===\\n")
logFile:write("Callbacks registered at top level\\n")
logFile:flush()

-- Track OAM writes by monitoring flags bytes
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

-- CRITICAL: Set up memory callbacks at TOP LEVEL (before frame callback)
-- This is the key difference from previous attempts!
for sprite = 0, 39 do
    local flags_addr = 0xFE00 + (sprite * 4) + 3
    emu:addMemoryCallback(function(addr, value)
        on_oam_write(addr, value)
    end, emu.memoryCallback.WRITE, flags_addr, flags_addr)
end

logFile:write("All 40 sprite callbacks registered\\n")
logFile:flush()

-- Frame callback
callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    -- Log writes from this frame
    if #writes_this_frame > 0 then
        logFile:write(string.format("\\n--- Frame %d ---\\n", frameCount))
        for _, write in ipairs(writes_this_frame) do
            logFile:write(string.format("Sprite[%d]: Tile=%d Palette=%d PC=0x%04X\\n",
                write.sprite, write.tile, write.palette, write.pc))
        end
        logFile:flush()
        writes_this_frame = {{}}
    end
    
    -- Capture screenshot every 60 frames (focus on sprite frames)
    if frameCount % 60 == 0 then
        local screenshot = emu:takeScreenshot()
        screenshot:save("{screenshot_base}" .. string.format("%05d", frameCount) .. ".png")
        
        -- Log current OAM state
        logFile:write(string.format("\\n=== Frame %d OAM State ===\\n", frameCount))
        local sprite_count = 0
        for i = 0, 39 do
            local oamBase = 0xFE00 + (i * 4)
            local y = emu:read8(oamBase)
            local x = emu:read8(oamBase + 1)
            local tile = emu:read8(oamBase + 2)
            local flags = emu:read8(oamBase + 3)
            local palette = flags & 0x07
            
            if y > 0 and y < 144 and x > 0 and x < 168 then
                sprite_count = sprite_count + 1
                logFile:write(string.format("Sprite %2d: Tile=%3d Palette=%d Pos=(%3d,%3d)\\n",
                    i, tile, palette, x, y))
            end
        end
        logFile:write(string.format("Visible sprites: %d\\n", sprite_count))
        logFile:flush()
    end
    
    -- Stop after 8 seconds (480 frames) - enough for sprites to appear
    if frameCount >= 480 then
        logFile:write(string.format("\\n=== Summary ===\\n"))
        logFile:write(string.format("Total frames: %d\\n", frameCount))
        logFile:write(string.format("Total OAM writes: %d\\n", writeCount))
        logFile:close()
        
        -- Write JSON
        local jsonFile = io.open("{oam_json}", "w")
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

print("Sprite capture script loaded - will capture for 8 seconds")
'''
        
        lua_script.write_text(script_content)
        return lua_script
    
    def run_sprite_capture(self) -> Dict:
        """Run sprite capture and return results"""
        lua_script = self.create_working_sprite_capture_lua()
        
        cmd = [
            "/usr/local/bin/mgba-qt",
            str(self.rom_path),
            "--fastforward",
            "--script", str(lua_script),
        ]
        
        start_time = time.time()
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            time.sleep(10)  # Wait for script to complete
            
            try:
                process.terminate()
                process.wait(timeout=2)
            except:
                process.kill()
            
            elapsed = time.time() - start_time
            
            # Check results
            oam_json = self.logs_dir / "oam_capture.json"
            screenshots = list(self.screenshots_dir.glob("sprite_frame_*.png"))
            
            oam_writes = []
            if oam_json.exists():
                try:
                    with open(oam_json) as f:
                        oam_writes = json.load(f)
                except:
                    pass
            
            return {
                "success": len(oam_writes) > 0 or len(screenshots) > 0,
                "elapsed": elapsed,
                "oam_writes": len(oam_writes),
                "screenshots": len(screenshots),
                "oam_data": oam_writes
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": time.time() - start_time
            }
    
    def analyze_sprite_colors_from_screenshots(self) -> Dict:
        """Analyze sprite colors from screenshots - focus on sprites, not title"""
        screenshots = sorted(self.screenshots_dir.glob("sprite_frame_*.png"))
        
        if not screenshots:
            return {"error": "No screenshots"}
        
        if not CV2_AVAILABLE:
            return {"error": "cv2 not available", "screenshot_count": len(screenshots)}
        
        sprite_color_analysis = []
        
        for screenshot_path in screenshots:
            img = cv2.imread(str(screenshot_path))
            if img is None:
                continue
            
            # Focus on center area where sprites appear (not title screen)
            h, w = img.shape[:2]
            center_y_start = h // 4
            center_y_end = 3 * h // 4
            center_x_start = w // 4
            center_x_end = 3 * w // 4
            
            center_region = img[center_y_start:center_y_end, center_x_start:center_x_end]
            
            # Extract distinct colors from center region
            pixels = center_region.reshape(-1, 3)
            unique_colors = np.unique(pixels, axis=0)
            
            # Count non-black colors
            non_black = pixels[np.any(pixels > 20, axis=1)]
            if len(non_black) > 0:
                unique_non_black = np.unique(non_black, axis=0)
                
                sprite_color_analysis.append({
                    "screenshot": screenshot_path.name,
                    "total_colors": len(unique_colors),
                    "sprite_colors": len(unique_non_black),
                    "distinct_colors": len(unique_non_black)
                })
        
        if not sprite_color_analysis:
            return {"error": "No valid sprite analysis"}
        
        avg_colors = np.mean([a["distinct_colors"] for a in sprite_color_analysis])
        
        return {
            "screenshot_count": len(sprite_color_analysis),
            "average_distinct_colors": avg_colors,
            "analysis": sprite_color_analysis
        }
    
    def analyze_oam_tile_palette_mapping(self, expected_mapping: Dict) -> Dict:
        """Analyze OAM data to find tile-to-palette mapping"""
        oam_json = self.logs_dir / "oam_capture.json"
        
        if not oam_json.exists():
            return {"error": "OAM JSON not found"}
        
        try:
            with open(oam_json) as f:
                oam_writes = json.load(f)
        except Exception as e:
            return {"error": f"Failed to parse OAM JSON: {e}"}
        
        if not oam_writes:
            return {"error": "No OAM writes captured"}
        
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
        
        # Compare with expected
        if "monster_palette_map" in expected_mapping:
            expected_tile_map = {}
            for monster_name, data in expected_mapping["monster_palette_map"].items():
                palette = data.get("palette", 0xFF)
                tile_range = data.get("tile_range", [])
                for tile in tile_range:
                    expected_tile_map[tile] = palette
            
            matches = 0
            mismatches = 0
            
            for tile, expected_pal in expected_tile_map.items():
                if tile in tile_palette_map:
                    actual_pal = tile_palette_map[tile].get("palette", 0xFF)
                    confidence = tile_palette_map[tile].get("confidence", 0)
                    
                    if actual_pal == expected_pal and confidence > 0.8:
                        matches += 1
                    else:
                        mismatches += 1
            
            accuracy = matches / len(expected_tile_map) if expected_tile_map else 0
            
            return {
                "total_oam_writes": len(oam_writes),
                "unique_tiles": len(tile_palette_map),
                "tile_palette_map": tile_palette_map,
                "matches": matches,
                "mismatches": mismatches,
                "accuracy": accuracy,
                "is_breakthrough": accuracy > 0.5  # Consider >50% accuracy a breakthrough
            }
        
        return {
            "total_oam_writes": len(oam_writes),
            "unique_tiles": len(tile_palette_map),
            "tile_palette_map": tile_palette_map
        }
    
    def test_injection_strategy(self, strategy_name: str, strategy_func) -> Dict:
        """Test a specific injection strategy"""
        print(f"Testing strategy: {strategy_name}")
        
        # Build ROM with this strategy
        result = strategy_func()
        if not result.get("success"):
            return {"success": False, "error": "ROM build failed"}
        
        # Run sprite capture
        capture_result = self.run_sprite_capture()
        if not capture_result.get("success"):
            return {"success": False, "error": "Capture failed"}
        
        # Analyze results
        oam_analysis = self.analyze_oam_tile_palette_mapping(self.expected_mapping)
        screenshot_analysis = self.analyze_sprite_colors_from_screenshots()
        
        return {
            "strategy": strategy_name,
            "success": True,
            "oam_analysis": oam_analysis,
            "screenshot_analysis": screenshot_analysis,
            "is_breakthrough": oam_analysis.get("is_breakthrough", False) or 
                             screenshot_analysis.get("average_distinct_colors", 0) > 10
        }
    
    def run_deep_search(self, expected_mapping: Dict):
        """Run deep search across multiple injection strategies"""
        self.expected_mapping = expected_mapping
        
        strategies = [
            ("current_1x_before", self.build_current_strategy),
            # Add more strategies here as we develop them
        ]
        
        best_result = None
        best_accuracy = 0
        
        for strategy_name, strategy_func in strategies:
            result = self.test_injection_strategy(strategy_name, strategy_func)
            
            if result.get("success"):
                accuracy = result.get("oam_analysis", {}).get("accuracy", 0)
                if accuracy > best_accuracy:
                    best_accuracy = accuracy
                    best_result = result
        
        return best_result
    
    def build_current_strategy(self) -> Dict:
        """Build ROM with current strategy"""
        # Import and run current penta_cursor_dx.py
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        
        try:
            from penta_cursor_dx import main as build_rom
            build_rom()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

def main():
    import sys
    
    rom_path = Path("rom/working/penta_dragon_cursor_dx.gb")
    output_dir = Path("test_output") / f"deep_search_{int(time.time())}"
    
    if len(sys.argv) > 1:
        rom_path = Path(sys.argv[1])
    
    # Load expected mapping
    monster_map_path = Path("palettes/monster_palette_map.yaml")
    expected_mapping = {}
    if monster_map_path.exists():
        with open(monster_map_path) as f:
            expected_mapping = yaml.safe_load(f)
    
    tester = DeepSearchAutomation(rom_path, output_dir)
    
    # Run deep search
    result = tester.run_deep_search(expected_mapping)
    
    if result and result.get("is_breakthrough"):
        print("=" * 80)
        print("BREAKTHROUGH FOUND!")
        print("=" * 80)
        print(f"Strategy: {result.get('strategy')}")
        print(f"Accuracy: {result.get('oam_analysis', {}).get('accuracy', 0)*100:.1f}%")
        print(f"Distinct colors: {result.get('screenshot_analysis', {}).get('average_distinct_colors', 0):.1f}")
        print("=" * 80)
    else:
        print("No breakthrough yet - continuing search...")

if __name__ == "__main__":
    main()

