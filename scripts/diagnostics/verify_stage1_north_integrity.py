#!/usr/bin/env python3
"""Gate natural Stage-1 north geometry and candidate CGB presentation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from build_v301_gdma import _bg_table  # noqa: E402
from stage1_hazard_art import load_stage1_hazard_config  # noqa: E402
from diagnostics.verify_stage1_spike_palettes import (  # noqa: E402
    publication_boundary as reviewed_publication_boundary,
)
from stage1_room01_wall_oracle import (  # noqa: E402
    load_reviewed_wall_contract,
    reviewed_room01_context_map,
    reviewed_room01_tile_attr_map,
    reviewed_stage1_wall_oracle,
)


PROBE = Path(__file__).with_name("probe_stage1_north_integrity.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
DEFAULT_BASELINE = ROOT / "rom/Penta Dragon (J).gb"
TRAJECTORY_SCHEMA = "penta-stage1-north-trajectory-v3"
TRAJECTORY_HEADER_SIZE = 31
TRAJECTORY_VIEW_SIZE = 21 * 19
TRAJECTORY_RECORD_SIZE = TRAJECTORY_HEADER_SIZE + 2 * TRAJECTORY_VIEW_SIZE
OWNER_STATUS_DMG = 0
OWNER_STATUS_CGB_OWNED = 1
OWNER_STATUS_CGB_MISSING = 2
OWNER_STATUS_CGB_INVALID = 3
OWNER_STATUS_NAMES = {
    OWNER_STATUS_DMG: "dmg-unsupported",
    OWNER_STATUS_CGB_OWNED: "cgb-publication-owned",
    OWNER_STATUS_CGB_MISSING: "cgb-missing",
    OWNER_STATUS_CGB_INVALID: "cgb-invalid",
}
PRIMARY_PUBLISHER_ADDR = 0x12E0
PRIMARY_PUBLISHER_END = 0x1303
OLD_PRIMARY = bytes.fromhex(
    "FA 0B DC B7 28 04 3E 8B 18 02 3E 83 E0 40 "
    "F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 C9"
)
NEW_PRIMARY = bytes.fromhex(
    "F3 F0 97 FE 02 28 07 FA 00 DC E6 0F E0 43 "
    "FA 02 DC E6 0F E0 42 FA 0B DC B7 3E 83 28 02 "
    "CB DF E0 40 FB C9"
)
VBLANK_PRIMARY = bytes.fromhex(
    "F3 00 F0 40 87 30 06 F0 44 FE 90 38 FA "
    "FA 00 DC E6 0F E0 43 FA 02 DC E6 0F E0 42 "
    "F0 40 EE 08 E0 40 FB C9"
)
PUBLICATION_VARIANTS = {
    "legacy-v1": {"bytes": OLD_PRIMARY, "publication_pc": 0x12EC},
    "r320-v1": {"bytes": NEW_PRIMARY, "publication_pc": 0x12FF},
    "r346-vblank-v1": {
        "bytes": VBLANK_PRIMARY,
        "publication_pc": 0x12FF,
    },
}
STAGE1_BASE_ATTRS = _bg_table()
STAGE1_HAZARD = load_stage1_hazard_config()
STAGE1_FIRE_TILES = STAGE1_HAZARD.ring_tiles | STAGE1_HAZARD.body_tiles
REVIEWED_WALL_FIXTURE = (
    Path(__file__).with_name("fixtures") / "stage1_room01_wall_oracle.json"
)
REVIEWED_WALL_CONTRACT = load_reviewed_wall_contract(REVIEWED_WALL_FIXTURE)
REVIEWED_WALL_CONTEXT = reviewed_room01_context_map(REVIEWED_WALL_CONTRACT)
REVIEWED_WALL_TILE_CONTEXT = reviewed_room01_tile_attr_map(
    REVIEWED_WALL_CONTRACT
)
REVIEWED_WALL_TILE_POLICY = {
    f"{room:02X}:{tile:02X}": attr
    for (room, tile), attr in sorted(REVIEWED_WALL_TILE_CONTEXT.items())
}
RECEIPT_SCHEMA = "penta-stage1-north-integrity-v3"


def stop_owned_process_group(process: subprocess.Popen[str]) -> None:
    """Stop only the guarded mGBA session created by this route."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def select_publication_variant(
    matches: list[tuple[str, dict[str, object]]],
) -> tuple[str, dict[str, object]]:
    """Require exactly one reviewed primary publisher variant."""
    if len(matches) != 1:
        names = [name for name, _ in matches]
        raise ValueError(
            "primary publisher evidence is "
            f"{'missing' if not matches else 'ambiguous'}: {names}"
        )
    return matches[0]


def detect_publication_boundary(rom: bytes) -> dict[str, object]:
    """Bind the owner hook to an exact reviewed 35-byte ROM preimage."""
    if len(rom) < PRIMARY_PUBLISHER_END:
        raise ValueError("ROM is truncated before the primary publisher")
    primary = rom[PRIMARY_PUBLISHER_ADDR:PRIMARY_PUBLISHER_END]
    try:
        reviewed = reviewed_publication_boundary(rom)
    except RuntimeError as error:
        # Preserve this verifier's fail-closed public contract while sharing
        # the stricter multi-site publisher detector with the spike gate.
        raise ValueError(
            "primary publisher evidence is missing: []"
        ) from error
    name = str(reviewed["variant"])
    publication_pc = int(reviewed["pc"])
    publication_segment = 0x0D if publication_pc >= 0x4000 else 0
    file_offset = (
        publication_pc if publication_segment == 0
        else publication_segment * 0x4000 + publication_pc - 0x4000
    )
    if rom[file_offset:file_offset + 2] != bytes.fromhex("E0 40"):
        raise ValueError(
            f"{name} does not write LCDC at ${publication_pc:04X}"
        )
    return {
        "variant": name,
        "range": "12E0-1302",
        "bytes": len(primary),
        "primary_hex": primary.hex().upper(),
        "primary_sha256": hashlib.sha256(primary).hexdigest(),
        "publication_pc": publication_pc,
        "publication_pc_hex": f"{publication_pc:04X}",
        "publication_segment": publication_segment,
        "publication_segment_hex": f"{publication_segment:02X}",
    }


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def physical_page_owner_report(
    report: dict[str, str],
    *,
    expect_cgb: bool,
    expected_publication: dict[str, object],
) -> dict[str, object]:
    """Validate probe-level hook provenance and summarize its evidence."""
    integer_fields = (
        "map_owner_arm_events",
        "map_owner_publications",
        "map_owner_reused_commits",
        "map_owner_superseded_arms",
        "map_owner_invalid_arms",
        "map_owner_invalid_commits",
        "map_owner_missing_commits",
        "map_owner_missing_trajectory_frames",
        "map_owner_invalid_trajectory_frames",
    )
    errors: list[str] = []
    counters: dict[str, int] = {}
    if report.get("trajectory_schema") != TRAJECTORY_SCHEMA:
        errors.append("trajectory-schema-missing-or-stale")
    cgb_value = report.get("cgb_rom")
    if cgb_value != ("1" if expect_cgb else "0"):
        errors.append("rom-mode-mismatch")
    publication_fields = {
        "map_owner_publication_variant": expected_publication["variant"],
        "map_owner_publication_pc": expected_publication[
            "publication_pc_hex"
        ],
        "map_owner_publication_primary_sha256": expected_publication[
            "primary_sha256"
        ],
        "map_owner_publication_primary_hex": expected_publication[
            "primary_hex"
        ],
    }
    for field, expected in publication_fields.items():
        if report.get(field) != expected:
            errors.append(f"{field}-mismatch")
    for field in integer_fields:
        text = report.get(field)
        try:
            value = int(text) if text is not None else -1
        except ValueError:
            value = -1
        counters[field] = value
        if value < 0:
            errors.append(f"malformed-{field}")
    if expect_cgb:
        if counters.get("map_owner_arm_events", 0) <= 0:
            errors.append("no-bank1-42a7-owner-arm")
        if counters.get("map_owner_publications", 0) <= 0:
            errors.append("no-reviewed-lcdc-owner-publication")
        for field in (
            "map_owner_invalid_arms",
            "map_owner_invalid_commits",
            "map_owner_missing_commits",
            "map_owner_missing_trajectory_frames",
            "map_owner_invalid_trajectory_frames",
        ):
            if counters.get(field, -1) != 0:
                errors.append(f"nonzero-{field}")
    else:
        if any(counters.get(field, -1) != 0 for field in integer_fields):
            errors.append("dmg-route-produced-cgb-owner-events")
    return {
        "trajectory_schema": report.get("trajectory_schema"),
        "rom_mode": "cgb" if expect_cgb else "dmg",
        "room_source": "FFE5-at-bank1:42A7",
        "promotion_boundary": (
            f"segment-{expected_publication['publication_segment_hex']}:"
            f"{expected_publication['publication_pc_hex']}"
            "-LCDC-write"
        ),
        "publication": expected_publication,
        "counters": counters,
        "trace": report.get("map_owner_trace", ""),
        "errors": errors,
        "exact": not errors,
    }


def run_route(
    rom: Path,
    output: Path,
    frames: int,
    play_frames: int,
    timeout: float,
    target_camera: int | None,
    target_room: int,
    target_settle: int,
    snap_interval: int,
    fire: bool,
    trace: Path | None,
    trace_writes: bool,
    trace_camera_min: int,
    trace_camera_max: int,
    via_opening: bool = False,
    trace_chr_writes: bool = False,
    profile_source_writers: bool = False,
    profile_pipeline: bool = False,
) -> dict[str, str]:
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=True)
    runtime_rom = runtime / "route.gb"
    (runtime / "route.sav").unlink(missing_ok=True)
    (runtime / "route.gb.ram").unlink(missing_ok=True)
    shutil.copy2(rom.resolve(), runtime_rom)
    publication = detect_publication_boundary(runtime_rom.read_bytes())
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("STAGE1_NORTH_"):
            env.pop(key)
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        env.pop(key, None)
    env.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        STAGE1_NORTH_OUT=str(output),
        STAGE1_NORTH_FRAMES=str(frames),
        STAGE1_NORTH_PLAY_FRAMES=str(play_frames),
        STAGE1_NORTH_TARGET_ROOM=str(target_room),
        STAGE1_NORTH_TARGET_SETTLE=str(target_settle),
        STAGE1_NORTH_SNAP_INTERVAL=str(snap_interval),
        STAGE1_NORTH_VIA_OPENING="1" if via_opening else "0",
        STAGE1_NORTH_PUBLICATION_VARIANT=str(publication["variant"]),
        STAGE1_NORTH_PUBLICATION_PC=str(publication["publication_pc_hex"]),
        STAGE1_NORTH_PUBLICATION_SEGMENT=str(
            publication["publication_segment_hex"]
        ),
        STAGE1_NORTH_PUBLICATION_PRIMARY_SHA256=str(
            publication["primary_sha256"]
        ),
        STAGE1_NORTH_PUBLICATION_PRIMARY_HEX=str(publication["primary_hex"]),
    )
    if target_camera is not None:
        env["STAGE1_NORTH_TARGET_CAMERA"] = str(target_camera)
    if fire:
        env["STAGE1_NORTH_FIRE"] = "1"
    if profile_pipeline:
        env["STAGE1_NORTH_PROFILE"] = "1"
        env["STAGE1_NORTH_MOVEMENT_TRACE"] = "1"
        if profile_source_writers:
            env["STAGE1_NORTH_SOURCE_WRITERS"] = "1"
    if trace is not None:
        env["STAGE1_NORTH_TRACE_FILE"] = str(trace.resolve())
    if trace_writes:
        env["STAGE1_NORTH_TRACE_WRITES"] = "1"
        env["STAGE1_NORTH_TRACE_CAMERA_MIN"] = str(trace_camera_min)
        env["STAGE1_NORTH_TRACE_CAMERA_MAX"] = str(trace_camera_max)
    if trace_chr_writes:
        env["STAGE1_NORTH_TRACE_CHR_WRITES"] = "1"
    command = [
        str(MGBA),
        "--fastforward",
        "-C",
        f"savegamePath={runtime}",
        "-C",
        f"savestatePath={runtime}",
        str(runtime_rom),
        "--script",
        str(PROBE),
    ]
    report_path = output / "probe.txt"
    done_path = output / "probe.done"
    done_path.unlink(missing_ok=True)
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            if done_path.is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
    finally:
        stop_owned_process_group(process)
    stdout = process.stdout.read() if process.stdout is not None else ""
    if not report_path.is_file():
        raise RuntimeError(
            f"route produced no report (exit {process.returncode}): "
            f"{stdout.rstrip()}"
        )
    if not done_path.is_file() or done_path.read_text() != (
        "penta-stage1-north-probe-complete-v1\n"
    ):
        raise RuntimeError("route produced an incomplete north probe receipt")
    report = parse_report(report_path)
    if report.get("status") != "ok":
        raise RuntimeError(
            f"route did not reach the first north room: {report}"
        )
    return report


def byte_diff(left: bytes, right: bytes) -> tuple[int, int]:
    offsets = [
        offset
        for offset, (a, b) in enumerate(zip(left, right, strict=True))
        if a != b
    ]
    return len(offsets), offsets[0] if offsets else -1


def read_trajectory(
    path: Path,
    *,
    expected_owner_mode: str | None = None,
) -> list[dict[str, object]]:
    """Parse one exact v3 trajectory and validate owner evidence shape.

    ``expected_owner_mode`` is ``"cgb"`` for the candidate and ``"dmg"``
    for the untouched baseline.  DMG has no CGB physical-page attribute
    semantics, so it records an explicit unsupported sentinel rather than a
    fabricated owner.  A CGB missing/invalid status remains parseable so the
    semantic gate can return a useful receipt, but an impossible status,
    malformed sentinel, or page-local epoch mutation is rejected here.
    """
    if expected_owner_mode not in (None, "cgb", "dmg"):
        raise ValueError(
            f"invalid expected owner mode {expected_owner_mode!r}"
        )
    data = path.read_bytes()
    if not data:
        raise ValueError("trajectory is empty")
    if len(data) % TRAJECTORY_RECORD_SIZE:
        raise ValueError(
            f"trajectory size {len(data)} is not divisible by "
            f"{TRAJECTORY_RECORD_SIZE}"
        )
    records = []
    page_epochs: dict[int, tuple[int, int]] = {}
    for start in range(0, len(data), TRAJECTORY_RECORD_SIZE):
        row = data[start:start + TRAJECTORY_RECORD_SIZE]
        owner_status = row[27]
        owner_room = row[28]
        owner_epoch = row[29] | row[30] << 8
        record_index = start // TRAJECTORY_RECORD_SIZE
        if owner_status not in OWNER_STATUS_NAMES:
            raise ValueError(
                f"trajectory record {record_index} has unknown physical-page "
                f"owner status {owner_status}"
            )
        if owner_status == OWNER_STATUS_CGB_OWNED:
            if owner_epoch in (0, 0xFFFF):
                raise ValueError(
                    f"trajectory record {record_index} has malformed owned "
                    f"epoch {owner_epoch}"
                )
            page = row[5] & 0x08
            previous = page_epochs.get(page)
            if previous is not None:
                previous_epoch, previous_room = previous
                if owner_epoch < previous_epoch:
                    raise ValueError(
                        f"trajectory record {record_index} regressed page "
                        f"{page >> 3} owner epoch {previous_epoch} -> "
                        f"{owner_epoch}"
                    )
                if (
                    owner_epoch == previous_epoch
                    and owner_room != previous_room
                ):
                    raise ValueError(
                        f"trajectory record {record_index} mutated page "
                        f"{page >> 3} owner room within epoch {owner_epoch}"
                    )
            page_epochs[page] = owner_epoch, owner_room
        elif owner_room != 0xFF or owner_epoch != 0xFFFF:
            raise ValueError(
                f"trajectory record {record_index} has malformed "
                f"{OWNER_STATUS_NAMES[owner_status]} sentinel "
                f"room={owner_room:02X} epoch={owner_epoch:04X}"
            )
        if expected_owner_mode == "cgb" and owner_status == OWNER_STATUS_DMG:
            raise ValueError(
                f"trajectory record {record_index} claims DMG ownership in "
                "a CGB candidate"
            )
        if expected_owner_mode == "dmg" and owner_status != OWNER_STATUS_DMG:
            raise ValueError(
                f"trajectory record {record_index} claims CGB ownership in "
                "the DMG baseline"
            )
        records.append({
            "gameplay_frame": row[0] | row[1] << 8,
            "room": row[2],
            "camera": row[3] | row[4] << 8,
            "lcdc": row[5],
            "scx": row[6],
            "scy": row[7],
            "camera_y": row[8] | row[9] << 8,
            "selector_c": row[10],
            "selector_d": row[11],
            "source": row[12] | row[13] << 8,
            "sara_x": row[14],
            "sara_state": row[15],
            "sara_y": row[16],
            "sara_y_state": row[17],
            "sara_hit": row[18],
            "scene": row[19],
            "active": row[20],
            "input_direction": row[21],
            "input_state": row[22],
            "section_scroll": row[23],
            "sara_oam_y": row[24],
            "sara_oam_x": row[25],
            "svbk": row[26],
            "page_owner_status": owner_status,
            "page_owner_status_name": OWNER_STATUS_NAMES[owner_status],
            "page_owner_room": owner_room,
            "page_owner_epoch": owner_epoch,
            "page_owner_base": 0x9C00 if row[5] & 0x08 else 0x9800,
            "tiles": row[
                TRAJECTORY_HEADER_SIZE:
                TRAJECTORY_HEADER_SIZE + TRAJECTORY_VIEW_SIZE
            ],
            "attrs": row[
                TRAJECTORY_HEADER_SIZE + TRAJECTORY_VIEW_SIZE:
            ],
        })
    return records


def expected_stage1_attr(tile: int, map_offset: int) -> int:
    """Return the YAML-owned semantic VBK1 byte for one Stage-1 cell."""
    # The two translated north-seam cells are position-owned metallic wall
    # edges. They are the only non-hazard Stage-1 exceptions to the canonical
    # per-tile table.
    if map_offset in (0x18D, 0x1AD) and tile in (0x21, 0x31):
        return 0x06
    if tile in STAGE1_HAZARD.tooth_tiles:
        return STAGE1_HAZARD.tooth_palette | 0x08
    if 0x01 <= tile <= 0x04:
        return 0x00
    if tile in STAGE1_FIRE_TILES:
        return STAGE1_HAZARD.body_palette
    if tile in STAGE1_HAZARD.connector_tiles:
        return STAGE1_HAZARD.connector_palette
    if tile in STAGE1_HAZARD.support_tiles:
        return STAGE1_HAZARD.support_palette
    return STAGE1_BASE_ATTRS[tile]


def effective_display_rooms(
    records: list[dict[str, object]],
) -> tuple[list[int], dict[str, object]]:
    """Return the owner captured for each actually selected physical page.

    This deliberately performs no inference from FFBD, camera cadence,
    selector tuples, or a hard-coded transition frame.  The Lua probe binds
    FFE5 to a destination page at bank 1:$42A7 and promotes that binding at
    the exact reviewed LCDC store ($12EC legacy, $12FF r320).  Each row
    therefore carries the owner of its selected LCDC page.  Missing or
    malformed evidence is an explicit gate failure.
    """
    display_rooms: list[int] = []
    evidence_errors: list[dict[str, object]] = []
    status_counts = {name: 0 for name in OWNER_STATUS_NAMES.values()}
    owner_transitions: list[dict[str, object]] = []
    previous_owner: tuple[int, int, int] | None = None

    for record_index, row in enumerate(records):
        required = (
            "page_owner_status", "page_owner_room", "page_owner_epoch",
            "page_owner_base", "lcdc", "gameplay_frame",
        )
        missing = [field for field in required if field not in row]
        if missing:
            display_rooms.append(-1)
            evidence_errors.append({
                "reason": "missing-owner-fields",
                "record_index": record_index,
                "missing": missing,
            })
            continue
        try:
            status = int(row["page_owner_status"])
            room = int(row["page_owner_room"])
            epoch = int(row["page_owner_epoch"])
            base = int(row["page_owner_base"])
            expected_base = (
                0x9C00 if int(row["lcdc"]) & 0x08 else 0x9800
            )
        except (TypeError, ValueError) as error:
            display_rooms.append(-1)
            evidence_errors.append({
                "reason": "non-integer-owner-fields",
                "record_index": record_index,
                "error": str(error),
            })
            continue
        status_name = OWNER_STATUS_NAMES.get(status)
        if status_name is None:
            display_rooms.append(-1)
            evidence_errors.append({
                "reason": "unknown-owner-status",
                "record_index": record_index,
                "status": status,
            })
            continue
        status_counts[status_name] += 1
        if base != expected_base:
            evidence_errors.append({
                "reason": "selected-page-base-mismatch",
                "record_index": record_index,
                "recorded_base": base,
                "expected_base": expected_base,
            })
        if status != OWNER_STATUS_CGB_OWNED:
            display_rooms.append(-1)
            evidence_errors.append({
                "reason": status_name,
                "record_index": record_index,
                "gameplay_frame": int(row["gameplay_frame"]),
                "base": base,
                "room": room,
                "epoch": epoch,
            })
            continue
        if not (0 <= room <= 0xFF and 1 <= epoch <= 0xFFFE):
            display_rooms.append(-1)
            evidence_errors.append({
                "reason": "malformed-owned-fields",
                "record_index": record_index,
                "room": room,
                "epoch": epoch,
            })
            continue
        display_rooms.append(room)
        owner = base, room, epoch
        if owner != previous_owner:
            owner_transitions.append({
                "record_index": record_index,
                "gameplay_frame": int(row["gameplay_frame"]),
                "base": base,
                "room": room,
                "epoch": epoch,
            })
            previous_owner = owner

    return display_rooms, {
        "policy": "ffe5-at-bank1-42a7-promoted-at-exact-lcdc-store-v2",
        "trajectory_schema": TRAJECTORY_SCHEMA,
        "records": len(records),
        "status_counts": status_counts,
        "owner_transitions": owner_transitions,
        "evidence_errors": evidence_errors,
        "first_error": evidence_errors[0] if evidence_errors else None,
        "exact": bool(records) and not evidence_errors,
    }


def trajectory_attribute_integrity(
    records: list[dict[str, object]],
    reviewed_context: dict[tuple[int, int, int], int] | None = None,
    reviewed_tile_context: dict[tuple[int, int], int] | None = None,
) -> dict[str, object]:
    """Check every published Stage-1 VBK1 cell against semantic oracles.

    Scene $02 becomes active a few frames before the first dungeon map flip.
    During that bounded handoff the *displayed* map is still the complete
    palette-0 STAGE card, which is owned by the separate frame-by-frame stage
    card gate.  Start the Stage-1 oracle at the first valid physical-map flip
    only when the short preceding run is an all-zero attribute card.  Any
    other prefix, or any later bad frame, remains a hard failure.
    """
    presentation_start = 0
    prefix_all_zero = False
    if records:
        initial_page = int(records[0]["lcdc"]) & 0x08
        for index, row in enumerate(records[1:9], 1):
            valid_stage1 = (
                int(row["scene"]) == 2
                and int(row["active"]) == 1
                and int(row["camera"]) not in (0, 0xFFFF)
            )
            if valid_stage1 and (int(row["lcdc"]) & 0x08) != initial_page:
                prefix = records[:index]
                prefix_all_zero = all(
                    not any(bytes(item["attrs"])) for item in prefix
                )
                if prefix_all_zero:
                    presentation_start = index
                break
    display_rooms, physical_page_ownership = effective_display_rooms(records)
    mismatch_frames = 0
    mismatch_cells = 0
    unsafe_cells = 0
    checked_cells = 0
    first_mismatch = None
    digest_value = hashlib.sha256()
    for row in records:
        digest_value.update(bytes(row["attrs"]))
    for row, display_room in zip(
        records[presentation_start:],
        display_rooms[presentation_start:],
        strict=True,
    ):
        tiles = bytes(row["tiles"])
        attrs = bytes(row["attrs"])
        frame_mismatches = 0
        visible_columns = 20 + (int(row["scx"]) & 0x07 != 0)
        visible_rows = 18 + (int(row["scy"]) & 0x07 != 0)
        for index, (tile, actual) in enumerate(
            zip(tiles, attrs, strict=True)
        ):
            screen_row, screen_column = divmod(index, 21)
            if screen_row >= visible_rows or screen_column >= visible_columns:
                continue
            checked_cells += 1
            map_y = ((int(row["scy"]) + screen_row * 8) >> 3) & 0x1F
            map_x = ((int(row["scx"]) + screen_column * 8) >> 3) & 0x1F
            map_offset = map_y * 32 + map_x
            reviewed_expected = (
                reviewed_context.get((display_room, map_offset, tile))
                if reviewed_context is not None else None
            )
            if reviewed_expected is None and reviewed_tile_context is not None:
                reviewed_expected = reviewed_tile_context.get((
                    display_room, tile
                ))
            expected = (
                reviewed_expected
                if reviewed_expected is not None
                else expected_stage1_attr(tile, map_offset)
            )
            # Stage 1 owns neither flips/priority nor the unused bit 4. FF is
            # especially important: it is the characteristic uninitialized
            # attribute residue seen on the Pocket.
            if actual & 0xF0:
                unsafe_cells += 1
            if actual == expected:
                continue
            frame_mismatches += 1
            mismatch_cells += 1
            if first_mismatch is None:
                first_mismatch = {
                    "gameplay_frame": row["gameplay_frame"],
                    "room": row["room"],
                    "display_room": display_room,
                    "camera": row["camera"],
                    "svbk": row["svbk"],
                    "view_index": index,
                    "map_offset": map_offset,
                    "tile": tile,
                    "actual": actual,
                    "expected": expected,
                }
        mismatch_frames += frame_mismatches > 0
    return {
        "records": len(records),
        "recorded_cells": len(records) * TRAJECTORY_VIEW_SIZE,
        "prepublication_card_records_skipped": presentation_start,
        "prepublication_card_attrs_all_zero": prefix_all_zero,
        "presentation_start_gameplay_frame": (
            records[presentation_start]["gameplay_frame"]
            if records and presentation_start < len(records) else None
        ),
        "visible_cells_checked": checked_cells,
        "mismatch_frames": mismatch_frames,
        "mismatch_cells": mismatch_cells,
        "unsafe_high_bit_cells": unsafe_cells,
        "first_mismatch": first_mismatch,
        "attribute_plane_sha256": digest_value.hexdigest(),
        "physical_page_ownership": physical_page_ownership,
        # Retain the old receipt key for one transition release, but its value
        # is now direct physical-page evidence rather than inferred cadence.
        "display_room_ownership": physical_page_ownership,
        "exact": (
            mismatch_cells == 0
            and unsafe_cells == 0
            and bool(physical_page_ownership["exact"])
        ),
    }


def replay_attributes_exact(first: Path, replay: Path) -> bool:
    first_records = read_trajectory(first, expected_owner_mode="cgb")
    replay_records = read_trajectory(replay, expected_owner_mode="cgb")
    return (
        len(first_records) == len(replay_records)
        and all(
            left["attrs"] == right["attrs"]
            for left, right in zip(first_records, replay_records, strict=True)
        )
    )


def prepublication_visual_report(path: Path) -> dict[str, object]:
    """Validate the deliberately unowned opening-pixel evidence stream.

    These records may support only the reviewed visual checkpoint.  Any
    physical-page owner here would mean the Lua probe split evidence at the
    wrong boundary, so reject it rather than silently combining the streams.
    """
    records = read_trajectory(path, expected_owner_mode="cgb")
    errors = [
        {
            "record_index": index,
            "gameplay_frame": row["gameplay_frame"],
            "owner_status": row["page_owner_status_name"],
        }
        for index, row in enumerate(records)
        if int(row["page_owner_status"]) != OWNER_STATUS_CGB_MISSING
    ]
    return {
        "records": len(records),
        "only_unowned_cgb_opening_records": not errors,
        "first_error": errors[0] if errors else None,
        "exact": bool(records) and not errors,
    }


def settled_candidate_state(report: dict[str, str]) -> dict[str, object]:
    """Require a quiescent, live Stage-1 endpoint before accepting dumps."""
    state = {
        key: int(value, 16)
        for key, value in re.findall(
            r"([a-z0-9]+):([0-9A-Fa-f]{2})",
            report.get("final_state", ""),
        )
    }
    hardware = {
        key: int(value, 16)
        for key, value in re.findall(
            r"([a-z0-9]+):([0-9A-Fa-f]{2})",
            report.get("final_hardware", ""),
        )
    }
    lcdc = hardware.get("lcdc", state.get("lcdc", -1))
    checks = {
        "scene_02": state.get("scene") == 0x02,
        "gameplay_active": state.get("ffc1") == 0x01,
        "hdma_idle": hardware.get("hdma5") == 0xFF,
        "svbk_readable": hardware.get("svbk") in (0, 1),
        "gameplay_lcdc_active": lcdc >= 0 and (lcdc & 0x81) == 0x81,
    }
    return {
        "final_state": report.get("final_state"),
        "final_hardware": report.get("final_hardware"),
        "checks": checks,
        "passed": all(checks.values()),
    }


def terrain_tile_equivalent(left: int, right: int) -> bool:
    """Treat only two valid rotating-hazard phases as static-terrain equal."""
    if left == right:
        return True
    hazard_tiles = lambda tile: (
        0x01 <= tile <= 0x04
        or tile in (0x4F, 0x5E, 0x5F)
        or 0x60 <= tile <= 0x7F
    )
    return hazard_tiles(left) and hazard_tiles(right)


def compare_trajectories(
    candidate_path: Path,
    baseline_path: Path,
    *,
    candidate_prepublication_path: Path | None = None,
) -> dict[str, object]:
    """Compare every candidate viewport with stock at the same world point."""
    candidate = read_trajectory(
        candidate_path, expected_owner_mode="cgb"
    )
    # The first CGB gameplay callbacks can precede the first authenticated
    # physical-map publication.  They are intentionally excluded from the
    # owner/attribute trajectory, but retain a separate untrusted pixel stream
    # for the reviewed opening room-05 visual control.  Missing this file is
    # tolerated only for historical/unit fixtures; the live caller requires it.
    prepublication = (
        read_trajectory(candidate_prepublication_path, expected_owner_mode="cgb")
        if candidate_prepublication_path is not None
        and candidate_prepublication_path.is_file()
        else []
    )
    baseline = read_trajectory(
        baseline_path, expected_owner_mode="dmg"
    )
    # DC03:DC02=$FFFF is the game's map-transition sentinel, not a world
    # coordinate. Pairing those records by (room, camera) compares unrelated
    # half-built maps whenever two ROMs reach the transition on different
    # frames. The completed-map and target-coordinate checks below remain
    # strict; omit only this explicitly invalid coordinate from alignment.
    def valid_world(
        row: dict[str, object], *, require_banked_wram_1: bool
    ) -> bool:
        return (
            int(row["camera"]) not in (0, 0xFFFF)
            and (
                not require_banked_wram_1
                or int(row["svbk"]) in (0, 1)
            )
            and int(row["active"]) == 1
            and int(row["scene"]) == 2
        )

    def progress_key(row: dict[str, object]) -> tuple[int, int]:
        return int(row["room"]), int(row["camera"])

    def logical_state_key(row: dict[str, object]) -> tuple[int, ...]:
        # Private selector/source cadence may legitimately differ in the DX
        # publisher. World Y may not: it is the stable logical ownership key
        # behind the same room/camera progress coordinate.
        return (
            int(row["room"]), int(row["camera"]), int(row["camera_y"]),
        )

    def display_state_key(row: dict[str, object]) -> tuple[int, ...]:
        # The room byte can advance one callback before or after the same
        # transition presentation.  Its logical legality is checked
        # independently above against stock_progress; do not put that private
        # cadence back into the visual key.  Bind the camera/scroll state and
        # then compare the actual tile bytes, so an exact boundary frame may
        # match on either side while any visible wall/edge difference remains
        # zero-tolerance.  The physical BG map bit is likewise private cadence.
        return (
            int(row["camera"]), int(row["camera_y"]),
            int(row["scx"]), int(row["scy"]),
        )

    def state_example(row: dict[str, object]) -> dict[str, object]:
        return {
            "gameplay_frame": row["gameplay_frame"],
            "room": row["room"],
            "camera": row["camera"],
            "camera_y": row["camera_y"],
            "selector_c": row["selector_c"],
            "selector_d": row["selector_d"],
            "source": row["source"],
            "sara_x": row["sara_x"],
            "sara_state": row["sara_state"],
            "sara_y": row["sara_y"],
            "sara_y_state": row["sara_y_state"],
            "sara_hit": row["sara_hit"],
            "lcdc": row["lcdc"],
            "scx": row["scx"],
            "scy": row["scy"],
            "svbk": row["svbk"],
            "page_owner_base": row["page_owner_base"],
            "page_owner_room": row["page_owner_room"],
            "page_owner_epoch": row["page_owner_epoch"],
            "page_owner_status": row["page_owner_status_name"],
        }

    candidate_world_indexed = [
        (index, row) for index, row in enumerate(candidate)
        if valid_world(row, require_banked_wram_1=True)
    ]
    candidate_world = [row for _, row in candidate_world_indexed]
    # The untouched DMG ROM does not enable CGB WRAM banking; FF70 is not a
    # meaningful ownership register there even when mGBA exposes a value.
    baseline_world = [
        row for row in baseline
        if valid_world(row, require_banked_wram_1=False)
    ]
    stock_progress: dict[tuple[int, int], set[tuple[int, ...]]] = {}
    stock_progress_tiles: dict[tuple[int, int], list[bytes]] = {}
    stock: dict[tuple[int, ...], list[bytes]] = {}
    for row in baseline_world:
        stock_progress.setdefault(progress_key(row), set()).add(
            logical_state_key(row)
        )
        stock_progress_tiles.setdefault(progress_key(row), []).append(
            row["tiles"]
        )
        stock.setdefault(display_state_key(row), []).append(row["tiles"])
    matched = []
    progress_matched = []
    unmatched_progress = []
    unexpected_state = []
    unmatched_display = []

    def minimum_tile_difference(
        tiles: bytes, choices: list[bytes]
    ) -> int:
        return min(
            sum(
                not terrain_tile_equivalent(left, right)
                for left, right in zip(tiles, choice, strict=True)
            )
            for choice in choices
        )

    for row in candidate_world:
        expected_states = stock_progress.get(progress_key(row))
        if expected_states is None:
            unmatched_progress.append(row)
            continue
        progress_difference = minimum_tile_difference(
            bytes(row["tiles"]), stock_progress_tiles[progress_key(row)]
        )
        progress_matched.append((progress_difference, row))
        if logical_state_key(row) not in expected_states:
            unexpected_state.append(row)
            continue
        choices = stock.get(display_state_key(row))
        if choices is None:
            unmatched_display.append(row)
            continue
        difference = minimum_tile_difference(bytes(row["tiles"]), choices)
        matched.append((difference, row))

    # SVBK 2/3 service frames and the native $FFFF transition sentinel make
    # logical WRAM unreadable, but their VRAM is still being presented to the
    # player. Bind every such frame to the nearest readable world state on
    # either side and require its tile plane to equal one of those stock
    # presentations. This tolerates how many frames the optimized publisher
    # spends parked without permitting that interval to hide a bad edge row.
    candidate_world_indices = {index for index, _ in candidate_world_indexed}
    previous_progress: list[tuple[int, int] | None] = []
    last_progress = None
    for index, row in enumerate(candidate):
        if index in candidate_world_indices:
            last_progress = progress_key(row)
        previous_progress.append(last_progress)
    next_progress: list[tuple[int, int] | None] = [None] * len(candidate)
    last_progress = None
    for index in range(len(candidate) - 1, -1, -1):
        if index in candidate_world_indices:
            last_progress = progress_key(candidate[index])
        next_progress[index] = last_progress

    service_matched = []
    service_unmatched = []
    for index, row in enumerate(candidate):
        if index in candidate_world_indices:
            continue
        neighbor_keys = {
            key for key in (previous_progress[index], next_progress[index])
            if key is not None
        }
        choices = [
            choice
            for key in neighbor_keys
            for choice in stock_progress_tiles.get(key, ())
        ]
        if not choices:
            service_unmatched.append(row)
            continue
        service_matched.append((
            minimum_tile_difference(bytes(row["tiles"]), choices), row,
        ))

    worst = sorted(matched, key=lambda item: item[0], reverse=True)[:12]
    progress_worst = sorted(
        progress_matched, key=lambda item: item[0], reverse=True
    )[:12]
    service_worst = sorted(
        service_matched, key=lambda item: item[0], reverse=True
    )[:12]
    candidate_attrs = trajectory_attribute_integrity(
        candidate, REVIEWED_WALL_CONTEXT, REVIEWED_WALL_TILE_CONTEXT
    )
    reviewed_wall_oracle = reviewed_stage1_wall_oracle(
        prepublication + candidate, REVIEWED_WALL_CONTRACT
    )
    baseline_attr_bytes = b"".join(bytes(row["attrs"]) for row in baseline)
    return {
        "candidate_records": len(candidate),
        "candidate_prepublication_visual_records": len(prepublication),
        "baseline_records": len(baseline),
        "candidate_world_records": len(candidate_world),
        "baseline_world_records": len(baseline_world),
        "candidate_parked_svbk_frames": sum(
            int(row["svbk"]) not in (0, 1) for row in candidate
        ),
        "baseline_parked_svbk_frames": 0,
        "candidate_transition_sentinels": sum(
            int(row["camera"]) == 0xFFFF for row in candidate
        ),
        "baseline_transition_sentinels": sum(
            int(row["camera"]) == 0xFFFF for row in baseline
        ),
        "matched_records": len(matched),
        "progress_matched_records": len(progress_matched),
        "unmatched_progress_records": len(unmatched_progress),
        "unexpected_logical_state_records": len(unexpected_state),
        "unmatched_display_state_records": len(unmatched_display),
        "service_presentation_records": len(service_matched),
        "unmatched_service_presentation_records": len(service_unmatched),
        "readable_non_gameplay_records": sum(
            int(row["svbk"]) in (0, 1)
            and (int(row["scene"]) != 2 or int(row["active"]) != 1)
            for row in candidate
        ),
        "first_unmatched_progress": (
            state_example(unmatched_progress[0]) if unmatched_progress else None
        ),
        "first_unexpected_logical_state": (
            state_example(unexpected_state[0]) if unexpected_state else None
        ),
        "first_unmatched_display_state": (
            state_example(unmatched_display[0]) if unmatched_display else None
        ),
        "first_unmatched_service_presentation": (
            state_example(service_unmatched[0]) if service_unmatched else None
        ),
        "differing_records": sum(difference > 0 for difference, _ in matched),
        "progress_differing_records": sum(
            difference > 0 for difference, _ in progress_matched
        ),
        "maximum_viewport_tile_differences": max(
            (difference for difference, _ in matched), default=-1
        ),
        "maximum_progress_viewport_tile_differences": max(
            (difference for difference, _ in progress_matched), default=-1
        ),
        "service_presentation_differing_records": sum(
            difference > 0 for difference, _ in service_matched
        ),
        "maximum_service_viewport_tile_differences": max(
            (difference for difference, _ in service_matched), default=-1
        ),
        "candidate_attribute_integrity": candidate_attrs,
        "reviewed_room01_wall_oracle": reviewed_wall_oracle,
        "baseline_attribute_plane": {
            "records": len(baseline),
            "cells": len(baseline) * TRAJECTORY_VIEW_SIZE,
            # The untouched DMG ROM has no semantic VBK1 plane. Capture and
            # hash it for evidence, but never use it as the DX color oracle.
            "sha256": hashlib.sha256(baseline_attr_bytes).hexdigest(),
            "oracle": "recorded-only; untouched baseline is DMG",
        },
        "worst_examples": [
            {"differences": difference, **state_example(row)}
            for difference, row in worst
        ],
        "progress_worst_examples": [
            {"differences": difference, **state_example(row)}
            for difference, row in progress_worst
        ],
        "service_worst_examples": [
            {"differences": difference, **state_example(row)}
            for difference, row in service_worst
        ],
    }


def target_only_route_contract(
    trajectory: dict[str, object],
    *,
    geometry_differences_present: bool,
    service_presentation_ok: bool,
    physical_page_ownership_ok: bool,
    attribute_trajectory_ok: bool,
) -> bool:
    """Return the timing-tolerant route verdict without weakening visuals."""
    return (
        int(trajectory["matched_records"]) > 0
        and int(trajectory["unmatched_progress_records"]) == 0
        and int(trajectory["maximum_viewport_tile_differences"]) == 0
        and not geometry_differences_present
        and int(trajectory["unexpected_logical_state_records"]) == 0
        and int(trajectory["unmatched_display_state_records"]) == 0
        and service_presentation_ok
        and physical_page_ownership_ok
        and attribute_trajectory_ok
    )


def compare_visible_terrain(
    candidate: bytes,
    baseline: bytes,
    *,
    width: int = 24,
    rows: int = 16,
    seam_columns: int = 2,
    max_phase: int = 4,
) -> dict[str, object]:
    """Compare the gameplay rows after accounting for the native X ring.

    C1A0 is a 24x24 circular packed map, not a fixed room image. Enemy
    contact can deflect Sara horizontally even under identical UP input, so
    the same world terrain can be published at a different two-column ring
    phase. Compare every mutually visible cell at the best bounded phase,
    while independently requiring the newly exposed wall seam to be stable
    and nonblank. The bottom eight rows are outside the 16-tile gameplay
    viewport (HUD/off-screen scratch) and are retained in the raw receipt but
    are not terrain.
    """
    usable_end = width - seam_columns
    options: list[dict[str, object]] = []
    for phase in range(-max_phase, max_phase + 1):
        if phase >= 0:
            baseline_start = phase
            candidate_start = 0
            length = usable_end - phase
        else:
            baseline_start = 0
            candidate_start = -phase
            length = usable_end + phase
        differences = 0
        dynamic_phase_differences = 0
        first_difference = -1
        for row in range(rows):
            baseline_offset = row * width + baseline_start
            candidate_offset = row * width + candidate_start
            for column in range(length):
                baseline_tile = baseline[baseline_offset + column]
                candidate_tile = candidate[candidate_offset + column]
                if baseline_tile == candidate_tile:
                    continue
                if terrain_tile_equivalent(baseline_tile, candidate_tile):
                    dynamic_phase_differences += 1
                    continue
                differences += 1
                if first_difference < 0:
                    first_difference = row * width + candidate_start + column
        options.append(
            {
                "phase_columns": phase,
                "compared_bytes": rows * length,
                "differences": differences,
                "dynamic_phase_differences": dynamic_phase_differences,
                "first_candidate_difference": first_difference,
            }
        )
    best = min(
        options,
        key=lambda row: (int(row["differences"]), -int(row["compared_bytes"])),
    )
    phase = int(best["phase_columns"])
    if phase > 0:
        baseline_edges = {
            baseline[row * width:row * width + phase].hex()
            for row in range(rows)
        }
        candidate_edges = {
            candidate[
                row * width + usable_end - phase:row * width + usable_end
            ].hex()
            for row in range(rows)
        }
    elif phase < 0:
        edge_width = -phase
        baseline_edges = {
            baseline[
                row * width + usable_end - edge_width:row * width + usable_end
            ].hex()
            for row in range(rows)
        }
        candidate_edges = {
            candidate[row * width:row * width + edge_width].hex()
            for row in range(rows)
        }
    else:
        baseline_edges = set()
        candidate_edges = set()
    padding_rows = {
        (
            baseline[row * width + usable_end:(row + 1) * width].hex(),
            candidate[row * width + usable_end:(row + 1) * width].hex(),
        )
        for row in range(rows)
    }
    edge_values = bytes.fromhex("".join(sorted(baseline_edges | candidate_edges)))
    best.update(
        {
            "width": width,
            "rows": rows,
            "seam_columns": seam_columns,
            "max_phase_columns": max_phase,
            "baseline_edge_signatures": sorted(baseline_edges),
            "candidate_edge_signatures": sorted(candidate_edges),
            "edge_signatures_stable": (
                len(baseline_edges) <= 1 and len(candidate_edges) <= 1
            ),
            "edge_signatures_nonblank": (
                phase == 0 or bool(edge_values) and all(edge_values)
            ),
            "padding_signatures": sorted(
                f"{left}/{right}" for left, right in padding_rows
            ),
            "padding_stable_and_equal": (
                len(padding_rows) == 1
                and next(iter(padding_rows))[0] == next(iter(padding_rows))[1]
            ),
        }
    )
    return best


def optional_camera(value: str) -> int | None:
    if value.lower() == "none":
        return None
    return int(value, 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=3000)
    parser.add_argument("--play-frames", type=int, default=240)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument(
        "--target-camera",
        type=optional_camera,
        default=0x03A4,
        help="stop when DC03:DC02 reaches this value in the target room",
    )
    parser.add_argument("--target-room", type=lambda value: int(value, 0), default=1)
    parser.add_argument("--target-settle", type=int, default=8)
    parser.add_argument("--snap-interval", type=int, default=0)
    parser.add_argument("--profile-pipeline", action="store_true",
                        help="read-only CPU-cycle traces of tile/attribute work")
    parser.add_argument("--profile-source-writers", action="store_true",
                        help="with --profile-pipeline, count native source writes (slower)")
    parser.add_argument(
        "--fire",
        action="store_true",
        help="hold A while walking north, matching ordinary armed play",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        help="replay recorded JSONL controller keys instead of generated input",
    )
    parser.add_argument(
        "--trace-writes",
        action="store_true",
        help="record C1A0-C1CF writes near the first failing north boundary",
    )
    parser.add_argument(
        "--trace-camera-min",
        type=lambda value: int(value, 0),
        default=0x02B0,
        help="lowest inclusive camera coordinate for --trace-writes",
    )
    parser.add_argument(
        "--trace-camera-max",
        type=lambda value: int(value, 0),
        default=0x02D0,
        help="highest inclusive camera coordinate for --trace-writes",
    )
    parser.add_argument(
        "--target-only",
        action="store_true",
        help=(
            "require exact OG terrain at the reported north-room coordinate "
            "plus exact semantic VBK1 presentation and candidate replay; "
            "report but do not gate on route timing, which the separate "
            "speed matrix owns"
        ),
    )
    parser.add_argument(
        "--dynamic-prefix",
        type=int,
        default=0,
        help="allow differences only in this off-screen C1A0 prefix",
    )
    parser.add_argument(
        "--max-frame-lag",
        type=int,
        help="maximum candidate gameplay-frame lag at the target coordinate",
    )
    parser.add_argument(
        "--max-frame-lag-ratio",
        type=float,
        default=0.15,
        help=(
            "maximum lag as a fraction of the untouched ROM's gameplay "
            "frames at the target coordinate (default: 0.15)"
        ),
    )
    args = parser.parse_args()
    if not 0 <= args.dynamic_prefix <= 0x240:
        parser.error("--dynamic-prefix must be between 0 and 576")
    if not 0 <= args.trace_camera_min <= args.trace_camera_max <= 0xFFFF:
        parser.error("trace camera range must be ordered within 0..0xFFFF")
    if args.max_frame_lag is not None and args.max_frame_lag < 0:
        parser.error("--max-frame-lag cannot be negative")
    if (
        args.max_frame_lag_ratio is not None
        and not 0 <= args.max_frame_lag_ratio < 1
    ):
        parser.error("--max-frame-lag-ratio must be in [0, 1)")
    if (
        args.max_frame_lag is not None
        and args.max_frame_lag_ratio is not None
    ):
        parser.error(
            "--max-frame-lag and --max-frame-lag-ratio are mutually exclusive"
        )

    baseline_publication = detect_publication_boundary(
        args.baseline.read_bytes()
    )
    candidate_publication = detect_publication_boundary(args.rom.read_bytes())

    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    baseline_report = run_route(
        args.baseline,
        output / "baseline",
        args.frames,
        args.play_frames,
        args.timeout,
        args.target_camera,
        args.target_room,
        args.target_settle,
        args.snap_interval,
        args.fire,
        args.trace,
        args.trace_writes,
        args.trace_camera_min,
        args.trace_camera_max,
        False,
        profile_source_writers=args.profile_source_writers,
        profile_pipeline=args.profile_pipeline,
    )
    candidate_report = run_route(
        args.rom,
        output / "candidate",
        args.frames,
        args.play_frames,
        args.timeout,
        args.target_camera,
        args.target_room,
        args.target_settle,
        args.snap_interval,
        args.fire,
        args.trace,
        args.trace_writes,
        args.trace_camera_min,
        args.trace_camera_max,
        False,
        profile_source_writers=args.profile_source_writers,
        profile_pipeline=args.profile_pipeline,
    )
    candidate_replay_report = None
    replay_artifacts: dict[str, dict[str, object]] = {}
    replay_exact = True
    candidate_replay_attributes_exact = True
    if args.target_only:
        candidate_replay_report = run_route(
            args.rom,
            output / "candidate-replay",
            args.frames,
            args.play_frames,
            args.timeout,
            args.target_camera,
            args.target_room,
            args.target_settle,
            args.snap_interval,
            args.fire,
            args.trace,
            args.trace_writes,
            args.trace_camera_min,
            args.trace_camera_max,
            False,
            profile_source_writers=args.profile_source_writers,
            profile_pipeline=args.profile_pipeline,
        )
        for name in (
            "c1a0.bin", "trajectory.bin", "prepublication-trajectory.bin",
            "visible-tiles.bin",
            "visible-attrs.bin", "vram9800.bin", "vram9800-attrs.bin",
            "vram9c00.bin", "vram9c00-attrs.bin", "shadow-oam.bin",
            "hardware-oam.bin", "bg-cram.bin", "obj-cram.bin",
            "world-at-entry.bin", "world-final.bin",
            "metatiles-at-entry.bin", "metatiles-final.bin",
        ):
            first = output / "candidate" / name
            replay = output / "candidate-replay" / name
            present = first.is_file() and replay.is_file()
            exact_replay = present and first.read_bytes() == replay.read_bytes()
            replay_artifacts[name] = {
                "present": present,
                "exact": exact_replay,
                "candidate_sha256": digest(first) if first.is_file() else None,
                "replay_sha256": digest(replay) if replay.is_file() else None,
            }
            replay_exact &= exact_replay
        candidate_replay_attributes_exact = replay_attributes_exact(
            output / "candidate/trajectory.bin",
            output / "candidate-replay/trajectory.bin",
        )
        replay_exact &= candidate_replay_attributes_exact

    baseline_owner_report = physical_page_owner_report(
        baseline_report,
        expect_cgb=False,
        expected_publication=baseline_publication,
    )
    candidate_owner_report = physical_page_owner_report(
        candidate_report,
        expect_cgb=True,
        expected_publication=candidate_publication,
    )
    candidate_replay_owner_report = (
        physical_page_owner_report(
            candidate_replay_report,
            expect_cgb=True,
            expected_publication=candidate_publication,
        )
        if candidate_replay_report is not None else None
    )
    owner_reports_exact = (
        bool(baseline_owner_report["exact"])
        and bool(candidate_owner_report["exact"])
        and (
            candidate_replay_owner_report is None
            or bool(candidate_replay_owner_report["exact"])
        )
    )

    candidate_settled = settled_candidate_state(candidate_report)
    candidate_replay_settled = (
        settled_candidate_state(candidate_replay_report)
        if candidate_replay_report is not None else None
    )
    final_state_ok = bool(candidate_settled["passed"]) and (
        candidate_replay_settled is None
        or bool(candidate_replay_settled["passed"])
    )

    baseline_room = (output / "baseline/c1a0.bin").read_bytes()
    candidate_room = (output / "candidate/c1a0.bin").read_bytes()
    differences, first_difference = byte_diff(candidate_room, baseline_room)

    # The stock dungeon template is the source of truth for every later room
    # expansion. A rendered target screenshot can look valid while an
    # off-screen source row is already poisoned; build 47 did exactly that by
    # copying 36 executable bytes to $CFAA-$CFCD. Make entry equivalence a
    # mandatory gate even under --target-only.
    baseline_world_entry = (
        output / "baseline/world-at-entry.bin"
    ).read_bytes()
    candidate_world_entry = (
        output / "candidate/world-at-entry.bin"
    ).read_bytes()
    baseline_world_final = (output / "baseline/world-final.bin").read_bytes()
    candidate_world_final = (output / "candidate/world-final.bin").read_bytes()
    if not all(
        len(blob) == 0x880
        for blob in (
            baseline_world_entry, candidate_world_entry,
            baseline_world_final, candidate_world_final,
        )
    ):
        raise RuntimeError("Stage-1 world dumps must each cover $C780-$CFFF")
    world_entry_differences, first_world_entry_difference = byte_diff(
        candidate_world_entry, baseline_world_entry
    )
    candidate_world_mutations, first_candidate_world_mutation = byte_diff(
        candidate_world_final, candidate_world_entry
    )
    baseline_world_mutations, first_baseline_world_mutation = byte_diff(
        baseline_world_final, baseline_world_entry
    )
    world_template_ok = world_entry_differences == 0

    baseline_metatiles = (
        output / "baseline/metatiles-at-entry.bin"
    ).read_bytes()
    candidate_metatiles = (
        output / "candidate/metatiles-at-entry.bin"
    ).read_bytes()
    if len(baseline_metatiles) != 0x400 or len(candidate_metatiles) != 0x400:
        raise RuntimeError("Stage-1 metatile dumps must each cover $A400-$A7FF")
    metatile_differences, first_metatile_difference = byte_diff(
        candidate_metatiles, baseline_metatiles
    )
    metatile_table_ok = metatile_differences == 0
    terrain = compare_visible_terrain(candidate_room, baseline_room)
    terrain_differences = int(terrain["differences"])
    first_terrain_difference = int(terrain["first_candidate_difference"])
    for report in (candidate_report, baseline_report):
        if int(report["native_gameplay_start"]) < 0 or int(report["native_gameplay_frames"]) <= 0:
            raise RuntimeError("missing native gameplay timing boundary")
    gameplay_frame_lag = (
        int(candidate_report["native_gameplay_frames"])
        - int(baseline_report["native_gameplay_frames"])
    )
    trajectory = compare_trajectories(
        output / "candidate/trajectory.bin",
        output / "baseline/trajectory.bin",
        candidate_prepublication_path=(
            output / "candidate/prepublication-trajectory.bin"
        ),
    )
    candidate_prepublication = prepublication_visual_report(
        output / "candidate/prepublication-trajectory.bin"
    )
    reviewed_wall_oracle = trajectory["reviewed_room01_wall_oracle"]
    reviewed_wall_replay_oracle = None
    candidate_replay_prepublication = None
    reviewed_wall_replay_exact = True
    if args.target_only:
        replay_prepublication_path = (
            output / "candidate-replay/prepublication-trajectory.bin"
        )
        candidate_replay_prepublication = prepublication_visual_report(
            replay_prepublication_path
        )
        reviewed_wall_replay_oracle = reviewed_stage1_wall_oracle(
            read_trajectory(replay_prepublication_path, expected_owner_mode="cgb")
            + read_trajectory(
                output / "candidate-replay/trajectory.bin",
                expected_owner_mode="cgb",
            ),
            REVIEWED_WALL_CONTRACT,
        )
        reviewed_wall_replay_exact = (
            reviewed_wall_replay_oracle["fingerprint_sha256"]
            == reviewed_wall_oracle["fingerprint_sha256"]
        )
    reviewed_wall_oracle_ok = (
        bool(reviewed_wall_oracle["exact"])
        and (
            reviewed_wall_replay_oracle is None
            or bool(reviewed_wall_replay_oracle["exact"])
        )
        and reviewed_wall_replay_exact
        and bool(candidate_prepublication["exact"])
        and (
            candidate_replay_prepublication is None
            or bool(candidate_replay_prepublication["exact"])
        )
    )
    service_presentation_ok = (
        int(trajectory["unmatched_service_presentation_records"]) == 0
        and int(trajectory["maximum_service_viewport_tile_differences"]) <= 0
    )
    physical_page_ownership_ok = bool(
        trajectory["candidate_attribute_integrity"]
        ["physical_page_ownership"]["exact"]
    ) and owner_reports_exact
    attribute_trajectory_ok = bool(
        trajectory["candidate_attribute_integrity"]["exact"]
    ) and owner_reports_exact
    trajectory_ok = (
        int(trajectory["matched_records"]) > 0
        and int(trajectory["maximum_viewport_tile_differences"]) == 0
        and int(trajectory["unexpected_logical_state_records"]) == 0
        and int(trajectory["unmatched_display_state_records"]) == 0
        and service_presentation_ok
        and attribute_trajectory_ok
    )
    progress_geometry_ok = (
        int(trajectory["progress_matched_records"]) > 0
        and int(trajectory["unmatched_progress_records"]) == 0
        and int(trajectory["maximum_progress_viewport_tile_differences"]) == 0
    )
    geometry_maxima = {
        "world_state": int(trajectory["maximum_viewport_tile_differences"]),
        "world_progress": int(
            trajectory["maximum_progress_viewport_tile_differences"]
        ),
        "service_presentation": int(
            trajectory["maximum_service_viewport_tile_differences"]
        ),
    }
    geometry_differences_present = any(
        value > 0 for value in geometry_maxima.values()
    )
    geometry_examples = [
        row
        for field in (
            "worst_examples", "progress_worst_examples",
            "service_worst_examples",
        )
        for row in trajectory[field]
        if int(row["differences"]) > 0
    ]
    worst_geometry_example = max(
        geometry_examples,
        key=lambda row: int(row["differences"]),
        default=None,
    )
    progress_trajectory_ok = (
        progress_geometry_ok
        and service_presentation_ok
        and attribute_trajectory_ok
    )
    target_only_static_route_ok = target_only_route_contract(
        trajectory,
        geometry_differences_present=geometry_differences_present,
        service_presentation_ok=service_presentation_ok,
        physical_page_ownership_ok=physical_page_ownership_ok,
        attribute_trajectory_ok=attribute_trajectory_ok,
    )
    max_frame_lag = args.max_frame_lag
    if args.max_frame_lag_ratio is not None:
        max_frame_lag = math.floor(
            int(baseline_report["native_gameplay_frames"])
            * args.max_frame_lag_ratio
        )
    lag_ok = (
        max_frame_lag is None
        or abs(gameplay_frame_lag) <= max_frame_lag
    )
    terrain_ok = (
        terrain_differences == 0
        and bool(terrain["edge_signatures_stable"])
        and bool(terrain["edge_signatures_nonblank"])
        and bool(terrain["padding_stable_and_equal"])
    )
    # Even the timing-tolerant target-only policy must validate every visible
    # viewport encountered on the way north.  Match by stock world progress
    # instead of frame number or private ring-selector state so harmless DX
    # cadence changes cannot hide (or invent) a wall/void corruption.
    route_policy_ok = (
        target_only_static_route_ok
        if args.target_only
        else progress_trajectory_ok and lag_ok and trajectory_ok
    )
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": (
            "pass"
            if (
                terrain_ok and route_policy_ok and replay_exact
                and world_template_ok and metatile_table_ok and final_state_ok
                and reviewed_wall_oracle_ok
            )
            else "fail"
        ),
        "candidate_rom": str(args.rom.resolve()),
        "candidate_sha256": digest(args.rom),
        "baseline_rom": str(args.baseline.resolve()),
        "baseline_sha256": digest(args.baseline),
        "input_route": (
            f"cold GAME START; recorded controller trace {args.trace}; "
            "no gameplay memory writes"
            if args.trace is not None
            else (
                "cold GAME START; hold UP+A; no gameplay memory writes"
                if args.fire
                else "cold GAME START; hold UP; no gameplay memory writes"
            )
        ),
        "gameplay_frames": args.play_frames,
        "target_camera": args.target_camera,
        "target_room": args.target_room,
        "target_settle_frames": args.target_settle,
        "candidate": candidate_report,
        "candidate_replay": candidate_replay_report,
        "candidate_replay_exact": replay_exact,
        "candidate_replay_attributes_exact": (
            candidate_replay_attributes_exact
        ),
        "trajectory_schema": TRAJECTORY_SCHEMA,
        "baseline_physical_page_owner_report": baseline_owner_report,
        "candidate_physical_page_owner_report": candidate_owner_report,
        "candidate_replay_physical_page_owner_report": (
            candidate_replay_owner_report
        ),
        "physical_page_owner_reports_exact": owner_reports_exact,
        "candidate_replay_artifacts": replay_artifacts,
        "candidate_settled_final_state": candidate_settled,
        "candidate_replay_settled_final_state": candidate_replay_settled,
        "settled_final_state_ok": final_state_ok,
        "target_only_policy": args.target_only,
        "baseline": baseline_report,
        "packed_room_bytes": len(candidate_room),
        "packed_room_differences": differences,
        "first_difference": first_difference,
        "world_template": {
            "address": "C780-CFFF",
            "bytes": len(candidate_world_entry),
            "entry_differences": world_entry_differences,
            "first_entry_difference": first_world_entry_difference,
            "first_entry_difference_address": (
                None
                if first_world_entry_difference < 0
                else f"{0xC780 + first_world_entry_difference:04X}"
            ),
            "candidate_entry_sha256": hashlib.sha256(
                candidate_world_entry
            ).hexdigest(),
            "baseline_entry_sha256": hashlib.sha256(
                baseline_world_entry
            ).hexdigest(),
            "candidate_route_mutations": candidate_world_mutations,
            "first_candidate_route_mutation": first_candidate_world_mutation,
            "baseline_route_mutations": baseline_world_mutations,
            "first_baseline_route_mutation": first_baseline_world_mutation,
            "exact_at_entry": world_template_ok,
        },
        "metatile_table": {
            "address": "A400-A7FF",
            "bytes": len(candidate_metatiles),
            "differences": metatile_differences,
            "first_difference": first_metatile_difference,
            "exact_at_entry": metatile_table_ok,
        },
        "dynamic_prefix_bytes": args.dynamic_prefix,
        "terrain_differences": terrain_differences,
        "first_terrain_difference": first_terrain_difference,
        "visible_terrain_overlap": terrain,
        "full_route_viewport_integrity": trajectory,
        "candidate_prepublication_visual_stream": candidate_prepublication,
        "candidate_replay_prepublication_visual_stream": (
            candidate_replay_prepublication
        ),
        "reviewed_wall_fixture": str(REVIEWED_WALL_FIXTURE.relative_to(ROOT)),
        "reviewed_wall_fixture_sha256": digest(REVIEWED_WALL_FIXTURE),
        "reviewed_room01_runtime_tile_attrs": REVIEWED_WALL_TILE_POLICY,
        "reviewed_room01_wall_oracle": reviewed_wall_oracle,
        "reviewed_room01_wall_replay_oracle": reviewed_wall_replay_oracle,
        "reviewed_room01_wall_replay_exact": reviewed_wall_replay_exact,
        "reviewed_room01_wall_oracle_ok": reviewed_wall_oracle_ok,
        "service_frame_presentations_exact": service_presentation_ok,
        "candidate_attribute_trajectory_exact": attribute_trajectory_ok,
        "candidate_physical_page_ownership_exact": (
            physical_page_ownership_ok
        ),
        "progress_route_geometry_exact": progress_geometry_ok,
        "full_route_geometry_maxima": geometry_maxima,
        "full_route_geometry_differences_present": (
            geometry_differences_present
        ),
        "full_route_geometry_worst_example": worst_geometry_example,
        "progress_route_viewports_exact": progress_trajectory_ok,
        "target_only_static_route_ok": target_only_static_route_ok,
        "gameplay_frame_lag": gameplay_frame_lag,
        "max_frame_lag": max_frame_lag,
        "max_frame_lag_ratio": args.max_frame_lag_ratio,
    }
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    if not world_template_ok:
        print(
            "FAIL: Stage-1 dungeon source differs from stock at entry: "
            f"{world_entry_differences}/0x880 bytes; first address "
            f"${0xC780 + first_world_entry_difference:04X}"
        )
        return 1
    if not metatile_table_ok:
        print(
            "FAIL: Stage-1 metatile table differs from stock at entry: "
            f"{metatile_differences}/0x400 bytes; first offset "
            f"0x{first_metatile_difference:03X}"
        )
        return 1
    if not terrain_ok:
        print(
            "FAIL: natural north room differs from the untouched ROM at "
            f"{terrain_differences}/{terrain['compared_bytes']} "
            "mutually visible terrain bytes; first candidate offset "
            f"0x{first_terrain_difference:03X}"
        )
        return 1
    if not replay_exact:
        print("FAIL: repeated candidate north route was not byte-identical")
        return 1
    if not final_state_ok:
        print(
            "FAIL: candidate north route did not stop at a settled Stage-1 "
            "presentation boundary: "
            f"candidate={candidate_settled['checks']} "
            f"replay={candidate_replay_settled and candidate_replay_settled['checks']}"
        )
        return 1
    # Presentation geometry is the primary user-facing contract.  Report an
    # actually corrupted viewport before any secondary palette or ownership
    # oracle, even when the same frame also produces attribute mismatches.
    if geometry_differences_present:
        print(
            "FAIL: a full-route north viewport contains non-stock geometry; "
            f"maxima={geometry_maxima}; worst={worst_geometry_example}"
        )
        return 1
    if not physical_page_ownership_ok:
        ownership = trajectory["candidate_attribute_integrity"][
            "physical_page_ownership"
        ]
        print(
            "FAIL: Stage-1 physical-page owner evidence is missing or "
            f"malformed; first={ownership['first_error']}; "
            f"candidate_report={candidate_owner_report['errors']}; "
            "replay_report="
            f"{candidate_replay_owner_report and candidate_replay_owner_report['errors']}"
        )
        return 1
    if not reviewed_wall_oracle_ok:
        wall = reviewed_wall_oracle["room01"]
        floor = reviewed_wall_oracle["room05_patterned_floor_control"]
        print(
            "FAIL: reviewed Stage-1 room-01 wall oracle rejected the north "
            f"trajectory: room01 records={wall['records']} "
            f"tile_mismatches={wall['tile_mismatches']} "
            f"attr_mismatches={wall['attr_mismatches']} "
            f"first={wall['first_mismatch']}; room05 "
            f"records={floor['records']} "
            f"patterned_attr_mismatches={floor['patterned_attr_mismatches']} "
            f"first={floor['first_mismatch']}; "
            f"replay_exact={reviewed_wall_replay_exact}"
        )
        if not candidate_prepublication["exact"]:
            print(
                "FAIL: opening visual stream is not exclusively unowned CGB "
                f"evidence: {candidate_prepublication}"
            )
        return 1
    if not attribute_trajectory_ok:
        attributes = trajectory["candidate_attribute_integrity"]
        print(
            "FAIL: a north-route VBK1 viewport differs from the configured "
            f"Stage-1 semantic checks in {attributes['mismatch_cells']} cells "
            f"across {attributes['mismatch_frames']} frames; first "
            f"{attributes['first_mismatch']}"
        )
        return 1
    if not service_presentation_ok:
        print(
            "FAIL: a banked/service north-route frame hid a non-stock "
            "presentation; maximum tile difference "
            f"{trajectory['maximum_service_viewport_tile_differences']}, "
            f"unmatched={trajectory['unmatched_service_presentation_records']}, "
            f"readable-nongameplay={trajectory['readable_non_gameplay_records']}"
        )
        return 1
    if not progress_geometry_ok:
        print(
            "FAIL: an intermediate north-route viewport differs from stock; "
            f"maximum tile difference "
            f"{trajectory['maximum_progress_viewport_tile_differences']} "
            f"across {trajectory['progress_matched_records']} progress-matched "
            f"frames, with {trajectory['unmatched_progress_records']} "
            "candidate frames having no stock world-coordinate counterpart"
        )
        return 1
    if (
        int(trajectory["unexpected_logical_state_records"]) != 0
        or int(trajectory["unmatched_display_state_records"]) != 0
    ):
        print(
            "FAIL: intermediate north-route state/viewport diverged from "
            "stock; maximum tile difference "
            f"{trajectory['maximum_viewport_tile_differences']} across "
            f"{trajectory['matched_records']} matched world states, "
            f"{trajectory['unexpected_logical_state_records']} unexpected "
            "logical states, and "
            f"{trajectory['unmatched_display_state_records']} unmatched "
            "display states"
        )
        return 1
    if not args.target_only and not lag_ok:
        print(
            "FAIL: candidate reached the target "
            f"{gameplay_frame_lag:+d} gameplay frames from stock; allowed "
            f"±{max_frame_lag}"
        )
        return 1
    print(
        "PASS: repeated north route reached stock-matching terrain and the "
        "reviewed room-01 walls remained exact "
        f"({terrain['compared_bytes']} exact bytes at ring phase "
        f"{terrain['phase_columns']:+d}) with "
        f"{gameplay_frame_lag:+d}-frame reported timing delta"
        f"{' (owned by speed matrix)' if args.target_only else ''}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
