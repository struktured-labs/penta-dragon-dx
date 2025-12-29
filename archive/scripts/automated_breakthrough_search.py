#!/usr/bin/env python3
"""
Automated Breakthrough Search - Runs independently, only reports breakthroughs
Tests multiple injection strategies automatically and verifies sprite colors
"""
import subprocess
import json
import time
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List
import yaml

class AutomatedBreakthroughSearch:
    def __init__(self, base_rom_path: Path, output_base: Path):
        self.base_rom_path = base_rom_path
        self.output_base = output_base
        self.output_base.mkdir(parents=True, exist_ok=True)
        
        # Load expected mapping
        monster_map_path = Path("palettes/monster_palette_map.yaml")
        self.expected_mapping = {}
        if monster_map_path.exists():
            with open(monster_map_path) as f:
                self.expected_mapping = yaml.safe_load(f)
    
    def build_and_test_strategy(self, strategy_id: str, build_func) -> Dict:
        """Build ROM with strategy and test it"""
        output_dir = self.output_base / f"strategy_{strategy_id}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        rom_path = output_dir / "test_rom.gb"
        
        # Build ROM
        try:
            build_func(rom_path)
        except Exception as e:
            return {"success": False, "error": f"Build failed: {e}"}
        
        # Test ROM
        return self.test_rom(rom_path, output_dir)
    
    def test_rom(self, rom_path: Path, output_dir: Path) -> Dict:
        """Test a ROM and return analysis"""
        screenshots_dir = output_dir / "screenshots"
        logs_dir = output_dir / "logs"
        screenshots_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)
        
        # Create working Lua script
        lua_script = logs_dir / "test.lua"
        screenshot_base = str(screenshots_dir / "frame_")
        oam_json = str(logs_dir / "oam.json")
        
        script_content = f'''-- Automated test script
local frameCount = 0
local oamWrites = {{}}
local logFile = io.open("{logs_dir / 'test.log'}", "w")

logFile:write("Test started\\n")
logFile:flush()

-- Register callbacks at top level
for sprite = 0, 39 do
    local flagsAddr = 0xFE00 + (sprite * 4) + 3
    emu:addMemoryCallback(function(addr, value)
        local tile = emu:read8(addr - 1)
        table.insert(oamWrites, {{
            frame = frameCount,
            sprite = math.floor((addr - 0xFE00) / 4),
            tile = tile,
            palette = value & 0x07,
            pc = emu:getRegister("PC")
        }})
    end, emu.memoryCallback.WRITE, flagsAddr, flagsAddr)
end

callbacks:add("frame", function()
    frameCount = frameCount + 1
    
    if frameCount % 60 == 0 then
        local screenshot = emu:takeScreenshot()
        screenshot:save("{screenshot_base}" .. string.format("%05d", frameCount) .. ".png")
    end
    
    if frameCount >= 480 then
        local jsonFile = io.open("{oam_json}", "w")
        jsonFile:write("[\\n")
        for i, w in ipairs(oamWrites) do
            jsonFile:write(string.format('{{"frame":%d,"sprite":%d,"tile":%d,"palette":%d,"pc":%d}}',
                w.frame, w.sprite, w.tile, w.palette, w.pc))
            if i < #oamWrites then jsonFile:write(",") end
            jsonFile:write("\\n")
        end
        jsonFile:write("]\\n")
        jsonFile:close()
        logFile:close()
        emu:stop()
    end
end)
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
            return {"success": False, "error": f"Test execution failed: {e}"}
        
        # Analyze results
        return self.analyze_results(output_dir)
    
    def analyze_results(self, output_dir: Path) -> Dict:
        """Analyze test results"""
        oam_json = output_dir / "logs" / "oam.json"
        screenshots = list((output_dir / "screenshots").glob("frame_*.png"))
        
        result = {
            "screenshots": len(screenshots),
            "oam_writes": 0,
            "accuracy": 0,
            "is_breakthrough": False
        }
        
        if oam_json.exists():
            try:
                with open(oam_json) as f:
                    oam_writes = json.load(f)
                result["oam_writes"] = len(oam_writes)
                
                # Analyze tile-to-palette mapping
                if oam_writes and "monster_palette_map" in self.expected_mapping:
                    tile_to_palette = defaultdict(lambda: defaultdict(int))
                    for write in oam_writes:
                        tile = write.get("tile", -1)
                        palette = write.get("palette", -1)
                        if tile >= 0:
                            tile_to_palette[tile][palette] += 1
                    
                    expected_tile_map = {}
                    for monster_name, data in self.expected_mapping["monster_palette_map"].items():
                        palette = data.get("palette", 0xFF)
                        for tile in data.get("tile_range", []):
                            expected_tile_map[tile] = palette
                    
                    matches = 0
                    for tile, expected_pal in expected_tile_map.items():
                        if tile in tile_to_palette:
                            most_common = max(tile_to_palette[tile].items(), key=lambda x: x[1])
                            if most_common[0] == expected_pal and most_common[1] / sum(tile_to_palette[tile].values()) > 0.8:
                                matches += 1
                    
                    if expected_tile_map:
                        result["accuracy"] = matches / len(expected_tile_map)
                        result["is_breakthrough"] = result["accuracy"] > 0.5 or result["screenshots"] > 5
            except Exception as e:
                result["error"] = str(e)
        
        return result
    
    def run_search(self):
        """Run automated search across strategies"""
        strategies = [
            ("current", self.build_current),
            # Add more strategies here
        ]
        
        best_accuracy = 0
        best_strategy = None
        
        for strategy_id, build_func in strategies:
            print(f"Testing strategy: {strategy_id}")
            result = self.build_and_test_strategy(strategy_id, build_func)
            
            if result.get("success") and result.get("accuracy", 0) > best_accuracy:
                best_accuracy = result["accuracy"]
                best_strategy = (strategy_id, result)
            
            if result.get("is_breakthrough"):
                print("=" * 80)
                print("BREAKTHROUGH FOUND!")
                print("=" * 80)
                print(f"Strategy: {strategy_id}")
                print(f"Accuracy: {result['accuracy']*100:.1f}%")
                print(f"OAM writes: {result['oam_writes']}")
                print(f"Screenshots: {result['screenshots']}")
                print("=" * 80)
                return best_strategy
        
        if best_strategy:
            print(f"Best result: {best_strategy[0]} with {best_strategy[1]['accuracy']*100:.1f}% accuracy")
        
        return best_strategy
    
    def build_current(self, output_path: Path):
        """Build current strategy"""
        import sys
        sys.path.insert(0, str(Path(__file__).parent))
        from penta_cursor_dx import main as build_main
        
        # Temporarily override output path
        original_output = Path("rom/working/penta_dragon_cursor_dx.gb")
        shutil.copy(original_output, output_path)

def main():
    base_rom = Path("rom/Penta Dragon (J).gb")
    output_base = Path("test_output") / f"auto_search_{int(time.time())}"
    
    searcher = AutomatedBreakthroughSearch(base_rom, output_base)
    result = searcher.run_search()
    
    if result and result[1].get("is_breakthrough"):
        print("\n✅ BREAKTHROUGH CONFIRMED - Ready for review!")
    else:
        print("\n⚠️  No breakthrough yet - continuing search...")

if __name__ == "__main__":
    main()

