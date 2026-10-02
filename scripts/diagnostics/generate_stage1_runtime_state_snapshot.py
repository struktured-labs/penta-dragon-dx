#!/usr/bin/env python3
"""Save an exact candidate-native state with a minimal guarded mGBA probe."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
MGBA = ROOT / "scripts/mgba-qt-singleflight"
PROBE = Path(__file__).with_name("probe_stage1_runtime_state_snapshot.lua")


def below_tmp(path: Path, label: str) -> Path:
    resolved = path.resolve()
    scratch = TMP.resolve()
    if resolved == scratch or scratch not in resolved.parents:
        raise ValueError(f"{label} must be below repository tmp/")
    return resolved


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("state", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=500)
    parser.add_argument("--timeout", type=float, default=90.0)
    args = parser.parse_args()

    rom = args.rom.resolve()
    state = args.state.resolve()
    output = below_tmp(args.output, "output state")
    if not rom.is_file() or not state.is_file():
        parser.error("ROM and source state must exist")
    if args.frames <= 0:
        parser.error("--frames must be positive")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    receipt = output.with_suffix(output.suffix + ".receipt")
    receipt.unlink(missing_ok=True)
    log = output.with_suffix(output.suffix + ".log")
    log.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "TMPDIR": str(TMP.resolve()),
        "PENTA_SNAPSHOT_STATE_OUT": str(output),
        "PENTA_SNAPSHOT_RECEIPT_OUT": str(receipt),
        "PENTA_SNAPSHOT_FRAME": str(args.frames),
    })
    environment.pop("DISPLAY", None)
    environment.pop("WAYLAND_DISPLAY", None)
    command = [
        str(MGBA), "--fastforward",
        "-t", str(state), "--script", str(PROBE), str(rom),
    ]
    completed = subprocess.run(
        command, cwd=ROOT, env=environment, timeout=args.timeout,
        check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, errors="replace",
    )
    probe_log = completed.stdout or ""
    log.write_text(probe_log)
    exact_qt_teardown = (
        (
            completed.returncode == 134
            and "pure virtual method called" in probe_log
            and "terminate called without an active exception" in probe_log
            and "Aborted (core dumped)" in probe_log
        )
        or (
            completed.returncode == 139
            and probe_log == "Segmentation fault (core dumped)\n"
        )
    )
    if (
        completed.returncode != 0
        and not exact_qt_teardown
    ) or not output.is_file() or not receipt.is_file():
        raise RuntimeError(
            f"snapshot probe status={completed.returncode}; output is incomplete "
            f"or teardown was not recognized; log={log}"
        )
    values = dict(
        line.split("=", 1) for line in receipt.read_text().splitlines()
        if "=" in line
    )
    if values.get("status") != "pass" or int(values.get("frames", "0")) < args.frames:
        raise RuntimeError("snapshot receipt did not reach its target frame")
    print(
        f"PASS: state={output} sha256={digest(output)} "
        f"scene={values['scene']} room={values['room']} lcdc={values['lcdc']} "
        f"process_status={completed.returncode} "
        f"qt_teardown_accepted={int(exact_qt_teardown)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
