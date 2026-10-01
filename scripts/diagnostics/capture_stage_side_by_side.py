#!/usr/bin/env python3
"""Build OG-versus-DX per-stage playthrough contact sheets for visual review.

For each requested stage, boots BOTH ROMs from power-on through the identical
scripted route (title -> level select -> stage), screenshots every STEP play
frames, and assembles a two-row contact sheet (OG on top, DX below) with
room/scroll annotations. The ~6% speed difference means late panels drift in
position between rows; the review target is palette/bleed/material
regressions, which do not require pixel alignment.

Runs everything through the guarded single-flight wrapper, one emulator at a
time. Announce on the intercom before running; the Ted lane has slot priority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
MGBA = ROOT / "scripts" / "mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_stage_side_by_side.lua")
DEFAULT_ORIGINAL = ROOT / "rom/Penta Dragon (J).gb"

SHOT = re.compile(
    r"shot frame=(?P<frame>\d+) room=(?P<room>[0-9A-F]{2}) "
    r"scx=(?P<scx>[0-9A-F]{2}) scy=(?P<scy>[0-9A-F]{2}) d880=(?P<scene>[0-9A-F]{2})"
)
GRID = re.compile(
    r"grid frame=(?P<frame>\d+) tiles=(?P<tiles>[0-9A-F]{720}) "
    r"attrs=(?P<attrs>[0-9A-F]{720})"
)
AUDIT = re.compile(
    r"audit frame=(?P<frame>\d+) tiles=(?P<tiles>[0-9A-F]{720}) "
    r"attrs=(?P<attrs>[0-9A-F]{720})"
)

# Later-stage semantic rows are sparse.  In Stage 5, BG1/BG2 are reserved for
# the health/rare pickup faces below; ordinary tiles carrying either palette
# are stale attribute trails, even when the stock grayscale happens to make
# them look like an intentional cast shadow.  This exact failure is visible in
# the r8 patrol at frames 240/480: 02/06/12/15 retain the previous pickup's
# palette while the replacement 88/89/98/99 cells remain on lava BG5.
STAGE5_PICKUP_PALETTES = {
    1: frozenset((0x88, 0x89, 0x96, 0x98, 0x99)),
    2: frozenset((0xAE, 0xAF, 0xBE, 0xBF, 0xC6, 0xC7, 0xD6, 0xD7)),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit_stage_semantic_palettes(stage: int, rows: list[dict]) -> dict:
    """Reject sampled later-stage pickup omissions and detached trails."""
    if stage != 5:
        return {"status": "not-applicable", "failures": []}
    failures: list[str] = []
    for row in rows:
        tiles = bytes.fromhex(row["tilemap_hex"])
        attrs = bytes.fromhex(row["attribute_hex"])
        if len(tiles) != 360 or len(attrs) != 360:
            failures.append(f"f{row['frame']:04d}: malformed visible grid")
            continue
        semantic_tiles = set().union(*STAGE5_PICKUP_PALETTES.values())
        for index, (tile, raw_attr) in enumerate(zip(tiles, attrs)):
            palette = raw_attr & 0x07
            expected = next(
                (slot for slot, members in STAGE5_PICKUP_PALETTES.items()
                 if tile in members),
                None,
            )
            grid = f"r{index // 20:02d}c{index % 20:02d}"
            if expected is not None and palette != expected:
                failures.append(
                    f"f{row['frame']:04d}:{grid}: pickup {tile:02X} "
                    f"uses BG{palette}, expected BG{expected}"
                )
            elif expected is None and palette in STAGE5_PICKUP_PALETTES:
                failures.append(
                    f"f{row['frame']:04d}:{grid}: non-pickup {tile:02X} "
                    f"retains semantic BG{palette}"
                )
            if raw_attr & 0xF8:
                failures.append(
                    f"f{row['frame']:04d}:{grid}: unsafe attr {raw_attr:02X}"
                )
        # Keep the local name alive as an explicit reminder that every
        # declared semantic tile belongs to exactly one palette class.
        assert len(semantic_tiles) == sum(map(len, STAGE5_PICKUP_PALETTES.values()))
    return {
        "status": "pass" if not failures else "fail",
        "sampled_frames": len(rows),
        "failures": failures,
    }


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


def capture(rom: Path, target: int, frames: int, step: int, audit_step: int,
            mode: str, prefix: Path, timeout: float,
            publication_trace: bool) -> tuple[list[dict], list[dict]]:
    prefix.parent.mkdir(parents=True, exist_ok=True)
    for stale in prefix.parent.glob(prefix.name + ".f*.png"):
        stale.unlink()
    marker = Path(str(prefix) + ".done")
    trace = Path(str(prefix) + ".trace")
    marker.unlink(missing_ok=True)
    trace.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(
        SSS_OUT=str(prefix),
        SSS_TARGET=str(target),
        SSS_FRAMES=str(frames),
        SSS_STEP=str(step),
        SSS_AUDIT_STEP=str(audit_step),
        SSS_MODE=mode,
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    if publication_trace:
        env["SSS_PUBLICATION_TRACE"] = str(prefix) + ".publications.tsv"
    process = subprocess.Popen(
        [str(MGBA), "--fastforward",
         "-C", f"savegamePath={prefix.parent}",
         "-C", f"savestatePath={prefix.parent}",
         str(rom), "--script", str(PROBE)],
        cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file() and marker.read_text().strip():
                break
            if process.poll() is not None:
                raise RuntimeError(f"mGBA exited {process.returncode}")
            time.sleep(0.05)
        else:
            raise TimeoutError(f"stage capture timed out: {prefix.name}")
    finally:
        terminate(process)
    status = marker.read_text().strip()
    if status != "ok":
        raise RuntimeError(f"stage capture rejected {prefix.name}: {status}")
    lines = trace.read_text().splitlines()
    audits = [
        {
            "frame": int(match.group("frame")),
            "tilemap_hex": match.group("tiles"),
            "attribute_hex": match.group("attrs"),
        }
        for line in lines
        if (match := AUDIT.fullmatch(line.strip()))
    ]
    grids = {
        int(match.group("frame")): {
            "tilemap_hex": match.group("tiles"),
            "attribute_hex": match.group("attrs"),
        }
        for line in lines
        if (match := AUDIT.fullmatch(line.strip()))
    }
    rows = []
    for line in lines:
        m = SHOT.fullmatch(line.strip())
        if m:
            shot_path = Path(f"{prefix}.f{int(m.group('frame')):04d}.png")
            if shot_path.is_file():
                row = {
                    "frame": int(m.group("frame")),
                    "room": m.group("room"),
                    "scx": m.group("scx"),
                    "scy": m.group("scy"),
                    "png": shot_path,
                    "png_sha256": sha256(shot_path),
                }
                row.update(grids.get(row["frame"], {}))
                rows.append(row)
    if not rows:
        raise RuntimeError(f"no screenshots captured for {prefix.name}")
    missing_grids = [row["frame"] for row in rows if "tilemap_hex" not in row]
    if missing_grids:
        raise RuntimeError(
            f"missing visible tile/attribute grids for {prefix.name}: "
            f"{missing_grids}"
        )
    if not audits:
        raise RuntimeError(f"no visible-map audit samples for {prefix.name}")
    return rows, audits


def assistance_summary(prefix: Path) -> dict:
    """#41 retain the physical-bank assistance totals, including scratch selection."""
    fields = dict(re.findall(r'^(native_assistance_\w+)=(\d+)$',
                             Path(str(prefix)+'.trace').read_text(), re.MULTILINE))
    total = int(fields['native_assistance_writes'])
    counts = {str(bank): int(fields[f'native_assistance_svbk_{bank}'])
              for bank in range(8)}
    if sum(counts.values()) != total:
        raise ValueError('inconsistent native assistance counters')
    return dict(physical_bank=1, writes=total, selected_svbk_counts=counts)


def build_sheet(og: list[dict], dx: list[dict], out: Path, stage: int) -> None:
    frames = sorted({r["frame"] for r in og} & {r["frame"] for r in dx})
    og_by = {r["frame"]: r for r in og}
    dx_by = {r["frame"]: r for r in dx}
    if not frames:
        raise RuntimeError("no aligned frames between OG and DX")
    w, h = Image.open(og_by[frames[0]]["png"]).size
    label_h = 14
    cols = len(frames)
    sheet = Image.new("RGB", (cols * w, 2 * (h + label_h) + label_h), "black")
    draw = ImageDraw.Draw(sheet)
    draw.text((4, 2 * (h + label_h)),
              f"stage {stage + 1}: top=OG bottom=DX, panels labeled frame/room/scx",
              fill="white")
    for col, frame in enumerate(frames):
        for row, src in ((0, og_by[frame]), (1, dx_by[frame])):
            y = row * (h + label_h)
            sheet.paste(Image.open(src["png"]).convert("RGB"), (col * w, y))
            draw.text((col * w + 2, y + h + 1),
                      f"f{frame} r{src['room']} x{src['scx']}",
                      fill="yellow" if row else "cyan")
    sheet.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dx_rom", type=Path)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--stage", action="append", type=int, choices=range(7),
                        help="FFBA target(s); default all 7")
    parser.add_argument("--frames", type=int, default=1200)
    parser.add_argument("--step", type=int, default=60)
    parser.add_argument(
        "--audit-step", type=int, default=1,
        help="sample visible tile/attribute semantics every N play frames",
    )
    parser.add_argument(
        "--publication-trace", action="store_true",
        help="record exact tile-copy decisions and native map flips",
    )
    parser.add_argument("--mode", choices=("right", "patrol"), default="patrol")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    stages = args.stage if args.stage is not None else list(range(7))
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "penta-stage-side-by-side-v1",
        "status": "pass",
        "probe_sha256": sha256(PROBE),
        "verifier_sha256": sha256(Path(__file__)),
        "assistance": "SRAM level select and stage setup; physical bank1 DCFD save flag and DCBB health (#41); no DCDD/DCDC refill (#37)",
        "original_rom_sha256": sha256(args.original.resolve()),
        "dx_rom_sha256": sha256(args.dx_rom.resolve()),
        "frames": args.frames, "step": args.step,
        "audit_step": args.audit_step, "mode": args.mode,
        "stages": {},
    }
    for target in stages:
        stage_dir = args.output / f"stage{target + 1}"
        og, og_audits = capture(
            args.original.resolve(), target, args.frames, args.step,
            args.audit_step, args.mode, stage_dir / "og" / "run",
            args.timeout, args.publication_trace,
        )
        dx, dx_audits = capture(
            args.dx_rom.resolve(), target, args.frames, args.step,
            args.audit_step, args.mode, stage_dir / "dx" / "run",
            args.timeout, args.publication_trace,
        )
        semantic_audit = audit_stage_semantic_palettes(target + 1, dx_audits)
        if semantic_audit["status"] == "fail":
            preview = "; ".join(semantic_audit["failures"][:8])
            raise RuntimeError(
                f"stage {target + 1} semantic palette audit failed: {preview}"
            )
        sheet = args.output / f"stage{target + 1}-side-by-side.png"
        build_sheet(og, dx, sheet, target)
        manifest["stages"][f"stage{target + 1}"] = {
            "native_assistance": {side: assistance_summary(stage_dir/side/'run')
                                  for side in ('og', 'dx')},
            "og_shots": len(og), "dx_shots": len(dx),
            "og_image_sha256": [row["png_sha256"] for row in og],
            "dx_image_sha256": [row["png_sha256"] for row in dx],
            "semantic_palette_audit": semantic_audit,
            "sheet": str(sheet), "sheet_sha256": sha256(sheet),
        }
        print(f"stage {target + 1}: og={len(og)} dx={len(dx)} shots -> {sheet}")
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Manifest: {args.output / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
