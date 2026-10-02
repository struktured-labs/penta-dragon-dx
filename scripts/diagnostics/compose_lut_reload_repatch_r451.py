#!/usr/bin/env python3
"""r451: re-apply the r297 room-01 wall companion patch after every ROM->C600 LUT reload.

Defect (hazard-menu receipts r297..r450, builder 3355390e clean): room-01 cells with tiles $27/$33
inside the animated tooth rows publish attr 0 instead of 6.  The r297 patch (C624/C627/C630/C633 :=
room==1 ? 6 : 0, Stage 1 only) is applied only from the FFBD room-write hooks (bank21 $6C80/$7D00) and
inside the bank30 compile preamble; the two ROM->C600 reloads in the transition/palette service
(bank13/16 $6E1C and $6FF0, copying bank13 $7000) silently drop it, so any Stage-1 attribute writer that
reads C600 before the next room write or bank30 compile publishes the global value 0.

Fix (per mirror bank, byte-identical logic):
  * $6E2A  `00 00 00`            -> `CALL repatch`; and $6E0B `JR Z,$6E2A` (DF02 already $5A = no reload)
           -> `JR Z,$6E2D` so the repatch runs ONLY after an actual reload, never on the every-call
           short-circuit (a per-VBlank write keyed on FFBD could disagree with bank30's FFE5 rule mid-compile)
  * $6FF0  `21 00 70` (LD HL,$7000) -> `JP reload_repatch`; $6FF3..$6FFE (LD DE,$C600; loop; RET) stay
           byte-identical because the arena palette path enters the shared loop at $6FF3 via `JR` from $6FDF
           with HL = $7200+boss*256 (r451 first cut NOP'd it; r451b keeps it)
  * cave `repatch`:        LDH A,(FFBA); OR A; RET NZ; LDH A,(FFBD); DEC A; LD A,0; JR NZ,+2; LD A,6;
                           LD (C624),A; LD (C627),A; LD (C630),A; LD (C633),A; RET
  * cave `reload_repatch`: LD HL,$7000; CALL $6FF3 (shared copy loop + RET); then falls into repatch.
Predicate is the r297 one (FFBA==0, FFBD==1 -> 6 else 0); later stages untouched (RET NZ).
"""
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "tmp/title-nightfall-port/r443e3f2-v6-r449fhelper/candidate.gb"
BASE_SHA = "d82f563d856995fc1844d48cdd317b12f2ac9218f023eec376ee73bc24308074"
CAVES = {13: 0x79BB, 16: 0x79D7}   # free runs (>=42 B) verified in each mirror bank
RELOAD = bytes.fromhex("21 00 70 11 00 C6 06 00 2A 12 13 05 20 FA")
REPATCH = bytes.fromhex("F0 BA B7 C0 F0 BD 3D 3E 00 20 02 3E 06 EA 24 C6 EA 27 C6 EA 30 C6 EA 33 C6 C9")

def off(bank, addr): return bank * 0x4000 + addr - 0x4000
def checksums(rom):
    x = 0
    for i in range(0x134, 0x14D): x = (x - rom[i] - 1) & 0xFF
    rom[0x14D] = x
    g = 0
    for i, b in enumerate(rom):
        if i not in (0x14E, 0x14F): g = (g + b) & 0xFFFF
    rom[0x14E] = g >> 8; rom[0x14F] = g & 0xFF

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--base", type=Path, default=BASE)
    ap.add_argument("--out-dir", type=Path, required=True); a = ap.parse_args()
    src = a.base.read_bytes(); assert hashlib.sha256(src).hexdigest() == BASE_SHA, "base is not d82f563d"
    rom = bytearray(src); changed = []
    for bank, cave in CAVES.items():
        o_call = off(bank, 0x6E2A); assert rom[o_call:o_call+3] == b"\x00\x00\x00", f"bank{bank} $6E2A preimage"
        o_jr = off(bank, 0x6E0B); assert rom[o_jr:o_jr+2] == bytes([0x28, 0x1D]), f"bank{bank} $6E0B JR Z,$6E2A preimage"
        rom[o_jr+1] = 0x20   # JR Z,$6E2D: skip the repatch call when no reload happened
        o_rl = off(bank, 0x6FF0); assert rom[o_rl:o_rl+15] == RELOAD + b"\xC9", f"bank{bank} $6FF0 preimage"
        # arena path enters the shared loop at $6FF3 (JR from $6FDF): keep $6FF3..$6FFE byte-identical
        assert rom[off(bank,0x6FDF):off(bank,0x6FDF)+2] == bytes([0x18, 0x12]), f"bank{bank} $6FDF JR->$6FF3 preimage"
        assert rom[off(bank,0x6E1C):off(bank,0x6E1C)+14] == RELOAD, f"bank{bank} $6E1C reload preimage"
        o_cave = off(bank, cave); body = bytes.fromhex("21 00 70 CD F3 6F") + REPATCH
        assert all(b in (0x00, 0xFF) for b in rom[o_cave:o_cave+len(body)]), f"bank{bank} cave not free"
        repatch_addr = cave + 6
        rom[o_call:o_call+3] = bytes([0xCD, repatch_addr & 0xFF, repatch_addr >> 8])
        rom[o_rl:o_rl+3] = bytes([0xC3, cave & 0xFF, cave >> 8])
        rom[o_cave:o_cave+len(body)] = body
        changed += [(bank, "$6E0C", "JR Z displacement 1D->20 (skip repatch when DF02 already $5A)"), (bank, "$6E2A", "CALL $%04X" % repatch_addr), (bank, "$6FF0", "JP $%04X (LD HL,$7000 replaced; $6FF3.. shared loop untouched)" % cave),
                    (bank, "$%04X" % cave, "LD HL,$7000; CALL $6FF3; repatch(26)")]
    checksums(rom)
    a.out_dir.mkdir(parents=True, exist_ok=True); out = a.out_dir / "candidate.gb"
    if out.exists() and out.read_bytes() != bytes(rom): raise SystemExit("immutable candidate collision")
    out.write_bytes(rom)
    sha = hashlib.sha256(rom).hexdigest()
    diff = [i for i in range(len(rom)) if rom[i] != src[i]]
    json.dump({"schema": "penta-compose-lut-reload-repatch-r451c-v1", "base_sha256": BASE_SHA, "candidate_sha256": sha,
               "changed": changed, "changed_bytes": len(diff), "changed_offsets": [hex(i) for i in diff],
               "predicate": "r297 wall companion rule re-applied after both ROM->C600 reloads: FFBA==0 && (FFBD==1 ? 6 : 0) -> C624/C627/C630/C633; later stages RET NZ",
               "acceptance": "stage1_current_hazard_menu replay: static_tooth_rows 36/36, empty mismatch trace (builder parity); north oracle + no-bleed unchanged; Stage1 speed unchanged (runs once per LUT reload)"},
              open(a.out_dir / "build-receipt.json", "w"), indent=1)
    print(json.dumps({"candidate_sha256": sha, "changed_bytes": len(diff)}))
if __name__ == "__main__": sys.exit(main())
