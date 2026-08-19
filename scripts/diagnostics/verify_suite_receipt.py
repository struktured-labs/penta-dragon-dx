#!/usr/bin/env python3
"""Fast pre-commit validation of the latest full-suite receipt."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from suite_contract import (
    DEFAULT_RECEIPT,
    ROOT,
    SCHEMA,
    source_paths,
    source_snapshot,
)

sys.path.insert(0, str(ROOT / "scripts/diagnostics"))
from verify_release_candidate import build_gates
from suite_release_ledger import validate_release_ledger


FORBIDDEN_SUFFIXES = {
    ".gb",
    ".gbc",
    ".gba",
    ".sav",
    ".ram",
    ".ss",
    ".ss0",
    ".ss1",
    ".ss2",
    ".ss3",
    ".ss4",
}


def fail(message: str) -> int:
    print(f"FAIL: {message}")
    return 1


def git_paths(arguments: list[str]) -> list[Path]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "could not inspect index")
    return [Path(line) for line in result.stdout.splitlines() if line]


def staged_paths() -> list[Path]:
    return git_paths(
        ["diff", "--cached", "--name-only", "--diff-filter=ACMR"]
    )


def verify_index_matches_receipt_inputs(receipt_path: Path) -> int:
    """Require the pending commit to contain the exact verified source."""

    bound = {
        path.relative_to(ROOT)
        for path in source_paths()
    }
    unstaged = set(
        git_paths(["diff", "--name-only", "--diff-filter=ACMR"])
    )
    untracked = set(
        git_paths(["ls-files", "--others", "--exclude-standard"])
    )
    missing_from_index = sorted(bound & (unstaged | untracked))
    if missing_from_index:
        return fail(
            "receipt-bound suite inputs are not staged exactly: "
            + ", ".join(str(path) for path in missing_from_index)
        )

    receipt_relative = receipt_path.relative_to(ROOT)
    if receipt_relative in unstaged:
        return fail(
            f"verified receipt has unstaged changes: {receipt_relative}"
        )
    indexed = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(receipt_relative)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if indexed.returncode != 0:
        return fail(
            f"verified receipt is absent from the pending commit: "
            f"{receipt_relative}"
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="also reject staged ROM/save/state artifacts",
    )
    args = parser.parse_args()

    receipt_path = args.receipt.resolve()
    if not receipt_path.is_file():
        return fail(
            f"full-suite receipt missing: {receipt_path}; run "
            "scripts/diagnostics/run_deterministic_suite.py"
        )
    try:
        receipt = json.loads(receipt_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return fail(f"receipt is unreadable: {exc}")

    if receipt.get("schema") != SCHEMA or receipt.get("status") != "passed":
        return fail("receipt schema/status is not a full deterministic pass")
    fingerprint, inputs = source_snapshot()
    if receipt.get("source_fingerprint") != fingerprint:
        return fail(
            "suite inputs changed after the full run; rerun "
            "scripts/diagnostics/run_deterministic_suite.py"
        )
    if receipt.get("source_inputs") != inputs:
        return fail("receipt source file inventory does not match the checkout")

    build = receipt.get("deterministic_build", {})
    candidate = receipt.get("candidate", {})
    profile = receipt.get("build_profile", {})
    expanded = profile.get("expanded_ted") is True
    menu_icons = profile.get("menu_icon_colors") is True
    expected_size = 524288 if expanded else 262144
    if (
        build.get("passes") != 2
        or build.get("byte_identical") is not True
        or build.get("build_a_sha256") != candidate.get("sha256")
        or build.get("build_b_sha256") != candidate.get("sha256")
        or candidate.get("size") != expected_size
    ):
        return fail(
            "receipt does not prove two byte-identical builds for its profile"
        )
    if menu_icons and not expanded:
        return fail("receipt enables menu icons without the expanded profile")
    if expanded and (
        profile.get("native_sparse") is not True
        or profile.get("native_pose_table") is not True
    ):
        return fail("expanded receipt omits native Ted sparse/pose controls")

    expected_names = [
        gate.name
        for gate in build_gates(
            ROOT / "tmp" / "receipt-candidate.gb",
            ROOT / "tmp" / "receipt-artifacts",
            expanded_candidate_override=expanded,
            menu_icon_candidate_override=menu_icons,
        )
    ]
    matrix = receipt.get("matrix", {})
    results = matrix.get("results", [])
    names = [
        result.get("name") for result in results if isinstance(result, dict)
    ]
    if (
        matrix.get("status") != "emulator-pass"
        or matrix.get("scope") != "full"
        or matrix.get("failures") != 0
        or matrix.get("gate_count") != len(expected_names)
        or names != expected_names
    ):
        return fail("receipt gate inventory is not the current full matrix")
    failed = [
        result.get("name")
        for result in results
        if result.get("status") != "passed"
        or result.get("returncode") != 0
    ]
    if failed:
        return fail(f"receipt contains non-passing gates: {failed}")

    ledger_errors = validate_release_ledger(
        receipt.get("release_ledger"), expanded=expanded
    )
    if ledger_errors:
        return fail("invalid release exception ledger: " + "; ".join(ledger_errors))

    if args.staged:
        try:
            staged = staged_paths()
        except RuntimeError as exc:
            return fail(str(exc))
        forbidden = [
            str(path)
            for path in staged
            if path.suffix.lower() in FORBIDDEN_SUFFIXES
        ]
        if forbidden:
            return fail(
                "ROM/save/state artifacts are staged: "
                + ", ".join(forbidden)
            )
        index_status = verify_index_matches_receipt_inputs(receipt_path)
        if index_status:
            return index_status

    print(
        f"PASS: receipt binds {len(expected_names)} serial gates to "
        f"source {fingerprint[:12]} and candidate "
        f"{candidate.get('sha256', '')[:12]}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
