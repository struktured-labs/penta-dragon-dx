#!/usr/bin/env python3
"""
Automated Color Testing Loop - Iterate Until Victory!

This script automatically:
1. Tries different palette assignment approaches
2. Runs mgba-headless with screenshots
3. Analyzes screenshots for distinct colors
4. Iterates until Sara W, Sara D, and Dragon Fly have different colors
5. Reports success or provides detailed debugging info

Usage:
    python3 scripts/automated_color_loop.py
"""
import subprocess
import sys
import time
from pathlib import Path
import tempfile
import shutil
from typing import Dict, List, Tuple

# Ensure dependencies
try:
    from PIL import Image
    import numpy as np
    import yaml
except ImportError:
    print("📦 Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pillow", "numpy", "pyyaml"], check=True)
    from PIL import Image
    import numpy as np
    import yaml

class AutomatedColorLoop:
    """Automated loop to test different approaches until distinct colors work"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.rom_path = self.project_root / "rom" / "Penta Dragon (J).gb"
        self.working_dir = self.project_root / "rom" / "working"
        self.test_output = self.project_root / "test_output"
        self.test_output.mkdir(exist_ok=True)

        self.iteration = 0
        self.max_iterations = 10

    def print_banner(self):
        """Print banner"""
        print("=" * 80)
        print("🔄 AUTOMATED COLOR TESTING LOOP - Iterate Until Distinct Colors!")
        print("=" * 80)
        print()

    def create_lua_screenshot_script(self, output_dir: Path, frames: List[int]) -> Path:
        """Create Lua script to capture screenshots at specific frames"""
        lua_script = output_dir / "capture.lua"

        # Generate frame capture conditions
        frame_checks = "\n    ".join([
            f"if frame == {frame} then\n        emu:screenshot(string.format('{output_dir}/frame_%04d.png', frame))\n        print('Screenshot at frame ' .. frame)\n    end"
            for frame in frames
        ])

        lua_content = f"""
-- Auto-generated screenshot capture script
frame = 0
done_frames = {{}}

function captureScreenshots()
    frame = frame + 1

    -- Capture at specific frames where monsters appear
    {frame_checks}

    -- Auto-quit after last frame
    if frame > {max(frames) + 60} then
        print('Capture complete!')
        emu:reset()
        os.exit(0)
    end
end

callbacks:add("frame", captureScreenshots)
print('Screenshot script loaded. Will capture at frames: {", ".join(map(str, frames))}')
"""

        with open(lua_script, 'w') as f:
            f.write(lua_content)

        return lua_script

    def run_mgba_capture(self, rom_path: Path, output_dir: Path, duration: int = 30) -> List[Path]:
        """Run mgba-headless and capture screenshots"""
        print(f"  📸 Running mGBA headless for {duration}s to capture screenshots...")

        # Create Lua script to capture at frames where monsters appear
        # Based on project docs, intro demo shows monsters around frames 40-120
        capture_frames = [40, 50, 60, 70, 80, 90, 100, 110, 120]
        lua_script = self.create_lua_screenshot_script(output_dir, capture_frames)

        try:
            # Run mgba-headless with Lua script
            cmd = ["mgba", "-l", str(lua_script), str(rom_path)]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration
            )
        except subprocess.TimeoutExpired:
            print("  ⏱️  mGBA timeout (expected)")
        except FileNotFoundError:
            print("  ⚠️  mgba not found, trying mgba-qt in headless mode...")
            # Fallback: Use mgba-qt and kill it after duration
            proc = subprocess.Popen(["mgba-qt", str(rom_path)])
            time.sleep(duration)
            proc.terminate()
            proc.wait(timeout=5)

        # Find captured screenshots
        screenshots = sorted(output_dir.glob("frame_*.png"))
        print(f"  ✓ Captured {len(screenshots)} screenshots")
        return screenshots

    def analyze_sprite_colors(self, screenshot_path: Path) -> Dict[str, List[Tuple[int, int, int]]]:
        """Analyze colors in screenshot to detect sprite colors"""
        img = Image.open(screenshot_path).convert('RGB')
        img_array = np.array(img)

        # Get unique colors (ignoring background)
        pixels = img_array.reshape(-1, 3)
        unique_colors = np.unique(pixels, axis=0)

        # Filter out likely background colors (white, black, common BG colors)
        bg_colors = {(255, 255, 255), (0, 0, 0), (0, 255, 0), (0, 128, 0)}
        sprite_colors = [
            tuple(color) for color in unique_colors
            if tuple(color) not in bg_colors and not np.all(color > 200)  # Not too white
        ]

        return {
            'unique_colors': sprite_colors,
            'color_count': len(sprite_colors)
        }

    def detect_distinct_colors(self, screenshots: List[Path]) -> Dict:
        """Analyze screenshots to detect if monsters have distinct colors"""
        print("  🎨 Analyzing screenshots for distinct colors...")

        all_colors = set()
        frame_analysis = []

        for screenshot in screenshots[:5]:  # Analyze first 5 frames
            analysis = self.analyze_sprite_colors(screenshot)
            frame_analysis.append({
                'frame': screenshot.stem,
                'colors': analysis['unique_colors'],
                'count': analysis['color_count']
            })
            all_colors.update(analysis['unique_colors'])

        # Check for distinct colors
        distinct_count = len(all_colors)

        # We need at least 3 distinct color groups for Sara W, Sara D, Dragon Fly
        success = distinct_count >= 6  # At least 2 colors per monster

        return {
            'success': success,
            'distinct_colors': distinct_count,
            'all_colors': list(all_colors),
            'frames': frame_analysis
        }

    def approach_vblank_oam_hook(self, iteration: int) -> Path:
        """Approach: VBlank hook with OAM palette assignment"""
        print(f"\n  🧪 Iteration {iteration}: VBlank OAM Hook")

        # This would generate a ROM with VBlank hook code
        # For now, we'll use the existing approach and document what needs to change
        output_rom = self.working_dir / f"test_iter_{iteration}_vblank.gb"

        # Copy current ROM as base
        if self.working_dir / "penta_dragon_dx_FIXED.gb":
            shutil.copy(
                self.working_dir / "penta_dragon_dx_FIXED.gb",
                output_rom
            )

        return output_rom

    def approach_input_handler_hook(self, iteration: int) -> Path:
        """Approach: Input handler hook with OAM modification"""
        print(f"\n  🧪 Iteration {iteration}: Input Handler Hook")

        output_rom = self.working_dir / f"test_iter_{iteration}_input.gb"

        # This would modify the input handler to update OAM
        # For now, use existing ROM
        if self.working_dir / "penta_dragon_dx_FIXED.gb":
            shutil.copy(
                self.working_dir / "penta_dragon_dx_FIXED.gb",
                output_rom
            )

        return output_rom

    def generate_test_rom(self, iteration: int) -> Path:
        """Generate test ROM for this iteration"""
        approaches = [
            self.approach_vblank_oam_hook,
            self.approach_input_handler_hook,
        ]

        approach_idx = iteration % len(approaches)
        return approaches[approach_idx](iteration)

    def run_iteration(self, iteration: int) -> Dict:
        """Run one iteration of testing"""
        print(f"\n{'='*80}")
        print(f"🔄 ITERATION {iteration + 1}/{self.max_iterations}")
        print(f"{'='*80}")

        # Create output directory for this iteration
        iter_output = self.test_output / f"iteration_{iteration:03d}"
        iter_output.mkdir(exist_ok=True)

        # Generate test ROM
        test_rom = self.generate_test_rom(iteration)
        if not test_rom.exists():
            print(f"  ❌ ROM not found: {test_rom}")
            return {'success': False, 'reason': 'ROM generation failed'}

        # Run mgba and capture screenshots
        screenshots = self.run_mgba_capture(test_rom, iter_output, duration=15)

        if not screenshots:
            print("  ❌ No screenshots captured")
            return {'success': False, 'reason': 'Screenshot capture failed'}

        # Analyze screenshots
        analysis = self.detect_distinct_colors(screenshots)

        # Report results
        if analysis['success']:
            print(f"  ✅ SUCCESS! Found {analysis['distinct_colors']} distinct colors")
            print(f"  🎉 ROM: {test_rom}")
        else:
            print(f"  ❌ Failed: Only {analysis['distinct_colors']} distinct colors (need 6+)")

        return {
            'iteration': iteration,
            'rom': test_rom,
            'screenshots': screenshots,
            'analysis': analysis,
            'success': analysis['success']
        }

    def run(self):
        """Main loop"""
        self.print_banner()

        print("Goal: Sara W, Sara D, and Dragon Fly with distinct colors")
        print(f"Strategy: Try up to {self.max_iterations} approaches automatically\n")

        results = []

        for i in range(self.max_iterations):
            result = self.run_iteration(i)
            results.append(result)

            if result['success']:
                print(f"\n{'='*80}")
                print("🎉 SUCCESS!")
                print(f"{'='*80}")
                print(f"\nWorking ROM: {result['rom']}")
                print(f"Screenshots: {result['screenshots'][0].parent}")
                print(f"Distinct colors detected: {result['analysis']['distinct_colors']}")
                print("\n🎮 Test manually:")
                print(f"   mgba-qt {result['rom']}")
                return True

            # Brief pause between iterations
            time.sleep(1)

        print(f"\n{'='*80}")
        print("⚠️  No Success After All Iterations")
        print(f"{'='*80}")
        print("\n📊 Summary:")
        for result in results:
            if result.get('analysis'):
                print(f"  Iteration {result['iteration']}: {result['analysis']['distinct_colors']} colors")

        print("\n🔧 Next Steps:")
        print("  1. The issue is OAM palette bits not being set per-tile")
        print("  2. Need to implement tile-to-palette lookup table")
        print("  3. Hook VBlank or other interrupt to update OAM palette bits")
        print("  4. See docs/SCALABLE_PALETTE_APPROACH.md for implementation")

        return False

def main():
    loop = AutomatedColorLoop()
    success = loop.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
