#!/usr/bin/env python3
"""
Test All Existing Iteration Scripts with Screenshot Analysis

Tests all penta_cursor_dx_iter*.py scripts systematically:
1. Run each script to generate ROM
2. Launch ROM in mgba-qt briefly
3. Capture screenshot using scrot/imagemagick
4. Analyze screenshot for distinct colors
5. Report which iteration (if any) achieves distinct colors
"""
import subprocess
import sys
import time
from pathlib import Path
import os
import signal

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("📦 Installing dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pillow", "numpy"], check=True)
    from PIL import Image
    import numpy as np

class IterationTester:
    """Test all iteration scripts systematically"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.scripts_dir = self.project_root / "scripts"
        self.test_output = self.project_root / "test_output" / f"iteration_test_{int(time.time())}"
        self.test_output.mkdir(parents=True, exist_ok=True)

    def print_banner(self):
        print("=" * 80)
        print("🔄 TEST ALL ITERATION SCRIPTS - Find the Working One!")
        print("=" * 80)
        print()

    def find_iteration_scripts(self):
        """Find all penta_cursor_dx iteration scripts"""
        scripts = sorted(self.scripts_dir.glob("penta_cursor_dx_iter*.py"))
        # Also include main scripts
        main_scripts = [
            self.scripts_dir / "penta_cursor_dx.py",
            self.scripts_dir / "penta_cursor_dx_breakthrough.py",
            self.scripts_dir / "penta_cursor_dx_final.py",
        ]
        scripts.extend([s for s in main_scripts if s.exists()])
        return scripts

    def run_script(self, script_path: Path) -> Path:
        """Run a ROM generation script"""
        print(f"  🔧 Running: {script_path.name}")

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.project_root
            )

            if result.returncode == 0:
                # Find generated ROM
                rom_candidates = [
                    self.project_root / "rom" / "working" / "penta_dragon_cursor_dx.gb",
                    self.project_root / "rom" / "working" / "penta_dragon_dx_FIXED.gb",
                    self.project_root / "rom" / "working" / "penta_dragon_breakthrough.gb",
                ]

                for rom in rom_candidates:
                    if rom.exists():
                        # Copy to test output
                        dest = self.test_output / f"{script_path.stem}.gb"
                        import shutil
                        shutil.copy(rom, dest)
                        print(f"  ✓ ROM created: {dest.name}")
                        return dest

            print(f"  ⚠️  Script failed or ROM not found")
            return None

        except subprocess.TimeoutExpired:
            print(f"  ⚠️  Script timeout")
            return None
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return None

    def capture_screenshot_scrot(self, rom_path: Path) -> Path:
        """Capture screenshot using scrot"""
        screenshot_path = self.test_output / f"screenshot_{rom_path.stem}.png"

        print(f"  📸 Capturing screenshot (launching ROM for 5s)...")

        # Launch mgba-qt
        env = os.environ.copy()
        env['QT_QPA_PLATFORM'] = 'xcb'
        env['__GLX_VENDOR_LIBRARY_NAME'] = 'nvidia'

        proc = subprocess.Popen(
            ["mgba-qt", str(rom_path)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Wait for window to open
        time.sleep(3)

        # Try to find mGBA window and capture it
        try:
            # Use xdotool to find window
            result = subprocess.run(
                ["xdotool", "search", "--name", "mGBA"],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.stdout.strip():
                window_id = result.stdout.strip().split('\n')[0]

                # Capture with scrot
                subprocess.run(
                    ["scrot", "-u", "-o", str(screenshot_path), "-e", f"xdotool windowkill {window_id}"],
                    timeout=2,
                    capture_output=True
                )
        except:
            pass

        # Kill mgba
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except:
            proc.kill()
            proc.wait()

        if screenshot_path.exists():
            print(f"  ✓ Screenshot: {screenshot_path.name}")
            return screenshot_path
        else:
            print(f"  ⚠️  Screenshot failed, trying alternative...")
            return self.capture_screenshot_xwd(rom_path)

    def capture_screenshot_xwd(self, rom_path: Path) -> Path:
        """Fallback: capture using xwd"""
        screenshot_path = self.test_output / f"screenshot_{rom_path.stem}.png"

        # Launch mgba-qt
        env = os.environ.copy()
        env['QT_QPA_PLATFORM'] = 'xcb'
        env['__GLX_VENDOR_LIBRARY_NAME'] = 'nvidia'

        proc = subprocess.Popen(
            ["mgba-qt", str(rom_path)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        time.sleep(4)

        try:
            # Use xwd + convert
            result = subprocess.run(
                ["xdotool", "search", "--name", "mGBA"],
                capture_output=True,
                text=True,
                timeout=2
            )

            if result.stdout.strip():
                window_id = result.stdout.strip().split('\n')[0]
                xwd_path = screenshot_path.with_suffix('.xwd')

                subprocess.run(
                    ["xwd", "-id", window_id, "-out", str(xwd_path)],
                    timeout=2,
                    capture_output=True
                )

                if xwd_path.exists():
                    subprocess.run(
                        ["convert", str(xwd_path), str(screenshot_path)],
                        timeout=2,
                        capture_output=True
                    )
                    xwd_path.unlink()
        except:
            pass
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except:
                proc.kill()
                proc.wait()

        if screenshot_path.exists():
            print(f"  ✓ Screenshot: {screenshot_path.name}")
            return screenshot_path
        else:
            print(f"  ⚠️  Screenshot capture failed")
            return None

    def analyze_colors(self, screenshot_path: Path) -> dict:
        """Analyze screenshot for distinct sprite colors"""
        if not screenshot_path or not screenshot_path.exists():
            return {'success': False, 'distinct_colors': 0, 'colors': []}

        try:
            img = Image.open(screenshot_path).convert('RGB')
            img_array = np.array(img)

            # Get unique colors
            pixels = img_array.reshape(-1, 3)
            unique_colors = np.unique(pixels, axis=0)

            # Filter background (white/black/green tones)
            sprite_colors = []
            for color in unique_colors:
                r, g, b = color
                # Skip if too white, too black, or common BG green
                if not (np.all(color > 200) or np.all(color < 30)):
                    # Skip common dungeon green
                    if not (g > 100 and r < 50 and b < 50):
                        sprite_colors.append(tuple(color))

            distinct_count = len(sprite_colors)

            # Success if we have 6+ distinct colors (2 per monster minimum)
            success = distinct_count >= 6

            print(f"  🎨 Distinct sprite colors: {distinct_count}")
            if distinct_count > 0:
                print(f"     Sample colors: {sprite_colors[:3]}")

            return {
                'success': success,
                'distinct_colors': distinct_count,
                'colors': sprite_colors[:20]  # Keep first 20
            }
        except Exception as e:
            print(f"  ❌ Analysis error: {e}")
            return {'success': False, 'distinct_colors': 0, 'colors': []}

    def test_iteration(self, script_path: Path) -> dict:
        """Test one iteration script"""
        print(f"\n{'='*80}")
        print(f"Testing: {script_path.name}")
        print(f"{'='*80}")

        # Run script to generate ROM
        rom_path = self.run_script(script_path)
        if not rom_path:
            return {
                'script': script_path.name,
                'success': False,
                'reason': 'ROM generation failed'
            }

        # Capture screenshot
        screenshot = self.capture_screenshot_scrot(rom_path)

        # Analyze colors
        analysis = self.analyze_colors(screenshot)

        return {
            'script': script_path.name,
            'rom': rom_path,
            'screenshot': screenshot,
            'analysis': analysis,
            'success': analysis['success']
        }

    def run(self):
        """Main test loop"""
        self.print_banner()

        # Find all iteration scripts
        scripts = self.find_iteration_scripts()
        print(f"Found {len(scripts)} iteration scripts to test\n")

        results = []

        for i, script in enumerate(scripts):
            print(f"\n[{i+1}/{len(scripts)}]")
            result = self.test_iteration(script)
            results.append(result)

            if result['success']:
                print(f"\n🎉 SUCCESS FOUND!")
                print(f"  Script: {result['script']}")
                print(f"  ROM: {result['rom']}")
                print(f"  Distinct colors: {result['analysis']['distinct_colors']}")
                print(f"\n🎮 Test manually:")
                print(f"  QT_QPA_PLATFORM=xcb __GLX_VENDOR_LIBRARY_NAME=nvidia mgba-qt {result['rom']}")

                # Continue testing to find all working ones

        # Final report
        print(f"\n{'='*80}")
        print("FINAL RESULTS")
        print(f"{'='*80}\n")

        successes = [r for r in results if r['success']]

        if successes:
            print(f"✅ {len(successes)} working iteration(s) found:\n")
            for r in successes:
                print(f"  • {r['script']}")
                print(f"    ROM: {r['rom']}")
                print(f"    Colors: {r['analysis']['distinct_colors']}")
        else:
            print(f"⚠️  No iterations achieved distinct colors yet\n")
            print("Color counts by iteration:")
            for r in results:
                if 'analysis' in r and r['analysis']:
                    print(f"  {r['script']}: {r['analysis']['distinct_colors']} colors")

        print(f"\n📁 All results saved in: {self.test_output}")

        return len(successes) > 0

def main():
    tester = IterationTester()
    success = tester.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
