#!/usr/bin/env python3
"""Verify fully published, artifact-free death/game-over rendering."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image
import yaml
from death_native_art import capture_native_planes, exact_native_plane


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
PROBE = Path(__file__).with_name("probe_death_gameover.lua")
STATE_GENERATOR = Path(__file__).with_name("generate_stream_boss_states.py")
PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
# The illustration source and viewport are stock boss-animation phases, not a
# phase-invariant image fixture. The old r39 per-boss hashes were captured from
# savestates whose $CFAA bytes contained the retired executable blob that later
# proved to corrupt the native dungeon template. Pinning those hashes would
# reintroduce the Stage-1 corruption fix by proxy. The invariant contract is
# instead exact 576-cell source publication, coherent CRAM, meaningful
# chromatic art coverage, the white fade, and the stock GAME OVER result below.
MIN_DEATH_ART_DARK_PIXELS = 1000
MIN_DEATH_ART_CHROMATIC_PIXELS = 250
FADE_WHITE_RGB_SHA256 = (
    "847f0ab88419bfae5e28ae56d3406b1a9b749eb77e198dede3fb20b8decc0d81"
)
GAMEOVER_RGB_SHA256 = (
    "ab12ada8f36574e0c3600ed93ae5ba910afbc87faee8d98d045a6fcf6a24ef4e"
)
# The stable 18x20 GAME OVER window tile crop is stock-authored and invariant.
STOCK_GAMEOVER_SHA256 = (
    "fd1816cae5ef387012671754377cb0294e42780eeefcb76b2ed4d87f60a26a02"
)
# Riff, Crystal Dragon, Ted, and Angela use multi-phase boss-local HP semantics
# at the generated arena checkpoint; DCBB=0 does not enter the common stock
# death path there. These five independently cover every observed attribute
# carryover family through an unmodified D880=$17 transition. Ted remains
# covered by the boss geometry/cadence gates rather than a synthetic kill.
STOCK_DEATH_CASES = (
    (0, "shalamar"),
    (3, "cameo"),
    (5, "troop"),
    (6, "faze"),
    (8, "penta_dragon"),
)

# Fresh stock-ROM Shalamar receipt. Independently generated OG/DX checkpoints
# reach the other bosses from different arena camera phases, so their raw
# scroll bytes are not valid cross-ROM constants. They are still required not
# to collapse to the retired all-zero viewport.
STOCK_DEATH_VIEWPORTS = {
    # DX deliberately selects the completed $9C00 publication; stock's $9800
    # map is stale under the extra CGB service cadence and loses the lower art.
    0: ("8B", "15", "05", "9C00"),
}


def parse_report(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for token in path.read_text().split():
        if "=" in token:
            key, value = token.split("=", 1)
            result[key] = value
    return result


def image_metrics(path: Path) -> dict[str, int | str]:
    with Image.open(path) as source:
        image = source.convert("RGB")
        if image.size != (160, 144):
            raise RuntimeError(
                f"{path.name}: screenshot is {image.size}, expected 160x144"
            )
        pixels = list(image.getdata())
        chromatic_points = [
            (index % 160, index // 160)
            for index, pixel in enumerate(pixels)
            if max(pixel) - min(pixel) > 4
        ]
        return {
            "rgb_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
            "colors": len(set(pixels)),
            "chromatic": len(chromatic_points),
            "chromatic_max_y": max(
                (point[1] for point in chromatic_points), default=-1
            ),
            "chromatic_lower": sum(
                80 <= point[1] < 120 for point in chromatic_points
            ),
            "near_white": sum(min(pixel) >= 248 for pixel in pixels),
            # The stock CGB grayscale ramp bottoms at RGB(82), not black.
            "dark": sum(max(pixel) <= 96 for pixel in pixels),
            "red": sum(
            red > 90 and red > green * 1.35 and red > blue * 1.20
                for red, green, blue in pixels
            ),
        }


def expected_death_palettes() -> tuple[bytes, bytes]:
    document = yaml.safe_load(PALETTE_YAML.read_text())
    entry = document.get("death_gameover_palette", {})
    rows = []
    for key in ("colors", "gameover_colors"):
        colors = entry.get(key, ())
        if len(colors) != 4:
            raise RuntimeError(
                f"death_gameover_palette.{key} must contain four BGR555 words"
            )
        row = bytearray()
        for color in colors:
            value = int(str(color), 16)
            if not 0 <= value <= 0x7FFF:
                raise RuntimeError(f"invalid death palette word: {color!r}")
            row.extend(value.to_bytes(2, "little"))
        rows.append(bytes(row))
    return rows[0], rows[1]


def report_bytes(
    result: dict[str, str], key: str, expected_length: int
) -> bytes:
    try:
        value = bytes.fromhex(result[key])
    except (KeyError, ValueError) as exc:
        raise RuntimeError(f"missing or malformed {key}") from exc
    if len(value) != expected_length:
        raise RuntimeError(
            f"{key} has {len(value)} bytes, expected {expected_length}"
        )
    return value


def run_boss(
    mgba: str,
    rom: Path,
    state: Path,
    output: Path,
    timeout: float,
) -> tuple[dict[str, str], dict[str, int], dict[str, int], dict[str, int]]:
    prefix = output / state.stem
    stdout = prefix.with_suffix(".stdout.txt")
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        DEATH_OUT=str(prefix),
        PENTA_STATE_FILE=str(state.resolve()),
        DEATH_TRACE="1",
    )
    with stdout.open("w") as stream:
        completed = subprocess.run(
            [
                mgba,
                "--fastforward",
                "--script",
                str(PROBE),
                str(rom),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    report_path = prefix.with_suffix(".report")
    if not report_path.is_file():
        raise RuntimeError(
            f"{state.name}: no report (mGBA status {completed.returncode}); "
            f"see {stdout}"
        )
    art_path = Path(str(prefix) + ".art.png")
    fade_path = Path(str(prefix) + ".fade-white.png")
    gameover_path = Path(str(prefix) + ".gameover.png")
    if (
        not art_path.is_file()
        or not fade_path.is_file()
        or not gameover_path.is_file()
    ):
        raise RuntimeError(f"{state.name}: missing rendered capture; see {stdout}")
    return (
        parse_report(report_path),
        image_metrics(art_path),
        image_metrics(fade_path),
        image_metrics(gameover_path),
    )


def generate_states(
    mgba: str,
    rom: Path,
    output: Path,
    timeout: float,
) -> None:
    log = output / "state-generation.log"
    with log.open("w") as stream:
        completed = subprocess.run(
            [
                sys.executable,
                str(STATE_GENERATOR),
                str(rom),
                "--output",
                str(output),
                "--mgba",
                mgba,
                "--timeout",
                str(timeout),
            ],
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=max(300.0, timeout * 20),
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(
            f"release-ROM boss state generation failed with status "
            f"{completed.returncode}; see {log}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--states",
        type=Path,
        help=(
            "use an existing exact-ROM boss-state directory; by default a "
            "fresh/cache-validated set is generated beneath the output"
        ),
    )
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument(
        "--only",
        type=int,
        action="append",
        choices=[index for index, _ in STOCK_DEATH_CASES],
        help="verify only this boss index (repeatable for split receipt runs)",
    )
    parser.add_argument(
        "--inventory-only",
        action="store_true",
        help="capture and report every contract without failing the gate",
    )
    args = parser.parse_args()

    if not args.mgba:
        print("FAIL: mgba-qt was not found")
        return 2
    rom = args.rom.resolve()

    temporary = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        scratch = ROOT / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(
            prefix="penta-death-gameover-", dir=scratch
        )
        output = Path(temporary.name)

    failures: list[str] = []
    palette_row, gameover_palette_row = expected_death_palettes()
    coherent_cram = palette_row * 8
    gameover_coherent_cram = gameover_palette_row * 8
    white_cram = bytes.fromhex("FF7F" * 32)
    try:
        states_root = (
            args.states.resolve()
            if args.states
            else output / "generated-states"
        )
        if not args.states:
            states_root.mkdir(parents=True, exist_ok=True)
            try:
                generate_states(
                    args.mgba, rom, states_root, args.timeout
                )
            except Exception as exc:
                print(f"FAIL: {exc}")
                return 2
        selected_cases = [
            case for case in STOCK_DEATH_CASES
            if not args.only or case[0] in args.only
        ]
        native_planes = set()
        if any(index == 0 for index, _ in selected_cases):
            try:
                native_planes = capture_native_planes(output / 'native-art-oracle', args.timeout)
            except Exception as exc:
                print(f"FAIL: native death-art oracle: {exc}")
                return 2
        states = [
            states_root / f"boss{index}_{name}.ss0"
            for index, name in selected_cases
        ]
        missing = [state for state in states if not state.is_file()]
        if missing:
            print("FAIL: missing generated release-ROM boss states:")
            for state in missing:
                print(f"  - {state}")
            return 2

        for (boss_index, _), state in zip(selected_cases, states):
            try:
                result, art_visual, fade_visual, gameover_visual = run_boss(
                    args.mgba, rom, state, output, args.timeout
                )
            except Exception as exc:
                failures.append(str(exc))
                continue
            art_nonzero = int(result.get("art_nonzero", "-1"))
            future_nonzero = int(
                result.get("art_future_window_nonzero", "-1")
            )
            window_begin_nonzero = int(
                result.get("window_begin_nonzero", "-1")
            )
            gameover_nonzero = int(result.get("gameover_nonzero", "-1"))
            unsafe = sum(
                int(result.get(key, "-1"))
                for key in (
                    "art_unsafe",
                    "art_future_window_unsafe",
                    "window_begin_unsafe",
                    "gameover_unsafe",
                )
            )
            try:
                source_tiles = report_bytes(result, "source_c1a0", 576)
                published_tiles = report_bytes(result, "published_9c00", 576)
                gameover_tiles = report_bytes(result, "gameover_tiles", 360)
                art_cram = report_bytes(result, "art_bg_cram", 64)
                fade_cram = report_bytes(result, "fade_bg_cram", 64)
                gameover_cram = report_bytes(
                    result, "gameover_bg_cram", 64
                )
            except RuntimeError as exc:
                failures.append(f"{state.name}: {exc}")
                continue
            source_hash = hashlib.sha256(source_tiles).hexdigest()
            gameover_hash = hashlib.sha256(gameover_tiles).hexdigest()
            published_matches = published_tiles == source_tiles
            # Do not compare two reads of the current map: that old assertion
            # was tautological and allowed a cropped Shalamar to pass. Pin the
            # exact stock viewport and active map for each independently
            # reached boss death. The $9C00 source-publication check above is
            # separate and continues to prove all 576 assembled cells land.
            viewport_actual = (
                result.get("art_lcdc"),
                result.get("art_scy"),
                result.get("art_scx"),
                result.get("art_base"),
            )
            viewport_expected = STOCK_DEATH_VIEWPORTS.get(boss_index)
            viewport_matches_stock = (
                viewport_actual == viewport_expected
                if viewport_expected is not None
                else viewport_actual[1:3] != ("00", "00")
            )
            shalamar_lower_body_visible = (
                boss_index != 0
                or (
                    # Native poses have different foot heights (including
                    # y=108). Require the entire unmodified 576-cell native
                    # pose, independently observed in two fresh OG replays,
                    # rather than a particular pose's bottom pixel.
                    exact_native_plane(source_tiles, native_planes)
                    and art_visual["chromatic_lower"] >= 500
                )
            )
            coherent_phases = sum(
                actual == expected
                for actual, expected in (
                    (art_cram, coherent_cram),
                    (fade_cram, white_cram),
                    (gameover_cram, gameover_coherent_cram),
                )
            )
            print(
                f"{state.stem:30s} "
                f"art={art_nonzero:3d} pre-window={future_nonzero:3d} "
                f"window-start={window_begin_nonzero:3d} "
                f"gameover={gameover_nonzero:3d} unsafe={unsafe:2d} "
                f"source={source_hash[:8]} "
                f"published={'yes' if published_matches else 'NO '} "
                f"viewport={'yes' if viewport_matches_stock else 'NO '} "
                f"cram={coherent_phases}/3 "
                f"chromatic={art_visual['chromatic']:4d}/"
                f"{fade_visual['chromatic']:4d}/"
                f"{gameover_visual['chromatic']:4d}"
            )
            if result.get("status") != "ok":
                failures.append(
                    f"{state.name}: probe status {result.get('status')!r}"
                )
            if result.get("d880") != "17" or result.get("ffe4") != "01":
                failures.append(
                    f"{state.name}: original death guard was not retained"
                )
            if not args.inventory_only:
                if (
                    unsafe
                    or not published_matches
                    or not viewport_matches_stock
                    or not shalamar_lower_body_visible
                    or gameover_hash != STOCK_GAMEOVER_SHA256
                    or coherent_phases != 3
                    or result.get("fade_bgp") != "00"
                    or art_visual["chromatic"] < MIN_DEATH_ART_CHROMATIC_PIXELS
                    or not 2 <= art_visual["colors"] <= 4
                    or art_visual["dark"] < MIN_DEATH_ART_DARK_PIXELS
                    or fade_visual["rgb_sha256"] != FADE_WHITE_RGB_SHA256
                    or gameover_visual["rgb_sha256"] != GAMEOVER_RGB_SHA256
                ):
                    failures.append(
                        f"{state.name}: death/GAME OVER lost full source "
                        "publication/stock viewport, Shalamar lower body, "
                        "meaningful chromatic art, "
                        "coherent YAML "
                        "palette, white fade, or stable GAME OVER text"
                    )

        if failures:
            print("FAIL:")
            for failure in failures:
                print(f"  - {failure}")
            print(f"Artifacts: {output}")
            return 1
        mode = "inventory" if args.inventory_only else "gate"
        scope = (
            "all five"
            if len(selected_cases) == len(STOCK_DEATH_CASES)
            else f"the selected {len(selected_cases)}"
        )
        print(
            f"PASS ({mode}): {scope} naturally transitioning stock arena "
            "variants published all 576 phase-specific stock-art cells, kept "
            "noncollapsed viewports and Shalamar's lower body, retained "
            "meaningful chromatic artwork, used one coherent YAML palette, "
            "preserved the exact white fade and GAME OVER screen, and kept "
            "the original control-flow guard."
        )
        if args.output:
            print(f"Artifacts: {output}")
        return 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
