#!/usr/bin/env python3
"""
Automated flicker detection test v2.
Uses ffmpeg to record xvfb display and extract frames.
"""
import subprocess
import time
import os
from pathlib import Path
from PIL import Image
import shutil
import signal

def run_and_capture(rom_path: Path, output_dir: Path, duration_sec: int = 30):
    """Run ROM with xvfb and capture video."""

    output_dir.mkdir(parents=True, exist_ok=True)
    video_file = output_dir / "gameplay.mp4"

    # Start xvfb on a specific display
    display = ":99"
    xvfb_proc = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "640x480x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(1)

    try:
        # Set display for child processes
        env = os.environ.copy()
        env["DISPLAY"] = display

        # Start mgba-qt
        mgba_proc = subprocess.Popen(
            ["mgba-qt", str(rom_path)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Wait for emulator to start
        time.sleep(3)

        # Record screen with ffmpeg
        print(f"Recording for {duration_sec} seconds...")
        ffmpeg_proc = subprocess.Popen(
            [
                "ffmpeg", "-y",
                "-f", "x11grab",
                "-video_size", "640x480",
                "-i", display,
                "-t", str(duration_sec),
                "-r", "30",
                str(video_file)
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        ffmpeg_proc.wait(timeout=duration_sec + 10)

    except Exception as e:
        print(f"Error during capture: {e}")
    finally:
        # Cleanup
        try:
            mgba_proc.terminate()
            mgba_proc.wait(timeout=5)
        except:
            mgba_proc.kill()

        xvfb_proc.terminate()
        xvfb_proc.wait(timeout=5)

    return video_file if video_file.exists() else None


def extract_frames(video_file: Path, output_dir: Path, fps: int = 2):
    """Extract frames from video."""
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    print(f"Extracting frames at {fps} fps...")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(video_file),
            "-vf", f"fps={fps}",
            str(frames_dir / "frame_%04d.png")
        ],
        capture_output=True
    )

    return sorted(frames_dir.glob("frame_*.png"))


def analyze_color_stability(frames: list[Path]) -> dict:
    """Analyze color consistency in sprite areas."""

    if not frames:
        return {"error": "No frames to analyze"}

    print(f"Analyzing {len(frames)} frames...")

    # Sample positions in the game area (adjust based on actual game window position)
    # These are rough estimates - game window is ~160x144 centered in 640x480
    center_x, center_y = 320, 240
    game_scale = 2  # Assume 2x scale

    sample_positions = [
        (center_x, center_y),
        (center_x - 40, center_y),
        (center_x + 40, center_y),
        (center_x, center_y - 40),
        (center_x, center_y + 40),
    ]

    color_history = {pos: [] for pos in sample_positions}

    for frame_path in frames:
        try:
            img = Image.open(frame_path)
            for pos in sample_positions:
                if 0 <= pos[0] < img.width and 0 <= pos[1] < img.height:
                    color = img.getpixel(pos)[:3]  # RGB only
                    color_history[pos].append(color)
        except Exception as e:
            print(f"Error: {e}")

    # Calculate flicker metrics
    total_changes = 0
    total_samples = 0

    for pos, colors in color_history.items():
        if len(colors) < 2:
            continue
        changes = sum(1 for i in range(1, len(colors))
                     if colors[i] != colors[i-1])
        total_changes += changes
        total_samples += len(colors) - 1

    flicker_rate = total_changes / total_samples if total_samples > 0 else 0

    return {
        "frames_analyzed": len(frames),
        "flicker_rate": flicker_rate,
        "total_color_changes": total_changes,
        "assessment": (
            "HIGH FLICKER" if flicker_rate > 0.5 else
            "MODERATE FLICKER" if flicker_rate > 0.2 else
            "LOW FLICKER" if flicker_rate > 0.05 else
            "STABLE"
        )
    }


def main():
    rom_path = Path("rom/working/penta_dragon_dx_FIXED.gb")
    output_dir = Path("test_output/flicker_test_v2")

    if not rom_path.exists():
        print(f"ROM not found: {rom_path}")
        return

    # Clean previous
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    print("=" * 60)
    print("AUTOMATED FLICKER TEST v2")
    print("=" * 60)

    # Record gameplay
    video = run_and_capture(rom_path, output_dir, duration_sec=25)

    if not video:
        print("Failed to capture video")
        return

    print(f"Video saved: {video}")

    # Extract frames
    frames = extract_frames(video, output_dir, fps=5)
    print(f"Extracted {len(frames)} frames")

    # Analyze
    results = analyze_color_stability(frames)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Frames analyzed: {results.get('frames_analyzed', 0)}")
    print(f"Color changes: {results.get('total_color_changes', 0)}")
    print(f"Flicker rate: {results.get('flicker_rate', 0):.1%}")
    print(f"Assessment: {results.get('assessment', 'UNKNOWN')}")


if __name__ == "__main__":
    main()
