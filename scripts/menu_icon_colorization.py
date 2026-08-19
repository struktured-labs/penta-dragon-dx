#!/usr/bin/env python3
"""Isolated expanded-bank publisher for native item-menu icon palettes."""

from __future__ import annotations

from arena_position import _Asm


BANK_SIZE = 0x4000
MENU_HELPER_BANK = 20
MENU_FIRST_ENTRY = 0x4000
MENU_INTERACTIVE_ENTRY = 0x4017
MENU_LUT_ADDR = 0x4100
MENU_FIXED_FIRST = 0x1B48
MENU_FIXED_INTERACTIVE = 0x1D78
MENU_PRELUDE_BANK = 13
MENU_PRELUDE_ADDR = 0x6E80

MENU_SETUP = bytes.fromhex("F3 3E 07 E0 4B 3E 60 E0 4A")
MENU_PALETTE_SERVICE = bytes.fromhex(
    "3E C4 E0 48 3E 00 E0 49 3E E4 E0 47"
)
MENU_FIRST_PREIMAGE = bytes.fromhex(
    "F3 3E 07 E0 4B 3E 60 E0 4A CD E4 41 CD 0E 20 "
    "F0 40 CB EF E0 40 FB"
)
MENU_INTERACTIVE_PREIMAGE = bytes.fromhex(
    "F3 3E 07 E0 4B 3E 60 E0 4A CD 0E 20 "
    "F0 40 CB EF E0 40 FB"
)
RELATIVE_LOOP_PREIMAGES = (
    (0x1DC0, bytes.fromhex("28 BF")),
    (0x1DD9, bytes.fromhex("28 A6")),
)
ABSOLUTE_LOOP_PREIMAGES = (
    (0x1DF3, bytes.fromhex("CA 81 1D")),
    (0x1E05, bytes.fromhex("C3 81 1D")),
    (0x1EBD, bytes.fromhex("C3 81 1D")),
    (0x1F5D, bytes.fromhex("C3 81 1D")),
)


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: 0x{address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def _fixed_wrapper(entry: int, capacity: int) -> bytes:
    """Map bank 20, run one menu publisher, restore bank and LCDC in A."""
    code = bytes([
        0xF0, 0x99,                         # LDH A,[FF99]
        0xF5,                               # PUSH AF
        0x3E, MENU_HELPER_BANK,
        0xCD, 0x61, 0x00,                   # coherent mapper helper
        0xCD, entry & 0xFF, entry >> 8,
        0xF1,
        0xCD, 0x61, 0x00,                   # restore caller's bank
        0xF0, 0x40,                         # match native A=LCDC exit
    ])
    if len(code) > capacity:
        raise AssertionError((len(code), capacity))
    return code + bytes(capacity - len(code))


def build_menu_helper() -> tuple[bytes, int]:
    """Build the bank-20 HBlank-safe attribute publisher and its used size."""
    a = _Asm()
    lookup_calls: list[int] = []

    # The alternate entry preserves the first native route's palette-register
    # setup before joining the ordinary SELECT-menu route.
    a.label("first")
    a.db(MENU_SETUP, MENU_PALETTE_SERVICE)
    a.jr(0x18, "common")
    if MENU_FIRST_ENTRY + len(a.code) != MENU_INTERACTIVE_ENTRY:
        raise AssertionError((len(a.code), MENU_INTERACTIVE_ENTRY))
    a.label("interactive")
    a.db(MENU_SETUP)

    a.label("common")
    a.db(0xCD, 0x0E, 0x20)                  # exact stock six-row tile copy
    a.db(0xF3, 0xF0, 0x4F, 0xF5)            # DI; preserve incoming VBK
    a.db(0x3E, 0x01, 0xE0, 0x4F)            # VBK1 attribute plane

    # The stock copier has already selected the Window map in LCDC.6.
    a.db(0xF0, 0x40, 0xE6, 0x40, 0x26, 0x98)
    a.jr(0x28, "map_ready")
    a.db(0x26, 0x9C)
    a.label("map_ready")
    a.db(0x2E, 0x00, 0x11, 0xE0, 0xC4, 0x06, 0x06)

    a.label("row")
    a.db(0x0E, 0x0A)                        # ten two-cell HBlanks
    a.label("pair")
    # Compute both attributes before the timing window. B/C temporarily hold
    # the two values while their outer counters remain balanced on the stack.
    a.db(0xC5, 0x1A, 0x13)
    lookup_calls.append(len(a.code) + 1)
    a.db(0xCD, 0x00, 0x00, 0x47)
    a.db(0x1A, 0x13)
    lookup_calls.append(len(a.code) + 1)
    a.db(0xCD, 0x00, 0x00, 0x4F)

    a.label("wait_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "wait_mode3")
    a.label("wait_mode0")
    a.db(0xF0, 0x41, 0xE6, 0x03)
    a.jr(0x20, "wait_mode0")
    a.db(0x78, 0x22, 0x79, 0x22, 0xC1, 0x0D)
    a.jr(0x20, "pair")

    # Skip the twelve hidden map columns and continue for all six rows.
    a.db(0x78, 0x06, 0x00, 0x0E, 0x0C, 0x09, 0x47, 0x05)
    a.jr(0x20, "row")

    # Publish only after every tile and attribute is complete.
    a.db(
        0xF1, 0xE0, 0x4F,
        0xF0, 0x40, 0xCB, 0xEF, 0xE0, 0x40,
        0xFB, 0xC9,
    )

    a.label("lookup")
    a.db(0xE5, 0x6F, 0x26, MENU_LUT_ADDR >> 8, 0x7E, 0xE1, 0xC9)
    code = bytearray(a.finish())
    lookup_addr = MENU_FIRST_ENTRY + a.labels["lookup"]
    for operand in lookup_calls:
        code[operand] = lookup_addr & 0xFF
        code[operand + 1] = lookup_addr >> 8
    if MENU_FIRST_ENTRY + len(code) > MENU_LUT_ADDR:
        raise AssertionError((len(code), MENU_LUT_ADDR))
    return bytes(code), len(code)


def _menu_owned_prelude(prelude: bytes) -> bytes:
    """Retire only the now-redundant live-Window scrub path in-place."""
    code = bytearray(prelude)
    stale = code.find(bytes.fromhex("CD 40 6A 28"))
    finish_marker = code.find(bytes.fromhex("F1 E0 4F 23 2B C3"))
    if stale < 0 or finish_marker < 0:
        raise AssertionError("menu Window maintenance layout moved")
    body_start = stale + 5                     # after JR Z,window_off
    finish = finish_marker + 3                 # receipt-locked INC/DEC/JP
    displacement = finish - (body_start + 2)
    if not -128 <= displacement <= 127:
        raise AssertionError(displacement)
    code[body_start:finish] = bytes([
        0x18, displacement & 0xFF,
    ]) + bytes(finish - body_start - 2)
    return bytes(code)


def expected_bank20(canonical_lut: bytes, arena_bank: bytes) -> bytes:
    """Return bank 20 with its existing arena helpers plus the menu payload."""
    if len(arena_bank) != BANK_SIZE or len(canonical_lut) != 0x100:
        raise ValueError("invalid bank/LUT size")
    bank = bytearray(arena_bank)
    helper, _ = build_menu_helper()
    helper_off = MENU_FIRST_ENTRY - 0x4000
    lut_off = MENU_LUT_ADDR - 0x4000
    if bank[helper_off:helper_off + len(helper)] != bytes([0xFF]) * len(helper):
        raise AssertionError("bank-20 menu helper range is not free")
    if bank[lut_off:lut_off + len(canonical_lut)] != bytes([0xFF]) * 0x100:
        raise AssertionError("bank-20 menu LUT range is not free")
    bank[helper_off:helper_off + len(helper)] = helper
    bank[lut_off:lut_off + 0x100] = canonical_lut
    return bytes(bank)


def install_menu_icon_colorization(rom: bytearray, prelude: bytes) -> dict[str, int]:
    """Install the optional menu-only publisher into a combined 512 KiB ROM."""
    if len(rom) != 32 * BANK_SIZE:
        raise AssertionError(f"expected 512 KiB image, got {len(rom)} bytes")

    # Both native menu entries become same-width fixed-bank mappers.  The
    # stock $200E copier itself remains byte-for-byte untouched.
    if rom[MENU_FIXED_FIRST:MENU_FIXED_FIRST + len(MENU_FIRST_PREIMAGE)] != MENU_FIRST_PREIMAGE:
        raise AssertionError("first menu entry preimage moved")
    if rom[
        MENU_FIXED_INTERACTIVE:
        MENU_FIXED_INTERACTIVE + len(MENU_INTERACTIVE_PREIMAGE)
    ] != MENU_INTERACTIVE_PREIMAGE:
        raise AssertionError("interactive menu entry preimage moved")
    rom[MENU_FIXED_FIRST:MENU_FIXED_FIRST + len(MENU_FIRST_PREIMAGE)] = (
        _fixed_wrapper(MENU_FIRST_ENTRY, len(MENU_FIRST_PREIMAGE))
    )
    rom[
        MENU_FIXED_INTERACTIVE:
        MENU_FIXED_INTERACTIVE + len(MENU_INTERACTIVE_PREIMAGE)
    ] = _fixed_wrapper(MENU_INTERACTIVE_ENTRY, len(MENU_INTERACTIVE_PREIMAGE))

    # Every interactive redraw now re-enters the complete helper, rather than
    # the old internal stock-copy/window-publication suffix at $1D81.
    for address, expected in RELATIVE_LOOP_PREIMAGES:
        if rom[address:address + 2] != expected:
            raise AssertionError(f"relative menu edge moved at 0x{address:04X}")
        displacement = MENU_FIXED_INTERACTIVE - (address + 2)
        rom[address + 1] = displacement & 0xFF
    for address, expected in ABSOLUTE_LOOP_PREIMAGES:
        if rom[address:address + 3] != expected:
            raise AssertionError(f"absolute menu edge moved at 0x{address:04X}")
        rom[address + 1:address + 3] = MENU_FIXED_INTERACTIVE.to_bytes(2, "little")

    # The helper reads a private copy of the immutable canonical Stage-1 LUT;
    # later-stage and boss C600 tables therefore cannot recolor menu icons.
    canonical_off = bank_offset(13, 0x7000)
    canonical_lut = bytes(rom[canonical_off:canonical_off + 0x100])
    bank20_start = MENU_HELPER_BANK * BANK_SIZE
    arena_bank = bytes(rom[bank20_start:bank20_start + BANK_SIZE])
    rom[bank20_start:bank20_start + BANK_SIZE] = expected_bank20(
        canonical_lut, arena_bank
    )

    # The completed menu publisher owns all six visible attrs before LCDC.5
    # is set. Bypass only the old live-Window scrub; the stale-Window guard,
    # Window-off reset, and every non-menu byte retain their original layout.
    prelude_off = bank_offset(MENU_PRELUDE_BANK, MENU_PRELUDE_ADDR)
    if rom[prelude_off:prelude_off + len(prelude)] != prelude:
        raise AssertionError("qualified production prelude moved")
    menu_prelude = _menu_owned_prelude(prelude)
    rom[prelude_off:prelude_off + len(prelude)] = menu_prelude

    helper, helper_size = build_menu_helper()
    return {
        "helper_bank": MENU_HELPER_BANK,
        "helper_entry": MENU_FIRST_ENTRY,
        "interactive_entry": MENU_INTERACTIVE_ENTRY,
        "helper_size": helper_size,
        "lut_size": len(canonical_lut),
        "prelude_changed_bytes": sum(a != b for a, b in zip(prelude, menu_prelude)),
    }
