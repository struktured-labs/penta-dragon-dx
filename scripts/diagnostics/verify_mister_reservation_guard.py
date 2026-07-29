#!/usr/bin/env python3
"""Verify that repository MiSTer tooling fails closed before hardware access."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
MISTER_SCRIPT = ROOT / "scripts/mister.py"


def run_cli(*arguments: str, environment: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(MISTER_SCRIPT), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def clean_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.pop("MISTER_RESERVATION_ID", None)
    environment.pop("MISTER_RESERVATION_CHECKER", None)
    environment["MISTER_HOST"] = "reservation-guard.invalid"
    return environment


def verify_low_level_guard() -> None:
    spec = importlib.util.spec_from_file_location("penta_mister_guard_test", MISTER_SCRIPT)
    require(spec is not None and spec.loader is not None, "could not load scripts/mister.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with mock.patch.dict(os.environ, {}, clear=True):
        with mock.patch.object(
            module.subprocess,
            "run",
            side_effect=AssertionError("network subprocess reached"),
        ) as runner:
            try:
                module.ssh("true")
            except module.ReservationError:
                pass
            else:
                raise AssertionError("ssh() accepted a missing reservation")
            require(not runner.called, "ssh() reached subprocess before reservation validation")

    checker_calls = 0

    def accept_checker(command, **_kwargs):
        nonlocal checker_calls
        require(
            command == ["reservation-checker-test"],
            f"unexpected checker command: {command!r}",
        )
        checker_calls += 1
        return subprocess.CompletedProcess(command, 0, "", "")

    with mock.patch.dict(
        os.environ,
        {
            "MISTER_RESERVATION_ID": "active-test-lease",
            "MISTER_RESERVATION_CHECKER": "reservation-checker-test",
        },
        clear=True,
    ):
        with mock.patch.object(module.subprocess, "run", side_effect=accept_checker):
            module.require_mister_reservation()
            module.require_mister_reservation()
    require(
        checker_calls == 2,
        "reservation result was cached instead of revalidated at each boundary",
    )


def main() -> int:
    environment = clean_environment()

    blocked = run_cli("status", environment=environment)
    require(blocked.returncode == 2, f"unguarded status exit was {blocked.returncode}")
    require(
        "RESERVATION BLOCKED:" in blocked.stderr,
        "unguarded status did not report the reservation block",
    )
    require(
        "MiSTer Status:" not in blocked.stdout,
        "status handler started before the reservation preflight",
    )

    local_only = run_cli("cheats", "list", environment=environment)
    require(local_only.returncode == 0, "local-only cheat listing was incorrectly blocked")
    require(
        "Available cheats for Penta Dragon DX:" in local_only.stdout,
        "local-only cheat listing did not run",
    )

    with tempfile.TemporaryDirectory(prefix="penta-mister-reservation-") as temp_dir:
        checker = Path(temp_dir) / "checker.sh"
        checker.write_text(
            "#!/bin/sh\n"
            "[ \"$MISTER_RESERVATION_ID\" = active-test-lease ] && "
            "[ \"$MISTER_RESERVATION_HOST\" = reservation-guard.invalid ] && "
            "exit 0\n"
            "printf 'SECRET-LEASE-METADATA\\n' >&2\n"
            "exit 1\n"
        )

        checked_environment = environment.copy()
        checked_environment["MISTER_RESERVATION_CHECKER"] = f"/bin/sh {checker}"
        checked_environment["MISTER_RESERVATION_ID"] = "wrong-lease"
        rejected = run_cli("reservation_check", environment=checked_environment)
        require(rejected.returncode == 2, "checker rejection did not block the reservation")
        require(
            "SECRET-LEASE-METADATA" not in rejected.stdout + rejected.stderr,
            "reservation checker output leaked through the CLI",
        )

        checked_environment["MISTER_RESERVATION_ID"] = "active-test-lease"
        accepted = run_cli("reservation_check", environment=checked_environment)
        require(accepted.returncode == 0, "valid checker result was not accepted")
        require(
            "MiSTer reservation verified" in accepted.stdout,
            "successful local reservation check was not reported",
        )

    verify_low_level_guard()
    print("PASS: MiSTer tooling fails closed and local-only commands remain usable")
    print("PASS: reservation checker receives and validates the exact lease ID and host")
    print("PASS: every hardware boundary revalidates without leaking checker output")
    print("PASS: no MiSTer connection was attempted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
