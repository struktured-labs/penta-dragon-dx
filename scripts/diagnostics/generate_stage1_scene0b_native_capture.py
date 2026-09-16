#!/usr/bin/env python3
"""Derive a closed scene-$0B capture through native SELECT input only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import time
from typing import Any
import zlib


ROOT = Path(__file__).resolve().parents[2]
DIAGNOSTICS = Path(__file__).resolve().parent
if str(DIAGNOSTICS) not in sys.path:
    sys.path.insert(0, str(DIAGNOSTICS))

from normalize_mgba_state_pc import (  # noqa: E402
    png_chunks,
    retarget_rom_identity,
    write_png,
)
from verify_stage1_scene0b_captured_menu_receipt import (  # noqa: E402
    ADDRESS_BY_NAME,
    gbas_payload,
    state_byte,
)


SCHEMA = "penta-stage1-scene0b-native-capture-v1"
SOURCE_LABEL = "operator-low-health-menu-loaded"
SOURCE = ROOT / "save_states_for_claude/rc11_low-health-degradation.ss0"
SOURCE_SHA256 = (
    "1ea1b02625268a64982bcf272177ce89527a5a99c0baa49e6a1e247a9d2c8b67"
)
SOURCE_GBAS_SHA256 = (
    "6d379c9711c8d2a396523ca50a6da268651e69fc2a8768e30ce4d139d8b4fdd0"
)
SOURCE_ROM_CRC32 = "ca97c15e"
SOURCE_ROM_IDENTITY = "50454e5441445241474f4e0000000080"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
SINGLEFLIGHT_IMPLEMENTATION = ROOT / "scripts/mgba_singleflight.py"
PROCESS_CHECK = ROOT / "scripts/check_emulator_processes.sh"
STATE_RETARGETER = DIAGNOSTICS / "normalize_mgba_state_pc.py"
PROBE = DIAGNOSTICS / "probe_generate_stage1_scene0b_native_capture.lua"
SETTLE_FRAMES = 60
GBAS_ROM_CRC_OFFSET = 4
GBAS_TITLE_OFFSET = 0x10
GBAS_TITLE_SIZE = 16
GBAS_MODEL_OFFSET = 0x08
GBAS_BOOT_REGISTER_OFFSET = 0x350
ROM_TITLE_OFFSET = 0x134
GB_MODEL_CGB = 0x80
CGB_COMPATIBLE_FLAG = 0x80
CGB_ONLY_FLAG = 0xC0


class CaptureError(RuntimeError):
    """The native capture could not be derived or authenticated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CaptureError(message)


def sha256(path: Path) -> str:
    require(path.is_file(), f"required file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def default_qt_emulator() -> Path:
    for candidate in (
        Path("/home/struktured/bin/mgba-qt"),
        Path("/usr/bin/mgba-qt"),
        Path("/usr/local/bin/mgba-qt"),
    ):
        if candidate.is_file():
            return candidate.resolve()
    raise CaptureError("default checked Qt emulator executable is missing")


def scratch_output(path: Path) -> Path:
    resolved = path.resolve()
    roots = ((ROOT / "tmp").resolve(), Path("/mnt/data/tmp").resolve())
    require(any(
        root.exists() and resolved != root and resolved.is_relative_to(root)
        for root in roots
    ), "output must be below repo tmp/ or /mnt/data/tmp/")
    require(not resolved.exists(), f"refusing to reuse output: {resolved}")
    resolved.mkdir(parents=True)
    return resolved


def state_fields(state: bytes) -> dict[str, str]:
    return {
        name: f"{state_byte(state, address):02X}"
        for name, address in ADDRESS_BY_NAME.items()
    }


def audit_probe_source(source: str) -> dict[str, Any]:
    required = (
        "emu:loadStateFile(STATE_IN)",
        "emu:saveStateFile(STATE_OUT)",
        "emu:setKeys(KEY_SELECT)",
        "emu:setKeys(0)",
        "emu:read8(0xD880)",
        "emu:read8(0xFFE4)",
        "emu:read8(0xFFC1)",
        "emu:read8(0xFF70)",
        "deferred_wram_frames = deferred_wram_frames + 1",
        'finish("pass", "candidate-native-select-close")',
        'write_token_marker(".startup", "started")',
        'write_token_marker(".ready", "ready")',
        'write_token_marker(".done", status)',
    )
    for snippet in required:
        require(snippet in source,
                f"native-capture probe lacks contract: {snippet}")
    for snippet in ("emu:write8", "writeRange", "memory:write"):
        require(snippet not in source,
                f"native-capture probe contains a machine write: {snippet}")
    require(source.count("emu:loadStateFile(") == 1,
            "native-capture probe must load exactly one source state")
    require(source.count("emu:saveStateFile(") == 1,
            "native-capture probe must save exactly one derived state")
    return {
        "probe_sha256": sha256_bytes(source.encode()),
        "native_select_only": True,
        "source_state_loads": 1,
        "derived_state_saves": 1,
        "gameplay_writes": 0,
        "fixture_writes": 0,
        "vram_injection_bytes": 0,
    }


def parse_marker(path: Path, token: str, status: str) -> bool:
    if not path.is_file():
        return False
    values = dict(
        line.split("=", 1) for line in path.read_text().splitlines()
        if "=" in line
    )
    return values == {"status": status, "startup_token": token}


def parse_report(path: Path, token: str) -> dict[str, str]:
    require(path.is_file(), "native-capture probe report is missing")
    values = dict(
        line.split("=", 1) for line in path.read_text().splitlines()
        if "=" in line
    )
    required = {
        "status", "reason", "startup_token", "frames", "select_frames",
        "closed_settle_frames", "menu_open_events", "menu_close_events",
        "deferred_wram_frames", "state_saved", "scene", "room", "active",
        "menu", "lcdc", "scy", "scx",
    }
    require(set(values) == required,
            "native-capture probe report fields changed")
    require(values["status"] == "pass"
            and values["reason"] == "candidate-native-select-close"
            and values["startup_token"] == token,
            "native-capture probe did not produce authenticated PASS")
    return values


def stop_owned_process(process: subprocess.Popen[bytes]) -> dict[str, Any]:
    existing = process.poll()
    if existing is not None:
        return {
            "exact_child_terminated": False,
            "termination_method": "already-exited",
            "return_code": existing,
        }
    process.terminate()
    method = "SIGTERM"
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)
        method = "SIGKILL-after-SIGTERM-timeout"
    return {
        "exact_child_terminated": True,
        "termination_method": method,
        "return_code": int(process.returncode),
    }


def export_legacy_identity(
    source: Path, destination: Path, identity_source: bytes,
) -> list[int]:
    chunks = png_chunks(source.read_bytes())
    indices = [index for index, (kind, _) in enumerate(chunks)
               if kind == b"gbAs"]
    require(len(indices) == 1,
            "generated state must contain exactly one gbAs chunk")
    index = indices[0]
    try:
        raw = bytearray(zlib.decompress(chunks[index][1]))
    except zlib.error as error:
        raise CaptureError("generated gbAs payload is malformed") from error
    require(len(raw) == len(identity_source),
            "generated and source gbAs sizes differ")
    before = bytes(raw)
    raw[GBAS_ROM_CRC_OFFSET:GBAS_ROM_CRC_OFFSET + 4] = identity_source[
        GBAS_ROM_CRC_OFFSET:GBAS_ROM_CRC_OFFSET + 4
    ]
    raw[GBAS_TITLE_OFFSET:GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE] = (
        identity_source[GBAS_TITLE_OFFSET:GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE]
    )
    differences = [
        offset for offset, pair in enumerate(zip(before, raw, strict=True))
        if pair[0] != pair[1]
    ]
    require(set(differences) <= {4, 5, 6, 7, 0x1F}
            and 0x1F in differences,
            "legacy export changed non-identity machine state")
    chunks[index] = (b"gbAs", zlib.compress(bytes(raw), level=9))
    write_png(destination, chunks)
    return differences


def run_process_check() -> dict[str, Any]:
    completed = subprocess.run(
        [str(PROCESS_CHECK)], cwd=ROOT, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace",
    )
    return {"return_code": completed.returncode,
            "output": completed.stdout.strip()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    try:
        candidate = args.rom.resolve()
        require(candidate.is_file(), f"candidate ROM is missing: {candidate}")
        require(args.timeout > 5.0, "--timeout must be greater than five seconds")
        output = scratch_output(args.output)
        require(sha256(SOURCE) == SOURCE_SHA256,
                "compatible operator source capture hash changed")
        source_state = gbas_payload(SOURCE)
        require(sha256_bytes(source_state) == SOURCE_GBAS_SHA256,
                "compatible operator source gbAs hash changed")
        require(f"{int.from_bytes(source_state[4:8], 'little'):08x}"
                == SOURCE_ROM_CRC32,
                "compatible operator source ROM CRC changed")
        require(source_state[GBAS_TITLE_OFFSET:
                             GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE].hex()
                == SOURCE_ROM_IDENTITY,
                "compatible operator source ROM identity changed")
        require(state_fields(source_state)["D880"] == "0B"
                and state_fields(source_state)["FFE4"] == "01",
                "compatible operator source is not menu-loaded scene $0B")
        probe_contract = audit_probe_source(PROBE.read_text())
    except (CaptureError, OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1

    runtime = output / "runtime"
    runtime.mkdir()
    runtime_rom = runtime / "candidate.gb"
    runtime_state = runtime / "source-retargeted.ss0"
    shutil.copy2(candidate, runtime_rom)
    try:
        require(sha256(runtime_rom) == sha256(candidate),
                "isolated candidate hash changed")
        retarget_rom_identity(SOURCE, runtime_state, runtime_rom)
        retargeted_payload = gbas_payload(runtime_state)
        changed_source_to_runtime = [
            offset for offset, pair in enumerate(zip(
                source_state, retargeted_payload, strict=True
            )) if pair[0] != pair[1]
        ]
        require(set(changed_source_to_runtime) <= {4, 5, 6, 7, 0x1F}
                and 0x1F in changed_source_to_runtime,
                "source retarget changed machine state")

        generated_state = output / "scene0b-native-closed.ss0"
        screenshot = output / "scene0b-native-closed.png"
        prefix = output / "derive"
        report_path = Path(str(prefix) + ".report")
        startup_path = Path(str(prefix) + ".startup")
        ready_path = Path(str(prefix) + ".ready")
        done_path = Path(str(prefix) + ".done")
        log_path = output / "emulator.log"
        token = secrets.token_hex(32)
        environment = os.environ.copy()
        for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
            environment.pop(key, None)
        environment.update({
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
            "TMPDIR": str((ROOT / "tmp").resolve()),
            "PENTA_SCENE0B_DERIVE_STATE_IN": str(runtime_state),
            "PENTA_SCENE0B_DERIVE_STATE_OUT": str(generated_state),
            "PENTA_SCENE0B_DERIVE_SCREENSHOT_OUT": str(screenshot),
            "PENTA_SCENE0B_DERIVE_PREFIX": str(prefix),
            "PENTA_SCENE0B_DERIVE_TOKEN": token,
            "PENTA_SCENE0B_DERIVE_SETTLE_FRAMES": str(SETTLE_FRAMES),
        })
        environment.pop("DISPLAY", None)
        environment.pop("WAYLAND_DISPLAY", None)
        command = [
            str(LAUNCHER), "--fastforward",
            "-C", f"savegamePath={runtime}",
            "-C", f"savestatePath={runtime}",
            "--script", str(PROBE), str(runtime_rom),
        ]
        started_at_ns = time.time_ns()
        with log_path.open("wb") as stream:
            process = subprocess.Popen(
                command, cwd=output, env=environment,
                stdout=stream, stderr=subprocess.STDOUT,
            )
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                if parse_marker(done_path, token, "pass"):
                    break
                if process.poll() is not None:
                    break
                time.sleep(0.02)
            completion_authenticated = parse_marker(done_path, token, "pass")
            if not completion_authenticated:
                outcome = stop_owned_process(process)
                process_check = run_process_check()
                if outcome["return_code"] == 75:
                    raise CaptureError(
                        "another emulator owns the single-flight slot"
                    )
                raise CaptureError(
                    "native-capture probe did not complete; "
                    f"process={outcome}; process_check={process_check}"
                )
            outcome = stop_owned_process(process)
        completed_at_ns = time.time_ns()
        require(parse_marker(startup_path, token, "started")
                and parse_marker(ready_path, token, "ready"),
                "native-capture startup/ready markers are not authenticated")
        require(outcome["return_code"] in {
            0, -signal.SIGTERM, -signal.SIGKILL,
        }, "native-capture child teardown status is not accepted")
        report = parse_report(report_path, token)
        require(generated_state.is_file() and screenshot.is_file(),
                "native-capture state or screenshot is missing")
        require(int(report["select_frames"]) > 0
                and int(report["closed_settle_frames"]) >= SETTLE_FRAMES
                and report["menu_open_events"] == "0"
                and report["menu_close_events"] == "1"
                and report["state_saved"] == "1"
                and report["scene"] == "0B"
                and report["active"] == "01"
                and report["menu"] == "00",
                "native-capture route did not close and settle exactly")

        generated_payload = gbas_payload(generated_state)
        candidate_bytes = candidate.read_bytes()
        candidate_crc32 = zlib.crc32(candidate_bytes) & 0xFFFFFFFF
        candidate_identity = candidate_bytes[
            ROM_TITLE_OFFSET:ROM_TITLE_OFFSET + GBAS_TITLE_SIZE
        ]
        require(generated_payload[GBAS_MODEL_OFFSET] == GB_MODEL_CGB
                and generated_payload[GBAS_BOOT_REGISTER_OFFSET] != 0xFF,
                "generated state is not post-BIOS CGB")
        require(int.from_bytes(generated_payload[4:8], "little")
                == candidate_crc32,
                "generated state does not carry candidate CRC")
        require(generated_payload[GBAS_TITLE_OFFSET:
                                  GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE]
                == candidate_identity
                and candidate_identity[15] == CGB_ONLY_FLAG,
                "generated state does not carry candidate identity")
        generated_fields = state_fields(generated_payload)
        require(generated_fields["D880"] == "0B"
                and generated_fields["FFE4"] == "00"
                and generated_fields["FFC1"] == "01",
                "generated state is not closed active scene $0B")

        legacy_state = output / "scene0b-native-closed-legacy-identity.ss0"
        changed_candidate_to_legacy = export_legacy_identity(
            generated_state, legacy_state, source_state
        )
        legacy_payload = gbas_payload(legacy_state)
        require(legacy_payload[4:8] == source_state[4:8]
                and legacy_payload[GBAS_TITLE_OFFSET:
                                   GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE]
                == source_state[GBAS_TITLE_OFFSET:
                                GBAS_TITLE_OFFSET + GBAS_TITLE_SIZE]
                and state_fields(legacy_payload) == generated_fields,
                "legacy export does not preserve generated machine state")

        tool_identity = {
            name: {"path": str(path.resolve()), "sha256": sha256(path.resolve())}
            for name, path in {
                "generator": Path(__file__),
                "probe": PROBE,
                "singleflight_launcher": LAUNCHER,
                "singleflight_implementation": SINGLEFLIGHT_IMPLEMENTATION,
                "emulator_binary": default_qt_emulator(),
                "state_retargeter": STATE_RETARGETER,
            }.items()
        }
        receipt = {
            "schema": SCHEMA,
            "status": "PASS",
            "candidate": str(candidate),
            "candidate_sha256": sha256(candidate),
            "candidate_crc32": f"{candidate_crc32:08x}",
            "candidate_rom_identity": candidate_identity.hex(),
            "source_capture": {
                "label": SOURCE_LABEL,
                "path": str(SOURCE.resolve()),
                "sha256": SOURCE_SHA256,
                "gbas_sha256": SOURCE_GBAS_SHA256,
                "serialized_rom_crc32": SOURCE_ROM_CRC32,
                "serialized_rom_identity": SOURCE_ROM_IDENTITY,
                "state": state_fields(source_state),
            },
            "identity_retarget": {
                "path": str(runtime_state.resolve()),
                "sha256": sha256(runtime_state),
                "gbas_sha256": sha256_bytes(retargeted_payload),
                "changed_gbAs_offsets": changed_source_to_runtime,
                "normalization_writes": 0,
                "machine_state_writes": 0,
            },
            "native_route": {
                "input": "SELECT-only",
                "initial_menu": "01",
                "final_menu": "00",
                "scene_values": ["0B"],
                "select_frames": int(report["select_frames"]),
                "closed_settle_frames": int(report["closed_settle_frames"]),
                "menu_open_events": int(report["menu_open_events"]),
                "menu_close_events": int(report["menu_close_events"]),
                "deferred_wram_frames": int(report["deferred_wram_frames"]),
                "gameplay_writes": 0,
                "fixture_writes": 0,
                "vram_injection_bytes": 0,
            },
            "generated_candidate_state": {
                "path": str(generated_state.resolve()),
                "sha256": sha256(generated_state),
                "gbas_sha256": sha256_bytes(generated_payload),
                "serialized_rom_crc32": f"{candidate_crc32:08x}",
                "serialized_rom_identity": candidate_identity.hex(),
                "state": generated_fields,
            },
            "exported_legacy_identity_state": {
                "path": str(legacy_state.resolve()),
                "sha256": sha256(legacy_state),
                "gbas_sha256": sha256_bytes(legacy_payload),
                "serialized_rom_crc32": SOURCE_ROM_CRC32,
                "serialized_rom_identity": SOURCE_ROM_IDENTITY,
                "state": state_fields(legacy_payload),
                "changed_gbAs_offsets": changed_candidate_to_legacy,
                "machine_state_writes": 0,
            },
            "screenshot": {
                "path": str(screenshot.resolve()),
                "sha256": sha256(screenshot),
            },
            "probe_report": {
                "path": str(report_path.resolve()),
                "sha256": sha256(report_path),
                "values": report,
            },
            "launch": {
                "command": command,
                "cwd": str(output),
                "startup_token_sha256": sha256_bytes(token.encode()),
                "started_at_ns": started_at_ns,
                "completed_at_ns": completed_at_ns,
                "completion_authenticated": True,
                **outcome,
            },
            "probe_contract": probe_contract,
            "tool_identity": tool_identity,
            "checks": {
                "exact compatible operator capture is authenticated": True,
                "source retarget changes identity metadata only": True,
                "native SELECT closes the menu without machine writes": True,
                "candidate-native state remains active scene $0B": True,
                "closed menu remains settled for sixty frames": True,
                "legacy export changes identity metadata only": True,
            },
            "process_check": run_process_check(),
            "failures": [],
        }
        (output / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
        print(
            "PASS: candidate-native closed scene-$0B capture "
            f"sha256={receipt['generated_candidate_state']['sha256']}"
        )
        return 0
    except (CaptureError, OSError, ValueError, subprocess.SubprocessError) as error:
        failure = {
            "schema": SCHEMA,
            "status": "NOT_READY",
            "candidate": str(candidate),
            "candidate_sha256": sha256(candidate),
            "failures": [str(error)],
            "process_check": run_process_check(),
        }
        (output / "receipt.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n"
        )
        print(f"FAIL: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
