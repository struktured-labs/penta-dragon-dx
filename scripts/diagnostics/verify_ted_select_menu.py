#!/usr/bin/env python3
"""#73 regression: Ted Select must show the real pause-menu chrome for frames 1-300.

Loads the ted-entry savestate, holds Select on frames 8-13, and screenshots
every frame through 300. Fails if the 120-byte C4E0 deck does not start with
the stock 00:212E chrome (12 x EF) once the menu has settled, or if any of
the 300 screenshots is missing. Attract is not exercised.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROBE = Path(__file__).with_name("probe_ted_select_menu.lua")
MGBA = ROOT / "scripts/mgba-qt-singleflight"
OFFICIAL_JP_SHA = "91d58599d3df5dde80131ce20d0a639d7056d015dc91cedd2e699b66a141ba18"
OFFICIAL_EN_SHA = "631b24a4fadb6257581cd6a4b5d951d68c47990a002b2418ce02dae00645c464"
CHROME = bytes([0xEF] * 12)
FRAMES = 300


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def update_checksums(rom: bytearray) -> None:
    header = 0
    for value in rom[0x0134:0x014D]:
        header = (header - value - 1) & 0xFF
    rom[0x014D] = header
    rom[0x014E:0x0150] = ((sum(rom[:0x014E]) + sum(rom[0x0150:])) & 0xFFFF).to_bytes(2, "big")


def apply_english_delta(jp: bytes, official_jp: bytes, official_en: bytes) -> bytes:
    if sha(official_jp) != OFFICIAL_JP_SHA or sha(official_en) != OFFICIAL_EN_SHA:
        raise ValueError("official JP/EN translation pair identity differs")
    if len(jp) != len(official_jp) or len(official_jp) != len(official_en):
        raise ValueError("JP/EN translation pair size differs")
    out = bytearray(jp)
    for i, (a, b) in enumerate(zip(official_jp, official_en)):
        if a != b and i not in (0x14D, 0x14E, 0x14F):
            out[i] = b
    update_checksums(out)
    return bytes(out)


def find_official_pair() -> tuple[Path, Path] | None:
    candidates = [
        (ROOT / "tmp/roms-main/JP.gbc", ROOT / "tmp/roms-main/EN.gbc"),
        (ROOT / "rom/working/penta_dragon_dx_FIXED.gb",
         ROOT / "rom/working/penta_dragon_dx_en.gb"),
    ]
    for jp, en in candidates:
        if jp.is_file() and en.is_file() and sha(jp.read_bytes()) == OFFICIAL_JP_SHA \
                and sha(en.read_bytes()) == OFFICIAL_EN_SHA:
            return jp, en
    return None


def run_probe(rom: Path, state: Path, output: Path, env: dict[str, str]) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(rom, output / "rom.gb")
    shutil.copy2(state, output / "identity.ss0")
    command = [
        str(MGBA),
        "--fastforward",
        "-t", str(output / "identity.ss0"),
        "--script", str(PROBE.resolve()),
        str(output / "rom.gb"),
    ]
    child = dict(env)
    for key in ("PENTA_MGBA_LOCK", "PENTA_MGBA_QT_BIN"):
        child.pop(key, None)
    child["TED_SELECT_OUT"] = str(output)
    child["QT_QPA_PLATFORM"] = "offscreen"
    child["SDL_AUDIODRIVER"] = "dummy"
    child.pop("WAYLAND_DISPLAY", None)
    result = subprocess.run(command, cwd=str(ROOT), env=child, check=False,
                            timeout=120)
    shots = [output / f"frame-{n:04d}.png" for n in range(1, FRAMES + 1)]
    missing = [p.name for p in shots if not p.is_file() or p.stat().st_size == 0]
    chrome = {}
    for tag in ("f0070", "f0300"):
        blob = output / f"c4e0_{tag}.bin"
        data = blob.read_bytes() if blob.is_file() else b""
        chrome[tag] = {
            "present": blob.is_file(),
            "prefix_ef": data[:12] == CHROME,
            "sha256": sha(data) if data else None,
        }
    return {
        "rom_sha256": sha(rom.read_bytes()),
        "returncode": result.returncode,
        "shots": FRAMES - len(missing),
        "missing": missing[:8],
        "chrome": chrome,
        "settled": chrome.get("f0070", {}).get("sha256") == chrome.get("f0300", {}).get("sha256")
                   and chrome.get("f0070", {}).get("prefix_ef") is True,
    }


def evaluate(report: dict, label: str) -> list[str]:
    errors = []
    if report["shots"] != FRAMES or report["missing"]:
        errors.append(f"{label}: missing Ted Select screenshots {report['missing']}")
    if not report["chrome"].get("f0070", {}).get("prefix_ef"):
        errors.append(f"{label}: C4E0 at frame 70 is not the 212E chrome")
    if not report["chrome"].get("f0300", {}).get("prefix_ef"):
        errors.append(f"{label}: C4E0 at frame 300 is not the 212E chrome")
    if not report["settled"]:
        errors.append(f"{label}: Ted Select menu did not settle with chrome through frame 300")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--en-rom", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    reports = {}
    errors = []
    if not args.state.is_file():
        errors.append(f"Ted entry savestate missing: {args.state}")
    else:
        reports["jp"] = run_probe(args.rom.resolve(), args.state.resolve(), output / "jp", env)
        errors.extend(evaluate(reports["jp"], "JP"))
        en_path = args.en_rom
        if en_path is None:
            pair = find_official_pair()
            if pair is not None:
                en_bytes = apply_english_delta(
                    args.rom.read_bytes(), pair[0].read_bytes(), pair[1].read_bytes())
                en_path = output / "en-applied.gbc"
                en_path.write_bytes(en_bytes)
        if en_path is not None:
            reports["en"] = run_probe(en_path.resolve(), args.state.resolve(), output / "en", env)
            errors.extend(evaluate(reports["en"], "EN"))
        else:
            errors.append("EN ROM was not provided and the official JP/EN pair was not found")
    (output / "receipt.json").write_text(json.dumps({
        "schema": "penta-ted-select-menu-v1",
        "reports": reports,
        "errors": errors,
    }, indent=2) + "\n")
    if errors:
        print("FAIL: " + "; ".join(errors), file=sys.stderr)
        return 1
    print(json.dumps({"status": "PASS", "reports": reports}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
