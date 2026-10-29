#!/usr/bin/env python3
"""Build the English DX variant: HTI's v1.00 translation merged into a DX ROM.

The HTI patch (penta.ips, Hiryuu/Tyrome Williams, 2003, hti.rpgclassics.com)
is NOT redistributed here; pass its path. Every IPS byte must land on a byte
DX leaves stock (asserted), except the bank-1 title text table, which both
patches rewrite and which is merged record-by-record (docs/english_variant.md).
DX's patched copy of bank 0E (bank 13) receives the same cinema-text edits.
The Japanese DX ROM is an input only and is never modified.
"""
import argparse, hashlib, json, sys
from pathlib import Path

ENGLISH_ORIGINAL_SHA = '5a8c4b63bf198865a1eacaaf2072e54b2ad47895902aa87851db0e08887b69f0'
IPS_SHA = '9ac36c13e6e4bd97de23f00480d2aa1b0e437f62b604d6e65ff5a9680767051d'
TITLE_START, TITLE_END = 0x4E63, 0x4F28          # 01:4E63 table (+4EA5 subtable)
BANK0E, BANK13 = 0x38000, 0x4C000                # DX mirror of cinema bank
DX_TAIL = bytes.fromhex('000ec09a000fd0d7d8d9')   # kana (c) row 0E + row 0F
EN_TAIL = bytes.fromhex('000f52d7d8d9')           # single-tile (c) on row 0F


def parse_ips(data):
    if data[:5] != b'PATCH':
        raise ValueError('not an IPS file')
    i, recs = 5, []
    while data[i:i + 3] != b'EOF':
        off = int.from_bytes(data[i:i + 3], 'big'); n = int.from_bytes(data[i + 3:i + 5], 'big'); i += 5
        if n == 0:
            n = int.from_bytes(data[i:i + 2], 'big'); val = data[i + 2:i + 3] * n; i += 3
        else:
            val = data[i:i + n]; i += n
        recs.append((off, val))
    return recs


def apply_ips(rom, recs):
    r = bytearray(rom)
    for off, val in recs:
        r[off:off + len(val)] = val
    return bytes(r)


def merge_title(table):
    k = table.find(DX_TAIL)
    if k <= 0:
        raise ValueError('DX title copyright rows not found')
    rest = table[k + len(DX_TAIL):]
    end = rest.find(bytes.fromhex('9a9a9a9ae5'))
    if end < 0:
        raise ValueError('DX title table terminator/slack not found')
    # The kana (c) record's 4 bytes become slack; DX title rows outside its
    # palette rows do not render, so no credit is placed here (see ending).
    merged = table[:k] + EN_TAIL + rest[:end + 1] + b'\x9a' * 7 + rest[end + 4:]
    if len(merged) != len(table):
        raise ValueError('merged title table changed length')
    return merged


# Script text (bank 0F 4803-) encoding, from HTI's own text.
def script(text):
    out = bytearray()
    for ch in text:
        if ch == ' ': out.append(0x00)
        elif ch == '\n': out.append(0x71)
        elif 'A' <= ch <= 'Z': out.append(0x0B + ord(ch) - 65)
        elif 'a' <= ch <= 'z': out.append(0x25 + ord(ch) - 97)
        elif ch == '.': out.append(0x54)
        else: raise ValueError(ch)
    return bytes(out)


# The last line of the ending dialogue (scene 1A): "...MOTHER!!!" + 4c (closing quote glyph),
# then 6c 6c and the epilogue section header.  The credit pages are inserted after
# that wait so they show in every normal playthrough, right before the staff roll.
ENDING_LAST = bytes.fromhex('17191e120f1cfbfbfb4c6c6cfe')
CREDIT = (bytes.fromhex('6c6c70') + script('English version\nby HTI\nHacking  Hiryuu') + bytes([0xF1])
          + bytes.fromhex('6c6c70') + script('Translation\nTyrome Williams\nHelp  Kero Hazel') + bytes([0xF1]))
SCRIPT_END_FILE = 0x3D138          # first byte after the stock end marker fe 00 fd
NOISE_END_FILE = 0x3D400           # unreferenced noise fill (no bank-0F/0 pointer into it)


def add_ending_credit(r, original):
    k = r.find(ENDING_LAST, 0x3C803, SCRIPT_END_FILE)
    if k < 0 or r.find(ENDING_LAST, k + 1, SCRIPT_END_FILE) >= 0:
        raise ValueError('HTI ending last line not found exactly once')
    if r[SCRIPT_END_FILE:NOISE_END_FILE] != original[SCRIPT_END_FILE:NOISE_END_FILE]:
        raise ValueError('bank-0F fill after the script is not stock')
    ins = k + 10                   # after "MOTHER!!!" and its closing quote (4c is the '”' glyph)
    tail = bytes(r[ins:SCRIPT_END_FILE])
    r[ins:ins + len(CREDIT) + len(tail)] = CREDIT + tail
    return len(CREDIT)


def fix_checksums(r):
    x = 0
    for b in r[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    r[0x14D] = x
    s = (sum(r) - r[0x14E] - r[0x14F]) & 0xFFFF
    r[0x14E:0x150] = s.to_bytes(2, 'big')


def build(original, dx, ips):
    if hashlib.sha256(ips).hexdigest() != IPS_SHA:
        raise ValueError('not HTI penta.ips v1.00')
    english = apply_ips(original, parse_ips(ips))
    if hashlib.sha256(english).hexdigest() != ENGLISH_ORIGINAL_SHA:
        raise ValueError('IPS on this original does not give HTI v1.00')
    r, edits, mirrored = bytearray(dx), 0, 0
    for i in range(len(original)):
        if original[i] == english[i] or i in (0x14D, 0x14E, 0x14F) or TITLE_START <= i < TITLE_END:
            continue
        if dx[i] != original[i]:
            raise ValueError(f'IPS byte {i:05X} collides with a DX change')
        r[i] = english[i]; edits += 1
        if BANK0E <= i < BANK0E + 0x4000:
            j = i - BANK0E + BANK13
            if dx[j] != original[i]:
                raise ValueError(f'bank-13 mirror preimage differs at {j:05X}')
            r[j] = english[i]; mirrored += 1
    r[TITLE_START:TITLE_END] = merge_title(bytes(dx[TITLE_START:TITLE_END]))
    credit = add_ending_credit(r, original)
    fix_checksums(r)
    return bytes(r), dict(ips_bytes_applied=edits, bank13_mirrored=mirrored, ending_credit_bytes=credit)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path, required=True)
    p.add_argument('--dx', type=Path, required=True)
    p.add_argument('--ips', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    o, d, i = a.original.read_bytes(), a.dx.read_bytes(), a.ips.read_bytes()
    rom, stats = build(o, d, i)
    a.output.write_bytes(rom)
    h = lambda b: hashlib.sha256(b).hexdigest()
    receipt = dict(schema='english-variant-v1', original_sha256=h(o), dx_sha256=h(d), ips_sha256=h(i),
                   output_sha256=h(rom), builder_sha256=h(Path(__file__).read_bytes()), **stats,
                   patch='HTI Penta Dragon English v1.00 (2003-02-28): hacking Hiryuu, translation Tyrome Williams')
    a.output.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    sys.exit(main())
