#!/usr/bin/env python3
"""Verify all nine production boss arenas through mGBA.

The verifier recaptures curated, visually valid arena fixtures under the
untouched candidate ROM, then reloads every new state in a second mGBA process.
Every receipt includes a rendered PNG, an exact $CC00 table dump, and all 64
bytes of CGB BG palette RAM. Structurally trivial striped/white frames fail.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = ROOT / "tmp/boss_arena_palette_probe"
GENERATOR = ROOT / "scripts/diagnostics/generate_stream_boss_states.py"
RECEIPT_PROBE = ROOT / "scripts/diagnostics/probe_boss_state_receipt.lua"
ROM_BANK_SIZE = 0x4000
PALETTE_ROM_BANK = 13
ARENA_TABLE_BASE = 0x7200
BG_TABLE_SIZE = 0x100
BOSS_NAMES = (
    "shalamar",
    "riff",
    "crystal_dragon",
    "cameo",
    "ted",
    "troop",
    "faze",
    "angela",
    "penta_dragon",
)


def fields(path: Path) -> dict[str, str]:
    return dict(
        field.split("=", 1)
        for field in path.read_text().split()
        if "=" in field
    )


def expected_table(rom: bytes, target: int) -> bytes:
    offset = (
        PALETTE_ROM_BANK * ROM_BANK_SIZE
        + ARENA_TABLE_BASE
        + target * BG_TABLE_SIZE
        - ROM_BANK_SIZE
    )
    return rom[offset:offset + BG_TABLE_SIZE]


def palette_words(raw: bytes) -> tuple[int, ...]:
    return tuple(
        raw[index] | (raw[index + 1] << 8)
        for index in range(0, len(raw), 2)
    )


def audit_state(
    mgba: str,
    rom: Path,
    state: Path,
    prefix: Path,
    target: int,
    timeout: float,
) -> None:
    marker = Path(f"{prefix}.audit.done")
    environment = os.environ.copy()
    environment.update(
        BOSS_RECEIPT_OUT=str(prefix),
        BOSS_RECEIPT_FRAMES="60",
        BOSS_TARGET=str(target),
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
    )
    process = subprocess.Popen(
        [
            mgba,
            "--fastforward",
            "-t",
            str(state),
            "-C",
            f"savegamePath={prefix.parent}",
            "-C",
            f"savestatePath={prefix.parent}",
            str(rom),
            "--script",
            str(RECEIPT_PROBE),
        ],
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if marker.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(
                    f"boss {target}: mGBA exited {process.returncode}"
                )
            time.sleep(0.05)
        if not marker.is_file():
            raise TimeoutError(f"boss {target}: receipt reload timed out")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if marker.read_text().strip() != "ok":
        raise RuntimeError(f"boss {target}: receipt reload failed")


def run_probe(
    rom: Path,
    output: Path,
    mgba: str,
    timeout: float,
    states: Path | None = None,
) -> bool:
    output.mkdir(parents=True, exist_ok=True)
    states_root = states or output
    if states is None:
        completed = subprocess.run(
            [
                sys.executable,
                str(GENERATOR),
                str(rom),
                "--output",
                str(output),
                "--mgba",
                mgba,
                "--timeout",
                str(timeout),
                "--force",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=max(180.0, timeout * 12),
            check=False,
        )
        print(completed.stdout, end="")
        if completed.returncode:
            print(f"FAIL: boss-state generator exited {completed.returncode}")
            return False

    rom_bytes = rom.read_bytes()
    report: list[dict[str, object]] = []
    passed = True
    for target, name in enumerate(BOSS_NAMES):
        prefix = states_root / f"boss{target}_{name}"
        receipt = prefix.with_suffix(".report")
        screenshot = prefix.with_suffix(".png")
        state = prefix.with_suffix(".ss0")
        failures: list[str] = []
        if not receipt.is_file():
            failures.append("missing report")
            data: dict[str, str] = {}
        else:
            data = fields(receipt)
        try:
            audit_state(mgba, rom, state, prefix, target, timeout)
        except Exception as error:
            failures.append(str(error))
            audit: dict[str, str] = {}
        else:
            audit = fields(Path(f"{prefix}.audit.report"))

        expected_scene = f"{0x0C + target:02X}"
        if data.get("status") != "ok":
            failures.append(f"status={data.get('status')}")
        if data.get("d880") != expected_scene:
            failures.append(
                f"D880={data.get('d880')}, expected {expected_scene}"
            )
        if data.get("ffc1") != "1":
            failures.append(f"FFC1={data.get('ffc1')}")
        if not state.is_file() or state.stat().st_size < 1024:
            failures.append("generated savestate is missing or trivial")
        if audit.get("status") != "ok":
            failures.append(f"reload status={audit.get('status')}")
        if audit.get("d880") != expected_scene:
            failures.append(
                f"reload D880={audit.get('d880')}, expected {expected_scene}"
            )
        if audit.get("ffc1") != "1":
            failures.append(f"reload FFC1={audit.get('ffc1')}")
        try:
            generated_lcdc = int(data.get("lcdc", "0"), 16)
            audit_lcdc = int(audit.get("lcdc", "0"), 16)
        except ValueError:
            generated_lcdc = audit_lcdc = 0
        if not generated_lcdc & 0x80:
            failures.append(f"generated LCDC={generated_lcdc:02X}")
        if not audit_lcdc & 0x80:
            failures.append(f"reload LCDC={audit_lcdc:02X}")

        try:
            active_table = bytes.fromhex(audit.get("active_table", ""))
        except ValueError:
            active_table = b""
        wanted_table = expected_table(rom_bytes, target)
        table_mismatches = sum(
            actual != expected
            for actual, expected in zip(active_table, wanted_table)
        ) + abs(len(active_table) - len(wanted_table))
        if len(active_table) != 256 or any(value > 7 for value in active_table):
            failures.append("active table is missing or contains invalid slots")

        try:
            bg_cram = bytes.fromhex(audit.get("bg_cram", ""))
        except ValueError:
            bg_cram = b""
        words = palette_words(bg_cram) if len(bg_cram) == 64 else ()
        meaningful = set(words) - {0x0000, 0x7FFF}
        if len(bg_cram) != 64:
            failures.append(f"BG CRAM bytes={len(bg_cram)}, expected 64")
        if not meaningful:
            failures.append("BG CRAM contains no non-black/non-white colors")

        rendered_colors: Counter[tuple[int, int, int]] = Counter()
        if not screenshot.is_file() or screenshot.stat().st_size < 1000:
            failures.append("missing/structurally trivial rendered screenshot")
        else:
            with Image.open(screenshot) as source:
                rendered_colors.update(source.convert("RGB").getdata())
            if set(rendered_colors) == {(255, 255, 255)}:
                failures.append("rendered frame is pure white")
            # The known bad serialized landing is a five-color horizontal
            # stripe field. Ted's valid early arena frame legitimately has
            # six or seven colors before its animation exposes the full set;
            # keep this consistent with the exact-state generator.
            if len(rendered_colors) < 6:
                failures.append(
                    f"rendered frame has only {len(rendered_colors)} colors"
                )

        status = "PASS" if not failures else "FAIL"
        print(
            f"arena {target} ({name}): {status} | D880={data.get('d880')} "
            f"recapture_frame={data.get('frame')} "
            f"table_mismatches={table_mismatches} "
            f"meaningful_cram={len(meaningful)} "
            f"rendered_colors={len(rendered_colors)}"
        )
        for failure in failures:
            print(f"  - {failure}")
        passed &= not failures
        report.append(
            {
                "arena": target,
                "name": name,
                "scene": data.get("d880"),
                "recapture_frame": data.get("frame"),
                "active_table_mismatches": table_mismatches,
                "meaningful_bg_cram_words": len(meaningful),
                "rendered_colors": len(rendered_colors),
                "screenshot": str(screenshot),
                "state": str(state),
                "failures": failures,
            }
        )

    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"{'PASS' if passed else 'FAIL'}: {sum(not r['failures'] for r in report)}/9 boss arenas")
    print(f"Artifacts: {output}")
    return passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", nargs="?", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--states",
        type=Path,
        help="audit an already-generated exact-ROM nine-state directory",
    )
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if not args.mgba:
        parser.error("mgba-qt was not found")
    try:
        passed = run_probe(
            args.rom.resolve(),
            args.output.resolve(),
            args.mgba,
            args.timeout,
            args.states.resolve() if args.states else None,
        )
    except Exception as error:
        print(f"FAIL: mGBA boss verifier error: {error}")
        return 1
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
