#!/usr/bin/env python3
"""Resume a captured stale-Window state and require bounded recovery."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stale_window_state.lua"


def digest(path: Path, algorithm: str = "sha256") -> str:
    value = hashlib.new(algorithm)
    value.update(path.read_bytes())
    return value.hexdigest()


def parse_fields(value: str) -> dict[str, str]:
    if value == "none":
        return {}
    return dict(re.findall(r"([a-z0-9_]+):([0-9A-F-]+)", value))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--mgba",
        type=Path,
        default=ROOT / "scripts/mgba-qt-singleflight",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()

    rom = args.rom.resolve()
    state = args.state.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STALE_WINDOW_STATE_OUT": str(output),
        "STALE_WINDOW_STATE_FRAMES": "60",
    })
    log = output.with_suffix(".mgba.log")
    with log.open("w") as stream:
        completed = subprocess.run(
            [
                str(args.mgba.resolve()),
                "--fastforward",
                "-t",
                str(state),
                "--script",
                str(PROBE),
                str(rom),
            ],
            cwd=ROOT,
            env=environment,
            stdout=stream,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
            check=False,
        )
    if completed.returncode != 0 or not output.is_file():
        print(f"FAIL: probe exited {completed.returncode}; see {log}")
        return 1

    report = dict(
        line.split("=", 1)
        for line in output.read_text().splitlines()
        if "=" in line
    )
    entry = parse_fields(report.get("entry", "none"))
    final = parse_fields(report.get("final", "none"))
    clear_frame = int(report.get("clear_frame", "-1"))
    entry_frame = int(entry.get("frame", "-1"))
    checks = {
        "captured current-ROM code executes after resume": (
            int(report.get("main_loop_hits", "0")) > 0
        ),
        "captured failure reaches the dungeon cleanup entry": (
            int(report.get("entry_hits", "0")) > 0
            and 0x02 <= int(entry.get("scene", "FF"), 16) < 0x0C
            and entry.get("active") == "01"
            and entry.get("ffe4") == "00"
            and int(entry.get("lcdc", "00"), 16) & 0x20 != 0
            and int(entry.get("wy", "FF"), 16) < 144
        ),
        "stale Window clears within two rendered frames": (
            clear_frame >= entry_frame >= 0
            and clear_frame - entry_frame <= 2
            and int(final.get("lcdc", "FF"), 16) & 0x20 == 0
        ),
        "entry, cleared, and final frames were captured": all(
            output.with_suffix(suffix).is_file()
            for suffix in (".entry.png", ".cleared.png", ".final.png")
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "penta-dragon-dx-stale-window-state-v1",
        "status": "pass" if not failures else "fail",
        "rom": str(rom),
        "rom_md5": digest(rom, "md5"),
        "rom_sha256": digest(rom),
        "state": str(state),
        "state_sha256": digest(state),
        "checks": checks,
        "report": report,
        "artifacts": {
            suffix: digest(output.with_suffix(suffix))
            for suffix in (".entry.png", ".cleared.png", ".final.png")
            if output.with_suffix(suffix).is_file()
        },
        "failures": failures,
    }
    receipt_path = output.with_suffix(".receipt.json")
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"Receipt: {receipt_path}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
