#!/usr/bin/env python3
"""Exec mGBA under a project-wide single-flight and parent-death guard.

The wrapper intentionally execs the emulator instead of spawning it.  A
caller's subprocess timeout therefore targets the real emulator process, and
Linux PR_SET_PDEATHSIG terminates it if the verifier itself is killed.
"""

from __future__ import annotations

import ctypes
import fcntl
import os
from pathlib import Path
import signal
import sys


LOCK_PATH = Path(
    os.environ.get(
        "PENTA_MGBA_LOCK",
        "/tmp/penta-dragon-dx.mgba-singleflight.lock",
    )
)
PR_SET_PDEATHSIG = 1


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
    metadata = (
        f"pid={os.getpid()}\n"
        f"ppid={os.getppid()}\n"
        f"mode={mode}\n"
        f"cwd={Path.cwd()}\n"
    ).encode()
    os.write(lock_fd, metadata)
    os.fsync(lock_fd)
    os.set_inheritable(lock_fd, True)

    environment = os.environ.copy()
    environment["PENTA_MGBA_SINGLEFLIGHT"] = "1"
    os.execve(binary, [str(binary), *arguments], environment)
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
