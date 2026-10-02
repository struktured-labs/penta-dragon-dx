#!/usr/bin/env python3
"""Prototype: trim DX VBlank overhead without changing what is drawn (issue #49).

Applies byte patches to a release-lock candidate (expected SHA-256 792319cb...)
and writes a new ROM. Every patch is guarded by an exact preimage check.

P1  bank 0 $082E  CALL $73FC -> CALL $7464 (skip the JP $7464 hop, -32 units/frame)
P2  bank 13 $76EE  fast path for the pending-LCDC request (C4&$60 == $40) at
    VBlank start: the bank-19 helper ($19:6C80) is a no-op for that request
    (it only runs a GDMA for $20, and its LCDC-off/D880==1 branches are kept),
    so the trampoline round trip (~890 units) is skipped. LY is re-checked
    (< $93) so the decision matches the helper's own LY read ~440 units later.
    The 12-byte helper at $76AE moves to the dead pad at $76A8 to make room.
    Only state difference: the trampoline's write of $0D to DC09, a
    write-only stock variable (no literal or indexed readers in stock or DX).
P3  bank 13 $6EF4  INC HL / DEC HL / JP $572C -> JP $572C (-32 units/frame)
P4  bank 13 $6F82  CALL $6DA7 + 7 NOPs -> inline guard
    LD A,(D880); SUB 2; CP $13; CALL NC,$6DA7  (6DA7 returns at once for
    D880 in 2..$14; -136 units/frame in gameplay)
"""
from __future__ import annotations
import argparse, hashlib, sys
from pathlib import Path

EXPECTED = "792319cbe9db7d56ae6497018b727c8a0a8737c3c8c7a4a122713054677022db"

def off(bank: int, addr: int) -> int:
    return addr if addr < 0x4000 else bank * 0x4000 + addr - 0x4000

def jr(src: int, dst: int) -> int:
    d = dst - (src + 2)
    assert -128 <= d <= 127, (hex(src), hex(dst))
    return d & 0xFF

PATCHES: dict[str, list[tuple[int, int, bytes, bytes]]] = {}

def add(name, bank, addr, old: bytes, new: bytes):
    assert len(new) <= len(old) or old == b"", name
    PATCHES.setdefault(name, []).append((bank, addr, old, new))

# P1
add("P1", 0, 0x082E, bytes.fromhex("cdfc73"), bytes.fromhex("cd6474"))

# P2: move helper 76AE (12 bytes) to 76A8; free 76B4..76C0 (13 bytes)
helper = bytes.fromhex("fafac4b72803" "3e08c9" "3e3fc9")
add("P2", 13, 0x76A8, bytes(6) + helper + bytes(7),
    helper + bytes(13))
add("P2", 13, 0x769B, bytes.fromhex("cdae76"), bytes.fromhex("cda876"))
FASTX, CALLX = 0x76B4, 0x76B8
blk = bytes([0xFE, 0x93, 0x38, jr(0x76B6, 0x7703)])          # CP $93 ; JR C,7703
blk += bytes.fromhex("3e19" "cd4708" "c38574")                 # LD A,$19; CALL $0847; JP $7485
assert len(blk) == 12
add("P2", 13, 0x76B4, bytes(12), blk)
old_76ee = bytes.fromhex("fa80d8" "3d" "2807" "f0c4" "e660" "ca1d6f" "3e19" "cd4708" "c38574")
new_76ee = bytes.fromhex("fa80d8" "3d") + bytes([0x28, jr(0x76F2, CALLX)])
new_76ee += bytes.fromhex("f0c4" "e660" "ca1d6f" "fe40") + bytes([0x20, jr(0x76FD, CALLX)])
new_76ee += bytes.fromhex("f044") + bytes([0x18, jr(0x7701, FASTX)])
assert len(new_76ee) == len(old_76ee) == 21
add("P2", 13, 0x76EE, old_76ee, new_76ee)

# P3
add("P3", 13, 0x6EF4, bytes.fromhex("232bc32c57"), bytes.fromhex("c32c570000"))

# P4
add("P4", 13, 0x6F82, bytes.fromhex("cda76d") + bytes(7),
    bytes.fromhex("fa80d8" "d602" "fe13" "d4a76d"))

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("rom", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--only", default="P1,P2,P3,P4")
    a = ap.parse_args()
    data = bytearray(a.rom.read_bytes())
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        print("unexpected input ROM", file=sys.stderr); return 2
    for name in a.only.split(","):
        for bank, addr, old, new in PATCHES[name]:
            o = off(bank, addr)
            assert bytes(data[o:o + len(old)]) == old, (name, hex(addr), data[o:o+len(old)].hex())
            data[o:o + len(new)] = new
    s = (sum(data) - data[0x14E] - data[0x14F]) & 0xFFFF
    data[0x14E], data[0x14F] = s >> 8, s & 0xFF
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_bytes(data)
    print(a.out, hashlib.sha256(data).hexdigest())
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
