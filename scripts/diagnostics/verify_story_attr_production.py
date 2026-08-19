#!/usr/bin/env python3
"""Gate ROM-native OPENING/final-story/ending palette attributes in mGBA."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from bg_experiment import load_palettes_from_yaml  # noqa: E402
from cutscene_region_palettes import (  # noqa: E402
    load_cutscene_region_palettes,
    panel_mask,
)

DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_STATES = ROOT / "tmp/palette_session/story_states"
DEFAULT_PALETTES = ROOT / "palettes/penta_palettes_v097.yaml"
PROBE = Path(__file__).with_name("probe_story_attr_production.lua")
SPECS = (
    ("opening", "neutral", 0, 0x15, {}),
    ("opening_book", "story", 1, 0x15, {"SEQUENCE": 0x02}),
    ("opening_sara", "story", 2, 0x15, {"SEQUENCE": 0x02}),
    ("opening_dragon_eye", "story", 3, 0x15, {"SEQUENCE": 0x02}),
    ("pre_final", "story", 4, 0x19, {"SEQUENCE": 0x04}),
    ("pre_final_sara", "story", 7, 0x19, {"SEQUENCE": 0x04}),
    ("post_final", "story", 5, 0x1A, {"SEQUENCE": 0x05}),
    ("post_final_lisa", "story", 6, 0x1A, {"SEQUENCE": 0x05}),
    # This stock post-final page auto-advances 167 frames after the generated
    # state resumes.  Audit 140 continuous frames: comfortably beyond the
    # independent 60-frame clean-load contract, but before the intentional
    # page transition.  All layout/CRAM/safety checks remain unchanged.
    (
        "post_final_sara", "story", 7, 0x1A,
        {"SEQUENCE": 0x05, "WAIT": 140},
    ),
    (
        "ending_credits", "ending", 1, 0x16,
        {"D889": 0x01, "DCE2": 0x00, "FFF9": 0x00, "WAIT": 140},
    ),
    (
        "ending_end", "ending", 2, 0x16,
        {"D889": 0x01, "DCE2": 0x00, "FFF9": 0x01, "WAIT": 140},
    ),
    (
        "ending_epilogue", "ending", 3, 0x00,
        {"D889": 0x0C, "DCE2": 0x01, "FFF9": 0x01, "WAIT": 180},
    ),
)


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        field.split("=", 1)
        for field in path.read_text().split()
        if "=" in field
    )


def terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def write_contact_sheet(
    output: Path,
    results: list[dict[str, object]],
) -> Path | None:
    """Render the native mGBA receipts in stable manifest order."""
    if not results:
        return None
    columns = min(4, len(results))
    rows = (len(results) + columns - 1) // columns
    label_height = 18
    sheet = Image.new("RGB", (columns * 160, rows * (144 + label_height)))
    draw = ImageDraw.Draw(sheet)
    for index, result in enumerate(results):
        x = (index % columns) * 160
        y = (index // columns) * (144 + label_height)
        with Image.open(str(result["screenshot"])) as capture:
            sheet.paste(capture.convert("RGB"), (x, y))
        draw.rectangle((x, y + 144, x + 159, y + 161), fill=(16, 16, 16))
        draw.text((x + 3, y + 147), str(result["state"]), fill=(255, 255, 255))
    path = output / "contact-sheet.png"
    sheet.save(path)
    return path


def screenshot_metrics(path: Path) -> dict[str, int | float]:
    """Measure the rendered frame, independently of its tile attributes."""
    with Image.open(path) as source:
        image = source.convert("RGB")
        if image.size != (160, 144):
            raise RuntimeError(
                f"{path.name} screenshot is {image.size}, expected 160x144"
            )
        colors = image.getcolors(maxcolors=160 * 144)
        chromatic = sum(
            max(pixel) - min(pixel) >= 24 for pixel in image.getdata()
        )
    if not colors:
        raise RuntimeError(f"{path.name} has an invalid color histogram")
    pixels = 160 * 144
    dominant = max(count for count, _color in colors)
    return {
        "distinct_colors": len(colors),
        "dominant_pixels": dominant,
        "non_dominant_pixels": pixels - dominant,
        "dominant_fraction": dominant / pixels,
        "chromatic_pixels": chromatic,
    }


def visual_semantic_contract(
    panels: dict,
    bg_data: bytes,
) -> tuple[dict[str, object], list[str]]:
    """Lock the reviewed panel silhouettes, not merely YAML self-consistency."""

    failures: list[str] = []
    masks = {art_id: panel_mask(panel) for art_id, panel in panels.items()}

    def cells_with(art_id: int, palette: int) -> set[tuple[int, int]]:
        return {
            (x, y)
            for y, row in enumerate(masks[art_id])
            for x, value in enumerate(row)
            if value == palette
        }

    def require(name: str, condition: bool) -> None:
        if not condition:
            failures.append(name)

    # The reviewed book keeps its masonry corners outside the warm page mask.
    book_warm = (
        {(x, 0) for x in range(7, 13)}
        | {(x, y) for y in range(1, 6) for x in range(6, 14)}
        | {(x, 6) for x in range(7, 13)}
    )
    require(
        "OpeningBook warm mask follows the page silhouette",
        cells_with(1, 5) == book_warm,
    )
    require(
        "OpeningBook top masonry corners remain BG6",
        masks[1][0][6] == 6 and masks[1][0][13] == 6,
    )

    # A tile-wide warm face rectangle cannot follow mixed face/hair pixels.
    # The native purple portrait row keeps those mixed cells continuous.
    require(
        "Sara portrait contains no blocky BG5 face rectangle",
        not cells_with(2, 5) and not cells_with(7, 5),
    )
    require(
        "Sara face cells remain continuous BG2",
        all(
            masks[2][y][x] == 2
            for y in range(4, 7)
            for x in range(8, 12)
        ),
    )

    eye_green = (
        {(x, 2) for x in range(16, 18)}
        | {(x, 3) for x in range(15, 19)}
        | {(x, 4) for x in range(15, 18)}
        | {(x, 5) for x in range(16, 18)}
    )
    eye_socket = {(x, 1) for x in range(13, 17)}
    require(
        "DragonEye green mask follows the eyeball silhouette",
        cells_with(3, 3) == eye_green,
    )
    require(
        "DragonEye BG6 mask follows the surrounding socket",
        cells_with(3, 6) == eye_socket,
    )

    expected_palette_sets = {
        1: {5, 6},
        2: {2, 4, 7},
        3: {3, 6, 7},
        4: {3, 4, 5},
        5: {5, 6},
        6: {2, 5, 7},
        7: {2, 4, 7},
    }
    actual_palette_sets = {
        art_id: {value for row in mask for value in row}
        for art_id, mask in masks.items()
    }
    require(
        "all opening and unstudied final panels retain reviewed palette sets",
        actual_palette_sets == expected_palette_sets,
    )

    words = [
        bg_data[index] | (bg_data[index + 1] << 8)
        for index in range(0, len(bg_data), 2)
    ]
    bg6 = words[6 * 4:7 * 4]

    def rgb5(word: int) -> tuple[int, int, int]:
        return word & 31, (word >> 5) & 31, (word >> 10) & 31

    bg6_rgb = [rgb5(word) for word in bg6]
    require(
        "BG6 light and dark stone shades are visibly blue-gray",
        all(
            blue > red and max(red, green, blue) - min(red, green, blue) >= 5
            for red, green, blue in bg6_rgb[1:3]
        ),
    )
    return {
        "status": "pass" if not failures else "fail",
        "covered_art_ids": sorted(masks),
        "palette_sets": {
            str(key): sorted(value)
            for key, value in actual_palette_sets.items()
        },
        "book_warm_cells": len(book_warm),
        "dragon_eye_green_cells": len(eye_green),
        "dragon_socket_cells": len(eye_socket),
        "bg6_words": [f"{word:04X}" for word in bg6],
    }, failures


def run_one(
    mgba: str,
    rom: Path,
    state: Path,
    output: Path,
    kind: str,
    palette: int,
    d880: int,
    guards: dict[str, int],
    mask: str,
    expected_cram: str,
    timeout: float,
) -> tuple[dict[str, str], dict[str, int | float]]:
    report = output.with_suffix(".report")
    done = output.with_suffix(".done")
    screenshot = output.with_suffix(".png")
    for path in (report, done, screenshot):
        path.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        STORY_ATTR_OUT=str(output),
        STORY_ATTR_KIND=kind,
        STORY_ATTR_PALETTE=str(palette),
        STORY_ATTR_D880=str(d880),
        # The ROM scheduler makes one LCD-safe 32-quarter art pass and then
        # clears 40 lower-panel quarters. STORY_ATTR_WAIT is the maximum for
        # pages that do not auto-advance; the Lua gate succeeds earlier only
        # after cursor $20 and an exact 360-cell layout.
        STORY_ATTR_WAIT="200",
        STORY_ATTR_MASK=mask,
    )
    if expected_cram:
        environment["STORY_ATTR_EXPECTED_CRAM"] = expected_cram
    for name, value in guards.items():
        environment[f"STORY_ATTR_{name}"] = str(value)
    process = subprocess.Popen(
        [
            mgba,
            "--fastforward",
            "-t",
            str(state),
            "--script",
            str(PROBE),
            str(rom),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if done.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before {state.name} report"
                )
            time.sleep(0.02)
        else:
            raise TimeoutError(f"{state.name} timed out")
    finally:
        terminate(process)
    if not report.is_file():
        raise RuntimeError(f"{state.name} produced no report")
    values = parse_report(report)
    if values.get("status") != "ok":
        raise RuntimeError(
            f"{state.name}: {values.get('message', 'probe failed')} "
            f"({report.read_text().strip()})"
        )
    if not screenshot.is_file():
        raise RuntimeError(f"{state.name} produced no screenshot")
    render = screenshot_metrics(screenshot)
    if (
        render["distinct_colors"] < 2
        or render["non_dominant_pixels"] < 100
        or render["dominant_fraction"] >= 0.995
    ):
        raise RuntimeError(f"{state.name} rendered blank/near-blank: {render}")
    if (
        (kind == "story" or (kind == "ending" and palette in (1, 2)))
        and render["chromatic_pixels"] < 16
    ):
        raise RuntimeError(f"{state.name} rendered no visible chroma: {render}")
    if expected_cram and values.get("cram") != expected_cram:
        raise RuntimeError(
            f"{state.name} CRAM {values.get('cram')} != YAML {expected_cram}"
        )
    return values, render


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=DEFAULT_STATES)
    parser.add_argument("--palette-yaml", type=Path, default=DEFAULT_PALETTES)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp/penta-story-attr-production",
    )
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--only-state",
        action="append",
        help="verify only this state stem (repeatable; focused diagnosis)",
    )
    args = parser.parse_args()
    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")
    args.output.mkdir(parents=True, exist_ok=True)
    panels = load_cutscene_region_palettes(args.palette_yaml)
    bg_data = load_palettes_from_yaml(args.palette_yaml)["bg_data"]
    if len(bg_data) != 64:
        parser.error(f"palette YAML compiled to {len(bg_data)} BG bytes, not 64")
    expected_cram = bg_data.hex().upper()

    failures: list[str] = []
    visual_semantics, semantic_failures = visual_semantic_contract(
        panels, bg_data
    )
    failures.extend(semantic_failures)
    results: list[dict[str, object]] = []
    specs = SPECS
    if args.only_state:
        known = {spec[0] for spec in SPECS}
        unknown = sorted(set(args.only_state) - known)
        if unknown:
            parser.error(f"unknown story state(s): {', '.join(unknown)}")
        selected = set(args.only_state)
        specs = tuple(spec for spec in SPECS if spec[0] in selected)
    for stem, kind, palette, d880, guards in specs:
        state = args.states / f"{stem}.ss0"
        if not state.is_file():
            failures.append(f"{stem}: missing {state}")
            continue
        try:
            mask = ""
            yaml_panel = None
            histogram: dict[str, int] = {}
            if kind == "story":
                panel = panels[palette]
                yaml_panel = panel.name
                cells = [value for row in panel_mask(panel) for value in row]
                mask = "".join(str(value) for value in cells)
                histogram = {
                    str(value): cells.count(value)
                    for value in sorted(set(cells))
                }
            values, render = run_one(
                args.mgba,
                args.rom.resolve(),
                state.resolve(),
                args.output / stem,
                kind,
                palette,
                d880,
                guards,
                mask,
                expected_cram if kind != "neutral" else "",
                args.timeout,
            )
            results.append({
                "state": stem,
                "kind": kind,
                "art_id_or_palette": palette,
                "yaml_panel": yaml_panel,
                "expected_art_histogram": histogram,
                "report": values,
                "render_metrics": render,
                "screenshot": str((args.output / stem).with_suffix(".png")),
            })
            print(
                f"{stem:19s} {kind:7s} "
                f"{yaml_panel or ('BG' + str(palette))} "
                f"target={values['target']} neutral={values['neutral']} "
                f"row={values['row']} key={values['key']}"
            )
        except Exception as error:
            failures.append(f"{stem}: {error}")

    contact_sheet = write_contact_sheet(args.output, results)
    receipt = {
        "status": "failed" if failures else "passed",
        "rom": str(args.rom.resolve()),
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "palette_yaml": str(args.palette_yaml.resolve()),
        "palette_yaml_sha256": hashlib.sha256(
            args.palette_yaml.read_bytes()
        ).hexdigest(),
        "states": len(results),
        "story_contract": (
            "all 160 top-panel cells exactly match the YAML region mask; "
            "all 200 dialogue cells remain BG0 with no unsafe attr bits; "
            "the live 64-byte BG CRAM deck exactly matches the YAML and the "
            "native screenshot is nonblank/chromatic; reviewed page, face, "
            "eye/socket, and every final-panel palette silhouette is locked"
        ),
        "ending_contract": (
            "all 360 visible cells exactly match the selected BG palette "
            "with no unsafe attr bits; the live 64-byte BG CRAM deck exactly "
            "matches the YAML and the rendered frame cannot be blank; $C600 "
            "is recorded diagnostically because the stock ending tail reuses "
            "it as script workspace"
        ),
        "results": results,
        "visual_semantics": visual_semantics,
        "contact_sheet": str(contact_sheet) if contact_sheet else None,
        "failures": failures,
    }
    (args.output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    if len(results) != len(specs):
        print(f"FAIL: verified {len(results)}/{len(specs)} states")
        return 1
    story_count = sum(result["kind"] == "story" for result in results)
    ending_count = sum(result["kind"] == "ending" for result in results)
    print(
        f"PASS: {story_count} committed story states exactly match their "
        "YAML region masks above a neutral dialogue separator; "
        f"{ending_count} ending states match their guarded viewport palettes."
    )
    if contact_sheet:
        print(f"Contact sheet: {contact_sheet}")
    print(f"Receipt: {args.output / 'receipt.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
