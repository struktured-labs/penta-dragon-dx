#!/usr/bin/env python3
"""Expanded-bank semantic row writer for Stage-1 rotating hazards."""

from __future__ import annotations

from arena_position import _Asm


BANK_SIZE = 0x4000
HELPER_BANK = 20
HELPER_ENTRY = 0x4300
LUT_ADDR = 0x4400
# $67ED is the column-2 envelope publisher in bank 14. The same numeric bank-
# 20 slot is a normal helper trampoline after the stock mapper changes banks.
CALLER_RETURNS = (0x61A0, 0x67ED, 0x6B70, 0x6D9E)
# The interrupt-safe completed-copy dispatcher now owns $6CCE-$6CDD. Keep the
# dual-bank return bridge immediately after it in independently asserted-free
# expanded-bank storage: bank 20 owns the five-byte mapper at $6CDF, while
# private bank 19 owns its three-byte continuation at $6CE4. Both end before
# the existing bank-19 code beginning at $6CE9.
RETURN_BRIDGE = 0x6CDF
PRIVATE_RETURN = RETURN_BRIDGE + 5
# Matched rows return to the scanner's stock-width row-advance tail.  The
# production baseline deliberately scans all 24 rows: later experiments that
# cached or short-circuited this path were faster in theory but changed the
# movement/collision cadence and failed the strict speed fixture.
PRIVATE_CONTINUATION = 0x61F6
STAGE1_TABLE_BANK = 13
STAGE1_TABLE_ADDR = 0x7000
STAGE1_PRIVATE_BANK = 19
TOOTH_TILES = frozenset((*range(0x64, 0x6A), *range(0x74, 0x7A)))


def bank_offset(bank: int, address: int) -> int:
    if not 0x4000 <= address < 0x8000:
        raise ValueError(f"switchable address out of range: 0x{address:04X}")
    return bank * BANK_SIZE + address - 0x4000


def build_helper() -> bytes:
    """Write C source-owned attrs at HL, two cells per safe HBlank.

    The switchable-bank caller tail-maps bank 20 and supplies DE=packed
    source, HL=destination, and C=span length. The helper owns B/C/E while
    the scanner's originals remain on its outer stack. Each bank-19 caller
    maps bank 20 with the stock mapper; its numeric return address is a bank-20
    trampoline into this helper. The helper tail maps bank 19 from a second
    dual-bank bridge, whose matching bank-19 address jumps to the scanner
    continuation. No return address is ever consumed under the wrong bank.
    """
    a = _Asm()
    lookup_calls: list[int] = []

    # Menu/item transitions can complete a packed-map publication while the
    # LCD is disabled.  Waiting for mode 3 in that state can never terminate.
    # VRAM is continuously accessible with LCDC.7 clear, so use a bounded
    # direct semantic copy for that exact case and retain the reviewed
    # mode-3 -> mode-0 cadence for rendered gameplay.
    a.db(0xF0, 0x40, 0xCB, 0x7F)           # LCDC bit 7 set?
    a.jr(0x28, "lcd_off")
    a.db(0x3E, 0x01, 0xE0, 0x4F)           # destination attributes (VBK1)
    a.db(0x79, 0xE6, 0x01, 0xF5)           # save odd-cell flag
    a.db(0xCB, 0x39)                       # C = pair count
    a.jr(0x28, "pairs_done")

    a.label("pair")
    a.db(0x1A, 0x13)
    lookup_calls.append(len(a.code) + 1)
    a.db(0xCD, 0x00, 0x00, 0x47)           # B = first semantic attr
    a.db(0x1A, 0x13)
    lookup_calls.append(len(a.code) + 1)
    a.db(0xCD, 0x00, 0x00)
    a.db(0xD5, 0x5F)                       # save source; E = second attr
    a.label("pair_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "pair_mode3")
    a.label("pair_mode0")
    a.db(0xF0, 0x41, 0xE6, 0x03)
    a.jr(0x20, "pair_mode0")
    a.db(0x78, 0x22, 0x7B, 0x22, 0xD1, 0x0D)
    a.jr(0x20, "pair")

    a.label("pairs_done")
    a.db(0xF1, 0xB7)
    a.jr(0x28, "done")
    a.db(0x1A)
    lookup_calls.append(len(a.code) + 1)
    a.db(0xCD, 0x00, 0x00, 0x47)
    a.label("single_mode3")
    a.db(0xF0, 0x41, 0xE6, 0x03, 0xFE, 0x03)
    a.jr(0x20, "single_mode3")
    a.label("single_mode0")
    a.db(0xF0, 0x41, 0xE6, 0x03)
    a.jr(0x20, "single_mode0")
    a.db(0x78, 0x22)
    a.jr(0x18, "done")

    a.label("lcd_off")
    a.db(0x3E, 0x01, 0xE0, 0x4F)
    a.label("lcd_off_cell")
    a.db(0x1A, 0x13)
    lookup_calls.append(len(a.code) + 1)
    a.db(0xCD, 0x00, 0x00, 0x22, 0x0D)
    a.jr(0x20, "lcd_off_cell")

    a.label("done")
    a.db(0xAF, 0xE0, 0x4F)                 # restore tile-map bank
    a.db(0xC3, RETURN_BRIDGE & 0xFF, RETURN_BRIDGE >> 8)

    a.label("lookup")
    a.db(0xE5, 0x6F, 0x26, LUT_ADDR >> 8, 0x7E, 0xE1, 0xC9)
    code = bytearray(a.finish())
    lookup_addr = HELPER_ENTRY + a.labels["lookup"]
    for operand in lookup_calls:
        code[operand] = lookup_addr & 0xFF
        code[operand + 1] = lookup_addr >> 8
    if HELPER_ENTRY + len(code) > LUT_ADDR:
        raise AssertionError((len(code), LUT_ADDR))
    return bytes(code)


def build_lut(stage1_lut: bytes) -> bytes:
    """Add VRAM-bank 1 only to real teeth; preserve every other YAML role."""
    if len(stage1_lut) != 0x100:
        raise ValueError("Stage-1 semantic LUT must contain 256 bytes")
    result = bytearray(value & 0x07 for value in stage1_lut)
    for tile in TOOTH_TILES:
        if result[tile] != 7:
            raise AssertionError(f"tooth tile ${tile:02X} is not YAML BG7")
        result[tile] = 0x0F
    return bytes(result)


def install(rom: bytearray) -> dict[str, int]:
    """Install the helper and LUT into asserted-free expanded bank 20."""
    if len(rom) != 32 * BANK_SIZE:
        raise AssertionError(f"expected 512 KiB image, got {len(rom)} bytes")
    helper = build_helper()
    helper_off = bank_offset(HELPER_BANK, HELPER_ENTRY)
    lut_off = bank_offset(HELPER_BANK, LUT_ADDR)
    if rom[helper_off:helper_off + len(helper)] != bytes([0xFF]) * len(helper):
        raise AssertionError("bank-20 Stage-1 semantic helper range is not free")
    if rom[lut_off:lut_off + 0x100] != bytes([0xFF]) * 0x100:
        raise AssertionError("bank-20 Stage-1 semantic LUT range is not free")
    for address in (*CALLER_RETURNS, RETURN_BRIDGE):
        size = 5 if address == RETURN_BRIDGE else 3
        offset = bank_offset(HELPER_BANK, address)
        if rom[offset:offset + size] != bytes([0xFF]) * size:
            raise AssertionError(
                f"bank-20 Stage-1 bridge ${address:04X} is not free"
            )
    private_return_off = bank_offset(STAGE1_PRIVATE_BANK, PRIVATE_RETURN)
    if rom[private_return_off:private_return_off + 3] != bytes(3):
        raise AssertionError("bank-19 Stage-1 return bridge is not free")
    table_off = bank_offset(STAGE1_TABLE_BANK, STAGE1_TABLE_ADDR)
    lut = build_lut(bytes(rom[table_off:table_off + 0x100]))
    rom[helper_off:helper_off + len(helper)] = helper
    for address in CALLER_RETURNS:
        offset = bank_offset(HELPER_BANK, address)
        rom[offset:offset + 3] = bytes([
            0xC3, HELPER_ENTRY & 0xFF, HELPER_ENTRY >> 8,
        ])
    bridge_off = bank_offset(HELPER_BANK, RETURN_BRIDGE)
    rom[bridge_off:bridge_off + 5] = bytes([
        0x3E, STAGE1_PRIVATE_BANK, 0xCD, 0x61, 0x00,
    ])
    rom[private_return_off:private_return_off + 3] = bytes([
        0xC3, PRIVATE_CONTINUATION & 0xFF,
        PRIVATE_CONTINUATION >> 8,
    ])
    rom[lut_off:lut_off + len(lut)] = lut
    return {
        "bank": HELPER_BANK,
        "entry": HELPER_ENTRY,
        "helper_size": len(helper),
        "lut_size": len(lut),
    }
