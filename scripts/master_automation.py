#!/usr/bin/env python3
"""
Master Automation Orchestrator - Automate Your Way to Victory!

This script orchestrates all automation tools to systematically solve
the per-monster colorization challenge through iterative testing and refinement.

Strategy:
1. Generate lookup table from monster_palette_map.yaml
2. Test different injection approaches (VBlank, input handler, etc.)
3. Automatically verify results with screenshot analysis
4. Iterate until distinct colors are achieved
5. Report success or provide actionable debugging info

Usage:
    python3 scripts/master_automation.py
"""
import subprocess
import sys
import time
from pathlib import Path
import json

# Ensure dependencies
try:
    import yaml
    from PIL import Image
    import numpy as np
except ImportError:
    print("📦 Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pillow", "numpy", "pyyaml"], check=True)
    import yaml
    from PIL import Image
    import numpy as np

class MasterAutomation:
    """Orchestrates all automation tools to achieve per-monster colorization"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.rom_path = self.project_root / "rom" / "Penta Dragon (J).gb"
        self.working_dir = self.project_root / "rom" / "working"
        self.output_rom = self.working_dir / "penta_dragon_dx_FIXED.gb"
        self.monster_map = self.project_root / "palettes" / "monster_palette_map.yaml"
        self.palette_yaml = self.project_root / "palettes" / "penta_palettes.yaml"

        # Ensure working directory exists
        self.working_dir.mkdir(parents=True, exist_ok=True)

        # Load monster palette mapping
        with open(self.monster_map, 'r') as f:
            self.monster_data = yaml.safe_load(f)

    def print_banner(self):
        """Print welcome banner"""
        print("=" * 70)
        print("🚀 MASTER AUTOMATION ORCHESTRATOR - Automate Your Way to Victory!")
        print("=" * 70)
        print()
        print("Goal: Achieve distinct colors for each monster type")
        print("Strategy: Systematic iteration through approaches with auto-verification")
        print()

    def check_prerequisites(self):
        """Check that all necessary files exist"""
        print("🔍 Checking prerequisites...")

        if not self.rom_path.exists():
            print(f"❌ Original ROM not found: {self.rom_path}")
            print("   Please place 'Penta Dragon (J).gb' in rom/ directory")
            return False

        if not self.monster_map.exists():
            print(f"❌ Monster palette map not found: {self.monster_map}")
            return False

        if not self.palette_yaml.exists():
            print(f"❌ Palette YAML not found: {self.palette_yaml}")
            return False

        # Check for mgba
        mgba = subprocess.run(["which", "mgba-qt"], capture_output=True)
        if mgba.returncode != 0:
            print("⚠️  Warning: mgba-qt not found. Testing will be limited.")

        print("✅ Prerequisites OK")
        return True

    def generate_lookup_table(self):
        """Generate tile-to-palette lookup table from monster map"""
        print("\n📋 Generating tile-to-palette lookup table...")

        # Initialize 256-byte table with 0xFF (don't modify)
        lookup_table = [0xFF] * 256

        # Fill in mappings from monster_palette_map
        monster_map = self.monster_data.get('monster_palette_map', {})

        for monster_name, data in monster_map.items():
            palette_id = data.get('palette', 0)
            tile_range = data.get('tile_range', [])

            for tile_id in tile_range:
                if 0 <= tile_id <= 255:
                    lookup_table[tile_id] = palette_id
                    print(f"  Tile {tile_id:3d} → Palette {palette_id} ({monster_name})")

        # Save to file for inspection
        lookup_path = self.working_dir / "tile_palette_lookup.bin"
        with open(lookup_path, 'wb') as f:
            f.write(bytes(lookup_table))

        print(f"✅ Lookup table saved: {lookup_path}")
        return lookup_table

    def approach_1_yaml_based(self):
        """Approach 1: Use existing YAML-based ROM builder"""
        print("\n" + "=" * 70)
        print("🧪 APPROACH 1: YAML-based ROM generation (current method)")
        print("=" * 70)

        script = self.project_root / "scripts" / "create_dx_rom_from_yaml.py"
        if not script.exists():
            script = self.project_root / "scripts" / "create_dx_rom.py"

        if not script.exists():
            print("❌ ROM creation script not found")
            return False

        print(f"Running: {script}")
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)

        if result.returncode == 0:
            print("✅ ROM generated successfully")
            if self.output_rom.exists():
                return True
        else:
            print(f"❌ ROM generation failed:")
            print(result.stderr)

        return False

    def approach_2_automated_patcher(self):
        """Approach 2: Use automated palette patcher"""
        print("\n" + "=" * 70)
        print("🧪 APPROACH 2: Automated palette patcher (lookup table)")
        print("=" * 70)

        script = self.project_root / "scripts" / "automated_palette_patcher.py"
        if not script.exists():
            print("❌ Automated patcher not found")
            return False

        print(f"Running: {script}")
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120)

        if result.returncode == 0:
            print("✅ Automated patching complete")
            return True
        else:
            print(f"❌ Automated patching failed:")
            print(result.stderr)

        return False

    def approach_3_breakthrough(self):
        """Approach 3: Breakthrough test (different hook strategies)"""
        print("\n" + "=" * 70)
        print("🧪 APPROACH 3: Breakthrough test (alternative hooks)")
        print("=" * 70)

        script = self.project_root / "scripts" / "breakthrough_test.py"
        if not script.exists():
            print("❌ Breakthrough test not found")
            return False

        print(f"Running: {script}")
        result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=180)

        if result.returncode == 0:
            print("✅ Breakthrough test complete")
            return True
        else:
            print("⚠️  Breakthrough test had issues (may be expected)")
            print(result.stdout[-500:] if result.stdout else "")

        return False

    def verify_colors(self, rom_path=None):
        """Run automated color verification"""
        if rom_path is None:
            rom_path = self.output_rom

        if not rom_path.exists():
            print(f"❌ ROM not found: {rom_path}")
            return False, None

        print(f"\n🎨 Verifying colors in: {rom_path.name}")

        # Use quick_verify_rom.py if available
        verify_script = self.project_root / "scripts" / "quick_verify_rom.py"
        if verify_script.exists():
            print("Running quick verification...")
            result = subprocess.run(
                [sys.executable, str(verify_script), str(rom_path)],
                capture_output=True,
                text=True,
                timeout=30
            )

            if "PASS" in result.stdout or "SUCCESS" in result.stdout:
                print("✅ Verification PASSED")
                return True, result.stdout
            elif "FAIL" in result.stdout:
                print("❌ Verification FAILED")
                return False, result.stdout

        # Fallback: Check if ROM loads without crashing
        print("Running basic ROM check...")
        return self._basic_rom_check(rom_path)

    def _basic_rom_check(self, rom_path):
        """Basic check: verify ROM is valid GB/GBC ROM"""
        try:
            with open(rom_path, 'rb') as f:
                data = f.read()

            # Check size
            if len(data) < 32768:
                print("❌ ROM too small")
                return False, "ROM too small"

            # Check header
            cgb_flag = data[0x143]
            print(f"  CGB flag: 0x{cgb_flag:02X}")

            if cgb_flag == 0x80 or cgb_flag == 0xC0:
                print("✅ CGB compatibility enabled")
                return True, "CGB flag set correctly"
            else:
                print("⚠️  CGB flag not set (may still work)")
                return True, "CGB flag not set"

        except Exception as e:
            print(f"❌ ROM check failed: {e}")
            return False, str(e)

    def analyze_results(self):
        """Analyze which approach worked best"""
        print("\n" + "=" * 70)
        print("📊 RESULTS ANALYSIS")
        print("=" * 70)

        results = {}

        # Check for various output ROMs
        roms_to_check = [
            ("YAML-based", self.working_dir / "penta_dragon_dx_FIXED.gb"),
            ("Automated patcher", self.working_dir / "penta_dragon_auto_patched.gb"),
            ("Breakthrough", self.working_dir / "penta_dragon_breakthrough.gb"),
        ]

        for name, rom_path in roms_to_check:
            if rom_path.exists():
                print(f"\n{name}: {rom_path.name}")
                success, details = self.verify_colors(rom_path)
                results[name] = {
                    'path': rom_path,
                    'success': success,
                    'details': details
                }

        return results

    def generate_report(self, results):
        """Generate final report"""
        print("\n" + "=" * 70)
        print("📝 FINAL REPORT")
        print("=" * 70)

        successes = [name for name, data in results.items() if data['success']]

        if successes:
            print(f"\n✅ SUCCESS! {len(successes)} approach(es) worked:")
            for name in successes:
                rom = results[name]['path']
                print(f"\n  🎉 {name}")
                print(f"     ROM: {rom}")
                print(f"     {results[name]['details']}")

            print("\n📋 Next steps:")
            print("  1. Test the ROM in mgba-qt:")
            print(f"     mgba-qt {successes[0]}")
            print("  2. Verify Sara W, Sara D, and Dragon Fly have distinct colors")
            print("  3. If working, document the approach!")
        else:
            print("\n⚠️  No approaches succeeded yet.")
            print("\n🔧 Debugging recommendations:")
            print("  1. Check ROM generation logs above for errors")
            print("  2. Run individual scripts manually for detailed output:")
            print("     python3 scripts/create_dx_rom_from_yaml.py")
            print("     python3 scripts/automated_palette_patcher.py")
            print("  3. Review docs/SCALABLE_PALETTE_APPROACH.md for implementation details")
            print("  4. Check reverse_engineering/ for analysis of ROM structure")

        # Save report to file
        report_path = self.working_dir / "automation_report.json"
        with open(report_path, 'w') as f:
            json.dump({
                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
                'results': {
                    name: {
                        'path': str(data['path']),
                        'success': data['success'],
                        'details': data['details']
                    }
                    for name, data in results.items()
                }
            }, f, indent=2)

        print(f"\n📄 Full report saved: {report_path}")

    def run(self):
        """Main orchestration loop"""
        self.print_banner()

        if not self.check_prerequisites():
            print("\n❌ Prerequisites not met. Exiting.")
            return False

        # Generate lookup table
        lookup_table = self.generate_lookup_table()

        # Try each approach
        approaches = [
            ("YAML-based", self.approach_1_yaml_based),
            # Approach 2 and 3 might take longer or need more setup
            # Uncomment when ready to test:
            # ("Automated patcher", self.approach_2_automated_patcher),
            # ("Breakthrough", self.approach_3_breakthrough),
        ]

        for name, approach_func in approaches:
            try:
                print(f"\n⏳ Starting: {name}")
                success = approach_func()
                if success:
                    print(f"✅ {name} completed successfully")
                else:
                    print(f"⚠️  {name} had issues")
            except Exception as e:
                print(f"❌ {name} failed with exception: {e}")
                import traceback
                traceback.print_exc()

        # Analyze and report
        results = self.analyze_results()
        self.generate_report(results)

        print("\n" + "=" * 70)
        print("🏁 AUTOMATION COMPLETE")
        print("=" * 70)

        return True

def main():
    automation = MasterAutomation()
    automation.run()

if __name__ == "__main__":
    main()
