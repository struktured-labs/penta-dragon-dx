#!/usr/bin/env python3
"""Exec mGBA under a project-wide single-flight and parent-death guard.

The wrapper intentionally execs the emulator instead of spawning it.  A
caller's subprocess timeout therefore targets the real emulator process, and
Linux PR_SET_PDEATHSIG terminates it if the verifier itself is killed.
"""

from __future__ import annotations

import ctypes
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sys


LOCK_PATH = Path(
    os.environ.get(
        "PENTA_MGBA_LOCK",
        "/tmp/penta-dragon-dx.mgba-singleflight.lock",
    )
)
PR_SET_PDEATHSIG = 1
OWNER_TOKEN_PATTERN = re.compile(r"[0-9a-f]{64}")


def process_start_time(pid: int) -> int:
    """Return Linux /proc start ticks without being confused by comm spaces."""

    stat = Path(f"/proc/{pid}/stat").read_text()
    fields_after_comm = stat[stat.rfind(")") + 2:].split()
    return int(fields_after_comm[19])  # field 22; field 3 starts at index 0


def outermost_pid() -> int:
    """Return the host-visible PID from Linux's nested PID namespace list."""

    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("NSpid:"):
            values = line.split()[1:]
            if values:
                return int(values[0])
    return os.getpid()


def matrix_owner_token() -> str | None:
    """Return a validated deterministic-suite token when one is present."""

    token = os.environ.get("PENTA_MATRIX_OWNER_TOKEN")
    if token is None:
        return None
    if OWNER_TOKEN_PATTERN.fullmatch(token) is None:
        fail("invalid deterministic-suite owner token", 70)
    return token


def publish_matrix_ownership(token: str | None) -> None:
    """Persist exact PID identity before exec can obscure its environment.

    Some mGBA builds rewrite the process environment that /proc exposes.  A
    random per-suite token is still inherited by this guarded wrapper, so
    publish PID, process group, and kernel start ticks under that unguessable
    token before exec. The suite validates immutable PID/start identity, then
    discovers the exact current group after any Qt session change; a stale
    marker therefore cannot claim a reused PID.
    """

    if token is None:
        return
    registry = Path(
        os.environ.get(
            "PENTA_MGBA_OWNER_REGISTRY",
            f"/tmp/penta-dragon-dx.mgba-owners-{os.getuid()}",
        )
    )
    owner_dir = registry / token
    owner_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    namespace_pid = os.getpid()
    pid = outermost_pid()
    marker = owner_dir / f"{pid}.json"
    temporary = owner_dir / f".{pid}.tmp"
    temporary.write_text(
        json.dumps(
            {
                "pid": pid,
                "namespace_pid": namespace_pid,
                "process_group": os.getpgrp(),
                "start_time": process_start_time(namespace_pid),
            },
            sort_keys=True,
        )
        + "\n"
    )
    os.chmod(temporary, 0o600)
    temporary.replace(marker)


def fail(message: str, status: int) -> "NoReturn":
    print(f"mGBA guard: {message}", file=sys.stderr)
    raise SystemExit(status)


def resolve_binary(mode: str) -> Path:
    if mode == "self-test":
        return Path("/bin/sleep")
    if mode == "qt":
        configured = os.environ.get("PENTA_MGBA_QT_BIN")
        candidates = (
            Path(configured) if configured else None,
            Path("/home/struktured/bin/mgba-qt"),
            Path("/usr/bin/mgba-qt"),
            Path("/usr/local/bin/mgba-qt"),
        )
    elif mode == "headless":
        configured = os.environ.get("PENTA_MGBA_HEADLESS_BIN")
        candidates = (
            Path(configured) if configured else None,
            Path("/usr/local/bin/mgba-headless"),
            Path("/usr/bin/mgba-headless"),
            Path("/home/struktured/bin/mgba-headless"),
        )
    else:
        fail(f"unknown mode {mode!r}; expected qt or headless", 64)

    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    fail(f"real {mode} emulator executable was not found", 69)


def arm_parent_death_signal(expected_parent: int) -> None:
    """Ask Linux to send SIGTERM if the verifier/launcher parent disappears."""

    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        fail(f"could not arm parent-death cleanup: errno {error}", 70)
    # Close the race where the parent exits immediately before prctl().
    if os.getppid() != expected_parent:
        os.kill(os.getpid(), signal.SIGTERM)


def main() -> int:
    if len(sys.argv) < 2:
        fail("usage: mgba_singleflight.py {qt|headless} [arguments...]", 64)
    original_parent = os.getppid()
    mode = sys.argv[1]
    arguments = sys.argv[2:]
    binary = resolve_binary(mode)

    lock_fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fail(
            "another guarded emulator is already active; parallel mGBA "
            "launches are forbidden",
            75,
        )

    arm_parent_death_signal(original_parent)
    os.ftruncate(lock_fd, 0)
    owner_token = matrix_owner_token()
    metadata = (
        f"pid={os.getpid()}\n"
        f"host_pid={outermost_pid()}\n"
        f"ppid={os.getppid()}\n"
        f"mode={mode}\n"
        f"cwd={Path.cwd()}\n"
        + (f"owner_token={owner_token}\n" if owner_token else "")
    ).encode()
    os.write(lock_fd, metadata)
    os.fsync(lock_fd)
    os.set_inheritable(lock_fd, True)
    publish_matrix_ownership(owner_token)

    environment = os.environ.copy()
    environment["PENTA_MGBA_SINGLEFLIGHT"] = "1"
    os.execve(binary, [str(binary), *arguments], environment)
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
