#!/usr/bin/env python3
"""Gate the complete title/logo/banner cycle through mGBA's CGB renderer."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image
import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
PROBE = Path(__file__).with_name("probe_title_showcase_mgba.lua")
PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
TITLE_ALIAS_OFFSET = 13 * 0x4000 + (0x6838 - 0x4000)


def expected_title_bg() -> bytes:
    document = yaml.safe_load(PALETTE_YAML.read_text())
    selected = document["title_bg_palette"]
    colors = document["bg_palettes"][selected]["colors"]
    result = bytearray()
    for color in colors:
        value = int(color, 16) & 0x7FFF
        result.extend((value & 0xFF, value >> 8))
    return bytes(result)


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def red_dominant_pixels(path: Path) -> int:
    with Image.open(path) as image:
        if image.size != (160, 144):
            raise RuntimeError(f"{path.name}: expected 160x144, got {image.size}")
        rgb = image.convert("RGB")
        spotlight = ".scene1B." in path.name
        count = 0
        for y in range(rgb.height):
            # The intentional Sara W/Dragonfly spotlight sprites occupy this
            # 16-pixel actor band. The old whole-frame test only passed while
            # those actors were missing; keep checking all title text/art.
            if spotlight and 60 <= y < 84:
                continue
            for x in range(rgb.width):
                # Nightfall's native title selector is deliberately orange.
                # It is checked independently by the exact mGBA cursor-route
                # gate; do not misclassify that one 8x7 selector cell as a
                # red artifact while retaining the whole-frame check elsewhere.
                if ".scene01." in path.name and 24 <= x < 32 and 65 <= y < 72:
                    continue
                red, green, blue = rgb.getpixel((x, y))
                count += (
                    red > 90
                    and red > green * 1.35
                    and red > blue * 1.20
                )
        return count


def lit_pixels(path: Path, box: tuple[int, int, int, int]) -> int:
    """Count visible non-black pixels in a renderer-space receipt region."""
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        left, top, right, bottom = box
        return sum(
            max(rgb.getpixel((x, y))) >= 40
            for y in range(top, bottom)
            for x in range(left, right)
        )


def is_safe_bgp_zero_frame(path: Path) -> bool:
    """Prove a sampled BGP=$00 transition contains no chromatic artifact.

    mGBA commits screenshots after the callback that sampled BGP, so the image
    can be either the fully white fade frame or the immediately following
    stock monochrome title frame. Both are safe; any unequal RGB channels are
    evidence that a stale CGB row escaped during the transition.
    """
    with Image.open(path) as image:
        if image.size != (160, 144):
            raise RuntimeError(f"{path.name}: expected 160x144, got {image.size}")
        return all(
            red == green == blue
            for red, green, blue in image.convert("RGB").getdata()
        )


def prepare_runtime_rom(rom: Path, output: Path) -> tuple[Path, Path]:
    """Copy the ROM into a clean private directory for a cold SRAM boot."""
    runtime = output.parent / f"{output.name}.runtime"
    if runtime.exists():
        shutil.rmtree(runtime)
    runtime.mkdir(parents=True)
    runtime_rom = runtime / "candidate.gb"
    shutil.copy2(rom, runtime_rom)
    return runtime_rom, runtime


def probe_command(
    mgba: str,
    runtime_rom: Path,
    runtime: Path,
) -> list[str]:
    return [
        mgba,
        "--fastforward",
        "-C", f"savegamePath={runtime}",
        "-C", f"savestatePath={runtime}",
        "--script", str(PROBE),
        str(runtime_rom),
    ]


def run_probe(
    mgba: str,
    rom: Path,
    output: Path,
    timeout: float,
) -> tuple[dict[str, str], list[Path], list[Path], list[Path]]:
    output.parent.mkdir(parents=True, exist_ok=True)
    report = Path(str(output) + ".report")
    done = Path(str(output) + ".done")
    for path in (report, done):
        path.unlink(missing_ok=True)
    for path in output.parent.glob(output.name + ".*.scene*.png"):
        path.unlink()
    for path in output.parent.glob(output.name + ".cram-*.png"):
        path.unlink()

    expected_bg = expected_title_bg()
    embedded_bg = rom.read_bytes()[
        TITLE_ALIAS_OFFSET:TITLE_ALIAS_OFFSET + 8
    ]
    if embedded_bg != expected_bg:
        raise RuntimeError(
            "ROM title alias does not match title_bg_palette: "
            f"{embedded_bg.hex().upper()} != {expected_bg.hex().upper()}"
        )
    runtime_rom, runtime = prepare_runtime_rom(rom, output)

    environment = os.environ.copy()
    environment.update(
        TITLE_SHOWCASE_OUT=str(output),
        TITLE_SHOWCASE_MAX_FRAMES="7000",
        TITLE_SHOWCASE_EXPECTED_BG0=",".join(
            f"{byte:02X}" for byte in expected_bg
        ),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        probe_command(mgba, runtime_rom, runtime),
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
                    f"mGBA exited {process.returncode} before title report"
                )
            time.sleep(0.05)
        else:
            raise TimeoutError(f"title showcase timed out after {timeout:g}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    if not report.is_file():
        raise RuntimeError("mGBA produced no title showcase report")
    screenshots = sorted(
        path
        for path in output.parent.glob(output.name + ".*.scene*.png")
        if ".cram-" not in path.name
    )
    blank_receipts = sorted(
        output.parent.glob(output.name + ".cram-blank.*.png")
    )
    bad_receipts = sorted(
        output.parent.glob(output.name + ".cram-bad.*.png")
    )
    return parse_report(report), screenshots, blank_receipts, bad_receipts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp/penta-title-showcase-mgba/title",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")

    try:
        report, screenshots, blank_receipts, bad_receipts = run_probe(
            args.mgba,
            args.rom.resolve(),
            args.output.resolve(),
            args.timeout,
        )
    except Exception as error:
        print(f"FAIL: {error}")
        return 1

    failures: list[str] = []
    expected_samples = {"01": 60, "1B": 200, "1C": 100}
    for scene, minimum in expected_samples.items():
        count = int(report.get(f"samples_{scene}", "0"))
        if count < minimum:
            failures.append(
                f"D880={scene} has only {count} samples (need {minimum}+)"
            )
    for field in (
        "unsafe_total",
        "banner_table_bad_samples",
        "cram_bad_samples",
    ):
        value = int(report.get(field, "-1"))
        if value != 0:
            failures.append(f"{field}={value}, expected 0")

    if report.get("status") != "ok":
        failures.append(
            f"probe status={report.get('status')!r}: "
            f"{report.get('message', 'no message')}"
        )
    if len(screenshots) != 9:
        failures.append(f"rendered {len(screenshots)} screenshots, expected 9")

    blank_samples = int(report.get("cram_blank_transition_samples", "-1"))
    if blank_samples != len(blank_receipts):
        failures.append(
            "BGP=$00 CRAM transition receipt count mismatch: "
            f"report={blank_samples}, screenshots={len(blank_receipts)}"
        )
    if len(blank_receipts) > 2:
        failures.append(
            f"BGP=$00 CRAM transition lasted {len(blank_receipts)} samples; "
            "expected no more than 2"
        )
    for screenshot in blank_receipts:
        try:
            if not is_safe_bgp_zero_frame(screenshot):
                failures.append(
                    f"{screenshot.name}: BGP=$00 exception contained "
                    "chromatic pixels"
                )
        except Exception as error:
            failures.append(str(error))
    if bad_receipts:
        failures.append(
            f"unexpected visible-BGP CRAM mismatch receipts: "
            f"{[path.name for path in bad_receipts]}"
        )

    red_counts: dict[str, int] = {}
    for screenshot in screenshots:
        try:
            red_counts[screenshot.name] = red_dominant_pixels(screenshot)
        except Exception as error:
            failures.append(str(error))
    red_total = sum(red_counts.values())
    if red_total:
        failures.append(
            f"{red_total} red-dominant pixels across rendered title frames"
        )

    # A colored OBJ on a black BG falsely passed the old palette/attribute
    # checks.  Require renderer-visible title art and monster-name glyphs in
    # at least two spotlight receipts; transitional captures may legitimately
    # contain only part of a sliding card.
    spotlight_screens = [
        screenshot for screenshot in screenshots
        if ".scene1B." in screenshot.name
    ]
    header_counts = {
        path.name: lit_pixels(path, (0, 28, 160, 54))
        for path in spotlight_screens
    }
    name_counts = {
        path.name: lit_pixels(path, (36, 82, 124, 98))
        for path in spotlight_screens
    }
    visible_headers = sum(value >= 40 for value in header_counts.values())
    visible_names = sum(value >= 12 for value in name_counts.values())
    if visible_headers < 2:
        failures.append(
            "spotlight title art is renderer-visible in only "
            f"{visible_headers}/4 receipts: {header_counts}"
        )
    if visible_names < 2:
        failures.append(
            "spotlight monster names are renderer-visible in only "
            f"{visible_names}/4 receipts: {name_counts}"
        )

    print(
        "Title cycle: "
        f"01={report.get('samples_01', '0')} samples, "
        f"1C={report.get('samples_1C', '0')} samples, "
        f"1B={report.get('samples_1B', '0')} samples; "
        f"screenshots={len(screenshots)} red_pixels={red_total}"
    )
    print(
        "Attrs: "
        f"nonzero={report.get('nonzero_total')} "
        f"unsafe={report.get('unsafe_total')} "
        f"banner_table_bad={report.get('banner_table_bad_samples')} "
        f"inactive_table_non_neutral="
        f"{report.get('table_non_neutral_samples')} "
        f"cram_bad={report.get('cram_bad_samples')} "
        f"blank_transition_receipts={len(blank_receipts)}"
    )
    print(
        "Spotlight pixels: "
        f"visible_headers={visible_headers}/{len(spotlight_screens)} "
        f"visible_names={visible_names}/{len(spotlight_screens)}"
    )
    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(
        "PASS: the full title/logo/banner cycle stays on intentional "
        "YAML-selected BG0 with no red artifacts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
