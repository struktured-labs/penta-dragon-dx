#!/usr/bin/env python3
"""Prove live-editor YAML colors bake into and run from a fresh release ROM."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = ROOT / "palettes/penta_palettes_v097.yaml"
DEFAULT_ROM = ROOT / "rom/working/penta_dragon_dx_FIXED.gb"
BUILDER = ROOT / "scripts/build_v302_title_fix.py"
PROBE = Path(__file__).with_name("probe_palette_build_roundtrip.lua")
BANK13 = 13 * 0x4000

TUNED = {
    ("bg_palettes", "Dungeon"): ["7FFF", "6A10", "3508", "0000"],
    ("bg_palettes", "BG7"): ["7FFF", "4210", "2108", "0000"],
    ("obj_palettes", "SaraWitch"): ["0000", "1234", "2345", "0001"],
    ("obj_palettes", "SaraWitchJet"): ["0000", "1123", "2456", "3001"],
    ("obj_palettes", "SaraDragonJet"): ["0000", "0765", "1ABC", "2DEF"],
    ("boss_palettes", "Gargoyle"): ["0000", "1111", "2222", "3333"],
    ("boss_palettes", "Boss3_Crimson"): ["0000", "0D1F", "0918", "0410"],
    ("powerup_palettes", "SpiralProjectile"): [
        "0000", "1023", "2045", "3067"
    ],
    ("powerup_palettes", "ShieldProjectile"): [
        "0000", "1765", "2543", "3321"
    ],
    ("powerup_palettes", "TurboProjectile"): ["0000", "1357", "2468", "0123"],
}


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def palette_bytes(colors: list[str]) -> bytes:
    result = bytearray()
    for color in colors:
        value = int(color, 16) & 0x7FFF
        result.extend((value & 0xFF, value >> 8))
    return bytes(result)


def replace_palettes(text: str) -> str:
    lines = text.splitlines(keepends=True)
    section = None
    palette = None
    replaced: set[tuple[str, str]] = set()
    for index, line in enumerate(lines):
        section_match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if section_match:
            section = section_match.group(1)
            palette = None
            continue
        palette_match = re.match(r"^  ([A-Za-z_][A-Za-z0-9_]*):\s*$", line)
        if palette_match:
            palette = palette_match.group(1)
            continue
        key = (section, palette)
        if key not in TUNED:
            continue
        color_match = re.match(
            r'^(\s*colors:\s*)\[[^\]]*\](\s*(?:#.*)?)((?:\r?\n)?)$',
            line,
        )
        if not color_match:
            continue
        colors = ", ".join(f'"{value}"' for value in TUNED[key])
        lines[index] = (
            f"{color_match.group(1)}[{colors}]"
            f"{color_match.group(2)}{color_match.group(3)}"
        )
        replaced.add(key)
    missing = set(TUNED) - replaced
    if missing:
        raise RuntimeError(f"could not tune YAML entries: {sorted(missing)}")
    return "".join(lines)


def parse_report(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if "=" in line
    )


def run_probe(
    mgba: str,
    rom: Path,
    output: Path,
    expected_bg0: bytes,
    expected_bg7: bytes,
    expected_obj2: bytes,
    timeout: float,
) -> dict[str, str]:
    report = Path(str(output) + ".report")
    done = Path(str(output) + ".done")
    report.unlink(missing_ok=True)
    done.unlink(missing_ok=True)
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="offscreen",
        SDL_AUDIODRIVER="dummy",
        PENTA_ROUNDTRIP_OUT=str(output),
        PENTA_EXPECTED_BG0=",".join(f"{byte:02X}" for byte in expected_bg0),
        PENTA_EXPECTED_BG7=",".join(f"{byte:02X}" for byte in expected_bg7),
        PENTA_EXPECTED_OBJ2=",".join(f"{byte:02X}" for byte in expected_obj2),
    )
    process = subprocess.Popen(
        [mgba, "--fastforward", "--script", str(PROBE), str(rom)],
        cwd=rom.parent,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if done.is_file():
                break
            if process.poll() is not None:
                raise RuntimeError(
                    f"mGBA exited {process.returncode} before round-trip report"
                )
            time.sleep(0.05)
        else:
            raise TimeoutError(f"mGBA round-trip probe exceeded {timeout:g}s")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    if not report.is_file():
        raise RuntimeError("mGBA produced no palette round-trip report")
    return parse_report(report)


def verify_backup_helper(work: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "penta_roundtrip_builder", BUILDER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not import production builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    target = work / "backup-contract.gb"
    old_payload = b"old release candidate"
    new_payload = b"new audience palette candidate"
    target.write_bytes(old_payload)
    backup = module.write_output_with_backup(
        target,
        new_payload,
        backup_existing=True,
    )
    expected_hash = hashlib.md5(old_payload).hexdigest()[:8]
    if backup is None or backup.name != (
        f"backup-contract.prebuild_{expected_hash}.backup.gb"
    ):
        raise RuntimeError(f"unexpected rollback path: {backup}")
    if backup.read_bytes() != old_payload or target.read_bytes() != new_payload:
        raise RuntimeError("rollback backup did not preserve the previous ROM")
    second = module.write_output_with_backup(
        target,
        new_payload,
        backup_existing=True,
    )
    if second is not None:
        raise RuntimeError("unchanged rebuild created an unnecessary backup")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yaml", type=Path, default=DEFAULT_YAML)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_ROM)
    parser.add_argument(
        "--mgba", default=str(ROOT / "scripts/mgba-qt-singleflight")
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--keep", type=Path)
    args = parser.parse_args()
    if not args.yaml.is_file():
        parser.error(f"palette YAML not found: {args.yaml}")
    if not args.candidate.is_file():
        parser.error(f"release candidate not found: {args.candidate}")
    if not args.mgba:
        parser.error("mgba-qt was not found")

    candidate_hash = md5(args.candidate)
    temporary = tempfile.TemporaryDirectory(prefix="penta-palette-roundtrip-")
    work = Path(temporary.name)
    if args.keep:
        temporary.cleanup()
        work = args.keep.resolve()
        work.mkdir(parents=True, exist_ok=True)
        temporary = None

    try:
        tuned_yaml = work / "tuned-palettes.yaml"
        tuned_yaml.write_text(replace_palettes(args.yaml.read_text()))
        output_rom = work / "penta-roundtrip.gb"
        base_rom = work / "penta-roundtrip.base.gb"
        build = subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--palette-yaml",
                str(tuned_yaml),
                "--output",
                str(output_rom),
                "--base-output",
                str(base_rom),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if build.returncode:
            print("FAIL: tuned-YAML release build failed")
            print(build.stdout[-4000:])
            print(build.stderr[-4000:])
            return 1
        if not output_rom.is_file() or output_rom.stat().st_size != 262144:
            print("FAIL: builder did not produce a 256 KiB round-trip ROM")
            return 1

        rom = output_rom.read_bytes()
        palette_data = BANK13 + (0x6800 - 0x4000)
        bg0 = palette_bytes(TUNED[("bg_palettes", "Dungeon")])
        bg7 = palette_bytes(TUNED[("bg_palettes", "BG7")])
        obj2 = palette_bytes(TUNED[("obj_palettes", "SaraWitch")])
        witch_jet = palette_bytes(TUNED[("obj_palettes", "SaraWitchJet")])
        dragon_jet = palette_bytes(TUNED[("obj_palettes", "SaraDragonJet")])
        gargoyle = palette_bytes(TUNED[("boss_palettes", "Gargoyle")])
        boss3 = palette_bytes(TUNED[("boss_palettes", "Boss3_Crimson")])
        spiral = palette_bytes(
            TUNED[("powerup_palettes", "SpiralProjectile")]
        )
        shield = palette_bytes(
            TUNED[("powerup_palettes", "ShieldProjectile")]
        )
        turbo = palette_bytes(TUNED[("powerup_palettes", "TurboProjectile")])

        static_checks = {
            "BG0 source": rom[palette_data:palette_data + 8] == bg0,
            "title BG7 mask": rom[palette_data + 56:palette_data + 64] == bg0,
            "tuned BG7 source": rom[
                BANK13 + (0x68F8 - 0x4000):
                BANK13 + (0x68F8 - 0x4000) + 8
            ] == bg7,
            "OBJ2 source": rom[
                palette_data + 64 + 16:palette_data + 64 + 24
            ] == obj2,
            "Sara Witch Jet source": rom[
                BANK13 + (0x68D0 - 0x4000):
                BANK13 + (0x68D0 - 0x4000) + 8
            ] == witch_jet,
            "Sara Dragon Jet source": rom[
                BANK13 + (0x68D8 - 0x4000):
                BANK13 + (0x68D8 - 0x4000) + 8
            ] == dragon_jet,
            "Gargoyle source": rom[
                BANK13 + (0x6880 - 0x4000):
                BANK13 + (0x6880 - 0x4000) + 8
            ] == gargoyle,
            "Boss3 source": rom[
                BANK13 + (0x6880 - 0x4000) + 16:
                BANK13 + (0x6880 - 0x4000) + 24
            ] == boss3,
            "Spiral source": rom[
                BANK13 + (0x68E0 - 0x4000):
                BANK13 + (0x68E0 - 0x4000) + 8
            ] == spiral,
            "Shield source": rom[
                BANK13 + (0x68E8 - 0x4000):
                BANK13 + (0x68E8 - 0x4000) + 8
            ] == shield,
            "Turbo source": rom[
                BANK13 + (0x68F0 - 0x4000):
                BANK13 + (0x68F0 - 0x4000) + 8
            ] == turbo,
        }
        failed_static = [name for name, passed in static_checks.items() if not passed]
        if failed_static:
            print("FAIL: tuned YAML bytes missing from ROM: " + ", ".join(failed_static))
            return 1

        report = run_probe(
            args.mgba,
            output_rom,
            work / "runtime",
            bg0,
            bg7,
            obj2,
            args.timeout,
        )
        verify_backup_helper(work)
        expected_fields = (
            "title_bg0_match",
            "title_bg7_masked",
            "gameplay_bg0_match",
            "gameplay_bg7_match",
            "gameplay_obj2_match",
        )
        failures = [
            f"{field}={report.get(field)!r}"
            for field in expected_fields
            if report.get(field) != "1"
        ]
        if report.get("status") != "ok":
            failures.append(
                f"status={report.get('status')!r} "
                f"message={report.get('message')!r}"
            )
        if report.get("d880") != "02" or report.get("ffc1") != "1":
            failures.append(
                f"runtime ended at D880={report.get('d880')} "
                f"FFC1={report.get('ffc1')}"
            )
        if md5(args.candidate) != candidate_hash:
            failures.append("workspace release candidate changed during test")
        if failures:
            print("FAIL: palette build round-trip")
            for failure in failures:
                print(f"  - {failure}")
            return 1

        print(
            "PASS: edited BG0/BG7/OBJ2, both Jet, Gargoyle/Boss3, and all "
            "powerup YAML bytes reached the ROM"
        )
        print("PASS: title kept the BG7 boot mask; gameplay restored tuned BG7")
        print("PASS: tuned BG0 and OBJ2 reached live mGBA CRAM")
        print("PASS: production rebuild preserves a hash-named rollback ROM")
        print(f"PASS: workspace candidate stayed {candidate_hash}")
        if args.keep:
            print(f"Artifacts: {work}")
        return 0
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
