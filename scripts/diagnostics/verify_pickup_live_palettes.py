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

from normalize_mgba_state_pc import (
    MAIN_LOOP_BANK,
    RUNTIME_HELPER_ADDR,
    RUNTIME_HELPER_SIZE,
    RUNTIME_HELPER_SOURCE_A,
    RUNTIME_HELPER_SOURCE_B,
    RUNTIME_HELPER_SPLIT,
    normalize,
    retarget_rom_identity,
)
from verify_stage1_pickup_art import PICKUP_GOLD, TARGETS, rom_tile, tile_indices
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
    # This fixture consistently hangs inside an obsolete serialized code
    # path. The current production mode reserves pickup color in tile art, so
    # render its exact native A6/A7/B6/B7 glyphs in the healthy Teleport room.
    "level1_sara_w_all_diagnol_arrow_item.ss0": (
        "level1_sara_w_teleport.ss0",
        ((0xAC, 0xAD, 0xBC, 0xBD), (0xA6, 0xA7, 0xB6, 0xB7)),
    ),
}
ARROW_VARIANT_STATE = (
    "level1_sara_w_fat_arrow_bidirectional_arrow_half_diagnol_arrow_"
    "wild_card_item.ss0"
)
ARROW_VARIANT_HOST = "level1_sara_w_teleport.ss0"
# The clean Teleport room is almost entirely traversable floor and its pickup
# already belongs to semantic BG4. Replace its
# native 2x2 pickup block while retaining the three arrow forms' original tile
# graphics.  The former All-Diagonals host has a large black south/right void
# and is unsuitable human evidence even though its four attrs are correct.
ARROW_VARIANT_SOURCE = (0xAC, 0xAD, 0xBC, 0xBD)
SOUTH_EDGE_ROWS = 24
ARROW_SCENE_MIN_NON_DARK_PIXELS = 20_000
STAGE1_RUNTIME_SOURCE_OFFSETS = (0x37C96, 0x43C96)
STAGE1_RUNTIME_LENGTH = 41
STAGE1_HELPER_SOURCE_BANKS = (13, 16)
STAGE1_LUT_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
MIN_MAIN_LOOP_HITS = 8


def bank_offset(bank: int, address: int) -> int:
    return bank * 0x4000 + address - 0x4000


def stage1_helper(rom_bytes: bytes, bank: int) -> bytes:
    source_a = bank_offset(bank, RUNTIME_HELPER_SOURCE_A)
    source_b = bank_offset(bank, RUNTIME_HELPER_SOURCE_B)
    return (
        rom_bytes[source_a:source_a + RUNTIME_HELPER_SPLIT]
        + rom_bytes[
            source_b:
            source_b + RUNTIME_HELPER_SIZE - RUNTIME_HELPER_SPLIT
        ]
    )


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
    tile_gfx: dict[tuple[int, int], bytes] = {}
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
        elif line.startswith("tilegfx="):
            bank_text, tile_text, payload = line.removeprefix("tilegfx=").split(":", 2)
            tile_gfx[(int(bank_text), int(tile_text, 16))] = bytes.fromhex(payload)
        elif "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
    result["cram"] = cram
    result["pickups"] = pickups
    result["tile_gfx"] = tile_gfx
    return result


def pickup_occurrences(details: str) -> list[dict]:
    occurrences = []
    for record in filter(None, details.split(";")):
        base, column, row, attrs = record.split(":", 3)
        occurrences.append({
            "base": base,
            "column": int(column),
            "row": int(row),
            "attrs": [int(value) for value in attrs.split("/")],
        })
    return occurrences


def run_state(
    mgba: Path,
    rom: Path,
    state: Path,
    pickups: list,
    output: Path,
    timeout: float,
    demo_rearm_rows: int,
    launch_attempts: int,
    runtime_image: Path,
    helper_image: Path,
    lut_image: Path,
    artifact_stem: str | None = None,
    substitute: tuple[tuple[int, ...], tuple[int, ...]] | None = None,
    tile_gfx: dict[tuple[int, int], bytes] | None = None,
    host: tuple[int, int, int] | None = None,
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
    # Probe controls must be owned entirely by this invocation.  Inherited
    # mutation payloads could otherwise rewrite tile IDs or VRAM graphics and
    # make a candidate-owned replay validate the caller's stale environment.
    for key in tuple(environment):
        if key.startswith("PICKUP_LIVE_"):
            environment.pop(key)
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        environment.pop(key, None)
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "PICKUP_LIVE_OUT": str(report),
        "PICKUP_LIVE_SCREENSHOT": str(screenshot),
        "PICKUP_LIVE_SPEC": str(spec),
        "PICKUP_LIVE_DEMO_REARM_ROWS": str(demo_rearm_rows),
        "PICKUP_LIVE_RUNTIME": str(runtime_image),
        "PICKUP_LIVE_HELPER": str(helper_image),
        "PICKUP_LIVE_LUT": str(lut_image),
    })
    if substitute is not None:
        before, after = substitute
        environment["PICKUP_LIVE_SUBSTITUTE"] = (
            ",".join(f"{value:02X}" for value in before)
            + ":"
            + ",".join(f"{value:02X}" for value in after)
        )
    if tile_gfx:
        environment["PICKUP_LIVE_TILE_GFX"] = ";".join(
            f"{bank}:{tile:02X}:{payload.hex().upper()}"
            for (bank, tile), payload in sorted(tile_gfx.items())
        )
    if host is not None:
        row, column, source_base = host
        environment.update({
            "PICKUP_LIVE_HOST_ROW": str(row),
            "PICKUP_LIVE_HOST_COLUMN": str(column),
            "PICKUP_LIVE_HOST_SOURCE": f"{source_base:04X}",
        })
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


def south_edge_transitions(path: Path, rows: int = SOUTH_EDGE_ROWS) -> int:
    """Retain south-edge complexity as diagnostic metadata, not a verdict."""
    with Image.open(path) as source:
        image = source.convert("RGB")
    y_start = image.height - rows
    return sum(
        image.getpixel((x, y)) != image.getpixel((x - 1, y))
        for y in range(y_start, image.height)
        for x in range(1, image.width)
    )


def non_dark_pixels(path: Path) -> int:
    with Image.open(path) as source:
        return sum(max(pixel) > 20 for pixel in source.convert("RGB").getdata())


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
        allowed = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
        if not any(output.is_relative_to(root) for root in allowed):
            parser.error("--output must be under repo tmp/ or /mnt/data/tmp/")
        output.mkdir(parents=True, exist_ok=True)
    else:
        temporary = tempfile.TemporaryDirectory(
            prefix="penta-pickup-live-", dir=ROOT / "tmp",
        )
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
    required_states = set(grouped)
    if ARROW_VARIANT_STATE in grouped:
        required_states.add(ARROW_VARIANT_HOST)
    for name in grouped:
        host = SYNTHETIC_PICKUP_HOSTS.get(name)
        if host:
            required_states.add(host[0])
    missing = [states / name for name in required_states if not (states / name).is_file()]
    if missing:
        for path in missing:
            print(f"FAIL: missing pickup state {path}")
        return 2

    rom_bytes = rom.read_bytes()
    runtime_images = [
        rom_bytes[offset:offset + STAGE1_RUNTIME_LENGTH]
        for offset in STAGE1_RUNTIME_SOURCE_OFFSETS
    ]
    if any(len(image) != STAGE1_RUNTIME_LENGTH for image in runtime_images):
        parser.error("candidate ROM is missing the Stage-1 runtime source")
    if runtime_images[0] != runtime_images[1]:
        parser.error("candidate Stage-1 runtime source copies disagree")
    runtime_image = output / "candidate-stage1-runtime.bin"
    runtime_image.write_bytes(runtime_images[0])
    helper_images = [
        stage1_helper(rom_bytes, bank)
        for bank in STAGE1_HELPER_SOURCE_BANKS
    ]
    if any(len(image) != RUNTIME_HELPER_SIZE for image in helper_images):
        parser.error("candidate ROM is missing the full Stage-1 WRAM helper")
    if helper_images[0] != helper_images[1]:
        parser.error("candidate Stage-1 WRAM helper source copies disagree")
    runtime_start = 0xDAD7 - RUNTIME_HELPER_ADDR
    if (
        helper_images[0][runtime_start:runtime_start + STAGE1_RUNTIME_LENGTH]
        != runtime_images[0]
    ):
        parser.error("candidate Stage-1 runtime is not contained in its helper")
    helper_image = output / "candidate-stage1-helper.bin"
    helper_image.write_bytes(helper_images[0])
    current_lut = rom_bytes[STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 256]
    if len(current_lut) != 256:
        parser.error("candidate ROM is missing the Stage-1 semantic LUT")
    lut_image = output / "candidate-stage1-lut.bin"
    lut_image.write_bytes(current_lut)
    expected_cram = {
        palette: palette_words(rom_bytes, palette)
        for palette in range(0, 6)
    }
    reserved_art_mode = (
        all(1 in tile_indices(rom_tile(rom_bytes, tile))
            and 2 not in tile_indices(rom_tile(rom_bytes, tile))
            for tile in TARGETS)
        and all(1 not in tile_indices(rom_tile(rom_bytes, tile))
                for tile in range(0x100) if tile not in TARGETS)
        and expected_cram[0][1] == PICKUP_GOLD
    )
    failures: list[str] = []
    state_results: list[dict] = []
    live_pickups: list[dict] = []
    try:
        for state_name, expected_pickups in grouped.items():
            state = states / state_name
            captures = []
            if state_name == ARROW_VARIANT_STATE:
                # The old multi-arrow state has a corrupt south edge. Produce
                # one card per semantic form from a healthy, almost full-floor
                # room and let the current ROM publish each target's attrs.
                try:
                    source_result = run_state(
                        args.mgba.resolve(), rom, state, expected_pickups,
                        output, args.timeout, args.demo_rearm_rows,
                        args.launch_attempts, runtime_image, helper_image,
                        lut_image,
                        artifact_stem=f"{state.stem}.native-gfx-source",
                    )
                except Exception as error:
                    failures.append(str(error))
                    continue
                source_gfx = source_result.get("tile_gfx", {})
                required_tiles = {
                    (bank, tile)
                    for pickup in expected_pickups
                    for tile in pickup.tiles
                    for bank in (0, 1)
                }
                missing_gfx = sorted(required_tiles - source_gfx.keys())
                if missing_gfx:
                    failures.append(
                        f"{state_name}: native graphics dump missing "
                        + ",".join(
                            f"VBK{bank}:{tile:02X}" for bank, tile in missing_gfx
                        )
                    )
                    continue
                normalized_host = output / "normalized" / ARROW_VARIANT_HOST
                normalized_host.parent.mkdir(parents=True, exist_ok=True)
                normalize(
                    states / ARROW_VARIANT_HOST,
                    normalized_host,
                    0x016C,
                    [],
                    rom,
                    bank=MAIN_LOOP_BANK,
                )
                for pickup in expected_pickups:
                    slug = pickup.name.lower().replace(" ", "-")
                    captures.append({
                        "id": f"{state_name}::{pickup.name}",
                        "runtime_state": normalized_host,
                        "pickups": [pickup],
                        "substitute": (ARROW_VARIANT_SOURCE, pickup.tiles),
                        "artifact_stem": f"{state.stem}.{slug}",
                        "visual_host": ARROW_VARIANT_HOST,
                        "tile_gfx": {
                            (bank, tile): source_gfx[(bank, tile)]
                            for tile in pickup.tiles for bank in (0, 1)
                        },
                    })
            else:
                runtime_state = state
                substitute = None
                host = SYNTHETIC_PICKUP_HOSTS.get(state_name)
                visual_host = None
                if host is not None:
                    host_name, substitute = host
                    runtime_state = states / host_name
                    visual_host = host_name
                captures.append({
                    "id": state_name,
                    "runtime_state": runtime_state,
                    "pickups": expected_pickups,
                    "substitute": substitute,
                    "artifact_stem": state.stem,
                    "visual_host": visual_host,
                    "tile_gfx": None,
                })
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
                captures[0]["runtime_state"] = normalized
            for capture in captures:
                try:
                    runtime_state = capture["runtime_state"]
                    if rom.read_bytes()[0x143] == 0xC0:
                        identity_state = output / "identity" / (
                            capture["artifact_stem"] + ".ss0"
                        )
                        retarget_rom_identity(runtime_state, identity_state, rom)
                        runtime_state = identity_state
                    result = run_state(
                        args.mgba.resolve(), rom, runtime_state,
                        capture["pickups"], output, args.timeout,
                        args.demo_rearm_rows, args.launch_attempts,
                        runtime_image, helper_image, lut_image,
                        artifact_stem=capture["artifact_stem"],
                        substitute=capture["substitute"],
                        tile_gfx=capture["tile_gfx"],
                    )
                except Exception as error:
                    failures.append(str(error))
                    continue
                state_failures = []
                main_loop_hits = int(result.get("main_loop_hits", "0"))
                if main_loop_hits < MIN_MAIN_LOOP_HITS:
                    state_failures.append(
                        "fixture did not recover into sustained current-ROM "
                        f"gameplay ({main_loop_hits} main-loop hits < "
                        f"{MIN_MAIN_LOOP_HITS}; PC={result.get('PC')}, "
                        f"SP={result.get('SP')}, FF99={result.get('FF99')})"
                    )
                if int(result.get("tile_copy_hits", "0")) < 1:
                    state_failures.append(
                        "fixture did not execute a current-ROM tile publication"
                    )
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
                for pickup in capture["pickups"]:
                    observed = result["pickups"].get(pickup.name)
                    if observed is None:
                        state_failures.append(f"{pickup.name}: missing report")
                        continue
                    occurrences = pickup_occurrences(observed["details"])
                    active_base = (
                        "9C00" if int(result.get("LCDC", "0"), 16) & 0x08
                        else "9800"
                    )
                    active = [
                        item for item in occurrences
                        if item["base"] == active_base
                    ]
                    allowed_palettes = (
                        {0, pickup.palette}
                        if reserved_art_mode else {pickup.palette}
                    )
                    active_valid = [
                        item for item in active
                        if len(set(item["attrs"])) == 1
                        and item["attrs"][0] in allowed_palettes
                    ]
                    if observed["found"] <= 0:
                        state_failures.append(f"{pickup.name}: signature absent")
                    elif not active:
                        state_failures.append(
                            f"{pickup.name}: signature absent from displayed "
                            f"map {active_base}; {observed['details']}"
                        )
                    elif len(active_valid) != len(active):
                        state_failures.append(
                            f"{pickup.name}: displayed {active_base} cells are "
                            f"mixed or outside {sorted(allowed_palettes)}; "
                            f"{observed['details']}"
                        )
                    live_pickups.append({
                        "name": pickup.name,
                        "palette": pickup.palette,
                        **observed,
                        "displayed_map": active_base,
                        "displayed_occurrences": active,
                        "displayed_valid_occurrences": len(active_valid),
                        "hidden_occurrences": [
                            item for item in occurrences
                            if item["base"] != active_base
                        ],
                        "state": capture["id"],
                    })
                screenshot = output / f"{capture['artifact_stem']}.png"
                edge_transitions = south_edge_transitions(screenshot)
                scene_pixels = non_dark_pixels(screenshot)
                if capture["visual_host"] == ARROW_VARIANT_HOST and (
                    scene_pixels < ARROW_SCENE_MIN_NON_DARK_PIXELS
                ):
                    state_failures.append(
                        f"incomplete arrow scene: {scene_pixels} non-dark "
                        f"pixels < {ARROW_SCENE_MIN_NON_DARK_PIXELS}"
                    )
                if state_failures:
                    failures.extend(
                        f"{capture['id']}: {item}" for item in state_failures
                    )
                state_results.append({
                    "state": capture["id"],
                    "source_state": state_name,
                    "visual_host_state": capture["visual_host"],
                    "screenshot": str(screenshot),
                    "screenshot_sha256": digest(screenshot),
                    "south_edge_rows": SOUTH_EDGE_ROWS,
                    "south_edge_transitions": edge_transitions,
                    "non_dark_pixels": scene_pixels,
                    "tile_graphics_sha256": {
                        f"VBK{bank}:{tile:02X}": hashlib.sha256(payload).hexdigest()
                        for (bank, tile), payload
                        in (capture["tile_gfx"] or {}).items()
                    },
                    "pickups": [pickup.name for pickup in capture["pickups"]],
                    "status": "fail" if state_failures else "pass",
                    "report": {
                        key: value for key, value in result.items()
                        if key != "tile_gfx"
                    },
                })

        sheet = output / "pickup-live-palettes.png"
        if state_results:
            contact_sheet(state_results, sheet)
        expected_form_count = sum(len(pickups) for pickups in grouped.values())
        arrow_results = [
            result for result in state_results
            if result.get("source_state") == ARROW_VARIANT_STATE
        ]
        checks = {
            f"all {expected_form_count} selected pickup forms resumed in current ROM": (
                len(live_pickups) == expected_form_count
            ),
            "every displayed pickup uses uniform gold-art fallback or its semantic palette": not any(
                "displayed" in failure or "signature absent" in failure
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
            "all fixtures execute a current-ROM tile publication": not any(
                "tile publication" in failure for failure in failures
            ),
            "all fixtures sustain current-ROM gameplay after helper retargeting": not any(
                "sustained current-ROM gameplay" in failure
                for failure in failures
            ),
            "one valid screenshot per pickup form group": (
                len(live_pickups) == expected_form_count
                and all(Path(result["screenshot"]).is_file()
                        for result in state_results)
            ),
            "three-arrow evidence uses the clean full-floor host": (
                not arrow_results
                or (
                    len(arrow_results) == 3
                    and all(
                        row.get("visual_host_state") == ARROW_VARIANT_HOST
                        and int(row.get("non_dark_pixels", 0))
                        >= ARROW_SCENE_MIN_NON_DARK_PIXELS
                        for row in arrow_results
                    )
                )
            ),
            "three native arrow glyphs render as distinct images": (
                not arrow_results
                or (
                    len(arrow_results) == 3
                    and len({row["screenshot_sha256"] for row in arrow_results}) == 3
                )
            ),
            "three-arrow screenshots contain a complete scene": not any(
                "incomplete arrow scene" in failure for failure in failures
            ),
        }
        failures.extend(name for name, passed in checks.items() if not passed)
        receipt = {
            "schema": "penta-dragon-dx-pickup-live-palettes-v4",
            "status": "pass" if not failures else "fail",
            "rom": str(rom),
            "rom_md5": digest(rom, "md5"),
            "rom_sha256": digest(rom),
            "candidate_runtime_source_offsets": [
                f"0x{offset:X}" for offset in STAGE1_RUNTIME_SOURCE_OFFSETS
            ],
            "candidate_runtime_sha256": digest(runtime_image),
            "candidate_helper_source_banks": list(STAGE1_HELPER_SOURCE_BANKS),
            "candidate_helper_runtime_address": f"0x{RUNTIME_HELPER_ADDR:04X}",
            "candidate_helper_sha256": digest(helper_image),
            "candidate_lut_sha256": digest(lut_image),
            "colorization_mode": (
                "reserved-pickup-gold-with-semantic-overrides"
                if reserved_art_mode else "semantic-palette-attributes"
            ),
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
