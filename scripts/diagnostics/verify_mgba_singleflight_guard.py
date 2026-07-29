#!/usr/bin/env python3
"""Hardware-free regression for the project mGBA safety boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from suite_contract import GUARDED_ENTRYPOINTS


ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/mgba_singleflight.py"
QT_WRAPPER = ROOT / "scripts/mgba-qt-singleflight"
HEADLESS_WRAPPER = ROOT / "scripts/mgba-headless-singleflight"
HOOK = ROOT / "scripts/hooks/guard_mgba_launch.py"
GIT_HOOK = ROOT / ".githooks/pre-commit"
SUITE_RUNNER = ROOT / "scripts/diagnostics/run_deterministic_suite.py"
PROJECT_SETTINGS = ROOT / ".claude/settings.json"
AGENT_RULES = ROOT / "AGENTS.md"


def hook_result(command: str) -> subprocess.CompletedProcess[str]:
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "tool_use_id": "mgba-safety-self-test",
    }
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=False,
        timeout=5,
    )


def wait_for_lock(path: Path, expected_pid: int, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            text = path.read_text()
        except OSError:
            text = ""
        if f"pid={expected_pid}\n" in text:
            return
        time.sleep(0.01)
    raise RuntimeError("single-flight owner did not publish its lock metadata")


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def main() -> int:
    failures: list[str] = []

    for path in (GUARD, QT_WRAPPER, HEADLESS_WRAPPER, HOOK, GIT_HOOK):
        if not path.is_file() or not os.access(path, os.X_OK):
            failures.append(f"missing or non-executable guard component: {path}")

    try:
        git_hook = GIT_HOOK.read_text()
        for command in (
            "verify_mgba_singleflight_guard.py",
            "verify_suite_receipt.py --staged",
        ):
            if command not in git_hook:
                failures.append(
                    f"pre-commit hook omits required command: {command}"
                )
    except OSError as exc:
        failures.append(f"pre-commit hook unavailable: {exc}")

    try:
        suite_runner = SUITE_RUNNER.read_text()
        if '[str(PROCESS_CHECK), "--require-none"]' not in suite_runner:
            failures.append(
                "deterministic suite lacks the empty-host-slot preflight"
            )
        if (
            "foreign_mgba_processes" not in suite_runner
            or "run_matrix_guarded" not in suite_runner
        ):
            failures.append(
                "deterministic suite lacks continuous foreign-emulator "
                "monitoring"
            )
        if "os.getpgid(int(process_dir.name))" not in suite_runner:
            failures.append(
                "deterministic suite does not bind allowed emulators to the "
                "exact matrix process group"
            )
        if "process_is_descendant" not in suite_runner:
            failures.append(
                "deterministic suite does not bind detached Qt groups to the "
                "exact matrix ancestry"
            )
        if (
            "PENTA_MATRIX_OWNER_TOKEN" not in suite_runner
            or "secrets.token_hex(32)" not in suite_runner
        ):
            failures.append(
                "deterministic suite lacks a per-run cross-namespace emulator "
                "ownership token"
            )
        if (
            "owned_mgba_processes" not in suite_runner
            or "stop_matrix_and_owned" not in suite_runner
            or 'status="owned-emulator-leak"' not in suite_runner
        ):
            failures.append(
                "deterministic suite does not clean token-owned emulator "
                "groups or reject post-matrix leaks"
            )
        if (
            "token_process_groups" not in suite_runner
            or "foreign_observations" not in suite_runner
            or ">= 3" not in suite_runner
        ):
            failures.append(
                "deterministic suite does not tolerate transient /proc races "
                "while confirming foreign emulator ownership"
            )
    except OSError as exc:
        failures.append(f"deterministic suite unavailable: {exc}")

    try:
        settings = json.loads(PROJECT_SETTINGS.read_text())
        pre_hooks = settings["hooks"]["PreToolUse"]
        if not any(entry.get("matcher") == "Bash" for entry in pre_hooks):
            failures.append("project settings do not install the Bash PreToolUse hook")
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        failures.append(f"project hook settings are invalid: {exc}")

    try:
        rules = AGENT_RULES.read_text()
        if "Never run two emulator-backed commands concurrently" not in rules:
            failures.append("AGENTS.md lacks the parallel-emulator hard rule")
    except OSError as exc:
        failures.append(f"AGENTS.md unavailable: {exc}")

    for relative in GUARDED_ENTRYPOINTS:
        path = ROOT / relative
        try:
            source = path.read_text()
        except OSError as exc:
            failures.append(f"guarded entrypoint unavailable: {relative}: {exc}")
            continue
        if "singleflight" not in source:
            failures.append(f"entrypoint bypasses the single-flight wrapper: {relative}")
        if "pkill" in source or "killall" in source:
            failures.append(f"entrypoint contains broad process killing: {relative}")

    raw = hook_result("mgba-qt game.gb")
    if raw.returncode != 2 or "BLOCKED" not in raw.stderr:
        failures.append("PreToolUse hook did not reject raw mgba-qt")
    override = hook_result(
        "python3 scripts/diagnostics/verify_frame_flicker.py "
        "--mgba /home/struktured/bin/mgba-qt game.gb"
    )
    if override.returncode != 2:
        failures.append("PreToolUse hook did not reject an unsafe --mgba override")
    legacy = hook_result("python3 scripts/quick_verify_rom.py game.gb")
    if legacy.returncode != 2 or "quarantined legacy launcher" not in legacy.stderr:
        failures.append("PreToolUse hook did not quarantine a legacy launcher")
    safe = hook_result("scripts/launch_mgba.sh game.gb")
    if safe.returncode != 0:
        failures.append("PreToolUse hook rejected the guarded headed launcher")
    status = hook_result("scripts/check_emulator_processes.sh")
    if status.returncode != 0:
        failures.append("PreToolUse hook rejected the read-only status helper")

    # Exercise the atomic lock using /bin/sleep only. No emulator is started.
    with tempfile.TemporaryDirectory(prefix="penta-mgba-guard-") as temp:
        lock = Path(temp) / "singleflight.lock"
        environment = os.environ.copy()
        environment["PENTA_MGBA_LOCK"] = str(lock)
        owner = subprocess.Popen(
            [sys.executable, str(GUARD), "self-test", "30"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_for_lock(lock, owner.pid)
            contender = subprocess.run(
                [sys.executable, str(GUARD), "self-test", "0.01"],
                env=environment,
                text=True,
                capture_output=True,
                check=False,
                timeout=3,
            )
            if contender.returncode != 75:
                failures.append(
                    "concurrent single-flight contender was not rejected "
                    f"(status {contender.returncode})"
                )
        finally:
            owner.terminate()
            owner.wait(timeout=3)

        after_release = subprocess.run(
            [sys.executable, str(GUARD), "self-test", "0.01"],
            env=environment,
            capture_output=True,
            check=False,
            timeout=3,
        )
        if after_release.returncode != 0:
            failures.append("single-flight lock was not released after owner exit")

        # Start a guarded sleep from a short-lived verifier. PR_SET_PDEATHSIG
        # must remove the child when that verifier exits.
        parent_code = (
            "import os,subprocess,sys,time;"
            f"p=subprocess.Popen([sys.executable,{str(GUARD)!r},"
            "'self-test','30']);"
            "lock=os.environ['PENTA_MGBA_LOCK'];"
            "deadline=time.monotonic()+2;"
            "\nwhile time.monotonic()<deadline:\n"
            " try:\n  text=open(lock).read()\n"
            " except OSError:\n  text=''\n"
            " if f'pid={p.pid}\\n' in text:\n  break\n"
            " time.sleep(0.01)\n"
            "print(p.pid,flush=True)"
        )
        parent = subprocess.run(
            [sys.executable, "-c", parent_code],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
            timeout=3,
        )
        try:
            orphan_pid = int(parent.stdout.strip())
        except ValueError:
            failures.append("parent-death test did not return a child PID")
        else:
            deadline = time.monotonic() + 2
            while process_exists(orphan_pid) and time.monotonic() < deadline:
                time.sleep(0.02)
            if process_exists(orphan_pid):
                failures.append(
                    f"parent-death cleanup left guarded child PID {orphan_pid}"
                )

    if failures:
        print("FAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("PASS: raw Claude mGBA commands are denied.")
    print("PASS: a second guarded emulator launch fails closed with status 75.")
    print("PASS: lock ownership is released on normal/terminated exit.")
    print("PASS: parent-death cleanup prevents verifier-timeout orphans.")
    print("PASS: pre-commit requires safety plus a staged full-suite receipt.")
    print(
        "PASS: the deterministic suite preflights and continuously monitors "
        "the host emulator slot."
    )
    print("PASS: no emulator was launched by this safety regression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
