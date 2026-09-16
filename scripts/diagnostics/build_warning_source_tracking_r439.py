"""Use Stage1's unbanked context for exact source tracking during warning."""
import hashlib
import build_exact_source_dirty_r385 as prior
from build_stage5_dead_pointer_moves_r435 import ROOT, guard

BASE = ROOT / 'tmp/compiled-tooth-bank-r438/candidate.gb'
SHA = '4913e494538bd6dba6427516a6ad250d59b927c5255d4368adefbc9b3aa3f796'
OUT = ROOT / 'tmp/warning-source-tracking-r439'
OLD = bytes.fromhex('FA 80 D8 FE 02')
NEW = bytes.fromhex('F0 B7 FE 02 00')


def blocks():
    return ((24,0x7100,prior.store_helper(0x7100,advance=True)),
            (24,0x7140,prior.store_helper(0x7140,advance=False)),
            (21,0x4100,prior.decider()))


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r438')
    result = bytearray(source)
    for bank,address,code in blocks():
        offset = prior.offset(bank,address)
        assert source[offset:offset+len(code)] == code
        assert code.count(OLD) == 1
        assert bytes.fromhex('F0 BA B7') in code
        # Keep all branch offsets, flags after CP, stack operations and the
        # later-stage FFBA guard intact. FFB7=2 covers Stage1 normal/warning.
        result[offset:offset+len(code)] = code.replace(OLD,NEW)
    guard.update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    result = build(BASE.read_bytes())
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/'candidate.gb'
    if target.exists() and target.read_bytes()!=result:
        raise ValueError('immutable candidate collision')
    target.write_bytes(result)
    print(hashlib.sha256(result).hexdigest())
