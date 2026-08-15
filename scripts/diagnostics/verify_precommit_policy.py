#!/usr/bin/env python3
"""Require the right evidence for production versus harness-only commits.

Regression tests must be committable before the bug they expose is fixed.
Production inputs still require the hash-bound, fully passing emulator receipt.
Harness-only changes instead run deterministic contract/negative-control tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from suite_contract import ROOT
from verify_suite_receipt import FORBIDDEN_SUFFIXES, staged_paths


HARNESS_PREFIXES = (
    Path("scripts/diagnostics"),
    Path("scripts/probes"),
    Path("docs/audit"),
)
HARNESS_FILES = {
    Path(".githooks/pre-commit"),
    Path("CHANGELOG.md"),
}


def is_harness_path(path: Path) -> bool:
    return path in HARNESS_FILES or any(
        path == prefix or prefix in path.parents for prefix in HARNESS_PREFIXES
    )


def run(*command: str) -> int:
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    staged = staged_paths()
    forbidden = [path for path in staged if path.suffix.lower() in FORBIDDEN_SUFFIXES]
    if forbidden:
        print("FAIL: ROM/save/state artifacts are staged: " + ", ".join(map(str, forbidden)))
        return 1

    production = [path for path in staged if not is_harness_path(path)]
    if production:
        print(
            "Production inputs staged; requiring the full emulator receipt: "
            + ", ".join(map(str, production))
        )
        return run(
            sys.executable,
            str(ROOT / "scripts/diagnostics/verify_suite_receipt.py"),
            "--staged",
        )

    checks = (
        (sys.executable, "-m", "compileall", "-q", "scripts/diagnostics", "scripts/probes"),
        (sys.executable, "scripts/diagnostics/verify_live_regression.py", "--check-contract"),
        (
            sys.executable,
            "scripts/diagnostics/verify_ted_contract_controls.py",
            "--output",
            "tmp/precommit-ted-contract-controls.json",
        ),
    )
    for command in checks:
        if run(*command):
            return 1
    print(
        "PASS: harness-only commit passed compilation, inventory, and "
        "deterministic negative controls; production receipt not required."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
