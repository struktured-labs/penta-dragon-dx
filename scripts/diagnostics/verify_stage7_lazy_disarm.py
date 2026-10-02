#!/usr/bin/env python3
"""Live duplicate forced-path gate for the r279 Stage-7 lazy disarm."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from verify_stage_speed_matrix import stop_owned_process_group


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage7_lazy_disarm.lua"
LAUNCHER = ROOT / "scripts/mgba-qt-singleflight"
EXPECTED_ROM_SHA256 = (
    "649dab3b8895e680ff9e64005641de89b3ac1f66bcb417d6a1c42ce98bc30a9d"
)
EXPECTED_CASES = {
    "later-stage-d880": {
        "d880": "06", "ffba": "04", "classifier": "1",
        "disarm": "1", "native": "1", "dab7": "EB",
    },
    "later-stage-ffba": {
        "d880": "08", "ffba": "04", "classifier": "0",
        "disarm": "1", "native": "1", "dab7": "EB",
    },
    "death-retry": {
        "d880": "17", "ffba": "06", "classifier": "1",
        "disarm": "0", "native": "0", "dab7": "31",
    },
    "miniboss-return": {
        "d880": "0A", "ffba": "06", "classifier": "1",
        "disarm": "0", "native": "0", "dab7": "31",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def parse_probe(path: Path) -> dict[str, object]:
    lines = path.read_text().splitlines()
    require(len(lines) >= 4, "lazy-disarm probe output is truncated")
    require(lines[0] == "status\tmessage", "probe status header changed")
    status, message = lines[1].split("\t", 1)
    rows = list(csv.DictReader(lines[2:], delimiter="\t"))
    return {"status": status, "message": message, "rows": rows}


def run_one(candidate: Path, output: Path, timeout: float) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    report = output / "probe.tsv"
    marker = output / "DONE"
    log = output / "mgba.log"
    for path in (report, marker, log):
        path.unlink(missing_ok=True)
    for stale_save in sorted(output.glob("*.sav")):
        stale_save.unlink()
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE7_DISARM_OUT": str(report),
        "STAGE7_DISARM_DONE": str(marker),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    with log.open("w") as stream:
        process = subprocess.Popen(
            [
                "xvfb-run", "-a", str(LAUNCHER), "--fastforward",
                "-C", f"savegamePath={output}",
                "-C", f"savestatePath={output}",
                str(candidate), "--script", str(PROBE), "-l", "0",
            ],
            cwd=output,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if report.is_file() and marker.is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
        stop_owned_process_group(process)
    require(report.is_file() and marker.is_file(),
            f"lazy-disarm probe did not finish; see {log}")
    parsed = parse_probe(report)
    parsed["report_sha256"] = sha256(report)
    parsed["marker"] = marker.read_text().strip()
    parsed["marker_sha256"] = sha256(marker)
    parsed["log"] = str(log)
    return parsed


def validate_run(result: dict[str, object]) -> None:
    require(result["status"] == "PASS", f"probe status: {result}")
    require(result["marker"] == "PASS\tforced-lazy-disarm-matrix",
            "probe completion marker changed")
    rows = result["rows"]
    require(isinstance(rows, list) and len(rows) == len(EXPECTED_CASES),
            "probe case cardinality changed")
    by_name = {row["name"]: row for row in rows}
    require(set(by_name) == set(EXPECTED_CASES), "probe case names changed")
    for name, expected in EXPECTED_CASES.items():
        row = by_name[name]
        for key, value in expected.items():
            require(row[key] == value,
                    f"{name} {key}: {row[key]} != {value}")
        require(row["helper"] == "1", f"{name} missed bank22 helper")
        require(row["sp"] == "CFF8", f"{name} stack changed")
        require(row["bank"] == "16", f"{name} bank mapping changed")
        require(row["svbk"] == "01", f"{name} SVBK changed")
        require(row["bc"] == "3333" and row["de"] == "2222"
                and row["hl"] == "1111", f"{name} register restore changed")
        if expected["native"] == "1":
            require(row["native_sp"] == "CFF8",
                    f"{name} native epilogue did not consume saved frame")
            require(row["native_bc"] == "3333"
                    and row["native_de"] == "2222"
                    and row["native_hl"] == "1111",
                    f"{name} native epilogue register restore changed")
            require(row["native_pc"] == "1234",
                    f"{name} native RET target changed")
        else:
            require(all(row[key] == "NA" for key in (
                "native_sp", "native_bc", "native_de", "native_hl", "native_pc"
            )), f"{name} unexpectedly executed native epilogue")
        require(row["passed"] == "1", f"{name} live assertion failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "candidate", type=Path,
        nargs="?",
        default=ROOT / "tmp/stage7-lazy-disarm-r279/candidate.gb",
    )
    parser.add_argument(
        "--build-receipt", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/build-receipt.json",
    )
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "tmp/stage7-lazy-disarm-r279/live-disarm-r1",
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()
    candidate = args.candidate.resolve()
    output = args.output.resolve()
    require(candidate.is_file(), f"candidate missing: {candidate}")
    candidate_sha = sha256(candidate)
    require(candidate_sha == EXPECTED_ROM_SHA256,
            f"wrong exact r279 candidate: {candidate_sha}")
    build = json.loads(args.build_receipt.read_text())
    require(build.get("schema") == "penta-stage7-lazy-disarm-r279-build-v1",
            "wrong build receipt schema")
    require(build.get("candidate_sha256") == candidate_sha,
            "build receipt candidate mismatch")

    runs = [
        run_one(candidate, output / f"run-{label}", args.timeout)
        for label in ("a", "b")
    ]
    for result in runs:
        validate_run(result)
    semantic = lambda result: {
        "status": result["status"],
        "message": result["message"],
        "rows": result["rows"],
        "marker": result["marker"],
    }
    require(semantic(runs[0]) == semantic(runs[1]),
            "forced lazy-disarm replay mismatch")
    receipt = {
        "schema": "penta-stage7-lazy-disarm-live-v1",
        "status": "PASS",
        "promotable": False,
        "candidate_sha256": candidate_sha,
        "build_receipt": str(args.build_receipt.resolve()),
        "build_receipt_sha256": sha256(args.build_receipt),
        "probe": str(PROBE.resolve()),
        "probe_sha256": sha256(PROBE),
        "launcher": str(LAUNCHER.resolve()),
        "launcher_sha256": sha256(LAUNCHER),
        "duplicate_replay": True,
        "cases": runs[0]["rows"],
        "run_receipts": [
            {
                "report_sha256": result["report_sha256"],
                "marker_sha256": result["marker_sha256"],
                "log": result["log"],
            }
            for result in runs
        ],
        "contracts": {
            "both_runtime_tail_routes_reach_bank22": True,
            "D880_mismatch_with_new_FFBA_disarms": True,
            "D880_exact_with_new_FFBA_disarms": True,
            "death_retry_preserves_arm": True,
            "miniboss_return_preserves_arm": True,
            "disarmed_redirect_executes_DAA3_epilogue_and_RET": True,
            "native_epilogue_restores_HL_DE_BC_and_stack": True,
            "helper_entry_registers_and_stack_are_exact": True,
        },
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS: duplicate forced Stage-7 lazy-disarm matrix")
    print(f"Receipt: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
