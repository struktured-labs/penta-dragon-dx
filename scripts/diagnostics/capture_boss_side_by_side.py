#!/usr/bin/env python3
"""Create an equal-duration OG-versus-DX boss animation for visual review."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from PIL import Image, ImageDraw
import yaml

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
PALETTE_YAML = ROOT / "palettes" / "penta_palettes_v097.yaml"

# Rows that are expected to be visible in each arena. Keep the names tied to
# the tuneable YAML rather than duplicating color bytes in this receipt tool.
BOSS_PALETTE_ROWS = {
    "shalamar": (("bg_palettes", "Dungeon"), ("bg_palettes", "BG4"), ("bg_palettes", "BG5")),
    "riff": (("bg_palettes", "BG2"),),
    "crystal_dragon": (("bg_palettes", "BG4"), ("boss_palettes", "Boss4_Ice")),
    "cameo": (("bg_palettes", "BG1"),),
    "ted": tuple(
        ("bg_palettes", name)
        for name in ("Dungeon", "BG3", "BG4", "BG5", "BG6")
    ),
    "troop": (("bg_palettes", "Dungeon"), ("bg_palettes", "BG7")),
    "faze": (("bg_palettes", "Dungeon"), ("bg_palettes", "BG1"), ("bg_palettes", "BG2"), ("bg_palettes", "BG6")),
    "angela": (("bg_palettes", "Dungeon"), ("bg_palettes", "BG1"), ("bg_palettes", "BG2"), ("bg_palettes", "BG7")),
    "penta_dragon": tuple(("bg_palettes", name) for name in ("Dungeon", "BG1", "BG2", "BG3", "BG4", "BG5")),
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bgr555_to_css(raw: str) -> str:
    value = int(raw, 16)
    channels = (value & 31, (value >> 5) & 31, (value >> 10) & 31)
    return "#" + "".join(f"{round(channel * 255 / 31):02x}" for channel in channels)


def expected_palette_rows(boss_name: str) -> list[dict[str, object]]:
    document = yaml.safe_load(PALETTE_YAML.read_text())
    rows = []
    for section, name in BOSS_PALETTE_ROWS[boss_name]:
        colors = document[section][name]["colors"]
        rows.append({
            "source": f"{section}.{name}",
            "bgr555": colors,
            "rgb": [bgr555_to_css(color) for color in colors],
        })
    return rows


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
    *,
    stock_rom: bool,
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
        BOSS_ANIMATION_STOCK_ROM="1" if stock_rom else "0",
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
    (ROOT / "tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="penta-boss-dx-entry-", dir=ROOT / "tmp"
    ) as raw:
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
    (ROOT / "tmp").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="penta-boss-og-entry-", dir=ROOT / "tmp"
    ) as raw:
        staging = Path(raw)
        safe = generate_safe_stage1_og(rom, staging, timeout)
        injected = staging / "injected.ss0"
        patch_state(safe, injected, target, stock_rom=True)
        prefix = output / f"boss{target}_{BOSSES[target].name}"
        capture_final(
            str(MGBA), rom, injected, prefix, target, timeout, output,
            stock_rom=True,
        )
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


def build_contact_sheet(output: Path, capture_seconds: int, sample_step: int) -> Path:
    """Build twelve evenly spaced OG/DX pairs from the captured native run."""
    pair_width, image_height, label_height = 320, 144, 22
    sheet = Image.new("RGB", (pair_width * 3, (image_height + label_height) * 4))
    draw = ImageDraw.Draw(sheet)
    for index in range(12):
        requested = round((index + 1) * capture_seconds * 60 / 12)
        frame = max(sample_step, requested - requested % sample_step)
        row, column = divmod(index, 3)
        x, y = column * pair_width, row * (image_height + label_height)
        for side_index, side in enumerate(("og", "dx")):
            path = output / side / f"frame.f{frame:04d}.png"
            with Image.open(path) as source:
                sheet.paste(source.convert("RGB"), (x + side_index * 160, y))
        draw.rectangle(
            (x, y + image_height, x + pair_width, y + image_height + label_height),
            fill="black",
        )
        draw.text(
            (x + 3, y + image_height + 4),
            f"OG | DX   {frame / 60:.1f}s",
            fill="white",
        )
    destination = output / "contact-sheet.png"
    sheet.save(destination)
    return destination


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


def ted_rendered_containment(frame_dir: Path) -> dict[str, object]:
    """Require Ted's thin expansion while rejecting duplicate shell debris.

    The legitimate tentacles reach the far-left band, so mere edge occupancy
    is not corruption. Their thin animation contributes 40--150 warm pixels;
    the deleted-animation regression stays below 40, while a copied chunk of
    shell exceeds 150. Scan every native frame and require the expansion to
    occur at least once.
    """
    violations: list[dict[str, object]] = []
    max_left_band_warm = 0
    expansion_frames = 0
    frames = 0
    for path in sorted(frame_dir.glob("frame.f*.png")):
        frames += 1
        with Image.open(path) as source:
            image = source.convert("RGB")
            warm = []
            for y in range(130):
                for x in range(160):
                    red, green, blue = image.getpixel((x, y))
                    if (
                        (red >= 140 and red > green * 1.35 and red > blue * 1.2)
                        or (red >= 220 and green >= 180 and blue < 80)
                    ):
                        warm.append((x, y))
        if not warm:
            violations.append({"frame": path.name, "kind": "missing-body"})
            continue
        left_band_warm = sum(x < 25 for x, _y in warm)
        bridge_band_warm = sum(25 <= x < 40 for x, _y in warm)
        max_left_band_warm = max(max_left_band_warm, left_band_warm)
        if left_band_warm >= 40:
            expansion_frames += 1
        # Ted's whole body legitimately scrolls through the left band, where
        # it can contribute well over 1,000 warm pixels. Only call it detached
        # shell debris when that mass lacks a warm bridge back toward the main
        # body. The former absolute >150 rule rejected clean native poses.
        if left_band_warm > 150 and bridge_band_warm < 40:
            violations.append({
                "frame": path.name,
                "kind": "duplicate-shell-left-edge",
                "left_band_warm_pixels": left_band_warm,
                "bridge_band_warm_pixels": bridge_band_warm,
            })
    if expansion_frames == 0:
        violations.append({"kind": "missing-tentacle-expansion"})
    return {
        "status": "pass" if not violations else "fail",
        "frames": frames,
        "max_left_band_warm_pixels": max_left_band_warm,
        "tentacle_expansion_frames": expansion_frames,
        "violations": violations[:24],
        "violation_count": len(violations),
    }


def ted_trace_contract(trace_path: Path) -> dict[str, object]:
    """Enforce smooth, contained, palette-owned Ted geometry."""
    frames = []
    violations = []
    palette_union = [0] * 8
    sparse_palette_union = [0] * 8
    sparse_counts = []
    for line in trace_path.read_text().splitlines():
        if not line.startswith("frame="):
            continue
        fields = dict(re.findall(r"([a-z0-9_]+)=([^ ]*)", line))
        crown = fields.get("crown", "-1,-1").split(",")
        body_palettes = [int(value) for value in fields["body_palettes"].split(",")]
        sparse_palettes = [int(value) for value in fields["sparse_palettes"].split(",")]
        for index, value in enumerate(body_palettes):
            palette_union[index] += value
        for index, value in enumerate(sparse_palettes):
            sparse_palette_union[index] += value
        frame = {
            "number": int(fields["frame"]),
            "crown": (int(crown[0]), int(crown[1])),
            "scx": int(fields["scx"], 16),
            "scy": int(fields["scy"], 16),
            "sparse": int(fields["sparse"]),
            "body_cells": sum(body_palettes),
            "svbk": int(fields["svbk"]),
        }
        sparse_counts.append(frame["sparse"])
        frames.append(frame)
        mismatches = int(fields["body_mismatches"])
        # OG retains 114-117 canonical numbered body cells throughout the
        # one-minute Ted corpus. A missing crown previously bypassed the
        # mismatch check entirely, allowing 24-cell partial bodies to pass.
        if frame["body_cells"] < 114:
            violations.append({
                "kind": "incomplete-body",
                "frame": frame["number"],
                "cells": frame["body_cells"],
                "crown": frame["crown"],
            })
        if mismatches:
            violations.append({
                "kind": "detached-numbered-body",
                "frame": frame["number"],
                "cells": mismatches,
            })
        for kind in ("bank1", "priority", "flipped"):
            if int(fields[kind]):
                violations.append({
                    "kind": f"unexpected-attr-{kind}",
                    "frame": frame["number"],
                    "cells": int(fields[kind]),
                })
        if sum(body_palettes) and any(
            body_palettes[index] for index in (0, 3, 4, 6, 7)
        ):
            violations.append({
                "kind": "body-palette-outside-yaml-materials",
                "frame": frame["number"],
                "histogram": body_palettes,
            })
        if sum(sparse_palettes) and any(
            sparse_palettes[index] for index in (0, 3, 4, 6, 7)
        ):
            violations.append({
                "kind": "tendril-palette-outside-yaml-materials",
                "frame": frame["number"],
                "histogram": sparse_palettes,
            })

    max_jump = 0
    for previous, current in zip(frames, frames[1:]):
        if current["number"] != previous["number"] + 1:
            continue
        # D000-DFFF is banked. During the private publisher's SVBK2 window,
        # crown/map-selector bytes are cache data rather than game state; a
        # physical-map handoff then looks like a false 31-33 px teleport.
        # Palette/geometry checks above intentionally still inspect those
        # rendered frames, but motion continuity uses stable bank-1 samples.
        if previous["svbk"] != 1 or current["svbk"] != 1:
            continue
        if min(*previous["crown"], *current["crown"]) < 0:
            continue
        old_x = (previous["crown"][1] * 8 - previous["scx"]) & 0xFF
        old_y = (previous["crown"][0] * 8 - previous["scy"]) & 0xFF
        new_x = (current["crown"][1] * 8 - current["scx"]) & 0xFF
        new_y = (current["crown"][0] * 8 - current["scy"]) & 0xFF
        jump = max(
            abs((new_x - old_x + 128) % 256 - 128),
            abs((new_y - old_y + 128) % 256 - 128),
        )
        max_jump = max(max_jump, jump)
        if jump > 1:
            violations.append({
                "kind": "teleport",
                "frame": current["number"],
                "pixels": jump,
            })
    sparse_transitions = sum(
        left != right for left, right in zip(sparse_counts, sparse_counts[1:])
    )
    if sparse_transitions < 2:
        violations.append({
            "kind": "insufficient-tendril-animation",
            "transitions": sparse_transitions,
        })
    missing_palettes = [
        palette for palette in (1, 2, 5) if palette_union[palette] == 0
    ]
    if missing_palettes:
        violations.append({
            "kind": "missing-body-material-palettes",
            "palettes": missing_palettes,
        })
    return {
        "status": "pass" if not violations else "fail",
        "frames": len(frames),
        "max_screen_jump_pixels": max_jump,
        "minimum_body_cells": min(
            (frame["body_cells"] for frame in frames), default=0
        ),
        "crown_absent_frames": sum(
            frame["crown"][0] < 0 for frame in frames
        ),
        "sparse_transitions": sparse_transitions,
        "body_palette_histogram": palette_union,
        "tendril_palette_histogram": sparse_palette_union,
        "violation_count": len(violations),
        "violations": violations[:24],
    }


def write_page(output: Path, target: int, video: Path, receipt: dict) -> Path:
    boss = BOSSES[target]
    receipt["expected_palette_rows"] = expected_palette_rows(boss.name)
    palette_rows = []
    for row in receipt["expected_palette_rows"]:
        swatches = "".join(
            f'<span class="swatch" style="background:{color}" '
            f'title="{html.escape(raw)} / {html.escape(color)}"></span>'
            for raw, color in zip(row["bgr555"], row["rgb"], strict=True)
        )
        palette_rows.append(
            f'<li><code>{html.escape(row["source"])}</code> {swatches} '
            f'<span class="values">{html.escape(" · ".join(row["bgr555"]))}</span></li>'
        )
    cameo_note = ""
    if boss.name == "cameo":
        cameo_note = (
            " Cameo's current table maps its traced animated contour tiles "
            "<code>$0C–$FF</code> to BG1: white, cherry red, deep crimson, "
            "and black."
        )
    elif boss.name == "ted":
        cameo_note = (
            " Ted is WIP: the bounded body table must keep all scrolling "
            "terrain neutral while covering the cyan shell rim, blue-gray "
            "sphere, orange core, and green lower tendrils. The small green "
            "shots are separate OBJ projectiles."
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
    geometry_note = ""
    geometry_path = output / "geometry.json"
    if geometry_path.is_file():
        geometry = json.loads(geometry_path.read_text())
        result = geometry.get("bosses", {}).get(boss.name, {})
        if result:
            geometry_note = (
                '<p class="meta"><strong>Strict geometry receipt:</strong> '
                f'{result.get("frames", 0)} frames, '
                f'{result.get("samples", 0):,} visible samples, '
                f'{result.get("contract_mismatches", 0)} contract mismatches. '
                '<a href="geometry.json">Open JSON</a>.</p>'
            )
    contact_link = (
        '<a href="contact-sheet.png">Open the 12-phase contact sheet</a> · '
        if (output / "contact-sheet.png").is_file() else ""
    )
    page = output / "index.html"
    page.write_text(f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{html.escape(boss.name.replace('_', ' ').title())}: OG vs DX</title>
<style>body{{margin:0;background:#10131a;color:#edf2ff;font:18px system-ui;padding:28px}}
main{{max-width:1320px;margin:auto}} video{{width:100%;background:#000;border:1px solid #46506a}}
.meta{{color:#aeb9d3}} code{{color:#ffd37a}} ul{{padding-left:1.4em}} .swatch{{display:inline-block;
width:1.25em;height:1.25em;margin:0 .12em;vertical-align:-.28em;border:1px solid #77819a}}
.values{{font:14px ui-monospace,monospace;color:#aeb9d3}}</style></head><body><main>
<h1>{html.escape(boss.name.replace('_', ' ').title())} — one-minute OG/DX audit</h1>
<p class="meta">Expected DX material: <strong>{html.escape(boss.material)}</strong>.
{cameo_note}</p>
<p class="meta">Expected tuneable rows from <code>palettes/penta_palettes_v097.yaml</code>:</p>
<ul>{''.join(palette_rows)}</ul>
<video controls autoplay loop muted playsinline src="{html.escape(video.name)}"></video>
{geometry_note}
<p class="meta">Equal-duration {receipt['capture_seconds']}-second native window,
repeated to {receipt['seconds']} seconds for close review. The two games use
independently generated states and are <strong>not phase-synchronized</strong>;
this video cannot by itself prove a timing lead or lag.
{landmark_note} Both sides keep player and boss alive only; no pose, palette,
scene, or timing writes are made.</p>
<p class="meta">{contact_link}<a href="receipt.json">Open capture receipt</a>.</p>
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
        frames, args.sample_step, args.timeout, stock_rom=True,
    )
    dx_count = wait_capture(
        dx, dx_state, output / "dx" / "frame", BOSSES[args.target].scene,
        frames, args.sample_step, args.timeout, stock_rom=False,
    )
    rendered_containment = None
    trace_contract = None
    if args.target == 4:
        rendered_containment = ted_rendered_containment(output / "dx")
        if rendered_containment["status"] != "pass":
            raise RuntimeError(
                "Ted rendered-containment gate failed: "
                + json.dumps(rendered_containment, sort_keys=True)
            )
        trace_contract = ted_trace_contract(output / "dx" / "frame.trace")
        if trace_contract["status"] != "pass":
            raise RuntimeError(
                "Ted trace contract failed: "
                + json.dumps(trace_contract, sort_keys=True)
            )
    video = encode_video(output, args.seconds, args.sample_step)
    contact_sheet = build_contact_sheet(output, capture_seconds, args.sample_step)
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
        "phase_synchronized": False,
        "timing_claim": False,
        "sample_step": args.sample_step,
        "og_frames": og_count,
        "dx_frames": dx_count,
        "temporal_landmarks": landmarks,
        "rendered_containment": rendered_containment,
        "ted_trace_contract": trace_contract,
        "original_sha256": digest(original),
        "dx_sha256": digest(dx),
        "video_sha256": digest(video),
        "contact_sheet_sha256": digest(contact_sheet),
    }
    page = write_page(output, args.target, video, receipt)
    print(f"PASS: {og_count} OG + {dx_count} DX frames; {video}")
    print(page)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
