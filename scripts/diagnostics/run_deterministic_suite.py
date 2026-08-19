#!/usr/bin/env python3
"""Build twice, run the complete serial emulator matrix, and write a receipt.

The explicit expanded profile reproduces the release-line 512 KiB image with
native Ted poses/sparse geometry and, optionally, the isolated menu publisher.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from suite_contract import (
    DEFAULT_RECEIPT,
    ROOT,
    SCHEMA,
    sha256_file,
    source_snapshot,
)
from suite_release_ledger import collect_release_ledger


LEGACY_BUILDER = ROOT / "scripts/build_v302_title_fix.py"
EXPANDED_BUILDER = ROOT / "scripts/build_ted_expanded_candidate.py"
MATRIX = ROOT / "scripts/diagnostics/verify_release_candidate.py"
PROCESS_CHECK = ROOT / "scripts/check_emulator_processes.sh"
OWNER_REGISTRY = Path(
    os.environ.get(
        "PENTA_MGBA_OWNER_REGISTRY",
        str(ROOT / "tmp" / f"penta-dragon-dx.mgba-owners-{os.getuid()}"),
    )
)
MGBA_LOCK = Path(
    os.environ.get(
        "PENTA_MGBA_LOCK",
        str(ROOT / "tmp" / "penta-dragon-dx.mgba-singleflight.lock"),
    )
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def md5_file(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def configure_repo_temp(output: Path) -> Path:
    """Route Python and child-process scratch files away from system /tmp."""

    runtime_tmp = output / "runtime-tmp"
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    for name in ("TMPDIR", "TMP", "TEMP"):
        os.environ[name] = str(runtime_tmp)
    return runtime_tmp


def run_logged(command: list[str], log: Path) -> int:
    with log.open("w") as handle:
        result = subprocess.run(
            command,
            cwd=ROOT,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    return result.returncode


def process_parent(pid: int) -> int | None:
    try:
        status = Path(f"/proc/{pid}/status").read_text()
    except OSError:
        return None
    for line in status.splitlines():
        if line.startswith("PPid:"):
            try:
                return int(line.split()[1])
            except (IndexError, ValueError):
                return None
    return None


def process_is_descendant(pid: int, root_pid: int) -> bool:
    """Return whether *pid* is in the live ancestry rooted at *root_pid*."""

    seen: set[int] = set()
    current = pid
    while current > 1 and current not in seen:
        if current == root_pid:
            return True
        seen.add(current)
        parent = process_parent(current)
        if parent is None:
            return False
        current = parent
    return current == root_pid


def process_start_time(pid: int) -> int | None:
    """Return Linux start ticks for a PID, tolerating spaces in comm."""

    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields_after_comm = stat[stat.rfind(")") + 2:].split()
        return int(fields_after_comm[19])
    except (OSError, ValueError, IndexError):
        return None


def registered_owner_process(
    owner_token: str,
    pid: int,
    process_group: int,
) -> bool:
    """Validate the wrapper's pre-exec ownership marker for this process."""

    marker = OWNER_REGISTRY / owner_token / f"{pid}.json"
    try:
        value = json.loads(marker.read_text())
    except (OSError, json.JSONDecodeError):
        return False
    start_time = process_start_time(pid)
    return (
        value.get("pid") == pid
        and value.get("start_time") == start_time
        and start_time is not None
        # Qt/headless may create a new session after exec. The immutable
        # PID/start-tick pair proves this is the registered process; its exact
        # current group is then obtained from os.getpgid() by the caller.
        and isinstance(value.get("process_group"), int)
        and value["process_group"] > 1
        and process_group > 1
    )


def process_holds_owned_lock(pid: int, owner_token: str) -> bool:
    """Prove a forked emulator inherited this run's locked file descriptor."""

    try:
        metadata = MGBA_LOCK.read_text()
        lock_stat = MGBA_LOCK.stat()
        descriptors = list(Path(f"/proc/{pid}/fd").iterdir())
    except OSError:
        return False
    if f"owner_token={owner_token}\n" not in metadata:
        return False
    for descriptor in descriptors:
        try:
            descriptor_stat = descriptor.stat()
        except OSError:
            continue
        if (
            descriptor_stat.st_dev == lock_stat.st_dev
            and descriptor_stat.st_ino == lock_stat.st_ino
        ):
            return True
    return False


def process_command(pid: int) -> str:
    """Return a bounded command line while the observed process still lives."""

    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return "(unavailable)"
    return command.replace(b"\0", b" ").decode(errors="replace")[:2048].strip()


def cleanup_owner_registry(owner_token: str) -> None:
    """Remove only marker files underneath this run's random token."""

    owner_dir = OWNER_REGISTRY / owner_token
    try:
        markers = list(owner_dir.iterdir())
    except OSError:
        return
    for marker in markers:
        if marker.is_file() and (
            marker.name.endswith(".json") or marker.name.endswith(".tmp")
        ):
            marker.unlink(missing_ok=True)
    try:
        owner_dir.rmdir()
    except OSError:
        pass


def token_process_groups(owner_token: str) -> set[int]:
    """Return host process groups carrying this matrix's random token."""

    groups: set[int] = set()
    owner_entry = f"PENTA_MATRIX_OWNER_TOKEN={owner_token}".encode()
    for process_dir in Path("/proc").iterdir():
        if not process_dir.name.isdigit():
            continue
        try:
            environment = (process_dir / "environ").read_bytes().split(b"\0")
            process_group = os.getpgid(int(process_dir.name))
        except OSError:
            continue
        pid = int(process_dir.name)
        if (
            owner_entry in environment
            or registered_owner_process(owner_token, pid, process_group)
            or process_holds_owned_lock(pid, owner_token)
        ):
            groups.add(process_group)
    return groups


def foreign_mgba_processes(
    allowed_root_pid: int,
    owner_token: str,
    allowed_process_groups: set[int],
) -> list[dict[str, str | int]]:
    """Return host mGBA processes outside the exact matrix process tree."""

    found: list[dict[str, str | int]] = []
    owner_entry = f"PENTA_MATRIX_OWNER_TOKEN={owner_token}".encode()
    for process_dir in Path("/proc").iterdir():
        if not process_dir.name.isdigit():
            continue
        try:
            name = (process_dir / "comm").read_text().strip()
        except OSError:
            continue
        if name not in {"mgba", "mgba-qt", "mgba-headless"}:
            continue
        try:
            process_group = os.getpgid(int(process_dir.name))
        except OSError:
            continue
        if process_group in allowed_process_groups:
            continue
        try:
            environment = (process_dir / "environ").read_bytes().split(b"\0")
        except OSError:
            environment = []
        pid = int(process_dir.name)
        if (
            owner_entry in environment
            or registered_owner_process(owner_token, pid, process_group)
            or process_holds_owned_lock(pid, owner_token)
        ):
            allowed_process_groups.add(process_group)
            continue
        if (
            process_group == allowed_root_pid
            or process_is_descendant(pid, allowed_root_pid)
        ):
            continue
        found.append(
            {
                "pid": pid,
                "name": name,
                "process_group": process_group,
                "command": process_command(pid),
                "owner_environment": owner_entry in environment,
                "owner_marker": registered_owner_process(
                    owner_token, pid, process_group
                ),
                "owner_lock": process_holds_owned_lock(pid, owner_token),
            }
        )
    return sorted(found, key=lambda item: int(item["pid"]))


def owned_mgba_processes(
    owner_token: str,
) -> list[dict[str, str | int]]:
    """Return mGBA processes carrying this exact matrix's random token."""

    found: list[dict[str, str | int]] = []
    owner_entry = f"PENTA_MATRIX_OWNER_TOKEN={owner_token}".encode()
    for process_dir in Path("/proc").iterdir():
        if not process_dir.name.isdigit():
            continue
        try:
            name = (process_dir / "comm").read_text().strip()
            environment = (process_dir / "environ").read_bytes().split(b"\0")
            process_group = os.getpgid(int(process_dir.name))
        except OSError:
            continue
        pid = int(process_dir.name)
        if (
            name not in {"mgba", "mgba-qt", "mgba-headless"}
            or (
                owner_entry not in environment
                and not registered_owner_process(
                    owner_token, pid, process_group
                )
                and not process_holds_owned_lock(pid, owner_token)
            )
        ):
            continue
        found.append(
            {
                "pid": pid,
                "name": name,
                "process_group": process_group,
            }
        )
    return sorted(found, key=lambda item: int(item["pid"]))


def signal_owned_groups(
    processes: list[dict[str, str | int]],
    selected_signal: signal.Signals,
) -> None:
    """Signal only unique process groups proven to carry the run token."""

    groups = {
        int(process["process_group"])
        for process in processes
        if int(process["process_group"]) > 1
    }
    for process_group in sorted(groups):
        try:
            os.killpg(process_group, selected_signal)
        except ProcessLookupError:
            pass


def stop_owned_mgba(owner_token: str) -> list[dict[str, str | int]]:
    """Stop and return only mGBA processes owned by this matrix token."""

    owned = owned_mgba_processes(owner_token)
    signal_owned_groups(owned, signal.SIGTERM)
    deadline = time.monotonic() + 0.5
    remaining = owned_mgba_processes(owner_token)
    while remaining and time.monotonic() < deadline:
        time.sleep(0.05)
        remaining = owned_mgba_processes(owner_token)
    signal_owned_groups(remaining, signal.SIGKILL)
    return owned


def stop_matrix_and_owned(
    process: subprocess.Popen,
    owner_token: str,
) -> list[dict[str, str | int]]:
    """Stop the exact matrix group plus any token-owned detached sessions."""

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    owned = stop_owned_mgba(owner_token)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    leftovers = stop_owned_mgba(owner_token)
    known_pids = {int(item["pid"]) for item in owned}
    owned.extend(
        item for item in leftovers if int(item["pid"]) not in known_pids
    )
    return owned


def run_matrix_guarded(
    command: list[str],
    log: Path,
) -> tuple[
    int,
    list[dict[str, str | int]],
    list[dict[str, str | int]],
]:
    """Run the matrix while continuously enforcing the empty foreign slot."""

    owner_token = secrets.token_hex(32)
    cleanup_owner_registry(owner_token)
    environment = os.environ.copy()
    environment["PENTA_MATRIX_OWNER_TOKEN"] = owner_token
    with log.open("w") as handle:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        allowed_process_groups: set[int] = set()
        group_deadline = time.monotonic() + 1
        while not allowed_process_groups and time.monotonic() < group_deadline:
            allowed_process_groups.update(token_process_groups(owner_token))
            if not allowed_process_groups:
                time.sleep(0.01)
        foreign: list[dict[str, str | int]] = []
        foreign_observations: dict[tuple[int, int], int] = {}
        while process.poll() is None:
            observed = foreign_mgba_processes(
                process.pid,
                owner_token,
                allowed_process_groups,
            )
            observed_keys = {
                (int(item["pid"]), int(item["process_group"]))
                for item in observed
            }
            foreign_observations = {
                key: foreign_observations.get(key, 0) + 1
                for key in observed_keys
            }
            foreign = [
                item
                for item in observed
                if foreign_observations[
                    (int(item["pid"]), int(item["process_group"]))
                ] >= 3
            ]
            if foreign:
                # Stop only the matrix group and per-run-token descendants.
                # Never signal the foreign owner or use a name-pattern kill.
                stop_matrix_and_owned(process, owner_token)
                cleanup_owner_registry(owner_token)
                return process.returncode, foreign, []
            time.sleep(0.05)
        # Close the small race between the final poll and matrix exit.
        foreign = foreign_mgba_processes(
            process.pid,
            owner_token,
            allowed_process_groups,
        )
        if foreign:
            stop_owned_mgba(owner_token)
            cleanup_owner_registry(owner_token)
            return process.returncode, foreign, []
        leaked = owned_mgba_processes(owner_token)
        if leaked:
            stop_owned_mgba(owner_token)
        cleanup_owner_registry(owner_token)
        return process.returncode, [], leaked


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def main() -> int:
    parser = argparse.ArgumentParser()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "tmp" / f"penta-deterministic-suite-{stamp}",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=DEFAULT_RECEIPT,
        help="committable hash-bound summary written only after a full pass",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume passed matrix gates from the selected output directory",
    )
    parser.add_argument(
        "--expanded-ted",
        action="store_true",
        help=(
            "build the 512 KiB release profile with native Ted sparse "
            "geometry and the exact native pose table"
        ),
    )
    parser.add_argument(
        "--menu-icon-colors",
        action="store_true",
        help="include the isolated expanded-bank item-menu publisher",
    )
    parser.add_argument("--timeout-scale", type=float, default=1.0)
    args = parser.parse_args()
    if args.timeout_scale <= 0:
        parser.error("--timeout-scale must be positive")
    if args.menu_icon_colors and not args.expanded_ted:
        parser.error("--menu-icon-colors requires --expanded-ted")

    build_profile = {
        "name": (
            "expanded-ted-menu" if args.menu_icon_colors
            else "expanded-ted" if args.expanded_ted
            else "legacy-256k"
        ),
        "expanded_ted": args.expanded_ted,
        "native_sparse": args.expanded_ted,
        "native_pose_table": args.expanded_ted,
        "menu_icon_colors": args.menu_icon_colors,
    }

    process_check = subprocess.run(
        [str(PROCESS_CHECK), "--require-none"],
        cwd=ROOT,
        check=False,
    )
    if process_check.returncode != 0:
        print(
            "FAIL: deterministic suite requires an empty host emulator slot"
        )
        return process_check.returncode

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    runtime_tmp = configure_repo_temp(output)
    logs = output / "logs"
    logs.mkdir(exist_ok=True)
    build_dir = output / "build"
    build_dir.mkdir(exist_ok=True)
    matrix_dir = output / "matrix"
    candidate_a = build_dir / "candidate-a.gb"
    candidate_b = build_dir / "candidate-b.gb"
    base_a = build_dir / "candidate-a-v301.gb"
    base_b = build_dir / "candidate-b-v301.gb"
    run_manifest = output / "run.json"

    source_fingerprint, source_inputs = source_snapshot()
    run = {
        "schema": SCHEMA,
        "status": "building",
        "started_at": utc_now(),
        "source_fingerprint": source_fingerprint,
        "source_inputs": source_inputs,
        "git_head_at_run": git_head(),
        "output": str(output),
        "runtime_tmp": str(runtime_tmp),
        "build_profile": build_profile,
    }
    write_json(run_manifest, run)

    print(f"Source fingerprint: {source_fingerprint}")
    for label, candidate, base in (
        ("a", candidate_a, base_a),
        ("b", candidate_b, base_b),
    ):
        if args.expanded_ted:
            command = [
                sys.executable,
                str(EXPANDED_BUILDER),
                "--output",
                str(candidate),
                "--native-sparse",
                "--native-pose-table",
                "--work",
                str(build_dir / f"expanded-work-{label}"),
            ]
            if args.menu_icon_colors:
                command.append("--menu-icon-colors")
        else:
            command = [
                sys.executable,
                str(LEGACY_BUILDER),
                "--output",
                str(candidate),
                "--base-output",
                str(base),
            ]
        returncode = run_logged(command, logs / f"build-{label}.log")
        if returncode != 0:
            run.update(
                status="build-failed",
                failed_build=label,
                returncode=returncode,
                finished_at=utc_now(),
            )
            write_json(run_manifest, run)
            print(f"FAIL: build {label} exited {returncode}")
            return 1

    build_sha256_a = sha256_file(candidate_a)
    build_sha256_b = sha256_file(candidate_b)
    build_md5_a = md5_file(candidate_a)
    build_md5_b = md5_file(candidate_b)
    if (
        candidate_a.read_bytes() != candidate_b.read_bytes()
        or build_sha256_a != build_sha256_b
        or build_md5_a != build_md5_b
    ):
        run.update(
            status="nondeterministic-build",
            build_a_sha256=build_sha256_a,
            build_b_sha256=build_sha256_b,
            finished_at=utc_now(),
        )
        write_json(run_manifest, run)
        print("FAIL: two clean candidate builds differ")
        return 1
    print(
        f"PASS deterministic build: SHA-256 {build_sha256_a}, "
        f"MD5 {build_md5_a}"
    )

    run.update(
        status="matrix-running",
        candidate_sha256=build_sha256_a,
        candidate_md5=build_md5_a,
        candidate_size=candidate_a.stat().st_size,
        deterministic_build=True,
    )
    write_json(run_manifest, run)

    matrix_command = [
        sys.executable,
        str(MATRIX),
        str(candidate_a),
        "--output",
        str(matrix_dir),
        "--timeout-scale",
        str(args.timeout_scale),
    ]
    if args.resume:
        matrix_command.append("--resume")
    matrix_returncode, foreign_processes, leaked_processes = run_matrix_guarded(
        matrix_command,
        logs / "matrix.log",
    )
    matrix_manifest = matrix_dir / "manifest.json"
    if foreign_processes:
        run.update(
            status="foreign-emulator-detected",
            returncode=matrix_returncode,
            foreign_emulator_processes=foreign_processes,
            finished_at=utc_now(),
        )
        write_json(run_manifest, run)
        rendered = ", ".join(
            f"{item['name']} PID {item['pid']}"
            for item in foreign_processes
        )
        print(
            "FAIL: foreign mGBA entered the host slot during the matrix: "
            f"{rendered}"
        )
        print(
            "The exact Penta matrix process group was stopped; the foreign "
            "owner was not signaled."
        )
        return 75
    if leaked_processes:
        run.update(
            status="owned-emulator-leak",
            returncode=matrix_returncode,
            leaked_emulator_processes=leaked_processes,
            finished_at=utc_now(),
        )
        write_json(run_manifest, run)
        rendered = ", ".join(
            f"{item['name']} PID {item['pid']}"
            for item in leaked_processes
        )
        print(
            "FAIL: the matrix exited with token-owned mGBA processes still "
            f"alive: {rendered}"
        )
        print("The exact owned process groups were stopped; receipt withheld.")
        return 70
    if not matrix_manifest.is_file():
        run.update(
            status="matrix-failed",
            returncode=matrix_returncode,
            error="matrix manifest missing",
            finished_at=utc_now(),
        )
        write_json(run_manifest, run)
        print("FAIL: release matrix produced no manifest")
        return 1

    matrix_value = json.loads(matrix_manifest.read_text())
    source_after, inputs_after = source_snapshot()
    if source_after != source_fingerprint or inputs_after != source_inputs:
        run.update(
            status="source-mutated",
            source_fingerprint_after=source_after,
            finished_at=utc_now(),
        )
        write_json(run_manifest, run)
        print("FAIL: suite inputs changed during verification")
        return 1
    if (
        matrix_returncode != 0
        or matrix_value.get("status") != "emulator-pass"
        or matrix_value.get("scope") != "full"
        or matrix_value.get("failures") != 0
    ):
        run.update(
            status="matrix-failed",
            returncode=matrix_returncode,
            matrix_status=matrix_value.get("status"),
            matrix_failures=matrix_value.get("failures"),
            matrix_manifest_sha256=sha256_file(matrix_manifest),
            finished_at=utc_now(),
        )
        write_json(run_manifest, run)
        print(f"FAIL: full matrix failed; see {matrix_manifest}")
        return 1

    results = [
        {
            "name": result["name"],
            "status": result["status"],
            "returncode": result["returncode"],
            "duration_seconds": result["duration_seconds"],
        }
        for result in matrix_value["results"]
    ]
    try:
        release_ledger = collect_release_ledger(
            matrix_dir, expanded=args.expanded_ted
        )
    except RuntimeError as exc:
        run.update(
            status="release-ledger-failed",
            error=str(exc),
            finished_at=utc_now(),
        )
        write_json(run_manifest, run)
        print(f"FAIL: could not construct release exception ledger: {exc}")
        return 1
    receipt = {
        "schema": SCHEMA,
        "status": "passed",
        "generated_at": utc_now(),
        "git_head_at_run": run["git_head_at_run"],
        "source_fingerprint": source_fingerprint,
        "source_inputs": source_inputs,
        "build_profile": build_profile,
        "candidate": {
            "size": candidate_a.stat().st_size,
            "md5": build_md5_a,
            "sha256": build_sha256_a,
        },
        "deterministic_build": {
            "passes": 2,
            "byte_identical": True,
            "build_a_sha256": build_sha256_a,
            "build_b_sha256": build_sha256_b,
        },
        "matrix": {
            "status": "emulator-pass",
            "scope": "full",
            "gate_count": len(results),
            "failures": 0,
            "manifest_sha256": sha256_file(matrix_manifest),
            "results": results,
        },
        "release_ledger": release_ledger,
        "rom_committed": False,
        "hardware_status": "pending-reservation-backed-mister",
    }
    write_json(args.receipt.resolve(), receipt)
    run.update(
        status="passed",
        receipt=str(args.receipt.resolve()),
        matrix_manifest_sha256=receipt["matrix"]["manifest_sha256"],
        finished_at=utc_now(),
    )
    write_json(run_manifest, run)
    print(
        f"PASS: {len(results)} serial gates and two byte-identical builds."
    )
    print(f"Receipt: {args.receipt.resolve()}")
    print("No ROM was copied into the repository.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
