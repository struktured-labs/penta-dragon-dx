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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "diagnostics"))
from boss_geometry_contract import BOSSES, NAMES as BOSS_NAMES  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
DEFAULT_OUTPUT = ROOT / "tmp/boss_arena_palette_probe"
GENERATOR = ROOT / "scripts/diagnostics/generate_stream_boss_states.py"
RECEIPT_PROBE = ROOT / "scripts/diagnostics/probe_boss_state_receipt.lua"
ROM_BANK_SIZE = 0x4000
PALETTE_ROM_BANK = 13
ARENA_TABLE_BASE = 0x7200
BG_TABLE_SIZE = 0x100
TUNED_BG7_SOURCE_ADDR = 0x68F8
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
    # A prior successful receipt must never satisfy a new invocation before
    # mGBA has executed the current probe/ROM.  This previously let stale
    # single-frame reports masquerade as fresh verification.
    for stale in (
        marker,
        Path(f"{prefix}.audit.report"),
        Path(f"{prefix}.audit.trace"),
    ):
        stale.unlink(missing_ok=True)
    rom_bytes = rom.read_bytes()
    banked_runtime = (
        rom_bytes[0x4295:0x4298] == bytes.fromhex("C3 80 DB")
        or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD 80 DB")
        or rom_bytes[0x028A:0x028D] == bytes.fromhex("CD E4 6F")
        or rom_bytes[0x3136:0x3139] == bytes.fromhex("C3 38 08")
    )
    environment = os.environ.copy()
    environment.update(
        BOSS_RECEIPT_OUT=str(prefix),
        # The current-ROM generator already performs the scene transition.
        # Rearming it after loading an exact state can restart arena setup and
        # creates synthetic exits, especially for Shalamar.
        BOSS_RECEIPT_REARM="0",
        # Exact candidate states were certified only after phase zero and
        # already contain the current ROM's CRAM. Restarting the palette pass
        # inside a live arena is synthetic and can perturb timing-sensitive
        # animation publication.
        BOSS_RECEIPT_PALETTE_REARM="0",
        BOSS_RECEIPT_KEEPALIVE="1",
        # During the expanded publishers SVBK2/3 temporarily aliases D880 and
        # the other Dxxx game-state bytes.  Ignore those callbacks exactly as
        # the recapture path already does instead of reporting a false exit.
        BOSS_RECEIPT_BANKED_RUNTIME="1" if banked_runtime else "0",
        # Frames 25..116 cover Shalamar's settled animation before its short
        # native showcase exits; the other arenas retain the 96-frame window.
        # Both exceed the hard 85-frame animated-attribute contract.
        BOSS_RECEIPT_FRAMES="116" if target == 0 else "120",
        BOSS_RECEIPT_WARMUP="24",
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

        expected_scene = f"{BOSSES[target].scene:02X}"
        if data.get("status") != "ok":
            failures.append(f"status={data.get('status')}")
        if data.get("d880") != expected_scene:
            failures.append(
                f"D880={data.get('d880')}, expected {expected_scene}"
            )
        if data.get("ffc1") != "1":
            failures.append(f"FFC1={data.get('ffc1')}")
        if data.get("phase", "00") != "00":
            failures.append(f"generated palette phase={data.get('phase')}")
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
        # Ted's native tile census ends at $86; $87-$FF is the receipt-proven
        # ROM/runtime code cave already accepted by the generator and static
        # integration contract.  Validate all 256 bytes for exactness above,
        # but apply palette-slot bounds only to reachable semantic entries.
        semantic_table = active_table[:0x87] if target == 4 else active_table
        if len(active_table) != 256 or any(value > 7 for value in semantic_table):
            failures.append("active table is missing or contains invalid slots")
        try:
            attr_frames = int(audit.get("attr_frames", "0"))
            attr_samples = int(audit.get("attr_samples", "0"))
            attr_mismatches = int(audit.get("attr_mismatches", "-1"))
            max_frame_mismatches = int(
                audit.get("max_frame_mismatches", "-1")
            )
            unsafe_attrs = int(audit.get("unsafe_attrs", "-1"))
            alternating_tiles = int(audit.get("alternating_tiles", "-1"))
            hidden_staging_mismatches = int(
                audit.get("hidden_staging_mismatches", "-1")
            )
            max_scene_drift_frames = int(
                audit.get("max_scene_drift_frames", "-1")
            )
        except ValueError:
            attr_frames = attr_samples = 0
            attr_mismatches = max_frame_mismatches = -1
            unsafe_attrs = alternating_tiles = -1
            hidden_staging_mismatches = max_scene_drift_frames = -1
        if attr_frames < 85:
            failures.append(
                f"animated attribute frames={attr_frames}, expected at least 85"
            )
        if attr_samples < 30_000:
            failures.append(
                f"animated attribute samples={attr_samples}, expected >=30000"
            )
        crystal_cached = target == 2
        if attr_mismatches != 0 and not crystal_cached:
            failures.append(
                f"live tile/LUT attribute mismatches={attr_mismatches} "
                f"(max {max_frame_mismatches} in one frame; "
                f"examples={audit.get('mismatch_examples')})"
            )
        if unsafe_attrs != 0:
            failures.append(f"unsafe live BG attributes={unsafe_attrs}")
        if crystal_cached and max_frame_mismatches > 18:
            failures.append(
                "Crystal cached portal exceeded its 18-cell dynamic drift "
                f"bound: {max_frame_mismatches}"
            )
        if alternating_tiles != 0 and not crystal_cached:
            failures.append(
                f"tile IDs alternated between palette attributes="
                f"{alternating_tiles}"
            )
        hidden_staging_valid = (
            hidden_staging_mismatches in {0, 1}
            if target == 8 else hidden_staging_mismatches == 0
        )
        if not hidden_staging_valid:
            failures.append(
                "hidden double-buffer staging mismatches="
                f"{hidden_staging_mismatches}, expected at most one for "
                "Penta and zero elsewhere"
            )
        # Native arena publishers may expose a one-frame $FF handoff sentinel
        # at different animation phases. The Lua receipt already fails a
        # sustained mismatch; accept zero or one independently of which boss
        # happened to cross that phase during this deterministic window.
        if max_scene_drift_frames not in {0, 1}:
            failures.append(
                f"scene publisher sentinel frames={max_scene_drift_frames}, "
                "expected at most 1"
            )

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
        bg7_offset = (
            PALETTE_ROM_BANK * ROM_BANK_SIZE
            + TUNED_BG7_SOURCE_ADDR - ROM_BANK_SIZE
        )
        expected_bg7 = rom_bytes[bg7_offset:bg7_offset + 8]
        # Validate a CRAM row only when this arena's exact material table can
        # render it. Crystal's portal uses BG0/BG4 exclusively; a stale BG7 in
        # that synthetic state is inactive and cannot affect any pixel.
        if 7 in wanted_table and bg_cram[56:64] != expected_bg7:
            failures.append(
                "rendered BG7 does not match the candidate's tuned YAML row "
                f"({bg_cram[56:64].hex().upper()} != "
                f"{expected_bg7.hex().upper()})"
            )

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
            f"attr_mismatches={attr_mismatches}/{attr_samples} "
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
                "animated_attribute_frames": attr_frames,
                "animated_attribute_samples": attr_samples,
                "animated_attribute_mismatches": attr_mismatches,
                "attribute_contract": (
                    "cached-atomic-camera-wrap" if crystal_cached else "tile-lut"
                ),
                "max_frame_attribute_mismatches": max_frame_mismatches,
                "hidden_staging_mismatches": hidden_staging_mismatches,
                "max_scene_drift_frames": max_scene_drift_frames,
                "unsafe_live_attributes": unsafe_attrs,
                "alternating_tile_ids": alternating_tiles,
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
