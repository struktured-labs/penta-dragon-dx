#!/usr/bin/env python3
"""Audit every Stage-1 pickup class in one candidate-bound live state.

Unlike the historical pickup-state matrix, this verifier starts every form
from the same state produced by the candidate ROM.  It first validates the
savestate and its complete pickup-tile VRAM payload offline, then asks the
existing live probe to publish one pickup at a fixed, visible coordinate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Any
import zlib

from normalize_mgba_state_pc import RUNTIME_HELPER_ADDR, RUNTIME_HELPER_SIZE
from verify_pickup_class_palettes import (
    PICKUPS,
    VRAM_OFFSET,
    VRAM_SIZE,
    palette_words,
)
from verify_pickup_live_palettes import (
    MIN_MAIN_LOOP_HITS,
    STAGE1_HELPER_SOURCE_BANKS,
    STAGE1_LUT_OFFSET,
    STAGE1_RUNTIME_LENGTH,
    STAGE1_RUNTIME_SOURCE_OFFSETS,
    contact_sheet,
    pickup_occurrences,
    release_lock_scene_read,
    run_state,
    stage1_helper,
)
from verify_stage1_pickup_art import TARGETS, live_tile, rom_tile


ROOT = Path(__file__).resolve().parents[2]
GUARDED_MGBA = ROOT / "scripts/mgba-qt-singleflight"
HOST = (4, 16, 0xC1A0)  # row, column, 24-column WRAM source base
HOST_SOURCE_WIDTH = 24
HOST_SIGNATURE_SIZE = (2, 2)
STATE_SIZE = 0x11800
STATE_MAGIC = 0x00400003
IO_OFFSET = 0x300
HRAM_OFFSET = 0x380
WRAM_OFFSET = 0x4400


class PreflightError(RuntimeError):
    """A candidate/state invariant failed before an emulator was started."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PreflightError(message)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def strict_serialized_state(path: Path) -> bytes:
    """Extract one CRC-valid mGBA ``gbAs`` payload from a PNG savestate."""

    data = path.read_bytes()
    require(data.startswith(b"\x89PNG\r\n\x1a\n"),
            f"not an mGBA PNG savestate: {path}")
    offset = 8
    states: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        require(offset + 12 <= len(data),
                f"truncated PNG chunk header: {path}")
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        end = offset + 12 + length
        require(end <= len(data), f"truncated PNG chunk payload: {path}")
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        observed_crc = int.from_bytes(
            data[offset + 8 + length:end], "big",
        )
        expected_crc = zlib.crc32(kind + payload) & 0xFFFFFFFF
        require(observed_crc == expected_crc,
                f"bad PNG chunk CRC for {kind!r}: {path}")
        if kind == b"gbAs":
            try:
                states.append(zlib.decompress(payload))
            except zlib.error as error:
                raise PreflightError(
                    f"malformed compressed gbAs payload: {path}"
                ) from error
        if kind == b"IEND":
            saw_iend = True
        offset = end
    require(offset == len(data) and saw_iend,
            f"incomplete savestate PNG: {path}")
    require(len(states) == 1,
            f"expected exactly one gbAs payload, found {len(states)}: {path}")
    state = states[0]
    require(len(state) == STATE_SIZE,
            f"gbAs payload is {len(state):#x}, expected {STATE_SIZE:#x}")
    require(int.from_bytes(state[:4], "little") == STATE_MAGIC,
            f"unsupported gbAs state version: {path}")
    return state


def state_byte(state: bytes, address: int) -> int:
    if 0xC000 <= address <= 0xDFFF:
        return state[WRAM_OFFSET + address - 0xC000]
    if 0xFF00 <= address <= 0xFF7F:
        return state[IO_OFFSET + address - 0xFF00]
    if 0xFF80 <= address <= 0xFFFF:
        return state[HRAM_OFFSET + address - 0xFF80]
    raise ValueError(f"unsupported serialized address ${address:04X}")


def block(payload: bytes, offset: int, stride: int) -> tuple[int, int, int, int]:
    return (
        payload[offset], payload[offset + 1],
        payload[offset + stride], payload[offset + stride + 1],
    )


def visible_host(scx: int, scy: int) -> bool:
    row, column, _ = HOST
    for dy in range(HOST_SIGNATURE_SIZE[1]):
        for dx in range(HOST_SIGNATURE_SIZE[0]):
            screen_x = ((column + dx) * 8 - scx) & 0xFF
            screen_y = ((row + dy) * 8 - scy) & 0xFF
            if screen_x >= 160 or screen_y >= 144:
                return False
    return True


def load_state_receipt(
    path: Path,
    rom_sha256: str,
    state_sha256: str,
) -> dict[str, Any]:
    try:
        receipt = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"cannot read state receipt {path}: {error}") from error
    require(isinstance(receipt, dict), f"state receipt is not an object: {path}")
    require(
        receipt.get("schema") == "penta-stage1-current-pickup-state-v1",
        "state receipt schema is not the candidate-owned pickup generator",
    )
    require(str(receipt.get("rom_sha256", "")).lower() == rom_sha256,
            "state receipt ROM SHA-256 does not match the candidate")
    require(str(receipt.get("state_sha256", "")).lower() == state_sha256,
            "state receipt state SHA-256 does not match --state")
    require(receipt.get("passed") is True, "state receipt passed flag is not true")
    require(receipt.get("status") == "pass",
            "state receipt status is not pass")
    checks = receipt.get("checks")
    required_checks = (
        "state CRC is bound to candidate",
        "state is active Stage 1 gameplay",
        "candidate WRAM helper is initialized",
        "hardware is settled at save",
        "semantic pickup was visible with no mismatch",
        "terminal probe sample remains Stage 1-owned",
    )
    require(isinstance(checks, dict), "state receipt checks are missing")
    require(
        all(checks.get(name) is True for name in required_checks),
        "state receipt is missing a required passing generator check",
    )
    return receipt


def inspect_state(
    state_path: Path,
    rom: bytes,
    rom_sha256: str,
    receipt_path: Path | None,
) -> tuple[bytes, dict[str, Any], dict[int, bytes]]:
    state_sha256 = sha256_file(state_path)
    state = strict_serialized_state(state_path)
    state_crc32 = int.from_bytes(state[4:8], "little")
    rom_crc32 = zlib.crc32(rom) & 0xFFFFFFFF
    require(state_crc32 == rom_crc32,
            "savestate embedded ROM CRC32 does not match the candidate")
    state_title = state[0x10:0x20]
    rom_title = rom[0x134:0x144]
    require(len(rom_title) == 16 and state_title == rom_title,
            "savestate cartridge title does not match the candidate")

    receipt: dict[str, Any] | None = None
    if receipt_path is not None:
        receipt = load_state_receipt(receipt_path, rom_sha256, state_sha256)

    vram0 = state[VRAM_OFFSET:VRAM_OFFSET + VRAM_SIZE]
    vram1 = state[VRAM_OFFSET + VRAM_SIZE:VRAM_OFFSET + 2 * VRAM_SIZE]
    require(len(vram0) == VRAM_SIZE and len(vram1) == VRAM_SIZE,
            "savestate does not contain both complete VRAM banks")

    target_gfx: dict[int, bytes] = {}
    gfx_rows = []
    gfx_mismatches = []
    for tile in sorted(TARGETS):
        expected = rom_tile(rom, tile)
        observed = live_tile(vram0, tile)
        exact = len(expected) == 16 and observed == expected
        if not exact:
            gfx_mismatches.append(f"{tile:02X}")
        else:
            target_gfx[tile] = expected
        gfx_rows.append({
            "tile": f"{tile:02X}",
            "rom_sha256": sha256_bytes(expected),
            "state_vbk0_sha256": sha256_bytes(observed),
            "exact": exact,
        })
    require(not gfx_mismatches,
            "candidate/state pickup tile graphics differ: "
            + ",".join(gfx_mismatches))

    row, column, source_base = HOST
    map_offset = row * 32 + column
    map_signatures = {
        "9800": block(vram0, 0x1800 + map_offset, 32),
        "9C00": block(vram0, 0x1C00 + map_offset, 32),
    }
    map_attributes = {
        "9800": block(vram1, 0x1800 + map_offset, 32),
        "9C00": block(vram1, 0x1C00 + map_offset, 32),
    }
    source_address = source_base + row * HOST_SOURCE_WIDTH + column
    require(0xC000 <= source_address
            and source_address + HOST_SOURCE_WIDTH + 1 <= 0xC5FF,
            "coordinate host is outside the Stage-1 source plane")
    source_offset = WRAM_OFFSET + source_address - 0xC000
    source_signature = block(state, source_offset, HOST_SOURCE_WIDTH)
    lcdc = state_byte(state, 0xFF40)
    active_map = "9C00" if lcdc & 0x08 else "9800"
    require(map_signatures[active_map] == source_signature,
            "displayed host signature does not match its C1A0 source cells")
    require(map_signatures["9800"] == map_signatures["9C00"],
            "physical BG maps disagree at the coordinate host")
    require(len(set(source_signature)) > 1,
            "coordinate host is blank or uniform")
    scx, scy = state_byte(state, 0xFF43), state_byte(state, 0xFF42)
    require(visible_host(scx, scy),
            "coordinate host is not fully visible in the supplied state")
    require(state_byte(state, 0xD880) == 0x02
            and state_byte(state, 0xFFC1) == 0x01,
            "supplied state is not settled Stage-1 gameplay")

    metadata = {
        "path": str(state_path),
        "sha256": state_sha256,
        "gbas_sha256": sha256_bytes(state),
        "rom_crc32": f"{rom_crc32:08x}",
        "state_rom_crc32": f"{state_crc32:08x}",
        "cartridge_title_hex": state_title.hex(),
        "binding": (
            "receipt-sha256+gbas-crc32+cartridge-title"
            if receipt_path is not None
            else "gbas-crc32+cartridge-title"
        ),
        "receipt": ({
            "path": str(receipt_path),
            "sha256": sha256_file(receipt_path),
            "schema": receipt.get("schema"),
        } if receipt_path is not None and receipt is not None else None),
        "stage": {
            "D880": f"{state_byte(state, 0xD880):02X}",
            "FFC1": f"{state_byte(state, 0xFFC1):02X}",
            "FFBD": f"{state_byte(state, 0xFFBD):02X}",
            "LCDC": f"{lcdc:02X}",
            "SCX": f"{scx:02X}",
            "SCY": f"{scy:02X}",
        },
        "host": {
            "row": row,
            "column": column,
            "source_base": f"{source_base:04X}",
            "source_address": f"{source_address:04X}",
            "displayed_map": active_map,
            "screen_origin": {
                "x": ((column * 8 - scx) & 0xFF),
                "y": ((row * 8 - scy) & 0xFF),
            },
            "source_signature": [f"{value:02X}" for value in source_signature],
            "initial_pickup_class": next((
                pickup.name for pickup in PICKUPS
                if tuple(pickup.tiles) == source_signature
            ), None),
            "map_signatures": {
                key: [f"{value:02X}" for value in values]
                for key, values in map_signatures.items()
            },
            "initial_map_attributes": {
                key: [f"{value:02X}" for value in values]
                for key, values in map_attributes.items()
            },
        },
        "target_vram": {
            "expected_count": 73,
            "observed_count": len(TARGETS),
            "all_vbk0_exact": not gfx_mismatches,
            "tiles": gfx_rows,
        },
    }
    return state, metadata, target_gfx


def candidate_payloads(
    rom: bytes,
    output: Path,
) -> tuple[Path, Path, Path, dict[str, Any], dict[int, list[int]]]:
    runtime_copies = [
        rom[offset:offset + STAGE1_RUNTIME_LENGTH]
        for offset in STAGE1_RUNTIME_SOURCE_OFFSETS
    ]
    require(all(len(item) == STAGE1_RUNTIME_LENGTH for item in runtime_copies),
            "candidate is missing a Stage-1 runtime copy")
    require(len(set(runtime_copies)) == 1,
            "candidate Stage-1 runtime copies disagree")
    helper_copies = [stage1_helper(rom, bank)
                     for bank in STAGE1_HELPER_SOURCE_BANKS]
    require(all(len(item) == RUNTIME_HELPER_SIZE for item in helper_copies),
            "candidate is missing a complete Stage-1 WRAM helper")
    require(len(set(helper_copies)) == 1
            or release_lock_scene_read(rom, helper_copies),
            "candidate Stage-1 helper copies disagree")
    runtime_start = 0xDAD7 - RUNTIME_HELPER_ADDR
    require(
        helper_copies[0][runtime_start:runtime_start + STAGE1_RUNTIME_LENGTH]
        == runtime_copies[0],
        "candidate runtime is not the exact DAD7-DAFF helper tail",
    )
    lut = rom[STAGE1_LUT_OFFSET:STAGE1_LUT_OFFSET + 256]
    require(len(lut) == 256, "candidate is missing its Stage-1 semantic LUT")
    wrong_lut = [
        f"{pickup.name}:{tile:02X}={lut[tile]}!={pickup.palette}"
        for pickup in PICKUPS for tile in pickup.tiles
        if lut[tile] != pickup.palette
    ]
    require(not wrong_lut,
            "candidate pickup LUT classes disagree: " + ", ".join(wrong_lut))

    runtime_path = output / "candidate-stage1-runtime.bin"
    helper_path = output / "candidate-stage1-helper.bin"
    lut_path = output / "candidate-stage1-lut.bin"
    runtime_path.write_bytes(runtime_copies[0])
    helper_path.write_bytes(helper_copies[0])
    lut_path.write_bytes(lut)
    metadata = {
        "runtime_source_offsets": [
            f"0x{offset:X}" for offset in STAGE1_RUNTIME_SOURCE_OFFSETS
        ],
        "runtime_sha256": sha256_bytes(runtime_copies[0]),
        "helper_source_banks": list(STAGE1_HELPER_SOURCE_BANKS),
        "helper_runtime_address": f"{RUNTIME_HELPER_ADDR:04X}",
        "helper_sha256": sha256_bytes(helper_copies[0]),
        "lut_offset": f"0x{STAGE1_LUT_OFFSET:X}",
        "lut_sha256": sha256_bytes(lut),
    }
    expected_cram = {
        palette: palette_words(rom, palette) for palette in range(6)
    }
    return runtime_path, helper_path, lut_path, metadata, expected_cram


def integer(result: dict[str, Any], key: str) -> int:
    try:
        return int(str(result.get(key, "")), 10)
    except ValueError:
        return -1


def validate_run(
    pickup: Any,
    result: dict[str, Any],
    expected_cram: dict[int, list[int]],
    target_gfx: dict[int, bytes],
) -> tuple[list[str], dict[str, Any]]:
    failures: list[str] = []
    main_loop_hits = integer(result, "main_loop_hits")
    tile_copy_hits = integer(result, "tile_copy_hits")
    host_decision_hits = integer(result, "host_decision_hits")
    sustained = main_loop_hits >= MIN_MAIN_LOOP_HITS
    tile_copy = tile_copy_hits >= 1
    host_decision = host_decision_hits >= 1
    stage1 = result.get("D880") == "02" and result.get("FFC1") == "01"
    if not sustained:
        failures.append(
            f"main_loop_hits={main_loop_hits} < {MIN_MAIN_LOOP_HITS} "
            f"(PC={result.get('PC')}, SP={result.get('SP')})"
        )
    if not tile_copy:
        failures.append(f"tile_copy_hits={tile_copy_hits} < 1")
    if not host_decision:
        failures.append(f"host_decision_hits={host_decision_hits} < 1")
    if not stage1:
        failures.append(
            f"settled outside Stage 1 ({result.get('D880')}/"
            f"{result.get('FFC1')})"
        )

    cram_exact = True
    for palette, words in expected_cram.items():
        observed_words = result.get("cram", {}).get(palette)
        if observed_words != words:
            cram_exact = False
            failures.append(f"BG{palette} CRAM {observed_words} != ROM {words}")

    live_gfx_exact = True
    for tile in pickup.tiles:
        observed_tile = result.get("tile_gfx", {}).get((0, tile))
        if observed_tile != target_gfx[tile]:
            live_gfx_exact = False
            failures.append(f"VBK0:{tile:02X} live graphics differ from ROM")

    observed = result.get("pickups", {}).get(pickup.name)
    active_base = None
    host_occurrences: dict[str, list[dict[str, Any]]] = {}
    exact_attrs = False
    if observed is None:
        failures.append("pickup report is missing")
    else:
        try:
            lcdc = int(str(result.get("LCDC", "")), 16)
        except ValueError:
            lcdc = -1
        if lcdc < 0:
            failures.append(f"invalid LCDC report {result.get('LCDC')!r}")
        else:
            active_base = "9C00" if lcdc & 0x08 else "9800"
            row, column, _ = HOST
            occurrences = pickup_occurrences(observed["details"])
            host_occurrences = {
                base: [
                    occurrence
                    for occurrence in occurrences
                    if occurrence["base"] == base
                    and occurrence["row"] == row
                    and occurrence["column"] == column
                ]
                for base in ("9800", "9C00")
            }
            exact_attrs = all(
                len(host_occurrences[base]) == 1
                and host_occurrences[base][0]["attrs"]
                == [pickup.palette] * 4
                for base in ("9800", "9C00")
            )
            if not exact_attrs:
                failures.append(
                    f"physical-map hosts ({column},{row}) are not both exact "
                    f"raw BG{pickup.palette} attrs: {host_occurrences}"
                )
        if observed.get("palette") != pickup.palette:
            exact_attrs = False
            failures.append(
                f"reported semantic class {observed.get('palette')} "
                f"!= BG{pickup.palette}"
            )

    host_visible = False
    try:
        host_visible = visible_host(
            int(str(result.get("SCX", "")), 16),
            int(str(result.get("SCY", "")), 16),
        )
    except ValueError:
        pass
    if not host_visible:
        failures.append("coordinate host is not fully visible in final frame")

    gates = {
        "main_loop_hits_at_least_8": sustained,
        "tile_copy_executed": tile_copy,
        "coordinate_host_decision_executed": host_decision,
        "stage1_gameplay": stage1,
        "candidate_cram_bg0_bg5_exact": cram_exact,
        "candidate_vbk0_pickup_gfx_exact": live_gfx_exact,
        "both_physical_hosts_exact_raw_semantic_attrs_no_bg0_fallback": exact_attrs,
        "displayed_host_fully_visible": host_visible,
        "displayed_map": active_base,
        "physical_host_occurrences": host_occurrences,
    }
    return failures, gates


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def write_receipt(output: Path, receipt: dict[str, Any]) -> Path:
    path = output / "receipt.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, help="candidate ROM")
    parser.add_argument("--state", type=Path, required=True,
                        help="candidate-generated current Stage-1 state")
    parser.add_argument("--state-receipt", type=Path, required=True,
                        help="required SHA-binding receipt for --state")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--demo-rearm-rows", type=int, default=18)
    parser.add_argument("--launch-attempts", type=int, default=2)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    if args.demo_rearm_rows < 0:
        parser.error("--demo-rearm-rows must be non-negative")
    if args.launch_attempts < 1:
        parser.error("--launch-attempts must be at least 1")

    rom_path = args.rom.resolve()
    state_path = args.state.resolve()
    receipt_path = args.state_receipt.resolve()
    output = args.output.resolve()
    allowed = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    if not any(root.exists() and output != root and output.is_relative_to(root)
               for root in allowed):
        parser.error("--output must be a child of repo tmp/ or /mnt/data/tmp/")
    if not rom_path.is_file():
        parser.error(f"candidate ROM not found: {rom_path}")
    if not state_path.is_file():
        parser.error(f"savestate not found: {state_path}")
    if not receipt_path.is_file():
        parser.error(f"state receipt not found: {receipt_path}")
    if not GUARDED_MGBA.is_file():
        parser.error(f"checked-in single-flight mGBA wrapper missing: {GUARDED_MGBA}")
    output.mkdir(parents=True, exist_ok=True)

    rom = rom_path.read_bytes()
    rom_sha256 = sha256_bytes(rom)
    failures: list[str] = []
    state_metadata: dict[str, Any] | None = None
    payload_metadata: dict[str, Any] | None = None
    state_results: list[dict[str, Any]] = []
    form_results: list[dict[str, Any]] = []
    sheet = output / "pickup-current-host-palettes.png"
    sheet.unlink(missing_ok=True)

    try:
        pickup_tiles = {tile for pickup in PICKUPS for tile in pickup.tiles}
        require(len(PICKUPS) == 19, f"pickup inventory has {len(PICKUPS)} forms")
        require(len(TARGETS) == 73,
                f"pickup target inventory has {len(TARGETS)} tiles")
        require(pickup_tiles == set(TARGETS),
                "pickup form inventory and target graphics inventory disagree")
        _, state_metadata, target_gfx = inspect_state(
            state_path, rom, rom_sha256, receipt_path,
        )
        (
            runtime_path,
            helper_path,
            lut_path,
            payload_metadata,
            expected_cram,
        ) = candidate_payloads(rom, output)
    except (OSError, PreflightError) as error:
        failures.append(f"preflight: {error}")
        state_ready = state_metadata is not None
        checks = {
            "current state is candidate-bound": state_ready,
            "all 73 target VRAM graphics match the candidate offline": state_ready,
            "coordinate host is source/map exact and visible": state_ready,
            "candidate Stage-1 helper and semantic LUT are internally exact": (
                payload_metadata is not None
            ),
            "all 19 pickup form replays completed": False,
        }
        receipt = {
            "schema": "penta-dragon-dx-pickup-current-host-palettes-v1",
            "status": "fail",
            "passed": False,
            "rom": str(rom_path),
            "rom_sha256": rom_sha256,
            "state": state_metadata or {
                "path": str(state_path),
                "sha256": sha256_file(state_path),
            },
            "candidate_payloads": payload_metadata,
            "host": {"row": HOST[0], "column": HOST[1],
                     "source_base": f"{HOST[2]:04X}"},
            "checks": checks,
            "forms": [],
            "contact_sheet": None,
            "failures": failures,
        }
        receipt_file = write_receipt(output, receipt)
        print(f"FAIL: {failures[0]}")
        print(f"Receipt: {receipt_file}")
        return 1

    for pickup in PICKUPS:
        artifact_stem = f"pickup-current-host-{slug(pickup.name)}"
        try:
            result = run_state(
                GUARDED_MGBA,
                rom_path,
                state_path,
                [pickup],
                output,
                args.timeout,
                args.demo_rearm_rows,
                args.launch_attempts,
                runtime_path,
                helper_path,
                lut_path,
                artifact_stem=artifact_stem,
                host=HOST,
            )
            run_failures, gates = validate_run(
                pickup, result, expected_cram, target_gfx,
            )
            screenshot = output / f"{artifact_stem}.png"
            form_failures = [f"{pickup.name}: {item}" for item in run_failures]
            failures.extend(form_failures)
            result_without_gfx = {
                key: value for key, value in result.items() if key != "tile_gfx"
            }
            form = {
                "name": pickup.name,
                "palette": pickup.palette,
                "tiles": [f"{tile:02X}" for tile in pickup.tiles],
                "status": "fail" if run_failures else "pass",
                "screenshot": str(screenshot),
                "screenshot_sha256": sha256_file(screenshot),
                "gates": gates,
                "report": result_without_gfx,
                "failures": run_failures,
            }
            form_results.append(form)
            state_results.append({
                "screenshot": str(screenshot),
                "pickups": [pickup.name],
            })
        except Exception as error:  # preserve all other form evidence
            message = f"{pickup.name}: replay failed: {error}"
            failures.append(message)
            form_results.append({
                "name": pickup.name,
                "palette": pickup.palette,
                "tiles": [f"{tile:02X}" for tile in pickup.tiles],
                "status": "fail",
                "screenshot": None,
                "gates": {},
                "failures": [str(error)],
            })

    if state_results:
        try:
            contact_sheet(state_results, sheet)
        except Exception as error:
            sheet.unlink(missing_ok=True)
            failures.append(f"contact sheet: {error}")

    replay_complete = len(form_results) == len(PICKUPS) and all(
        form.get("screenshot") is not None for form in form_results
    )
    all_forms = replay_complete and all(
        form["status"] == "pass" for form in form_results
    )
    all_screenshots = len(state_results) == len(PICKUPS) and all(
        Path(row["screenshot"]).is_file() for row in state_results
    )

    def every_form_gate(name: str) -> bool:
        return replay_complete and all(
            form.get("gates", {}).get(name) is True for form in form_results
        )

    checks = {
        "current state is candidate-bound": state_metadata is not None,
        "coordinate host is source/map exact and visible": state_metadata is not None,
        "all 73 target VRAM graphics match the candidate offline": (
            state_metadata is not None
            and state_metadata["target_vram"]["all_vbk0_exact"]
            and state_metadata["target_vram"]["observed_count"] == 73
        ),
        "candidate Stage-1 helper and semantic LUT are internally exact": (
            payload_metadata is not None
        ),
        "all 19 pickup form replays completed": replay_complete,
        "all 19 pickup forms passed every live gate": all_forms,
        "both physical hosts use exact raw semantic attrs with no BG0 fallback": (
            every_form_gate(
                "both_physical_hosts_exact_raw_semantic_attrs_no_bg0_fallback"
            )
        ),
        f"all form runs hit the main loop at least {MIN_MAIN_LOOP_HITS} times": (
            every_form_gate("main_loop_hits_at_least_8")
        ),
        "all form runs execute a current-ROM tile copy": (
            every_form_gate("tile_copy_executed")
        ),
        "all form runs execute the coordinate-host decision": (
            every_form_gate("coordinate_host_decision_executed")
        ),
        "all form runs remain in Stage 1": (
            every_form_gate("stage1_gameplay")
        ),
        "all form runs load candidate BG0-BG5 CRAM exactly": (
            every_form_gate("candidate_cram_bg0_bg5_exact")
        ),
        "all live pickup graphics remain candidate-exact": (
            every_form_gate("candidate_vbk0_pickup_gfx_exact")
        ),
        "one valid screenshot per pickup form": all_screenshots,
        "contact sheet covers all 19 pickup forms": (
            all_screenshots and sheet.is_file()
        ),
    }
    for name, passed in checks.items():
        if not passed and name not in failures:
            failures.append(name)

    receipt = {
        "schema": "penta-dragon-dx-pickup-current-host-palettes-v1",
        "status": "pass" if not failures else "fail",
        "passed": not failures,
        "rom": str(rom_path),
        "rom_md5": hashlib.md5(rom).hexdigest(),  # release receipt compatibility
        "rom_sha256": rom_sha256,
        "state": state_metadata,
        "candidate_payloads": payload_metadata,
        "host": {"row": HOST[0], "column": HOST[1],
                 "source_base": f"{HOST[2]:04X}"},
        "checks": checks,
        "forms": form_results,
        "contact_sheet": sheet.name if sheet.is_file() else None,
        "contact_sheet_sha256": sha256_file(sheet) if sheet.is_file() else None,
        "failures": failures,
    }
    receipt_file = write_receipt(output, receipt)
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    for failure in failures[:40]:
        print(f"  FAIL: {failure}")
    if sheet.is_file():
        print(f"Contact sheet: {sheet}")
    print(f"Receipt: {receipt_file}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
