#!/usr/bin/env python3
"""Verify the natural Stage-1 death/Continue selector-driven CHR reload.

The verifier first generates a fresh candidate-owned Stage-1 hazard state via
``generate_stage1_hazard_state.py``.  It then runs a dedicated observation
probe through the repository's fail-closed single-flight launcher.  The probe
holds neutral keys and performs exactly one gameplay-memory stimulus:
``DCBB := 0``.

Acceptance requires the exact bank1:$4AF2 -> $4AFB CALL fixed:$0C9C ->
bank1:$4AFE chain, all 2,048 ordered canonical bank-zero CHR writes, invariant
native selectors, safe serial state, no noncanonical post-return write, and
canonical final physical pages.  No caller-selected emulator path is exposed.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from typing import Any

sys.dont_write_bytecode = True

import verify_stage1_chr_writer as chr_contract


ROOT = Path(__file__).resolve().parents[2]
SELF = Path(__file__).resolve()
DIAGNOSTICS = SELF.parent
PROBE = DIAGNOSTICS / "probe_stage1_death_continue_chr_reload.lua"
STATE_GENERATOR = DIAGNOSTICS / "generate_stage1_hazard_state.py"
STATE_GENERATOR_PROBE = DIAGNOSTICS / "probe_stage1_north_integrity.lua"
CHR_WRITER_VERIFIER = DIAGNOSTICS / "verify_stage1_chr_writer.py"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
GUARD = ROOT / "scripts/mgba_singleflight.py"
PROCESS_CHECK = ROOT / "scripts/check_emulator_processes.sh"
REPO_TMP = ROOT / "tmp"
LARGE_TMP = Path("/mnt/data/tmp")

SCHEMA = "penta-stage1-death-continue-chr-reload-v1"
PROBE_SCHEMA = "penta-stage1-death-continue-chr-reload-probe-v1"
STATE_SCHEMA = "penta-stage1-hazard-state-v1"
NATURAL_SELECTORS = "1011121314151617"
PAGE_FIRST = 0x9000
PAGE_BYTES = 0x0800
CGB_ONLY_FLAG = 0xC0
CONTINUE_ROUTE_ADDRESS = 0x4AF2
CONTINUE_ROUTE = bytes.fromhex(
    "F0 DA B7 20 11 F3 31 FF DF CD 9C 0C CD C0 1E FB "
    "CD E4 41 C3 6C 01"
)
EXPECTED_ROUTE = (
    ("continue-check-4AF2", 0x4AF2),
    ("continue-call-4AFB", 0x4AFB),
    ("selector-loader-0C9C", 0x0C9C),
    ("continue-return-4AFE", 0x4AFE),
)
HEX_FIELDS = frozenset({
    "pc", "bank", "sp", "ret", "ffda", "ff01", "ff72", "ff73",
    "ff74", "sc", "ie", "address", "old", "new", "af", "bc",
    "de", "hl", "caller",
})
DECIMAL_FIELDS = frozenset({"index", "frame"})


class GateError(RuntimeError):
    """A fail-closed gate prerequisite or runtime contract failed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest(path: Path) -> str:
    require(path.is_file(), f"required file is missing: {path}")
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def file_identity(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": str(path.resolve()),
        "resolved_path": str(resolved),
        "size": resolved.stat().st_size,
        "sha256": digest(resolved),
    }


def resolved_mgba_qt() -> Path:
    # The launcher uses this exact deterministic order.  The verifier removes
    # the environment override before either guarded subprocess is started.
    for candidate in (
        Path("/home/struktured/bin/mgba-qt"),
        Path("/usr/bin/mgba-qt"),
        Path("/usr/local/bin/mgba-qt"),
    ):
        if candidate.is_file():
            return candidate.resolve(strict=True)
    raise GateError("single-flight launcher has no deterministic mGBA-Qt")


def tool_identities() -> dict[str, dict[str, Any]]:
    return {
        "python_interpreter": file_identity(Path(sys.executable)),
        "verifier": file_identity(SELF),
        "probe": file_identity(PROBE),
        "state_generator": file_identity(STATE_GENERATOR),
        "state_generator_probe": file_identity(STATE_GENERATOR_PROBE),
        "chr_writer_contract": file_identity(CHR_WRITER_VERIFIER),
        "singleflight_launcher": file_identity(LAUNCHER),
        "singleflight_guard": file_identity(GUARD),
        "mgba_qt": file_identity(resolved_mgba_qt()),
        "process_check": file_identity(PROCESS_CHECK),
    }


def scratch_output(path: Path) -> Path:
    resolved = path.resolve()
    allowed = [REPO_TMP.resolve()]
    if LARGE_TMP.is_dir() and os.access(LARGE_TMP, os.W_OK):
        allowed.append(LARGE_TMP.resolve())
    require(
        any(root in resolved.parents for root in allowed),
        "output must be a strict child of repository tmp/ or /mnt/data/tmp/",
    )
    require(not resolved.exists(), f"fresh output already exists: {resolved}")
    return resolved


def canonical_art(rom: bytes) -> bytes:
    pages = chr_contract.canonical_pages(rom)
    payload = b"".join(pages[address] for address in sorted(pages))
    require(len(payload) == PAGE_BYTES, "canonical Stage-1 page set is incomplete")
    return payload


def validate_candidate_contract(rom: bytes) -> dict[str, Any]:
    require(len(rom) == 512 * 1024, "candidate must be exactly 512 KiB")
    require(rom[0x0143] == CGB_ONLY_FLAG, "candidate is not CGB-only")
    chr_contract.validate_stock_loader(rom)
    actual = rom[
        CONTINUE_ROUTE_ADDRESS:
        CONTINUE_ROUTE_ADDRESS + len(CONTINUE_ROUTE)
    ]
    require(actual == CONTINUE_ROUTE, "bank1 death/Continue route changed")
    require(
        rom[0x4AFB:0x4AFE] == bytes.fromhex("CD 9C 0C"),
        "bank1:$4AFB no longer calls fixed:$0C9C",
    )
    pages = chr_contract.canonical_pages(rom)
    return {
        "rom_size": len(rom),
        "cgb_header_0143": rom[0x0143],
        "continue_route": "bank1:$4AF2-$4B08 exact",
        "selector_loader": "fixed:$0C9C-$0CB1 exact",
        "canonical_pages": {
            f"{address:04X}": digest_bytes(page)
            for address, page in sorted(pages.items())
        },
    }


def audit_probe_source(source: str) -> dict[str, Any]:
    require(
        # #41: the single stimulus goes through the physical-bank1 helper.
        source.count("emu:write8(") == 0
        and source.count("native_assistance.write(0x") == 1
        and "native_assistance.write(0xDCBB, 0)" in source,
        "probe must perform only the one DCBB-zero gameplay write",
    )
    set_keys = [
        line.strip() for line in source.splitlines()
        if "emu:setKeys(" in line
    ]
    require(
        len(set_keys) >= 2
        and all(line == "emu:setKeys(0)" for line in set_keys),
        "probe controller stimulus is not neutral-only",
    )
    for site in ("0x4AF2", "0x4AFB", "0x0C9C", "0x4AFE"):
        require(
            f"install_route_breakpoint({site}" in source,
            f"probe lacks exact route breakpoint {site}",
        )
    required = (
        "raw_vram:read8(address - 0x8000)",
        "PAGE_FIRST, PAGE_LAST, C.WATCHPOINT_TYPE.WRITE",
        "PAGE_LAST, C.WATCHPOINT_TYPE.WRITE",
        "for address = 0xFFA4, 0xFFAB do",
        "word((sp + 4) & 0xFFFF)",
        "emu:read8(0xFF02)",
        "emu:read8(0xFFFF)",
        "emu:read8(0xFF01)",
        "emu:read8(0xFF72)",
        "emu:read8(0xFF73)",
        "emu:read8(0xFF74)",
        "emu:read8(0xFF94) & 0x01",
        "assert(os.rename(temporary, OUT .. \"/report.txt\"))",
    )
    for snippet in required:
        require(snippet in source, f"probe lacks contract: {snippet}")
    for forbidden in (
        "writeRange", "memory:write", "emu:write16", "emu:write32",
        "PENTA_MGBA_QT_BIN",
    ):
        require(
            forbidden not in source,
            f"probe contains forbidden operation: {forbidden}",
        )
    return {
        "sha256": digest_bytes(source.encode()),
        "gameplay_memory_writes": 1,
        "gameplay_memory_write": "$DCBB=00",
        "controller_policy": "neutral-only",
        "bank0_vram_observation": "raw-vram-domain-only",
        "route_breakpoints": ["4AF2", "4AFB", "0C9C", "4AFE"],
        "selector_write_watchpoints": 8,
        "caller_stack_offset": 4,
    }


def load_json(path: Path, label: str) -> dict[str, Any]:
    require(path.is_file(), f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise GateError(f"invalid {label}: {error}") from error
    require(isinstance(value, dict), f"{label} is not a JSON object")
    return value


def parse_key_values(path: Path) -> dict[str, str]:
    require(path.is_file(), f"probe report is missing: {path}")
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        require("=" in line, f"malformed probe report line: {line!r}")
        key, value = line.split("=", 1)
        require(key and key not in result, f"duplicate probe report key: {key}")
        result[key] = value
    return result


def parse_tsv(path: Path, label: str) -> list[dict[str, Any]]:
    require(path.is_file(), f"{label} is missing: {path}")
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    result: list[dict[str, Any]] = []
    for position, raw in enumerate(rows, start=1):
        require(None not in raw and all(value is not None for value in raw.values()),
                f"malformed {label} row {position}")
        row: dict[str, Any] = dict(raw)
        try:
            for name in HEX_FIELDS & row.keys():
                row[name] = int(str(row[name]), 16)
            for name in DECIMAL_FIELDS & row.keys():
                row[name] = int(str(row[name]), 10)
        except ValueError as error:
            raise GateError(f"non-numeric {label} row {position}") from error
        result.append(row)
    return result


def integer_report(report: dict[str, str], name: str) -> int:
    try:
        value = int(report[name], 10)
    except (KeyError, ValueError) as error:
        raise GateError(f"probe report lacks integer {name}") from error
    return value


def grade_reload_evidence(
    *, canonical: bytes, preflight: bytes, final: bytes,
    route_rows: list[dict[str, Any]], chr_rows: list[dict[str, Any]],
    selector_rows: list[dict[str, Any]], report: dict[str, str],
) -> dict[str, Any]:
    """Independently re-grade every acceptance property from raw artifacts."""

    loader_rows = [row for row in chr_rows if row.get("phase") == "loader"]
    preloader_rows = [row for row in chr_rows if row.get("phase") == "preloader"]
    postreturn_rows = [
        row for row in chr_rows if row.get("phase") == "postreturn"
    ]
    phase_partition_exact = (
        len(preloader_rows) + len(loader_rows) + len(postreturn_rows)
        == len(chr_rows)
    )
    route_exact = (
        len(route_rows) == len(EXPECTED_ROUTE)
        and all(
            row.get("index") == index
            and row.get("kind") == kind
            and row.get("pc") == pc
            and row.get("bank") == 0x01
            for index, (row, (kind, pc)) in enumerate(
                zip(route_rows, EXPECTED_ROUTE, strict=True), start=1
            )
        )
        and all(
            earlier.get("frame", -1) <= later.get("frame", -1)
            for earlier, later in zip(route_rows, route_rows[1:])
        )
    )
    rooted_stack_exact = (
        route_exact
        and route_rows[1].get("sp") == 0xDFFF
        and route_rows[2].get("sp") == 0xDFFD
        and route_rows[2].get("ret") == 0x4AFE
        and route_rows[3].get("sp") == 0xDFFF
    )
    route_state_exact = bool(route_rows) and all(
        row.get("selectors") == NATURAL_SELECTORS
        and row.get("ffda") == 0
        and row.get("sc", 0x80) & 0x80 == 0
        and row.get("ie", 0x08) & 0x08 == 0
        for row in route_rows
    )

    loader_sequence_exact = len(loader_rows) == PAGE_BYTES and all(
        row.get("address") == PAGE_FIRST + offset
        and row.get("new") == canonical[offset]
        and row.get("pc") == (0x0D47 if offset & 1 == 0 else 0x0D4A)
        and row.get("bank") == 0x07
        and row.get("de") == PAGE_FIRST + offset
        and row.get("hl") == 0x5001 + offset
        and row.get("caller") == 0x0CAC
        and row.get("selectors") == NATURAL_SELECTORS
        and row.get("ffda") == 0
        and row.get("sc", 0x80) & 0x80 == 0
        and row.get("ie", 0x08) & 0x08 == 0
        for offset, row in enumerate(loader_rows)
    )
    postreturn_exact = all(
        PAGE_FIRST <= row.get("address", 0) < PAGE_FIRST + PAGE_BYTES
        and row.get("new") == canonical[row["address"] - PAGE_FIRST]
        and row.get("selectors") == NATURAL_SELECTORS
        and row.get("sc", 0x80) & 0x80 == 0
        and row.get("ie", 0x08) & 0x08 == 0
        for row in postreturn_rows
    )

    try:
        report_counts_match = (
            integer_report(report, "chr_event_count") == len(chr_rows)
            and integer_report(report, "preloader_write_count")
            == len(preloader_rows)
            and integer_report(report, "loader_write_count") == len(loader_rows)
            and integer_report(report, "postreturn_write_count")
            == len(postreturn_rows)
            and integer_report(report, "route_event_count") == len(route_rows)
            and integer_report(report, "selector_watch_writes")
            == len(selector_rows)
            and phase_partition_exact
        )
        report_contract = (
            report.get("schema") == PROBE_SCHEMA
            and report.get("status") == "pass"
            and report.get("reason") == "complete"
            and integer_report(report, "state_loaded") == 1
            and integer_report(report, "preflight_done") == 1
            and integer_report(report, "stimulus_writes") == 1
            and integer_report(report, "loader_entries") == 1
            and integer_report(report, "chr_event_dropped") == 0
            and integer_report(report, "postreturn_bad_write_count") == 0
            and integer_report(report, "selector_frame_violations") == 0
            and integer_report(report, "serial_sc_busy_samples") == 0
            and integer_report(report, "serial_ie_enabled_samples") == 0
            and integer_report(report, "preflight_mismatches") == 0
            and integer_report(report, "final_mismatches") == 0
            and integer_report(report, "death_scene_frames") > 0
            and report.get("final_selectors") == NATURAL_SELECTORS
        )
    except GateError:
        report_counts_match = False
        report_contract = False

    checks = {
        "preflight physical bank-zero pages are canonical": (
            len(preflight) == PAGE_BYTES and preflight == canonical
        ),
        "exact Continue loader root and return stack are observed": (
            route_exact and rooted_stack_exact
        ),
        "selectors FFDA SC and IE are safe at every route boundary": (
            route_state_exact
        ),
        "exactly 0x800 ordered bank7 canonical writes have stock ownership": (
            loader_sequence_exact
        ),
        "native selector array has no observed write": not selector_rows,
        "no noncanonical CHR write occurs after the Continue return": (
            postreturn_exact
        ),
        "final physical bank-zero pages are canonical": (
            len(final) == PAGE_BYTES and final == canonical
        ),
        "probe counters exactly match raw artifacts": report_counts_match,
        "probe reports one neutral DCBB death and complete reload": report_contract,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "counts": {
            "route_events": len(route_rows),
            "preloader_writes": len(preloader_rows),
            "loader_writes": len(loader_rows),
            "postreturn_writes": len(postreturn_rows),
            "selector_writes": len(selector_rows),
        },
        "preflight_sha256": digest_bytes(preflight),
        "final_sha256": digest_bytes(final),
        "canonical_sha256": digest_bytes(canonical),
    }


def synthetic_good_evidence() -> dict[str, Any]:
    canonical = bytes(range(256)) * 8
    route_rows: list[dict[str, Any]] = []
    for index, (kind, pc) in enumerate(EXPECTED_ROUTE, start=1):
        route_rows.append({
            "index": index,
            "frame": 100 + index,
            "kind": kind,
            "pc": pc,
            "bank": 1,
            "sp": 0xDFFF if index != 3 else 0xDFFD,
            "ret": 0x4AFE if index == 3 else 0,
            "selectors": NATURAL_SELECTORS,
            "ffda": 0,
            "sc": 0,
            "ie": 7,
        })
    chr_rows = []
    for offset, value in enumerate(canonical):
        chr_rows.append({
            "index": offset + 1,
            "phase": "loader",
            "frame": 103,
            "address": PAGE_FIRST + offset,
            "new": value,
            "pc": 0x0D47 if offset & 1 == 0 else 0x0D4A,
            "bank": 7,
            "de": PAGE_FIRST + offset,
            "hl": 0x5001 + offset,
            "caller": 0x0CAC,
            "selectors": NATURAL_SELECTORS,
            "ffda": 0,
            "sc": 0,
            "ie": 7,
        })
    report = {
        "schema": PROBE_SCHEMA,
        "status": "pass",
        "reason": "complete",
        "state_loaded": "1",
        "preflight_done": "1",
        "stimulus_writes": "1",
        "loader_entries": "1",
        "chr_event_count": str(PAGE_BYTES),
        "chr_event_dropped": "0",
        "preloader_write_count": "0",
        "loader_write_count": str(PAGE_BYTES),
        "postreturn_write_count": "0",
        "postreturn_bad_write_count": "0",
        "route_event_count": "4",
        "selector_watch_writes": "0",
        "selector_frame_violations": "0",
        "serial_sc_busy_samples": "0",
        "serial_ie_enabled_samples": "0",
        "preflight_mismatches": "0",
        "final_mismatches": "0",
        "death_scene_frames": "1",
        "final_selectors": NATURAL_SELECTORS,
    }
    return {
        "canonical": canonical,
        "preflight": canonical,
        "final": canonical,
        "route_rows": route_rows,
        "chr_rows": chr_rows,
        "selector_rows": [],
        "report": report,
    }


def mutation_controls() -> dict[str, bool]:
    good = synthetic_good_evidence()

    def accepted(evidence: dict[str, Any]) -> bool:
        return bool(grade_reload_evidence(**evidence)["passed"])

    controls: dict[str, bool] = {"good_control_passes": accepted(good)}
    mutations: dict[str, Any] = {}

    wrong_root = copy.deepcopy(good)
    wrong_root["route_rows"][2]["ret"] = 0x4AFF
    mutations["foreign_loader_root_rejected"] = wrong_root

    reordered = copy.deepcopy(good)
    reordered["chr_rows"][10], reordered["chr_rows"][11] = (
        reordered["chr_rows"][11], reordered["chr_rows"][10]
    )
    mutations["reordered_write_rejected"] = reordered

    bad_byte = copy.deepcopy(good)
    bad_byte["chr_rows"][0x105]["new"] ^= 0xFF
    mutations["noncanonical_loader_byte_rejected"] = bad_byte

    wrong_owner = copy.deepcopy(good)
    wrong_owner["chr_rows"][0]["caller"] = 0x0CAD
    mutations["wrong_stock_caller_rejected"] = wrong_owner

    wrong_bank = copy.deepcopy(good)
    wrong_bank["chr_rows"][0]["bank"] = 0x0E
    mutations["wrong_source_bank_rejected"] = wrong_bank

    mutated_selector = copy.deepcopy(good)
    mutated_selector["chr_rows"][0]["selectors"] = "1000121314151617"
    mutations["mutated_selector_rejected"] = mutated_selector

    selector_write = copy.deepcopy(good)
    selector_write["selector_rows"] = [{"address": 0xFFA5}]
    selector_write["report"]["selector_watch_writes"] = "1"
    mutations["selector_write_rejected"] = selector_write

    bad_postreturn = copy.deepcopy(good)
    bad_postreturn["chr_rows"].append({
        "phase": "postreturn", "address": PAGE_FIRST + 2,
        "new": good["canonical"][2] ^ 0xFF,
        "selectors": NATURAL_SELECTORS, "sc": 0, "ie": 7,
    })
    bad_postreturn["report"]["chr_event_count"] = str(PAGE_BYTES + 1)
    bad_postreturn["report"]["postreturn_write_count"] = "1"
    bad_postreturn["report"]["postreturn_bad_write_count"] = "1"
    mutations["bad_postreturn_write_rejected"] = bad_postreturn

    bad_final = copy.deepcopy(good)
    final = bytearray(bad_final["final"])
    final[0x100] ^= 0xFF
    bad_final["final"] = bytes(final)
    mutations["bad_final_page_rejected"] = bad_final

    serial_busy = copy.deepcopy(good)
    serial_busy["route_rows"][1]["sc"] = 0x80
    mutations["active_serial_transfer_rejected"] = serial_busy

    serial_irq = copy.deepcopy(good)
    serial_irq["chr_rows"][100]["ie"] |= 0x08
    mutations["enabled_serial_irq_rejected"] = serial_irq

    foreign_entry = copy.deepcopy(good)
    foreign_entry["report"]["loader_entries"] = "2"
    mutations["second_loader_entry_rejected"] = foreign_entry

    unknown_phase = copy.deepcopy(good)
    unknown_phase["chr_rows"][0]["phase"] = "unclassified"
    unknown_phase["report"]["loader_write_count"] = str(PAGE_BYTES - 1)
    mutations["unclassified_chr_write_rejected"] = unknown_phase

    for name, evidence in mutations.items():
        controls[name] = not accepted(evidence)
    return controls


def read_only_process_check(log: Path) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [str(PROCESS_CHECK)], cwd=ROOT, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=10.0, check=False,
        )
        output = completed.stdout.decode(errors="replace")
        log.write_text(output)
        return {"exit_status": completed.returncode, "output": output}
    except (OSError, subprocess.SubprocessError) as error:
        log.write_text(f"process check failed: {error}\n")
        return {"exit_status": -1, "output": str(error)}


def run_logged(
    command: list[str], *, cwd: Path, environment: dict[str, str],
    log: Path, timeout: float,
) -> dict[str, Any]:
    started_ns = time.time_ns()
    try:
        with log.open("wb") as stream:
            completed = subprocess.run(
                command, cwd=cwd, env=environment, stdout=stream,
                stderr=subprocess.STDOUT, timeout=timeout, check=False,
            )
    except subprocess.TimeoutExpired as error:
        process = read_only_process_check(log.with_suffix(".process-check.log"))
        raise GateError(
            f"guarded command timed out after {timeout:.1f}s; "
            f"process check exit {process['exit_status']}"
        ) from error
    completed_ns = time.time_ns()
    return {
        "command": command,
        "cwd": str(cwd.resolve()),
        "timeout_seconds": timeout,
        "exit_status": completed.returncode,
        "log": str(log.resolve()),
        "log_sha256": digest(log),
        "started_at_ns": started_ns,
        "completed_at_ns": completed_ns,
        "elapsed_ns": completed_ns - started_ns,
    }


def validate_generated_state(
    receipt_path: Path, state: Path, candidate: Path, candidate_sha256: str,
) -> dict[str, Any]:
    receipt = load_json(receipt_path, "generated Stage-1 state receipt")
    require(receipt.get("schema") == STATE_SCHEMA, "wrong state receipt schema")
    require(receipt.get("passed") is True, "generated Stage-1 state did not pass")
    require(receipt.get("rom_sha256") == candidate_sha256,
            "generated state targets another candidate")
    require(Path(str(receipt.get("rom"))).resolve() == candidate.resolve(),
            "generated state receipt names another candidate path")
    require(receipt.get("state_sha256") == digest(state),
            "generated state hash differs from its receipt")
    require(Path(str(receipt.get("state"))).resolve() == state.resolve(),
            "generated state receipt names another state path")
    require(receipt.get("target_camera") == 0x015C,
            "generated state target camera changed")
    require(receipt.get("target_settle") == 20,
            "generated state settle contract changed")
    require(receipt.get("fire") is False,
            "generated state unexpectedly used fire input")
    require(receipt.get("minimum_hazard_cells") == 40
            and receipt.get("minimum_tooth_cells") == 10,
            "generated state coverage minima changed")
    require(receipt.get("hazard_cells", 0) >= 40
            and receipt.get("tooth_cells", 0) >= 10,
            "generated state lacks hazard/tooth coverage")
    hardware = receipt.get("hardware")
    require(
        isinstance(hardware, dict)
        and hardware.get("settled") is True
        and hardware.get("hdma5") == 0xFF
        and hardware.get("vbk") == 0
        and hardware.get("svbk") == 1
        and int(hardware.get("lcdc", 0)) & 0x80 != 0,
        "generated state hardware is not settled",
    )
    require(digest(candidate) == candidate_sha256,
            "candidate changed while the state was generated")
    return {
        "receipt": str(receipt_path.resolve()),
        "receipt_sha256": digest(receipt_path),
        "state": str(state.resolve()),
        "state_sha256": digest(state),
        "hazard_cells": receipt["hazard_cells"],
        "tooth_cells": receipt["tooth_cells"],
        "hardware": hardware,
    }


def run_gate(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    candidate = args.rom.resolve()
    require(candidate.is_file(), f"candidate ROM is missing: {candidate}")
    output = scratch_output(args.output)
    output.mkdir(parents=True)
    candidate_bytes = candidate.read_bytes()
    candidate_sha256 = digest_bytes(candidate_bytes)
    receipt_path = output / "receipt.json"
    receipt: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "FAIL",
        "candidate": str(candidate),
        "candidate_sha256": candidate_sha256,
        "output": str(output),
        "failures": [],
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    try:
        candidate_contract = validate_candidate_contract(candidate_bytes)
        probe_contract = audit_probe_source(PROBE.read_text())
        controls = mutation_controls()
        require(all(controls.values()), f"mutation controls failed: {controls}")
        tools_before = tool_identities()
        environment = os.environ.copy()
        for name in tuple(environment):
            if name.startswith(("STAGE1_NORTH_", "PENTA_DEATH_RELOAD_")):
                environment.pop(name)
        for name in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
            environment.pop(name, None)
        environment.update({
            "QT_QPA_PLATFORM": "offscreen",
            "SDL_AUDIODRIVER": "dummy",
        })
        environment.pop("DISPLAY", None)
        environment.pop("WAYLAND_DISPLAY", None)

        state_output = output / "generated-state"
        state_command = [
            sys.executable, str(STATE_GENERATOR), str(candidate),
            "--output", str(state_output),
            "--timeout", str(args.state_timeout),
            "--target-camera", "0x015C",
            "--target-settle", "20",
            "--min-hazard-cells", "40",
            "--min-tooth-cells", "10",
        ]
        state_run = run_logged(
            state_command, cwd=ROOT, environment=environment,
            log=output / "state-generator.log",
            timeout=args.state_timeout + 15.0,
        )
        require(state_run["exit_status"] == 0,
                "fresh Stage-1 state generator failed")
        state = state_output / "stage1-hazard.ss0"
        state_receipt = state_output / "receipt.json"
        state_evidence = validate_generated_state(
            state_receipt, state, candidate, candidate_sha256,
        )

        runtime = output / "runtime"
        probe_output = output / "probe"
        runtime.mkdir()
        probe_output.mkdir()
        runtime_rom = runtime / "candidate.gb"
        runtime_state = runtime / "input.ss0"
        shutil.copy2(candidate, runtime_rom)
        shutil.copy2(state, runtime_state)
        canonical = canonical_art(candidate_bytes)
        canonical_path = runtime / "canonical-stage1-bank0.bin"
        canonical_path.write_bytes(canonical)
        require(digest(runtime_rom) == candidate_sha256,
                "isolated runtime ROM differs from the candidate")
        runtime_state_sha256 = digest(runtime_state)
        require(runtime_state_sha256 == state_evidence["state_sha256"],
                "isolated runtime state differs from generated state")

        startup_token = secrets.token_hex(32)
        replay_environment = dict(environment)
        replay_environment.update({
            "PENTA_DEATH_RELOAD_OUT": str(probe_output),
            "PENTA_DEATH_RELOAD_STATE": str(runtime_state),
            "PENTA_DEATH_RELOAD_CANONICAL": str(canonical_path),
            "PENTA_DEATH_RELOAD_STARTUP_TOKEN": startup_token,
            "PENTA_DEATH_RELOAD_ROM_SHA256": candidate_sha256,
            "PENTA_DEATH_RELOAD_FRAME_LIMIT": str(args.frame_limit),
            "PENTA_DEATH_RELOAD_STIMULUS_FRAME": str(args.stimulus_frame),
            "PENTA_DEATH_RELOAD_POSTRETURN_FRAMES": str(args.postreturn_frames),
        })
        replay_command = [
            str(LAUNCHER), "--fastforward",
            "-C", f"savegamePath={runtime}",
            "-C", f"savestatePath={runtime}",
            str(runtime_rom), "--script", str(PROBE),
        ]
        replay_run = run_logged(
            replay_command, cwd=runtime, environment=replay_environment,
            log=output / "replay.log", timeout=args.replay_timeout,
        )

        marker = probe_output / "complete.marker"
        report_path = probe_output / "report.txt"
        require(marker.is_file(), "probe completion marker is missing")
        marker_lines = marker.read_text().splitlines()
        require(marker_lines and marker_lines[0] == startup_token,
                "probe completion marker token differs")
        report = parse_key_values(report_path)
        require(report.get("startup_token") == startup_token,
                "probe report token differs")
        require(report.get("expected_rom_sha256") == candidate_sha256,
                "probe report names another candidate")

        preflight_path = probe_output / "preflight-bank0-9000-97ff.bin"
        final_path = probe_output / "final-bank0-9000-97ff.bin"
        route_path = probe_output / "route.tsv"
        chr_path = probe_output / "chr-writes.tsv"
        selector_path = probe_output / "selector-writes.tsv"
        preflight = preflight_path.read_bytes()
        final = final_path.read_bytes()
        route_rows = parse_tsv(route_path, "Continue route trace")
        chr_rows = parse_tsv(chr_path, "CHR write trace")
        selector_rows = parse_tsv(selector_path, "selector write trace")
        grade = grade_reload_evidence(
            canonical=canonical, preflight=preflight, final=final,
            route_rows=route_rows, chr_rows=chr_rows,
            selector_rows=selector_rows, report=report,
        )

        tools_after = tool_identities()
        provenance_checks = {
            "guarded replay exited successfully": replay_run["exit_status"] == 0,
            "authenticated completion status is pass": (
                marker_lines == [startup_token, "pass"]
            ),
            "source candidate remained exact": digest(candidate) == candidate_sha256,
            "tested runtime ROM is exact": digest(runtime_rom) == candidate_sha256,
            "generated source state remained exact": (
                digest(state) == state_evidence["state_sha256"]
            ),
            "tested runtime state remained exact": (
                digest(runtime_state) == runtime_state_sha256
            ),
            "canonical source artifact remained exact": (
                digest(canonical_path) == digest_bytes(canonical)
            ),
            "all tool identities remained exact": tools_after == tools_before,
            "fresh output path owns every runtime artifact": all(
                output in path.resolve().parents
                for path in (
                    state, state_receipt, runtime_rom, runtime_state,
                    canonical_path, report_path, marker, route_path,
                    chr_path, selector_path, preflight_path, final_path,
                )
            ),
        }
        passed = grade["passed"] and all(provenance_checks.values())
        receipt.update({
            "status": "PASS" if passed else "FAIL",
            "candidate_contract": candidate_contract,
            "probe_contract": probe_contract,
            "mutation_controls": controls,
            "state_generation": {**state_run, **state_evidence},
            "replay": replay_run,
            "tested_runtime_rom": str(runtime_rom.resolve()),
            "tested_runtime_rom_sha256": digest(runtime_rom),
            "tested_runtime_state": str(runtime_state.resolve()),
            "tested_runtime_state_sha256": runtime_state_sha256,
            "canonical_art": {
                "path": str(canonical_path.resolve()),
                "sha256": digest(canonical_path),
                "physical_range": "$9000-$97FF VBK0",
                "rom_range": "file 0x1D000-0x1D7FF (bank7:$5000-$57FF)",
            },
            "artifacts": {
                str(path.name): {
                    "path": str(path.resolve()), "sha256": digest(path),
                }
                for path in (
                    report_path, marker, route_path, chr_path, selector_path,
                    probe_output / "latch-serial-trace.tsv",
                    preflight_path, final_path,
                )
            },
            "grade": grade,
            "provenance_checks": provenance_checks,
            "tool_identities": tools_before,
            "coverage_limits": {
                "route": (
                    "one fresh room-$01 camera-$015C Stage-1 state and one "
                    "neutral-key DCBB-zero death/Continue transition"
                ),
                "latches": (
                    "FF01/FF72/FF73/FF74 are traced at frame changes, route "
                    "breakpoints, and every loader write; this route does not "
                    "claim to execute every producer/consumer role"
                ),
                "serial": (
                    "SC.bit7 and IE.bit3 are sampled each frame, at every "
                    "route boundary, and at every loader/postreturn CHR write"
                ),
                "input": "neutral keys only; no A/Start pulse is synthesized",
                "continue_liveness": (
                    "stock bank1:$4A9D tests FF94.bit0 before branching to "
                    "$4AD4->$4AF2; the probe rejects a latent preflight A edge "
                    "and therefore may time out unless neutral execution has "
                    "another route established by live evidence"
                ),
                "hardware": "mGBA evidence; Analogue Pocket remains separate",
            },
            "failures": [
                name for name, ok in {
                    **grade["checks"], **provenance_checks,
                }.items() if not ok
            ],
        })
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
        return (0 if passed else 1), receipt
    except (GateError, OSError, KeyError, TypeError, ValueError,
            subprocess.SubprocessError) as error:
        receipt["status"] = "FAIL"
        receipt["failures"] = [str(error)]
        receipt_path.write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n"
        )
        return 1, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path, nargs="?")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--state-timeout", type=float, default=90.0)
    parser.add_argument("--replay-timeout", type=float, default=180.0)
    parser.add_argument("--frame-limit", type=int, default=1800)
    parser.add_argument("--stimulus-frame", type=int, default=30)
    parser.add_argument("--postreturn-frames", type=int, default=60)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    try:
        probe_contract = audit_probe_source(PROBE.read_text())
        controls = mutation_controls()
        require(all(controls.values()), f"mutation controls failed: {controls}")
    except (GateError, OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1
    if args.self_test:
        print(json.dumps({
            "status": "PASS",
            "emulator_run": False,
            "probe_contract": probe_contract,
            "mutation_controls": controls,
        }, indent=2, sort_keys=True))
        return 0
    if args.rom is None or args.output is None:
        parser.error("ROM and --output are required outside --self-test")
    if args.state_timeout <= 10 or args.replay_timeout <= 10:
        parser.error("timeouts must be greater than ten seconds")
    if args.frame_limit < 300:
        parser.error("--frame-limit must be at least 300")
    if not 1 <= args.stimulus_frame < args.frame_limit:
        parser.error("--stimulus-frame must be inside the replay")
    if not 1 <= args.postreturn_frames < args.frame_limit:
        parser.error("--postreturn-frames must be inside the replay")

    exit_status, receipt = run_gate(args)
    if exit_status == 0:
        print("PASS: natural Stage-1 death/Continue CHR reload is exact")
    else:
        print("FAIL: natural Stage-1 death/Continue CHR reload gate")
        for failure in receipt.get("failures", []):
            print(f"  - {failure}")
    print(f"Receipt: {Path(args.output).resolve() / 'receipt.json'}")
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
