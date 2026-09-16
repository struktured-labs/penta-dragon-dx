#!/usr/bin/env python3
"""r443e: de-alias the DX deferred-palette-reload request from stock FFE1 (on exact r443d).

Why: FFE1 is a STOCK title/game-start state byte (GAME START sets 2 at b0:$11E8; the
VBlank chain $07A0 raises it to 3 after the DCF7 countdown; $11C3 dispatches 0/1/2/3+).
DX reused it: bank13 $7D18 sets FFE1:=1 on scene-02 entry and the ISR commit path
$7407/$740C tests and zeroes it.  Between the set (VBlank prelude) and the next commit,
the stock main loop can poll $11C3, see 1, and enter the NEW-GAME init ($11CE ->
$7CB8, ~280 frames).  r442 wins that race by phase luck; title v4 lost it (Stage 1
north +316 frames).  Fix: a DX-owned WRAM byte carries the request.

Allocation (proved against exact r443d, see tmp/title-color/audit/df5d_allocation_census.md):
  $DF5D (WRAM bank 1, next to DX's $DF5C SCX mirror).  Zero references in the DX ROM,
  the vanilla ROM and the WRAM-resident stubs (all 16-bit immediates + LD HL/DE/BC
  bases with their loop extents checked); still holds mGBA's power-on fill ($FF) in
  400/400 savestates across stages 2..7, i.e. never written.  Read/written only with
  SVBK=1 (ISR commit path and the transition hook, same guarantee r442 relies on for
  $DF08/$DF4C).  Protocol: exactly 1 = request pending; any other value = none, so an
  uninitialized $FF (or random hardware WRAM) cannot request a reload; the DF02
  one-shot init block also zeroes it.

Patches (bank13 unless noted):
  $7D18  INC A; LDH (FFE1),A; JR $7D26   -> JP cave_set ; NOP; NOP
  cave_set ($770E): INC A; LD ($DF5D),A; JP $7D26
  $7407  LDH A,(FFE1); OR A; JR Z,$742D  -> JP cave_test ; NOP; NOP
  $740C  XOR A; LDH (FFE1),A             -> NOP x3   (DX never touches FFE1 again)
  cave_test ($7701): LD A,($D880); CP $02; JP NZ,$742D; LD A,($DF5D); DEC A; JP NZ,$742D;
                     XOR A; LD ($DF5D),A; JP $740F
     Power-on ordering (r443e2): stock boot clears $C000..$DEFF and HRAM but NOT $DF00..
     $DFFF (b1:$400F LD BC,$1F00), so $DF5D is random on hardware and may equal 1, and
     the ISR commit consumer runs BEFORE the prelude's one-shot init in the same ISR.
     Hence the consumer also requires D880==2: the request is only ever raised by the
     scene-02 entry hook, $D880 IS boot-cleared, and the first commits happen on the
     title (scene $01), so a random pending value can never fire before a real scene-02
     entry, where the hook sets it anyway (worst case one extra reload); every consume
     clears it.  No boot-time init is required or performed.
  (r443e/e2 also patched the $6E12 one-shot init; WRONG: $6E2A is the `JR Z` join of
   that one-shot, so the shifted loop ran on every later cleaner call.  Removed in e3.)
Cave: bank13 $7701..$771D (top of the 77-byte zero run after RET $76D5), leaving
$76D6..$7700 for the title port (which must be composed with --no-fix-a on this base:
the reload can no longer fire on scene $01 because only the scene-02 hook sets the flag).
Dead code left untouched: bank31:$71D1 / bank21:$4000 (the old FFE1-testing $DBDF stub
image, copied only by bank31's dead installer $6F00; the live installer is bank13:$7CBF
whose $DBDF image $56E1 is `JP $3497`, asserted) and the bank16 mirrors.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/later-stage-deferred-dma-r443d/candidate.gb"
BASE_SHA = "7b3de7acf60614b958658b9f7f7139bb7b855dd23bc5f41c6c42d7322cead620"
OUT = ROOT / "tmp/reload-flag-dealias-r443e3"
FLAG = 0xDF5D
CAVE_TEST, CAVE_SET, CAVE_END = 0x7701, 0x7717, 0x7723   # r443e2 layout: test 22 B, set 7 B
CAVE_TEST_F, CAVE_SET_F = 0x7703, 0x7719               # on r443f the pretest owns $76EE..$7702
CHECKSUMS = frozenset((0x014D, 0x014E, 0x014F))


def off(bank, addr): return bank * 0x4000 + addr - 0x4000


def update_checksums(rom):
    h = 0
    for v in rom[0x134:0x14D]: h = (h - v - 1) & 0xFF
    rom[0x14D] = h
    g = (sum(rom[:0x14E]) + sum(rom[0x150:])) & 0xFFFF
    rom[0x14E:0x150] = g.to_bytes(2, "big")


def build(source: bytes, cave_test: int = CAVE_TEST, cave_set: int = CAVE_SET, base_sha: str = BASE_SHA):
    assert hashlib.sha256(source).hexdigest() == base_sha, "wrong exact base"
    b13 = lambda a, n: source[off(13, a):off(13, a) + n]
    assert b13(0x7D18, 5) == bytes.fromhex("3C E0 E1 18 09"), "scene-02 FFE1 setter preimage"
    assert b13(0x7407, 8) == bytes.fromhex("F0 E1 B7 28 21 AF E0 E1"), "ISR reload test preimage"
    assert b13(0x740F, 2) == bytes.fromhex("3E 80"), "reload body head"
    assert b13(0x742D, 2) == bytes.fromhex("F0 97"), "commit continuation"
    assert b13(0x7D26, 3) == bytes.fromhex("CD 33 6A"), "scene-02 continuation"
    # $6E2A..$6E2C are NOT padding: `$6E0B JR Z,$6E2A` joins there when the DF02 one-shot
    # is already done.  r443e/r443e2 inserted a store before it and shifted the loop
    # under that join (every later cleaner call ran a garbage copy: title froze).  The
    # cleaner is left byte-identical; no boot init is needed under the D880==2 guard.
    assert b13(0x6E0B, 2) == bytes.fromhex("28 1D") and b13(0x6E2A, 3) == bytes(3), "cleaner join point moved"
    assert source[off(13, 0x76D5)] == 0xC9 and set(b13(cave_test, CAVE_END - cave_test)) == {0}, "bank13 cave range not free"
    # no other live DX FFE1 access: the only remaining LDH FFE1 sites must be vanilla-identical or dead mirrors
    # The LIVE WRAM-stub installer is bank13:$7CBF (r442 savestates hold its images); its
    # $DBC8..$DBEB image comes from $56CA, so $DBDF = $56E1 must be the plain `JP $3497`.
    # Bank31's installer ($6F00) copies $71BA..$71DD, which still carries the old
    # FFE1-testing $DBDF stub ($71D1) -- dead in this lineage, left untouched.
    assert b13(0x7CE6, 3) == bytes.fromhex("21 3A 56") and b13(0x7CF2, 3) == bytes.fromhex("C3 5C 57")
    assert b13(0x5767, 3) == bytes.fromhex("21 CA 56") and b13(0x576F, 6) == bytes.fromhex("11 EC DB 21 FA 56")
    assert b13(0x56E1, 3) == bytes.fromhex("C3 97 34"), "live $DBDF image is not JP $3497"
    # DF5D: no 16-bit immediate anywhere in the ROM
    for i in range(len(source) - 2):
        assert not (source[i] in (0xEA, 0xFA, 0x21, 0x11, 0x01, 0x08, 0x31) and source[i + 1] == 0x5D and source[i + 2] == 0xDF), f"DF5D referenced at {i:#x}"

    rom = bytearray(source); owned = set()
    def put(bank, addr, data):
        o = off(bank, addr); rom[o:o + len(data)] = data; owned.update(range(o, o + len(data)))
    put(13, 0x7D18, bytes((0xC3, cave_set & 0xFF, cave_set >> 8, 0x00, 0x00)))
    put(13, cave_set, bytes.fromhex("3C EA 5D DF C3 26 7D"))
    put(13, 0x7407, bytes((0xC3, cave_test & 0xFF, cave_test >> 8, 0x00, 0x00, 0x00, 0x00, 0x00)))
    put(13, cave_test, bytes.fromhex("FA 80 D8 FE 02 C2 2D 74 FA 5D DF 3D C2 2D 74 AF EA 5D DF C3 0F 74"))
    assert cave_test + 22 == cave_set and cave_set + 7 <= CAVE_END
    assert source[0x400F:0x4012] == bytes.fromhex("01 00 1F"), "boot WRAM clear extent changed (expect $C000..$DEFF)"
    update_checksums(rom)
    changed = {i for i, (x, y) in enumerate(zip(source, rom)) if x != y}
    assert changed <= owned | CHECKSUMS
    # controls: stock FFE1 machine bytes untouched
    for a, n in ((0x11C3, 0x30), (0x07A0, 0x12), (0x0AF0, 0x0C)):
        assert rom[a:a + n] == source[a:a + n]
    # DX no longer reads/writes FFE1 in bank 13
    b13n = rom[off(13, 0x4000):off(13, 0x8000)]
    hits = [0x4000 + i for i in range(len(b13n) - 1) if b13n[i] in (0xE0, 0xF0) and b13n[i + 1] == 0xE1]
    # $7D5E is the operand byte of `LDH ($FFE0),A` at $7D5D followed by `POP HL` ($E1): not an FFE1 access
    assert hits == [0x7D5E], f"bank13 still touches FFE1 at {[hex(h) for h in hits]}"
    receipt = {"schema": "penta-reload-flag-dealias-r443e3-build-v1", "base_sha256": base_sha,
               "candidate_sha256": hashlib.sha256(rom).hexdigest(), "changed_offsets": sorted(changed),
               "flag": f"${FLAG:04X} (exactly 1 = pending, consumed only while D880==2)", "cave": f"bank13:${cave_set:04X}..${CAVE_END - 1:04X}",
               "title_port_note": "compose with --no-fix-a; Fix A preimage at $7407 no longer exists",
               "provenance": "tmp/title-color/audit/df5d_allocation_census.md", "live_tested": False}
    return bytes(rom), receipt


def main():
    ap = argparse.ArgumentParser(description=__doc__); ap.add_argument("--base", type=Path, default=BASE); ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--base-sha", default=BASE_SHA); ap.add_argument("--on-r443f", action="store_true", help="shift the caves to $7703/$7719 (r443f pretest owns $76EE..$7702)")
    a = ap.parse_args()
    rom, rec = (build(a.base.read_bytes(), CAVE_TEST_F, CAVE_SET_F, a.base_sha) if a.on_r443f else build(a.base.read_bytes(), base_sha=a.base_sha))
    a.out_dir.mkdir(parents=True, exist_ok=True)
    t = a.out_dir / "candidate.gb"
    if t.exists() and t.read_bytes() != rom: raise SystemExit("candidate collision")
    t.write_bytes(rom); (a.out_dir / "build-receipt.json").write_text(json.dumps(rec, indent=2) + "\n")
    print(json.dumps({k: rec[k] for k in ("candidate_sha256", "flag", "cave")}, indent=1)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
