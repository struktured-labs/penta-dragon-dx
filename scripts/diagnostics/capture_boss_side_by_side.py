#!/usr/bin/env python3
"""Create a frame-aligned OG-versus-DX boss animation for visual review."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from PIL import Image

from boss_geometry_contract import BOSSES
from generate_stream_boss_states import (
    ARENA_TABLE_BASE,
    BG_TABLE_SIZE,
    PALETTE_ROM_BANK,
    ROM_BANK_SIZE,
    STAGE_PROBE,
    capture_final,
    generate_one,
    generate_safe_stage1,
    patch_state,
)


ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "rom" / "Penta Dragon (J).gb"
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_boss_animation.lua")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def wait_capture(
    rom: Path,
    state: Path,
    prefix: Path,
    scene: int,
    frames: int,
    step: int,
    timeout: float,
) -> int:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for old in prefix.parent.glob(prefix.name + ".f*.png"):
        old.unlink()
    for suffix in (".done", ".trace"):
        Path(str(prefix) + suffix).unlink(missing_ok=True)
    marker = Path(str(prefix) + ".done")
    env = os.environ.copy()
    env.update(
        BOSS_ANIMATION_OUT=str(prefix),
        BOSS_ANIMATION_SCENE=str(scene),
        BOSS_ANIMATION_FRAMES=str(frames),
        BOSS_ANIMATION_STEP=str(step),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [
            str(MGBA), "--fastforward", "-t", str(state),
            "-C", f"savegamePath={prefix.parent}",
            "-C", f"savestatePath={prefix.parent}",
            str(rom), "--script", str(PROBE),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    expected = frames // step
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file() and marker.read_text().strip():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.1)
        else:
            raise TimeoutError(f"animation capture timed out: {prefix.name}")
        status = marker.read_text().strip()
        if status != "ok":
            raise RuntimeError(f"animation capture rejected: {status}")
        flush_deadline = time.monotonic() + 8
        while time.monotonic() < flush_deadline:
            count = len(list(prefix.parent.glob(prefix.name + ".f*.png")))
            if count == expected:
                return count
            time.sleep(0.1)
        raise RuntimeError(f"captured {count}/{expected} frames for {prefix.name}")
    finally:
        terminate(process)


def make_dx_state(rom: Path, output: Path, target: int, timeout: float) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="penta-boss-dx-entry-") as raw:
        staging = Path(raw)
        safe = generate_safe_stage1(str(MGBA), rom, staging, timeout)
        data = rom.read_bytes()
        table_start = (
            PALETTE_ROM_BANK * ROM_BANK_SIZE
            + ARENA_TABLE_BASE + target * BG_TABLE_SIZE - ROM_BANK_SIZE
        )
        generate_one(
            str(MGBA), rom, safe, output, target,
            data[table_start:table_start + BG_TABLE_SIZE], timeout,
        )
    return output / f"boss{target}_{BOSSES[target].name}.ss0"


def generate_safe_stage1_og(rom: Path, output: Path, timeout: float) -> Path:
    """Capture stock Stage 1 without requiring DX-only bookkeeping bytes."""
    prefix = output / "safe_stage1"
    state = prefix.with_suffix(".ss0")
    env = os.environ.copy()
    env.update(
        STAGE_TARGET="0",
        STAGE_OUT=str(prefix),
        STAGE_SHOT="0",
        STAGE_STATE_OUT=str(state),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    result = subprocess.run(
        [
            str(MGBA), "--fastforward",
            "-C", f"savegamePath={output}",
            "-C", f"savestatePath={output}",
            str(rom), "--script", str(STAGE_PROBE),
        ],
        cwd=output,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    meta = prefix.with_suffix(".meta")
    detail = meta.read_text() if meta.is_file() else ""
    required = ("target=0", "expected_scene=02", "D880=02", "FFC1=01", "FFBA=00", "state_saved=true")
    missing = [token for token in required if token not in detail]
    if result.returncode != 0 or not state.is_file() or missing:
        raise RuntimeError(
            "stock Stage 1 fixture failed: " + ", ".join(missing or [f"exit {result.returncode}"])
        )
    return state


def make_og_state(rom: Path, output: Path, target: int, timeout: float) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="penta-boss-og-entry-") as raw:
        staging = Path(raw)
        safe = generate_safe_stage1_og(rom, staging, timeout)
        injected = staging / "injected.ss0"
        patch_state(safe, injected, target)
        prefix = output / f"boss{target}_{BOSSES[target].name}"
        capture_final(str(MGBA), rom, injected, prefix, target, timeout, output)
    return output / f"boss{target}_{BOSSES[target].name}.ss0"


def encode_video(output: Path, seconds: int, sample_rate: int) -> Path:
    video = output / "og-vs-dx.mp4"
    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    rate = 60 / sample_rate
    filter_graph = (
        f"[0:v]scale=640:576:flags=neighbor,pad=640:620:0:44:black,"
        f"drawtext=fontfile={font}:text='ORIGINAL GAME BOY':"
        "fontcolor=white:fontsize=24:x=(w-text_w)/2:y=9[og];"
        f"[1:v]scale=640:576:flags=neighbor,pad=640:620:0:44:black,"
        f"drawtext=fontfile={font}:text='PENTA DRAGON DX':"
        "fontcolor=white:fontsize=24:x=(w-text_w)/2:y=9[dx];"
        "[og][dx]hstack=inputs=2[v]"
    )
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-stream_loop", "-1",
            "-framerate", f"{rate:g}", "-pattern_type", "glob",
            "-i", str(output / "og" / "frame.f*.png"),
            "-stream_loop", "-1",
            "-framerate", f"{rate:g}", "-pattern_type", "glob",
            "-i", str(output / "dx" / "frame.f*.png"),
            "-filter_complex", filter_graph, "-map", "[v]",
            "-t", str(seconds), "-c:v", "libx264", "-crf", "18",
            "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(video),
        ],
        check=True,
    )
    return video


def temporal_landmarks(output: Path, side: str) -> dict[str, int | float | None]:
    """Report low-detail arena frames without claiming what caused them.

    A two-color center/top crop is the useful deterministic landmark for the
    Cameo disappear/reappear phase.  Keeping the metric generic also exposes
    comparable blank or near-blank phases in later boss reviews without
    pretending that independently running OG and DX fixtures are phase-locked.
    """
    frames: list[int] = []
    for path in sorted((output / side).glob("frame.f*.png")):
        frame = int(path.stem.rsplit("f", 1)[1])
        with Image.open(path) as source:
            crop = source.convert("RGB").crop((15, 0, 145, 125))
            if len(set(crop.getdata())) <= 2:
                frames.append(frame)
    first = frames[0] if frames else None
    last = frames[-1] if frames else None
    return {
        "low_detail_frames": len(frames),
        "first_low_detail_frame": first,
        "first_low_detail_seconds": round(first / 60, 3) if first else None,
        "last_low_detail_frame": last,
    }


def write_page(output: Path, target: int, video: Path, receipt: dict) -> Path:
    boss = BOSSES[target]
    cameo_note = ""
    if boss.name == "cameo":
        cameo_note = (
            " Cameo's current table maps its traced animated contour tiles "
            "<code>$0C–$FF</code> to BG1: white, cherry red, deep crimson, "
            "and black."
        )
    og_landmark = receipt["temporal_landmarks"]["og"]
    dx_landmark = receipt["temporal_landmarks"]["dx"]
    landmark_note = (
        "Low-detail arena landmark: "
        f"OG frame {og_landmark['first_low_detail_frame']} "
        f"({og_landmark['first_low_detail_seconds']} s); "
        f"DX frame {dx_landmark['first_low_detail_frame']} "
        f"({dx_landmark['first_low_detail_seconds']} s)."
    )
    page = output / "index.html"
    page.write_text(f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(boss.name.replace('_', ' ').title())}: OG vs DX</title>
<style>body{{margin:0;background:#10131a;color:#edf2ff;font:18px system-ui;padding:28px}}
main{{max-width:1320px;margin:auto}} video{{width:100%;background:#000;border:1px solid #46506a}}
.meta{{color:#aeb9d3}} code{{color:#ffd37a}}</style></head><body><main>
<h1>{html.escape(boss.name.replace('_', ' ').title())} — one-minute OG/DX audit</h1>
<p class="meta">Expected DX material: <strong>{html.escape(boss.material)}</strong>.
{cameo_note}</p>
<video controls autoplay loop muted playsinline src="{html.escape(video.name)}"></video>
<p class="meta">Frame-aligned {receipt['capture_seconds']}-second native window,
repeated to {receipt['seconds']} seconds for close review. The two games run
independently, so animation phases can diverge when their cadence differs.
{landmark_note} Both sides keep player and boss alive only; no pose, palette,
scene, or timing writes are made.</p>
</main></body></html>""")
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dx_rom", type=Path)
    parser.add_argument("--original", type=Path, default=ORIGINAL)
    parser.add_argument("--target", type=int, choices=range(len(BOSSES)), default=3)
    parser.add_argument("--dx-state", type=Path, help="validated DX boss state to reuse")
    parser.add_argument("--og-state", type=Path, help="validated original boss state to reuse")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument(
        "--capture-seconds", type=int,
        help="native source window before repetition (default: --seconds)",
    )
    parser.add_argument("--sample-step", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    dx, original, output = args.dx_rom.resolve(), args.original.resolve(), args.output.resolve()
    if not dx.is_file() or not original.is_file():
        parser.error("both original and DX ROMs must exist")
    output.mkdir(parents=True, exist_ok=True)
    states = output / "states"
    states.mkdir(exist_ok=True)
    dx_state = (
        args.dx_state.resolve()
        if args.dx_state else make_dx_state(dx, states / "dx", args.target, args.timeout)
    )
    og_state = (
        args.og_state.resolve()
        if args.og_state else make_og_state(original, states / "og", args.target, args.timeout)
    )
    for label, state in (("DX", dx_state), ("OG", og_state)):
        if not state.is_file() or state.stat().st_size < 1024:
            parser.error(f"{label} state is missing or invalid: {state}")
    capture_seconds = args.capture_seconds or args.seconds
    frames = capture_seconds * 60
    og_count = wait_capture(
        original, og_state, output / "og" / "frame", BOSSES[args.target].scene,
        frames, args.sample_step, args.timeout,
    )
    dx_count = wait_capture(
        dx, dx_state, output / "dx" / "frame", BOSSES[args.target].scene,
        frames, args.sample_step, args.timeout,
    )
    video = encode_video(output, args.seconds, args.sample_step)
    landmarks = {
        side: temporal_landmarks(output, side)
        for side in ("og", "dx")
    }
    receipt = {
        "status": "pass",
        "boss_index": args.target,
        "boss": BOSSES[args.target].name,
        "scene": f"{BOSSES[args.target].scene:02X}",
        "expected_material": BOSSES[args.target].material,
        "seconds": args.seconds,
        "capture_seconds": capture_seconds,
        "sample_step": args.sample_step,
        "og_frames": og_count,
        "dx_frames": dx_count,
        "temporal_landmarks": landmarks,
        "original_sha256": digest(original),
        "dx_sha256": digest(dx),
        "video_sha256": digest(video),
    }
    page = write_page(output, args.target, video, receipt)
    print(f"PASS: {og_count} OG + {dx_count} DX frames; {video}")
    print(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
