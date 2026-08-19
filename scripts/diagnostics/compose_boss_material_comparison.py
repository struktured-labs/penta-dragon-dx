#!/usr/bin/env python3
"""Compose four-phase OG/DX boss galleries without launching an emulator."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from boss_geometry_contract import BOSSES


SCHEMA = "penta-boss-material-side-by-side-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_path(gallery: Path, target: int, name: str, frame: int,
               frames: int) -> Path:
    prefix = gallery / f"boss{target}_{name}"
    return Path(
        f"{prefix}.f{frame:03d}.png" if frame != frames else f"{prefix}.png"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--og", type=Path, required=True)
    parser.add_argument("--dx", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    og, dx = args.og.resolve(), args.dx.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for gallery in (og, dx):
        report = gallery / "report.json"
        if not report.is_file():
            parser.error(f"missing gallery report: {report}")
        payload = json.loads(report.read_text())
        if payload.get("boss_count") != len(BOSSES):
            parser.error(f"incomplete gallery report: {report}")

    phases = (
        args.frames // 4, args.frames // 2,
        args.frames * 3 // 4, args.frames,
    )
    rows: list[dict[str, object]] = []
    for target, boss in enumerate(BOSSES):
        paths = {
            side: [
                image_path(gallery, target, boss.name, frame, args.frames)
                for frame in phases
            ]
            for side, gallery in (("og", og), ("dx", dx))
        }
        missing = [
            str(path) for side_paths in paths.values()
            for path in side_paths if not path.is_file()
        ]
        if missing:
            parser.error("missing boss phase image(s): " + ", ".join(missing))
        width, height = Image.open(paths["og"][0]).size
        label = 18
        sheet = Image.new("RGB", (4 * width, 2 * (height + label)), "black")
        draw = ImageDraw.Draw(sheet)
        image_receipts = []
        for row_index, side in enumerate(("og", "dx")):
            for col, (frame, path) in enumerate(zip(phases, paths[side], strict=True)):
                x, y = col * width, row_index * (height + label)
                with Image.open(path) as source:
                    sheet.paste(source.convert("RGB"), (x, y))
                draw.text(
                    (x + 2, y + height + 2),
                    f"{side.upper()} f{frame}",
                    fill="cyan" if side == "og" else "yellow",
                )
                image_receipts.append({
                    "side": side, "frame": frame,
                    "path": str(path), "sha256": sha256(path),
                })
        destination = output / f"boss{target}_{boss.name}-side-by-side.png"
        sheet.save(destination)
        rows.append({
            "target": target,
            "boss": boss.name,
            "scene": f"{boss.scene:02X}",
            "expected_material": boss.material,
            "sheet": str(destination),
            "sheet_sha256": sha256(destination),
            "images": image_receipts,
        })
        print(f"{boss.name}: {destination}")

    receipt = {
        "schema": SCHEMA,
        "status": "pass",
        "boss_count": len(rows),
        "phases_per_side": len(phases),
        "frames": args.frames,
        "og_gallery": str(og),
        "dx_gallery": str(dx),
        "og_report_sha256": sha256(og / "report.json"),
        "dx_report_sha256": sha256(dx / "report.json"),
        "bosses": rows,
    }
    (output / "report.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(output / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
