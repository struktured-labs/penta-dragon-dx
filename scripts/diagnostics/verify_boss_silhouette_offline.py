#!/usr/bin/env python3
"""Offline silhouette checks for boss corruption missed by palette LUT gates.

This verifier never starts an emulator.  It consumes an already captured
160x144 frame and detects two observed failure modes:

* Troop artwork copied into the checker field below the boss.
* Detached Penta Dragon fragments outside the connected body silhouette.

The contracts deliberately describe geometry, not RGB palette choices, so a
palette tuning session cannot make a corrupt frame pass by changing colors.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACTS = ROOT / "docs/audit/boss_silhouette_contracts.json"


def normalized_cell_signature(image: Image.Image, row: int, col: int,
                              cell_size: int) -> tuple[int, ...]:
    """Return a color-name-independent partition of one tile-sized cell."""
    labels: dict[tuple[int, int, int], int] = {}
    result: list[int] = []
    for y in range(row * cell_size, (row + 1) * cell_size):
        for x in range(col * cell_size, (col + 1) * cell_size):
            color = image.getpixel((x, y))
            if color not in labels:
                labels[color] = len(labels)
            result.append(labels[color])
    return tuple(result)


def analyze_troop(image: Image.Image, contract: dict[str, object]) -> dict[str, object]:
    cell = int(contract["cell_size"])
    if image.size != (160, 144) or image.width % cell or image.height % cell:
        raise ValueError(f"Troop receipt must be 160x144, got {image.size}")
    rows, cols = image.height // cell, image.width // cell
    signatures = {
        (row, col): normalized_cell_signature(image, row, col, cell)
        for row in range(rows) for col in range(cols)
    }
    counts = Counter(signatures.values())
    minimum = int(contract["minimum_repeated_background_cells"])
    minimum_colors = int(contract["minimum_cell_colors"])
    background = {
        signature for signature, count in counts.items()
        if count >= minimum and len(set(signature)) >= minimum_colors
    }
    if not background:
        raise AssertionError("Troop checker background was not observed")

    foreign: list[list[int]] = []
    sampled = 0
    for top, bottom, left, right in contract["clear_rectangles"]:
        for row in range(top, bottom):
            for col in range(left, right):
                sampled += 1
                if signatures[(row, col)] not in background:
                    foreign.append([row, col])
    limit = int(contract["maximum_foreign_cells"])
    return {
        "status": "pass" if len(foreign) <= limit else "fail",
        "boss": "troop",
        "contract": contract["kind"],
        "sampled_clear_cells": sampled,
        "repeated_background_signatures": len(background),
        "foreign_cells": len(foreign),
        "foreign_examples": foreign[:24],
        "limit": limit,
    }


def in_rectangles(x: int, y: int, rectangles: list[list[int]]) -> bool:
    return any(top <= y < bottom and left <= x < right
               for top, bottom, left, right in rectangles)


def foreground_components(image: Image.Image, background: tuple[int, int, int],
                          ignored: list[list[int]]) -> list[list[tuple[int, int]]]:
    foreground = {
        (x, y)
        for y in range(image.height)
        for x in range(image.width)
        if image.getpixel((x, y)) != background and not in_rectangles(x, y, ignored)
    }
    components: list[list[tuple[int, int]]] = []
    while foreground:
        seed = foreground.pop()
        pending = [seed]
        component = [seed]
        while pending:
            x, y = pending.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    neighbor = (x + dx, y + dy)
                    if neighbor in foreground:
                        foreground.remove(neighbor)
                        pending.append(neighbor)
                        component.append(neighbor)
        components.append(component)
    return sorted(components, key=len, reverse=True)


def analyze_penta(image: Image.Image, contract: dict[str, object]) -> dict[str, object]:
    if image.size != (160, 144):
        raise ValueError(f"Penta Dragon receipt must be 160x144, got {image.size}")
    background = Counter(image.getdata()).most_common(1)[0][0]
    components = foreground_components(
        image, background, list(contract["ignored_rectangles"]),
    )
    low = int(contract["minimum_fragment_pixels"])
    high = int(contract["maximum_fragment_pixels"])
    # The largest component is the dragon. Medium independent islands are the
    # observed copied-head/confetti failure; tiny raster islands are tolerated.
    fragments = [component for component in components[1:] if low <= len(component) <= high]
    examples = []
    for component in fragments[:16]:
        xs = [point[0] for point in component]
        ys = [point[1] for point in component]
        examples.append({
            "pixels": len(component),
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
        })
    limit = int(contract["maximum_detached_fragments"])
    return {
        "status": "pass" if len(fragments) <= limit else "fail",
        "boss": "penta_dragon",
        "contract": contract["kind"],
        "foreground_components": len(components),
        "largest_component_pixels": len(components[0]) if components else 0,
        "detached_fragments": len(fragments),
        "fragment_examples": examples,
        "limit": limit,
    }


def load_contract(path: Path, boss: str) -> dict[str, object]:
    payload = json.loads(path.read_text())
    if payload.get("schema") != "penta-dragon-dx-boss-silhouette-v1":
        raise ValueError(f"unsupported silhouette contract schema in {path}")
    return payload["contracts"][boss]


def analyze_image(image_path: Path, boss: str, contract_path: Path) -> dict[str, object]:
    image = Image.open(image_path).convert("RGB")
    contract = load_contract(contract_path, boss)
    result = analyze_troop(image, contract) if boss == "troop" else analyze_penta(image, contract)
    result.update({
        "image": str(image_path.resolve()),
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
    })
    return result


def aggregate_gallery_rows(
    boss: str, rows: list[dict[str, object]], contract: dict[str, object]
) -> dict[str, object]:
    """Gate a phase corpus against stock-derived bounds, not frame alignment."""

    if boss == "troop":
        counts = [int(row["foreign_cells"]) for row in rows]
        mean = sum(counts) / len(counts) if counts else float("inf")
        peak = max(counts, default=10**9)
        mean_limit = float(contract["gallery_maximum_mean_foreign_cells"])
        peak_limit = int(contract["gallery_maximum_peak_foreign_cells"])
        passed = mean <= mean_limit + 1e-9 and peak <= peak_limit
        return {
            "boss": boss,
            "status": "pass" if passed else "fail",
            "sampled_phases": len(counts),
            "mean_foreign_cells": mean,
            "maximum_foreign_cells": peak,
            "mean_limit": mean_limit,
            "peak_limit": peak_limit,
        }

    fragments = [int(row["detached_fragments"]) for row in rows]
    clean = sum(value == 0 for value in fragments)
    peak = max(fragments, default=10**9)
    clean_minimum = int(contract["gallery_minimum_clean_phases"])
    peak_limit = int(contract["gallery_maximum_peak_detached_fragments"])
    passed = clean >= clean_minimum and peak <= peak_limit
    return {
        "boss": boss,
        "status": "pass" if passed else "fail",
        "sampled_phases": len(fragments),
        "clean_phases": clean,
        "clean_phase_minimum": clean_minimum,
        "maximum_detached_fragments": peak,
        "peak_limit": peak_limit,
    }


def analyze_gallery(
    gallery: Path, frames: int, contract_path: Path
) -> dict[str, object]:
    """Require clean silhouettes only at stock-qualified gallery phases."""
    rows: list[dict[str, object]] = []
    aggregates: list[dict[str, object]] = []
    phase_counts: dict[str, int] = {}
    for target, boss in ((5, "troop"), (8, "penta_dragon")):
        prefix = gallery / f"boss{target}_{boss}"
        contract = load_contract(contract_path, boss)
        fractions = contract.get("gallery_phase_fractions")
        if not isinstance(fractions, list) or not fractions:
            raise ValueError(f"{boss}: missing gallery_phase_fractions")
        selected_frames = tuple(round(frames * float(value)) for value in fractions)
        if any(frame <= 0 or frame > frames for frame in selected_frames):
            raise ValueError(f"{boss}: invalid gallery phase fraction")
        phase_counts[boss] = len(selected_frames)
        for frame in selected_frames:
            image = Path(
                f"{prefix}.f{frame:03d}.png"
                if frame != frames else f"{prefix}.png"
            )
            if not image.is_file():
                rows.append({
                    "status": "fail", "boss": boss, "frame": frame,
                    "image": str(image.resolve()), "error": "missing image",
                })
                continue
            row = analyze_image(image, boss, contract_path)
            row["strict_phase_status"] = row.pop("status")
            row["frame"] = frame
            rows.append(row)
        boss_rows = [row for row in rows if row.get("boss") == boss]
        if len(boss_rows) == len(selected_frames):
            aggregates.append(aggregate_gallery_rows(boss, boss_rows, contract))
    expected_images = sum(phase_counts.values())
    passed = (
        len(rows) == expected_images
        and len(aggregates) == 2
        and all(row.get("status") == "pass" for row in aggregates)
    )
    return {
        "schema": "penta-dragon-dx-boss-silhouette-gallery-v1",
        "status": "pass" if passed else "fail",
        "gallery": str(gallery.resolve()),
        "stock_qualified_phases_per_boss": phase_counts,
        "image_count": len(rows),
        "bosses": ["troop", "penta_dragon"],
        "results": rows,
        "phase_corpus_contracts": aggregates,
        "failures": [
            f"{row.get('boss')}: phase corpus {row.get('status')}"
            for row in aggregates if row.get("status") != "pass"
        ] + [
            f"{row.get('boss')}@{row.get('frame')}: {row.get('error')}"
            for row in rows if row.get("error")
        ],
    }


def self_test(contract_path: Path) -> None:
    troop_contract = load_contract(contract_path, "troop")
    penta_contract = load_contract(contract_path, "penta_dragon")
    with tempfile.TemporaryDirectory(prefix="boss-silhouette-", dir=ROOT / "tmp") as directory:
        directory = Path(directory)
        checker = Image.new("RGB", (160, 144))
        draw = ImageDraw.Draw(checker)
        for y in range(144):
            for x in range(160):
                shade = 255 if ((x // 4) + (y // 4)) & 1 else 170
                checker.putpixel((x, y), (shade, shade, shade))
        draw.rectangle((24, 0, 135, 87), fill=(20, 20, 20))
        draw.rectangle((72, 128, 87, 143), fill=(40, 40, 40))
        assert analyze_troop(checker, troop_contract)["status"] == "pass"
        draw.rectangle((0, 104, 15, 119), fill=(20, 20, 20))
        assert analyze_troop(checker, troop_contract)["status"] == "fail"

        penta = Image.new("RGB", (160, 144), (0, 0, 0))
        draw = ImageDraw.Draw(penta)
        draw.rectangle((24, 8, 135, 79), fill=(220, 20, 20))
        draw.rectangle((72, 128, 87, 143), fill=(255, 255, 255))
        assert analyze_penta(penta, penta_contract)["status"] == "pass"
        draw.rectangle((145, 32, 150, 37), fill=(20, 220, 20))
        assert analyze_penta(penta, penta_contract)["status"] == "fail"
        assert aggregate_gallery_rows(
            "troop",
            [{"foreign_cells": value} for value in (13, 12)],
            troop_contract,
        )["status"] == "pass"
        assert aggregate_gallery_rows(
            "troop",
            [{"foreign_cells": value} for value in (21, 21)],
            troop_contract,
        )["status"] == "fail"
        assert aggregate_gallery_rows(
            "penta_dragon",
            [{"detached_fragments": value} for value in (3, 2, 0, 0)],
            penta_contract,
        )["status"] == "pass"
        assert aggregate_gallery_rows(
            "penta_dragon",
            [{"detached_fragments": value} for value in (4, 2, 1, 0)],
            penta_contract,
        )["status"] == "fail"
    print("PASS: offline boss silhouette controls")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--boss", choices=("troop", "penta_dragon"))
    parser.add_argument("--image", type=Path)
    parser.add_argument("--gallery", type=Path)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test(args.contracts.resolve())
        return 0
    if args.gallery is not None:
        result = analyze_gallery(
            args.gallery.resolve(), args.frames, args.contracts.resolve()
        )
        text = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text)
        print(text, end="")
        return 0 if result["status"] == "pass" else 1
    if args.boss is None or args.image is None:
        parser.error(
            "--boss and --image, --gallery, or --self-test is required"
        )
    result = analyze_image(args.image.resolve(), args.boss, args.contracts.resolve())
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
