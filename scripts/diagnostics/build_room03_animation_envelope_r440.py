"""Experimental full translated-cylinder envelope; no readiness claim."""
import hashlib
from build_stage5_dead_pointer_moves_r435 import ROOT, guard
from arena_position import _Asm

BASE = ROOT / 'tmp/compiled-tooth-bank-r438/candidate.gb'
SHA = '4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796'
OUT = ROOT / 'tmp/room03-animation-envelope-r440'
ENTRY = 20 * 0x4000 + 0x300
CAVE = 20 * 0x4000 + 0x380


def helper():
    a = _Asm()
    a.db(0xF0, 0xE5, 0xFE, 3)  # effective incoming room
    a.jr(0x20, 'original')
    a.db(0x79, 0xFE, 10)
    a.jr(0x20, 'left')
    # Right phase starts at column 8; include retracted columns 4..7.
    a.db(0x1B, 0x1B, 0x1B, 0x1B, 0x2B, 0x2B, 0x2B, 0x2B)
    a.jr(0x18, 'span')
    a.label('left')
    a.db(0xFE, 11)
    a.jr(0x20, 'original')
    a.label('span')
    a.db(0x0E, 14)  # both phases cover columns 4..17
    a.label('original')
    a.db(0xF0, 0x40, 0xCB, 0x7F, 0xC3, 0x04, 0x43)
    return a.finish()


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r438')
    code = helper()
    assert source[ENTRY:ENTRY+4] == bytes.fromhex('F0 40 CB 7F')
    assert source[CAVE:CAVE+len(code)] == b'\xff' * len(code)
    assert len(code) <= 0x80
    result = bytearray(source)
    result[ENTRY:ENTRY+4] = bytes.fromhex('C3 80 43 00')
    result[CAVE:CAVE+len(code)] = code
    guard.update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    result = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != result:
        raise ValueError('immutable candidate collision')
    target.write_bytes(result)
    print(hashlib.sha256(result).hexdigest())
