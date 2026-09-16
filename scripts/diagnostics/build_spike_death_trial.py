#!/usr/bin/env python3
"""Experimental Stage-1 death-entry attribute retirement and prelude rearm.

Exact row-guard parent only. Uses the expanded build's retired bank13 Ted
fragment, not its live bank16 counterpart. Not release-qualified.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT = "e709869c85edfd647dd01dbca0c222a493b335ee6759adaa573416143a66e45b"
CANDIDATE_SHA = "c693eafb50e7872fa884d0d26ce3fbfd4f2fac0dba246ff738931643e7f0ba5d"


def offset(bank, address):
    return bank * 0x4000 + address - 0x4000


def cleanup_body():
    return bytes.fromhex(
        "C5 D5 "             # preserve BC, DE; native clear will replace HL
        "3E 01 E0 91 "       # rearm scene prelude before returning to title
        "F0 FF F5 AF E0 FF " # preserve/mask IE without changing IME
        "F0 40 F5 CB 7F 28 06 "
        "F0 44 FE 90 38 FA " # if enabled, wait for legal LCD-off boundary
        "AF E0 40 "          # LCD off: retire stale bank/flip/priority attrs
        "F0 4F F5 3E 01 E0 4F "
        "21 00 98 01 00 08 16 00 "
        "72 23 0B 78 B1 20 F9 " # clear both 1024-byte physical map planes
        "21 00 FE 06 A0 AF 22 05 20 FC " # retire OAM while writable
        "F1 E0 4F F1 E0 40 F1 E0 FF D1 C1 "
        "21 95 71 E5 3E 0D C3 61 00" # bank13 -> native OAM clear -> caller
    )


def patches():
    title_guard = bytes.fromhex("FA 80 D8 FE 01 CA 73 6A C3 45 7E")
    body = cleanup_body()
    return (
        (13, 0x713F, bytes.fromhex("CD 95 71"), bytes.fromhex("CD 60 58")),
        (13, 0x5860, bytes(5), bytes.fromhex("3E 19 CD 61 00")),
        (13, 0x6A97, bytes.fromhex("C3 45 7E"), bytes.fromhex("C3 65 58")),
        (13, 0x5865, bytes(len(title_guard)), title_guard),
        (25, 0x5865, b"\xff" * 3, bytes.fromhex("C3 00 7E")),
        (25, 0x7E00, b"\xff" * len(body), body),
    )


def build(source):
    if hashlib.sha256(source).hexdigest() != PARENT:
        raise ValueError("requires exact row-guard parent")
    result = bytearray(source)
    for bank, address, before, after in patches():
        start = offset(bank, address)
        assert len(before) == len(after)
        assert source[start:start + len(before)] == before, (bank, hex(address))
        result[start:start + len(after)] = after
    result[0x14E:0x150] = ((sum(result[:0x14E]) + sum(result[0x150:])) & 65535).to_bytes(2, 'big')
    assert hashlib.sha256(result).hexdigest() == CANDIDATE_SHA
    return bytes(result)


def authenticated_parent(candidate):
    """Reverse only the exact trial delta and authenticate the row-guard parent."""
    if hashlib.sha256(candidate).hexdigest() != CANDIDATE_SHA:
        raise ValueError("not the exact spike-death successor")
    parent = bytearray(candidate)
    for bank, address, before, after in patches():
        start = offset(bank, address)
        assert parent[start:start + len(after)] == after
        parent[start:start + len(before)] = before
    parent[0x14E:0x150] = ((sum(parent[:0x14E]) + sum(parent[0x150:])) & 65535).to_bytes(2, 'big')
    assert hashlib.sha256(parent).hexdigest() == PARENT
    return bytes(parent)


def authenticated_r536_parent(candidate):
    """Authenticate the complete reversible lineage back to exact r536."""
    from build_gameover_row_guard import authenticated_parent as row_parent
    return row_parent(authenticated_parent(candidate))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or (ROOT / 'tmp').resolve() not in out.parents:
        parser.error('output must be fresh below repository tmp/')
    rom = build(args.source.read_bytes())
    out.mkdir(parents=True)
    (out / 'candidate.gb').write_bytes(rom)
    receipt = dict(source_sha256=PARENT, candidate_sha256=hashlib.sha256(rom).hexdigest(),
                   release_qualified=False, scope='experimental bank13 death entry')
    (out / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
