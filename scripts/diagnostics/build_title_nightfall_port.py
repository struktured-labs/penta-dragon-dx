#!/usr/bin/env python3
"""Port the reviewed Nightfall title treatment onto any r365-lineage base.

Why this exists (2026-09-05):

* r366/r367 placed the title service at bank23:$6C80.  r370+ reuse exactly
  that vector for the timer-safe attribute GDMA service, and both are reached
  through the fixed-bank trampoline at $0847 (``CALL $0061; CALL $6C80;
  JP $0061``), so the two cannot coexist in one bank.  This builder installs
  the title payload in a *virgin* expansion bank (default 25) at the same
  in-bank addresses r366 used, and the bank13 cleaner tail selects that bank.
  Nothing in bank 23 is touched.
* r366/r367 rendered a white title with gameplay palettes because the
  page-flip epilogue at b00:$12FC arms a deferred palette reload (``DF5C``)
  that the VBlank hook (b00:$082E -> b13:$73FC) executes when ``FFE1`` is
  set, overwriting BG1-6 with the gameplay rows from $6800 *after* the
  one-shot title paint.  "Fix A" skips that reload on scene $01 only; every
  other scene keeps its exact existing path.  The 21-byte body is placed in
  the first free run of bank 13 at or after $7464.

Static only.  Emits a receipt with every changed offset.  Live gates remain
mandatory (mGBA; PyBoy cannot boot r316+ because it does not store FF01).
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TMP = ROOT / "tmp"
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_stage1_title_nightfall_r366 as r366  # noqa: E402
import build_title_color_prototype as title  # noqa: E402

BANK_SIZE = 0x4000
LIVE_BANK = 13
DEFAULT_CODE_BANK = 25
DEFAULT_BASE = TMP / "interrupt-checked-vblank-r373/candidate.gb"
DEFAULT_OUT_DIR = TMP / "title-nightfall-port"

# r367 tail: reach the cleaner's saved LCDC below the two return addresses.
R366_TAIL = bytes.fromhex("AF E0 4F F1 E0 40 3E 0D C9")
R367_TAIL = bytes.fromhex("AF E0 4F E1 D1 F1 D5 E5 E0 40 3E 0D C9")

# Deferred palette reload routine, from its FFE1 test to its final JP $6F1D.
RELOAD_TEST_ADDR = 0x7407
RELOAD_IMAGE_FROM_TEST = bytes.fromhex(
    "f0e1b72821afe0e13e80e0682100680e692ae22ae22ae22ae22ae22ae22ae22ae2"
    "3e11ea4cdff097fe022807fa00dce60fe043fa02dce60fe042f0c4b72815e60407"
    "b720023e4047afe0c4f040e6b7b0e0401806f040ee48e040c31d6f"
)
RELOAD_BODY_ADDR = 0x740C      # XOR A; LDH (FFE1),A; reload 8 rows; ...
RELOAD_CONT_ADDR = 0x742D      # post-reload continuation (scroll/LCDC)
RELOAD_END_ADDR = RELOAD_TEST_ADDR + len(RELOAD_IMAGE_FROM_TEST)  # $7464
# Fix A depends only on the FFE1 test + reload body ($7407..$742C) and on $742D being the
# skip target; the post-reload continuation ($742D..) may differ between lineages (r384 latch).
RELOAD_CORE_LEN = RELOAD_CONT_ADDR - RELOAD_TEST_ADDR              # 38 bytes
FIX_A_SEARCH_START = RELOAD_END_ADDR
FIX_A_BODY_LEN = 21
CHECKSUM_OFFSETS = frozenset((0x014D, 0x014E, 0x014F))


def digest(payload: bytes | bytearray) -> str:
    return hashlib.sha256(payload).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bank_offset(bank: int, address: int) -> int:
    require(0x4000 <= address < 0x8000, f"invalid banked address ${address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def fix_a_body(body_addr: int) -> bytes:
    """Scene-$01 guard in front of the deferred YAML palette reload."""
    skip = body_addr + 15                      # XOR A; LDH (FFE1),A; JP cont
    code = bytearray()
    code += bytes((0xFA, 0x80, 0xD8))          # LD A,($D880)
    code += bytes((0x3D,))                     # DEC A
    code += bytes((0x28, 0x09))                # JR Z,skip   (title)
    code += bytes((0xF0, 0xE1))                # LDH A,($FFE1)
    code += bytes((0xB7,))                     # OR A
    code += bytes((0x28, 0x04))                # JR Z,skip   (no request)
    code += bytes((0xC3, RELOAD_BODY_ADDR & 0xFF, RELOAD_BODY_ADDR >> 8))
    code += bytes((0x00,))                     # pad
    require(len(code) == 15 and body_addr + len(code) == skip, "fix A layout")
    code += bytes((0xAF,))                     # XOR A
    code += bytes((0xE0, 0xE1))                # LDH ($FFE1),A  (consume)
    code += bytes((0xC3, RELOAD_CONT_ADDR & 0xFF, RELOAD_CONT_ADDR >> 8))
    require(len(code) == FIX_A_BODY_LEN, "fix A body length")
    return bytes(code)


class Asm:
    def __init__(self, org: int) -> None:
        self.org, self.code, self.labels, self.fix = org, bytearray(), {}, []

    def label(self, n: str) -> None:
        self.labels[n] = self.org + len(self.code)

    def db(self, *b: int) -> None:
        self.code += bytes(b)

    def jr(self, op: int, n: str) -> None:
        self.fix.append((len(self.code) + 1, n, "rel")); self.db(op, 0)

    def jp(self, op: int, n: str) -> None:
        self.fix.append((len(self.code) + 1, n, "abs")); self.db(op, 0, 0)

    def finish(self) -> bytes:
        for pos, n, kind in self.fix:
            if kind == "abs":
                t = self.labels[n]; self.code[pos] = t & 0xFF; self.code[pos + 1] = t >> 8
            else:
                d = self.labels[n] - (self.org + pos + 1); require(-128 <= d <= 127, f"JR range {n}")
                self.code[pos] = d & 0xFF
        return bytes(self.code)


def build_title_service_v2(cleaner_service: bytes, org: int = r366.SERVICE_ADDR) -> bytes:
    """r367 cleaner-context service + a VBlank-context repaint for the RETURNED title.

    Entry with LCD off = the cleaner call (unchanged bytes follow).  Entry with LCD
    on = the VBlank prelude call: if scene $01, DF08 != $5A and LY in 144..147,
    repaint in two VBlank steps (DF08: 0 -> palettes + $9820 image, sets 1;
    1 -> $9C20 image, sets $5A).  Each step is one 36-block GDMA (~2.5 lines) so
    it completes inside VBlank; BC/DE/HL preserved; returns A=$0D for $0847.
    """
    a = Asm(org)
    a.db(0xF0, 0x40, 0xCB, 0x7F); a.jp(0xC2, "vbl")               # LDH A,(FF40); BIT 7,A; JP NZ,vbl
    a.db(*cleaner_service)                                        # LCD off: r367 service, byte-identical
    a.label("vbl")
    a.db(0xFA, 0x80, 0xD8, 0x3D); a.jp(0xC2, "ret")               # not scene $01
    a.db(0xFA, 0x08, 0xDF, 0xFE, 0x5A); a.jp(0xCA, "ret")         # already painted
    a.db(0xF0, 0x44, 0xFE, 0x90); a.jp(0xDA, "ret")               # LY < 144
    a.db(0xFE, 0x94); a.jp(0xD2, "ret")                           # LY > 147
    a.db(0xC5, 0xD5, 0xE5)                                        # PUSH BC/DE/HL
    a.db(0xFA, 0x08, 0xDF, 0xB7); a.jr(0x20, "step2")             # DF08 != 0 -> second map
    a.db(0x3E, 0x88, 0xE0, 0x68, 0x21, r366.PAL_DATA_ADDR & 0xFF, r366.PAL_DATA_ADDR >> 8, 0x06, 0x30)
    a.label("pal")
    a.db(0x2A, 0xE0, 0x69, 0x05); a.jr(0x20, "pal")               # 48 BCPD writes
    a.db(0x3E, 0x01, 0xE0, 0x4F)                                  # VBK=1
    a.db(0x3E, r366.ATTR_IMAGE_ADDR >> 8, 0xE0, 0x51, 0xAF, 0xE0, 0x52)   # src $6000
    a.db(0x3E, 0x18, 0xE0, 0x53, 0x3E, 0x20, 0xE0, 0x54, 0x3E, 0x23, 0xE0, 0x55)  # $9820, 36 blocks
    a.db(0xAF, 0xE0, 0x4F, 0x3E, 0x01, 0xEA, 0x08, 0xDF); a.jr(0x18, "done")       # VBK=0; DF08:=1
    a.label("step2")
    a.db(0x3E, 0x01, 0xE0, 0x4F)
    a.db(0x3E, r366.ATTR_IMAGE_ADDR >> 8, 0xE0, 0x51, 0xAF, 0xE0, 0x52)
    a.db(0x3E, 0x1C, 0xE0, 0x53, 0x3E, 0x20, 0xE0, 0x54, 0x3E, 0x23, 0xE0, 0x55)  # $9C20, 36 blocks
    a.db(0xAF, 0xE0, 0x4F, 0x3E, 0x5A, 0xEA, 0x08, 0xDF)                           # VBK=0; DF08:=$5A
    a.label("done")
    a.db(0xE1, 0xD1, 0xC1)
    a.label("ret")
    a.db(0x3E, LIVE_BANK, 0xC9)
    return a.finish()


# Scene-transition wrapper (replaces r366's 9-byte pad wrapper): clear DF08 when the OLD
# scene is $01 (leave: cleaner blanks at the next LCD-off) AND when the NEW scene is $01
# (enter/return: the VBlank repaint above runs).  Entry contract as r366: old scene in
# (HL), new scene in B; exits with A=B into the stock helper $6BDF.
def rearm_wrapper_v2(clear_leaf: int) -> bytes:
    return bytes((0x7E, 0x3D, 0xCC, clear_leaf & 0xFF, clear_leaf >> 8,
                  0x78, 0x3D, 0xCC, clear_leaf & 0xFF, clear_leaf >> 8,
                  0x78, 0xC3, 0xDF, 0x6B))


PRELUDE_HOOK_ADDR = 0x6F23                      # CALL $6A60 in the VBlank prelude (every VBlank)
PRELUDE_HOOK_OLD = bytes.fromhex("CD 60 6A")
# The prelude runs the colorize/sweep entry ($6C90 -> $6BA4 -> $6900) whenever FFC1 != 0.
# After the attract reel the title returns with FFC1 = 1 (cold boot has 0), so the gameplay
# sweep rewrote the DISPLAYED title map's attributes to pal0 every frame (Astra: returned
# title attrs9800 0/576, attrs9C00 576/576).  Gate that block on FFC1 AND scene != $01.
SWEEP_GATE_ADDR = 0x6F26
SWEEP_GATE_OLD = bytes.fromhex("F0 C1 B7")     # LDH A,(FFC1); OR A   (followed by JR Z,$6F3D)
SWEEP_GATE_STUB = bytes.fromhex("F0 C1 B7 C8 FA 80 D8 3D C9")   # ...; RET Z; LD A,(D880); DEC A; RET


def prelude_stub(code_bank: int) -> bytes:
    return bytes.fromhex("CD 60 6A") + bytes((0x3E, code_bank, 0xCD, 0x47, 0x08, 0xC9))


CODE_CAVE_FENCE = 0x76D5           # bank13: `RET` ending the routine before the 77-byte zero cave
CODE_CAVE_ADDR = 0x76D7            # first byte used (one zero fence kept at $76D6)
CODE_CAVE_MAX = 0x76D6 + 77


def carve(rom: bytes, bank: int, cursor: int, length: int) -> int:
    """Allocate `length` bytes at `cursor` inside the RET-fenced code cave.

    Zero runs elsewhere in bank 13 ($74FC, $78FF, $79BB) are the interiors of
    04/00 and 02/00 tables (e.g. $7488..$751A is referenced from $443F), so a
    generic "zero run" search is NOT a free-space proof there.  Only the run
    that follows the RET at $76D5 is a code cave.
    """
    require(rom[bank_offset(bank, CODE_CAVE_FENCE)] == 0xC9, "code cave fence at $76D5 is not a RET")
    require(cursor + length <= CODE_CAVE_MAX, "code cave exhausted")
    o = bank_offset(bank, cursor)
    require(all(b == 0 for b in rom[o:o + length]), f"cave bytes at ${cursor:04X} not zero")
    return cursor


def find_free_run(rom: bytes, bank: int, start: int, length: int) -> int:
    """First address >= start in `bank` whose `length` bytes are all $00/$FF.
    (Retained for non-bank-13 uses; bank-13 allocations go through carve().)"""
    address = start
    while address + length <= 0x8000:
        offset = bank_offset(bank, address)
        window = rom[offset:offset + length]
        if all(b in (0x00, 0xFF) for b in window):
            # Require a 1-byte free fence on each side so we never abut code.
            before = rom[offset - 1] if address > 0x4000 else 0
            after = rom[offset + length] if address + length < 0x8000 else 0
            if before in (0, 0xFF) and after in (0, 0xFF):
                return address
        address += 1
    raise AssertionError(f"no free {length}-byte run in bank {bank} after ${start:04X}")


ATOMIC_SVC_BANK, ATOMIC_SVC_ADDR = 23, 0x6C80
# Title atomic-DMA guard (v4).  The returned title (D880=$01, FFC1=1) takes the
# atomic publisher path, and bank23's wait+GDMA service then copies the compiled
# $D000 buffer (all zero for title tiles) over the displayed map's attributes on
# every title publish (live trace: PC $6CC6, frames 9147/9165/9167/...), erasing
# the bank25 paint.  Prefix: `LD A,($D880); CP $01; JR NZ,body; LD A,$01; RET`.
# SVBK is 1 at entry ($4324 sets it before the far call), so $D880 is the real
# scene byte.  A=1 restores the caller's bank 1.  Gameplay scenes fall through.
ATOMIC_GUARD_PREFIX = bytes.fromhex("FA 80 D8 FE 01 20 03 3E 01 C9")

# --isr-merge (v5): on r443+ bases every expansion bank already owns its $0847 slot
# ($6C80); bank 25's is the r443 ISR DMA/commit service (position-independent, JR only).
# The merged bank25:$6C80 becomes:
#   LDH A,(FF40); BIT 7,A; JP Z,$6D00   ; LCD off = the cleaner-tail call -> title service
#   CALL $6D00                          ; LCD on  = ISR $746D: title VBlank repaint check
#   <r443 ISR body, byte-identical>     ; then the DMA/commit decision (sets Z/NZ, A=$0D)
# so the title's VBlank path runs from the $746D call (same LY 144..147 gate) and the
# $6F23 prelude stub is not installed.  The title service itself is assembled at $6D00.
MERGE_SERVICE_ADDR = 0x6D00
# v6 fast path: with the LCD on, only scene $01 calls the title service (v5 called it on
# every gameplay VBlank: ~30 cycles/frame, enough to push S1/S2 under the 97.5 floor).
MERGE_HEADS = {
    # v5 (6b375a80 on r443e3): title service called on every LCD-on ISR
    "v5": bytes((0xF0, 0x40, 0xCB, 0x7F, 0xCA, MERGE_SERVICE_ADDR & 0xFF, MERGE_SERVICE_ADDR >> 8,
                 0xCD, MERGE_SERVICE_ADDR & 0xFF, MERGE_SERVICE_ADDR >> 8)),
    # v6: LCD on -> only scene $01 calls the title service
    "v6": bytes((0xF0, 0x40, 0xCB, 0x7F, 0xCA, MERGE_SERVICE_ADDR & 0xFF, MERGE_SERVICE_ADDR >> 8,   # LCD off -> title (cleaner frame)
                 0xFA, 0x80, 0xD8, 0x3D, 0xCC, MERGE_SERVICE_ADDR & 0xFF, MERGE_SERVICE_ADDR >> 8)),  # LD A,(D880); DEC A; CALL Z,title
}


def build(source: bytes, *, code_bank: int, apply_fix_a: bool, return_repaint: bool = True,
          atomic_guard: bool = True, isr_merge: bool = False, merge_head: str = "v6") -> tuple[bytes, dict]:
    MERGE_HEAD = MERGE_HEADS[merge_head]
    require(len(source) == 32 * BANK_SIZE, "base is not a 32-bank (512 KiB) ROM")
    require(source[0x0148] == 0x04, "header ROM size is not 512 KiB")
    require(0x18 <= code_bank <= 0x1F, "code bank must be an expansion bank 24..31")
    require(title.ACTIVE_SCHEME == "Nightfall",
            "palette YAML no longer selects reviewed Nightfall")
    # r365 clears Sara's priority bit at $1199 (CB BF); r368+ folds the
    # same clear into $1188 (RES 7,A; RET).  Record which form the base has.
    sara_clear = ("r365:$1199" if source[0x1199:0x119B] == bytes.fromhex("CB BF")
                  else "r368:$1188" if bytes.fromhex("CB BF C9") in source[0x1180:0x11A0]
                  else "ABSENT")
    require(sara_clear != "ABSENT", "base has no Sara priority clear (pre-r365 lineage?)")

    bank_bytes = source[code_bank * BANK_SIZE:(code_bank + 1) * BANK_SIZE]
    isr_body = b""
    if isr_merge:
        from build_later_stage_deferred_dma_r443 import isr_service as r443_isr_service  # noqa: E402
        isr_body = r443_isr_service()
        require(not apply_fix_a and return_repaint, "--isr-merge requires --no-fix-a and the v2+ repaint")
        require(not any(b in (0xC3, 0xCD, 0xC2, 0xCA, 0xC4, 0xCC, 0xD2, 0xDA)
                        and i + 2 < len(isr_body) and isr_body[i + 2] in (0x6C,)
                        for i, b in enumerate(isr_body)), "r443 ISR body is not position-independent")
        bb = lambda lo, hi: bank_bytes[lo - 0x4000:hi - 0x4000]
        require(bb(0x6C80, 0x6C80 + len(isr_body)) == isr_body, "bank25 $6C80 is not the exact r443 ISR service")
        require(set(bb(0x6C80 + len(isr_body), 0x6E00)) == {0xFF}, "bank25 $6CC9..$6DFF not free")
        require(set(bb(0x6000, 0x6280)) == {0xFF}, "bank25 $6000..$627F not free")
    else:
        require(set(bank_bytes) <= {0xFF}, f"bank {code_bank} is not virgin ($FF)")

    # bank13 anchors identical to r366's contract.
    def at(bank: int, addr: int, n: int) -> bytes:
        o = bank_offset(bank, addr)
        return source[o:o + n]

    require(at(LIVE_BANK, r366.CLEANER_TAIL_ADDR, 5) == r366.CLEANER_TAIL_PREIMAGE,
            "cleaner tail preimage changed")
    require(at(LIVE_BANK, r366.REARM_WRAPPER_PAD_ADDR, r366.REARM_WRAPPER_PAD_SIZE)
            == bytes(r366.REARM_WRAPPER_PAD_SIZE), "rearm wrapper pad not free")
    require(at(LIVE_BANK, r366.CLEAR_HELPER_PAD_ADDR, r366.CLEAR_HELPER_PAD_SIZE)
            == bytes(r366.CLEAR_HELPER_PAD_SIZE), "clear helper pad not free")
    require(at(LIVE_BANK, r366.TRANSITION_CRYSTAL_CALL_ADDR, 3)
            == r366.TRANSITION_CRYSTAL_CALL_PREIMAGE,
            "scene-transition crystal call changed")
    # Trampoline must still be the fixed-bank $6C80 vector.
    require(source[0x0847:0x0850] == bytes.fromhex("CD 61 00 CD 80 6C C3 61 00"),
            "$0847 trampoline changed")

    records = title.parse_title_list(source)
    attr_image, coverage = title.build_attribute_image(records)
    palettes = title.build_palette_block(title.SCHEMES["Nightfall"])
    service = r366.build_title_service()
    require(service.endswith(R366_TAIL), "r366 service tail drifted")
    service = service[:-len(R366_TAIL)] + R367_TAIL
    service_addr = MERGE_SERVICE_ADDR if isr_merge else r366.SERVICE_ADDR
    if return_repaint:
        service = build_title_service_v2(service, service_addr)
        require(at(LIVE_BANK, PRELUDE_HOOK_ADDR, 3) == PRELUDE_HOOK_OLD, "prelude CALL $6A60 changed")
        require(at(LIVE_BANK, SWEEP_GATE_ADDR, 5) == SWEEP_GATE_OLD + bytes.fromhex("28 12"),
                "prelude FFC1 sweep gate changed (expect LDH A,(FFC1); OR A; JR Z,+$12)")
    wrapper_pad, clear_pad = r366.build_rearm_pads()

    rom = bytearray(source)
    owned: set[int] = set()
    cave_cursor = CODE_CAVE_ADDR

    def install(bank: int, address: int, data: bytes) -> None:
        offset = bank_offset(bank, address)
        rom[offset:offset + len(data)] = data
        owned.update(range(offset, offset + len(data)))

    install(code_bank, r366.ATTR_IMAGE_ADDR, bytes(attr_image))
    install(code_bank, r366.PAL_DATA_ADDR, palettes)
    install(code_bank, service_addr, service)
    if isr_merge:
        require(service_addr + len(service) <= 0x6E00, "merged title service overflows $6DFF")
        install(code_bank, r366.SERVICE_ADDR, MERGE_HEAD + isr_body)
    install(LIVE_BANK, r366.CLEANER_TAIL_ADDR, bytes((0x3E, code_bank, 0xCD, 0x47, 0x08)))
    install(LIVE_BANK, r366.CLEAR_HELPER_PAD_ADDR, clear_pad)
    repaint: dict[str, object] = {"applied": False}
    if return_repaint:
        wrapper = rearm_wrapper_v2(r366.CLEAR_HELPER_ADDR)
        w_addr = carve(bytes(rom), LIVE_BANK, cave_cursor, len(wrapper)); cave_cursor += len(wrapper)
        install(LIVE_BANK, w_addr, wrapper)
        if isr_merge:
            s_addr = None
        else:
            stub = prelude_stub(code_bank)
            s_addr = carve(bytes(rom), LIVE_BANK, cave_cursor, len(stub)); cave_cursor += len(stub)
            install(LIVE_BANK, s_addr, stub)
            install(LIVE_BANK, PRELUDE_HOOK_ADDR, bytes((0xCD, s_addr & 0xFF, s_addr >> 8)))
        install(LIVE_BANK, r366.TRANSITION_CRYSTAL_CALL_ADDR, bytes((0xCD, w_addr & 0xFF, w_addr >> 8)))
        g_addr = carve(bytes(rom), LIVE_BANK, cave_cursor, len(SWEEP_GATE_STUB)); cave_cursor += len(SWEEP_GATE_STUB)
        install(LIVE_BANK, g_addr, SWEEP_GATE_STUB)
        install(LIVE_BANK, SWEEP_GATE_ADDR, bytes((0xCD, g_addr & 0xFF, g_addr >> 8)))
        repaint = {"applied": True,
                   "rearm_wrapper": f"bank13:${w_addr:04X} clears DF08 on leave AND enter of scene $01",
                   "prelude_stub": ("none: merged into the r443 ISR service call at $746D" if isr_merge else
                                    f"bank13:${s_addr:04X} CALL $6A60; LD A,${code_bank:02X}; CALL $0847; RET (from $6F23)"),
                   "service_vblank_path": "scene $01 & DF08!=$5A & LY 144..147: step1 palettes+$9820, step2 $9C20; two VBlanks",
                   "sweep_gate": f"bank13:${g_addr:04X} from $6F26: colorize/sweep block skipped when FFC1==0 OR scene==$01 "
                                 "(returned title has FFC1=1; the gameplay sweep was blanking the displayed map)",
                   "r366_wrapper_pad_left_zero": True}
    else:
        install(LIVE_BANK, r366.REARM_WRAPPER_PAD_ADDR, wrapper_pad)
        install(LIVE_BANK, r366.TRANSITION_CRYSTAL_CALL_ADDR,
                bytes((0xCD, r366.REARM_WRAPPER_ADDR & 0xFF, r366.REARM_WRAPPER_ADDR >> 8)))

    fix_a: dict[str, object] = {"applied": False}
    if apply_fix_a:
        require(at(LIVE_BANK, RELOAD_TEST_ADDR, RELOAD_CORE_LEN)
                == RELOAD_IMAGE_FROM_TEST[:RELOAD_CORE_LEN],
                "deferred palette reload routine at $7407..$742C differs from r367")
        require(at(LIVE_BANK, RELOAD_TEST_ADDR, 5) == bytes.fromhex("F0 E1 B7 28 21"),
                "FFE1 test/skip at $7407 must jump +$21 to $742D")
        require(source[0x082E:0x0831] == bytes.fromhex("CD FC 73"),
                "VBlank hook no longer calls $73FC")
        body_addr = carve(bytes(rom), LIVE_BANK, cave_cursor, FIX_A_BODY_LEN); cave_cursor += FIX_A_BODY_LEN
        body = fix_a_body(body_addr)
        install(LIVE_BANK, body_addr, body)
        install(LIVE_BANK, RELOAD_TEST_ADDR,
                bytes((0xC3, body_addr & 0xFF, body_addr >> 8, 0x00, 0x00)))
        fix_a = {
            "applied": True,
            "redirect": f"bank13:${RELOAD_TEST_ADDR:04X} JP ${body_addr:04X}",
            "body": f"bank13:${body_addr:04X}",
            "body_hex": body.hex(),
            "semantics": "scene $01 skips the deferred YAML BG reload; "
                         "other scenes unchanged; FFE1 consumed as before",
        }

    guard: dict[str, object] = {"applied": False}
    if atomic_guard:
        svc_off = bank_offset(ATOMIC_SVC_BANK, ATOMIC_SVC_ADDR)
        svc_len = max(i for i in range(0x100) if rom[svc_off + i] != 0xFF) + 1
        body = bytes(rom[svc_off:svc_off + svc_len])
        require(body[:4] == bytes.fromhex("C5 F0 FF F5") or body[:5] == bytes.fromhex("F0 BA B7 28 0F"),
                "bank23 atomic service preimage unknown (expect r442 body or r443b prefix)")
        require(body[-1] == 0xC9 and b"\xc3" not in body and b"\xcd" not in body,
                "bank23 service has absolute references; cannot shift it")
        require(set(rom[svc_off + svc_len:svc_off + svc_len + len(ATOMIC_GUARD_PREFIX)]) == {0xFF},
                "no free bytes after the bank23 service")
        require(source[0x4324:0x4330] == bytes.fromhex("3E 01 E0 70 3E 17 CD 47 08 C3 54 43"),
                "atomic tail no longer sets SVBK=1 before the bank23 far call")
        install(ATOMIC_SVC_BANK, ATOMIC_SVC_ADDR, ATOMIC_GUARD_PREFIX + body)
        guard = {
            "applied": True,
            "site": f"bank{ATOMIC_SVC_BANK}:${ATOMIC_SVC_ADDR:04X}",
            "prefix_hex": ATOMIC_GUARD_PREFIX.hex(),
            "body_shifted_by": len(ATOMIC_GUARD_PREFIX),
            "semantics": "scene $01 skips the atomic attribute GDMA (title map keeps the bank25 paint); "
                         "all other scenes run the unchanged body",
        }

    r366.update_checksums(rom)
    candidate = bytes(rom)
    changed = {i for i, (a, b) in enumerate(zip(source, candidate, strict=True)) if a != b}
    require(changed <= owned | CHECKSUM_OFFSETS,
            f"escaped owned bytes: {sorted(changed - owned - CHECKSUM_OFFSETS)[:8]}")
    require(candidate[0x1180:0x11A0] == source[0x1180:0x11A0], "Sara clear region altered")

    receipt = {
        "schema": "penta-title-nightfall-port-build-v1",
        "status": "STATIC_PASS_LIVE_GATES_REQUIRED",
        "promotable": False,
        "emulator_invoked": False,
        "base_sha256": digest(source),
        "base_sara_priority_clear": sara_clear,
        "candidate_sha256": digest(candidate),
        "changed_offsets": sorted(changed),
        "title": {
            "scheme": "Nightfall",
            "palette_source": str(title.PALETTE_YAML),
            "palette_source_sha256": digest(title.PALETTE_YAML.read_bytes()),
            "attribute_cells": coverage,
            "expansion_bank": code_bank,
            "attribute_image": f"bank{code_bank}:${r366.ATTR_IMAGE_ADDR:04X}",
            "palette_block": f"bank{code_bank}:${r366.PAL_DATA_ADDR:04X}",
            "service": f"bank{code_bank}:${service_addr:04X}",
            "isr_merge": ({"head_version": merge_head, "head": f"bank{code_bank}:${r366.SERVICE_ADDR:04X} {MERGE_HEAD.hex()} + r443 ISR body ({len(isr_body)} B)"}
                          if isr_merge else None),
            "service_tail": "r367 nested-call stack repair",
            "cleaner_tail_patch": f"bank13:${r366.CLEANER_TAIL_ADDR:04X} "
                                  f"LD A,${code_bank:02X}; CALL $0847",
        },
        "atomic_guard": guard,
        "fix_a": fix_a,
        "return_repaint": repaint,
        "required_live_gates": [
            "cold boot Nightfall title: BG1-6 CRAM == YAML block at frames 200/400/800",
            "title field/ink roles (mGBA verify_title_color_mgba.py)",
            "title -> opening/GAME START/splash/Stage 1 leave path",
            "full release matrix on the exact candidate hash",
        ],
    }
    return candidate, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--code-bank", type=lambda s: int(s, 0), default=DEFAULT_CODE_BANK)
    parser.add_argument("--no-fix-a", action="store_true",
                        help="build the title port without Fix A (negative control)")
    parser.add_argument("--no-atomic-guard", action="store_true",
                        help="omit the bank23 scene-$01 atomic-DMA guard (reproduces v3-class returned-title blanking)")
    parser.add_argument("--isr-merge", action="store_true",
                        help="r443+ bases: merge the title service into bank25's $0847 slot (see MERGE_HEAD); implies --no-fix-a")
    parser.add_argument("--merge-head", choices=("v5", "v6"), default="v6",
                        help="merged $6C80 head version (v5 = literal head of 6b375a80; v6 = scene-$01 fast path)")
    parser.add_argument("--legacy-rearm", action="store_true",
                        help="r366 leave-only rearm (reproduces 558d9b06-class builds; returned title stays blank)")
    args = parser.parse_args()
    out_dir = r366.checked_output(args.out_dir, "out-dir")
    candidate, receipt = build(args.base.read_bytes(), code_bank=args.code_bank,
                               apply_fix_a=not args.no_fix_a, return_repaint=not args.legacy_rearm,
                               atomic_guard=not args.no_atomic_guard, isr_merge=args.isr_merge, merge_head=args.merge_head)
    receipt["base_path"] = str(args.base)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidate.gb").write_bytes(candidate)
    (out_dir / "build-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "base_sha256": receipt["base_sha256"][:16],
        "candidate_sha256": receipt["candidate_sha256"],
        "changed_bytes": len(receipt["changed_offsets"]),
        "fix_a": receipt["fix_a"].get("body", "off"),
        "output": str(out_dir / "candidate.gb"),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"FAIL: {error}")
        raise SystemExit(1)
