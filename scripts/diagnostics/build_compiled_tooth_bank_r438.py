"""Experimental immutable tooth-bank selection in the Stage1 compiler LUT."""
import hashlib
from build_stage5_dead_pointer_moves_r435 import ROOT, guard

BASE = ROOT / 'tmp/single-recovery-art-r436/candidate.gb'
SHA = '37b4e9c8b4eed6621be28103d2df9a0ffb6484ca1f9d80497d956c8b8b99f2c3'
OUT = ROOT / 'tmp/compiled-tooth-bank-r438'
TABLE = 13 * 0x4000 + 0x3000
TEETH = (*range(0x64,0x6A), *range(0x74,0x7A))


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r436')
    assert all(source[TABLE+t] == 7 for t in TEETH)
    # The reviewed native and bulk compilers copy the full LUT byte. This
    # changes neither control flow nor neutral/body palette assignments.
    result = bytearray(source)
    for tile in TEETH:
        result[TABLE+tile] = 0x0F
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
