#!/usr/bin/env python3
"""r446: route the later-stage stock copy through the qualified bank28 five-tile helper.

bank1 $42BB `LD A,$18; PUSH AF; LD C,$06; JP $4330` is the entry of the DX stock-clone
copy loop (4 tiles per HBlank window, 144 windows per publication) used by every
publication that reaches `$13DE JP $42BB` (all stages whose bank27 decision is not the
Stage-1 mode-C path).  The Stage-1 mode-C path already enters the bank28 helper via
`$42C6 POP AF; LD A,$1C; CALL $0847; JP $42ED`, and r445c made that helper a
(5,5,5,5,4)-tile row loop (120 windows, worst case 39 <= 41.75 cycles), live-qualified
on Stage 1 (665/667).  Its contract equals the bank1 loop's: DE:=$C1A0 set inside, HL
from the caller ($42A7: page in H, L=0), row counter pushed/popped internally, exit with
H = end-of-copy page byte, C=0, A=1 (bank restore for $0847), Z=1; continuation $42ED.
This composer replaces the 8 bytes at $42BB with the same 8 bytes that already sit at
$42C7 (`LD A,$1C; CALL $0847; JP $42ED`), so every $42BB entrant now runs the helper.
The old loop body ($42C3..$42EC, $4330..$4350) stays in place (still reachable only from
itself) and the bank28 helper's scene-$02 VBlank shortcut semantics are unchanged.
Byte scope: bank1 $42BB..$42C2 + checksums.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

SITE = 0x42BB
OLD = bytes.fromhex("3E 18 F5 0E 06 C3 30 43")
NEW = bytes.fromhex("3E 1C CD 47 08 C3 ED 42")
HELPER_SHA = "8680e5f6eda6acd70e30666002c6d91a2423f63e30c4c58d6922e153435c1502"   # sha256 of the exact 240-byte r445c helper (bank28 $6C80..$6D6F)


def update_checksums(rom):
    h = 0
    for v in rom[0x134:0x14D]: h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", type=Path, required=True); ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--helper-sha", default=HELPER_SHA, help="sha256 of the bank28 helper image the base must carry (default: r445c 240 B)")
    ap.add_argument("--helper-len", type=int, default=240)
    a = ap.parse_args(); src = a.base.read_bytes()
    assert src[SITE:SITE + 8] == OLD, "bank1 $42BB loop entry preimage differs"
    assert src[0x42C6:0x42CF] == bytes.fromhex("F1") + NEW, "mode-C helper entry at $42C6 differs"
    assert src[0x0847:0x0850] == bytes.fromhex("CD 61 00 CD 80 6C C3 61 00"), "$0847 dispatcher changed"
    h = src[28 * 0x4000 + 0x2C80:28 * 0x4000 + 0x2C80 + a.helper_len]
    assert hashlib.sha256(h).hexdigest() == a.helper_sha, "bank28 helper image digest mismatch"
    assert set(src[28 * 0x4000 + 0x2C80 + a.helper_len:28 * 0x4000 + 0x2C80 + a.helper_len + 16]) == {0xFF}
    rom = bytearray(src); rom[SITE:SITE + 8] = NEW; update_checksums(rom)
    changed = sorted(i for i in range(len(src)) if src[i] != rom[i])
    assert set(changed) <= set(range(SITE, SITE + 8)) | {0x14D, 0x14E, 0x14F}, changed
    a.out_dir.mkdir(parents=True, exist_ok=True)
    t = a.out_dir / "candidate.gb"
    if t.exists() and t.read_bytes() != bytes(rom): raise SystemExit("candidate collision")
    t.write_bytes(bytes(rom))
    rec = {"schema": "penta-compose-later-stage-bank28-copy-r446-v1", "base_sha256": hashlib.sha256(src).hexdigest(),
           "candidate_sha256": hashlib.sha256(rom).hexdigest(), "changed_offsets": changed,
           "patch": f"bank1 ${SITE:04X}: {OLD.hex()} -> {NEW.hex()} (= the $42C7 mode-C helper entry)",
           "helper": f"bank28 $6C80.. ({a.helper_len} B, sha256 {a.helper_sha[:16]}), exit A=1,C=0,Z=1, H=end page", "live_tested": False}
    (a.out_dir / "build-receipt.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("candidate_sha256", "changed_offsets")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
