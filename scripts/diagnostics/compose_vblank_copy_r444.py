#!/usr/bin/env python3
"""Compose Astra's r444 later-stage VBlank tile-copy shortcut onto an existing candidate.

r444 (build_later_vblank_copy_r444.py, exact r443d) replaces the scene-$02-only predicate
of the DX copy cave, bank1 $4331..$4335 `LD A,($D880); CP $02`, with `XOR A; NOP x4`, so
the existing `JR NZ,$4340` never skips the LY 144..151 VBlank branch: every scene copies
4 tiles per group without a STAT wait while in VBlank (vanilla and DX stages other than
Stage 1 previously idled through the whole VBlank).  The fallback STAT wait and the
4-tile group are untouched.  This composer applies exactly those 5 bytes (+ header
checksums) to any base whose $4330..$434F cave is byte-identical to r443d's, and proves
the byte scope in the receipt.  Experiment only: never replaces an existing candidate.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

SITE, OLD, NEW = 0x4331, bytes.fromhex("FA 80 D8 FE 02"), bytes.fromhex("AF 00 00 00 00")
CAVE = bytes.fromhex("F3 FA 80 D8 FE 02 20 08 F0 44 E6 F8 FE 90 28 0E F0 41 E6 03 FE 03 20 F8 F0 41 E6 03 20 FA C3 CF 42")


def update_checksums(rom: bytearray) -> None:
    h = 0
    for v in rom[0x134:0x14D]: h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True); ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args(); src = a.base.read_bytes()
    assert src[0x4330:0x4330 + len(CAVE)] == CAVE, "DX copy cave $4330.. is not the r443d image"
    rom = bytearray(src); rom[SITE:SITE + 5] = NEW; update_checksums(rom)
    changed = sorted(i for i in range(len(src)) if src[i] != rom[i])
    assert set(changed) <= set(range(SITE, SITE + 5)) | {0x14D, 0x14E, 0x14F}, changed
    a.out_dir.mkdir(parents=True, exist_ok=True)
    t = a.out_dir / "candidate.gb"
    if t.exists() and t.read_bytes() != bytes(rom): raise SystemExit("candidate collision")
    t.write_bytes(bytes(rom))
    rec = {"schema": "penta-compose-vblank-copy-r444-v1", "base_sha256": hashlib.sha256(src).hexdigest(),
           "candidate_sha256": hashlib.sha256(rom).hexdigest(), "changed_offsets": changed,
           "patch": f"bank1 ${SITE:04X}: {OLD.hex()} -> {NEW.hex()} (r444 predicate removal)", "live_tested": False}
    (a.out_dir / "build-receipt.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("candidate_sha256", "changed_offsets")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
