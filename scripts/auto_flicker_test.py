#!/usr/bin/env python3
"""
Automated flicker detection test.
Runs ROM headlessly, captures frames during demo, analyzes color stability.
"""
import subprocess
import time
import os
from pathlib import Path
from PIL import Image
import tempfile
import shutil

def run_headless_capture(rom_path: Path, output_dir: Path, num_captures: int = 20,
                         start_frame: int = 3000, frame_interval: int = 100):
    """Run ROM headlessly and capture screenshots."""

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create Lua script for automated capture
    lua_script = output_dir / "capture.lua"
    lua_content = f'''
local frame = 0
local capture_start = {start_frame}
local capture_interval = {frame_interval}
local captures_remaining = {num_captures}
local output_dir = "{output_dir}"

function on_frame()
    frame = frame + 1

    if frame >= capture_start and captures_remaining > 0 then
        if (frame - capture_start) % capture_interval == 0 then
            local filename = output_dir .. "/frame_" .. string.format("%05d", frame) .. ".png"
            emu:screenshot(filename)
            console:log("Captured: " .. filename)
            captures_remaining = captures_remaining - 1
        end
    end

    if captures_remaining <= 0 then
        console:log("All captures complete")
        emu:quit()
    end

    -- Safety timeout at frame 15000
    if frame > 15000 then
        console:log("Timeout reached")
        emu:quit()
    end
end

callbacks:add("frame", on_frame)
console:log("Flicker test started, waiting for frame " .. capture_start)
'''

    lua_script.write_text(lua_content)

    # Run mGBA headlessly with xvfb
    print(f"Running headless capture (starting at frame {start_frame})...")
    try:
        result = subprocess.run(
            ["xvfb-run", "-a", "mgba-qt", "-l", str(lua_script), str(rom_path)],
            timeout=180,
            capture_output=True,
            text=True
        )
        print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
    except subprocess.TimeoutExpired:
        print("Capture timed out (expected)")
    except Exception as e:
        print(f"Error: {e}")

    return list(output_dir.glob("frame_*.png"))


def analyze_sprite_colors(screenshots: list[Path]) -> dict:
    """Analyze color consistency across frames."""

    if not screenshots:
        return {"error": "No screenshots captured"}

    screenshots = sorted(screenshots)
    print(f"\nAnalyzing {len(screenshots)} screenshots...")

    # Sample specific pixel positions where sprites typically appear
    # Game screen is 160x144, sprites are typically in the play area
    sample_positions = [
        # Center area where Sara W and monsters appear
        (80, 72), (80, 80), (80, 88),
        (60, 72), (100, 72),
        (40, 60), (120, 60),
        (40, 100), (120, 100),
    ]

    color_history = {pos: [] for pos in sample_positions}

    for screenshot in screenshots:
        try:
            img = Image.open(screenshot)
            for pos in sample_positions:
                if pos[0] < img.width and pos[1] < img.height:
                    color = img.getpixel(pos)
                    color_history[pos].append(color)
        except Exception as e:
            print(f"Error reading {screenshot}: {e}")

    # Analyze color changes at each position
    results = {}
    total_changes = 0
    total_samples = 0

    for pos, colors in color_history.items():
        if len(colors) < 2:
            continue

        unique_colors = len(set(colors))
        changes = sum(1 for i in range(1, len(colors)) if colors[i] != colors[i-1])

        results[pos] = {
            "unique_colors": unique_colors,
            "color_changes": changes,
            "total_frames": len(colors),
            "change_rate": changes / (len(colors) - 1) if len(colors) > 1 else 0
        }

        total_changes += changes
        total_samples += len(colors) - 1

    overall_flicker_rate = total_changes / total_samples if total_samples > 0 else 0

    return {
        "positions": results,
        "overall_flicker_rate": overall_flicker_rate,
        "total_frames": len(screenshots),
        "assessment": "HIGH FLICKER" if overall_flicker_rate > 0.3 else
                      "MODERATE FLICKER" if overall_flicker_rate > 0.1 else
                      "LOW FLICKER" if overall_flicker_rate > 0.02 else "STABLE"
    }


def main():
    rom_path = Path("rom/working/penta_dragon_dx_FIXED.gb")
    output_dir = Path("test_output/flicker_test")

    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return

    # Clean previous results
    if output_dir.exists():
        shutil.rmtree(output_dir)

    print("=" * 60)
    print("AUTOMATED FLICKER DETECTION TEST")
    print("=" * 60)
    print(f"ROM: {rom_path}")
    print(f"Waiting for demo section (frame ~3000+)")
    print()

    # Capture frames
    screenshots = run_headless_capture(
        rom_path,
        output_dir,
        num_captures=30,      # Capture 30 frames
        start_frame=4000,     # Start after demo begins
        frame_interval=50     # Every 50 frames
    )

    if not screenshots:
        print("No screenshots captured. Check if mgba-qt supports scripting.")
        return

    # Analyze
    results = analyze_sprite_colors(screenshots)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Frames analyzed: {results.get('total_frames', 0)}")
    print(f"Overall flicker rate: {results.get('overall_flicker_rate', 0):.2%}")
    print(f"Assessment: {results.get('assessment', 'UNKNOWN')}")

    print("\nPer-position analysis:")
    for pos, data in results.get("positions", {}).items():
        if data["color_changes"] > 0:
            print(f"  {pos}: {data['unique_colors']} colors, {data['color_changes']} changes ({data['change_rate']:.1%})")

    # Save results
    results_file = output_dir / "results.txt"
    with open(results_file, "w") as f:
        f.write(f"Flicker Test Results\n")
        f.write(f"ROM: {rom_path}\n")
        f.write(f"Frames: {results.get('total_frames', 0)}\n")
        f.write(f"Flicker Rate: {results.get('overall_flicker_rate', 0):.2%}\n")
        f.write(f"Assessment: {results.get('assessment', 'UNKNOWN')}\n")

    print(f"\nResults saved to: {results_file}")
    print(f"Screenshots in: {output_dir}")


if __name__ == "__main__":
    main()
