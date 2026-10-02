"""Track exact source changes throughout Stage1, including native scene0A."""
import hashlib
from pathlib import Path
from build_stage1_fast_final_window_selector_r363 import update_checksums

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT/'tmp/stage2-seven-rows-r441/candidate.gb'
# Exact reviewed r441, not an arbitrary candidate with matching local bytes.
SHA = '44ac932aca17701ae97596fd511f77fa0eae8f98761d61e618262a7f71bf9702'
OUT = ROOT/'tmp/stage1-subscene-tracking-r442'
SITES = (24*0x4000+0x3000, 21*0x4000+0x100)
OLD = bytes.fromhex('FA 80 D8 FE 02')
NEW = bytes.fromhex('F0 B7 FE 02 00')


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r441')
    result = bytearray(source)
    for offset in SITES:
        assert source[offset:offset+5] == OLD
        # Same-width predicate; preserve both absolute branches and FFBA=0
        # later-stage guard. FFB7 is the compiler's existing stage context.
        assert source[offset+5] == 0xC2
        assert source[offset+8:offset+11] == bytes.fromhex('F0 BA B7')
        result[offset:offset+5] = NEW
    update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT/'candidate.gb'
    if path.exists() and path.read_bytes() != rom:
        raise ValueError('immutable candidate collision')
    path.write_bytes(rom)
    print(hashlib.sha256(rom).hexdigest())
