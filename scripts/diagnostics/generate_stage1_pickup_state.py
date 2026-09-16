#!/usr/bin/env python3
"""Generate a candidate-owned Stage-1 state with live semantic pickups."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import zlib


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/diagnostics"))

from normalize_mgba_state_pc import (  # noqa: E402
    GB_STATE_SIZE,
    png_chunks,
    state_offset,
)
from verify_stage1_pickup_art import TARGETS  # noqa: E402


PROBE = ROOT / "scripts/diagnostics/probe_stage1_no_bleed.lua"
MGBA = ROOT / "scripts/mgba-qt-singleflight"
DUNGEON_TABLE_OFFSET = 13 * 0x4000 + (0x7000 - 0x4000)
IO_OFFSET = 0x300
VIDEO_CURRENT_VRAM_BANK = 0x00CC
CURRENT_RUNTIME_EPOCH = 0xA9
RUNTIME_EPOCH_OFFSETS = tuple(
    bank * 0x4000 + address - 0x4000 + 4
    for bank in (13, 16)
    for address in (0x6B10, 0x6B19, 0x6B80, 0x5551)
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_probe(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result.setdefault(key, value)
    return result


def stop_owned_process_group(process: subprocess.Popen) -> None:
    """Stop only the guarded emulator session started by this generator."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=2)


def serialized_state(path: Path) -> bytes:
    payloads = [
        payload for kind, payload in png_chunks(path.read_bytes())
        if kind == b"gbAs"
    ]
    if len(payloads) != 1:
        raise RuntimeError("generated state does not contain exactly one gbAs chunk")
    raw = zlib.decompress(payloads[0])
    if len(raw) != GB_STATE_SIZE:
        raise RuntimeError(f"unexpected generated state size 0x{len(raw):X}")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--mgba", type=Path, default=MGBA)
    args = parser.parse_args()

    rom = args.rom.resolve()
    output = args.output.resolve()
    allowed = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    if not any(output.is_relative_to(root) for root in allowed):
        parser.error("--output must be under repo tmp/ or /mnt/data/tmp/")
    if not rom.is_file():
        parser.error(f"ROM not found: {rom}")
    if args.mgba.resolve() != MGBA.resolve():
        parser.error("--mgba must remain the checked-in single-flight wrapper")
    output.mkdir(parents=True, exist_ok=True)

    state = output / "current-pickup.ss0"
    screenshot = output / "current-pickup.png"
    report = output / "probe.txt"
    done = output / "DONE"
    receipt_path = output / "receipt.json"
    log = output / "mgba.log"
    lut = output / "stage1-bg-table.bin"
    for stale in (state, screenshot, report, done, receipt_path):
        stale.unlink(missing_ok=True)

    rom_bytes = rom.read_bytes()
    lut_bytes = rom_bytes[DUNGEON_TABLE_OFFSET:DUNGEON_TABLE_OFFSET + 256]
    # BG7 tooth entries intentionally carry the VBK1 bit (0x08), yielding
    # semantic value 0x0F.  Reject other values, but do not reject the
    # reviewed hazard encoding itself.
    if len(lut_bytes) != 256 or any(
        value not in (*range(8), 0x0F) for value in lut_bytes
    ):
        parser.error("candidate ROM is missing a valid Stage-1 semantic LUT")
    lut.write_bytes(lut_bytes)

    environment = os.environ.copy()
    # This state must come from a cold candidate boot.  Never inherit the
    # no-bleed probe's optional state/runtime injection controls.
    for key in tuple(environment):
        if key.startswith("STAGE1_BLEED_"):
            environment.pop(key)
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        environment.pop(key, None)
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE1_BLEED_OUT": str(output),
        "STAGE1_BLEED_FRAMES": "6",
        "STAGE1_BLEED_MODE": "box",
        "STAGE1_BLEED_LUT": str(lut),
        "STAGE1_BLEED_PICKUP_TILES": ",".join(
            f"{tile:02X}" for tile in sorted(TARGETS)
        ),
        "STAGE1_BLEED_PICKUP_STATE_OUT": str(state),
        "STAGE1_BLEED_PICKUP_STATE_SCREENSHOT": str(screenshot),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)

    process = None
    with log.open("w") as stream:
        try:
            process = subprocess.Popen(
                [
                    str(MGBA), "--fastforward",
                    "-C", f"savegamePath={output}",
                    "-C", f"savestatePath={output}",
                    str(rom), "--script", str(PROBE), "-l", "0",
                ],
                cwd=ROOT,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                if state.is_file() and report.is_file() and done.is_file():
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            if process is not None:
                stop_owned_process_group(process)

    if not (state.is_file() and screenshot.is_file()
            and report.is_file() and done.is_file()):
        status = None if process is None else process.returncode
        raise RuntimeError(
            f"guarded current-pickup generator failed ({status}); see {log}"
        )
    probe = parse_probe(report)
    required_probe = {
        "pickup_state_saved": "1",
        "unexpected_cells": "0",
        "unsafe_cells": "0",
        "final_ffc1": "1",
    }
    wrong = {
        key: probe.get(key) for key, expected in required_probe.items()
        if probe.get(key) != expected
    }
    # The probe saves the fixture before its final callback.  That callback can
    # land while banked WRAM makes D880 unreadable (the report above records
    # the raw byte, not a reconstructed scene).  The saved state is the
    # artifact subsequently consumed by dependent gates, so authenticate its
    # own Stage-1 ownership as an independent terminal witness.
    raw = serialized_state(state)
    saved_state_stage1_owned = (
        raw[state_offset(0xD880)] in {0x02, 0x0A}
        and raw[state_offset(0xFFC1)] == 0x01
    )
    try:
        final_pc = int(probe.get("final_pc", "-1"))
        final_svbk = int(probe.get("final_svbk", "-1")) & 0x07
        scene_frames = int(probe.get("scene_frames", "-1"))
        frames = int(probe.get("frames", "-1"))
    except ValueError as error:
        raise RuntimeError(
            "generated pickup state has malformed terminal probe values"
        ) from error
    terminal_compiler_sample = (
        probe.get("final_compiler_unreadable") == "1"
        and final_svbk == 0x03
        and (
            0x42A7 <= final_pc <= 0x436D
            or 0xD400 <= final_pc <= 0xD478
        )
    )
    terminal_scene_owned = (
        probe.get("final_scene") in {"2", "10"}
        or terminal_compiler_sample
        or saved_state_stage1_owned
    )
    # The first frame can be sampled before the scene byte is published even
    # though the active gameplay latch and the terminal ownership sample are
    # already valid.  Keep this bounded to exactly one callback; the saved
    # fixture still requires every requested frame to be active gameplay and
    # the final sample to be Stage-1-owned.
    scene_coverage_ok = scene_frames >= frames - 1
    if (
        wrong
        or not terminal_scene_owned
        or not scene_coverage_ok
        or int(probe.get("pal1_cells", "0")) <= 0
    ):
        wrong["terminal_scene_ownership"] = {
            "final_scene": probe.get("final_scene"),
            "final_pc": probe.get("final_pc"),
            "final_svbk": probe.get("final_svbk"),
            "final_compiler_unreadable": probe.get(
                "final_compiler_unreadable"
            ),
            "scene_frames": probe.get("scene_frames"),
            "frames": probe.get("frames"),
        }
        raise RuntimeError(f"generated pickup state failed semantic probe: {wrong}")

    expected_crc = zlib.crc32(rom_bytes) & 0xFFFFFFFF
    candidate_runtime_epochs = {
        rom_bytes[offset] for offset in RUNTIME_EPOCH_OFFSETS
    }
    hardware = {
        "hdma5": raw[IO_OFFSET + 0x55],
        "vbk": raw[VIDEO_CURRENT_VRAM_BANK],
        "svbk": raw[IO_OFFSET + 0x70] & 0x07,
        "lcdc": raw[IO_OFFSET + 0x40],
        "runtime_epoch": raw[state_offset(0xDF51)],
    }
    checks = {
        "state CRC is bound to candidate": (
            int.from_bytes(raw[0x0004:0x0008], "little") == expected_crc
        ),
        "state is active Stage 1 gameplay": (
            raw[state_offset(0xD880)] == 0x02
            and raw[state_offset(0xFFC1)] == 0x01
        ),
        "candidate WRAM helper is initialized": (
            candidate_runtime_epochs == {CURRENT_RUNTIME_EPOCH}
            and hardware["runtime_epoch"] == CURRENT_RUNTIME_EPOCH
        ),
        "hardware is settled at save": (
            hardware["hdma5"] == 0xFF
            and hardware["vbk"] == 0
            and hardware["svbk"] == 1
            and hardware["lcdc"] & 0x80 != 0
        ),
        "semantic pickup was visible with no mismatch": (
            int(probe.get("pal1_cells", "0")) > 0
            and probe.get("unexpected_cells") == "0"
            and probe.get("unsafe_cells") == "0"
        ),
        "terminal probe sample remains Stage 1-owned": (
            terminal_scene_owned
            and scene_coverage_ok
            and probe.get("final_ffc1") == "1"
        ),
        "saved state independently records active Stage 1": (
            saved_state_stage1_owned
        ),
    }
    receipt = {
        "schema": "penta-stage1-current-pickup-state-v1",
        "status": "pass" if all(checks.values()) else "fail",
        "passed": all(checks.values()),
        "rom": str(rom),
        "rom_sha256": digest(rom),
        "state": str(state),
        "state_sha256": digest(state),
        "screenshot": str(screenshot),
        "screenshot_sha256": digest(screenshot),
        "probe": probe,
        "hardware": hardware,
        "checks": checks,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"State: {state}")
    print(f"Receipt: {receipt_path}")
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
