#!/usr/bin/env python3
"""Build hash-bound, non-promotable later-stage prelude speed controls.

These controls operate only on an already-qualified combined image.  They are
used to attribute steady-VBlank cost before implementing a semantic-preserving
production fast path; no output from this script is release eligible.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import build_v302_title_fix as build  # noqa: E402
from menu_icon_colorization import _menu_owned_prelude  # noqa: E402


BANK_SIZE = 0x4000
BANK13 = 13 * BANK_SIZE
PRELUDE_OFFSET = BANK13 + build.COLORIZE_PRELUDE_ADDR - 0x4000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def header_checksum(rom: bytes | bytearray) -> int:
    value = 0
    for byte in rom[0x0134:0x014D]:
        value = (value - byte - 1) & 0xFF
    return value


def global_checksum(rom: bytes | bytearray) -> int:
    return (
        sum(rom[:0x014E]) + sum(rom[0x0150:])
    ) & 0xFFFF


def replace_once(blob: bytearray, old: bytes, new: bytes, name: str) -> None:
    if len(old) != len(new):
        raise AssertionError(f"{name}: replacement width changed")
    count = blob.count(old)
    if count != 1:
        raise AssertionError(f"{name}: expected one preimage, found {count}")
    offset = blob.index(old)
    blob[offset:offset + len(old)] = new


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("minimal", "skip-bg0-repair", "skip-arena-tail", "skip-both"),
        required=True,
    )
    args = parser.parse_args()

    base = args.base.resolve()
    rom = bytearray(base.read_bytes())
    if len(rom) != 32 * BANK_SIZE:
        raise SystemExit(f"expected 512 KiB combined ROM, got {len(rom)} bytes")

    expected = _menu_owned_prelude(build.build_colorize_prelude())
    actual = bytes(rom[PRELUDE_OFFSET:PRELUDE_OFFSET + len(expected)])
    if actual != expected:
        raise SystemExit("qualified menu-owned prelude preimage moved")

    patched = bytearray(actual)
    changes: list[str] = []
    if args.mode == "minimal":
        _, level_select_tail = build.build_levelsel_rom_transition()
        if not patched.endswith(level_select_tail):
            raise SystemExit("ROM-resident GAME START continuation moved")
        executable_length = len(patched) - len(level_select_tail)
        patched[:executable_length] = bytes([
            0xCD,
            build.SCENE_DETECT_ADDR & 0xFF,
            build.SCENE_DETECT_ADDR >> 8,
            0xC9,
        ]) + bytes(executable_length - 4)
        changes.append("scene-detect-only")
    else:
        if args.mode in {"skip-bg0-repair", "skip-both"}:
            replace_once(
                patched,
                bytes([
                    0xCD,
                    build.LATER_STAGE_BG0_REPAIR_ADDR & 0xFF,
                    build.LATER_STAGE_BG0_REPAIR_ADDR >> 8,
                ]),
                bytes(3),
                "later-stage BG0 repair call",
            )
            changes.append("skip-bg0-repair")
        if args.mode in {"skip-arena-tail", "skip-both"}:
            replace_once(
                patched,
                bytes([
                    0x23,
                    0x2B,
                    0xC3,
                    build.ARENA_ATTR_SEMANTIC_CHANGED_ADDR & 0xFF,
                    build.ARENA_ATTR_SEMANTIC_CHANGED_ADDR >> 8,
                ]),
                bytes([0x23, 0x2B, 0xC9, 0x00, 0x00]),
                "arena semantic tail",
            )
            changes.append("skip-arena-tail")

    rom[PRELUDE_OFFSET:PRELUDE_OFFSET + len(patched)] = patched
    rom[0x014D] = header_checksum(rom)
    checksum = global_checksum(rom)
    rom[0x014E:0x0150] = checksum.to_bytes(2, "big")

    output = args.output.resolve()
    receipt = args.receipt.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(rom)
    report = {
        "schema": "penta-later-prelude-speed-control-v1",
        "status": "non-promotable-control",
        "mode": args.mode,
        "changes": changes,
        "base": str(base),
        "base_sha256": sha256(base.read_bytes()),
        "output": str(output),
        "output_sha256": sha256(rom),
        "prelude_offset": PRELUDE_OFFSET,
        "prelude_length": len(expected),
        "changed_bytes": sum(a != b for a, b in zip(actual, patched)),
    }
    receipt.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
