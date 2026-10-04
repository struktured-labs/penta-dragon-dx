#!/usr/bin/env python3
"""Continue-into-miniboss BG palette reload (prototype on exact 792319cb main).

Bug: a death during a miniboss fight followed by Continue resumes straight into
scene D880=$0A (FFBF still set).  DX's deferred BG reload request $DF5D is raised
only by the scene-02 entry hook (bank13 $7D18 -> $7719) and consumed by the
VBlank commit gate ($7703) only while D880==$02, so the death/white-fade CRAM
(all eight BG palettes FFFF/FFFF/7E1F/294A, byte-shifted) survives until the
miniboss dies and the native publisher writes D880=$02.  Visible result: flat
pink room/HUD after Continue in any miniboss fight.

Fix (bank 13 + one private routine):
  $7703 gate : accept D880 AND $F7 == $02 (scenes $02 and $0A), same 22 bytes.
               The palette sequencer's BG writer ($71B6) already treats $0A as
               $02 the same way.  Power-on safety is unchanged: $0A is reachable
               only after a scene-02 entry, which raises and consumes the flag.
  $7D18      : scene-02 path jumps straight to its continuation $7D26.
  $7D35      : common hook tail CALL $6D9E -> CALL $7719.
  $7719 cave : PUSH AF; LD A,$27; CALL $0847; POP AF; JP $6D9E  (10 bytes,
               exactly the old 7-byte setter plus its 3 free bytes).
  bank $27:$6C80 (via the existing $0847 bank-call ABI used by $76FB):
               raise $DF5D:=1 when D880==$02 (old behaviour) or when D880==$0A
               and the previous observed scene $DF0D==$17 (Continue out of the
               death sequence).  Miniboss spawn ($02->$0A) and kill ($0A->$02)
               keep their exact old behaviour.  Returns A=$0D for $0847.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = "792319cbe9db7d56ae6497018b727c8a0a8737c3c8c7a4a122713054677022db"
PRIVATE_BANK = 0x27
PRIVATE_ENTRY = 0x6C80
CHECKSUMS = frozenset((0x014D, 0x014E, 0x014F))

GATE_OLD = bytes.fromhex("FA80D8 FE02 C22D74 FA5DDF 3D C22D74 AF EA5DDF C30F74")
GATE_NEW = bytes.fromhex(
    "FA5DDF"    # 7703 LD A,[DF5D]
    "3D"        # 7706 DEC A
    "C22D74"    # 7707 JP NZ,742D      (no request)
    "FA80D8"    # 770A LD A,[D880]
    "E6F7"      # 770D AND F7          ($02 and $0A)
    "D602"      # 770F SUB 02          (A=0 on match)
    "20F4"      # 7711 JR NZ,7707      (Z clear -> JP NZ,742D)
    "EA5DDF"    # 7713 LD [DF5D],A     (consume: A=0)
    "C30F74")   # 7716 JP 740F
SETTER_OLD = bytes.fromhex("3C EA5DDF C3267D 000000")
CAVE_NEW = bytes.fromhex("F5 3E27 CD4708 F1 C39E6D")
HOOK02_OLD = bytes.fromhex("C31977 0000")
HOOK02_NEW = bytes.fromhex("C3267D 0000")
TAIL_OLD = bytes.fromhex("CD9E6D")
TAIL_NEW = bytes.fromhex("CD1977")
PRIVATE = bytes.fromhex(
    "FA80D8"    # LD A,[D880]
    "FE02"      # CP 02
    "280B"      # JR Z,set
    "FE0A"      # CP 0A
    "200C"      # JR NZ,done
    "FA0DDF"    # LD A,[DF0D]   previous observed scene (written after the hook)
    "FE17"      # CP 17
    "2005"      # JR NZ,done
    "3E01"      # set: LD A,1
    "EA5DDF"    # LD [DF5D],A
    "3E0D"      # done: LD A,0D  (bank for $0847's JP $0061)
    "C9")


def off(bank, addr): return bank * 0x4000 + addr - 0x4000


def update_checksums(rom):
    h = 0
    for v in rom[0x134:0x14D]: h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


def build(source: bytes, base_sha: str = BASE_SHA):
    assert hashlib.sha256(source).hexdigest() == base_sha, "wrong exact base"
    assert source[0x147] == 0x1B and source[0x148] == 0x05, "MBC5 1 MiB expected"
    b13 = lambda a, n: source[off(13, a):off(13, a) + n]
    assert b13(0x7703, 22) == GATE_OLD, "gate preimage"
    assert b13(0x7719, 10) == SETTER_OLD, "setter/cave preimage"
    assert b13(0x7D18, 5) == HOOK02_OLD, "scene-02 hook preimage"
    assert b13(0x7D35, 3) == TAIL_OLD, "hook tail preimage"
    assert b13(0x6D9E, 8) == bytes.fromhex("AF EA49DF EA4BDF C9"), "tail callee"
    assert source[0x0847:0x0850] == bytes.fromhex("CD6100 CD806C C36100"), "bank-call ABI"
    assert set(source[off(PRIVATE_BANK, 0x4000):off(PRIVATE_BANK, 0x8000)]) == {0xFF}, "private bank not free"
    # Only the gate, the old setter and the private routine may name DF5D.
    for i in range(len(source) - 2):
        if source[i] in (0xEA, 0xFA) and source[i + 1] == 0x5D and source[i + 2] == 0xDF:
            assert off(13, 0x7703) <= i < off(13, 0x7723), f"DF5D referenced at {i:#x}"
    rom = bytearray(source); owned = set()
    def put(o, data):
        rom[o:o + len(data)] = data; owned.update(range(o, o + len(data)))
    put(off(13, 0x7703), GATE_NEW)
    put(off(13, 0x7719), CAVE_NEW)
    put(off(13, 0x7D18), HOOK02_NEW)
    put(off(13, 0x7D35), TAIL_NEW)
    put(off(PRIVATE_BANK, PRIVATE_ENTRY), PRIVATE)
    assert len(GATE_NEW) == 22 and len(CAVE_NEW) == 10
    update_checksums(rom)
    changed = {i for i, (x, y) in enumerate(zip(source, rom)) if x != y}
    assert changed <= owned | CHECKSUMS
    return bytes(rom), {
        "schema": "penta-continue-miniboss-reload-proto-v1",
        "base_sha256": base_sha,
        "candidate_sha256": hashlib.sha256(rom).hexdigest(),
        "changed_offsets": [hex(i) for i in sorted(changed)],
        "live_tested": False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--base-sha", default=BASE_SHA)
    a = ap.parse_args()
    rom, receipt = build(a.base.read_bytes(), a.base_sha)
    a.out.write_bytes(rom)
    a.out.with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
