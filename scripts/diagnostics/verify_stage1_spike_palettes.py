#!/usr/bin/env python3
"""Prove the YAML-owned Stage 1 rotating-spike art and palettes are live."""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v301_gdma import _bg_table  # noqa: E402
from build_v302_title_fix import (  # noqa: E402
    BANK13,
    BANK14,
    LAVA_ATTR_DECIDER_ADDR,
    PALETTE_COPY_CRAM8_ADDR,
    PALETTE_LOADER_ADDR,
    PALETTE_LOADER_EXT_ADDR,
    STAGE1_HAZARD_BG7_SOURCE_ADDR,
    STAGE1_HAZARD_ROW_COMPILER_ADDR,
    STAGE1_HAZARD_ROW_HELPER_ADDR,
    build_phased_palette_loader,
    build_stage1_attr_runtime,
    build_stage1_hazard_dispatcher,
    build_stage1_hazard_row_helper,
)
from normalize_mgba_state_pc import normalize  # noqa: E402
from stage1_hazard_art import (  # noqa: E402
    compile_stage1_hazard_variants,
    load_stage1_hazard_config,
    load_stage1_hazard_palette,
)
from verify_pickup_class_palettes import (
    BG_PALETTE_OFFSET,
    BG_TABLE_OFFSET,
    serialized_state,
)


DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
STOCK_ROM = ROOT / "rom/Penta Dragon (J).gb"
PALETTE_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
DEFAULT_MGBA = ROOT / "scripts/mgba-qt-singleflight"
STATE_DIR = ROOT / "save_states_for_claude"
PROBE = Path(__file__).with_name("probe_stage1_spike_palettes.lua")
LIVE_STATE = "level1_cat_fish_moth_spike_hazard_orb_item.ss0"
STATE_NAMES = (
    "level1_sara_w_spike_hazard.ss0",
    "level1_sara_w_thrusting_spike_hazard.ss0",
    "level1_cat_fish_moth_spike_hazard_orb_item.ss0",
    "v2.26_level1_sara_w_gargoyle_mini_boss.ss0",
)
HAZARD = load_stage1_hazard_config()
SPIKE_TILES = HAZARD.family_tiles
SPIKE_TOOTH_TILES = HAZARD.tooth_tiles
SPIKE_FIRE_TILES = HAZARD.ring_tiles | HAZARD.body_tiles
SPIKE_CONNECTOR_TILES = HAZARD.connector_tiles
SPIKE_SUPPORT_TILES = HAZARD.support_tiles
SPIKE_TOOTH_PALETTE = HAZARD.tooth_palette
SPIKE_FIRE_PALETTE = HAZARD.body_palette
SPIKE_CONNECTOR_PALETTE = HAZARD.connector_palette
SPIKE_SUPPORT_PALETTE = HAZARD.support_palette
LEGACY_SPIKE_TILES = frozenset(
    (*range(0x2A, 0x2F), *range(0x3A, 0x3E))
)
ROOM_OFFSET = 0x4400 + 0x1A0
ROOM_SIZE = 24 * 24
EXPECTED_TABLE = _bg_table()
EXPECTED_HISTOGRAM = dict(sorted(Counter(EXPECTED_TABLE).items()))
APPROVED_ART_TILES = HAZARD.art_tiles - {0x60, 0x61, 0x70, 0x71}
APPROVED_ART_SHA256 = (
    "b777a161c3ee50ff8d184637de0b0adbae23adb6756db0c3f0984702106ad3e5"
)
# Captured natural animation corpus: four raw phase cells XOR to these eight
# desired-layout signatures. The runtime reserves bit 7 for the destination
# map and adds one, so both physical-map key sets must remain nonzero/disjoint.
CAPTURED_PHASE_SIGNATURES = (0, 4, 12, 17, 18, 21, 29, 115)
CYLINDER_BODY = bytes.fromhex(
    "60 61 6E 6E 6C 6D 6E 6E 6C 6D 6E 62"
)
CYLINDER_LOWER = bytes.fromhex(
    "70 71 7E 7D 7C 7E 7E 7D 7C 7E 7E 72"
)


def room_source(path: Path) -> bytes:
    state = serialized_state(path)
    return state[ROOM_OFFSET:ROOM_OFFSET + ROOM_SIZE]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def parse_live_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def live_receipt(
    rom: Path,
    state: Path,
    mgba: Path,
    output: Path,
    timeout: float,
    *,
    prefix_name: str = "stage1-spike-live",
    reinitialize: bool = True,
    settle: int = 180,
) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    prefix = output / prefix_name
    report_path = Path(str(prefix) + ".txt")
    screenshot_path = Path(str(prefix) + ".png")
    log_path = output / "mgba.log"
    for path in (report_path, screenshot_path, log_path):
        path.unlink(missing_ok=True)
    normalized = output / "stage1-spike-current.ss0"
    normalize(state, normalized, 0x016C, [], rom)

    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE1_SPIKE_OUT": str(prefix),
        "STAGE1_SPIKE_SETTLE": str(settle),
        "STAGE1_SPIKE_REINIT": "1" if reinitialize else "0",
        "STAGE1_SPIKE_REFRESH_CODE": "1",
    })
    with log_path.open("w") as stream:
        completed = subprocess.run(
            [
                str(mgba), "--fastforward", "-t", str(normalized),
                "--script", str(PROBE), str(rom),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    if (
        completed.returncode != 0
        or not report_path.is_file()
        or not screenshot_path.is_file()
    ):
        raise RuntimeError(
            f"live spike probe status={completed.returncode}; see {log_path}"
        )
    values = parse_live_report(report_path)
    found9800, matched9800 = (
        int(value) for value in values["map9800"].split(",")
    )
    found9c00, matched9c00 = (
        int(value) for value in values["map9c00"].split(",")
    )
    lcdc = int(values["lcdc"], 16)
    active_base = "9c00" if lcdc & 0x08 else "9800"
    active_found, active_matched = (
        (found9c00, matched9c00)
        if active_base == "9c00"
        else (found9800, matched9800)
    )
    rom_bytes = rom.read_bytes()
    expected_bg5 = rom_bytes[
        BG_PALETTE_OFFSET + SPIKE_FIRE_PALETTE * 8:
        BG_PALETTE_OFFSET + (SPIKE_FIRE_PALETTE + 1) * 8
    ]
    expected_bg7 = rom_bytes[
        BANK13 + (STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000):
        BANK13 + (STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000) + 8
    ]
    expected_bg5_words = [
        expected_bg5[index] | (expected_bg5[index + 1] << 8)
        for index in range(0, 8, 2)
    ]
    expected_bg7_words = [
        expected_bg7[index] | (expected_bg7[index + 1] << 8)
        for index in range(0, 8, 2)
    ]
    actual_bg5 = [int(value, 16) for value in values["bg5"].split(",")]
    actual_bg7 = [int(value, 16) for value in values["bg7"].split(",")]
    tooth_found, tooth_matched = (
        int(value) for value in values["tooth"].split(",")
    )
    fire_found, fire_matched = (
        int(value) for value in values["fire"].split(",")
    )
    support_found, support_matched = (
        int(value) for value in values["support"].split(",")
    )
    transient_mismatch_frames = int(values["transient_mismatch_frames"])
    checks = {
        "historical spike room remains live Stage 1": values["scene"] == "02",
        "active map contains the rotating spike family": active_found >= 20,
        "every active-map spike tile uses its YAML material split": (
            active_matched == active_found
        ),
        "visible map contains complete BG7 teeth": (
            tooth_found >= 4 and tooth_matched == tooth_found
        ),
        "visible map contains BG5 rings and fire body": (
            fire_found >= 4 and fire_matched == fire_found
        ),
        "visible support and shadow cells remain metallic BG6": (
            support_found >= 2 and support_matched == support_found
        ),
        "every sampled animation frame keeps tile and palette atomic": (
            transient_mismatch_frames == 0
        ),
        "live BG5 CRAM matches the candidate": (
            actual_bg5 == expected_bg5_words
        ),
        "live Stage-1 BG7 CRAM matches the YAML hazard row": (
            actual_bg7 == expected_bg7_words
        ),
    }
    return {
        "state": str(state),
        "state_sha256": digest(state),
        "normalized_state": str(normalized),
        "report": str(report_path),
        "screenshot": str(screenshot_path),
        "active_map": active_base,
        "map9800": {"found": found9800, "matched": matched9800},
        "map9c00": {"found": found9c00, "matched": matched9c00},
        "tooth": {"found": tooth_found, "matched": tooth_matched},
        "fire": {"found": fire_found, "matched": fire_matched},
        "support": {"found": support_found, "matched": support_matched},
        "transient_mismatch_frames": transient_mismatch_frames,
        "first_transient_mismatch": values["first_transient_mismatch"],
        "bg5": [f"{word:04X}" for word in actual_bg5],
        "bg7": [f"{word:04X}" for word in actual_bg7],
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--states", type=Path, default=STATE_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mgba", type=Path, default=DEFAULT_MGBA)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--static-only", action="store_true")
    args = parser.parse_args()

    rom_path = args.rom.resolve()
    rom = rom_path.read_bytes()
    if len(rom) != 0x40000:
        print(f"FAIL: ROM size is {len(rom)}, expected 262144")
        return 1

    rooms = {
        name: room_source((args.states / name).resolve())
        for name in STATE_NAMES
    }
    observed_family = {
        tile
        for room in rooms.values()
        for tile in room
        if 0x60 <= tile <= 0x7F
    }
    cylinder_room = rooms[STATE_NAMES[0]]
    rows = [
        cylinder_room[offset:offset + 24]
        for offset in range(0, ROOM_SIZE, 24)
    ]
    body_rows = [index for index, row in enumerate(rows) if CYLINDER_BODY in row]
    paired_rows = [
        row
        for row in body_rows
        if row + 1 < len(rows) and CYLINDER_LOWER in rows[row + 1]
    ]

    table = rom[BG_TABLE_OFFSET:BG_TABLE_OFFSET + 256]
    histogram = dict(sorted(Counter(table).items()))
    stock = STOCK_ROM.read_bytes()
    variants = compile_stage1_hazard_variants(stock, HAZARD)
    candidate_variants = {
        tile: rom[
            HAZARD.source_offset + tile * 16:
            HAZARD.source_offset + (tile + 1) * 16
        ]
        for tile in HAZARD.art_tiles
    }
    changed_bytes = sum(
        before != after
        for tile in sorted(HAZARD.art_tiles)
        for before, after in zip(
            stock[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ],
            candidate_variants[tile],
        )
    )
    hazard_slot, hazard_palette = load_stage1_hazard_palette(PALETTE_YAML)
    hazard_palette_off = (
        BANK13 + STAGE1_HAZARD_BG7_SOURCE_ADDR - 0x4000
    )
    loader, loader_ext, copy_cram8 = build_phased_palette_loader()
    loader_off = BANK13 + PALETTE_LOADER_ADDR - 0x4000
    loader_ext_off = BANK13 + PALETTE_LOADER_EXT_ADDR - 0x4000
    copy_cram8_off = BANK13 + PALETTE_COPY_CRAM8_ADDR - 0x4000
    runtime_gate = build_stage1_attr_runtime()
    hazard_row_helper, hazard_row_compiler = build_stage1_hazard_row_helper()
    hazard_row_helper_off = (
        BANK14 + STAGE1_HAZARD_ROW_HELPER_ADDR - 0x4000
    )
    hazard_row_compiler_off = (
        BANK14 + STAGE1_HAZARD_ROW_COMPILER_ADDR - 0x4000
    )
    hazard_dispatcher = build_stage1_hazard_dispatcher()
    hazard_dispatcher_off = BANK13 + LAVA_ATTR_DECIDER_ADDR - 0x4000
    map9800_phase_keys = {
        (signature & 0x7F) + 1
        for signature in CAPTURED_PHASE_SIGNATURES
    }
    map9c00_phase_keys = {
        (((signature & 0x7F) | 0x80) + 1) & 0xFF
        for signature in CAPTURED_PHASE_SIGNATURES
    }
    checks = {
        "tracked BG room fixtures cover every 60-7F animation tile": (
            observed_family == SPIKE_TILES
        ),
        "rotating cylinder body is serialized in the packed BG room": (
            bool(paired_rows)
        ),
        "all 24 production source-art variants match the YAML compiler": (
            candidate_variants == variants
        ),
        "the 20 audience-approved variants retain their exact artifact hash": (
            hashlib.sha256(b"".join(
                candidate_variants[tile]
                for tile in sorted(APPROVED_ART_TILES)
            )).hexdigest() == APPROVED_ART_SHA256
        ),
        "duplicate 61/71 body phases exactly match remapped 6E/7E": (
            candidate_variants[0x61] == candidate_variants[0x6E]
            and candidate_variants[0x71] == candidate_variants[0x7E]
        ),
        "production source-art delta is exactly 258 of 384 bytes": (
            changed_bytes == 258 and len(candidate_variants) == 24
        ),
        "all 8 support and cast-shadow source tiles remain stock": all(
            rom[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ] == stock[
                HAZARD.source_offset + tile * 16:
                HAZARD.source_offset + (tile + 1) * 16
            ]
            for tile in SPIKE_SUPPORT_TILES
        ),
        "tooth frames select scene-local BG7": all(
            table[tile] == SPIKE_TOOTH_PALETTE
            for tile in SPIKE_TOOTH_TILES
        ),
        "rings and continuous body select fire BG5": all(
            table[tile] == SPIKE_FIRE_PALETTE
            for tile in SPIKE_FIRE_TILES
        ),
        "wall-facing cylinder connector selects fire BG5": all(
            table[tile] == SPIKE_CONNECTOR_PALETTE
            for tile in SPIKE_CONNECTOR_TILES
        ),
        "unpainted support and shadow cells remain metallic BG6": all(
            table[tile] == SPIKE_SUPPORT_PALETTE
            for tile in SPIKE_SUPPORT_TILES
        ),
        "legacy spike family selects visible hazard BG5": all(
            table[tile] == SPIKE_FIRE_PALETTE
            for tile in LEGACY_SPIKE_TILES
        ),
        "complete Stage 1 palette table equals its YAML compilation": (
            table == EXPECTED_TABLE
        ),
        "Stage 1 palette histogram is exact": histogram == EXPECTED_HISTOGRAM,
        "candidate embeds the YAML Stage-1 hazard palette row": (
            hazard_slot == SPIKE_TOOTH_PALETTE
            and rom[
                hazard_palette_off:hazard_palette_off + 8
            ] == hazard_palette
        ),
        "candidate embeds the cycle-neutral inline Stage-1 BG7 selector": (
            rom[loader_off:loader_off + len(loader)] == loader
            and rom[
                loader_ext_off:loader_ext_off + len(loader_ext)
            ] == loader_ext
        ),
        "candidate embeds the shared LCD-safe eight-byte CRAM copier": (
            rom[
                copy_cram8_off:copy_cram8_off + len(copy_cram8)
            ] == copy_cram8
            and rom[
                copy_cram8_off + len(copy_cram8):copy_cram8_off + 18
            ] == bytes(18 - len(copy_cram8))
        ),
        "candidate embeds one scene-gated Stage 1 attr runtime": (
            runtime_gate.startswith(bytes.fromhex("FA80D8FE02"))
            and rom.count(runtime_gate) == 1
        ),
        "captured hazard phase keys are nonzero and map-disjoint": (
            len(map9800_phase_keys) == len(CAPTURED_PHASE_SIGNATURES)
            and len(map9c00_phase_keys) == len(CAPTURED_PHASE_SIGNATURES)
            and 0 not in map9800_phase_keys
            and 0 not in map9c00_phase_keys
            and map9800_phase_keys.isdisjoint(map9c00_phase_keys)
        ),
        "candidate embeds the bounded bank-14 animation publisher": (
            rom[
                hazard_row_helper_off:
                hazard_row_helper_off + len(hazard_row_helper)
            ] == hazard_row_helper
            and rom.count(hazard_row_helper) == 1
            and rom[
                hazard_row_compiler_off:
                hazard_row_compiler_off + len(hazard_row_compiler)
            ] == hazard_row_compiler
            and rom.count(hazard_row_compiler) == 1
        ),
        "candidate embeds the shared Stage-1/Stage-5 dispatcher": (
            rom[
                hazard_dispatcher_off:
                hazard_dispatcher_off + len(hazard_dispatcher)
            ] == hazard_dispatcher
        ),
    }
    receipt = {
        "rom": str(rom_path),
        "states": list(STATE_NAMES),
        "observed_animation_tiles": [
            f"{tile:02X}" for tile in sorted(observed_family)
        ],
        "cylinder_body_rows": paired_rows,
        "tooth_palette": SPIKE_TOOTH_PALETTE,
        "fire_palette": SPIKE_FIRE_PALETTE,
        "support_palette": SPIKE_SUPPORT_PALETTE,
        "connector_palette": SPIKE_CONNECTOR_PALETTE,
        "art_tiles": [f"{tile:02X}" for tile in sorted(HAZARD.art_tiles)],
        "art_changed_bytes": changed_bytes,
        "hazard_palette_source": (
            f"bank13:{STAGE1_HAZARD_BG7_SOURCE_ADDR:04X}"
        ),
        "hazard_palette": hazard_palette.hex(),
        "selector": f"inline bank13:{PALETTE_LOADER_EXT_ADDR:04X}",
        "cram8_copier": f"bank13:{PALETTE_COPY_CRAM8_ADDR:04X}",
        "table_histogram": {str(key): value for key, value in histogram.items()},
        "expected_table_histogram": {
            str(key): value for key, value in EXPECTED_HISTOGRAM.items()
        },
        "checks": checks,
        "passed": all(checks.values()),
    }
    live = None
    natural_live = None
    if not args.static_only and receipt["passed"]:
        if not args.mgba.is_file():
            print(f"FAIL: guarded mGBA frontend not found: {args.mgba}")
            return 1
        if args.output:
            live_output = args.output.parent / "stage1-spike-live"
            live = live_receipt(
                rom_path,
                (args.states / LIVE_STATE).resolve(),
                args.mgba.resolve(),
                live_output,
                args.timeout,
            )
            natural_live = live_receipt(
                rom_path,
                (args.states / LIVE_STATE).resolve(),
                args.mgba.resolve(),
                args.output.parent / "stage1-spike-natural",
                args.timeout,
                prefix_name="stage1-spike-natural",
                reinitialize=False,
                settle=420,
            )
        else:
            with tempfile.TemporaryDirectory(prefix="penta-spike-live-") as name:
                live = live_receipt(
                    rom_path,
                    (args.states / LIVE_STATE).resolve(),
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                )
                natural_live = live_receipt(
                    rom_path,
                    (args.states / LIVE_STATE).resolve(),
                    args.mgba.resolve(),
                    Path(name),
                    args.timeout,
                    prefix_name="stage1-spike-natural",
                    reinitialize=False,
                    settle=420,
                )
                live["normalized_state"] = "temporary"
                live["report"] = "temporary"
                live["screenshot"] = "temporary"
                natural_live["normalized_state"] = "temporary"
                natural_live["report"] = "temporary"
                natural_live["screenshot"] = "temporary"
        receipt["live"] = live
        receipt["natural_live"] = natural_live
        receipt["passed"] = (
            receipt["passed"] and live["passed"] and natural_live["passed"]
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n")

    failed = [name for name, passed in checks.items() if not passed]
    if live:
        failed.extend(
            name for name, passed in live["checks"].items() if not passed
        )
    if natural_live:
        failed.extend(
            "untouched state: " + name
            for name, passed in natural_live["checks"].items()
            if not passed
        )
    if failed:
        print("FAIL: " + "; ".join(failed))
        return 1
    print(
        "PASS: tracked room sources prove BG-only 60-7F spike animation; "
        "24 YAML-compiled art variants use BG7 teeth + BG5 rings/body/wall "
        "connector + BG6 supports"
        + (
            "; current-ROM mGBA confirms the visible map and CRAM."
            if live else "."
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
