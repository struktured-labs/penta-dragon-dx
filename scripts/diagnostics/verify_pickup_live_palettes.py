#!/usr/bin/env python3
"""Resume every inventoried pickup state in the current ROM and audit it."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from PIL import Image, ImageDraw

from normalize_mgba_state_pc import MAIN_LOOP_BANK, normalize
from verify_pickup_class_palettes import (
    BG_PALETTE_OFFSET,
    DEFAULT_ROM,
    DEFAULT_STATES,
    PICKUPS,
    palette_words,
)


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_pickup_live_palettes.lua"
NORMALIZED_RESUME_STATES = {
    "level1_sara_spiral_powerup_item.ss0",
    "level1_sara_w_dragon_powerup_item.ss0",
    "level1_sara_w_rock_item.ss0",
    "level1_sara_w_teleport.ss0",
}
SYNTHETIC_PICKUP_HOSTS = {
    # This sole fixture was captured mid-HRAM DMA and cannot safely cross the
    # release ROM's MBC1->MBC5 expansion.  Reuse the healthy P-item room,
    # replace only its 2x2 source tile IDs, clear their attributes, and require
    # the current-ROM room publisher to materialize Orb's semantic class.
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0": (
        "level1_sara_w_p_item.ss0",
        ((0xCA, 0xCB, 0xDA, 0xDB), (0xCC, 0xCD, 0xDC, 0xDD)),
    ),
}


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def parse_report(path: Path) -> dict:
    result: dict[str, str] = {}
    cram: dict[int, list[int]] = {}
    pickups: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if line.startswith("cram="):
            values = line.removeprefix("cram=").split(",")
            cram[int(values[0])] = [int(value, 16) for value in values[1:]]
        elif line.startswith("pickup\t"):
            _, name, palette, found, matched, details = line.split("\t", 5)
            pickups[name] = {
                "palette": int(palette),
                "found": int(found),
                "matched": int(matched),
                "details": details,
            }
        elif "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    result["cram"] = cram
    result["pickups"] = pickups
    return result


def run_state(
    mgba: Path,
    rom: Path,
    state: Path,
    pickups: list,
    output: Path,
    timeout: float,
    demo_rearm_rows: int,
    launch_attempts: int,
    artifact_stem: str | None = None,
    substitute: tuple[tuple[int, ...], tuple[int, ...]] | None = None,
) -> dict:
    stem = artifact_stem or state.stem
    spec = output / f"{stem}.spec.tsv"
    report = output / f"{stem}.report.tsv"
    screenshot = output / f"{stem}.png"
    spec.write_text("".join(
        f"{pickup.name}\t{pickup.palette}\t"
        + ",".join(f"{tile:02X}" for tile in pickup.tiles)
        + "\n"
        for pickup in pickups
    ))
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "PICKUP_LIVE_OUT": str(report),
        "PICKUP_LIVE_SCREENSHOT": str(screenshot),
        "PICKUP_LIVE_SPEC": str(spec),
        "PICKUP_LIVE_DEMO_REARM_ROWS": str(demo_rearm_rows),
    })
    if substitute is not None:
        before, after = substitute
        environment["PICKUP_LIVE_SUBSTITUTE"] = (
            ",".join(f"{value:02X}" for value in before)
            + ":"
            + ",".join(f"{value:02X}" for value in after)
        )
    attempts = []
    for attempt in range(1, launch_attempts + 1):
        # A failed Qt process must never leave output that can make its retry
        # look successful.  Semantic failures are evaluated only after a
        # complete report and screenshot are produced.
        report.unlink(missing_ok=True)
        screenshot.unlink(missing_ok=True)
        stdout = output / f"{stem}.attempt-{attempt:02d}.stdout.txt"
        timed_out = False
        with stdout.open("w") as stream:
            try:
                completed = subprocess.run(
                    [
                        str(mgba), "--fastforward", "-t", str(state),
                        "--script", str(PROBE), str(rom),
                    ],
                    cwd=ROOT,
                    env=environment,
                    stdout=stream,
                    stderr=subprocess.STDOUT,
                    timeout=timeout,
                    check=False,
                )
                returncode = completed.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                returncode = None
        complete = (
            returncode == 0
            and report.is_file()
            and screenshot.is_file()
        )
        attempts.append({
            "attempt": attempt,
            "returncode": returncode,
            "timed_out": timed_out,
            "report_written": report.is_file(),
            "screenshot_written": screenshot.is_file(),
            "log": str(stdout),
            "complete": complete,
        })
        if complete:
            break
    else:
        statuses = [
            "timeout" if item["timed_out"] else str(item["returncode"])
            for item in attempts
        ]
        raise RuntimeError(
            f"{state.name}: mGBA transport failed after {launch_attempts} "
            f"attempt(s), statuses={statuses}; see {attempts[-1]['log']}"
        )
    with Image.open(screenshot) as image:
        if image.size != (160, 144):
            raise RuntimeError(
                f"{state.name}: screenshot {image.size}, expected 160x144"
            )
        image.verify()
    result = parse_report(report)
    result["launch_attempts"] = attempts
    return result


def contact_sheet(state_results: list[dict], output: Path) -> None:
    columns = 4
    scale = 2
    cell_width, cell_height = 328, 316
    rows = (len(state_results) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)
    for index, result in enumerate(state_results):
        x = (index % columns) * cell_width
        y = (index // columns) * cell_height
        with Image.open(result["screenshot"]) as source:
            frame = source.convert("RGB").resize(
                (160 * scale, 144 * scale), Image.Resampling.NEAREST
            )
        sheet.paste(frame, (x + 4, y + 4))
        names = ", ".join(result["pickups"])
        draw.text((x + 4, y + 294), names[:52], fill="black")
    sheet.save(output)


def chromatic(word: int) -> bool:
    channels = (word & 0x1F, (word >> 5) & 0x1F, (word >> 10) & 0x1F)
    return max(channels) - min(channels) >= 6


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=DEFAULT_STATES)
    parser.add_argument(
        "--mgba", type=Path,
        default=ROOT / "scripts/mgba-qt-singleflight",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--only-state",
        action="append",
        help="run only this inventoried state (repeatable; focused diagnosis)",
    )
    parser.add_argument(
        "--demo-rearm-rows",
        type=int,
        default=18,
        help="reproduce this many missed attract-demo repair rows",
    )
    parser.add_argument(
        "--launch-attempts",
        type=int,
        default=2,
        help="bounded attempts for process-level mGBA transport failures",
    )
    args = parser.parse_args()
    if args.launch_attempts < 1:
        parser.error("--launch-attempts must be at least 1")

    rom = args.rom.resolve()
    states = args.states.resolve()
    temporary = None
    if args.output:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="penta-pickup-live-")
        output = Path(temporary.name)

    grouped: dict[str, list] = defaultdict(list)
    for pickup in PICKUPS:
        grouped[pickup.state].append(pickup)
    if args.only_state:
        unknown = sorted(set(args.only_state) - grouped.keys())
        if unknown:
            parser.error(f"unknown pickup state(s): {', '.join(unknown)}")
        grouped = {
            name: grouped[name]
            for name in args.only_state
        }
    missing = [states / name for name in grouped if not (states / name).is_file()]
    if missing:
        for path in missing:
            print(f"FAIL: missing pickup state {path}")
        return 2

    rom_bytes = rom.read_bytes()
    expected_cram = {
        palette: palette_words(rom_bytes, palette)
        for palette in range(1, 6)
    }
    failures: list[str] = []
    state_results: list[dict] = []
    live_pickups: list[dict] = []
    try:
        for state_name, expected_pickups in grouped.items():
            state = states / state_name
            runtime_state = state
            substitute = None
            host = SYNTHETIC_PICKUP_HOSTS.get(state_name)
            if host is not None:
                host_name, substitute = host
                runtime_state = states / host_name
            # These fixtures serialize a PC inside code replaced by the
            # current build. Preserve their game/video memory, retarget the
            # ROM CRC, and resume at the shared fixed-bank main loop. The
            # spiral/dragon fixtures point at $6AA6/$6AB8, now occupied by
            # story/ending helpers. Other fixtures intentionally retain their
            # native resume points: several capture one-frame pickup forms
            # that disappear after a generic main-loop resume.
            if state_name in NORMALIZED_RESUME_STATES:
                normalized = output / "normalized" / state.name
                normalized.parent.mkdir(parents=True, exist_ok=True)
                writes = (
                    [(0xDF02, 0x00), (0xDF0D, 0xFF)]
                    if state_name == "level1_sara_w_rock_item.ss0"
                    else []
                )
                normalize(
                    state, normalized, 0x016C, writes, rom,
                    bank=MAIN_LOOP_BANK,
                )
                runtime_state = normalized
            try:
                result = run_state(
                    args.mgba.resolve(), rom, runtime_state, expected_pickups,
                    output, args.timeout, args.demo_rearm_rows,
                    args.launch_attempts,
                    artifact_stem=state.stem,
                    substitute=substitute,
                )
            except Exception as error:
                failures.append(str(error))
                continue
            state_failures = []
            if (
                result.get("D880") not in {"02", "0A"}
                or result.get("FFC1") != "01"
            ):
                state_failures.append(
                    f"settled outside Stage 1 ({result.get('D880')}/"
                    f"{result.get('FFC1')})"
                )
            for palette, words in expected_cram.items():
                if result["cram"].get(palette) != words:
                    state_failures.append(
                        f"BG{palette} CRAM {result['cram'].get(palette)} "
                        f"!= ROM {words}"
                    )
                if not any(chromatic(word) for word in words[1:3]):
                    state_failures.append(f"BG{palette} has no chromatic color")
            for pickup in expected_pickups:
                observed = result["pickups"].get(pickup.name)
                if observed is None:
                    state_failures.append(f"{pickup.name}: missing report")
                    continue
                if observed["found"] <= 0:
                    state_failures.append(f"{pickup.name}: signature absent")
                elif observed["matched"] != observed["found"]:
                    state_failures.append(
                        f"{pickup.name}: {observed['matched']}/"
                        f"{observed['found']} occurrences use BG{pickup.palette}; "
                        f"{observed['details']}"
                    )
                live_pickups.append({
                    "name": pickup.name,
                    "palette": pickup.palette,
                    **observed,
                    "state": state_name,
                })
            if state_failures:
                failures.extend(f"{state_name}: {item}" for item in state_failures)
            state_results.append({
                "state": state_name,
                "screenshot": str(output / f"{state.stem}.png"),
                "pickups": [pickup.name for pickup in expected_pickups],
                "status": "fail" if state_failures else "pass",
                "report": result,
            })

        sheet = output / "pickup-live-palettes.png"
        if state_results:
            contact_sheet(state_results, sheet)
        expected_form_count = sum(len(pickups) for pickups in grouped.values())
        checks = {
            f"all {expected_form_count} selected pickup forms resumed in current ROM": (
                len(live_pickups) == expected_form_count
            ),
            "every live signature uses its semantic BG attribute": not any(
                "occurrences use" in failure or "signature absent" in failure
                for failure in failures
            ),
            "live BG1-BG5 CRAM equals the candidate ROM": not any(
                "CRAM" in failure for failure in failures
            ),
            "all five live pickup classes contain chromatic colors": not any(
                "chromatic" in failure for failure in failures
            ),
            "all resumed states remain Stage 1 gameplay": not any(
                "settled outside" in failure for failure in failures
            ),
            "one native screenshot per pickup state": (
                len(state_results) == len(grouped)
                and all(Path(result["screenshot"]).is_file()
                        for result in state_results)
            ),
        }
        failures.extend(name for name, passed in checks.items() if not passed)
        receipt = {
            "schema": "penta-dragon-dx-pickup-live-palettes-v2",
            "status": "pass" if not failures else "fail",
            "rom": str(rom),
            "rom_md5": digest(rom, "md5"),
            "rom_sha256": digest(rom),
            "checks": checks,
            "pickups": live_pickups,
            "states": state_results,
            "contact_sheet": sheet.name if state_results else None,
            "contact_sheet_sha256": digest(sheet) if sheet.is_file() else None,
            "failures": failures,
        }
        receipt_path = output / "receipt.json"
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        for name, passed in checks.items():
            print(f"{'PASS' if passed else 'FAIL'}: {name}")
        for failure in failures[:30]:
            print(f"  FAIL: {failure}")
        print(f"Contact sheet: {sheet}")
        print(f"Receipt: {receipt_path}")
        return 1 if failures else 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
