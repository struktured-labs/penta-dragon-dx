#!/usr/bin/env python3
"""Verify conservative later-stage BG attributes and the vetted lava overrides."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/diagnostics/probe_stage_integrity.lua"


def parse_meta(path: Path) -> dict[str, int]:
    first_line = path.read_text().splitlines()[0]
    values: dict[str, int] = {}
    hex_keys = {"expected_scene", "D880", "FFC1", "FFBA", "LCDC", "SCX", "SCY", "active_map"}
    for key, raw in re.findall(r"([A-Za-z0-9_]+)=([0-9A-Fa-f]+)", first_line):
        values[key] = int(raw, 16 if key in hex_keys else 10)
    return values


def capture(mgba: str, rom: Path, target: int, prefix: Path, timeout: float) -> None:
    env = os.environ.copy()
    env.update({
        "QT_QPA_PLATFORM": "offscreen",
        "SDL_AUDIODRIVER": "dummy",
        "STAGE_TARGET": str(target),
        "STAGE_OUT": str(prefix),
        "STAGE_SHOT": "0",
    })
    proc = subprocess.Popen(
        [mgba, "--script", str(PROBE), str(rom)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + timeout
    meta = prefix.with_suffix(".meta")
    try:
        while time.monotonic() < deadline:
            if meta.exists() and meta.stat().st_size:
                return
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        raise RuntimeError(f"stage {target + 1} capture timed out")
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def visible_attrs(prefix: Path, meta: dict[str, int]) -> list[int]:
    attrs = prefix.with_suffix(".attr.bin").read_bytes()
    offset = 0x400 if meta["active_map"] == 0x9C00 else 0
    first_col, first_row = meta["SCX"] // 8, meta["SCY"] // 8
    cols = 20 if meta["SCX"] & 7 == 0 else 21
    rows = 18 if meta["SCY"] & 7 == 0 else 19
    return [
        attrs[
            offset
            + ((first_row + row) & 31) * 32
            + ((first_col + col) & 31)
        ]
        for row in range(rows)
        for col in range(cols)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("rom", type=Path)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-headless-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=7.0)
    args = parser.parse_args()

    failures: list[str] = []
    # FFBA 1/2/3/5 are intentionally neutral until their tilesets are tuned.
    # FFBA 4 and 6 retain only the audited Stage 5/7 lava palette.
    expected = {1: {0}, 2: {0}, 3: {0}, 4: {0, 5}, 5: {0}, 6: {0, 5}}
    lava_tiles = {
        4: {0x02, 0x03, 0x04, 0x05, 0x12, 0x13, 0x14, 0x15},
        6: {0x19, 0x1A},
    }

    with tempfile.TemporaryDirectory(prefix="penta-stage-integrity-") as temp:
        temp_path = Path(temp)
        for target, allowed in expected.items():
            prefix = temp_path / f"stage{target + 1}"
            try:
                capture(args.mgba, args.rom.resolve(), target, prefix, args.timeout)
                meta = parse_meta(prefix.with_suffix(".meta"))
                attrs = visible_attrs(prefix, meta)
                all_attrs = prefix.with_suffix(".attr.bin").read_bytes()
                all_tiles = prefix.with_suffix(".map0.bin").read_bytes()
            except Exception as exc:
                failures.append(str(exc))
                continue

            counts = {value: attrs.count(value) for value in sorted(set(attrs))}
            bad = sorted(value for value in counts if value not in allowed)
            unsafe = sum(1 for value in attrs if value & 0xF8)
            lava_count = sum(value == 5 for value in all_attrs)
            lava_mismatches = sum(
                attr == 5 and tile not in lava_tiles.get(target, set())
                for attr, tile in zip(all_attrs, all_tiles)
            )
            if meta.get("D880") != target + 2:
                failures.append(
                    f"stage {target + 1}: D880={meta.get('D880')} expected {target + 2}"
                )
            if bad:
                failures.append(f"stage {target + 1}: unexpected attrs {bad}")
            if unsafe:
                failures.append(f"stage {target + 1}: {unsafe} unsafe attribute bytes")
            if 5 in allowed and lava_count == 0:
                failures.append(f"stage {target + 1}: audited lava palette is absent")
            if lava_mismatches:
                failures.append(
                    f"stage {target + 1}: {lava_mismatches} lava attrs map to non-lava tiles"
                )
            print(
                f"Stage {target + 1}: attrs={counts} unsafe={unsafe} "
                f"lava={lava_count} lava_mismatch={lava_mismatches}"
            )

    if failures:
        print("\nFAIL:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("\nPASS: later stages use only neutral attrs plus vetted Stage 5/7 lava.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
