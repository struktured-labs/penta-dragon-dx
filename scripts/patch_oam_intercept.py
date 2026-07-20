#!/usr/bin/env python3
"""
O(1) Shadow OAM Intercept patches — post-processes v301 teleport ROM.

Patches: WRAM LUT copy, 3 OAM write-site hooks, removes stamper CALL.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_v301_teleport import (
    build_obj_pal_table, build_teleport_routine, build_landing_pad,
    BANK13, TELEPORT_ADDR, COLORIZE_ADDR,
    OBJ_STAMPER_ADDR, OBJ_PAL_TABLE_ADDR,
)
from build_v301_gdma import build_v301

BASE_OUT = Path("rom/working/penta_dragon_dx_v301.gb")
TP_OUT = Path("rom/working/penta_dragon_dx_teleport.gb")

# WRAM allocations
OBJ_PAL_WRAM = 0xD900
OBJ_PAL_WRAM_HI = 0xD9

WRAM_TRAMP_BASE = 0xDB80
S1_TRAMP = WRAM_TRAMP_BASE       # site 1 at attr write (0x10E4)
S2_TRAMP = WRAM_TRAMP_BASE + 48  # site 2 at tile write (0x3487)
S3_TRAMP = WRAM_TRAMP_BASE + 96  # site 3 at attr write (bank1:0x5221)
TRAMP_ROM_SRC = 0x6A70           # bank13 source for trampolines (free at 0x6A70)

# Adjusted layout: bump wrapper/landing pad to give teleport room
WRAPPER_ADDR = 0x6F60
LANDING_PAD_ROM = 0x6FA0

_B = bytearray


def s1_tramp():
    """Site 1 trampoline: called from 0x10E4.
    Entry: A=transformed attr, DE=entry+3. Returns to 0x10E6.
    """
    c = _B()
    c.extend([0xE5])                         # PUSH HL
    c.extend([0x47])                         # LD B,A  (save attr in B)
    c.extend([0x1B, 0x1A, 0x13])            # DEC DE; LD A,[DE]; INC DE (tile)
    c.extend([0x6F, 0x26, OBJ_PAL_WRAM_HI]) # LD L,A; LD H,$D9
    c.extend([0x7E])                         # LD A,[HL] (palette)
    c.extend([0xFE, 0xFF])                   # CP $FF
    js = len(c); c.extend([0x28, 0x00])      # JR Z, sara
    # Normal
    c.extend([0x4F])                         # LD C,A (pal)
    c.extend([0x78, 0xE6, 0xF8, 0xB1])      # LD A,B; AND $F8; OR C
    c.extend([0x12, 0x13])                   # LD [DE],A; INC DE
    c.extend([0xE1, 0x79, 0xC9])            # POP HL; LD A,C; RET
    # Sara
    sp = len(c); c[js+1] = (sp - js - 2) & 0xFF
    c.extend([0xE5, 0xF0, 0xBE, 0xB7])      # PUSH HL; LDH A,[FFBE]; OR A
    c.extend([0x3E, 0x02])                   # LD A,2 (Sara W default)
    jw = len(c); c.extend([0x28, 0x00])      # JR Z, w
    c.extend([0x3E, 0x01])                   # LD A,1 (Sara D)
    wp = len(c); c[jw+1] = (wp - jw - 2) & 0xFF
    c.extend([0x4F])                         # LD C,A
    c.extend([0xE1])                         # POP HL (restore HL)
    c.extend([0x78, 0xE6, 0xF8, 0xB1])      # LD A,B; AND $F8; OR C
    c.extend([0x12, 0x13, 0xE1, 0x79, 0xC9])
    return bytes(c)


def s2_tramp():
    """Site 2 trampoline: called from 0x3487.
    Entry: D=tile, HL=entry+3. Returns to 0x348C (after pushes).
    """
    c = _B()
    c.extend([0x7A, 0x6F])                   # LD A,D; LD L,A
    c.extend([0x26, OBJ_PAL_WRAM_HI])        # LD H,$D9
    c.extend([0x7E])                         # LD A,[HL]
    c.extend([0xFE, 0xFF])
    js = len(c); c.extend([0x28, 0x00])      # JR Z, sara
    # Normal
    c.extend([0x4F])                         # LD C,A
    c.extend([0x7E, 0xE6, 0xF8, 0xB1])      # LD A,[HL]; AND $F8; OR C
    c.extend([0x77, 0x23])                   # LD [HL],A; INC HL
    c.extend([0xF5, 0xC5, 0xD5, 0xE5, 0xC9]) # pushes + RET
    # Sara
    sp = len(c); c[js+1] = (sp - js - 2) & 0xFF
    c.extend([0xE5, 0xF0, 0xBE, 0xB7])
    c.extend([0x3E, 0x02])
    jw = len(c); c.extend([0x28, 0x00])
    c.extend([0x3E, 0x01])
    wp = len(c); c[jw+1] = (wp - jw - 2) & 0xFF
    c.extend([0x4F, 0xE1])                   # LD C,A; POP HL
    c.extend([0x7E, 0xE6, 0xF8, 0xB1])      # LD A,[HL]; AND $F8; OR C
    c.extend([0x77, 0x23, 0xF5, 0xC5, 0xD5, 0xE5, 0xC9])
    return bytes(c)


def s3_tramp():
    """Site 3 trampoline: called from bank1:0x5221.
    Entry: DE=entry+3, HL=attr src. Returns to 0x5224.
    """
    c = _B()
    c.extend([0xE5])                         # PUSH HL
    c.extend([0x1B, 0x1A, 0x13])            # DEC DE; LD A,[DE]; INC DE (tile)
    c.extend([0x6F, 0x26, OBJ_PAL_WRAM_HI])
    c.extend([0x7E])
    c.extend([0xFE, 0xFF])
    js = len(c); c.extend([0x28, 0x00])
    # Normal
    c.extend([0x4F])                         # LD C,A
    c.extend([0xE1])                         # POP HL (restore to attr src)
    c.extend([0x7E, 0xE6, 0xF8, 0xB1])      # LD A,[HL]; AND $F8; OR C
    c.extend([0x12, 0x13, 0x23, 0xC9])      # [DE],A; INC DE; INC HL; RET
    # Sara
    sp = len(c); c[js+1] = (sp - js - 2) & 0xFF
    c.extend([0xE5, 0xF0, 0xBE, 0xB7])
    c.extend([0x3E, 0x02])
    jw = len(c); c.extend([0x28, 0x00])
    c.extend([0x3E, 0x01])
    wp = len(c); c[jw+1] = (wp - jw - 2) & 0xFF
    c.extend([0x4F, 0xE1])                   # LD C,A; POP HL
    c.extend([0x7E, 0xE6, 0xF8, 0xB1])
    c.extend([0x12, 0x13, 0x23, 0xC9])
    return bytes(c)


def build_wrapper():
    """VBlank wrapper WITHOUT stamper CALL."""
    c = _B()
    c.extend([0xC5, 0xD5, 0xE5])  # push BC, DE, HL
    # joypad read (8-debounce)
    c.extend([0x3E, 0x20, 0xE0, 0x00, 0xF0, 0x00, 0xF0, 0x00,
              0x2F, 0xE6, 0x0F, 0xCB, 0x37, 0x47])
    c.extend([0x3E, 0x10, 0xE0, 0x00])
    for _ in range(8):
        c.extend([0xF0, 0x00])
    c.extend([0x2F, 0xE6, 0x0F, 0xB0, 0xE0, 0x93, 0x47])
    c.extend([0x3E, 0x30, 0xE0, 0x00, 0x78])
    # CALL teleport (includes scene_detect + lava + colorize JP)
    c.extend([0xCD, TELEPORT_ADDR & 0xFF, (TELEPORT_ADDR >> 8) & 0xFF])
    # NO stamper CALL
    c.extend([0xE1, 0xD1, 0xC1, 0xC9])  # pop HL, DE, BC; RET
    return bytes(c)


def main():
    # Build base v301
    build_v301()
    print(f"  Built {BASE_OUT}")

    # Apply teleport patches on top
    from build_v301_teleport import main as teleport_main
    # Need to re-import because we need to call the original main()
    # but it writes to TP_OUT. We'll just call it directly.
    # Actually we can't easily import main here due to circular issues.
    # Let's just exec the teleport build module's main:
    import build_v301_teleport as tp_mod
    tp_mod.main()

    # Now read the teleport ROM (which has all teleport features)
    rom = bytearray(TP_OUT.read_bytes())

    # === Phase 1: DMG NOPs ===
    n = 0
    for r in [0x47, 0x48, 0x49]:
        for i in range(len(rom) - 1):
            if rom[i] == 0xE0 and rom[i+1] == r:
                rom[i] = rom[i+1] = 0x00
                n += 1
    print(f"  DMG NOPs: {n}")

    # === Phase 2: OBJ palette LUT ===
    pt = build_obj_pal_table()
    off = BANK13 + (OBJ_PAL_TABLE_ADDR - 0x4000)
    rom[off:off + 256] = pt

    # Build trampolines, place in bank 13 free space at TRAMP_ROM_SRC
    t1, t2, t3 = s1_tramp(), s2_tramp(), s3_tramp()
    blob = t1 + t2 + t3
    print(f"  Tramps: s1={len(t1)} s2={len(t2)} s3={len(t3)} total={len(blob)}")
    off = BANK13 + (TRAMP_ROM_SRC - 0x4000)
    for i in range(len(blob)):
        assert rom[off + i] == 0, f"tramp site {TRAMP_ROM_SRC + i:04X} not free"
    rom[off:off + len(blob)] = blob
    print(f"  Tramps at bank13:0x{TRAMP_ROM_SRC:04X}")

    # === Phase 3: OAM intercept hooks ===

    # Site 1: 0x10E4 (12 13 -> CD ll hh)
    assert bytes(rom[0x10E4:0x10E6]) == bytes([0x12, 0x13]), "site1 changed"
    rom[0x10E4:0x10E7] = _B([0xCD, S1_TRAMP & 0xFF, (S1_TRAMP >> 8) & 0xFF])
    print(f"  Site1: 0x10E4 CALL {S1_TRAMP:04X}")

    # Site 2: 0x3487 (7A 22 F5 -> CD ll hh)
    assert bytes(rom[0x3487:0x348A]) == bytes([0x7A, 0x22, 0xF5]), "site2 changed"
    rom[0x3487:0x348A] = _B([0xCD, S2_TRAMP & 0xFF, (S2_TRAMP >> 8) & 0xFF])
    print(f"  Site2: 0x3487 CALL {S2_TRAMP:04X}")

    # Site 2 memcpy fix: 0x3499: 03 -> 04 (LD BC, $0003 -> LD BC, $0004)
    assert rom[0x3499] == 0x03, f"memcpy size at 0x3499: {rom[0x3499]}"
    rom[0x3499] = 0x04
    print(f"  Site2: memcpy 3->4 at 0x349A")

    # Site 3: bank1:0x5221 (13 2A 12 -> CD ll hh)
    b1 = 0x4000
    addr = b1 + (0x5221 - 0x4000)
    assert bytes(rom[addr:addr + 3]) == bytes([0x13, 0x2A, 0x12]), "site3 changed"
    rom[addr:addr + 3] = _B([0xCD, S3_TRAMP & 0xFF, (S3_TRAMP >> 8) & 0xFF])
    print(f"  Site3: bank1:0x5221 CALL {S3_TRAMP:04X}")

    # === Phase 4: Remove stamper from wrapper ===
    found = False
    for i in range(len(rom) - 2):
        if rom[i] == 0xCD:
            tgt = rom[i+1] | (rom[i+2] << 8)
            if tgt == OBJ_STAMPER_ADDR:
                print(f"  Stamper CALL at 0x{i:04X} -> NOP")
                rom[i:i+3] = _B([0x00, 0x00, 0x00])
                found = True
                break
    if not found:
        print("  WARNING: stamper CALL not found")

    # Remove FF09 writes
    for i in range(len(rom) - 1):
        if rom[i] == 0xE0 and rom[i+1] == 0x09:
            print(f"  FF09 write at 0x{i:04X} -> NOP")
            rom[i:i+2] = _B([0x00, 0x00])

    # === Phase 5: Augment teleport routine with LUT copy + tramp copy ===
    tp = bytearray(build_teleport_routine())
    # Find sentinel write (3E 5A EA 0E DF)
    sentinel = bytes([0x3E, 0x5A, 0xEA, 0x0E, 0xDF])
    si = tp.find(sentinel)
    if si < 0:
        print("ERROR: sentinel not found in teleport routine")
        sys.exit(1)

    # Build LUT copy (6B00 -> D900, 256B)
    lc = _B()
    lc.extend([0x21, OBJ_PAL_TABLE_ADDR & 0xFF, (OBJ_PAL_TABLE_ADDR >> 8) & 0xFF])
    lc.extend([0x11, OBJ_PAL_WRAM & 0xFF, (OBJ_PAL_WRAM >> 8) & 0xFF])
    lc.extend([0x06, 0x00])  # B=0 = 256
    l = len(lc)
    lc.extend([0x2A, 0x12, 0x13, 0x05, 0x20, (l - (len(lc) + 2)) & 0xFF])
    print(f"  LUT copy: {len(lc)} bytes")

    # Build trampoline copy (6A70 -> DB80)
    tc = _B()
    tc.extend([0x21, TRAMP_ROM_SRC & 0xFF, (TRAMP_ROM_SRC >> 8) & 0xFF])
    tc.extend([0x11, WRAM_TRAMP_BASE & 0xFF, (WRAM_TRAMP_BASE >> 8) & 0xFF])
    tc.extend([0x06, len(blob)])
    l = len(tc)
    tc.extend([0x2A, 0x12, 0x13, 0x05, 0x20, (l - (len(tc) + 2)) & 0xFF])
    print(f"  Tramp copy: {len(tc)} bytes")

    # Insert before sentinel
    tp[si:si] = lc + tc

    # Last byte should be RET (C9), replace with JP COLORIZE
    assert tp[-1] == 0xC9, f"last byte: {tp[-1]:02X}"
    tp[-1] = 0xC3
    tp.extend([COLORIZE_ADDR & 0xFF, (COLORIZE_ADDR >> 8) & 0xFF])

    print(f"  Teleport: {len(tp)} bytes at 0x{TELEPORT_ADDR:04X}")
    assert TELEPORT_ADDR + len(tp) <= WRAPPER_ADDR, \
        f"teleport 0x{TELEPORT_ADDR + len(tp):04X} > wrapper 0x{WRAPPER_ADDR:04X}"

    off = BANK13 + (TELEPORT_ADDR - 0x4000)
    rom[off:off + len(tp)] = tp

    # === Fix: relocate colorize handler tail (FFC1 gate + shadow_main + OAM DMA + VBK restore + RET)
    SHADOW_MAIN_ADDR = 0x69D0
    COLORIZE_TAIL_ADDR = 0x6F50   # between teleport routine end (~0x6F3D) and wrapper (0x6F60)
    off = BANK13 + (0x6E7E - 0x4000)
    rom[off:off + 3] = _B([0xC3, COLORIZE_TAIL_ADDR & 0xFF, (COLORIZE_TAIL_ADDR >> 8) & 0xFF])
    tail = _B([
        0xF0, 0xC1,                               # LDH A, [FFC1]
        0xB7,                                      # OR A
        0x28, 0x06,                                # JR Z, +6 (skip shadow_main + OAM DMA)
        0xCD, SHADOW_MAIN_ADDR & 0xFF, (SHADOW_MAIN_ADDR >> 8) & 0xFF,
        0xCD, 0x80, 0xFF,                          # CALL OAM DMA
        0xF1, 0xE0, 0x4F,                          # POP AF; LDH [VBK], A
        0xC9,                                      # RET
    ])
    assert len(tail) == 15, f"tail code length: {len(tail)}"
    off = BANK13 + (COLORIZE_TAIL_ADDR - 0x4000)
    rom[off:off + len(tail)] = tail

    # === Write wrapper (no stamper) at WRAPPER_ADDR ===
    wr = build_wrapper()
    print(f"  Wrapper: {len(wr)} bytes at 0x{WRAPPER_ADDR:04X}")
    off = BANK13 + (WRAPPER_ADDR - 0x4000)
    rom[off:off + len(wr)] = wr

    # === Write landing pad at new address ===
    lp = bytearray(build_landing_pad())
    assert len(lp) <= 40, f"landing pad {len(lp)} > 40"
    lp.extend(bytes(40 - len(lp)))  # pad to 40
    print(f"  Landing pad: {len(lp)} bytes at 0x{LANDING_PAD_ROM:04X}")
    off = BANK13 + (LANDING_PAD_ROM - 0x4000)
    rom[off:off + len(lp)] = lp

    # === Fix VBlank hook CALL target (old WRAPPER_ADDR -> new) ===
    old_wrapper = 0x6F50  # teleport build's wrapper addr (build_v301_teleport.py WRAPPER_ADDR)
    found_hook = False
    for i in range(len(rom) - 2):
        if rom[i] == 0xCD:
            tgt = rom[i+1] | (rom[i+2] << 8)
            if tgt == old_wrapper:
                print(f"  VBlank hook CALL at 0x{i:04X}: {old_wrapper:04X} -> {WRAPPER_ADDR:04X}")
                rom[i+1] = WRAPPER_ADDR & 0xFF
                rom[i+2] = (WRAPPER_ADDR >> 8) & 0xFF
                found_hook = True
    if not found_hook:
        print("  WARNING: VBlank hook CALL target not found")

    # === Fix landing pad ROM address in teleport routine ===
    old_lp = 0x6F80
    new_lp = LANDING_PAD_ROM
    off = BANK13 + (TELEPORT_ADDR - 0x4000)
    found_lp = False
    for i in range(off, off + len(tp) + 10):
        val = rom[i] | (rom[i+1] << 8)
        if val == old_lp:
            print(f"  LP addr ref at 0x{i:05X}: {old_lp:04X} -> {new_lp:04X}")
            rom[i] = new_lp & 0xFF
            rom[i+1] = (new_lp >> 8) & 0xFF
            found_lp = True
    if not found_lp:
        print("  WARNING: landing pad address ref not found")

    # === Header checksum ===
    chk = 0
    for b in rom[0x134:0x14D]:
        chk = (chk - b - 1) & 0xFF
    rom[0x14D] = chk

    out_path = TP_OUT
    out_path.write_bytes(rom)
    print(f"\nWrote {out_path} ({len(rom)} bytes)")
    print()
    print("=== O(1) Shadow OAM Intercept Applied ===")
    print("  OBJ palette LUT: bank13:0x6B00 -> WRAM 0xD900")
    print("  Trampolines: bank13:0x6A70 -> WRAM 0xDB80")
    print("  Site 1 (central @ 0x10E4): CALL WRAM tramp")
    print("  Site 2 (free-slot @ 0x3487): CALL WRAM tramp")
    print("  Site 3 (bank1 @ 0x5221): CALL WRAM tramp")
    print("  Stamper CALL removed from VBlank wrapper")
    print("  Palette assigned at sprite-emission time (O(1) per sprite)")


if __name__ == "__main__":
    main()
