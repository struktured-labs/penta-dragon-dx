#!/usr/bin/env python3
"""Trace the cold Stage-1 owners of collision-sensitive bank-zero CHR."""

# PENTA_CHECKED_SINGLEFLIGHT_DELEGATION: run_route invokes only the checked-in
# fail-closed wrapper and never accepts a caller-selected emulator executable.

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from verify_stage1_north_integrity import run_route


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
SELF = Path(__file__).resolve()
PROBE = Path(__file__).with_name("probe_stage1_north_integrity.lua")
ROUTE_DRIVER = Path(__file__).with_name("verify_stage1_north_integrity.py")
MGBA_LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
MGBA_GUARD = ROOT / "scripts/mgba_singleflight.py"
PAGE_BYTES = 0x100
CANONICAL_OFFSET = 0x1D000
PAGE_SHA256 = (
    "d79280fbc224237ac1303c2535a4894fc3076f0e5fd2605f06c0685e1937d09a",
    "0f2108c1ee36e7211b10f1dac478a6fdf8548ecc2b275407e40a2a4af9116654",
    "fd6328be6426d0fa96fef8c6c494123ba934c550daf4494ff46db6edad7e36c1",
    "88656e3480e11469b7e1b3966c93d065eefbd278791cbe7859ba7ca75394f0ef",
    "13c40d0ee903577a70fc4ab9a21fbe0d7e9fa451e4093fa8248ea40a02a3899e",
    "2966c2290017962ec7c22e291bc4dcffc1297ee53ed93a0ce476022f0a9f957a",
    "f05230b6c837c37bc682f6f5d6f836668e9b0e7765c7bb13a17cd6fd39bb3b53",
    "0b8c7314ed5e2773b31d95ea2bc9902c96e8fc5ea539cb3bb15cf790cbdc7159",
)
PAGE_CONTRACTS = {
    0x9000 + index * PAGE_BYTES: {
        "rom_offset": CANONICAL_OFFSET + index * PAGE_BYTES,
        "selector_address": 0xFFA4 + index,
        "selector_value": 0x10 + index,
        "sha256": PAGE_SHA256[index],
    }
    for index in range(8)
}
SELECTOR_FIELDS = tuple(f"ffa{n:x}" for n in range(4, 12))
STAGE_LOAD_SCENE = 0x18
STAGE_LOAD_BANK = 0x07
STOCK_COPY_PCS = frozenset((0x0D47, 0x0D4A))
STOCK_SELECTOR_LOOP_ADDR = 0x0C9C
STOCK_SELECTOR_LOOP = bytes.fromhex(
    "21A4FF06081690C52AFE403009CD350D14C10520F2C9"
)
STOCK_COPY_CALL = bytes.fromhex("CD350D")
STOCK_COPY_CALL_OFFSET = STOCK_SELECTOR_LOOP.index(STOCK_COPY_CALL)
STOCK_COPY_CALL_ADDR = STOCK_SELECTOR_LOOP_ADDR + STOCK_COPY_CALL_OFFSET
STOCK_COPY_RETURN = STOCK_COPY_CALL_ADDR + len(STOCK_COPY_CALL)
if STOCK_COPY_CALL_ADDR != 0x0CA9 or STOCK_COPY_RETURN != 0x0CAC:
    raise AssertionError("stock selector-loop CALL geometry drifted")
MAX_STAGE_LOAD_TO_GAMEPLAY_FRAMES = 30
EVENT_RE = re.compile(
    r"^f(?P<frame>\d+):g(?P<gameplay>\d+):a(?P<address>[0-9A-F]{4}):"
    r"o(?P<old>[0-9A-F]{2}):n(?P<new>[0-9A-F]{2}):"
    r"p(?P<pc>[0-9A-F]{4}):b(?P<bank>[0-9A-F]{2}):"
    r"af(?P<af>[0-9A-F]{4}):bc(?P<bc>[0-9A-F]{4}):"
    r"de(?P<de>[0-9A-F]{4}):hl(?P<hl>[0-9A-F]{4}):"
    r"sp(?P<sp>[0-9A-F]{4}):k(?P<caller>[0-9A-F]{4}):"
    r"u(?P<ffa4>[0-9A-F]{2})(?P<ffa5>[0-9A-F]{2})"
    r"(?P<ffa6>[0-9A-F]{2})(?P<ffa7>[0-9A-F]{2})"
    r"(?P<ffa8>[0-9A-F]{2})(?P<ffa9>[0-9A-F]{2})"
    r"(?P<ffaa>[0-9A-F]{2})(?P<ffab>[0-9A-F]{2}):"
    r"l(?P<lcdc>[0-9A-F]{2}):s(?P<scene>[0-9A-F]{2}):"
    r"r(?P<room>[0-9A-F]{2}):i(?P<active>[0-9A-F]{2})$"
)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def file_identity(path: Path) -> dict[str, object]:
    resolved = path.resolve(strict=True)
    payload = resolved.read_bytes()
    return {
        "path": str(path.resolve()),
        "resolved_path": str(resolved),
        "size": len(payload),
        "sha256": digest(payload),
    }


def resolved_mgba_qt() -> Path:
    # run_route removes PENTA_MGBA_QT_BIN before invoking the checked-in
    # wrapper, so this is the wrapper's exact deterministic search order.
    for candidate in (
        Path("/home/struktured/bin/mgba-qt"),
        Path("/usr/bin/mgba-qt"),
        Path("/usr/local/bin/mgba-qt"),
    ):
        if candidate.is_file():
            return candidate.resolve(strict=True)
    raise FileNotFoundError("checked single-flight wrapper has no mGBA-Qt")


def tool_identities() -> dict[str, dict[str, object]]:
    return {
        "verifier": file_identity(SELF),
        "probe": file_identity(PROBE),
        "route_driver": file_identity(ROUTE_DRIVER),
        "mgba_launcher": file_identity(MGBA_LAUNCHER),
        "mgba_guard": file_identity(MGBA_GUARD),
        "mgba_qt": file_identity(resolved_mgba_qt()),
    }


def checked_output(path: Path) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    if resolved == scratch or scratch not in resolved.parents:
        raise ValueError("output must be a child of repository tmp/")
    return resolved


def parse_events(value: str) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    for raw in filter(None, value.split(";")):
        match = EVENT_RE.fullmatch(raw)
        if match is None:
            raise ValueError(f"malformed CHR writer event: {raw}")
        row = {
            name: int(text, 10 if name in {"frame", "gameplay"} else 16)
            for name, text in match.groupdict().items()
        }
        if not any(
            base <= row["address"] < base + PAGE_BYTES
            for base in PAGE_CONTRACTS
        ):
            raise ValueError(f"out-of-page CHR writer event: {raw}")
        rows.append(row)
    return rows


def canonical_pages(rom: bytes) -> dict[int, bytes]:
    """Return independently pinned Stage-1 selector pages from one ROM."""

    pages: dict[int, bytes] = {}
    for address, contract in PAGE_CONTRACTS.items():
        offset = int(contract["rom_offset"])
        page = rom[offset:offset + PAGE_BYTES]
        if len(page) != PAGE_BYTES:
            raise ValueError(
                f"candidate canonical page ${address:04X} is truncated"
            )
        expected_sha256 = str(contract["sha256"])
        if digest(page) != expected_sha256:
            raise ValueError(
                f"candidate canonical page ${address:04X} identity changed"
            )
        pages[address] = page
    return pages


def validate_stock_loader(rom: bytes) -> None:
    """Pin the CALL instruction from which the probe derives its return PC."""

    actual = rom[
        STOCK_SELECTOR_LOOP_ADDR:
        STOCK_SELECTOR_LOOP_ADDR + len(STOCK_SELECTOR_LOOP)
    ]
    if actual != STOCK_SELECTOR_LOOP:
        raise ValueError(
            "candidate stock selector loop $0C9C-$0CB1 changed"
        )


def page_base(address: int) -> int:
    for base in PAGE_CONTRACTS:
        if base <= address < base + PAGE_BYTES:
            return base
    raise ValueError(f"unowned CHR address: ${address:04X}")


def trace_counts(report: dict[str, str], parsed_count: int) -> dict[str, int | bool]:
    claimed = int(report.get("chr_write_count", "-1"))
    stored = int(report.get("chr_write_stored_count", "-1"))
    dropped = int(report.get("chr_write_dropped_count", "-1"))
    if (
        min(claimed, stored, dropped) < 0
        or stored != parsed_count
        or claimed != stored + dropped
    ):
        raise ValueError(
            "CHR writer event count drift: "
            f"total={claimed} stored={stored} "
            f"dropped={dropped} parsed={parsed_count}"
        )
    return {
        "claimed": claimed,
        "stored": stored,
        "dropped": dropped,
        "complete": dropped == 0,
    }


def analyze_events(
    events: list[dict[str, int]],
    expected: dict[int, bytes],
    first_gameplay: int,
) -> dict[str, object]:
    """Bind one exact pre-gameplay stock load and all later page writes."""

    if first_gameplay <= 0:
        raise ValueError("cold route has no positive first-gameplay frame")
    if any(
        later["frame"] < earlier["frame"]
        for earlier, later in zip(events, events[1:])
    ):
        raise ValueError("CHR writer events are not frame ordered")

    stage_load_positions = [
        index for index, row in enumerate(events)
        if row["frame"] < first_gameplay
        and row["scene"] == STAGE_LOAD_SCENE
        and row["active"] == 1
        and row["bank"] == STAGE_LOAD_BANK
        and row["pc"] in STOCK_COPY_PCS
        and row["caller"] == STOCK_COPY_RETURN
    ]
    stage_load = [events[index] for index in stage_load_positions]
    expected_addresses = list(range(0x9000, 0x9800))
    stage_load_sequence_exact = (
        [row["address"] for row in stage_load] == expected_addresses
    )
    stage_load_owner_exact = stage_load_sequence_exact and all(
        row["pc"] == (0x0D47 if row["address"] & 1 == 0 else 0x0D4A)
        and row["de"] == row["address"]
        and row["hl"] == 0x5001 + row["address"] - 0x9000
        and row["gameplay"] == 0
        for row in stage_load
    )
    stage_load_bad_bytes = [
        row for row in stage_load
        if row["new"] != expected[page_base(row["address"])][
            row["address"] - page_base(row["address"])
        ]
    ]
    stage_load_bad_selectors = [
        row for row in stage_load
        if any(
            row[field] != 0x10 + index
            for index, field in enumerate(SELECTOR_FIELDS)
        )
    ]

    coverage: dict[str, dict[str, object]] = {}
    coverage_ok = True
    for base in PAGE_CONTRACTS:
        addresses = {
            row["address"] for row in stage_load
            if base <= row["address"] < base + PAGE_BYTES
        }
        missing = sorted(set(range(base, base + PAGE_BYTES)) - addresses)
        page_ok = not missing
        coverage_ok &= page_ok
        coverage[f"{base:04X}"] = {
            "observed_addresses": len(addresses),
            "missing_addresses": [f"{address:04X}" for address in missing],
            "complete": page_ok,
        }

    stage_load_frames = [row["frame"] for row in stage_load]
    load_to_gameplay = (
        first_gameplay - max(stage_load_frames) if stage_load_frames else -1
    )
    stage_load_fresh = (
        1 <= load_to_gameplay <= MAX_STAGE_LOAD_TO_GAMEPLAY_FRAMES
    )
    # Do not start only after the final stock-copy event.  A foreign writer
    # can run in the middle of the 0x800-byte load and be overwritten by a
    # later stock event, which would otherwise disappear from both this phase
    # and the final VRAM dump.  Once the qualifying load begins, every
    # pre-gameplay event not owned by that exact load is evidence we retain.
    stage_load_position_set = set(stage_load_positions)
    post_load_pre_gameplay = (
        [
            row for index, row in enumerate(
                events[stage_load_positions[0]:],
                start=stage_load_positions[0],
            )
            if index not in stage_load_position_set
            and row["frame"] < first_gameplay
        ]
        if stage_load_positions else []
    )
    bad_post_load_pre_gameplay = [
        row for row in post_load_pre_gameplay
        if row["new"] != expected[page_base(row["address"])][
            row["address"] - page_base(row["address"])
        ]
    ]
    post_gameplay = [row for row in events if row["frame"] >= first_gameplay]
    bad_post_gameplay = [
        row for row in post_gameplay
        if row["new"] != expected[page_base(row["address"])][
            row["address"] - page_base(row["address"])
        ]
    ]
    return {
        "stage_load_event_count": len(stage_load),
        "stage_load_first_frame": min(stage_load_frames, default=-1),
        "stage_load_last_frame": max(stage_load_frames, default=-1),
        "stage_load_to_gameplay_frames": load_to_gameplay,
        "stage_load_fresh": stage_load_fresh,
        "stage_load_sequence_exact": stage_load_sequence_exact,
        "stage_load_owner_exact": stage_load_owner_exact,
        "stage_load_coverage": coverage,
        "stage_load_coverage_exact": coverage_ok,
        "stage_load_bad_byte_count": len(stage_load_bad_bytes),
        "stage_load_bad_byte_examples": stage_load_bad_bytes[:16],
        "stage_load_bad_selector_count": len(stage_load_bad_selectors),
        "stage_load_bad_selector_examples": stage_load_bad_selectors[:16],
        "post_load_pre_gameplay_event_count": len(post_load_pre_gameplay),
        "bad_post_load_pre_gameplay_event_count": len(
            bad_post_load_pre_gameplay
        ),
        "bad_post_load_pre_gameplay_examples": (
            bad_post_load_pre_gameplay[:16]
        ),
        "post_gameplay_event_count": len(post_gameplay),
        "bad_post_gameplay_event_count": len(bad_post_gameplay),
        "bad_post_gameplay_examples": bad_post_gameplay[:16],
        "exact": (
            bool(stage_load)
            and stage_load_sequence_exact
            and stage_load_owner_exact
            and coverage_ok
            and stage_load_fresh
            and not stage_load_bad_bytes
            and not stage_load_bad_selectors
            and not bad_post_load_pre_gameplay
            and not bad_post_gameplay
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--frames", type=int, default=12000)
    parser.add_argument("--target-camera", type=lambda value: int(value, 0),
                        default=0x03A4)
    parser.add_argument("--target-room", type=lambda value: int(value, 0),
                        default=1)
    args = parser.parse_args()

    rom = args.rom.resolve()
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    try:
        output = checked_output(args.output)
    except ValueError as error:
        parser.error(str(error))
    if output == rom or output in rom.parents:
        parser.error("output must not contain the source ROM")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    rom_bytes = rom.read_bytes()
    try:
        validate_stock_loader(rom_bytes)
        expected = canonical_pages(rom_bytes)
    except ValueError as error:
        parser.error(str(error))
    candidate_sha256 = digest(rom_bytes)
    tools_before = tool_identities()

    report = run_route(
        rom=rom,
        output=output,
        frames=args.frames,
        play_frames=240,
        timeout=args.timeout,
        target_camera=args.target_camera,
        target_room=args.target_room,
        target_settle=12,
        snap_interval=0,
        fire=False,
        trace=None,
        trace_writes=False,
        trace_camera_min=0x02B0,
        trace_camera_max=0x02D0,
        trace_chr_writes=True,
    )
    runtime_rom = output / "runtime/route.gb"
    if not runtime_rom.is_file():
        raise RuntimeError("guarded route did not preserve its tested ROM copy")
    source_sha256_after = digest(rom.read_bytes())
    runtime_sha256 = digest(runtime_rom.read_bytes())
    if source_sha256_after != candidate_sha256:
        raise RuntimeError("source candidate changed during CHR writer route")
    if runtime_sha256 != candidate_sha256:
        raise RuntimeError("guarded route tested a different ROM copy")
    tools_after = tool_identities()
    if tools_after != tools_before:
        raise RuntimeError("CHR writer tool identity changed during route")
    events = parse_events(report.get("chr_writes", ""))
    try:
        counts = trace_counts(report, len(events))
    except ValueError as error:
        raise RuntimeError(str(error)) from error
    claimed_count = int(counts["claimed"])
    stored_count = int(counts["stored"])
    dropped_count = int(counts["dropped"])

    final_art = (output / "vram-signed-positive-tiles.bin").read_bytes()
    if len(final_art) != 0x800:
        raise RuntimeError("final signed-positive CHR dump has wrong width")
    final_pages: dict[int, bytes] = {}
    final_mismatches: dict[int, list[int]] = {}
    for address, wanted in expected.items():
        offset = address - 0x9000
        actual = final_art[offset:offset + PAGE_BYTES]
        final_pages[address] = actual
        final_mismatches[address] = [
            index for index, (got, need) in enumerate(
                zip(actual, wanted, strict=True)
            ) if got != need
        ]

    first_gameplay = int(report["first_gameplay"])
    analysis = analyze_events(events, expected, first_gameplay)
    writers = sorted({
        f"bank{row['bank']:02X}:${row['pc']:04X}" for row in events
    })
    final_exact = not any(final_mismatches.values())
    trace_complete = bool(counts["complete"])
    receipt = {
        "schema": "penta-stage1-chr-writer-cold-route-v3",
        "status": "PASS" if (
            final_exact and events and trace_complete and analysis["exact"]
        ) else "FAIL",
        "candidate": str(rom),
        "candidate_sha256": candidate_sha256,
        "tested_runtime_rom": str(runtime_rom.resolve()),
        "tested_runtime_rom_sha256": runtime_sha256,
        "tool_identities": tools_before,
        "route": {
            "cold_blank_sram": True,
            "target_room": args.target_room,
            "target_camera": args.target_camera,
            "first_gameplay_frame": first_gameplay,
            "final_state": report.get("final_state"),
        },
        "contract": {
            "physical_pages": "$9000-$97FF (eight 256-byte pages)",
            "canonical_rom_ranges": (
                "file 0x1D000-0x1D7FF (bank7:$5000-$57FF)"
            ),
            "canonical_sha256": {
                f"{address:04X}": digest(page)
                for address, page in expected.items()
            },
            "stock_selector_array": "$FFA4-$FFAB",
            "selector_values": "$10,$11,$12,$13,$14,$15,$16,$17",
            "known_DX_collisions": ["$FFA5", "$FFA7", "$FFA8", "$FFA9"],
            "stock_loader": (
                f"${STOCK_SELECTOR_LOOP_ADDR:04X} CALL "
                f"${int.from_bytes(STOCK_COPY_CALL[1:], 'little'):04X} at "
                f"${STOCK_COPY_CALL_ADDR:04X}; return site "
                f"${STOCK_COPY_RETURN:04X}"
            ),
            "watchpoint": (
                "VBK0 writes only, with PC/software-bank/register/selector state"
            ),
        },
        "evidence": {
            "event_count": claimed_count,
            "stored_event_count": stored_count,
            "dropped_event_count": dropped_count,
            "trace_complete": trace_complete,
            "writers": writers,
            "phase_analysis": analysis,
            "final_pages": {
                f"{address:04X}": {
                    "sha256": digest(final_pages[address]),
                    "mismatch_bytes": len(final_mismatches[address]),
                    "first_mismatch": (
                        final_mismatches[address][0]
                        if final_mismatches[address] else -1
                    ),
                }
                for address in PAGE_CONTRACTS
            },
            "final_exact": final_exact,
            "events": events,
        },
    }
    receipt_path = output / "chr-writer-receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    console = dict(receipt)
    console["evidence"] = {
        key: value for key, value in receipt["evidence"].items()
        if key != "events"
    }
    console["receipt"] = str(receipt_path)
    print(json.dumps(console, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
