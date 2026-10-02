"""Remove obsolete HL->DE->HL moves around Stage5's BC-only pointer formula."""
import hashlib
from build_combined_dma_compile_r434 import ROOT, guard
from build_metatile_pointer_r406 import NEW

BASE = ROOT / 'tmp/combined-dma-compile-r434/candidate.gb'
SHA = 'e9d7f4417e4835b1dc9bf1fd68eb9651cee5d06bd6819e7a640ab853eb3117b1'
OUT = ROOT / 'tmp/stage5-dead-pointer-moves-r435'
SITE = 0x63800


def optimize(old):
    assert len(old) == 0x4B
    assert old[0x10:0x14] == bytes.fromhex('1A D5 5D 54')
    assert old[0x14:0x20] == NEW
    assert old[0x20:0x23] == bytes.fromhex('6B 62 0A')
    assert old[0x37:0x39] == bytes.fromhex('20 D6')
    assert old[0x45:0x47] == bytes.fromhex('20 C6')
    # NEW touches A, B, C, flags only. HL remains the tile destination;
    # DE remains saved on the stack until the original POP DE at old33.
    code = bytearray(old[:0x12] + old[0x14:0x20] + old[0x22:])
    code[0x34] = 0xDA  # JR NZ back to original0F (PUSH BC).
    code[0x42] = 0xCA  # JR NZ back to original0D (LD C,11).
    return bytes(code)


def build(source):
    if hashlib.sha256(source).hexdigest() != SHA:
        raise ValueError('requires exact r434')
    assert source[0x63380:0x6338B] == bytes.fromhex('F0 BA FE 04 CA 00 78 C3 00 73 FF')
    code = optimize(source[SITE:SITE + 0x4B])
    result = bytearray(source)
    result[SITE:SITE + 0x4B] = code.ljust(0x4B, b'\xff')
    guard.update_checksums(result)
    return bytes(result)


if __name__ == '__main__':
    rom = build(BASE.read_bytes())
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'candidate.gb'
    if target.exists() and target.read_bytes() != rom:
        raise ValueError('immutable candidate collision')
    target.write_bytes(rom)
    print(hashlib.sha256(rom).hexdigest())
